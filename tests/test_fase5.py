import hashlib
import json

import pytest

from mfl import db, maps, resolve, seed, ui
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
    seed.importar_linhas(c, [{"nome": "Grupo GESTORES", "telefone": "+5551988887777"}], "teste")
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
        lugar("P6", "Casa do Dono", fone="51 98888-7777"),                     # telefone do grupo → vincula
        lugar("P7", "Cantina do Zé", fone="51 99333-4444", cep="90570-050"),    # CEP8 + nome → vincula ao CNPJ
        lugar("P8", "Bella Napoli Pizzas", cep="90570-123"),                    # CEP5 + nome parecido → revisão
    ]
    contagem = maps.ingerir(con, arquivo(tmp_path, lugares), BAIRRO, MUNICIPIOS, ["subway"])
    assert contagem == {"novos": 3, "vinculados": 2, "revisao": 1, "repetidos": 0, "descartados": 3, "aptos": 3}
    assert tuple(status_de(con, place_id="P1")) == ("novo", None)
    assert con.execute("SELECT tel1 FROM entity WHERE place_id='P1'").fetchone()[0] == "+5551991112222"
    assert tuple(status_de(con, place_id="P2")) == ("enriquecimento", None)
    assert [status_de(con, place_id=p)[1] for p in ("P3", "P4", "P5")] == ["fechado", "fora_da_regiao", "franquia"]
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
    assert con.execute("SELECT count(*) FROM source_record WHERE source='maps'").fetchone()[0] == 8


def test_fila_so_com_celular_validado(con, tmp_path):
    maps.ingerir(con, arquivo(tmp_path, [lugar("P1", "A", fone="51 99111-2222"), lugar("P2", "B", fone="51 3222-1111")]),
                 BAIRRO, MUNICIPIOS, [])
    from datetime import date
    from mfl import cadencia
    na_fila = {l["tel1"] for l, _ in cadencia.fila(con, date(2026, 11, 24), 50)}
    assert na_fila == {"+5551988887777", "+5551991112222"}
    assert all(t.startswith("+55") for t in na_fila)


def test_grupo_cnpj_por_telefone_unico(con):
    ingerir_cnpj(con, [{"cnpj": f"3333333{i}000155", "fantasia": f"CONTADOR {i}", "cnae": "5611201", "cnae_descricao": "x",
                        "municipio": "PORTO ALEGRE", "bairro": "B", "cep": "90000000", "endereco": "R", "fone1": "5130001000",
                        "fone2": None} for i in range(2)], "teste")
    seed.importar_linhas(con, [{"nome": "Grupo X", "telefone": "+555130001000"}], "teste")  # telefone de contador
    con.execute("UPDATE entity SET tel2='+5551988887777' WHERE cnpj='22222222000155'")
    dono = con.execute("SELECT entity_id FROM entity WHERE tel1='+5551988887777'").fetchone()[0]
    con.execute("INSERT INTO touch (entity_id, canal, texto, enviado_em) VALUES (?, 'whatsapp', 'oi', '2026-11-24')", (dono,))
    assert resolve.resolver_grupo_cnpj(con) == 1
    fundido = con.execute("SELECT cnpj, nome, fantasia FROM entity WHERE entity_id=?", (dono,)).fetchone()
    assert tuple(fundido) == ("22222222000155", "PIZZARIA BELLA NAPOLI", "PIZZARIA BELLA NAPOLI")
    assert con.execute("SELECT count(*) FROM touch WHERE entity_id=?", (dono,)).fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM entity WHERE cnpj LIKE '3333333%'").fetchone()[0] == 2


def test_tela_de_revisao_funde(con, tmp_path):
    maps.ingerir(con, arquivo(tmp_path, [lugar("P8", "Bella Napoli Pizzas", cep="90570-123")]), BAIRRO, MUNICIPIOS, [])
    caminho = tmp_path / "t.db"
    cliente = ui.criar_app(caminho).test_client()
    assert "Bella Napoli Pizzas" in cliente.get("/revisao").get_data(as_text=True)
    (rid,) = con.execute("SELECT id FROM revisao").fetchone()
    cliente.post(f"/revisao/{rid}", data={"decisao": "mesmo"})
    assert con.execute("SELECT place_id FROM entity WHERE cnpj='22222222000155'").fetchone()[0] == "P8"
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
    saida = maps.rodar(BAIRRO, tmp_path / "o.json", tmp_path / "l.log")
    assert json.loads(saida.read_text())["place_id"] == "X"
