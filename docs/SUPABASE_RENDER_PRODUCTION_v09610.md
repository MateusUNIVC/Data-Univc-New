# Data UNIVC v0.9.6.10 — Supabase + Render em produção

## Objetivo

Publicar a v0.9.6.10 com Supabase PostgreSQL/Auth/Storage e Render, mantendo o schema 33 e permitindo que a própria Reitoria crie identidades reais no Supabase Auth.

## Correções desta release

A v0.9.6.10 resolve dois pontos de produção:

1. projetos Supabase novos usam `SUPABASE_SECRET_KEY=sb_secret_...`; a chave vai no header `apikey` e não é tratada como JWT;
2. o trigger `on_auth_user_created` da migration 033 já cria `profiles` e `app_users`. O endpoint da Reitoria agora reconhece essa linha sincronizada e aplica os grants, em vez de retornar conflito depois que o Auth já criou a conta.

Não existe migration 034. `SCHEMA_VERSION=33` e `033_identity_access_security_rebase.sql` continuam canônicos.

## Variáveis do Render

O Blueprint pede os segredos externos:

```text
DATABASE_URL
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_SECRET_KEY
```

O `render.yaml` configura automaticamente:

```text
ENVIRONMENT=production
REQUIRE_SCHEMA_VERSION=true
AUTH_DISABLED=false
COOKIE_SECURE=true
AUTO_CREATE_DB=false
DEFAULT_DIRECTORATE_CODE=DTNH
SUPABASE_AVATAR_BUCKET=data-univc-avatars
HIDDEN_DIRECTORATE_CODES=DPE
```

`DATA_UNIVC_JWT_SECRET` é gerado pelo Render com `generateValue: true` na primeira criação do Blueprint.

## Bootstrap da primeira Reitoria

A primeira Reitoria é a única conta que precisa ser criada fora do Data UNIVC, porque ainda não existe administrador para abrir `/reitoria`.

1. Supabase > Authentication > Users > Add user.
2. Crie o usuário da Reitoria com senha forte e e-mail confirmado.
3. Confirme que a identidade foi sincronizada:

```sql
select
  au.id,
  au.email,
  p.full_name,
  app.name,
  app.global_role,
  app.active
from auth.users au
left join public.profiles p on p.id = au.id
left join public.app_users app on app.id = au.id
where lower(au.email) = lower('SEU_EMAIL_DA_REITORIA');
```

4. Promova a conta:

```sql
update public.app_users
set
  name = 'Reitoria UNIVC',
  global_role = 'REITORIA',
  active = true
where lower(email) = lower('SEU_EMAIL_DA_REITORIA');

update public.profiles
set
  full_name = 'Reitoria UNIVC',
  role = 'admin',
  directorate_id = null
where lower(email) = lower('SEU_EMAIL_DA_REITORIA');
```

## Criar DADM e Rodrigo pela Reitoria

Depois do deploy, entre em `/reitoria` e use **Novo usuário**.

### dadm@ivc.br

```text
Tipo: DIRECTORATE
DADM: EDIT
Diretoria principal: DADM
```

O e-mail canônico `dadm@ivc.br` ativa automaticamente leitura limitada a:

```text
Financeiro
Secretaria Acadêmica
Mestrado
Negociação
Prouni / Nbolsa / Fies
Estágio
```

A ingestão TALLOS continua compartilhada/global; a restrição é de leitura no backend/SQL.

### rodrigo.ghirardelli@ivc.br

```text
Tipo: DIRECTORATE
DADM: EDIT
Diretoria principal: DADM
```

O e-mail canônico `rodrigo.ghirardelli@ivc.br` possui leitura integral da DADM: Financeiro, Negociações, Central de Atendimento e todos os demais departamentos presentes na base.

## Verificação

Após cada login consulte `/api/auth/me`.

DADM limitado deve apresentar:

```json
"data_scopes": {
  "DADM": {
    "full": false
  }
}
```

Rodrigo deve apresentar:

```json
"data_scopes": {
  "DADM": {
    "full": true,
    "departments": []
  }
}
```

Reitoria tem acesso global e administração de identidades.

## Segurança

- nunca versionar `.env`;
- nunca colocar `SUPABASE_SECRET_KEY` em frontend;
- `SUPABASE_URL` deve ser a raiz `https://<project-ref>.supabase.co`, sem `/rest/v1/`;
- `DATABASE_URL` usa o Session Pooler com `sslmode=require` no Render;
- DPE permanece apenas oculta, não removida.
