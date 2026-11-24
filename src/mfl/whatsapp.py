"""Traduz eventos da Evolution em toques, respostas e tiques de leads.

Regra de privacidade: mensagem de número que não é lead é descartada sem gravar nada.
"""

import sqlite3
from datetime import datetime, timedelta

import structlog

from mfl.classifica import classificar
from mfl.db import FUSO, agora, tel_hash
from mfl.fone import de_jid

log = structlog.get_logger()

IGNORAR_TIPOS = {"reactionMessage", "protocolMessage", "pollUpdateMessage", "senderKeyDistributionMessage"}
ACK = {"SERVER_ACK": "servidor", "DELIVERY_ACK": "entregue", "READ": "lida", "PLAYED": "lida", "ERROR": "falha",
       "2": "servidor", "3": "entregue", "4": "lida", "5": "lida", "0": "falha"}
ORDEM_ACK = ["servidor", "entregue", "lida"]
# Toque novo num estado de cadência só avança a etapa se o anterior tiver mais de 24h:
# duas mensagens seguidas no mesmo dia são o mesmo D0.
AVANCO = {"novo": "enviado_d0", "qualificado": "enviado_d0", "na_fila": "enviado_d0", "frio": "enviado_d0",
          "enviado_d0": "d3", "d3": "d7"}
VIRA_RESPONDEU = {"novo", "qualificado", "na_fila", "enviado_d0", "d3", "d7", "frio"}
ABRINDO_VALIDO = timedelta(hours=1)


def processar(con: sqlite3.Connection, corpo: dict) -> str:
    """Devolve o que foi feito (para log e teste). Nunca levanta por payload estranho."""
    evento = str(corpo.get("event", "")).lower().replace("_", ".")
    dados = corpo.get("data")
    dados = dados[0] if isinstance(dados, list) and dados else dados
    if not isinstance(dados, dict):
        return "ignorado"
    if evento == "connection.update":
        con.execute("INSERT OR REPLACE INTO estado VALUES ('evolution_conexao',?,?)",
                    (str(dados.get("state", "")), agora()))
        con.commit()
        return "conexao"
    if evento == "messages.update":
        return _ack(con, dados)
    if evento == "messages.upsert":
        return _mensagem(con, dados)
    return "ignorado"


def registrar_envio(con: sqlite3.Connection, entity_id: str, texto: str, momento: str,
                    msg_id: str | None = None, template_id: str | None = None) -> bool:
    """Ponto único de envio (webhook ou botão manual): grava o toque e anda a cadência.

    Sem template explícito, usa o que a UI marcou ao abrir o WhatsApp na última hora.
    """
    lead = con.execute("SELECT status FROM entity WHERE entity_id=?", (entity_id,)).fetchone()
    anterior = con.execute("SELECT max(enviado_em) FROM touch WHERE entity_id=?", (entity_id,)).fetchone()[0]
    template_id = template_id or _template_aberto(con, entity_id)
    cur = con.execute(
        "INSERT OR IGNORE INTO touch (entity_id, canal, template_id, texto, enviado_em, wa_msg_id)"
        " VALUES (?,?,?,?,?,?)", (entity_id, "whatsapp", template_id, texto, momento, msg_id))
    if not cur.rowcount:
        return False
    if lead["status"] == "opt_out":
        log.warning("envio_para_opt_out", entity_id=entity_id)
    elif lead["status"] in AVANCO and _passou_24h(anterior, momento, lead["status"]):
        mudar_status(con, entity_id, AVANCO[lead["status"]])
    con.commit()
    return True


def marcar_opt_out(con: sqlite3.Connection, entity_id: str, motivo: str) -> None:
    """Irreversível sem ação manual: bloqueio por hash sobrevive a reimportação."""
    tel = con.execute("SELECT tel1 FROM entity WHERE entity_id=?", (entity_id,)).fetchone()["tel1"]
    mudar_status(con, entity_id, "opt_out")
    con.execute("UPDATE entity SET opt_out=1 WHERE entity_id=?", (entity_id,))
    if tel:
        con.execute("INSERT OR IGNORE INTO bloqueio VALUES (?,?,?)", (tel_hash(tel), motivo, agora()))
    con.commit()


def mudar_status(con: sqlite3.Connection, entity_id: str, novo: str, motivo: str | None = None) -> None:
    con.execute("UPDATE entity SET status=?, motivo_descarte=coalesce(?, motivo_descarte), atualizado_em=?"
                " WHERE entity_id=?", (novo, motivo, agora(), entity_id))
    log.info("status", entity_id=entity_id, status=novo)


def _mensagem(con: sqlite3.Connection, msg: dict) -> str:
    chave = msg.get("key") or {}
    jid = chave.get("remoteJid") or ""
    if jid.endswith("@lid"):
        jid = chave.get("remoteJidAlt") or chave.get("senderPn") or jid
    if msg.get("messageType") in IGNORAR_TIPOS:
        return "ignorado"
    e164 = de_jid(jid)
    lead = e164 and con.execute("SELECT entity_id, status FROM entity WHERE tel1=?", (e164,)).fetchone()
    if not lead:
        return "nao_lead"

    texto, momento, msg_id = _texto(msg), _momento(msg.get("messageTimestamp")), chave.get("id")
    if chave.get("fromMe"):
        return "toque" if registrar_envio(con, lead["entity_id"], texto, momento, msg_id) else "repetido"

    rotulo = classificar(texto)
    cur = con.execute(
        "INSERT OR IGNORE INTO reply (entity_id, texto, classificacao, recebido_em, wa_msg_id) VALUES (?,?,?,?,?)",
        (lead["entity_id"], texto, rotulo, momento, msg_id),
    )
    if cur.rowcount and rotulo == "opt_out":
        marcar_opt_out(con, lead["entity_id"], "pediu_sair")
    elif cur.rowcount and lead["status"] in VIRA_RESPONDEU:
        mudar_status(con, lead["entity_id"], "respondeu")
    con.commit()
    return "resposta" if cur.rowcount else "repetido"


def _ack(con: sqlite3.Connection, dados: dict) -> str:
    """Só sobe de nível (servidor → entregue → lida); 1 tique parado é o sinal de bloqueio."""
    chave = dados.get("key") or {}
    msg_id = dados.get("keyId") or dados.get("messageId") or chave.get("id")
    bruto = (dados.get("update") or {}).get("status", dados.get("status"))
    ack = ACK.get(str(bruto).upper())
    if not msg_id or not ack:
        return "ignorado"
    atual = con.execute("SELECT ack FROM touch WHERE wa_msg_id=?", (msg_id,)).fetchone()
    if not atual:
        return "nao_lead"
    sobe = ack == "falha" or atual["ack"] not in ORDEM_ACK or ORDEM_ACK.index(ack) > ORDEM_ACK.index(atual["ack"])
    if sobe and atual["ack"] != "falha":
        con.execute("UPDATE touch SET ack=?, ack_em=? WHERE wa_msg_id=?", (ack, agora(), msg_id))
        con.commit()
    return "ack"


def _template_aberto(con: sqlite3.Connection, entity_id: str) -> str | None:
    linha = con.execute("SELECT valor, atualizado_em FROM estado WHERE chave=?", (f"abrindo:{entity_id}",)).fetchone()
    if not linha:
        return None
    con.execute("DELETE FROM estado WHERE chave=?", (f"abrindo:{entity_id}",))
    recente = datetime.now(FUSO) - datetime.fromisoformat(linha["atualizado_em"]) < ABRINDO_VALIDO
    return linha["valor"] if recente else None


def _texto(msg: dict) -> str:
    conteudo = msg.get("message") or {}
    return (
        conteudo.get("conversation")
        or (conteudo.get("extendedTextMessage") or {}).get("text")
        or (conteudo.get("imageMessage") or {}).get("caption")
        or (conteudo.get("videoMessage") or {}).get("caption")
        or f"[{msg.get('messageType') or 'midia'}]"
    )


def _momento(ts: object) -> str:
    try:
        return datetime.fromtimestamp(int(ts), FUSO).isoformat(timespec="seconds")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return agora()


def _passou_24h(anterior: str | None, momento: str, status: str) -> bool:
    if status in ("novo", "qualificado", "na_fila", "frio") or anterior is None:
        return True
    return datetime.fromisoformat(momento) - datetime.fromisoformat(anterior) > timedelta(hours=24)
