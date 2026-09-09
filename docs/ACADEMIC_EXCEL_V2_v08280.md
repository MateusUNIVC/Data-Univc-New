# Academic Excel V2 — v0.8.28.0

## Objetivo

Substituir a exportação acadêmica histórica de DTNH/DCS por um relatório gerencial alinhado ao modelo atual do Data UNIVC. A rota oficial `/api/excel` deixa de entregar o workbook legado de cálculo/entrada e passa a refletir os mesmos KPIs, filtros, metas e regras de agregação exibidos no dashboard.

## Contrato funcional

O relatório respeita o contexto ativo da interface:

- granularidade;
- referência e comparação;
- janela temporal;
- curso;
- disciplina.

As regras específicas dos indicadores são preservadas:

- `01A` NPS da Instituição · Alunos continua institucional UNIVC (DTNH + DCS) e não é recalculado pelo filtro de curso;
- o detalhamento de `01A` por curso permanece restrito à diretoria em visualização;
- `01B`, `02` e `03` respeitam curso/disciplina quando aplicável;
- `01C` NPS da Instituição · Docentes continua institucional e anônimo, sem curso ou identificação de professor;
- a comparação entre cursos permanece restrita aos cursos da diretoria ativa.

## Estrutura oficial

O workbook possui nove abas:

1. `Resumo Executivo`
2. `NPS Instituição Alunos`
3. `NPS Cursos`
4. `NPS Instituição Docentes`
5. `Avaliação Docente`
6. `Aprovação e Resultados`
7. `Comparação Cursos`
8. `Metas e Planos`
9. `Parâmetros`

Abas técnicas do modelo antigo, como `CALC`, `MATRIZ`, `LISTAS DE APOIO`, `DIM_PERIODO`, `DIM_MES` e bases editáveis, não fazem mais parte da rota oficial.

## Privacidade e granularidade

A exportação é gerencial e agregada. Não são exportados:

- nome ou matrícula de aluno;
- linhas individuais de resultado acadêmico;
- respostas brutas de pesquisas;
- identidade individual de docentes no NPS 01C.

As abas usam agregações por semestre, curso e disciplina, conforme o indicador.

## Excel nativo

O arquivo usa recursos nativos e editáveis do Excel:

- Excel Tables com autofiltros;
- gráficos de linha e barras;
- cores de status orientadas pelas metas;
- fórmulas para NPS e taxa de aprovação derivada;
- formatação percentual/decimal apropriada;
- cálculo automático ao abrir o arquivo.

O `Resumo Executivo` reúne `01A`, `01B`, `01C`, `02` e `03`, com resultado, meta, faixa de atenção, status, comparação e evolução. Períodos sem qualquer dado factual não são transformados em zeros nos gráficos.

## Compatibilidade

O módulo histórico `academic_excel_builder.py` permanece no código apenas para compatibilidade interna/regressões antigas que ainda possam precisar de seus helpers. A rota oficial acadêmica usa exclusivamente `academic_excel_v2_builder.py`.

Não há migration nesta release. O schema permanece na versão 31.
