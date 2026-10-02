from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from ..context import AdapterInput
from ..contract import (
    ActionPlanRowSource,
    ActionPlanRowSpec,
    ActionPlanSpec,
    AdapterCapabilities,
    ChartRole,
    ChartSpec,
    ChartType,
    ColumnDataType,
    ColumnSpec,
    DashboardSpec,
    DatasetSpec,
    DimensionSpec,
    DomainSheetSpec,
    IdentitySpec,
    InitialStateSpec,
    KpiSpec,
    LimitationSpec,
    MatrixSpec,
    MetricAggregation,
    MetricBinding,
    MetricSpec,
    MetricUnit,
    ParameterSpec,
    QualityCheckSpec,
    QualitySeverity,
    QualitySpec,
    SheetRole,
    SnapshotSpec,
    TargetBindingSpec,
    TechnicalSpec,
    WorkbookSpec,
)
from .base import DirectorateAdapter


DPE_METRICS = {
    "total_revenue": "dpe.total_revenue",
    "total_expense": "dpe.total_expense",
    "institutional_result": "dpe.institutional_result",
    "institutional_margin": "dpe.institutional_margin",
    "institutional_revenue": "dpe.institutional_revenue",
    "institutional_expense": "dpe.institutional_expense",
    "allocatable_expense": "dpe.allocatable_expense",
    "coverage_index": "dpe.coverage_index",
    "active_students": "dpe.active_students",
    "course_revenue": "dpe.course_revenue",
    "course_cost": "dpe.course_cost",
    "course_result": "dpe.course_result",
    "course_margin": "dpe.course_margin",
    "revenue_per_student": "dpe.revenue_per_student",
    "cost_per_student": "dpe.cost_per_student",
    "selected_expense": "dpe.selected_expense",
    "allocated_cost": "dpe.allocated_cost",
    "allocation_coverage": "dpe.allocation_coverage",
    "teaching_cost": "dpe.teaching_cost",
    "total_workload_hours": "dpe.total_workload_hours",
    "avg_workload_hours_per_teacher": "dpe.avg_workload_hours_per_teacher",
    "teacher_count": "dpe.teacher_count",
    "allocated_expense": "dpe.allocated_expense",
    "unallocated_expense": "dpe.unallocated_expense",
    "reconciliation_pct": "dpe.reconciliation_pct",
    "closure_blockers": "dpe.closure_blockers",
    "payroll_pending": "dpe.payroll_pending",
    "target_collisions": "dpe.target_collisions",
    "component_amount": "dpe.course_component_amount",
    "trend_revenue": "dpe.trend.total_revenue",
    "trend_expense": "dpe.trend.total_expense",
    "trend_result": "dpe.trend.institutional_result",
}

DPE_COMPARISON_METRICS = {
    "total_revenue": "dpe.previous.total_revenue",
    "total_expense": "dpe.previous.total_expense",
    "institutional_result": "dpe.previous.institutional_result",
    "institutional_margin": "dpe.previous.institutional_margin",
}


DPE_TARGET_METRIC_MAP = {
    ("DPE-RESULT", "institutional_result"): DPE_METRICS["institutional_result"],
    ("DPE-RESULT", "institutional_margin_pct"): DPE_METRICS["institutional_margin"],
    ("DPE-RESULT", "coverage_index"): DPE_METRICS["coverage_index"],
    ("DPE-RESULT", "course_result"): DPE_METRICS["course_result"],
    ("DPE-RESULT", "course_margin_pct"): DPE_METRICS["course_margin"],
    ("DPE-REVENUE", "total_revenue"): DPE_METRICS["total_revenue"],
    ("DPE-REVENUE", "institutional_revenue"): DPE_METRICS["institutional_revenue"],
    ("DPE-REVENUE", "course_revenue"): DPE_METRICS["course_revenue"],
    ("DPE-REVENUE", "revenue_per_student"): DPE_METRICS["revenue_per_student"],
    ("DPE-EXPENSE", "total_expense"): DPE_METRICS["total_expense"],
    ("DPE-EXPENSE", "institutional_expense"): DPE_METRICS["institutional_expense"],
    ("DPE-EXPENSE", "allocatable_expense"): DPE_METRICS["allocatable_expense"],
    ("DPE-EXPENSE", "course_total_cost"): DPE_METRICS["course_cost"],
    ("DPE-TEACHING", "teaching_cost"): DPE_METRICS["teaching_cost"],
    ("DPE-TEACHING", "total_workload_hours"): DPE_METRICS["total_workload_hours"],
    ("DPE-TEACHING", "avg_workload_hours_per_teacher"): DPE_METRICS["avg_workload_hours_per_teacher"],
    ("DPE-TEACHING", "teacher_count"): DPE_METRICS["teacher_count"],
    ("DPE-ALLOCATION", "allocated_expense"): DPE_METRICS["allocated_expense"],
    ("DPE-ALLOCATION", "unallocated_expense"): DPE_METRICS["unallocated_expense"],
    ("DPE-ALLOCATION", "reconciliation_pct"): DPE_METRICS["reconciliation_pct"],
}

_DPE_PERCENT_TARGET_METRICS = {
    DPE_METRICS["institutional_margin"], DPE_METRICS["course_margin"], DPE_METRICS["reconciliation_pct"],
}


@dataclass(frozen=True, slots=True)
class DPEAdapterError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _period_key(value: str) -> int:
    text = _text(value)
    try:
        year, month = text[:7].split("-")
        return int(year) * 12 + int(month)
    except (ValueError, TypeError):
        return 0


def _selected_period(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload.get("selected_period") or {})


def _analytics(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload.get("analytics") or {})


def _overview(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload.get("overview") or {})


def _card_value(payload: Mapping[str, Any], key: str) -> float | int | None:
    card = dict((_analytics(payload).get("cards") or {}).get(key) or {})
    return card.get("value")


def _period_summary_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    selected = _selected_period(payload)
    overview_summary = dict(_overview(payload).get("summary") or {})
    if not selected:
        return ()
    total_revenue = _float(_card_value(payload, "total_revenue"))
    total_expense = _float(_card_value(payload, "expense_total"))
    result = _float(_card_value(payload, "economic_result"))
    return ({
        "period": _text(selected.get("period")),
        "status": _text(selected.get("status")),
        "total_revenue": total_revenue,
        "course_revenue": _float(_card_value(payload, "course_revenue")),
        "institutional_revenue": _float(_card_value(payload, "institutional_revenue")),
        "total_expense": total_expense,
        "institutional_result": result,
        "active_students": _int(_card_value(payload, "active_students")),
        "allocated_cost": _float(overview_summary.get("allocated_cost")),
        "pending_distribution_total": _float(overview_summary.get("pending_distribution_total")),
        "allocation_coverage": (_float(overview_summary.get("allocation_coverage_percent")) / 100.0)
            if _float(overview_summary.get("allocation_coverage_percent")) is not None else None,
    },)


def _previous_summary_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    analytics = _analytics(payload)
    previous = dict(analytics.get("previous_period") or {})
    previous_period = _text(previous.get("period"))
    if not previous_period:
        return ()
    row = next((dict(item) for item in analytics.get("trend") or () if _text(item.get("period")) == previous_period), None)
    if row is None:
        return ()
    return ({
        "period": previous_period,
        "total_revenue": _float(row.get("total_revenue")),
        "total_expense": _float(row.get("expense_total")),
        "institutional_result": _float(row.get("economic_result")),
        "active_students": _int(row.get("active_students")),
    },)


def _trend_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in _analytics(payload).get("trend") or ():
        period = _text(raw.get("period"))
        if not period:
            continue
        rows.append({
            "period": period,
            "total_revenue": _float(raw.get("total_revenue")),
            "total_expense": _float(raw.get("expense_total")),
            "institutional_result": _float(raw.get("economic_result")),
            "active_students": _int(raw.get("active_students")),
        })
    return tuple(sorted(rows, key=lambda row: (_period_key(row["period"]), row["period"])))


def _context_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in _overview(payload).get("offerings") or ():
        context_id = raw.get("period_offering_id")
        course = _text(raw.get("product"))
        label = _text(raw.get("label")) or course
        if context_id in (None, "") or not course:
            continue
        rows.append({
            "context_id": int(context_id),
            "course": course,
            "context_label": label,
            "modality": _text(raw.get("modality")),
            "shift": _text(raw.get("shift")),
            "location": _text(raw.get("location")),
            "active_students": _int(raw.get("active_students")),
            "revenue": _float(raw.get("revenue")),
            "allocated_cost": _float(raw.get("allocated_cost")),
            "economic_result": _float(raw.get("economic_result")),
        })
    return tuple(sorted(rows, key=lambda row: (row["course"].casefold(), row["context_label"].casefold(), row["context_id"])))


def _course_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in _analytics(payload).get("courses") or ():
        course = _text(raw.get("course"))
        if not course:
            continue
        rows.append({
            "course": course,
            "course_key": _text(raw.get("course_key")) or course,
            "active_students": _int(raw.get("active_students")),
            "offering_count": _int(raw.get("offering_count")),
            "revenue": _float(raw.get("revenue")),
            "allocated_cost": _float(raw.get("allocated_cost")),
            "economic_result": _float(raw.get("economic_result")),
            "teaching_cost": _float(raw.get("teaching_cost")),
            "direct_cost": _float(raw.get("direct_cost")),
            "shared_cost": _float(raw.get("shared_cost")),
            "revenue_complete": bool(raw.get("revenue_complete")),
            "cost_complete": bool(raw.get("cost_complete")),
        })
    return tuple(sorted(rows, key=lambda row: row["course"].casefold()))


def _course_component_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    order = {
        "Receita": 1,
        "Custo docente": 2,
        "Custo direto": 3,
        "Custo compartilhado": 4,
        "Resultado": 5,
    }
    for course in _course_rows(payload):
        values = (
            ("Receita", course.get("revenue")),
            ("Custo docente", course.get("teaching_cost")),
            ("Custo direto", course.get("direct_cost")),
            ("Custo compartilhado", course.get("shared_cost")),
            ("Resultado", course.get("economic_result")),
        )
        for component, amount in values:
            rows.append({"course": course["course"], "component": component, "sort_order": order[component], "amount": amount})
    return tuple(rows)


def _revenue_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("revenue_entries") or ():
        rows.append({
            "id": _int(raw.get("id")),
            "period": _text(_selected_period(payload).get("period")),
            "context_id": int(raw["period_offering_id"]) if raw.get("period_offering_id") not in (None, "") else None,
            "course": _text(raw.get("course_name")),
            "context_label": _text(raw.get("offering_label")),
            "category_code": _text(raw.get("category_code")),
            "category": _text(raw.get("category_name")),
            "scope": _text(raw.get("category_scope")),
            "description": _text(raw.get("description")),
            "amount": _float(raw.get("amount")) or 0.0,
            "source_type": _text(raw.get("source_type")),
            "source_reference": _text(raw.get("source_reference")),
            "notes": _text(raw.get("notes")),
        })
    return tuple(rows)


def _expense_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in (payload.get("expenses") or {}).get("expenses") or ():
        rows.append({
            "id": _int(raw.get("id")),
            "period": _text(raw.get("period")) or _text(_selected_period(payload).get("period")),
            "expense_date": _date(raw.get("expense_date")),
            "description": _text(raw.get("description")),
            "amount": _float(raw.get("amount")) or 0.0,
            "expense_kind": _text(raw.get("expense_kind")),
            "expense_scope": _text(raw.get("expense_scope")),
            "cost_center_code": _text(raw.get("cost_center_code")) or "(sem centro)",
            "cost_center_name": _text(raw.get("cost_center_name")) or _text(raw.get("cost_center_code")) or "(sem centro)",
            "category_code": _text(raw.get("category_code")) or "(sem categoria)",
            "category": _text(raw.get("category_name")) or _text(raw.get("category_code")) or "(sem categoria)",
            "allocation_rule": _text(raw.get("allocation_rule_name")) or _text(raw.get("allocation_rule_code")),
            "allocation_driver": _text(raw.get("allocation_driver")),
            "counterparty": _text(raw.get("counterparty_name")),
            "document_number": _text(raw.get("document_number")),
            "source_type": _text(raw.get("source_type")),
        })
    return tuple(rows)


def _allocation_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    selected = dict((payload.get("allocation") or {}).get("selected_run") or {})
    rows: list[dict[str, Any]] = []
    for raw in selected.get("results") or ():
        expense = dict(raw.get("expense_snapshot") or {})
        classification = dict(expense.get("classification") or {})
        center = dict(classification.get("cost_center") or {})
        category = dict(classification.get("category") or {})
        offering = dict(raw.get("offering_snapshot") or {})
        product = dict(offering.get("product") or {})
        rows.append({
            "run_id": _int(selected.get("id")),
            "run_number": _int(selected.get("run_number")),
            "expense_id": _int(raw.get("expense_id")),
            "expense": _text(raw.get("expense_description")),
            "context_id": _int(raw.get("period_offering_id")),
            "context_label": _text(raw.get("offering_label")),
            "course": _text(product.get("name")),
            "cost_center_code": _text(center.get("code")) or "(sem centro)",
            "cost_center_name": _text(center.get("name")) or _text(center.get("code")) or "(sem centro)",
            "category": _text(category.get("name")) or _text(category.get("code")) or "(sem categoria)",
            "expense_kind": _text(expense.get("expense_kind")),
            "driver_type": _text(raw.get("driver_type")),
            "allocated_amount": _float(raw.get("allocated_amount")) or 0.0,
        })
    return tuple(rows)


def _teaching_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in (payload.get("teaching") or {}).get("period_teachers") or ():
        teacher = dict(raw.get("teacher") or {})
        rows.append({
            "teacher_id": _int(raw.get("teacher_id")),
            "teacher": _text(teacher.get("display_name")) or _text(raw.get("teacher_name")),
            "relationship": _text(raw.get("relationship_type")),
            "workload_hours": _float(raw.get("workload_hours")),
            "payroll_total": _float(raw.get("payroll_total")),
            "payroll_count": _int(raw.get("payroll_count")),
        })
    return tuple(rows)


def _target_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = []
    for raw in (payload.get("management") or {}).get("targets") or ():
        rows.append({
            "indicator": _text(raw.get("indicator_label")) or _text(raw.get("indicator_code")),
            "metric": _text(raw.get("metric_label")) or _text(raw.get("metric_key")),
            "dimension": _text(raw.get("dimension_label")) or "Institucional",
            "current_value": _float(raw.get("current_value")),
            "target": _float(raw.get("target")),
            "target_min": _float(raw.get("target_min")),
            "target_max": _float(raw.get("target_max")),
            "attention": _float(raw.get("attention")),
            "status": _text((raw.get("status") or {}).get("label")),
            "valid_from": _text(raw.get("valid_from")),
            "valid_to": _text(raw.get("valid_to")),
            "justification": _text(raw.get("justification")),
        })
    return tuple(rows)


def _closure_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    checks = ((payload.get("closure") or {}).get("checklist") or {}).get("checks") or ()
    return tuple({
        "code": _text(raw.get("code")),
        "check": _text(raw.get("label")),
        "status": _text(raw.get("status")),
        "detail": _text(raw.get("detail")),
    } for raw in checks)


def _action_rows(payload: Mapping[str, Any]) -> tuple[ActionPlanRowSpec, ...]:
    rows: list[ActionPlanRowSpec] = []
    for raw in (payload.get("management") or {}).get("actions") or ():
        indicator = _text(raw.get("indicator_label")) or _text(raw.get("indicator_code"))
        metric = _text(raw.get("metric_label")) or _text(raw.get("metric_key"))
        if metric:
            indicator = f"{indicator} · {metric}"
        rows.append(ActionPlanRowSpec(
            source=ActionPlanRowSource.OFFICIAL,
            values={
                "indicator": indicator,
                "problem": _text(raw.get("problem")),
                "diagnosis": _text(raw.get("probable_cause")) or _text(raw.get("cause")),
                "action": _text(raw.get("corrective_action")),
                "owner": _text(raw.get("responsible")),
                "deadline": _date(raw.get("due_date")),
                "status": _text(raw.get("effective_status")) or _text(raw.get("status")),
            },
        ))
    return tuple(rows)


def _management_fact_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in (payload.get("management") or {}).get("facts") or ():
        dimensions = dict(raw.get("dimensions") or {})
        rows.append({
            "indicator_code": _text(raw.get("indicator_code")),
            "metric_key": _text(raw.get("metric_key")),
            "dimension_key": _text(raw.get("dimension_key")) or "TOTAL",
            "dimension_label": _text(raw.get("dimension_label")) or "TOTAL",
            "course": _text(dimensions.get("course")),
            "academic_directorate": _text(dimensions.get("academic_directorate")),
            "value": _float(raw.get("value")),
            "available": bool(raw.get("available", raw.get("value") is not None)),
            "source": _text(raw.get("source")),
            "note": _text(raw.get("note")),
        })
    return tuple(rows)


def _management_fact_value(payload: Mapping[str, Any], indicator_code: str, metric_key: str) -> float | None:
    for row in _management_fact_rows(payload):
        if row["indicator_code"] == indicator_code and row["metric_key"] == metric_key and row["dimension_key"] == "TOTAL":
            return row["value"] if row["available"] else None
    return None


def _management_summary_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    period = _text(_selected_period(payload).get("period"))
    if not period:
        return ()
    expenses = _expense_rows(payload)
    revenue = _float(_card_value(payload, "total_revenue"))
    expense = _float(_card_value(payload, "expense_total"))
    institutional_expense_fallback = sum(float(row.get("amount") or 0) for row in expenses if _text(row.get("expense_scope")).upper() == "INSTITUTIONAL")
    allocatable_fallback = sum(float(row.get("amount") or 0) for row in expenses if _text(row.get("expense_scope")).upper() != "INSTITUTIONAL")
    teaching = dict(payload.get("teaching") or {})
    teaching_summary = dict(teaching.get("summary") or {})
    teachers = tuple(teaching.get("period_teachers") or ())
    workload_fallback = _float(teaching_summary.get("total_workload_hours"))
    if workload_fallback is None:
        workload_fallback = sum(float(row.get("workload_hours") or 0) for row in teachers)
    teacher_count_fallback = _int(teaching_summary.get("period_teacher_count")) or len(teachers)
    avg_fallback = (workload_fallback / teacher_count_fallback) if workload_fallback is not None and teacher_count_fallback else None
    selected_run = dict((payload.get("allocation") or {}).get("selected_run") or {})
    allocated_fallback = _float(selected_run.get("allocated_total"))
    unallocated_fallback = _float(selected_run.get("unallocated_total"))
    run_expense = _float(selected_run.get("expense_total"))
    reconciliation_fallback = None
    if run_expense is not None:
        reconciliation_fallback = 1.0 if run_expense == 0 else ((allocated_fallback or 0.0) / run_expense)
    targets = _effective_target_rows(payload)
    collision_count = sum(1 for row in targets if int(row.get("collision_count") or 0) > 1)
    return ({
        "period": period,
        "institutional_revenue": _management_fact_value(payload, "DPE-REVENUE", "institutional_revenue") if _management_fact_value(payload, "DPE-REVENUE", "institutional_revenue") is not None else _float(_card_value(payload, "institutional_revenue")),
        "institutional_expense": _management_fact_value(payload, "DPE-EXPENSE", "institutional_expense") if _management_fact_value(payload, "DPE-EXPENSE", "institutional_expense") is not None else institutional_expense_fallback,
        "allocatable_expense": _management_fact_value(payload, "DPE-EXPENSE", "allocatable_expense") if _management_fact_value(payload, "DPE-EXPENSE", "allocatable_expense") is not None else allocatable_fallback,
        "coverage_index": _management_fact_value(payload, "DPE-RESULT", "coverage_index") if _management_fact_value(payload, "DPE-RESULT", "coverage_index") is not None else (None if expense in (None, 0) or revenue is None else revenue / expense),
        "teaching_cost": _management_fact_value(payload, "DPE-TEACHING", "teaching_cost"),
        "total_workload_hours": _management_fact_value(payload, "DPE-TEACHING", "total_workload_hours") if _management_fact_value(payload, "DPE-TEACHING", "total_workload_hours") is not None else workload_fallback,
        "avg_workload_hours_per_teacher": _management_fact_value(payload, "DPE-TEACHING", "avg_workload_hours_per_teacher") if _management_fact_value(payload, "DPE-TEACHING", "avg_workload_hours_per_teacher") is not None else avg_fallback,
        "teacher_count": int(_management_fact_value(payload, "DPE-TEACHING", "teacher_count")) if _management_fact_value(payload, "DPE-TEACHING", "teacher_count") is not None else int(teacher_count_fallback),
        "allocated_expense": _management_fact_value(payload, "DPE-ALLOCATION", "allocated_expense") if _management_fact_value(payload, "DPE-ALLOCATION", "allocated_expense") is not None else allocated_fallback,
        "unallocated_expense": _management_fact_value(payload, "DPE-ALLOCATION", "unallocated_expense") if _management_fact_value(payload, "DPE-ALLOCATION", "unallocated_expense") is not None else unallocated_fallback,
        "reconciliation_pct": (lambda v: None if v is None else v / 100.0)(_management_fact_value(payload, "DPE-ALLOCATION", "reconciliation_pct")) if _management_fact_value(payload, "DPE-ALLOCATION", "reconciliation_pct") is not None else reconciliation_fallback,
        "target_collision_count": collision_count,
    },)


def _target_course_selector(raw: Mapping[str, Any]) -> tuple[str, str]:
    fact = dict(raw.get("fact") or {})
    dimensions = dict(fact.get("dimensions") or {})
    course = _text(dimensions.get("course"))
    academic_directorate = _text(dimensions.get("academic_directorate"))
    if course:
        return course, academic_directorate
    if _text(raw.get("dimension_key")) == "TOTAL":
        return "(todos)", ""
    label = _text(raw.get("dimension_label"))
    for part in label.split(" | "):
        if part.lower().startswith("curso:"):
            course = part.split(":", 1)[1].strip()
        elif "diretoria" in part.lower() and ":" in part:
            academic_directorate = part.split(":", 1)[1].strip()
    return course or "(todos)", academic_directorate


def _effective_target_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw_value in (payload.get("management") or {}).get("targets") or ():
        raw = dict(raw_value)
        if not bool(raw.get("active_for_period")) or bool(raw.get("historical_metric")):
            continue
        key = (_text(raw.get("indicator_code")), _text(raw.get("metric_key")))
        metric_code = DPE_TARGET_METRIC_MAP.get(key)
        if not metric_code:
            continue
        course_selector, academic_directorate = _target_course_selector(raw)
        row = {
            "metric_code": metric_code,
            "indicator_code": key[0],
            "metric_key": key[1],
            "metric_label": _text(raw.get("metric_label")) or key[1],
            "course_selector": course_selector,
            "academic_directorate": academic_directorate,
            "direction": _text(raw.get("direction")),
            "target": _float(raw.get("target")),
            "attention": _float(raw.get("attention")),
            "target_min": _float(raw.get("target_min")),
            "target_max": _float(raw.get("target_max")),
            "attention_min": _float(raw.get("attention_min")),
            "attention_max": _float(raw.get("attention_max")),
            "current_value": _float(raw.get("current_value")),
            "status": _text((raw.get("status") or {}).get("label")),
            "valid_from": _text(raw.get("valid_from")),
            "valid_to": _text(raw.get("valid_to")),
            "dimension_label": _text(raw.get("dimension_label")) or "TOTAL",
            "collision_count": 1,
        }
        grouped.setdefault((metric_code, course_selector), []).append(row)
    output: list[dict[str, Any]] = []
    for _, rows in sorted(grouped.items(), key=lambda item: item[0]):
        row = dict(rows[0])
        row["collision_count"] = len(rows)
        if len(rows) > 1:
            row["target"] = None
            row["attention"] = None
            row["status"] = "Múltiplas metas ativas"
        output.append(row)
    return tuple(output)


def _closure_summary_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    checklist = dict((payload.get("closure") or {}).get("checklist") or {})
    summary = dict(checklist.get("summary") or {})
    teaching_summary = dict((payload.get("teaching") or {}).get("summary") or {})
    if not checklist and not teaching_summary:
        return ()
    return ({
        "period": _text(_selected_period(payload).get("period")),
        "pass_count": _int(summary.get("pass_count")),
        "warning_count": _int(summary.get("warning_count")),
        "blocker_count": _int(summary.get("blocker_count")),
        "review_pending_count": _int(summary.get("review_pending_count")),
        "check_count": _int(summary.get("check_count")),
        "checklist_ready": bool(summary.get("checklist_ready")),
        "can_close": bool(summary.get("can_close")),
        "payroll_pending_count": _int(teaching_summary.get("payroll_pending_count")),
    },)


def _dimension_rows(rows: tuple[Mapping[str, Any], ...], key: str, label_key: str | None = None) -> tuple[dict[str, Any], ...]:
    values: dict[Any, str] = {}
    for row in rows:
        raw = row.get(key)
        if raw in (None, ""):
            continue
        label = _text(row.get(label_key)) if label_key else _text(raw)
        values.setdefault(raw, label or _text(raw))
    sorted_values = sorted(values.items(), key=lambda item: (item[1].casefold(), str(item[0])))
    return tuple({key: value, "label": label, "sort_order": idx} for idx, (value, label) in enumerate(sorted_values, 1))


def _dataset_specs(payload: Mapping[str, Any], auth_scope: tuple[str, ...]) -> tuple[DatasetSpec, ...]:
    summary = _period_summary_rows(payload)
    previous = _previous_summary_rows(payload)
    trend = _trend_rows(payload)
    contexts = _context_rows(payload)
    courses = _course_rows(payload)
    components = _course_component_rows(payload)
    revenues = _revenue_rows(payload)
    expenses = _expense_rows(payload)
    allocations = _allocation_rows(payload)
    teaching = _teaching_rows(payload)
    targets = _target_rows(payload)
    effective_targets = _effective_target_rows(payload)
    management_facts = _management_fact_rows(payload)
    management_summary = _management_summary_rows(payload)
    closure = _closure_rows(payload)
    closure_summary = _closure_summary_rows(payload)

    course_dim = _dimension_rows(courses, "course")
    context_dim_map: dict[int, dict[str, Any]] = {}
    for idx, row in enumerate(contexts, 1):
        context_dim_map[int(row["context_id"])] = {
            "context_id": int(row["context_id"]), "context_label": row["context_label"], "course": row["course"], "sort_order": idx,
        }
    context_dim = tuple(context_dim_map.values())
    center_dim = _dimension_rows(expenses, "cost_center_code", "cost_center_name")
    category_dim = _dimension_rows(expenses, "category")
    component_dim = tuple({"component": name, "label": name, "sort_order": idx} for idx, name in enumerate(
        ("Receita", "Custo docente", "Custo direto", "Custo compartilhado", "Resultado"), 1
    ))
    period_dim = tuple({"period": row["period"], "label": row["period"], "sort_order": _period_key(row["period"])} for row in trend)

    return (
        DatasetSpec("dpe_period_summary", "Resumo Financeiro", "RESUMO FINANCEIRO", "tbDPEResumo", (
            ColumnSpec("period", "Competência", ColumnDataType.TEXT),
            ColumnSpec("status", "Status", ColumnDataType.TEXT),
            ColumnSpec("total_revenue", "Receita total", ColumnDataType.DECIMAL),
            ColumnSpec("course_revenue", "Receita de cursos", ColumnDataType.DECIMAL),
            ColumnSpec("institutional_revenue", "Receita institucional", ColumnDataType.DECIMAL),
            ColumnSpec("total_expense", "Despesa total", ColumnDataType.DECIMAL),
            ColumnSpec("institutional_result", "Resultado institucional", ColumnDataType.DECIMAL),
            ColumnSpec("active_students", "Alunos ativos", ColumnDataType.INTEGER),
            ColumnSpec("allocated_cost", "Custo distribuído", ColumnDataType.DECIMAL),
            ColumnSpec("pending_distribution_total", "Pendente de distribuição", ColumnDataType.DECIMAL),
            ColumnSpec("allocation_coverage", "Cobertura de distribuição", ColumnDataType.DECIMAL),
        ), grain=("period",), rows=summary, source="DPECostAnalyticsRepository + DPEV2OverviewRepository", authorization_scope=auth_scope),
        DatasetSpec("dpe_previous_summary", "Resumo Competência Anterior", "RESUMO ANTERIOR DPE", "tbDPEAnterior", (
            ColumnSpec("period", "Competência anterior", ColumnDataType.TEXT),
            ColumnSpec("total_revenue", "Receita total", ColumnDataType.DECIMAL),
            ColumnSpec("total_expense", "Despesa total", ColumnDataType.DECIMAL),
            ColumnSpec("institutional_result", "Resultado institucional", ColumnDataType.DECIMAL),
            ColumnSpec("active_students", "Alunos ativos", ColumnDataType.INTEGER),
        ), grain=("period",), rows=previous, source="DPECostAnalyticsRepository.previous_period", authorization_scope=auth_scope),
        DatasetSpec("dpe_trend", "Histórico DPE", "TENDENCIA DPE", "tbDPETendencia", (
            ColumnSpec("period", "Competência", ColumnDataType.TEXT),
            ColumnSpec("total_revenue", "Receita total", ColumnDataType.DECIMAL),
            ColumnSpec("total_expense", "Despesa total", ColumnDataType.DECIMAL),
            ColumnSpec("institutional_result", "Resultado institucional", ColumnDataType.DECIMAL),
            ColumnSpec("active_students", "Alunos ativos", ColumnDataType.INTEGER),
        ), grain=("period",), rows=trend, source="DPECostAnalyticsRepository.trend", authorization_scope=auth_scope, filter_dimensions=("period",), dimension_columns={"period": "period"}),
        DatasetSpec("dpe_contexts", "Cursos e Contextos", "CURSOS E CONTEXTOS", "tbDPEContextos", (
            ColumnSpec("context_id", "Contexto ID", ColumnDataType.INTEGER),
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("context_label", "Curso / contexto", ColumnDataType.TEXT),
            ColumnSpec("modality", "Modalidade", ColumnDataType.TEXT),
            ColumnSpec("shift", "Turno", ColumnDataType.TEXT),
            ColumnSpec("location", "Local", ColumnDataType.TEXT),
            ColumnSpec("active_students", "Alunos ativos", ColumnDataType.INTEGER),
            ColumnSpec("revenue", "Receita atribuída", ColumnDataType.DECIMAL),
            ColumnSpec("allocated_cost", "Custo atribuído", ColumnDataType.DECIMAL),
            ColumnSpec("economic_result", "Resultado", ColumnDataType.DECIMAL),
        ), grain=("context_id",), rows=contexts, source="DPEV2OverviewRepository.offerings", authorization_scope=auth_scope, filter_dimensions=("course", "context"), dimension_columns={"course": "course", "context": "context_id"}),
        DatasetSpec("dpe_courses", "Resumo por Curso", "CURSOS DPE", "tbDPECursos", (
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("course_key", "Chave", ColumnDataType.TEXT, technical=True),
            ColumnSpec("offering_count", "Contextos", ColumnDataType.INTEGER),
            ColumnSpec("active_students", "Alunos ativos", ColumnDataType.INTEGER),
            ColumnSpec("revenue", "Receita", ColumnDataType.DECIMAL),
            ColumnSpec("allocated_cost", "Custo atribuído", ColumnDataType.DECIMAL),
            ColumnSpec("economic_result", "Resultado", ColumnDataType.DECIMAL),
            ColumnSpec("teaching_cost", "Custo docente", ColumnDataType.DECIMAL),
            ColumnSpec("direct_cost", "Custo direto", ColumnDataType.DECIMAL),
            ColumnSpec("shared_cost", "Custo compartilhado", ColumnDataType.DECIMAL),
            ColumnSpec("revenue_complete", "Receita completa", ColumnDataType.BOOLEAN),
            ColumnSpec("cost_complete", "Custo completo", ColumnDataType.BOOLEAN),
        ), grain=("course",), rows=courses, source="DPECostAnalyticsRepository.courses", authorization_scope=auth_scope, filter_dimensions=("course",), dimension_columns={"course": "course"}),
        DatasetSpec("dpe_course_components", "Composição por Curso", "COMPOSICAO CURSOS", "tbDPEComposicao", (
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("component", "Componente", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
            ColumnSpec("amount", "Valor", ColumnDataType.DECIMAL),
        ), grain=("course", "component"), rows=components, source="DPECostAnalyticsRepository.courses", authorization_scope=auth_scope, filter_dimensions=("course", "component"), dimension_columns={"course": "course", "component": "component"}),
        DatasetSpec("dpe_revenues", "Receitas", "RECEITAS DPE", "tbDPEReceitas", (
            ColumnSpec("id", "ID", ColumnDataType.INTEGER),
            ColumnSpec("period", "Competência", ColumnDataType.TEXT),
            ColumnSpec("context_id", "Contexto ID", ColumnDataType.INTEGER),
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("context_label", "Curso / contexto", ColumnDataType.TEXT),
            ColumnSpec("category_code", "Categoria código", ColumnDataType.TEXT),
            ColumnSpec("category", "Categoria", ColumnDataType.TEXT),
            ColumnSpec("scope", "Escopo", ColumnDataType.TEXT),
            ColumnSpec("description", "Descrição", ColumnDataType.TEXT),
            ColumnSpec("amount", "Valor", ColumnDataType.DECIMAL),
            ColumnSpec("source_type", "Origem", ColumnDataType.TEXT),
            ColumnSpec("source_reference", "Referência", ColumnDataType.TEXT),
            ColumnSpec("notes", "Observações", ColumnDataType.TEXT),
        ), grain=("id",), rows=revenues, source="dpe_revenue_entries", authorization_scope=auth_scope, sensitivity="internal", filter_dimensions=("course", "context"), dimension_columns={"course": "course", "context": "context_id"}),
        DatasetSpec("dpe_expenses", "Despesas", "DESPESAS DPE", "tbDPEDespesas", (
            ColumnSpec("id", "ID", ColumnDataType.INTEGER),
            ColumnSpec("period", "Competência", ColumnDataType.TEXT),
            ColumnSpec("expense_date", "Data", ColumnDataType.DATE),
            ColumnSpec("description", "Descrição", ColumnDataType.TEXT),
            ColumnSpec("amount", "Valor", ColumnDataType.DECIMAL),
            ColumnSpec("expense_kind", "Natureza", ColumnDataType.TEXT),
            ColumnSpec("expense_scope", "Tratamento", ColumnDataType.TEXT),
            ColumnSpec("cost_center_code", "Centro código", ColumnDataType.TEXT),
            ColumnSpec("cost_center_name", "Centro de custo", ColumnDataType.TEXT),
            ColumnSpec("category_code", "Categoria código", ColumnDataType.TEXT),
            ColumnSpec("category", "Categoria", ColumnDataType.TEXT),
            ColumnSpec("allocation_rule", "Forma de distribuição", ColumnDataType.TEXT),
            ColumnSpec("allocation_driver", "Base", ColumnDataType.TEXT),
            ColumnSpec("counterparty", "Favorecido", ColumnDataType.TEXT),
            ColumnSpec("document_number", "Documento", ColumnDataType.TEXT),
            ColumnSpec("source_type", "Origem", ColumnDataType.TEXT),
        ), grain=("id",), rows=expenses, source="dpe_cost_expenses", authorization_scope=auth_scope, sensitivity="restricted", filter_dimensions=("cost_center", "expense_category"), dimension_columns={"cost_center": "cost_center_code", "expense_category": "category"}),
        DatasetSpec("dpe_allocations", "Rateios Oficiais", "RATEIOS DPE", "tbDPERateios", (
            ColumnSpec("run_id", "Run ID", ColumnDataType.INTEGER),
            ColumnSpec("run_number", "Versão", ColumnDataType.INTEGER),
            ColumnSpec("expense_id", "Despesa ID", ColumnDataType.INTEGER),
            ColumnSpec("expense", "Despesa", ColumnDataType.TEXT),
            ColumnSpec("context_id", "Contexto ID", ColumnDataType.INTEGER),
            ColumnSpec("context_label", "Curso / contexto", ColumnDataType.TEXT),
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("cost_center_code", "Centro código", ColumnDataType.TEXT),
            ColumnSpec("cost_center_name", "Centro de custo", ColumnDataType.TEXT),
            ColumnSpec("category", "Categoria", ColumnDataType.TEXT),
            ColumnSpec("expense_kind", "Natureza", ColumnDataType.TEXT),
            ColumnSpec("driver_type", "Base de distribuição", ColumnDataType.TEXT),
            ColumnSpec("allocated_amount", "Valor atribuído", ColumnDataType.DECIMAL),
        ), grain=("run_id", "expense_id", "context_id"), rows=allocations, source="dpe_cost_allocation_results official run", authorization_scope=auth_scope, sensitivity="internal", filter_dimensions=("course", "context", "cost_center"), dimension_columns={"course": "course", "context": "context_id", "cost_center": "cost_center_code"}),
        DatasetSpec("dpe_teaching", "Docência", "DOCENCIA DPE", "tbDPEDocencia", (
            ColumnSpec("teacher_id", "Docente ID", ColumnDataType.INTEGER),
            ColumnSpec("teacher", "Docente", ColumnDataType.TEXT),
            ColumnSpec("relationship", "Vínculo", ColumnDataType.TEXT),
            ColumnSpec("workload_hours", "Carga no mês", ColumnDataType.DECIMAL),
            ColumnSpec("payroll_total", "Custo conciliado", ColumnDataType.DECIMAL),
            ColumnSpec("payroll_count", "Lançamentos de folha", ColumnDataType.INTEGER),
        ), grain=("teacher_id",), rows=teaching, source="DPECostTeachingRepository", authorization_scope=auth_scope, sensitivity="restricted"),
        DatasetSpec("dpe_targets", "Metas DPE", "METAS DPE BACKEND", "tbDPEMetasBackend", (
            ColumnSpec("indicator", "Indicador", ColumnDataType.TEXT),
            ColumnSpec("metric", "Métrica", ColumnDataType.TEXT),
            ColumnSpec("dimension", "Escopo", ColumnDataType.TEXT),
            ColumnSpec("current_value", "Atual", ColumnDataType.DECIMAL),
            ColumnSpec("target", "Meta", ColumnDataType.DECIMAL),
            ColumnSpec("target_min", "Meta mínima", ColumnDataType.DECIMAL),
            ColumnSpec("target_max", "Meta máxima", ColumnDataType.DECIMAL),
            ColumnSpec("attention", "Atenção", ColumnDataType.DECIMAL),
            ColumnSpec("status", "Situação", ColumnDataType.TEXT),
            ColumnSpec("valid_from", "Vigência inicial", ColumnDataType.TEXT),
            ColumnSpec("valid_to", "Vigência final", ColumnDataType.TEXT),
            ColumnSpec("justification", "Justificativa", ColumnDataType.TEXT),
        ), grain=("indicator", "metric", "dimension"), rows=targets, source="management_indicator_targets via DPEManagementRepository", authorization_scope=auth_scope),
        DatasetSpec("dpe_targets_effective", "Metas Efetivas DPE", "METAS EFETIVAS DPE", "tbDPEMetasEfetivas", (
            ColumnSpec("metric_code", "Métrica Core", ColumnDataType.TEXT),
            ColumnSpec("indicator_code", "Indicador", ColumnDataType.TEXT),
            ColumnSpec("metric_key", "Métrica backend", ColumnDataType.TEXT),
            ColumnSpec("metric_label", "Métrica", ColumnDataType.TEXT),
            ColumnSpec("course_selector", "Curso seletor", ColumnDataType.TEXT),
            ColumnSpec("academic_directorate", "Diretoria acadêmica", ColumnDataType.TEXT),
            ColumnSpec("direction", "Direção", ColumnDataType.TEXT),
            ColumnSpec("target", "Meta", ColumnDataType.DECIMAL),
            ColumnSpec("attention", "Atenção", ColumnDataType.DECIMAL),
            ColumnSpec("target_min", "Meta mínima", ColumnDataType.DECIMAL),
            ColumnSpec("target_max", "Meta máxima", ColumnDataType.DECIMAL),
            ColumnSpec("attention_min", "Atenção mínima", ColumnDataType.DECIMAL),
            ColumnSpec("attention_max", "Atenção máxima", ColumnDataType.DECIMAL),
            ColumnSpec("current_value", "Atual backend", ColumnDataType.DECIMAL),
            ColumnSpec("status", "Situação", ColumnDataType.TEXT),
            ColumnSpec("valid_from", "Vigência inicial", ColumnDataType.TEXT),
            ColumnSpec("valid_to", "Vigência final", ColumnDataType.TEXT),
            ColumnSpec("dimension_label", "Escopo", ColumnDataType.TEXT),
            ColumnSpec("collision_count", "Metas ativas no mesmo seletor", ColumnDataType.INTEGER),
        ), grain=("metric_code", "course_selector"), rows=effective_targets, source="DPEManagementRepository · metas vigentes pré-resolvidas para o Excel Oficial", authorization_scope=auth_scope),
        DatasetSpec("dpe_management_facts", "Fatos de Gestão DPE", "INDICADORES GESTAO DPE", "tbDPEFatosGestao", (
            ColumnSpec("indicator_code", "Indicador", ColumnDataType.TEXT),
            ColumnSpec("metric_key", "Métrica", ColumnDataType.TEXT),
            ColumnSpec("dimension_key", "Chave do escopo", ColumnDataType.TEXT),
            ColumnSpec("dimension_label", "Escopo", ColumnDataType.TEXT),
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("academic_directorate", "Diretoria acadêmica", ColumnDataType.TEXT),
            ColumnSpec("value", "Valor atual", ColumnDataType.DECIMAL),
            ColumnSpec("available", "Disponível", ColumnDataType.BOOLEAN),
            ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ColumnSpec("note", "Observação", ColumnDataType.TEXT),
        ), grain=("indicator_code", "metric_key", "dimension_key"), rows=management_facts, source="DPEManagementRepository.facts", authorization_scope=auth_scope),
        DatasetSpec("dpe_management_summary", "Resumo de Gestão DPE", "RESUMO GESTAO DPE", "tbDPEResumoGestao", (
            ColumnSpec("period", "Competência", ColumnDataType.TEXT),
            ColumnSpec("institutional_revenue", "Receita institucional", ColumnDataType.DECIMAL),
            ColumnSpec("institutional_expense", "Despesa institucional", ColumnDataType.DECIMAL),
            ColumnSpec("allocatable_expense", "Despesa distribuível", ColumnDataType.DECIMAL),
            ColumnSpec("coverage_index", "Índice de cobertura", ColumnDataType.DECIMAL),
            ColumnSpec("teaching_cost", "Custo docente", ColumnDataType.DECIMAL),
            ColumnSpec("total_workload_hours", "Carga docente total", ColumnDataType.DECIMAL),
            ColumnSpec("avg_workload_hours_per_teacher", "Carga média por docente", ColumnDataType.DECIMAL),
            ColumnSpec("teacher_count", "Docentes", ColumnDataType.INTEGER),
            ColumnSpec("allocated_expense", "Despesa distribuída", ColumnDataType.DECIMAL),
            ColumnSpec("unallocated_expense", "Despesa não distribuída", ColumnDataType.DECIMAL),
            ColumnSpec("reconciliation_pct", "Reconciliação", ColumnDataType.DECIMAL),
            ColumnSpec("target_collision_count", "Conflitos de metas", ColumnDataType.INTEGER),
        ), grain=("period",), rows=management_summary, source="DPEManagementRepository + Cost Engine oficial", authorization_scope=auth_scope),
        DatasetSpec("dpe_closure", "Checklist de Fechamento", "CHECKLIST DPE", "tbDPEChecklist", (
            ColumnSpec("code", "Código", ColumnDataType.TEXT),
            ColumnSpec("check", "Verificação", ColumnDataType.TEXT),
            ColumnSpec("status", "Situação", ColumnDataType.TEXT),
            ColumnSpec("detail", "Detalhe", ColumnDataType.TEXT),
        ), grain=("code",), rows=closure, source="DPECostClosureRepository", authorization_scope=auth_scope),
        DatasetSpec("dpe_closure_summary", "Resumo de Governança DPE", "GOVERNANCA DPE", "tbDPEGovernanca", (
            ColumnSpec("period", "Competência", ColumnDataType.TEXT),
            ColumnSpec("pass_count", "Checks aprovados", ColumnDataType.INTEGER),
            ColumnSpec("warning_count", "Avisos", ColumnDataType.INTEGER),
            ColumnSpec("blocker_count", "Bloqueios", ColumnDataType.INTEGER),
            ColumnSpec("review_pending_count", "Revisões pendentes", ColumnDataType.INTEGER),
            ColumnSpec("check_count", "Checks totais", ColumnDataType.INTEGER),
            ColumnSpec("checklist_ready", "Checklist pronto", ColumnDataType.BOOLEAN),
            ColumnSpec("can_close", "Pode fechar", ColumnDataType.BOOLEAN),
            ColumnSpec("payroll_pending_count", "Folha pendente de conciliação", ColumnDataType.INTEGER),
        ), grain=("period",), rows=closure_summary, source="DPECostClosureRepository + DPECostTeachingRepository", authorization_scope=auth_scope),
        DatasetSpec("dpe_courses_dim", "Cursos", "CURSOS DPE DIM", "tbDPECursosDim", (
            ColumnSpec("course", "Código do curso", ColumnDataType.TEXT),
            ColumnSpec("label", "Curso", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ), grain=("course",), rows=course_dim, source="DPE Cost Engine course catalog", technical=True, authorization_scope=auth_scope),
        DatasetSpec("dpe_contexts_dim", "Contextos", "CONTEXTOS DPE DIM", "tbDPEContextosDim", (
            ColumnSpec("context_id", "Contexto ID", ColumnDataType.INTEGER),
            ColumnSpec("context_label", "Curso / contexto", ColumnDataType.TEXT),
            ColumnSpec("course", "Curso", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ), grain=("context_id",), rows=context_dim, source="DPE Cost Engine offering snapshots", technical=True, authorization_scope=auth_scope),
        DatasetSpec("dpe_cost_centers_dim", "Centros de Custo", "CENTROS CUSTO DIM", "tbDPECentrosDim", (
            ColumnSpec("cost_center_code", "Código", ColumnDataType.TEXT),
            ColumnSpec("label", "Centro de custo", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ), grain=("cost_center_code",), rows=center_dim, source="dpe_cost_centers", technical=True, authorization_scope=auth_scope),
        DatasetSpec("dpe_categories_dim", "Categorias de Despesa", "CATEGORIAS DPE DIM", "tbDPECategoriasDim", (
            ColumnSpec("category", "Chave da categoria", ColumnDataType.TEXT),
            ColumnSpec("label", "Categoria", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ), grain=("category",), rows=category_dim, source="dpe_expense_categories", technical=True, authorization_scope=auth_scope),
        DatasetSpec("dpe_components_dim", "Componentes", "COMPONENTES DPE DIM", "tbDPEComponentesDim", (
            ColumnSpec("component", "Código do componente", ColumnDataType.TEXT),
            ColumnSpec("label", "Componente", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ), grain=("component",), rows=component_dim, source="DPE course analytics", technical=True, authorization_scope=auth_scope),
        DatasetSpec("dpe_periods_dim", "Competências", "DIM_PERIODO", "tbDPEPeriodos", (
            ColumnSpec("period", "Código da competência", ColumnDataType.TEXT),
            ColumnSpec("label", "Competência", ColumnDataType.TEXT),
            ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ), grain=("period",), rows=period_dim, source="DPECostAnalyticsRepository.periods", technical=True, authorization_scope=auth_scope),
    )


def _metric_specs() -> tuple[MetricSpec, ...]:
    currency = MetricUnit.CURRENCY_BRL
    return (
        MetricSpec(DPE_METRICS["total_revenue"], "Receita total", MetricAggregation.SUM, currency, "Todas as receitas do ledger oficial da competência.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["total_expense"], "Despesa total", MetricAggregation.SUM, currency, "Todas as despesas oficiais ativas da competência.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["institutional_result"], "Resultado institucional", MetricAggregation.SUM, currency, "Receita total menos despesa total da competência.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["institutional_margin"], "Margem institucional", MetricAggregation.RATIO, MetricUnit.PERCENT, "Resultado institucional dividido pela receita total.", offline_recut=False, display_precision=1),
        MetricSpec(DPE_METRICS["institutional_revenue"], "Receita institucional", MetricAggregation.VALUE, currency, "Receita registrada sem vínculo a curso/contexto.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["institutional_expense"], "Despesa institucional", MetricAggregation.VALUE, currency, "Despesas com tratamento institucional, fora da margem dos cursos.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["allocatable_expense"], "Despesa distribuível", MetricAggregation.VALUE, currency, "Despesas diretas/compartilhadas sujeitas ao Allocation Engine.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["coverage_index"], "Índice de cobertura", MetricAggregation.VALUE, MetricUnit.DECIMAL, "Receita total dividida pela despesa total.", offline_recut=False, valid_min=0, display_precision=2, number_format='0.00x'),
        MetricSpec(DPE_METRICS["active_students"], "Alunos ativos", MetricAggregation.SUM, MetricUnit.COUNT, allowed_dimensions=("course", "context"), display_precision=0),
        MetricSpec(DPE_METRICS["course_revenue"], "Receita atribuída ao curso", MetricAggregation.SUM, currency, allowed_dimensions=("course", "context"), display_precision=2),
        MetricSpec(DPE_METRICS["course_cost"], "Custo atribuído ao curso", MetricAggregation.SUM, currency, allowed_dimensions=("course", "context"), display_precision=2),
        MetricSpec(DPE_METRICS["course_result"], "Resultado do curso", MetricAggregation.SUM, currency, allowed_dimensions=("course", "context"), display_precision=2),
        MetricSpec(DPE_METRICS["course_margin"], "Margem do curso", MetricAggregation.RATIO, MetricUnit.PERCENT, allowed_dimensions=("course", "context"), display_precision=1),
        MetricSpec(DPE_METRICS["revenue_per_student"], "Receita por aluno", MetricAggregation.RATIO, currency, allowed_dimensions=("course", "context"), display_precision=2),
        MetricSpec(DPE_METRICS["cost_per_student"], "Custo por aluno", MetricAggregation.RATIO, currency, allowed_dimensions=("course", "context"), display_precision=2),
        MetricSpec(DPE_METRICS["selected_expense"], "Despesa no recorte", MetricAggregation.SUM, currency, allowed_dimensions=("cost_center", "expense_category"), display_precision=2),
        MetricSpec(DPE_METRICS["allocated_cost"], "Custo oficial distribuído", MetricAggregation.SUM, currency, allowed_dimensions=("course", "context", "cost_center"), display_precision=2),
        MetricSpec(DPE_METRICS["allocation_coverage"], "Cobertura da distribuição", MetricAggregation.SUM, MetricUnit.PERCENT, offline_recut=False, valid_min=0, valid_max=1, display_precision=1),
        MetricSpec(DPE_METRICS["teaching_cost"], "Custo docente", MetricAggregation.VALUE, currency, "Custo docente canônico apurado pelo Cost Engine.", offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["total_workload_hours"], "Carga docente total", MetricAggregation.VALUE, MetricUnit.HOURS, "Soma das cargas das atividades docentes da competência.", offline_recut=False, valid_min=0, display_precision=1),
        MetricSpec(DPE_METRICS["avg_workload_hours_per_teacher"], "Carga média por docente", MetricAggregation.VALUE, MetricUnit.HOURS, "Carga docente total dividida pelos docentes vinculados à competência.", offline_recut=False, valid_min=0, display_precision=1),
        MetricSpec(DPE_METRICS["teacher_count"], "Docentes na competência", MetricAggregation.VALUE, MetricUnit.COUNT, offline_recut=False, valid_min=0, display_precision=0),
        MetricSpec(DPE_METRICS["allocated_expense"], "Despesa distribuída", MetricAggregation.VALUE, currency, offline_recut=False, valid_min=0, display_precision=2),
        MetricSpec(DPE_METRICS["unallocated_expense"], "Despesa não distribuída", MetricAggregation.VALUE, currency, offline_recut=False, valid_min=0, display_precision=2),
        MetricSpec(DPE_METRICS["reconciliation_pct"], "Reconciliação da distribuição", MetricAggregation.VALUE, MetricUnit.PERCENT, offline_recut=False, valid_min=1, valid_max=1, display_precision=1),
        MetricSpec(DPE_METRICS["closure_blockers"], "Bloqueios de fechamento", MetricAggregation.VALUE, MetricUnit.COUNT, offline_recut=False, valid_min=0, valid_max=0, display_precision=0),
        MetricSpec(DPE_METRICS["payroll_pending"], "Folha pendente de conciliação", MetricAggregation.VALUE, MetricUnit.COUNT, offline_recut=False, valid_min=0, valid_max=0, display_precision=0),
        MetricSpec(DPE_METRICS["target_collisions"], "Conflitos de metas vigentes", MetricAggregation.VALUE, MetricUnit.COUNT, offline_recut=False, valid_min=0, valid_max=0, display_precision=0),
        MetricSpec(DPE_METRICS["component_amount"], "Composição financeira do curso", MetricAggregation.SUM, currency, allowed_dimensions=("course", "component"), display_precision=2),
        MetricSpec(DPE_METRICS["trend_revenue"], "Receita total", MetricAggregation.SUM, currency, allowed_dimensions=("period",), offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["trend_expense"], "Despesa total", MetricAggregation.SUM, currency, allowed_dimensions=("period",), offline_recut=False, display_precision=2),
        MetricSpec(DPE_METRICS["trend_result"], "Resultado institucional", MetricAggregation.SUM, currency, allowed_dimensions=("period",), offline_recut=False, display_precision=2),
        MetricSpec(DPE_COMPARISON_METRICS["total_revenue"], "Receita anterior", MetricAggregation.SUM, currency, offline_recut=False, display_precision=2),
        MetricSpec(DPE_COMPARISON_METRICS["total_expense"], "Despesa anterior", MetricAggregation.SUM, currency, offline_recut=False, display_precision=2),
        MetricSpec(DPE_COMPARISON_METRICS["institutional_result"], "Resultado anterior", MetricAggregation.SUM, currency, offline_recut=False, display_precision=2),
        MetricSpec(DPE_COMPARISON_METRICS["institutional_margin"], "Margem anterior", MetricAggregation.RATIO, MetricUnit.PERCENT, offline_recut=False, display_precision=1),
    )


def _metric_bindings() -> tuple[MetricBinding, ...]:
    return (
        MetricBinding(DPE_METRICS["total_revenue"], "dpe_period_summary", value_column="total_revenue"),
        MetricBinding(DPE_METRICS["total_expense"], "dpe_period_summary", value_column="total_expense"),
        MetricBinding(DPE_METRICS["institutional_result"], "dpe_period_summary", value_column="institutional_result"),
        MetricBinding(DPE_METRICS["institutional_margin"], "dpe_period_summary", components={"numerator": "institutional_result", "denominator": "total_revenue"}),
        MetricBinding(DPE_METRICS["institutional_revenue"], "dpe_management_summary", value_column="institutional_revenue"),
        MetricBinding(DPE_METRICS["institutional_expense"], "dpe_management_summary", value_column="institutional_expense"),
        MetricBinding(DPE_METRICS["allocatable_expense"], "dpe_management_summary", value_column="allocatable_expense"),
        MetricBinding(DPE_METRICS["coverage_index"], "dpe_management_summary", value_column="coverage_index"),
        MetricBinding(DPE_METRICS["active_students"], "dpe_contexts", value_column="active_students", filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["course_revenue"], "dpe_contexts", value_column="revenue", filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["course_cost"], "dpe_contexts", value_column="allocated_cost", filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["course_result"], "dpe_contexts", value_column="economic_result", filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["course_margin"], "dpe_contexts", components={"numerator": "economic_result", "denominator": "revenue"}, filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["revenue_per_student"], "dpe_contexts", components={"numerator": "revenue", "denominator": "active_students"}, filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["cost_per_student"], "dpe_contexts", components={"numerator": "allocated_cost", "denominator": "active_students"}, filter_parameters={"course": "course", "context": "context"}),
        MetricBinding(DPE_METRICS["selected_expense"], "dpe_expenses", value_column="amount", filter_parameters={"cost_center": "cost_center"}),
        MetricBinding(DPE_METRICS["allocated_cost"], "dpe_allocations", value_column="allocated_amount", filter_parameters={"course": "course", "context": "context", "cost_center": "cost_center"}),
        MetricBinding(DPE_METRICS["allocation_coverage"], "dpe_period_summary", value_column="allocation_coverage"),
        MetricBinding(DPE_METRICS["teaching_cost"], "dpe_management_summary", value_column="teaching_cost"),
        MetricBinding(DPE_METRICS["total_workload_hours"], "dpe_management_summary", value_column="total_workload_hours"),
        MetricBinding(DPE_METRICS["avg_workload_hours_per_teacher"], "dpe_management_summary", value_column="avg_workload_hours_per_teacher"),
        MetricBinding(DPE_METRICS["teacher_count"], "dpe_management_summary", value_column="teacher_count"),
        MetricBinding(DPE_METRICS["allocated_expense"], "dpe_management_summary", value_column="allocated_expense"),
        MetricBinding(DPE_METRICS["unallocated_expense"], "dpe_management_summary", value_column="unallocated_expense"),
        MetricBinding(DPE_METRICS["reconciliation_pct"], "dpe_management_summary", value_column="reconciliation_pct"),
        MetricBinding(DPE_METRICS["target_collisions"], "dpe_management_summary", value_column="target_collision_count"),
        MetricBinding(DPE_METRICS["closure_blockers"], "dpe_closure_summary", value_column="blocker_count"),
        MetricBinding(DPE_METRICS["payroll_pending"], "dpe_closure_summary", value_column="payroll_pending_count"),
        MetricBinding(DPE_METRICS["component_amount"], "dpe_course_components", value_column="amount", filter_parameters={"course": "course"}),
        MetricBinding(DPE_METRICS["trend_revenue"], "dpe_trend", value_column="total_revenue"),
        MetricBinding(DPE_METRICS["trend_expense"], "dpe_trend", value_column="total_expense"),
        MetricBinding(DPE_METRICS["trend_result"], "dpe_trend", value_column="institutional_result"),
        MetricBinding(DPE_COMPARISON_METRICS["total_revenue"], "dpe_previous_summary", value_column="total_revenue"),
        MetricBinding(DPE_COMPARISON_METRICS["total_expense"], "dpe_previous_summary", value_column="total_expense"),
        MetricBinding(DPE_COMPARISON_METRICS["institutional_result"], "dpe_previous_summary", value_column="institutional_result"),
        MetricBinding(DPE_COMPARISON_METRICS["institutional_margin"], "dpe_previous_summary", components={"numerator": "institutional_result", "denominator": "total_revenue"}),
    )


def _target_bindings() -> tuple[TargetBindingSpec, ...]:
    dataset = "dpe_targets_effective"
    institutional = (
        DPE_METRICS["total_revenue"], DPE_METRICS["total_expense"], DPE_METRICS["institutional_result"],
        DPE_METRICS["institutional_margin"], DPE_METRICS["institutional_revenue"], DPE_METRICS["institutional_expense"],
        DPE_METRICS["allocatable_expense"], DPE_METRICS["coverage_index"], DPE_METRICS["teaching_cost"],
        DPE_METRICS["total_workload_hours"], DPE_METRICS["teacher_count"], DPE_METRICS["allocated_expense"],
        DPE_METRICS["unallocated_expense"], DPE_METRICS["reconciliation_pct"],
    )
    rows = [
        TargetBindingSpec(
            metric_code=code, dataset_code=dataset, target_column="target", attention_column="attention",
            criteria_constants={"metric_code": code, "course_selector": "(todos)"},
            value_scale=0.01 if code in _DPE_PERCENT_TARGET_METRICS else 1.0,
        )
        for code in institutional
    ]
    for code in (
        DPE_METRICS["course_revenue"], DPE_METRICS["course_cost"], DPE_METRICS["course_result"],
        DPE_METRICS["course_margin"], DPE_METRICS["revenue_per_student"],
    ):
        rows.append(TargetBindingSpec(
            metric_code=code, dataset_code=dataset, target_column="target", attention_column="attention",
            criteria_parameters={"course_selector": "course"}, criteria_constants={"metric_code": code},
            value_scale=0.01 if code in _DPE_PERCENT_TARGET_METRICS else 1.0,
        ))
    return tuple(rows)


class DPEAdapter(DirectorateAdapter):
    adapter_code = "dpe"
    adapter_version = 2

    def build_spec(self, adapter_input: AdapterInput) -> WorkbookSpec:
        payload = adapter_input.authorized_data
        if adapter_input.snapshot_context.directorate.upper() != "DPE":
            raise DPEAdapterError("dpe.snapshot_scope_mismatch", "DPEAdapter aceita somente snapshots da DPE.")

        selected = _selected_period(payload)
        period = _text(selected.get("period"))
        if not period:
            raise DPEAdapterError("dpe.no_period", "O snapshot DPE não possui competência selecionada.")

        datasets = _dataset_specs(payload, adapter_input.snapshot_context.authorization_scope)
        contexts = next(item for item in datasets if item.code == "dpe_contexts").rows
        expenses = next(item for item in datasets if item.code == "dpe_expenses").rows
        if not contexts:
            raise DPEAdapterError("dpe.no_contexts", "A competência não possui cursos/contextos econômicos incluídos.")

        raw_initial = dict(adapter_input.snapshot_context.initial_filters)
        raw_initial.update(adapter_input.initial_state or {})
        course = _text(raw_initial.get("course")) or "(todos)"
        context = raw_initial.get("context") if raw_initial.get("context") not in (None, "") else "(todos)"
        cost_center = _text(raw_initial.get("cost_center")) or "(todos)"

        parameters = (
            ParameterSpec("period", "Competência", "period", initial_value=period, editable=False, required=True, description="Competência oficial incorporada ao snapshot. Para trocar o mês, gere um novo Excel Oficial.", display_order=10),
            ParameterSpec("course", "Curso", "course", initial_value=course, empty_option="(todos)", description="Recorta métricas atribuídas explicitamente a curso/contexto.", display_order=20),
            ParameterSpec("context", "Curso / contexto", "context", initial_value=context, empty_option="(todos)", depends_on=("course",), description="Contexto econômico do curso dentro da competência.", display_order=30),
            ParameterSpec("cost_center", "Centro de custo", "cost_center", initial_value=cost_center, empty_option="(todos)", description="Recorta despesas e valores distribuídos por centro de custo.", display_order=40),
            ParameterSpec("period_status", "Status da competência", "", initial_value=_text(selected.get("status")), editable=False, required=True, description="Estado da competência no momento da exportação.", display_order=50),
        )

        dimensions = (
            DimensionSpec("period", "Competência", "dpe_periods_dim", "period", "label", sort_order_column="sort_order"),
            DimensionSpec("course", "Curso", "dpe_courses_dim", "course", "label", sort_order_column="sort_order"),
            DimensionSpec("context", "Curso / contexto", "dpe_contexts_dim", "context_id", "context_label", sort_order_column="sort_order", parent_dimension="course", parent_key_column="course"),
            DimensionSpec("cost_center", "Centro de custo", "dpe_cost_centers_dim", "cost_center_code", "label", sort_order_column="sort_order"),
            DimensionSpec("expense_category", "Categoria de despesa", "dpe_categories_dim", "category", "label", sort_order_column="sort_order"),
            DimensionSpec("component", "Componente financeiro", "dpe_components_dim", "component", "label", sort_order_column="sort_order"),
        )

        metrics = _metric_specs()
        bindings = _metric_bindings()
        ctx = adapter_input.snapshot_context
        snapshot = SnapshotSpec(
            export_id=ctx.export_id,
            generated_at=ctx.generated_at,
            generated_by=ctx.generated_by,
            authorization_scope=ctx.authorization_scope,
            system_version=ctx.system_version,
            schema_version=ctx.schema_version,
            adapter_version=self.adapter_version,
            initial_scope=dict(ctx.initial_filters),
            minimum_period=ctx.minimum_period or period,
            maximum_period=ctx.maximum_period or period,
            payload_hash=ctx.payload_hash,
        )
        identity = IdentitySpec(
            workbook_title="Excel Oficial · Diretoria de Planejamento Econômico",
            directorate_code="DPE",
            directorate_label="Diretoria de Planejamento Econômico",
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            scope_label="DPE",
        )

        quality = QualitySpec(
            dataset_checks=(
                QualityCheckSpec("dpe_summary_present", "Resumo financeiro disponível", "dataset_non_empty", "dpe_period_summary", QualitySeverity.BLOCKING, "Resumo financeiro disponível", "Resumo financeiro ausente."),
                QualityCheckSpec("dpe_contexts_present", "Cursos/contextos disponíveis", "dataset_non_empty", "dpe_contexts", QualitySeverity.BLOCKING, "Cursos/contextos disponíveis", "Nenhum curso/contexto incluído."),
                QualityCheckSpec("dpe_expenses_present", "Despesas oficiais disponíveis", "dataset_non_empty", "dpe_expenses", QualitySeverity.WARNING, "Ledger de despesas disponível", "Nenhuma despesa oficial exportada."),
                QualityCheckSpec("dpe_allocations_present", "Rateio oficial disponível", "dataset_non_empty", "dpe_allocations", QualitySeverity.WARNING, "Memória de rateio disponível", "Run oficial ausente ou sem resultados."),
            ),
            metric_checks=(
                QualityCheckSpec("dpe_revenue_available", "Receita total disponível", "metric_has_data", DPE_METRICS["total_revenue"], QualitySeverity.BLOCKING, "Receita disponível", "Receita total indisponível."),
                QualityCheckSpec("dpe_expense_available", "Despesa total disponível", "metric_has_data", DPE_METRICS["total_expense"], QualitySeverity.BLOCKING, "Despesa disponível", "Despesa total indisponível."),
                QualityCheckSpec("dpe_result_available", "Resultado institucional disponível", "metric_has_data", DPE_METRICS["institutional_result"], QualitySeverity.WARNING, "Resultado disponível", "Resultado indisponível; confira completude das receitas."),
                QualityCheckSpec("dpe_allocation_coverage_valid", "Cobertura da distribuição válida", "metric_valid_range", DPE_METRICS["allocation_coverage"], QualitySeverity.WARNING, "Cobertura válida", "Cobertura fora da faixa 0–100% ou indisponível."),
                QualityCheckSpec("dpe_reconciliation_complete", "Distribuição reconciliada", "metric_valid_range", DPE_METRICS["reconciliation_pct"], QualitySeverity.WARNING, "Distribuição reconciliada em 100%", "O run oficial ainda não reconcilia 100% das despesas distribuíveis."),
                QualityCheckSpec("dpe_closure_no_blockers", "Checklist de fechamento sem bloqueios", "metric_valid_range", DPE_METRICS["closure_blockers"], QualitySeverity.WARNING, "Nenhum bloqueio no checklist", "A competência ainda possui bloqueios de fechamento; o Excel permanece válido para análise, mas não representa um mês pronto para encerrar."),
                QualityCheckSpec("dpe_payroll_reconciled", "Folha docente conciliada", "metric_valid_range", DPE_METRICS["payroll_pending"], QualitySeverity.WARNING, "Folha docente conciliada", "Existem lançamentos de folha ainda não conciliados com docentes."),
                QualityCheckSpec("dpe_target_collisions", "Metas vigentes sem conflito", "metric_valid_range", DPE_METRICS["target_collisions"], QualitySeverity.WARNING, "Não há metas duplicadas no mesmo seletor", "Há mais de uma meta ativa para a mesma métrica e escopo; o target do card fica vazio até a governança ser corrigida."),
            ),
            coverage_checks=(
                QualityCheckSpec("dpe_course_dimension", "Dimensão Curso", "dimension_non_empty", "course", QualitySeverity.BLOCKING, "Cursos disponíveis", "Dimensão Curso vazia."),
                QualityCheckSpec("dpe_context_dimension", "Dimensão Curso / contexto", "dimension_non_empty", "context", QualitySeverity.BLOCKING, "Contextos disponíveis", "Dimensão Contexto vazia."),
            ),
            snapshot_checks=(
                QualityCheckSpec("dpe_export_id", "Export ID presente", "snapshot_field_present", "export_id", QualitySeverity.BLOCKING, "Export ID identificado", "Export ID ausente."),
                QualityCheckSpec("dpe_authorization_scope", "Escopo autorizado presente", "snapshot_field_present", "authorization_scope", QualitySeverity.BLOCKING, "Escopo identificado", "Escopo autorizado ausente."),
            ),
        )

        limitations = (
            LimitationSpec(
                code="dpe.fixed_competence_snapshot",
                title="Competência fixa no snapshot",
                description="A competência é protegida no Excel Oficial. Curso, contexto e centro de custo podem ser recortados offline; para trocar a competência deve ser gerado um novo arquivo.",
                severity=QualitySeverity.INFO,
                affected_dimension="period",
            ),
            LimitationSpec(
                code="dpe.institutional_vs_course_scope",
                title="Resultado institucional e resultado dos cursos possuem escopos diferentes",
                description="Resultado institucional usa todas as receitas e despesas oficiais. Resultado por curso usa somente receitas explicitamente atribuídas e custos do run oficial. Receitas/despesas institucionais podem permanecer fora da margem dos cursos.",
                severity=QualitySeverity.INFO,
                affected_metric=DPE_METRICS["course_result"],
            ),
            LimitationSpec(
                code="dpe.official_allocation_required",
                title="Custo por curso depende de run oficial atual",
                description="Quando não existe Allocation Run oficial conciliado com as despesas atuais, custos, resultado e margem por curso/contexto podem ficar indisponíveis. O Excel não cria rateio substituto.",
                severity=QualitySeverity.WARNING,
                affected_metric=DPE_METRICS["course_cost"],
            ),
            LimitationSpec(
                code="dpe.no_inferred_overhead",
                title="Overhead administrativo não é inferido pelo nome",
                description="A DPE atual exige classificação contábil explícita. O Excel Oficial preserva essa regra e não classifica despesas como overhead a partir de descrição, favorecido ou categoria textual.",
                severity=QualitySeverity.INFO,
            ),
            LimitationSpec(
                code="dpe.previous_period_snapshot",
                title="Comparação usa a competência anterior do snapshot",
                description="Receita, despesa, resultado e margem comparam a competência exportada com o mês imediatamente anterior calculado pelo Analytics DPE. Como a competência é fixa, essa evidência não é recalculada offline.",
                severity=QualitySeverity.INFO,
            ),
            LimitationSpec(
                code="dpe.range_targets_backend",
                title="Metas de faixa permanecem como mínimo e máximo",
                description="Metas do tipo faixa, como carga média por docente, são preservadas em METAS EFETIVAS DPE com limites mínimo/máximo. O card não reduz uma faixa a um único número artificial.",
                severity=QualitySeverity.INFO,
                affected_metric=DPE_METRICS["avg_workload_hours_per_teacher"],
            ),
        )

        domain_sheets = (
            DomainSheetSpec("summary", "Resumo Financeiro", "dpe_period_summary", "Resumo institucional da competência exportada.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("contexts", "Cursos e Contextos", "dpe_contexts", "Receita, custo, resultado e alunos por curso/contexto.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("courses", "Cursos DPE", "dpe_courses", "Consolidação econômica por curso.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("revenues", "Receitas DPE", "dpe_revenues", "Ledger de receitas da competência.", SheetRole.RAW_DATA),
            DomainSheetSpec("expenses", "Despesas DPE", "dpe_expenses", "Ledger oficial de despesas da competência.", SheetRole.RAW_DATA),
            DomainSheetSpec("allocations", "Rateios DPE", "dpe_allocations", "Memória do run oficial por despesa × contexto.", SheetRole.RAW_DATA),
            DomainSheetSpec("teaching", "Docência DPE", "dpe_teaching", "Carga e folha docente conciliada no período.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("targets", "Metas DPE Backend", "dpe_targets", "Metas e situação apuradas pelo backend DPE para auditoria.", SheetRole.REFERENCE),
            DomainSheetSpec("targets_effective", "Metas Efetivas DPE", "dpe_targets_effective", "Metas vigentes pré-resolvidas para os cards e recortes offline suportados.", SheetRole.REFERENCE),
            DomainSheetSpec("management_facts", "Indicadores Gestão DPE", "dpe_management_facts", "Fatos canônicos usados por metas e planos de gestão.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("management_summary", "Resumo Gestão DPE", "dpe_management_summary", "Resumo de docência, cobertura e distribuição da competência.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("closure", "Checklist DPE", "dpe_closure", "Checklist de fechamento e governança da competência.", SheetRole.REFERENCE),
            DomainSheetSpec("closure_summary", "Governança DPE", "dpe_closure_summary", "Resumo de bloqueios, avisos e conciliação docente para o fechamento.", SheetRole.REFERENCE),
            DomainSheetSpec("trend", "Tendência DPE", "dpe_trend", "Histórico institucional disponibilizado pelo Cost Engine.", SheetRole.DOMAIN_ANALYSIS),
        )

        return WorkbookSpec(
            identity=identity,
            snapshot=snapshot,
            initial_state=InitialStateSpec(values={
                "period": period,
                "course": course,
                "context": context,
                "cost_center": cost_center,
                "period_status": _text(selected.get("status")),
            }),
            parameters=parameters,
            datasets=datasets,
            dimensions=dimensions,
            metric_codes=tuple(metric.code for metric in metrics),
            metric_bindings=bindings,
            domain_sheets=domain_sheets,
            dashboard=DashboardSpec(
                title="PAINEL ECONÔMICO · DPE",
                kpis=(
                    KpiSpec(DPE_METRICS["total_revenue"], comparison_metric_code=DPE_COMPARISON_METRICS["total_revenue"], priority=10),
                    KpiSpec(DPE_METRICS["total_expense"], comparison_metric_code=DPE_COMPARISON_METRICS["total_expense"], priority=20),
                    KpiSpec(DPE_METRICS["institutional_result"], comparison_metric_code=DPE_COMPARISON_METRICS["institutional_result"], priority=30),
                    KpiSpec(DPE_METRICS["institutional_margin"], comparison_metric_code=DPE_COMPARISON_METRICS["institutional_margin"], priority=40),
                    KpiSpec(DPE_METRICS["course_result"], label_override="Resultado do curso/contexto", priority=50),
                    KpiSpec(DPE_METRICS["selected_expense"], label_override="Despesa no centro selecionado", priority=60),
                    KpiSpec(DPE_METRICS["teaching_cost"], label_override="Custo docente", priority=70),
                    KpiSpec(DPE_METRICS["avg_workload_hours_per_teacher"], label_override="Carga média por docente", priority=80),
                ),
                charts=(
                    ChartSpec("dpe_revenue_trend", "Receita total por competência", DPE_METRICS["trend_revenue"], "dpe_trend", "period", ChartType.LINE, ChartRole.EVOLUTION, sort="dimension_asc"),
                    ChartSpec("dpe_expense_trend", "Despesa total por competência", DPE_METRICS["trend_expense"], "dpe_trend", "period", ChartType.LINE, ChartRole.EVOLUTION, sort="dimension_asc"),
                    ChartSpec("dpe_result_trend", "Resultado institucional por competência", DPE_METRICS["trend_result"], "dpe_trend", "period", ChartType.COLUMN, ChartRole.EVOLUTION, sort="dimension_asc"),
                    ChartSpec("dpe_expenses_by_category", "Despesas por categoria", DPE_METRICS["selected_expense"], "dpe_expenses", "expense_category", ChartType.BAR, ChartRole.COMPOSITION, sort="dimension_asc"),
                    ChartSpec("dpe_course_result", "Resultado por curso", DPE_METRICS["course_result"], "dpe_contexts", "course", ChartType.BAR, ChartRole.COMPARISON, sort="dimension_asc"),
                ),
                attention_blocks=(
                    "Receita, despesa, resultado e margem institucionais representam a competência inteira e não mudam com o filtro de Curso/Centro de custo.",
                    "Resultado e margem de curso/contexto usam somente receitas explicitamente atribuídas e custos do Allocation Run oficial.",
                    "Centro de custo recorta despesas e valores distribuídos; o Excel não atribui automaticamente receitas institucionais a centros de custo.",
                    "Quando o run oficial está ausente ou desatualizado, custos e resultados por curso podem ficar indisponíveis em vez de usar estimativas.",
                    "Metas vigentes são lidas do módulo gerencial DPE; metas de faixa permanecem como mínimo/máximo e não são convertidas em um único alvo artificial.",
                    "Checklist de fechamento, reconciliação do rateio e conciliação da folha aparecem em Qualidade e Governança como avisos enquanto a competência ainda estiver em andamento.",
                ),
            ),
            matrix=MatrixSpec(
                metric_code=DPE_METRICS["component_amount"],
                row_dimension="course",
                column_dimension="component",
                delta=False,
                sorting="label_asc",
                empty_behavior="blank",
            ),
            quality=quality,
            action_plan=ActionPlanSpec(
                enabled=True,
                official_fields=(),
                local_editable_fields=("indicator", "problem", "diagnosis", "action", "owner", "deadline", "status"),
                rows=_action_rows(payload),
                local_blank_rows=8,
                status_options=("Aberto", "Em andamento", "Concluído", "Atrasado", "Cancelado"),
                completed_statuses=("Concluído", "Cancelado"),
            ),
            technical=TechnicalSpec(include_targets=True, include_indicators=True, include_calc=True, include_support_lists=True, include_period_dimension=False, include_month_dimension=False),
            capabilities=AdapterCapabilities(supports_comparison=True, supports_history_window=False, supports_action_plan=True, interactive_dimensions=("course", "context", "cost_center")),
            limitations=limitations,
            metrics=metrics,
            target_bindings=_target_bindings(),
        )


__all__ = ["DPE_COMPARISON_METRICS", "DPE_METRICS", "DPEAdapter", "DPEAdapterError"]
