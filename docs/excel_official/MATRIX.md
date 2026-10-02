# Excel Official V1 - Matrix Engine

## Purpose

Phase 01G materializes the institutional `MATRIZ` from `MatrixSpec` without introducing directorate-specific formulas or layout rules.

Public rendering API:

`write_matrix_sheet(workbook, spec, dataset_refs, parameter_system) -> MatrixRef | None`

The component is optional: when `WorkbookSpec.matrix` is `None`, it performs no workbook mutation.

## Calculation semantics

The matrix reuses the same metric-expression engine used by the 01E KPI cards and the 01F Charts Engine. A matrix cell therefore follows the exact `MetricSpec` / `MetricBinding` aggregation contract for:

- value / sum;
- count;
- ratio;
- average from sum/count;
- weighted average;
- NPS from promoters/detractors/respondents.

No matrix-specific business formula is allowed.

## Dimension overrides

`row_dimension` and `column_dimension` define the two axes. For each matrix cell, the row and column members override the corresponding parameter filters while every other metric-bound workbook filter remains active.

Example: a `course x period` matrix calculates each course/period pair independently of the currently selected course/reference period, while a third dimension such as discipline can continue to follow `PARAMETROS` if it is part of the metric binding.

Both dimensions must:

- exist in `WorkbookSpec.dimensions`;
- be different;
- be allowed by the selected `MetricSpec` when `allowed_dimensions` is declared;
- map to physical columns in the metric dataset.

## Ordering

The column axis always preserves the canonical `DimensionSpec` order. This is important for time dimensions such as semester/month.

The row axis may use:

- default / `dimension_asc`;
- `dimension_desc`;
- `label_asc`;
- `label_desc`.

Contract V1 does not rank matrix rows by metric value.

## Target

When `MatrixSpec.target` is present, `MATRIZ` adds a `Meta` column using the same number format as the selected metric.

The target is presentation/reference metadata and does not alter the metric calculation.

## Delta

When `MatrixSpec.delta = true`, the matrix adds a `Δ` column calculated as:

`last displayed column - previous displayed column`

The delta is numeric, not preformatted text. Its number format follows metric semantics:

- percentage -> percentage-point-style numeric difference;
- NPS / score / decimal -> signed numeric difference;
- currency -> currency difference.

A delta requires at least two members in the column dimension.

## Missing data

`empty_behavior` supports:

- `blank` (default): no matching facts remain blank;
- `zero`: no matching facts display numeric zero.

The choice is explicit because absence of data and a legitimate zero are semantically different.

## Layout and protection

The institutional sheet is named `MATRIZ`, is visible and protected, and contains:

- institutional title/subtitle;
- selected metric identity;
- row-dimension header;
- one column per column-dimension member;
- optional `Meta`;
- optional `Δ`.

Formula cells are derived/locked. Labels and targets are static/imported/locked. Contract V1 does not make matrix cells editable.

## Current Contract V1 scope

`MatrixSpec.metric_code` selects one metric for one matrix instance. The sheet clearly identifies that metric, but 01G does not yet introduce a user-editable multi-metric dropdown. A future extension may add a metric selector only when mixed-unit number formatting and per-metric targets can remain numeric and auditable; 01G deliberately avoids converting matrix values to formatted text to simulate such a selector.

## Compatibility

Matrix formulas remain compatible with the Excel Official V1 target (Excel 2019+/Microsoft 365) and do not require `FILTER`, `XLOOKUP`, `SORT`, `UNIQUE`, `INDIRECT` or `OFFSET`.
