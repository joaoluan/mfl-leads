import csv

import pytest

from conftest import criar_lead
from mfl import db, export


@pytest.fixture
def con(tmp_path):
    return db.conectar(tmp_path / "t.db")


def test_export_gera_csv(con, tmp_path):
    criar_lead(con, "Casa A", "+5551999990001", score=50)
    criar_lead(con, "Casa B", None, status="enriquecimento")
    saida = tmp_path / "out.csv"
    assert export.exportar(con, saida) == 2
    linhas = list(csv.DictReader(saida.open()))
    assert [l["nome"] for l in linhas] == ["Casa A", "Casa B"]  # ordem por score
    assert {l["fontes"] for l in linhas} == {"maps"}
