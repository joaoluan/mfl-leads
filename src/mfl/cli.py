"""Comandos da esteira (`uv run mfl --help`)."""

import base64
import logging
import os
import subprocess
import time
from datetime import date
from pathlib import Path

import structlog
import typer
from dotenv import load_dotenv

from mfl import db, evolution, export, log, seed, webhook
from mfl.fone import de_jid

app = typer.Typer(no_args_is_help=True)
logger = structlog.get_logger()


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


@app.command("evo-conectar")
def cmd_evo_conectar() -> None:
    """Cria/conecta a instância e abre o QR para parear pelo celular."""
    log.configurar("evolution")
    qr = evolution.conectar()
    if not qr:
        logger.info("ja_conectado", situacao=(evolution.situacao() or {}).get("connectionStatus"))
        return
    arquivo = db.RAIZ / "data" / "qr.png"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(base64.b64decode(qr.split(",", 1)[-1]))
    subprocess.Popen(["xdg-open", str(arquivo)])
    logger.info("leia_o_qr", dica="WhatsApp > Aparelhos conectados > Conectar aparelho")
    try:
        for _ in range(60):
            time.sleep(3)
            if (evolution.situacao() or {}).get("connectionStatus") == "open":
                logger.info("conectado")
                return
        logger.error("qr_expirou", dica="rode de novo")
    finally:
        arquivo.unlink(missing_ok=True)


@app.command("evo-status")
def cmd_evo_status() -> None:
    """Mostra se a instância está conectada."""
    log.configurar("evolution")
    s = evolution.situacao() or {}
    logger.info("evolution", instancia=evolution.instancia(), conexao=s.get("connectionStatus"))


@app.command("grupos")
def cmd_grupos() -> None:
    """Lista os grupos (nome e tamanho, sem números) para escolher o de donos."""
    log.configurar("evolution")
    for g in sorted(evolution.grupos(), key=lambda g: -int(g.get("size") or 0)):
        logger.info("grupo", nome=g.get("subject"), participantes=g.get("size"))


@app.command("grupo-importar")
def cmd_grupo_importar(nome: str = typer.Argument(..., help="Nome exato do grupo")) -> None:
    """Importa os participantes do grupo como leads (fonte grupo)."""
    log.configurar("seed")
    achados = [g for g in evolution.grupos() if g.get("subject") == nome]
    if len(achados) != 1:
        raise typer.BadParameter(f"{len(achados)} grupos com o nome {nome!r}; use `mfl grupos`")
    dono = de_jid((evolution.situacao() or {}).get("ownerJid") or "")
    linhas, sem_numero = evolution.participantes(achados[0], dono)
    if sem_numero:
        logger.warning("participantes_sem_numero", quantidade=sem_numero, motivo="WhatsApp escondeu (LID)")
    seed.importar_linhas(db.conectar(), linhas, f"whatsapp:grupo:{nome}")


@app.command("webhook")
def cmd_webhook() -> None:
    """Sobe o receptor do webhook da Evolution (deixar rodando)."""
    log.configurar("webhook")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # o log de acesso imprimiria o token da URL
    webhook.criar_app().run(
        host=os.environ.get("MFL_WEBHOOK_HOST", "172.31.250.1"),
        port=int(os.environ.get("MFL_WEBHOOK_PORTA", "8001")),
    )
