import json
import sqlite3
import uuid
from datetime import date
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from conftest import criar_lead
from mfl import cadencia, cli, controle, db, ifood, log, ops, resolve, score, ui, whatsapp

HOJE = date(2026, 11, 24)


@pytest.fixture
def elementos(monkeypatch):
    alvos = {}
    monkeypatch.setattr(ifood, "_elemento", lambda aba, seletor, **kw: alvos.setdefault(seletor, Mock()))
    return alvos


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
    assert resultado == {"novos": 3, "vinculados": 0, "revisao": 1, "repetidos": 0, "descartados": 0, "atualizados": 0}  # franquia entra
    assert con.execute("SELECT count(*) FROM entity WHERE status='enriquecimento' AND tel1 IS NULL").fetchone()[0] == 3
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
    def coletar(endereco, limite, conhecidos, municipios, **opcoes):
        chamadas.append((endereco, limite, conhecidos))
        return [loja()], None
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
    assert cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": "x", "limite": "1001"}).status_code == 400


@pytest.mark.parametrize("limite", [101, 1000])
def test_limite_ifood_da_tela_ate_coletor(tmp_path, monkeypatch, limite):
    caminho = tmp_path / "t.db"
    monkeypatch.setenv("MFL_DB", str(caminho))
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(log, "configurar", lambda *_: None)
    monkeypatch.setattr(controle, "_proximas", lambda: {})
    recebidos = []
    def coletar(endereco, quantidade, conhecidos, municipios, **opcoes):
        recebidos.append(quantidade)
        return [], None
    monkeypatch.setattr(ifood, "coletar", coletar)
    def disparar(job, *args):
        assert job == "ifood"
        resultado = CliRunner().invoke(cli.app, list(args))
        assert resultado.exit_code == 0, resultado.output
    monkeypatch.setattr(controle, "disparar", disparar)
    cliente = ui.criar_app(caminho).test_client()
    assert f'max="{ifood.LIMITE_MAX}"' in cliente.get("/coleta").get_data(as_text=True)
    endereco = "Rua Fictícia, 10, Porto Alegre"
    assert cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": endereco, "limite": str(limite)}).status_code == 302
    assert recebidos == [limite]
    assert cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": endereco, "limite": "1001"}).status_code == 400
    assert CliRunner().invoke(cli.app, ["ifood", endereco, "--limite", "1001"]).exit_code == 2
    with pytest.raises(ValueError, match="1000"):
        ifood.rodar(db.conectar(caminho), endereco, 1001)
    assert recebidos == [limite]


def test_bloqueio_encerra_e_fecha_aba_sem_gravar(tmp_path, monkeypatch):
    con = db.conectar(tmp_path / "t.db")
    fechadas = []
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba-teste")
    monkeypatch.setattr(ifood, "_fechar", lambda aba: fechadas.append(aba))
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    monkeypatch.setattr(ifood, "_esperar",
                        lambda aba, exp: (_ for _ in ()).throw(ifood.DetalhesBloqueados("iFood pediu verificação")))
    with pytest.raises(RuntimeError, match="verificação"):
        ifood.rodar(con, "Rua Fictícia, 10, Porto Alegre", 3)
    assert fechadas == ["aba-teste"]
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


# Ordem 0000 não identifica estabelecimento real; dígitos verificadores sintéticos.
CNPJ_TESTE = "98765432000007"
# Resposta merchant-info/graphql fictícia, no mesmo formato que o iFood devolve.
INFO = {"data": {"merchantExtra": {
    "address": {"streetName": "Rua Fictícia", "streetNumber": "123", "district": "Bairro Teste",
                "city": "PORTO ALEGRE", "state": "RS", "zipCode": "90000001"},
    "documents": {"CNPJ": {"value": CNPJ_TESTE}},
}}}


def test_merchant_info_extrai_endereco_bairro_cep_e_cnpj():
    detalhe = ifood._ler_info(INFO)
    assert detalhe == {"endereco": "Rua Fictícia 123", "bairro": "Bairro Teste", "cep": "90000001",
                       "municipio": "PORTO ALEGRE", "uf": "RS", "cnpj": CNPJ_TESTE}
    l = loja(detalhes=detalhe)
    assert (l.endereco, l.bairro, l.cep, l.cnpj) == ("Rua Fictícia 123", "Bairro Teste", "90000001", CNPJ_TESTE)
    assert ifood.cnpj_valido("98.765.432/0000-08") is None
    assert ifood.cnpj_valido("11.111.111/1111-11") is None
    assert ifood.cnpj_valido(123) is None
    assert loja(detalhes={**detalhe, "municipio": "Canoas"}).cnpj is None


def test_ler_detalhes_usa_merchant_info(monkeypatch):
    monkeypatch.setattr(ifood, "_ler_resposta_info", lambda aba, url: INFO)
    l = ifood.ler_detalhes("aba", loja(), ["Porto Alegre"])
    assert l.cnpj == CNPJ_TESTE and l.endereco == "Rua Fictícia 123" and l.detalhes_em


def test_cnpj_vincula_receita_mesmo_com_nome_diferente(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    eid = criar_lead(con, "Nome Antigo Fictício", None, cnpj=CNPJ_TESTE, status="enriquecimento", municipio="Porto Alegre")
    assert ifood.ingerir(con, [loja(detalhes={"cnpj": CNPJ_TESTE, "endereco": "Rua Fictícia, 10"})], [])["vinculados"] == 1
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 1
    assert con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0] == eid
    assert con.execute("SELECT endereco FROM entity WHERE entity_id=?", (eid,)).fetchone()[0] == "Rua Fictícia, 10"


def test_loja_antiga_completa_sem_duplicar_e_sem_apagar_dados(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    ifood.ingerir(con, [loja()], [])
    eid = con.execute("SELECT entity_id FROM entity").fetchone()[0]
    completa = loja(detalhes={"endereco": "Rua Fictícia, 10 - Centro", "cep": "90000001", "bairro": "Centro", "cnpj": CNPJ_TESTE})
    assert ifood.ingerir(con, [completa], [])["atualizados"] == 1
    assert tuple(con.execute("SELECT endereco,cep,bairro,cnpj FROM entity WHERE entity_id=?", (eid,)).fetchone()) == (
        "Rua Fictícia, 10 - Centro", "90000001", "Centro", CNPJ_TESTE)
    ifood.ingerir(con, [loja()], [])  # próxima leitura parcial não apaga os detalhes já coletados
    raw = json.loads(con.execute("SELECT raw_json FROM source_record").fetchone()[0])
    assert raw["cnpj"] == CNPJ_TESTE and raw["endereco"] == completa.endereco
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM source_record").fetchone()[0] == 1


def test_backfill_funde_descoberta_provisoria_com_dono_do_cnpj(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    eid = criar_lead(con, "Nome Antigo Fictício", None, cnpj=CNPJ_TESTE, municipio="Porto Alegre", status="enriquecimento")
    ifood.ingerir(con, [loja()], [])
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 2
    assert ifood.ingerir(con, [loja(detalhes={"cnpj": CNPJ_TESTE})], [])["atualizados"] == 1
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 1
    assert con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0] == eid
    assert con.execute("SELECT cnpj FROM entity").fetchone()[0] == CNPJ_TESTE


def test_backfill_preserva_conversa_e_manda_conflito_de_cnpj_para_revisao(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    dono = criar_lead(con, "Nome Antigo Fictício", None, cnpj=CNPJ_TESTE, municipio="Porto Alegre", status="enriquecimento")
    ifood.ingerir(con, [loja()], [])
    eid = con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0]
    con.execute("INSERT INTO touch(entity_id,texto,enviado_em) VALUES (?,'texto fictício',?)", (eid, db.agora()))
    con.commit()
    assert ifood.ingerir(con, [loja(detalhes={"cnpj": CNPJ_TESTE})], [])["revisao"] == 1
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == 2
    assert con.execute("SELECT entity_id FROM touch").fetchone()[0] == eid
    assert tuple(con.execute("SELECT a,b FROM revisao WHERE decidido=0").fetchone()) == (eid, dono)
    assert con.execute("SELECT cnpj FROM entity WHERE entity_id=?", (eid,)).fetchone()[0] is None


def test_recoleta_incompletos_usa_data_dos_detalhes(tmp_path, monkeypatch):
    con = db.conectar(tmp_path / "t.db")
    ifood.ingerir(con, [loja()], [])
    raw = json.loads(con.execute("SELECT raw_json FROM source_record").fetchone()[0])
    raw.pop("cnpj")  # formato anterior à correção
    con.execute("UPDATE source_record SET raw_json=?", (json.dumps(raw),))
    con.commit()
    conhecidos = []
    def coletar(endereco, limite, ignorados, municipios, **opcoes):
        conhecidos.append((ignorados, opcoes["revisitar"]))
        return [loja().model_copy(update={"detalhes_em": db.agora()})], None
    monkeypatch.setattr(ifood, "coletar", coletar)
    ifood.rodar(con, "Rua Fictícia, 10, Porto Alegre", 1)
    ifood.rodar(con, "Rua Fictícia, 10, Porto Alegre", 1)
    identificador = str(loja().id)
    assert conhecidos == [({identificador}, {identificador}), ({identificador}, set())]


@pytest.mark.parametrize("bloqueado", [False, True])
def test_lote_segue_sem_detalhes_mas_respeita_bloqueio(monkeypatch, bloqueado, elementos):
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba")
    monkeypatch.setattr(ifood, "_esperar", lambda *a: True)
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    monkeypatch.setattr(ifood, "_fechar", lambda aba: None)
    monkeypatch.setattr(ifood, "_js", lambda aba, js: [item(), item(2, nome="Cozinha Teste Verde")] if js == ifood.JS_LISTA else True)
    visitadas = []
    def detalhes(aba, l, municipios):
        visitadas.append(l.id)
        if len(visitadas) == 1:
            if bloqueado:
                raise ifood.DetalhesBloqueados("403")
            return l
        return loja(2, nome="Cozinha Teste Verde", detalhes={"cnpj": CNPJ_TESTE})
    monkeypatch.setattr(ifood, "ler_detalhes", detalhes)
    lojas, motivo = ifood.coletar("Rua Fictícia, 10, Porto Alegre", 2, set(), ["Porto Alegre"])
    assert len(lojas) == 2
    assert len(visitadas) == (1 if bloqueado else 2)
    assert lojas[1].cnpj == (None if bloqueado else CNPJ_TESTE)
    assert motivo == ("403" if bloqueado else None)


def test_leitura_parcial_nao_funde_cnpjs_distintos_pelo_endereco(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    primeiro = criar_lead(con, "Nome Antigo Fictício", None, cnpj=CNPJ_TESTE, status="enriquecimento", municipio="Porto Alegre")
    ifood.ingerir(con, [loja(detalhes={"cnpj": CNPJ_TESTE})], [])
    segundo = criar_lead(con, "Cantina Teste Azul", None, cnpj="87654321000007", status="enriquecimento",
                         municipio="Porto Alegre", cep="90000001", endereco="Rua Fictícia, 10")
    parcial = loja(detalhes={"endereco": "Rua Fictícia, 10", "cep": "90000001"})
    assert ifood.ingerir(con, [parcial], [])["revisao"] == 1
    assert {r[0] for r in con.execute("SELECT cnpj FROM entity")} == {CNPJ_TESTE, "87654321000007"}
    assert con.execute("SELECT entity_id FROM source_record WHERE source='ifood'").fetchone()[0] == primeiro
    assert tuple(con.execute("SELECT a,b FROM revisao WHERE decidido=0").fetchone()) == (primeiro, segundo)


def test_merchant_info_parcial_vale_e_ausencia_bloqueia(monkeypatch):
    parcial = {"data": {"merchantExtra": {"address": {"streetName": "Rua Fictícia", "streetNumber": "10"}}}}
    monkeypatch.setattr(ifood, "_ler_resposta_info", lambda aba, url: parcial)
    l = ifood.ler_detalhes("aba", loja(), ["Porto Alegre"])
    assert l.endereco == "Rua Fictícia 10" and l.cnpj is None
    monkeypatch.setattr(ifood, "_ler_resposta_info", lambda aba, url: None)
    with pytest.raises(ifood.DetalhesBloqueados):
        ifood.ler_detalhes("aba", loja(), ["Porto Alegre"])


def evento_info(status=200):
    return {"message": json.dumps({"message": {"method": "Network.responseReceived", "params": {
        "requestId": "pedido-sintetico", "response": {
            "url": "https://exemplo.test/merchant-info/graphql", "status": status,
        },
    }}})}


@pytest.mark.parametrize("conectado", [True, False])
def test_js_usa_sintaxe_do_protocolo_ativo(conectado):
    aba = Mock()
    aba.is_connected.return_value = conectado
    aba.execute_script.return_value = aba.cdp.evaluate.return_value = {"ok": True}
    assert ifood._js(aba, "({ok:true})") == {"ok": True}
    if conectado:
        aba.execute_script.assert_called_once_with("return (({ok:true}));")
        aba.cdp.evaluate.assert_not_called()
    else:
        aba.cdp.evaluate.assert_called_once_with("(({ok:true}))")
        aba.execute_script.assert_not_called()


def test_comando_nativo_reconecta_webdriver_sem_clique_js(monkeypatch):
    aba = Mock()
    aba.is_connected.return_value = False
    monkeypatch.setattr(ifood, "_js", lambda *a: False)
    alvo = Mock()
    aba.driver.find_elements.return_value = [alvo]
    ifood._elemento(aba, "button").click()
    aba.driver.connect.assert_called_once()
    alvo.click.assert_called_once()
    aba.execute_script.assert_not_called()


def test_resposta_pendente_nao_perde_request_id_nem_repete_requisicao(monkeypatch):
    aba = Mock()
    aba.driver.get_log.side_effect = [[], [evento_info()], []]
    aba.driver.execute_cdp_cmd.side_effect = [
        ifood.WebDriverException("corpo ainda não disponível"), {"body": json.dumps(INFO)},
    ]
    monkeypatch.setattr(ifood, "_ir", lambda *a: None)
    monkeypatch.setattr(ifood, "_verificar", lambda *a: 0)
    assert ifood._ler_resposta_info(aba, loja().url) == INFO
    assert aba.driver.execute_cdp_cmd.call_count == 2
    assert all(c.args == ("Network.getResponseBody", {"requestId": "pedido-sintetico"})
               for c in aba.driver.execute_cdp_cmd.call_args_list)
    aba.refresh.assert_not_called()


@pytest.mark.parametrize("status", [403, 429])
def test_bloqueio_confirmado_nao_recarrega_nem_le_corpo(monkeypatch, status):
    aba = Mock()
    aba.driver.get_log.side_effect = [[], [evento_info(status)]]
    monkeypatch.setattr(ifood, "_ir", lambda *a: None)
    monkeypatch.setattr(ifood, "_verificar", lambda *a: 0)
    with pytest.raises(ifood.DetalhesBloqueados, match=f"HTTP {status}"):
        ifood._ler_resposta_info(aba, loja().url)
    aba.refresh.assert_not_called()
    aba.driver.execute_cdp_cmd.assert_not_called()


def test_recarrega_uma_vez_quando_uc_nao_expoe_primeira_resposta(monkeypatch):
    aba = Mock()
    aba.driver.get_log.side_effect = [[], [], [evento_info()]]
    aba.driver.execute_cdp_cmd.return_value = {"body": json.dumps(INFO)}
    monkeypatch.setattr(ifood, "_ir", lambda *a: None)
    monkeypatch.setattr(ifood, "_verificar", lambda *a: 0)
    assert ifood._ler_resposta_info(aba, loja().url) == INFO
    aba.refresh.assert_called_once()


def test_resposta_invalida_informa_erro_sem_inventar_403(monkeypatch):
    aba = Mock()
    aba.driver.get_log.side_effect = [[], [evento_info()]]
    aba.driver.execute_cdp_cmd.return_value = {"body": "{"}
    monkeypatch.setattr(ifood, "_ir", lambda *a: None)
    monkeypatch.setattr(ifood, "_verificar", lambda *a: 0)
    with pytest.raises(ifood.DetalhesBloqueados, match="inválida") as erro:
        ifood._ler_resposta_info(aba, loja().url)
    assert "403" not in str(erro.value)
    aba.refresh.assert_not_called()


def test_checkpoint_impede_clique_nativo(monkeypatch):
    aba = Mock()
    aba._mfl_ao_verificar = None
    monkeypatch.setattr(ifood, "_js", lambda aba, expr: expr == ifood.JS_CHECKPOINT)
    with pytest.raises(ifood.DetalhesBloqueados, match="HUMAN"):
        ifood._elemento(aba, "button").click()
    aba.driver.find_elements.assert_not_called()


def test_elemento_aguarda_visibilidade_habilitacao_e_recriacao(monkeypatch):
    aba = Mock()
    oculto, desabilitado, antigo, pronto = (Mock() for _ in range(4))
    oculto.is_displayed.return_value = False
    desabilitado.is_enabled.return_value = False
    antigo.is_displayed.side_effect = ifood.StaleElementReferenceException("renderizando")
    aba.driver.find_elements.side_effect = [[oculto, desabilitado], [antigo], [pronto]]
    monkeypatch.setattr(ifood, "_js", lambda *a: False)
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    assert ifood._elemento(aba, "button") is pronto
    assert aba.driver.find_elements.call_count == 3


def test_endereco_usa_teclado_e_cliques_nativos(monkeypatch, elementos):
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba")
    monkeypatch.setattr(ifood, "_fechar", lambda *a: None)
    monkeypatch.setattr(ifood, "_esperar", lambda *a: True)
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    monkeypatch.setattr(ifood, "_js", lambda aba, js: [item()] if js == ifood.JS_LISTA else True)
    lojas, bloqueio = ifood.coletar("Rua Fictícia, 10, Porto Alegre", 1, set(), ["Porto Alegre"], detalhar=False)
    assert len(lojas) == 1 and bloqueio is None
    campo = elementos['input[placeholder="Endereço de entrega e número"]']
    campo.click.assert_called_once()
    campo.send_keys.assert_called_once_with("Rua Fictícia, 10, Porto Alegre")
    elementos[".btn-address--full-size"].click.assert_called_once()
    for texto in ("Confirmar localização", "Salvar endereço"):
        elementos[f'//button[normalize-space(.)="{texto}"]'].click.assert_called_once()


def test_checkpoint_apos_lista_preserva_lojas_sem_detalhar(monkeypatch, elementos):
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba")
    monkeypatch.setattr(ifood, "_fechar", lambda *a: None)
    monkeypatch.setattr(ifood, "_esperar", lambda *a: True)
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    monkeypatch.setattr(ifood, "_js", lambda aba, js: [item()] if js == ifood.JS_LISTA else True)
    elementos["body"] = Mock()
    elementos["body"].send_keys.side_effect = ifood.DetalhesBloqueados("HUMAN pediu verificação")
    detalhes = Mock()
    monkeypatch.setattr(ifood, "ler_detalhes", detalhes)
    lojas, bloqueio = ifood.coletar("Rua Fictícia, 10, Porto Alegre", 2, set(), ["Porto Alegre"])
    assert len(lojas) == 1 and bloqueio == "HUMAN pediu verificação"
    detalhes.assert_not_called()


@pytest.mark.parametrize("erro", [ifood.DetalhesBloqueados, TimeoutError])
def test_bloqueio_persiste_e_outros_processos_so_descobrem_novas(tmp_path, monkeypatch, erro, elementos):
    caminho = tmp_path / "t.db"
    con = db.conectar(caminho)
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba")
    monkeypatch.setattr(ifood, "_esperar", lambda *a: True)
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    monkeypatch.setattr(ifood, "_fechar", lambda aba: None)
    monkeypatch.setattr(ifood, "_js", lambda aba, js: [item(n) for n in range(1,4)] if js == ifood.JS_LISTA else True)
    visitadas = []
    def bloquear(aba, l, municipios):
        visitadas.append(l.id)
        raise erro("detalhes indisponíveis")
    monkeypatch.setattr(ifood, "ler_detalhes", bloquear)
    assert ifood.rodar(con, "Rua Fictícia, 1, Porto Alegre", 1)["novos"] == 1
    assert ifood.detalhes_suspensos(con) == "detalhes indisponíveis"
    con.close()
    con = db.conectar(caminho)
    for n in (2,3):
        assert ifood.rodar(con, f"Rua Fictícia, {n}, Porto Alegre", 1)["novos"] == 1
    assert len(visitadas) == 1
    assert con.execute("SELECT count(*) FROM source_record WHERE source='ifood'").fetchone()[0] == 3


def test_lojas_novas_tem_prioridade_sobre_incompletas(monkeypatch, elementos):
    monkeypatch.setattr(ifood, "_abrir", lambda: "aba")
    monkeypatch.setattr(ifood, "_esperar", lambda *a: True)
    monkeypatch.setattr(ifood.time, "sleep", lambda *a: None)
    monkeypatch.setattr(ifood, "_fechar", lambda aba: None)
    monkeypatch.setattr(ifood, "_js", lambda aba, js: [item(n) for n in range(1,6)] if js == ifood.JS_LISTA else True)
    visitadas = []
    monkeypatch.setattr(ifood, "ler_detalhes", lambda aba, l, municipios: visitadas.append(l.id) or l)
    antigos = {str(loja(n).id) for n in (1,2,3)}
    lojas, bloqueio = ifood.coletar("Rua Fictícia, 1, Porto Alegre", 2, antigos, ["Porto Alegre"], revisitar=antigos)
    assert [l.id for l in lojas] == [loja(4).id, loja(5).id]
    assert visitadas == [loja(4).id, loja(5).id] and bloqueio is None


def test_metadado_de_leitura_nao_conta_como_dado_atualizado(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    ifood.ingerir(con, [loja()], [])
    resultado = ifood.ingerir(con, [loja().model_copy(update={"detalhes_em": db.agora()})], [])
    assert resultado["atualizados"] == 0 and resultado["repetidos"] == 1


def test_retomada_de_detalhes_exige_opcao_explicita(tmp_path, monkeypatch):
    caminho = tmp_path / "t.db"
    con = db.conectar(caminho)
    ifood.suspender_detalhes(con, "403 confirmado")
    monkeypatch.setenv("MFL_DB", str(caminho))
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(log, "configurar", lambda *a: None)
    opcoes = []
    def coletar(*args, **kwargs):
        opcoes.append(kwargs["detalhar"])
        return [], None
    monkeypatch.setattr(ifood, "coletar", coletar)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["ifood", "Rua Fictícia, 1, Porto Alegre"]).exit_code == 0
    assert ifood.detalhes_suspensos(con) == "403 confirmado"
    assert runner.invoke(cli.app, ["ifood", "Rua Fictícia, 1, Porto Alegre", "--retomar-detalhes"]).exit_code == 0
    assert ifood.detalhes_suspensos(con) is None and opcoes == [False, True]
