# Parte 8 - Avaliacao Docente: limpeza de legado e hardening de release

Data: 2026-09-29
Versao: Data UNIVC 0.13.0
Schema: 49 (sem migration nova)

## Objetivo

Remover do frontend academico a implementacao antiga da Avaliacao Docente em nota historica 0-10, mantendo apenas o modulo oficial de favorabilidade categórica em `faculty-evaluation.js`, e ampliar os checks de producao para todos os JavaScripts ativos.

## Frontend removido

Foram removidos de `static/js/app.js` os estados, filtros, renderizadores e chamadas antigas ligados a:

- `loadTeacherOptions`;
- `loadTeacherAnalysis`;
- filtros `teacherPeriodFilter`, `teacherCourseFilter`, `teacherDisciplineFilter`, `teacherProfessorFilter`;
- cards/graficos antigos em nota 0-10;
- tabela server-side antiga da avaliacao docente;
- modal antigo de readiness que nao possuia mais botao no template.

O `app.js` caiu de 3122 para 2936 linhas, removendo 186 linhas de frontend morto.

## Compatibilidade

Os endpoints antigos abaixo continuam registrados no backend e retornando HTTP 410:

- `/api/avaliacao-docente/opcoes`;
- `/api/avaliacao-docente/analise`.

Isso preserva um contrato explicito de aposentadoria para clientes antigos sem reintroduzir a interface legada.

O modulo oficial continua em:

- frontend: `static/js/faculty-evaluation.js`;
- API: `/api/surveys/faculty-student/*`.

## Hardening de release

`scripts/run_release_checks.py` agora:

1. compila os Python;
2. descobre todos os `static/js/**/*.js`;
3. valida que os scripts referenciados pelos templates realmente existem;
4. executa `node --check` em todos os JavaScripts;
5. bloqueia tokens conhecidos do frontend docente legado;
6. executa a suite completa de testes;
7. preserva os checks de legado DPE ja existentes.

Na release atual foram encontrados 26 JavaScripts em `static/js` e os 26 sao referenciados pelos templates.

## Validacao

- Python compile: OK;
- JavaScript: 26/26 arquivos aprovados no `node --check`;
- referencias JS nos templates: 26/26 existentes;
- Pytest: 196 passed, 2 skipped;
- release checks: OK;
- schema: 49, sem migration nova.
