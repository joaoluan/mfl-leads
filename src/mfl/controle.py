"""Coleta pela UI: dispara rotinas em segundo plano e mostra o estado delas (rodando, ok, erro, próxima execução).

Disparo via `systemd-run --user`: o job vira uma unidade própria, então reiniciar a UI não mata uma raspagem em curso.
A trava por job (ops.job) continua valendo: manual e timer nunca rodam o mesmo job ao mesmo tempo.
"""

import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from mfl import bairros
from mfl.db import RAIZ

ROTINAS = {  # job -> (nome na tela, timer do systemd, o que faz)
    "maps": ("Google Maps", "mfl-maps.timer",
             "Procura comida no mapa, bairro por bairro (restaurante, pizzaria, padaria…). De cada lugar pega nome, "
             "telefone, site, Instagram, nota e avaliações. Junta com o lead que já existe ou cria um novo. "
             "É a principal fonte de telefone."),
    "ig": ("Instagram", "mfl-ig.timer",
           "Não procura casas novas: completa as que já existem. Acha o @ nos links do Maps e nos sites e visita até "
           "30 perfis por dia, primeiro os leads sem WhatsApp. Se a bio tem WhatsApp, o lead entra na fila. Também vê "
           "se a casa posta e se vende no iFood (sinais do score)."),
    "diario": ("Rotina diária", "mfl-diario.timer",
               "Atualiza a cadência (quem passou de 3 ou 7 dias sem resposta vira lembrete; depois do D7, frio), "
               "recalcula o score de todos e faz o backup."),
    "cnpj": ("CNPJ da Receita", "mfl-cnpj.timer",
             "Uma vez por mês baixa a base da Receita e atualiza as empresas de comida das cidades do recorte "
             "(nome, endereço, data de abertura, filiais). Não traz telefone útil: o da Receita costuma ser do contador."),
}
EVENTOS = {"maps_ingerido": "Bairro raspado", "maps_bairro_falhou": "Bairro falhou", "maps_fila": "Lote do Maps terminou",
           "ig_rodado": "Perfis do Instagram visitados", "ig_checkpoint": "Instagram pediu verificação",
           "ig_em_checkpoint": "Instagram parado (verificação)", "ig_handles": "@ do Instagram achados",
           "score_recalculado": "Score recalculado", "job_ja_rodando": "Já estava rodando", "backup": "Backup",
           "bairros_gerados": "Lista de bairros gerada", "cidade": "Bairros da cidade lidos"}
LOGS = {"maps": "Google Maps", "ig": "Instagram", "ops": "Rotinas", "score": "Score", "cnpj": "CNPJ", "evolution": "WhatsApp"}


def disparar(job: str, *args: str) -> None:
    mfl = Path(sys.executable).with_name("mfl")
    subprocess.run(["systemd-run", "--user", "--collect", "--quiet", "--nice=10",
                    f"--unit=mfl-manual-{job}-{int(time.time())}", f"--working-directory={RAIZ}", str(mfl), *args],
                   check=True, timeout=15, capture_output=True)


def rodando(valor: str | None) -> bool:
    """ops.job grava 'rodando pid=N' ao começar; processo morto à força deixa o texto, por isso confere o pid."""
    pid = re.match(r"rodando pid=(\d+)", valor or "")
    return bool(pid) and Path(f"/proc/{pid.group(1)}").exists()


def _proximas() -> dict[str, str]:
    timers = [t for _, t, _ in ROTINAS.values()]
    try:
        saida = subprocess.run(["systemctl", "--user", "show", *timers, "-p", "Id", "-p", "NextElapseUSecRealtime"],
                               capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    proximas = {}
    for bloco in saida.strip().split("\n\n"):
        campos = dict(l.split("=", 1) for l in bloco.splitlines() if "=" in l)
        quando = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", campos.get("NextElapseUSecRealtime", ""))
        if quando:
            proximas[campos.get("Id", "")] = quando.group(1)
    return proximas


def rotinas(con: sqlite3.Connection) -> list[dict]:
    estado = {r[0][4:]: (r[1], r[2]) for r in con.execute("SELECT chave, valor, atualizado_em FROM estado WHERE chave LIKE 'job:%'")}
    proximas = _proximas()
    linhas = []
    for job, (nome, timer, explica) in ROTINAS.items():
        valor, quando = estado.get(job, (None, None))
        situacao = "rodando" if rodando(valor) else "erro" if (valor or "").startswith("erro") else \
            "ok" if valor == "ok" else "interrompido" if valor else "nunca rodou"
        linhas.append({"job": job, "nome": nome, "explica": explica, "situacao": situacao,
                       "detalhe": valor if situacao == "erro" else "", "quando": quando, "proxima": proximas.get(timer, ""),
                       "andamento": _andamento(con, job) if situacao == "rodando" else ""})
    return linhas


def _andamento(con: sqlite3.Connection, job: str) -> str:
    """O que dá para mostrar enquanto roda: o Maps só grava no fim do bairro, então lê o log do raspador."""
    if job == "maps":
        logs = sorted((RAIZ / "logs" / "maps").glob("*.log"), key=lambda p: p.stat().st_mtime)
        if not logs:
            return ""
        nome = bairros.carregar().get(logs[-1].stem, {}).get("nome", logs[-1].stem)
        paginas = logs[-1].read_text(encoding="utf-8", errors="replace").count('"message":"job finished"')
        return f"Raspando {nome}: {paginas} páginas lidas até agora"
    if job == "ig":
        feitos = con.execute("SELECT count(*) FROM source_record WHERE source='instagram'"
                             " AND substr(captured_at,1,10)=date('now','localtime')").fetchone()[0]
        return f"{feitos} perfis visitados hoje"
    return ""


def eventos(job: str, quantos: int = 40) -> list[dict]:
    """Últimos eventos do log JSONL do job, do mais novo para o mais velho (lê só o fim do arquivo)."""
    caminho = RAIZ / "logs" / f"{job}.jsonl"
    if not caminho.exists():
        return []
    tamanho = caminho.stat().st_size
    with caminho.open("rb") as f:
        f.seek(max(0, tamanho - 200_000))
        linhas = f.read().decode("utf-8", "replace").splitlines()
    if tamanho > 200_000:
        linhas = linhas[1:]  # a primeira veio cortada no meio
    saida = []
    for linha in reversed(linhas):
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        extra = {k: v for k, v in e.items() if k not in ("event", "level", "timestamp", "job", "job_id")}
        saida.append({"quando": e.get("timestamp", ""), "nivel": e.get("level", ""), "evento": EVENTOS.get(e.get("event", ""), e.get("event", "")),
                      "extra": ", ".join(f"{k}: {v}" for k, v in extra.items())[:300]})
        if len(saida) >= quantos:
            break
    return saida


def progresso_maps(con: sqlite3.Connection, cidade: str | None) -> tuple[list[dict], list[dict]]:
    """Por cidade: bairros feitos/total e leads do Maps. Bairros da cidade escolhida com a data da última raspagem."""
    feitos = {r[0][5:]: r[1] for r in con.execute("SELECT chave, valor FROM estado WHERE chave LIKE 'maps:%'")}
    leads = dict(con.execute(
        "SELECT upper(e.municipio), count(DISTINCT e.entity_id) FROM entity e JOIN source_record s"
        " ON s.entity_id=e.entity_id AND s.source='maps' GROUP BY 1").fetchall())
    cidades: dict[str, dict] = {}
    lista = []
    for chave, info in bairros.carregar().items():
        c = cidades.setdefault(info["municipio"], {"nome": info["municipio"], "total": 0, "feitos": 0,
                                                    "leads": leads.get(info["municipio"].upper(), 0)})
        c["total"] += 1
        c["feitos"] += chave in feitos
        if info["municipio"] == cidade:
            lista.append({"chave": chave, "nome": info["nome"], "feito": feitos.get(chave, "")})
    lista.sort(key=lambda b: (b["feito"] != "", b["feito"], b["nome"]))  # nunca raspados primeiro
    return sorted(cidades.values(), key=lambda c: (-c["leads"], c["nome"])), lista

