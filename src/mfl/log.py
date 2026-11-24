"""Log JSONL por job (logs/<job>.jsonl) e legível no terminal."""

import json
import os
import uuid
from pathlib import Path

import structlog

from mfl.db import RAIZ

MAX_BYTES = 20 * 1024 * 1024


def configurar(job: str) -> None:
    """Um arquivo por job para auditar coleta (LGPD) sem misturar fontes."""
    pasta = Path(os.environ.get("MFL_LOGS", RAIZ / "logs"))
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{job}.jsonl"
    if caminho.exists() and caminho.stat().st_size > MAX_BYTES:
        caminho.replace(caminho.with_suffix(".jsonl.1"))  # guarda um arquivo anterior; o mais velho sai
    arquivo = caminho.open("a", encoding="utf-8")

    def gravar(_logger: object, _metodo: str, evento: dict) -> dict:
        arquivo.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
        arquivo.flush()
        return evento

    job_id = uuid.uuid4().hex[:12]

    def identificar(_logger: object, _metodo: str, evento: dict) -> dict:
        # Processador e não contextvars: as threads do Flask não herdam o contexto.
        evento.setdefault("job", job)
        evento.setdefault("job_id", job_id)
        return evento

    structlog.configure(
        processors=[
            identificar,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            gravar,
            structlog.dev.ConsoleRenderer(),
        ]
    )
