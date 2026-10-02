# Excel Official V1 - Dashboard & KPI Cards

## Purpose

Phase 01E materializes the institutional `PAINEL` and makes KPI rendering generic. The dashboard does not know DTNH, DCS, DM, DADM or DPE. It consumes `WorkbookSpec`, runtime metric semantics, materialized dataset references and the parameter system.

## Public rendering API

`write_dashboard_sheet(workbook, spec, dataset_refs, parameter_system) -> DashboardRef`

The function performs a complete preflight before creating `PAINEL`.

## Runtime metric contract

`MetricSpec` now provides the minimum executable semantics needed by KPI cards:

- stable metric code and label;
- aggregation method;
- unit;
- allowed dimensions;
- offline-recut capability;
- valid range metadata;
- display precision / optional number format.

V1 KPI aggregations are:

- `value`;
- `sum`;
- `count`;
- `ratio`;
- `average`;
- `weighted_average`;
- `nps`.

This is intentionally not yet an application-wide metric registry. 01E only establishes the executable contract the future shared registry will feed.

## MetricBinding

A `MetricBinding` maps semantic metric components to physical dataset columns.

Examples:

- NPS: respondents, promoters, detractors;
- ratio: numerator, denominator;
- average: sum, count;
- weighted average: weighted_sum, weight;
- sum/value: value_column.

Bindings also declare `filter_parameters`, mapping a semantic dimension to the workbook parameter used for the reference calculation.

Example:

`period -> reference_period`

`course -> course`

No dashboard formula contains directorate-specific filtering rules.

## Dataset dimension mapping

`DatasetSpec.dimension_columns` maps semantic dimensions to physical fact columns when their names differ.

If a fact dataset declares `filter_dimensions`, every filterable dimension must be resolvable either by:

- a same-named physical column; or
- `dimension_columns`.

## KPI formula semantics

The Core uses fixed snapshot ranges and Excel-2019-compatible formulas.

Filters are applied using `SUMPRODUCT` masks. An optional parameter/empty option such as `(todos)` acts as an all-members selection without using volatile `INDIRECT` or `OFFSET`.

### NPS

NPS is recomposed from components:

`((sum(promoters) / sum(respondents)) - (sum(detractors) / sum(respondents))) * 100`

The Core never calculates institutional NPS as an average of course-level NPS values.

### Ratio

Ratios use the summed numerator divided by the summed denominator.

### Average

Averages use the summed raw total divided by the summed count. The Core never averages already-calculated group averages.

### Weighted average

Weighted averages use `weighted_sum / weight` components supplied by the snapshot.

### Missing data

The Core first counts matching snapshot rows. When no row matches, the KPI returns blank rather than zero. This preserves the Contract distinction between real zero and no data.

## Comparison

`KpiSpec.comparison` names an alternate parameter whose `values_source` is the same dimension used by a reference filter.

Example:

- reference binding: `period -> reference_period`;
- comparison: `comparison_period`.

The comparison formula replaces only `period`; course and other filters remain unchanged.

Delta remains numeric in Excel (`reference - comparison`) and uses unit-appropriate number formatting.

## PAINEL structure

V1 01E creates:

1. institutional title and snapshot subtitle;
2. `CONTEXTO ATUAL` linked to the parameter named ranges;
3. `RESUMO EXECUTIVO DOS KPIs`;
4. reusable KPI cards;
5. `VISUALIZAÇÕES` section and chart anchors when ChartSpecs exist;
6. optional attention/governance text blocks.

01E deliberately creates no charts. 01F consumes the `DashboardRef.chart_anchors` generated here.

## KPI cards

The shared layout uses a 12-column dashboard grid and four three-column cards per row.

Each card can contain:

- metric label;
- reference value;
- comparison value;
- numeric delta;
- optional numeric target;
- snapshot/offline provenance note.

All styling/protection is provided by the 01B Design System.

## Preflight guarantees

Before `PAINEL` is created, the Core verifies:

- WorkbookSpec validity;
- `PAINEL` does not already exist;
- every KPI has an executable MetricSpec;
- every KPI has a MetricBinding;
- every required DatasetRef exists;
- bound components/values are numeric;
- filter dimensions and parameters are compatible;
- comparison parameter belongs to a dimension already used by the reference binding;
- every required physical column exists.

A preflight failure leaves the workbook without a partially-created `PAINEL`.

## Architectural boundary

`MetricSpec`, `DashboardSpec`, `KpiRef` and `DashboardRef` remain openpyxl-independent.

Only `excel_official/components/dashboard.py` materializes cells, formulas and layout.
