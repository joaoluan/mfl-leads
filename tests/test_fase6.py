import json
import re
from datetime import date

from conftest import criar_lead
from mfl import cadencia, db, mensagens, score

HOJE = date(2026, 11, 24)
PERTO = {"NOVO HAMBURGO"}
CLIENTES = {"pizzaria"}
FRANQUIAS = re.compile(r"\b(subway)\b")


def lead(**campos):
    return {"categoria": None, "municipio": "Porto Alegre", "nome": "Casa X", "fantasia": None, **campos}


def maps(**campos):
    return {"web_site": "", "order_online": [], "user_reviews": [], **campos}


def sinais(l, fontes):
    return score.sinais(l, fontes, PERTO, HOJE, CLIENTES, FRANQUIAS)


def test_sinais_do_maps_e_cnpj():
    achados = sinais(lead(categoria="Pizzaria", municipio="Novo Hamburgo"), {
        "cnpj": [{"data_inicio_atividade": "20260301", "filiais": 1}],
        "maps": [maps(order_online=[{"link": "https://wa.me/5551999990000"}],
                      user_reviews=[{"Description": "Pizza boa mas demorou 1h pra chegar"}])],
    })
    assert achados == ["mesma_categoria_de_cliente", "raio", "aberto_menos_12m", "unidade_unica",
                       "sem_site", "wa_me_na_bio", "reclamacao_demora"]
    assert sinais(lead(), {"cnpj": [{"data_inicio_atividade": "20200101", "filiais": 3}]}) == []
    assert sinais(lead(nome="Subway Centro"), {}) == ["franquia"]


def test_site_proprio_concorrente_e_encomenda():
    proprio = maps(web_site="https://www.casax.com.br/", order_online=[{"link": "https://casax.com.br/pedido"}])
    assert sinais(lead(), {"maps": [proprio]}) == ["site_com_pedido_proprio"]
    rival = maps(web_site="https://app.cardapioweb.com/casax")
    assert sinais(lead(), {"maps": [rival]}) == ["usa_concorrente"]
    insta = maps(web_site="https://www.instagram.com/casax")
    assert sinais(lead(categoria="Confeitaria"), {"maps": [insta]}) == ["sem_site", "aceita_encomenda"]


def test_corte_na_fila_e_texto_de_troca(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    # A: pizzaria (categoria de cliente) perto da base, sem site = 60; B: site com pedido próprio = -30
    criar_lead(con, "A", "+5551999990001", categoria="Pizzaria", municipio="Novo Hamburgo", raw=maps(web_site=""))
    criar_lead(con, "B", "+5551999990002", raw=maps(web_site="https://www.casab.com.br",
                                                   order_online=[{"link": "https://www.casab.com.br/x"}]))
    assert score.recalcular(con, HOJE) == {"leads": 2, "acima_do_corte": 1}
    na_fila = [l for l, _ in cadencia.fila(con, HOJE, 10)]
    assert [l["tel1"] for l in na_fila] == ["+5551999990001"]
    assert json.loads(na_fila[0]["sinais"]) == ["mesma_categoria_de_cliente", "raio", "sem_site"]
    assert mensagens.arquivo_d0("Pizzaria", ["usa_concorrente"]) == "concorrente"
