"""Formulários de "Textos e regras" para os arquivos .toml: cada campo com nome, explicação e validação.

O operador não edita TOML à mão: lê o arquivo, mostra os campos, valida e grava de volta.
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from mfl.db import RAIZ

FAIXA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
AJUDA_SINAL = {
    "mesma_categoria_de_cliente": "Mesmo tipo de casa dos seus clientes: você tem caso para mostrar.",
    "raio": "Fica numa das cidades perto da base.",
    "wa_me_na_bio": "Tem link de WhatsApp no Maps ou no Instagram: já vende pelo WhatsApp.",
    "reclamacao_demora": "Avaliações no Google reclamam de demora.",
    "aberto_menos_12m": "CNPJ aberto há menos de um ano: ainda escolhendo ferramentas.",
    "sem_site": "Não tem site, ou o site é só Instagram.",
    "aceita_encomenda": "Confeitaria, bolos, salgados: pedido pelo WhatsApp é o normal.",
    "ig_ativo_30d": "Postou no Instagram nos últimos 30 dias.",
    "unidade_unica": "Só um endereço: o dono decide sozinho.",
    "franquia": "Nome de rede ou franquia: a decisão é da rede.",
    "site_com_pedido_proprio": "Site já tem pedido online próprio.",
    "ig_inativo_6m": "Instagram parado há mais de 6 meses.",
    "usa_concorrente": "Usa outro sistema de pedido (Goomer, Anota AI…).",
    "vende_ifood": "Vende no iFood: o argumento é pedido direto sem comissão.",
}


@dataclass
class Campo:
    chave: str          # "secao.nome" ou "nome"
    rotulo: str
    tipo: str           # inteiro | pontos | pct | faixas | linhas | categorias
    ajuda: str = ""
    avancado: bool = False


def _campos_ritmo(_dados: dict) -> list[Campo]:
    return [
        Campo("semana_1", "Abordagens por dia na 1ª semana", "inteiro", "Começo mais devagar para o WhatsApp se acostumar com o volume."),
        Campo("depois", "Abordagens por dia depois da 1ª semana", "inteiro"),
        Campo("bloqueio_max", "Bloqueio máximo", "pct", "Se o bloqueio estimado dos últimos 7 dias passar disso, o teto volta ao da 1ª semana."),
        Campo("alerta_bloqueio", "Alerta de bloqueio", "pct", "O painel avisa quando passar disso 3 dias seguidos."),
        Campo("janela.segunda", "Horário de envio na segunda", "faixas", "Faixas no formato 09:00-18:00, separadas por vírgula."),
        Campo("janela.terca_a_sexta", "Horário de envio de terça a sexta", "faixas", "Fora do horário a fila só avisa, não bloqueia."),
    ]


def _campos_pontuacao(dados: dict) -> list[Campo]:
    from mfl.ui import ROTULOS  # rótulos dos sinais ficam junto dos outros textos da tela
    pesos = [Campo(f"pesos.{s}", ROTULOS.get(s, s.replace("_", " ")), "pontos", AJUDA_SINAL.get(s, ""))
             for s in sorted(dados.get("pesos", {}), key=lambda s: -dados["pesos"][s])]
    return [
        Campo("corte", "Pontos mínimos para entrar na fila", "inteiro", "Lead novo abaixo disso não aparece na fila. Lembretes D3 e D7 seguem sempre."),
        *pesos,
        Campo("score.categorias_clientes", "Tipos de casa dos seus clientes", "categorias",
              "Quem for do mesmo tipo ganha os pontos de “Categoria de cliente”. Clientes marcados no sistema também contam."),
        Campo("score.municipios_perto", "Cidades perto da base", "linhas", "Uma por linha. Quem estiver nelas ganha os pontos de “Perto da base”."),
        Campo("recorte.municipios", "Cidades da coleta", "linhas",
              "Uma por linha, como a Receita escreve (maiúsculas, sem acento). Vale para o CNPJ e o Maps.", True),
        Campo("recorte.cnaes", "CNAEs de comida", "linhas", "Um código de 7 dígitos por linha. Muda só a próxima carga mensal do CNPJ.", True),
        Campo("recorte.filiais_rede", "A partir de quantas filiais é rede", "inteiro", "Redes ficam de fora do CNPJ.", True),
    ]


ARQUIVOS = {
    "tetos.toml": ("Ritmo de envio", RAIZ / "cfg" / "tetos.toml", _campos_ritmo),
    "icp.toml": ("Pontuação dos leads", RAIZ / "cfg" / "icp.toml", _campos_pontuacao),
}


def _numero(bruto: str, tipo=int):
    try:
        return tipo(bruto.replace(",", ".") if tipo is float else bruto)
    except ValueError:
        raise ValueError("digite um número inteiro" if tipo is int else "digite um número") from None


def _pegar(dados: dict, chave: str):
    secao, _, nome = chave.rpartition(".")
    return (dados.get(secao, {}) if secao else dados).get(nome)


def _por(dados: dict, chave: str, valor) -> None:
    secao, _, nome = chave.rpartition(".")
    (dados.setdefault(secao, {}) if secao else dados)[nome] = valor


def ler(arquivo: str) -> tuple[str, list[Campo], dict]:
    titulo, caminho, campos = ARQUIVOS[arquivo]
    with caminho.open("rb") as f:
        dados = tomllib.load(f)
    return titulo, campos(dados), dados


def valor_na_tela(campo: Campo, dados: dict) -> str | list[str]:
    valor = _pegar(dados, campo.chave)
    if campo.tipo == "pct":
        return f"{(valor or 0) * 100:g}"
    if campo.tipo == "faixas":
        return ", ".join(valor or [])
    if campo.tipo == "linhas":
        return "\n".join(valor or [])
    if campo.tipo == "categorias":
        return list(valor or [])
    return str(valor if valor is not None else "")


def aplicar(arquivo: str, form, categorias_validas: list[str]) -> dict[str, str]:
    """Valida o formulário e grava o arquivo. Devolve {chave: erro}; vazio = salvo."""
    _, campos, dados = ler(arquivo)
    erros: dict[str, str] = {}
    for c in campos:
        bruto = form.getlist(c.chave) if c.tipo == "categorias" else form.get(c.chave, "").strip()
        try:
            if c.tipo in ("inteiro", "pontos"):
                valor = _numero(bruto)
                if c.tipo == "inteiro" and valor < 0:
                    raise ValueError("use um número positivo")
            elif c.tipo == "pct":
                valor = _numero(bruto, float) / 100
                if not 0 <= valor <= 1:
                    raise ValueError("use um valor entre 0 e 100")
            elif c.tipo == "faixas":
                valor = [f.replace(" ", "") for f in bruto.split(",") if f.strip()]
                ruins = [f for f in valor if not FAIXA.match(f) or f[:5] >= f[6:]]
                if ruins:
                    raise ValueError(f"faixa inválida: {', '.join(ruins)}. Use 09:00-18:00")
            elif c.tipo == "linhas":
                valor = [l.strip() for l in bruto.splitlines() if l.strip()]
                if c.chave == "recorte.cnaes" and any(not re.fullmatch(r"\d{7}", v) for v in valor):
                    raise ValueError("cada CNAE tem 7 dígitos")
                if c.chave == "recorte.municipios" and not valor:
                    raise ValueError("informe ao menos uma cidade")
            else:  # categorias
                valor = [v for v in bruto if v in categorias_validas]
        except ValueError as erro:
            erros[c.chave] = str(erro)
            continue
        _por(dados, c.chave, valor)
    if not erros:
        gravar(ARQUIVOS[arquivo][1], dados)
    return erros


def _toml(valor) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)
    if isinstance(valor, str):
        return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(valor, list):
        itens = [_toml(v) for v in valor]
        return "[" + ", ".join(itens) + "]" if len(itens) <= 4 else "[\n" + "".join(f"  {i},\n" for i in itens) + "]"
    raise TypeError(f"tipo não suportado no TOML: {type(valor).__name__}")


def gravar(caminho: Path, dados: dict) -> None:
    """Escreve o TOML (valores simples no topo, depois as seções) e confere que relê igual antes de trocar o arquivo."""
    linhas = ["# Editado pela tela Textos e regras (http://127.0.0.1:8000/config). As explicações de cada campo estão lá."]
    linhas += [f"{k} = {_toml(v)}" for k, v in dados.items() if not isinstance(v, dict)]
    for secao, valores in dados.items():
        if isinstance(valores, dict):
            linhas += ["", f"[{secao}]", *(f"{k} = {_toml(v)}" for k, v in valores.items())]
    texto = "\n".join(linhas) + "\n"
    if tomllib.loads(texto) != dados:
        raise RuntimeError("o TOML gerado não confere com os valores; nada foi gravado")
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(texto, encoding="utf-8")
    temporario.replace(caminho)
