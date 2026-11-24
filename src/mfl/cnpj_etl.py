"""Zips do CNPJ → Parquet só com RS ativo (camada analítica, lida pelo DuckDB).

Layout: https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf (CSV ; com aspas, latin-1, sem cabeçalho).
Razão social fica de fora: em MEI ela traz nome e CPF da pessoa (LGPD).
"""

import csv
import io
import shutil
import zipfile
from pathlib import Path

import duckdb
import structlog

log = structlog.get_logger()

LAYOUT = {
    "estab": ["cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial", "nome_fantasia", "situacao_cadastral",
              "data_situacao", "motivo", "cidade_exterior", "pais", "data_inicio_atividade", "cnae_fiscal_principal",
              "cnae_secundaria", "tipo_logradouro", "logradouro", "numero", "complemento", "bairro", "cep", "uf",
              "municipio", "ddd1", "telefone1", "ddd2", "telefone2", "ddd_fax", "fax", "correio_eletronico",
              "situacao_especial", "data_situacao_especial"],
    "empresas": ["cnpj_basico", "razao_social", "natureza_juridica", "qualificacao_responsavel", "capital_social",
                 "porte", "ente_federativo"],
    "cnae": ["codigo", "descricao"],
    "municipios": ["codigo", "descricao"],
}
PREFIXO = {"Estabelecimentos": "estab", "Empresas": "empresas", "Cnaes": "cnae", "Municipios": "municipios"}


class LayoutMudou(RuntimeError):
    """A Receita mudou o arquivo: melhor parar do que gravar coluna trocada."""


def _ler_csv(caminho: Path, tabela: str) -> str:
    colunas = ", ".join(f"'{c}': 'VARCHAR'" for c in LAYOUT[tabela])
    return (f"read_csv('{caminho}', delim=';', quote='\"', escape='\"', header=false, encoding='utf-8',"
            f" all_varchar=true, columns={{{colunas}}})")


def validar_layout(caminho: Path, tabela: str) -> None:
    with caminho.open(encoding="utf-8", newline="") as f:
        primeira = next(csv.reader(f, delimiter=";", quotechar='"'), None)
    esperado = len(LAYOUT[tabela])
    if primeira is None or len(primeira) != esperado:
        achado = 0 if primeira is None else len(primeira)
        raise LayoutMudou(f"{caminho.name}: {achado} colunas, esperado {esperado} ({tabela}). Confira o layout da Receita.")


def _extrair(zip_: Path, tmp: Path) -> Path:
    """Extrai já em UTF-8: o latin-1 do DuckDB recusa bytes de controle que a Receita deixa nos arquivos,
    e o decodificador do Python aceita qualquer byte."""
    with zipfile.ZipFile(zip_) as z:
        (membro,) = z.namelist()  # cada zip da Receita tem um CSV
        destino = tmp / f"{zip_.stem}.csv"
        with z.open(membro) as origem, destino.open("w", encoding="utf-8", newline="") as saida:
            shutil.copyfileobj(io.TextIOWrapper(origem, encoding="latin-1", newline=""), saida, 1 << 20)
        return destino


def _copiar(con: duckdb.DuckDBPyConnection, select: str, saida: Path) -> int:
    """COPY e confere: linhas escritas no Parquet = linhas selecionadas."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    escritas = con.execute(f"COPY ({select}) TO '{saida}' (FORMAT parquet)").fetchone()[0]
    lidas = con.execute(f"SELECT count(*) FROM read_parquet('{saida}')").fetchone()[0]
    if escritas != lidas:
        raise RuntimeError(f"{saida.name}: {escritas} escritas, {lidas} no Parquet")
    return escritas


def converter(zips: list[Path], destino: Path, tmp: Path) -> dict[str, int]:
    """Gera destino/{estab,empresas}/uf=RS/*.parquet, cnae.parquet e municipios.parquet.

    Escreve numa pasta nova e só troca no fim: um mês com erro não deixa o Parquet pela metade.
    """
    novo = destino.with_name(destino.name + ".novo")
    shutil.rmtree(novo, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    por_tabela = {t: sorted(z for z in zips if PREFIXO.get(z.stem.rstrip("0123456789")) == t) for t in LAYOUT}
    if not por_tabela["estab"]:
        raise RuntimeError("nenhum Estabelecimentos*.zip")
    contagem: dict[str, int] = {}

    def cada(tabela: str, select_de) -> None:
        for zip_ in por_tabela[tabela]:
            csv_ = _extrair(zip_, tmp)
            try:
                validar_layout(csv_, tabela)
                total = con.execute(f"SELECT count(*) FROM {_ler_csv(csv_, tabela)}").fetchone()[0]
                saida = novo / (f"{tabela}/uf=RS/{zip_.stem}.parquet" if tabela in ("estab", "empresas") else f"{tabela}.parquet")
                n = _copiar(con, select_de(_ler_csv(csv_, tabela)), saida)
                contagem[tabela] = contagem.get(tabela, 0) + n
                log.info("convertido", arquivo=zip_.name, lidas=total, gravadas=n)
            finally:
                csv_.unlink(missing_ok=True)

    cada("estab", lambda fonte: f"SELECT * FROM {fonte} WHERE situacao_cadastral = '02' AND uf = 'RS'")
    basicos = f"SELECT DISTINCT cnpj_basico FROM read_parquet('{novo}/estab/uf=RS/*.parquet')"
    cada("empresas", lambda fonte: f"SELECT cnpj_basico, natureza_juridica, capital_social, porte FROM {fonte}"
                                   f" WHERE cnpj_basico IN ({basicos})")
    cada("cnae", lambda fonte: f"SELECT * FROM {fonte}")
    cada("municipios", lambda fonte: f"SELECT * FROM {fonte}")

    velho = destino.with_name(destino.name + ".velho")
    shutil.rmtree(velho, ignore_errors=True)
    if destino.exists():
        destino.rename(velho)
    novo.rename(destino)
    shutil.rmtree(velho, ignore_errors=True)
    log.info("etl_concluido", **contagem)
    return contagem
