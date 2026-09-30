# -*- coding: utf-8 -*-
"""Avaliação local com a métrica oficial (kaggle_metric.py).

Reproduz o score da competição a partir de ``goldenset_offsets.csv`` e do
``submission.csv``, sem depender do Kaggle. É o único ponto do repositório que
precisa de pandas/numpy (a métrica dos organizadores é escrita neles).

Uso:
    python avaliar_submissao.py [submission.csv] [--dados desafio-jusbrasil-bracis-2026]
    python avaliar_submissao.py --minimo 1.0     # falha se o score ficar abaixo

Contrato da métrica lembrado aqui: a solução e a submissão têm UMA linha por
documento, com a célula ``citacoes`` no formato ``inicio,fim,classe,id_canonico,confianca``
separada por ``|``.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, OrderedDict
from pathlib import Path

DIRETORIOS_DADOS = ("desafio-jusbrasil-bracis-2026", "dados_competicao")


def encontrar_dados(base: Path | None = None) -> Path:
    raiz = base or Path(__file__).resolve().parent
    for nome in DIRETORIOS_DADOS:
        pasta = raiz / nome
        if (pasta / "goldenset_offsets.csv").is_file():
            return pasta
    raise SystemExit(
        "goldenset_offsets.csv não encontrado; informe --dados com o pacote da competição"
    )


def carregar_metricas(dados: Path):
    if not (dados / "kaggle_metric.py").is_file():
        raise SystemExit(
            f"kaggle_metric.py não encontrado em {dados}: ele vem no pacote de "
            "dados da competição, que não é versionado neste repositório"
        )
    sys.path.insert(0, str(dados))
    import kaggle_metric  # noqa: E402  (depende do sys.path acima)
    return kaggle_metric


def montar_solution(golden: list[dict]):
    """goldenset_offsets.csv -> DataFrame da solução (1 linha por documento)."""
    import pandas as pd

    celulas: "OrderedDict[str, list[str]]" = OrderedDict()
    niveis: dict[str, int] = {}
    for linha in golden:
        documento = linha["documento_id"]
        id_canonico = (linha.get("id_canonico") or "").strip() or "-"
        celulas.setdefault(documento, []).append(
            f"{linha['inicio']},{linha['fim']},{linha['classificacao']},{id_canonico}"
        )
        niveis[documento] = int(linha["nivel"])
    return pd.DataFrame(
        [
            {"documento_id": documento, "nivel": niveis[documento], "citacoes": "|".join(partes)}
            for documento, partes in celulas.items()
        ]
    )


def relatar_erros(km, golden: list[dict], submission) -> None:
    """Lista as divergências de classe/vínculo nos pares casados."""
    por_documento: dict[str, list[dict]] = {}
    for linha in golden:
        por_documento.setdefault(linha["documento_id"], []).append(linha)

    predicoes = {
        linha["documento_id"]: km._parse_submission_cell(linha["citacoes"], linha["documento_id"])
        for _, linha in submission.iterrows()
    }

    confusao: Counter = Counter()
    erros: list[tuple] = []
    for documento, linhas in por_documento.items():
        celula = "|".join(
            f"{r['inicio']},{r['fim']},{r['classificacao']},{(r.get('id_canonico') or '').strip() or '-'}"
            for r in linhas
        )
        gabaritos = km._parse_solution_cell(celula, documento)
        pares, sem_par_gold, sem_par_pred = km._casar(gabaritos, predicoes.get(documento, []))
        for indice_g, indice_p in pares:
            esperado, obtido = gabaritos[indice_g], predicoes[documento][indice_p]
            confusao[(esperado["classe"], obtido["classe"])] += 1
            if esperado["classe"] != obtido["classe"] or (
                esperado["classe"] == "real" and obtido["id_canonico"] not in esperado["doc_ids"]
            ):
                erros.append(
                    (documento, esperado["classe"], obtido["classe"],
                     sorted(esperado["doc_ids"])[0] if esperado["doc_ids"] else "-",
                     obtido["id_canonico"])
                )
        for indice in sem_par_gold:
            confusao[(gabaritos[indice]["classe"], "NAO-EXTRAIDA")] += 1
        for indice in sem_par_pred:
            confusao[("EXTRA-ESPURIA", predicoes[documento][indice]["classe"])] += 1

    print("\nmatriz de confusão (esperado, obtido):")
    for (esperado, obtido), quantidade in sorted(confusao.items()):
        print(f"  {esperado:>15s} -> {obtido:<15s} {quantidade:>5d}")
    print(f"\ndivergências: {len(erros)}")
    for documento, esperado, obtido, id_esperado, id_obtido in erros:
        print(f"  {documento}: {esperado} -> {obtido} (id esperado {id_esperado}, obtido {id_obtido})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score local pela métrica oficial do desafio.")
    parser.add_argument("submissao", nargs="?", default="submission.csv", help="CSV de submissão")
    parser.add_argument("--dados", type=Path, default=None, help="pacote da competição")
    parser.add_argument("--minimo", type=float, default=None, help="falha se o score for menor que este valor")
    parser.add_argument("--sem-erros", action="store_true", help="não detalhar as divergências")
    args = parser.parse_args()

    dados = encontrar_dados(args.dados)
    km = carregar_metricas(dados)
    import pandas as pd

    caminho_submissao = Path(args.submissao)
    if not caminho_submissao.is_file():
        raise SystemExit(f"submissão não encontrada: {caminho_submissao}")

    with (dados / "goldenset_offsets.csv").open(encoding="utf-8-sig", newline="") as arquivo:
        golden = list(csv.DictReader(arquivo))

    solution = montar_solution(golden)
    submission = pd.read_csv(caminho_submissao, dtype=str, keep_default_na=False)

    faltando = set(solution["documento_id"]) - set(submission["documento_id"])
    if faltando:
        raise SystemExit(
            f"submissão sem linha para {len(faltando)} documento(s), ex.: {sorted(faltando)[:3]}"
        )

    resultado = km.avaliar(solution, submission)

    print(f"submissão : {caminho_submissao} ({len(submission)} documentos)")
    print(f"gabarito  : {dados / 'goldenset_offsets.csv'} ({len(golden)} citações)")
    for nivel, detalhe in sorted(resultado["niveis"].items()):
        f1s = ", ".join(f"{classe}={valor:.4f}" for classe, valor in sorted(detalhe["f1_por_classe"].items()))
        print(
            f"\nnível {nivel}: macro-F1={detalhe['macro_f1']:.4f} | τ={detalhe['tau']:.4f} | "
            f"s={detalhe['s']:.4f} | bônus={detalhe['b']:.4f} | score={detalhe['score']:.4f}"
        )
        print(f"  F1 por classe: {f1s}")
    print(f"\nSCORE FINAL: {resultado['score_final']:.4f}")

    if not args.sem_erros:
        relatar_erros(km, golden, submission)

    if args.minimo is not None and resultado["score_final"] < args.minimo:
        print(f"\nFALHA: score {resultado['score_final']:.4f} < mínimo {args.minimo:.4f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    raise SystemExit(main())
