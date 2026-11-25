import gzip
import sqlite3
from datetime import date

import pytest

from mfl import controle, db, log, ops, ui


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(ops, "LOCAL", tmp_path / "data" / "backup" / "diario")
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "icp.toml").write_text("corte = 40\n")
    (tmp_path / "data" / "parquet").mkdir(parents=True)
    (tmp_path / "data" / "parquet" / "estab.parquet").write_text("x")
    return db.conectar(tmp_path / "t.db")


def test_job_registra_ok_erro_e_trava(con):
    with ops.job(con, "teste"):
        pass
    assert con.execute("SELECT valor FROM estado WHERE chave='job:teste'").fetchone()[0] == "ok"
    with pytest.raises(ValueError), ops.job(con, "teste"):
        raise ValueError("caiu")
    assert con.execute("SELECT valor FROM estado WHERE chave='job:teste'").fetchone()[0] == "erro: caiu"
    with ops.job(con, "longo"), pytest.raises(ops.JaRodando), ops.job(con, "longo"):
        pass


def test_falha_da_coleta_aparece_no_historico(con, tmp_path, monkeypatch):
    monkeypatch.setattr(controle, "RAIZ", tmp_path)
    monkeypatch.setenv("MFL_LOGS", str(tmp_path / "logs"))
    log.configurar("maps")
    with pytest.raises(ValueError), ops.job(con, "maps"):
        raise ValueError("Falha sintética no botão")
    eventos = controle.eventos("maps")
    assert eventos[0]["evento"] == "A coleta falhou" and eventos[0]["nivel"] == "error"
    assert "Falha sintética no botão" in eventos[0]["extra"]
    pagina = ui.criar_app(tmp_path / "t.db").test_client().get("/coleta?log=maps").get_data(as_text=True)
    assert "A coleta falhou" in pagina and "Falha sintética no botão" in pagina


def test_backup_local_ssd_e_poda(con, tmp_path, monkeypatch):
    ssd = tmp_path / "ssd"
    ssd.mkdir()
    monkeypatch.setattr(ops, "SSD", ssd)
    monkeypatch.setattr(ops.os.path, "ismount", lambda p: p == ssd)
    con.execute("INSERT INTO estado VALUES ('x', 'y', 'z')")
    con.commit()
    antigo = ops.LOCAL / "leads-2026-01-01.db.gz"
    antigo.parent.mkdir(parents=True)
    antigo.write_bytes(b"velho")
    feito = ops.backup(con, date(2026, 11, 24))  # terça: sem Orange Pi
    assert feito == {"local": True, "ssd": True, "pi": False}
    assert not antigo.exists()
    copia = tmp_path / "copia.db"
    copia.write_bytes(gzip.decompress((ssd / "mfl-leads" / "diario" / "leads-2026-11-24.db.gz").read_bytes()))
    assert sqlite3.connect(copia).execute("SELECT valor FROM estado WHERE chave='x'").fetchone()[0] == "y"
    assert (ssd / "mfl-leads" / "diario" / "cfg-2026-11-24.tar.gz").exists()
    assert (ssd / "mfl-leads" / "parquet" / "estab.parquet").exists()

    monkeypatch.setattr(ops.os.path, "ismount", lambda p: False)
    assert ops.backup(con, date(2026, 11, 25))["ssd"] is False  # SSD desmontado: só local, sem erro


def test_faixa_de_rotina_com_erro(con, tmp_path):
    con.execute("INSERT INTO estado VALUES ('job:maps', 'erro: bairros com falha: centro', '2026-11-24T02:00')")
    con.commit()
    cliente = ui.criar_app(tmp_path / "t.db").test_client()
    assert "Rotina com erro: maps" in cliente.get("/").get_data(as_text=True)
    assert "bairros com falha: centro" in cliente.get("/coleta").get_data(as_text=True)


def test_noite_do_maps_revisita_por_rendimento_horario_e_bloqueio(con, monkeypatch):
    from datetime import timedelta
    from mfl import cli
    hoje = date.today()
    todos = {"a": {"municipio": "Porto Alegre", "nome": "A"}, "b": {"municipio": "Porto Alegre", "nome": "B"},
             "c": {"municipio": "Canoas", "nome": "C"}, "d": {"municipio": "Canoas", "nome": "D"}}
    monkeypatch.setattr(cli.bairros, "carregar", lambda: todos)
    for chave, dias, lugares in (("a", 50, 30), ("b", 50, 3), ("c", 130, 3)):
        con.execute("INSERT INTO estado VALUES (?,?,?)", (f"maps:{chave}", (hoje - timedelta(days=dias)).isoformat(), "x"))
        con.execute("INSERT INTO estado VALUES (?,?,?)", (f"maps_rende:{chave}", str(lugares), "x"))
    con.commit()
    # d nunca raspado vem primeiro; a rendeu e venceu (45 d); b veio vazio e ainda não venceu (120 d); c venceu
    assert [k for k, _ in cli.pendentes_maps(con, hoje)] == ["d", "a", "c"]

    rodados = []
    def falso(chave, info):
        rodados.append(chave)
        return {"lugares": 0}
    monkeypatch.setattr(cli, "_maps_bairro", falso)
    monkeypatch.setattr(cli.score, "recalcular", lambda *a: None)
    with pytest.raises(RuntimeError, match="bloqueando"):
        cli._maps_fila(con, 12, None)
    assert rodados == ["d", "a"]  # dois vazios seguidos: para antes do c

    rodados.clear()
    hora = {"valor": "03:50"}
    def termina_tarde(chave, info):
        hora["valor"] = "04:00"
        return falso(chave, info)
    monkeypatch.setattr(cli, "_maps_bairro", termina_tarde)
    cli._maps_fila(con, 12, None, ate="04:00", agora=lambda: hora["valor"])
    assert rodados == ["d"]  # às 04:00 não começa outro
