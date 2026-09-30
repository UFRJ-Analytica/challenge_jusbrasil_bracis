# Ambiente declarado da solução.
#
# A solução usa apenas a biblioteca padrão do Python (regex + sqlite3), sem
# dependências externas, sem modelos e sem pesos. A imagem é, portanto, uma
# base Python enxuta; os dados da competição (.db e .txt) ficam de fora e são
# montados em tempo de execução.
FROM python:3.11-slim

WORKDIR /app

# Cópia do código da solução (os dados são excluídos pelo .dockerignore).
COPY . /app

# Ponto de entrada único: recebe <caminho_db> <pasta_txt> <arquivo_saida>.
ENTRYPOINT ["bash", "run.sh"]
