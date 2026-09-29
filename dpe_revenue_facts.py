from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import DPERevenueCategory, DPERevenueEntry

CENT = Decimal("0.01")


def _money(value: Decimal | int | float | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


@dataclass(frozen=True)
class RevenueFacts:
    """Canonical revenue facts for one DPE competence.

    The revenue ledger is the single source of truth. A course/context is
    considered *confirmed* when a COURSE_REVENUE entry exists, including an
    explicit zero-value entry. Other attributed revenue is included in the
    economic result but does not replace that confirmation step.
    """

    attributed_by_offering: dict[int, Decimal]
    base_by_offering: dict[int, Decimal]
    confirmed_offering_ids: frozenset[int]
    institutional_total: Decimal
    attributed_total: Decimal
    total_revenue: Decimal

    def attributed(self, period_offering_id: int) -> Decimal:
        return self.attributed_by_offering.get(int(period_offering_id), Decimal("0.00"))

    def base(self, period_offering_id: int) -> Decimal:
        return self.base_by_offering.get(int(period_offering_id), Decimal("0.00"))

    def is_confirmed(self, period_offering_id: int) -> bool:
        return int(period_offering_id) in self.confirmed_offering_ids


def revenue_facts(db: Session, directorate_id: int, period_id: int) -> RevenueFacts:
    rows = db.execute(
        select(
            DPERevenueEntry.period_offering_id,
            DPERevenueCategory.code,
            func.coalesce(func.sum(DPERevenueEntry.amount), 0),
        )
        .join(DPERevenueCategory, DPERevenueCategory.id == DPERevenueEntry.category_id)
        .where(
            DPERevenueEntry.directorate_id == int(directorate_id),
            DPERevenueEntry.period_id == int(period_id),
        )
        .group_by(DPERevenueEntry.period_offering_id, DPERevenueCategory.code)
    ).all()

    attributed: dict[int, Decimal] = {}
    base: dict[int, Decimal] = {}
    confirmed: set[int] = set()
    institutional = Decimal("0.00")

    for period_offering_id, category_code, value in rows:
        amount = _money(value)
        if period_offering_id is None:
            institutional += amount
            continue
        oid = int(period_offering_id)
        attributed[oid] = (attributed.get(oid, Decimal("0.00")) + amount).quantize(CENT)
        if str(category_code or "").upper() == "COURSE_REVENUE":
            base[oid] = (base.get(oid, Decimal("0.00")) + amount).quantize(CENT)
            confirmed.add(oid)

    attributed_total = sum(attributed.values(), Decimal("0.00")).quantize(CENT)
    institutional = institutional.quantize(CENT)
    return RevenueFacts(
        attributed_by_offering=attributed,
        base_by_offering=base,
        confirmed_offering_ids=frozenset(confirmed),
        institutional_total=institutional,
        attributed_total=attributed_total,
        total_revenue=(attributed_total + institutional).quantize(CENT),
    )
