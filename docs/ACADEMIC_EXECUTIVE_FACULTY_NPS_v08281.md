# v0.8.28.1 — Academic Executive Faculty NPS & Sidebar Groups

## Objetivo

Completar a presença do KPI 01C no Painel Executivo acadêmico e tornar a navegação lateral de DTNH/DCS semanticamente agrupada.

## Painel Executivo

O backend agora expõe `cards.nps_faculty` usando a mesma referência semestral dos demais NPS. O card contém valor, comparação, variação, meta aplicável, status, respondentes, composição e fonte. A série `series.nps_faculty_semestral`, já existente desde a v0.8.25.0, passa a ser renderizada no executivo.

O 01C continua sendo institucional e anônimo. A fonte docente do SEI não identifica curso, portanto nenhum agrupamento ou inferência por curso é criado.

## Sidebar

A navegação acadêmica passa a seguir a hierarquia:

- Painel executivo
- NPS Discente
  - NPS da instituição
  - NPS do curso
- NPS Docente
  - NPS da instituição · docentes
- Indicadores acadêmicos
  - Avaliação docente
  - Aprovação e notas
- Gestão
  - Planos de ação
  - Metas dos KPIs
  - Cursos e disciplinas
- Sistema

A separação deixa explícita a diferença entre NPS respondido pelos docentes (01C) e avaliação do docente pelo aluno (02).

## Banco

Nenhuma migration. `SCHEMA_VERSION = 31`.
