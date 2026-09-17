"""Baseline de deteccao de citacoes juridicas em documentos de texto.

O modulo nao depende de bibliotecas externas. A funcao publica
``identificar_citacoes`` recebe o texto integral e devolve os spans no formato
pedido pelo desafio: documento, inicio, fim e trecho.

Os indices seguem a convencao do Python: inicio baseado em zero e fim
exclusivo. Assim, para toda linha produzida, vale a invariavel:

    trecho == texto[inicio:fim]
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


_FLAGS = re.IGNORECASE | re.UNICODE | re.VERBOSE

_TRIBUNAL = r"""
    (?:
        STF | STJ | TST | TSE | STM | CNJ |
        TRF\s*[-.]?\s*[1-6](?:[ªa]\s*Regi[aã]o)? |
        TRT\s*[-.]?\s*\d{1,2}(?:[ªa]\s*Regi[aã]o)? |
        TJ\s*[-.]?\s*[A-Z]{2} |
        Supremo\s+Tribunal\s+Federal |
        Superior\s+Tribunal\s+de\s+Justi[cç]a |
        Tribunal\s+Superior\s+do\s+Trabalho |
        Tribunal\s+Superior\s+Eleitoral
    )
"""

_UF = r"(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)"

_NUMERO_CNJ = r"""
    \d{1,7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}
"""

# Linhas de identificacao presentes nos documentos, nao referencias no corpo.
_IDENTIFICACAO_PROCESSO = re.compile(
    rf"""
    \s*(?:Refer[eê]ncia\s*:\s*)?(?:Processo|Autos)\s+
    n[º°o.]\s*{_NUMERO_CNJ}\s*
    """,
    _FLAGS,
)

_DIGITO_OCR = r"[0-9OolISGg]"
_TOKEN_NUMERO = rf"(?={_DIGITO_OCR}*\d){_DIGITO_OCR}+"

_NUMERO_PROCESSO = rf"""
    \d{_DIGITO_OCR}*
    (?:(?:(?:\s*[.\-/–—]\s*)+|\s+){_TOKEN_NUMERO})*
"""

_CLASSE_BASE = r"""
    (?:
        A[cç][aã]o\s+Direta\s+de\s+Inconstitucionalidade |
        A[cç][aã]o\s+Declarat[oó]ria\s+de\s+Constitucionalidade |
        Argui[cç][aã]o\s+de\s+Descumprimento\s+de\s+Preceito\s+Fundamental |
        Recurso\s+em\s+Habeas\s+Corpus |
        Recurso\s+em\s+Mandado\s+de\s+Seguran[cç]a |
        Agravo\s+em\s+Recurso\s+Especial |
        Agravo\s+de\s+Instrumento |
        Suspens[aã]o\s+de\s+Liminar\s+e\s+de\s+Senten[cç]a |
        Recurso\s+Especial\s+Eleitoral |
        Recurso\s+Extraordin[aá]rio |
        Recurso\s+Especial |
        Recurso\s+de\s+Revista |
        Reclama[cç][aã]o |
        Habeas\s+Corpus |
        Mandado\s+de\s+Seguran[cç]a |
        Rec\.?\s*Esp\.? |
        R\.?\s*Esp\.? |
        A\.?\s*REsp |
        H\.?\s*C\.? |
        R\s*-\s*Rp |
        AGR\s*-\s*RESPE |
        Ag\.?\s*Int\.? |
        AgREsp |
        (?:ADI|ADC|ADPF|ADO|ADIn|AREspEl|REspe\.?|AREsp|EREsp|EAREsp|REsp|RESP|
           R\.?E\.?|ARE|Recl\.?|Rcl|RHC|HC|RMS|MS|MI|AI|ACO|AO|APL|RSE|AR|AP|PET|SL|
           STA|SS|IF|Inq|RR|AIRR|ARR|RRAg|RO|ROT|RCED|AIME)
    )
"""

_MODIFICADOR = r"""
    (?:
        (?:Primeiro|Segundo|Terceiro)?\s*AG\.?\s*REG\.? |
        Ag\.?\s*Int\.? | AgRg | AgR | EDcl | EDs? |
        Agravo\s+(?:Interno|Regimental) |
        Embargos?\s+de\s+Declara[cç][aã]o
    )
"""

_CLASSE_PROCESSUAL = rf"""
    (?:
        (?:(?:{_MODIFICADOR})\s*(?:-|–|—|\s+(?:no|na|nos|nas)\s+)){{1,5}}{_CLASSE_BASE} |
        {_CLASSE_BASE} |
        AgInt | AgRg | EDcl
    )
"""

_CLASSE_TST = r"(?:R\s*-\s*Rp|AgARR|AIRR|ARR|RR|ED|E)"

_PROCESSO_TST = rf"""
    \b(?:processo\s*(?:n(?:[.º°o]|[uú]mero)?\s*)?)?
    (?:TST\s*-\s*)?
    {_CLASSE_TST}(?:\s*-\s*{_CLASSE_TST})*\s*-\s*
    {_NUMERO_PROCESSO}
"""

_FONTE_NORMATIVA = r"""
    (?:
        (?:CPC|CPP|CP|CC|CLT|CDC|CTN|CF|CRFB)(?:\s*/\s*\d{2,4})? |
        Constitui[cç][aã]o(?:\s+da\s+Rep[uú]blica|\s+Fed.ral)?(?:\s+de\s+1988)? |
        Consolida[cç][aã]o\s+das\s+Leis\s+do\s+Trabalho |
        C[oó]digo\s+(?:Civil|Penal(?:\s+Militar)?|de\s+Processo\s+Civil|de\s+Processo\s+Penal|
                         Tribut[aá]rio\s+Nacional|Eleitoral|de\s+Defesa\s+do\s+Consumidor) |
        Lei(?:\s+Complementar)?\s*(?:n(?:[.º°o]|[uú]mero)?\s*)?
            \d+(?:\.\d{3})*(?:\s*/\s*\d{2,4})? |
        Decreto(?:-Lei)?\s*(?:n(?:[.º°o]|[uú]mero)?\s*)?
            \d+(?:\.\d{3})*(?:\s*/\s*\d{2,4})?
    )
"""

_ARTIGO = rf"""
    \b(?:arts?\.?|artigos?)\s*
    \d+(?:\.\d{{3}})*[A-Z]?(?:[º°o])?
    (?:
        \s*(?:,|e|a)\s*
        (?:
            §{{1,2}}\s*\d+[A-Z]?(?:[º°o])?(?:\s*-\s*[A-Z])? |
            \d+[A-Z]?(?:[º°o])? |
            (?:incisos?\s+)?[IVXLCDM]+(?![A-Z]) |
            al[ií]nea\s+["']?[a-z]["']? |
            ["'][a-z]["'] |
            caput
        )
    )*
    (?:\s*,?\s*(?:do|da|dos|das)\s+{_FONTE_NORMATIVA})?
"""

_COMPLEMENTO_ARTIGO = r"""
    (?:
        §{1,2}\s*\d+[A-Z]?(?:[º°o])? |
        par[aá]grafo\s+\d+[A-Z]?(?:[º°o])? |
        inciso\s+[IVXLCDM]+ |
        al[ií]nea\s+["']?[a-z]["']?
    )
"""

_NOME_PESSOA = r"""
    (?-i:[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç'-]+)
    (?:\s+(?-i:[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç'-]+)){1,5}
"""

_REFERENCIA_INCOMPLETA = rf"""
    \b(?:
        (?:julgado|precedente)\s+do\s+{_TRIBUNAL}\s+
            (?:(?:proferido|prof.rido)\s+em|de)\s+\d{{4}}\s*,?\s*
            (?:pela|da)\s+relatoria\s+d[eaoc]\s+{_NOME_PESSOA} |
        ac[oó]rd[aã]o\s+do\s+{_TRIBUNAL}\s+julgado\s+em\s+\d{{4}}\s+
            sob\s+relatoria\s+de\s+{_NOME_PESSOA} |
        (?:Reclama[cç][aã]o|Agravo\s+em\s+Recurso\s+Especial|
           Recurso\s+em\s+Habeas\s+Corpus)\s+do\s+{_TRIBUNAL}\s*,?\s*
            de\s+\d{{4}}\s*,?\s*Rel\.?\s*Min\.?\s*{_NOME_PESSOA} |
        (?:Rcl|APL)\s+de\s+\d{{4}}\s*,?\s*Rel\.?\s*Min\.?\s*{_NOME_PESSOA}
    )
"""


@dataclass(frozen=True, slots=True)
class _Padrao:
    tipo: str
    expressao: re.Pattern[str]
    prioridade: int


@dataclass(frozen=True, slots=True)
class _Candidato:
    inicio: int
    fim: int
    tipo: str
    prioridade: int

    @property
    def tamanho(self) -> int:
        return self.fim - self.inicio


def _compilar(tipo: str, expressao: str, prioridade: int) -> _Padrao:
    return _Padrao(tipo, re.compile(expressao, _FLAGS), prioridade)


_PADROES: tuple[_Padrao, ...] = (
    _compilar("processo", _PROCESSO_TST, 120),
    _compilar(
        "processo",
        rf"""
        \b{_CLASSE_PROCESSUAL}
        \s+(?:n(?:[.º°o]|[uú]mero)?\s*)?
        {_NUMERO_PROCESSO}
        (?:\s*(?:[-/–—]\s*|\(\s*){_UF}\s*\)?)?
        (?:\s*,?\s*(?:do|da)\s+{_TRIBUNAL})?
        """,
        110,
    ),
    _compilar(
        "sumula",
        rf"""
        \b(?:S[uú]mula|5[uú]mula|S[uú]m\.)(?:\s+Vinculante)?
        \s*(?:n(?:[.º°o]|[uú]mero)?\s*)?\d+(?:\.\d{{3}})*
        (?:\s*[-/]\s*{_TRIBUNAL}|\s+(?:do|da)\s+{_TRIBUNAL})?
        """,
        110,
    ),
    _compilar(
        "dispositivo",
        rf"""
        \b{_COMPLEMENTO_ARTIGO}\s+(?:do|da)\s+{_ARTIGO}
        """,
        105,
    ),
    _compilar("dispositivo", _ARTIGO, 100),
    _compilar(
        "tema",
        rf"""
        \bTem[aáã]
        (?:\s+(?:Repetitivo|de\s+Repercuss[aã]o\s+Geral))?
        \s*(?:n(?:[.º°o]|[uú]mero)?\s*)?\d+(?:\.\d{{3}})*
        (?:\s+da\s+repercuss[aã]o\s+geral)?
        (?:\s+(?:do|da)\s+{_TRIBUNAL})?
        """,
        95,
    ),
    _compilar(
        "norma",
        rf"""
        \b(?:
            Lei(?:\s+Complementar)? |
            Decreto(?:-Lei)? |
            Emenda\s+Constitucional |
            Medida\s+Provis[oó]ria |
            Resolu[cç][aã]o
        )
        \s*(?:n(?:[.º°o]|[uú]mero)?\s*)?
        \d+(?:\.\d{{3}})*(?:\s*/\s*\d{{2,4}})?
        (?:\s*,?\s+de\s+\d{{1,2}}\s+de\s+[a-zç]+\s+de\s+\d{{4}})?
        """,
        90,
    ),
    _compilar("processo_cnj", rf"\b{_NUMERO_CNJ}\b", 85),
    _compilar("referencia_incompleta", _REFERENCIA_INCOMPLETA, 105),
)


def _aparar(texto: str, inicio: int, fim: int) -> tuple[int, int]:
    """Remove apenas espacos e pontuacao terminal que nao pertencem ao span."""
    while inicio < fim and texto[inicio].isspace():
        inicio += 1
    while fim > inicio and (texto[fim - 1].isspace() or texto[fim - 1] in ",;:"):
        fim -= 1
    return inicio, fim


def _sobrepoe(a: _Candidato, b: _Candidato) -> bool:
    return a.inicio < b.fim and b.inicio < a.fim


def _eh_identificacao_processo(texto: str, inicio: int, fim: int) -> bool:
    """Reconhece uma linha inteira de metadados, sem corte por posicao."""
    inicio_linha = texto.rfind("\n", 0, inicio) + 1
    fim_linha = texto.find("\n", fim)
    if fim_linha == -1:
        fim_linha = len(texto)
    return _IDENTIFICACAO_PROCESSO.fullmatch(texto[inicio_linha:fim_linha]) is not None


def _selecionar_sem_sobreposicao(candidatos: Iterable[_Candidato]) -> list[_Candidato]:
    """Mantem o candidato mais especifico e, no empate, o span mais longo."""
    ordenados = sorted(
        candidatos,
        key=lambda c: (-c.prioridade, -c.tamanho, c.inicio, c.fim),
    )
    escolhidos: list[_Candidato] = []
    for candidato in ordenados:
        if not any(_sobrepoe(candidato, existente) for existente in escolhidos):
            escolhidos.append(candidato)
    return sorted(escolhidos, key=lambda c: (c.inicio, c.fim))


def identificar_citacoes(texto: str, documento_id: str) -> list[dict[str, object]]:
    """Identifica citacoes e devolve documento, inicio, fim e trecho.

    ``inicio`` e baseado em zero; ``fim`` e exclusivo. O texto nunca e
    normalizado antes da extracao, portanto os offsets sempre apontam para o
    documento original.
    """
    if not isinstance(texto, str):
        raise TypeError("texto deve ser uma string")
    if not documento_id:
        raise ValueError("documento_id nao pode ser vazio")

    candidatos: set[_Candidato] = set()
    for padrao in _PADROES:
        for correspondencia in padrao.expressao.finditer(texto):
            if padrao.tipo == "processo_cnj" and _eh_identificacao_processo(
                texto, *correspondencia.span()
            ):
                continue
            inicio, fim = _aparar(texto, *correspondencia.span())
            if inicio < fim:
                candidatos.add(_Candidato(inicio, fim, padrao.tipo, padrao.prioridade))

    selecionados = _selecionar_sem_sobreposicao(candidatos)
    return [
        {
            "documento_id": documento_id,
            "inicio": citacao.inicio,
            "fim": citacao.fim,
            "trecho": texto[citacao.inicio : citacao.fim],
        }
        for citacao in selecionados
    ]


def identificar_citacoes_em_diretorio(diretorio: str | Path) -> list[dict[str, object]]:
    """Executa a deteccao em todos os arquivos ``.txt`` do diretorio."""
    raiz = Path(diretorio)
    if not raiz.is_dir():
        raise FileNotFoundError(f"diretorio de entrada nao encontrado: {raiz}")

    arquivos = sorted(p for p in raiz.rglob("*.txt") if p.is_file())
    if not arquivos:
        raise FileNotFoundError(f"nenhum arquivo .txt encontrado em: {raiz}")

    linhas: list[dict[str, object]] = []
    for arquivo in arquivos:
        try:
            texto = arquivo.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnicodeError(f"{arquivo} nao esta em UTF-8") from exc
        linhas.extend(identificar_citacoes(texto, arquivo.stem))
    return linhas


def salvar_csv(linhas: Sequence[dict[str, object]], destino: str | Path) -> None:
    """Salva a tabela em CSV UTF-8, preservando quebras de linha nos trechos."""
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=("documento_id", "inicio", "fim", "trecho"),
            extrasaction="ignore",
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrai spans de citacoes juridicas dos documentos .txt."
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("dados_competicao") / "txt",
        help="diretorio dos .txt (padrao: dados_competicao/txt)",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("resultados") / "citacoes.csv",
        help="CSV de saida (padrao: resultados/citacoes.csv)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = _criar_parser().parse_args(argv)
    try:
        linhas = identificar_citacoes_em_diretorio(argumentos.entrada)
    except (FileNotFoundError, UnicodeError) as exc:
        raise SystemExit(str(exc)) from exc
    salvar_csv(linhas, argumentos.saida)
    print(f"{len(linhas)} citacoes salvas em {argumentos.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
