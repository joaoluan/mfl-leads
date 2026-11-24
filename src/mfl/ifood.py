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
from datetime import date, timedelta

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
LIMITE_MAX = 1000
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
                municipio:r.address.addressLocality || null, uf:r.address.addressRegion || null,
                cnpj:r.taxID || null};
      }
    }
  }
  return null;
})()"""
JS_SOBRE = """(() => {
  const painel = document.querySelector('.merchant-details-about');
  if (!painel) return null;
  const texto = painel.innerText || painel.textContent || '';
  const endereco = texto.match(/(?:^|\\n)\\s*Endere[cç]o\\s*\\n([\\s\\S]*?)(?=\\n\\s*(?:Outras informa[cç][oõ]es|CNPJ|O iFood é gratuito)|$)/i);
  const cnpj = texto.match(/\\bCNPJ\\s*:?\\s*(\\d{2}\\.?\\d{3}\\.?\\d{3}\\/?\\d{4}-?\\d{2})\\b/i);
  const bloqueado = performance.getEntriesByType('resource').some(r =>
    r.responseStatus === 403 && /merchant-info|catalog/.test(r.name));
  return {endereco_bloco:endereco?.[1]?.trim() || null, cnpj:cnpj?.[1] || null, bloqueado};
})()"""


class DetalhesBloqueados(RuntimeError):
    """Página abriu, mas o iFood negou os dados da loja ao navegador."""


class Loja(BaseModel):
    id: uuid.UUID
    url: str
    nome: str = Field(min_length=1, max_length=300)
    municipio: str
    categoria: str | None = None
    endereco: str | None = None
    cep: str | None = None
    bairro: str | None = None
    cnpj: str | None = None
    detalhes_em: str | None = None


def detalhes_suspensos(con: sqlite3.Connection) -> str | None:
    linha = con.execute("SELECT valor FROM estado WHERE chave='ifood_detalhes_bloqueados'").fetchone()
    return linha[0] if linha else None


def suspender_detalhes(con: sqlite3.Connection, motivo: str) -> None:
    """O bloqueio sobrevive ao processo e vale para todos os bairros até retomada explícita."""
    con.execute("INSERT OR REPLACE INTO estado VALUES ('ifood_detalhes_bloqueados',?,?)", (motivo[:200], agora()))
    con.commit()


def _franquias(termos: list[str]) -> re.Pattern | None:
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in termos) + r")\b") if termos else None


def cnpj_valido(bruto: str | None) -> str | None:
    """Dígitos verificadores evitam vincular empresas por erro de leitura."""
    if not isinstance(bruto, str):
        return None
    numero = re.sub(r"[.\-/\s]", "", bruto or "")
    if not re.fullmatch(r"\d{14}", numero) or len(set(numero)) == 1:
        return None
    for tamanho, pesos in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
                           (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        resto = sum(int(d) * p for d, p in zip(numero[:tamanho], pesos)) % 11
        if int(numero[tamanho]) != (0 if resto < 2 else 11 - resto):
            return None
    return numero


def detalhes_do_painel(painel: dict | None) -> dict:
    """Interpreta apenas o painel Sobre; endereço de entrega e rodapé ficam fora."""
    if not painel:
        return {}
    linhas = [l.strip() for l in (painel.get("endereco_bloco") or "").splitlines() if l.strip()]
    dados = {"cnpj": painel.get("cnpj")}
    if linhas:
        dados["endereco"] = linhas[0]
        bairro = re.split(r"\s+[-–]\s+", linhas[0], maxsplit=1)
        if len(bairro) == 2:
            dados["bairro"] = bairro[1]
        for linha in linhas[1:]:
            if cep := re.search(r"\bCEP\s*:?\s*(\d{5}-?\d{3})\b", linha, re.I):
                dados["cep"] = cep.group(1)
            elif cidade := re.fullmatch(r"(.+?)\s*[-–]\s*([A-Z]{2})", linha):
                dados["municipio"], dados["uf"] = cidade.groups()
    return {k: v for k, v in dados.items() if v}


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
                cep=cep if len(cep) == 8 else None, bairro=detalhe.get("bairro"), cnpj=cnpj_valido(detalhe.get("cnpj")))


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
                raise DetalhesBloqueados("iFood pediu verificação ou bloqueou o acesso. Coleta interrompida.")
            if resultado := _js(aba, expressao):
                return resultado
        except urllib.error.HTTPError as erro:
            if erro.code != 409:  # navegação durante leitura: aguarda a página, sem repetir cliques
                raise
        time.sleep(1)
    raise TimeoutError("iFood não carregou a etapa esperada. Confira o endereço ou tente mais tarde.")


def ler_detalhes(aba: str, loja: Loja, municipios: list[str]) -> Loja:
    """Abre Sobre mesmo com JSON-LD: o CNPJ fica no painel visível da loja."""
    _js(aba, f"(() => {{location.href={json.dumps(loja.url)};return true;}})()")
    _esperar(aba, f"location.pathname==={json.dumps(urlsplit(loja.url).path)} && !!document.querySelector('.merchant-details__button')")
    estruturados = _js(aba, JS_DETALHES) or {}
    _js(aba, "(() => {document.querySelector('.merchant-details__button').click();return true;})()")
    _esperar(aba, "!!document.querySelector('.merchant-details-about')")
    try:
        _esperar(aba, "(() => {const s=" + JS_SOBRE + ";return !!s && !!(s.endereco_bloco || s.cnpj || s.bloqueado);})()")
    except TimeoutError:
        pass  # o JSON-LD pode já ter dados úteis mesmo com o painel vazio
    sobre = _js(aba, JS_SOBRE) or {}
    painel = detalhes_do_painel(sobre)
    if sobre.get("bloqueado") and not (painel or estruturados):
        raise DetalhesBloqueados("iFood bloqueou os detalhes das lojas (403); lista preservada.")
    completa = analisar({**loja.model_dump(mode="json"), "detalhes": {**estruturados, **painel}}, municipios)
    if not (painel or estruturados):
        raise DetalhesBloqueados("Painel Sobre sem dados; leitura de detalhes suspensa.")
    return (completa or loja).model_copy(update={"detalhes_em": agora()})


def coletar(endereco: str, limite: int, conhecidos: set[str], municipios: list[str], *,
            revisitar: set[str] | None = None, detalhar: bool = True) -> tuple[list[Loja], str | None]:
    """Prioriza descobertas; devolve o motivo da suspensão junto da lista preservada."""
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
        antigas: dict[str, Loja] = {}
        padrao = _franquias(cnpj_icp.termos_franquia())
        sem_novas = 0
        for _ in range(20):
            antes = len(lojas)
            for item in _js(aba, JS_LISTA):
                loja = analisar(item, municipios)
                if loja and not (padrao and padrao.search(normalizar(loja.nome))):
                    if str(loja.id) not in conhecidos:
                        lojas[str(loja.id)] = loja
                    elif detalhar and str(loja.id) in (revisitar or set()):
                        antigas[str(loja.id)] = loja
            if len(lojas) >= limite:
                break
            sem_novas = sem_novas + 1 if len(lojas) == antes else 0
            if sem_novas >= 3:
                break
            _js(aba, "(() => {window.scrollTo(0, document.body.scrollHeight);return true;})()")
            time.sleep(2)
        escolhidas = [*lojas.values(), *antigas.values()][:limite]
        bloqueio = None
        for i, loja in enumerate(escolhidas if detalhar else []):
            try:
                completa = ler_detalhes(aba, loja, municipios)
            except (DetalhesBloqueados, TimeoutError) as erro:
                bloqueio = str(erro)
                log.warning("ifood_detalhes_bloqueados", motivo=bloqueio)
                break
            escolhidas[i] = completa
            if not completa.endereco:
                log.warning("ifood_sem_endereco", motivo="Detalhes indisponíveis; lojas seguem sem vínculo automático")
            time.sleep(2)
        return escolhidas, bloqueio
    finally:
        try:
            api("DELETE", f"/tabs/{aba}?userId={USUARIO}")
        except (OSError, urllib.error.URLError):
            log.warning("ifood_aba_nao_fechou")


def ingerir(con: sqlite3.Connection, lojas: list[Loja], franquias: list[str]) -> dict[str, int]:
    """Idempotência pelo UUID da loja, endereço para vínculo, nome apenas para revisão."""
    total = {"novos": 0, "vinculados": 0, "revisao": 0, "repetidos": 0, "descartados": 0, "atualizados": 0}
    padrao = _franquias(franquias)
    compartilhados = resolve.telefones_compartilhados(con)
    momento = agora()
    gravados = 0
    with con:
        for loja in lojas:
            existente = con.execute("SELECT entity_id,raw_json FROM source_record WHERE source='ifood' AND source_key=?",
                                    (str(loja.id),)).fetchone()
            if padrao and padrao.search(normalizar(loja.nome)):
                total["descartados"] += 1
                continue
            dados = {"_fonte": "ifood", "nome": loja.nome, "fantasia": loja.nome, "municipio": loja.municipio,
                     "categoria": loja.categoria, "endereco": loja.endereco, "cep": loja.cep, "bairro": loja.bairro,
                     "cnpj": loja.cnpj, "uf": "RS"}
            candidato, nota = resolve.melhor_candidato(con, dados, compartilhados, existente["entity_id"] if existente else None)
            if candidato is not None and (candidato["opt_out"] or candidato["status"] == "opt_out"):
                total["descartados"] += 1
                continue
            if existente:
                eid = existente["entity_id"]
                atual = con.execute("SELECT * FROM entity WHERE entity_id=?", (eid,)).fetchone()
                if atual["opt_out"] or atual["status"] == "opt_out":
                    total["descartados"] += 1
                    continue
                if loja.cnpj and atual["cnpj"] and loja.cnpj != atual["cnpj"]:
                    log.warning("ifood_cnpj_divergente", source_key=str(loja.id))
                    if candidato is not None and nota >= resolve.REVISA:
                        if not con.execute("SELECT 1 FROM revisao WHERE a=? AND b=? AND decidido=0",
                                           (eid, candidato["entity_id"])).fetchone():
                            con.execute("INSERT INTO revisao(a,b,score) VALUES (?,?,?)", (eid, candidato["entity_id"], nota))
                        total["revisao"] += 1
                    else:
                        total["descartados"] += 1
                    continue
                if candidato is not None and nota >= resolve.VINCULA:
                    conversou = con.execute("SELECT 1 FROM touch WHERE entity_id=? UNION ALL SELECT 1 FROM reply WHERE entity_id=?",
                                             (eid, eid)).fetchone()
                    cnpj_diverge = atual["cnpj"] and candidato["cnpj"] and atual["cnpj"] != candidato["cnpj"]
                    if atual["status"] in ("enriquecimento", "novo", "qualificado", "na_fila") and not conversou and not cnpj_diverge:
                        resolve.fundir(con, candidato["entity_id"], eid)
                        eid = candidato["entity_id"]
                    else:
                        if not con.execute("SELECT 1 FROM revisao WHERE a=? AND b=? AND decidido=0",
                                           (eid, candidato["entity_id"])).fetchone():
                            con.execute("INSERT INTO revisao(a,b,score) VALUES (?,?,?)", (eid, candidato["entity_id"], nota))
                        total["revisao"] += 1
                        dados["cnpj"] = None  # o CNPJ já pertence ao outro lead, aguarda revisão da conversa
                resolve.preencher(con, eid, dados)
                anterior = json.loads(existente["raw_json"])
                novos = loja.model_dump(mode="json")
                for campo, valor in anterior.items():
                    if campo in novos and novos[campo] is None and valor is not None:
                        novos[campo] = valor
                mudou = any(novos.get(c) != anterior.get(c) for c in
                            ("nome", "categoria", "municipio", "bairro", "endereco", "cep", "cnpj"))
                total["atualizados" if mudou else "repetidos"] += 1
            elif candidato is not None and nota >= resolve.VINCULA:
                eid = candidato["entity_id"]
                resolve.preencher(con, eid, dados)
                total["vinculados"] += 1
            else:
                eid = str(uuid.uuid4())
                con.execute("INSERT INTO entity (entity_id,nome,fantasia,categoria,municipio,uf,endereco,cep,bairro,cnpj,status,criado_em,atualizado_em)"
                            " VALUES (?,?,?,?,?,'RS',?,?,?,?,'enriquecimento',?,?)",
                            (eid, loja.nome, loja.nome, loja.categoria, loja.municipio, loja.endereco, loja.cep,
                             loja.bairro, loja.cnpj, momento, momento))
                total["novos"] += 1
                if candidato is not None and nota >= resolve.REVISA:
                    con.execute("INSERT INTO revisao (a,b,score) VALUES (?,?,?)", (eid, candidato["entity_id"], nota))
                    total["revisao"] += 1
            raw = json.dumps(novos if existente else loja.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            con.execute("INSERT INTO source_record (source,source_key,entity_id,raw_json,url,captured_at,hash,match_score)"
                        " VALUES ('ifood',?,?,?,?,?,?,?) ON CONFLICT(source,source_key) DO UPDATE SET"
                        " entity_id=excluded.entity_id,raw_json=excluded.raw_json,url=excluded.url,"
                        " captured_at=excluded.captured_at,hash=excluded.hash,match_score=coalesce(excluded.match_score,source_record.match_score)",
                        (str(loja.id), eid, raw, loja.url, momento, hashlib.sha256(raw.encode()).hexdigest(), nota or None))
            gravados += 1
            if gravados % LOTE == 0:
                con.commit()
        con.commit()
    log.info("ifood_ingerido", **total)
    return total


def rodar(con: sqlite3.Connection, endereco: str, limite: int = 30) -> dict[str, int]:
    if not endereco.strip() or len(endereco) > 300 or not 1 <= limite <= LIMITE_MAX:
        raise ValueError(f"Informe um endereço com até 300 caracteres e limite entre 1 e {LIMITE_MAX} lojas.")
    from mfl.score import config
    municipios = config()["recorte"]["municipios"]
    conhecidos = set()
    revisitar = set()
    motivo = detalhes_suspensos(con)
    if motivo:
        log.info("ifood_detalhes_suspensos", motivo=motivo)
    vencido = (date.fromisoformat(agora()[:10]) - timedelta(days=7)).isoformat()
    for registro in con.execute("SELECT source_key,raw_json FROM source_record WHERE source='ifood'"):
        dados = json.loads(registro["raw_json"])
        conhecidos.add(registro["source_key"])
        completo = all(dados.get(c) for c in ("endereco", "cep", "cnpj"))
        if not motivo and not completo and (dados.get("detalhes_em") or "")[:10] <= vencido:
            revisitar.add(registro["source_key"])
    lojas, bloqueio = coletar(endereco, limite, conhecidos, municipios, revisitar=revisitar, detalhar=not motivo)
    if bloqueio:
        suspender_detalhes(con, bloqueio)
    return ingerir(con, lojas, cnpj_icp.termos_franquia())
