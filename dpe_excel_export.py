from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dpe_cost_allocation import DPECostAllocationRepository
from dpe_cost_analytics import DPECostAnalyticsRepository
from dpe_cost_closure import DPECostClosureRepository
from dpe_cost_expenses import DPECostExpenseRepository
from dpe_cost_teaching import DPECostTeachingRepository
from dpe_cost_v2 import DPEV2OverviewRepository
from dpe_management import DPEManagementRepository
from dpe_revenues import DPERevenueRepository
from models import DPECostPeriod, DPECostPeriodOffering, DPERevenueEntry
from dpe_course_context import snapshot_context_label
from security import DirectorateScope


def _iso(value):
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


class DPEExcelExportRepository:
    """Compose one export payload from the same repositories used by the DPE UI."""

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A exportação pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    def _period_id(self, period_id: int | None = None, reference: str | None = None) -> int | None:
        if period_id:
            return int(period_id)
        if reference:
            row = self.db.scalar(
                select(DPECostPeriod).where(
                    DPECostPeriod.directorate_id == self.scope.directorate_id,
                    DPECostPeriod.period == str(reference).strip(),
                )
            )
            if row:
                return int(row.id)
        latest = self.db.scalar(
            select(DPECostPeriod)
            .where(DPECostPeriod.directorate_id == self.scope.directorate_id)
            .order_by(DPECostPeriod.period.desc())
        )
        return int(latest.id) if latest else None

    def _revenue_entries(self, period_id: int) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(DPERevenueEntry).where(
                DPERevenueEntry.directorate_id == self.scope.directorate_id,
                DPERevenueEntry.period_id == int(period_id),
            ).order_by(DPERevenueEntry.id)
        ).all()
        offering_rows = self.db.scalars(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            )
        ).all()
        offering_map = {row.id: row for row in offering_rows}
        result: list[dict[str, Any]] = []
        for row in rows:
            category = row.category
            period_offering = offering_map.get(row.period_offering_id) if row.period_offering_id is not None else None
            snapshot = dict(period_offering.offering_snapshot_json or {}) if period_offering else {}
            product = dict(snapshot.get("product") or {})
            result.append({
                "id": row.id,
                "period_id": row.period_id,
                "period_offering_id": row.period_offering_id,
                "offering_label": snapshot_context_label(snapshot) if period_offering else None,
                "course_name": product.get("name") if period_offering else None,
                "category_id": row.category_id,
                "category_code": category.code if category else None,
                "category_name": category.name if category else None,
                "category_scope": category.scope if category else None,
                "description": row.description,
                "amount": float(row.amount),
                "source_type": row.source_type,
                "source_reference": row.source_reference,
                "notes": row.notes,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            })
        return result

    def payload(self, *, period_id: int | None = None, reference: str | None = None) -> dict[str, Any]:
        selected_id = self._period_id(period_id, reference)
        if selected_id is None:
            return {"selected_period": None, "revenues": {}, "revenue_entries": [], "expenses": {}, "teaching": {}, "allocation": {}, "analytics": {}, "management": {}, "closure": {}, "overview": {}}

        closure = DPECostClosureRepository(self.db, self.scope).central_payload(period_id=selected_id)
        selected = closure.get("selected_period")
        if not selected:
            raise LookupError("Competência não encontrada para exportação.")
        return {
            "selected_period": selected,
            "revenues": DPERevenueRepository(self.db, self.scope).central(selected_id),
            "revenue_entries": self._revenue_entries(selected_id),
            "expenses": DPECostExpenseRepository(self.db, self.scope).central_payload(period_id=selected_id),
            "teaching": DPECostTeachingRepository(self.db, self.scope).central_payload(period_id=selected_id),
            "allocation": DPECostAllocationRepository(self.db, self.scope).central_payload(period_id=selected_id),
            "analytics": DPECostAnalyticsRepository(self.db, self.scope).dashboard(period_id=selected_id, window_months=12),
            "management": DPEManagementRepository(self.db, self.scope).overview(period_id=selected_id),
            "closure": closure,
            "overview": DPEV2OverviewRepository(self.db, self.scope).overview(period_id=selected_id),
        }
