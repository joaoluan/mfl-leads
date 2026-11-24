from datetime import date

from conftest import criar_lead
from mfl import cadencia, db, resolve, ui, whatsapp

HOJE = date(2026, 11, 24)


def resposta(tel, texto, msg_id):
    return {"event": "messages.upsert", "data": {
        "key": {"remoteJid": f"{tel.lstrip('+')}@s.whatsapp.net", "fromMe": False, "id": msg_id},
        "message": {"conversation": texto}, "messageTimestamp": 1_764_000_000}}


def test_numero_bloqueado_nao_volta_por_outra_fonte(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    saiu = criar_lead(con, "Saiu", "+5551999990001")
    whatsapp.marcar_opt_out(con, saiu, "pediu_sair")
    outro = criar_lead(con, "Casa do CNPJ", None, status="enriquecimento")
    resolve.preencher(con, outro, {"tel1": "+5551999990001", "_celular": True})  # ex.: wa.me no Instagram
    assert tuple(con.execute("SELECT tel1, status FROM entity WHERE entity_id=?", (outro,)).fetchone()) == (None, "enriquecimento")


def test_ui_recusa_outro_site_e_outro_host(tmp_path):
    cliente = ui.criar_app(tmp_path / "t.db").test_client()
    assert cliente.post("/config", data={"arquivo": "icp.toml", "conteudo": "x"},
                        headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert cliente.get("/", headers={"Host": "evil.example:8000"}).status_code == 403
    assert cliente.get("/").status_code == 200


def test_conversa_agrupada_e_cliente_nao_rebaixa(tmp_path):
    caminho = tmp_path / "t.db"
    con = db.conectar(caminho)
    eid = criar_lead(con, "Cliente Antigo", "+5551999990002", status="cliente")
    whatsapp.processar(con, resposta("+5551999990002", "bom dia", "R1"))
    whatsapp.processar(con, resposta("+5551999990002", "não quero mais nada hoje", "R2"))
    cliente = ui.criar_app(caminho).test_client()
    pagina = cliente.get("/respostas").get_data(as_text=True)
    assert pagina.count('class="nome"') == 1 and "bom dia" in pagina
    (ultima,) = con.execute("SELECT max(id) FROM reply").fetchone()
    cliente.post(f"/respostas/{ultima}", data={"classificacao": "nao"})
    assert con.execute("SELECT status FROM entity WHERE entity_id=?", (eid,)).fetchone()[0] == "cliente"
    assert con.execute("SELECT count(*) FROM reply WHERE revisado=0").fetchone()[0] == 0
    assert "Cliente Antigo" in cliente.get("/busca?q=99999-0002").get_data(as_text=True)


def test_conversa_nao_gasta_o_teto(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    a = criar_lead(con, "A", "+5551999990003", status="respondeu")
    b = criar_lead(con, "B", "+5551999990004")
    whatsapp.registrar_envio(con, a, "respondendo a dúvida", "2026-11-24T10:00:00-03:00")
    whatsapp.registrar_envio(con, b, "oi", "2026-11-24T10:05:00-03:00", template_id="pizzaria:0")
    assert cadencia.feitos(con, HOJE) == 1


def test_nome_provisorio_nao_vai_no_texto_e_ficha_de_conversa_sem_sugestao(tmp_path):
    from mfl import mensagens
    caminho = tmp_path / "t.db"
    con = db.conectar(caminho)
    eid = criar_lead(con, "CNPJ 12345678000199", "+5551999990005", ig_username="casa.doce", categoria="Pizzaria")
    lead = con.execute("SELECT * FROM entity WHERE entity_id=?", (eid,)).fetchone()
    _, texto = mensagens.sugerir(con, lead, "d0", HOJE)
    assert "CNPJ" not in texto and "@casa.doce" in texto
    conversa = criar_lead(con, "Contato (51) 99999-0006", "+5551999990006", status="respondeu")
    pagina = ui.criar_app(caminho).test_client().get(f"/lead/{conversa}").get_data(as_text=True)
    assert "Texto sugerido" not in pagina and "Abrir conversa no WhatsApp" in pagina


def test_regras_em_formulario_validam_e_gravam(tmp_path, monkeypatch):
    import shutil
    import tomllib
    from mfl import ajustes
    for nome in ("tetos.toml", "icp.toml"):
        shutil.copy(db.RAIZ / "cfg" / nome, tmp_path / nome)
    monkeypatch.setattr(ajustes, "ARQUIVOS", {k: (t, tmp_path / k, f) for k, (t, _, f) in ajustes.ARQUIVOS.items()})
    cliente = ui.criar_app(tmp_path / "t.db").test_client()
    pagina = cliente.get("/config?arquivo=icp.toml").get_data(as_text=True)
    assert "Vende no iFood" in pagina and "Pontos mínimos para entrar na fila" in pagina

    _, campos, dados = ajustes.ler("tetos.toml")
    form = {c.chave: ajustes.valor_na_tela(c, dados) for c in campos}
    ruim = {**form, "janela.segunda": "18:00-09:00", "depois": "trinta"}
    pagina = cliente.post("/config", data={"arquivo": "tetos.toml", **ruim}).get_data(as_text=True)
    assert "faixa inválida" in pagina and "digite um número inteiro" in pagina
    assert tomllib.loads((tmp_path / "tetos.toml").read_text())["depois"] == dados["depois"]  # nada gravado

    bom = {**form, "depois": "25", "bloqueio_max": "4,5", "janela.segunda": "09:00-12:00, 13:00-18:00"}
    assert cliente.post("/config", data={"arquivo": "tetos.toml", **bom}).status_code == 302
    novo = tomllib.loads((tmp_path / "tetos.toml").read_text())
    assert novo["depois"] == 25 and novo["bloqueio_max"] == 0.045
    assert novo["janela"]["segunda"] == ["09:00-12:00", "13:00-18:00"] and novo["semana_1"] == dados["semana_1"]

    _, campos, dados = ajustes.ler("icp.toml")  # salvar sem mudar nada mantém os valores
    form = {c.chave: ajustes.valor_na_tela(c, dados) for c in campos}
    form["score.categorias_clientes"] = dados["score"]["categorias_clientes"]
    assert cliente.post("/config", data={"arquivo": "icp.toml", **form}).status_code == 302
    assert tomllib.loads((tmp_path / "icp.toml").read_text()) == dados
