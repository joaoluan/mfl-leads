"""Bairros (nome, cidade, bbox) para o Maps rodar um bairro por vez. Gerado uma vez do OpenStreetMap.

cfg/bairros.toml é versionado e editável; regenerar só se a lista de cidades mudar.
"""

import json
import math
import re
import tomllib
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from mfl.classifica import normalizar
from mfl.db import RAIZ

log = structlog.get_logger()
ARQUIVO = RAIZ / "cfg" / "bairros.toml"
OVERPASS = "https://overpass-api.de/api/interpreter"
CIDADES = ["Porto Alegre", "Canoas", "Gravataí", "Viamão", "São Leopoldo", "Novo Hamburgo", "Alvorada",
           "Cachoeirinha", "Sapucaia do Sul", "Esteio", "Guaíba", "Montenegro", "Campo Bom", "Estância Velha",
           "Ivoti", "Dois Irmãos", "Sapiranga", "Portão"]
MAX_CELULAS = 60  # cada célula roda todas as consultas: limita o tempo por bairro


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


def celula_km(bbox: tuple[float, float, float, float]) -> float:
    """0,5 km (spec) em bairro pequeno; maior em área grande (ilha, zona rural) para caber em MAX_CELULAS."""
    min_lat, min_lon, max_lat, max_lon = bbox
    altura = (max_lat - min_lat) * 111.0
    largura = (max_lon - min_lon) * 111.0 * math.cos(math.radians((min_lat + max_lat) / 2))
    return round(max(0.5, math.sqrt(altura * largura / MAX_CELULAS)), 1)


@retry(stop=stop_after_attempt(8), wait=wait_exponential(min=10, max=120), reraise=True)
def _overpass(consulta: str) -> list[dict]:
    pedido = Request(OVERPASS, data=urlencode({"data": consulta}).encode(), headers={"User-Agent": "mfl-leads/0.1"})
    with urlopen(pedido, timeout=120) as resposta:
        return json.load(resposta)["elements"]


def _caixa(b: dict) -> tuple[float, float, float, float]:
    return (round(b["minlat"], 5), round(b["minlon"], 5), round(b["maxlat"], 5), round(b["maxlon"], 5))


def gerar() -> int:
    """Consulta o OSM cidade a cidade (dentro do RS) e escreve cfg/bairros.toml. Devolve quantos bairros."""
    itens: list[tuple[str, str, tuple]] = []
    cache = RAIZ / "data" / "osm"
    cache.mkdir(parents=True, exist_ok=True)
    for cidade in CIDADES:
        arquivo = cache / f"{slug(cidade)}.json"
        if arquivo.exists():  # o Overpass público cai no meio: rodar de novo continua daqui
            itens += [(c, n, tuple(b)) for c, n, b in json.loads(arquivo.read_text())]
            continue
        antes = len(itens)
        base = (f'[out:json][timeout:90];area["name"="Rio Grande do Sul"]["admin_level"="4"]->.rs;'
                f'rel["name"="{cidade}"]["boundary"="administrative"]["admin_level"="8"](area.rs)->.c;')
        bairros = _overpass(base + '.c map_to_area->.a;rel(area.a)["boundary"="administrative"]["admin_level"="10"];out tags bb;')
        if bairros:
            itens += [(cidade, b["tags"]["name"], _caixa(b["bounds"])) for b in bairros if "name" in b.get("tags", {})]
        else:
            (mun,) = _overpass(base + ".c out tags bb;")
            itens.append((cidade, cidade, _caixa(mun["bounds"])))
        arquivo.write_text(json.dumps(itens[antes:], ensure_ascii=False))
        log.info("cidade", cidade=cidade, bairros=len(bairros) or 1)

    contagem: dict[str, int] = {}
    for _, nome, _ in itens:
        contagem[slug(nome)] = contagem.get(slug(nome), 0) + 1
    linhas = ["# Gerado por `mfl bairros-gerar` (OpenStreetMap). bbox = minLat,minLon,maxLat,maxLon.", ""]
    for cidade, nome, caixa in sorted(itens):
        chave = slug(nome) if contagem[slug(nome)] == 1 else f"{slug(cidade)}-{slug(nome)}"
        linhas += [f"[{chave}]", f"nome = {json.dumps(nome, ensure_ascii=False)}",
                   f"municipio = {json.dumps(cidade, ensure_ascii=False)}",
                   f'bbox = "{",".join(str(v) for v in caixa)}"', f"celula_km = {celula_km(caixa)}", ""]
    ARQUIVO.write_text("\n".join(linhas), encoding="utf-8")
    return len(itens)


def carregar() -> dict[str, dict]:
    with ARQUIVO.open("rb") as f:
        return tomllib.load(f)
