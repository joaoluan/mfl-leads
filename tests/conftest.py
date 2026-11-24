import json
import uuid

from mfl.db import agora


def criar_lead(con, nome, tel, score=0, raw=None, **campos):
    """Lead de teste vindo do Maps (dados falsos). Devolve o entity_id."""
    entity_id = str(uuid.uuid4())
    valores = {"entity_id": entity_id, "nome": nome, "tel1": tel, "score": score, "status": "novo",
               "criado_em": agora(), "atualizado_em": agora(), **campos}
    con.execute(f"INSERT INTO entity ({', '.join(valores)}) VALUES ({', '.join('?' * len(valores))})", list(valores.values()))
    con.execute("INSERT INTO source_record (source, source_key, entity_id, raw_json, captured_at) VALUES ('maps',?,?,?,?)",
                (f"teste:{entity_id}", entity_id, json.dumps(raw or {}), agora()))
    con.commit()
    return entity_id
