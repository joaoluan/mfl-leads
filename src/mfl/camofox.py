"""Acesso ao navegador local compartilhado pelas fontes."""

import json
import os
import urllib.request


def api(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    pedido = urllib.request.Request(
        os.environ.get("MFL_CAMOFOX_URL", "http://127.0.0.1:9377") + caminho,
        method=metodo, headers={"Content-Type": "application/json"},
        data=json.dumps(corpo).encode() if corpo is not None else None,
    )
    with urllib.request.urlopen(pedido, timeout=90) as resposta:
        return json.load(resposta)
