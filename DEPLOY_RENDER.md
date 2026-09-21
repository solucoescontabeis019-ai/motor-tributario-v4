# Publicação compartilhada no Render

Este projeto está preparado para abrir em uma URL HTTPS e usar PostgreSQL
persistente. O acesso exige usuário e senha; não publique sem essas variáveis.

1. Crie uma conta da empresa no Render e um repositório privado no GitHub.
2. Envie este projeto ao repositório, sem `venv`, arquivos `.db` ou `.env`.
3. No Render, escolha **New > Blueprint** e selecione o repositório. O arquivo
   `render.yaml` criará o serviço e o PostgreSQL.
4. Defina `APP_USERNAME` e `APP_PASSWORD` como segredos do serviço. Use uma
   senha exclusiva, longa e não reutilizada.
5. Faça o deploy. A URL fornecida pelo Render poderá ser compartilhada com a
   sócia; o navegador solicitará essas credenciais antes de abrir o painel.

## Dados já existentes

O banco local `motor_tributario_v4.db` não deve ser enviado ao Git. O banco
PostgreSQL inicia vazio. Após o Render criar a base, copie a URL de conexão
para `DATABASE_URL` no computador que contém os dados locais e rode:

```powershell
$env:DATABASE_URL='postgresql://...'
python migrate_sqlite_to_postgres.py
```

A migração copia os registros existentes e interrompe caso encontre dados no
destino; ela não apaga nem substitui informações remotas.

## Segurança operacional

- Mantenha o repositório privado.
- Não envie `APP_PASSWORD` por e-mail ou WhatsApp em texto aberto.
- Troque a senha quando uma pessoa deixar de ter acesso.
- Faça backup periódico do PostgreSQL e dos PDFs originais.
