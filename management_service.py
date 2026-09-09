from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from management_catalog import (
    ManagementCatalogError,
    default_comparison,
    dimension_keys,
    directorate_spec,
    field_keys,
    indicator_spec,
    indicator_specs,
    metric_spec,
    period_sort_key,
    validate_period,
)


class ManagementValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


DIMENSION_LABELS = {
    "channel": "Canal",
    "request_type": "Tipo de solicitação",
    "week": "Semana",
    "resolution_band": "Faixa de resolução",
    "course": "Curso",
    "academic_directorate": "Diretoria acadêmica",
    "modality": "Modalidade",
    "shift": "Turno",
    "cost_center": "Centro de custo",
    "expense_nature": "Natureza de despesa",
    "category": "Categoria",
    "nature": "Natureza",
    "cohort": "Coorte",
    "research_line": "Linha de pesquisa",
    "exit_reason": "Motivo de saída",
    "advisor": "Orientador",
}


def _as_decimal(value: Any, *, field: str) -> Decimal:
    if value is None or value == "":
        raise ManagementValidationError("Valor obrigatório ausente.", {field: "Informe um valor."})
    if isinstance(value, bool):
        raise ManagementValidationError("Valor numérico inválido.", {field: "Use um número."})
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if text.count(",") == 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(",") == 1:
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ManagementValidationError("Valor numérico inválido.", {field: "Use um número válido."}) from exc
    if not number.is_finite():
        raise ManagementValidationError("Valor numérico inválido.", {field: "Use um número finito."})
    return number


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _safe_ratio(numerator: Any, denominator: Any, scale: float = 1.0) -> float | None:
    num = _number(numerator)
    den = _number(denominator)
    if num is None or den in (None, 0):
        return None
    return num / den * scale


def canonical_dimensions(spec: dict[str, Any], dimensions: dict[str, Any] | None) -> tuple[dict[str, str], str, str]:
    dimensions = dimensions or {}
    if not isinstance(dimensions, dict):
        raise ManagementValidationError("Dimensões inválidas.", {"dimensions": "Use um objeto chave/valor."})
    allowed = dimension_keys(spec)
    unknown = sorted(set(dimensions) - allowed)
    if unknown:
        raise ManagementValidationError(
            "Existem dimensões que não pertencem ao indicador.",
            {"dimensions": "Não permitidas: " + ", ".join(unknown)},
        )
    cleaned: dict[str, str] = {}
    for key in spec.get("dimensions") or []:
        value = str(dimensions.get(key) or "").strip()
        if value:
            if len(value) > 180:
                raise ManagementValidationError(
                    "Dimensão muito longa.", {f"dimensions.{key}": "Use no máximo 180 caracteres."}
                )
            cleaned[key] = value
    if not cleaned:
        return {}, "TOTAL", "TOTAL"
    raw = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
    label = " | ".join(f"{DIMENSION_LABELS.get(k, k)}: {v}" for k, v in cleaned.items())
    return cleaned, key, label


def validate_measurement_payload(directorate_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    indicator_code = str(payload.get("indicator_code") or "").strip().upper()
    try:
        spec = indicator_spec(directorate_code, indicator_code)
        period = validate_period(directorate_code, payload.get("period"))
    except ManagementCatalogError as exc:
        raise ManagementValidationError(str(exc)) from exc

    dimensions, dimension_key, dimension_label = canonical_dimensions(spec, payload.get("dimensions"))
    if directorate_code == "DADM" and indicator_code in {"DADM-01", "DADM-02"} and not dimensions.get("channel"):
        raise ManagementValidationError(
            "Informe o canal do atendimento.",
            {"dimensions.channel": "O canal é obrigatório para lançamentos da DADM."},
        )
    values = payload.get("values") or {}
    if not isinstance(values, dict):
        raise ManagementValidationError("Componentes inválidos.", {"values": "Use um objeto chave/valor."})
    allowed_fields = field_keys(spec)
    unknown = sorted(set(values) - allowed_fields)
    if unknown:
        raise ManagementValidationError(
            "Existem componentes que não pertencem ao indicador.",
            {"values": "Não permitidos: " + ", ".join(unknown)},
        )

    cleaned_values: dict[str, int | float | None] = {}
    errors: dict[str, str] = {}
    for field in spec.get("fields") or []:
        key = field["key"]
        raw = values.get(key)
        if (raw is None or raw == "") and not field.get("required"):
            cleaned_values[key] = None
            continue
        if raw is None or raw == "":
            errors[f"values.{key}"] = "Campo obrigatório."
            continue
        try:
            number = _as_decimal(raw, field=f"values.{key}")
            if number < 0:
                errors[f"values.{key}"] = "Use zero ou um valor positivo."
                continue
            if field.get("type") == "integer":
                if number != number.to_integral_value():
                    errors[f"values.{key}"] = "Use um número inteiro."
                    continue
                cleaned_values[key] = int(number)
            else:
                cleaned_values[key] = float(number)
        except ManagementValidationError as exc:
            errors.update(exc.field_errors)
    if errors:
        raise ManagementValidationError("Revise os componentes informados.", errors)

    _validate_component_consistency(indicator_code, cleaned_values)
    notes = str(payload.get("notes") or "").strip() or None
    source_reference = str(payload.get("source_reference") or "").strip() or None
    return {
        "indicator_code": indicator_code,
        "period": period,
        "dimensions": dimensions,
        "dimension_key": dimension_key,
        "dimension_label": dimension_label,
        "values": cleaned_values,
        "notes": notes,
        "source_reference": source_reference,
        "validated": bool(payload.get("validated", False)),
    }


def _validate_component_consistency(indicator_code: str, values: dict[str, Any]) -> None:
    errors: dict[str, str] = {}
    if indicator_code == "DADM-01":
        if (values.get("requests_within_sla") or 0) > (values.get("requests_received") or 0):
            errors["values.requests_within_sla"] = "Não pode superar as solicitações recebidas."
        if (values.get("reopened") or 0) > (values.get("concluded") or 0):
            errors["values.reopened"] = "Não pode superar as solicitações concluídas."
    elif indicator_code == "DADM-02":
        respondents = values.get("respondents") or 0
        if respondents > (values.get("eligible_interactions") or 0):
            errors["values.respondents"] = "Não pode superar os atendimentos elegíveis."
        if (values.get("satisfied") or 0) + (values.get("dissatisfied") or 0) > respondents:
            errors["values.satisfied"] = "Satisfeitos e insatisfeitos não podem superar os respondentes."
    elif indicator_code == "DPE-01":
        if (values.get("net_revenue") or 0) <= 0:
            errors["values.net_revenue"] = "A receita líquida precisa ser maior que zero."
        if (values.get("weekly_teaching_hours") or 0) <= 0:
            errors["values.weekly_teaching_hours"] = "As horas-aula semanais precisam ser maiores que zero."
        if (values.get("teacher_count") or 0) <= 0:
            errors["values.teacher_count"] = "O número de docentes precisa ser maior que zero."
    elif indicator_code == "DPE-02":
        if (values.get("net_revenue") or 0) <= 0:
            errors["values.net_revenue"] = "A receita líquida precisa ser maior que zero."
        total_expense = sum(float(values.get(key) or 0) for key in (
            "personnel_expense", "operational_expense", "administrative_expense", "financial_expense"
        ))
        if total_expense <= 0:
            errors["values.personnel_expense"] = "A despesa total precisa ser maior que zero."
    elif indicator_code == "DPE-03":
        if (values.get("net_revenue") or 0) <= 0:
            errors["values.net_revenue"] = "A receita líquida precisa ser maior que zero."
        breakdown_keys = ("gross_salaries", "charges", "provisions")
        informed = [values.get(key) is not None for key in breakdown_keys]
        if any(informed) and not all(informed):
            errors["values.gross_salaries"] = (
                "Preencha salários brutos, encargos e provisões em conjunto, ou deixe os três campos vazios."
            )
        elif all(informed):
            payroll_by_category = float(values.get("faculty_payroll") or 0) + float(values.get("administrative_payroll") or 0)
            payroll_by_nature = sum(float(values.get(key) or 0) for key in breakdown_keys)
            tolerance = max(1.0, abs(payroll_by_category) * 0.005)
            if abs(payroll_by_category - payroll_by_nature) > tolerance:
                errors["values.gross_salaries"] = (
                    "Salários, encargos e provisões devem totalizar a mesma folha informada nas categorias docente e administrativa."
                )
    elif indicator_code == "DM-02":
        if (values.get("graduated_within_24") or 0) > (values.get("cohort_entrants") or 0):
            errors["values.graduated_within_24"] = "Não pode superar os ingressantes da coorte."
    if errors:
        raise ManagementValidationError("Os componentes são internamente inconsistentes.", errors)


def raw_components(row: dict[str, Any]) -> dict[str, Any]:
    values = row.get("values")
    if isinstance(values, dict):
        return values
    raw = row.get("values_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def row_dimensions(row: dict[str, Any]) -> dict[str, str]:
    value = row.get("dimensions")
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if str(v).strip()}
    raw = row.get("dimensions_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}


def calculate_metric_from_components(metric: dict[str, Any], components: dict[str, Any]) -> float | None:
    aggregation = metric.get("aggregation")
    if aggregation == "ratio":
        return _safe_ratio(
            components.get(metric.get("numerator")),
            components.get(metric.get("denominator")),
            float(metric.get("scale", 1)),
        )
    if aggregation == "sum":
        return _number(components.get(metric.get("field")))
    if aggregation == "weighted_average":
        return _number(components.get(metric.get("field")))
    if aggregation == "derived_total_cost":
        return sum(_number(components.get(key)) or 0 for key in (
            "faculty_cost", "coordination_cost", "other_direct_cost", "indirect_cost"
        ))
    if aggregation == "derived_margin":
        revenue = _number(components.get("net_revenue"))
        cost = calculate_metric_from_components({"aggregation": "derived_total_cost"}, components)
        return _safe_ratio((revenue or 0) - (cost or 0), revenue, 100)
    if aggregation == "derived_total_expense":
        return sum(_number(components.get(key)) or 0 for key in (
            "personnel_expense", "operational_expense", "administrative_expense", "financial_expense"
        ))
    if aggregation == "derived_coverage":
        revenue = _number(components.get("net_revenue"))
        expense = calculate_metric_from_components({"aggregation": "derived_total_expense"}, components)
        return _safe_ratio(revenue, expense, 1)
    if aggregation == "derived_operating_margin":
        coverage = calculate_metric_from_components({"aggregation": "derived_coverage"}, components)
        if coverage in (None, 0):
            return None
        return (1 - 1 / coverage) * 100
    if aggregation == "derived_payroll_ratio":
        payroll = (_number(components.get("faculty_payroll")) or 0) + (
            _number(components.get("administrative_payroll")) or 0
        )
        return _safe_ratio(payroll, components.get("net_revenue"), 100)
    if aggregation == "derived_active_end":
        return (
            (_number(components.get("active_start")) or 0)
            + (_number(components.get("entrants")) or 0)
            - (_number(components.get("graduates")) or 0)
            - (_number(components.get("dropped")) or 0)
        )
    if aggregation == "derived_net_change":
        active_start = _number(components.get("active_start"))
        active_end = calculate_metric_from_components({"aggregation": "derived_active_end"}, components)
        return _safe_ratio((active_end or 0) - (active_start or 0), active_start, 100)
    if aggregation in {
        "rolling_payroll_ratio_3m",
        "month_over_month_payroll_change",
        "rolling_margin_12m",
        "rolling_coverage_12m",
        "rolling_operating_margin_12m",
    }:
        return None
    raise ManagementCatalogError(f"Agregação desconhecida: {aggregation!r}.")


def aggregate_components(spec: dict[str, Any], rows: Iterable[dict[str, Any]]) -> dict[str, float | int | None]:
    rows = list(rows)
    aggregate: dict[str, float | int | None] = {}
    for field in spec.get("fields") or []:
        key = field["key"]
        values = [_number(raw_components(row).get(key)) for row in rows]
        usable = [value for value in values if value is not None]
        aggregate[key] = sum(usable) if usable else None

    # Average/median fields are already aggregated upstream. They must be combined
    # using the relevant evidence count instead of being summed.
    for metric in spec.get("metrics") or []:
        if metric.get("aggregation") != "weighted_average":
            continue
        field = metric.get("field")
        weight = metric.get("weight")
        numerator = 0.0
        denominator = 0.0
        for row in rows:
            components = raw_components(row)
            value = _number(components.get(field))
            row_weight = _number(components.get(weight)) if weight else 1.0
            if value is None or row_weight is None or row_weight <= 0:
                continue
            numerator += value * row_weight
            denominator += row_weight
        aggregate[field] = numerator / denominator if denominator else None
    return aggregate


def calculate_indicator_metrics(spec: dict[str, Any], rows: Iterable[dict[str, Any]]) -> dict[str, float | None]:
    rows = list(rows)
    components = aggregate_components(spec, rows)
    return {
        metric["key"]: calculate_metric_from_components(metric, components)
        for metric in spec.get("metrics") or []
    }


def enrich_rolling_metrics(
    directorate_code: str,
    indicator: dict[str, Any],
    period_rows: list[dict[str, Any]],
) -> None:
    """Enriquece indicadores móveis usando os componentes consolidados.

    A janela é sempre baseada nos períodos cronológicos disponíveis, sem somar
    percentuais. Margens e índices são recalculados a partir dos numeradores e
    denominadores acumulados, preservando a equivalência matemática entre site
    e Excel.
    """
    code = indicator.get("code")
    if code not in {"DPE-01", "DPE-02", "DPE-03"}:
        return
    ordered = sorted(period_rows, key=lambda item: period_sort_key(item["period"]))
    for index, item in enumerate(ordered):
        current_components = item.get("components") or {}

        if code == "DPE-01":
            window = ordered[max(0, index - 11): index + 1]
            revenue = sum(_number((row.get("components") or {}).get("net_revenue")) or 0 for row in window)
            cost = 0.0
            for row in window:
                components = row.get("components") or {}
                cost += sum(_number(components.get(key)) or 0 for key in (
                    "faculty_cost", "coordination_cost", "other_direct_cost", "indirect_cost"
                ))
            item["metrics"]["net_margin_12m_pct"] = _safe_ratio(revenue - cost, revenue, 100)
            continue

        if code == "DPE-02":
            window = ordered[max(0, index - 11): index + 1]
            revenue = sum(_number((row.get("components") or {}).get("net_revenue")) or 0 for row in window)
            expense = 0.0
            for row in window:
                components = row.get("components") or {}
                expense += sum(_number(components.get(key)) or 0 for key in (
                    "personnel_expense", "operational_expense", "administrative_expense", "financial_expense"
                ))
            coverage = _safe_ratio(revenue, expense, 1)
            item["metrics"]["coverage_index_12m"] = coverage
            item["metrics"]["operating_margin_12m_pct"] = (
                None if coverage in (None, 0) else (1 - 1 / coverage) * 100
            )
            continue

        payroll = (_number(current_components.get("faculty_payroll")) or 0) + (
            _number(current_components.get("administrative_payroll")) or 0
        )
        window = ordered[max(0, index - 2): index + 1]
        revenues = [
            _number((row.get("components") or {}).get("net_revenue"))
            for row in window
        ]
        revenues = [value for value in revenues if value is not None]
        average_revenue = sum(revenues) / len(revenues) if revenues else None
        item["metrics"]["payroll_on_revenue_3m_pct"] = _safe_ratio(payroll, average_revenue, 100)
        if index == 0:
            item["metrics"]["payroll_monthly_change_pct"] = None
        else:
            previous_components = ordered[index - 1].get("components") or {}
            previous_payroll = (_number(previous_components.get("faculty_payroll")) or 0) + (
                _number(previous_components.get("administrative_payroll")) or 0
            )
            item["metrics"]["payroll_monthly_change_pct"] = _safe_ratio(
                payroll - previous_payroll, previous_payroll, 100
            )


def status_for_metric(value: float | None, metric: dict[str, Any], target: dict[str, Any] | None = None) -> str:
    if value is None:
        return "Não apurado"
    target = target or {}
    direction = metric.get("direction")
    if direction in {"context", None}:
        return "Informativo"
    if direction == "higher":
        goal = _number(target.get("target"))
        attention = _number(target.get("attention"))
        if goal is None:
            goal = _number(metric.get("target"))
        if attention is None:
            attention = _number(metric.get("attention"))
        if goal is None:
            return "Sem meta"
        if value >= goal:
            return "Dentro da meta"
        if attention is not None and value >= attention:
            return "Atenção"
        return "Fora da meta"
    if direction == "lower":
        goal = _number(target.get("target"))
        attention = _number(target.get("attention"))
        if goal is None:
            goal = _number(metric.get("target"))
        if attention is None:
            attention = _number(metric.get("attention"))
        if goal is None:
            return "Sem meta"
        if value <= goal:
            return "Dentro da meta"
        if attention is not None and value <= attention:
            return "Atenção"
        return "Fora da meta"
    if direction == "range":
        minimum = _number(target.get("target_min"))
        maximum = _number(target.get("target_max"))
        if minimum is None:
            minimum = _number(metric.get("target_min"))
        if maximum is None:
            maximum = _number(metric.get("target_max"))
        attention_min = _number(target.get("attention_min"))
        attention_max = _number(target.get("attention_max"))
        if attention_min is None:
            attention_min = _number(metric.get("attention_min"))
        if attention_max is None:
            attention_max = _number(metric.get("attention_max"))
        if minimum is None or maximum is None:
            return "Sem meta"
        if minimum <= value <= maximum:
            return "Dentro da meta"
        if attention_min is not None and attention_max is not None and attention_min <= value <= attention_max:
            return "Atenção"
        return "Fora da meta"
    return "Sem meta"


def _target_for(
    metric: dict[str, Any],
    targets: Iterable[dict[str, Any]],
    period: str,
    dimension_key: str = "TOTAL",
) -> dict[str, Any]:
    period_key = period_sort_key(period)
    candidates = []
    for target in targets:
        if target.get("metric_key") != metric.get("key"):
            continue
        if target.get("dimension_key", "TOTAL") not in {dimension_key, "TOTAL"}:
            continue
        start = period_sort_key(target.get("valid_from"))
        end = period_sort_key(target.get("valid_to")) if target.get("valid_to") else 10**12
        if start <= period_key <= end:
            specificity = 1 if target.get("dimension_key", "TOTAL") == dimension_key else 0
            candidates.append((specificity, start, target))
    if candidates:
        return dict(max(candidates, key=lambda item: (item[0], item[1]))[2])
    return {
        "target": metric.get("target"),
        "attention": metric.get("attention"),
        "target_min": metric.get("target_min"),
        "target_max": metric.get("target_max"),
        "attention_min": metric.get("attention_min"),
        "attention_max": metric.get("attention_max"),
        "source": "catalog",
    }


def target_label(metric: dict[str, Any], target: dict[str, Any]) -> str:
    direction = metric.get("direction")
    if direction == "higher" and _number(target.get("target")) is not None:
        return f"≥ {_number(target.get('target')):g}"
    if direction == "lower" and _number(target.get("target")) is not None:
        return f"≤ {_number(target.get('target')):g}"
    if direction == "range":
        low = _number(target.get("target_min"))
        high = _number(target.get("target_max"))
        if low is not None and high is not None:
            return f"{low:g} a {high:g}"
    return "—"


def _matches_dimensions(row: dict[str, Any], filters: dict[str, str] | None) -> bool:
    if not filters:
        return True
    dims = row_dimensions(row)
    return all(str(dims.get(key, "")).casefold() == str(value).strip().casefold() for key, value in filters.items() if str(value).strip())


def build_management_dashboard(
    directorate_code: str,
    measurements: Iterable[dict[str, Any]],
    targets: Iterable[dict[str, Any]] = (),
    actions: Iterable[dict[str, Any]] = (),
    *,
    reference: str | None = None,
    comparison: str | None = None,
    indicator_code: str | None = None,
    dimension_filters: dict[str, str] | None = None,
    window: int | None = None,
) -> dict[str, Any]:
    directorate_code = str(directorate_code).strip().upper()
    directory = directorate_spec(directorate_code)
    rows = [dict(row) for row in measurements if row.get("indicator_code")]
    rows = [row for row in rows if _matches_dimensions(row, dimension_filters)]
    periods = sorted({str(row.get("period")) for row in rows if period_sort_key(row.get("period")) >= 0}, key=period_sort_key)
    if reference:
        reference = validate_period(directorate_code, reference)
    elif periods:
        reference = periods[-1]
    else:
        reference = None
    if comparison:
        comparison = validate_period(directorate_code, comparison)
    elif reference:
        comparison = default_comparison(directorate_code, reference)
    else:
        comparison = None

    specs = indicator_specs(directorate_code)
    if indicator_code:
        selected = indicator_spec(directorate_code, indicator_code)
    else:
        selected = specs[0]
    target_rows = [dict(item) for item in targets]

    by_indicator_period: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_indicator_period[(row["indicator_code"], row["period"])].append(row)

    all_period_results: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        series = []
        for period in periods:
            period_measurements = by_indicator_period.get((spec["code"], period), [])
            if not period_measurements:
                continue
            components = aggregate_components(spec, period_measurements)
            metrics = {
                metric["key"]: calculate_metric_from_components(metric, components)
                for metric in spec.get("metrics") or []
            }
            series.append({
                "period": period,
                "components": components,
                "metrics": metrics,
                "records": len(period_measurements),
                "validated_records": sum(1 for row in period_measurements if row.get("validated")),
            })
        enrich_rolling_metrics(directorate_code, spec, series)
        all_period_results[spec["code"]] = series

    cards = []
    for spec in specs:
        metric = metric_spec(directorate_code, spec["code"], spec["primary_metric"])
        by_period = {item["period"]: item for item in all_period_results[spec["code"]]}
        current = by_period.get(reference or "")
        compared = by_period.get(comparison or "")
        value = current["metrics"].get(metric["key"]) if current else None
        comparison_value = compared["metrics"].get(metric["key"]) if compared else None
        target = _target_for(metric, target_rows, reference or "", "TOTAL") if reference else {}
        change = None if value is None or comparison_value is None else value - comparison_value
        status = status_for_metric(value, metric, target)
        notes = []
        if spec["code"] == "DADM-01" and reference:
            ordered_service = sorted(
                [item for item in all_period_results.get("DADM-01", []) if period_sort_key(item["period"]) <= period_sort_key(reference)],
                key=lambda item: period_sort_key(item["period"]),
            )
            if len(ordered_service) >= 3:
                balances = [item.get("metrics", {}).get("open_balance") for item in ordered_service[-3:]]
                if all(value is not None for value in balances) and balances[0] < balances[1] < balances[2]:
                    notes.append("Alerta: o saldo em aberto cresceu por dois fechamentos consecutivos.")
        if spec["code"] == "DADM-02" and current:
            response_rate = current["metrics"].get("response_rate_pct")
            if response_rate is not None and response_rate < 25:
                notes.append("Amostra indicativa: taxa de resposta abaixo de 25%.")
        if spec["code"] == "DPE-02" and reference:
            ordered_coverage = sorted(
                [item for item in all_period_results.get("DPE-02", []) if period_sort_key(item["period"]) <= period_sort_key(reference)],
                key=lambda item: period_sort_key(item["period"]),
            )
            consecutive = 0
            for item in reversed(ordered_coverage):
                coverage = item.get("metrics", {}).get("coverage_index")
                if coverage is not None and coverage < 1.0:
                    consecutive += 1
                else:
                    break
            if consecutive > 2:
                notes.append(f"Alerta: {consecutive} meses consecutivos com cobertura abaixo de 1,00.")
        cards.append({
            "indicator_code": spec["code"],
            "indicator_name": spec["name"],
            "short_name": spec["short_name"],
            "metric_key": metric["key"],
            "unit": metric.get("unit"),
            "value": value,
            "comparison_value": comparison_value,
            "change": change,
            "target": target,
            "target_label": target_label(metric, target),
            "status": status,
            "records": current["records"] if current else 0,
            "validated_records": current["validated_records"] if current else 0,
            "notes": notes,
        })

    selected_series = deepcopy(all_period_results.get(selected["code"], []))
    if window and window > 0:
        selected_series = selected_series[-window:]
    selected_metrics = []
    current_lookup = {item["period"]: item for item in all_period_results.get(selected["code"], [])}
    current = current_lookup.get(reference or "")
    compared = current_lookup.get(comparison or "")
    for metric in selected.get("metrics") or []:
        target = _target_for(metric, target_rows, reference or "", "TOTAL") if reference else {}
        value = current["metrics"].get(metric["key"]) if current else None
        comparison_value = compared["metrics"].get(metric["key"]) if compared else None
        selected_metrics.append({
            **metric,
            "value": value,
            "comparison_value": comparison_value,
            "change": None if value is None or comparison_value is None else value - comparison_value,
            "target": target,
            "target_label": target_label(metric, target),
            "status": status_for_metric(value, metric, target),
        })

    dimension_items = []
    if reference:
        reference_rows = by_indicator_period.get((selected["code"], reference), [])
        for row in sorted(reference_rows, key=lambda item: str(item.get("dimension_label", "TOTAL"))):
            components = raw_components(row)
            metrics = {
                metric["key"]: calculate_metric_from_components(metric, components)
                for metric in selected.get("metrics") or []
            }
            primary = metric_spec(directorate_code, selected["code"], selected["primary_metric"])
            target_metric = primary
            dimensions = row_dimensions(row)
            # O documento da DPE define 15% para o consolidado e 10% por curso.
            # Na ausência de uma meta específica cadastrada para o curso, o
            # fallback institucional correto para a dimensão curso é 10%.
            dimension_key = row.get("dimension_key", "TOTAL")
            target_candidates = target_rows
            if selected["code"] == "DPE-01" and dimensions.get("course"):
                target_metric = {**primary, "target": 10, "attention": 0}
                # A meta institucional de 15% não deve substituir silenciosamente
                # a regra específica do documento para cursos (10%). Uma meta
                # cadastrada para a dimensão exata continua tendo prioridade.
                target_candidates = [
                    item for item in target_rows
                    if item.get("dimension_key", "TOTAL") == dimension_key
                ]
            target = _target_for(target_metric, target_candidates, reference, dimension_key)
            value = metrics.get(primary["key"])
            dimension_items.append({
                "dimension_key": dimension_key,
                "dimension_label": row.get("dimension_label", "TOTAL"),
                "dimensions": dimensions,
                "components": components,
                "metrics": metrics,
                "primary_value": value,
                "target": target,
                "target_label": target_label(target_metric, target),
                "status": status_for_metric(value, primary, target),
                "validated": bool(row.get("validated")),
            })

    open_actions = [
        item for item in actions
        if item.get("status") not in {"Concluído", "Concluido", "Cancelado"}
    ]
    return {
        "directorate": {
            "code": directorate_code,
            "name": directory["name"],
            "periodicity": directory["periodicity"],
            "period_label": directory.get("period_label"),
        },
        "reference": reference,
        "comparison": comparison,
        "periods": periods,
        "cards": cards,
        "selected_indicator": selected,
        "selected_metrics": selected_metrics,
        "series": selected_series,
        "dimension_items": dimension_items,
        "quality": {
            "measurements": len(rows),
            "validated_measurements": sum(1 for row in rows if row.get("validated")),
            "periods": len(periods),
            "open_actions": len(open_actions),
            "coverage_pct": (
                sum(1 for card in cards if card["value"] is not None) / len(cards) * 100
                if cards else 0
            ),
        },
    }
