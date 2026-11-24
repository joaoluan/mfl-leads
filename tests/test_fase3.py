from datetime import date, datetime, timedelta

import pytest

from mfl import cadencia, db, mensagens, score, seed, ui, whatsapp
from mfl.db import FUSO

CFG = {"semana_1": 2, "depois": 3, "bloqueio_max": 0.05, "alerta_bloqueio": 0.03,
       "janela": {"segunda": ["09:00-18:00"], "terca_a_sexta": ["09:00-11:00", "14:30-17:30"]}}
HOJE = date(2026, 11, 24)  # terça


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "t.db")
    seed.importar_linhas(c, [{"nome": f"Lead {i}", "telefone": f"+55519999900{i:02d}"} for i in range(1, 6)], "teste")
    score.recalcular(c, HOJE)  # do grupo: passa do corte
    return c


def ids(con):
    return [r[0] for r in con.execute("SELECT entity_id FROM entity ORDER BY tel1")]


def tocar(con, entity_id, dia, template_id=None, msg_id=None, ack=None):
    con.execute("INSERT INTO touch (entity_id, canal, texto, enviado_em, template_id, wa_msg_id, ack)"
                " VALUES (?,?,?,?,?,?,?)", (entity_id, "whatsapp", "oi", f"{dia}T10:00:00-03:00", template_id, msg_id, ack))
    con.commit()


def test_todos_os_textos_sao_validos():
    for arquivo in mensagens.arquivos():
        assert mensagens.validar(arquivo, (mensagens.PASTA / f"{arquivo}.md").read_text()) == [], arquivo
        assert len(mensagens.variantes(arquivo)) >= 1


def test_validar_recusa_sem_sair_e_campo_errado():
    erros = mensagens.validar("pizzaria", "Oi {cidade}\n---\nOi, responde SAIR")
    assert any("SAIR" in e for e in erros) and any("cidade" in e for e in erros)


@pytest.mark.parametrize("categoria,fontes,arquivo", [
    ("Pizzaria", {"maps"}, "pizzaria"), ("Hamburgueria artesanal", {"maps"}, "hamburgueria"),
    ("Confeitaria e doces", {"maps"}, "padaria"), ("Bar e petiscaria", {"maps"}, "bar"),
    ("Cafeteria", {"maps"}, "lanchonete"), ("Restaurante italiano", {"maps"}, "restaurante"),
    ("Pizzaria", {"grupo"}, "grupo"), ("Pizzaria", {"grupo", "cnpj"}, "grupo"), (None, {"maps"}, "restaurante"),
])
def test_arquivo_por_categoria(categoria, fontes, arquivo):
    assert mensagens.arquivo_d0(categoria, fontes) == arquivo


def test_rodizio_nao_repete_variante(con):
    assert mensagens.proxima_variante(con, "grupo") == 0
    tocar(con, ids(con)[0], "2026-11-20", template_id="grupo:0")
    assert mensagens.proxima_variante(con, "grupo") == 1
    tocar(con, ids(con)[1], "2026-11-21", template_id="grupo:2")
    assert mensagens.proxima_variante(con, "grupo") == 0


def test_preencher_some_com_vazio_e_horario():
    assert mensagens.preencher("Oi {nome}!\n{sinal}\nTchau", {"nome": "Casa"}) == "Oi Casa!\nTchau"
    # parágrafo do autor fica; placeholder vazio entre parágrafos não deixa linha dupla
    assert mensagens.preencher("A\n\nB\n{sinal}\n\nC", {}) == "A\n\nB\n\nC"
    assert mensagens.preencher("A\n\n{sinal}\n\nC", {}) == "A\n\nC"
    assert mensagens.horario(date(2026, 11, 24)) == "amanhã às 15h"
    assert mensagens.horario(date(2026, 11, 28)) == "segunda às 15h"  # sábado pula domingo
    assert "text=Oi%20tudo%0Abem" in mensagens.link_whatsapp("+5551999990001", "Oi tudo\nbem")


def test_fila_follow_up_primeiro_e_exclusoes(con):
    a, b, c, d, e = ids(con)
    tocar(con, a, "2026-11-21")  # D0 há 3 dias: vence D3
    whatsapp.mudar_status(con, a, "enviado_d0")
    tocar(con, b, "2026-11-24")  # já tocado hoje
    whatsapp.mudar_status(con, b, "enviado_d0")
    cadencia.pular(con, c, HOJE)
    whatsapp.mudar_status(con, d, "cliente")
    con.commit()
    fila = cadencia.fila(con, HOJE, 10)
    assert [(l["entity_id"], etapa) for l, etapa in fila] == [(a, "d3"), (e, "d0")]
    assert cadencia.fila(con, HOJE + timedelta(days=1), 10)[-1][0]["entity_id"] in (c, e)
    assert len(cadencia.fila(con, HOJE, 1)) == 1


def test_transicoes_por_tempo(con):
    a, b, *_ = ids(con)
    tocar(con, a, "2026-11-20")
    whatsapp.mudar_status(con, a, "d7")
    con.execute("UPDATE entity SET status='frio', atualizado_em='2026-09-20T10:00:00-03:00' WHERE entity_id=?", (b,))
    con.commit()
    cadencia.atualizar(con, HOJE)
    status = dict(con.execute("SELECT entity_id, status FROM entity WHERE entity_id IN (?,?)", (a, b)).fetchall())
    assert status == {a: "frio", b: "na_fila"}


def test_teto_rampa_e_bloqueio(con):
    a, b, c, *_ = ids(con)
    assert cadencia.teto(con, CFG, HOJE) == (2, "semana 1")
    tocar(con, a, "2026-11-10", msg_id="M1", ack="entregue")
    tocar(con, b, "2026-11-20", msg_id="M2", ack="entregue")
    assert cadencia.teto(con, CFG, HOJE) == (3, None)
    tocar(con, c, "2026-11-21", msg_id="M3", ack="servidor")  # 1 de 2 parado
    limite, motivo = cadencia.teto(con, CFG, HOJE)
    assert limite == 2 and "bloqueio" in motivo


def test_janela():
    assert cadencia.na_janela(CFG, datetime(2026, 11, 23, 16, 0, tzinfo=FUSO))       # segunda à tarde
    assert not cadencia.na_janela(CFG, datetime(2026, 11, 24, 12, 0, tzinfo=FUSO))   # terça no almoço
    assert cadencia.na_janela(CFG, datetime(2026, 11, 24, 15, 0, tzinfo=FUSO))
    assert not cadencia.na_janela(CFG, datetime(2026, 11, 29, 10, 0, tzinfo=FUSO))   # domingo


def test_telas_e_fluxo(tmp_path, monkeypatch):
    caminho = tmp_path / "ui.db"
    con = db.conectar(caminho)
    seed.importar_linhas(con, [{"nome": "Lead UI", "telefone": "+5551999990009"}], "teste")
    score.recalcular(con, HOJE)
    (lead,) = ids(con)
    monkeypatch.setattr(cadencia, "config", lambda: {**CFG, "semana_1": 1})
    cliente = ui.criar_app(caminho).test_client()

    pagina = cliente.get("/").get_data(as_text=True)
    assert "Lead UI" in pagina and "web.whatsapp.com/send?phone=5551999990009" in pagina
    assert cliente.post(f"/api/abrir/{lead}", json={"template_id": "grupo:1"}).status_code == 204
    whatsapp.registrar_envio(con, lead, "Oi", db.agora(), msg_id="X1")
    assert con.execute("SELECT template_id FROM touch").fetchone()[0] == "grupo:1"
    assert "Teto do dia atingido" in cliente.get("/").get_data(as_text=True)
    assert cliente.post(f"/enviado/{lead}", data={"texto": "x"}).status_code == 409

    whatsapp.processar(con, {"event": "messages.upsert", "data": {
        "key": {"remoteJid": "5551999990009@s.whatsapp.net", "fromMe": False, "id": "R1"},
        "message": {"conversation": "quanto custa?"}, "messageTimestamp": 1_764_000_000}})
    pagina = cliente.get("/respostas").get_data(as_text=True)
    assert "quanto custa?" in pagina and "R$149" in pagina
    (reply_id,) = con.execute("SELECT id FROM reply").fetchone()
    cliente.post(f"/respostas/{reply_id}", data={"classificacao": "nao"})
    assert con.execute("SELECT status FROM entity").fetchone()[0] == "frio"

    assert cliente.get(f"/lead/{lead}").status_code == 200
    cliente.post(f"/lead/{lead}/dados", data={"nome": "Pizzaria Real", "categoria": "pizzaria", "bairro": "Centro"})
    assert "Pizzaria Real" in cliente.get(f"/lead/{lead}").get_data(as_text=True)
    assert cliente.get("/painel").status_code == 200
    assert cliente.get("/config?arquivo=grupo").status_code == 200
    recusa = cliente.post("/config", data={"arquivo": "grupo", "conteudo": "sem opt-out"}).get_data(as_text=True)
    assert "falta o" in recusa
    assert cliente.get("/config?arquivo=../../etc/passwd").status_code == 404
