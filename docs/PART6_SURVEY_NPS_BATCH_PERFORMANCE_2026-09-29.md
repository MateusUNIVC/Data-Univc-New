# Parte 6 — NPS e questionários em lote

Data: 29/09/2026
Schema: 49 (sem migration nova)

## Objetivo

Reduzir o custo de persistência dos questionários/NPS na VPS sem alterar a metodologia, os contratos de curso, a resolução de Educação Física ou as projeções NPS já existentes.

## Problema anterior

`SurveyRepository.import_workbooks()` repetia, para cada relatório de curso, consultas de `SurveyRunCourse`, `SurveyQuestion`, `SurveyQuestionnaireQuestion` e inserts ORM de cada resposta. O fluxo institucional dos docentes fazia o mesmo para cada contexto anônimo.

Em um benchmark sintético com 50 relatórios e uma pergunta por relatório, cada pergunta contendo 3 opções agregadas e 1 resposta aberta:

- NPS por curso: **153 SELECT + 256 INSERT + 1 UPDATE**;
- NPS institucional dos docentes: **152 SELECT + 256 INSERT + 1 UPDATE**.

## Implementação

### Catálogo de perguntas

As perguntas normalizadas de todos os relatórios novos são coletadas antes da persistência. O repositório executa uma única consulta para perguntas existentes, cria as ausentes em conjunto e resolve os vínculos do questionário também em uma única consulta.

A semântica anterior foi preservada:

- `nps_candidate` só evolui para `True`;
- um tipo métrico específico pode substituir `categorical`;
- a posição do vínculo do questionário continua atualizada.

### NPS por curso / questionário genérico

- cursos da diretoria continuam usando o cache já existente;
- cursos já importados no `survey_run` são carregados em uma consulta;
- `SurveyRunCourse` é inserido em lote;
- `SurveyResponseAggregate` é inserido em lote;
- `SurveyRawResponse` é inserido em lote;
- a transação continua atômica: não há commit parcial por lote.

### NPS institucional dos docentes

- `source_path` já importados são carregados em uma consulta;
- contextos anônimos novos usam `INSERT ... RETURNING` em massa para recuperar os IDs necessários às FKs;
- agregados e respostas abertas são inseridos em lotes;
- refresh de uma mesma aplicação SEI continua invalidando corretamente a projeção NPS oficial anterior antes de reconstruir a origem.

## Configuração

`SURVEY_IMPORT_BATCH_SIZE=50`

- padrão: 50;
- mínimo interno: 10;
- máximo interno: 250.

A variável controla o tamanho de grupos de relatórios e serve como base para os lotes maiores de respostas. Em VPS pequena, 50 é o valor recomendado inicial.

## Benchmark após a mudança

Mesmo cenário sintético de 50 relatórios:

- NPS por curso: **6 SELECT + 9 INSERT + 1 UPDATE**;
- NPS institucional dos docentes: **5 SELECT + 9 INSERT + 1 UPDATE**.

O benchmark usa SQLite local e mede quantidade de comandos SQL, não latência de PostgreSQL. O objetivo é comprovar a remoção do padrão N × pergunta/curso/contexto.

## Compatibilidade

Preservados:

- cálculo e classificação do NPS;
- resolução manual de cursos ambíguos;
- regra específica do SEI atual: `Educação Física` → `Educação Física - Licenciatura` somente no adapter da fonte;
- Bacharelado de Educação Física separado;
- idempotência de reimportação;
- candidatos NPS e projeções oficiais;
- schema 49.

## Validação

- testes novos de performance e idempotência do NPS;
- regressão completa: 187 aprovados, 2 ignorados;
- nenhuma migration nova.
