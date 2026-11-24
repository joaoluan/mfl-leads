"""Google Maps via o binário gosom/google-maps-scraper (versão fixa, SHA conferido) e ingestão.

Telefone do Maps é do estabelecimento: celular válido torna o lead apto para a fila; fixo fica em
`enriquecimento` (o WhatsApp pode aparecer depois pelo Instagram).
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import structlog

from mfl import cnpj_icp, ifood, resolve
from mfl.classifica import normalizar
from mfl.db import LOTE, RAIZ, agora, bloqueado
from mfl.fone import celular as e_celular, para_e164, whatsapp_em

log = structlog.get_logger()
BINARIO = RAIZ / "bin" / "google-maps-scraper"
SHA = RAIZ / "bin" / "SHA256SUMS"
CONSULTAS = RAIZ / "cfg" / "maps_consultas.txt"
TIMEOUT = 3600  # depth 3: bairro grande (até 81 células) passa de 30 min
PROFUNDIDADE = 3  # rolagens por busca; medido no Moinhos: depth 1 = 87 lugares, depth 3 = 119 (24/11/2026)
ESPERA_SAIDA, INTERVALO = 15, 3  # segundos (variáveis para o teste)
FECHADO = re.compile(r"fechad[oa] (permanentemente|temporariamente)", re.I)
EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


class Incompleto(Exception):
    """Estourou o tempo: o que veio é ingerido, mas o bairro fica pendente para a próxima noite."""

    def __init__(self, saida: Path):
        super().__init__(f"tempo esgotado; {saida.name} parcial")
        self.saida = saida


def conferir_binario() -> None:
    """Não roda binário que não seja o registrado em bin/SHA256SUMS."""
    esperado = SHA.read_text().split()[0]
    achado = hashlib.sha256(BINARIO.read_bytes()).hexdigest()
    if achado != esperado:
        raise RuntimeError(f"SHA256 do {BINARIO.name} não confere ({achado[:12]}… != {esperado[:12]}…)")


def rodar(bairro: dict, saida: Path, log_arquivo: Path, consultas: Path | None = None) -> Path:
    """Uma execução por bairro. A v1.20.0 termina o trabalho mas às vezes não sai do processo:
    ao ver 'scrapemate exited' no log, espera um pouco e encerra."""
    conferir_binario()
    saida.unlink(missing_ok=True)
    if consultas is None:
        busca = ["-grid-bbox", bairro["bbox"], "-grid-cell", str(bairro["celula_km"]), "-grid-strict",
                 "-depth", str(PROFUNDIDADE), "-c", "4"]
    else:
        lat1, lon1, lat2, lon2 = map(float, bairro["bbox"].split(","))
        busca = ["-geo", f"{(lat1 + lat2) / 2},{(lon1 + lon2) / 2}", "-depth", "1", "-c", "2"]
    timeout = TIMEOUT if consultas is None else min(TIMEOUT, 300)
    cmd = [str(BINARIO), "-input", str(consultas or CONSULTAS), "-results", str(saida), "-json", *busca,
           "-zoom", "16", "-email", "-lang", "pt", "-exit-on-inactivity", "3m"]
    for pasta in (saida.parent, log_arquivo.parent):
        pasta.mkdir(parents=True, exist_ok=True)
    inicio = time.monotonic()
    with log_arquivo.open("w") as registro:
        proc = subprocess.Popen(cmd, stdout=registro, stderr=subprocess.STDOUT,
                                env={**os.environ, "DISABLE_TELEMETRY": "1"})
        terminou_em = None
        while proc.poll() is None:
            time.sleep(INTERVALO)
            if terminou_em is None and "scrapemate exited" in log_arquivo.read_text(errors="replace"):
                terminou_em = time.monotonic()
            atrasado = time.monotonic() - inicio > timeout
            if atrasado or (terminou_em and time.monotonic() - terminou_em > ESPERA_SAIDA):
                proc.terminate()
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if atrasado:
                    log.error("maps_timeout", bairro=bairro["nome"], segundos=timeout)
    if not saida.exists():
        raise RuntimeError(f"Maps não gerou {saida.name}; veja {log_arquivo}")
    if time.monotonic() - inicio > timeout:
        raise Incompleto(saida)
    return saida


def _email(lugar: dict) -> str | None:
    """Regex + MX: e-mail de domínio sem servidor de e-mail não serve para nada."""
    for email in lugar.get("emails") or []:
        if EMAIL.match(email or ""):
            try:
                mx = subprocess.run(["dig", "+short", "+time=3", "+tries=2", "MX", email.split("@")[1]],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
            except subprocess.TimeoutExpired:
                continue
            if mx:
                return email.lower()
    return None


def _dados(lugar: dict, bairro: dict) -> dict:
    endereco = lugar.get("complete_address") or {}
    fone = para_e164(lugar.get("phone") or "")
    links = " ".join([lugar.get("web_site") or "", *[o.get("link") or "" for o in lugar.get("order_online") or []]])
    zap = whatsapp_em(links)
    tel = zap or fone
    celular = bool(zap) or e_celular(tel)  # "_celular" = apto para WhatsApp
    titulo = (lugar.get("title") or "").strip()
    return {
        "_fonte": "maps", "_celular": celular, "_whatsapp": bool(zap), "place_id": lugar["place_id"], "nome": titulo, "fantasia": titulo,
        "_ifood_ids": _ids_ifood(lugar),
        "categoria": lugar.get("category") or None, "uf": "RS", "municipio": endereco.get("city") or bairro["municipio"],
        "bairro": endereco.get("borough") or bairro["nome"],
        "cep": re.sub(r"\D", "", endereco.get("postal_code") or "") or None,
        "endereco": re.sub(rf"^{re.escape(titulo)} - ", "", lugar.get("address") or "") or None,
        "tel1": tel, "tel2": fone if zap and fone != zap else None, "site": lugar.get("web_site") or None, "nota": lugar.get("review_rating"),
        "avaliacoes": lugar.get("review_count"),
    }


def _ids_ifood(lugar: dict) -> list[str]:
    links = [lugar.get("web_site") or "", *[o.get("link") or "" for o in lugar.get("order_online") or []]]
    return sorted({identificador for link in links if (identificador := ifood.id_da_url(link))})


def _unir_ifood(con: sqlite3.Connection, lugar: dict, existente: sqlite3.Row) -> None:
    """UUID exato permite absorver descoberta provisória, preservando o lead já conhecido no Maps."""
    ids = _ids_ifood(lugar)
    if not ids:
        return
    candidato, _ = resolve.melhor_candidato(con, {"_ifood_ids": ids}, set(), existente["entity_id"])
    if candidato is not None and candidato["status"] == "enriquecimento" and candidato["tel1"] is None and not candidato["opt_out"]:
        if not con.execute("SELECT 1 FROM touch WHERE entity_id=? UNION ALL SELECT 1 FROM reply WHERE entity_id=?",
                           (candidato["entity_id"], candidato["entity_id"])).fetchone():
            resolve.fundir(con, existente["entity_id"], candidato["entity_id"])


def _descarte(lugar: dict, dados: dict, municipios: set[str], franquias: re.Pattern | None) -> str | None:
    if FECHADO.search(f"{lugar.get('status', '')} {lugar.get('description', '')}"):
        return "fechado"
    if normalizar(dados["municipio"] or "").upper() not in municipios:
        return "fora_da_regiao"
    if franquias and franquias.search(normalizar(dados["nome"])):
        return "franquia"
    return None


def ingerir(con: sqlite3.Connection, arquivo: Path, bairro: dict, municipios: list[str],
            franquias: list[str]) -> dict[str, int]:
    """Idempotente por place_id. Cada lugar novo é resolvido contra o que já existe (CNPJ, Instagram)."""
    contagem = {"novos": 0, "vinculados": 0, "revisao": 0, "repetidos": 0, "descartados": 0, "aptos": 0}
    alvo = {normalizar(m).upper() for m in municipios}
    padrao = re.compile(r"\b(" + "|".join(re.escape(t) for t in franquias) + r")\b") if franquias else None
    compartilhados = resolve.telefones_compartilhados(con)
    momento = agora()
    linhas = [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]
    for n, lugar in enumerate(linhas, start=1):
        if not lugar.get("place_id"):
            contagem["repetidos"] += 1
            continue
        existente = con.execute("SELECT entity_id FROM source_record WHERE source='maps' AND source_key=?", (lugar["place_id"],)).fetchone()
        if existente:
            _unir_ifood(con, lugar, existente)
            contagem["repetidos"] += 1
            continue
        dados = _dados(lugar, bairro)
        if dados["tel1"] and bloqueado(con, dados["tel1"]):  # pediu SAIR: não volta nem fica gravado
            contagem["descartados"] += 1
            continue
        motivo = _descarte(lugar, dados, alvo, padrao)
        candidato, nota = (None, 0.0) if motivo else resolve.melhor_candidato(con, dados, compartilhados)
        if candidato is not None and (candidato["opt_out"] or candidato["status"] == "opt_out"):
            contagem["descartados"] += 1
            continue
        if candidato is not None and nota >= resolve.VINCULA:
            entity_id = candidato["entity_id"]
            resolve.preencher(con, entity_id, {**dados, "email": _email(lugar)})
            contagem["vinculados"] += 1
        else:
            entity_id = str(uuid.uuid4())
            status = "descartado" if motivo else ("novo" if dados["_celular"] else "enriquecimento")
            colunas = [c for c in dados if not c.startswith("_")]
            con.execute(
                f"INSERT INTO entity (entity_id, {', '.join(colunas)}, email, status, motivo_descarte, criado_em,"
                f" atualizado_em) VALUES (?, {', '.join('?' * len(colunas))}, ?, ?, ?, ?, ?)",
                (entity_id, *[dados[c] for c in colunas], None if motivo else _email(lugar), status, motivo, momento, momento))
            contagem["descartados" if motivo else "novos"] += 1
            if candidato is not None and nota >= resolve.REVISA:
                con.execute("INSERT INTO revisao (a, b, score) VALUES (?,?,?)", (entity_id, candidato["entity_id"], nota))
                contagem["revisao"] += 1
        if dados["tel1"]:
            con.execute("INSERT OR REPLACE INTO validacao VALUES (?,?,?)",
                        (dados["tel1"], "whatsapp" if dados["_whatsapp"] else
                         "celular" if dados["_celular"] else "fixo", momento))
        contagem["aptos"] += dados["_celular"] and not motivo
        raw = json.dumps(lugar, ensure_ascii=False, sort_keys=True)
        con.execute(
            "INSERT INTO source_record (source, source_key, entity_id, raw_json, url, captured_at, hash, match_score)"
            " VALUES ('maps',?,?,?,?,?,?,?)",
            (lugar["place_id"], entity_id, raw, lugar.get("link"), momento, hashlib.sha256(raw.encode()).hexdigest(),
             nota or None))
        if n % LOTE == 0:
            con.commit()
    con.commit()
    log.info("maps_ingerido", bairro=bairro["nome"], **contagem)
    return contagem


def alvos_ifood(con: sqlite3.Connection, cidade: str | None = None) -> list[sqlite3.Row]:
    """Alvos vencidos também entram na noite quando os bairros das duas fontes estão em dia."""
    hoje = date.fromisoformat(agora()[:10])
    return con.execute(
        "SELECT e.entity_id,coalesce(e.fantasia,e.nome) AS nome,e.municipio,q.id AS fila_id"
        " FROM entity e LEFT JOIN queue q ON q.entity_id=e.entity_id AND q.kind='maps_ifood'"
        " WHERE e.status='enriquecimento' AND e.opt_out=0 AND e.place_id IS NULL"
        " AND (? IS NULL OR lower(e.municipio) IN (lower(?),lower(?)))"
        " AND EXISTS (SELECT 1 FROM source_record s WHERE s.entity_id=e.entity_id AND s.source='ifood')"
        " AND (q.id IS NULL OR (q.done=0 AND q.next_at<=?)) ORDER BY coalesce(q.next_at,''),e.entity_id LIMIT ?",
        (cidade, cidade, normalizar(cidade or ""), hoje.isoformat(), 30 if cidade else -1)).fetchall()


def completar_ifood(con: sqlite3.Connection, chave: str, bairro: dict) -> int:
    """Busca até 30 descobertas do iFood pelo nome/cidade, com tentativas espaçadas na fila existente."""
    hoje = date.fromisoformat(agora()[:10])
    leads = alvos_ifood(con, bairro["municipio"])
    if not leads:
        return 0
    filas = []
    for lead in leads:
        fila_id = lead["fila_id"]
        if fila_id is None:
            fila_id = con.execute("INSERT INTO queue(entity_id,kind,next_at) VALUES (?,'maps_ifood',?)",
                                  (lead["entity_id"], hoje.isoformat())).lastrowid
        filas.append(fila_id)
    # Reserva antes da rede: outro bairro não repete os mesmos alvos se a busca cair.
    con.executemany("UPDATE queue SET tries=tries+1,next_at=? WHERE id=?",
                    [((hoje + timedelta(days=1)).isoformat(), i) for i in filas])
    con.commit()
    pasta = RAIZ / "data" / "maps" / "ifood" / hoje.isoformat()
    pasta.mkdir(parents=True, exist_ok=True)
    consultas = pasta / f"{chave}.txt"
    consultas.write_text("\n".join(" ".join(f"{l['nome']} {l['municipio']} RS".split()) for l in leads) + "\n", encoding="utf-8")
    municipios, franquias = cnpj_icp.recorte()["municipios"], cnpj_icp.termos_franquia()
    try:
        saida = rodar(bairro, pasta / f"{chave}.json", RAIZ / "logs" / "maps" / f"ifood-{chave}.log", consultas)
    except Incompleto as parcial:
        ingerir(con, parcial.saida, bairro, municipios, franquias)
        raise
    ingerir(con, saida, bairro, municipios, franquias)
    con.executemany(
        "UPDATE queue SET next_at=?,done=EXISTS (SELECT 1 FROM entity e WHERE e.entity_id=queue.entity_id"
        " AND (e.place_id IS NOT NULL OR e.status<>'enriquecimento' OR e.opt_out=1)) WHERE id=?",
        [((hoje + timedelta(days=7)).isoformat(), i) for i in filas])
    con.commit()
    log.info("ifood_maps_completado", bairro=chave, buscados=len(leads))
    return len(leads)
