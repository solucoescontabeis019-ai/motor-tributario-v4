# Motor Tributário v4 — fluxo por PDF

Sistema local e multicliente para organizar documentos de 2026, conferir a extração e preparar a comparação entre Simples e a opção híbrida. O fluxo aceita apenas PDFs.

## Iniciar

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app_v4:app --reload
```

Abra `http://127.0.0.1:8000/`. A documentação técnica da API está em `http://127.0.0.1:8000/docs`.

## Fluxo de trabalho

1. Cadastre o CNPJ e a razão social do cliente.
2. Envie PDFs de PGDAS-D, acompanhamento de entradas e acompanhamento de saídas. Relações de fornecedores e clientes são opcionais, mas melhoram a conferência cadastral.
3. Confira a extração. PDFs com leitura parcial não habilitam cálculo automaticamente; registre a confirmação humana, mantendo o original e a extração inicial.
4. Consulte a consolidação por CNPJ, com documento, página e linha de origem.
5. Crie a análise. O sistema registra os valores históricos do PGDAS quando disponíveis e bloqueia projeções até que existam documentos, regras tributárias versionadas, composição do DAS remanescente, bases de débito e créditos com evidência fiscal.

## Garantias do motor

- O DAS mensal usa a receita da competência, não a simples divisão anual por 12.
- O híbrido recebe o DAS remanescente; IBS/CBS não são somados ao DAS integral.
- Créditos sem evidência fiscal válida são rejeitados.
- Não há CNPJ ou regime de fornecedor pré-classificado no código.
- Uma alíquota de cenário não é tratada como alíquota oficial nem produz recomendação automática.
- Cada arquivo é preservado em base64 para permitir reprocessamento após evolução do extrator.

## Testes

```powershell
.\venv\Scripts\python.exe -m unittest -v test_tax_engine_audit.py
```

Os testes cobrem validação de CNPJ, DAS por competência, reconciliação de seções do PGDAS e cálculo híbrido com créditos documentados.

## Estado atual

O sistema já é utilizável para cadastro de clientes, carga de PDFs, extração auditável, revisão manual, consolidação e registro da base real de 2026. A recomendação de opção híbrida fica propositalmente bloqueada até a validação técnica das regras e dos créditos aplicáveis ao cliente.
