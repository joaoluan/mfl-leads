"""Instagram pelo camofox-browser já instalado (127.0.0.1:9377), logado na conta secundária.

Só páginas de perfil (sem API, que dá 429), até ~30 por dia, uma por vez com pausa. O @ vem do Maps ou do site
da casa; nada de busca dentro do Instagram. Grava o mínimo (LGPD): bio, links, contagens, último post, data.
Pedido de login/verificação = checkpoint: grava em `estado` e para o lote.
"""

import json
import os
import random
import re
import sqlite3
import string
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

import structlog

from rapidfuzz import fuzz

from mfl import resolve
from mfl.score import CONCORRENTE
from mfl.db import FUSO, LOTE, agora
from mfl.fone import WHATSAPP, celular, para_e164, whatsapp_em

log = structlog.get_logger()
API = os.environ.get("MFL_CAMOFOX_URL", "http://127.0.0.1:9377")
# Mesma sessão do script baixar-insta (onde a conta secundária está logada).
USUARIO = os.environ.get("MFL_CAMOFOX_USER", "baixar-insta")
POR_DIA = 30
PAUSA = (15, 45)  # segundos entre perfis: devagar para não pesar na conta secundária
PAUSA_LONGA, A_CADA = (180, 300), 8  # descanso de 3 a 5 min a cada 8 perfis (30 perfis ~ 30 min)
ESPERA_PAGINA = 6
RESERVADOS = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "direct", "about", "legal", "share"}
HANDLE = re.compile(r"instagram\.com/(?!(?:" + "|".join(RESERVADOS) + r")\b)([A-Za-z0-9_.]{2,30})", re.I)
TELEFONE = re.compile(r"(?:\+?55\s?)?\(?\b[1-9]{2}\)?\s?9\s?\d{4}[\s.-]?\d{4}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ALFABETO = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"
JS_PERFIL = """(() => ({
  url: location.href,
  logado: document.cookie.includes('ds_user_id'),
  meta: document.querySelector('meta[name=description]')?.content || '',
  cabecalho: document.querySelector('header')?.innerText || '',
  links: [...document.querySelectorAll('a[href*="l.instagram.com"], a[href*="wa.me"], a[href*="whatsapp.com"]')].map(a => a.href),
  grade: [...document.querySelectorAll('a')].map(a => a.getAttribute('href') || '').filter(h => /\\/(p|reel)\\/[^/]+\\/?$/.test(h)),
  indisponivel: /isn.t available|não está disponível/i.test(document.body?.innerText || ''),
}))()"""


class Checkpoint(Exception):
    """Instagram pediu login ou verificação: parar tudo até o operador resolver."""


def handle(texto: str | None) -> str | None:
    achado = HANDLE.search(texto or "")
    return achado.group(1).lower().rstrip(".") if achado else None


def data_do_post(shortcode: str) -> date | None:
    """O shortcode é o id da mídia em base64; os bits altos são milissegundos desde a época do Instagram.

    Post de conta privada e alguns reels têm shortcode mais longo: o id são os 11 primeiros caracteres.
    Código que não decodifica numa data plausível vira None, em vez de derrubar a rodada.
    """
    n = 0
    for ch in shortcode[:11]:
        if ch not in ALFABETO:
            return None
        n = n * 64 + ALFABETO.index(ch)
    try:
        dia = datetime.fromtimestamp(((n >> 23) + 1314220021721) / 1000, FUSO).date()
    except (OverflowError, OSError, ValueError):
        return None
    return dia if date(2010, 1, 1) <= dia <= date.today() + timedelta(days=1) else None


def _destino(link: str) -> str:
    """Link externo vem embrulhado em l.instagram.com/?u=<url>."""
    if "l.instagram.com" in link:
        return unquote(parse_qs(urlparse(link).query).get("u", [""])[0])
    return link


def _numero(texto: str) -> int | None:
    """'10.4K' / '1,2 mil' / '781' -> inteiro."""
    achado = re.match(r"([\d.,]+)\s*(k|m|mil|mi)?", texto.strip(), re.I)
    if not achado:
        return None
    valor, mult = achado.group(1), (achado.group(2) or "").lower()
    if mult:
        valor = float(valor.replace(",", ".")) * {"k": 1e3, "mil": 1e3, "m": 1e6, "mi": 1e6}[mult]
    else:
        valor = float(valor.replace(".", "").replace(",", ""))
    return int(valor)


def analisar(pagina: dict) -> dict:
    """Página de perfil (resultado de JS_PERFIL) -> dados mínimos."""
    meta = pagina.get("meta") or ""
    bio = meta.split(" on Instagram: ", 1)[1].strip().strip('"') if " on Instagram: " in meta else ""
    contagens = re.match(r"([\d.,]+\s*[KkMm]?)\s+Followers?,\s*([\d.,]+\s*[KkMm]?)\s+Following,\s*([\d.,]+\s*[KkMm]?)\s+Posts?", meta)
    links = sorted({_destino(l) for l in pagina.get("links") or []})
    datas = [d for h in pagina.get("grade") or [] if (d := data_do_post(h.rstrip("/").rsplit("/", 1)[1]))]
    texto = " ".join([bio, pagina.get("cabecalho") or "", *links])
    tel = telefone_em(texto)
    email = next((e.lower() for e in EMAIL.findall(texto) if not e.lower().endswith((".png", ".jpg"))), None)
    return {
        "bio": bio, "links": links, "whatsapp": bool(WHATSAPP.search(texto)),
        "seguidores": _numero(contagens.group(1)) if contagens else None,
        "posts": _numero(contagens.group(3)) if contagens else None,
        "ultimo_post": max(datas).isoformat() if datas else None,
        "telefone": tel, "email": email,
    }


def telefone_em(texto: str) -> str | None:
    """wa.me primeiro (é o WhatsApp de pedido), depois celular escrito na bio. Os dois servem para WhatsApp."""
    return whatsapp_em(texto) or next(filter(None, (para_e164(b) for b in TELEFONE.findall(texto or ""))), None)


def telefone_nos_links(links: list[str], baixar) -> str | None:
    """Linktree e afins escondem o wa.me numa página externa: abre até 2 (GET simples, fora do Instagram)."""
    for link in [l for l in links if not WHATSAPP.search(l)][:2]:
        tel = telefone_em(baixar(link))
        if tel:
            return tel
    return None


def _api(metodo: str, caminho: str, corpo: dict | None = None):
    pedido = urllib.request.Request(API + caminho, method=metodo, headers={"Content-Type": "application/json"},
                                    data=json.dumps(corpo).encode() if corpo is not None else None)
    with urllib.request.urlopen(pedido, timeout=90) as resposta:
        return json.load(resposta)


def visitar(username: str) -> dict:
    """Abre o perfil numa aba nova, lê a página e fecha a aba (a sessão fica, para não deslogar)."""
    for tentativa in range(3):
        aba = _abrir_aba(f"https://www.instagram.com/{username}/")
        try:
            time.sleep(ESPERA_PAGINA)
            return _api("POST", f"/tabs/{aba}/evaluate", {"userId": USUARIO, "expression": JS_PERFIL})["result"]
        except urllib.error.HTTPError as erro:
            # 410: o camofox reiniciou o navegador (pressão de memória) com a aba aberta; abre de novo
            if erro.code != 410 or tentativa == 2:
                raise
            log.warning("ig_aba_perdida", perfil=username, tentativa=tentativa + 1)
            time.sleep(5)
        finally:
            try:
                _api("DELETE", f"/tabs/{aba}?userId={USUARIO}")
            except (urllib.error.URLError, OSError):
                pass


def _abrir_aba(url: str) -> str:
    for tentativa in range(10):
        try:
            return _api("POST", "/tabs", {"userId": USUARIO, "sessionKey": uuid.uuid4().hex, "url": url})["tabId"]
        except urllib.error.HTTPError as erro:
            if erro.code != 503 or tentativa == 9:
                raise
            time.sleep(3)  # 503: o camofox está reabrindo o navegador ocioso


def extrair_handles(con: sqlite3.Connection, buscar_site=None) -> int:
    """@ dos links do Maps (site, pedido online) e, se não houver, da página inicial do site da casa."""
    buscar_site = buscar_site or _baixar_site
    usados = {r[0] for r in con.execute("SELECT ig_username FROM entity WHERE ig_username IS NOT NULL")}
    leads = con.execute(
        "SELECT e.entity_id, e.site, e.fantasia, e.nome, group_concat(json_extract(s.raw_json, '$.web_site') || ' '"
        " || coalesce(json_extract(s.raw_json, '$.order_online'), ''), ' ') FROM entity e"
        " LEFT JOIN source_record s ON s.entity_id=e.entity_id AND s.source='maps'"
        " WHERE e.ig_username IS NULL AND e.status NOT IN ('cliente','descartado','opt_out')"
        " AND (e.site IS NOT NULL OR s.id IS NOT NULL) GROUP BY e.entity_id").fetchall()
    achados = 0
    for n, (entity_id, site, fantasia, razao, links) in enumerate(leads, start=1):
        nome = handle(links)
        if not nome and site and "instagram.com" not in site and not CONCORRENTE.search(site.lower()):
            achado = handle(buscar_site(site))
            # site feito por agência/plataforma traz o @ deles no rodapé: só vale se parecer com o nome da casa
            casa = resolve.nome_normal(fantasia or razao).replace(" ", "")
            if achado and casa and fuzz.partial_ratio(re.sub(r"[._]", "", achado), casa) >= 70:
                nome = achado
        if nome and nome not in usados:  # shortcut: @ repetido em outro lead não funde os dois; ver na Revisão
            con.execute("UPDATE entity SET ig_username=?, atualizado_em=? WHERE entity_id=?", (nome, agora(), entity_id))
            usados.add(nome)
            achados += 1
        if n % LOTE == 0:
            con.commit()
    con.commit()
    return achados


def _baixar_site(url: str) -> str:
    try:
        pedido = urllib.request.Request(url if "://" in url else f"https://{url}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            return resposta.read(500_000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def pendentes(con: sqlite3.Connection, hoje: date, limite: int) -> list[sqlite3.Row]:
    """Primeiro quem pode ganhar telefone (enriquecimento), depois por score. Revisita após 60 dias."""
    return con.execute(
        "SELECT e.* FROM entity e WHERE e.ig_username IS NOT NULL"
        " AND e.status NOT IN ('cliente','descartado','opt_out')"
        " AND NOT EXISTS (SELECT 1 FROM source_record s WHERE s.source='instagram' AND s.source_key=e.ig_username"
        "                 AND s.captured_at >= ?)"
        " ORDER BY e.status='enriquecimento' DESC, e.score DESC LIMIT ?",
        ((hoje - timedelta(days=60)).isoformat(), limite)).fetchall()


def rodar(con: sqlite3.Connection, hoje: date, limite: int = POR_DIA, visitar_perfil=None,
          baixar=None) -> dict[str, int]:
    visitar_perfil = visitar_perfil or visitar
    baixar = baixar or _baixar_site
    if con.execute("SELECT 1 FROM estado WHERE chave='ig_checkpoint'").fetchone():
        log.error("ig_em_checkpoint", dica="resolva o login (baixar-insta --login) e rode com --retomar")
        return {"perfis": 0, "telefones": 0, "indisponiveis": 0, "checkpoint": 1}
    feitos_hoje = con.execute("SELECT count(*) FROM source_record WHERE source='instagram' AND substr(captured_at,1,10)=?",
                              (hoje.isoformat(),)).fetchone()[0]
    contagem = {"perfis": 0, "telefones": 0, "indisponiveis": 0, "checkpoint": 0}
    leads = pendentes(con, hoje, max(0, min(limite, POR_DIA - feitos_hoje)))
    for i, lead in enumerate(leads):
        if i:
            time.sleep(random.uniform(*(PAUSA_LONGA if i % A_CADA == 0 else PAUSA)))
        pagina = visitar_perfil(lead["ig_username"])
        if not pagina.get("logado") or re.search(r"/accounts/login|/challenge|/suspended", pagina.get("url") or ""):
            con.execute("INSERT OR REPLACE INTO estado VALUES ('ig_checkpoint', ?, ?)", (pagina.get("url"), agora()))
            con.commit()
            contagem["checkpoint"] = 1
            log.error("ig_checkpoint", url=pagina.get("url"), perfil=lead["ig_username"])
            break
        dados = {"indisponivel": True} if pagina.get("indisponivel") else analisar(pagina)
        if not dados.get("indisponivel") and not dados["telefone"]:
            dados["telefone"] = telefone_nos_links(dados["links"], baixar)
        momento = agora()
        raw = json.dumps({**dados, "coletado_em": momento}, ensure_ascii=False, sort_keys=True)
        con.execute("DELETE FROM source_record WHERE source='instagram' AND source_key=?", (lead["ig_username"],))
        con.execute("INSERT INTO source_record (source, source_key, entity_id, raw_json, url, captured_at)"
                    " VALUES ('instagram', ?, ?, ?, ?, ?)",
                    (lead["ig_username"], lead["entity_id"], raw, f"https://www.instagram.com/{lead['ig_username']}/", momento))
        if dados.get("indisponivel"):
            contagem["indisponiveis"] += 1
        elif dados["telefone"] or dados["email"]:
            # telefone_em só devolve wa.me ou celular: sempre apto para WhatsApp
            resolve.preencher(con, lead["entity_id"], {"tel1": dados["telefone"], "_celular": bool(dados["telefone"]),
                                                       "email": dados["email"]})
            if dados["telefone"]:
                con.execute("INSERT OR REPLACE INTO validacao VALUES (?,?,?)",
                            (dados["telefone"], "celular" if celular(dados["telefone"]) else "whatsapp", momento))
                contagem["telefones"] += 1
        contagem["perfis"] += 1
        con.commit()
    log.info("ig_rodado", **contagem)
    return contagem
