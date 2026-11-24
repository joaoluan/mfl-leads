import json
import urllib.error
from datetime import date, timedelta

import pytest

from conftest import criar_lead
from mfl import cli, controle, db, ifood, maps, ops, ui
from test_ifood import loja

BAIRRO = {"nome": "Centro", "municipio": "Porto Alegre", "bbox": "-30.03,-51.21,-30.02,-51.19", "celula_km": 0.5}


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(maps, "RAIZ", tmp_path)
    return db.conectar(tmp_path / "t.db")


def lugar(l, pid="P1", telefone="51999990001"):
    return {"place_id": pid, "title": l.nome, "phone": telefone, "category": "Restaurante",
            "address": "Rua Fictícia, 10 - Centro, Porto Alegre - RS", "complete_address": {
                "city": "Porto Alegre", "borough": "Centro", "postal_code": "90000-001"},
            "web_site": "", "order_online": [{"link": l.url}], "emails": []}


def test_ponto_usa_endereco_comercial_do_bairro_e_nao_inventa(con):
    assert ifood.ponto_de_entrega(con, BAIRRO) is None
    criar_lead(con, "Outra Casa", None, municipio="Porto Alegre", bairro="Outro", endereco="Rua Outra, 20")
    criar_lead(con, "Casa Fechada", None, municipio="Porto Alegre", bairro="Centro", endereco="Rua Fechada, 20", status="descartado")
    criar_lead(con, "Casa Sem Número", None, municipio="Porto Alegre", bairro="Centro", endereco="Rua Fictícia, s/n")
    assert ifood.ponto_de_entrega(con, BAIRRO) is None
    criar_lead(con, "Casa de Teste", None, municipio="Porto Alegre", bairro="CENTRO", endereco="Rua Fictícia, 10")
    assert ifood.ponto_de_entrega(con, BAIRRO) == "Rua Fictícia, 10, Porto Alegre - RS"


def test_maps_completa_descoberta_ifood_e_nao_repete_busca(con, monkeypatch):
    l = loja()
    ifood.ingerir(con, [l], [])
    eid = con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0]
    chamadas = []
    def raspar(bairro, saida, log, consultas=None):
        chamadas.append(consultas.read_text())
        saida.write_text(json.dumps(lugar(l)))
        return saida
    monkeypatch.setattr(maps, "rodar", raspar)
    assert maps.completar_ifood(con, "centro", BAIRRO) == 1
    assert chamadas == ["Cantina Teste Azul Porto Alegre RS\n"]
    assert tuple(con.execute("SELECT place_id,tel1,status FROM entity WHERE entity_id=?", (eid,)).fetchone()) == ("P1", "+5551999990001", "novo")
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 1
    assert {r[0] for r in con.execute("SELECT source FROM source_record WHERE entity_id=?", (eid,))} == {"maps", "ifood"}
    assert tuple(con.execute("SELECT tries,done FROM queue WHERE kind='maps_ifood'").fetchone()) == (1, 1)
    assert maps.completar_ifood(con, "outro", BAIRRO) == 0


def test_nome_sozinho_mantem_revisao_e_busca_espera_sete_dias(con, monkeypatch):
    l = loja()
    ifood.ingerir(con, [l], [])
    def raspar(bairro, saida, log, consultas=None):
        dados = lugar(l)
        dados["order_online"] = []
        saida.write_text(json.dumps(dados))
        return saida
    monkeypatch.setattr(maps, "rodar", raspar)
    maps.completar_ifood(con, "centro", BAIRRO)
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM revisao WHERE decidido=0").fetchone()[0] == 1
    fila = con.execute("SELECT tries,done,next_at FROM queue WHERE kind='maps_ifood'").fetchone()
    assert tuple(fila) == (1, 0, (date.today() + timedelta(days=7)).isoformat())
    assert maps.completar_ifood(con, "centro", BAIRRO) == 0


def test_maps_ja_conhecido_absorve_ifood_so_por_uuid_comprovado(con, tmp_path):
    l = loja()
    arquivo = tmp_path / "maps.json"
    dados = lugar(l)
    dados["order_online"] = []
    arquivo.write_text(json.dumps(dados))
    maps.ingerir(con, arquivo, BAIRRO, ["Porto Alegre"], [])
    original = con.execute("SELECT entity_id FROM entity WHERE place_id='P1'").fetchone()[0]
    ifood.ingerir(con, [l], [])
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 2
    arquivo.write_text(json.dumps(lugar(l)))
    assert maps.ingerir(con, arquivo, BAIRRO, ["Porto Alegre"], [])["repetidos"] == 1
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 1
    assert con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0] == original


def test_ifood_marca_bairro_so_depois_de_sucesso(con, monkeypatch):
    hoje = date.today()
    monkeypatch.setattr(cli.bairros, "carregar", lambda: {"centro": BAIRRO})
    assert cli.pendentes_ifood(con, hoje) == [("centro", BAIRRO)]
    assert cli._ifood_bairro(con, "centro", BAIRRO) is False
    assert not con.execute("SELECT 1 FROM estado WHERE chave='ifood_bairro:centro'").fetchone()
    criar_lead(con, "Casa de Teste", None, municipio="Porto Alegre", bairro="Centro", endereco="Rua Fictícia, 10")
    monkeypatch.setattr(ifood, "rodar", lambda *args: {"novos": 1})
    assert cli._ifood_bairro(con, "centro", BAIRRO) is True
    assert cli.pendentes_ifood(con, hoje) == []
    assert cli.pendentes_ifood(con, hoje + timedelta(days=60)) == [("centro", BAIRRO)]
    def bloqueado(*args):
        raise RuntimeError("verificação")
    monkeypatch.setattr(ifood, "rodar", bloqueado)
    with pytest.raises(RuntimeError, match="verificação"):
        cli._ifood_bairro(con, "outro", BAIRRO)
    assert not con.execute("SELECT 1 FROM estado WHERE chave='ifood_bairro:outro'").fetchone()


def test_noite_fontes_completam_sequencialmente_e_falha_ifood_nao_para_maps(con, monkeypatch):
    todos = {"a": BAIRRO, "b": {**BAIRRO, "nome": "Outro"}}
    monkeypatch.setattr(cli.bairros, "carregar", lambda: todos)
    monkeypatch.setattr(cli.score, "recalcular", lambda *a: None)
    chamadas = []
    def raspar(chave, info):
        chamadas.append(("maps", chave))
        return {"lugares": 10}
    def comida(con, chave, info):
        chamadas.append(("ifood", chave))
        raise RuntimeError("verificação")
    monkeypatch.setattr(cli, "_maps_bairro", raspar)
    monkeypatch.setattr(cli, "_ifood_bairro", comida)
    monkeypatch.setattr(maps, "completar_ifood", lambda con, chave, info: chamadas.append(("buscar", chave)))
    with pytest.raises(RuntimeError, match="iFood:a"):
        cli._maps_fila(con, 2, None)
    assert chamadas == [("maps", "a"), ("ifood", "a"), ("buscar", "a"), ("maps", "b"), ("buscar", "b")]


def test_bairro_maps_em_dia_ainda_coleta_ifood(con, monkeypatch):
    monkeypatch.setattr(cli.bairros, "carregar", lambda: {"centro": BAIRRO})
    con.execute("INSERT INTO estado VALUES ('maps:centro',?,?)", (date.today().isoformat(), db.agora()))
    con.commit()
    monkeypatch.setattr(cli, "_maps_bairro", lambda *args: pytest.fail("Maps não venceu"))
    monkeypatch.setattr(cli.score, "recalcular", lambda *args: None)
    chamadas = []
    monkeypatch.setattr(cli, "_ifood_bairro", lambda con, chave, info: chamadas.append("ifood"))
    monkeypatch.setattr(maps, "completar_ifood", lambda *args: chamadas.append("buscar"))
    cli._maps_fila(con, 1, None)
    assert chamadas == ["ifood", "buscar"]


def test_duas_respostas_maps_vazias_param_so_google(con, monkeypatch):
    todos = {str(n): {**BAIRRO, "nome": str(n)} for n in range(3)}
    monkeypatch.setattr(cli.bairros, "carregar", lambda: todos)
    monkeypatch.setattr(cli.score, "recalcular", lambda *args: None)
    fontes = []
    monkeypatch.setattr(cli, "_maps_bairro", lambda chave, info: fontes.append(("maps", chave)) or {"lugares": 0})
    monkeypatch.setattr(cli, "_ifood_bairro", lambda con, chave, info: fontes.append(("ifood", chave)))
    monkeypatch.setattr(maps, "completar_ifood", lambda *args: 0)
    with pytest.raises(RuntimeError, match="Maps interrompido"):
        cli._maps_fila(con, 3, None)
    assert [f for f in fontes if f[0] == "maps"] == [("maps", "0"), ("maps", "1")]
    assert [f for f in fontes if f[0] == "ifood"] == [("ifood", "0"), ("ifood", "1"), ("ifood", "2")]


def test_falha_da_busca_reserva_tentativa_para_amanha(con, monkeypatch):
    ifood.ingerir(con, [loja()], [])
    def falhar(*args):
        raise OSError("falha simulada")
    monkeypatch.setattr(maps, "rodar", falhar)
    with pytest.raises(OSError, match="falha simulada"):
        maps.completar_ifood(con, "centro", BAIRRO)
    assert tuple(con.execute("SELECT tries,next_at,done FROM queue WHERE kind='maps_ifood'").fetchone()) == (
        1, (date.today() + timedelta(days=1)).isoformat(), 0)
    assert maps.completar_ifood(con, "outro", BAIRRO) == 0


def test_coleta_mostra_data_ifood_e_timer_compartilhado(con, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.bairros, "carregar", lambda: {"centro": BAIRRO})
    monkeypatch.setattr(controle, "_proximas", lambda: {"mfl-maps.timer": "2026-11-25 01:30"})
    con.execute("INSERT INTO estado VALUES ('ifood_bairro:centro','2026-11-24',?)", (db.agora(),))
    con.commit()
    rotinas = {r["job"]: r for r in controle.rotinas(con)}
    assert rotinas["ifood"]["proxima"] == rotinas["maps"]["proxima"] == "2026-11-25 01:30"
    pagina = ui.criar_app(tmp_path / "t.db").test_client().get("/coleta").get_data(as_text=True)
    assert "Último iFood" in pagina and "24/11/2026" in pagina and "01h30" in pagina


def test_leitura_aguarda_navegacao_sem_repetir_acao(monkeypatch):
    resultados = iter([urllib.error.HTTPError("local", 409, "navegando", None, None), False, "carregou"])
    def js(*args):
        resultado = next(resultados)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado
    monkeypatch.setattr(ifood, "_js", js)
    monkeypatch.setattr(ifood.time, "sleep", lambda *_: None)
    assert ifood._esperar("aba", "somente leitura") == "carregou"


def test_complemento_pendente_entra_na_noite_com_as_duas_fontes_em_dia(con, monkeypatch):
    monkeypatch.setattr(cli.bairros, "carregar", lambda: {"centro": BAIRRO})
    for fonte in ("maps", "ifood_bairro"):
        con.execute("INSERT INTO estado VALUES (?,?,?)", (f"{fonte}:centro", date.today().isoformat(), db.agora()))
    con.commit()
    ifood.ingerir(con, [loja()], [])
    monkeypatch.setattr(cli, "_maps_bairro", lambda *a: pytest.fail("Maps está em dia"))
    monkeypatch.setattr(cli, "_ifood_bairro", lambda *a: pytest.fail("iFood está em dia"))
    monkeypatch.setattr(cli.score, "recalcular", lambda *a: None)
    buscados = []
    monkeypatch.setattr(maps, "completar_ifood", lambda con, chave, info: buscados.append(chave))
    cli._maps_fila(con, 1, None)
    assert buscados == ["centro"]


def test_bairro_sem_ponto_nao_trava_fila_ifood(con, monkeypatch):
    monkeypatch.setattr(cli.bairros, "carregar", lambda: {"a": BAIRRO, "b": {**BAIRRO, "nome": "Outro"}})
    assert [k for k, _ in cli.pendentes_ifood(con, date.today())] == ["a", "b"]
    assert cli._ifood_bairro(con, "a", BAIRRO) is False
    assert [k for k, _ in cli.pendentes_ifood(con, date.today())] == ["b", "a"]


def test_nao_inicia_ifood_ou_busca_depois_do_horario(con, monkeypatch):
    monkeypatch.setattr(cli.bairros, "carregar", lambda: {"centro": BAIRRO})
    hora = {"valor": "03:50"}
    def termina_tarde(*args):
        hora["valor"] = "04:01"
        return {"lugares": 10}
    monkeypatch.setattr(cli, "_maps_bairro", termina_tarde)
    monkeypatch.setattr(cli, "_ifood_bairro", lambda *a: pytest.fail("iFood passou do horário"))
    monkeypatch.setattr(maps, "completar_ifood", lambda *a: pytest.fail("Busca passou do horário"))
    monkeypatch.setattr(cli.score, "recalcular", lambda *a: None)
    cli._maps_fila(con, 1, None, ate="04:00", agora=lambda: hora["valor"])


def test_varios_uuids_nao_absorvem_duas_lojas_distintas(con, tmp_path):
    lojas = [loja(), loja(2, nome="Cozinha Teste Verde")]
    ifood.ingerir(con, lojas, [])
    dados = lugar(lojas[0])
    dados["order_online"] = [{"link": l.url} for l in lojas]
    arquivo = tmp_path / "maps.json"
    arquivo.write_text(json.dumps(dados))
    maps.ingerir(con, arquivo, BAIRRO, ["Porto Alegre"], [])
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 3
    assert con.execute("SELECT count(DISTINCT entity_id) FROM source_record WHERE source='ifood'").fetchone()[0] == 2
