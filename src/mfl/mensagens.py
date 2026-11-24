"""Textos de abordagem: escolha de variante, preenchimento e deep link do WhatsApp Web.

Cada arquivo em cfg/mensagens tem variantes separadas por uma linha com só `---`.
template_id = "<arquivo>:<índice>".
"""

import re
import sqlite3
import string
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from mfl.classifica import normalizar
from mfl.db import RAIZ

PASTA = RAIZ / "cfg" / "mensagens"
CAMPOS = {"nome", "bairro", "sinal", "horario"}
SEM_SAIR = {"preco", "ja_tenho", "interesse"}  # respostas a quem já está conversando
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
# Ordem importa: "lanchonete de açaí" não pode cair em bar, "padaria e confeitaria" em lanchonete.
CATEGORIAS = [
    ("pizzaria", r"pizz"),
    ("hamburgueria", r"hamburg|burger"),
    ("churrascaria", r"churrasc|grill|parrilla|espeto"),
    ("japones", r"japon|sushi|temaki|oriental"),
    ("padaria", r"padaria|confeitaria|doce|bolo|torta|panific"),
    ("bar", r"\b(bar|pub|boteco|choperia|cervejaria)\b"),
    ("lanchonete", r"lanch|cafe|pastel|acai|sanduich|salgad"),
]


def variantes(arquivo: str) -> list[str]:
    texto = (PASTA / f"{arquivo}.md").read_text(encoding="utf-8")
    return [v.strip() for v in re.split(r"^---$", texto, flags=re.M) if v.strip()]


def arquivo_d0(categoria: str | None, fontes: set[str]) -> str:
    """Quem está no grupo recebe o texto do grupo, mesmo depois de ganhar CNPJ ou Maps."""
    if "grupo" in fontes:
        return "grupo"
    limpo = normalizar(categoria or "")
    return next((nome for nome, padrao in CATEGORIAS if re.search(padrao, limpo)), "restaurante")


def proxima_variante(con: sqlite3.Connection, arquivo: str) -> int:
    """Nunca repete a variante do último envio do mesmo arquivo (rodízio)."""
    ultimo = con.execute(
        "SELECT template_id FROM touch WHERE template_id LIKE ? ORDER BY enviado_em DESC, id DESC LIMIT 1",
        (f"{arquivo}:%",),
    ).fetchone()
    total = len(variantes(arquivo))
    return (int(ultimo[0].split(":")[1]) + 1) % total if ultimo else 0


def horario(hoje: date) -> str:
    """Próximo dia útil às 15h, por extenso; o operador ajusta se não servir."""
    dia = hoje + timedelta(days=1)
    while dia.weekday() == 6:
        dia += timedelta(days=1)
    return "amanhã às 15h" if dia == hoje + timedelta(days=1) else f"{DIAS[dia.weekday()]} às 15h"


def preencher(texto: str, valores: dict[str, str]) -> str:
    """Placeholder vazio some, e a linha que só tinha ele também; linha em branco do autor fica (parágrafo)."""
    mapa = {c: valores.get(c) or "" for c in CAMPOS}
    saida: list[str] = []
    for original in texto.splitlines():
        linha = re.sub(r" {2,}", " ", original.format_map(mapa)).strip()
        if linha or ("{" not in original and saida and saida[-1]):
            saida.append(linha)
    return "\n".join(saida).strip()


def sugerir(con: sqlite3.Connection, lead: sqlite3.Row, etapa: str, fontes: set[str], hoje: date) -> tuple[str, str]:
    """(template_id, texto) para a etapa da cadência (d0, d3, d7)."""
    arquivo = etapa if etapa in ("d3", "d7") else arquivo_d0(lead["categoria"], fontes)
    indice = proxima_variante(con, arquivo)
    valores = {"nome": lead["fantasia"] or lead["nome"], "bairro": lead["bairro"], "sinal": "", "horario": horario(hoje)}
    return f"{arquivo}:{indice}", preencher(variantes(arquivo)[indice], valores)


def resposta_sugerida(arquivo: str, hoje: date) -> str:
    return preencher(variantes(arquivo)[0], {"horario": horario(hoje)})


def link_whatsapp(e164: str, texto: str) -> str:
    return f"https://web.whatsapp.com/send?phone={e164.lstrip('+')}&text={quote(texto)}"


def validar(arquivo: str, conteudo: str) -> list[str]:
    """Erros que impedem salvar pelo /config: placeholder desconhecido e falta do SAIR (LGPD)."""
    erros = []
    partes = [v.strip() for v in re.split(r"^---$", conteudo, flags=re.M) if v.strip()]
    if not partes:
        erros.append("nenhuma variante")
    for i, parte in enumerate(partes, start=1):
        try:
            campos = {c for _, c, _, _ in string.Formatter().parse(parte) if c}
        except ValueError as erro:
            erros.append(f"variante {i}: chave mal formada ({erro})")
            continue
        if campos - CAMPOS:
            erros.append(f"variante {i}: campo desconhecido {sorted(campos - CAMPOS)}")
        if arquivo not in SEM_SAIR and "SAIR" not in parte:
            erros.append(f"variante {i}: falta o 'responde SAIR' (LGPD)")
    return erros


def arquivos() -> list[str]:
    return sorted(p.stem for p in Path(PASTA).glob("*.md"))
