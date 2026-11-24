"""Fila do dia, teto, janela de envio, bloqueio estimado e transições por tempo."""

import sqlite3
import tomllib
from datetime import date, datetime, time, timedelta

from mfl import score
from mfl.db import FUSO, RAIZ, agora

TETOS = RAIZ / "cfg" / "tetos.toml"


def config() -> dict:
    with TETOS.open("rb") as f:
        return tomllib.load(f)


def _dia(d: date) -> str:
    return d.isoformat()


def atualizar(con: sqlite3.Connection, hoje: date) -> None:
    """Transições que dependem só do tempo: rodam a cada carga da fila (barato e sem timer)."""
    momento = agora()
    con.execute(
        "UPDATE entity SET status='frio', atualizado_em=? WHERE status='d7' AND"
        " (SELECT substr(max(enviado_em),1,10) FROM touch t WHERE t.entity_id=entity.entity_id) <= ?",
        (momento, _dia(hoje - timedelta(days=3))),
    )
    con.execute("UPDATE entity SET status='frio', atualizado_em=? WHERE status='objecao' AND substr(atualizado_em,1,10) <= ?",
                (momento, _dia(hoje - timedelta(days=7))))
    con.execute("UPDATE entity SET status='na_fila', atualizado_em=? WHERE status='frio' AND substr(atualizado_em,1,10) <= ?",
                (momento, _dia(hoje - timedelta(days=60))))
    con.commit()


def feitos(con: sqlite3.Connection, hoje: date) -> int:
    """Abordagens da fila no dia. Resposta a quem já conversa (sem template) não gasta o teto."""
    return con.execute("SELECT count(DISTINCT entity_id) FROM touch WHERE template_id IS NOT NULL AND substr(enviado_em,1,10)=?",
                       (_dia(hoje),)).fetchone()[0]


def bloqueio(con: sqlite3.Connection, inicio: datetime, fim: datetime) -> tuple[float, int]:
    """(taxa, envios) entre inicio e fim: tique parado em servidor/nenhum + opt-outs, sobre envios capturados.

    Só conta toque com id do WhatsApp (o manual não tem tique) e com mais de 24h (tempo de entregar).
    """
    limite = min(fim, datetime.now(FUSO) - timedelta(hours=24)).isoformat(timespec="seconds")
    ini = inicio.isoformat(timespec="seconds")
    envios, presos = con.execute(
        "SELECT count(*), sum(coalesce(ack,'servidor')='servidor') FROM touch"
        " WHERE wa_msg_id IS NOT NULL AND enviado_em >= ? AND enviado_em < ?", (ini, limite)).fetchone()
    saidas = con.execute("SELECT count(*) FROM reply WHERE classificacao='opt_out' AND recebido_em >= ? AND recebido_em < ?",
                         (ini, fim.isoformat(timespec="seconds"))).fetchone()[0]
    return ((presos or 0) + saidas) / envios if envios else 0.0, envios


def teto(con: sqlite3.Connection, cfg: dict, hoje: date) -> tuple[int, str | None]:
    """(teto, motivo do teto reduzido)."""
    primeiro = con.execute("SELECT min(substr(enviado_em,1,10)) FROM touch").fetchone()[0]
    if primeiro is None or date.fromisoformat(primeiro) > hoje - timedelta(days=7):
        return cfg["semana_1"], "semana 1"
    fim = datetime.combine(hoje, time.min, FUSO)
    taxa, _ = bloqueio(con, fim - timedelta(days=7), fim)
    if taxa >= cfg["bloqueio_max"]:
        return cfg["semana_1"], f"bloqueio de {taxa:.0%} nos últimos 7 dias"
    return cfg["depois"], None


def na_janela(cfg: dict, quando: datetime) -> bool:
    faixas = cfg["janela"]["segunda"] if quando.weekday() == 0 else (
        cfg["janela"]["terca_a_sexta"] if quando.weekday() <= 4 else [])
    hhmm = quando.strftime("%H:%M")
    return any(ini <= hhmm < fim for ini, fim in (f.split("-") for f in faixas))


def fila(con: sqlite3.Connection, hoje: date, vagas: int) -> list[tuple[sqlite3.Row, str]]:
    """(lead, etapa) para hoje: follow-ups vencidos primeiro, depois leads novos por score."""
    if vagas <= 0:
        return []
    fora_hoje = (
        " AND e.entity_id NOT IN (SELECT entity_id FROM touch WHERE substr(enviado_em,1,10)=:hoje)"
        " AND e.entity_id NOT IN (SELECT entity_id FROM queue WHERE kind='pular' AND done=0 AND next_at > :hoje)"
    )
    vencidos = con.execute(
        "SELECT e.*, CASE e.status WHEN 'enviado_d0' THEN 'd3' ELSE 'd7' END AS etapa FROM entity e"
        " WHERE e.status IN ('enviado_d0','d3') AND e.opt_out=0" + fora_hoje +
        " AND (SELECT substr(max(enviado_em),1,10) FROM touch t WHERE t.entity_id=e.entity_id)"
        "     <= CASE e.status WHEN 'enviado_d0' THEN :d3 ELSE :d7 END"
        " ORDER BY e.score DESC LIMIT :vagas",
        {"hoje": _dia(hoje), "d3": _dia(hoje - timedelta(days=3)), "d7": _dia(hoje - timedelta(days=4)), "vagas": vagas},
    ).fetchall()
    novos = con.execute(
        "SELECT e.*, 'd0' AS etapa FROM entity e WHERE e.status IN ('novo','qualificado','na_fila')"
        " AND e.tel1 IS NOT NULL AND e.opt_out=0 AND e.score >= :corte" + fora_hoje +
        " ORDER BY e.score DESC, e.criado_em, e.entity_id LIMIT :vagas",
        {"hoje": _dia(hoje), "vagas": vagas - len(vencidos), "corte": score.config()["corte"]},
    ).fetchall()
    return [(l, l["etapa"]) for l in [*vencidos, *novos]]


def pular(con: sqlite3.Connection, entity_id: str, hoje: date) -> None:
    con.execute("INSERT INTO queue (entity_id, kind, next_at) VALUES (?, 'pular', ?)",
                (entity_id, _dia(hoje + timedelta(days=1))))
    con.commit()
