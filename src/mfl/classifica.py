"""Sugestão de classificação de resposta por palavra-chave; o operador confirma na UI."""

import re
import unicodedata

# Opt-out é automático, então só casa pedido explícito. Ordem importa: o primeiro que casar vence.
REGRAS: list[tuple[str, re.Pattern[str]]] = [
    ("opt_out", re.compile(
        r"^(sair|pare|parar|stop|remover|cancelar|descadastrar)$"
        r"|\b(nao (me )?mand\w* mais|pare de mandar|para de mandar|me (tira|remove|exclui)\w*|descadastr\w*)\b"
    )),
    ("nao", re.compile(r"\b(nao (tenho interesse|quero|preciso|obrigad\w*)|sem interesse|dispenso)\b")),
    ("ja_tenho", re.compile(
        r"\bja (tenho|uso|usamos|temos|trabalho com|trabalhamos com)\b"
        r"|\b(goomer|saipos|anota ?ai|leadsfood|consumer|linx|menudino|cardapio web)\b"
    )),
    ("preco", re.compile(r"\b(quanto (custa|e|sai|fica)|valor\w*|preco\w*|mensalidade|planos?)\b")),
    ("interesse", re.compile(
        r"\b(tenho interesse|quero|como funciona|me explica|pode ser|bora|vamos|testar|teste|manda|sim)\b"
    )),
]


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^\w\s]", " ", sem_acento.lower()).split())


def classificar(texto: str) -> str | None:
    """None = sem palpite; fica para o operador classificar."""
    limpo = normalizar(texto or "")
    return next((rotulo for rotulo, padrao in REGRAS if padrao.search(limpo)), None)
