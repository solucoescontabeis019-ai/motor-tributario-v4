"""
Motor Tributário v4.0 - Configuração Global
Valores tributários vêm daqui, NÃO de hardcodes no código.
"""

from decimal import Decimal
from datetime import date
from typing import Optional
import os
from enum import Enum


class TaxStatus(str, Enum):
    """Status de uma alíquota tributária"""
    OFICIAL = "OFICIAL"
    ESTIMADA = "ESTIMADA"
    PROVISORIA = "PROVISORIA"
    REVOGADA = "REVOGADA"
    NÃO_VALIDADO = "NÃO_VALIDADO"


class TaxRates:
    """
    Taxa tributária com metadados completos.
    Nunca um número fixo sozinho - sempre com contexto.
    """

    def __init__(
        self,
        nome: str,
        valor: Decimal,
        status: TaxStatus,
        vigencia_inicio: date,
        vigencia_fim: Optional[date] = None,
        legislacao: str = "",
        observacoes: str = ""
    ):
        self.nome = nome
        self.valor = valor
        self.status = status
        self.vigencia_inicio = vigencia_inicio
        self.vigencia_fim = vigencia_fim
        self.legislacao = legislacao
        self.observacoes = observacoes

    def is_vigente(self) -> bool:
        """Verifica se taxa está em vigência"""
        hoje = date.today()
        if self.vigencia_inicio > hoje:
            return False
        if self.vigencia_fim and self.vigencia_fim < hoje:
            return False
        return True

    def __str__(self):
        return f"{self.nome}: {self.valor} ({self.status.value})"


class AppConfig:
    """Configuração da aplicação"""

    # ========================================================================
    # 2027 - ALÍQUOTAS
    # ========================================================================

    # IBS 2027 - OFICIAL (LC 214/2025)
    ibs_2027_aliquota = Decimal("0.0010")  # 0,10%
    ibs_2027_status = TaxStatus.OFICIAL
    ibs_2027_legislacao = "LC 214/2025"
    ibs_2027_observacoes = "0,05% estadual + 0,05% municipal. Padrão nacional."

    # CBS 2027 - CENÁRIO INTERNO
    # ⚠️ Não é alíquota legal automática e não pode ser usada sem uma TaxRule
    # versionada, com fonte, vigência e aprovação técnica.
    cbs_2027_aliquota = Decimal("0.088")  # 8,8% (ESTIMATIVA)
    cbs_2027_status = TaxStatus.ESTIMADA
    cbs_2027_legislacao = "Cenário interno - regra tributária pendente"
    cbs_2027_observacoes = (
        "Alíquota de cenário. Não representa uma alíquota oficial e deve ser "
        "substituída por uma regra versionada antes de qualquer recomendação."
    )

    # CBS 2027 - INTERVALO DE CONFIANÇA
    # Sistema pode rodar cenários otimista/base/pessimista
    cbs_2027_minima = Decimal("0.085")    # Cenário otimista
    cbs_2027_provavel = Decimal("0.088")  # Cenário base (atual)
    cbs_2027_maxima = Decimal("0.093")    # Cenário conservador

    # ========================================================================
    # SIMPLES NACIONAL 2027
    # ========================================================================

    # Continuará com mesmas alíquotas de 2026
    simples_anexo_iii_secao_iv_aliquota = Decimal("0.102291334606")  # ~10,23%
    simples_anexo_iii_secao_v_aliquota = Decimal("0.137195526562")   # ~13,72%

    # ========================================================================
    # PERCENTUAIS FIXOS - REMOVIDOS
    # ========================================================================
    #
    # ❌ NÃO HÁ MAIS:
    # - percentual_elegibilidade = 0,75 (75%)
    # - percentual_risco_critico = 0,30 (30%)
    # - percentual_credito_fornecedor_simples = 0,30 (30%)
    #
    # MOTIVO: Estes não são constantes, variam por legislação.
    # SOLUÇÃO: Usar TaxLegislationEngine para determinar o valor correto.

    # ========================================================================
    # DATABASE
    # ========================================================================

    # Em desenvolvimento, usar banco local sem depender de um PostgreSQL
    # configurado. Em produção, DATABASE_URL é obrigatória e deve apontar
    # para o PostgreSQL gerenciado.
    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///./motor_tributario_v4.db"
    )
    # Alguns provedores usam o esquema legado postgres://; o SQLAlchemy usa
    # postgresql:// para a conexão via psycopg2.
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]

    # ========================================================================
    # APLICAÇÃO
    # ========================================================================

    app_name = "Motor Tributário v4.0"
    app_version = "4.0.0"
    app_env = os.getenv("APP_ENV", "development")  # development, staging, production
    require_auth = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
    app_username = os.getenv("APP_USERNAME", "")
    app_password = os.getenv("APP_PASSWORD", "")

    # ========================================================================
    # VALIDAÇÃO DE CNPJ
    # ========================================================================

    # Qual serviço usar para validar regime tributário
    cnpj_consulta_modo = os.getenv("CNPJ_CONSULTA_MODO", "local")  # local ou receita_federal

    # Se modo = receita_federal, precisa credentials
    receita_federal_usuario = os.getenv("RECEITA_FEDERAL_USUARIO", "")
    receita_federal_senha = os.getenv("RECEITA_FEDERAL_SENHA", "")

    # ========================================================================
    # LIMITES E TIMEOUTS
    # ========================================================================

    # Tamanho máximo de arquivo de upload (bytes)
    max_arquivo_size = 50 * 1024 * 1024  # 50 MB

    # Timeout para consulta de CNPJ (segundos)
    cnpj_consulta_timeout = 30

    # ========================================================================
    # LOGGING
    # ========================================================================

    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE", "/tmp/motor_tributario_v4.log")


# Instância global de config
_config = None


def get_config() -> AppConfig:
    """Obtém instância global de configuração"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def get_tax_rate(nome: str) -> TaxRates:
    """
    Busca taxa tributária por nome.

    Nomes conhecidos:
    - IBS_2027
    - CBS_2027
    - SIMPLES_ANEXO_III_SECAO_IV
    - SIMPLES_ANEXO_III_SECAO_V
    """

    config = get_config()

    if nome == "IBS_2027":
        return TaxRates(
            nome="IBS 2027",
            valor=config.ibs_2027_aliquota,
            status=config.ibs_2027_status,
            vigencia_inicio=date(2027, 1, 1),
            legislacao=config.ibs_2027_legislacao,
            observacoes=config.ibs_2027_observacoes
        )

    elif nome == "CBS_2027":
        return TaxRates(
            nome="CBS 2027",
            valor=config.cbs_2027_aliquota,
            status=config.cbs_2027_status,
            vigencia_inicio=date(2027, 1, 1),
            legislacao=config.cbs_2027_legislacao,
            observacoes=config.cbs_2027_observacoes
        )

    elif nome == "SIMPLES_ANEXO_III_SECAO_IV":
        return TaxRates(
            nome="Simples Nacional - Anexo III, Seção IV",
            valor=config.simples_anexo_iii_secao_iv_aliquota,
            status=TaxStatus.OFICIAL,
            vigencia_inicio=date(2026, 1, 1),
            legislacao="Resolução CGSN 140/2018",
            observacoes="Locação de imóvel / Serviços"
        )

    elif nome == "SIMPLES_ANEXO_III_SECAO_V":
        return TaxRates(
            nome="Simples Nacional - Anexo III, Seção V",
            valor=config.simples_anexo_iii_secao_v_aliquota,
            status=TaxStatus.OFICIAL,
            vigencia_inicio=date(2026, 1, 1),
            legislacao="Resolução CGSN 140/2018",
            observacoes="Transporte de carga"
        )

    else:
        raise ValueError(f"Taxa tributária desconhecida: {nome}")


# ============================================================================
# VALORES POR CENÁRIO CBS
# ============================================================================

def get_cbs_otimista() -> Decimal:
    """Cenário otimista: CBS = 8,5%"""
    return get_config().cbs_2027_minima


def get_cbs_base() -> Decimal:
    """Cenário base: CBS = 8,8% (atual)"""
    return get_config().cbs_2027_provavel


def get_cbs_conservador() -> Decimal:
    """Cenário conservador: CBS = 9,3%"""
    return get_config().cbs_2027_maxima


# ============================================================================
# INFORMAÇÕES DE DEBUG
# ============================================================================

def print_config_info():
    """Imprime configuração para debug"""
    config = get_config()
    print("\n" + "="*80)
    print("CONFIGURAÇÃO TRIBUTÁRIA v4.0")
    print("="*80)
    print(f"IBS 2027: {config.ibs_2027_aliquota} ({config.ibs_2027_status.value})")
    print(f"CBS 2027: {config.cbs_2027_aliquota} ({config.cbs_2027_status.value})")
    print(f"  Mínima:     {get_cbs_otimista()}")
    print(f"  Base:       {get_cbs_base()}")
    print(f"  Máxima:     {get_cbs_conservador()}")
    print(f"Database: {config.database_url}")
    print("="*80 + "\n")


if __name__ == "__main__":
    print_config_info()
