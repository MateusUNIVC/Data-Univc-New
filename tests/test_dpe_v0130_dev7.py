from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

import release_info
from database import Base
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_cost_expenses import DPECostExpenseRepository
from models import (
    Directorate,
    DPEAllocationRule,
    DPECostExpense,
    DPECostExpenseAllocationTarget,
    DPECostPeriod,
    DPECostPeriodOffering,
    DPEExpenseCategory,
)
from schema_version import migrate_local_dpe_expense_scope
from security import AuthorizationContext, DirectorateScope

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    dpe = Directorate(code="DPE", name="DPE", active=True)
    db.add(dpe); db.commit(); db.refresh(dpe)
    user = AuthorizationContext(
        user_id="dev7", email="dev7@test.local", full_name="Dev7",
        role="editor", directorate_id=dpe.id, directorate_code="DPE",
        directorate_name="DPE",
    )
    scope = DirectorateScope(
        user=user, directorate_id=dpe.id, directorate_code="DPE",
        directorate_name="DPE", can_write=True, is_home=True,
    )
    period = DPECostPeriod(directorate_id=dpe.id, period="2026-09", status="REVIEW", created_by="test")
    direct = DPEAllocationRule(directorate_id=dpe.id, code="DIRECT", name="Direto", driver_type="DIRECT", system_defined=True, active=True)
    equal = DPEAllocationRule(directorate_id=dpe.id, code="EQUAL", name="Igualitário", driver_type="EQUAL", system_defined=True, active=True)
    db.add_all([period, direct, equal]); db.flush()
    category = DPEExpenseCategory(directorate_id=dpe.id, code="GERAL", name="Geral", default_rule_id=equal.id, active=True)
    direct_category = DPEExpenseCategory(directorate_id=dpe.id, code="LEGACY_DIRECT", name="Direta antiga", default_rule_id=direct.id, active=True)
    offering = DPECostPeriodOffering(
        period_id=period.id, offering_id=1, included=True,
        offering_snapshot_json={"product": {"name": "Administração"}, "offering": {"shift": "Noturno"}},
        created_by="test",
    )
    db.add_all([category, direct_category, offering]); db.commit()
    for row in (period, direct, equal, category, direct_category, offering): db.refresh(row)
    return engine, db, period, offering, category, direct_category, scope


def test_expense_scope_migration_47_remains_in_release_history():
    assert release_info.SCHEMA_VERSION >= 47
    migration = "047_dpe_expense_scope_v0130.sql"
    sql = (ROOT / "database" / migration).read_text(encoding="utf-8").lower()
    assert "expense_scope" in sql
    assert "'direct','shared','institutional'" in sql.replace(" ", "")
    assert "driver_type = 'direct'" in sql


def test_direct_expense_owns_one_course_and_institutional_has_no_targets():
    engine, db, period, offering, category, _direct_category, scope = _fixture()
    try:
        repo = DPECostExpenseRepository(db, scope)
        direct = repo.create_expense({
            "period_id": period.id, "description": "Laboratório", "amount": "1000",
            "category_id": category.id, "expense_scope": "DIRECT",
            "direct_period_offering_id": offering.id,
        })
        assert direct["expense_scope"] == "DIRECT"
        assert direct["direct_period_offering_id"] == offering.id
        assert direct["direct_destination_label"]
        assert db.scalar(select(DPECostExpenseAllocationTarget).where(DPECostExpenseAllocationTarget.expense_id == direct["id"])) is not None

        institutional = repo.create_expense({
            "period_id": period.id, "description": "Campanha institucional", "amount": "500",
            "category_id": category.id, "expense_scope": "INSTITUTIONAL",
        })
        assert institutional["expense_scope"] == "INSTITUTIONAL"
        assert institutional["allocation_rule_id"] is None
        assert db.scalar(select(DPECostExpenseAllocationTarget).where(DPECostExpenseAllocationTarget.expense_id == institutional["id"])) is None
    finally:
        db.close(); engine.dispose()


def test_shared_expense_does_not_silently_inherit_legacy_direct_rule():
    engine, db, period, _offering, _category, direct_category, scope = _fixture()
    try:
        repo = DPECostExpenseRepository(db, scope)
        row = repo.create_expense({
            "period_id": period.id, "description": "Compartilhada", "amount": "900",
            "category_id": direct_category.id, "expense_scope": "SHARED",
        })
        assert row["expense_scope"] == "SHARED"
        assert row["allocation_rule_id"] is None
    finally:
        db.close(); engine.dispose()


def test_allocation_excludes_institutional_expense_from_reconciliation():
    engine, db, period, offering, category, _direct_category, scope = _fixture()
    try:
        expense_repo = DPECostExpenseRepository(db, scope)
        allocation = DPECostAllocationRepository(db, scope)
        direct = expense_repo.create_expense({
            "period_id": period.id, "description": "Direta", "amount": "100",
            "category_id": category.id, "expense_scope": "DIRECT", "direct_period_offering_id": offering.id,
        })
        expense_repo.create_expense({
            "period_id": period.id, "description": "Institucional", "amount": "300",
            "category_id": category.id, "expense_scope": "INSTITUTIONAL",
        })
        run = allocation.calculate(period.id)
        assert run["expense_total"] == 100.0
        assert run["allocated_total"] == 100.0
        assert run["unallocated_total"] == 0.0
        assert not [i for i in run["issues"] if i["severity"] == "BLOCKER"]
        assert direct["expense_scope"] == "DIRECT"
    finally:
        db.close(); engine.dispose()


def test_bulk_can_move_expenses_to_institutional_but_not_direct_without_destination():
    engine, db, period, offering, category, _direct_category, scope = _fixture()
    try:
        repo = DPECostExpenseRepository(db, scope)
        row = repo.create_expense({
            "period_id": period.id, "description": "Direta", "amount": "100",
            "category_id": category.id, "expense_scope": "DIRECT", "direct_period_offering_id": offering.id,
        })
        repo.bulk_classify(period.id, {"expense_ids": [row["id"]], "expense_scope": "INSTITUTIONAL"})
        refreshed = repo.list_expenses(period_id=period.id)[0]
        assert refreshed["expense_scope"] == "INSTITUTIONAL"
        assert refreshed["direct_period_offering_id"] is None
    finally:
        db.close(); engine.dispose()


def test_local_migration_backfills_legacy_direct_rule():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE dpe_allocation_rules (id INTEGER PRIMARY KEY, driver_type TEXT)"))
        conn.execute(text("CREATE TABLE dpe_cost_expenses (id INTEGER PRIMARY KEY, directorate_id INTEGER, period_id INTEGER, allocation_rule_id INTEGER, status TEXT)"))
        conn.execute(text("INSERT INTO dpe_allocation_rules VALUES (1,'DIRECT'),(2,'EQUAL')"))
        conn.execute(text("INSERT INTO dpe_cost_expenses VALUES (10,1,1,1,'ACTIVE'),(11,1,1,2,'ACTIVE')"))
        migrate_local_dpe_expense_scope(conn)
        rows = conn.execute(text("SELECT id,expense_scope FROM dpe_cost_expenses ORDER BY id")).all()
        assert rows == [(10, "DIRECT"), (11, "SHARED")]
    engine.dispose()


def test_frontend_exposes_three_treatments_and_disables_empty_visible_selection():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "dpe_cost_expenses.js").read_text(encoding="utf-8")
    assert "Diretas" in html and "Compartilhadas" in html and "Institucionais" in html
    assert "Como esta despesa entra no resultado?" in js
    assert "Não distribui aos cursos" in js
    assert "selectAll.disabled=!visible.length" in js
    assert "Competência protegida" in js
