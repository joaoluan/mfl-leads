from datetime import date

from mfl import mensagens, score

HOJE = date(2026, 11, 24)


def sinais(fontes):
    lead = {"categoria": None, "municipio": "Porto Alegre", "nome": "Casa X", "fantasia": None}
    return score.sinais(lead, fontes, set(), HOJE, set(), None)


def maps(**campos):
    return {"web_site": "https://casax.com.br", "order_online": [], "user_reviews": [], **campos}


def test_vende_ifood_por_link_avaliacao_ou_bio():
    assert "vende_ifood" in sinais({"maps": [maps(order_online=[{"link": "https://www.ifood.com.br/delivery/x"}])]})
    assert "vende_ifood" in sinais({"maps": [maps(user_reviews=[{"Description": "Pedi pelo iFood e chegou quente"}])]})
    assert "vende_ifood" in sinais({"instagram": [{"bio": "Peça no iFood!", "links": [], "ultimo_post": None}]})
    assert sinais({"maps": [maps()], "instagram": [{"bio": "Bistrô", "links": []}]}).count("vende_ifood") == 0
    assert sinais({"maps": [maps(user_reviews=[{"Description": "ifood"}])],
                   "instagram": [{"bio": "ifood", "links": []}]}).count("vende_ifood") == 1


def test_texto_do_ifood():
    assert mensagens.arquivo_d0("Pizzaria", {"maps"}, ["vende_ifood"]) == "ifood"
    assert mensagens.arquivo_d0("Pizzaria", {"maps"}, ["usa_concorrente", "vende_ifood"]) == "concorrente"
    assert mensagens.arquivo_d0("Pizzaria", {"grupo"}, ["vende_ifood"]) == "grupo"
