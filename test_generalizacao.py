import unittest

from extrair_citacoes import identificar_citacoes


class GeneralizacaoCitacoesTest(unittest.TestCase):
    """Casos sintéticos independentes dos documentos e do golden set."""

    def assertTrechos(self, texto, esperados, documento_id="doc_sintetico"):
        resultados = identificar_citacoes(texto, documento_id)

        self.assertEqual([item["trecho"] for item in resultados], esperados)
        for item in resultados:
            self.assertEqual(item["documento_id"], documento_id)
            self.assertEqual(
                item["trecho"], texto[item["inicio"] : item["fim"]]
            )
        for anterior, atual in zip(resultados, resultados[1:]):
            self.assertLessEqual(anterior["fim"], atual["inicio"])

    def test_familias_juridicas_em_frases_ineditas(self):
        casos = (
            (
                "O colegiado aplicou o RE 635.659/SP ao caso concreto.",
                "RE 635.659/SP",
            ),
            (
                "A decisão menciona o AgInt no AREsp nº 2.345.678/SC.",
                "AgInt no AREsp nº 2.345.678/SC",
            ),
            (
                "Foi mantido o acórdão na Apelação Cível nº "
                "1000123-45.2024.8.26.0100.",
                "Apelação Cível nº 1000123-45.2024.8.26.0100",
            ),
            (
                "O fundamento consta do TST-AIRR-1000123-45.2023.5.02.0001.",
                "TST-AIRR-1000123-45.2023.5.02.0001",
            ),
            (
                "A vedação decorre da Súmula Vinculante nº 13 do STF.",
                "Súmula Vinculante nº 13 do STF",
            ),
            (
                "A pretensão encontra óbice na Súmula 7/STJ.",
                "Súmula 7/STJ",
            ),
            (
                "A controvérsia foi decidida no Tema Repetitivo 1.076 do STJ.",
                "Tema Repetitivo 1.076 do STJ",
            ),
            (
                "Aplica-se o Tema 1.046 da repercussão geral do STF.",
                "Tema 1.046 da repercussão geral do STF",
            ),
            (
                "A proteção está no art. 5º, inciso X, da Constituição Federal.",
                "art. 5º, inciso X, da Constituição Federal",
            ),
            (
                "A indenização decorre dos arts. 186 e 927 do Código Civil.",
                "arts. 186 e 927 do Código Civil",
            ),
            (
                "A multa prevista no § 4º do art. 1.021 do CPC/2015 é aplicável.",
                "§ 4º do art. 1.021 do CPC/2015",
            ),
            (
                "Incide a Lei Complementar nº 101/2000.",
                "Lei Complementar nº 101/2000",
            ),
            (
                "O procedimento segue a Lei nº 14.133, de 1º de abril de 2021.",
                "Lei nº 14.133, de 1º de abril de 2021",
            ),
            (
                "A competência mudou com a Emenda Constitucional nº 45/2004.",
                "Emenda Constitucional nº 45/2004",
            ),
            (
                "O documento observa a Medida Provisória nº 2.200-2/2001.",
                "Medida Provisória nº 2.200-2/2001",
            ),
            (
                "A política foi instituída pela Resolução CNJ nº 125/2010.",
                "Resolução CNJ nº 125/2010",
            ),
            (
                "O ato observa a Resolução nº 345/2020 do CNJ.",
                "Resolução nº 345/2020 do CNJ",
            ),
            (
                "A tipificação remete ao Decreto-Lei nº 2.848/1940.",
                "Decreto-Lei nº 2.848/1940",
            ),
            (
                "Consulte também os autos 0001234-56.2024.8.26.0100.",
                "0001234-56.2024.8.26.0100",
            ),
        )

        for texto, esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertTrechos(texto, [esperado])

    def test_variacoes_tipograficas_e_de_espacamento(self):
        casos = (
            "REsp n. 1.234.567/RS",
            "resp NÚMERO 1.234.567 / RS",
            "ADI n° 4.277 - DF",
            "Lei\nnº 8.078 / 1990",
            "Tema\u00a0Repetitivo\u00a01.076 do STJ",
        )

        for citacao in casos:
            with self.subTest(citacao=citacao):
                self.assertTrechos(f"Antes: {citacao}; depois.", [citacao])

    def test_offsets_nao_dependem_da_posicao_nem_de_unicode_anterior(self):
        citacao = "Súmula 331 do TST"
        prefixos = ("", "Decisão: ", "ação ⚖ " * 80 + "\n")

        for prefixo in prefixos:
            with self.subTest(tamanho_prefixo=len(prefixo)):
                texto = prefixo + citacao + " encerra a referência."
                resultado = identificar_citacoes(texto, "doc_deslocado")
                self.assertEqual(len(resultado), 1)
                self.assertEqual(resultado[0]["inicio"], len(prefixo))
                self.assertEqual(resultado[0]["fim"], len(prefixo) + len(citacao))
                self.assertEqual(resultado[0]["trecho"], citacao)

    def test_multiplas_citacoes_sao_ordenadas_e_nao_se_sobrepoem(self):
        texto = (
            "À luz do art. 37 da Constituição Federal e da Súmula 473 do STF, "
            "reexaminou-se o RE 123.456/MG."
        )

        self.assertTrechos(
            texto,
            [
                "art. 37 da Constituição Federal",
                "Súmula 473 do STF",
                "RE 123.456/MG",
            ],
        )

    def test_linhas_de_metadados_processuais_nao_sao_citacoes(self):
        numero = "0001234-56.2024.8.26.0100"
        rotulos = (
            f"Processo nº {numero}",
            f"Autos n. {numero}",
            f"Referência: Processo número {numero}",
            f"Nº do Processo: {numero}",
            f"Número do processo: {numero}",
        )

        for rotulo in rotulos:
            with self.subTest(rotulo=rotulo):
                self.assertTrechos(rotulo + "\nAutor: Fulano", [])

    def test_texto_nao_juridico_nao_gera_falsos_positivos(self):
        textos = (
            "A reunião ocorreu em 12/10/2024 e custou R$ 1.234,56.",
            "A lei da oferta e da procura foi discutida na aula.",
            "O tema da palestra será definido pela comissão.",
            "O tribunal analisou o recurso conforme jurisprudência pacífica.",
            "Consulte as páginas 45 a 52 e a tabela 3 do relatório.",
            "O artigo científico recebeu o identificador DOI 10.1000/xyz123.",
        )

        for texto in textos:
            with self.subTest(texto=texto):
                self.assertTrechos(texto, [])

    def test_codigos_alfanumericos_nao_sao_cortados_em_falsa_citacao(self):
        textos = (
            "O código interno art. 123abc foi descontinuado.",
            "O produto Lei 123abc saiu de linha.",
            "A etiqueta Tema 456xyz identifica a caixa.",
            "O campo Súmula 12abc pertence ao sistema legado.",
            "O identificador ADI 123abc não representa um processo.",
        )

        for texto in textos:
            with self.subTest(texto=texto):
                self.assertTrechos(texto, [])

    def test_contrato_rejeita_entradas_invalidas(self):
        with self.assertRaises(TypeError):
            identificar_citacoes(None, "doc")
        with self.assertRaises(ValueError):
            identificar_citacoes("art. 5º da Constituição Federal", "")

    def test_ponto_final_antes_de_secao_numerada(self):
        for citacao in (
            "Lei 123/2020", "art. 5", "Súmula 7", "Tema 123",
            "REsp 1.234.567", "REsp 1.234.567/SP", "TST-RR-1234",
        ):
            for separador in (" ", "\n", "\r\n", "\n\n"):
                with self.subTest(citacao=citacao, separador=repr(separador)):
                    self.assertTrechos(
                        f"Aplica-se {citacao}.{separador}2. Dos pedidos", [citacao]
                    )

    def test_uf_nao_e_validada_na_etapa_de_extracao(self):
        # A detecção não afirma que o processo ou a UF existem.
        for classe in ("REsp", "ADI", "Apelação Cível"):
            for numero in ("1.234.567", "987654"):
                for sufixo in ("/ZZ", " - XY", " (ZZ)", "/SP"):
                    citacao = f"{classe} {numero}{sufixo}"
                    with self.subTest(citacao=citacao):
                        self.assertTrechos(
                            f"Conforme {citacao}, requer-se a reforma.", [citacao]
                        )

    def test_cnj_em_linha_isolada_no_corpo_e_preservado(self):
        numero = "0001234-56.2024.8.26.0100"
        for rotulo in ("Processo", "Processo nº", "Autos nº", "Número do processo:"):
            for contexto in (
                "Jurisprudência citada:", "Veja o precedente abaixo.",
                "A decisão recorrida diverge do seguinte julgado:",
            ):
                with self.subTest(rotulo=rotulo, contexto=contexto):
                    self.assertTrechos(
                        f"{contexto}\n{rotulo} {numero}\n"
                        "Esse precedente fundamenta o pedido.", [numero]
                    )

    def test_metadados_e_precedente_no_mesmo_documento(self):
        numero = "0001234-56.2024.8.26.0100"
        texto = (
            f"TRIBUNAL\nProcesso nº {numero}\nAutor: Fulano\nRéu: Empresa\n\n"
            f"Jurisprudência citada:\nProcesso nº {numero}\nAplica-se esse julgado."
        )
        self.assertTrechos(texto, [numero])
        self.assertEqual(identificar_citacoes(texto, "doc")[0]["inicio"], texto.rindex(numero))

    def test_numeros_pontuados_nao_sao_confundidos_com_ponto_final(self):
        for citacao in ("REsp 1.234.567", "Tema 1.076", "art. 1.021 do CPC"):
            with self.subTest(citacao=citacao):
                self.assertTrechos(f"Aplica-se {citacao}.", [citacao])

    def test_numero_processual_fragmentado_por_ocr(self):
        for citacao in (
            "REsp 8. 765.432/XY",
            "Reclamação 76.\n543 (ZZ)",
            "TST-AIRR-2222-33.2022.5.04.\n0123",
            "Apelação Cível 1234567-89. 2022. 8. 01. 1234",
        ):
            with self.subTest(citacao=citacao):
                self.assertTrechos(f"Conforme {citacao}, aplica-se a tese.", [citacao])

    def test_precedente_transcrito_com_campos_de_partes(self):
        numero = "0001234-56.2024.8.26.0100"
        for contexto in ("Precedente citado:", "Considere o seguinte julgado."):
            with self.subTest(contexto=contexto):
                self.assertTrechos(
                    f"{contexto}\nProcesso nº {numero}\n"
                    "Autor: Fulano\nRéu: Empresa\n", [numero]
                )

    def test_cabecalho_com_campos_nao_reconhecidos_por_ocr(self):
        self.assertTrechos(
            "TRIBUNAL\nProcesso nº 0001234-56.2024.8.26.0100\n"
            "Aut0r: Fulano\nRequer1do: Empresa\n\nDECISÃO", []
        )

    def test_referencia_com_relator_isolado_e_preservada(self):
        numero = "0001234-56.2024.8.26.0100"
        self.assertTrechos(
            f"JURISPRUDÊNCIA\nProcesso nº {numero}\nRelator: Fulano de Tal", [numero]
        )

    def test_campo_em_outro_paragrafo_nao_transforma_referencia_em_cabecalho(self):
        numero = "0001234-56.2024.8.26.0100"
        self.assertTrechos(
            f"JURISPRUDÊNCIA\nProcesso nº {numero}\n\nAutor: Fulano", [numero]
        )


if __name__ == "__main__":
    unittest.main()
