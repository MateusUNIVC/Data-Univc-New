# Parte 5 — Avaliação Docente: importação em lote e redução de CPU

Data: 2026-09-29

## Objetivo

Reduzir o custo de CPU/SQL da importação da Avaliação Docente na VPS sem alterar identidade acadêmica, turmas compartilhadas, indicadores, respostas ou contratos de API.

## Problema encontrado

O fluxo anterior fazia resolução/persistência contexto por contexto. Para cada relatório eram repetidos vários ciclos de:

- consulta de curso;
- consulta/criação de professor;
- leitura de todas as disciplinas do curso;
- consulta/criação de oferta;
- consulta/criação de vínculo docente;
- consulta de contexto;
- consulta/criação de pergunta;
- `flush()` intermediário;
- inserts ORM individuais de respostas.

Em um benchmark sintético com 50 contextos distintos, isso gerava cerca de 860 operações SQL no SQLite de teste.

## Arquitetura nova

A importação passa a trabalhar em lotes configuráveis:

1. valida todos os contextos e resolve cursos antes de iniciar os lotes;
2. prefetch de professores do lote;
3. prefetch de disciplinas dos cursos envolvidos;
4. prefetch de ofertas do semestre;
5. prefetch de vínculos docentes;
6. prefetch de contextos existentes e escopos compartilhados;
7. prefetch de perguntas/vínculos do questionário;
8. criação das dimensões ausentes por `executemany`;
9. criação dos contextos novos por `executemany`;
10. inserts em massa de escopos, agregados e respostas abertas;
11. commit por lote;
12. próximo lote.

O lote padrão é `100` contextos e pode ser ajustado por:

`FACULTY_IMPORT_BATCH_SIZE=100`

Valores aceitos são limitados internamente entre 25 e 500.

## Retomada após interrupção

Cada lote confirmado permanece persistido. Se houver falha posterior:

- a importação fica com status `failed`;
- os lotes anteriores permanecem válidos;
- uma nova execução encontra os contextos já existentes;
- esses contextos são ignorados;
- apenas o restante é persistido.

Assim, uma interrupção não exige refazer toda a carga e não duplica respostas.

## Turmas compartilhadas

A otimização respeita integralmente a Parte 3:

- um contexto continua armazenando as respostas uma única vez;
- vários cursos continuam ligados via `faculty_evaluation_context_scopes`;
- reimportação pode acrescentar um novo curso compartilhado sem recriar respostas;
- visão global continua deduplicada.

## Benchmark sintético

Cenário: 50 contextos, cada um com professor e disciplina distintos, uma pergunta e duas opções.

### Antes

Aproximadamente 860 operações SQL no SQLite de teste.

### Depois

- 19 `SELECT`;
- 13 `INSERT` agrupados;
- 1 `UPDATE`;
- 50 contextos persistidos;
- 100 agregados de resposta persistidos.

O objetivo do benchmark não é reproduzir a latência do PostgreSQL da VPS, mas comprovar que o número de operações deixou de crescer no padrão `contexto × entidade`.

## Observabilidade

A resposta da importação passa a incluir `performance` com:

- tamanho do lote;
- quantidade de lotes;
- contextos preparados/importados/ignorados;
- tempo total;
- métricas por lote.

Os logs registram apenas métricas operacionais, sem payloads de respostas ou dados pessoais desnecessários.

## Banco de dados

Nenhuma migration nova nesta etapa.

O schema permanece 49 e continua exigindo a migration acumulada:

`049_academic_faculty_context_scopes_v0130.sql`

## Regressão

- suíte completa: 182 testes aprovados, 2 ignorados;
- inclui teste de volume/contagem SQL;
- inclui teste de interrupção no segundo lote + retomada;
- inclui deduplicação de duas fontes com a mesma identidade dentro do mesmo lote;
- release checks: OK.
