# Parte 15 — Convergência visual do NPS e NPS institucional por curso

## Objetivos

1. Reutilizar em DTNH e DCS a mesma distribuição 0–10 usada pela Reitoria.
2. Dar aos gráficos da Reitoria a leitura por hover já esperada nos painéis acadêmicos.
3. Exibir, na Reitoria, como os alunos de cada curso avaliam a instituição, sem confundir esse recorte com o NPS do próprio curso.

## Distribuição 0–10 compartilhada

`data-univc-academic-charts.js` passa a fornecer o renderer oficial de distribuição NPS. `app.js` delega a ele em DTNH/DCS. O componente mostra respondentes, média 0–10, NPS, barras 0–10 e agrupamentos detratores/neutros/promotores.

## Hover da Reitoria

Os gráficos de linha e barras usam `chart-hover-card` e mostram, conforme o indicador:

- NPS: respondentes, promotores, neutros e detratores;
- avaliação docente: participações, respostas classificadas e favoráveis;
- aprovação: aprovados, finalizados, média e alunos quando disponíveis;
- notas/alunos: volume correspondente ao ponto.

## NPS da instituição por curso

A projeção `nps_institution` é consolidada por diretoria e não possui `course_id`. Entretanto, os agregados oficiais preservam o curso em `survey_response_aggregates`. A Reitoria reconstrói o NPS institucional por curso diretamente desses agregados usando `survey_nps_institution_sources`.

Esse comparativo responde: **"como os alunos de cada curso avaliaram a UNIVC na pergunta institucional?"**. Ele não substitui nem reaproveita o NPS do Curso.

## Banco

Nenhuma migration. Schema permanece 49.

## Validação

- 238 testes aprovados;
- 2 ignorados;
- 28/28 JavaScripts válidos;
- release checks OK.
