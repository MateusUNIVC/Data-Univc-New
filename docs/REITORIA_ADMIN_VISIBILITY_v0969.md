# Data UNIVC v0.9.6.9 — Reitoria Administration & Directorate Visibility

## Objetivo

Esta release fecha duas lacunas da camada Identity & Access V2 sem alterar o schema 33:

1. a Reitoria ganha uma área administrativa própria para criar e manter usuários completos;
2. a DPE pode ficar temporariamente fora da publicação sem perda de código, dados ou autorizações históricas.

## Área da Reitoria

A rota canônica é `/reitoria`. `/admin/users` permanece por compatibilidade, mas usa a mesma página.

O workspace contém:

- Visão geral de usuários ativos, usuários com edição e sessões;
- atalhos apenas para diretorias atualmente publicadas;
- Usuários e acessos;
- Auditoria de autenticação, identidade, permissões e sessões.

Quando uma identidade `REITORIA` entra sem solicitar uma diretoria explicitamente, o frontend direciona para `/reitoria` em vez de usar DTNH como tela administrativa improvisada.

## Criação e manutenção de identidades

`auth/identity_admin.py` encapsula chamadas server-side ao Supabase Admin Auth. A `SUPABASE_SERVICE_ROLE_KEY` fica exclusivamente no backend.

### Novo usuário

Fluxo:

```text
Reitoria
  -> valida nome/e-mail/senha/grants
  -> Supabase Admin Auth cria identidade
  -> Profile/AppUser são vinculados ao mesmo UUID
  -> UserDirectorateAccess recebe READ/EDIT e principal
  -> auditoria registra USER_PROVISIONED
```

Campos suportados:

- nome completo;
- e-mail;
- senha inicial (mínimo 8 caracteres no Data UNIVC);
- tipo `DIRECTORATE` ou `REITORIA`;
- ativo/bloqueado;
- `NONE`, `READ` ou `EDIT` por diretoria visível;
- diretoria principal.

A senha é transmitida diretamente ao Admin Auth e nunca é persistida no banco local ou na auditoria.

### Usuário existente

A Reitoria pode alterar nome, e-mail, senha, tipo, status e grants. Senha em branco significa preservar a senha existente; a senha atual nunca é exibida.

Mudanças de autorização usam `permission_version` e revogação de sessões já existentes. Mudanças de e-mail/senha também forçam revogação para evitar sessão antiga sobrevivendo a uma troca de credencial.

O backend valida o novo papel e os grants antes de chamar o provedor externo, reduzindo estados parciais entre Supabase Auth e o banco do Data UNIVC.

## Foto de perfil

Avatares usam caminho determinístico:

```text
users/<app_user_id>/avatar
```

no bucket privado configurado por `SUPABASE_AVATAR_BUCKET` (padrão `data-univc-avatars`). Como o caminho é determinístico, nenhuma coluna adicional é necessária e o schema permanece 33.

Regras:

- JPEG, PNG e WEBP;
- limite de 2 MB;
- validação do tipo declarado e da assinatura binária;
- bucket privado;
- download via `/api/profile/avatar/{user_id}` exige sessão válida do Data UNIVC;
- interfaces usam as iniciais do nome quando o objeto não existe.

## Visibilidade de diretorias

`security.py` mantém `OPERATING_DIRECTORATE_CODES` como catálogo de domínio e aplica uma segunda dimensão: visibilidade/publicação.

```text
HIDDEN_DIRECTORATE_CODES=DPE
```

faz a DPE permanecer existente, mas indisponível na experiência ativa.

### Enquanto DPE estiver oculta

- não aparece em `available_directorates` de `/api/auth/me`;
- não aparece em seletor/troca de diretoria;
- não aparece na Área da Reitoria nem no editor de novos grants;
- `/dpe` retorna indisponível;
- resolução de escopo DPE nas APIs retorna 404;
- grants já existentes não são apagados.

### Preservação de grants ocultos

Ao editar um usuário de diretoria, o backend combina os novos grants visíveis com grants ocultos já armazenados. Se o usuário ganha uma diretoria visível, o grant oculto deixa de ser principal, mas permanece armazenado. Se o usuário tinha somente acesso oculto, nome/e-mail/senha ainda podem ser editados sem obrigar a conceder outra diretoria.

A UI informa apenas que existem acessos ocultos preservados, mantendo a DPE fora dos controles publicados.

## Segurança

- `SUPABASE_SERVICE_ROLE_KEY` não aparece em templates ou assets estáticos;
- operações administrativas continuam `REITORIA`-only;
- self-demotion/self-disable da Reitoria é bloqueado pela tela/API;
- e-mail duplicado é rejeitado antes da mutação;
- password não existe em `AppUser`/`Profile`;
- fotos são privadas e passam pelo backend autenticado;
- alterações relevantes entram no log de auditoria.

## Compatibilidade

- schema: `33`;
- migration canônica: `033_identity_access_security_rebase.sql`;
- nenhuma `034` foi criada;
- permissões continuam `REITORIA` / `DIRECTORATE` e `READ` / `EDIT`;
- DTNH, DCS, DADM, DM e seus Excel/fluxos não mudam de domínio;
- DPE é ocultada, não removida.

## Reativação futura da DPE

Basta retirar `DPE` de `HIDDEN_DIRECTORATE_CODES` e reiniciar/publicar a aplicação. Os grants preservados voltam a ser considerados na navegação/autorização sem recadastro.
