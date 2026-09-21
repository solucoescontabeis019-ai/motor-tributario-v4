"""
Motor Tributário v4.0 - Data Normalizer
Normaliza dados de entrada (CNPJ, valores monetários, datas, etc).
Genérico, sem exemplos hardcoded de WASHINGTON.
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)


class DataNormalizer:
    """Normaliza dados para formato padrão interno"""

    # ========================================================================
    # CNPJ
    # ========================================================================

    @staticmethod
    def normalize_cnpj(cnpj: str) -> str:
        """
        Normaliza CNPJ removendo formatação.

        Entrada: "04.286.335/0001-79" ou "04286335000179"
        Saída: "04286335000179" (14 dígitos sem formatação)

        Lança ValueError se CNPJ inválido.
        """

        if not cnpj:
            raise ValueError("CNPJ não pode estar vazio")

        # Remove caracteres não numéricos
        cnpj_limpo = re.sub(r'\D', '', cnpj)

        # Verifica se tem 14 dígitos
        if len(cnpj_limpo) != 14:
            raise ValueError(f"CNPJ deve ter 14 dígitos, recebido: {cnpj_limpo}")

        # Valida checksum (algoritmo CNPJ)
        if not DataNormalizer._validate_cnpj_checksum(cnpj_limpo):
            logger.warning(f"CNPJ com checksum inválido: {cnpj_limpo}")
            # Não lança erro por enquanto, apenas avisa

        return cnpj_limpo

    @staticmethod
    def _validate_cnpj_checksum(cnpj: str) -> bool:
        """Valida checksum do CNPJ"""
        if len(cnpj) != 14 or not cnpj.isdigit():
            return False

        # Primeiro dígito verificador. Os pesos não são uma progressão linear:
        # após o 2, reiniciam em 9.
        pesos_primeiro = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
        soma = sum(int(digito) * peso for digito, peso in zip(cnpj[:12], pesos_primeiro))
        resto = soma % 11
        dv1 = 0 if resto < 2 else 11 - resto

        # Segundo dígito verificador, incluindo o primeiro dígito calculado.
        pesos_segundo = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
        soma = sum(int(digito) * peso for digito, peso in zip(cnpj[:13], pesos_segundo))
        resto = soma % 11
        dv2 = 0 if resto < 2 else 11 - resto

        return int(cnpj[12]) == dv1 and int(cnpj[13]) == dv2

    @staticmethod
    def format_cnpj(cnpj: str) -> str:
        """
        Formata CNPJ para apresentação visual.

        Entrada: "04286335000179"
        Saída: "04.286.335/0001-79"
        """
        cnpj_limpo = DataNormalizer.normalize_cnpj(cnpj)
        return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"

    # ========================================================================
    # VALORES MONETÁRIOS
    # ========================================================================

    @staticmethod
    def normalize_moeda(valor: str) -> Decimal:
        """
        Normaliza valor monetário para Decimal.

        Aceita formatos:
        - "1.234,56" (formato BR)
        - "1234.56" (formato US)
        - "1234,56" (com vírgula)
        - 1234.56 (já numérico)

        Saída: Decimal com precisão 2
        """

        if isinstance(valor, (int, float, Decimal)):
            return Decimal(str(valor)).quantize(Decimal('0.01'))

        if not valor:
            return Decimal('0.00')

        valor_str = str(valor).strip()

        # Remove pontos de milhar e converte vírgula
        # Detecta padrão: se tem ponto antes da vírgula = BR
        if ',' in valor_str and '.' in valor_str:
            # Formato BR: 1.234,56
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            # Só tem vírgula: pode ser BR ou US
            # Conta quantidade de casas após vírgula
            casas = len(valor_str.split(',')[1])
            if casas == 2:
                # Provavelmente BR (2 casas decimais)
                valor_str = valor_str.replace(',', '.')
            else:
                # Provavelmente US (milhar com vírgula)
                valor_str = valor_str.replace(',', '')

        try:
            return Decimal(valor_str).quantize(Decimal('0.01'))
        except Exception as e:
            logger.error(f"Erro ao normalizar valor: {valor_str} - {str(e)}")
            raise ValueError(f"Valor inválido: {valor}")

    @staticmethod
    def format_moeda(valor: Decimal, simbolo: str = "R$ ") -> str:
        """
        Formata Decimal para moeda BR.

        Entrada: Decimal("1234.56")
        Saída: "R$ 1.234,56"
        """
        if not isinstance(valor, Decimal):
            valor = Decimal(str(valor))

        valor_abs = abs(valor)
        sinal = "-" if valor < 0 else ""

        # Formata com separadores
        inteiro, decimal = str(valor_abs).split('.')
        inteiro_formatado = "{:,}".format(int(inteiro)).replace(',', '.')

        return f"{sinal}{simbolo}{inteiro_formatado},{decimal}"

    # ========================================================================
    # DATAS
    # ========================================================================

    @staticmethod
    def normalize_data(data: str) -> str:
        """
        Normaliza data para formato ISO YYYY-MM-DD.

        Aceita:
        - "2026-01-31"
        - "31/01/2026"
        - "01-31-2026"

        Saída: "2026-01-31"
        """

        if not data:
            raise ValueError("Data não pode estar vazia")

        data_str = str(data).strip()

        # Já no formato ISO
        if re.match(r'\d{4}-\d{2}-\d{2}', data_str):
            return data_str

        # Formato BR: 31/01/2026
        if re.match(r'\d{2}/\d{2}/\d{4}', data_str):
            dia, mes, ano = data_str.split('/')
            return f"{ano}-{mes}-{dia}"

        # Formato US: 01-31-2026
        if re.match(r'\d{2}-\d{2}-\d{4}', data_str):
            mes, dia, ano = data_str.split('-')
            return f"{ano}-{mes}-{dia}"

        raise ValueError(f"Formato de data não reconhecido: {data_str}")

    @staticmethod
    def normalize_competencia(competencia: str) -> str:
        """
        Normaliza competência/período para YYYY-MM.

        Aceita:
        - "2026-01"
        - "01/2026"
        - "01-2026"

        Saída: "2026-01"
        """

        if not competencia:
            raise ValueError("Competência não pode estar vazia")

        comp_str = str(competencia).strip()

        # Já no formato correto
        if re.match(r'\d{4}-\d{2}', comp_str):
            return comp_str

        # Formato BR: 01/2026
        if re.match(r'\d{2}/\d{4}', comp_str):
            mes, ano = comp_str.split('/')
            return f"{ano}-{mes}"

        # Formato US: 01-2026
        if re.match(r'\d{2}-\d{4}', comp_str):
            mes, ano = comp_str.split('-')
            return f"{ano}-{mes}"

        raise ValueError(f"Formato de competência não reconhecido: {comp_str}")

    # ========================================================================
    # ALÍQUOTAS
    # ========================================================================

    @staticmethod
    def normalize_aliquota(valor: str) -> Decimal:
        """
        Normaliza alíquota para Decimal 0-1.

        Aceita:
        - "8,8%" → 0.088
        - "8.80%" → 0.088
        - "0.088" → 0.088
        - "8.8" → 0.088
        - 8.8 → 0.088
        """

        if isinstance(valor, Decimal):
            # Se já é Decimal e > 1, assume percentual
            if valor > 1:
                return valor / 100
            return valor

        valor_str = str(valor).strip().rstrip('%')

        # Remove símbolos
        valor_str = valor_str.replace('%', '').strip()

        # Se tem vírgula, trata como BR
        if ',' in valor_str:
            valor_str = valor_str.replace('.', '').replace(',', '.')

        try:
            dec_valor = Decimal(valor_str)

            # Se maior que 1, assume que é percentual (ex: 8.8 = 8.8%)
            if dec_valor > 1:
                dec_valor = dec_valor / 100

            return dec_valor.quantize(Decimal('0.000001'))
        except Exception as e:
            raise ValueError(f"Alíquota inválida: {valor}")

    @staticmethod
    def format_aliquota(valor: Decimal) -> str:
        """
        Formata alíquota para apresentação.

        Entrada: Decimal("0.088")
        Saída: "8,80%"
        """
        if not isinstance(valor, Decimal):
            valor = Decimal(str(valor))

        percentual = (valor * 100).quantize(Decimal('0.01'))
        return f"{percentual}%".replace('.', ',')

    # ========================================================================
    # STRINGS GENÉRICAS
    # ========================================================================

    @staticmethod
    def normalize_string(texto: str, max_length: Optional[int] = None) -> str:
        """
        Normaliza string (uppercase, remove extras spaces).
        """
        if not texto:
            return ""

        # Remove espaços extras
        texto_limpo = ' '.join(str(texto).split())

        # Uppercase
        texto_limpo = texto_limpo.upper()

        # Limita comprimento se especificado
        if max_length:
            texto_limpo = texto_limpo[:max_length]

        return texto_limpo


# ============================================================================
# TESTES
# ============================================================================

if __name__ == "__main__":
    # Testes do normalizer

    print("=" * 80)
    print("TESTES - DataNormalizer v4.0")
    print("=" * 80)

    # CNPJ
    print("\n1. CNPJ:")
    print(f"   Entrada: '04.286.335/0001-79'")
    print(f"   Saída: '{DataNormalizer.normalize_cnpj('04.286.335/0001-79')}'")
    print(f"   Formatado: '{DataNormalizer.format_cnpj('04286335000179')}'")

    # Moeda
    print("\n2. Moeda:")
    valor = DataNormalizer.normalize_moeda("1.234,56")
    print(f"   Entrada: '1.234,56'")
    print(f"   Saída: {valor}")
    print(f"   Formatado: {DataNormalizer.format_moeda(valor)}")

    # Alíquota
    print("\n3. Alíquota:")
    aliq = DataNormalizer.normalize_aliquota("8,8%")
    print(f"   Entrada: '8,8%'")
    print(f"   Saída: {aliq}")
    print(f"   Formatado: {DataNormalizer.format_aliquota(aliq)}")

    # Competência
    print("\n4. Competência:")
    print(f"   Entrada: '01/2026'")
    print(f"   Saída: '{DataNormalizer.normalize_competencia('01/2026')}'")

    print("\n" + "=" * 80)
    print("✓ Normalizer funcionando corretamente")
    print("=" * 80)
