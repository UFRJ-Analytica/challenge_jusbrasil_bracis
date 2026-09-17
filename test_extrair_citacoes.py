import csv
import shutil
import unittest
import uuid
from collections import Counter
from pathlib import Path

from extrair_citacoes import (
    identificar_citacoes,
    identificar_citacoes_em_diretorio,
    salvar_csv,
)


class IdentificarCitacoesTest(unittest.TestCase):
    def test_numeros_sem_ponto_nao_sao_truncados(self):
        for trecho in (
            "art. 1022 do CPC",
            "Tema 1234 do STF",
            "Lei 8078/1990",
            "art. 14 da Lei 8078/1990",
            "Decreto 1234/2020",
            "art. 1 do Decreto 1234/2020",
        ):
            with self.subTest(trecho=trecho):
                texto = f"Aplica-se {trecho}."
                inicio = texto.index(trecho)
                self.assertEqual(identificar_citacoes(texto, "teste"), [{
                    "documento_id": "teste", "inicio": inicio,
                    "fim": inicio + len(trecho), "trecho": trecho,
                }])

    def test_cnj_independe_da_posicao_no_texto(self):
        numero = "0600216-46.2020.6.14.0022"
        for prefixo in ("", "Conforme o processo ", "x" * 450 + " Conforme o processo "):
            with self.subTest(tamanho_prefixo=len(prefixo)):
                texto = prefixo + numero + ", aplica-se o precedente."
                self.assertEqual(identificar_citacoes(texto, "teste"), [{
                    "documento_id": "teste", "inicio": len(prefixo),
                    "fim": len(prefixo) + len(numero), "trecho": numero,
                }])

    def test_cnj_em_linha_de_identificacao_nao_e_citacao(self):
        numero = "0600216-46.2020.6.14.0022"
        for rotulo in ("Processo nº", "Autos nº", "Referência: autos nº"):
            for prefixo in ("", "Cabeçalho " * 50 + "\n"):
                with self.subTest(rotulo=rotulo, tamanho_prefixo=len(prefixo)):
                    texto = prefixo + rotulo + " " + numero + "\nAssistido: Empresa"
                    self.assertEqual(identificar_citacoes(texto, "teste"), [])

    def test_filtro_cnj_preserva_mencao_no_corpo(self):
        numero = "0600216-46.2020.6.14.0022"
        texto = f"Processo nº {numero}\nConforme o processo nº {numero}, aplica-se o precedente."
        linhas = identificar_citacoes(texto, "teste")
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["inicio"], texto.rindex(numero))
        self.assertEqual(linhas[0]["fim"], texto.rindex(numero) + len(numero))
        self.assertEqual(linhas[0]["trecho"], numero)

    def test_extracao_preserva_todos_os_offsets_do_golden(self):
        raiz = Path(__file__).resolve().parent / "dados_competicao"
        with (raiz / "goldenset_offsets.csv").open(encoding="utf-8-sig", newline="") as arquivo:
            golden = list(csv.DictReader(arquivo))
        linhas = identificar_citacoes_em_diretorio(raiz / "txt")
        def chave(linha):
            return linha["documento_id"], int(linha["inicio"]), int(linha["fim"])
        self.assertEqual(Counter(map(chave, linhas)), Counter(map(chave, golden)))
        textos = {p.stem: p.read_text(encoding="utf-8-sig") for p in (raiz / "txt").glob("*.txt")}
        for linha in linhas:
            self.assertEqual(linha["trecho"], textos[linha["documento_id"]][linha["inicio"]:linha["fim"]])

    def test_identifica_referencia_sumula_e_artigo_com_offsets_exatos(self):
        texto = (
            "Conforme o REsp 1.741.784 - PR e a Súmula 83 do STJ, "
            "aplica-se o art. 373, I, do CPC."
        )
        esperado = [
            "REsp 1.741.784 - PR",
            "Súmula 83 do STJ",
            "art. 373, I, do CPC",
        ]

        linhas = identificar_citacoes(texto, "doc_teste")

        self.assertEqual([linha["trecho"] for linha in linhas], esperado)
        for linha in linhas:
            self.assertEqual(linha["documento_id"], "doc_teste")
            self.assertEqual(
                linha["trecho"], texto[linha["inicio"] : linha["fim"]]
            )

    def test_identifica_numero_cnj_com_espacos_sem_alterar_o_texto(self):
        texto = "x" * 400 + " Foi citado o processo 0600216- 46.2020.6.14.0022 no voto."

        linhas = identificar_citacoes(texto, "doc_cnj")

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["trecho"], "0600216- 46.2020.6.14.0022")
        self.assertEqual(
            linhas[0]["trecho"], texto[linhas[0]["inicio"] : linhas[0]["fim"]]
        )

    def test_numero_cnj_sem_zeros_a_esquerda_nao_e_cortado(self):
        texto = "Consta do AIRR nº 129-87.2013.5.01.0004 do TST."

        linhas = identificar_citacoes(texto, "doc_airr")

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["trecho"], "AIRR nº 129-87.2013.5.01.0004 do TST")

    def test_conjuncao_antes_da_classe_nao_entra_no_span(self):
        texto = "A tese foi fixada na ADPF 324 e no Recurso Extraordinário 958.252."

        linhas = identificar_citacoes(texto, "doc_conjuncao")

        self.assertEqual(
            [linha["trecho"] for linha in linhas],
            ["ADPF 324", "Recurso Extraordinário 958.252"],
        )

    def test_prefere_dispositivo_completo_a_lei_sobreposta(self):
        texto = "Incide o art. 14 da Lei nº 8.078/1990 sobre a controvérsia."

        linhas = identificar_citacoes(texto, "doc_lei")

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["trecho"], "art. 14 da Lei nº 8.078/1990")

    def test_nao_marca_boilerplate_generico_como_citacao(self):
        texto = (
            "Aplica-se a jurisprudência pacífica desta Corte e o dispositivo "
            "legal de regência."
        )

        linhas = identificar_citacoes(texto, "doc_incompleto")

        self.assertEqual(linhas, [])

    def test_identifica_referencia_incompleta_com_tribunal_ano_e_relator(self):
        texto = (
            "Invoca-se o julgado do STF proferido em 2024 pela relatoria de "
            "Dias Toffoli, no ponto relevante."
        )

        linhas = identificar_citacoes(texto, "doc_incompleto")

        self.assertEqual(len(linhas), 1)
        self.assertEqual(
            linhas[0]["trecho"],
            "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli",
        )

    def test_processa_diretorio_e_salva_tabela(self):
        raiz = Path.cwd() / f"_test_citacoes_{uuid.uuid4().hex}"
        try:
            entrada = raiz / "txt"
            entrada.mkdir(parents=True)
            (entrada / "doc_0001.txt").write_text(
                "Aplicação da Súmula Vinculante nº 10 do STF.", encoding="utf-8"
            )
            saida = raiz / "citacoes.csv"

            linhas = identificar_citacoes_em_diretorio(entrada)
            salvar_csv(linhas, saida)

            with saida.open(encoding="utf-8-sig", newline="") as arquivo:
                gravadas = list(csv.DictReader(arquivo))
            self.assertEqual(len(gravadas), 1)
            self.assertEqual(gravadas[0]["documento_id"], "doc_0001")
            self.assertEqual(
                gravadas[0]["trecho"], "Súmula Vinculante nº 10 do STF"
            )
        finally:
            if raiz.exists():
                shutil.rmtree(raiz)


if __name__ == "__main__":
    unittest.main()
