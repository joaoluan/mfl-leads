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
from datetime import datetime
from pathlib import Path

from mfl import bairros
from mfl.db import FUSO, RAIZ

ROTINAS = {  # job -> (nome na tela, timer do systemd, o que faz)
    "maps": ("Google Maps", "mfl-maps.timer",
             "Procura comida no mapa, bairro por bairro (restaurante, pizzaria, padaria…). De cada lugar pega nome, "
             "telefone, site, Instagram, nota e avaliações. Junta com o lead que já existe ou cria um novo."),
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
           "job_falhou": "A coleta falhou",
           "job_iniciado": "Coleta iniciada", "job_concluido": "Coleta concluída",
           "job_interrompido": "Coleta interrompida pelo sistema",
           "maps_bairro_iniciado": "Começou a raspar o bairro", "maps_bairro_concluido": "Bairro concluído",
           "maps_timeout": "Bairro atingiu o limite de tempo", "maps_horario_limite": "Fim da janela noturna",
           "maps_arquivo_preservado": "Arquivo da busca anterior preservado",
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
    timers = [t for _, t, _ in ROTINAS.values() if t]
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
        chave = logs[-1].stem
        nome = bairros.carregar().get(chave, {}).get("nome", chave)
        contagem = {"success": 0, "failed": 0}
        for linha in logs[-1].read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(linha)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("message") == "job finished" and e.get("status") in contagem:
                contagem[e["status"]] += 1
        return (f"Raspando {nome}: {contagem['success']} páginas concluídas; "
                f"{contagem['failed']} tentativas falharam. Resultados salvos ao terminar o bairro.")
    if job == "ig":
        feitos = con.execute("SELECT count(*) FROM source_record WHERE source='instagram'"
                             " AND substr(captured_at,1,10)=date('now','localtime')").fetchone()[0]
        return f"{feitos} perfis visitados hoje"
    return ""


def registros(job: str) -> list[dict]:
    """Une o fim do JSONL às interrupções do sistema em ordem cronológica."""
    caminho = RAIZ / "logs" / f"{job}.jsonl"
    linhas = []
    if caminho.exists():
        tamanho = caminho.stat().st_size
        with caminho.open("rb") as f:
            f.seek(max(0, tamanho - 200_000))
            linhas = f.read().decode("utf-8", "replace").splitlines()
        if tamanho > 200_000:
            linhas = linhas[1:]  # a primeira veio cortada no meio
    saida = []
    for linha in linhas:
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        if isinstance(e, dict):
            saida.append(e)
    if job == "maps":
        # SIGTERM/SIGKILL não passam pelo except do job: a evidência fica no journal do systemd.
        try:
            journal = subprocess.run(
                ["journalctl", "--user", "-u", "mfl-maps.service", "-u", "mfl-manual-maps-*",
                 "--since", "7 days ago", "-n", "20", "-o", "json", "--no-pager",
                 "UNIT_RESULT=timeout", "UNIT_RESULT=signal", "UNIT_RESULT=oom-kill"],
                capture_output=True, text=True, timeout=5, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            journal = ""
        for linha in journal.splitlines():
            try:
                e = json.loads(linha)
                quando = datetime.fromtimestamp(int(e["__REALTIME_TIMESTAMP"]) / 1_000_000, FUSO).isoformat()
            except (ValueError, KeyError, TypeError, OverflowError):
                continue
            motivo = {"timeout": "O serviço atingiu o limite de duração e encerrou a coleta em andamento.",
                      "oom-kill": "O sistema encerrou a coleta por falta de memória.",
                      "signal": "O processo recebeu um sinal de encerramento do sistema."}.get(e.get("UNIT_RESULT"))
            if motivo:
                saida.append({"event": "job_interrompido", "level": "error", "timestamp": quando,
                              "motivo": motivo, "servico": e.get("USER_UNIT", "mfl-maps.service")})
    return sorted(saida, key=lambda e: e.get("timestamp", "")[:26])


def eventos(job: str, quantos: int = 40, *, dados: list[dict] | None = None) -> list[dict]:
    saida = []
    for e in reversed(registros(job) if dados is None else dados):
        extra = {k: v for k, v in e.items() if k not in ("event", "level", "timestamp", "job", "job_id")}
        if e.get("event") == "maps_ingerido":
            detalhe = (f"{e.get('bairro')}: {e.get('novos', 0)} leads novos; {e.get('vinculados', 0)} vinculados "
                       f"a leads existentes; {e.get('repetidos', 0)} repetidos ignorados; "
                       f"{e.get('descartados', 0)} descartados. {e.get('aptos', 0)} com telefone apto para WhatsApp; "
                       f"{e.get('revisao', 0)} pares para conferir em Revisão.")
        else:
            detalhe = str(e.get("motivo") or e.get("erro") or ", ".join(f"{k}: {v}" for k, v in extra.items()))
        saida.append({"quando": e.get("timestamp", ""), "nivel": e.get("level", ""), "evento": EVENTOS.get(e.get("event", ""), e.get("event", "")),
                      "extra": detalhe})
        if len(saida) >= quantos:
            break
    return saida


def resumo_maps(con: sqlite3.Connection, dados: list[dict]) -> dict | None:
    """Cruza a última rodada com interrupções externas e distingue arquivo parcial de dados no banco."""
    estado = con.execute("SELECT valor, atualizado_em FROM estado WHERE chave='job:maps'").fetchone()
    aplicacao = [e for e in dados if e.get("job_id") and e.get("event") != "job_ja_rodando"]
    if not aplicacao and not estado:
        return None
    ultimo = aplicacao[-1] if aplicacao else {}
    rodada = [e for e in aplicacao if e.get("job_id") == ultimo.get("job_id")]
    inicio = next((e["timestamp"] for e in rodada if e.get("event") == "job_iniciado"),
                  rodada[0].get("timestamp", "") if rodada else "")
    valor = estado[0] if estado else ""
    if valor.startswith("rodando") and estado:
        inicio = estado[1]
        # A execução acabou de começar e ainda não chegou ao primeiro evento.
        if inicio[:19] > ultimo.get("timestamp", "")[:19]:
            rodada = []
    rodando_agora = rodando(valor)
    falha = next((e for e in reversed(dados) if e.get("event") == "job_interrompido"
                  and e.get("timestamp", "")[:19] >= inicio[:19]), None) if inicio and not rodando_agora else None
    terminou = any(e.get("event") in ("job_concluido", "maps_fila", "score_recalculado") for e in rodada)
    erro = next((e for e in reversed(rodada) if e.get("event") == "job_falhou"), None)
    situacao = "rodando" if rodando_agora else "erro" if erro else "interrompido" if falha or not terminou else "ok"
    motivo = (falha or erro or {}).get("motivo", "")
    if situacao == "interrompido" and not motivo:
        motivo = "O processo parou sem registrar o fim. Não há evidência suficiente para determinar a causa."
    ingeridos = [e for e in rodada if e.get("event") == "maps_ingerido"]
    todos = bairros.carregar()
    falhos = {todos.get(e.get("bairro"), {}).get("nome", e.get("bairro"))
              for e in rodada if e.get("event") == "maps_bairro_falhou"}
    concluidos = {e.get("bairro") for e in ingeridos if e.get("bairro") not in falhos}
    if any(e.get("event") == "job_iniciado" for e in rodada):
        concluidos = {e.get("bairro") for e in rodada if e.get("event") == "maps_bairro_concluido"}
    resumo = {"inicio": inicio, "fim": (falha or erro or (rodada[-1] if rodada else {})).get("timestamp", ""),
              "situacao": situacao, "motivo": motivo, "bairros": len(concluidos),
              "totais": {k: sum(e.get(k, 0) for e in ingeridos)
                         for k in ("novos", "vinculados", "repetidos", "descartados", "aptos", "revisao")},
              "pendente": None}
    iniciado = next((e for e in reversed(rodada) if e.get("event") == "maps_bairro_iniciado"), None)
    chave = iniciado.get("chave") if iniciado else None
    if not chave and inicio:
        logs = sorted((RAIZ / "logs" / "maps").glob("*.log"), key=lambda p: p.stat().st_mtime)
        if logs and datetime.fromtimestamp(logs[-1].stat().st_mtime, FUSO).isoformat()[:19] >= inicio[:19]:
            chave = logs[-1].stem
    if chave in todos and todos[chave]["nome"] not in concluidos:
        nome = todos[chave]["nome"]
        arquivos = sorted((RAIZ / "data" / "maps").glob(f"*/{chave}.json"))
        arquivo = RAIZ / iniciado["arquivo"] if iniciado else (arquivos[-1] if arquivos else None)
        ids = set()
        invalidos = 0
        try:
            linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines() if arquivo else []
        except FileNotFoundError:  # a próxima busca pode preservar o arquivo enquanto a tela o lê
            arquivo, linhas = None, []
        for linha in linhas:
            if not linha.strip():
                continue
            try:
                lugar = json.loads(linha)
                if lugar.get("place_id"):
                    ids.add(lugar["place_id"])
            except (ValueError, AttributeError, TypeError):
                invalidos += 1
        lista = list(ids)
        existentes = 0
        for n in range(0, len(lista), 100):
            lote = lista[n:n + 100]
            existentes += con.execute("SELECT count(*) FROM source_record WHERE source='maps' AND source_key IN ("
                                       + ",".join("?" for _ in lote) + ")", lote).fetchone()[0]
        resumo["pendente"] = {"nome": nome, "lugares": len(ids), "fora_do_banco": len(ids) - existentes,
                              "invalidos": invalidos, "arquivo_disponivel": bool(arquivo and arquivo.is_file())}
    return resumo


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

