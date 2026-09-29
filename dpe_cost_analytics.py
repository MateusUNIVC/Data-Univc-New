from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    DPECostAllocationResult,
    DPECostAllocationRun,
    DPECostExpense,
    DPECostOfferingEconomics,
    DPECostPeriod,
    DPECostPeriodOffering,
)
from security import DirectorateScope
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_revenue_facts import revenue_facts

CENT = Decimal("0.01")


def _money(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(CENT))


def _pct(numerator: Decimal | float | int | None, denominator: Decimal | float | int | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    den = Decimal(str(denominator))
    if den == 0:
        return None
    return float((Decimal(str(numerator)) / den * 100).quantize(Decimal("0.01")))


def _product(snapshot: dict[str, Any]) -> tuple[str, str, int | None]:
    product = dict((snapshot or {}).get("product") or {})
    name = str(product.get("name") or "Curso sem identificação")
    source_id = product.get("source_course_id")
    key = f"course:{source_id}" if source_id else f"name:{name.casefold()}"
    try:
        source_int = int(source_id) if source_id is not None else None
    except (TypeError, ValueError):
        source_int = None
    return key, name, source_int


def _expense_dimension(expense: DPECostExpense, key: str) -> str:
    snapshot = dict(expense.classification_snapshot_json or {})
    value = dict(snapshot.get(key) or {})
    name = str(value.get("name") or "").strip()
    return name or ("Sem setor" if key == "cost_center" else "Sem categoria")


def _driver_from_expense(expense: DPECostExpense) -> str | None:
    snapshot = dict(expense.classification_snapshot_json or {})
    rule = dict(snapshot.get("allocation_rule") or {})
    value = str(rule.get("driver_type") or "").strip().upper()
    return value or None


class DPECostAnalyticsRepository:
    """Read-only analytics over the canonical DPE monthly cost engine.

    No aggregate table is introduced here. Every chart is derived from the same
    historical snapshots, official expenses, economics facts and official allocation
    runs used by the operational workflow.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("Os analytics econômicos pertencem exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return int(self.scope.directorate_id)

    def _periods(self) -> list[DPECostPeriod]:
        return self.db.scalars(
            select(DPECostPeriod)
            .where(DPECostPeriod.directorate_id == self.directorate_id)
            .order_by(DPECostPeriod.period.asc())
        ).all()

    def _period(self, period_id: int | None) -> DPECostPeriod | None:
        periods = self._periods()
        if not periods:
            return None
        if period_id is None:
            return periods[-1]
        for row in periods:
            if int(row.id) == int(period_id):
                return row
        raise LookupError("Competência DPE não encontrada.")

    def _window(self, selected: DPECostPeriod, months: int) -> list[DPECostPeriod]:
        eligible = [row for row in self._periods() if row.period <= selected.period]
        return eligible[-max(1, min(int(months or 12), 36)):]

    def _official_run(self, period_id: int) -> DPECostAllocationRun | None:
        return self.db.scalar(
            select(DPECostAllocationRun)
            .where(
                DPECostAllocationRun.directorate_id == self.directorate_id,
                DPECostAllocationRun.period_id == int(period_id),
                DPECostAllocationRun.status == "OFFICIAL",
            )
            .order_by(DPECostAllocationRun.run_number.desc())
            .limit(1)
        )

    def _run_is_current(self, period_id: int, run: DPECostAllocationRun | None) -> bool:
        if not run or run.status != "OFFICIAL" or Decimal(str(run.unallocated_total or 0)) != 0:
            return False
        current = DPECostAllocationRepository(self.db, self.scope)._input_fingerprint(int(period_id))
        return bool(run.input_fingerprint and run.input_fingerprint == current)

    def _offerings(self, period_id: int) -> list[DPECostPeriodOffering]:
        return self.db.scalars(
            select(DPECostPeriodOffering)
            .where(
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            )
            .order_by(DPECostPeriodOffering.id.asc())
        ).all()

    def _economics(self, period_id: int) -> dict[int, DPECostOfferingEconomics]:
        rows = self.db.scalars(
            select(DPECostOfferingEconomics).where(
                DPECostOfferingEconomics.directorate_id == self.directorate_id,
                DPECostOfferingEconomics.period_id == int(period_id),
            )
        ).all()
        return {int(row.period_offering_id): row for row in rows}

    def _expenses(self, period_id: int) -> list[DPECostExpense]:
        return self.db.scalars(
            select(DPECostExpense)
            .where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.status == "ACTIVE",
            )
            .order_by(DPECostExpense.id.asc())
        ).all()

    def _allocation_results(self, run: DPECostAllocationRun | None) -> list[DPECostAllocationResult]:
        if not run:
            return []
        return self.db.scalars(
            select(DPECostAllocationResult)
            .where(DPECostAllocationResult.run_id == run.id)
            .order_by(DPECostAllocationResult.id.asc())
        ).all()

    def _period_metrics(self, period: DPECostPeriod) -> dict[str, Any]:
        offerings = self._offerings(period.id)
        economics = self._economics(period.id)
        expenses = self._expenses(period.id)
        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        revenue_complete = bool(offerings) and all(revenues.is_confirmed(int(offering.id)) for offering in offerings)
        econ_rows = [economics.get(int(offering.id)) for offering in offerings]
        students_complete = bool(offerings) and all(row is not None and row.active_students is not None for row in econ_rows)
        active = sum((int(row.active_students or 0) for row in econ_rows if row), 0)
        expense_total = sum((Decimal(str(row.amount or 0)) for row in expenses), Decimal("0"))
        total_revenue = revenues.total_revenue
        result = total_revenue - expense_total if revenue_complete else None
        run = self._official_run(period.id)
        allocation_ready = self._run_is_current(period.id, run)
        return {
            "period_id": period.id,
            "period": period.period,
            "status": period.status,
            "offering_count": len(offerings),
            "course_revenue": _money(revenues.attributed_total),
            "institutional_revenue": _money(revenues.institutional_total),
            "total_revenue": _money(total_revenue) if revenue_complete else None,
            "expense_total": _money(expense_total),
            "economic_result": _money(result),
            "operating_margin_percent": _pct(result, total_revenue) if result is not None else None,
            "active_students": active if students_complete else None,
            "revenue_per_active_student": _money(total_revenue / active) if revenue_complete and students_complete and active > 0 else None,
            "revenue_complete": revenue_complete,
            "students_complete": students_complete,
            "allocation_ready": allocation_ready,
            "official_run_id": run.id if run else None,
            "official_run_number": run.run_number if run else None,
        }

    @staticmethod
    def _comparison(current: float | int | None, previous: float | int | None) -> dict[str, Any]:
        if current is None or previous is None:
            return {"absolute": None, "percent": None, "direction": "UNKNOWN"}
        current_d = Decimal(str(current))
        previous_d = Decimal(str(previous))
        absolute = current_d - previous_d
        percent = None if previous_d == 0 else absolute / abs(previous_d) * 100
        direction = "FLAT"
        if absolute > 0:
            direction = "UP"
        elif absolute < 0:
            direction = "DOWN"
        return {
            "absolute": _money(absolute),
            "percent": float(percent.quantize(Decimal("0.01"))) if percent is not None else None,
            "direction": direction,
        }

    def _expense_dimension_rows(self, period_id: int, dimension: str) -> list[dict[str, Any]]:
        buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for expense in self._expenses(period_id):
            label = _expense_dimension(expense, "category" if dimension == "category" else "cost_center")
            buckets[label] += Decimal(str(expense.amount or 0))
        return [
            {"key": key, "amount": _money(value)}
            for key, value in sorted(buckets.items(), key=lambda item: (-item[1], item[0]))
        ]

    def _category_comparison(self, current_id: int, previous_id: int | None) -> list[dict[str, Any]]:
        current = {row["key"]: Decimal(str(row["amount"] or 0)) for row in self._expense_dimension_rows(current_id, "category")}
        previous = {} if previous_id is None else {
            row["key"]: Decimal(str(row["amount"] or 0)) for row in self._expense_dimension_rows(previous_id, "category")
        }
        output = []
        for key in sorted(set(current) | set(previous), key=lambda name: (-(current.get(name, Decimal("0"))), name)):
            now = current.get(key, Decimal("0"))
            before = previous.get(key, Decimal("0"))
            output.append({
                "key": key,
                "current": _money(now),
                "previous": _money(before),
                "change": _money(now - before),
                "change_percent": None if before == 0 else float(((now - before) / abs(before) * 100).quantize(Decimal("0.01"))),
            })
        return output

    @staticmethod
    def _component_from_result(result: DPECostAllocationResult) -> str:
        expense = dict(result.expense_snapshot_json or {})
        kind = str(expense.get("expense_kind") or "").upper()
        if kind == "PAYROLL":
            return "teaching"
        driver = str(result.driver_type or "").upper()
        if driver == "DIRECT":
            return "direct"
        return "shared"

    def _courses_for_period(self, period: DPECostPeriod) -> list[dict[str, Any]]:
        offerings = self._offerings(period.id)
        economics = self._economics(period.id)
        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        run = self._official_run(period.id)
        allocation_ready = self._run_is_current(period.id, run)
        results = self._allocation_results(run) if allocation_ready else []

        offering_cost: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        offering_components: dict[int, dict[str, Decimal]] = defaultdict(lambda: {
            "teaching": Decimal("0"), "direct": Decimal("0"), "shared": Decimal("0")
        })
        if allocation_ready:
            for item in results:
                oid = int(item.period_offering_id)
                amount = Decimal(str(item.allocated_amount or 0))
                offering_cost[oid] += amount
                offering_components[oid][self._component_from_result(item)] += amount

        buckets: dict[str, dict[str, Any]] = {}
        for offering in offerings:
            oid = int(offering.id)
            key, name, source_course_id = _product(dict(offering.offering_snapshot_json or {}))
            bucket = buckets.setdefault(key, {
                "course_key": key, "course_id": source_course_id, "course": name,
                "offering_count": 0, "active_students": 0, "revenue": Decimal("0"),
                "allocated_cost": Decimal("0"), "teaching_cost": Decimal("0"),
                "direct_cost": Decimal("0"), "shared_cost": Decimal("0"),
                "revenue_complete": True, "students_complete": True, "cost_complete": allocation_ready,
            })
            bucket["offering_count"] += 1
            eco = economics.get(oid)
            if not eco or eco.active_students is None:
                bucket["students_complete"] = False
            else:
                bucket["active_students"] += int(eco.active_students)
            bucket["revenue"] += revenues.attributed(oid)
            if not revenues.is_confirmed(oid):
                bucket["revenue_complete"] = False
            if allocation_ready:
                bucket["allocated_cost"] += offering_cost[oid]
                bucket["teaching_cost"] += offering_components[oid]["teaching"]
                bucket["direct_cost"] += offering_components[oid]["direct"]
                bucket["shared_cost"] += offering_components[oid]["shared"]

        output = []
        for bucket in buckets.values():
            revenue = bucket["revenue"].quantize(CENT)
            cost = bucket["allocated_cost"].quantize(CENT)
            result = revenue - cost if bucket["revenue_complete"] and bucket["cost_complete"] else None
            active = bucket["active_students"] if bucket["students_complete"] else None
            output.append({
                "course_key": bucket["course_key"],
                "course_id": bucket["course_id"],
                "course": bucket["course"],
                "offering_count": bucket["offering_count"],
                "active_students": active,
                "revenue": _money(revenue) if bucket["revenue_complete"] else None,
                "allocated_cost": _money(cost) if bucket["cost_complete"] else None,
                "economic_result": _money(result),
                "margin_percent": _pct(result, revenue) if result is not None else None,
                "revenue_per_active_student": _money(revenue / active) if bucket["revenue_complete"] and active else None,
                "cost_per_active_student": _money(cost / active) if bucket["cost_complete"] and active else None,
                "teaching_cost": _money(bucket["teaching_cost"]) if bucket["cost_complete"] else None,
                "direct_cost": _money(bucket["direct_cost"]) if bucket["cost_complete"] else None,
                "shared_cost": _money(bucket["shared_cost"]) if bucket["cost_complete"] else None,
                "revenue_complete": bool(bucket["revenue_complete"]),
                "cost_complete": bool(bucket["cost_complete"]),
            })
        return sorted(output, key=lambda row: str(row["course"]))

    def _waterfall(self, period: DPECostPeriod, metrics: dict[str, Any]) -> dict[str, Any]:
        expenses = self._expenses(period.id)
        payroll = Decimal("0")
        direct = Decimal("0")
        shared = Decimal("0")
        institutional = Decimal("0")
        unclassified = Decimal("0")
        for expense in expenses:
            amount = Decimal(str(expense.amount or 0))
            scope = str(expense.expense_scope or "SHARED").upper()
            if scope == "INSTITUTIONAL":
                institutional += amount
                continue
            if str(expense.expense_kind or "").upper() == "PAYROLL":
                payroll += amount
                continue
            driver = _driver_from_expense(expense)
            if scope == "DIRECT" or (scope == "SHARED" and driver == "DIRECT"):
                direct += amount
            elif scope == "SHARED":
                shared += amount
            else:
                unclassified += amount
        revenue = metrics.get("total_revenue")
        result = metrics.get("economic_result")
        return {
            "total_revenue": revenue,
            "course_revenue": metrics.get("course_revenue"),
            "institutional_revenue": metrics.get("institutional_revenue"),
            "teaching_cost": _money(payroll),
            "direct_cost": _money(direct),
            "shared_cost": _money(shared),
            "institutional_cost": _money(institutional),
            "unclassified_cost": _money(unclassified),
            "operating_result": result,
            "reconciled": bool(
                revenue is not None and result is not None
                and abs((Decimal(str(revenue)) - payroll - direct - shared - institutional - unclassified) - Decimal(str(result))) <= CENT
            ),
            "note": (
                "O resultado institucional usa todas as receitas do ledger e todas as despesas oficiais. "
                "Receitas e despesas institucionais permanecem fora da margem dos cursos, salvo quando uma receita é vinculada explicitamente a um curso/contexto."
            ),
        }

    def dashboard(
        self,
        *,
        period_id: int | None = None,
        window_months: int = 12,
        course_key: str | None = None,
    ) -> dict[str, Any]:
        selected = self._period(period_id)
        if not selected:
            return {
                "periods": [], "selected_period": None, "previous_period": None,
                "cards": {}, "trend": [], "expenses_by_category": [], "expenses_by_sector": [],
                "category_comparison": [], "courses": [], "course_history": [], "waterfall": {},
                "course_options": [], "selected_course_key": None,
                "limitations": [],
            }

        all_periods = [row for row in self._periods() if row.period <= selected.period]
        window = self._window(selected, window_months)
        selected_index = next((i for i, row in enumerate(all_periods) if row.id == selected.id), len(all_periods) - 1)
        previous = all_periods[selected_index - 1] if selected_index > 0 else None
        current_metrics = self._period_metrics(selected)
        previous_metrics = self._period_metrics(previous) if previous else None
        trend = [self._period_metrics(row) for row in window]
        courses = self._courses_for_period(selected)
        course_options = [{"key": row["course_key"], "label": row["course"]} for row in courses]
        selected_course_key = course_key if course_key and any(row["key"] == course_key for row in course_options) else None
        if not selected_course_key and course_options:
            selected_course_key = course_options[0]["key"]

        course_history = []
        if selected_course_key:
            for period in window:
                period_course = next((row for row in self._courses_for_period(period) if row["course_key"] == selected_course_key), None)
                if period_course:
                    course_history.append({"period": period.period, **period_course})
                else:
                    course_history.append({
                        "period": period.period,
                        "course_key": selected_course_key,
                        "course": next((row["label"] for row in course_options if row["key"] == selected_course_key), "Curso"),
                        "revenue": None,
                        "allocated_cost": None,
                        "economic_result": None,
                        "margin_percent": None,
                    })

        card_fields = [
            "total_revenue", "course_revenue", "institutional_revenue", "expense_total",
            "economic_result", "operating_margin_percent", "active_students",
        ]
        cards = {}
        for field in card_fields:
            cards[field] = {
                "value": current_metrics.get(field),
                "comparison": self._comparison(
                    current_metrics.get(field),
                    previous_metrics.get(field) if previous_metrics else None,
                ),
            }

        limitations = []
        if not current_metrics.get("revenue_complete"):
            limitations.append("A receita do mês ainda está incompleta; resultado e margem podem ficar indisponíveis.")
        if not current_metrics.get("allocation_ready"):
            limitations.append("Não há Allocation Run oficial totalmente reconciliado para o mês; análises de custo por curso ficam indisponíveis.")
        limitations.append(
            "Overhead administrativo não é separado enquanto não existir classificação contábil explícita; o sistema não infere essa natureza pelo nome."
        )

        return {
            "periods": [{"id": row.id, "period": row.period, "status": row.status} for row in self._periods()],
            "selected_period": {"id": selected.id, "period": selected.period, "status": selected.status},
            "previous_period": None if not previous else {"id": previous.id, "period": previous.period, "status": previous.status},
            "window_months": len(window),
            "cards": cards,
            "trend": trend,
            "expenses_by_category": self._expense_dimension_rows(selected.id, "category"),
            "expenses_by_sector": self._expense_dimension_rows(selected.id, "sector"),
            "category_comparison": self._category_comparison(selected.id, previous.id if previous else None),
            "courses": courses,
            "course_options": course_options,
            "selected_course_key": selected_course_key,
            "course_history": course_history,
            "waterfall": self._waterfall(selected, current_metrics),
            "limitations": limitations,
            "definitions": {
                "operating_result": "Todas as receitas do ledger menos todas as despesas oficiais da competência.",
                "operating_margin": "Resultado institucional dividido pela receita total do ledger.",
                "course_result": "Receita explicitamente atribuída ao curso menos custos atribuídos pelo cálculo oficial.",
                "course_cost_components": "Docentes = folha; Diretos = critério DIRECT; Compartilhados = demais critérios de rateio.",
            },
        }
