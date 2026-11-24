"""Importa contatos (nome, telefone, categoria, bairro) como fonte `grupo`: CSV ou grupo do WhatsApp."""

import csv
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mfl.db import LOTE, agora, bloqueado
from mfl.fone import para_e164

COLUNAS = {"nome", "telefone", "categoria", "bairro"}
log = structlog.get_logger()


class LinhaSeed(BaseModel):
    """Contrato da importação: nome é o mínimo para alguém revisar o lead depois."""

    model_config = ConfigDict(str_strip_whitespace=True)
    nome: str = Field(min_length=1)
    telefone: str = ""
    categoria: str = ""
    bairro: str = ""


def importar(con: sqlite3.Connection, arquivo: Path) -> dict[str, int]:
    """Lê o CSV e delega; o cabeçalho é conferido antes para errar cedo."""
    with arquivo.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        faltando = COLUNAS - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"{arquivo.name}: faltam as colunas {sorted(faltando)}")
        return importar_linhas(con, leitor, f"csv:{arquivo.name}", primeira_linha=2)


def importar_linhas(
    con: sqlite3.Connection, linhas: Iterable[dict], url: str, primeira_linha: int = 1
) -> dict[str, int]:
    """Idempotente: importar de novo não duplica (UNIQUE source+source_key) e opt-out nunca volta."""
    contagem = {"novos": 0, "repetidos": 0, "invalidos": 0, "sem_telefone": 0, "bloqueados": 0}
    for n, bruto in enumerate(linhas):
        try:
            linha = LinhaSeed.model_validate(bruto)
        except ValidationError as erro:
            contagem["invalidos"] += 1
            log.warning("linha_invalida", linha=n + primeira_linha, erro=erro.errors()[0]["msg"])
            continue
        contagem[_gravar(con, linha, bruto, url)] += 1
        if (n + 1) % LOTE == 0:
            con.commit()
    con.commit()
    log.info("seed_concluido", url=url, **contagem)
    return contagem


def _gravar(con: sqlite3.Connection, linha: LinhaSeed, bruto: dict, url: str) -> str:
    e164 = para_e164(linha.telefone)
    if e164 and bloqueado(con, e164):
        return "bloqueados"
    raw = json.dumps(bruto, ensure_ascii=False, sort_keys=True)
    chave = e164 or "sem-tel:" + hashlib.sha256(f"{linha.nome}|{linha.bairro}".encode()).hexdigest()[:16]
    if con.execute(
        "SELECT 1 FROM source_record WHERE source='grupo' AND source_key=?", (chave,)
    ).fetchone():
        return "repetidos"

    existente = e164 and con.execute("SELECT entity_id FROM entity WHERE tel1=?", (e164,)).fetchone()
    momento = agora()
    if existente:
        entity_id = existente["entity_id"]
    else:
        entity_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO entity (entity_id, nome, categoria, bairro, tel1, status, criado_em, atualizado_em)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (entity_id, linha.nome, linha.categoria or None, linha.bairro or None, e164,
             "novo" if e164 else "enriquecimento", momento, momento),
        )
    con.execute(
        "INSERT INTO source_record (source, source_key, entity_id, raw_json, url, captured_at, hash)"
        " VALUES ('grupo',?,?,?,?,?,?)",
        (chave, entity_id, raw, url, momento, hashlib.sha256(raw.encode()).hexdigest()),
    )
    return "novos" if e164 else "sem_telefone"
