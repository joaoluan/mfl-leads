"""Score do lead: soma dos pesos de cfg/icp.toml para cada sinal presente. Abaixo do corte não entra na fila.

Sinais de Instagram (wa_me_na_bio na bio, ig_ativo_30d, ig_inativo_6m) e iFood (vende_ifood) chegam nas fases 7 e 8;
os do Maps e do CNPJ já são calculados aqui. Os sinais ficam em entity.sinais (a fila mostra como etiquetas).
"""

import json
import re
import sqlite3
import tomllib
from collections import defaultdict
from itertools import groupby
from datetime import date, timedelta

import structlog

from mfl import cnpj_icp
from mfl.classifica import normalizar
from mfl.db import LOTE, agora
from mfl.mensagens import arquivo_d0

log = structlog.get_logger()
CONCORRENTE = re.compile(r"leadsfood|cardapioweb|cardapio\.?web|anota\.?ai|goomer|saipos|menudino|consumer\.com|"
                         r"deliverydireto|instadelivery|neemo|aiqfome|pedefacil|ola\.click|delivery\.?much|partiupedido")
SOCIAL = re.compile(r"instagram\.com|facebook\.com|linktr\.ee|wa\.me|whatsapp\.com|wa\.link|contate\.me|bio\.site")
WHATSAPP = re.compile(r"wa\.me|whatsapp\.com|wa\.link|contate\.me")
DEMORA = re.compile(r"\b(demor\w*|atras\w*|esper(ei|amos|ando) (muito|mais|quase|\d)|lent[oa]|nunca chegou|chegou fri[oa])\b")
IFOOD = re.compile(r"\bifood\b")
ENCOMENDA = re.compile(r"\b(confeitaria|doceria|bolos?|tortas?|salgados?|docinhos?|panificadora)\b")  # categoria/nome


def config() -> dict:
    with cnpj_icp.ICP.open("rb") as f:
        return tomllib.load(f)


def _dominio(url: str | None) -> str:
    achado = re.match(r"(?:https?://)?(?:www\.)?([^/?#]+)", url or "")
    return achado.group(1).lower() if achado else ""


def sinais(lead: sqlite3.Row | dict, fontes: dict[str, list[dict]], perto: set[str], hoje: date,
           categorias_clientes: set[str], franquias: re.Pattern | None) -> list[str]:
    s = []
    maps = fontes.get("maps", [])
    cnpj = fontes.get("cnpj", [])
    if arquivo_d0(lead["categoria"]) in categorias_clientes:
        s.append("mesma_categoria_de_cliente")
    if normalizar(lead["municipio"] or "").upper() in perto:
        s.append("raio")
    if cnpj:
        inicio = cnpj[0].get("data_inicio_atividade") or ""
        if len(inicio) == 8 and inicio >= (hoje - timedelta(days=365)).strftime("%Y%m%d"):
            s.append("aberto_menos_12m")
        if str(cnpj[0].get("filiais") or "") == "1":
            s.append("unidade_unica")
    if maps:
        links = [l for m in maps for l in [m.get("web_site") or ""] + [o.get("link") or "" for o in m.get("order_online") or []]]
        site = maps[0].get("web_site") or ""
        if not site or SOCIAL.search(site):
            s.append("sem_site")
        if any(WHATSAPP.search(l) for l in links):
            s.append("wa_me_na_bio")
        if any(CONCORRENTE.search(l.lower()) for l in links):
            s.append("usa_concorrente")
        elif site and not SOCIAL.search(site) and any(
                _dominio(o.get("link")) == _dominio(site) for m in maps for o in m.get("order_online") or []):
            s.append("site_com_pedido_proprio")
        avaliacoes = " ".join(normalizar(r.get("Description") or "") for m in maps for r in m.get("user_reviews") or [])
        if DEMORA.search(avaliacoes):
            s.append("reclamacao_demora")
        # quem avalia "pedi pelo iFood" confirma que a casa vende lá
        if any("ifood.com.br" in l.lower() for l in links) or IFOOD.search(avaliacoes):
            s.append("vende_ifood")
        if ENCOMENDA.search(normalizar(f"{lead['categoria'] or ''} {lead['nome'] or ''}")) or "encomenda" in avaliacoes:
            s.append("aceita_encomenda")
    for perfil in fontes.get("instagram", []):
        if perfil.get("indisponivel"):
            continue
        if perfil.get("whatsapp") and "wa_me_na_bio" not in s:
            s.append("wa_me_na_bio")
        if any(CONCORRENTE.search(l.lower()) for l in perfil.get("links") or []) and "usa_concorrente" not in s:
            s.append("usa_concorrente")
        if "vende_ifood" not in s and (IFOOD.search(normalizar(perfil.get("bio") or "")) or
                                       any("ifood.com.br" in l.lower() for l in perfil.get("links") or [])):
            s.append("vende_ifood")
        ultimo = perfil.get("ultimo_post") or ""
        if ultimo >= (hoje - timedelta(days=30)).isoformat():
            s.append("ig_ativo_30d")
        elif (ultimo and ultimo < (hoje - timedelta(days=180)).isoformat()) or perfil.get("posts") == 0:
            s.append("ig_inativo_6m")
    if franquias and franquias.search(normalizar(lead["fantasia"] or lead["nome"] or "")):
        s.append("franquia")
    return s


def recalcular(con: sqlite3.Connection, hoje: date) -> dict[str, int]:
    """Recalcula score e sinais de todos os leads ativos (clientes, descartados e opt-outs ficam como estão)."""
    cfg = config()
    pesos, perto = cfg["pesos"], {normalizar(m).upper() for m in cfg["score"]["municipios_perto"]}
    clientes = set(cfg["score"]["categorias_clientes"]) | {
        arquivo_d0(r[0]) for r in con.execute("SELECT categoria FROM entity WHERE status='cliente'") if r[0]}
    termos = cnpj_icp.termos_franquia()
    franquias = re.compile(r"\b(" + "|".join(re.escape(t) for t in termos) + r")\b") if termos else None
    ativos = {l["entity_id"]: l for l in con.execute(
        "SELECT * FROM entity WHERE status NOT IN ('cliente','descartado','opt_out')")}
    # Calcula tudo antes de gravar e lê as fontes um lead por vez: o JSON do Maps
    # (~13 KB por lugar) não cabe todo em memória quando a região inteira estiver raspada.
    novos: list[tuple[float, str, str]] = []

    def pontuar(lead: sqlite3.Row, fontes: dict[str, list[dict]]) -> None:
        achados = sinais(lead, fontes, perto, hoje, clientes, franquias)
        novos.append((sum(pesos.get(x, 0) for x in achados), json.dumps(achados), lead["entity_id"]))

    registros = con.execute("SELECT entity_id, source, raw_json FROM source_record ORDER BY entity_id")
    for entity_id, grupo in groupby(registros, key=lambda r: r[0]):
        lead = ativos.pop(entity_id, None)
        if lead is not None:
            fontes: dict[str, list[dict]] = defaultdict(list)
            for _, fonte, raw in grupo:
                fontes[fonte].append(json.loads(raw))
            pontuar(lead, fontes)
    for lead in ativos.values():  # sem nenhuma fonte (ex.: marcado à mão)
        pontuar(lead, {})
    for i in range(0, len(novos), LOTE):
        con.executemany("UPDATE entity SET score=?, sinais=? WHERE entity_id=?", novos[i:i + LOTE])
        con.commit()
    contagem = {"leads": len(novos), "acima_do_corte": sum(total >= cfg["corte"] for total, _, _ in novos)}
    con.execute("INSERT OR REPLACE INTO estado VALUES ('score_recalculado', ?, ?)", (hoje.isoformat(), agora()))
    con.commit()
    log.info("score_recalculado", **contagem)
    return contagem
