"""Acesso ao SQLite operacional."""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[2]
SCHEMA = RAIZ / "db" / "schema.sql"
FUSO = ZoneInfo("America/Sao_Paulo")
LOTE = 100


def agora() -> str:
    """Horário local do operador: cadência e janela de envio são em hora de Porto Alegre."""
    return datetime.now(FUSO).isoformat(timespec="seconds")


def conectar(caminho: Path | None = None) -> sqlite3.Connection:
    """Aplica o schema a cada conexão (idempotente) para que nenhum job rode em banco velho.

    busy_timeout porque UI, webhook e jobs escrevem no mesmo arquivo.
    """
    caminho = caminho or Path(os.environ.get("MFL_DB", RAIZ / "db" / "leads.db"))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA.read_text())
    return con
