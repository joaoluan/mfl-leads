"""Exporta as entities em CSV para conferência fora do sistema."""

import csv
import sqlite3
from pathlib import Path

import structlog

log = structlog.get_logger()

CONSULTA = """
SELECT e.entity_id, e.nome, e.categoria, e.bairro, e.municipio, e.tel1, e.status,
       e.score, e.opt_out, group_concat(DISTINCT s.source) AS fontes, e.criado_em
FROM entity e LEFT JOIN source_record s USING (entity_id)
GROUP BY e.entity_id ORDER BY e.score DESC, e.criado_em
"""


def exportar(con: sqlite3.Connection, saida: Path) -> int:
    """Devolve quantas linhas saíram, para o log conferir com o banco."""
    cursor = con.execute(CONSULTA)
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow([c[0] for c in cursor.description])
        linhas = 0
        for linha in cursor:
            escritor.writerow(tuple(linha))
            linhas += 1
    log.info("export_concluido", arquivo=str(saida), linhas=linhas)
    return linhas
