# EXCEL-OFFICIAL-04A — DADM Golden Master candidate

Status: **implemented in parallel; DADM production route intentionally unchanged**.

## Scope

04A brings the current DADM V2/TALLOS operational analytics into the shared Excel Official Core without changing the production export endpoint. The semantic source remains the current normalized `dadm_tallos_attendances` fact table and the same `dadm_tallos_analytics` / `dadm_v2_report` rules used by the web product.

## Domain decisions

The Excel Official candidate follows the current DADM V2 semantics rather than reviving legacy assumptions from older management spreadsheets.

- **DADM-01** is represented operationally by TME and TMA.
- **DADM-02** uses the homologated TALLOS numeric evaluation scale **1–10** and evaluation coverage.
- No institutional “satisfaction” percentage is inferred from 1–10 scores without an approved threshold rule.
- Protocols, people and active operators are distinct-count metrics and therefore are **not** exposed as additive offline metrics.
- The interactive offline model contains only metrics that are additive or exactly recomposable from sufficient statistics.

## Privacy / offline grain

The candidate does **not** export protocol IDs, customer references, names, phone numbers, CPF/CNPJ or raw TALLOS payloads.

The offline fact sheet `OPERACAO TALLOS` is an aggregate cube at:

`month × department × employee × channel × status × tabulation`

with sufficient statistics for:

- attendances;
- finalized/open counts;
- TME sum + count;
- TMA sum + count;
- rating sum + count;
- transfers;
- sent/received messages.

Distinct protocol/person/operator totals stay in the protected `RESUMO BACKEND` sheet as snapshot evidence.

## Interactive metrics

Stable metric codes introduced in 04A:

- `dadm.attendances`
- `dadm.finalization_rate`
- `dadm.open_attendances`
- `dadm.tme_avg_minutes`
- `dadm.tma_avg_minutes`
- `dadm.rating_avg`
- `dadm.rating_coverage`
- `dadm.transfer_rate`

TME/TMA are displayed in minutes in Excel but are derived from the same seconds-based normalized facts used by the backend.

## Parameters / dimensions

The candidate supports:

- period/month;
- department;
- employee (dependent on department);
- channel;
- status;
- tabulation;
- matrix metric selector.

The authorized export window remains fixed by the snapshot; filters recut the authorized cube offline.

## Dashboard and matrix

The executive dashboard contains:

1. Attendimentos
2. DADM-01 · TME
3. DADM-01 · TMA
4. DADM-02 · Avaliação média
5. DADM-02 · Cobertura de avaliações

Evolution charts cover volume, TME, TMA and rating by month.

The institutional matrix is **Department × Month** and supports Attendimentos, TME, TMA, Avaliação média, Cobertura and Finalização. `delta=False` is deliberate so one-month snapshots remain valid.

## Quality / governance

The workbook records the following limitations explicitly:

- no inferred satisfaction threshold;
- non-additive distinct counts stay as backend-summary evidence;
- customer/protocol identifiers are excluded from the offline cube.

All DADM datasets, support dimensions, formulas and parameters remain protected according to the shared Contract V1 rules.

## 04A parity result

Representative fixture covering 3 months and 2 departments:

- semantic parity cases: **48**
- failures: **0**
- cutover status: **CANDIDATE_PASS** (fixture evidence)
- Excel Official release findings: **0**

Parity compares the current DADM V2 backend against the Core candidate for the full period, every department and every month across all eight recomposable metrics.

## Golden Master comparison

Current DADM V2 report:

- 8 sheets
- 43 formulas
- 8 charts
- 0 external links / 0 VBA / 0 prohibited functions in the representative QA file

Excel Official 04A candidate:

- 21 sheets
- 59 formulas
- 4 executive charts
- six institutional sheets first
- 0 external links / 0 VBA / 0 prohibited functions
- release audit allowed with 0 findings

The reduction from eight to four charts is intentional: detailed distributions remain auditable in protected data sheets while the institutional `PAINEL` keeps only executive views.

## Explicit 04B closure items

04A is the Golden Master / first-parity phase. Before DADM cutover, 04B must close:

1. **dynamic management targets** with the current DADM V2 inheritance semantics (`TOTAL → department → channel`, where applicable);
2. **previous-period comparison/deltas** for the executive indicators;
3. final decision/documentation for median/P90 values, which cannot be safely recomputed from the aggregated offline cube without exporting a finer-grained timing distribution.

No DADM production route is changed in 04A.
