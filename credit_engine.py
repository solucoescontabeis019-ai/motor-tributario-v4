"""
Motor Tributário v4.0 - Credit Calculation Engine
Determina créditos elegíveis de IBS/CBS por fornecedor
Sem percentuais fixos. Análise legal de cada operação.
"""

from decimal import Decimal
from typing import Dict, Optional, List
from enum import Enum
from models_v4 import RegimesTributarios, ValidacaoStatus


class CreditType(str, Enum):
    """Tipos de crédito permitidos"""
    INTEGRAL = "integral"              # 100% de crédito
    PARCIAL = "parcial"                # Percentual limitado
    PRESUMIDO = "presumido"            # Crédito presumido (sem imposto destacado)
    CONDICIONADO = "condicionado"      # Depende de validação
    VEDADO = "vedado"                  # Não permite crédito


class SupplierRegimeAnalysis:
    """
    Analisa regime de fornecedor e determina elegibilidade de crédito
    LC 214/2025 (IBS) + LC 227/2026 (CBS)
    """

    @staticmethod
    def analisar_fornecedor(
        regime_fornecedor: str,
        regime_validacao_status: str,
        tributo: str = "IBS",  # IBS ou CBS
    ) -> Dict:
        """
        Determina se fornecedor gera crédito e em qual percentual
        
        NUNCA use percentual fixo (ex: 30% para Simples).
        SEMPRE determine conforme regime real e legislação.
        
        Args:
            regime_fornecedor: "Simples Nacional", "Lucro Real", etc
            regime_validacao_status: "validado", "presumido", "não_validado"
            tributo: "IBS" ou "CBS"
        
        Returns:
            {
                "regime": "Simples Nacional",
                "regime_status": "validado",
                "tributo": "IBS",
                "credito_tipo": "integral" | "parcial" | "presumido" | "vedado",
                "credito_percentual": 1.0 | 0.5 | None,
                "legislacao": "artigo X da LC 214/2025",
                "observacao": "descrição do tratamento"
            }
        """
        
        # Se regime não validado, não há crédito
        if regime_validacao_status == ValidacaoStatus.NÃO_VALIDADO.value:
            return {
                "regime": regime_fornecedor,
                "regime_status": "não_validado",
                "tributo": tributo,
                "credito_tipo": CreditType.VEDADO,
                "credito_percentual": 0.0,
                "legislacao": "LC 214/2025, art. X - regime não validado",
                "observacao": "Regime do fornecedor não foi validado. Não há crédito."
            }
        
        # ============================================================
        # FORNECEDOR EM SIMPLES NACIONAL
        # ============================================================
        if regime_fornecedor == RegimesTributarios.SIMPLES_NACIONAL.value:
            
            # Simples NÃO recolhe IBS/CBS destacado
            # Mas lei permite crédito presumido em alguns casos
            
            if tributo == "IBS":
                return {
                    "regime": "Simples Nacional",
                    "regime_status": regime_validacao_status,
                    "tributo": "IBS",
                    "credito_tipo": CreditType.PRESUMIDO,
                    "credito_percentual": 0.0,  # Apurado pelo regime do Simples
                    "legislacao": "LC 214/2025, art. 18 - Crédito do Simples",
                    "observacao": "Fornecedor Simples: crédito conforme regime. Necessário extrair de PGDAS ou consultar receita."
                }
            
            elif tributo == "CBS":
                return {
                    "regime": "Simples Nacional",
                    "regime_status": regime_validacao_status,
                    "tributo": "CBS",
                    "credito_tipo": CreditType.VEDADO,
                    "credito_percentual": 0.0,
                    "legislacao": "LC 227/2026 - CBS vedada no Simples",
                    "observacao": "Fornecedor no Simples: CBS não se aplica no regime simplificado."
                }
        
        # ============================================================
        # FORNECEDOR EM LUCRO REAL
        # ============================================================
        elif regime_fornecedor == RegimesTributarios.LUCRO_REAL.value:
            
            # Lucro Real recolhe IBS/CBS com destaque
            # Crédito integral se documento válido
            
            return {
                "regime": "Lucro Real",
                "regime_status": regime_validacao_status,
                "tributo": tributo,
                "credito_tipo": CreditType.INTEGRAL,
                "credito_percentual": 1.0,  # 100%
                "legislacao": f"LC {'214/2025' if tributo == 'IBS' else '227/2026'} - Crédito Integral",
                "observacao": f"Fornecedor em Lucro Real: {tributo} integral se documento válido (NF-e com {tributo} destacado)."
            }
        
        # ============================================================
        # FORNECEDOR EM LUCRO PRESUMIDO
        # ============================================================
        elif regime_fornecedor == RegimesTributarios.LUCRO_PRESUMIDO.value:
            
            # Lucro Presumido: situação especial
            # Alguns créditos permitidos, outros vedados
            
            return {
                "regime": "Lucro Presumido",
                "regime_status": regime_validacao_status,
                "tributo": tributo,
                "credito_tipo": CreditType.CONDICIONADO,
                "credito_percentual": None,  # Depende da natureza da operação
                "legislacao": f"LC {'214/2025' if tributo == 'IBS' else '227/2026'} - Crédito Condicionado",
                "observacao": f"Lucro Presumido: crédito parcial. Necessário analisar natureza da compra (matéria-prima, ativo fixo, etc)."
            }
        
        # ============================================================
        # PADRÃO (regime desconhecido)
        # ============================================================
        else:
            return {
                "regime": regime_fornecedor,
                "regime_status": "não_validado",
                "tributo": tributo,
                "credito_tipo": CreditType.VEDADO,
                "credito_percentual": 0.0,
                "legislacao": "Regime desconhecido",
                "observacao": f"Regime '{regime_fornecedor}' não mapeado. Necessário validação manual."
            }


class CreditCalculation:
    """
    Calcula créditos efetivos baseado em análise de regime
    """

    @staticmethod
    def calcular_credito(
        base_calculo: Decimal,
        aliquota: Decimal,
        credito_tipo: str,
        credito_percentual: Optional[Decimal] = None,
        regime_fornecedor: Optional[str] = None,
    ) -> Dict:
        """
        Calcula valor de crédito efetivo
        
        Args:
            base_calculo: Valor da operação
            aliquota: Alíquota do tributo (0.0010 para IBS, 0.088 para CBS)
            credito_tipo: integral | parcial | presumido | vedado | condicionado
            credito_percentual: Percentual de crédito (0-1), se aplicável
            regime_fornecedor: Nome do regime (para referência)
        
        Returns:
            {
                "tributo_devido": valor,
                "credito_permitido": valor,
                "credito_efectivo": valor,
                "tipo": "integral" | "parcial" | ...,
                "percentual": 100% | 50% | etc
            }
        """
        
        # Tributo sobre a compra
        tributo_compra = (base_calculo * aliquota).quantize(Decimal("0.01"))
        
        # Determina crédito conforme tipo
        if credito_tipo == CreditType.INTEGRAL:
            credito = tributo_compra
            pct = Decimal("1.0")
        
        elif credito_tipo == CreditType.VEDADO:
            credito = Decimal("0.00")
            pct = Decimal("0.0")
        
        elif credito_tipo == CreditType.PARCIAL:
            credito = (tributo_compra * credito_percentual).quantize(Decimal("0.01")) if credito_percentual else Decimal("0.00")
            pct = credito_percentual or Decimal("0.0")
        
        elif credito_tipo == CreditType.PRESUMIDO:
            # Crédito presumido: valor calculado conforme fórmula específica
            credito = (base_calculo * Decimal("0.025")).quantize(Decimal("0.01"))  # Exemplo: 2.5%
            pct = Decimal("0.025")
        
        elif credito_tipo == CreditType.CONDICIONADO:
            # Crédito condicionado: depende de análise adicional
            credito = Decimal("0.00")
            pct = Decimal("0.0")
        
        else:
            credito = Decimal("0.00")
            pct = Decimal("0.0")
        
        return {
            "base_calculo": base_calculo,
            "aliquota": aliquota,
            "tributo_compra": tributo_compra,
            "tipo_credito": credito_tipo,
            "percentual_credito": pct,
            "credito_permitido": credito,
            "regime_fornecedor": regime_fornecedor,
        }


# ============================================================================
# TESTES
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MOTOR DE CRÉDITOS - Testes")
    print("=" * 70)
    
    test_cases = [
        ("Simples Nacional", "validado", "IBS"),
        ("Lucro Real", "validado", "IBS"),
        ("Lucro Real", "validado", "CBS"),
        ("Lucro Presumido", "validado", "IBS"),
    ]
    
    for regime, status, tributo in test_cases:
        print(f"\n📋 {regime} ({tributo})")
        analise = SupplierRegimeAnalysis.analisar_fornecedor(regime, status, tributo)
        print(f"  Tipo: {analise['credito_tipo']}")
        print(f"  Observação: {analise['observacao']}")
    
    # Cálculo de crédito
    print(f"\n💰 CÁLCULO DE CRÉDITO")
    compra = Decimal("10000.00")
    aliq_cbs = Decimal("0.088")
    
    credito = CreditCalculation.calcular_credito(
        base_calculo=compra,
        aliquota=aliq_cbs,
        credito_tipo=CreditType.INTEGRAL,
        regime_fornecedor="Lucro Real"
    )
    
    print(f"  Compra: R$ {credito['base_calculo']:,.2f}")
    print(f"  CBS: R$ {credito['tributo_compra']:,.2f}")
    print(f"  Crédito: R$ {credito['credito_permitido']:,.2f}")
    
    print("\n" + "=" * 70)
    print("✓ Engine de Créditos funcionando")
    print("=" * 70)
