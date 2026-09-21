-- ETAPA 2 - CRIAÇÃO DAS TABELAS DO MOTOR TRIBUTÁRIO
-- Motor Tributário v3.0 - PostgreSQL Schema
-- Validado: Setembro 18, 2026

CREATE TABLE IF NOT EXISTS tax_rules (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    descricao TEXT NOT NULL,
    legislacao VARCHAR(100),
    artigo VARCHAR(50),
    paragrafo VARCHAR(50),
    inciso VARCHAR(50),
    data_publicacao DATE,
    data_vigencia_inicio DATE NOT NULL,
    data_vigencia_fim DATE,
    status VARCHAR(20) CHECK (status IN ('OFICIAL', 'ESTIMADA', 'REVOGADA', 'PROVISORIA')),
    versao INT DEFAULT 1,
    fonte_url TEXT,
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS simples_secoes (
    id SERIAL PRIMARY KEY,
    anexo INT NOT NULL,
    secao VARCHAR(10) NOT NULL,
    descricao VARCHAR(255),
    aliquota_nominal DECIMAL(12, 8) NOT NULL,
    parcela_deducao DECIMAL(15, 2),
    rbt12_minima DECIMAL(15, 2),
    rbt12_maxima DECIMAL(15, 2),
    tax_rule_id INT REFERENCES tax_rules(id),
    composicao_tributos TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    cnpj VARCHAR(14) UNIQUE NOT NULL,
    razao_social VARCHAR(255) NOT NULL,
    nome_fantasia VARCHAR(255),
    uf VARCHAR(2) NOT NULL,
    municipio VARCHAR(100),
    cnae_principal VARCHAR(10),
    regime_tributario VARCHAR(50),
    simples_anexo INT,
    rbt12 DECIMAL(15, 2),
    faturamento_anual DECIMAL(15, 2),
    faturamento_mensal DECIMAL(15, 2),
    b2b_percentual DECIMAL(5, 2),
    data_cadastro DATE,
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS company_simples_sections (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    simples_secao_id INT NOT NULL REFERENCES simples_secoes(id),
    rba_anual DECIMAL(15, 2),
    rba_mes_corrente DECIMAL(15, 2),
    das_calculado DECIMAL(15, 2),
    data_consulta DATE,
    confianca_percentual INT DEFAULT 100,
    status VARCHAR(20) CHECK (status IN ('VALIDADO', 'ESTIMADO', 'PENDENTE')),
    memoria_calculo JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    cnpj VARCHAR(14) UNIQUE NOT NULL,
    razao_social VARCHAR(255) NOT NULL,
    uf VARCHAR(2),
    municipio VARCHAR(100),
    total_comprado DECIMAL(15, 2) DEFAULT 0,
    quantidade_notas INT DEFAULT 0,
    data_primeira_nota DATE,
    data_ultima_nota DATE,
    status VARCHAR(20) CHECK (status IN ('ATIVO', 'INATIVO', 'SUSPENSE')),
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS supplier_regimes (
    id SERIAL PRIMARY KEY,
    supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    regime VARCHAR(50) NOT NULL,
    data_consulta DATE NOT NULL,
    fonte VARCHAR(100),
    confianca_percentual INT DEFAULT 0,
    status VARCHAR(20) CHECK (status IN ('VALIDADO', 'PRESUMIDO', 'NÃO_VALIDADO')),
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS supplier_purchases (
    id SERIAL PRIMARY KEY,
    supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    numero_nf VARCHAR(50),
    data_nf DATE,
    valor DECIMAL(15, 2) NOT NULL,
    cfop VARCHAR(10),
    ncm VARCHAR(10),
    descricao TEXT,
    ibs_destacado DECIMAL(15, 2),
    cbs_destacado DECIMAL(15, 2),
    icms_destacado DECIMAL(15, 2),
    pis_destacado DECIMAL(15, 2),
    cofins_destacado DECIMAL(15, 2),
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ibs_cbs_rules (
    id SERIAL PRIMARY KEY,
    regime_fornecedor VARCHAR(50) NOT NULL,
    tipo_tributo VARCHAR(20) NOT NULL,
    tipo_credito VARCHAR(50) NOT NULL,
    percentual_credito DECIMAL(5, 2),
    tax_rule_id INT REFERENCES tax_rules(id),
    status VARCHAR(20) CHECK (status IN ('OFICIAL', 'ESTIMADA', 'REVOGADA')),
    observacoes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tax_rules_codigo ON tax_rules(codigo);
CREATE INDEX idx_tax_rules_status ON tax_rules(status);
CREATE INDEX idx_simples_secoes_anexo_secao ON simples_secoes(anexo, secao);
CREATE INDEX idx_companies_cnpj ON companies(cnpj);
CREATE INDEX idx_company_simples_sections_company ON company_simples_sections(company_id);
CREATE INDEX idx_suppliers_company_cnpj ON suppliers(company_id, cnpj);
CREATE INDEX idx_supplier_regimes_supplier ON supplier_regimes(supplier_id);
CREATE INDEX idx_supplier_purchases_supplier ON supplier_purchases(supplier_id);
CREATE INDEX idx_ibs_cbs_rules_regime_tributo ON ibs_cbs_rules(regime_fornecedor, tipo_tributo);

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_tax_rules_updated_at BEFORE UPDATE ON tax_rules
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trigger_simples_secoes_updated_at BEFORE UPDATE ON simples_secoes
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trigger_companies_updated_at BEFORE UPDATE ON companies
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trigger_company_simples_sections_updated_at BEFORE UPDATE ON company_simples_sections
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trigger_suppliers_updated_at BEFORE UPDATE ON suppliers
FOR EACH ROW EXECUTE FUNCTION update_timestamp();
