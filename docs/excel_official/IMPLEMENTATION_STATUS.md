# Excel Oficial - Implementation Status

## Contract

- Excel Official Contract: **V1**.
- Data UNIVC remains the operational and semantic source of truth.
- Official workbooks are offline authorized snapshots, not database clients.
- Import templates and official analytical exports remain separate products.
- Contract V1 does not depend on VBA/macros or external data connections.

## Phase EXCEL-OFFICIAL-01A

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- typed `WorkbookSpec` contract;
- snapshot and identity contracts;
- parameter, dataset, dimension and metric-binding contracts;
- declarative dashboard, KPI, chart and matrix contracts;
- quality, limitation, action-plan and technical-layer contracts;
- base `DirectorateAdapter` boundary;
- pre-render WorkbookSpec validation;
- institutional and technical sheet-name constants.

Not implemented yet:

- metric registry;
- theme/rendering engine;
- workbook generation;
- Academic adapter;
- DM adapter;
- DADM adapter;
- DPE adapter;
- Reitoria adapter;
- route/frontend migration.

## Migration safety

No existing builder, route, frontend component or legacy test is changed by 01A.
The new package can therefore evolve while the current Excel paths remain intact.

## Phase EXCEL-OFFICIAL-01B

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- institutional `ExcelOfficialTheme` as a single source of visual tokens;
- frozen UNIVC palette aligned with the Academic V3 / DTNH golden-master language;
- Arial typography tokens and institutional number-format tokens;
- semantic cell roles for input, imported, derived, static, control, technical, warning, error, success, KPI and structural content;
- reusable openpyxl named styles prefixed with `du_`;
- standard worksheet view/page defaults;
- centralized row-height primitives for titles, subtitles, sections and table headers;
- centralized lock/unlock helpers and worksheet-protection primitive;
- input cells are unlocked by style while imported/formula/technical cells are locked by default.

Still intentionally not implemented:

- workbook rendering/orchestration;
- institutional sheet components;
- tables/dataset writer;
- parameters/dropdowns;
- dashboard, charts and matrix builders;
- directorate adapters;
- route/frontend migration.

### Design-system rule

Directorate adapters must not define fonts, fills, borders, RGB values, protection rules or table/chart appearance. Those belong to the shared Excel Official design system/core.

## Phase EXCEL-OFFICIAL-01C

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- neutral `DatasetRef` returned by the rendering layer;
- reusable dataset/table writer under `excel_official/components/tables.py`;
- standardized standalone dataset sheets with title, provenance notice and table starting on row 4;
- Excel Tables sized to the actual snapshot instead of preallocated future ranges;
- one structural empty table row only when a zero-record dataset must remain a valid Excel Table;
- centralized type validation before worksheet mutation;
- semantic number formats derived from `ColumnSpec` and the institutional theme;
- imported vs technical cell roles applied automatically;
- literal handling for imported text beginning with `=` so source data is never executed as a formula;
- workbook-wide table-name collision protection and case-insensitive sheet collision protection;
- automatic column widths with institutional min/max bounds;
- visible and protected technical datasets;
- stronger WorkbookSpec validation for case-insensitive sheet/table collisions, duplicate Excel headers, empty datasets and cell-reference-like table names.

Still intentionally not implemented:

- workbook orchestration;
- parameter/dropdown engine;
- dimension/list writer;
- dashboard, KPI and chart builders;
- matrix builder;
- institutional sheets;
- directorate adapters;
- route/frontend migration.

### Dataset writer rule

`DatasetSpec` remains declarative and openpyxl-independent. Only the shared rendering component knows how to materialize it as an Excel Table. Directorate adapters must never write table cells directly.

## Phase EXCEL-OFFICIAL-01D

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- `PARAMETROS` institutional rendering from declarative `ParameterSpec`;
- visible/protected `LISTAS DE APOIO` technical layer;
- stable `P_*` names for parameter cells and `LST_*` names for dropdown sources;
- initial-state precedence: `InitialStateSpec` -> `ParameterSpec.initial_value` -> snapshot initial scope;
- dimension-backed dropdowns using `DimensionSpec` key/label/sort metadata;
- direct dataset-backed lists with explicit `values_column` when necessary;
- one-parent dependent dropdowns such as Course -> Discipline;
- non-volatile Excel 2019-compatible dependent ranges using `INDEX`, `MATCH` and `COUNTIF`;
- no `FILTER`, `XLOOKUP`, `INDIRECT` or `OFFSET` dependency;
- support for parent/child empty options such as `(todos)` / `(todas)`;
- date/number parameter formatting through the shared Design System;
- editable parameter cells unlocked while every other parameter/support cell remains protected;
- preflight that rejects invalid initial state, out-of-scope selections, type mismatches, parent-dimension inconsistencies, sheet collisions and defined-name collisions before workbook mutation;
- neutral `ParameterRef`, `SupportListRef` and `ParameterSystemRef` outputs for downstream Core components;
- `parent_key_column`, `values_column`, `data_type` and `number_format` contract extensions needed for generic directorate adapters.

Dimension backing datasets continue to use the 01C Dataset/Table Writer. 01D consumes the same declarative dimensions to create interactive lists, avoiding a second catalogue engine.

Still intentionally not implemented:

- workbook-wide orchestration/order;
- calculation layer;
- dashboard/KPI cards;
- charts;
- matrix;
- Quality & Governance sheet;
- Action Plan sheet;
- directorate adapters;
- route/frontend migration.

### Parameter-system rule

The preferred V1 API is `write_parameter_system()`. It performs full preflight before creating `PARAMETROS`, `LISTAS DE APOIO` or any defined name. Web filters seed the initial state; they do not shrink the authorized offline snapshot.

## Phase EXCEL-OFFICIAL-01E

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- institutional `PAINEL` shell generated from `DashboardSpec`;
- reusable KPI cards with a 12-column institutional layout;
- current-context strip bound to the `P_*` names created by 01D;
- runtime `MetricSpec` with V1 aggregation semantics for `value`, `sum`, `count`, `ratio`, `average`, `weighted_average` and `nps`;
- metric units and centralized KPI/delta number formatting;
- `MetricBinding.filter_parameters` so metrics declare which workbook parameter filters each dimension;
- `DatasetSpec.dimension_columns` so fact datasets map semantic dimensions to physical columns without hardcoding directorate logic;
- formula generation through Excel-2019-compatible `SUMPRODUCT`, `SUM`, `IF` and `IFERROR` only;
- NPS recomposition from promoters/detractors/respondents rather than averaging already-calculated NPS values;
- ratio and average recomposition from components rather than averaging percentages/averages;
- comparison KPI support by replacing only the bound dimension parameter (for example reference period -> comparison period);
- blank KPI result for zero-record snapshots rather than silently representing missing data as zero;
- neutral `KpiRef` and `DashboardRef` outputs for downstream components;
- chart anchor reservation for 01F without creating chart objects in 01E;
- preflight validation before creating `PAINEL`;
- protected dashboard output using the 01B Design System.

Still intentionally not implemented:

- shared application-wide metric registry/source-of-truth migration;
- chart objects (01F);
- matrix (01G);
- Quality & Governance (01H);
- Action Plan (01I);
- workbook-wide orchestration/metadata/audit (01J);
- directorate adapters;
- route/frontend migration.

### KPI rule

A directorate adapter never writes KPI formulas. It references a `MetricSpec` and a `MetricBinding`; the Core converts those declarations into Excel formulas. Adding a KPI must therefore not introduce an `if directorate == ...` branch in the renderer.

### Comparison rule

`KpiSpec.comparison` identifies an alternate parameter for the same semantic dimension already bound by the metric. The Core replaces only that dimension while preserving the remaining filters. This allows reference/comparison-period KPIs without hardcoding period semantics in the dashboard renderer.

## Phase EXCEL-OFFICIAL-01F

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- reusable Charts Engine under `excel_official/components/charts.py`;
- neutral `ChartRef` / `ChartSystemRef` outputs;
- consumption of the stable dashboard anchors reserved by 01E;
- visible/protected `CALC` helper ranges as auditable chart sources;
- line, column, horizontal-bar, pie and doughnut chart objects;
- shared metric-expression semantics with KPI cards rather than duplicated chart formulas;
- category-dimension override so evolution charts evaluate every dimension member while preserving other workbook filters;
- second-dimension multi-series charts;
- reference-vs-comparison series using alternate bound parameters;
- institutional semantic axes: NPS `-100..100`, percent `0..100%`, score `0..10`, counts from zero;
- shared theme palette for chart series and reusable chart sizing;
- pie/doughnut slice coloring and percentage labels;
- stable dimension/label sorting plus `top_n` truncation without dynamic arrays;
- Excel-2019-compatible helper formulas with no `FILTER`, `XLOOKUP`, `SORT`, `UNIQUE`, `INDIRECT` or `OFFSET` dependency;
- append-safe reuse of an existing `CALC` technical sheet;
- preflight that rejects invalid chart declarations before workbook mutation;
- stronger WorkbookSpec chart validation for binding/dataset mismatches, unsupported dimensions, comparison conflicts, circular-chart multi-series and sort semantics.

Still intentionally not implemented:

- metric-value ranking for `top_n` (only declared dimension/label ordering exists in V1);
- matrix (01G);
- Quality & Governance (01H);
- Action Plan (01I);
- workbook-wide orchestration/metadata/audit (01J);
- directorate adapters;
- route/frontend migration.

### Chart rule

A directorate adapter declares `ChartSpec`; it never creates an openpyxl chart, writes helper formulas or defines axis bounds/colors. The shared Core converts the declaration into `CALC` formulas and chart objects using `MetricSpec`, `MetricBinding`, `DatasetRef`, `ParameterSystemRef` and the institutional Design System.

## Phase EXCEL-OFFICIAL-01G

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- institutional `MATRIZ` engine under `excel_official/components/matrix.py`;
- neutral `MatrixRef` output;
- row-dimension x column-dimension evaluation using the same metric-expression engine as KPI cards and charts;
- axis dimensions override their corresponding parameter filters while unrelated bound filters remain active;
- canonical dimension ordering with optional row sorting by dimension/label;
- optional numeric `Meta` column using metric-native number formatting;
- optional numeric `Δ` column as last displayed member minus previous member;
- explicit `blank` vs `zero` missing-data behavior;
- visible/protected institutional matrix sheet;
- Excel-2019-compatible formulas with no dynamic-array/volatile lookup dependency;
- preflight and WorkbookSpec validation for metric binding, dimension compatibility, physical fact columns, sort behavior and empty behavior;
- no workbook mutation when matrix preflight fails.

Still intentionally not implemented:

- user-editable multi-metric selector inside one matrix (Contract V1 keeps matrix cells numeric and metric-format-correct rather than simulating mixed units with text);
- metric-value row ranking;
- per-row targets;
- Quality & Governance (01H);
- Action Plan (01I);
- workbook-wide orchestration/metadata/audit (01J);
- directorate adapters;
- route/frontend migration.

### Matrix rule

A directorate declares a `MatrixSpec`; it does not write matrix formulas or style cells. The shared Core resolves dimensions, `MetricSpec`, `MetricBinding`, `DatasetRef` and `ParameterSystemRef`, then writes the protected institutional matrix using the same metric semantics already used elsewhere in the workbook.

## Phase EXCEL-OFFICIAL-01H

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- institutional `QUALIDADE E GOVERNANCA` engine under `excel_official/components/quality.py`;
- neutral `QualityRef` / `QualityCheckRef` outputs;
- explicit quality severities `INFO`, `WARNING`, `ERROR`, `BLOCKING`;
- dataset checks for non-empty snapshots and required-field completeness;
- metric checks for current-filter data availability and declared valid ranges;
- dimension availability and snapshot-field checks;
- metric checks reuse the same `MetricSpec` / `MetricBinding` expression engine as KPI cards, charts and matrix;
- overall trust status based on **failed** checks plus actual declared limitations;
- explicit `SEM CHECKS DECLARADOS` state instead of a false green workbook;
- coverage section with period bounds, interactive dimensions and dimension-member counts;
- sources/bases section with provenance, row counts, sensitivity, authorization scope and grain;
- snapshot section with export/system/schema/contract/adapter metadata and payload hash;
- limitations section with severity and affected metric/dimension;
- visible/protected audit sheet with conditional semantic status formatting;
- preflight and WorkbookSpec validation before workbook mutation;
- Excel-2019-compatible formulas without dynamic arrays or volatile lookup functions.

Still intentionally not implemented:

- Action Plan (01I);
- workbook-wide orchestration/metadata/audit (01J);
- directorate adapters;
- route/frontend migration.

### Quality rule

A check severity is the consequence of a failed check, not the current workbook status. Known `LimitationSpec` entries represent conditions that actually exist and therefore contribute directly to the overall status. Metric checks remain parameter-sensitive after download; structural snapshot checks remain fixed to the exported data.

## Phase EXCEL-OFFICIAL-01I

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- institutional `PLANO_DE_ACAO` engine under `excel_official/components/action_plan.py`;
- explicit action-row provenance through `OFFICIAL` and `LOCAL` row sources;
- immutable official rows and allow-list editing for local rows;
- local-editing notice stating that workbook changes do not synchronize automatically with Data UNIVC;
- configurable local blank-row capacity without large preallocated future ranges;
- stable action-status list in visible/protected `LISTAS DE APOIO` and `LST_ACTION_STATUS` defined name;
- status dropdown applied only to editable local rows;
- indicator dropdown generated from registered `MetricSpec` labels for editable local rows;
- derived/locked `Dias restantes` formula based on deadline, completed-status semantics and `TODAY()`;
- conditional visual flags for status and overdue local/official actions;
- Excel Table materialization with institutional styles, widths, freeze panes and worksheet protection;
- literal handling of imported text beginning with `=`;
- neutral `ActionPlanRef` output;
- preflight and WorkbookSpec validation for field declarations, row sources, status semantics, derived fields and capability compatibility;
- Excel-2019-compatible formulas without dynamic-array or volatile lookup dependencies.

Still intentionally not implemented:

- workbook-wide orchestration/metadata/audit (01J);
- directorate adapters;
- route/frontend migration;
- synchronization from local action-plan edits back to Data UNIVC (explicitly outside Contract V1).

### Action-plan rule

Official rows are snapshot evidence and never editable. LOCAL rows are workbook-only working space; only `local_editable_fields` are unlocked. The Excel file must never imply that a local edit has changed the Data UNIVC source of truth.

## Phase EXCEL-OFFICIAL-01J

Status: **implemented in parallel, not connected to production routes**.

Implemented:

- `ExcelOfficialCore.build(WorkbookSpec)` as the single orchestration entry point;
- deterministic build sequence for datasets, parameters, dashboard, charts, matrix, quality, action plan, README and technical registries;
- mandatory institutional workbook order: `LEIA-ME`, `PARAMETROS`, `PAINEL`, `QUALIDADE E GOVERNANCA`, `MATRIZ`, `PLANO_DE_ACAO`;
- protected placeholder surfaces when MATRIX or Action Plan is intentionally disabled, preserving the institutional contract;
- `LEIA-ME` institutional surface documenting snapshot identity, offline behavior, source-of-truth rules, local action-plan behavior and declared limitations;
- technical `METAS` and `INDICADORES` registries generated from the declarative contract;
- guaranteed visible/protected technical layers requested by `TechnicalSpec`;
- workbook standard properties plus custom Data UNIVC snapshot/contract/adapter metadata;
- `WorkbookArtifact` and `WorkbookBuildRefs` as the final build result;
- final structural/security/formula audit before release;
- release blocking for failed `BLOCKING` quality checks evaluated directly from the snapshot and initial filter state;
- save-time re-audit so post-build workbook mutations cannot bypass release checks;
- checks for required sheets/order, protection, allowed unlocked cells, macros, external links, table references, named-range references, formula error tokens, unsupported Excel functions and chart references;
- Excel-2019 compatibility enforcement for official formulas;
- forced full recalculation on open;
- round-trip test coverage for workbook metadata, charts, tables, order and recalculation settings.

Core V1 status after 01J: **complete and ready for directorate migration**.

Still intentionally not implemented:

- Academic adapter / DTNH-DCS Golden Master migration (02);
- DM adapter migration (03);
- DADM adapter migration (04);
- DPE adapter migration (05);
- Reitoria adapter migration (06);
- production route/frontend cutover;
- legacy builder removal.

### Release rule

An Excel Official artifact is releasable only after `ExcelOfficialCore` completes its final audit without `BLOCKING` findings. `WorkbookArtifact.save()` performs the audit again immediately before writing the XLSX.

## Phase EXCEL-OFFICIAL-02A — Academic Golden Master Candidate

Status: **implemented in parallel; DTNH/DCS production route intentionally unchanged**.

Implemented:

- one declarative `AcademicAdapter` shared by DTNH and DCS;
- transition provider `academic_excel_official.py` reusing the current authorized Academic V3 payload builder;
- stable Excel Official metric codes for 01A, 01B, 01C, 02, 03 and Average Grade;
- official Academic scope semantics: 01A/01C remain institutional while 01B/02/03 use their supported dimensions;
- NPS recomposition from respondents/promoters/detractors;
- Faculty Favorability as favorable/classified with explicit invalidation when unmapped responses exist;
- Approval as approved/finalized;
- Average Grade as grade sum/grade count, including export of the missing aggregation components from the current Academic result rows;
- Academic datasets for periods, courses, disciplines, NPS, NPS distribution, faculty evaluation, results and effective-goal audit base;
- five KPI cards and five evolution charts through the shared Core;
- Course × Period matrix candidate using Course NPS (01B);
- Academic Quality & Governance checks and source limitations;
- official action-plan rows plus local tracking rows;
- deterministic artifact-from-payload path for parity tests;
- `WorkbookArtifact.to_bytes()` release-safe serialization for future endpoint integration;
- DTNH/DCS adapter and workbook parity tests.

Explicit blockers before production cutover:

- dynamic effective-goal binding to KPI/matrix cells;
- history-window behavior in the shared Charts Engine;
- multi-metric matrix selector with numeric/format-safe semantics;
- production-data parity audit before route replacement.

### Academic migration rule

The legacy route remains the active production route while 02A is a candidate. The new adapter may be exercised in tests/QA without changing user-visible download behavior.

## Phase EXCEL-OFFICIAL-02B — Academic Parity Closure

Status: **implemented in parallel; DTNH/DCS production route intentionally unchanged**.

Closed the three 02A blockers:

- `TargetBindingSpec` and dynamic Academic goals/targets from `BASE METAS ACADEMICAS`;
- history-window parameter (4/6/8/12/Todo histórico) in the shared Charts Engine, capped at 12 visible semesters ending at the selected reference;
- numeric matrix KPI selector for 01A/01B/02/03 with dynamic targets.

Additional parity hardening:

- dedicated `academic.nps_institution_students_by_course` support metric/dataset for the legacy 01A course matrix behavior;
- percentage target normalization from payload percentage points to native 0..1 KPI semantics;
- percentage matrix values rescaled to numeric 0..100 points so heterogeneous matrix options remain numeric without `TEXT()`;
- Teacher/Approval matrix options aggregate all disciplines by course while their executive KPIs continue to honor the Discipline parameter;
- `METAS` technical registry now records dynamic target bindings instead of incorrectly reporting no targets;
- Contract/validation tests for target bindings, windowed charts and matrix selectors.

Route cutover remains deferred until a final production-data parity audit is accepted. No endpoint or frontend behavior is changed in 02B.

## Phase EXCEL-OFFICIAL-02C — Academic Production Parity & Cutover Readiness

Status: **implemented as a gated cutover mechanism; production flag remains off by default**.

Implemented:

- `academic_excel_parity.py` semantic parity harness;
- total/course/discipline parity cases for Academic KPIs and Average Grade;
- current-payload reported-value vs sufficient-statistics drift checks;
- current Academic V3 workbook build evidence;
- Excel Official workbook build + release-audit evidence;
- source-quality gate using Academic payload consistency counters;
- `BLOCKED` / `CANDIDATE_PASS` / `READY` report states;
- cross-directorate readiness requiring DTNH and DCS on the same app/schema version;
- offline JSON audit CLI under `scripts/audit_academic_excel_parity.py`;
- `audit_academic_repository_parity()` for live authorized server-side audits;
- `ACADEMIC_EXCEL_OFFICIAL_ENABLED` cutover flag in `excel_service.py`;
- default production behavior remains Academic V3 while the flag is false.

Production cutover remains a deployment decision after real DTNH and DCS reports reach `READY`.

## Phase EXCEL-OFFICIAL-02D — Controlled Production Cutover

Status: **cutover tooling implemented; no production activation performed in this development environment**.

Implemented:

- `academic_excel_cutover.py` freshness/version/hash gate for DTNH + DCS production parity evidence;
- cutover manifest with SHA-256 identity of the exact approved report bytes;
- 24h default evidence age window (operator-configurable at manifest generation);
- activation blocked unless both reports are production `READY`, source quality passed, both workbook builds passed and the Excel Official release audit passed;
- activation requires explicit `ENABLE_EXCEL_OFFICIAL` confirmation;
- atomic `.env.production` flag update with timestamped backup;
- rollback that is always available without parity evidence;
- `selected_academic_excel_engine()` operational engine marker;
- authenticated `X-Data-UNIVC-Excel-Engine` response header on `/api/excel-interativo`;
- authenticated HTTP/XLSX smoke script for DTNH/DCS;
- release-check guards preventing the production example from defaulting the cutover flag to true;
- VPS runbook under `docs/excel_official/ACADEMIC_CUTOVER_RUNBOOK.md`.

Production state remains unchanged until an operator executes the runbook with real authorized DTNH and DCS production reports. Academic V3 stays present as the immediate rollback engine.


## 02E — Academic Finalization

Status de desenvolvimento: **COMPLETE**.

- produção parity endpoint protegido por `require_fresh_reitoria`;
- `prepare_academic_excel_cutover.py` captura DTNH+DCS e gera o gate;
- smoke gera evidência JSON sem credenciais;
- finalization report exige DTNH+DCS pós-cutover em `excel_official`;
- `/api/bootstrap` publica o engine acadêmico atual;
- UI troca automaticamente `Excel Interativo` → `Excel Oficial` após ativação;
- Academic V3 permanece para rollback/observação.

Status de produção: **PENDING LIVE CUTOVER** até que o comando `finalize` gere `COMPLETE` no VPS.

## 02F — Academic export unification

- DTNH/DCS `/api/excel` now builds the Excel Official Core workbook.
- Academic UI exposes one analytical Excel only: **Excel Oficial**.
- Removed user-facing Snapshot/Base consolidada card and duplicate Excel Interativo action.
- Existing Academic dashboard context is preserved in the canonical export.
- `/api/excel-interativo` remains temporarily for compatibility only; it is not a second UI option.

## Phase EXCEL-OFFICIAL-03A — DM Adapter + Golden Master + Parity

Status: **implemented in parallel; DM production routes intentionally unchanged**.

Implemented:

- declarative `DMAdapter` over the shared `ExcelOfficialCore`;
- transition provider `dm_excel_official.py` reusing current authorized DM payload/dashboard semantics;
- stable metric specs for DM-01, DM-02, active/graduated, occupancy, dropout, on-time defense, risk >30m and entry-date completeness;
- protected official cutoff date and effective target semester;
- interactive Area, Cohort, comparison and Matrix KPI controls;
- dynamic DM-01 / DM-02 target bindings from `BASE METAS DM`;
- standard institutional dashboard, quality/governance, matrix and action-plan layers;
- restricted protected `ALUNOS E DEFESAS` evidence sheet;
- semantic parity tests against `build_dm_dashboard()`;
- same-snapshot structural comparison against DM Excel V3.

Representative QA parity on cutoff 2026-08-28: 6 compared measures, 0 failures; Excel Official release audit: 0 findings.

03A deliberately does not change `/api/dm/excel` or `/api/dm/excel-interativo`. Production route unification belongs to condensed phase 03B.

## Phase EXCEL-OFFICIAL-03B — DM Production Cutover

Status de desenvolvimento: **COMPLETE**. Status de produção: **PENDING LIVE CUTOVER** até o gate retornar `READY` no VPS.

Implementado:

- `/api/dm/excel` como única rota canônica de exportação apresentada na interface;
- `DM_EXCEL_OFFICIAL_ENABLED` com default `false` e rollback imediato para DM V2;
- `dm_excel_service.py` para seleção observável de engine;
- `X-Data-UNIVC-Excel-Engine` no download;
- filename oficial `Excel_Oficial_DM.xlsx` após ativação;
- `/api/dm/excel-interativo` mantido somente como alias de compatibilidade;
- remoção da duplicidade “Excel Interativo beta” da UI;
- `dm_excel_parity.py` comparando backend × Core na DM total, por área e por turma;
- rota Reitoria-only `/api/admin/excel-official/dm/parity`;
- smoke CLI `scripts/smoke_dm_excel_cutover.py`;
- release checks e env examples protegendo a flag desligada por padrão.

Nenhuma migration é necessária. O schema permanece 53.

## Phase EXCEL-OFFICIAL-04A — DADM Adapter + Golden Master + First Parity

Status: **implemented in parallel; DADM production routes intentionally unchanged**.

Implemented:

- declarative `DADMAdapter` over the shared `ExcelOfficialCore`;
- transition provider `dadm_excel_official.py` reusing current DADM V2/TALLOS normalized semantics;
- privacy-preserving offline aggregate cube at month × department × employee × channel × status × tabulation;
- exact sufficient statistics for attendance counts, finalization/open, TME, TMA, rating, rating coverage and transfers;
- explicit preservation of TALLOS 1–10 evaluation semantics without inferring an unapproved satisfaction threshold;
- backend-summary evidence for non-additive distinct counts such as protocols, people and active operators;
- dependent Department → Employee dimension plus Month, Channel, Status and Tabulation filters;
- five executive KPI cards, four evolution charts and Department × Month matrix with selectable metric;
- one-month snapshot compatibility with matrix delta disabled;
- Quality & Governance declarations for privacy, non-additive counts and evaluation semantics;
- official/local action-plan support through the shared Core;
- `dadm_excel_parity.py` comparing current DADM V2 backend vs Core candidate for full-period, department and month scopes;
- same-fixture DADM V2 Golden Master vs Excel Official structural audit.

Representative QA: **48 semantic parity cases, 0 failures, CANDIDATE_PASS; Excel Official release audit 0 findings**.

Explicit 04B closure items before production cutover:

- dynamic management targets with current TOTAL → department → channel inheritance;
- previous-period comparison/delta behavior;
- final treatment/documentation of median/P90 timing statistics that are not recomposable from the privacy-preserving aggregate cube.

No DADM route/frontend behavior is changed by 04A.

## Phase EXCEL-OFFICIAL-04B — DADM Parity Closure

Status: **semantic closure complete; production routes intentionally unchanged**.

Implemented:

- DADMAdapter v2;
- dynamic target bindings using protected `METAS EFETIVAS DADM`;
- exact DADM V2 target inheritance: Department > Channel > TOTAL, including vigency;
- automatic export of current V2 management targets/actions from schema 53;
- target unit conversion for seconds→minutes and 0–100→Excel percent;
- backend `previous_period` comparison for the exact export context;
- generic KPI `comparison_metric_code` support in the shared Core;
- protected `RESUMO ANTERIOR` evidence sheet;
- protected `PERCENTIS BACKEND` sheet for TME/TMA median and P90;
- explicit governance limitation that previous-period comparison is snapshot-context evidence and does not recut with offline filters;
- explicit governance limitation that percentiles are non-additive and therefore backend-only;
- parity report v2 including previous-period evidence.

No customer-level PII was added. DADM production route/frontend cutover remains 04C.

## Phase EXCEL-OFFICIAL-04C — DADM Complete

Status de desenvolvimento: **COMPLETE**. Status de produção: **PENDING LIVE CUTOVER** até a paridade real retornar `READY` no VPS.

Implementado:

- `/api/dadm/excel` como única rota canônica do download DADM;
- `DADM_EXCEL_OFFICIAL_ENABLED=false` por padrão e rollback para DADM V2;
- `dadm_excel_service.py` para seleção observável de engine;
- `X-Data-UNIVC-Excel-Engine` e filename `Excel_Oficial_DADM.xlsx` após ativação;
- `/api/dadm/v2/report.xlsx` mantido somente como alias de compatibilidade;
- workbook legado de gestão movido para `/api/dadm/legacy/excel`;
- UI DADM V2 usando somente `/api/dadm/excel`, com rótulo Excel Oficial após ativação;
- rota Reitoria-only `/api/admin/excel-official/dadm/parity`;
- smoke CLI `scripts/smoke_dadm_excel_cutover.py`;
- release checks protegendo flag, rota, UI e smoke;
- nenhum dado individual de cliente adicionado ao Excel Oficial;
- nenhuma migration; schema permanece 53.

QA 04C: 53 casos de paridade, 0 divergências, `CANDIDATE_PASS`; workbook final com 24 abas, 75 fórmulas, 4 gráficos, 17 tabelas, 0 links externos, 0 VBA e 0 campos brutos sensíveis auditados.

## Phase EXCEL-OFFICIAL-05A — DPE Adapter + Golden Master + First Parity

Status: **implemented in parallel; DPE production route intentionally unchanged**.

Implemented:

- declarative `DPEAdapter` over the shared `ExcelOfficialCore`;
- transition provider `dpe_excel_official.py` reusing `DPEExcelExportRepository` and the current consolidated Cost Engine payload;
- fixed official competence with interactive Course, Course/Context and Cost Center dimensions;
- strict separation between institutional result, course/context economics and cost-center expense views;
- financial metrics for revenue, expense, institutional result/margin, course result/margin, revenue/cost per student, selected expenses and allocation coverage;
- five executive charts and Course × Financial Component matrix;
- protected evidence datasets for revenue ledger, official expense ledger, official allocation memory, teaching reconciliation, management targets and closure checklist;
- governance limitations for institutional-vs-course scope, official allocation dependency and no inferred overhead;
- `dpe_excel_parity.py` recomposing ledger totals, context/course economics, cost-center expense totals and official allocated totals;
- same-fixture structural comparison against the current modern DPE workbook.

Representative QA: **25 semantic parity cases, 0 failures, CANDIDATE_PASS; Excel Official release audit 0 findings**.

Explicit 05B closure items before production cutover:

- dynamic management targets in final KPI/matrix surfaces;
- final previous-period behavior;
- teaching/productivity and allocation-quality metric closure;
- production-data parity.

No DPE route/frontend behavior is changed by 05A. Schema remains 53.

## Phase EXCEL-OFFICIAL-05B — DPE Parity Closure

Status: **semantic closure complete; production route intentionally unchanged**.

Implemented:

- DPEAdapter v2;
- effective management targets in protected `METAS EFETIVAS DPE`;
- KPI target bindings for institutional and course-level metrics;
- explicit preservation of range targets without flattening min/max;
- collision-safe target resolution with governance warning instead of arbitrary selection;
- teaching/productivity metrics from the existing DPE Cost Engine sources;
- allocation reconciliation, closure blockers, payroll pending and target-collision quality checks;
- official DPE management actions mapped to the institutional action-plan sheet;
- expanded DPE parity gate covering previous competence, management facts, target current values and closure/official-run reconciliation;
- no migration; schema remains 53.

Representative QA: **61 semantic parity cases, 0 failures, CANDIDATE_PASS; release audit allowed**.

Next: **05C — DPE Complete**, limited to canonical route/UI, production parity gate, feature flag, smoke test and rollback.
