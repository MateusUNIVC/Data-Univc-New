# Academic NPS Core — v0.8.24.0

## Objetivo

A v0.8.24.0 fecha a ambiguidade histórica do KPI acadêmico `01`, separando o NPS institucional dos alunos do NPS do Curso em contratos independentes e compartilhados entre DTNH e DCS.

## Contrato oficial

- `DTNH-01A` / `DCS-01A`: **NPS da Instituição · Alunos**.
- `DTNH-01B` / `DCS-01B`: **NPS do Curso**.
- `DTNH/DCS-01` permanece apenas como referência histórica e é desativado no catálogo operacional.

O código legado `-01` sempre media NPS do Curso. Por isso, a migration 030 move metas e planos existentes apenas para `-01B`. Nenhuma meta institucional retroativa é criada.

## NPS institucional

O valor institucional continua representando a UNIVC. O backend agrega as parcelas DTNH e DCS por `respondentes`, `promotores`, `neutros` e `detratores`, calculando o NPS somente depois da soma. Isso evita média simples entre NPS de tamanhos de amostra diferentes.

O filtro de diretoria não altera esse número institucional. Ele altera apenas o detalhamento por curso:

- no DTNH, `by_course` contém apenas cursos DTNH;
- no DCS, `by_course` contém apenas cursos DCS.

## Painel Executivo

O painel passa a ter quatro KPIs acadêmicos:

1. NPS da Instituição · Alunos (`01A`);
2. NPS do Curso (`01B`);
3. Avaliação Docente pelo Aluno (`02`);
4. Taxa de Aprovação (`03`).

01A e 01B possuem cards, séries e metas independentes. O alias JSON `cards.nps`/`metas_vigentes.nps` permanece temporariamente apontando para 01B para compatibilidade com integrações anteriores.

## Metas

- 01A aceita exclusivamente recorte `TOTAL`;
- 01B aceita `TOTAL` ou um curso ativo da diretoria;
- 01B não aceita disciplina;
- comparação executiva por curso recebe `meta`, `atencao`, `meta_vigencia`, `meta_recorte` e `status`, permitindo que a etapa visual posterior use cores orientadas à meta sem recalcular regras no navegador.

## Migration

Arquivo: `database/030_academic_nps_kpi_split_v08240.sql`

A migration:

- cria/ativa 01A e 01B para DTNH/DCS;
- cria schedules semestrais e herda prazos do antigo 01 quando existirem;
- converte metas e planos 01 para 01B, removendo duplicatas equivalentes antes da conversão;
- desativa definição e schedule do código 01 antigo;
- atualiza `data_univc_schema_version` para 30.

O `scripts/init_local.py` implementa o equivalente seguro para SQLite persistente.
