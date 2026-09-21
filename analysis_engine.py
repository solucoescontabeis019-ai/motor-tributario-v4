"""
Motor Tributário v4.0 - Analysis Engine
Análise comercial de risco, exposição e viabilidade
"""

from decimal import Decimal
from typing import Dict, List, Optional
from enum import Enum


class RiskLevel(str, Enum):
    """Níveis de risco comercial"""
    BAIXO = "baixo"
    MÉDIO = "médio"
    ALTO = "alto"
    CRÍTICO = "crítico"


class CommercialAnalysis:
    """Análise de impacto comercial do regime tributário"""

    @staticmethod
    def analisar_cliente(
        cnpj: str,
        faturamento: Decimal,
        percentual_faturamento: Decimal,
        regime: str,
        potencial_credito: Decimal,
    ) -> Dict:
        """
        Analisa risco comercial de cada cliente
        
        Critérios:
        - Percentual do faturamento (concentração)
        - Regime do cliente (interesse em crédito?)
        - Potencial de crédito
        - B2B vs B2C
        """
        
        # Determina nível de risco baseado em concentração
        if percentual_faturamento > 0.30:
            risk = RiskLevel.CRÍTICO
            motivo = "Cliente representa > 30% do faturamento"
        elif percentual_faturamento > 0.15:
            risk = RiskLevel.ALTO
            motivo = "Cliente representa 15-30% do faturamento"
        elif percentual_faturamento > 0.05:
            risk = RiskLevel.MÉDIO
            motivo = "Cliente representa 5-15% do faturamento"
        else:
            risk = RiskLevel.BAIXO
            motivo = "Cliente < 5% do faturamento"
        
        # Se regime é Lucro Real/Presumido, interesse em crédito aumenta risco
        if regime in ["Lucro Real", "Lucro Presumido"]:
            if risk in [RiskLevel.CRÍTICO, RiskLevel.ALTO]:
                motivo += " + Cliente em Lucro Real/Presumido (valoriza crédito)"
        
        return {
            "cnpj": cnpj,
            "faturamento": faturamento,
            "percentual_faturamento": percentual_faturamento,
            "percentual_faturamento_pct": f"{(percentual_faturamento * 100):.1f}%",
            "regime": regime,
            "potencial_credito": potencial_credito,
            "risco": risk.value,
            "motivo": motivo,
        }

    @staticmethod
    def analisar_carteira_clientes(
        clientes: List[Dict],
    ) -> Dict:
        """
        Analisa carteira total de clientes
        
        clientes = [
            {"cnpj": "...", "faturamento": 500000, "regime": "Lucro Real"},
            ...
        ]
        
        Returns:
            {
                "total_faturamento": valor,
                "clientes_alto_risco": count,
                "percentual_b2b": percentual,
                "concentração_top_3": percentual,
                "recomendação": ""
            }
        """
        
        total_fat = sum(c.get("faturamento", Decimal("0")) for c in clientes)
        
        # Top 3 clientes
        clientes_ordenados = sorted(
            clientes,
            key=lambda x: x.get("faturamento", Decimal("0")),
            reverse=True
        )
        top_3 = sum(c.get("faturamento", Decimal("0")) for c in clientes_ordenados[:3])
        concentracao_top_3 = (top_3 / total_fat * 100) if total_fat > 0 else Decimal("0")
        
        # Clientes alto risco
        alto_risco = sum(
            1 for c in clientes_ordenados
            if (c.get("faturamento", Decimal("0")) / total_fat * 100) > 15
        )
        
        # B2B (assume que cliente > 50k é B2B)
        b2b_count = sum(1 for c in clientes if c.get("faturamento", Decimal("0")) > 50_000)
        b2b_pct = (b2b_count / len(clientes) * 100) if clientes else 0
        
        # Recomendação
        if concentracao_top_3 > 80:
            recomendacao = "⚠️ ALTA CONCENTRAÇÃO: Proteja relacionamento com top 3 clientes"
        elif alto_risco >= 3:
            recomendacao = "⚠️ RISCO MÚLTIPLO: 3+ clientes significativos podem ser impactados"
        elif b2b_pct > 70:
            recomendacao = "✓ PERFIL B2B: Regime híbrido pode ser atrativo"
        else:
            recomendacao = "✓ CARTEIRA DIVERSIFICADA: Risco distribuído"
        
        return {
            "total_clientes": len(clientes),
            "total_faturamento": total_fat,
            "clientes_alto_risco": alto_risco,
            "percentual_b2b": f"{b2b_pct:.1f}%",
            "concentração_top_3": f"{concentracao_top_3:.1f}%",
            "recomendação": recomendacao,
        }

    @staticmethod
    def analisar_fornecedores(
        fornecedores: List[Dict],
    ) -> Dict:
        """
        Analisa potencial de crédito dos fornecedores
        
        fornecedores = [
            {"cnpj": "...", "compras": 100000, "regime": "Lucro Real", "credito_ibs": 100},
            ...
        ]
        """
        
        total_compras = sum(f.get("compras", Decimal("0")) for f in fornecedores)
        total_credito = sum(f.get("credito_ibs", Decimal("0")) + f.get("credito_cbs", Decimal("0")) 
                           for f in fornecedores)
        
        # Fornecedores por regime
        regime_simples = sum(1 for f in fornecedores if "Simples" in f.get("regime", ""))
        regime_regular = sum(1 for f in fornecedores if "Lucro" in f.get("regime", ""))
        
        # Concentração
        fornecedores_ord = sorted(fornecedores, 
                                  key=lambda x: x.get("compras", Decimal("0")), 
                                  reverse=True)
        top_3_compras = sum(f.get("compras", Decimal("0")) for f in fornecedores_ord[:3])
        concentracao = (top_3_compras / total_compras * 100) if total_compras > 0 else 0
        
        return {
            "total_fornecedores": len(fornecedores),
            "total_compras": total_compras,
            "total_credito": total_credito,
            "credito_potencial_pct": f"{(total_credito / total_compras * 100):.2f}%" if total_compras > 0 else "0%",
            "fornecedores_simples": regime_simples,
            "fornecedores_regular": regime_regular,
            "concentração_top_3": f"{concentracao:.1f}%",
        }


class HybridViability:
    """Determina viabilidade econômica do regime híbrido"""

    @staticmethod
    def calcular_breakeven(
        compras_totais: Decimal,
        aliquota_ibs: Decimal,
        aliquota_cbs: Decimal,
        percentual_compras_elegivel: Decimal,
        economia_estimada: Decimal,
    ) -> Dict:
        """
        Calcula ponto de equilíbrio: a partir de quanto o híbrido é melhor?
        """
        
        # Se não há créditos, híbrido é pior
        if percentual_compras_elegivel == 0:
            return {
                "breakeven": None,
                "mensagem": "❌ Não há compras elegíveis para crédito. Simples é melhor.",
            }
        
        # Crédito potencial
        credito_potencial = (
            compras_totais * 
            percentual_compras_elegivel * 
            (aliquota_ibs + aliquota_cbs)
        )
        
        # Breakeven: quanto de compras precisa ser elegível
        # para que o crédito pague os custos do híbrido?
        
        return {
            "compras_totais": compras_totais,
            "percentual_elegivel": percentual_compras_elegivel,
            "credito_potencial": credito_potencial,
            "economia_estimada": economia_estimada,
            "viavel": economia_estimada > 0,
            "recomendação": "✓ Híbrido viável" if economia_estimada > 0 else "❌ Simples melhor",
        }


# ============================================================================
# TESTES
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MOTOR DE ANÁLISE COMERCIAL - Testes")
    print("=" * 70)
    
    # Teste análise de cliente
    print("\n📊 CLIENTE INDIVIDUAL")
    cliente = CommercialAnalysis.analisar_cliente(
        cnpj="06.980.064/0001-XX",
        faturamento=Decimal("1641623.67"),
        percentual_faturamento=Decimal("0.73"),
        regime="Lucro Real",
        potencial_credito=Decimal("50000.00")
    )
    print(f"  Percentual: {cliente['percentual_faturamento_pct']}")
    print(f"  Risco: {cliente['risco'].upper()}")
    print(f"  Motivo: {cliente['motivo']}")
    
    # Teste carteira
    print("\n👥 CARTEIRA DE CLIENTES")
    clientes = [
        {"cnpj": "06.980.064/0001-XX", "faturamento": Decimal("1641623.67"), "regime": "Lucro Real"},
        {"cnpj": "11.222.333/0001-XX", "faturamento": Decimal("300000.00"), "regime": "Simples"},
        {"cnpj": "22.333.444/0001-XX", "faturamento": Decimal("150000.00"), "regime": "Lucro Real"},
    ]
    
    carteira = CommercialAnalysis.analisar_carteira_clientes(clientes)
    print(f"  Total: R$ {carteira['total_faturamento']:,.2f}")
    print(f"  B2B: {carteira['percentual_b2b']}")
    print(f"  Top 3: {carteira['concentração_top_3']}")
    print(f"  → {carteira['recomendação']}")
    
    print("\n" + "=" * 70)
    print("✓ Engine de Análise funcionando")
    print("=" * 70)
