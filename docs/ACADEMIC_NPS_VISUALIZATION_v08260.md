# Data UNIVC v0.8.26.0 — Academic NPS Visualization & UX

## Objetivo

Melhorar a leitura comparativa dos NPS acadêmicos de DTNH/DCS sem alterar o cálculo ou a fonte dos indicadores 01A, 01B e 01C.

## Regras de cor

As barras de comparação NPS usam o mesmo status calculado pela camada de metas:

- **Dentro da meta** → verde;
- **Atenção** → amarelo;
- **Fora da meta** → vermelho;
- **Sem meta** → neutro/cinza.

### NPS do Curso — 01B

Cada curso recebe sua meta efetiva no semestre. Meta específica do curso tem precedência sobre `TOTAL`; na ausência de específica, a meta geral da diretoria é herdada.

### NPS da Instituição — 01A

O detalhamento institucional por curso continua sendo apenas uma segmentação analítica da pergunta sobre recomendar a UNIVC. Por isso todos os cursos são comparados à meta institucional `01A/TOTAL`; metas 01B não são reutilizadas nessa visualização.

## Rótulos longos

O renderer de barras passou a reservar uma margem maior e quebrar nomes de cursos em até duas linhas. Quando o nome excede o espaço disponível, a segunda linha recebe reticências. O tooltip sempre usa o nome completo.

## Tooltips

Quando disponíveis, mostram:

- valor;
- meta;
- vigência;
- recorte da meta;
- status;
- respondentes, promotores, neutros e detratores.

## NPS docente — 01C

Permanece sem comparação por curso, pois a pesquisa institucional dos docentes é anônima e não contém vínculo confiável com curso, disciplina ou diretoria de origem do respondente.

## Banco

Nenhuma migration nova. `SCHEMA_VERSION = 31`, mantendo `031_academic_faculty_nps_v08250.sql` como migration corrente.
