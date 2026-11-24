"""Recorte de ICP sobre o Parquet do CNPJ (DuckDB, só leitura) e ingestão no SQLite.

Lead que vem só do CNPJ entra como `enriquecimento`: o telefone da Receita costuma ser do contador,
então fica em tel2 (serve para cruzar fontes na fase 5) e nunca vai para a fila.
"""

import hashlib
import json
import re
import sqlite3
import tomllib
import uuid
from pathlib import Path

import duckdb
import structlog

from mfl.db import LOTE, RAIZ, agora
from mfl.fone import para_e164

log = structlog.get_logger()
ICP = RAIZ / "cfg" / "icp.toml"
FRANQUIAS = RAIZ / "cfg" / "franquias.txt"


def recorte() -> dict:
    with ICP.open("rb") as f:
        return tomllib.load(f)["recorte"]


def termos_franquia(arquivo: Path = FRANQUIAS) -> list[str]:
    return [l.strip() for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def consultar(parquet: Path, cfg: dict, franquias: list[str]) -> list[dict]:
    """Só ativa (já no ETL), só RS, só município e CNAE do recorte, com endereço, sem rede/franquia."""
    padrao = r"\b(" + "|".join(re.escape(t) for t in franquias) + r")\b" if franquias else r"$^"
    con = duckdb.connect()
    sql = f"""
    WITH e AS (SELECT * FROM read_parquet('{parquet}/estab/uf=RS/*.parquet')),
    filiais AS (SELECT cnpj_basico, count(*) AS n FROM e GROUP BY cnpj_basico),
    emp AS (SELECT * FROM read_parquet('{parquet}/empresas/uf=RS/*.parquet', union_by_name=true))
    SELECT e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj, nullif(trim(e.nome_fantasia), '') AS fantasia,
           e.cnae_fiscal_principal AS cnae, c.descricao AS cnae_descricao, m.descricao AS municipio,
           nullif(trim(e.bairro), '') AS bairro, e.cep,
           trim(concat_ws(' ', e.tipo_logradouro, e.logradouro, e.numero, e.complemento)) AS endereco,
           nullif(trim(e.ddd1) || trim(e.telefone1), '') AS fone1, nullif(trim(e.ddd2) || trim(e.telefone2), '') AS fone2,
           nullif(lower(trim(e.correio_eletronico)), '') AS email, e.data_inicio_atividade,
           emp.porte, emp.natureza_juridica, f.n AS filiais
    FROM e
    JOIN read_parquet('{parquet}/municipios.parquet') m ON m.codigo = e.municipio
    LEFT JOIN read_parquet('{parquet}/cnae.parquet') c ON c.codigo = e.cnae_fiscal_principal
    JOIN filiais f USING (cnpj_basico)
    LEFT JOIN emp USING (cnpj_basico)
    WHERE list_contains($municipios, m.descricao)
      AND list_contains($cnaes, e.cnae_fiscal_principal)
      AND nullif(trim(e.logradouro), '') IS NOT NULL
      AND f.n < $filiais_rede
      AND NOT regexp_matches(lower(strip_accents(coalesce(e.nome_fantasia, ''))), $padrao)
    ORDER BY cnpj
    """
    cursor = con.execute(sql, {"municipios": cfg["municipios"], "cnaes": cfg["cnaes"],
                               "filiais_rede": cfg["filiais_rede"], "padrao": padrao})
    colunas = [c[0] for c in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def ingerir(con: sqlite3.Connection, linhas: list[dict], url: str) -> dict[str, int]:
    """Idempotente por CNPJ: rodar o mês de novo não duplica.

    shortcut: lead que saiu do recorte (baixado, mudou de CNAE) não é descartado aqui; tratar na atualização mensal.
    """
    contagem = {"novos": 0, "repetidos": 0}
    momento = agora()
    for n, l in enumerate(linhas, start=1):
        raw = json.dumps(l, ensure_ascii=False, sort_keys=True, default=str)
        if con.execute("SELECT 1 FROM source_record WHERE source='cnpj' AND source_key=?", (l["cnpj"],)).fetchone():
            contagem["repetidos"] += 1
            continue
        existente = con.execute("SELECT entity_id FROM entity WHERE cnpj=?", (l["cnpj"],)).fetchone()
        entity_id = existente[0] if existente else str(uuid.uuid4())
        if not existente:
            fone = next((e for e in (para_e164(l["fone1"] or ""), para_e164(l["fone2"] or "")) if e), None)
            con.execute(
                "INSERT INTO entity (entity_id, cnpj, nome, fantasia, cnae, categoria, uf, municipio, bairro, cep,"
                " endereco, tel2, status, criado_em, atualizado_em)"
                " VALUES (?,?,?,?,?,?,'RS',?,?,?,?,?,'enriquecimento',?,?)",
                (entity_id, l["cnpj"], l["fantasia"] or f"CNPJ {l['cnpj']}", l["fantasia"], l["cnae"],
                 (l["cnae_descricao"] or "").lower() or None, l["municipio"], l["bairro"], l["cep"], l["endereco"],
                 fone, momento, momento),
            )
        con.execute(
            "INSERT INTO source_record (source, source_key, entity_id, raw_json, url, captured_at, hash)"
            " VALUES ('cnpj',?,?,?,?,?,?)",
            (l["cnpj"], entity_id, raw, url, momento, hashlib.sha256(raw.encode()).hexdigest()),
        )
        contagem["novos"] += 1
        if n % LOTE == 0:
            con.commit()
    con.commit()
    log.info("cnpj_ingerido", url=url, **contagem)
    return contagem
