"""Operação: trava por job, estado dos jobs (aparece no Painel) e backup.

Backup diário (banco + cfg) em data/backup/diario, espelhado no SSD backup-ssd com o Parquet;
aos domingos uma cópia vai para o Orange Pi pela Tailscale.
"""

import fcntl
import gzip
import os
import shutil
import sqlite3
import subprocess
import tarfile
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import structlog

from mfl.db import RAIZ, agora

log = structlog.get_logger()
LOCAL = RAIZ / "data" / "backup" / "diario"
SSD = Path(os.environ.get("MFL_BACKUP_SSD", "/mnt/backup-ssd"))
PI = os.environ.get("MFL_BACKUP_PI", "orangepi:backup/mfl-leads")
MANTER_LOCAL, MANTER_SSD, MANTER_PI = 7, 30, 60  # dias


class JaRodando(Exception):
    pass


@contextmanager
def job(con: sqlite3.Connection, nome: str):
    """flock -n por job (timer atrasado não roda por cima do anterior) e registro de ok/erro em `estado`."""
    trava_dir = RAIZ / "data" / "travas"
    trava_dir.mkdir(parents=True, exist_ok=True)
    with (trava_dir / f"{nome}.lock").open("w") as trava:
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.warning("job_ja_rodando", job=nome)
            raise JaRodando(nome) from None
        con.execute("INSERT OR REPLACE INTO estado VALUES (?,?,?)", (f"job:{nome}", f"rodando pid={os.getpid()}", agora()))
        con.commit()  # a tela Coleta mostra "rodando" enquanto o pid existir
        try:
            yield
        except Exception as erro:
            con.execute("INSERT OR REPLACE INTO estado VALUES (?,?,?)", (f"job:{nome}", f"erro: {erro}"[:300], agora()))
            con.commit()
            raise
        con.execute("INSERT OR REPLACE INTO estado VALUES (?,?,?)", (f"job:{nome}", "ok", agora()))
        con.commit()


def _podar(pasta: Path, dias: int, hoje: date) -> None:
    limite = (hoje - timedelta(days=dias)).isoformat()
    for arquivo in pasta.glob("*-????-??-??.*"):
        if arquivo.name.split("-", 1)[1][:10] < limite:
            arquivo.unlink()


def _rsync(*args: str) -> None:
    subprocess.run(["rsync", "-a", "--timeout=60", *args], check=True, capture_output=True, text=True, timeout=1800)


def backup(con: sqlite3.Connection, hoje: date) -> dict[str, bool]:
    """Cópia consistente do SQLite (API de backup, segura com o webhook gravando) + cfg/."""
    LOCAL.mkdir(parents=True, exist_ok=True)
    temporario = LOCAL / f"leads-{hoje}.db"
    destino = sqlite3.connect(temporario)
    con.backup(destino)
    destino.close()
    with temporario.open("rb") as origem, gzip.open(f"{temporario}.gz", "wb") as saida:
        shutil.copyfileobj(origem, saida)
    temporario.unlink()
    with tarfile.open(LOCAL / f"cfg-{hoje}.tar.gz", "w:gz") as tar:  # cfg é editado na UI e não vai pro git
        tar.add(RAIZ / "cfg", arcname="cfg")
    _podar(LOCAL, MANTER_LOCAL, hoje)
    feito = {"local": True, "ssd": False, "pi": False}

    if os.path.ismount(SSD):
        alvo = SSD / "mfl-leads"
        (alvo / "diario").mkdir(parents=True, exist_ok=True)
        _rsync(f"{LOCAL}/", f"{alvo}/diario/")
        _rsync("--delete", f"{RAIZ / 'data' / 'parquet'}/", f"{alvo}/parquet/")
        _podar(alvo / "diario", MANTER_SSD, hoje)
        feito["ssd"] = True
    else:
        log.warning("backup_ssd_desmontado", ponto=str(SSD))

    if hoje.weekday() == 6:
        try:
            host, caminho = PI.split(":", 1)
            subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host,
                            f"mkdir -p {caminho} && find {caminho} -name '*.gz' -mtime +{MANTER_PI} -delete"],
                           check=True, capture_output=True, timeout=60)
            _rsync(f"{LOCAL}/leads-{hoje}.db.gz", f"{LOCAL}/cfg-{hoje}.tar.gz", f"{PI}/")
            feito["pi"] = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as erro:
            log.error("backup_pi_falhou", erro=str(erro))  # o Pi fora do ar não derruba o backup local
    log.info("backup", **feito)
    return feito
