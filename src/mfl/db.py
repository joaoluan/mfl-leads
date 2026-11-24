"""Acesso ao SQLite operacional."""

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[2]
SCHEMA = RAIZ / "db" / "schema.sql"
MIGRACOES = RAIZ / "db" / "migracoes"
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
    _migrar(con)
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """schema.sql é a base (v1) e não muda mais; cada mudança vira db/migracoes/NNN_*.sql.

    BEGIN IMMEDIATE + releitura da versão: webhook e CLI podem abrir o banco ao mesmo tempo.
    """
    con.execute("BEGIN IMMEDIATE")
    try:
        versao = con.execute("PRAGMA user_version").fetchone()[0]
        for arquivo in sorted(MIGRACOES.glob("[0-9][0-9][0-9]_*.sql")):
            numero = int(arquivo.name[:3])
            if numero <= versao:
                continue
            for comando in arquivo.read_text().split(";"):
                if comando.strip():
                    con.execute(comando)
            con.execute(f"PRAGMA user_version={numero}")
        con.commit()
    except Exception:
        con.rollback()
        raise


def tel_hash(e164: str) -> str:
    """Opt-out guardado como hash para sobreviver a limpezas sem manter o contato."""
    return hashlib.sha256(e164.encode()).hexdigest()


def bloqueado(con: sqlite3.Connection, e164: str) -> bool:
    return con.execute("SELECT 1 FROM bloqueio WHERE tel_hash=?", (tel_hash(e164),)).fetchone() is not None
