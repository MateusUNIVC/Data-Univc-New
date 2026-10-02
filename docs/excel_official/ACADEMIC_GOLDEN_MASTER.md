# EXCEL-OFFICIAL-02B — Academic Parity Closure Candidate

## Status

**Academic parity blockers closed in the shared Core. Production route still not migrated.**

DTNH and DCS continue to share one declarative `AcademicAdapter` (adapter version 2) and the common `ExcelOfficialCore`.

## Source of truth

Business semantics continue to come from the current Data UNIVC Academic stack. The transition provider reuses `build_academic_interactive_payload()` so the candidate consumes the same authorized full-history snapshot assembled for the current Academic interactive export.

Prior DTNH spreadsheets remain Golden Masters for UX/behavior only; they are not an independent source of metric semantics.

## Stable metric mapping

| Legacy Academic code | Excel Official metric | Semantics |
| --- | --- | --- |
| `DTNH/DCS-01A` | `academic.nps_institution_students` | Institutional student NPS; period only on the executive KPI |
| `DTNH/DCS-01A` matrix breakdown | `academic.nps_institution_students_by_course` | Institutional student NPS disaggregated by course; matrix support metric |
| `DTNH/DCS-01B` | `academic.nps_course_students` | Course NPS; period + course |
| `DTNH/DCS-01C` | `academic.nps_institution_faculty` | Institutional faculty NPS; anonymous population; period only |
| `DTNH/DCS-02` | `academic.faculty_favorability` | favorable / classified; unavailable when any unmapped response exists |
| `DTNH/DCS-03` | `academic.approval_rate` | approved / finalized |
| — | `academic.average_grade` | grade sum / grade count; never average-of-averages |

The 01A matrix breakdown is deliberately a separate MetricSpec instead of pretending that the institutional KPI itself is course-filterable.

## Offline datasets

The candidate now includes:

- `academic_periods` → `DIM_PERIODO`;
- `academic_history_windows` → `DIM_JANELA`;
- `academic_matrix_metrics` → `DIM_KPI_MATRIZ`;
- `academic_courses` → `CURSOS`;
- `academic_disciplines` → `DISCIPLINAS`;
- `academic_nps_institution` → `NPS INSTITUICAO`;
- `academic_nps_institution_course` → `NPS INST POR CURSO`;
- `academic_nps_course` → `NPS CURSO`;
- `academic_nps_faculty` → `NPS DOCENTES`;
- `academic_nps_distribution` → `NPS DISTRIBUICAO`;
- `academic_teacher` → `AVALIACAO DOCENTE`;
- `academic_results` → `RESULTADOS ACADEMICOS`;
- `academic_goals_base` → `BASE METAS ACADEMICAS`.

Fact datasets carry the aggregation components needed for mathematically correct offline recuts, not only already-calculated KPI values.

## Parameters

The Academic candidate now supports:

- reference period;
- comparison period;
- history window: 4, 6, 8, 12 or `Todo histórico`;
- matrix KPI selector;
- course;
- dependent discipline selector.

Site state seeds the initial workbook state; the authorized snapshot remains available for offline recutting.

## Dynamic goals

The shared Core now supports `TargetBindingSpec`.

Academic effective goals remain pre-expanded by the current backend hierarchy and the workbook performs exact offline lookup by the declared criteria. This preserves backend ownership of inheritance while allowing target cells to react to parameter changes.

Examples:

- 01A/01B: period + course + `(todas)` discipline;
- 01C: period + `(todos)` course + `(todas)` discipline;
- 02/03: period + course + discipline.

Academic percentage goals are stored as percentage points in the current payload and normalized to the metric's native 0..1 unit for KPI cards. Matrix presentation rescales percentage metrics to 0..100 numeric points to coexist safely with NPS in a single selectable matrix.

## History-window behavior

All Academic evolution charts now declare:

- `window_parameter = history_window`;
- `window_reference_parameter = reference_period`;
- `window_max_categories = 12`.

`CALC` materializes fixed chart slots that dynamically end at the selected reference period. A numeric window shows the requested number of semesters; `Todo histórico` is capped at the most recent 12 semesters ending at reference, matching the current V3 readability rule.

The implementation remains Excel 2019 compatible and does not use `FILTER`, `XLOOKUP`, `SORT`, `UNIQUE`, `INDIRECT` or `OFFSET`.

## Matrix metric selector

The Academic matrix now follows `P_MATRIX_METRIC` and supports:

1. `01A · NPS Instituição · Alunos` — via the dedicated course-breakdown metric;
2. `01B · NPS do Curso`;
3. `02 · Avaliação Docente`;
4. `03 · Aprovação`.

Cells remain numeric. For the heterogeneous selector, NPS stays in NPS points and percentage metrics are displayed as numeric percentage points (0..100) with the matrix unit contract, rather than being converted to text.

Teacher/Approval matrix views aggregate all disciplines for each course, matching the current Academic V3 matrix behavior, while KPI cards continue to honor the selected discipline.

Matrix targets are dynamic by selected KPI, reference period and row course.

## Dashboard

The executive panel keeps five primary KPI cards and five evolution charts:

1. NPS Institution — Students (01A);
2. NPS Course (01B);
3. NPS Institution — Faculty (01C);
4. Faculty Favorability (02);
5. Approval Rate (03).

All five cards now expose dynamic target cells when an effective target exists. Average Grade remains a reusable metric with `grade_sum` + `grade_count`, but is not promoted to a sixth executive card without a separate product decision.

## Quality rules

The candidate validates:

- available periods/courses;
- required fields on Academic fact datasets;
- metric valid ranges;
- period/course/discipline dimension availability;
- snapshot export id and authorization scope;
- payload-reported NPS/result source inconsistencies.

Faculty Favorability retains the current semantic guard: any unmapped response makes the selected recut unavailable instead of calculating a partial percentage.

## Golden Master comparison

Reference workbooks:

- `Painel_DTNH_v0.5.9_DEMONSTRATIVO.xlsx`;
- `Prototipo_DTNH_Excel_Interativo_V3_v0.9.6.6.xlsx`.

Contract V1 differences remain intentional: `CALC` and `LISTAS DE APOIO` are visible/protected and the six institutional sheets always lead the workbook.

## Parity status

The three explicit 02A cutover blockers are now closed in the candidate:

- dynamic effective-goal binding — **closed**;
- shared history-window behavior — **closed**;
- numeric multi-metric matrix selector — **closed**.

The remaining prerequisite before endpoint replacement is a production-data parity/cutover audit using representative authorized DTNH and DCS snapshots.

## Route strategy

02B still does **not** change `/api/excel-interativo` or `excel_service.py` production behavior.

The transition module `academic_excel_official.py` can generate the new workbook from the same authorized Academic payload. Production cutover belongs to the next controlled migration step after final parity evidence is accepted.

## Phase 02C — Production Parity & Cutover Readiness

02C does not enable the new Academic engine by default. It adds a controlled production-readiness gate around the existing `/api/excel-interativo` path.

### Parity harness

`academic_excel_parity.py` audits the same authorized full-history payload used by Academic V3. It compares the current Academic semantics against the Excel Official MetricSpecs across:

- 01A institutional student NPS by period;
- 01A institutional student NPS course breakdown;
- 01B course NPS by period/course;
- 01C faculty institutional NPS by period;
- KPI 02 at total, course and discipline recuts;
- KPI 03 at total, course and discipline recuts;
- Average Grade using `grade_sum / grade_count` at the same result recuts.

The audit also cross-checks values already reported in the current payload against the exported sufficient statistics. This allows a report to detect both `backend/current payload -> components` drift and `current semantics -> Excel Official Core` drift.

### Readiness states

- `BLOCKED`: semantic mismatch, source-quality failure, workbook build failure, or Excel Official release-audit failure.
- `CANDIDATE_PASS`: all checks pass, but evidence did not come from a live production repository.
- `READY`: all checks pass on a production snapshot.

Cross-directorate cutover is `READY` only when **both DTNH and DCS** are `READY` and were audited on the same application/schema version.

### Production helper

`audit_academic_repository_parity(repo, ...)` accepts an already-authorized `DatabaseRepository`. It does not create a wider database scope and builds the audit from the same `build_academic_interactive_payload()` used by Academic V3.

For offline or retained authorized snapshot payloads:

```bash
python scripts/audit_academic_excel_parity.py dtnh_snapshot.json dcs_snapshot.json --source-kind production --output-dir parity_output
```

Only use `--source-kind production` for snapshots actually captured from the live authorized repository.

### Cutover flag

`excel_service.export_academic_interactive_excel()` now supports:

```text
ACADEMIC_EXCEL_OFFICIAL_ENABLED=false
```

Default `false` keeps the existing Academic V3 builder unchanged. After accepted DTNH/DCS production parity evidence, setting the flag to `true` switches the existing endpoint to `build_academic_excel_official_workbook_bytes()` without changing the public route or frontend contract.

There is intentionally no silent fallback from Excel Official to V3 when the flag is enabled: a post-cutover Core failure must remain visible rather than serving an untracked different engine.
