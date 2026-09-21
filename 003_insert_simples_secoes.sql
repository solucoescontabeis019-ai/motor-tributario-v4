-- ETAPA 2 - INSERÇÃO DAS SEÇÕES SIMPLES NACIONAL
-- Motor Tributário v3.0 - Anexo III

INSERT INTO simples_secoes (anexo, secao, descricao, aliquota_nominal, parcela_deducao, rbt12_minima, rbt12_maxima, tax_rule_id, composicao_tributos) VALUES

(3, 'IV',
 'Serviços de locação, consultoria, contabilidade, auditoria',
 0.10229133,
 NULL,
 1800000.01,
 3600000.00,
 (SELECT id FROM tax_rules WHERE codigo = 'SIMPLES_ANEXO_III_SECAO_IV'),
 '{"IRPJ": 5.5, "CSLL": 3.5, "COFINS": 0.7647, "PIS": 0.3643, "INSS": 0.1010}'),

(3, 'V',
 'Transporte de cargas, frete, distribuição',
 0.13712036,
 NULL,
 1800000.01,
 3600000.00,
 (SELECT id FROM tax_rules WHERE codigo = 'SIMPLES_ANEXO_III_SECAO_V'),
 '{"IRPJ": 7.3, "CSLL": 4.7, "COFINS": 0.6820, "PIS": 0.3265, "INSS": 0.7235}');
