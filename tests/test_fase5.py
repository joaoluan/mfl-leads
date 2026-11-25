import hashlib
import json
from datetime import date

import pytest

from conftest import criar_lead
from mfl import db, maps, resolve, score, ui
from mfl.cnpj_icp import ingerir as ingerir_cnpj

BAIRRO = {"nome": "Moinhos de Vento", "municipio": "Porto Alegre", "bbox": "-30.03,-51.21,-30.02,-51.19", "celula_km": 0.5}
MUNICIPIOS = ["PORTO ALEGRE", "CANOAS"]


def lugar(pid, titulo, fone="", cep="90570-050", cidade="Porto Alegre", status="", categoria="Pizzaria"):
    return {"place_id": pid, "title": titulo, "phone": fone, "category": categoria, "status": status,
            "address": f"{titulo} - R. Dinarte Ribeiro, 17 - Moinhos de Vento, {cidade} - RS",
            "complete_address": {"borough": "Moinhos de Vento", "city": cidade, "postal_code": cep},
            "web_site": "", "review_rating": 4.7, "review_count": 120, "link": f"https://maps/{pid}", "emails": []}


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "t.db")
    criar_lead(c, None, "+5551988887777")  # já conhecido pelo telefone (ex.: Instagram)
    ingerir_cnpj(c, [
        {"cnpj": "11111111000155", "fantasia": "CANTINA DO ZE", "cnae": "5611201", "cnae_descricao": "Restaurantes e similares",
         "municipio": "PORTO ALEGRE", "bairro": "MOINHOS", "cep": "90570050", "endereco": "RUA X 1",
         "fone1": "5133334444", "fone2": None},
        {"cnpj": "22222222000155", "fantasia": "PIZZARIA BELLA NAPOLI", "cnae": "5611201", "cnae_descricao": "Restaurantes",
         "municipio": "PORTO ALEGRE", "bairro": "MOINHOS", "cep": "90570999", "endereco": "RUA Y 2",
         "fone1": None, "fone2": None},
    ], "teste")
    return c


def arquivo(tmp_path, lugares):
    caminho = tmp_path / "out.json"
    caminho.write_text("\n".join(json.dumps(l) for l in lugares))
    return caminho


def status_de(con, **filtro):
    (campo, valor), = filtro.items()
    return con.execute(f"SELECT status, motivo_descarte FROM entity WHERE {campo}=?", (valor,)).fetchone()


def test_ingestao_resolve_e_descarta(con, tmp_path):
    lugares = [
        lugar("P1", "Pizzaria Nova", fone="(51) 99111-2222"),                   # celular → novo
        lugar("P2", "Lancheria Fixa", fone="(51) 3222-1111", cep="90000-000"),  # fixo → enriquecimento
        lugar("P3", "Fechou", status="Fechado permanentemente"),
        lugar("P4", "Longe", cidade="Pelotas"),
        lugar("P5", "Subway Moinhos"),
        lugar("P6", "Casa do Dono", fone="51 98888-7777"),                     # mesmo telefone → vincula
        lugar("P7", "Cantina do Zé", fone="51 99333-4444", cep="90570-050"),    # CEP8 + nome → vincula ao CNPJ
        lugar("P8", "Bella Napoli Pizzas", cep="90570-123"),                    # CEP5 + nome parecido → revisão
    ]
    contagem = maps.ingerir(con, arquivo(tmp_path, lugares), BAIRRO, MUNICIPIOS, ["subway"])
    assert contagem == {"novos": 4, "vinculados": 2, "revisao": 1, "repetidos": 0, "descartados": 2, "aptos": 3}
    assert tuple(status_de(con, place_id="P1")) == ("novo", None)
    assert con.execute("SELECT tel1 FROM entity WHERE place_id='P1'").fetchone()[0] == "+5551991112222"
    assert tuple(status_de(con, place_id="P2")) == ("enriquecimento", None)
    assert [status_de(con, place_id=p)[1] for p in ("P3", "P4", "P5")] == ["fechado", "fora_da_regiao", None]  # franquia entra (só perde pontos no score)
    dono = con.execute("SELECT nome, place_id, status, tel1 FROM entity WHERE tel1='+5551988887777'").fetchone()
    assert tuple(dono) == ("Casa do Dono", "P6", "novo", "+5551988887777")
    cantina = con.execute("SELECT place_id, status, tel1, categoria FROM entity WHERE cnpj='11111111000155'").fetchone()
    assert tuple(cantina) == ("P7", "novo", "+5551993334444", "Pizzaria")
    assert con.execute("SELECT count(*) FROM revisao WHERE decidido=0").fetchone()[0] == 1
    assert dict(con.execute("SELECT telefone, resultado FROM validacao").fetchall()) == {
        "+5551991112222": "celular", "+555132221111": "fixo", "+5551988887777": "celular", "+5551993334444": "celular"}

    total = con.execute("SELECT count(*) FROM entity").fetchone()[0]
    assert maps.ingerir(con, arquivo(tmp_path, lugares), BAIRRO, MUNICIPIOS, ["subway"])["repetidos"] == 8
    assert con.execute("SELECT count(*) FROM entity").fetchone()[0] == total
    assert con.execute("SELECT count(*) FROM source_record WHERE source='maps' AND source_key LIKE 'P%'").fetchone()[0] == 8


def test_fila_so_com_celular_validado(con, tmp_path):
    maps.ingerir(con, arquivo(tmp_path, [lugar("P1", "A", fone="51 99111-2222"), lugar("P2", "B", fone="51 3222-1111")]),
                 BAIRRO, MUNICIPIOS, [])
    score.recalcular(con, date(2026, 11, 24))  # P1: pizzaria (categoria de cliente) 30 + sem site 10
    from mfl import cadencia
    na_fila = {l["tel1"] for l, _ in cadencia.fila(con, date(2026, 11, 24), 50)}
    assert na_fila == {"+5551991112222"}  # P2 é fixo; o lead sem sinais fica abaixo do corte
    assert all(t.startswith("+55") for t in na_fila)


def test_tela_de_revisao_funde(con, tmp_path):
    maps.ingerir(con, arquivo(tmp_path, [lugar("P8", "Bella Napoli Pizzas", cep="90570-123")]), BAIRRO, MUNICIPIOS, [])
    caminho = tmp_path / "t.db"
    cliente = ui.criar_app(caminho).test_client()
    tela = cliente.get("/revisao").get_data(as_text=True)
    assert "Bella Napoli Pizzas" in tela and "veio de" in tela and "Google Maps" in tela and "Porto Alegre" in tela
    (rid,) = con.execute("SELECT id FROM revisao").fetchone()
    cliente.post(f"/revisao/{rid}", data={"decisao": "mesmo"})
    assert tuple(con.execute("SELECT place_id, categoria FROM entity WHERE cnpj='22222222000155'").fetchone()) == (
        "P8", "Pizzaria")
    assert con.execute("SELECT count(*) FROM entity WHERE place_id='P8'").fetchone()[0] == 1


def test_wrapper_confere_sha_e_encerra_processo_pendurado(tmp_path, monkeypatch):
    falso = tmp_path / "scraper"
    falso.write_text("#!/bin/sh\nwhile [ $# -gt 0 ]; do [ \"$1\" = -results ] && out=$2; shift; done\n"
                     "echo '{\"place_id\":\"X\"}' > \"$out\"\necho 'scrapemate exited'\nsleep 600\n")
    falso.chmod(0o755)
    sha = tmp_path / "SHA256SUMS"
    monkeypatch.setattr(maps, "BINARIO", falso)
    monkeypatch.setattr(maps, "SHA", sha)
    monkeypatch.setattr(maps, "ESPERA_SAIDA", 0.5)
    monkeypatch.setattr(maps, "INTERVALO", 0.2)
    sha.write_text("0" * 64 + "  scraper\n")
    with pytest.raises(RuntimeError, match="SHA256"):
        maps.rodar(BAIRRO, tmp_path / "o.json", tmp_path / "l.log")
    sha.write_text(hashlib.sha256(falso.read_bytes()).hexdigest() + "  scraper\n")
    saida = maps.rodar(BAIRRO, tmp_path / "nova" / "o.json", tmp_path / "l.log")
    assert json.loads(saida.read_text())["place_id"] == "X"


def test_pontuar_porta_e_bairro():
    cnpj = {"tel1": None, "tel2": None, "cep": "90560004", "fantasia": "COZINHA & ARTE", "nome": "COZINHA & ARTE",
            "endereco": "AVENIDA CRISTOVAO COLOMBO 1144"}
    maps_ = {"cep": "90560001", "fantasia": "Cozinha & Arte", "bairro": "Moinhos de Vento", "municipio": "Porto Alegre",
             "endereco": "Av. Cristóvão Colombo, 1144 - Floresta, Porto Alegre - RS"}
    assert resolve.pontuar(maps_, cnpj, set()) >= resolve.VINCULA  # CEP5 + porta + nome
    assert resolve.pontuar({**maps_, "endereco": "Av. Cristóvão Colombo, 17 - X"}, cnpj, set()) < resolve.VINCULA
    outro = {**cnpj, "fantasia": "The Chefs Hamburgueria - Moinhos", "nome": "x"}
    assert resolve.pontuar({**maps_, "fantasia": "Moinhos Pizzaria"}, outro, set()) < resolve.REVISA  # "Moinhos" não conta
