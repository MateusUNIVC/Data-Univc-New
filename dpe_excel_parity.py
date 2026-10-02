from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DPEParityCase:
    code: str
    scope: str
    expected: float | None
    actual: float | None
    tolerance: float
    passed: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DPEParityReport:
    cases: tuple[DPEParityCase, ...]
    source_kind: str = "fixture"

    @property
    def failures(self) -> tuple[DPEParityCase, ...]:
        return tuple(case for case in self.cases if not case.passed)

    @property
    def status(self) -> str:
        if self.failures:
            return "BLOCKED"
        return "READY" if self.source_kind == "production" else "CANDIDATE_PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_kind": self.source_kind,
            "case_count": len(self.cases),
            "failure_count": len(self.failures),
            "cases": [case.as_dict() for case in self.cases],
        }


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same(expected: float | None, actual: float | None, tolerance: float) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    return abs(float(expected) - float(actual)) <= tolerance


def _case(code: str, scope: str, expected: float | None, actual: float | None, *, tolerance: float = 0.01, note: str = "") -> DPEParityCase:
    return DPEParityCase(code, scope, expected, actual, tolerance, _same(expected, actual, tolerance), note)


def audit_dpe_payload_parity(payload: Mapping[str, Any], *, source_kind: str = "fixture") -> DPEParityReport:
    analytics = dict(payload.get("analytics") or {})
    cards = dict(analytics.get("cards") or {})
    overview = dict(payload.get("overview") or {})
    overview_summary = dict(overview.get("summary") or {})
    revenues = [dict(row) for row in payload.get("revenue_entries") or ()]
    expenses = [dict(row) for row in (payload.get("expenses") or {}).get("expenses") or ()]
    teaching = dict(payload.get("teaching") or {})
    teaching_summary = dict(teaching.get("summary") or {})
    teachers = [dict(row) for row in teaching.get("period_teachers") or ()]
    allocation = dict((payload.get("allocation") or {}).get("selected_run") or {})
    allocation_rows = [dict(row) for row in allocation.get("results") or ()]
    management = dict(payload.get("management") or {})
    management_facts = [dict(row) for row in management.get("facts") or ()]
    management_targets = [dict(row) for row in management.get("targets") or ()]
    closure = dict(payload.get("closure") or {})
    checklist = dict(closure.get("checklist") or {})
    checklist_checks = [dict(row) for row in checklist.get("checks") or ()]
    checklist_summary = dict(checklist.get("summary") or {})
    closure_official_run = dict(closure.get("official_run") or {})

    cases: list[DPEParityCase] = []
    raw_revenue = sum(float(row.get("amount") or 0) for row in revenues)
    raw_expense = sum(float(row.get("amount") or 0) for row in expenses)
    raw_result = raw_revenue - raw_expense
    raw_margin = None if raw_revenue == 0 else raw_result / raw_revenue * 100.0

    def card(key: str) -> float | None:
        return _num((cards.get(key) or {}).get("value"))

    cases.extend((
        _case("institution.total_revenue", "TOTAL", card("total_revenue"), raw_revenue),
        _case("institution.total_expense", "TOTAL", card("expense_total"), raw_expense),
        _case("institution.result", "TOTAL", card("economic_result"), raw_result),
        _case("institution.margin_pct", "TOTAL", card("operating_margin_percent"), raw_margin),
        _case("overview.total_revenue", "TOTAL", _num(overview_summary.get("total_revenue")), raw_revenue),
        _case("overview.expense_total", "TOTAL", _num(overview_summary.get("expense_total")), raw_expense),
    ))

    contexts = {int(row.get("period_offering_id")): dict(row) for row in overview.get("offerings") or () if row.get("period_offering_id") is not None}
    for context_id, context in sorted(contexts.items()):
        label = str(context.get("label") or context_id)
        context_revenue = sum(float(row.get("amount") or 0) for row in revenues if row.get("period_offering_id") == context_id)
        context_cost = sum(float(row.get("allocated_amount") or 0) for row in allocation_rows if row.get("period_offering_id") == context_id)
        context_result = context_revenue - context_cost
        context_margin = None if context_revenue == 0 else context_result / context_revenue * 100.0
        cases.extend((
            _case("context.revenue", label, _num(context.get("revenue")), context_revenue),
            _case("context.allocated_cost", label, _num(context.get("allocated_cost")), context_cost),
            _case("context.result", label, _num(context.get("economic_result")), context_result),
            _case("context.margin_pct", label, _num(context.get("margin_percent")), context_margin, tolerance=0.02),
        ))

    analytics_courses = {str(row.get("course") or ""): dict(row) for row in analytics.get("courses") or () if str(row.get("course") or "")}
    for course_name, course in sorted(analytics_courses.items()):
        course_context_ids = {cid for cid, row in contexts.items() if str(row.get("product") or "") == course_name}
        revenue = sum(float(row.get("amount") or 0) for row in revenues if row.get("period_offering_id") in course_context_ids)
        cost = sum(float(row.get("allocated_amount") or 0) for row in allocation_rows if row.get("period_offering_id") in course_context_ids)
        result = revenue - cost
        margin = None if revenue == 0 else result / revenue * 100.0
        cases.extend((
            _case("course.revenue", course_name, _num(course.get("revenue")), revenue),
            _case("course.allocated_cost", course_name, _num(course.get("allocated_cost")), cost),
            _case("course.result", course_name, _num(course.get("economic_result")), result),
            _case("course.margin_pct", course_name, _num(course.get("margin_percent")), margin, tolerance=0.02),
        ))

    sector_rows = {str(row.get("key") or ""): _num(row.get("amount")) for row in analytics.get("expenses_by_sector") or ()}
    by_center: dict[str, float] = {}
    for row in expenses:
        name = str(row.get("cost_center_name") or row.get("cost_center_code") or "(sem centro)")
        by_center[name] = by_center.get(name, 0.0) + float(row.get("amount") or 0)
    for center, amount in sorted(by_center.items()):
        cases.append(_case("cost_center.expense", center, sector_rows.get(center), amount))

    allocated_total = sum(float(row.get("allocated_amount") or 0) for row in allocation_rows)
    cases.append(_case("allocation.allocated_total", "TOTAL", _num(allocation.get("allocated_total")), allocated_total))

    # Previous-period semantics come from the DPE Analytics previous month.
    previous = dict(analytics.get("previous_period") or {})
    previous_period = str(previous.get("period") or "")
    previous_row = next((dict(row) for row in analytics.get("trend") or () if str(row.get("period") or "") == previous_period), None)
    if previous_row:
        previous_map = {
            "total_revenue": _num(previous_row.get("total_revenue")),
            "expense_total": _num(previous_row.get("expense_total")),
            "economic_result": _num(previous_row.get("economic_result")),
            "operating_margin_percent": _num(previous_row.get("operating_margin_percent")),
        }
        for key, previous_value in previous_map.items():
            current_value = card(key)
            comparison = dict((cards.get(key) or {}).get("comparison") or {})
            expected_absolute = _num(comparison.get("absolute"))
            actual_absolute = None if current_value is None or previous_value is None else current_value - previous_value
            # Only assert card comparison when the backend provided it; always audit the previous row itself.
            cases.append(_case(f"previous.{key}.value", previous_period, previous_value, _num(previous_row.get(key))))
            if expected_absolute is not None:
                cases.append(_case(f"previous.{key}.absolute_delta", previous_period, expected_absolute, actual_absolute, tolerance=0.02))

    # Management facts must reconcile with the operational sources that feed the DPE engine.
    fact_map: dict[tuple[str, str, str], float | None] = {}
    for fact in management_facts:
        if not bool(fact.get("available", fact.get("value") is not None)):
            continue
        fact_map[(str(fact.get("indicator_code") or ""), str(fact.get("metric_key") or ""), str(fact.get("dimension_key") or "TOTAL"))] = _num(fact.get("value"))

    institutional_revenue = sum(float(row.get("amount") or 0) for row in revenues if str(row.get("category_scope") or "").upper() == "INSTITUTIONAL" or row.get("period_offering_id") in (None, ""))
    institutional_expense = sum(float(row.get("amount") or 0) for row in expenses if str(row.get("expense_scope") or "").upper() == "INSTITUTIONAL")
    allocatable_expense = sum(float(row.get("amount") or 0) for row in expenses if str(row.get("expense_scope") or "").upper() != "INSTITUTIONAL")
    workload = _num(teaching_summary.get("total_workload_hours"))
    if workload is None:
        workload = sum(float(row.get("workload_hours") or 0) for row in teachers)
    teacher_count = _num(teaching_summary.get("period_teacher_count"))
    if teacher_count is None:
        teacher_count = float(len(teachers))
    avg_workload = None if not teacher_count else (workload or 0.0) / teacher_count
    teaching_cost = sum(float(row.get("allocated_amount") or 0) for row in allocation_rows if str((row.get("expense_snapshot") or {}).get("expense_kind") or "").upper() == "PAYROLL")
    run_expense = _num(allocation.get("expense_total"))
    run_allocated = _num(allocation.get("allocated_total"))
    run_unallocated = _num(allocation.get("unallocated_total"))
    reconciliation_pct = None if run_expense is None else (100.0 if run_expense == 0 else 100.0 * (run_allocated or 0.0) / run_expense)

    independent_totals = {
        ("DPE-RESULT", "institutional_result", "TOTAL"): raw_result,
        ("DPE-RESULT", "institutional_margin_pct", "TOTAL"): raw_margin,
        ("DPE-RESULT", "coverage_index", "TOTAL"): None if raw_expense == 0 else raw_revenue / raw_expense,
        ("DPE-REVENUE", "total_revenue", "TOTAL"): raw_revenue,
        ("DPE-REVENUE", "institutional_revenue", "TOTAL"): institutional_revenue,
        ("DPE-EXPENSE", "total_expense", "TOTAL"): raw_expense,
        ("DPE-EXPENSE", "institutional_expense", "TOTAL"): institutional_expense,
        ("DPE-EXPENSE", "allocatable_expense", "TOTAL"): allocatable_expense,
        ("DPE-TEACHING", "teaching_cost", "TOTAL"): teaching_cost,
        ("DPE-TEACHING", "total_workload_hours", "TOTAL"): workload,
        ("DPE-TEACHING", "avg_workload_hours_per_teacher", "TOTAL"): avg_workload,
        ("DPE-TEACHING", "teacher_count", "TOTAL"): teacher_count,
        ("DPE-ALLOCATION", "allocated_expense", "TOTAL"): run_allocated,
        ("DPE-ALLOCATION", "unallocated_expense", "TOTAL"): run_unallocated,
        ("DPE-ALLOCATION", "reconciliation_pct", "TOTAL"): reconciliation_pct,
    }
    for key, actual in independent_totals.items():
        if key in fact_map:
            cases.append(_case(f"management.{key[0]}.{key[1]}", key[2], fact_map[key], actual, tolerance=0.02))

    # Course facts are reconciled with analytics course rows when present.
    for fact in management_facts:
        dims = dict(fact.get("dimensions") or {})
        course_name = str(dims.get("course") or "")
        if not course_name or not bool(fact.get("available", fact.get("value") is not None)):
            continue
        course = analytics_courses.get(course_name)
        if not course:
            continue
        metric_key = str(fact.get("metric_key") or "")
        source_map = {
            "course_revenue": "revenue",
            "course_total_cost": "allocated_cost",
            "course_result": "economic_result",
            "course_margin_pct": "margin_percent",
        }
        if metric_key in source_map:
            cases.append(_case(f"management.course.{metric_key}", course_name, _num(fact.get("value")), _num(course.get(source_map[metric_key])), tolerance=0.02))

    # Every active management target that carries a current value should point to the same underlying fact.
    for target in management_targets:
        if not bool(target.get("active_for_period")) or bool(target.get("historical_metric")):
            continue
        fact = dict(target.get("fact") or {})
        dimension_key = str(fact.get("dimension_key") or target.get("dimension_key") or "TOTAL")
        key = (str(target.get("indicator_code") or ""), str(target.get("metric_key") or ""), dimension_key)
        fact_value = fact_map.get(key)
        current_value = _num(target.get("current_value"))
        if fact_value is not None or current_value is not None:
            cases.append(_case(f"target.current_value.{key[0]}.{key[1]}", str(target.get("dimension_label") or dimension_key), fact_value, current_value, tolerance=0.02))

    # Closure summary counts must equal the checklist details.
    if checklist_summary or checklist_checks:
        statuses = [str(row.get("status") or "").upper() for row in checklist_checks]
        expected_counts = {
            "pass_count": float(statuses.count("PASS")),
            "warning_count": float(statuses.count("WARNING")),
            "blocker_count": float(statuses.count("BLOCKER")),
        }
        for field, actual in expected_counts.items():
            if checklist_summary.get(field) is not None:
                cases.append(_case(f"closure.{field}", "TOTAL", _num(checklist_summary.get(field)), actual, tolerance=0.0))
        if checklist_summary.get("check_count") is not None:
            cases.append(_case("closure.check_count", "TOTAL", _num(checklist_summary.get("check_count")), float(len(checklist_checks)), tolerance=0.0))

    # Closure run must describe the same official allocation memory used by the cost engine.
    if closure_official_run and allocation:
        for field in ("allocated_total", "unallocated_total", "expense_total"):
            if closure_official_run.get(field) is not None or allocation.get(field) is not None:
                cases.append(_case(f"closure.official_run.{field}", "TOTAL", _num(closure_official_run.get(field)), _num(allocation.get(field)), tolerance=0.01))

    return DPEParityReport(tuple(cases), source_kind=source_kind)

def render_dpe_parity_markdown(report: DPEParityReport) -> str:
    lines = [
        "# DPE Excel Official — Parity Report",
        "",
        f"- Status: **{report.status}**",
        f"- Source kind: `{report.source_kind}`",
        f"- Cases: **{len(report.cases)}**",
        f"- Failures: **{len(report.failures)}**",
        "",
        "| Case | Scope | Expected | Actual | Result |",
        "|---|---|---:|---:|---|",
    ]
    for case in report.cases:
        lines.append(f"| {case.code} | {case.scope} | {case.expected} | {case.actual} | {'PASS' if case.passed else 'FAIL'} |")
    return "\n".join(lines) + "\n"


__all__ = ["DPEParityCase", "DPEParityReport", "audit_dpe_payload_parity", "render_dpe_parity_markdown"]
