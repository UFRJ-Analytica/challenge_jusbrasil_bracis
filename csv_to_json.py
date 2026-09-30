# -*- coding: utf-8 -*-
"""Conversor: CSV no formato padrão -> JSONs do Contrato de Entrada e Saída v1.2.

Lê um CSV com **uma citação por linha** e gera um JSON por documento no schema
acordado (``schema_version: "1.2"``). É o inverso do ``json_to_submission.py``
(que faz JSON -> CSV de submissão).

Formato do CSV (cabeçalho; a ordem das colunas é livre):

    documento_id, inicio, fim, trecho, tipo, classificacao, id_canonico, confianca

  * documento_id  — identificador do parecer (o JSON sai como <documento_id>.json)
  * inicio, fim   — offsets inteiros, base zero, ``fim`` exclusivo
  * trecho        — texto exato da citação (``trecho == texto[inicio:fim]``)
  * tipo          — "jurisprudencia" ou "lei" (opcional; padrão "jurisprudencia")
  * classificacao — "real", "inventada" ou "incompleta"
  * id_canonico   — id canônico (obrigatório quando ``classificacao == "real"``;
                    ignorado nas demais)
  * confianca     — opcional, float em [0, 1]; ausente se a coluna estiver vazia

O JSON gerado segue as mesmas regras conferidas pelo ``validar_json_submissao.py``
(``id`` único por documento, ``0 <= inicio < fim``, ``real`` exigindo
``id_canonico`` só com dígitos, ``confianca`` em [0, 1], ``resolucao`` nula para
não-``real``).

Uso:
    python3 csv_to_json.py <arquivo_csv> [pasta_saida]

Exemplo:
    python3 csv_to_json.py citacoes.csv resultados/json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

CLASSIFICACOES = {"real", "inventada", "incompleta"}
TIPOS = {"jurisprudencia", "lei"}
FONTE = "jusbrasil"


def _ler_citacoes(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))

    if not linhas:
        raise SystemExit(f"nenhuma linha de dados em {caminho}")

    obrigatorias = {"documento_id", "inicio", "fim", "trecho", "classificacao"}
    faltando = obrigatorias - set(linhas[0].keys())
    if faltando:
        raise SystemExit(
            "colunas obrigatórias ausentes no CSV: " + ", ".join(sorted(faltando))
            + " (esperado: documento_id, inicio, fim, trecho, tipo, "
              "classificacao, id_canonico, confianca)"
        )

    citacoes: list[dict] = []
    for numero, linha in enumerate(linhas, start=2):  # linha 1 é o cabeçalho
        documento_id = (linha.get("documento_id") or "").strip()
        if not documento_id:
            raise SystemExit(f"linha {numero}: documento_id vazio")

        try:
            inicio = int((linha.get("inicio") or "").strip())
            fim = int((linha.get("fim") or "").strip())
        except ValueError:
            raise SystemExit(f"linha {numero}: inicio/fim não são inteiros")

        if not (0 <= inicio < fim):
            raise SystemExit(f"linha {numero}: esperado 0 <= inicio < fim")

        trecho = linha.get("trecho") or ""

        tipo = (linha.get("tipo") or "").strip().lower() or "jurisprudencia"
        if tipo not in TIPOS:
            raise SystemExit(f"linha {numero}: tipo inválido {tipo!r}")

        classificacao = (linha.get("classificacao") or "").strip().lower()
        if classificacao not in CLASSIFICACOES:
            raise SystemExit(
                f"linha {numero}: classificacao inválida {classificacao!r}"
            )

        id_canonico = (linha.get("id_canonico") or "").strip()
        if classificacao == "real":
            if not id_canonico or not id_canonico.isdigit():
                raise SystemExit(
                    f"linha {numero}: classificacao 'real' exige id_canonico "
                    "apenas com dígitos"
                )
        else:
            id_canonico = ""

        confianca_s = (linha.get("confianca") or "").strip()
        confianca = None
        if confianca_s:
            try:
                confianca = float(confianca_s)
            except ValueError:
                raise SystemExit(f"linha {numero}: confianca não é número")
            if not (0.0 <= confianca <= 1.0):
                raise SystemExit(f"linha {numero}: confianca fora de [0, 1]")

        citacoes.append(
            {
                "documento_id": documento_id,
                "inicio": inicio,
                "fim": fim,
                "trecho": trecho,
                "tipo": tipo,
                "classificacao": classificacao,
                "id_canonico": id_canonico,
                "confianca": confianca,
            }
        )

    return citacoes


def _agrupar(citacoes: list[dict]) -> dict[str, list[dict]]:
    agrupado: dict[str, list[dict]] = defaultdict(list)
    for citacao in citacoes:
        agrupado[citacao["documento_id"]].append(citacao)
    # Ordem determinística: por offset dentro de cada documento.
    for documento_id in agrupado:
        agrupado[documento_id].sort(key=lambda c: (c["inicio"], c["fim"]))
    return dict(agrupado)


def _montar(documento_id: str, citacoes: list[dict]) -> dict:
    itens = []
    for indice, citacao in enumerate(citacoes, start=1):
        resolucao = (
            {"fonte": FONTE, "id_canonico": citacao["id_canonico"]}
            if citacao["classificacao"] == "real"
            else None
        )
        item = {
            "id": f"c{indice}",
            "inicio": citacao["inicio"],
            "fim": citacao["fim"],
            "trecho": citacao["trecho"],
            "tipo": citacao["tipo"],
            "classificacao": citacao["classificacao"],
            "resolucao": resolucao,
        }
        if citacao["confianca"] is not None:
            item["confianca"] = citacao["confianca"]
        itens.append(item)

    return {
        "schema_version": "1.2",
        "documento_id": documento_id,
        "citacoes": itens,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Converte um CSV de citações no JSON do contrato v1.2."
    )
    parser.add_argument("arquivo_csv", type=Path, help="CSV no formato padrão")
    parser.add_argument(
        "pasta_saida",
        nargs="?",
        type=Path,
        default=Path("resultados") / "json",
        help="pasta de saída (padrão: resultados/json)",
    )
    args = parser.parse_args(argv)

    if not args.arquivo_csv.is_file():
        raise SystemExit(f"CSV não encontrado: {args.arquivo_csv}")

    citacoes = _ler_citacoes(args.arquivo_csv)
    agrupado = _agrupar(citacoes)

    args.pasta_saida.mkdir(parents=True, exist_ok=True)
    for documento_id, itens in agrupado.items():
        destino = args.pasta_saida / f"{documento_id}.json"
        destino.write_text(
            json.dumps(_montar(documento_id, itens), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"JSONs gerados: {len(agrupado)}")
    print(f"Pasta de saída: {args.pasta_saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
