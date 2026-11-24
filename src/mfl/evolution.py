"""Cliente mínimo da Evolution API local (só leitura do WhatsApp: nunca envia mensagem)."""

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from mfl.fone import de_jid

EVENTOS = ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CONNECTION_UPDATE"]
# alwaysOnline/readMessages desligados: o celular continua notificando e o lead não vê "lida" sem você ler.
# groupsIgnore: mensagens de grupo nem chegam ao webhook.
AJUSTES = {"rejectCall": False, "groupsIgnore": True, "alwaysOnline": False,
           "readMessages": False, "readStatus": False, "syncFullHistory": False}


def instancia() -> str:
    return os.environ.get("MFL_EVOLUTION_INSTANCIA", "pessoal")


def url_webhook() -> str:
    host = os.environ.get("MFL_WEBHOOK_HOST", "172.31.250.1")
    porta = os.environ.get("MFL_WEBHOOK_PORTA", "8001")
    return f"http://{host}:{porta}/webhook/evolution?token={os.environ['MFL_WEBHOOK_TOKEN']}"


class ErroEvolution(RuntimeError):
    def __init__(self, codigo: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


def _rede_transitoria(erro: BaseException) -> bool:
    return isinstance(erro, (URLError, TimeoutError, ConnectionError)) and not isinstance(erro, HTTPError)


@retry(retry=retry_if_exception(_rede_transitoria), stop=stop_after_attempt(3),
       wait=wait_exponential(min=1, max=8), reraise=True)
def chamar(metodo: str, caminho: str, corpo: dict | None = None) -> Any:
    """Retry só em falha de rede; erro HTTP sobe com o corpo para o operador entender."""
    base = os.environ.get("MFL_EVOLUTION_URL", "http://127.0.0.1:8080")
    pedido = Request(
        base + caminho, method=metodo,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"apikey": os.environ["MFL_EVOLUTION_KEY"], "Content-Type": "application/json"},
    )
    try:
        with urlopen(pedido, timeout=20) as resposta:
            return json.loads(resposta.read() or b"null")
    except HTTPError as erro:
        corpo_erro = erro.read()[:300].decode(errors="replace")
        raise ErroEvolution(erro.code, f"Evolution {metodo} {caminho}: {erro.code} {corpo_erro}") from erro


def situacao() -> dict | None:
    """Instância como a Evolution a vê (connectionStatus, ownerJid) ou None se não existe."""
    try:
        lista = chamar("GET", f"/instance/fetchInstances?instanceName={instancia()}") or []
    except ErroEvolution as erro:
        if erro.codigo == 404:
            return None
        raise
    return lista[0] if lista else None


def conectar() -> str | None:
    """Cria a instância se faltar, reaplica webhook e ajustes, e devolve o QR (data URI) se precisar parear."""
    nome = instancia()
    if situacao() is None:
        criada = chamar("POST", "/instance/create", {
            "instanceName": nome, "integration": "WHATSAPP-BAILEYS", "qrcode": True, **AJUSTES,
        })
        qr = (criada.get("qrcode") or {}).get("base64")
    else:
        qr = (chamar("GET", f"/instance/connect/{nome}") or {}).get("base64")
    chamar("POST", f"/webhook/set/{nome}", {"webhook": {
        "enabled": True, "url": url_webhook(), "events": EVENTOS, "byEvents": False, "base64": False,
    }})
    chamar("POST", f"/settings/set/{nome}", AJUSTES)
    return qr
