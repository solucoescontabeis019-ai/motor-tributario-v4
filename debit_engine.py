"""
Motor Tributário v4.0 - Debit Calculation Engine
Calcula débitos de IBS/CBS nas vendas
"""

from decimal import Decimal
from typing import Dict, Optional
from enum import Enum


class DebitCalculation:
    """Calcula débitos sobre operações de saída"""

    @staticmethod
    def calcular_debito(
        valor_operacao: Decimal,
        aliquota: Decimal,
        tipo_operacao: str = "venda_produto",
        regime_cliente: Optional[str] = None,
    ) -> Dict:
        """
        Calcula débito de IBS/CBS na saída
        
        Args:
            valor_operacao: Valor total da venda/serviço
            aliquota: Alíquota (0.001 para IBS, 0.088 para CBS)
            tipo_operacao: "venda_produto", "prestacao_servico", "exportacao", etc
            regime_cliente: Regime do cliente (para referência)
        
        Returns:
            {
                "valor_operacao": valor,
                "aliquota": aliquota,
                "debito": valor_devido,
                "tipo": tipo,
                "observacao": ""
            }
        """
        
        # Operações de exportação podem ter alíquota zero
        if tipo_operacao == "exportacao":
            debito = Decimal("0.00")
            observacao = "Exportação: IBS/CBS 0%"
        
        elif tipo_operacao == "operacao_isenta":
            debito = Decimal("0.00")
            observacao = "Operação isenta conforme legislação"
        
        else:
            # Venda normal: débito = valor × alíquota
            debito = (valor_operacao * aliquota).quantize(Decimal("0.01"))
            observacao = f"Débito de {tipo_operacao}"
        
        return {
            "valor_operacao": valor_operacao,
            "aliquota": aliquota,
            "debito": debito,
            "tipo_operacao": tipo_operacao,
            "regime_cliente": regime_cliente,
            "observacao": observacao,
        }

    @staticmethod
    def calcular_debito_total(
        vendas_por_tipo: Dict[str, Decimal],
        aliquota: Decimal,
    ) -> Dict:
        """
        Calcula total de débitos por tipo de operação
        
        vendas_por_tipo = {
            "venda_produto": 1000000,
            "prestacao_servico": 500000,
            "exportacao": 200000,
        }
        """
        
        total_vendas = Decimal("0.00")
        total_debito = Decimal("0.00")
        detalhamento = {}
        
        for tipo, valor in vendas_por_tipo.items():
            calculo = DebitCalculation.calcular_debito(valor, aliquota, tipo)
            total_vendas += valor
            total_debito += calculo["debito"]
            detalhamento[tipo] = calculo
        
        return {
            "total_vendas": total_vendas,
            "total_debito": total_debito,
            "aliquota": aliquota,
            "detalhamento": detalhamento,
            "taxa_efetiva": (total_debito / total_vendas) if total_vendas > 0 else Decimal("0.00"),
        }


# ============================================================================
# TESTES
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MOTOR DE DÉBITOS - Testes")
    print("=" * 70)
    
    # Teste simples
    print("\n📊 DÉBITO SIMPLES")
    debito = DebitCalculation.calcular_debito(
        valor_operacao=Decimal("100000.00"),
        aliquota=Decimal("0.088"),
        tipo_operacao="venda_produto"
    )
    print(f"  Venda: R$ {debito['valor_operacao']:,.2f}")
    print(f"  CBS: R$ {debito['debito']:,.2f}")
    
    # Teste múltiplos tipos
    print("\n📈 DÉBITO MÚLTIPLOS TIPOS")
    vendas = {
        "venda_produto": Decimal("1150693.77"),
        "prestacao_servico": Decimal("308320.90"),
        "exportacao": Decimal("50000.00"),
    }
    
    totais = DebitCalculation.calcular_debito_total(vendas, Decimal("0.088"))
    print(f"  Total vendas: R$ {totais['total_vendas']:,.2f}")
    print(f"  Total CBS: R$ {totais['total_debito']:,.2f}")
    print(f"  Taxa efetiva: {totais['taxa_efetiva']:.4%}")
    
    print("\n" + "=" * 70)
    print("✓ Engine de Débitos funcionando")
    print("=" * 70)
