import json
import os
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from mfl import controle, db, ui


@pytest.fixture
def coleta(tmp_path, monkeypatch):
    monkeypatch.setattr(controle, "RAIZ", tmp_path)
    monkeypatch.setattr(controle.bairros, "carregar", lambda: {
        "concluido": {"nome": "Bairro Concluído", "municipio": "Porto Alegre"},
        "pendente": {"nome": "Bairro Pendente", "municipio": "Porto Alegre"},
    })
    falha = {"__REALTIME_TIMESTAMP": str(int(datetime.fromisoformat("2026-11-26T04:01:59-03:00").timestamp() * 1_000_000)),
             "UNIT_RESULT": "timeout", "USER_UNIT": "mfl-maps.service"}
    monkeypatch.setattr(controle.subprocess, "run", lambda args, **kw:
                        SimpleNamespace(stdout=json.dumps(falha) if args[0] == "journalctl" else ""))
    con = db.conectar(tmp_path / "t.db")
    con.execute("INSERT INTO estado VALUES ('job:maps', 'rodando pid=0', '2026-11-26T00:01:26-03:00')")
    con.execute("INSERT INTO source_record (source,source_key,raw_json,captured_at) VALUES ('maps','TESTE_SALVO','{}','2026-11-26T01:00')")
    con.commit()
    registros = [
        {"event": "maps_ingerido", "job_id": "anterior", "timestamp": "2026-11-25T01:00", "novos": 999},
        {"event": "maps_ingerido", "job_id": "noite", "timestamp": "2026-11-26T01:00", "bairro": "Bairro Concluído",
         "novos": 2, "vinculados": 1, "aptos": 2, "repetidos": 4, "revisao": 1},
    ]
    (tmp_path / "logs" / "maps").mkdir(parents=True)
    (tmp_path / "logs" / "maps.jsonl").write_text("\n".join(map(json.dumps, registros)))
    log = tmp_path / "logs" / "maps" / "pendente.log"
    log.write_text('{}\n')
    instante = datetime.fromisoformat("2026-11-26T04:01:28-03:00").timestamp()
    os.utime(log, (instante, instante))
    pasta = tmp_path / "data" / "maps" / "2026-11-26"
    pasta.mkdir(parents=True)
    parcial = pasta / "pendente.json"
    parcial.write_text('\n'.join(json.dumps({"place_id": pid}) for pid in
                                  ["TESTE_SALVO", "TESTE_NOVO", "TESTE_NOVO"]) + '\n{"cortado":')
    yield con, tmp_path
    con.close()


def test_resumo_da_interrupcao_distingue_resultados_salvos_e_parcial(coleta):
    con, raiz = coleta
    dados = controle.registros("maps")
    resumo = controle.resumo_maps(con, dados)
    assert resumo["situacao"] == "interrompido"
    assert resumo["inicio"] == "2026-11-26T00:01:26-03:00"
    assert resumo["fim"].startswith("2026-11-26T04:01:59")
    assert "limite de duração" in resumo["motivo"]
    assert resumo["bairros"] == 1
    assert resumo["totais"]["novos"] == 2  # não soma a rodada anterior nem o arquivo parcial
    assert resumo["pendente"] == {"nome": "Bairro Pendente", "lugares": 2, "fora_do_banco": 1,
                                  "invalidos": 1, "arquivo_disponivel": True}
    assert controle.eventos("maps", dados=dados)[0]["evento"] == "Coleta interrompida pelo sistema"
    pagina = ui.criar_app(raiz / "t.db").test_client().get("/coleta").get_data(as_text=True)
    for texto in ("Última execução do Google Maps", "limite de duração", "Bairro Pendente",
                  "1 ainda não constam no banco", "Não retoma a célula", "Coleta interrompida pelo sistema",
                  "Rotina com erro: maps."):
        assert texto in pagina


def test_ausencia_de_journal_nao_inventa_a_causa(coleta, monkeypatch):
    con, _ = coleta
    def indisponivel(*args, **kwargs):
        raise subprocess.TimeoutExpired("journalctl", 5)
    monkeypatch.setattr(controle.subprocess, "run", indisponivel)
    resumo = controle.resumo_maps(con, controle.registros("maps"))
    assert resumo["situacao"] == "interrompido"
    assert "Não há evidência suficiente" in resumo["motivo"]
    assert resumo["totais"]["novos"] == 2


def test_nova_coleta_nao_herda_totais_nem_interrupcao_antiga(coleta):
    con, raiz = coleta
    con.execute("UPDATE estado SET valor=?, atualizado_em='2026-11-26T06:00:00-03:00' WHERE chave='job:maps'",
                (f"rodando pid={os.getpid()}",))
    con.commit()
    dados = controle.registros("maps")
    resumo = controle.resumo_maps(con, dados)
    assert resumo["situacao"] == "rodando"
    assert resumo["totais"]["novos"] == 0
    assert not resumo["motivo"] and not resumo["pendente"]
    dados += [
        {"event": "job_iniciado", "job_id": "manual", "timestamp": "2026-11-26T06:00:00"},
        {"event": "job_concluido", "job_id": "manual", "timestamp": "2026-11-26T06:20:00"},
    ]
    con.execute("UPDATE estado SET valor='ok' WHERE chave='job:maps'")
    con.commit()
    resumo = controle.resumo_maps(con, dados)
    assert resumo["situacao"] == "ok" and not resumo["motivo"]
    assert any(e["evento"] == "Coleta interrompida pelo sistema" for e in controle.eventos("maps", dados=dados))


def test_bairro_com_parcial_ingerido_continua_pendente(coleta):
    con, _ = coleta
    dados = controle.registros("maps")
    dados += [
        {"event": "maps_bairro_iniciado", "job_id": "noite", "timestamp": "2026-11-26T03:00",
         "chave": "pendente", "arquivo": "data/maps/2026-11-26/pendente.json"},
        {"event": "maps_ingerido", "job_id": "noite", "timestamp": "2026-11-26T04:00",
         "bairro": "Bairro Pendente", "novos": 3},
        {"event": "maps_bairro_falhou", "job_id": "noite", "timestamp": "2026-11-26T04:00",
         "bairro": "pendente", "erro": "Tempo esgotado; parcial aproveitado"},
    ]
    resumo = controle.resumo_maps(con, dados)
    assert resumo["bairros"] == 1
    assert resumo["totais"]["novos"] == 5
    assert resumo["pendente"]["nome"] == "Bairro Pendente"


def test_progresso_separa_sucesso_de_tentativas_falhas(coleta):
    con, raiz = coleta
    log = raiz / "logs" / "maps" / "pendente.log"
    log.write_text('\n'.join(json.dumps({"message": "job finished", "status": status})
                             for status in ["success", "failed", "failed"]) + '\nlinha incompleta')
    texto = controle._andamento(con, "maps")
    assert "1 páginas concluídas; 2 tentativas falharam" in texto


def test_interrupcao_entre_ingestao_e_marcacao_nao_conclui_bairro(coleta):
    con, _ = coleta
    dados = controle.registros("maps")
    dados.insert(1, {"event": "job_iniciado", "job_id": "noite", "timestamp": "2026-11-26T00:01:26"})
    resumo = controle.resumo_maps(con, dados)
    assert resumo["bairros"] == 0
    assert resumo["totais"]["novos"] == 2  # já gravado, mesmo sem concluir o bairro
