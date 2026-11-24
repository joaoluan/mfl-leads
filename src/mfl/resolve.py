"""Resolução de entidade: o mesmo estabelecimento vindo de fontes diferentes vira um lead só.

Regra da spec: 0,35 CEP5 igual + 0,35 telefone igual + 0,30 similaridade do nome.
>= 0,85 vincula; 0,55–0,85 vai para revisão; abaixo, entidades separadas.
Ajustes (Parte A): telefone igual sozinho já vincula (é o mesmo WhatsApp), desde que o
telefone não se repita entre CNPJs (aí é do contador); CEP completo + nome >= 0,85 também vincula.
"""

import re
import sqlite3

from rapidfuzz import fuzz

from mfl.classifica import normalizar
from mfl.db import agora, bloqueado
from mfl.fone import celular

VINCULA, REVISA = 0.85, 0.55
SUFIXOS = re.compile(r"\b(ltda|me|eireli|sa|mei|epp)\b")
# Palavras de tipo de casa não identificam ninguém: "Pizzaria Nova" e "Pizzaria Bella" não são parecidas.
GENERICAS = re.compile(r"\b(pizzaria|pizza|pizzas|restaurante|lanchonete|lancheria|lanches|bar|cafe|cafeteria|padaria"
                       r"|confeitaria|doceria|hamburgueria|burger|churrascaria|sushi|casa|do|da|de|dos|das|e|o|a)\b")
PROVISORIO = re.compile(r"^(CNPJ |Marcado como |Contato \()")
# Campos que a fonte nova preenche quando o lead sobrevivente não tem.
PREENCHE = ["cnpj", "place_id", "ig_username", "fantasia", "cnae", "categoria", "uf", "municipio", "bairro", "cep",
            "endereco", "tel2", "email", "site", "nota", "avaliacoes"]


def nome_normal(nome: str | None, lugar: set[str] = frozenset()) -> str:
    """`lugar`: palavras do bairro/cidade ("Moinhos", "POA"), que não identificam a casa."""
    if not nome or PROVISORIO.match(nome):
        return ""
    return " ".join(t for t in GENERICAS.sub(" ", SUFIXOS.sub(" ", normalizar(nome))).split() if t not in lugar)


def numero(endereco: str | None) -> str | None:
    """Número do endereço no formato do Maps ("R. X, 905 - ...")."""
    achado = re.search(r",\s*(\d+)\b", endereco or "")
    return achado.group(1) if achado else None


def telefones_compartilhados(con: sqlite3.Connection) -> set[str]:
    """Telefone em mais de um CNPJ é do contador: não serve para casar."""
    return {r[0] for r in con.execute(
        "SELECT tel2 FROM entity WHERE cnpj IS NOT NULL AND tel2 IS NOT NULL GROUP BY tel2 HAVING count(*) > 1")}


def pontuar(a: dict, b: sqlite3.Row | dict, compartilhados: set[str]) -> float:
    tels_a = {t for t in (a.get("tel1"), a.get("tel2")) if t and t not in compartilhados}
    tels_b = {t for t in (b["tel1"], b["tel2"]) if t and t not in compartilhados}
    if tels_a & tels_b:
        return 1.0
    cep_a, cep_b = a.get("cep") or "", b["cep"] or ""
    lugar = set(normalizar(f"{a.get('bairro') or ''} {a.get('municipio') or ''} poa").split())
    nome_a = nome_normal(a.get("fantasia") or a.get("nome"), lugar)
    nome_b = nome_normal(b["fantasia"] or b["nome"], lugar)
    similar = fuzz.token_set_ratio(nome_a, nome_b) / 100 if nome_a and nome_b else 0.0
    mesmo_cep5 = len(cep_a) >= 5 and cep_a[:5] == cep_b[:5]
    nota = 0.35 * mesmo_cep5 + 0.30 * similar
    # CEP do Maps e da Receita costumam diferir no fim; o número da porta não.
    mesma_porta = numero(a.get("endereco")) in re.findall(r"\b\d+\b", b["endereco"] or "")
    if similar >= 0.85 and ((len(cep_a) == 8 and cep_a == cep_b) or (mesmo_cep5 and mesma_porta)):
        nota = max(nota, VINCULA)
    return round(nota, 3)


def melhor_candidato(con: sqlite3.Connection, novo: dict, compartilhados: set[str],
                     ignorar: str | None = None) -> tuple[sqlite3.Row | None, float]:
    """Bloqueio por CEP5 ou telefone (spec) antes de comparar nomes."""
    ids_ifood = novo.get("_ifood_ids") or []
    if ids_ifood:
        lojas = con.execute(
            f"SELECT DISTINCT e.* FROM entity e JOIN source_record s ON s.entity_id=e.entity_id"
            f" WHERE s.source='ifood' AND s.source_key IN ({','.join('?' * len(ids_ifood))}) AND e.entity_id IS NOT ?",
            (*ids_ifood, ignorar)).fetchall()
        if len(lojas) == 1:
            return lojas[0], 1.0
    cep5 = (novo.get("cep") or "")[:5]
    tels = [t for t in (novo.get("tel1"), novo.get("tel2")) if t] or [""]
    marcas = ",".join("?" * len(tels))
    linhas = con.execute(
        f"SELECT * FROM entity WHERE ((? <> '' AND cep >= ? AND cep < ?) OR tel1 IN ({marcas}) OR tel2 IN ({marcas}))"
        " AND entity_id IS NOT ?",
        (cep5, cep5, cep5[:-1] + chr(ord(cep5[-1]) + 1) if cep5 else "", *tels, *tels, ignorar),
    ).fetchall()
    melhor = max(((l, pontuar(novo, l, compartilhados)) for l in linhas), key=lambda x: x[1], default=(None, 0.0))
    if melhor[1] < VINCULA and novo.get("municipio"):
        # iFood pode mostrar só nome/cidade. Serve para revisão, nunca para vínculo automático.
        cidade = novo["municipio"]
        nome = nome_normal(novo.get("fantasia") or novo.get("nome"))
        if len(nome) >= 3:
            candidatos = con.execute(
                "SELECT e.* FROM entity e WHERE lower(municipio) IN (lower(?),lower(?)) AND entity_id IS NOT ?"
                " AND (?='ifood' OR EXISTS (SELECT 1 FROM source_record s WHERE s.entity_id=e.entity_id AND s.source='ifood'))",
                (cidade, normalizar(cidade), ignorar, novo.get("_fonte")))
            for linha in candidatos:
                outro = nome_normal(linha["fantasia"] or linha["nome"])
                if outro and fuzz.ratio(nome, outro) >= 85 and melhor[1] < REVISA:
                    melhor = linha, REVISA
    return melhor


def preencher(con: sqlite3.Connection, entity_id: str, dados: dict) -> None:
    """Completa o lead sobrevivente sem apagar o que ele já tem; nome provisório (CNPJ/marcado) é trocado."""
    atual = con.execute("SELECT * FROM entity WHERE entity_id=?", (entity_id,)).fetchone()
    if dados.get("tel1") and bloqueado(con, dados["tel1"]):  # pediu SAIR: não volta por outra fonte
        dados = {**dados, "tel1": None, "_celular": False}
    mudancas = {c: dados[c] for c in PREENCHE if dados.get(c) is not None and atual[c] is None}
    if dados.get("nome") and not PROVISORIO.match(dados["nome"]) and (
            atual["nome"] is None or PROVISORIO.match(atual["nome"])):
        mudancas["nome"] = dados["nome"]
    if dados.get("categoria") and dados.get("_fonte") == "maps":
        mudancas["categoria"] = dados["categoria"]  # categoria do Maps é mais específica que a descrição do CNAE
    if dados.get("tel1") and dados["tel1"] != atual["tel1"]:
        if atual["tel1"] is None:
            mudancas["tel1"] = dados["tel1"]
        elif dados.get("_celular") and not celular(atual["tel1"]):
            mudancas["tel1"] = dados["tel1"]  # fixo não recebe WhatsApp: o celular novo assume
            if atual["tel2"] is None:
                mudancas["tel2"] = atual["tel1"]
        elif atual["tel2"] is None:
            mudancas["tel2"] = dados["tel1"]  # o celular que já estava continua sendo o principal
    if atual["status"] == "enriquecimento" and dados.get("_celular") and (mudancas.get("tel1") or atual["tel1"]):
        mudancas["status"] = "novo"
    if mudancas:
        sets = ", ".join(f"{c}=?" for c in mudancas)
        con.execute(f"UPDATE entity SET {sets}, atualizado_em=? WHERE entity_id=?", (*mudancas.values(), agora(), entity_id))


def fundir(con: sqlite3.Connection, sobrevivente: str, absorvido: str) -> None:
    """Move tudo do absorvido para o sobrevivente (fontes, toques, respostas) e apaga o absorvido."""
    dados = dict(con.execute("SELECT * FROM entity WHERE entity_id=?", (absorvido,)).fetchone())
    for tabela in ("source_record", "touch", "reply", "queue"):
        con.execute(f"UPDATE {tabela} SET entity_id=? WHERE entity_id=?", (sobrevivente, absorvido))
    unicos = {c: dados.pop(c) for c in ("cnpj", "place_id", "ig_username")}
    con.execute("DELETE FROM entity WHERE entity_id=?", (absorvido,))
    con.execute("UPDATE revisao SET decidido=1 WHERE (a=? OR b=?) AND decidido=0", (absorvido, absorvido))
    preencher(con, sobrevivente, {**dados, **unicos, "_celular": dados["status"] != "enriquecimento",
                                  "_fonte": "maps" if unicos["place_id"] else None})
