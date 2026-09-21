-- ETAPA 2 - INSERÇÃO DAS REGRAS DE CRÉDITO IBS/CBS
-- Motor Tributário v3.0 - Matriz de Elegibilidade

INSERT INTO ibs_cbs_rules (regime_fornecedor, tipo_tributo, tipo_credito, percentual_credito, tax_rule_id, status, observacoes) VALUES

('Simples Nacional', 'IBS', 'INTEGRAL', 100.00,
 (SELECT id FROM tax_rules WHERE codigo = 'IBS_2027_OFICIAL'),
 'OFICIAL',
 'Art. 50, LC 214/2025 - Fornecedor Simples gera crédito integral de IBS'),

('Simples Nacional', 'CBS', 'PRESUMIDO', 30.00,
 (SELECT id FROM tax_rules WHERE codigo = 'CBS_2027_ESTIMADA'),
 'ESTIMADA',
 'Crédito presumido 30% conforme simulação conservadora. Valor sujeito a regulamentação'),

('Lucro Real', 'IBS', 'INTEGRAL', 100.00,
 (SELECT id FROM tax_rules WHERE codigo = 'IBS_2027_OFICIAL'),
 'OFICIAL',
 'Art. 50, LC 214/2025 - Crédito integral do IBS destacado'),

('Lucro Real', 'CBS', 'INTEGRAL', 100.00,
 (SELECT id FROM tax_rules WHERE codigo = 'CBS_2027_ESTIMADA'),
 'ESTIMADA',
 'Crédito integral da CBS destacada - regime regular'),

('Lucro Presumido', 'IBS', 'INTEGRAL', 100.00,
 (SELECT id FROM tax_rules WHERE codigo = 'IBS_2027_OFICIAL'),
 'OFICIAL',
 'Art. 50, LC 214/2025 - Crédito integral do IBS'),

('Lucro Presumido', 'CBS', 'INTEGRAL', 100.00,
 (SELECT id FROM tax_rules WHERE codigo = 'CBS_2027_ESTIMADA'),
 'ESTIMADA',
 'Crédito integral da CBS - regime regular'),

('MEI', 'IBS', 'INTEGRAL', 100.00,
 (SELECT id FROM tax_rules WHERE codigo = 'IBS_2027_OFICIAL'),
 'OFICIAL',
 'MEI em regime de transição gera crédito de IBS'),

('MEI', 'CBS', 'PRESUMIDO', 15.00,
 (SELECT id FROM tax_rules WHERE codigo = 'CBS_2027_ESTIMADA'),
 'ESTIMADA',
 'Crédito presumido reduzido para MEI - 15% conforme transição');
