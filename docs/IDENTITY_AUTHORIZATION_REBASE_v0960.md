# Identity, Session & Authorization Rebase — v0.9.6.0

## Base e objetivo

A v0.9.6.0 usa a **v0.8.33.0 DM Excel V2** como base oficial. O objetivo é portar as garantias de identidade e autorização conquistadas na linha v0.9.x sem substituir os avanços de domínio, SEI, UI e Excel feitos entre v0.8.29 e v0.8.33.

## Arquitetura

```text
e-mail + senha
  -> Supabase Auth (somente login)
  -> Data UNIVC
  -> access JWT local + refresh opaco rotativo
  -> app_users + user_directorate_access
  -> AuthorizationContext
  -> autorização por diretoria + por objeto
```

`REITORIA` possui acesso global. `DIRECTORATE` depende somente de grants explícitos. `READ` consulta; `EDIT` consulta e altera. Não há cross-read implícito por papel legado.

## Migration consolidada

A v0.8.33.0 já usa `032_dm_domain_simplification_v08290.sql`, então as antigas migrations 032–035 da linha paralela não podem ser reaplicadas. A rebase cria `033_identity_access_security_rebase.sql`, contendo o estado final necessário para esta etapa:

- `app_users`;
- `user_directorate_access`;
- `auth_sessions`;
- `auth_audit_log`;
- ownership de `survey_imports` e `survey_runs`;
- constraints/índices correspondentes;
- atualização do trigger de novos usuários;
- ledger de schema 33.

A migração de perfis existentes é conservadora: não promove `admin` legado automaticamente a `REITORIA`.

## Proteções

Routers dedicados usam escopo fixo: DM=DM, DPE=DPE e DADM=DADM. Recursos carregados por ID passam por ownership checks, impedindo que um grant válido em uma diretoria seja usado para buscar objetos pertencentes a outra.

## O que foi preservado da v0.8.33

- domínio DM `Ativo`, `Titulado`, `Desligado`;
- `_reconcile_cohort_statuses` e encerramento/reabertura automática das turmas;
- integração SEI e iconografia compartilhada v0.8.31;
- identidade visual DM v0.8.32;
- Excel V2 DM v0.8.33 com 8 abas;
- Excel V2 acadêmico DTNH/DCS.

## Compatibilidade transitória

O frontend ainda não foi migrado nesta release. `/api/auth/me` entrega o contrato V2 canônico e, temporariamente, aliases usados pelo JavaScript 8.33. O enforcement CSRF também permanece desligado até que todos os writes usem o wrapper compartilhado na v0.9.6.1.

## Próxima etapa

A v0.9.6.1 deverá portar `data-univc-auth.js`, `data-univc-identity.js`, painel de usuários/acessos da Reitoria, CSRF end-to-end e o ambiente local de contas de teste, removendo então a dependência frontend dos aliases legados.
