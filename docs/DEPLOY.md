## v0.9.6.9 — Reitoria Administration & Directorate Visibility

Sem migration nova; schema permanece `33` com `033_identity_access_security_rebase.sql`.

### Variáveis de produção

Além das variáveis já existentes, configure no backend:

```text
SUPABASE_SERVICE_ROLE_KEY=<segredo server-side do projeto Supabase>
SUPABASE_AVATAR_BUCKET=data-univc-avatars
HIDDEN_DIRECTORATE_CODES=DPE
```

`SUPABASE_SERVICE_ROLE_KEY` é obrigatória para criar/alterar identidades pelo Data UNIVC e para o Storage privado de avatares. Nunca exponha essa chave em HTML, JavaScript ou variável pública. `render.yaml` declara a chave com `sync: false`, portanto o valor deve ser informado como segredo no serviço.

O bucket `data-univc-avatars` é criado automaticamente como privado na primeira gravação, caso ainda não exista. Pode-se definir outro nome por `SUPABASE_AVATAR_BUCKET`.

### Homologação pós-deploy

1. entre com um usuário `REITORIA` e confirme que o login abre `/reitoria`;
2. confirme que DTNH, DCS, DADM e DM aparecem em "Diretorias disponíveis" e que DPE não aparece;
3. tente abrir `/dpe` diretamente e confirme indisponibilidade enquanto `HIDDEN_DIRECTORATE_CODES=DPE`;
4. crie um novo usuário informando nome, e-mail, senha e `EDIT` em uma diretoria; saia e valide o login dessa conta;
5. altere o mesmo usuário para `READ`, confirme revogação das sessões e novo comportamento após login;
6. altere e-mail e senha e confirme que a credencial antiga deixa de ser a credencial válida;
7. envie/remova uma foto JPEG, PNG ou WEBP até 2 MB e confirme foto + fallback por iniciais;
8. edite um usuário que possuía grant DPE e confirme que a interface informa acesso oculto preservado sem apagar esse grant;
9. valide Auditoria e Sessões na Área da Reitoria;
10. confirme `/api/health/live` e `/api/health/ready` com versão `0.9.6.9` e schema `33`.

Para reexibir a DPE futuramente, remova `DPE` de `HIDDEN_DIRECTORATE_CODES` e publique/reinicie a aplicação. Não é necessário recriar dados ou grants.

## v0.9.6.8

Sem migration nova; schema permanece 33. A DM ganha `/api/dm/excel-interativo` como beta adicional, enquanto `/api/dm/excel` continua sendo o relatorio V2 oficial. Apos publicar, valide os dois downloads, confirme que Area/Turma/Data de corte iniciam `PARAMETROS` no V3 e que as bases tecnicas ficam ocultas. Teste tambem `METAS E PLANOS`, `INTEGRACAO SEI` e a ausencia dos campos legados de titulacao/diploma.

## v0.9.6.7

Sem migration nova; schema permanece 33. Após publicar, valide `/api/excel-interativo` tanto em DTNH quanto em DCS. Confirme que o arquivo DCS usa somente códigos `DCS-*`, catálogo DCS e nome `Painel_DCS_Interativo_beta.xlsx`, enquanto o benchmark geral UNIVC permanece agregado entre as duas diretorias. O Excel V2 continua em `/api/excel`.

## v0.9.6.6

O Excel Interativo V3 é um endpoint adicional e não exige migration. O schema continua em 33. Em produção, `/api/excel` continua sendo o Excel V2 e `/api/excel-interativo` é o beta DTNH.

## v0.9.6.5

Esta release não adiciona migration. O schema continua em `33` com `033_identity_access_security_rebase.sql`.

Após publicar/homologar:

1. entre como `dadm@ivc.br` e sincronize um período com atendimentos de `financeiro_12c84`, `secretaria_academica_a967b`, `mestrado_8155e`, `negociacao_b623`, `prouni_nbolsa_fies_9bc56` e/ou `estagio_80bc4`;
2. confirme que os fatos aparecem nos dashboards/filtros do usuário limitado;
3. confirme que `central_de_atendimento_95de6`, `secretaria_academica_ead_83f67`, `univc_digital_aa103` e demais setores continuam fora do escopo;
4. abra Governança > Mapeamento de departamentos e confira que o identificador técnico é preservado, enquanto o nome automático não exibe mais o sufixo hexadecimal;
5. confirme que nomes personalizados manualmente continuam intactos.

Não é necessário limpar a base. Um novo sync atualiza a normalização; a leitura já passa a reconhecer as chaves reais imediatamente.

## v0.9.6.4

Esta release não adiciona migration. O schema continua em `33` com `033_identity_access_security_rebase.sql`.

Após publicar/homologar:

1. entre como `dadm@ivc.br`, abra **Dados & integração**, informe um token TALLOS e valide/salve;
2. sincronize um período que contenha setores autorizados e não autorizados;
3. confirme que todos os registros foram persistidos, mas que o dashboard do `dadm@ivc.br` mostra somente os seis setores autorizados;
4. entre como `rodrigo.ghirardelli@ivc.br` e confirme que os mesmos registros aparecem integralmente;
5. confirme que ambos enxergam o mesmo histórico de sincronizações;
6. valide que `dadm@ivc.br` recebe `403` ao consultar manualmente um departamento fora do escopo ou ao tentar limpar a base/remover o token.

Em produção, a persistência de token continua obedecendo `local_token_management_enabled()`; se o ambiente exigir token por variável de servidor, configure `TALLOS_API_TOKEN` no runtime.

## v0.9.6.3

Esta release não adiciona migration. O schema continua em `33` com `033_identity_access_security_rebase.sql`. O deploy exige apenas atualização da aplicação/assets.

Após publicar, valide na DM: abrir Integração SEI, gerar uma prévia, sincronizar uma turma nova sem data, sincronizar outra com data opcional e confirmar que uma abertura existente só muda ao usar `Alterar`.

## v0.9.6.2

Esta release não adiciona migration. O schema continua em `33` com `033_identity_access_security_rebase.sql`. Para homologação, reutilize o launcher local da v0.9.6.1; os dados existentes são preservados. O deploy exige apenas atualização dos arquivos da aplicação e assets estáticos.

# Deploy — Data UNIVC v0.9.6.0

## Rebase de identidade — migration 033 obrigatória

Esta release parte da **v0.8.33.0/schema 32**. Antes de publicar em PostgreSQL/Supabase:

1. confirme que `database/032_dm_domain_simplification_v08290.sql` já foi aplicada;
2. faça backup;
3. execute uma única vez `database/033_identity_access_security_rebase.sql`;
4. configure `DATA_UNIVC_JWT_SECRET` ou, preferencialmente, `DATA_UNIVC_JWT_KEYS_JSON` + `DATA_UNIVC_JWT_ACTIVE_KID`;
5. mantenha `AUTH_DISABLED=false`, `COOKIE_SECURE=true`, `REQUIRE_SCHEMA_VERSION=true`;
6. publique a aplicação e confirme `/api/health/live` e `/api/health/ready` com schema esperado/atual **33**;
7. valide login, refresh, logout e um usuário `READ`/`EDIT` por diretoria.

### Escopo desta release

A v0.9.6.0 fecha o **backend** de identidade/autorização. O frontend ainda preserva a navegação 8.33 e os aliases transitórios de `/api/auth/me`. Não trate esta etapa como a conclusão do hardening do browser: wrapper de identidade, CSRF enforcement, administração pela Reitoria e launcher local entram na v0.9.6.1.

A DM deve ser verificada especialmente em `/api/dm/excel`, integração SEI, alunos/defesas e ciclo automático de turmas; esses recursos são preservados da v0.8.33.0 e não foram substituídos pela linha antiga 9.5.5.

---

# Deploy — Data UNIVC v0.8.18.0

## Query Performance — sem nova migration

A v0.8.18.0 mantém `SCHEMA_VERSION = 26`. Confirme que `database/026_schema_version_baseline_v08160.sql` já está aplicada.

Antes de publicar:

```text
python scripts/run_test_gate.py --profile release
```

Após o deploy, valide `/api/health/live`, `/api/health/ready`, o workspace Avaliação Docente, `/api/dadm/dashboard` e `/api/dpe/finance/dashboard` em uma janela de 12 meses. Para números absolutos de performance em produção, meça PostgreSQL/Supabase; `docs/PERFORMANCE_v08180.md` contém somente benchmarks sintéticos de regressão.

---

# Deploy — Data UNIVC v0.8.17.0

## Cleanup e Performance I — sem nova migration

A v0.8.17.0 mantém `SCHEMA_VERSION = 26`. Antes do deploy, confirme que a migration `026_schema_version_baseline_v08160.sql` já está aplicada e que `/api/health/ready` está compatível.

Esta release altera caminhos de leitura/importação, mas preserva contratos funcionais. Use o gate completo antes da publicação:

```text
python scripts/run_test_gate.py --profile release
```

No artefato PRODUCTION não existem testes/scripts de benchmark. No SOURCE, o benchmark pode ser reproduzido com:

```text
python scripts/benchmark_scalability.py --profile quick
python scripts/benchmark_scalability.py --profile stress --json-out docs/benchmark_v08170.json
```

Após o deploy valide `/api/health/live`, `/api/health/ready`, uma listagem de despesas DPE e uma importação acadêmica controlada antes de cargas grandes.

---

# Deploy — Data UNIVC v0.8.16.0

## Fundação arquitetural — migration 026 obrigatória em produção

A v0.8.16.0 não altera indicadores ou regras acadêmicas/financeiras/DM. Ela adiciona controles de confiabilidade para as próximas refatorações.

### Ordem obrigatória em PostgreSQL/Supabase

1. Faça backup do banco.
2. Confirme que as migrations anteriores, incluindo `025_dm_graduation_digital_diploma_v08130.sql`, já foram aplicadas.
3. Execute uma única vez:

```text
database/026_schema_version_baseline_v08160.sql
```

4. Só então publique o código v0.8.16.0.
5. Confirme `/api/health/live` e `/api/health/ready`.

O `ready` de produção agora exige:

```text
schema.expected = 26
schema.current = 26
schema.compatible = true
```

Se a 026 não tiver sido aplicada, `/api/health/ready` retorna **503 `schema_incompatible`** e o deploy não deve receber tráfego. Esse bloqueio é intencional: evita executar código novo contra um schema antigo.

### Artefatos

- **SOURCE**: para continuar desenvolvimento; contém testes, scripts e baseline, mas não bancos/caches.
- **PRODUCTION**: para deploy; contém somente runtime/config/migrations/docs/assets necessários e `release_manifest.json`.

Os dois ZIPs são flat (`app.py` diretamente na raiz). Não use mais a árvore inteira do repositório como pacote de produção.

### Gate de qualidade

```text
python scripts/run_test_gate.py --profile smoke
python scripts/run_test_gate.py --profile pr
python scripts/run_test_gate.py --profile release
```

`pytest.ini` descobre todos os `test_*.py`; os perfis controlam apenas a abrangência da execução.

---

# Deploy — Data UNIVC v0.8.15.1

## Redesign completo — sem nova migração

A v0.8.15.1 é uma release de frontend, cache busting e fingerprint. Não cria tabelas ou colunas novas. Se o ambiente já está na v0.8.13.x/v0.8.14.0, mantenha aplicada a migration `database/025_dm_graduation_digital_diploma_v08130.sql` e publique o novo código.

O Design System agora está ativo em DTNH/DCS, DADM, DPE e DM, além do workspace gerencial. Após o deploy confirme:

```text
/api/health/live
version = 0.8.15.1
build = <fingerprint de 12 caracteres>
```

O ZIP continua flat: `app.py`, `render.yaml`, `static/` e `templates/` devem ficar diretamente na raiz do deploy. Se CSS antigo permanecer após publicação, faça um novo deploy/restart; todos os templates usam cache-buster da v0.8.15.1.

---

# Deploy — Data UNIVC v0.8.14.0

## UI/UX pilot — sem nova migração

A v0.8.14.0 altera somente frontend, cache busting e fingerprint do build. Não existe migration nova. Em bancos que já estavam na v0.8.13.x, mantenha a migration `025_dm_graduation_digital_diploma_v08130.sql` já aplicada e publique o novo código.

Os pilotos do novo Design System são DTNH/DCS, NPS e Alunos/Titulação do DM. DADM e DPE especializados permanecem no visual anterior nesta fase.

Após o deploy, confirme em `/api/health/live`:

```text
version = 0.8.14.0
build = <fingerprint de 12 caracteres>
```

O ZIP da release deve continuar sendo extraído de forma flat, com `app.py` diretamente na raiz.

---


## Migração obrigatória do DM — v0.8.13.1

Antes de usar as ações de titulação em PostgreSQL/Supabase, execute:

`database/025_dm_graduation_digital_diploma_v08130.sql`

A migração é aditiva: cria os campos de data de titulação/situação do diploma e a tabela de auditoria `dm_graduation_events`; não preenche datas históricas automaticamente.

# Deploy — Data UNIVC v0.8.13.1

## Ajuste v0.8.13.1 — sem nova migração

A v0.8.13.1 altera somente regras de validação e interface do DM. Não há nova coluna ou tabela. Se a migração `025_dm_graduation_digital_diploma_v08130.sql` já foi executada, não é necessário executar outra migração.


## Verificação obrigatória do build v0.8.13.1

Esta entrega inclui um ZIP **flat**. Ao extrair, `app.py`, `repository.py` e `render.yaml` devem ficar diretamente na raiz do projeto/deploy, e não dentro de outra pasta `UNIVC_Data_Driven_Cloud_...`.

Antes de testar Educação Física, abra `/api/health/live` e confirme:

```text
version = 0.8.13.1
educacao_fisica_policy = xlsx-course-field-only-v3
build = <fingerprint de 12 caracteres>
```

Se a aplicação ainda exibir a mensagem antiga `As turmas do XLSX contradizem...`, o processo em execução não é este build: essa regra não existe em `repository.py` da v0.8.13.1.


## Requisitos

- Python 3.12 recomendado;
- PostgreSQL/Supabase em produção;
- variáveis de ambiente conforme `.env.example`;
- Render ou Docker suportados pelos arquivos existentes na raiz.

## Atualização a partir da v0.8.7

1. Faça backup do banco.
2. Execute uma única vez:

```text
database/024_dcs_educacao_fisica_habilitacoes_v088.sql
```

3. Faça o deploy da aplicação v0.8.9.5.
4. Valide `/api/health/ready`.
5. Em DCS, confirme que aparecem **Educação Física - Bacharelado** e **Educação Física - Licenciatura** como cursos independentes.
6. Em homologação, use **Buscar direto no SEI** para ambos. O Bacharelado pode estar em página posterior do seletor; a paginação deve ocorrer automaticamente.

A migration 024 considera a premissa institucional informada para esta evolução: o cadastro histórico `Educação Física` corresponde ao **Bacharelado**. Se o banco já possuir simultaneamente o registro legado e outro registro de Bacharelado, a migration interrompe explicitamente em vez de fundir dados silenciosamente.


## Validação específica da v0.8.9.5

Na DCS, teste preferencialmente 2026/2 e consulte primeiro os dois cursos de Educação Física juntos. O conector deve encontrar Bacharelado na página 2 e, na consulta seguinte, voltar para a página 1 para encontrar Licenciatura. Se algum curso falhar, o resumo da sincronização informa a etapa (`buscar curso`, `selecionar curso`, `gerar/baixar Excel` ou `Importação do XLSX`).

## Atualização a partir da v0.8.6

A v0.8.9.5 não cria migration nova. Se a instalação ainda estiver em uma versão anterior à v0.8.8, aplique primeiro `database/024_dcs_educacao_fisica_habilitacoes_v088.sql`; depois publique a v0.8.9.5.

## Atualização a partir da v0.8.5

1. Faça backup do banco.
2. No SQL Editor do Supabase/PostgreSQL execute, uma única vez:

```text
database/023_dual_nps_v086.sql
database/024_dcs_educacao_fisica_habilitacoes_v088.sql
```

3. Faça o deploy da aplicação v0.8.9.5.
4. Valide `/api/health/ready`.
5. Em homologação, entre em DTNH e DCS e teste separadamente **NPS da Instituição → Atualizar NPS da Instituição pelo SEI** e **NPS do Curso → Atualizar NPS dos Cursos pelo SEI**.
6. Confirme que cada formulário permite vincular apenas a pergunta oficial correspondente.
7. Confira a cobertura da área institucional; o semestre só aparece como cobertura completa quando todas as diretorias acadêmicas esperadas estiverem sincronizadas.

A migration 023 é aditiva. Ela cria a projeção institucional (`nps_institution`) e a tabela de fonte oficial institucional (`survey_nps_institution_sources`). A estrutura existente do NPS do Curso é preservada.

## Atualização a partir da v0.8.4

Execute, nesta ordem:

```text
database/022_academic_surveys_sei_v085.sql
database/023_dual_nps_v086.sql
database/024_dcs_educacao_fisica_habilitacoes_v088.sql
```

A migration 022 cria a camada `survey_*`, a fundação da avaliação docente e a rastreabilidade do NPS. A 023 separa institucionalmente as duas métricas de NPS. A 024 separa as duas habilitações de Educação Física no DCS.

## Banco novo / instalação histórica

Para uma instalação realmente nova, as migrations estruturais devem ser aplicadas em ordem crescente. Os números 003, 006 e 008 não aparecem nesta distribuição porque eram apenas exemplos/opções demonstrativas, não migrations estruturais.

Arquivos estruturais presentes:

```text
001, 002, 004, 005, 007, 009, 010, 011, 012, 013, 014,
015, 016, 017, 018, 019, 020, 021, 022, 023, 024
```

Não reaplique uma migration já executada em produção sem revisar seu conteúdo.

## NPS e importação

Não existe mais modelo Excel nem botão **Importar legado** para NPS. Os caminhos oficiais são **Atualizar NPS da Instituição pelo SEI** e **Atualizar NPS dos Cursos pelo SEI**. O upload manual de XLSX/ZIP continua disponível dentro desse mesmo fluxo como contingência e utiliza exatamente o mesmo parser e as mesmas regras de mapeamento.

## Variáveis essenciais

```text
DATABASE_URL
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
AUTH_DISABLED=false
COOKIE_SECURE=true
AUTO_CREATE_DB=false
DEFAULT_DIRECTORATE_CODE=DTNH
```

Consulte `.env.example` para limites de upload, Excel, cache de autenticação e demais opções.

## Segurança SEI

Usuário e senha do SEI são usados apenas para a sessão atual. Senha, `JSESSIONID` e `ViewState` não são persistidos no banco ou em arquivos de configuração.

## Validação antes do deploy

```bash
python scripts/run_release_checks.py
```

O CI em `.github/workflows/ci.yml` executa compilação Python, validação JavaScript e o gate de regressão.


## Validação do estado JSF — v0.8.9.5

Ao testar Educação Física em períodos históricos, confirme no resumo que o build é `0.8.9.5`. O conector agora usa o formulário real retornado pelo SEI após selecionar o curso. Se o SEI devolver ano, semestre ou curso divergente antes do Excel, a operação falha explicitamente nessa etapa em vez de importar um relatório de outro contexto. Não há migration nova de banco nesta versão.

## v0.8.16.0 — passo obrigatório antes do deploy

1. Aplique `database/026_schema_version_baseline_v08160.sql` no PostgreSQL/Supabase depois da migration 025.
2. Confirme que existe uma linha em `data_univc_schema_version` com `version = 26`.
3. Faça o deploy do código v0.8.16.0.
4. Verifique `/api/health/ready`: `database` deve ser `ok` e `schema.compatible` deve ser `true`.

O `render.yaml` agora declara `ENVIRONMENT=production`, portanto o readiness check recusa schema ausente ou incompatível.

Para gerar um artefato de produção sem testes, DBs locais ou caches:

```bash
python scripts/build_release.py --profile production
```

## v0.8.19.0 — DADM / TALLOS Analytics Center

Antes de publicar a v0.8.19.0:

1. aplique `database/027_dadm_tallos_analytics_v08190.sql` depois da migration 026;
2. confirme `SCHEMA_VERSION = 27` em `/api/health/ready`;
3. configure `TALLOS_API_TOKEN` como segredo somente no backend;
4. mantenha `TALLOS_PAGE_LIMIT=49`;
5. faça a primeira homologação com `01/08/2026` a `31/08/2026` antes de usar os dados TALLOS como base gerencial oficial.

Variáveis opcionais:

```env
TALLOS_BASE_URL=https://api.tallos.com.br
TALLOS_PAGE_LIMIT=49
TALLOS_REQUEST_TIMEOUT=60
TALLOS_REQUEST_RETRIES=4
TALLOS_CHUNK_DAYS=90
```

Para o fechamento mensal, execute como cron/Render Job:

```bash
python scripts/dadm_tallos_sync.py --previous-month
```

A aplicação web lê somente o banco local/Supabase para dashboards. A chamada à API TALLOS fica restrita à sincronização.

## v0.9.6.1 — frontend identity e administração

A v0.9.6.1 não cria migration. Antes do deploy, a base já deve estar compatível com `database/033_identity_access_security_rebase.sql` e `/api/health/ready` deve reportar schema esperado/atual 33.

Em produção mantenha `ENVIRONMENT=production`, `AUTH_DISABLED=false`, `COOKIE_SECURE=true` e segredos JWT/fingerprint fortes. O provedor local (`DATA_UNIVC_LOCAL_TEST_AUTH`) não pode ser usado em produção e o pacote PRODUCTION não deve conter os launchers `.bat` de homologação.

O frontend agora depende dos cookies V2 e de CSRF para métodos mutáveis. Após o deploy, valide login, refresh silencioso, um POST/PATCH legítimo, logout, `/api/auth/me`, uma exportação Excel de DTNH/DCS e `/api/dm/excel`. Confirme também que um usuário de diretoria recebe `403` em `/api/admin/users` e que uma conta `REITORIA` recebe `200`.

Não reaplique a migration 033 se ela já estiver registrada/aplicada.

