# Relatório PDF por cliente

Após **Calcular comparação**, o sistema prepara o PDF e habilita **Baixar relatório para o cliente**. O relatório apresenta o resultado da simulação, uma sugestão condicionada às premissas, os três maiores compradores com movimento no período e argumentos comerciais. A decisão final permanece com o empresário, orientado pela contabilidade.

- Reutiliza os cálculos existentes; não altera registros nem regras tributárias.
- Usa somente os documentos e compradores do cliente selecionado, no período da comparação.
- Uma nova comparação, edição de premissas, mudança de cliente ou atualização de documentos invalida o arquivo anterior.
- O servidor confere se o resultado continua igual ao exibido. Se os valores mudaram, pede nova comparação.
- Não exporta uma competência diferente da usada pelo PGDAS histórico. Para o PDF, use ano ou competência mensal.
- Créditos dos compradores são hipóteses comerciais, não créditos efetivos ou perdas garantidas.
- O endpoint mantém a autenticação existente e retorna o arquivo em memória com `Cache-Control: no-store`.
- Falhas de geração não impedem a comparação nem o uso do painel.

## Instalação

A dependência `reportlab>=4.2,<5` foi incluída em `requirements.txt`. O próximo build Docker instala a biblioteca. Nenhuma migração de banco é necessária.

## Testes

Com as dependências do projeto e `pypdf` instaladas:

```text
python -m unittest test_relatorio_pdf.py
node test_pdf_frontend.cjs
```

Os testes usam banco SQLite temporário e empresas fictícias. Cobrem isolamento entre clientes e períodos, autenticação, comparação desatualizada, ausência de dados, falha de exportação, recomendações dinâmicas, nomes longos, duas páginas e ausência de alterações no banco. O teste do navegador simula download, troca de cliente, respostas atrasadas e falhas de geração.

Arquivos de produção: `app_v4.py`, `dashboard_v4.html`, `relatorio_cliente.py`, `requirements.txt`.
