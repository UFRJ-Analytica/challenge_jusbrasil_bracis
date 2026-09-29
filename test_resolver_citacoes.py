# -*- coding: utf-8 -*-
"""Testes do caminho de classificação — a parte que decide o score.

Cobre a regressão que faltava: ``trecho`` com quebra de linha real (vindo do
documento) precisa produzir a mesma decisão que a forma escapada (``\\n``) que
aparece no gabarito.
"""
import csv
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from extrair_citacoes import identificar_citacoes_em_diretorio
from resolver_citacoes import (
    Resolver,
    caminho_db_padrao,
    expand_ocr,
    flatten,
    law_source,
    raw_numeric_tokens,
)
from validar_json_submissao import validar_documento

DIRETORIOS_DADOS = ("desafio-jusbrasil-bracis-2026", "dados_competicao")


def _raiz_dados() -> Path | None:
    raiz = Path(__file__).resolve().parent
    for nome in DIRETORIOS_DADOS:
        pasta = raiz / nome
        if (pasta / "goldenset_offsets.csv").is_file() and caminho_db_padrao():
            return pasta
    return None


class FlattenTest(unittest.TestCase):
    def test_colapsa_quebra_real_e_escapada_do_mesmo_jeito(self):
        with self.subTest(caso="escapada do gabarito"):
            self.assertEqual(flatten("Código\\nde Processo\\nPenal"), "Código de Processo Penal")
        with self.subTest(caso="quebra real do documento"):
            self.assertEqual(flatten("Código\nde Processo\nPenal"), "Código de Processo Penal")
        with self.subTest(caso="espaços múltiplos e tabulação"):
            self.assertEqual(flatten("  Lei \t nº  8.078  "), " Lei nº 8.078 ")


class LawSourceTest(unittest.TestCase):
    def test_tolera_erro_de_ocr_em_nome_longo(self):
        self.assertEqual(law_source("artigo 7º, XXIX, da Constituição Fedcral"), ("cf", None))
        self.assertEqual(law_source("art. 5º da Constituição Federal"), ("cf", None))
        self.assertEqual(
            law_source("art. 5º da Constituição da República Federativa do Brasil"), ("cf", None)
        )

    def test_sigla_desconhecida_nao_casa_por_similaridade(self):
        # Sigla curta não participa da comparação aproximada: vínculo errado
        # custa mais caro que ausência de vínculo.
        self.assertIsNone(law_source("art. 9º do RICMS"))
        self.assertEqual(law_source("art. 1.143 da CLT"), ("law", "5452"))

    def test_lei_por_numero_continua_sendo_o_caminho_generico(self):
        self.assertEqual(law_source("art. 14 da Lei nº 8.078/1990"), ("law", "8078"))
        self.assertEqual(law_source("art. 3º da Lei Complementar nº 64/1990"), ("law", "64"))


class ExpandOcrTest(unittest.TestCase):
    def test_respeita_o_teto_e_e_deterministico(self):
        variantes = expand_ocr("g" * 12)
        self.assertLessEqual(len(variantes), 512)
        self.assertEqual(variantes, expand_ocr("g" * 12))
        self.assertTrue(all(set(variante) <= set("69") for variante in variantes))

    def test_confusoes_usuais(self):
        self.assertEqual(expand_ocr("1O1"), {"101"})
        self.assertEqual(expand_ocr("12g"), {"126", "129"})


class ClassificacaoGoldenTest(unittest.TestCase):
    """Regressão da amostra aberta: spans, classes e vínculos do gabarito."""

    raiz = None
    resolver = None
    golden: list[dict] = []
    linhas: list[dict] = []

    @classmethod
    def setUpClass(cls):
        cls.raiz = _raiz_dados()
        banco = caminho_db_padrao()
        if cls.raiz is None or banco is None:
            raise unittest.SkipTest("dados oficiais não estão disponíveis neste checkout")
        cls.resolver = Resolver(banco)
        with (cls.raiz / "goldenset_offsets.csv").open(encoding="utf-8-sig", newline="") as arquivo:
            cls.golden = list(csv.DictReader(arquivo))
        cls.linhas = identificar_citacoes_em_diretorio(cls.raiz / "txt")

    def _classificar(self, linha: dict) -> tuple[str, int | None]:
        trecho = linha["trecho"]
        return self.resolver.resolve(trecho, self.resolver.infer_type(trecho))

    def test_spans_do_detector_batem_com_o_gabarito(self):
        def chave(linha):
            return linha["documento_id"], int(linha["inicio"]), int(linha["fim"])

        self.assertEqual(
            Counter(map(chave, self.linhas)),
            Counter(map(chave, self.golden)),
        )

    def test_classificacao_e_vinculo_batem_com_o_gabarito(self):
        por_chave = {
            (linha["documento_id"], int(linha["inicio"]), int(linha["fim"])): linha
            for linha in self.linhas
        }
        divergencias = []
        for esperado in self.golden:
            chave = (esperado["documento_id"], int(esperado["inicio"]), int(esperado["fim"]))
            obtido = por_chave.get(chave)
            if obtido is None:
                divergencias.append((chave, "citação não extraída"))
                continue
            classe, id_canonico = self._classificar(obtido)
            id_esperado = (esperado.get("id_canonico") or "").strip() or None
            if classe != esperado["classificacao"] or (id_esperado and str(id_canonico) != id_esperado):
                divergencias.append(
                    (chave, f"{esperado['classificacao']}/{id_esperado} -> {classe}/{id_canonico}")
                )
        self.assertEqual(divergencias, [])

    def test_numero_ausente_da_base_e_inventada(self):
        """Protege o erro grave (τ): número inexistente nunca vira `real`.

        Altera um dígito de uma citação `real` do gabarito até o token sair do
        índice numérico — assim o teste funciona com qualquer base canônica.
        """
        for esperado in self.golden:
            if esperado["classificacao"] != "real":
                continue
            original = (esperado["trecho"] or "").replace("\\n", " ")
            if not any(ch.isdigit() for ch in original):
                continue
            for substituto in "0123456789":
                indice = next(i for i, ch in enumerate(original) if ch.isdigit())
                alterado = original[:indice] + substituto + original[indice + 1:]
                raw = raw_numeric_tokens(alterado)
                if not raw:
                    continue
                if any(variant in self.resolver.numeric_index for variant in expand_ocr(raw)):
                    continue
                classe, id_canonico = self.resolver.resolve(alterado, "jurisprudencia")
                self.assertEqual(classe, "inventada", f"{alterado!r} -> {classe}")
                self.assertIsNone(id_canonico)
                return
        self.skipTest("nenhuma citação de jurisprudência adequada no gabarito")

    def test_desempate_entre_candidatos_escolhe_o_documento_certo(self):
        """Exercita o caminho de desempate: número com mais de um candidato.

        Só faz sentido para jurisprudência — em citação de norma quem decide é
        ``law_keys``, não o ``score_candidate``.
        """
        for esperado in self.golden:
            if esperado["classificacao"] != "real":
                continue
            trecho = (esperado["trecho"] or "").replace("\\n", " ")
            tipo = self.resolver.infer_type(trecho)
            if tipo != "jurisprudencia":
                continue
            raw = raw_numeric_tokens(trecho)
            if not raw:
                continue
            candidatos: set[int] = set()
            for variant in expand_ocr(raw):
                candidatos.update(self.resolver.numeric_index.get(variant, set()))
            if len(candidatos) < 2:
                continue
            classe, id_canonico = self.resolver.resolve(trecho, tipo)
            self.assertEqual(classe, "real", f"{trecho!r} -> {classe} (candidatos: {len(candidatos)})")
            self.assertIn(str(id_canonico), esperado["id_canonico"].split(":"))
            return
        self.skipTest("nenhuma citação ambígua no gabarito aberto")

    def test_quebra_de_linha_real_nao_degrada_a_decisao(self):
        """O ``trecho`` do documento tem quebra real; o do gabarito, ``\\n``.

        Antes do ajuste de ``flatten``, toda citação que cruzava linha caía em
        ``incompleta`` — era exatamente o erro que sobrava na amostra aberta.
        """
        afetados = 0
        for esperado in self.golden:
            if "\\n" not in esperado["trecho"]:
                continue
            afetados += 1
            chave = (esperado["documento_id"], int(esperado["inicio"]), int(esperado["fim"]))
            linha = next(
                (
                    item
                    for item in self.linhas
                    if (item["documento_id"], int(item["inicio"]), int(item["fim"])) == chave
                ),
                None,
            )
            self.assertIsNotNone(linha, f"citação do gabarito não extraída: {chave}")
            self.assertIn("\n", linha["trecho"])
            classe, _ = self._classificar(linha)
            self.assertEqual(
                classe,
                esperado["classificacao"],
                f"{linha['trecho']!r} classificada como {classe}",
            )
        self.assertGreater(afetados, 0, "o gabarito não trouxe nenhuma citação com quebra de linha")


class ContratoJsonTest(unittest.TestCase):
    def test_json_emitido_segue_o_contrato_v12(self):
        from resolver_citacoes import classify_csv

        db = caminho_db_padrao()
        if db is None:
            self.skipTest("base canônica não está disponível neste checkout")

        raiz = Path(tempfile.mkdtemp(prefix="citacoes_json_"))
        try:
            entrada = raiz / "citacoes.csv"
            with entrada.open("w", encoding="utf-8-sig", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=("documento_id", "inicio", "fim", "trecho"))
                escritor.writeheader()
                escritor.writerow({
                    "documento_id": "doc_teste",
                    "inicio": 0,
                    "fim": 27,
                    "trecho": "art. 373, I, do CPC\nsegue",
                })
            saida = raiz / "json"
            classify_csv(entrada, saida, db)

            destino = saida / "doc_teste.json"
            self.assertTrue(destino.is_file())
            documento = json.loads(destino.read_text(encoding="utf-8"))
            erros, _ = validar_documento(documento, origem="doc_teste")
            self.assertEqual(erros, [])
            self.assertEqual(documento["schema_version"], "1.2")
            self.assertEqual(documento["citacoes"][0]["id"], "c1")
            self.assertNotIn("confianca", documento["citacoes"][0])
        finally:
            shutil.rmtree(raiz, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
