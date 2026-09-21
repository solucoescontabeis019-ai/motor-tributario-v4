#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parser de Documentos Tributários v2.3
Extrai dados de PGDAS-D, Entradas e Saídas
"""

import re
from typing import Dict, List, Any, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class DocumentParser:
    """Parser profissional de documentos tributários"""

    def __init__(self):
        self.confidence_threshold = 0.7

    def _clean_currency(self, value: str) -> float:
        """Converte formato brasileiro de moeda (1.234,56) para float"""
        if not value:
            return 0.0

        # Remove espaços
        value = value.strip()

        # Padrão brasileiro: 1.234,56 -> 1234.56
        value = value.replace('.', '')  # Remove milhares
        value = value.replace(',', '.')  # Substitui vírgula por ponto

        try:
            return float(value)
        except ValueError:
            return 0.0

    def _extract_cnpj(self, text: str) -> Optional[str]:
        """Extrai CNPJ em qualquer formato"""
        # Procura padrão XX.XXX.XXX/XXXX-XX ou XXXXXXXXXXXXXXXX
        match = re.search(r'(\d{2}\.?\d{3}\.?\d{3}/?:?\d{4}-?\d{2})', text)
        if match:
            cnpj = match.group(1)
            # Normaliza
            cnpj = re.sub(r'[^\d]', '', cnpj)
            if len(cnpj) == 14:
                return cnpj
        return None

    @staticmethod
    def _pages_do_relatorio(pdf, marcador: str):
        """Seleciona páginas do relatório solicitado em um PDF consolidado."""
        paginas = []
        marcadores = (marcador,) if isinstance(marcador, str) else tuple(marcador)
        for page in pdf.pages:
            texto = page.extract_text() or ""
            texto_maiusculo = texto.upper()
            if all(item in texto_maiusculo for item in marcadores):
                paginas.append((page, texto))
        return paginas

    def parse_pgdas(self, file_path: str) -> Dict[str, Any]:
        """
        Extrai dados do PGDAS-D (Simples Nacional)

        Retorna:
        - company_name
        - company_cnpj
        - rbt12_value
        - das_value
        - faixa_tributaria
        - mes_competencia
        """
        try:
            if not pdfplumber:
                return self._error_response("pdfplumber não disponível")

            result = {
                "type": "PGDAS-D",
                "company_name": None,
                "company_cnpj": None,
                "rbt12_value": 0.0,
                "receita_periodo_value": 0.0,
                "das_value": 0.0,
                "faixa_tributaria": None,
                "mes_competencia": None,
                "aliquota_efetiva": None,
                "confidence": 0.0,
                "status": "NÃO_VALIDADO"
            }

            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return self._error_response("PDF vazio")

                # Extrai texto das primeiras 2 páginas
                full_text = ""
                for page in pdf.pages[:2]:
                    full_text += page.extract_text() or ""

            # Busca CNPJ
            cnpj = self._extract_cnpj(full_text)
            if cnpj:
                result["company_cnpj"] = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

            # A identificação do PGDAS tem formato estável: Empresa: ... Página.
            empresa_match = re.search(r'Empresa:\s*(.+?)\s+P[áa]gina:', full_text, re.IGNORECASE)
            if empresa_match:
                result["company_name"] = empresa_match.group(1).strip()

            # Busca RBT12
            rbt_pattern = r'\(RBT12\)\s*([\d.,]+)\s+[\d.,]+\s+([\d.,]+)'
            rbt_match = re.search(rbt_pattern, full_text, re.IGNORECASE)
            if rbt_match:
                result["rbt12_value"] = self._clean_currency(rbt_match.group(2))

            rpa_pattern = r'Regime de Compet[êe]ncia\s+([\d.,]+)\s+[\d.,]+\s+([\d.,]+)'
            rpa_match = re.search(rpa_pattern, full_text, re.IGNORECASE)
            if rpa_match:
                result["receita_periodo_value"] = self._clean_currency(rpa_match.group(2))

            # Busca DAS
            das_pattern = r'Simples Nacional a recolher:\s*([\d.,]+)'
            das_match = re.search(das_pattern, full_text, re.IGNORECASE)
            if das_match:
                result["das_value"] = self._clean_currency(das_match.group(1))

            # A palavra-chave evita capturar parte do CNPJ como competência.
            mes_pattern = r'(?:Per[ií]odo|Compet[êe]ncia):\s*(\d{2})/(\d{4})'
            mes_match = re.search(mes_pattern, full_text)
            if mes_match:
                result["mes_competencia"] = f"{mes_match.group(1)}/{mes_match.group(2)}"

            # A taxa da competência é DAS / RPA; DAS / RBT12 não é alíquota
            # efetiva e não pode alimentar a simulação.
            if result["receita_periodo_value"] > 0:
                result["aliquota_efetiva"] = (
                    result["das_value"] / result["receita_periodo_value"]
                ) * 100

            secoes = []
            secao_pattern = (
                r'Receita Tributada Total:\s*([\d.,]+)\s+'
                r'Al[íi]quota:\s*([\d.,]+)\s+'
                r'Simples Nacional Total:\s*([\d.,]+)'
            )
            for receita, aliquota, das_secao in re.findall(secao_pattern, full_text, re.IGNORECASE):
                secoes.append({
                    "receita_tributada": self._clean_currency(receita),
                    "aliquota_efetiva_percentual": self._clean_currency(aliquota),
                    "das_secao": self._clean_currency(das_secao),
                })
            result["secoes"] = secoes

            obrigatorios = ("company_cnpj", "company_name", "mes_competencia")
            campos_presentes = all(result[campo] for campo in obrigatorios)
            valores_validos = result["rbt12_value"] > 0 and result["receita_periodo_value"] > 0 and result["das_value"] > 0
            if campos_presentes and valores_validos:
                result["confidence"] = 0.90 if secoes else 0.80
                result["status"] = "VALIDADO"
            else:
                result["status"] = "DADOS_INSUFICIENTES"
                result["campos_ausentes"] = [
                    campo for campo in obrigatorios if not result[campo]
                ] + [
                    campo for campo in ("rbt12_value", "receita_periodo_value", "das_value")
                    if not result[campo]
                ]

            return result

        except Exception as e:
            return self._error_response(f"Erro ao processar PGDAS: {str(e)}")

    def parse_entradas(self, file_path: str) -> Dict[str, Any]:
        """
        Extrai dados de Entradas (Compras/Fornecedores)

        Retorna lista de fornecedores com:
        - cnpj
        - razao_social
        - valor
        """
        return self._parse_movimentacao_pdf(
            file_path, "ACOMPANHAMENTO DE ENTRADAS", "ENTRADAS",
            cnpj_intervalo=(280, 410), nome_intervalo=(235, 355), valor_intervalo=(450, 535),
        )

    def _parse_movimentacao_pdf(
        self, file_path: str, marcador: str, tipo: str,
        cnpj_intervalo: tuple, nome_intervalo: tuple, valor_intervalo: tuple,
    ) -> Dict[str, Any]:
        """Extrai linhas financeiras pelas posições das colunas do PDF."""
        try:
            if not pdfplumber:
                return self._error_response("pdfplumber não disponível")

            operacoes = []
            with pdfplumber.open(file_path) as pdf:
                paginas = self._pages_do_relatorio(pdf, marcador)
                if not paginas:
                    return self._error_response(f"Relatório '{marcador}' não encontrado")
                # Alguns relatórios trazem o título apenas na primeira página.
                # Incluímos as folhas do mesmo bloco, parando ao encontrar
                # explicitamente outro relatório em um PDF consolidado.
                indice_inicial = next(
                    i for i, page in enumerate(pdf.pages)
                    if marcador.upper() in (page.extract_text() or "").upper()
                )
                bloco = []
                for page in pdf.pages[indice_inicial:]:
                    texto = page.extract_text() or ""
                    texto_maiusculo = texto.upper()
                    if bloco and (
                        ("ACOMPANHAMENTO DE" in texto_maiusculo and marcador.upper() not in texto_maiusculo)
                        or "RELAÇÃO DE " in texto_maiusculo
                    ):
                        break
                    bloco.append((page, texto))
                paginas = bloco
                cnpj_empresa = self._extract_cnpj(paginas[0][1])

                for numero_pagina, (page, _) in enumerate(paginas, start=1):
                    linhas = {}
                    for palavra in page.extract_words(use_text_flow=True, keep_blank_chars=False):
                        linhas.setdefault(round(palavra["top"]), []).append(palavra)
                    for y, palavras in linhas.items():
                        if y < 68:
                            continue
                        palavras.sort(key=lambda item: item["x0"])
                        cnpj_texto = next(
                            (item["text"] for item in palavras
                             if cnpj_intervalo[0] <= item["x0"] <= cnpj_intervalo[1]
                             and self._extract_cnpj(item["text"])),
                            None,
                        )
                        cnpj = self._extract_cnpj(cnpj_texto or "")
                        if not cnpj or cnpj == cnpj_empresa:
                            continue
                        nome = " ".join(
                            item["text"] for item in palavras
                            if nome_intervalo[0] <= item["x0"] < nome_intervalo[1]
                            and not self._extract_cnpj(item["text"])
                            and not re.fullmatch(r"[\d./-]+", item["text"])
                        ).strip() or "NÃO IDENTIFICADO"
                        valores = [
                            self._clean_currency(re.match(r"[\d.,]+", item["text"]).group(0))
                            for item in palavras
                            if valor_intervalo[0] <= item["x0"] <= valor_intervalo[1]
                            and re.match(r"[\d.,]+(?:ICMS|IPI)?$", item["text"])
                        ]
                        if not valores:
                            continue
                        datas = [item["text"] for item in palavras if re.fullmatch(r"\d{2}/\d{2}/\d{4}", item["text"])]
                        operacoes.append({
                            "cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                            "razao_social": nome[:255],
                            "valor_contabil": valores[0],
                            "data_emissao": datas[0] if datas else None,
                            "pagina_origem": numero_pagina,
                            "linha_origem": y,
                        })

            consolidados = {}
            for operacao in operacoes:
                item = consolidados.setdefault(operacao["cnpj"], {
                    "cnpj": operacao["cnpj"], "razao_social": operacao["razao_social"],
                    "valor": 0.0, "quantidade_notas": 0,
                })
                item["valor"] += operacao["valor_contabil"]
                item["quantidade_notas"] += 1
            return {
                "type": tipo,
                "entities": list(consolidados.values()),
                "operacoes": operacoes,
                "total_entities": len(consolidados),
                "total_operacoes": len(operacoes),
                "confidence": 0.65 if operacoes else 0.0,
                "status": "DADOS_PARCIAIS" if operacoes else "VAZIO",
                "message": "Linhas identificadas por posição no PDF; totais aguardam reconciliação com os totais do relatório.",
            }
        except Exception as e:
            return self._error_response(f"Erro ao processar {tipo}: {str(e)}")

        try:
            if not pdfplumber:
                return self._error_response("pdfplumber não disponível")

            entities = []

            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return self._error_response("PDF vazio")

                paginas = self._pages_do_relatorio(pdf, "ACOMPANHAMENTO DE ENTRADAS")
                if not paginas:
                    paginas = [(page, page.extract_text() or "") for page in pdf.pages]

                cnpj_empresa = self._extract_cnpj(paginas[0][1]) if paginas else None
                for page, text in paginas:

                    # Procura linhas com CNPJ
                    for line in text.split('\n'):
                        cnpj = self._extract_cnpj(line)
                        if cnpj and cnpj != cnpj_empresa:
                            # Procura valor na mesma linha ou próximas linhas
                            value_match = re.search(r'([\d.,]+)\s*$', line)
                            valor = 0.0

                            if value_match:
                                valor = self._clean_currency(value_match.group(1))

                            # Razão social é geralmente antes do CNPJ
                            razao_social = line.split(cnpj)[0].strip() if cnpj in line else "N/A"
                            if not razao_social:
                                razao_social = "N/A"

                            entities.append({
                                "cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                                "razao_social": razao_social[:60],  # Trunca
                                "valor": valor
                            })

            if not entities:
                # Fallback: tenta tabelas
                with pdfplumber.open(file_path) as pdf:
                    paginas = self._pages_do_relatorio(pdf, "ACOMPANHAMENTO DE ENTRADAS")
                    if not paginas:
                        paginas = [(page, page.extract_text() or "") for page in pdf.pages]
                    for page, _ in paginas:
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                for row in table:
                                    # Procura CNPJ na linha
                                    for cell in row:
                                        cnpj = self._extract_cnpj(str(cell))
                                        if cnpj:
                                            # Coleta informações da linha
                                            razao = row[0] if row else "N/A"
                                            valor_str = row[-1] if row else "0"

                                            entities.append({
                                                "cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                                                "razao_social": str(razao)[:60],
                                                "valor": self._clean_currency(str(valor_str))
                                            })

            # Em PDF de relatório, o valor pode estar em outra coluna ou em
            # uma linha "Total Fornecedor". Sem reconciliação por NF, a lista
            # é útil para cadastro, mas não para calcular crédito.
            return {
                "type": "ENTRADAS",
                "entities": entities,
                "total_entities": len(entities),
                "confidence": 0.40 if entities else 0.0,
                "status": "DADOS_PARCIAIS" if entities else "VAZIO",
                "message": "Fornecedores identificados; valores por nota exigem reconciliação antes do cálculo de crédito.",
            }

        except Exception as e:
            return self._error_response(f"Erro ao processar Entradas: {str(e)}")

    def parse_servicos_prestados(self, file_path: str) -> Dict[str, Any]:
        """Extrai serviços prestados quando houver relatório próprio."""
        return self._parse_movimentacao_pdf(
            file_path, "ACOMPANHAMENTO DE SERV", "SERVIÇOS PRESTADOS",
            cnpj_intervalo=(330, 420), nome_intervalo=(280, 400), valor_intervalo=(510, 540),
        )

    def parse_saidas(self, file_path: str) -> Dict[str, Any]:
        """
        Extrai dados de Saídas (Vendas/Clientes)

        Retorna lista de clientes com:
        - cnpj
        - razao_social
        - valor
        """
        return self._parse_movimentacao_pdf(
            file_path, "ACOMPANHAMENTO DE SA", "SAÍDAS",
            cnpj_intervalo=(350, 425), nome_intervalo=(250, 360), valor_intervalo=(540, 580),
        )

        try:
            if not pdfplumber:
                return self._error_response("pdfplumber não disponível")

            entities = []

            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return self._error_response("PDF vazio")

                # "SA" cobre o caractere de acento eventualmente corrompido
                # na extração de texto de alguns PDFs.
                paginas = self._pages_do_relatorio(pdf, "ACOMPANHAMENTO DE SA")
                if not paginas:
                    paginas = [(page, page.extract_text() or "") for page in pdf.pages]

                cnpj_empresa = self._extract_cnpj(paginas[0][1]) if paginas else None
                for page, text in paginas:

                    # Procura linhas com CNPJ
                    for line in text.split('\n'):
                        cnpj = self._extract_cnpj(line)
                        if cnpj and cnpj != cnpj_empresa:
                            # Procura valor na mesma linha
                            value_match = re.search(r'([\d.,]+)\s*$', line)
                            valor = 0.0

                            if value_match:
                                valor = self._clean_currency(value_match.group(1))

                            # Razão social
                            razao_social = line.split(cnpj)[0].strip() if cnpj in line else "N/A"
                            if not razao_social:
                                razao_social = "N/A"

                            entities.append({
                                "cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                                "razao_social": razao_social[:60],
                                "valor": valor
                            })

            if not entities:
                # Fallback: tenta tabelas
                with pdfplumber.open(file_path) as pdf:
                    paginas = self._pages_do_relatorio(pdf, "ACOMPANHAMENTO DE SA")
                    if not paginas:
                        paginas = [(page, page.extract_text() or "") for page in pdf.pages]
                    for page, _ in paginas:
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                for row in table:
                                    for cell in row:
                                        cnpj = self._extract_cnpj(str(cell))
                                        if cnpj:
                                            razao = row[0] if row else "N/A"
                                            valor_str = row[-1] if row else "0"

                                            entities.append({
                                                "cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                                                "razao_social": str(razao)[:60],
                                                "valor": self._clean_currency(str(valor_str))
                                            })

            return {
                "type": "SAÍDAS",
                "entities": entities,
                "total_entities": len(entities),
                "confidence": 0.40 if entities else 0.0,
                "status": "DADOS_PARCIAIS" if entities else "VAZIO",
                "message": "Clientes identificados; valores por nota exigem reconciliação antes da análise comercial.",
            }

        except Exception as e:
            return self._error_response(f"Erro ao processar Saídas: {str(e)}")

    def _parse_relacao_cnpjs(self, file_path: str, marcador: str, tipo: str) -> Dict[str, Any]:
        """Lê relação cadastral, sem inferir que houve compra ou venda."""
        try:
            if not pdfplumber:
                return self._error_response("pdfplumber não disponível")

            entidades = []
            vistos = set()
            with pdfplumber.open(file_path) as pdf:
                paginas = self._pages_do_relatorio(pdf, marcador)
                if not paginas:
                    return self._error_response(f"Relatório '{marcador}' não encontrado")

                cnpj_empresa = self._extract_cnpj(paginas[0][1])
                for page, _ in paginas:
                    # A extração de texto linear mistura as duas colunas do
                    # relatório. Usar as coordenadas preserva razão social e
                    # CNPJ na mesma linha visual.
                    linhas = {}
                    for palavra in page.extract_words(use_text_flow=True, keep_blank_chars=False):
                        chave = round(palavra["top"])
                        linhas.setdefault(chave, []).append(palavra)

                    for _, palavras in sorted(linhas.items()):
                        if not palavras or palavras[0]["top"] < 90:
                            continue
                        palavras.sort(key=lambda item: item["x0"])
                        nome = " ".join(item["text"] for item in palavras if item["x0"] < 135).strip()
                        cnpj_texto = "".join(item["text"] for item in palavras if item["x0"] >= 135)
                        match = re.search(r'\d{14}', re.sub(r'\D', '', cnpj_texto))
                        if not match:
                            continue
                        cnpj = match.group(0)
                        if cnpj == "00000000000000" or cnpj == cnpj_empresa or cnpj in vistos:
                            continue
                        vistos.add(cnpj)
                        entidades.append({
                            "cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                            "razao_social": nome[:255],
                        })

            return {
                "type": tipo,
                "entities": entidades,
                "total_entities": len(entidades),
                "confidence": 0.75 if entidades else 0.0,
                "status": "DADOS_PARCIAIS" if entidades else "VAZIO",
                "message": "Relação cadastral identificada; não representa movimentação financeira.",
            }
        except Exception as e:
            return self._error_response(f"Erro ao processar {tipo}: {str(e)}")

    def parse_fornecedores(self, file_path: str) -> Dict[str, Any]:
        return self._parse_relacao_cnpjs(file_path, ("RELA", "FORNECEDORES"), "FORNECEDORES")

    def parse_clientes(self, file_path: str) -> Dict[str, Any]:
        return self._parse_relacao_cnpjs(file_path, ("RELA", "CLIENTES"), "CLIENTES")

    @staticmethod
    def _error_response(message: str) -> Dict[str, Any]:
        """Formata resposta de erro"""
        return {
            "status": "erro",
            "message": message,
            "confidence": 0.0
        }
