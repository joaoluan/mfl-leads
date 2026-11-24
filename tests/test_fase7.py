import json
from datetime import date

import pytest

from conftest import criar_lead
from mfl import db, ig, score

HOJE = date(2026, 11, 24)
RECENTE, ANTIGO = "DgImMOugWvN", "C0aaaaaaaaa"  # 24/11/2026 e 2023


def pagina(**campos):
    return {"url": "https://www.instagram.com/casa/", "logado": True, "indisponivel": False,
            "meta": '10.4K Followers, 181 Following, 781 Posts - Casa (@casa) on Instagram: "Tortas por encomenda\nPedidos 51 99999-0000"',
            "cabecalho": "casa\n781 posts", "grade": [f"/casa/p/{RECENTE}/", f"/casa/p/{ANTIGO}/"],
            "links": ["https://l.instagram.com/?u=https%3A%2F%2Fwa.me%2F5551999990001%3Ftext%3Doi&e=x"], **campos}


def test_handle_data_e_analise():
    assert ig.handle("https://www.instagram.com/Doce.Casa/?hl=pt") == "doce.casa"
    assert ig.handle("https://instagram.com/p/ABC123/") is None
    assert ig.data_do_post(RECENTE) == HOJE
    dados = ig.analisar(pagina())
    assert dados["telefone"] == "+5551999990001"  # wa.me vem antes do número solto na bio
    assert dados["whatsapp"] and dados["seguidores"] == 10400 and dados["posts"] == 781
    assert dados["ultimo_post"] == "2026-11-24" and dados["links"] == ["https://wa.me/5551999990001?text=oi"]
    assert ig.analisar(pagina(links=[]))["telefone"] == "+5551999990000"


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "PAUSA", (0, 0))
    monkeypatch.setattr(ig, "PAUSA_LONGA", (0, 0))
    c = db.conectar(tmp_path / "t.db")
    for i in range(1, 7):
        criar_lead(c, f"Casa {i}", f"+55513333000{i}")
    for i, (eid,) in enumerate(c.execute("SELECT entity_id FROM entity ORDER BY tel1").fetchall(), start=1):
        c.execute("UPDATE entity SET ig_username=?, status='enriquecimento' WHERE entity_id=?", (f"casa{i}", eid))
    c.commit()
    return c


def test_coleta_cinco_perfis_e_para_no_checkpoint(con):
    visitados = []

    def falso(nome):
        visitados.append(nome)
        if nome == "casa1":
            return pagina()
        if nome == "casa6":
            return pagina(url="https://www.instagram.com/accounts/login/?next=x", logado=False)
        return pagina(links=[], meta="", grade=[f"/{nome}/p/{ANTIGO}/"])

    contagem = ig.rodar(con, HOJE, 10, falso)
    assert contagem == {"perfis": 5, "telefones": 1, "indisponiveis": 0, "checkpoint": 1}
    assert len(visitados) == 6
    lead = con.execute("SELECT tel1, tel2, status FROM entity WHERE ig_username='casa1'").fetchone()
    assert tuple(lead) == ("+5551999990001", "+555133330001", "novo")  # celular do Instagram assume; fixo vai p/ tel2
    raw = json.loads(con.execute("SELECT raw_json FROM source_record WHERE source_key='casa1'").fetchone()[0])
    assert raw["bio"].startswith("Tortas") and raw["coletado_em"]
    assert ig.rodar(con, HOJE, 10, falso)["perfis"] == 0  # travado até --retomar
    assert len(visitados) == 6

    score.recalcular(con, HOJE)
    sinais = json.loads(con.execute("SELECT sinais FROM entity WHERE ig_username='casa1'").fetchone()[0])
    assert {"wa_me_na_bio", "ig_ativo_30d"} <= set(sinais)
    sinais = json.loads(con.execute("SELECT sinais FROM entity WHERE ig_username='casa2'").fetchone()[0])
    assert "ig_inativo_6m" in sinais


def test_teto_diario_e_handles(con):
    con.execute("DELETE FROM estado")
    assert ig.rodar(con, HOJE, 3, lambda n: pagina(links=[], meta=""))["perfis"] == 3
    assert len(ig.pendentes(con, HOJE, 50)) == 3  # já visitados saem até 60 dias
    con.execute("UPDATE entity SET ig_username=NULL, site='https://casa.com.br', fantasia='Casa Nova Pizzaria'"
                " WHERE ig_username IN ('casa4', 'casa5')")
    con.execute("UPDATE entity SET fantasia='Bar do Zé' WHERE fantasia='Casa Nova Pizzaria' AND tel1 LIKE '%5'")
    rodape = '<a href="https://instagram.com/casa_nova">' + '<a href="https://instagram.com/agencia_web">'
    assert ig.extrair_handles(con, lambda url: rodape) == 1  # o @ que não lembra o nome (agência) é ignorado
    assert con.execute("SELECT fantasia FROM entity WHERE ig_username='casa_nova'").fetchone()[0] == "Casa Nova Pizzaria"
    con.execute("UPDATE entity SET site='https://partiupedido.com/loja' WHERE fantasia='Bar do Zé'")
    assert ig.extrair_handles(con, lambda url: '<a href="https://instagram.com/barze">') == 0  # site de plataforma


def test_telefone_em_links():
    assert ig.telefone_em("https://wa.me/c/555199120.2014?utm=x") == "+5551991202014"
    links = ["https://linktr.ee/casa"]
    assert ig.telefone_nos_links(links, lambda u: '<a href="https://api.whatsapp.com/send?phone=5551999990003">') == "+5551999990003"
    assert ig.telefone_nos_links(links, lambda u: "") is None


def test_whatsapp_fixo_do_maps_e_apto(tmp_path):
    from mfl import maps
    con = db.conectar(tmp_path / "t.db")
    lugar = {"place_id": "PZ", "title": "Pub X", "phone": "(51) 3013-0000", "category": "Bar", "status": "",
             "address": "Pub X - R. A, 1 - Centro, Porto Alegre - RS",
             "complete_address": {"borough": "Centro", "city": "Porto Alegre", "postal_code": "90000-000"},
             "web_site": "https://wa.me/5130130000", "order_online": [], "emails": []}
    arquivo = tmp_path / "o.json"
    arquivo.write_text(json.dumps(lugar))
    bairro = {"nome": "Centro", "municipio": "Porto Alegre"}
    assert maps.ingerir(con, arquivo, bairro, ["PORTO ALEGRE"], [])["aptos"] == 1
    assert tuple(con.execute("SELECT tel1, status FROM entity").fetchone()) == ("+555130130000", "novo")
    assert con.execute("SELECT resultado FROM validacao").fetchone()[0] == "whatsapp"
