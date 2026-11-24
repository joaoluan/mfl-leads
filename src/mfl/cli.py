"""Comandos da esteira (`uv run mfl --help`)."""

from datetime import date
from pathlib import Path

import typer
from dotenv import load_dotenv

from mfl import db, export, log, seed

app = typer.Typer(no_args_is_help=True)


@app.callback()
def _inicio() -> None:
    load_dotenv(db.RAIZ / ".env")


@app.command("seed")
def cmd_seed(csv: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Importa CSV de contatos (nome, telefone, categoria, bairro)."""
    log.configurar("seed")
    seed.importar(db.conectar(), csv)


@app.command("export")
def cmd_export(saida: Path | None = None) -> None:
    """Gera data/export/leads-<data>.csv."""
    log.configurar("export")
    export.exportar(db.conectar(), saida or db.RAIZ / "data" / "export" / f"leads-{date.today()}.csv")
