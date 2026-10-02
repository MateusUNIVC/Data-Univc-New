# Excel Official V1 - Workbook Orchestration and Release Audit

## Purpose

Phase 01J closes the shared Excel Official Core. Directorate code provides a validated `WorkbookSpec`; the Core owns workbook construction, metadata, ordering, protection and release auditing.

Public entry point:

`ExcelOfficialCore().build(spec) -> WorkbookArtifact`

## Build pipeline

1. validate `WorkbookSpec`;
2. create a clean XLSX workbook and register the institutional Design System;
3. materialize snapshot datasets through the 01C writer;
4. materialize `LISTAS DE APOIO` + `PARAMETROS`;
5. build `PAINEL` and KPI cards;
6. build charts and auditable `CALC` helpers;
7. build `MATRIZ`, or the protected institutional placeholder when not configured;
8. build `QUALIDADE E GOVERNANCA`;
9. build `PLANO_DE_ACAO`, or the protected institutional placeholder when disabled;
10. build `LEIA-ME`;
11. materialize technical `METAS`, `INDICADORES` and any required technical placeholders;
12. apply standard/custom workbook metadata;
13. reorder sheets to the institutional contract;
14. enable full recalculation on open;
15. run the final release audit.

## Institutional order

The first six worksheets are always:

1. `LEIA-ME`
2. `PARAMETROS`
3. `PAINEL`
4. `QUALIDADE E GOVERNANCA`
5. `MATRIZ`
6. `PLANO_DE_ACAO`

Domain snapshot sheets follow. Technical sheets remain visible/protected and are placed after domain surfaces.

## Metadata

The XLSX carries ordinary document properties plus custom properties for:

- export ID;
- generation timestamp/user;
- directorate;
- authorization scope;
- system version;
- DB schema version;
- Excel Official Contract version;
- adapter code/version;
- payload hash.

These properties are persisted in the OOXML package and survive save/reopen.

## Release audit

The final audit checks, at minimum:

- required institutional sheets and order;
- visibility/protection of technical layers;
- protection of institutional sheets;
- unlocked cells only in declared `PARAMETROS` inputs and LOCAL Action Plan fields;
- absence of macros/VBA;
- absence of external workbook links;
- valid table references and unique table names;
- no `#REF!` in formulas, charts or named ranges;
- no stored formula error tokens;
- no dynamic/volatile functions prohibited by Contract V1;
- required custom metadata;
- failed `BLOCKING` quality checks.

`WorkbookArtifact.save()` re-runs the audit before writing the file. A blocked artifact cannot be saved as Excel Official.

## Quality checks before Excel recalculation

A `BLOCKING` quality rule is also evaluated in Python against the exported snapshot and the initial workbook state. Release therefore does not depend on desktop Excel calculating `QUALIDADE E GOVERNANCA` first.

Supported release-time checks mirror the V1 quality types:

- dataset non-empty;
- required dataset fields;
- dimension non-empty;
- snapshot field present;
- metric has data;
- metric valid range.

Metric evaluation reuses the same contract semantics for sum, count, ratio, average, weighted average and NPS.

## Offline boundary

The resulting workbook contains no database credentials, API client, external Excel link or macro. It is an authorized offline snapshot. The Data UNIVC remains the operational source of truth.

## Transition safety

01J does not alter current production Excel routes/builders. The next phase is 02, where Academic/DTNH-DCS is migrated to a real adapter and compared against the established Golden Master before any endpoint cutover.
