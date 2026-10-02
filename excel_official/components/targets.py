from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from openpyxl.utils import get_column_letter

from ..contract import DatasetRef, ParameterSystemRef, TargetBindingSpec, WorkbookSpec


def _excel_sheet(sheet_name: str) -> str:
    return "'" + sheet_name.replace("'", "''") + "'"


def _excel_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _formula_literal(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        base = f"DATE({value.year},{value.month},{value.day})"
        if value.hour or value.minute or value.second:
            base += f"+TIME({value.hour},{value.minute},{value.second})"
        return base
    if isinstance(value, date):
        return f"DATE({value.year},{value.month},{value.day})"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    return _excel_string(str(value))


def _column_range(dataset_ref: DatasetRef, column_code: str) -> str:
    letter = dataset_ref.column_letter(column_code)
    sheet = _excel_sheet(dataset_ref.sheet_name)
    if dataset_ref.row_count <= 0:
        return f"{sheet}!${letter}$1:${letter}$1"
    return f"{sheet}!${letter}${dataset_ref.first_data_row}:${letter}${dataset_ref.last_data_row}"


def target_binding_by_metric(spec: WorkbookSpec) -> dict[str, TargetBindingSpec]:
    return {item.metric_code: item for item in spec.target_bindings}


def target_expression(
    spec: WorkbookSpec,
    metric_code: str,
    dataset_refs: Mapping[str, DatasetRef],
    parameter_system: ParameterSystemRef,
    *,
    field: str = "target",
    criteria_overrides: Mapping[str, str] | None = None,
) -> str | None:
    """Return an Excel formula for the effective target of a metric.

    Target datasets are expected to be pre-expanded by the domain adapter.  The
    Core only performs exact matching against declared parameter/constant criteria.
    This keeps business inheritance (for example TOTAL -> course -> discipline)
    outside the rendering layer while still allowing the workbook to react offline.
    """
    binding = target_binding_by_metric(spec).get(metric_code)
    if binding is None:
        return None
    dataset_ref = dataset_refs.get(binding.dataset_code)
    if dataset_ref is None or dataset_ref.row_count <= 0:
        return '=""'

    if field == "target":
        value_column = binding.target_column
    elif field == "attention":
        value_column = binding.attention_column
        if not value_column:
            return None
    else:
        raise ValueError(f"Campo de meta nao suportado: {field!r}.")

    overrides = dict(criteria_overrides or {})
    criteria: list[tuple[str, str]] = []
    for column_code, parameter_code in binding.criteria_parameters.items():
        expression = overrides.pop(column_code, None)
        if expression is None:
            parameter_ref = parameter_system.parameters[parameter_code]
            expression = parameter_ref.defined_name
        criteria.append((column_code, expression))
    for column_code, value in binding.criteria_constants.items():
        expression = overrides.pop(column_code, None) or _formula_literal(value)
        criteria.append((column_code, expression))
    for column_code, expression in overrides.items():
        criteria.append((column_code, expression))

    value_range = _column_range(dataset_ref, value_column)
    masks = [f"--({_column_range(dataset_ref, column)}={expression})" for column, expression in criteria]
    masks.append(f"--({value_range}<>\"\")")
    mask_expr = ",".join(masks)
    matches = f"SUMPRODUCT({mask_expr})"
    total = f"SUMPRODUCT({value_range},{mask_expr})"
    scaled = total if binding.value_scale == 1 else f"({total}*{binding.value_scale})"
    return f'=IF({matches}=0,"",{scaled})'


__all__ = ["target_binding_by_metric", "target_expression"]
