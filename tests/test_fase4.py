import zipfile

import pytest

from mfl import cnpj_etl, cnpj_icp, db

POA, PELOTAS = "8801", "8791"
CFG = {"municipios": ["PORTO ALEGRE"], "cnaes": ["5611201", "1091102"], "filiais_rede": 4}


def estab(basico, ordem="0001", fantasia="", situacao="02", uf="RS", municipio=POA, cnae="5611201",
          logradouro="RUA A", ddd="51", tel="33334444"):
    campos = {c: "" for c in cnpj_etl.LAYOUT["estab"]}
    campos.update(cnpj_basico=basico, cnpj_ordem=ordem, cnpj_dv="55", matriz_filial="1", nome_fantasia=fantasia,
                  situacao_cadastral=situacao, data_inicio_atividade="20260301", cnae_fiscal_principal=cnae,
                  tipo_logradouro="RUA", logradouro=logradouro, numero="10", bairro="CENTRO", cep="90000000",
                  uf=uf, municipio=municipio, ddd1=ddd, telefone1=tel)
    return [campos[c] for c in cnpj_etl.LAYOUT["estab"]]


def zipar(pasta, nome, linhas):
    texto = "\n".join(";".join(f'"{v}"' for v in l) for l in linhas) + "\n"
    caminho = pasta / f"{nome}.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(f"K3241.{nome.upper()}", texto.encode("latin-1"))
    return caminho


@pytest.fixture
def amostra(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    linhas = [
        estab("10000001", fantasia="CANTINA BOA"),                      # entra
        estab("10000002", fantasia="INATIVA", situacao="08"),           # fora no ETL
        estab("10000003", fantasia="DE SP", uf="SP"),                   # fora no ETL
        estab("10000004", fantasia="BUFE", cnae="5620102"),             # CNAE fora
        estab("10000005", fantasia="EM PELOTAS", municipio=PELOTAS),    # município fora
        estab("10000006", fantasia="SEM ENDERECO", logradouro=""),      # sem logradouro
        estab("10000007", fantasia="SUBWAY CENTRO"),                    # franquia por nome
        *[estab("10000008", ordem=f"000{i}", fantasia="REDE X") for i in range(1, 5)],  # 4 filiais
        estab("10000009", fantasia="PADARIA PÃO QUENTE", cnae="1091102", ddd="51", tel="985711759"),
    ]
    zips = [
        zipar(raw, "Estabelecimentos0", linhas),
        zipar(raw, "Empresas0", [["10000001", "FULANO 12345678901", "2135", "50", "1000,00", "01", ""],
                                 ["99999999", "OUTRA UF", "2062", "49", "0,00", "05", ""]]),
        zipar(raw, "Cnaes", [["5611201", "Restaurantes e similares"], ["1091102", "Padaria com produção própria"]]),
        zipar(raw, "Municipios", [[POA, "PORTO ALEGRE"], [PELOTAS, "PELOTAS"]]),
    ]
    destino = tmp_path / "parquet"
    contagem = cnpj_etl.converter(zips, destino, tmp_path / "tmp")
    return destino, contagem


def test_etl_filtra_rs_ativo_e_confere(amostra):
    destino, contagem = amostra
    assert contagem == {"estab": 10, "empresas": 1, "cnae": 2, "municipios": 2}
    assert not (destino.parent / "parquet.novo").exists()
    assert list((destino / "estab" / "uf=RS").glob("*.parquet"))


def test_etl_aborta_se_layout_mudar(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    ruim = zipar(raw, "Estabelecimentos0", [estab("1")[:-1]])
    with pytest.raises(cnpj_etl.LayoutMudou, match="29 colunas, esperado 30"):
        cnpj_etl.converter([ruim], tmp_path / "parquet", tmp_path / "tmp")
    assert not (tmp_path / "parquet").exists()


def test_recorte_icp(amostra):
    destino, _ = amostra
    linhas = cnpj_icp.consultar(destino, CFG, ["subway", "mc donalds"])
    assert [l["fantasia"] for l in linhas] == ["CANTINA BOA", "SUBWAY CENTRO", "PADARIA PÃO QUENTE"]  # franquia entra
    assert linhas[0]["porte"] == "01" and linhas[0]["cnae_descricao"] == "Restaurantes e similares"
    assert "razao_social" not in linhas[0]


def test_ingestao_idempotente_e_enriquecimento(amostra, tmp_path):
    destino, _ = amostra
    con = db.conectar(tmp_path / "t.db")
    linhas = cnpj_icp.consultar(destino, CFG, ["subway"])
    assert cnpj_icp.ingerir(con, linhas, "teste")["novos"] == 3
    assert cnpj_icp.ingerir(con, linhas, "teste") == {"novos": 0, "repetidos": 3}
    rows = [tuple(r) for r in con.execute("SELECT status, tel1, tel2, municipio FROM entity WHERE fantasia <> 'SUBWAY CENTRO'"
                                          " ORDER BY cnpj")]
    assert rows == [("enriquecimento", None, "+555133334444", "PORTO ALEGRE"),
                    ("enriquecimento", None, "+5551985711759", "PORTO ALEGRE")]


def test_recorte_real_esta_bem_formado():
    cfg = cnpj_icp.recorte()
    assert len(cfg["municipios"]) == 18 and "1091102" in cfg["cnaes"] and "5620102" not in cfg["cnaes"]
    assert "subway" in cnpj_icp.termos_franquia()
