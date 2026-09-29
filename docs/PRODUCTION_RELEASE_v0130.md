# Data UNIVC v0.13.0 — Release de Produção

## Base

- Aplicação: `0.13.0`
- Base acadêmica: `0.11.6.7`
- Schema esperado: `49`
- Migration registrada: `049_academic_faculty_context_scopes_v0130.sql`

## Variáveis obrigatórias

Defina no servidor, sem gravar segredos no repositório:

- `ENVIRONMENT=production`
- `AUTH_DISABLED=false`
- `COOKIE_SECURE=true`
- `REQUIRE_SCHEMA_VERSION=true`
- `AUTO_CREATE_DB=false`
- `ENABLE_API_DOCS=false`
- `LOGIN_RATE_LIMIT_ENABLED=true`
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`
- `DATA_UNIVC_JWT_SECRET` ou keyring JWT configurado
- `TALLOS_API_TOKEN` quando a sincronização DADM for utilizada

## Antes do deploy

1. Fazer backup completo do PostgreSQL/Supabase.
2. Confirmar que todas as migrations até schema 49 foram aplicadas.
3. Confirmar `AUTH_DISABLED=false`.
4. Confirmar HTTPS/Nginx e `COOKIE_SECURE=true`.
5. Confirmar segredos fortes fora do ZIP.
6. Rodar `python scripts/run_release_checks.py` na árvore fonte antes da publicação.

## Depois do deploy

1. Verificar `/api/health/ready`.
2. Fazer login real.
3. Abrir DTNH, DCS, DADM, DPE, DM e Reitoria conforme permissões.
4. Exportar pelo menos um Excel DPE e um Excel acadêmico.
5. Confirmar DADM/Tallos sem executar sincronização destrutiva.
6. Confirmar logs sem traceback.

## Rollback

Não faça rollback de código sem considerar migrations já aplicadas. Preserve o backup pré-deploy e reverta aplicação + banco de forma coordenada quando necessário.

## Docker Compose no VPS

O pacote inclui `docker-compose.production.yml` como serviço **somente da aplicação**. Ele não cria PostgreSQL local e utiliza a `DATABASE_URL` definida em `.env.production`. Isso permite continuar usando Supabase/PostgreSQL externo ou integrar o serviço ao compose já existente do VPS.

Exemplo de preparação:

```bash
cp .env.production.example .env.production
# editar .env.production com os segredos reais
docker compose -f docker-compose.production.yml config -q
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

A porta é publicada somente em `127.0.0.1:8000`, esperando Nginx/HTTPS na frente.
