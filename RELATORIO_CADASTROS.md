# Clientes e fornecedores analisados

Selecione a empresa e, em **4. Consolidação documental**, clique em **Baixar PDF de clientes e fornecedores**.

O PDF apresenta duas seções, com paginação automática: compradores e fornecedores cadastrados para a empresa selecionada que possuem valor movimentado acima de R$ 0,00. Inclui razão social, CNPJ, período registrado, valor movimentado, regime, validação e crédito estimado do cenário. A base é o cadastro consolidado, sem filtro mensal.

O crédito reutiliza os cálculos do endpoint de classificação, com as alíquotas informadas no painel. Quando não há cálculo automático elegível, o relatório indica **Não apurado automaticamente**, sem concluir que o direito ao crédito é zero.

Não altera cálculos ou registros, não refaz consultas externas de CNPJ, mantém a autenticação existente e gera o arquivo em memória. Trocar de empresa descarta respostas de download anteriores. Nenhuma dependência ou migração de banco adicional é necessária.

Testes (dependências do projeto e pypdf instalados):

```text
python -m unittest test_cadastros.py
node test_cadastros_frontend.cjs
```
