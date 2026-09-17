# Baseline de identificação de citações

O arquivo `extrair_citacoes.py` percorre os documentos `.txt`, identifica
referências jurídicas e gera uma tabela com:

| coluna | significado |
|---|---|
| `documento_id` | nome do arquivo sem a extensão `.txt` |
| `inicio` | posição inicial da citação, começando em zero |
| `fim` | posição imediatamente posterior ao último caractere |
| `trecho` | texto original entre `inicio` e `fim` |

Para toda linha, vale `trecho == texto[inicio:fim]`. O texto não é normalizado
antes da extração, portanto espaços e quebras de linha não invalidam os offsets.

## Execução

Os arquivos oficiais foram baixados para `dados_competicao/`. Para reproduzir a
tabela entregue, execute:

```powershell
python extrair_citacoes.py --entrada dados_competicao\txt --saida resultados\citacoes.csv
```

Também é possível usar a função diretamente:

```python
from extrair_citacoes import identificar_citacoes

linhas = identificar_citacoes(texto, documento_id="doc_0001")
```

O baseline reconhece números CNJ, classes processuais e seus números, súmulas,
temas, artigos, normas e referências incompletas formadas por tribunal, ano e
relator. Frases genéricas de fundamentação, sem uma referência concreta, não são
marcadas.

Na amostra aberta, o detector encontra as 192 citações do
`goldenset_offsets.csv`, sem falsos positivos ou falsos negativos no limiar de IoU
da métrica oficial. Os 192 pares de offsets também coincidem exatamente com o
gabarito. Essa aferição é sobre o conjunto de desenvolvimento aberto; o conjunto
final privado pode conter novas variações.

O golden representa quebras de linha dentro da coluna `trecho` como os caracteres
`\n`. Já `resultados/citacoes.csv` preserva as quebras reais dos documentos,
mantendo a invariante `trecho == texto[inicio:fim]`.

## Testes

```powershell
python -m unittest -v
```

O contrato oficial confirma offsets baseados em zero e `fim` exclusivo.
