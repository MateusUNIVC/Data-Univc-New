from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dpe_cost_analytics import DPECostAnalyticsRepository
from dpe_cost_closure import DPECostClosureRepository
from dpe_cost_expenses import DPECostExpenseRepository
from dpe_cost_teaching import DPECostTeachingRepository
from management_catalog import indicator_spec, metric_spec, period_sort_key
from management_repository import ManagementRepository
from management_service import canonical_dimensions
from models import Course, Directorate
from security import DirectorateScope

CANONICAL_CODES = {
    "DPE-RESULT",
    "DPE-REVENUE",
    "DPE-EXPENSE",
    "DPE-TEACHING",
    "DPE-ALLOCATION",
}
FINAL_ACTION_STATUSES = {"CONCLUÍDO", "CONCLUIDO", "CANCELADO"}


@dataclass(frozen=True)
class MetricFact:
    indicator_code: str
    metric_key: str
    value: float | int | None
    dimensions: dict[str, str]
    dimension_key: str
    dimension_label: str
    source: str
    available: bool = True
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "indicator_code": self.indicator_code,
            "metric_key": self.metric_key,
            "value": self.value,
            "dimensions": dict(self.dimensions),
            "dimension_key": self.dimension_key,
            "dimension_label": self.dimension_label,
            "source": self.source,
            "available": bool(self.available),
            "note": self.note,
        }


class DPEManagementRepository:
    """Connect management targets/actions directly to the canonical DPE runtime.

    This repository never persists KPI measurements. Current values are calculated
    from the same Cost Engine repositories used by the operational and executive
    screens. The generic management tables remain only as durable stores for goals
    and action plans.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A gestão de metas da DPE pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope
        self.management = ManagementRepository(db, scope)

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _metric_dimensions(indicator_code: str, metric_key: str) -> list[str]:
        metric = metric_spec("DPE", indicator_code, metric_key)
        dimensions = metric.get("dimensions")
        if isinstance(dimensions, list):
            return [str(item) for item in dimensions]
        return []

    def _fact(
        self,
        indicator_code: str,
        metric_key: str,
        value: float | int | None,
        *,
        dimensions: dict[str, str] | None = None,
        source: str,
        available: bool | None = None,
        note: str | None = None,
    ) -> MetricFact:
        spec = indicator_spec("DPE", indicator_code)
        clean_dimensions, dimension_key, dimension_label = canonical_dimensions(spec, dimensions or {})
        return MetricFact(
            indicator_code=indicator_code,
            metric_key=metric_key,
            value=value,
            dimensions=clean_dimensions,
            dimension_key=dimension_key,
            dimension_label=dimension_label,
            source=source,
            available=(value is not None) if available is None else bool(available),
            note=note,
        )

    def _course_directorates(self) -> dict[int, str]:
        rows = self.db.execute(
            select(Course.id, Directorate.code)
            .join(Directorate, Directorate.id == Course.directorate_id)
        ).all()
        return {int(course_id): str(code) for course_id, code in rows}

    def _facts(self, period_id: int | None = None) -> tuple[dict[str, Any], list[MetricFact]]:
        analytics = DPECostAnalyticsRepository(self.db, self.scope).dashboard(period_id=period_id, window_months=12)
        selected = analytics.get("selected_period")
        if not selected:
            return analytics, []
        selected_id = int(selected["id"])
        cards = analytics.get("cards") or {}
        waterfall = analytics.get("waterfall") or {}
        expenses = DPECostExpenseRepository(self.db, self.scope).expense_summary(period_id=selected_id)
        teaching = DPECostTeachingRepository(self.db, self.scope).central_payload(period_id=selected_id)
        closure = DPECostClosureRepository(self.db, self.scope).central_payload(period_id=selected_id)
        official = closure.get("official_run") or {}
        teaching_summary = teaching.get("summary") or {}
        course_directorates = self._course_directorates()

        total_revenue = self._number(cards.get("total_revenue", {}).get("value"))
        institutional_revenue = self._number(cards.get("institutional_revenue", {}).get("value"))
        total_expense = self._number(cards.get("expense_total", {}).get("value"))
        institutional_result = self._number(cards.get("economic_result", {}).get("value"))
        institutional_margin = self._number(cards.get("operating_margin_percent", {}).get("value"))
        coverage_index = None
        if total_revenue is not None and total_expense not in (None, 0):
            coverage_index = total_revenue / total_expense

        allocatable = self._number(expenses.get("allocatable_amount"))
        institutional_expense = self._number(expenses.get("institutional_amount"))
        allocated = self._number(official.get("allocated_total")) if official else None
        unallocated = self._number(official.get("unallocated_total")) if official else None
        reconciliation = None
        if official and bool(official.get("current")):
            base = self._number(official.get("expense_total")) or 0.0
            if base == 0:
                reconciliation = 100.0
            elif allocated is not None:
                reconciliation = max(0.0, min(100.0, allocated / base * 100.0))

        teacher_count = int(teaching_summary.get("period_teacher_count") or 0)
        workload = self._number(teaching_summary.get("total_workload_hours"))
        avg_workload = (workload / teacher_count) if workload is not None and teacher_count > 0 else None
        teaching_cost = self._number(waterfall.get("teaching_cost"))

        facts: list[MetricFact] = [
            self._fact("DPE-RESULT", "institutional_result", institutional_result, source="analytics"),
            self._fact("DPE-RESULT", "institutional_margin_pct", institutional_margin, source="analytics"),
            self._fact("DPE-RESULT", "coverage_index", coverage_index, source="analytics"),
            self._fact("DPE-REVENUE", "total_revenue", total_revenue, source="revenue_ledger"),
            self._fact("DPE-REVENUE", "institutional_revenue", institutional_revenue, source="revenue_ledger"),
            self._fact("DPE-EXPENSE", "total_expense", total_expense, source="expense_ledger"),
            self._fact("DPE-EXPENSE", "institutional_expense", institutional_expense, source="expense_ledger"),
            self._fact("DPE-EXPENSE", "allocatable_expense", allocatable, source="expense_ledger"),
            self._fact("DPE-TEACHING", "teaching_cost", teaching_cost, source="allocation_waterfall"),
            self._fact("DPE-TEACHING", "total_workload_hours", workload, source="teaching_activities"),
            self._fact("DPE-TEACHING", "avg_workload_hours_per_teacher", avg_workload, source="teaching_activities"),
            self._fact("DPE-TEACHING", "teacher_count", teacher_count, source="teaching_activities"),
            self._fact(
                "DPE-ALLOCATION", "allocated_expense", allocated,
                source="official_allocation_run", available=bool(official and official.get("current")),
                note=None if official and official.get("current") else "Não há cálculo oficial atual para a competência.",
            ),
            self._fact(
                "DPE-ALLOCATION", "unallocated_expense", unallocated,
                source="official_allocation_run", available=bool(official and official.get("current")),
                note=None if official and official.get("current") else "Não há cálculo oficial atual para a competência.",
            ),
            self._fact(
                "DPE-ALLOCATION", "reconciliation_pct", reconciliation,
                source="official_allocation_run", available=reconciliation is not None,
                note=None if reconciliation is not None else "A conciliação depende de um cálculo oficial atual.",
            ),
        ]

        for course in analytics.get("courses") or []:
            name = str(course.get("course") or "").strip()
            if not name:
                continue
            course_id = course.get("course_id")
            directorate = course_directorates.get(int(course_id)) if course_id else None
            dimensions = {"course": name}
            if directorate:
                dimensions["academic_directorate"] = directorate
            facts.extend([
                self._fact("DPE-RESULT", "course_result", self._number(course.get("economic_result")), dimensions=dimensions, source="analytics"),
                self._fact("DPE-RESULT", "course_margin_pct", self._number(course.get("margin_percent")), dimensions=dimensions, source="analytics"),
                self._fact("DPE-REVENUE", "course_revenue", self._number(course.get("revenue")), dimensions=dimensions, source="revenue_ledger"),
                self._fact("DPE-REVENUE", "revenue_per_student", self._number(course.get("revenue_per_active_student")), dimensions=dimensions, source="analytics"),
                self._fact("DPE-EXPENSE", "course_total_cost", self._number(course.get("allocated_cost")), dimensions=dimensions, source="official_allocation_run"),
                self._fact("DPE-TEACHING", "teaching_cost", self._number(course.get("teaching_cost")), dimensions=dimensions, source="official_allocation_run"),
            ])
            # Compatibility for targets created with only the course dimension.
            course_only = {"course": name}
            if dimensions != course_only:
                facts.extend([
                    self._fact("DPE-RESULT", "course_result", self._number(course.get("economic_result")), dimensions=course_only, source="analytics"),
                    self._fact("DPE-RESULT", "course_margin_pct", self._number(course.get("margin_percent")), dimensions=course_only, source="analytics"),
                    self._fact("DPE-REVENUE", "course_revenue", self._number(course.get("revenue")), dimensions=course_only, source="revenue_ledger"),
                    self._fact("DPE-REVENUE", "revenue_per_student", self._number(course.get("revenue_per_active_student")), dimensions=course_only, source="analytics"),
                    self._fact("DPE-EXPENSE", "course_total_cost", self._number(course.get("allocated_cost")), dimensions=course_only, source="official_allocation_run"),
                    self._fact("DPE-TEACHING", "teaching_cost", self._number(course.get("teaching_cost")), dimensions=course_only, source="official_allocation_run"),
                ])
        return analytics, facts

    @staticmethod
    def _target_active(target: dict[str, Any], period: str) -> bool:
        if period_sort_key(target["valid_from"]) > period_sort_key(period):
            return False
        valid_to = target.get("valid_to")
        return not valid_to or period_sort_key(valid_to) >= period_sort_key(period)

    @staticmethod
    def _evaluate(metric: dict[str, Any], target: dict[str, Any], value: float | int | None) -> dict[str, str]:
        if value is None:
            return {"key": "UNAVAILABLE", "label": "Sem apuração"}
        direction = str(metric.get("direction") or "context").lower()
        current = float(value)
        if direction == "range":
            low, high = target.get("target_min"), target.get("target_max")
            if low is None or high is None:
                return {"key": "UNAVAILABLE", "label": "Meta incompleta"}
            if float(low) <= current <= float(high):
                return {"key": "GOOD", "label": "Dentro da meta"}
            att_low, att_high = target.get("attention_min"), target.get("attention_max")
            if att_low is not None and att_high is not None and float(att_low) <= current <= float(att_high):
                return {"key": "ATTENTION", "label": "Atenção"}
            return {"key": "BAD", "label": "Fora da meta"}
        goal = target.get("target")
        if goal is None:
            return {"key": "UNAVAILABLE", "label": "Meta incompleta"}
        attention = target.get("attention")
        if direction == "lower":
            if current <= float(goal):
                return {"key": "GOOD", "label": "Dentro da meta"}
            if attention is not None and current <= float(attention):
                return {"key": "ATTENTION", "label": "Atenção"}
            return {"key": "BAD", "label": "Fora da meta"}
        if direction == "higher":
            if current >= float(goal):
                return {"key": "GOOD", "label": "Dentro da meta"}
            if attention is not None and current >= float(attention):
                return {"key": "ATTENTION", "label": "Atenção"}
            return {"key": "BAD", "label": "Fora da meta"}
        return {"key": "INFO", "label": "Acompanhamento"}

    def overview(self, *, period_id: int | None = None) -> dict[str, Any]:
        analytics, facts = self._facts(period_id=period_id)
        selected = analytics.get("selected_period")
        period = str((selected or {}).get("period") or "")
        fact_map = {(f.indicator_code, f.metric_key, f.dimension_key): f for f in facts}

        all_targets = [
            row for row in self.management.list_targets()
            if row.get("indicator_code") in CANONICAL_CODES
        ]
        evaluated_targets: list[dict[str, Any]] = []
        summary = {"active": 0, "good": 0, "attention": 0, "bad": 0, "unavailable": 0}
        for target in all_targets:
            code = str(target["indicator_code"])
            key = str(target["metric_key"])
            metric = metric_spec("DPE", code, key)
            historical_metric = bool(metric.get("legacy_metric"))
            active = bool(period and self._target_active(target, period) and not historical_metric)
            fact = fact_map.get((code, key, str(target.get("dimension_key") or "TOTAL"))) if active else None
            if historical_metric:
                status = {"key": "HISTORICAL", "label": "Meta histórica"}
            else:
                status = self._evaluate(metric, target, fact.value if fact and fact.available else None) if active else {"key": "INACTIVE", "label": "Fora da vigência"}
            row = {
                **target,
                "indicator_label": indicator_spec("DPE", code).get("short_name") or code,
                "metric_label": metric.get("label") or key,
                "unit": metric.get("unit"),
                "direction": metric.get("direction"),
                "active_for_period": active,
                "historical_metric": historical_metric,
                "current_value": fact.value if fact and fact.available else None,
                "fact": fact.as_dict() if fact else None,
                "status": status,
            }
            evaluated_targets.append(row)
            if active:
                summary["active"] += 1
                bucket = {"GOOD": "good", "ATTENTION": "attention", "BAD": "bad"}.get(status["key"], "unavailable")
                summary[bucket] += 1

        all_actions = [
            row for row in self.management.list_actions()
            if row.get("indicator_code") in CANONICAL_CODES
        ]
        today = date.today()
        action_rows: list[dict[str, Any]] = []
        action_summary = {"open": 0, "in_progress": 0, "overdue": 0, "completed": 0, "cancelled": 0}
        for action in all_actions:
            stored = str(action.get("status") or "Aberto").strip()
            normalized = stored.upper()
            due = None
            try:
                due = date.fromisoformat(str(action.get("due_date") or ""))
            except ValueError:
                due = None
            is_final = normalized in FINAL_ACTION_STATUSES
            is_overdue = bool(due and due < today and not is_final)
            effective_status = "Atrasado" if is_overdue else stored
            if normalized in {"CONCLUÍDO", "CONCLUIDO"}:
                action_summary["completed"] += 1
            elif normalized == "CANCELADO":
                action_summary["cancelled"] += 1
            elif is_overdue:
                action_summary["overdue"] += 1
            elif normalized == "EM ANDAMENTO":
                action_summary["in_progress"] += 1
            else:
                action_summary["open"] += 1
            metric = metric_spec("DPE", action["indicator_code"], action["metric_key"]) if action.get("metric_key") else None
            action_rows.append({
                **action,
                "indicator_label": indicator_spec("DPE", action["indicator_code"]).get("short_name") or action["indicator_code"],
                "metric_label": (metric or {}).get("label") if metric else None,
                "effective_status": effective_status,
                "is_overdue": is_overdue,
            })

        return {
            "selected_period": selected,
            "targets": sorted(evaluated_targets, key=lambda row: (not row["active_for_period"], row["indicator_label"], row["metric_label"], row.get("dimension_label") or "")),
            "target_summary": summary,
            "actions": action_rows,
            "action_summary": action_summary,
            "facts": [fact.as_dict() for fact in facts],
            "source_of_truth": "DPE Cost Engine / revenue ledger / expense ledger / official allocation run",
            "manual_measurements_required": False,
        }
