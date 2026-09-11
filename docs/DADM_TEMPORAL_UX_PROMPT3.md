# DADM V2 — Prompt 3 · Comportamento temporal e gráficos de cobertura

## Escopo

Esta etapa parte da versão do Prompt 2 e altera somente a experiência temporal do DADM V2 e a disponibilidade de cobertura como métrica gráfica. A integração Tallos, o endpoint de avaliações individuais, o schema do banco, as APIs gerenciais e os cálculos existentes foram preservados.

## Regra temporal adotada

A interface passou a distinguir o objetivo do recorte selecionado:

- **1 mês:** é uma fotografia. Não existe evolução temporal a ser representada. Gráficos que repetiam KPIs, média ou distribuição já presentes são ocultados.
- **2 ou mais meses:** é um intervalo temporal. Os gráficos mensais de evolução são exibidos normalmente.
- **Comparação de entidades em 1 mês:** continua exibindo um snapshot comparativo, pois o objetivo é comparar operadores/departamentos no mesmo período e não representar evolução.

A decisão é baseada no intervalo selecionado (`fromMonth`/`toMonth`), e não apenas na quantidade de pontos retornados pela base.

## Visão Geral

Em um único mês:

- o painel "Volume ao longo do período" é ocultado, pois o total já está no KPI;
- o gráfico de evolução de TME/TMA é ocultado, mantendo os KPIs e definições;
- o gráfico temporal de avaliação é ocultado, mantendo avaliação média e distribuição de notas;
- a distribuição de avaliação ocupa a leitura sem uma coluna vazia ao lado.

Com múltiplos meses, todos esses componentes temporais voltam automaticamente.

## Pessoas & Setores

No perfil de operador ou departamento, em um único mês:

- o painel "Evolução" não é renderizado;
- o bloco "Avaliações por mês" não é renderizado, pois teria apenas uma fotografia redundante;
- permanecem KPIs, contexto/equipe e as avaliações individuais introduzidas no Prompt 2.

Com múltiplos meses:

- o seletor de métrica temporal aparece;
- a evolução mensal volta a ser exibida;
- o bloco de médias/quantidades por mês volta a aparecer.

## Experiência

Em um único mês:

- permanecem avaliação média, avaliações válidas, cobertura, distribuição 1–10 e análise por dimensão;
- o gráfico "Média mensal e amostra" é ocultado por ser redundante.

Com múltiplos meses, o line chart da avaliação média mensal é exibido normalmente.

## Análise Comparativa

Para operadores/departamentos:

- em **1 mês**, usa `snapshotComparisonChart`, com título "Comparação do mês";
- em **2+ meses**, usa `lineChart`, com título "Evolução mensal das entidades".

Dessa forma um mês não é apresentado como "evolução", mas ainda há representação gráfica quando a pergunta é comparar entidades.

## Cobertura das avaliações

A cobertura **não foi removida do sistema**.

Foi retirada somente como opção de gráfico em:

- perfil de Pessoas & Setores;
- gráfico de comparação entre operadores/departamentos.

Continuam preservados:

- `rating_coverage_pct` no backend;
- cartões e resumos;
- tabelas;
- comparação tabular de períodos;
- metas e planos;
- relatórios/Excel existentes;
- compatibilidade com histórico.

## Arquivos alterados

- `static/js/dadm_v2.js`
- `static/css/dadm_v2.css`
- `templates/dadm_v2.html`
- `tests/test_v08220_ui_foundation_sync.py` (expectativa atualizada para a nova regra temporal)
- `tests/test_dadm_prompt3_temporal_ux.py` (novo)

## Banco e deploy

- **Schema:** permanece 33.
- **Migration:** não é necessária.
- **Supabase:** nenhuma mudança estrutural.
- **Render:** nenhuma mudança necessária nesta etapa.

## Validação

- `node --check static/js/dadm_v2.js`: aprovado.
- suíte focada DADM/Tallos/UI/escopo: **88 testes aprovados**.
- a suíte global completa foi iniciada, porém excedeu o limite de execução do ambiente; portanto não é registrada como concluída.
