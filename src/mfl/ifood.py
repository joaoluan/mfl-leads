"""Lojas públicas do iFood por endereço de entrega, sem conta e sem coletar cardápio ou avaliações.

Telefone continua vindo do Maps/Instagram. Sem endereço da loja, nome parecido vai só para revisão.
"""

import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import uuid
from urllib.parse import urlsplit

import structlog
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from mfl import bairros, cnpj_icp, resolve
from mfl.camofox import api
from mfl.classifica import normalizar
from mfl.db import LOTE, agora

log = structlog.get_logger()
USUARIO = "mfl-ifood"  # sessão separada da conta secundária do Instagram
ESPERA = 30
JS_LISTA = """[...document.querySelectorAll('a[href*="/delivery/"]')].map(a => ({
  url: a.href, nome: a.querySelector('.merchant-v2__name')?.textContent?.trim() || '',
  categoria: a.querySelector('[aria-label^="Categoria "]')?.textContent?.trim() || null
})).filter(l => l.nome)"""
JS_DETALHES = """(() => {
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    let d; try { d=JSON.parse(s.textContent); } catch { continue; }
    for (const r of (Array.isArray(d) ? d : (d['@graph'] || [d]))) {
      if (r['@type'] === 'Restaurant' && r.name && r.address?.streetAddress &&
          (r.url || r['@id'])?.split('?')[0] === location.origin + location.pathname) {
        return {endereco:r.address.streetAddress, cep:r.address.postalCode || null,
                municipio:r.address.addressLocality || null, uf:r.address.addressRegion || null};
      }
    }
  }
  return null;
})()"""


class Loja(BaseModel):
    id: uuid.UUID
    url: str
    nome: str = Field(min_length=1, max_length=300)
    municipio: str
    categoria: str | None = None
    endereco: str | None = None
    cep: str | None = None


def id_da_url(endereco: str) -> str | None:
    """Só um link de loja no domínio do iFood prova identidade entre fontes."""
    try:
        url = urlsplit(endereco)
        partes = url.path.strip("/").split("/")
        if url.scheme != "https" or url.netloc != "www.ifood.com.br" or len(partes) != 4 or partes[0] != "delivery":
            return None
        return str(uuid.UUID(partes[3]))
    except ValueError:
        return None


def analisar(item: dict, municipios: list[str]) -> Loja | None:
    """A URL identifica loja e cidade. Nunca confia na cidade do ponto de entrega."""
    identificador = id_da_url(item.get("url") or "")
    if not identificador:
        return None
    url = urlsplit(item["url"])
    partes = url.path.strip("/").split("/")
    nomes = {normalizar(c): c for c in bairros.CIDADES}
    cidades = {f"{bairros.slug(m)}-rs": nomes.get(normalizar(m), m) for m in municipios}
    cidade = cidades.get(partes[1])
    if not cidade or not (item.get("nome") or "").strip():
        return None
    # Detalhe de outra cidade/UF não pode produzir vínculo no endereço errado.
    detalhe = item.get("detalhes") or {}
    if ((detalhe.get("municipio") and normalizar(detalhe["municipio"]) != normalizar(cidade)) or
            (detalhe.get("uf") and detalhe["uf"].upper() not in ("RS", "RIO GRANDE DO SUL"))):
        detalhe = {}
    cep = re.sub(r"\D", "", detalhe.get("cep") or "")
    return Loja(id=identificador, url=f"https://www.ifood.com.br{url.path}", nome=item["nome"].strip(),
                municipio=cidade, categoria=item.get("categoria"), endereco=detalhe.get("endereco"),
                cep=cep if len(cep) == 8 else None)


def ponto_de_entrega(con: sqlite3.Connection, bairro: dict) -> str | None:
    """Usa endereço comercial já coletado no bairro, sem inventar rua ou número."""
    cidade = bairro["municipio"]
    linhas = con.execute(
        "SELECT endereco,bairro FROM entity e WHERE endereco IS NOT NULL AND opt_out=0"
        " AND status NOT IN ('descartado','opt_out') AND lower(municipio) IN (lower(?),lower(?))"
        " AND EXISTS (SELECT 1 FROM source_record s WHERE s.entity_id=e.entity_id AND s.source IN ('maps','cnpj'))"
        " ORDER BY EXISTS (SELECT 1 FROM source_record s WHERE s.entity_id=e.entity_id AND s.source='maps') DESC, entity_id",
        (cidade, normalizar(cidade)))
    for linha in linhas:
        if normalizar(linha["bairro"] or "") in {normalizar(n) for n in bairro["nome"].split("/")} and (
                re.search(r",\s*[1-9]\d*\b", linha["endereco"]) or re.search(r"\s[1-9]\d*$", linha["endereco"])):
            return f"{linha['endereco']}, {cidade} - RS"
    return None


@retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=8), reraise=True,
       retry=retry_if_exception(lambda e: isinstance(e, urllib.error.HTTPError) and e.code == 503))
def _abrir() -> str:
    return api("POST", "/tabs", {"userId": USUARIO, "sessionKey": "coleta",
                                "url": "https://www.ifood.com.br/"})["tabId"]


def _js(aba: str, expressao: str):
    return api("POST", f"/tabs/{aba}/evaluate", {"userId": USUARIO, "expression": expressao}).get("result")


def _esperar(aba: str, expressao: str):
    fim = time.monotonic() + ESPERA
    while time.monotonic() < fim:
        try:
            if _js(aba, "!!document.querySelector('#px-captcha, iframe[src*=captcha]') || "
                   "/access denied|acesso negado/i.test(document.title)"):
                raise RuntimeError("iFood pediu verificação ou bloqueou o acesso. Coleta interrompida.")
            if resultado := _js(aba, expressao):
                return resultado
        except urllib.error.HTTPError as erro:
            if erro.code != 409:  # navegação durante leitura: aguarda a página, sem repetir cliques
                raise
        time.sleep(1)
    raise RuntimeError("iFood não carregou a etapa esperada. Confira o endereço ou tente mais tarde.")


def coletar(endereco: str, limite: int, conhecidos: set[str], municipios: list[str]) -> list[Loja]:
    """Segue as telas públicas do site. Bloqueio nunca vira coleta vazia bem-sucedida."""
    aba = _abrir()
    try:
        _esperar(aba, "!!document.querySelector('input[placeholder=\"Endereço de entrega e número\"]')")
        time.sleep(3)  # aguarda a hidratação antes de disparar o input do React
        _js(aba, "(() => {const e=document.querySelector('input[placeholder=\"Endereço de entrega e número\"]');"
            "e.click(); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"
            + json.dumps(endereco) + "); e.dispatchEvent(new Event('input',{bubbles:true})); return true;})()")
        _esperar(aba, "!!document.querySelector('.btn-address--full-size')")
        _js(aba, "(() => {document.querySelector('.btn-address--full-size').click();return true;})()")
        _esperar(aba, "[...document.querySelectorAll('button')].some(b=>b.innerText==='Confirmar localização')")
        _js(aba, "(() => {[...document.querySelectorAll('button')].find(b=>b.innerText==='Confirmar localização').click();return true;})()")
        _esperar(aba, "[...document.querySelectorAll('button')].some(b=>b.innerText==='Salvar endereço' && !b.disabled)")
        _js(aba, "(() => {[...document.querySelectorAll('button')].find(b=>b.innerText==='Salvar endereço').click();return true;})()")
        _esperar(aba, f"({JS_LISTA}).length")
        lojas: dict[str, Loja] = {}
        sem_novas = 0
        for _ in range(20):
            antes = len(lojas)
            for item in _js(aba, JS_LISTA):
                loja = analisar(item, municipios)
                if loja and str(loja.id) not in conhecidos:
                    lojas[str(loja.id)] = loja
            if len(lojas) >= limite:
                break
            sem_novas = sem_novas + 1 if len(lojas) == antes else 0
            if sem_novas >= 3:
                break
            _js(aba, "(() => {window.scrollTo(0, document.body.scrollHeight);return true;})()")
            time.sleep(2)
        escolhidas = list(lojas.values())[:limite]
        for loja in escolhidas:
            _js(aba, f"(() => {{location.href={json.dumps(loja.url)};return true;}})()")
            _esperar(aba, f"location.pathname==={json.dumps(urlsplit(loja.url).path)} && "
                     "!!document.querySelector('script[type=\"application/ld+json\"]') && "
                     "[...document.querySelectorAll('button')].some(b=>b.innerText==='Ver mais')")
            detalhe = _js(aba, JS_DETALHES)
            if detalhe:
                completa = analisar({**loja.model_dump(mode="json"), "detalhes": detalhe}, municipios)
                if completa:
                    lojas[str(loja.id)] = completa
            else:
                log.warning("ifood_sem_endereco", motivo="Detalhes indisponíveis; lojas seguem sem vínculo automático")
                break  # não insiste nos detalhes bloqueados, preserva o que a lista mostrou
            time.sleep(2)
        return [lojas[str(l.id)] for l in escolhidas]
    finally:
        try:
            api("DELETE", f"/tabs/{aba}?userId={USUARIO}")
        except (OSError, urllib.error.URLError):
            log.warning("ifood_aba_nao_fechou")


def ingerir(con: sqlite3.Connection, lojas: list[Loja], franquias: list[str]) -> dict[str, int]:
    """Idempotência pelo UUID da loja, endereço para vínculo, nome apenas para revisão."""
    total = {"novos": 0, "vinculados": 0, "revisao": 0, "repetidos": 0, "descartados": 0}
    padrao = re.compile(r"\b(" + "|".join(re.escape(t) for t in franquias) + r")\b") if franquias else None
    compartilhados = resolve.telefones_compartilhados(con)
    momento = agora()
    gravados = 0
    with con:
        for loja in lojas:
            if con.execute("SELECT 1 FROM source_record WHERE source='ifood' AND source_key=?", (str(loja.id),)).fetchone():
                total["repetidos"] += 1
                continue
            if padrao and padrao.search(normalizar(loja.nome)):
                total["descartados"] += 1
                continue
            dados = {"_fonte": "ifood", "nome": loja.nome, "fantasia": loja.nome, "municipio": loja.municipio,
                     "categoria": loja.categoria, "endereco": loja.endereco, "cep": loja.cep, "uf": "RS"}
            candidato, nota = resolve.melhor_candidato(con, dados, compartilhados)
            if candidato is not None and (candidato["opt_out"] or candidato["status"] == "opt_out"):
                total["descartados"] += 1
                continue
            if candidato is not None and nota >= resolve.VINCULA:
                eid = candidato["entity_id"]
                resolve.preencher(con, eid, dados)
                total["vinculados"] += 1
            else:
                eid = str(uuid.uuid4())
                con.execute("INSERT INTO entity (entity_id,nome,fantasia,categoria,municipio,uf,endereco,cep,status,criado_em,atualizado_em)"
                            " VALUES (?,?,?,?,?,'RS',?,?,'enriquecimento',?,?)",
                            (eid, loja.nome, loja.nome, loja.categoria, loja.municipio, loja.endereco, loja.cep, momento, momento))
                total["novos"] += 1
                if candidato is not None and nota >= resolve.REVISA:
                    con.execute("INSERT INTO revisao (a,b,score) VALUES (?,?,?)", (eid, candidato["entity_id"], nota))
                    total["revisao"] += 1
            raw = json.dumps(loja.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            con.execute("INSERT INTO source_record (source,source_key,entity_id,raw_json,url,captured_at,hash,match_score)"
                        " VALUES ('ifood',?,?,?,?,?,?,?)",
                        (str(loja.id), eid, raw, loja.url, momento, hashlib.sha256(raw.encode()).hexdigest(), nota or None))
            gravados += 1
            if gravados % LOTE == 0:
                con.commit()
        con.commit()
    log.info("ifood_ingerido", **total)
    return total


def rodar(con: sqlite3.Connection, endereco: str, limite: int = 30) -> dict[str, int]:
    if not endereco.strip() or len(endereco) > 300 or not 1 <= limite <= 100:
        raise ValueError("Informe um endereço com até 300 caracteres e limite entre 1 e 100 lojas.")
    from mfl.score import config
    municipios = config()["recorte"]["municipios"]
    conhecidos = {r[0] for r in con.execute("SELECT source_key FROM source_record WHERE source='ifood'")}
    return ingerir(con, coletar(endereco, limite, conhecidos, municipios), cnpj_icp.termos_franquia())
