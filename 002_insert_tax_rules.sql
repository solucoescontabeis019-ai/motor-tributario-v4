-- ETAPA 2 - INSERÇÃO DAS REGRAS TRIBUTÁRIAS
-- Motor Tributário v3.0 - Legislação Oficial

INSERT INTO tax_rules (codigo, descricao, legislacao, artigo, data_vigencia_inicio, status, versao, observacoes) VALUES

('SIMPLES_ANEXO_III_SECAO_IV', 
 'Simples Nacional - Anexo III - Seção IV (Locação, Serviços)',
 'Resolução CGSN 140/2018',
 'art. 12',
 '2018-01-01',
 'OFICIAL',
 1,
 'Alíquota nominal 10,2291% - Distribuição: IRPJ 5,5% + CSLL 3,5% + COFINS 0,7647% + PIS 0,3643% + INSS 0,1010%'),

('SIMPLES_ANEXO_III_SECAO_V',
 'Simples Nacional - Anexo III - Seção V (Transporte)',
 'Resolução CGSN 140/2018',
 'art. 12',
 '2018-01-01',
 'OFICIAL',
 1,
 'Alíquota nominal 13,7120% - Distribuição: IRPJ 7,3% + CSLL 4,7% + COFINS 0,6820% + PIS 0,3265% + INSS 0,7235%'),

('IBS_2027_OFICIAL',
 'Imposto sobre Bens e Serviços - 2027',
 'LC 214/2025 e EC 132/2023',
 'arts. 1-50',
 '2027-01-01',
 'OFICIAL',
 1,
 'Alíquota: 0,10% (Estadual 0,05% + Municipal 0,05%). Legislação oficial vigente.'),

('CBS_2027_ESTIMADA',
 'Contribuição Social sobre Bens e Serviços - 2027 (Estimativa)',
 'LC 227/2026',
 'arts. 1-100',
 '2027-01-01',
 'ESTIMADA',
 1,
 'Alíquota ESTIMADA: 8,80%. Legislação pendente de regulamentação final. Sujeita a alteração conforme publicação de LC de regulamentação.');
