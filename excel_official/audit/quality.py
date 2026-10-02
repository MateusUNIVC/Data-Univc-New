from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..contract import MetricAggregation, QualityCheckSpec, QualitySeverity, WorkbookSpec
from .models import AuditFinding


def _initial_value(spec: WorkbookSpec, parameter_code: str) -> Any:
    if parameter_code in spec.initial_state.values:
        return spec.initial_state.values[parameter_code]
    parameter = next((item for item in spec.parameters if item.code == parameter_code), None)
    if parameter is None:
        return None
    if parameter.initial_value is not None:
        return parameter.initial_value
    return spec.snapshot.initial_scope.get(parameter_code)


def _rows_for_metric(spec: WorkbookSpec, metric_code: str) -> list[dict[str, Any]]:
    binding = next(item for item in spec.metric_bindings if item.metric_code == metric_code)
    dataset = next(item for item in spec.datasets if item.code == binding.dataset_code)
    output: list[dict[str, Any]] = []
    parameters = {item.code: item for item in spec.parameters}
    for raw in dataset.rows:
        row = dict(raw)
        keep = True
        for dimension_code, parameter_code in binding.filter_parameters.items():
            parameter = parameters[parameter_code]
            selected = _initial_value(spec, parameter_code)
            all_value = parameter.empty_option
            if all_value is None and not parameter.required:
                all_value = ""
            if selected is None or selected == all_value:
                continue
            column_code = dataset.dimension_columns.get(dimension_code, dimension_code)
            if row.get(column_code) != selected:
                keep = False
                break
        if keep:
            output.append(row)
    return output


def _numeric_sum(rows: list[dict[str, Any]], column: str) -> float:
    total = Decimal("0")
    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        total += Decimal(str(value))
    return float(total)


def evaluate_metric(spec: WorkbookSpec, metric_code: str) -> float | int | None:
    metric = next(item for item in spec.metrics if item.code == metric_code)
    binding = next(item for item in spec.metric_bindings if item.metric_code == metric_code)
    rows = _rows_for_metric(spec, metric_code)
    if not rows:
        return None

    if metric.aggregation in {MetricAggregation.VALUE, MetricAggregation.SUM}:
        if not binding.value_column:
            return None
        return _numeric_sum(rows, binding.value_column)
    if metric.aggregation is MetricAggregation.COUNT:
        return len(rows)

    def component(name: str) -> float:
        return _numeric_sum(rows, binding.components[name])

    try:
        if any(component(name) > 0 for name in metric.invalid_when_positive_components):
            return None
        if metric.aggregation is MetricAggregation.RATIO:
            denominator = component("denominator")
            return None if denominator == 0 else component("numerator") / denominator
        if metric.aggregation is MetricAggregation.AVERAGE:
            count = component("count")
            return None if count == 0 else component("sum") / count
        if metric.aggregation is MetricAggregation.WEIGHTED_AVERAGE:
            weight = component("weight")
            return None if weight == 0 else component("weighted_sum") / weight
        if metric.aggregation is MetricAggregation.NPS:
            respondents = component("respondents")
            if respondents == 0:
                return None
            return ((component("promoters") / respondents) - (component("detractors") / respondents)) * 100
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    return None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (tuple, list, set, dict)):
        return bool(value)
    return True


def _snapshot_value(spec: WorkbookSpec, field_name: str) -> Any:
    if hasattr(spec.snapshot, field_name):
        return getattr(spec.snapshot, field_name)
    if hasattr(spec.identity, field_name):
        return getattr(spec.identity, field_name)
    return None


def _required_missing_count(spec: WorkbookSpec, dataset_code: str) -> int:
    dataset = next(item for item in spec.datasets if item.code == dataset_code)
    required = tuple(column.code for column in dataset.columns if not column.nullable)
    missing = 0
    for row in dataset.rows:
        for code in required:
            value = row.get(code)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing += 1
    return missing


def _dimension_member_count(spec: WorkbookSpec, dimension_code: str) -> int:
    dimension = next(item for item in spec.dimensions if item.code == dimension_code)
    dataset = next(item for item in spec.datasets if item.code == dimension.dataset_code)
    seen: set[tuple[object, object]] = set()
    parent_column = dimension.parent_key_column or dimension.parent_dimension
    for row in dataset.rows:
        key = row.get(dimension.key_column)
        label = row.get(dimension.label_column)
        if key is None or label is None:
            continue
        parent = row.get(parent_column) if parent_column else None
        seen.add((parent, key))
    return len(seen)


def evaluate_quality_check(spec: WorkbookSpec, check: QualityCheckSpec) -> bool:
    if check.check_type == "dataset_non_empty":
        dataset = next(item for item in spec.datasets if item.code == check.source_code)
        return bool(dataset.rows)
    if check.check_type == "dataset_required_fields":
        return _required_missing_count(spec, check.source_code) == 0
    if check.check_type == "dimension_non_empty":
        return _dimension_member_count(spec, check.source_code) > 0
    if check.check_type == "snapshot_field_present":
        return _present(_snapshot_value(spec, check.source_code))
    if check.check_type == "metric_has_data":
        return evaluate_metric(spec, check.source_code) is not None
    if check.check_type == "metric_valid_range":
        metric = next(item for item in spec.metrics if item.code == check.source_code)
        value = evaluate_metric(spec, check.source_code)
        if value is None:
            return False
        if metric.valid_min is not None and value < metric.valid_min:
            return False
        if metric.valid_max is not None and value > metric.valid_max:
            return False
        return True
    return False


def blocking_quality_findings(spec: WorkbookSpec) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    for check in spec.quality.checks:
        if check.severity is not QualitySeverity.BLOCKING:
            continue
        if not evaluate_quality_check(spec, check):
            findings.append(
                AuditFinding(
                    code=f"quality.{check.code}",
                    severity=QualitySeverity.BLOCKING,
                    message=check.message_error,
                    sheet_name="QUALIDADE E GOVERNANCA",
                )
            )
    return tuple(findings)
