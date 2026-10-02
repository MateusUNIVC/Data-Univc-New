# Excel Official V1 - Action Plan

## Purpose

Phase 01I materializes the institutional `PLANO_DE_ACAO` surface from `ActionPlanSpec`.

Public rendering API:

`write_action_plan_sheet(workbook, spec) -> ActionPlanRef | None`

The component distinguishes immutable snapshot actions from local workbook follow-up without implying synchronization back to Data UNIVC.

## Row provenance

Every declared action row has an explicit source:

- `OFFICIAL`: imported from the authorized snapshot and always locked;
- `LOCAL`: workbook-local follow-up. Only fields listed in `local_editable_fields` are unlocked.

The same semantic column may therefore be read-only in an official row and editable in a local row without duplicating the schema.

## Local editing contract

`ActionPlanSpec.local_editable_fields` is the allow-list for editable local cells. Everything else remains locked.

The sheet always states that local changes remain only in the downloaded workbook and are not synchronized automatically with Data UNIVC.

`days_remaining_field` is always derived and cannot be declared locally editable or supplied as source data.

## Status

Status options are declared by `ActionPlanSpec.status_options` and materialized in the visible/protected `LISTAS DE APOIO` technical layer under the stable defined name `LST_ACTION_STATUS`.

Only LOCAL status cells receive the dropdown validation. Official status values remain locked snapshot data.

When `indicator_field` is locally editable and registered metrics exist, the Core also materializes `LST_ACTION_INDICATOR` from `MetricSpec.label` values and applies an indicator dropdown to LOCAL rows.

`completed_statuses` controls which status values suppress the days-remaining calculation.

## Days remaining

When deadline/status/days-remaining fields are present, the Core writes an Excel-2019-compatible formula equivalent to:

`IF(deadline is blank OR status is completed, blank, deadline - TODAY())`

The result remains numeric and locked. Negative values receive an overdue visual flag.

## Capacity

`local_blank_rows` controls the number of blank local rows shipped in the snapshot. Contract V1 deliberately avoids preallocating hundreds or thousands of future rows.

## Protection

- official rows: fully locked;
- local source/provenance cell: locked;
- local editable allow-list: unlocked and visually identified as input;
- derived fields: locked;
- worksheet protection: enabled as an accidental-editing guard, not a security boundary.

Authorization is enforced before data enters the workbook.

## Compatibility

The Action Plan uses standard Excel Tables, list validation and `IF`/`OR`/`TODAY` formulas. It does not require dynamic arrays, macros, external links, `INDIRECT` or `OFFSET`.
