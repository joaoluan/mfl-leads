import json
from unittest.mock import MagicMock, Mock

import pytest
from typer.testing import CliRunner

from mfl import cli, controle, db, ifood, log, ops, ui


def test_verificacao_manual_so_observa_e_preserva_janela(monkeypatch):
    aba = Mock()
    callback = Mock()
    aba._mfl_ao_verificar = callback
    respostas = iter([True, True, False])
    relogio = [0]
    monkeypatch.setattr(ifood, "_js", lambda *a: next(respostas))
    monkeypatch.setattr(ifood.time, "monotonic", lambda: relogio[0])
    monkeypatch.setattr(ifood.time, "sleep", lambda s: relogio.__setitem__(0, relogio[0] + s))
    assert ifood._verificar(aba) == 1
    assert [c.args for c in callback.call_args_list] == [(True,), (False,)]
    assert all(c[0] == "_mfl_ao_verificar" for c in aba.method_calls)


@pytest.mark.parametrize("fechou", [False, True])
def test_espera_limpa_aviso_em_timeout_ou_janela_fechada(monkeypatch, fechou):
    aba = Mock()
    callback = Mock()
    aba._mfl_ao_verificar = callback
    relogio = [0]
    monkeypatch.setattr(ifood.time, "monotonic", lambda: relogio[0])
    monkeypatch.setattr(ifood.time, "sleep", lambda s: relogio.__setitem__(0, 600))
    if fechou:
        respostas = iter([True, ifood.WebDriverException("janela fechada")])
        def js(*a):
            resposta = next(respostas)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta
        monkeypatch.setattr(ifood, "_js", js)
    else:
        monkeypatch.setattr(ifood, "_js", lambda *a: True)
    with pytest.raises(ifood.WebDriverException if fechou else ifood.DetalhesBloqueados):
        ifood._verificar(aba)
    assert [c.args for c in callback.call_args_list] == [(True,), (False,)]


def test_verificacao_nao_consume_tempo_da_etapa(monkeypatch):
    aba = Mock()
    aba._mfl_ao_verificar = Mock()
    relogio = [0]
    monkeypatch.setattr(ifood.time, "monotonic", lambda: relogio[0])
    monkeypatch.setattr(ifood.time, "sleep", lambda s: relogio.__setitem__(0, 60 if relogio[0] < 60 else relogio[0] + s))
    monkeypatch.setattr(ifood, "_js", lambda *a: relogio[0] < 60)
    assert ifood._esperar(aba, lambda: "pronto" if relogio[0] >= 61 else False) == "pronto"


@pytest.mark.parametrize("falha", [False, True])
def test_abertura_manual_visivel_e_fechamento_se_inicializacao_falhar(monkeypatch, falha):
    contexto = MagicMock()
    aba = contexto.__enter__.return_value
    fabrica = Mock(return_value=contexto)
    callback = Mock()
    monkeypatch.setattr(ifood, "SB", fabrica)
    monkeypatch.setattr(ifood, "HEADLESS", True)
    def ir(a, url):
        assert a is aba and a._mfl_ao_verificar is callback
        if falha:
            raise ifood.DetalhesBloqueados("não resolveu")
    monkeypatch.setattr(ifood, "_ir", ir)
    if falha:
        with pytest.raises(ifood.DetalhesBloqueados):
            ifood._abrir(callback)
        contexto.__exit__.assert_called_once()
    else:
        assert ifood._abrir(callback) is aba
        contexto.__exit__.assert_not_called()
        ifood._fechar(aba)
        contexto.__exit__.assert_called_once()
    assert fabrica.call_args.kwargs["headless"] is False and fabrica.call_count == 1


def test_navegacao_manual_nao_tenta_resolver_desafio(monkeypatch):
    aba = Mock()
    aba._mfl_ao_verificar = Mock()
    monkeypatch.setattr(ifood, "_verificar", lambda a: 12)
    assert ifood._ir(aba, "https://exemplo.test/") == 12
    aba.uc_gui_click_captcha.assert_not_called()


@pytest.mark.parametrize("na_navegacao", [False, True])
def test_dados_retomam_apos_verificacao_sem_reusar_403_antigo(monkeypatch, na_navegacao):
    aba = Mock()
    def evento(status):
        return {"message": json.dumps({"message": {"method": "Network.responseReceived", "params": {
            "requestId": "teste", "response": {"url": "https://exemplo.test/merchant-info/graphql", "status": status},
        }}})}
    aba.driver.get_log.side_effect = [[], [evento(403)], [], [evento(200)]]
    aba.driver.execute_cdp_cmd.return_value = {"body": '{"data":{"merchantExtra":{}}}'}
    relogio = [0]
    def verificar(a):
        if relogio[0] == 0:
            relogio[0] = 60
            return 60
        return 0
    monkeypatch.setattr(ifood, "_ir", lambda *a: verificar(aba) if na_navegacao else 0)
    monkeypatch.setattr(ifood, "_verificar", verificar)
    monkeypatch.setattr(ifood.time, "monotonic", lambda: relogio[0])
    assert ifood._ler_resposta_info(aba, "https://exemplo.test/") == {"data": {"merchantExtra": {}}}
    aba.refresh.assert_called_once()


@pytest.mark.parametrize("falha", [False, True])
def test_aviso_manual_aparece_so_enquanto_job_espera(tmp_path, monkeypatch, falha):
    caminho = tmp_path / "teste.db"
    con = db.conectar(caminho)
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(controle, "_proximas", lambda: {})
    cliente = ui.criar_app(caminho).test_client()
    def coletar(*a, ao_verificar, **kw):
        ao_verificar(True)
        pagina = cliente.get("/coleta?log=ifood").get_data(as_text=True)
        assert "Aguardando sua verificação:" in pagina and "http-equiv=\"refresh\"" in pagina
        if falha:
            raise RuntimeError("janela fechada")
        ao_verificar(False)
        return [], None
    monkeypatch.setattr(ifood, "coletar", coletar)
    if falha:
        with pytest.raises(RuntimeError), ops.job(con, "ifood"):
            ifood.rodar(con, "Rua Fictícia, 10, Porto Alegre", aguardar_verificacao=True)
    else:
        with ops.job(con, "ifood"):
            ifood.rodar(con, "Rua Fictícia, 10, Porto Alegre", aguardar_verificacao=True)
    assert con.execute("SELECT 1 FROM estado WHERE chave='ifood_verificacao'").fetchone() is None
    assert "Aguardando sua verificação:" not in cliente.get("/coleta").get_data(as_text=True)


def test_formulario_e_cli_habilitam_verificacao_com_retomada(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.db"
    monkeypatch.setenv("MFL_DB", str(caminho))
    monkeypatch.setattr(ops, "RAIZ", tmp_path)
    monkeypatch.setattr(log, "configurar", lambda *a: None)
    monkeypatch.setattr(controle, "_proximas", lambda: {})
    chamadas = []
    monkeypatch.setattr(controle, "disparar", lambda *a: chamadas.append(a))
    cliente = ui.criar_app(caminho).test_client()
    pagina = cliente.get("/coleta").get_data(as_text=True)
    assert 'name="verificacao_manual" value="1" checked' in pagina
    cliente.post("/coleta/rodar", data={"acao": "ifood", "endereco": "Rua Fictícia, 10, Porto Alegre", "verificacao_manual": "1"})
    assert chamadas[0][-2:] == ("--aguardar-verificacao", "--retomar-detalhes")
    con = db.conectar(caminho)
    ifood.suspender_detalhes(con, "bloqueio sintético")
    def coletar(*a, ao_verificar, **kw):
        assert callable(ao_verificar) and kw["detalhar"]
        return [], None
    monkeypatch.setattr(ifood, "coletar", coletar)
    resultado = CliRunner().invoke(cli.app, list(chamadas[0][1:]))
    assert resultado.exit_code == 0, resultado.exception
    assert ifood.detalhes_suspensos(con) is None
