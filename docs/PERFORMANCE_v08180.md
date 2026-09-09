# Data UNIVC v0.8.18.0 — Query Performance

Esta etapa reduz o volume materializado pelos workspaces analíticos sem alterar o schema (`SCHEMA_VERSION = 26`). Os números abaixo vêm de bancos SQLite sintéticos e servem para regressão relativa; PostgreSQL/Supabase continua sendo a referência para latência absoluta e `EXPLAIN ANALYZE`.

## Avaliação Docente

Antes, o workspace carregava a coleção completa de avaliações no navegador e fazia busca, filtros, paginação e agregações em JavaScript.

Agora:

- tabela: `COUNT` + uma consulta paginada (`LIMIT/OFFSET`), com no máximo 100 linhas por página;
- opções dos filtros: quatro consultas `DISTINCT`;
- KPIs/evolução/comparação: três consultas agregadas SQL;
- comparação limitada a 20 categorias;
- busca da tabela é server-side e não altera os KPIs, preservando o comportamento anterior;
- o dashboard executivo recebe avaliação docente já agregada em `semestre × curso × disciplina`, sem linhas por professor.

Cenário sintético com 1.000 avaliações individuais em um único curso/disciplina distribuídas por dois semestres:

- antes no snapshot executivo: 1.000 linhas de professor;
- depois: 2 linhas agregadas;
- consultas para o resumo do dashboard: 1;
- média ponderada e total de respondentes preservados.

## DADM

`/api/dadm/dashboard` não usa mais `all_measurements()`.

Para uma janela de 12 meses, o repositório busca:

1. até 12 competências relevantes (mínimo técnico de 3 para a regra de crescimento do saldo em aberto);
2. a competência de comparação quando estiver fora desse conjunto;
3. somente os `ManagementMeasurement` dessas competências.

Cenário sintético de 48 meses × 2 indicadores:

- antes: 96 fatos materializados;
- depois para janela 12: 24 fatos;
- consultas do repositório: 2;
- cards, série e itens dimensionais iguais ao dashboard produzido com o histórico completo.

## DPE financeiro

O dashboard financeiro precisa de lookback para métricas móveis. Por isso a leitura limitada **não** busca apenas a janela visível.

Para `janela = N`, o repositório carrega no máximo `N + 11` competências. Isso preserva os cálculos de rolling 12 meses do primeiro ponto visível.

Cenário sintético de 48 competências, janela visível de 12:

- antes: 48 receitas + 48 despesas materializadas;
- depois: 23 receitas + 23 despesas (12 visíveis + 11 de lookback);
- snapshot bounded: 6 statements fixos no cenário com despesas (união de períodos, quatro bases financeiras e rateios);
- cards, série mensal e série de margem por curso equivalentes ao snapshot completo.

A consulta extra para descobrir competências é intencional: o objetivo é reduzir linhas transferidas/processadas e impedir que o custo cresça indefinidamente com o histórico.

## O que esta release não faz

- não introduz cache;
- não adiciona Redis/Celery;
- não altera índices ou schema;
- não muda NPS, que já trabalha com fatos agregados de baixo volume;
- não transforma dados Tallos em `ManagementMeasurement` bruto;
- não afirma latência de produção com base em SQLite.

Próxima validação de infraestrutura: executar `EXPLAIN ANALYZE` e medir p50/p95 no PostgreSQL/Supabase com volumes representativos.
