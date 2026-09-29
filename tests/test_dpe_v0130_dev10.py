from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import release_info
from database import Base
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_revenue_facts import revenue_facts
from dpe_revenues import DPERevenueRepository
from models import Directorate, DPECostOfferingEconomics, DPECostPeriod, DPECostPeriodOffering
from security import AuthorizationContext, DirectorateScope

ROOT = Path(__file__).resolve().parents[1]


def _context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    directorate = Directorate(code="DPE", name="DPE", active=True)
    db.add(directorate)
    db.commit()
    db.refresh(directorate)
    user = AuthorizationContext(
        user_id="dev10",
        email="dev10@test.local",
        full_name="Dev10",
        role="editor",
        directorate_id=directorate.id,
        directorate_code="DPE",
        directorate_name="DPE",
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code="DPE",
        directorate_name="DPE",
        can_write=True,
        is_home=True,
    )
    period = DPECostPeriod(
        directorate_id=directorate.id,
        period="2026-09",
        status="REVIEW",
        created_by="test",
    )
    db.add(period)
    db.flush()
    offering = DPECostPeriodOffering(
        period_id=period.id,
        offering_id=1,
        included=True,
        offering_snapshot_json={
            "product": {"name": "Administração"},
            "offering": {"is_default_context": True},
        },
        created_by="test",
    )
    db.add(offering)
    db.commit()
    db.refresh(period)
    db.refresh(offering)
    return engine, db, directorate, scope, period, offering


def test_release_preserves_dev10_consolidated_results_contract():
    assert release_info.APP_VERSION.startswith("0.13.0")
    if release_info.APP_VERSION != "0.13.0":
        assert int(release_info.APP_VERSION.rsplit(".", 1)[-1]) >= 10
    assert release_info.SCHEMA_VERSION >= 48


def test_economics_model_no_longer_maps_legacy_revenue_columns():
    columns = set(DPECostOfferingEconomics.__table__.columns.keys())
    for legacy in (
        "paying_students",
        "gross_revenue",
        "scholarships_discounts",
        "other_deductions",
        "net_revenue",
        "revenue_type",
    ):
        assert legacy not in columns
    assert "active_students" in columns


def test_explicit_zero_course_revenue_is_confirmed_not_missing():
    engine, db, directorate, scope, period, offering = _context()
    try:
        repo = DPERevenueRepository(db, scope)
        repo.bulk_courses(period.id, [{"period_offering_id": offering.id, "amount": 0}])
        facts = revenue_facts(db, directorate.id, period.id)
        assert facts.is_confirmed(offering.id)
        assert float(facts.base(offering.id)) == 0.0
        assert float(facts.total_revenue) == 0.0
    finally:
        db.close()
        engine.dispose()


def test_revenue_change_changes_allocation_fingerprint():
    engine, db, directorate, scope, period, offering = _context()
    try:
        revenues = DPERevenueRepository(db, scope)
        allocation = DPECostAllocationRepository(db, scope)
        revenues.bulk_courses(period.id, [{"period_offering_id": offering.id, "amount": 10000}])
        first = allocation._input_fingerprint(period.id)
        revenues.bulk_courses(period.id, [{"period_offering_id": offering.id, "amount": 12000}])
        second = allocation._input_fingerprint(period.id)
        assert first != second
    finally:
        db.close()
        engine.dispose()


def test_modern_dpe_consumers_do_not_read_legacy_revenue_fields():
    files = [
        "dpe_cost_analytics.py",
        "dpe_cost_allocation.py",
        "dpe_cost_closure.py",
        "dpe_cost_productivity.py",
        "dpe_cost_v2.py",
        "static/js/dpe_cost_analytics.js",
        "static/js/dpe_cost_allocation.js",
        "static/js/dpe_cost_productivity.js",
        "static/js/dpe_v2.js",
    ]
    legacy = ("paying_students", "gross_revenue", "scholarships_discounts", "other_deductions", "net_revenue", "net_ticket")
    for relative in files:
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        for token in legacy:
            assert token not in text, f"{relative} ainda referencia {token}"


def test_current_dpe_ui_no_longer_describes_net_revenue_or_paying_students():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8").lower()
    js = (ROOT / "static" / "js" / "dpe_v2.js").read_text(encoding="utf-8").lower()
    current = html.split('id="section-dashboard"', 1)[1]
    assert "receita líquida" not in current
    assert "alunos pagantes" not in current
    assert "ticket médio" not in js
