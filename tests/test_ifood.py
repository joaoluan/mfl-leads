import json
import sqlite3
import uuid
from datetime import date

import pytest
from typer.testing import CliRunner

from conftest import criar_lead
from mfl import cadencia, cli, controle, db, ifood, log, ops, resolve, score, ui, whatsapp

HOJE = date(2026, 11, 24)


def item(n=1, nome="Cantina Teste Azul", cidade="porto-alegre-rs", **campos):
    return {"url": f"https://www.ifood.com.br/delivery/{cidade}/cantina-teste-centro/{uuid.UUID(int=n)}",
            "nome": nome, "categoria": "Brasileira", **campos}


def loja(n=1, **campos):
    return ifood.analisar(item(n, **campos), ["Porto Alegre", "Canoas"])


def test_analise_confere_origem_cidade_id_e_minimiza_dados():
    raw = item(detalhes={"endereco": "Rua Fictícia, 10", "cep": "90000-001", "municipio": "Porto Alegre", "uf": "RS"},
               telefone="51999990000", reviews=[{"author": "Pessoa de teste"}])
    l = ifood.analisar(raw, ["Porto Alegre"])
    assert l.endereco == "Rua Fictícia, 10" and l.cep == "90000001"
    assert "telefone" not in l.model_dump() and "reviews" not in l.model_dump()
    assert ifood.analisar(item(cidade="pelotas-rs"), ["Porto Alegre"]) is None
    for url in (raw["url"].replace("www.ifood.com.br", "www.ifood.com.br.evil.test"),
                raw["url"].replace("https:", "http:"), raw["url"].rsplit("/", 1)[0] + "/invalido"):
        assert ifood.analisar({**raw, "url": url}, ["Porto Alegre"]) is None
    assert loja(detalhes={"endereco": "Rua Errada, 10", "municipio": "Canoas"}).endereco is None


def test_ingestao_idempotente_score_fila_e_revisao(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    existente = criar_lead(con, "Cantina Teste Azul", "+5551999990001", municipio="Porto Alegre",
                          cep="90000001", endereco="Rua Fictícia, 10")
    resultado = ifood.ingerir(con, [loja(), loja(2, nome="Cozinha Teste Verde"), loja(3, nome="Rede Falsa")], ["rede falsa"])
    assert resultado == {"novos": 2, "vinculados": 0, "revisao": 1, "repetidos": 0, "descartados": 1}
    assert con.execute("SELECT count(*) FROM entity WHERE status='enriquecimento' AND tel1 IS NULL").fetchone()[0] == 2
    assert tuple(con.execute("SELECT b,score FROM revisao").fetchone()) == (existente, resolve.REVISA)
    assert ifood.ingerir(con, [loja()], [])["repetidos"] == 1
    score.recalcular(con, HOJE)
    l = con.execute("SELECT * FROM entity WHERE entity_id=(SELECT entity_id FROM source_record WHERE source='ifood' LIMIT 1)").fetchone()
    assert json.loads(l["sinais"]).count("vende_ifood") == 1
    con.execute("UPDATE entity SET score=100 WHERE status='enriquecimento'")
    assert all(r[0]["entity_id"] == existente for r in cadencia.fila(con, HOJE, 30))
    assert con.execute("SELECT count(*) FROM validacao").fetchone()[0] == 0
    registro = con.execute("SELECT url,captured_at,hash FROM source_record WHERE source='ifood' LIMIT 1").fetchone()
    assert all(registro) and len(registro["hash"]) == 64


def test_endereco_vincula_sem_alterar_telefone_ou_cliente_e_opt_out_nao_volta(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    eid = criar_lead(con, "Cantina Teste Azul", "+5551999990002", municipio="Porto Alegre",
                     cep="90000001", endereco="Rua Fictícia, 10", status="cliente")
    l = loja(detalhes={"endereco": "Rua Fictícia, 10", "cep": "90000-001"})
    assert ifood.ingerir(con, [l], [])["vinculados"] == 1
    assert tuple(con.execute("SELECT tel1,status FROM entity WHERE entity_id=?", (eid,)).fetchone()) == ("+5551999990002", "cliente")
    assert con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0] == eid
    whatsapp.marcar_opt_out(con, eid, "teste")
    assert ifood.ingerir(con, [loja(2)], [])["descartados"] == 1
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 1


def test_maps_posterior_encontra_ifood_sem_cep_so_para_revisao(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    ifood.ingerir(con, [loja()], [])
    novo = {"_fonte": "maps", "nome": "Cantina Teste Azul", "municipio": "Porto Alegre", "cep": "90000001"}
    candidato, nota = resolve.melhor_candidato(con, novo, set())
    assert candidato is not None and nota == resolve.REVISA
    assert resolve.melhor_candidato(con, {**novo, "municipio": "Canoas"}, set()) == (None, 0.0)
    assert resolve.melhor_candidato(con, {**novo, "nome": "Outra Casa Distinta"}, set()) == (None, 0.0)


def test_migracao_preserva_fontes_ids_e_indices(tmp_path):
    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript(db.SCHEMA.read_text())
    for arquivo in sorted(db.MIGRACOES.glob("00[234]_*.sql")):
        antigo.executescript(arquivo.read_text())
    antigo.execute("INSERT INTO entity(entity_id,nome) VALUES ('antigo','Casa Fictícia')")
    antigo.execute("INSERT INTO source_record(id,source,source_key,entity_id,raw_json,captured_at)"
                   " VALUES (42,'maps','antes','antigo','{}','2026-01-01')")
    antigo.execute("PRAGMA user_version=4")
    antigo.commit()
    antigo.close()
    con = db.conectar(caminho)
    assert tuple(con.execute("SELECT id,source,source_key,entity_id FROM source_record").fetchone()) == (42, "maps", "antes", "antigo")
    assert con.execute("PRAGMA user_version").fetchone()[0] == 5
    assert not con.execute("PRAGMA foreign_key_check").fetchall()
    assert "source_record_entity" in {r[1] for r in con.execute("PRAGMA index_list(source_record)")}
    assert ifood.ingerir(con, [loja()], [])["novos"] == 1
    con.close()
    assert db.conectar(caminho).execute("SELECT count(*) FROM source_record").fetchone()[0] == 2


def test_cli_coleta_e_ui_filtra_e_dispara(tmp_path, monkeypatch):
    caminho = tmp_path / "t.db"
    monkeypatch.setenv("MFL_DB", str(caminho))
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(log, "configurar", lambda *_: None)
    chamadas = []
    def coletar(endereco, limite, conhecidos, municipios):
        chamadas.append((endereco, limite, conhecidos))
        return [loja()]
    monkeypatch.setattr(ifood, "coletar", coletar)
    resultado = CliRunner().invoke(cli.app, ["ifood", "Rua Fictícia, 10, Porto Alegre", "--limite", "3"])
    assert resultado.exit_code == 0, resultado.exception
    assert chamadas == [("Rua Fictícia, 10, Porto Alegre", 3, set())]
    con = db.conectar(caminho)
    assert con.execute("SELECT valor FROM estado WHERE chave='job:ifood'").fetchone()[0] == "ok"
    cliente = ui.criar_app(caminho).test_client()
    assert "Cantina Teste Azul" in cliente.get("/leads?fonte=ifood").get_data(as_text=True)
    assert "Cantina Teste Azul" not in cliente.get("/leads?fonte=maps").get_data(as_text=True)
    monkeypatch.setattr(controle, "_proximas", lambda: {})
    assert "Coletar iFood" in cliente.get("/coleta").get_data(as_text=True)
    disparos = []
    monkeypatch.setattr(controle, "disparar", lambda *args: disparos.append(args))
    assert cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": "Rua Fictícia, 10, Porto Alegre", "limite": "3"}).status_code == 302
    assert disparos == [("ifood", "ifood", "Rua Fictícia, 10, Porto Alegre", "--limite", "3")]
    assert cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": ""}).status_code == 400
    assert cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": "x", "limite": "101"}).status_code == 400


def test_bloqueio_encerra_e_fecha_aba_sem_gravar(tmp_path, monkeypatch):
    con = db.conectar(tmp_path / "t.db")
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba-teste")
    chamadas = []
    def api(metodo, caminho, corpo=None):
        chamadas.append((metodo, caminho))
        return {"result": True}  # detector de checkpoint
    monkeypatch.setattr(ifood, "api", api)
    with pytest.raises(RuntimeError, match="verificação"):
        ifood.rodar(con, "Rua Fictícia, 10, Porto Alegre", 3)
    assert chamadas[-1] == ("DELETE", "/tabs/aba-teste?userId=mfl-ifood")
    assert con.execute("SELECT count(*) FROM source_record").fetchone()[0] == 0


def test_sinal_ifood_nao_duplica():
    lead = {"categoria": None, "municipio": "Porto Alegre", "nome": "Casa Teste", "fantasia": None}
    fontes = {"ifood": [{}], "maps": [{"user_reviews": [{"Description": "ifood"}]}], "instagram": [{"bio": "ifood"}]}
    assert score.sinais(lead, fontes, set(), HOJE, set(), None).count("vende_ifood") == 1


def test_falha_no_lote_nao_deixa_entidade_sem_fonte(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    con.execute("CREATE TRIGGER falha_ifood BEFORE INSERT ON source_record WHEN NEW.source='ifood'"
                " BEGIN SELECT RAISE(ABORT, 'falha simulada'); END")
    con.commit()
    with pytest.raises(sqlite3.IntegrityError, match="falha simulada"):
        ifood.ingerir(con, [loja()], [])
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM source_record").fetchone()[0] == 0
