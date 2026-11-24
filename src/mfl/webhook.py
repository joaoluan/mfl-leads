"""Receptor do webhook da Evolution.

Escuta no gateway da rede Docker da Evolution (não no localhost da UI nem na LAN) e exige token.
"""

import hmac
import os
from pathlib import Path

import structlog
from flask import Flask, abort, request

from mfl import db, whatsapp

log = structlog.get_logger()


def criar_app(caminho_db: Path | None = None) -> Flask:
    app = Flask(__name__)
    token = os.environ["MFL_WEBHOOK_TOKEN"]

    @app.post("/webhook/evolution")
    def receber() -> tuple[str, int]:
        if not hmac.compare_digest(request.args.get("token", ""), token):
            abort(403)
        con = db.conectar(caminho_db)
        try:
            resultado = whatsapp.processar(con, request.get_json(silent=True) or {})
        finally:
            con.close()
        if resultado not in ("nao_lead", "ignorado"):
            log.info("evento", resultado=resultado)
        return "", 204

    return app
