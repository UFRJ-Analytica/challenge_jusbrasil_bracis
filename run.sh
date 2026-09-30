#!/usr/bin/env bash
# Ponto de entrada único da solução.
#
# Recebe a base canônica (.db) e a pasta de pareceres (.txt) e gera a
# submissão no formato oficial: CSV com cabeçalho `documento_id,citacoes`,
# uma linha por documento, citações separadas por "|" no formato
# `inicio,fim,classe,id_canonico,confianca`.
#
# Não depende de internet nem de APIs externas: o pipeline (detecção ->
# classificação/vínculo -> transporte) usa apenas a biblioteca padrão.
#
# Antes de executar, valida todas as entradas e avisa o que estiver faltando,
# sem criar nenhum arquivo nem diretório. Só roda se tudo estiver no lugar.
#
# Uso:  bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>
set -euo pipefail

uso() {
    echo "Uso: $0 <caminho_db> <pasta_txt> <arquivo_saida>" >&2
    echo "  caminho_db     base canônica SQLite no formato original do desafio" >&2
    echo "  pasta_txt      diretório com os pareceres .txt" >&2
    echo "  arquivo_saida  CSV de submissão (documento_id,citacoes)" >&2
}

[ "$#" -ge 3 ] || { uso; exit 2; }

DB="$1"
TXT="$2"
SAIDA="$3"

# Diretório deste script — funciona de qualquer cwd e de dentro do container.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Validação: confere tudo o que é preciso ANTES de criar qualquer coisa.
# ---------------------------------------------------------------------------
problemas=()

# 1) base canônica: precisa existir, ser um arquivo e ser legível.
if [ -f "$DB" ] && [ -r "$DB" ]; then
    :
else
    problemas+=("  - base canônica não encontrada ou ilegível: $DB")
fi

# 2) pasta de pareceres: precisa existir e conter ao menos um .txt.
if [ -d "$TXT" ]; then
    if [ -z "$(find "$TXT" -type f -name '*.txt' -print -quit)" ]; then
        problemas+=("  - pasta de pareceres sem nenhum arquivo .txt: $TXT")
    fi
else
    problemas+=("  - pasta de pareceres não encontrada: $TXT")
fi

# 3) pasta de saída: precisa já existir (não é criada) e ser gravável.
PASTA_SAIDA="$(dirname "$SAIDA")"
if [ -d "$PASTA_SAIDA" ]; then
    if [ ! -w "$PASTA_SAIDA" ]; then
        problemas+=("  - pasta de saída sem permissão de escrita: $PASTA_SAIDA")
    fi
else
    problemas+=("  - pasta de saída não encontrada: $PASTA_SAIDA")
fi

# Se algo faltou, avisa o que é e encerra sem executar nem criar nada.
if [ "${#problemas[@]}" -gt 0 ]; then
    echo "Não vou executar — está faltando:" >&2
    printf '%s\n' "${problemas[@]}" >&2
    echo >&2
    echo "Esperado: bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>" >&2
    echo "  - <caminho_db>    : arquivo SQLite existente e legível" >&2
    echo "  - <pasta_txt>     : diretório existente com ao menos um .txt" >&2
    echo "  - <arquivo_saida> : caminho cuja pasta já existe (não é criada)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 "$DIR/extrair_citacoes.py" \
    --entrada "$TXT" --saida "$TMP/citacoes.csv"

python3 "$DIR/resolver_citacoes.py" \
    --entrada "$TMP/citacoes.csv" --saida "$TMP/json" --db "$DB"

python3 "$DIR/desafio-jusbrasil-bracis-2026/json_to_submission.py" \
    "$TMP/json" "$SAIDA"

echo "Submissão gerada em: $SAIDA"
