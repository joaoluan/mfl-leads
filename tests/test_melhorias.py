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
