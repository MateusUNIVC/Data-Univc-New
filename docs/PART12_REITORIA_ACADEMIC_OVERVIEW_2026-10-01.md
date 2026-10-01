# Parte 12 — Visão Acadêmica Geral da Reitoria

Data: 01/10/2026  
Versão: Data UNIVC v0.13.0  
Schema: 49 (sem migration nova)

## Objetivo

Adicionar à Reitoria uma visão acadêmica institucional, somente leitura, consolidando DTNH e DCS sem exigir navegação diretoria por diretoria.

## Nova seção

A página `/reitoria` passa a oferecer **Indicadores Acadêmicos** com o recorte padrão **Todas · UNIVC** e filtros opcionais por:

- semestre;
- diretoria (Todas, DTNH ou DCS);
- curso;
- disciplina.

As operações de importação, edição e exclusão permanecem nas áreas das diretorias. A Reitoria consulta os indicadores, mas não ganha endpoints de escrita acadêmica.

## Indicadores consolidados

A visão institucional apresenta:

- NPS da Instituição · Alunos;
- NPS dos Cursos;
- NPS da Instituição · Docentes;
- Avaliação Docente pelo Aluno (favorabilidade);
- Taxa de Aprovação;
- Média das Notas;
- Alunos Distintos.

Também apresenta séries históricas, comparação por curso e distribuições NPS 0–10 quando a fonte oficial permite reconstrução a partir dos agregados.

## Regra de agregação institucional

A Reitoria não usa média de médias.

- NPS é recalculado com promotores, detratores e respondentes agregados.
- Aprovação é recalculada por aprovados / resultados finalizados.
- Média de notas é recalculada por soma das notas / quantidade de notas válidas.
- Favorabilidade docente é recalculada por respostas favoráveis / respostas classificadas.

Isso evita distorções quando DTNH e DCS possuem volumes de alunos ou respostas diferentes.

## Turmas compartilhadas

A visão geral reutiliza o motor oficial da Avaliação Docente. Contextos compartilhados entre cursos continuam aparecendo nos cursos aos quais pertencem, mas são deduplicados no consolidado institucional para não dobrar participações e respostas.

## NPS de docentes

O NPS institucional de docentes permanece anônimo e institucional. Por isso, ele não é reinterpretado como indicador por curso ou disciplina na Reitoria. A interface explicita essa diferença metodológica.

## Filtro de disciplina e NPS

O NPS não possui dimensão de disciplina. Portanto, o filtro de disciplina afeta Avaliação Docente e Resultados Acadêmicos, mas não inventa um recorte inexistente para NPS.

## Backend

Novos componentes:

- `reitoria_academic.py` — serviço de agregação institucional;
- `reitoria_academic_router.py` — endpoints somente leitura;
- `GET /api/reitoria/academic/filters`;
- `GET /api/reitoria/academic/overview`.

Os endpoints exigem `require_fresh_reitoria`.

## Frontend

Novos componentes:

- `static/js/data-univc-academic-charts.js` — gráficos acadêmicos usados pela Reitoria com escalas semânticas;
- `static/js/reitoria_academic.js` — filtros, carregamento e renderização da visão institucional;
- nova seção `#academico` em `templates/reitoria.html`;
- estilos próprios em `static/css/reitoria.css`.

Escalas preservadas:

- percentuais: 0–100;
- NPS: -100 a +100;
- notas: 0–10;
- contagens: mínimo zero.

## Validação

- suíte completa: **219 testes aprovados, 2 ignorados**;
- JavaScript: **28/28** arquivos aprovados no `node --check`;
- referências JavaScript dos templates: **28/28** presentes;
- autenticação da Reitoria verificada no preflight;
- agregações ponderadas testadas com volumes deliberadamente diferentes entre DTNH e DCS;
- schema permanece 49.
