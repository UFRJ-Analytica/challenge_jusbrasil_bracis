# -*- coding: utf-8 -*-
"""Validador do Contrato de Entrada e Saída v1.2 (JSON por parecer).

O site do desafio pede para rodar o validador de formato antes de submeter.
Este é o validador do contrato, com as mesmas regras que a métrica oficial
aplica na célula CSV:

  · ``schema_version`` == "1.2", ``documento_id`` e ``citacoes`` presentes;
  · cada citação com ``id`` único, ``inicio``/``fim`` inteiros, ``0 <= inicio < fim``;
  · ``classificacao`` em real | inventada | incompleta;
  · ``classificacao == "real"`` exige ``resolucao.id_canonico`` só com dígitos;
  · ``resolucao`` ausente/nula quando a classificação não é ``real``;
  · ``confianca`` opcional, mas em [0, 1] quando presente;
  · nada de duas citações do mesmo documento com IoU >= 0.5 (duplicata);
  · ``trecho`` igual a ``texto[inicio:fim]`` quando o .txt do parecer existir.

Uso:  python validar_json_submissao.py <pasta_json> [--dados desafio-jusbrasil-bracis-2026]
Saída: erros em stderr (exit 1) e avisos em stdout (exit 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLASSES = ("real", "inventada", "incompleta")
TIPOS = ("jurisprudencia", "lei")
IOU_MIN = 0.5
SCHEMA = "1.2"
DIRETORIOS_DADOS = ("desafio-jusbrasil-bracis-2026", "dados_competicao")


def _iou(a: dict, b: dict) -> float:
    inicio = max(a["inicio"], b["inicio"])
    fim = min(a["fim"], b["fim"])
    intersecao = max(0, fim - inicio)
    uniao = (a["fim"] - a["inicio"]) + (b["fim"] - b["inicio"]) - intersecao
    return intersecao / uniao if uniao > 0 else 0.0


def validar_documento(doc: dict, texto: str | None = None, origem: str = "?") -> tuple[list[str], list[str]]:
    """Devolve (erros, avisos) do documento, sem levantar exceção."""
    erros: list[str] = []
    avisos: list[str] = []

    if not isinstance(doc, dict):
        return [f"[{origem}] o JSON não é um objeto"], []
    if doc.get("schema_version") != SCHEMA:
        erros.append(f"[{origem}] schema_version deve ser {SCHEMA!r}; recebido {doc.get('schema_version')!r}")
    if not str(doc.get("documento_id") or "").strip():
        erros.append(f"[{origem}] documento_id ausente ou vazio")

    citacoes = doc.get("citacoes")
    if not isinstance(citacoes, list):
        return erros + [f"[{origem}] citacoes deve ser uma lista"], avisos

    for indice, citacao in enumerate(citacoes, start=1):
        onde = f"[{origem}] citação #{indice}"
        if not isinstance(citacao, dict):
            erros.append(f"{onde}: deve ser um objeto")
            continue

        if not str(citacao.get("id") or "").strip():
            erros.append(f"{onde}: id ausente")

        inicio, fim = citacao.get("inicio"), citacao.get("fim")
        if not isinstance(inicio, int) or not isinstance(fim, int) or isinstance(inicio, bool) or isinstance(fim, bool):
            erros.append(f"{onde}: inicio/fim devem ser inteiros; recebidos {inicio!r}/{fim!r}")
            continue
        if inicio < 0 or fim <= inicio:
            erros.append(f"{onde}: span inválido ({inicio}, {fim}) — exige 0 <= inicio < fim")

        classe = citacao.get("classificacao")
        if classe not in CLASSES:
            erros.append(f"{onde}: classificacao {classe!r} inválida; use real | inventada | incompleta")

        if citacao.get("tipo") not in TIPOS:
            avisos.append(f"{onde}: tipo {citacao.get('tipo')!r} fora de {TIPOS}")

        resolucao = citacao.get("resolucao")
        if classe == "real":
            if not isinstance(resolucao, dict):
                erros.append(f"{onde}: classificacao=real exige resolucao com id_canonico")
            else:
                if resolucao.get("fonte") != "jusbrasil":
                    erros.append(f"{onde}: resolucao.fonte deve ser 'jusbrasil'; recebido {resolucao.get('fonte')!r}")
                id_canonico = str(resolucao.get("id_canonico") or "")
                if not id_canonico.isdigit():
                    erros.append(f"{onde}: id_canonico deve conter só dígitos; recebido {id_canonico!r}")
        elif resolucao not in (None, {}):
            erros.append(f"{onde}: resolucao deve ser nula quando a classificação não é 'real'")

        if "confianca" in citacao:
            confianca = citacao["confianca"]
            if not isinstance(confianca, (int, float)) or isinstance(confianca, bool) or not (0.0 <= float(confianca) <= 1.0):
                erros.append(f"{onde}: confianca deve ser número em [0, 1]; recebido {confianca!r}")

        trecho = citacao.get("trecho")
        if not isinstance(trecho, str):
            erros.append(f"{onde}: trecho deve ser texto")
        elif texto is not None and isinstance(inicio, int) and isinstance(fim, int) and not isinstance(inicio, bool) and not isinstance(fim, bool):
            if 0 <= inicio < fim <= len(texto) and trecho != texto[inicio:fim]:
                erros.append(
                    f"{onde}: trecho diferente de texto[inicio:fim] "
                    f"({trecho!r} != {texto[inicio:fim]!r})"
                )

    for a in range(len(citacoes)):
        for b in range(a + 1, len(citacoes)):
            if not isinstance(citacoes[a], dict) or not isinstance(citacoes[b], dict):
                continue
            if isinstance(citacoes[a].get("inicio"), int) and isinstance(citacoes[b].get("inicio"), int):
                if _iou(citacoes[a], citacoes[b]) >= IOU_MIN:
                    erros.append(
                        f"[{origem}] citações #{a + 1} e #{b + 1} se sobrepõem com IoU >= {IOU_MIN} (duplicata)"
                    )

    return erros, avisos


def encontrar_dados(base: Path | None = None) -> tuple[Path | None, Path | None]:
    raiz = base or Path(__file__).resolve().parent
    for nome in DIRETORIOS_DADOS:
        pasta = raiz / nome
        if pasta.is_dir():
            return pasta, pasta / "txt"
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida os JSONs contra o contrato v1.2.")
    parser.add_argument("pasta", type=Path, help="pasta com um .json por parecer")
    parser.add_argument("--dados", type=Path, default=None, help="pacote de dados (para conferir o trecho)")
    args = parser.parse_args()

    if not args.pasta.is_dir():
        print(f"erro: {args.pasta} não é um diretório", file=sys.stderr)
        return 2

    arquivos = sorted(args.pasta.glob("*.json"))
    if not arquivos:
        print(f"erro: nenhum .json em {args.pasta}", file=sys.stderr)
        return 2

    _, textos = encontrar_dados(args.dados)
    if textos is None or not textos.is_dir():
        print("aviso: .txt dos pareceres não encontrado; a conferência de trecho foi pulada")
        textos = None
    erros: list[str] = []
    avisos: list[str] = []
    vistos: dict[str, str] = {}

    for arquivo in arquivos:
        try:
            doc = json.loads(arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            erros.append(f"[{arquivo.name}] JSON inválido: {exc}")
            continue

        origem = arquivo.stem
        texto = None
        if textos is not None:
            candidato = textos / f"{origem}.txt"
            if candidato.is_file():
                texto = candidato.read_text(encoding="utf-8-sig")

        documento_erros, documento_avisos = validar_documento(doc, texto, origem)
        erros.extend(documento_erros)
        avisos.extend(documento_avisos)

        nome_doc = str(doc.get("documento_id") or origem)
        if nome_doc in vistos:
            erros.append(f"[{origem}] documento_id {nome_doc!r} repetido (também em {vistos[nome_doc]})")
        vistos[nome_doc] = arquivo.name

        if isinstance(doc.get("citacoes"), list):
            ids = [c.get("id") for c in doc["citacoes"] if isinstance(c, dict)]
            repetidos = {i for i in ids if ids.count(i) > 1}
            for repetido in sorted(repetidos, key=str):
                erros.append(f"[{origem}] id de citação repetido: {repetido!r}")

    for aviso in avisos:
        print(f"aviso: {aviso}")
    for erro in erros:
        print(f"erro: {erro}", file=sys.stderr)

    print(f"{len(arquivos)} arquivo(s) validado(s), {len(erros)} erro(s), {len(avisos)} aviso(s)")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
