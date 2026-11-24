"""Baixa os zips do CNPJ (dados abertos da Receita) pelo WebDAV público do compartilhamento.

Só o necessário: Estabelecimentos, Empresas, Cnaes e Municipios. Sócios ficam de fora (LGPD, nada usa).
"""

import base64
import re
from pathlib import Path
from urllib.request import Request, urlopen

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()

BASE = "https://arquivos.receitafederal.gov.br/public.php/webdav"
TOKEN = "YggdBLfdninEJX9"
AUTH = {"Authorization": "Basic " + base64.b64encode(f"{TOKEN}:".encode()).decode()}
NECESSARIOS = re.compile(r"^(Estabelecimentos\d|Empresas\d|Cnaes|Municipios)\.zip$")
BLOCO = 1 << 20


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=2, max=60), reraise=True)
def listar(mes: str) -> dict[str, int]:
    """{arquivo: tamanho} do mês (ex.: 2026-11), já filtrado para o que a esteira usa."""
    pedido = Request(f"{BASE}/{mes}/", method="PROPFIND", headers={**AUTH, "Depth": "1"})
    with urlopen(pedido, timeout=60) as resposta:
        xml = resposta.read().decode()
    arquivos = {}
    for bloco in re.findall(r"<d:response>(.*?)</d:response>", xml, re.S):
        nome = re.search(r"<d:href>[^<]*/([^/<]+)</d:href>", bloco)
        tamanho = re.search(r"<d:getcontentlength>(\d+)", bloco)
        if nome and tamanho and NECESSARIOS.match(nome.group(1)):
            arquivos[nome.group(1)] = int(tamanho.group(1))
    if not arquivos:
        raise RuntimeError(f"mês {mes} sem arquivos esperados: o layout do compartilhamento mudou?")
    return arquivos


@retry(stop=stop_after_attempt(8), wait=wait_exponential(min=5, max=120), reraise=True)
def _baixar_um(mes: str, nome: str, tamanho: int, destino: Path) -> None:
    """Retoma do .part com Range: o servidor da Receita cai no meio de arquivos grandes."""
    final, parcial = destino / nome, destino / f"{nome}.part"
    feito = parcial.stat().st_size if parcial.exists() else 0
    cabecalhos = {**AUTH, **({"Range": f"bytes={feito}-"} if feito else {})}
    with urlopen(Request(f"{BASE}/{mes}/{nome}", headers=cabecalhos), timeout=120) as resposta:
        if feito and resposta.status != 206:
            feito = 0  # servidor ignorou o Range: recomeça
        with parcial.open("ab" if feito else "wb") as f:
            while bloco := resposta.read(BLOCO):
                f.write(bloco)
    if parcial.stat().st_size != tamanho:
        raise IOError(f"{nome}: {parcial.stat().st_size} de {tamanho} bytes")
    parcial.rename(final)


def baixar(mes: str, destino: Path) -> list[Path]:
    """Pula o que já está completo; devolve os zips prontos."""
    destino.mkdir(parents=True, exist_ok=True)
    prontos = []
    for nome, tamanho in sorted(listar(mes).items(), key=lambda x: x[1]):
        final = destino / nome
        if not (final.exists() and final.stat().st_size == tamanho):
            log.info("baixando", arquivo=nome, mb=round(tamanho / 1e6, 1))
            _baixar_um(mes, nome, tamanho, destino)
        prontos.append(final)
    log.info("download_concluido", mes=mes, arquivos=len(prontos))
    return prontos
