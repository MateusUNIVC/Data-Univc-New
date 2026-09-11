# DADM v0.9.6.10 - producao sem Cron

Esta entrega promove o Prompt 3 para producao sem criar Cron Job ou qualquer segundo servico no Render.

## Arquitetura de producao

- Mantem somente o Web Service existente `univc-data-driven`.
- Mantem o schema PostgreSQL/Supabase 33; nao existe migration nova.
- Mantem usuarios, sessoes, atendimentos Tallos e demais dados existentes.
- A sincronizacao Tallos continua manual pela interface DADM e usa `POST /api/dadm/tallos/sync`.
- O backend executa a sincronizacao como BackgroundTask do FastAPI.
- Nao existe `TALLOS_CRON_ENABLED`, `type: cron` ou servico agendado nesta release.

## Variaveis Tallos no Web Service

Configure no Environment do mesmo servico Render:

- `TALLOS_API_TOKEN` - segredo obrigatorio para sincronizar;
- `TALLOS_BASE_URL=https://api.tallos.com.br`;
- `TALLOS_PAGE_LIMIT=49`;
- `TALLOS_REQUEST_TIMEOUT=60`;
- `TALLOS_REQUEST_RETRIES=4`;
- `TALLOS_CHUNK_DAYS=90`.

O `render.yaml` declara essas configuracoes no mesmo Web Service. Nenhum token e gravado no frontend.

## Atualizacao do projeto existente

A atualizacao deve apontar para o mesmo banco atual. Nao recrie o Supabase e nao apague tabelas.

Antes do deploy, preserve os valores atuais de `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY` e `DATA_UNIVC_JWT_SECRET`.

Depois do deploy, valide `/api/health/ready`, login e acesso ao DADM. Em seguida, abra a area de sincronizacao do DADM e sincronize um intervalo curto para confirmar o Tallos.

## Rollback

Como nao existe migration nova, o rollback consiste apenas em republicar a versao anterior do codigo. O schema permanece 33.
