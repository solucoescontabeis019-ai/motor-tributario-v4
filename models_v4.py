"""
Motor Tributário v4.0 - Data Models (Pydantic + SQLAlchemy)
Schema multicliente genérico sem hardcodes.

Estrutura:
Client (empresa/usuário)
  ├── Analysis (análise realizada)
  │   └── Document (PGDAS, Entradas, Saídas, etc)
  ├── Supplier (fornecedor)
  └── Customer (cliente/comprador)
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, Date, DateTime, Text,
    ForeignKey, Enum, Boolean, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
import enum

# Base para modelos SQLAlchemy
Base = declarative_base()


# ============================================================================
# ENUMS
# ============================================================================

class DocumentType(str, enum.Enum):
    """Tipo de documento que pode ser carregado"""
    PGDAS = "pgdas"           # PGDAS-D (imposto Simples)
    ENTRADAS = "entradas"     # Relação de compras/notas
    SAIDAS = "saidas"         # Relação de vendas/notas
    FORNECEDORES = "fornecedores"  # Planilha de fornecedores
    CLIENTES = "clientes"     # Planilha de clientes/compradores


class AnalysisStatus(str, enum.Enum):
    """Status de uma análise"""
    INICIADA = "iniciada"
    PROCESSANDO = "processando"
    COMPLETA = "completa"
    COM_ERRO = "com_erro"
    PENDENTE_DADOS = "pendente_dados"


class DocumentStatus(str, enum.Enum):
    """Status de um documento"""
    RECEBIDO = "recebido"
    PROCESSANDO = "processando"
    PROCESSADO = "processado"
    ERRO = "erro"


class RegimesTributarios(str, enum.Enum):
    """Regimes tributários possíveis"""
    SIMPLES_NACIONAL = "Simples Nacional"
    LUCRO_REAL = "Lucro Real"
    LUCRO_PRESUMIDO = "Lucro Presumido"
    MEI = "MEI"
    ISENTO = "Isento"
    NÃO_VALIDADO = "Não Validado"


class ValidacaoStatus(str, enum.Enum):
    """Status de validação de regime"""
    VALIDADO = "validado"
    PRESUMIDO = "presumido"
    NÃO_VALIDADO = "não_validado"


# ============================================================================
# MODELS: Core
# ============================================================================

class Client(Base):
    """
    Cliente (empresa que está sendo analisada).
    Um cliente pode ter múltiplas análises.
    """
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação
    cnpj = Column(String(14), unique=True, index=True, nullable=False)  # Sem formatação
    razao_social = Column(String(255), nullable=False)
    nome_fantasia = Column(String(255), nullable=True)

    # Localização
    uf = Column(String(2), nullable=True)
    municipio = Column(String(255), nullable=True)

    # Informações tributárias (ao registrar o cliente)
    regime_atual = Column(String(50), default=RegimesTributarios.NÃO_VALIDADO.value)
    regime_validacao_status = Column(
        String(20),
        default=ValidacaoStatus.NÃO_VALIDADO.value
    )
    regime_validacao_data = Column(Date, nullable=True)
    regime_validacao_fonte = Column(String(255), nullable=True)  # Receita Federal, manual, etc

    # Atividade
    atividade_principal = Column(String(255), nullable=True)
    cnae = Column(String(10), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    analises = relationship("Analysis", back_populates="cliente")
    fornecedores = relationship("Supplier", back_populates="cliente")
    clientes = relationship("Customer", back_populates="cliente")

    def __repr__(self):
        return f"<Client {self.cnpj}: {self.razao_social}>"


class Analysis(Base):
    """
    Análise tributária de um cliente em um período.
    Contém os resultados de 2026 Real, 2027 Simples, 2027 Híbrido.
    """
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    cliente = relationship("Client", back_populates="analises")

    # Período analisado
    periodo = Column(String(20), nullable=False)  # Ex: "2026-01-a-08"

    # Status
    status = Column(
        String(20),
        default=AnalysisStatus.INICIADA.value,
        index=True
    )

    # Resultado agregado (JSON para flexibilidade)
    resultado = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    documentos = relationship("Document", back_populates="analise")

    def __repr__(self):
        return f"<Analysis {self.cliente_id} - {self.periodo} - {self.status}>"


class Document(Base):
    """
    Documento carregado (PGDAS, Entradas, Saídas, etc).
    Armazena conteúdo bruto e parsed.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    # O documento é recebido antes da análise. Vincular a uma análise é
    # opcional; exigir esse campo tornava impossível gravar o upload.
    analise_id = Column(Integer, ForeignKey("analyses.id"), nullable=True, index=True)
    analise = relationship("Analysis", back_populates="documentos")
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    # Tipo e período
    tipo = Column(String(20), nullable=False)  # pgdas, entradas, saidas, etc
    periodo = Column(String(20), nullable=True)  # Se aplicável

    # Conteúdo
    conteudo_raw = Column(String, nullable=True)  # Conteúdo original (texto ou base64)
    conteudo_parsed = Column(JSON, nullable=True)  # Dados extraídos

    # Status
    status = Column(
        String(20),
        default=DocumentStatus.RECEBIDO.value,
        index=True
    )
    erro_mensagem = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Document {self.tipo} - {self.periodo} - {self.status}>"


# ============================================================================
# MODELS: Fornecedores e Clientes
# ============================================================================

class Supplier(Base):
    """
    Fornecedor consolidado por CNPJ.
    Um cliente pode ter múltiplos fornecedores.
    """
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    cliente = relationship("Client", back_populates="fornecedores")

    # Identificação
    cnpj = Column(String(14), nullable=False, index=True)
    razao_social = Column(String(255), nullable=False)

    # Regime tributário
    regime = Column(String(50), default=RegimesTributarios.NÃO_VALIDADO.value)
    regime_validacao_status = Column(
        String(20),
        default=ValidacaoStatus.NÃO_VALIDADO.value
    )

    # Totais consolidados
    total_compras = Column(Numeric(15, 2), default=0)
    quantidade_notas = Column(Integer, default=0)

    # Período
    periodo = Column(String(20), nullable=True)  # Ex: "2026-01-a-08"

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Supplier {self.cnpj}: {self.razao_social} - R${self.total_compras}>"


class Customer(Base):
    """
    Cliente (comprador) consolidado por CNPJ.
    Um cliente da empresa pode ter múltiplas filiais (mesmo CNPJ raiz).
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    cliente = relationship("Client", back_populates="clientes")

    # Identificação
    cnpj_raiz = Column(String(8), index=True)  # CNPJ raiz (primeiros 8 dígitos)
    cnpj = Column(String(14), nullable=False, index=True)
    razao_social = Column(String(255), nullable=False)
    quantidade_filiais = Column(Integer, default=1)

    # Regime tributário
    regime = Column(String(50), default=RegimesTributarios.NÃO_VALIDADO.value)
    regime_validacao_status = Column(
        String(20),
        default=ValidacaoStatus.NÃO_VALIDADO.value
    )

    # Totais consolidados
    total_faturamento = Column(Numeric(15, 2), default=0)
    quantidade_notas = Column(Integer, default=0)
    percentual_faturamento = Column(Numeric(5, 2), default=0)  # %

    # Risco comercial
    risco_nivel = Column(String(20), default="BAIXO")  # CRÍTICO, ALTO, MÉDIO, BAIXO
    risco_observacao = Column(String, nullable=True)

    # Período
    periodo = Column(String(20), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Customer {self.cnpj}: {self.razao_social} - R${self.total_faturamento}>"


# ============================================================================
# MODELS: Legislação e Regras
# ============================================================================

class TaxRule(Base):
    """
    Regra tributária versionada.
    Cada regra tem: vigência, legislação, status (OFICIAL/ESTIMADA).
    """
    __tablename__ = "tax_rules"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação
    nome = Column(String(255), nullable=False)  # Ex: "CBS 2027", "IBS 2027"
    versao = Column(Integer, default=1)

    # Legislação
    lei_complementar = Column(String(20), nullable=True)  # Ex: "LC 214/2025"
    artigo = Column(String(50), nullable=True)
    observacoes = Column(String, nullable=True)

    # Valores
    aliquota = Column(Numeric(5, 4), nullable=True)  # Ex: 0.0880

    # Status e vigência
    status = Column(String(20), default="ESTIMADA")  # OFICIAL, ESTIMADA, REVOGADA
    vigencia_inicio = Column(Date, nullable=True)
    vigencia_fim = Column(Date, nullable=True)

    # Timestamps
    criada_em = Column(DateTime, default=datetime.utcnow)
    atualizada_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<TaxRule {self.nome} v{self.versao}: {self.aliquota} ({self.status})>"


# ============================================================================
# MODELS: Créditos e Débitos
# ============================================================================

class Credit(Base):
    """
    Crédito de IBS/CBS calculado por operação ou fornecedor.
    Rastreabilidade completa: qual documento, qual regra, quanto credita.
    """
    __tablename__ = "credits"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    fornecedor_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    # Tipo de crédito
    tributo = Column(String(20), nullable=False)  # IBS ou CBS
    tipo_credito = Column(String(50), nullable=True)  # INTEGRAL, PARCIAL, PRESUMIDO, VEDADO

    # Valores
    base_calculo = Column(Numeric(15, 2), nullable=False)
    aliquota = Column(Numeric(5, 4), nullable=False)
    valor_credito = Column(Numeric(15, 2), nullable=False)

    # Legislação
    regra_id = Column(Integer, ForeignKey("tax_rules.id"), nullable=True)

    # Período
    periodo = Column(String(20), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Credit {self.tributo} - R${self.valor_credito} ({self.tipo_credito})>"


class Debit(Base):
    """
    Débito de IBS/CBS calculado sobre vendas.
    """
    __tablename__ = "debits"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    cliente_id_comprador = Column(Integer, ForeignKey("customers.id"), nullable=True)

    # Tipo de débito
    tributo = Column(String(20), nullable=False)  # IBS ou CBS

    # Valores
    base_calculo = Column(Numeric(15, 2), nullable=False)
    aliquota = Column(Numeric(5, 4), nullable=False)
    valor_debito = Column(Numeric(15, 2), nullable=False)

    # Período
    periodo = Column(String(20), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Debit {self.tributo} - R${self.valor_debito}>"


# ============================================================================
# MODELS: Audit
# ============================================================================

class CalculationLog(Base):
    """
    Log de cada cálculo realizado (para auditoria).
    Permite reproduzir qualquer resultado exatamente.
    """
    __tablename__ = "calculation_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamento
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    analise_id = Column(Integer, ForeignKey("analyses.id"), nullable=True)

    # O que foi calculado
    tipo_calculo = Column(String(50), nullable=False)  # ex: "credito_fornecedor"

    # Entrada e saída
    entrada_json = Column(JSON, nullable=True)
    saida_json = Column(JSON, nullable=True)

    # Regra aplicada
    regra_id = Column(Integer, ForeignKey("tax_rules.id"), nullable=True)
    regra_versao = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<CalculationLog {self.tipo_calculo} - {self.cliente_id}>"
