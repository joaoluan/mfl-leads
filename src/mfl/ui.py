"""UI local (Flask, 127.0.0.1:8000): fila, ficha, respostas, painel e config. Sem login: só localhost."""

import json
import sqlite3
import tomllib
from datetime import date, datetime, time, timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for

from mfl import cadencia, db, mensagens, resolve, whatsapp
from mfl.db import FUSO, agora

STATUS_FICHA = ["respondeu", "trial", "cliente", "objecao", "frio", "na_fila", "descartado"]
MOTIVOS_DESCARTE = ["sem_whatsapp", "nao_e_restaurante", "franquia", "outro"]
CLASSES = {"interesse": "respondeu", "preco": "respondeu", "ja_tenho": "objecao", "nao": "frio", "opt_out": None}
EDITAVEIS = {"tetos.toml": cadencia.TETOS, "icp.toml": db.RAIZ / "cfg" / "icp.toml"}


def criar_app(caminho_db: Path | None = None) -> Flask:
    app = Flask(__name__)

    def con() -> sqlite3.Connection:
        if "con" not in g:
            g.con = db.conectar(caminho_db)
        return g.con

    @app.teardown_appcontext
    def fechar(_erro: BaseException | None) -> None:
        if (c := g.pop("con", None)) is not None:
            c.close()

    def hoje() -> date:
        return datetime.now(FUSO).date()

    def lead_ou_404(entity_id: str) -> sqlite3.Row:
        lead = con().execute("SELECT * FROM entity WHERE entity_id=?", (entity_id,)).fetchone()
        return lead or abort(404)

    def fontes(entity_id: str) -> set[str]:
        return {r[0] for r in con().execute("SELECT source FROM source_record WHERE entity_id=?", (entity_id,))}

    @app.context_processor
    def comum() -> dict:
        estado = con().execute("SELECT valor FROM estado WHERE chave='evolution_conexao'").fetchone()
        pendentes = con().execute("SELECT count(*) FROM reply WHERE revisado=0").fetchone()[0]
        revisoes = con().execute("SELECT count(*) FROM revisao WHERE decidido=0").fetchone()[0]
        ig_checkpoint = con().execute("SELECT 1 FROM estado WHERE chave='ig_checkpoint'").fetchone() is not None
        return {"evolution_ok": estado is None or estado[0] == "open", "pendentes": pendentes, "revisoes": revisoes,
                "ig_checkpoint": ig_checkpoint}

    @app.get("/")
    def fila() -> str:
        cfg, d = cadencia.config(), hoje()
        cadencia.atualizar(con(), d)
        limite, motivo = cadencia.teto(con(), cfg, d)
        feitos = cadencia.feitos(con(), d)
        cartoes = []
        for lead, etapa in cadencia.fila(con(), d, limite - feitos):
            template_id, texto = mensagens.sugerir(con(), lead, etapa, fontes(lead["entity_id"]), d)
            cartoes.append({"lead": lead, "etapa": etapa, "template_id": template_id, "texto": texto,
                            "sinais": json.loads(lead["sinais"] or "[]"),
                            "link": mensagens.link_whatsapp(lead["tel1"], texto)})
        return render_template("fila.html", cartoes=cartoes, feitos=feitos, teto=limite, motivo_teto=motivo,
                               na_janela=cadencia.na_janela(cfg, datetime.now(FUSO)))

    @app.post("/api/abrir/<entity_id>")
    def abrir(entity_id: str) -> tuple[str, int]:
        """Guarda qual variante foi aberta: o webhook liga o envio a ela (métrica por variante)."""
        lead_ou_404(entity_id)
        con().execute("INSERT OR REPLACE INTO estado VALUES (?,?,?)",
                      (f"abrindo:{entity_id}", request.get_json(force=True)["template_id"], agora()))
        con().commit()
        return "", 204

    @app.get("/api/hoje")
    def api_hoje() -> dict:
        return jsonify(feitos=cadencia.feitos(con(), hoje()))

    @app.post("/enviado/<entity_id>")
    def enviado(entity_id: str):
        """Reserva para quando a Evolution não capturou (caída ou DM do Instagram)."""
        lead_ou_404(entity_id)
        limite, _ = cadencia.teto(con(), cadencia.config(), hoje())
        if cadencia.feitos(con(), hoje()) >= limite:
            abort(409, "teto do dia atingido")
        whatsapp.registrar_envio(con(), entity_id, request.form["texto"], agora(),
                                 template_id=request.form.get("template_id"))
        return redirect(request.referrer or url_for("fila"))

    @app.post("/pular/<entity_id>")
    def pular(entity_id: str):
        lead_ou_404(entity_id)
        cadencia.pular(con(), entity_id, hoje())
        return redirect(url_for("fila"))

    @app.get("/lead/<entity_id>")
    def ficha(entity_id: str) -> str:
        lead = lead_ou_404(entity_id)
        etapa = {"enviado_d0": "d3", "d3": "d7"}.get(lead["status"], "d0")
        template_id, texto = mensagens.sugerir(con(), lead, etapa, fontes(entity_id), hoje())
        origem = con().execute("SELECT source, url, captured_at, match_score FROM source_record WHERE entity_id=?"
                               " ORDER BY captured_at", (entity_id,)).fetchall()
        linha = con().execute(
            "SELECT enviado_em AS quando, 'enviado' AS tipo, texto, coalesce(ack,'') AS extra FROM touch WHERE entity_id=?"
            " UNION ALL SELECT recebido_em, 'recebido', texto, coalesce(classificacao,'') FROM reply WHERE entity_id=?"
            " ORDER BY quando DESC", (entity_id, entity_id)).fetchall()
        return render_template("lead.html", lead=lead, origem=origem, linha=linha, texto=texto,
                               template_id=template_id, link=mensagens.link_whatsapp(lead["tel1"], texto) if lead["tel1"] else None,
                               status_ficha=STATUS_FICHA, motivos=MOTIVOS_DESCARTE)

    @app.post("/lead/<entity_id>/status")
    def mudar_status(entity_id: str):
        lead_ou_404(entity_id)
        novo = request.form["status"]
        if novo == "opt_out":
            whatsapp.marcar_opt_out(con(), entity_id, "manual")
        elif novo in STATUS_FICHA:
            motivo = request.form.get("motivo") if novo == "descartado" else None
            whatsapp.mudar_status(con(), entity_id, novo, motivo)
            con().commit()
        else:
            abort(400)
        return redirect(url_for("ficha", entity_id=entity_id))

    @app.post("/lead/<entity_id>/dados")
    def mudar_dados(entity_id: str):
        """Contato do grupo chega só com telefone: o operador completa na conversa."""
        lead_ou_404(entity_id)
        campos = {c: request.form.get(c, "").strip() or None for c in ("nome", "categoria", "bairro")}
        con().execute("UPDATE entity SET nome=coalesce(:nome, nome), categoria=:categoria, bairro=:bairro,"
                      " atualizado_em=:agora WHERE entity_id=:id", {**campos, "agora": agora(), "id": entity_id})
        con().commit()
        return redirect(url_for("ficha", entity_id=entity_id))

    @app.get("/respostas")
    def respostas() -> str:
        itens = con().execute(
            "SELECT r.*, e.nome, e.fantasia, e.tel1, e.status FROM reply r JOIN entity e USING(entity_id)"
            " WHERE r.revisado=0 ORDER BY r.recebido_em DESC").fetchall()
        sugestoes = {a: mensagens.resposta_sugerida(a, hoje()) for a in ("interesse", "preco", "ja_tenho")}
        return render_template("respostas.html", itens=itens, classes=list(CLASSES), sugestoes=sugestoes)

    @app.post("/respostas/<int:reply_id>")
    def classificar(reply_id: str):
        classe = request.form["classificacao"]
        resposta = con().execute("SELECT entity_id FROM reply WHERE id=?", (reply_id,)).fetchone()
        if not resposta or classe not in CLASSES:
            abort(400)
        con().execute("UPDATE reply SET classificacao=?, revisado=1 WHERE id=?", (classe, reply_id))
        if classe == "opt_out":
            whatsapp.marcar_opt_out(con(), resposta["entity_id"], "manual")
        else:
            whatsapp.mudar_status(con(), resposta["entity_id"], CLASSES[classe])
        con().commit()
        return redirect(url_for("respostas"))

    @app.get("/revisao")
    def revisao() -> str:
        pares = con().execute("SELECT * FROM revisao WHERE decidido=0 ORDER BY score DESC LIMIT 50").fetchall()
        lead = lambda i: con().execute("SELECT * FROM entity WHERE entity_id=?", (i,)).fetchone()
        itens = [(p, lead(p["a"]), lead(p["b"])) for p in pares]
        return render_template("revisao.html", itens=[i for i in itens if i[1] and i[2]])

    @app.post("/revisao/<int:revisao_id>")
    def decidir(revisao_id: int):
        """'mesmo': o novo (a, do Maps) é absorvido pelo que já existia (b), que guarda toques e respostas."""
        par = con().execute("SELECT * FROM revisao WHERE id=? AND decidido=0", (revisao_id,)).fetchone() or abort(404)
        if request.form["decisao"] == "mesmo":
            resolve.fundir(con(), par["b"], par["a"])
        con().execute("UPDATE revisao SET decidido=1 WHERE id=?", (revisao_id,))
        con().commit()
        return redirect(url_for("revisao"))

    @app.get("/painel")
    def painel() -> str:
        return render_template("painel.html", **_metricas(con(), cadencia.config(), hoje()))

    @app.route("/config", methods=["GET", "POST"])
    def config() -> str:
        erros: list[str] = []
        arquivo = request.values.get("arquivo", "tetos.toml")
        caminho = EDITAVEIS.get(arquivo) or (
            mensagens.PASTA / f"{arquivo}.md" if arquivo in mensagens.arquivos() else None)
        if caminho is None:
            abort(404)
        conteudo = caminho.read_text(encoding="utf-8")
        if request.method == "POST":
            conteudo = request.form["conteudo"].replace("\r\n", "\n")
            if arquivo.endswith(".toml"):
                try:
                    tomllib.loads(conteudo)
                except tomllib.TOMLDecodeError as erro:
                    erros.append(f"TOML inválido: {erro}")
            else:
                erros = mensagens.validar(arquivo, conteudo)
            if not erros:
                caminho.write_text(conteudo.rstrip("\n") + "\n", encoding="utf-8")
                return redirect(url_for("config", arquivo=arquivo, salvo=1))
        return render_template("config.html", arquivo=arquivo, conteudo=conteudo, erros=erros,
                               opcoes=[*EDITAVEIS, *mensagens.arquivos()], salvo=request.args.get("salvo"))

    return app


def _metricas(con: sqlite3.Connection, cfg: dict, hoje: date) -> dict:
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    desde = (hoje - timedelta(days=30)).isoformat()

    def contar(sql: str, *args: object) -> int:
        return con.execute(sql, args).fetchone()[0] or 0

    enviados_30 = contar("SELECT count(DISTINCT entity_id) FROM touch WHERE enviado_em >= ?", desde)
    responderam_30 = contar(
        "SELECT count(DISTINCT r.entity_id) FROM reply r JOIN (SELECT entity_id, min(enviado_em) p FROM touch"
        " WHERE enviado_em >= ? GROUP BY entity_id) t USING(entity_id) WHERE r.recebido_em >= t.p", desde)
    fim = datetime.combine(hoje + timedelta(days=1), time.min, FUSO)
    taxa_7, envios_7 = cadencia.bloqueio(con, fim - timedelta(days=7), fim)
    por_dia = [cadencia.bloqueio(con, fim - timedelta(days=i + 1), fim - timedelta(days=i)) for i in range(1, 4)]
    alerta = all(envios and taxa > cfg["alerta_bloqueio"] for taxa, envios in por_dia)
    return {
        "hoje_n": contar("SELECT count(DISTINCT entity_id) FROM touch WHERE substr(enviado_em,1,10)=?", hoje.isoformat()),
        "semana_n": contar("SELECT count(DISTINCT entity_id) FROM touch WHERE substr(enviado_em,1,10)>=?",
                           inicio_semana.isoformat()),
        "taxa_resposta": responderam_30 / enviados_30 if enviados_30 else 0.0,
        "enviados_30": enviados_30, "taxa_bloqueio": taxa_7, "envios_7": envios_7, "alerta_bloqueio": alerta,
        "status": dict(con.execute("SELECT status, count(*) FROM entity GROUP BY status").fetchall()),
        "tabelas": {nome: _funil(con, desde, expr, junta) for nome, expr, junta in [
            ("Por fonte", "s.source", "JOIN source_record s ON s.entity_id = t.entity_id"),
            ("Por variante de texto", "coalesce(t0.template_id, 'sem registro')",
             "JOIN touch t0 ON t0.entity_id = t.entity_id AND t0.enviado_em = t.primeiro"),
            ("Por categoria", "coalesce(e.categoria, 'sem categoria')", ""),
            ("Por bairro", "coalesce(e.bairro, 'sem bairro')", ""),
        ]},
    }


def _funil(con: sqlite3.Connection, desde: str, expr: str, junta: str) -> list[sqlite3.Row]:
    """Enviados, responderam e viraram trial/cliente nos últimos 30 dias, agrupados por `expr`."""
    return con.execute(
        "WITH t AS (SELECT entity_id, min(enviado_em) primeiro FROM touch WHERE enviado_em >= ? GROUP BY entity_id),"
        " r AS (SELECT DISTINCT reply.entity_id FROM reply JOIN t ON t.entity_id = reply.entity_id"
        "       WHERE reply.recebido_em >= t.primeiro)"
        f" SELECT {expr} AS chave, count(DISTINCT t.entity_id) AS enviados, count(DISTINCT r.entity_id) AS responderam,"
        " count(DISTINCT CASE WHEN e.status IN ('trial','cliente') THEN e.entity_id END) AS trials"
        f" FROM t JOIN entity e ON e.entity_id = t.entity_id LEFT JOIN r ON r.entity_id = t.entity_id {junta}"
        " GROUP BY chave ORDER BY enviados DESC LIMIT 30", (desde,)).fetchall()
