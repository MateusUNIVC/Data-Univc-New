# EXCEL-OFFICIAL-05B — DPE Parity Closure

## Status

Semantic closure complete in parallel. `/api/dpe/excel` remains on the current DPE workbook until 05C.

## Scope closed in 05B

### Management targets

The Excel Official consumes the same DPE management target payload used by the current application. Active targets are pre-resolved by competence and dimension before workbook generation and written to the protected `METAS EFETIVAS DPE` dataset.

Targets are not duplicated as independent business inputs in the workbook. KPI target formulas reference the effective target dataset through `TargetBindingSpec`.

Percentage targets are converted only at the Excel presentation boundary (0–100 backend scale to 0–1 Excel scale). Currency, count, hour and ratio targets keep their native semantic scale.

Range targets, such as average workload per teacher, are intentionally **not collapsed into one target value**. Their minimum/maximum values remain visible in `METAS EFETIVAS DPE` and `METAS DPE BACKEND` and are documented as backend-governed ranges.

If more than one active target resolves to the same metric and selector, the workbook does not sum or arbitrarily select one of them. The effective target is left blank and `target_collision_count` becomes positive, which surfaces as a governance warning.

### Previous competence

The DPE comparison continues to use the previous competence selected by `DPECostAnalyticsRepository.previous_period`, normally the previous month. The protected `RESUMO ANTERIOR DPE` dataset stores the comparison evidence for:

- total revenue;
- total expense;
- institutional result;
- institutional margin.

Because the official competence is fixed in a DPE snapshot, this comparison is also fixed. Offline changes to Course/Context/Cost Center do not pretend to recompute a different historical comparison.

### Teaching and productivity

The workbook now exposes current Cost Engine facts for:

- teaching cost;
- total workload hours;
- average workload hours per teacher;
- teacher count.

These are not new measurements and do not introduce another financial source of truth. They are derived from the same DPE teaching/allocation payload already used by the application.

### Allocation quality and month-close governance

Protected governance evidence is exported in `RESUMO GESTAO DPE` and `GOVERNANCA DPE`, including:

- allocated expense;
- unallocated expense;
- reconciliation percentage;
- closure blocker count;
- payroll pending count;
- active target collision count;
- checklist PASS/WARNING/BLOCKER counts.

During an in-progress competence these controls are quality **warnings**, not workbook release blockers. A month can therefore be analyzed before formal close without representing it as closed or fully reconciled.

### Official action plan

Management actions remain official snapshot rows in `PLANO_DE_ACAO`. `probable_cause` is preserved as Diagnosis/Cause and local workbook follow-up remains explicitly separate from Data UNIVC persistence.

## Expanded parity gate

`dpe_excel_parity.py` now independently checks:

1. revenue/expense/result/margin from ledgers;
2. course/context economics from revenue + official allocation memory;
3. cost-center expense totals;
4. previous-competence values and backend card deltas when supplied;
5. DPE management facts against their operational sources;
6. course management facts against course analytics;
7. active target `current_value` against its referenced management fact;
8. closure checklist counts against checklist rows;
9. closure official-run totals against the selected allocation run.

Representative 05B QA: **61 cases, 0 failures, CANDIDATE_PASS**.

## Explicit non-goals

05B does not:

- change `/api/dpe/excel`;
- change the DPE Cost Engine;
- add migrations;
- infer overhead;
- flatten range targets;
- create a second measurement store;
- mark an in-progress month as unexportable only because close checks remain pending.

Schema remains **53**.

## Next step

05C is intentionally short: canonical DPE route + UI unification + feature-flag rollback + production parity/smoke gate.
