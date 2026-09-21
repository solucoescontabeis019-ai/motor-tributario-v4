"""
Motor Tributário v4.0 - Aggregador de Engines FASE 2

Este módulo centraliza todos os 5 engines de FASE 2:
1. tax_engine - Cálculo de Simples e Híbrido
2. credit_engine - Determinação de créditos
3. debit_engine - Cálculo de débitos
4. legislation_engine - Repositório de regras
5. analysis_engine - Análise comercial

Aliases para compatibilidade com app_v4.py
"""

from tax_engine import SimplesCalculation, HybridCalculation
from credit_engine import SupplierRegimeAnalysis, CreditCalculation
from debit_engine import DebitCalculation
from legislation_engine import TaxLegislation
from analysis_engine import CommercialAnalysis, HybridViability

# Aliases para compatibilidade com imports esperados em app_v4.py
TaxLegislationEngine = TaxLegislation
SimplesCalculationEngine = SimplesCalculation
HibridoCalculationEngine = HybridCalculation
CreditEngine = CreditCalculation
AnalysisEngine = CommercialAnalysis

__all__ = [
    'TaxLegislationEngine',
    'SimplesCalculationEngine',
    'HibridoCalculationEngine',
    'CreditEngine',
    'AnalysisEngine',
    # Também exportar classes originais
    'SimplesCalculation',
    'HybridCalculation',
    'SupplierRegimeAnalysis',
    'CreditCalculation',
    'DebitCalculation',
    'TaxLegislation',
    'CommercialAnalysis',
    'HybridViability',
]
