# Excel Official V1 - Quality & Governance

## Purpose

Phase 01H materializes the institutional `QUALIDADE E GOVERNANCA` audit surface from `QualitySpec` without introducing directorate-specific rules.

Public rendering API:

`write_quality_sheet(workbook, spec, dataset_refs, parameter_system) -> QualityRef`

The sheet answers the operational question: **can this workbook be trusted for the analysis it is currently showing?**

## Quality model

A `QualityCheckSpec` declares:

- a stable code and human label;
- a supported check type;
- the source code being checked;
- the severity to emit **only when the check fails**;
- success and failure messages.

Severity levels are:

- `INFO`;
- `WARNING`;
- `ERROR`;
- `BLOCKING`.

The configured severity is not itself a failure. A blocking check that passes reports `OK` and does not block the workbook.

## Contract V1 check types

Dataset checks:

- `dataset_non_empty`;
- `dataset_required_fields`.

Metric checks:

- `metric_has_data`;
- `metric_valid_range`.

Coverage checks:

- `dimension_non_empty`.

Snapshot checks:

- `snapshot_field_present`.

Unsupported check types are rejected during `WorkbookSpec` validation and before workbook mutation.

## Dynamic metric checks

Metric checks reuse the same metric-expression engine used by KPI cards, charts and the matrix. They therefore follow the same `MetricSpec`, `MetricBinding`, current parameters and aggregation semantics.

Examples:

- NPS is recomposed from promoters/detractors/respondents;
- ratios are recomposed from numerator/denominator;
- averages use sum/count rather than averages of averages.

Metric quality checks react to the current workbook parameters after download. Dataset, dimension and snapshot checks describe the exported snapshot itself and are evaluated during generation.

## Institutional sections

The sheet contains:

1. overall status;
2. quality checks;
3. coverage;
4. sources and bases;
5. snapshot metadata;
6. known limitations.

### Coverage

Coverage shows the snapshot minimum/maximum period, interactive-dimension count and the available member count for each declared dimension.

### Sources and bases

Every dataset is listed with:

- source/provenance;
- exported record count;
- sensitivity classification;
- authorization scope;
- grain;
- stable dataset code.

### Snapshot

The audit surface exposes, when available:

- export ID;
- generation timestamp and exporter;
- system/version;
- schema version;
- Excel Official Contract version;
- adapter/version;
- directorate;
- authorization scope;
- payload hash.

### Limitations

A `LimitationSpec` is a known limitation that actually exists in the exported workbook. Its severity therefore contributes directly to the overall status, unlike a quality-check severity which contributes only when the check fails.

## Overall status

The overall status evaluates failed checks plus declared limitations using the following precedence:

1. `BLOCKING` -> `NAO UTILIZAR`;
2. `ERROR` -> `REVISAR`;
3. `WARNING` -> `APTO COM ALERTAS`;
4. `INFO` -> `APTO COM OBSERVACOES`;
5. otherwise -> `APTO`.

If neither checks nor limitations are declared, the workbook explicitly reports `SEM CHECKS DECLARADOS` instead of presenting a false green status.

## Protection and compatibility

`QUALIDADE E GOVERNANCA` is visible and fully protected. It is an audit surface, not a data-entry surface.

Contract V1 formulas remain compatible with Excel 2019+/Microsoft 365 and do not require `FILTER`, `XLOOKUP`, `SORT`, `UNIQUE`, `INDIRECT` or `OFFSET`.
