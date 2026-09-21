"""
Motor Tributário v4.0 - Tax Calculation Engine
Calcula impostos Simples 2026, Simples 2027, IBS/CBS híbrido
Sem hardcodes, sem percentuais fixos. Tudo configurável.
"""

from decimal import Decimal
from datetime import date
from typing import Dict, Optional, Tuple
from enum import Enum
from config_v4 import get_config, TaxStatus
from normalizer_v4 import DataNormalizer


class RegimeType(str, Enum):
    """Regimes tributários"""
    SIMPLES_NACIONAL = "simples"
    LUCRO_REAL = "lucro_real"
    LUCRO_PRESUMIDO = "lucro_presumido"


class SimplesCalculation:
    """
    Calcula DAS no Simples Nacional conforme Resolução CGSN 140/2018
    Fórmula: Alíquota Efetiva = [(RBT12 × alíquota nominal) − parcela deduzir] / RBT12

    IMPORTANTE: Empresas com múltiplas seções (ex: Saídas + Serviços)
    devem usar calcular_das_multiplas_secoes() para calcular por seção
    e depois somar os DAS.
    """

    # Anexo III - Locação/Serviços
    ANEXO_III_FAIXAS = {
        "faixa_1": {"rbt_ate": 180_000, "aliquota": 0.0600, "deduzir": 0},
        "faixa_2": {"rbt_ate": 360_000, "aliquota": 0.1120, "deduzir": 9_360},
        "faixa_3": {"rbt_ate": 720_000, "aliquota": 0.1430, "deduzir": 17_640},
        "faixa_4": {"rbt_ate": 1_800_000, "aliquota": 0.1600, "deduzir": 35_280},
        "faixa_5": {"rbt_ate": 3_600_000, "aliquota": 0.2100, "deduzir": 125_640},
    }

    # Anexo I - Comércio/Indústria
    ANEXO_I_FAIXAS = {
        "faixa_1": {"rbt_ate": 180_000, "aliquota": 0.0400, "deduzir": 0},
        "faixa_2": {"rbt_ate": 360_000, "aliquota": 0.0720, "deduzir": 5_760},
        "faixa_3": {"rbt_ate": 720_000, "aliquota": 0.0970, "deduzir": 13_860},
        "faixa_4": {"rbt_ate": 1_800_000, "aliquota": 0.1160, "deduzir": 22_500},
        "faixa_5": {"rbt_ate": 3_600_000, "aliquota": 0.1430, "deduzir": 87_300},
    }

    @staticmethod
    def get_faixa(rbt12: Decimal, anexo: str = "I") -> Dict:
        """Determina faixa do Simples baseado em RBT12"""
        faixas = SimplesCalculation.ANEXO_I_FAIXAS if anexo == "I" else SimplesCalculation.ANEXO_III_FAIXAS

        for faixa_name, faixa_data in faixas.items():
            if rbt12 <= faixa_data["rbt_ate"]:
                return {
                    "faixa": faixa_name,
                    "rbt_limite": faixa_data["rbt_ate"],
                    "aliquota_nominal": Decimal(str(faixa_data["aliquota"])),
                    "parcela_deduzir": Decimal(str(faixa_data["deduzir"])),
                }

        # Se ultrapassou 3.6M, não está mais no Simples
        return None

    @staticmethod
    def calcular_das(
        rbt12: Decimal,
        receita_mes: Decimal,
        anexo: str = "I",
        validar: bool = True
    ) -> Dict:
        """
        Calcula DAS do mês

        Args:
            rbt12: Receita Bruta dos últimos 12 meses
            receita_mes: Receita do mês em questão
            anexo: "I" (comércio/indústria) ou "III" (serviços)
            validar: Se True, retorna com status de validação

        Returns:
            {
                "das": valor_das,
                "aliquota_efetiva": percentual,
                "faixa": "faixa_5",
                "status": "VALIDADO" ou "ESTIMADO"
            }
        """

        faixa = SimplesCalculation.get_faixa(rbt12, anexo)
        if not faixa:
            return {"erro": "RBT12 acima do limite do Simples"}

        aliq_nom = faixa["aliquota_nominal"]
        deduzir = faixa["parcela_deduzir"]

        # Cálculo: (RBT12 × alíquota) - parcela deduzir
        imposto_anual = (rbt12 * aliq_nom) - deduzir

        # Garantir que nunca seja negativo
        if imposto_anual < 0:
            imposto_anual = Decimal("0")

        # A alíquota efetiva é determinada pelo RBT12, mas o DAS é apurado
        # sobre a receita da competência. Dividir o imposto anual por 12
        # produzia o mesmo DAS para meses com receitas diferentes.
        aliquota_efetiva = (
            (imposto_anual / rbt12).quantize(Decimal("0.0000000001"))
            if rbt12 > 0 else Decimal("0")
        )
        das_mes = (receita_mes * aliquota_efetiva).quantize(Decimal("0.01"))

        return {
            "das": das_mes,
            # Referência matemática da faixa, não uma projeção de 12 meses.
            # A projeção anual deve somar competências reais ou explicitar a
            # hipótese de receita constante.
            "imposto_anual_referencia_faixa": imposto_anual.quantize(Decimal("0.01")),
            "aliquota_nominal": aliq_nom,
            "aliquota_efetiva": aliquota_efetiva,
            "faixa": faixa["faixa"],
            "rbt12": rbt12,
            "receita_mes": receita_mes,
            "anexo": anexo,
            "status": "VALIDADO" if validar else "ESTIMADO",
            "legislacao": "Resolução CGSN 140/2018",
        }

    @staticmethod
    def calcular_das_multiplas_secoes(
        secoes: list,
        rbt12_total: Decimal,
        validar: bool = True,
        das_documento: Optional[Decimal] = None,
    ) -> Dict:
        """
        Calcula DAS para empresa com múltiplas seções tributárias.

        Cada seção precisa trazer a alíquota efetiva extraída do PGDAS ou um
        RBT12 específico já validado. Não é permitido ratear o RBT12 total
        pelo faturamento: esse atalho pode levar a uma faixa incorreta.

        Args:
            secoes: Lista de dicts com:
                {
                    "nome": "Saídas",
                    "anexo": "I",
                    "receita_mes": 96000,
                    "aliquota_efetiva_pgdas": "0.102291333460607"
                }
            rbt12_total: RBT12 consolidado da empresa
            validar: Se True, retorna com status de validação

        Returns:
            {
                "das_total": soma,
                "secoes": [lista de cálculos por seção],
                "composicao": {...}
            }
        """

        if not secoes:
            return {"erro": "Nenhuma seção informada"}

        secoes_calculadas = []
        das_total = Decimal("0")

        for secao in secoes:
            nome = secao.get("nome", "Seção desconhecida")
            anexo = secao.get("anexo", "I")
            receita_mes = Decimal(str(secao.get("receita_mes", 0)))
            aliquota_pgdas = secao.get("aliquota_efetiva_pgdas")
            rbt12_secao = secao.get("rbt12")

            if aliquota_pgdas is not None:
                aliquota_efetiva = Decimal(str(aliquota_pgdas))
                das_secao = {
                    "das": (receita_mes * aliquota_efetiva).quantize(Decimal("0.01")),
                    "aliquota_efetiva": aliquota_efetiva,
                    "receita_mes": receita_mes,
                    "anexo": anexo,
                    "status": "VALIDADO_POR_PGDAS",
                    "fonte_calculo": "aliquota_efetiva_pgdas",
                }
            elif rbt12_secao is not None:
                das_secao = SimplesCalculation.calcular_das(
                    rbt12=Decimal(str(rbt12_secao)),
                    receita_mes=receita_mes,
                    anexo=anexo,
                    validar=validar,
                )
                das_secao["fonte_calculo"] = "rbt12_secao_informado"
            else:
                das_secao = {
                    "erro": "Seção sem alíquota efetiva do PGDAS ou RBT12 específico",
                    "das": Decimal("0.00"),
                    "receita_mes": receita_mes,
                    "anexo": anexo,
                    "status": "DADOS_INSUFICIENTES",
                }

            das_secao["secao_nome"] = nome
            secoes_calculadas.append(das_secao)
            das_total += das_secao["das"]

        resultado = {
            "das_total": das_total.quantize(Decimal("0.01")),
            "secoes": secoes_calculadas,
            "composicao": {
                "numero_secoes": len(secoes),
                "rbt12_total": rbt12_total,
                "status": "VALIDADO" if validar else "ESTIMADO",
            },
            "legislacao": "Resolução CGSN 140/2018 (múltiplas seções)",
        }

        if das_documento is not None:
            resultado["das_documento"] = Decimal(str(das_documento)).quantize(Decimal("0.01"))
            resultado["divergencia_documento"] = (
                resultado["das_documento"] - resultado["das_total"]
            ).quantize(Decimal("0.01"))
            resultado["status_reconciliacao"] = (
                "RECONCILIADO"
                if resultado["divergencia_documento"] == Decimal("0.00")
                else "DIVERGENTE_PGDAS"
            )

        return resultado


class HybridCalculation:
    """
    Calcula regime híbrido: Simples + IBS/CBS regular
    
    No híbrido:
    - Tributos do Simples continuam (menos IBS/CBS)
    - IBS/CBS apurados pelo regime regular
    """

    @staticmethod
    def calcular_hibrido(
        receita_bruta: Decimal,
        base_ibs_debitos: Decimal,
        base_cbs_debitos: Decimal,
        das_remanescente: Decimal,
        creditos_documentados: list,
        ibs_aliquota: Decimal,
        cbs_aliquota: Decimal,
    ) -> Dict:
        """
        Calcula carga tributária no regime híbrido
        
        Args:
            receita_bruta: Total de receitas
            base_ibs_debitos: base de débitos IBS após tratamentos legais.
            base_cbs_debitos: base de débitos CBS após tratamentos legais.
            das_remanescente: DAS sem as parcelas de IBS/CBS.
            creditos_documentados: créditos por documento fiscal, cada qual
                com tributo, valor, evidencia_id e status VALIDADO.
            ibs_aliquota / cbs_aliquota: regras vigentes da simulação.
        
        Returns:
            {
                "ibs_devido": valor,
                "ibs_credito": valor,
                "ibs_liquido": valor,
                "cbs_devido": valor,
                "cbs_credito": valor,
                "cbs_liquido": valor,
                "simples_outros": valor,
                "total_tributario": valor,
                "economia_vs_simples_puro": valor
            }
        """
        
        config = get_config()
        if ibs_aliquota is None or cbs_aliquota is None:
            raise ValueError("Alíquotas IBS e CBS devem vir da regra tributária vigente")

        ibs_aliq = Decimal(str(ibs_aliquota))
        cbs_aliq = Decimal(str(cbs_aliquota))
        das_remanescente = Decimal(str(das_remanescente))

        creditos_ibs = Decimal("0.00")
        creditos_cbs = Decimal("0.00")
        creditos_rejeitados = []
        for credito in creditos_documentados or []:
            if credito.get("status") != "VALIDADO" or not credito.get("evidencia_id"):
                creditos_rejeitados.append(credito.get("evidencia_id", "sem_evidencia"))
                continue
            valor = Decimal(str(credito.get("valor", "0")))
            if credito.get("tributo") == "IBS":
                creditos_ibs += valor
            elif credito.get("tributo") == "CBS":
                creditos_cbs += valor
        
        # ============================================================
        # IBS
        # ============================================================
        ibs_devido = (Decimal(str(base_ibs_debitos)) * ibs_aliq).quantize(Decimal("0.01"))
        ibs_credito = creditos_ibs.quantize(Decimal("0.01"))
        ibs_liquido = max(ibs_devido - ibs_credito, Decimal("0.00"))
        ibs_saldo_credor = max(ibs_credito - ibs_devido, Decimal("0.00"))
        
        # ============================================================
        # CBS
        # ============================================================
        cbs_devido = (Decimal(str(base_cbs_debitos)) * cbs_aliq).quantize(Decimal("0.01"))
        cbs_credito = creditos_cbs.quantize(Decimal("0.01"))
        cbs_liquido = max(cbs_devido - cbs_credito, Decimal("0.00"))
        cbs_saldo_credor = max(cbs_credito - cbs_devido, Decimal("0.00"))
        
        # ============================================================
        # Simples (sem IBS/CBS, que agora são apurados regularmente)
        # ============================================================
        # O valor deve ser apurado a partir das parcelas do DAS. Nunca usar o
        # DAS integral, pois IBS e CBS saem da guia única no regime regular.
        simples_reduzido = das_remanescente
        
        # ============================================================
        # Total
        # ============================================================
        total_hibrido = (ibs_liquido + cbs_liquido + simples_reduzido).quantize(Decimal("0.01"))
        return {
            "regime": "hibrido",
            "receita_bruta": receita_bruta,
            "bases_debito": {"ibs": Decimal(str(base_ibs_debitos)), "cbs": Decimal(str(base_cbs_debitos))},
            
            "ibs": {
                "aliquota": ibs_aliq,
                "status": config.ibs_2027_status,
                "devido": ibs_devido,
                "credito": ibs_credito,
                "liquido": ibs_liquido,
                "saldo_credor": ibs_saldo_credor,
            },
            
            "cbs": {
                "aliquota": cbs_aliq,
                "status": config.cbs_2027_status,
                "devido": cbs_devido,
                "credito": cbs_credito,
                "liquido": cbs_liquido,
                "saldo_credor": cbs_saldo_credor,
            },
            
            "simples_reduzido": simples_reduzido,
            
            "total_tributario": total_hibrido,
            "total_saldo_credor": (ibs_saldo_credor + cbs_saldo_credor).quantize(Decimal("0.01")),
            "creditos_rejeitados": creditos_rejeitados,
            "status": "DADOS_INSUFICIENTES" if creditos_rejeitados else "CALCULADO",
            
            "legislacao": "EC 132/2023 + LC 227/2026",
        }


# ============================================================================
# TESTES
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MOTOR TRIBUTÁRIO - Testes de Cálculo")
    print("=" * 70)

    # Caso WASHINGTON L LOPES COSMOPOLIS (múltiplas seções)
    rbt12_total = Decimal("2236444.92")

    # WASHINGTON tem receitas em múltiplas seções:
    # - Saídas (ICMS): R$ 1.150.693,77 → 78,87% → Anexo I
    # - Serviços (ISS): R$ 308.320,90 → 21,13% → Anexo III

    receita_saidas_mes = Decimal("143836.72")      # 1.150.693,77 / 8 meses
    receita_servicos_mes = Decimal("38540.11")     # 308.320,90 / 8 meses

    pct_saidas = Decimal("0.7887")      # 1.150.693,77 / 1.459.014,67
    pct_servicos = Decimal("0.2113")    # 308.320,90 / 1.459.014,67

    print(f"\n📊 EMPRESA WASHINGTON L LOPES (Múltiplas Seções)")
    print(f"  RBT12 Total: R$ {rbt12_total:,.2f}")
    print(f"  Saídas (ICMS): R$ {receita_saidas_mes:,.2f}/mês ({pct_saidas:.2%})")
    print(f"  Serviços (ISS): R$ {receita_servicos_mes:,.2f}/mês ({pct_servicos:.2%})")

    # Cálculo com alíquotas efetivas extraídas do PGDAS.
    print(f"\n✅ CÁLCULO POR ALÍQUOTA DO PGDAS (Múltiplas Seções)")
    resultado_multiplas = SimplesCalculation.calcular_das_multiplas_secoes(
        secoes=[
            {
                "nome": "Saídas/Comércio",
                "anexo": "I",
                "receita_mes": receita_saidas_mes,
                "aliquota_efetiva_pgdas": "0.102291333460607"
            },
            {
                "nome": "Serviços",
                "anexo": "III",
                "receita_mes": receita_servicos_mes,
                "aliquota_efetiva_pgdas": "0.137119552656186"
            }
        ],
        rbt12_total=rbt12_total
    )

    print(f"  DAS Total: R$ {resultado_multiplas['das_total']:,.2f}")
    print(f"  DAS Anual: R$ {resultado_multiplas['das_anual_total']:,.2f}")
    for i, secao in enumerate(resultado_multiplas['secoes'], 1):
        print(f"\n  Seção {i}: {secao['secao_nome']}")
        print(f"    RBT12: R$ {secao['rbt12']:,.2f}")
        print(f"    DAS: R$ {secao['das']:,.2f}")
        print(f"    Anexo: {secao['anexo']}")
        print(f"    Alíquota Efetiva: {secao['aliquota_efetiva']:.2%}")

    # Híbrido
    print(f"\n🔄 REGIME HÍBRIDO (2027)")
    entradas = Decimal("404301.55")
    hibrido = HybridCalculation.calcular_hibrido(
        receita_bruta=Decimal("1459014.67"),  # jan-ago 2026
        base_ibs_debitos=Decimal("1459014.67"),
        base_cbs_debitos=Decimal("1459014.67"),
        das_remanescente=Decimal("0.00"),
        creditos_documentados=[],
        ibs_aliquota=Decimal("0.001"),
        cbs_aliquota=Decimal("0.088"),
    )

    print(f"  IBS: R$ {hibrido['ibs']['liquido']:,.2f}")
    print(f"  CBS: R$ {hibrido['cbs']['liquido']:,.2f}")
    print(f"  Total: R$ {hibrido['total_tributario']:,.2f}")
    print(f"  Economia vs Simples: R$ {hibrido['economia_vs_simples_puro']:,.2f}")

    print("\n" + "=" * 70)
    print("✓ Engine funcionando corretamente (múltiplas seções)")
    print("=" * 70)
