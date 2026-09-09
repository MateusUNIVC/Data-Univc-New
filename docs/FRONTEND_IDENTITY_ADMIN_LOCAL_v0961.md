# Data UNIVC v0.9.6.1 — Frontend Identity, User Administration & Local Test Harness

Esta release conclui a ligação do frontend v0.8.33 com a arquitetura de identidade/autorização rebaseada na v0.9.6.0, sem substituir o domínio, SEI ou Excel V2 mais novos da DM.

## Identidade canônica no frontend

Todas as superfícies carregam `static/js/data-univc-auth.js` e `static/js/data-univc-identity.js` antes dos scripts específicos. `/api/auth/me` passa a expor somente o contrato canônico V2 (`user`, `role`, `directorates`, `available_directorates`, `home_directorate`, `global_access`, `permission_version`, `session_version`). Os aliases legados de papel/diretoria deixam de ser parte do contrato.

`data-univc-auth.js` mantém compatibilidade com os módulos v0.8.33 que ainda chamam `fetch()` diretamente: chamadas same-origin para `/api/*` são protegidas pelo bridge global, recebem CSRF em métodos mutáveis e fazem uma tentativa de refresh silencioso em `401` antes do retry.

## CSRF e sessão

O middleware ativa double-submit CSRF em `POST`, `PUT`, `PATCH` e `DELETE` autenticados. O access/refresh permanece HttpOnly; somente o cookie CSRF fica disponível ao JavaScript. A tela de login continua simples e não exibe credenciais, duração de sessão ou seletor de diretoria.

## Administração pela Reitoria

`/admin/users` e `/api/admin/*` são exclusivos de `REITORIA`. O painel permite consultar usuários, role global, grants por diretoria, READ/EDIT, status, sessões e auditoria. Alterações de autorização incrementam `permission_version` e revogam sessões do usuário afetado.

## Ambiente local de testes

O SOURCE inclui `INICIAR_DATA_UNIVC_TESTE.bat` e `RESETAR_DADOS_TESTE.bat`. O launcher usa `univc_test.db`, não apaga dados ao reiniciar e provisiona sete identidades locais: DTNH, DCS, DADM, Rodrigo Ghirardelli (DADM completa), DPE, DM e Reitoria. O provedor local recusa execução quando `ENVIRONMENT=production`.

A experiência local mantém a sessão por até 24 horas (`SESSION_ABSOLUTE_TTL_SECONDS=86400` e `SESSION_IDLE_TTL_SECONDS=86400`) enquanto o access JWT permanece curto e é renovado silenciosamente. O rate limit rígido fica desabilitado no launcher local.

O bootstrap da v0.8.33 preserva dois registros estruturais de curso do catálogo de Educação Física; isso é configuração estrutural, não carga demonstrativa. Turmas DM, alunos DM, NPS, resultados acadêmicos e avaliações docentes começam vazios.

## Schema

Não há migration nova. O schema permanece 33 e requer `database/033_identity_access_security_rebase.sql` sobre a base v0.8.33/schema 32.

## Deliberadamente fora desta release

- novo layout de três gráficos do NPS institucional DTNH/DCS;
- refinamento da prévia SEI da DM e data de abertura opcional pela UI;
- escopo DADM por setor e política final do token TALLOS.

Esses itens permanecem em blocos posteriores para evitar misturar regressões de negócio com a fundação de identidade do frontend.
