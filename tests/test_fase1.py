import csv
from pathlib import Path

import pytest

from mfl import db, export, seed

CSV = Path(__file__).parent / "fixtures" / "grupo.csv"


@pytest.fixture
def con(tmp_path):
    return db.conectar(tmp_path / "t.db")


def test_seed_normaliza_e_deduplica(con):
    assert seed.importar(con, CSV) == {"novos": 2, "repetidos": 1, "invalidos": 1, "sem_telefone": 1, "bloqueados": 0}
    tels = {r["tel1"] for r in con.execute("SELECT tel1 FROM entity WHERE tel1 IS NOT NULL")}
    assert tels == {"+5551999990001", "+5551999990002"}
    sem = con.execute("SELECT status FROM entity WHERE nome='Sem Telefone Valido'").fetchone()
    assert sem["status"] == "enriquecimento"


def test_seed_rodar_de_novo_nao_duplica(con):
    seed.importar(con, CSV)
    assert seed.importar(con, CSV) == {"novos": 0, "repetidos": 4, "invalidos": 1, "sem_telefone": 0, "bloqueados": 0}
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 3
    assert con.execute("SELECT count(*) FROM source_record").fetchone()[0] == 3


def test_seed_recusa_csv_sem_coluna(con, tmp_path):
    ruim = tmp_path / "ruim.csv"
    ruim.write_text("nome,fone\nX,51999990001\n")
    with pytest.raises(ValueError, match="telefone"):
        seed.importar(con, ruim)


def test_export_gera_csv(con, tmp_path):
    seed.importar(con, CSV)
    saida = tmp_path / "out.csv"
    assert export.exportar(con, saida) == 3
    linhas = list(csv.DictReader(saida.open()))
    assert {l["fontes"] for l in linhas} == {"grupo"}
