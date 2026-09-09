# DADM · TALLOS Analytics Center — v0.8.20.3

## Objetivo

A v0.8.19.0 incorpora o TALLOS Analytics Center **dentro da DADM existente**. O TALLOS não é um sistema paralelo e o navegador não consulta a API externa diretamente. A arquitetura preserva o padrão FastAPI + SQLAlchemy + PostgreSQL/Supabase + HTML/CSS/JS puro e o Design System `ui-v2`.

O DADM-01 e o DADM-02 continuam sendo os indicadores institucionais oficiais. O Analytics Center adiciona a camada operacional detalhada por atendimento, protocolo, pessoa, operador, departamento, canal e período. Dados TALLOS individuais **não** são gravados como `ManagementMeasurement`.

## Arquitetura

```text
TALLOS / RD Station Conversas
          |
          | GET /v4/reports (Bearer, limit=49)
          v
 dadm_tallos_client.py
          |
          v
 dadm_tallos_normalization.py
          |
          v
 dadm_tallos_repository.py ----> PostgreSQL/Supabase
          |                       - dadm_tallos_attendances
          |                       - dadm_tallos_sync_runs
          |                       - dadm_tallos_department_map
          v
 dadm_tallos_analytics.py
          |
          v
 /api/dadm/tallos/*
          |
          v
 dadm_tallos.js + dadm_tallos.css
          |
          v
 DADM / TALLOS Analytics Center
```

### Regra de performance

O frontend nunca recebe a base completa para calcular KPIs ou gráficos. O SQL filtra e agrega no servidor. A resposta HTTP contém apenas cards, séries, distribuições, operadores e departamentos do recorte solicitado.

**Escopo desta homologação:** a fonte de verdade permanece em `dadm_tallos_attendances` e as agregações são feitas server-side. As tabelas físicas diárias/mensais planejadas ficam para a etapa posterior à validação do golden dataset. Isso evita congelar agregados incorretos antes de confirmarmos TME/departamentos e preserva cálculos exatos de `COUNT(DISTINCT ...)`, mediana e P90, que não podem ser obtidos somando ou fazendo média de agregados simples.

A base detalhada permanece no banco para permitir filtros e reprocessamento histórico sem repetir chamadas TALLOS.

## Unidade de análise

- **Atendimento**: uma sessão/registro operacional da API TALLOS (`source_id`).
- **Protocolo**: `protocol` distinto. Pode aparecer em mais de um atendimento/sessão.
- **Pessoa**: `customer.id` distinto, armazenado somente como identificador opaco (`customer_ref`).

O protocolo não é chave primária. A persistência usa `(directorate_id, source_id)` como chave única.

## Mapeamento operacional

| Métrica | Campo API | Situação |
|---|---|---|
| Operador | `employee.name` | validado |
| ID do operador | `employee.id` / `_id` | operacional |
| Protocolo | `protocol` | validado |
| Pessoa | `customer.id` / `_id` | operacional |
| Canal | `channel` | validado |
| Tabulação | `to_tabulation` | validado |
| TMA | `tma.value` | validado |
| Avaliação | `level` | validado como campo; escala operacional 1–10; 0 = ausência na homologação |
| Mensagens enviadas | `total_send_messages` | validado |
| Mensagens recebidas | `total_receive_messages` | validado |
| Iniciado por | `initiation_info.initiated_by` | validado |
| TME | `tme.value` | provisório |
| Departamento | `to_department` | exige mapeamento de exibição |
| TMRO | `operational_metrics.tmro` | experimental |
| TMRC | `operational_metrics.tmrc` | experimental |
| Status | flags/timestamps de abertura/fechamento | derivado |

Campos provisórios/experimentais são armazenados para validação futura, mas TMRO/TMRC não entram como KPI institucional oficial nesta release.

### Significado de TME e TMA

- **TME — Tempo Médio de Espera:** tempo médio que o contato aguarda até o início do atendimento. Fonte atual: `tme.value`. Continua marcado como **provisório** até a validação final do mapeamento.
- **TMA — Tempo Médio de Atendimento:** duração média do atendimento após o início. Fonte: `tma.value`. O mapeamento foi **validado** contra o conjunto de agosto.

Os nomes por extenso aparecem na interface, nos tooltips e nas áreas de operador para evitar que a sigla seja interpretada sem contexto.

## Privacidade

A tabela operacional não possui colunas para nome do cliente, telefone, CPF ou CNPJ. O JSON técnico persistido é uma whitelist sanitizada. O `customer.id` é usado somente para contagem distinta de pessoas.

## Banco e migration

A integração base nasce na migration 027. A v0.8.20.3 exige `SCHEMA_VERSION = 29` e aplica as migrations 028 e 029 em sequência:

```text
database/027_dadm_tallos_analytics_v08190.sql
database/028_dadm_tallos_rating_scale_v08201.sql
database/029_dadm_tallos_rating_1_10_v08203.sql
```

A 027 cria:

- `dadm_tallos_attendances`: fato operacional detalhado;
- `dadm_tallos_sync_runs`: auditoria da ingestão;
- `dadm_tallos_department_map`: tradução governada de identificadores TALLOS.

A 028 representa a hipótese intermediária 0–10. A 029 substitui esse contrato por **1–10**, limpa zeros históricos e reprocessa o `source_payload_json`: somente notas 1–10 permanecem válidas. Em produção aplique 027, 028 e 029 em ordem **antes** de publicar o código. O readiness bloqueia código/schema incompatíveis.

## Homologação real v0.8.20.3

A homologação local foi desenhada para começar **sem dados demonstrativos**. Execute `TESTAR_DADM.bat`: ele usa `univc_dadm_homolog.db`, mantém `SEED_DEMO_DATA=false` e não mistura a validação TALLOS com os seeds institucionais.

Na primeira abertura, o Analytics Center apresenta três etapas: conectar, sincronizar agosto/2026 e validar indicadores. Em ambiente local e com permissão de escrita, a aba **Sincronização** aceita o token, testa `/v2/employees` e, somente após uma conexão válida, grava `TALLOS_API_TOKEN` no `.env` do backend. O endpoint de status informa apenas se existe token e onde ele é gerenciado (`.env` local ou ambiente do servidor); o valor do segredo nunca é retornado.

Em produção, a gravação do token pela interface é bloqueada. Configure `TALLOS_API_TOKEN` no ambiente do serviço.

A aba também permite limpar **somente** atendimentos, mapeamentos de departamento e histórico de sincronização TALLOS do banco local, preservando DADM-01/DADM-02. Isso serve para repetir a homologação do zero.

Para o primeiro teste real, informe agosto/2026 na área de sincronização. O progresso exibe páginas, recebidos, inseridos, atualizados, inalterados e falhas. Depois valide volume, protocolos, operadores, Tempo Médio de Atendimento (TMA), avaliações 1–10 e canais; em seguida repita o mesmo período para confirmar a idempotência do UPSERT.

### Avaliações na homologação

A exportação oficial usada para reconciliação diferencia explicitamente `S/A` de notas numéricas. No recorte recebido havia 536 linhas: 504 `S/A` e 32 avaliações válidas. Não havia nota 0. A média das avaliações numéricas era 9,28125; a distribuição era 24×10, 4×9, 1×8, 1×7 e 2×3.

Contrato adotado nesta release:

- notas válidas: **1 a 10**;
- `S/A`, `NULL`, campo ausente e `level=0`: **sem avaliação**;
- ausência nunca entra em `AVG` ou `COUNT` de avaliações;
- mês sem avaliação retorna `rating_avg = null` e aparece como `—`;
- a média mensal de um operador é calculada somente sobre suas avaliações válidas naquele mês;
- a avaliação é preservada por sessão/`source_id`; protocolos repetidos entre operadores não propagam a nota para outra sessão.

Além da normalização, as consultas aplicam defensivamente a faixa 1–10 para impedir que um zero histórico de banco antigo volte a contaminar médias. A aba de auditoria mostra o `level` bruto, o valor normalizado e a classificação usada.

Não existe conversão automática para “satisfeito/insatisfeito”. O DADM-02 apresenta nota média, distribuição, quantidade e cobertura até que exista uma regra institucional aprovada para faixas de satisfação.

## Sincronização

### Configuração

No backend:

```env
TALLOS_API_TOKEN=SEU_TOKEN
TALLOS_BASE_URL=https://api.tallos.com.br
TALLOS_PAGE_LIMIT=49
TALLOS_REQUEST_TIMEOUT=60
TALLOS_REQUEST_RETRIES=4
TALLOS_CHUNK_DAYS=90
```

O token nunca deve ir para HTML, JavaScript ou `localStorage`.

### Pela interface

Na DADM, abra **TALLOS Analytics Center → Sincronização**, escolha início/fim e execute a atualização. A gravação é idempotente:

- novo `source_id` → INSERT;
- mesmo `source_id` e mesmo hash → unchanged;
- mesmo `source_id` com avaliação/status/tempo alterado → UPDATE.

### CLI / tarefa agendada

Mês anterior:

```bash
python scripts/dadm_tallos_sync.py --previous-month
```

Janela recente:

```bash
python scripts/dadm_tallos_sync.py --rolling-days 7
```

Intervalo explícito:

```bash
python scripts/dadm_tallos_sync.py --start 2026-08-01 --end 2026-08-31
```

Para automação mensal, agende `--previous-month` no cron/Render Job/serviço de scheduler da infraestrutura. A sincronização não depende de o navegador estar aberto.

## Analytics e filtros

O mesmo filtro é aplicado a toda a leitura TALLOS:

- mês inicial e mês final;
- comparação opcional com período anterior equivalente ou mesmo período do ano anterior;
- departamento;
- operador;
- canal;
- status;
- tabulação;
- leitura gerencial mensal; a sincronização continua usando datas exatas.

Principais KPIs:

- atendimentos;
- protocolos únicos;
- pessoas únicas;
- operadores ativos;
- finalizados/em aberto;
- TME médio, mediano e P90;
- TMA médio, mediano e P90;
- avaliação média;
- avaliações válidas e cobertura;
- avaliações válidas, cobertura e ausência de avaliação;
- mensagens;
- transferências.

## Operadores

A área de operadores traz ranking, ordenação, percentis, volume, avaliação e matriz TMA × avaliação com tamanho da bolha proporcional ao volume. Também existe comparação mensal de até quatro operadores no frontend.

## Departamentos

A API pode fornecer chaves/slug em `to_department`. A tabela `dadm_tallos_department_map` mantém o nome legível sem alterar os fatos. A aba de Governança permite editar o nome de exibição.

## DADM-01 e DADM-02

O Analytics Center não sobrescreve automaticamente a base oficial já existente.

### DADM-01

A camada operacional fornece protocolos, atendimentos, abertos/finalizados, TME e TMA. O percentual de SLA só deve ser derivado após existir uma meta formal de tempo por canal/recorte; a release não inventa essa meta.

### DADM-02

A avaliação operacional TALLOS é exibida como **média 1–10**, distribuição por nota e cobertura. O sistema não transforma automaticamente essa escala no indicador institucional DADM-02. Essa conversão só deve existir após uma regra institucional aprovada (por exemplo, quais notas representam satisfação, neutralidade e insatisfação).

A cobertura de avaliação é sempre exibida para contextualizar a amostra, e atendimentos sem `level` válido não entram na média.

## API interna

Principais rotas:

```text
GET  /api/dadm/tallos/status
GET  /api/dadm/tallos/filters
GET  /api/dadm/tallos/dashboard
GET  /api/dadm/tallos/summary
GET  /api/dadm/tallos/timeline
GET  /api/dadm/tallos/operators
GET  /api/dadm/tallos/departments
GET  /api/dadm/tallos/ratings
GET  /api/dadm/tallos/channels
GET  /api/dadm/tallos/operator-comparison
GET  /api/dadm/tallos/sync-runs
POST /api/dadm/tallos/sync
GET  /api/dadm/tallos/department-map
PUT  /api/dadm/tallos/department-map/{source_key}
```

Leituras respeitam o escopo DADM. Sincronização e alteração do mapa de departamentos exigem permissão de escrita.

## Golden dataset — agosto/2026

A validação externa anterior encontrou 5.074 registros na API no período de 01/08/2026 a 31/08/2026, com mapeamentos fortes para operador, TMA, avaliação, canal, tabulação e mensagens. Depois de configurar o token, agosto deve ser a primeira carga real de homologação.

Fluxo recomendado:

```text
1. sincronizar 01/08/2026 → 31/08/2026
2. conferir quantidade ingerida
3. conferir protocolos únicos
4. conferir TMA por operador
5. conferir média e distribuição das notas 1–10
6. conferir canais
7. repetir a mesma sync e confirmar ausência de duplicação
```

Depois da carga, gere um resumo de homologação diretamente do banco:

```bash
python scripts/dadm_tallos_validate.py --golden-august-2026
```

Não publique a integração como fonte oficial antes dessa homologação real.

## Validação técnica da release

O projeto contém `tests/test_v08190_dadm_tallos_analytics.py`, cobrindo normalização, privacidade, UPSERT, protocolos repetidos, métricas, percentis, mapeamento de departamentos e contratos de rota/UI/schema.

Use:

```bash
python scripts/run_test_gate.py --profile pr
```

Para a entrega final completa:

```bash
python scripts/run_test_gate.py --profile release
```


## Regra de ausência de avaliação (v0.8.20.3)

- `level = 1..10` → avaliação válida.
- `level = 0`, `null`, campo ausente, `S/A` ou valor não numérico → `rating = NULL`.
- `rating = NULL` não entra em média, distribuição nem comparação.
- um período com `rating_count = 0` retorna `rating_avg = null`; a interface mostra `—`, nunca `0/10`.
- a associação é por sessão/`source_id`, não por protocolo isolado.
