import json
import sqlite3

import pytest

from conftest import criar_lead
from mfl import db, maps, webhook, whatsapp
from mfl.classifica import classificar
from mfl.fone import de_jid, para_e164

LEAD = "+5551999990001"
JID_LEAD = "555199990001@s.whatsapp.net"  # formato antigo, sem o nono dígito


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "t.db")
    criar_lead(c, "Pizzaria Teste", LEAD)
    return c


def upsert(jid, texto, from_me, msg_id, ts=1_764_000_000, **extra):
    return {"event": "messages.upsert", "data": {
        "key": {"remoteJid": jid, "fromMe": from_me, "id": msg_id, **extra},
        "message": {"conversation": texto}, "messageType": "conversation", "messageTimestamp": ts}}


def status(con):
    return con.execute("SELECT status FROM entity WHERE tel1=?", (LEAD,)).fetchone()[0]


def conta(con, tabela):
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def test_telefone_e_jid():
    assert para_e164("51 8571-1759") == "+5551985711759"  # celular antigo ganha o 9
    assert para_e164("(51) 3333-4444") == "+555133334444"  # fixo não muda
    assert de_jid(JID_LEAD) == LEAD
    assert de_jid("123456789@lid") is None
    assert de_jid("120363000@g.us") is None


@pytest.mark.parametrize("texto,rotulo", [
    ("SAIR", "opt_out"), ("Sair.", "opt_out"), ("Bom dia!\nSAIR", "opt_out"), ("Claro", "interesse"), ("por favor não me mande mais", "opt_out"),
    ("Quanto custa?", "preco"), ("já uso o Goomer", "ja_tenho"), ("não tenho interesse", "nao"),
    ("como funciona?", "interesse"), ("bom dia", None), ("vou sair às 15h", None),
])
def test_classificar(texto, rotulo):
    assert classificar(texto) == rotulo


def test_envio_vira_toque_e_cadencia(con):
    assert whatsapp.processar(con, upsert(JID_LEAD, "Oi, tudo bem?", True, "A1")) == "toque"
    assert status(con) == "enviado_d0"
    whatsapp.processar(con, upsert(JID_LEAD, "complemento", True, "A2", ts=1_764_000_600))
    assert status(con) == "enviado_d0"  # mesmo dia continua D0
    whatsapp.processar(con, upsert(JID_LEAD, "D3", True, "A3", ts=1_764_000_000 + 3 * 86400))
    assert status(con) == "d3"
    assert whatsapp.processar(con, upsert(JID_LEAD, "Oi, tudo bem?", True, "A1")) == "repetido"
    assert conta(con, "touch") == 3


def test_resposta_classifica_e_opt_out_bloqueia(con):
    whatsapp.processar(con, upsert(JID_LEAD, "Oi", True, "A1"))
    assert whatsapp.processar(con, upsert(JID_LEAD, "quanto custa?", False, "B1")) == "resposta"
    assert status(con) == "respondeu"
    whatsapp.processar(con, upsert(JID_LEAD, "SAIR", False, "B2"))
    assert status(con) == "opt_out"
    assert db.bloqueado(con, LEAD)



def test_opt_out_nao_volta_pelo_maps(con, tmp_path):
    whatsapp.processar(con, upsert(JID_LEAD, "SAIR", False, "B2"))
    for tabela in ("source_record", "reply", "touch", "entity"):
        con.execute(f"DELETE FROM {tabela}")
    arquivo = tmp_path / "o.json"
    arquivo.write_text(json.dumps({"place_id": "PX", "title": "X", "phone": "51 99999-0001", "status": "",
                                   "complete_address": {"city": "Porto Alegre"}}))
    contagem = maps.ingerir(con, arquivo, {"nome": "Centro", "municipio": "Porto Alegre"}, ["PORTO ALEGRE"], [])
    assert contagem["descartados"] == 1 and conta(con, "entity") == 0


def test_nao_lead_grupo_e_lid_nao_gravam_nada(con):
    antes = (conta(con, "touch"), conta(con, "reply"))
    assert whatsapp.processar(con, upsert("5551988887777@s.whatsapp.net", "oi mãe", False, "C1")) == "nao_lead"
    assert whatsapp.processar(con, upsert("120363000@g.us", "grupo", False, "C2")) == "nao_lead"
    assert whatsapp.processar(con, upsert("999@lid", "lid sem alt", False, "C3")) == "nao_lead"
    assert (conta(con, "touch"), conta(con, "reply")) == antes


def test_lid_com_alt_casa_lead(con):
    assert whatsapp.processar(con, upsert("999@lid", "oi", False, "D1", remoteJidAlt=JID_LEAD)) == "resposta"


def test_ack_so_sobe(con):
    whatsapp.processar(con, upsert(JID_LEAD, "Oi", True, "A1"))
    for st in ("SERVER_ACK", "READ", "DELIVERY_ACK"):
        whatsapp.processar(con, {"event": "messages.update", "data": {"keyId": "A1", "status": st}})
    assert con.execute("SELECT ack FROM touch").fetchone()[0] == "lida"


def test_conexao_vira_estado(con):
    whatsapp.processar(con, {"event": "connection.update", "data": {"state": "close"}})
    assert con.execute("SELECT valor FROM estado WHERE chave='evolution_conexao'").fetchone()[0] == "close"


def test_migracao_em_banco_v1(tmp_path):
    caminho = tmp_path / "v1.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript(db.SCHEMA.read_text())
    antigo.close()
    novo = db.conectar(caminho)
    ultima = max(int(p.name[:3]) for p in db.MIGRACOES.glob("*.sql"))
    assert novo.execute("PRAGMA user_version").fetchone()[0] == ultima
    assert "wa_msg_id" in {r[1] for r in novo.execute("PRAGMA table_info(touch)")}
    db.conectar(caminho)  # reabrir não reaplica


def test_webhook_exige_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MFL_WEBHOOK_TOKEN", "segredo")
    cliente = webhook.criar_app(tmp_path / "w.db").test_client()
    assert cliente.post("/webhook/evolution?token=errado", json={}).status_code == 403
    assert cliente.post("/webhook/evolution?token=segredo", json={"event": "x"}).status_code == 204
