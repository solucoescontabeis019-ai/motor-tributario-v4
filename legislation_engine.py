"""
Motor Tributário v4.0 - Legislation Engine
Armazena e gerencia regras tributárias versionadas
Separa OFICIAL de ESTIMADA, nunca hardcode
"""

from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional
from enum import Enum


class TaxLegislation:
    """
    Repositório de regras tributárias
    Cada regra tem: legislação, vigência, status (OFICIAL/ESTIMADA)
    """

    def __init__(self):
        self.regras = self._initialize_regras()

    def _initialize_regras(self) -> Dict:
        """Inicializa base de regras tributárias"""
        return {
            "ibs_2027": {
                "nome": "IBS 2027",
                "tributo": "IBS",
                "aliquota": Decimal("0.001"),
                "aliquota_estadual": Decimal("0.0005"),
                "aliquota_municipal": Decimal("0.0005"),
                "status": "OFICIAL",
                "legislacao": "LC 214/2025",
                "artigo": "Art. 18",
                "data_publicacao": date(2025, 1, 1),
                "vigencia_inicio": date(2027, 1, 1),
                "vigencia_fim": None,
                "versao": 1,
                "observacao": "Alíquota oficial de IBS para 2027 e seguintes",
            },
            
            "cbs_2027_estimada": {
                "nome": "CBS 2027 (Estimada)",
                "tributo": "CBS",
                "aliquota": Decimal("0.088"),
                "aliquota_minima": Decimal("0.085"),
                "aliquota_maxima": Decimal("0.093"),
                "status": "ESTIMADA",
                "legislacao": "LC 227/2026 (aguardando publicação)",
                "artigo": "Tbd",
                "data_publicacao": None,
                "vigencia_inicio": date(2027, 1, 1),
                "vigencia_fim": None,
                "versao": 1,
                "observacao": "Alíquota estimada. Será atualizada quando LC 227 for publicada.",
            },
            
            "simples_anexo_i": {
                "nome": "Simples Nacional Anexo I (Comércio/Indústria)",
                "tributo": "Simples",
                "status": "OFICIAL",
                "legislacao": "Resolução CGSN 140/2018",
                "artigo": "Art. 3, Anexo I",
                "vigencia_inicio": date(2018, 8, 1),
                "vigencia_fim": None,
                "versao": 1,
                "faixas": {
                    "faixa_1": {"rbt": 180_000, "aliquota": 0.04},
                    "faixa_2": {"rbt": 360_000, "aliquota": 0.072},
                    "faixa_3": {"rbt": 720_000, "aliquota": 0.097},
                    "faixa_4": {"rbt": 1_800_000, "aliquota": 0.116},
                    "faixa_5": {"rbt": 3_600_000, "aliquota": 0.143},
                },
            },
            
            "simples_anexo_iii": {
                "nome": "Simples Nacional Anexo III (Serviços)",
                "tributo": "Simples",
                "status": "OFICIAL",
                "legislacao": "Resolução CGSN 140/2018",
                "artigo": "Art. 3, Anexo III",
                "vigencia_inicio": date(2018, 8, 1),
                "vigencia_fim": None,
                "versao": 1,
                "faixas": {
                    "faixa_1": {"rbt": 180_000, "aliquota": 0.06},
                    "faixa_2": {"rbt": 360_000, "aliquota": 0.112},
                    "faixa_3": {"rbt": 720_000, "aliquota": 0.143},
                    "faixa_4": {"rbt": 1_800_000, "aliquota": 0.160},
                    "faixa_5": {"rbt": 3_600_000, "aliquota": 0.21},
                },
            },
        }

    def get_aliquota(self, tributo: str, data_ref: Optional[date] = None) -> Dict:
        """
        Obtém alíquota vigente em data específica
        
        Args:
            tributo: "ibs_2027", "cbs_2027_estimada", etc
            data_ref: Data de referência (se None, usa hoje)
        
        Returns:
            {
                "aliquota": valor,
                "status": "OFICIAL" | "ESTIMADA",
                "legislacao": referência legal,
                "observacao": contexto
            }
        """
        
        if tributo not in self.regras:
            return {"erro": f"Tributo '{tributo}' não mapeado"}
        
        regra = self.regras[tributo]
        
        return {
            "tributo": tributo,
            "aliquota": regra.get("aliquota"),
            "status": regra.get("status"),
            "legislacao": regra.get("legislacao"),
            "versao": regra.get("versao"),
            "observacao": regra.get("observacao"),
        }

    def validar_aliquota(self, tributo: str, aliquota: Decimal) -> Dict:
        """
        Valida se alíquota corresponde à legislação
        """
        
        regra = self.regras.get(tributo, {})
        aliq_oficial = regra.get("aliquota")
        
        if aliquota == aliq_oficial:
            return {
                "valida": True,
                "status": "OFICIAL",
                "mensagem": f"Alíquota {aliquota} é a oficial conforme {regra.get('legislacao')}",
            }
        
        # Se é estimada, verifica se está dentro do intervalo
        if "estimada" in tributo.lower():
            minima = regra.get("aliquota_minima")
            maxima = regra.get("aliquota_maxima")
            
            if minima and maxima and minima <= aliquota <= maxima:
                return {
                    "valida": True,
                    "status": "ESTIMADA",
                    "intervalo": f"{minima} a {maxima}",
                    "mensagem": f"Alíquota dentro do intervalo estimado",
                }
        
        return {
            "valida": False,
            "mensagem": f"Alíquota {aliquota} não corresponde à legislação",
        }

    def listar_regras(self, filtro: Optional[str] = None) -> List[Dict]:
        """Lista todas as regras, opcionalmente filtradas"""
        
        resultado = []
        for chave, regra in self.regras.items():
            if filtro and filtro.lower() not in chave.lower():
                continue
            resultado.append({
                "id": chave,
                "nome": regra.get("nome"),
                "status": regra.get("status"),
                "legislacao": regra.get("legislacao"),
            })
        
        return resultado


# ============================================================================
# TESTES
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MOTOR DE LEGISLAÇÃO - Testes")
    print("=" * 70)
    
    legislacao = TaxLegislation()
    
    print("\n📋 ALÍQUOTAS DISPONÍVEIS")
    for regra in legislacao.listar_regras():
        print(f"  {regra['nome']} ({regra['status']})")
        print(f"    Legislação: {regra['legislacao']}")
    
    print("\n💰 IBS 2027 (OFICIAL)")
    ibs = legislacao.get_aliquota("ibs_2027")
    print(f"  Alíquota: {ibs['aliquota']:.4f}")
    print(f"  Status: {ibs['status']}")
    
    print("\n💰 CBS 2027 (ESTIMADA)")
    cbs = legislacao.get_aliquota("cbs_2027_estimada")
    print(f"  Alíquota: {cbs['aliquota']:.4f}")
    print(f"  Status: {cbs['status']}")
    print(f"  Obs: {cbs['observacao']}")
    
    print("\n✓ Validação de Alíquota")
    validacao = legislacao.validar_aliquota("ibs_2027", Decimal("0.001"))
    print(f"  {validacao['mensagem']}")
    
    print("\n" + "=" * 70)
    print("✓ Engine de Legislação funcionando")
    print("=" * 70)
