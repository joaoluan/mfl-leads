"""Importa CSV de contatos (nome, telefone, categoria, bairro) como fonte `grupo`."""

import csv
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mfl.db import LOTE, agora
from mfl.fone import para_e164

COLUNAS = {"nome", "telefone", "categoria", "bairro"}
log = structlog.get_logger()


class LinhaSeed(BaseModel):
    """Contrato do CSV: nome é o mínimo para alguém revisar o lead depois."""

    model_config = ConfigDict(str_strip_whitespace=True)
    nome: str = Field(min_length=1)
    telefone: str = ""
    categoria: str = ""
    bairro: str = ""


def importar(con: sqlite3.Connection, arquivo: Path) -> dict[str, int]:
    """Idempotente: rodar de novo o mesmo CSV não duplica (UNIQUE source+source_key)."""
    contagem = {"novos": 0, "repetidos": 0, "invalidos": 0, "sem_telefone": 0}
    with arquivo.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        faltando = COLUNAS - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"{arquivo.name}: faltam as colunas {sorted(faltando)}")
        for n, bruto in enumerate(leitor, start=1):
            try:
                linha = LinhaSeed.model_validate(bruto)
            except ValidationError as erro:
                contagem["invalidos"] += 1
                log.warning("linha_invalida", linha=n + 1, erro=erro.errors()[0]["msg"])
                continue
            contagem[_gravar(con, linha, bruto, arquivo)] += 1
            if n % LOTE == 0:
                con.commit()
    con.commit()
    log.info("seed_concluido", arquivo=arquivo.name, **contagem)
    return contagem


def _gravar(con: sqlite3.Connection, linha: LinhaSeed, bruto: dict, arquivo: Path) -> str:
    e164 = para_e164(linha.telefone)
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
        (chave, entity_id, raw, f"csv:{arquivo.name}", momento, hashlib.sha256(raw.encode()).hexdigest()),
    )
    return "novos" if e164 else "sem_telefone"
