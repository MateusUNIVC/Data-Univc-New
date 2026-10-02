# Excel Official V1 - Charts Engine

## Purpose

Phase 01F materializes `ChartSpec` declarations as Excel chart objects without moving chart formulas, colors, axis rules or placement logic into directorate adapters.

Public rendering API:

`write_dashboard_charts(workbook, spec, dataset_refs, parameter_system, dashboard_ref) -> ChartSystemRef`

The chart engine runs after the 01E dashboard shell because it consumes the stable anchors reserved by `DashboardRef`.

## Technical calculation layer

Charts do not calculate directly inside the drawing object. 01F writes an auditable helper block to the visible/protected `CALC` technical sheet and points each chart at those cells.

This gives every chart a traceable path:

`MetricSpec -> MetricBinding -> CALC formulas -> chart series`

If `CALC` already exists, 01F appends new blocks and does not overwrite existing technical content.

## Metric semantics

01F reuses the same metric-expression engine introduced for KPI cards in 01E. Charts therefore inherit the same aggregation rules for:

- sum/value;
- count;
- ratio;
- average from sum/count;
- weighted average;
- NPS from promoters/detractors/respondents.

A directorate adapter never writes chart formulas.

## Category dimensions

`ChartSpec.dimension_code` identifies the chart category dimension. The selected parameter for that dimension is intentionally replaced by each category member while all other workbook filters remain active.

Example: an NPS evolution chart by `period` evaluates every authorized period while continuing to respect the selected course.

## Series dimensions

`series_dimension_code` creates one series per member of a second declared dimension. Contract V1 does not combine a series dimension with `comparison` in the same chart.

## Reference/comparison series

`ChartSpec.comparison` can produce a two-series chart when its parameter controls a different dimension from the category dimension. This is intended for comparisons such as reference period vs comparison period by course.

## Supported chart types

Contract V1 supports:

- line;
- vertical column;
- horizontal bar;
- pie;
- doughnut.

Pie and doughnut charts are single-series in Contract V1.

## Semantic axes

Axis limits come from metric semantics, not autoscale defaults:

- NPS: -100 to +100;
- percentage: 0% to 100% (internally 0 to 1);
- score 0-10: 0 to 10;
- counts: minimum 0, automatic maximum;
- explicit `MetricSpec.valid_min` / `valid_max` can refine the contract when appropriate.

## Sorting and top_n

Contract V1 supports stable dimension ordering:

- `dimension_asc` / default declared dimension order;
- `dimension_desc`;
- `label_asc`;
- `label_desc`.

`top_n` truncates that ordered member list. Metric-value ranking is deliberately not implied by `top_n`; a future extension must define that behavior explicitly rather than silently approximating it.

## Compatibility

Helper formulas remain compatible with the Excel Official V1 target (Excel 2019+/Microsoft 365). 01F does not depend on dynamic-array functions or volatile lookup techniques such as `INDIRECT` or `OFFSET`.

## Safety

01F performs preflight before creating `CALC` or chart objects. It rejects, among other cases:

- missing dataset refs;
- metric/dataset binding mismatches;
- unsupported dimensions;
- invalid comparison dimensions;
- series + comparison combinations in V1;
- multi-series pie/doughnut charts;
- unsupported sort semantics.

The `CALC` sheet stays visible and protected in accordance with Contract V1.
