"""Lojas públicas do iFood por endereço de entrega, sem conta e sem coletar cardápio ou avaliações.

O Chrome abre em modo UC (SeleniumBase); CNPJ e endereço vêm da
resposta merchant-info/graphql que a própria página recebe. Telefone continua vindo do
Maps/Instagram. Sem endereço da loja, nome parecido vai só para revisão.
"""

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from urllib.parse import urlsplit
from datetime import date, timedelta
from collections.abc import Callable

import structlog
from pydantic import BaseModel, Field
from seleniumbase import SB
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from mfl import bairros, cnpj_icp, resolve
from mfl.classifica import normalizar
from mfl.db import LOTE, agora

log = structlog.get_logger()
ESPERA = 30
ESPERA_VERIFICACAO = 600
LIMITE_MAX = 1000
# Captcha do Cloudflare é clicado via PyAutoGUI, que precisa de tela: headed por padrão (Xvfb no timer).
HEADLESS = os.getenv("MFL_IFOOD_HEADLESS") == "1"
RESPOSTA_INFO = "/merchant-info/graphql"
JS_CHECKPOINT = """(() => {
  const seletores = '[id^="px-captcha"], [class*="px-captcha"], iframe[src*="captcha"], '
    + 'iframe[title*="human" i], iframe[title*="challenge" i], iframe[title*="captcha" i]';
  const visivel = e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden';
  };
  return [...document.querySelectorAll(seletores)].some(visivel)
    || /access denied|acesso negado|um momento|just a moment/i.test(document.title)
    || /press\\s*(?:&|and)\\s*hold|before we continue|confirm you are (?:a )?human|confirme que voc[eê] [eé] humano/i
         .test(document.body?.innerText || '');
})()"""
JS_LISTA = """[...document.querySelectorAll('a[href*="/delivery/"]')].map(a => ({
  url: a.href, nome: a.querySelector('.merchant-v2__name')?.textContent?.trim() || '',
  categoria: a.querySelector('[aria-label^="Categoria "]')?.textContent?.trim() || null
})).filter(l => l.nome)"""


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


def _abrir(ao_verificar: Callable[[bool], None] | None = None):
    """Abre o Chrome em modo UC (passa pelo Cloudflare) numa sessão própria do iFood."""
    cm = SB(uc=True, locale="pt-BR", headless=False if ao_verificar else HEADLESS, log_cdp=True)
    aba = cm.__enter__()
    aba._mfl_cm = cm  # guardado para _fechar devolver o contexto do SeleniumBase
    aba._mfl_ao_verificar = ao_verificar
    try:
        _ir(aba, "https://www.ifood.com.br/")
    except BaseException:
        _fechar(aba)
        raise
    return aba


def _fechar(aba) -> None:
    aba._mfl_cm.__exit__(None, None, None)


def _ir(aba, url: str) -> float:
    """Navega e resolve o captcha do Cloudflare quando ele aparece."""
    aba.uc_open_with_reconnect(url, reconnect_time=6)
    if getattr(aba, "_mfl_ao_verificar", None):
        return _verificar(aba)
    if "Um momento" in aba.get_title():
        aba.uc_gui_click_captcha()
        aba.sleep(4)
    if "Um momento" in aba.get_title():
        raise DetalhesBloqueados("iFood não liberou o acesso (verificação do Cloudflare). Lista preservada.")
    return 0


def _js(aba, expressao: str):
    if not aba.is_connected():
        return aba.cdp.evaluate(f"({expressao})")
    return aba.execute_script(f"return ({expressao});")


def _verificar(aba) -> float:
    """Na coleta assistida, só observa o desafio enquanto o operador o resolve."""
    if not _js(aba, JS_CHECKPOINT):
        return 0
    ao_verificar = getattr(aba, "_mfl_ao_verificar", None)
    if not ao_verificar:
        raise DetalhesBloqueados("iFood pediu verificação HUMAN ou bloqueou o acesso. Lista preservada.")
    inicio = time.monotonic()
    log.warning("ifood_aguardando_verificacao", limite_minutos=ESPERA_VERIFICACAO // 60)
    ao_verificar(True)
    try:
        while _js(aba, JS_CHECKPOINT):
            if time.monotonic() - inicio >= ESPERA_VERIFICACAO:
                raise DetalhesBloqueados("Verificação manual do iFood não concluída em 10 minutos. Lista preservada.")
            time.sleep(1)
    finally:
        ao_verificar(False)
    log.info("ifood_verificacao_concluida")
    return time.monotonic() - inicio


def _esperar(aba, expressao: str | Callable[[], object]):
    fim = time.monotonic() + ESPERA
    while time.monotonic() < fim:
        fim += _verificar(aba)
        if resultado := expressao() if callable(expressao) else _js(aba, expressao):
            return resultado
        time.sleep(1)
    raise TimeoutError("iFood não carregou a etapa esperada. Confira o endereço ou tente mais tarde.")


def _driver(aba):
    """Reconecta o WebDriver após navegação UC para comandos nativos e leitura da rede."""
    if not aba.is_connected():
        aba.driver.connect()
    return aba.driver


def _elemento(aba, seletor: str, por: str = By.CSS_SELECTOR):
    """Espera um alvo visível e habilitado, conferindo o bloqueio a cada leitura."""
    def pronto():
        try:
            return next((e for e in _driver(aba).find_elements(por, seletor) if e.is_displayed() and e.is_enabled()), False)
        except StaleElementReferenceException:
            return False
    return _esperar(aba, pronto)


def _clicar_botao(aba, texto: str) -> None:
    """Ignora cópias ocultas e espera o botão pelo texto antes do clique nativo."""
    _elemento(aba, f"//button[normalize-space(.)={json.dumps(texto, ensure_ascii=False)}]", por=By.XPATH).click()


def _ler_resposta_info(aba, url: str) -> dict | None:
    """Lê a resposta merchant-info/graphql que a própria página da loja recebe (CNPJ e endereço)."""
    _driver(aba).get_log("performance")  # descarta somente eventos da página anterior
    if _ir(aba, url):
        _driver(aba).get_log("performance")  # descarta respostas anteriores à intervenção manual
    limite = time.monotonic() + ESPERA
    pendentes: set[str] = set()
    recarregou = False
    while time.monotonic() < limite:
        pausa = _verificar(aba)
        limite += pausa
        driver = _driver(aba)
        if pausa:
            driver.get_log("performance")
            pendentes.clear()
            recarregou = False
        for entrada in driver.get_log("performance"):
            msg = json.loads(entrada["message"])["message"]
            if msg.get("method") != "Network.responseReceived":
                continue
            resposta = msg["params"]["response"]
            if RESPOSTA_INFO not in resposta["url"]:
                continue
            if resposta["status"] in (403, 429):
                raise DetalhesBloqueados(f"iFood bloqueou os dados da loja (HTTP {resposta['status']}); lista preservada.")
            if resposta["status"] == 200:
                pendentes.add(msg["params"]["requestId"])
        for pedido in pendentes:
            try:
                corpo = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": pedido})["body"]
            except WebDriverException:
                continue  # mantém o requestId até o corpo terminar, sem repetir a requisição
            try:
                return json.loads(corpo)
            except (TypeError, ValueError) as erro:
                raise DetalhesBloqueados("Resposta de dados da loja inválida; lista preservada.") from erro
        if not pendentes and not recarregou:
            # UC pode não expor eventos durante a primeira navegação desconectada.
            aba.refresh()
            recarregou = True
        aba.sleep(0.5)
    return None


def _ler_info(info: dict) -> dict:
    """Extrai do merchant-info só o que o casamento por endereço precisa."""
    extra = info["data"]["merchantExtra"]
    end = extra.get("address") or {}
    rua = " ".join(p for p in [end.get("streetName", ""), end.get("streetNumber", "")] if p)
    return {k: v for k, v in {
        "endereco": rua,
        "bairro": end.get("district"),
        "cep": re.sub(r"\D", "", end.get("zipCode") or ""),
        "municipio": end.get("city"),
        "uf": end.get("state"),
        "cnpj": ((extra.get("documents") or {}).get("CNPJ") or {}).get("value"),
    }.items() if v}


def ler_detalhes(aba, loja: Loja, municipios: list[str]) -> Loja:
    """CNPJ e endereço vêm da resposta merchant-info/graphql da loja, não do DOM."""
    info = _ler_resposta_info(aba, loja.url)
    if not info:
        raise DetalhesBloqueados("iFood não disponibilizou os dados da loja. Lista preservada.")
    try:
        detalhe = _ler_info(info)
    except (KeyError, TypeError, ValueError) as erro:
        raise DetalhesBloqueados(f"merchant-info mudou de formato: {type(erro).__name__}: {erro}") from erro
    completa = analisar({**loja.model_dump(mode="json"), "detalhes": detalhe}, municipios)
    return (completa or loja).model_copy(update={"detalhes_em": agora()})


def coletar(endereco: str, limite: int, conhecidos: set[str], municipios: list[str], *,
            revisitar: set[str] | None = None, detalhar: bool = True,
            ao_verificar: Callable[[bool], None] | None = None) -> tuple[list[Loja], str | None]:
    """Prioriza descobertas; devolve o motivo da suspensão junto da lista preservada."""
    aba = _abrir(ao_verificar) if ao_verificar else _abrir()
    try:
        _esperar(aba, "!!document.querySelector('input[placeholder=\"Endereço de entrega e número\"]')")
        time.sleep(3)  # aguarda a hidratação antes de preencher o input do React
        campo = 'input[placeholder="Endereço de entrega e número"]'
        _elemento(aba, campo).click()
        _elemento(aba, campo).send_keys(endereco)
        _esperar(aba, "!!document.querySelector('.btn-address--full-size')")
        _elemento(aba, ".btn-address--full-size").click()
        _clicar_botao(aba, "Confirmar localização")
        _clicar_botao(aba, "Salvar endereço")
        _esperar(aba, f"({JS_LISTA}).length")
        lojas: dict[str, Loja] = {}
        antigas: dict[str, Loja] = {}
        sem_novas = 0
        bloqueio = None
        for _ in range(20):
            antes = len(lojas)
            for item in _js(aba, JS_LISTA):
                loja = analisar(item, municipios)
                if loja:  # franquia entra e só perde pontos no score (sinal "franquia")
                    if str(loja.id) not in conhecidos:
                        lojas[str(loja.id)] = loja
                    elif detalhar and str(loja.id) in (revisitar or set()):
                        antigas[str(loja.id)] = loja
            if len(lojas) >= limite:
                break
            sem_novas = sem_novas + 1 if len(lojas) == antes else 0
            if sem_novas >= 3:
                break
            try:
                _elemento(aba, "body").send_keys(Keys.END)
            except DetalhesBloqueados as erro:
                bloqueio = str(erro)
                log.warning("ifood_detalhes_bloqueados", motivo=bloqueio)
                break
            time.sleep(2)
        escolhidas = [*lojas.values(), *antigas.values()][:limite]
        for i, loja in enumerate(escolhidas if detalhar and not bloqueio else []):
            try:
                completa = ler_detalhes(aba, loja, municipios)
            except (DetalhesBloqueados, TimeoutError, WebDriverException) as erro:
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
            _fechar(aba)
        except Exception:
            log.warning("ifood_aba_nao_fechou")


def ingerir(con: sqlite3.Connection, lojas: list[Loja], franquias: list[str]) -> dict[str, int]:
    """Idempotência pelo UUID da loja, endereço para vínculo, nome apenas para revisão."""
    total = {"novos": 0, "vinculados": 0, "revisao": 0, "repetidos": 0, "descartados": 0, "atualizados": 0}
    compartilhados = resolve.telefones_compartilhados(con)
    momento = agora()
    gravados = 0
    with con:
        for loja in lojas:
            existente = con.execute("SELECT entity_id,raw_json FROM source_record WHERE source='ifood' AND source_key=?",
                                    (str(loja.id),)).fetchone()
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


def rodar(con: sqlite3.Connection, endereco: str, limite: int = 30, *, aguardar_verificacao: bool = False) -> dict[str, int]:
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

    def verificacao(aguardando: bool) -> None:
        if aguardando:
            con.execute("INSERT OR REPLACE INTO estado VALUES ('ifood_verificacao',?,?)",
                        ("Aguardando sua verificação: conclua o desafio na janela do iFood em até 10 minutos. "
                         "A coleta continuará na mesma janela. Não feche o navegador.", agora()))
        else:
            con.execute("DELETE FROM estado WHERE chave='ifood_verificacao'")
        con.commit()

    if aguardar_verificacao:
        verificacao(False)
    try:
        opcoes = {"ao_verificar": verificacao} if aguardar_verificacao else {}
        lojas, bloqueio = coletar(endereco, limite, conhecidos, municipios, revisitar=revisitar, detalhar=not motivo, **opcoes)
    finally:
        if aguardar_verificacao:
            verificacao(False)
    if bloqueio:
        suspender_detalhes(con, bloqueio)
    return ingerir(con, lojas, cnpj_icp.termos_franquia())
