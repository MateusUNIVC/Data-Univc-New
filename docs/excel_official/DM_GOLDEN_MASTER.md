# EXCEL-OFFICIAL-03A — DM Adapter + Golden Master + Parity

## Status

**Implemented in parallel. DM production routes remain unchanged in 03A.**

The Directorate of Master's Programs (DM) now has a declarative `DMAdapter` that produces a `WorkbookSpec` for the shared `ExcelOfficialCore`. The current DM Excel V3 remains the UX/behavior Golden Master for parity review; business semantics come from `dm_analytics.py` and the authorized DM payload assembled by the current backend.

## Source of truth

The transition provider `dm_excel_official.py` reuses the current authorized DM data structures and calls `build_dm_dashboard()` to retain the same semantic source used by the web dashboard.

The Excel Official adapter does not treat calculated values from DM V3 as a second source of truth. Instead it exports sufficient statistics and authorized student/defense rows so the shared Core can recalculate supported offline recuts.

## Official and analytical metrics

| DM concept | Excel Official metric | Semantics |
| --- | --- | --- |
| `DM-01` | `dm.cohort_members` | members per cohort |
| Active students | `dm.active_students` | active members in selected scope |
| Graduated students | `dm.graduated_students` | graduated members in selected scope |
| Occupancy | `dm.occupancy_rate` | members / authorized vacancies |
| Dropout | `dm.dropout_rate` | dropped / members |
| `DM-02` | `dm.average_months_to_defense` | weighted average months from confirmed individual entry to defense |
| Defenses ≤24m | `dm.on_time_graduation_rate` | graduated within 24 months / confirmed entry dates |
| Risk >30m | `dm.active_over_30_no_defense` | active students above 30 months without defense |
| Entry completeness | `dm.entry_date_completeness` | confirmed entry dates / members |

`DM-01` and `DM-02` preserve the official DM semantics. Occupancy, on-time defense, risk and completeness are analytical measures used to make the workbook operational without changing the meaning of the official indicators.

## Offline datasets

The adapter declares:

- `dm_areas` → `AREAS DM`;
- `dm_cohorts` → `TURMAS`;
- `dm_cohort_numbers` → `DIM_TURMA`;
- `dm_matrix_metrics` → `DIM_KPI_MATRIZ_DM`;
- `dm_cohort_metrics` → `INDICADORES TURMAS`;
- `dm_students` → `ALUNOS E DEFESAS`;
- `dm_targets_effective` → `BASE METAS DM`.

`ALUNOS E DEFESAS` is classified as restricted data and remains protected. It is included only within the authorization scope of the exported snapshot.

## Parameters and cutoff governance

Interactive offline parameters:

- Area;
- Turma;
- Turma de comparação;
- KPI da Matriz.

Protected snapshot parameters:

- Data de corte;
- Período-alvo derived from the cutoff.

The cutoff date is deliberately fixed in an official offline workbook. A different competence/cutoff is obtained by choosing that date in Data UNIVC and exporting a new Excel Official snapshot. This prevents an already-issued file from silently changing its temporal reference and effective targets after export.

## Dashboard

The executive panel exposes five primary KPI cards:

1. DM-01 · Membros por turma;
2. Alunos ativos;
3. Ocupação de vagas;
4. DM-02 · Tempo médio até defesa;
5. Defesas em até 24 meses.

Four charts show cohort evolution for members, average defense time, on-time defenses and students at risk above 30 months.

## Matrix

The standard institutional `MATRIZ` uses Área × Número da Turma and supports the selector:

1. `DM-01 · Membros por turma`;
2. `Ocupação · Vagas`;
3. `DM-02 · Tempo médio até defesa`;
4. `Defesas · Até 24 meses`;
5. `Risco · >30m sem defesa`.

Percentage options remain numeric and use the shared matrix display scaling instead of converting values to text.

## Targets

Effective DM targets are exported to `BASE METAS DM` and bound through the shared `TargetBindingSpec` mechanism using the protected cutoff semester.

The current 03A candidate wires targets for:

- DM-01 members per cohort;
- DM-02 average months to defense.

## Quality and limitations

Quality checks cover:

- cohort/student/metric datasets present;
- occupancy/defense/on-time valid metric ranges;
- Area and Cohort dimensions;
- snapshot export id and authorization scope.

Declared limitations include:

- cutoff fixed in the exported offline snapshot;
- student-level data is restricted and must remain within the authorized workbook scope.

## Golden Master and parity

Golden Master: the current `dm_excel_v3_builder.py` output generated from the same DM demo/authorized structures.

On the 2026-08-28 representative QA snapshot, the new source components matched `build_dm_dashboard()` for:

- members: 132;
- active: 61;
- occupancy: 77.65%;
- average months to defense: 23.54;
- on-time graduation: 24.24%;
- active >30m without defense: 9.

Parity failures: **0**.

The Excel Official workbook passed the Core release audit with **0 findings**, no external links and no VBA.

## Structural differences from DM V3

These differences are intentional:

- the six institutional Core sheets always lead the workbook;
- `QUALIDADE E GOVERNANÇA`, `MATRIZ` and `PLANO_DE_ACAO` are standardized instead of DM-specific variants;
- DM-01/DM-02 analysis is consolidated into the common dashboard/matrix model;
- the official cutoff is immutable inside the exported snapshot;
- the student/defense base remains available as protected authorized evidence;
- `CALC` and support lists follow Contract V1 visibility/protection rules.

## Route strategy

03A does **not** replace `/api/dm/excel` or `/api/dm/excel-interativo`.

The next condensed phase, 03B, is the DM production cutover: route unification to one Excel Oficial action, production parity gate/smoke, and rollback preparation. Until then, `dm_excel_official.py` is a parallel candidate builder.
