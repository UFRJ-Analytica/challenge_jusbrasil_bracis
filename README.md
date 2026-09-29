# Caça-Alucinações — BRACIS 2026 × Jusbrasil

Solução completa do desafio: encontrar as citações jurídicas de cada parecer,
decidir se cada uma é **real**, **inventada** ou **incompleta** e, quando for
real, apontar o `id_canonico` do documento na base canônica.

## O que a competição pontua

| Item | Regra |
|---|---|
| Casamento | IoU ≥ 0,5 entre o span previsto e o do gabarito, guloso 1-para-1 por maior IoU |
| Classes | `real` (exige `id_canonico` ∈ `doc_ids` do gabarito), `inventada`, `incompleta` |
| Níveis | nível 1 (formato padrão) peso **1x**; nível 2 (ruído e variação) peso **2x** |
| Score | `s = macroF1 · (1 − 0,5·τ)`, τ = fração das `inventada` preditas `real` (erro grave) |
| Bônus | `b = 0,10 · (1 − Brier)` sobre os pares casados; `score = s · (1 + b)` |
| Final | `(1·score_N1 + 2·score_N2) / 3` |

Predição sem par que seja **componente** de uma citação do gabarito já casada é
ignorada (§6 EXTRA), o que tolera sub-spans mas não extração espúria.

## Pipeline

Três etapas em cascata, todas em **biblioteca padrão** (nenhuma dependência
externa), mais duas ferramentas de apoio:

```bash
# 1. detecção dos spans            -> resultados/citacoes.csv
python3 extrair_citacoes.py --saida resultados/citacoes.csv

# 2. classificação e vínculo       -> resultados/json/<documento_id>.json
python3 resolver_citacoes.py --entrada resultados/citacoes.csv --saida resultados/json

# 3. transporte CSV do Kaggle      -> submission.csv
python3 desafio-jusbrasil-bracis-2026/json_to_submission.py resultados/json submission.csv

# 4. validação do contrato v1.2 (rode antes de submeter)
python3 validar_json_submissao.py resultados/json

# 5. score local pela métrica oficial
python3 avaliar_submissao.py submission.csv --minimo 1.0
```

Os caminhos do pacote de dados (`desafio-jusbrasil-bracis-2026/`, com `txt/`,
`goldenset_offsets.csv` e `desafio1_bracis.db`) são detectados automaticamente;
`dados_competicao/` continua aceito como alternativa, e `--entrada` / `--db` /
`--dados` sobrepõem a detecção.

### 1. `extrair_citacoes.py` — detecção

Regexes com prioridade, aplicadas sobre o texto original (nunca normalizado),
para preservar a invariante `trecho == texto[inicio:fim]`: números CNJ, classe
processual + número, súmulas, temas, artigos e normas, e referências incompletas
(tribunal + ano + relator). O span mais específico vence quando há sobreposição,
e linhas de identificação de processo no cabeçalho são descartadas.

Colunas geradas: `documento_id` (nome do arquivo sem `.txt`), `inicio`
(baseado em zero), `fim` (exclusivo) e `trecho`.

### 2. `resolver_citacoes.py` — classificação e vínculo

Monta os índices da base canônica (`desafio1_bracis.db`): número → documentos,
chaves de artigo/norma dos dispositivos e as súmulas. A decisão segue, em
ordem: referência incompleta por template → súmula → artigo + norma
(`law_keys`) → número processual no índice numérico:

* nenhum candidato no índice → `inventada`;
* candidato único e coerente (número no cabeçalho, tribunal, UF, classe e ano,
  pontuados por `score_candidate`) → `real` com o `doc_id`;
* ano isolado ou empate entre candidatos → `incompleta`.

`flatten()` colapsa tanto a quebra de linha **real** do documento quanto a
forma escapada `\n` que aparece no gabarito. Sem isso, toda citação que cruzava
linha perdia a normalização e caía indevidamente em `incompleta`.

### 3. `desafio-jusbrasil-bracis-2026/json_to_submission.py` — transporte

Converte um JSON por parecer na célula exigida pelo Kaggle:
`inicio,fim,classe,id_canonico,confianca`, separadas por `|`, uma linha por
documento. Campos ausentes viram `-` (o Kaggle rejeita célula vazia).

### 4 e 5. Ferramentas de apoio

`validar_json_submissao.py` aplica as mesmas regras que a métrica usa na célula
(schema `1.2`, `id` único, `0 <= inicio < fim`, `classificacao` válida, `real`
exigindo `id_canonico` só com dígitos, `confianca` em [0, 1] quando presente,
ausência de duplicata com IoU ≥ 0,5) e confere `trecho == texto[inicio:fim]`
contra o `.txt` original. Sai com código 1 se houver erro.

`avaliar_submissao.py` reproduz o score da competição fora do Kaggle, a partir
do `kaggle_metric.py` dos organizadores, detalhando F1 por classe, τ, bônus e as
divergências de classe/vínculo.

## Contrato JSON v1.2

```json
{
  "schema_version": "1.2",
  "documento_id": "gen_n2_002",
  "citacoes": [
    {
      "id": "c1",
      "inicio": 1225,
      "fim": 1242,
      "trecho": "REsp 1.234.567/SP",
      "tipo": "jurisprudencia",
      "classificacao": "real",
      "resolucao": { "fonte": "jusbrasil", "id_canonico": "1289710776" }
    }
  ]
}
```

`resolucao` é `null` quando a classificação não é `real`. O campo `confianca` é
opcional e **não é emitido** por esta solução: o bônus de calibração (Brier) não
é reivindicado, e o `json_to_submission.py` escreve `-` nessa posição.

## Resultado na amostra aberta

| Métrica | Valor |
|---|---|
| Spans (offsets exatos vs. gabarito) | **192/192**, sem falso positivo |
| macro-F1 nível 1 | **1,0000** (real, inventada e incompleta = 1,0000) |
| macro-F1 nível 2 | **1,0000** (real, inventada e incompleta = 1,0000) |
| τ (erro grave) | 0,0000 |
| Bônus Brier | 0,0000 (não reivindicado) |
| **Score final** | **1,0000** |

Reproduza com `avaliar_submissao.py submission.csv --minimo 1.0` (precisa de
`pandas`/`numpy`; as etapas 1 a 3 não).

## Testes

```bash
python3 -m unittest -v
```

43 testes, sem skips quando o pacote de dados está presente:

* `test_extrair_citacoes.py` — detecção, offsets, filtro de metadados e a
  regressão de spans contra o gabarito;
* `test_generalizacao.py` — frases sintéticas: variações de caixa, espaços e
  quebras de linha, famílias distintas de citação e falsos positivos;
* `test_resolver_citacoes.py` — classificação e vínculo contra o gabarito,
  número ausente da base → `inventada` (proteção do τ), desempate entre
  candidatos, quebra de linha real vs. escapada, tolerância a erro de OCR em
  nomes de norma, teto do `expand_ocr` e conformidade do JSON com o contrato v1.2.

## Dependências

O pipeline (etapas 1 a 3) usa **apenas a biblioteca padrão**. O
`requirements.txt` lista `pandas` e `numpy`, necessários somente para
`avaliar_submissao.py` e para o `kaggle_metric.py` oficial.

## Limitações conhecidas

* **Sem `confianca`**: a solução abre mão de até `0,10 · score` do bônus Brier.
  Como o bônus é multiplicativo, uma solução com F1 um pouco menor e confiança
  bem calibrada pode ultrapassar esta.
* **Detecção por enumeração**: as famílias de template (referência incompleta,
  abreviações de classe) e a tabela de normas são finitas. Nomes longos de norma
  toleram erro de digitação por similaridade; siglas curtas não, porque vínculo
  errado custa mais que vínculo ausente. Forma de superfície nova, fora das
  famílias, cai em `incompleta`.
* **Caixa na referência incompleta**: o nome do relator exige inicial maiúscula;
  texto todo em minúsculas não produz esse span.
* **UF**: a extração aceita qualquer par de letras maiúsculas; a conferência
  contra a lista real de UFs acontece só no `score_candidate`.
* **Lógica de desempate**: na amostra aberta quase toda citação `real` resolve
  por número único, então os pesos de desempate decidem poucos casos, e a
  sub-família de `incompleta` por ambiguidade real tem cobertura pequena.
* `expand_ocr` limita a 512 variantes por token (truncagem ordenada e
  determinística).

O gabarito representa quebras de linha dentro de `trecho` como os caracteres
`\n`; `resultados/citacoes.csv` preserva as quebras reais dos documentos,
mantendo a invariante `trecho == texto[inicio:fim]`. O contrato oficial confirma
offsets baseados em zero e `fim` exclusivo.
