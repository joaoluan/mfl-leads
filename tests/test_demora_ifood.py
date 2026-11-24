import re
from datetime import date

from mfl import score

HOJE = date(2026, 11, 24)
PERTO: set[str] = set()
CLIENTES: set[str] = set()
FRANQUIAS = None


def lead(**campos):
    return {"categoria": None, "municipio": "Porto Alegre", "nome": "Casa X", "fantasia": None, **campos}


def maps(*reviews, **campos):
    return {"web_site": "", "order_online": [], "user_reviews": [{"Description": r} for r in reviews], **campos}


def sinais(*reviews, **campos):
    return score.sinais(lead(), {"maps": [maps(*reviews, **campos)]}, PERTO, HOJE, CLIENTES, FRANQUIAS)


def test_demora_do_ifood_nao_e_demora_da_casa():
    achados = sinais("Pedi pelo iFood e demorou 1h pra chegar")
    assert "reclamacao_demora" not in achados
    assert "vende_ifood" in achados


def test_demora_da_casa_continua_contando():
    assert "reclamacao_demora" in sinais("Demorou muito, quase 40 minutos")


def test_avaliacao_do_ifood_nao_apaga_a_da_casa():
    assert "reclamacao_demora" in sinais("Pedi pelo iFood e demorou", "A casa demora muito no salao")


def test_mencao_ao_ifood_marca_venda():
    assert "vende_ifood" in sinais("Sempre peco pelo iFood")


def test_encomenda_continua_lendo_avaliacao():
    assert "aceita_encomenda" in sinais("Fazem encomenda de bolo")
