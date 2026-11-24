"""Comandos da esteira (`uv run mfl --help`)."""

import base64
import logging
import os
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import structlog
import typer
from dotenv import load_dotenv

from mfl import bairros, cnpj_baixar, cnpj_etl, cnpj_icp, db, maps, resolve, score, evolution, export, log, seed, ui, webhook, whatsapp
from mfl.fone import de_jid, para_e164

app = typer.Typer(no_args_is_help=True)
logger = structlog.get_logger()


@app.callback()
def _inicio() -> None:
    load_dotenv(db.RAIZ / ".env")


@app.command("seed")
def cmd_seed(csv: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Importa CSV de contatos (nome, telefone, categoria, bairro)."""
    log.configurar("seed")
    seed.importar(db.conectar(), csv)


@app.command("export")
def cmd_export(saida: Path | None = None) -> None:
    """Gera data/export/leads-<data>.csv."""
    log.configurar("export")
    export.exportar(db.conectar(), saida or db.RAIZ / "data" / "export" / f"leads-{date.today()}.csv")


@app.command("evo-conectar")
def cmd_evo_conectar() -> None:
    """Cria/conecta a instância e abre o QR para parear pelo celular."""
    log.configurar("evolution")
    qr = evolution.conectar()
    if not qr:
        logger.info("ja_conectado", situacao=(evolution.situacao() or {}).get("connectionStatus"))
        return
    arquivo = db.RAIZ / "data" / "qr.png"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(base64.b64decode(qr.split(",", 1)[-1]))
    subprocess.Popen(["xdg-open", str(arquivo)])
    logger.info("leia_o_qr", dica="WhatsApp > Aparelhos conectados > Conectar aparelho")
    try:
        for _ in range(60):
            time.sleep(3)
            if (evolution.situacao() or {}).get("connectionStatus") == "open":
                logger.info("conectado")
                return
        logger.error("qr_expirou", dica="rode de novo")
    finally:
        arquivo.unlink(missing_ok=True)


@app.command("evo-status")
def cmd_evo_status() -> None:
    """Mostra se a instância está conectada."""
    log.configurar("evolution")
    s = evolution.situacao() or {}
    logger.info("evolution", instancia=evolution.instancia(), conexao=s.get("connectionStatus"))


@app.command("grupos")
def cmd_grupos() -> None:
    """Lista os grupos (nome e tamanho, sem números) para escolher o de donos."""
    log.configurar("evolution")
    for g in sorted(evolution.grupos(), key=lambda g: -int(g.get("size") or 0)):
        logger.info("grupo", nome=g.get("subject"), participantes=g.get("size"))


@app.command("grupo-importar")
def cmd_grupo_importar(nome: str = typer.Argument(..., help="Nome exato do grupo")) -> None:
    """Importa os participantes do grupo como leads (fonte grupo)."""
    log.configurar("seed")
    achados = [g for g in evolution.grupos() if g.get("subject") == nome]
    if len(achados) != 1:
        raise typer.BadParameter(f"{len(achados)} grupos com o nome {nome!r}; use `mfl grupos`")
    dono = de_jid((evolution.situacao() or {}).get("ownerJid") or "")
    linhas, sem_numero = evolution.participantes(achados[0], dono)
    if sem_numero:
        logger.warning("participantes_sem_numero", quantidade=sem_numero, motivo="WhatsApp escondeu (LID)")
    seed.importar_linhas(db.conectar(), linhas, f"whatsapp:grupo:{nome}")


@app.command("webhook")
def cmd_webhook() -> None:
    """Sobe o receptor do webhook da Evolution (deixar rodando)."""
    log.configurar("webhook")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # o log de acesso imprimiria o token da URL
    webhook.criar_app().run(
        host=os.environ.get("MFL_WEBHOOK_HOST", "172.31.250.1"),
        port=int(os.environ.get("MFL_WEBHOOK_PORTA", "8001")),
    )


@app.command("ui")
def cmd_ui() -> None:
    """Sobe a UI em http://127.0.0.1:8000 (só localhost: não tem login)."""
    log.configurar("ui")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    ui.criar_app().run(host="127.0.0.1", port=8000)


@app.command("marcar")
def cmd_marcar(telefone: str, status: str = typer.Argument(..., help="cliente | opt_out | descartado")) -> None:
    """Marca um número (cria o lead se faltar). Uso: clientes atuais nunca entram na fila."""
    log.configurar("seed")
    if status not in ("cliente", "opt_out", "descartado"):
        raise typer.BadParameter("status deve ser cliente, opt_out ou descartado")
    e164 = para_e164(telefone)
    if not e164:
        raise typer.BadParameter(f"telefone inválido: {telefone}")
    con = db.conectar()
    if not con.execute("SELECT 1 FROM entity WHERE tel1=?", (e164,)).fetchone():
        seed.importar_linhas(con, [{"nome": f"Marcado como {status}", "telefone": e164}], "manual:marcar")
    entity_id = con.execute("SELECT entity_id FROM entity WHERE tel1=?", (e164,)).fetchone()[0]
    if status == "opt_out":
        whatsapp.marcar_opt_out(con, entity_id, "manual")
    else:
        whatsapp.mudar_status(con, entity_id, status, "manual" if status == "descartado" else None)
        con.commit()


@app.command("cnpj-baixar")
def cmd_cnpj_baixar(mes: str = typer.Argument(..., help="AAAA-MM, ex.: 2026-11")) -> None:
    """Baixa os zips do CNPJ necessários para data/cnpj/raw/<mes> (retoma se cair)."""
    log.configurar("cnpj")
    cnpj_baixar.baixar(mes, db.RAIZ / "data" / "cnpj" / "raw" / mes)


@app.command("cnpj-etl")
def cmd_cnpj_etl(mes: str = typer.Argument(..., help="AAAA-MM já baixado"),
                 manter_zips: bool = typer.Option(False, help="Não apagar os zips depois")) -> None:
    """Converte os zips do mês em data/parquet (só RS ativo)."""
    log.configurar("cnpj")
    raw = db.RAIZ / "data" / "cnpj" / "raw" / mes
    zips = sorted(raw.glob("*.zip"))
    cnpj_etl.converter(zips, db.RAIZ / "data" / "parquet", db.RAIZ / "data" / "cnpj" / "tmp")
    if not manter_zips:
        for z in zips:
            z.unlink()


@app.command("cnpj-icp")
def cmd_cnpj_icp() -> None:
    """Aplica o recorte (cfg/icp.toml + cfg/franquias.txt) e grava os leads no banco."""
    log.configurar("cnpj")
    linhas = cnpj_icp.consultar(db.RAIZ / "data" / "parquet", cnpj_icp.recorte(), cnpj_icp.termos_franquia())
    cnpj_icp.ingerir(db.conectar(), linhas, "https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9")


@app.command("bairros-gerar")
def cmd_bairros_gerar() -> None:
    """Gera cfg/bairros.toml a partir do OpenStreetMap (uma vez)."""
    log.configurar("maps")
    logger.info("bairros_gerados", total=bairros.gerar())


def _maps_bairro(chave: str, info: dict) -> dict:
    con = db.conectar()
    pasta = db.RAIZ / "data" / "maps" / date.today().isoformat()
    saida = maps.rodar(info, pasta / f"{chave}.json", db.RAIZ / "logs" / "maps" / f"{chave}.log")
    contagem = maps.ingerir(con, saida, info, cnpj_icp.recorte()["municipios"], cnpj_icp.termos_franquia())
    con.execute("INSERT OR REPLACE INTO estado VALUES (?,?,?)", (f"maps:{chave}", date.today().isoformat(), db.agora()))
    con.commit()
    score.recalcular(con, date.today())
    return contagem


@app.command("maps")
def cmd_maps(bairro: str = typer.Argument(..., help="chave em cfg/bairros.toml, ex.: moinhos-de-vento")) -> None:
    """Raspa um bairro no Google Maps e ingere (place_id único)."""
    log.configurar("maps")
    todos = bairros.carregar()
    if bairro not in todos:
        raise typer.BadParameter(f"{bairro!r} não está em cfg/bairros.toml")
    _maps_bairro(bairro, todos[bairro])


@app.command("maps-fila")
def cmd_maps_fila(limite: int = typer.Option(5, help="Quantos bairros nesta execução"),
                  cidade: str | None = typer.Option(None, help="Só esta cidade (nome como no bairros.toml)")) -> None:
    """Raspa os bairros nunca raspados ou raspados há mais de 60 dias (Porto Alegre e base primeiro)."""
    log.configurar("maps")
    con = db.conectar()
    limite_data = (date.today() - timedelta(days=60)).isoformat()
    feitos = {r[0][5:]: r[1] for r in con.execute("SELECT chave, valor FROM estado WHERE chave LIKE 'maps:%'")}
    ordem = {"Porto Alegre": 0, "Novo Hamburgo": 1}
    pendentes = sorted(((k, v) for k, v in bairros.carregar().items()
                        if (cidade is None or v["municipio"] == cidade) and feitos.get(k, "") <= limite_data),
                       key=lambda kv: (ordem.get(kv[1]["municipio"], 2), kv[1]["municipio"], kv[0]))
    for chave, info in pendentes[:limite]:
        _maps_bairro(chave, info)
    logger.info("maps_fila", feitos=min(limite, len(pendentes)), restantes=max(0, len(pendentes) - limite))


@app.command("resolver")
def cmd_resolver() -> None:
    """Junta contato do grupo com o CNPJ de mesmo telefone (quando o telefone não é de contador)."""
    log.configurar("resolve")
    con = db.conectar()
    logger.info("grupo_cnpj_fundidos", total=resolve.resolver_grupo_cnpj(con))
    score.recalcular(con, date.today())


@app.command("score")
def cmd_score() -> None:
    """Recalcula score e sinais de todos os leads (pesos em cfg/icp.toml)."""
    log.configurar("score")
    score.recalcular(db.conectar(), date.today())
