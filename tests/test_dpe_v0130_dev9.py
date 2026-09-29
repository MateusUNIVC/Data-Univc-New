from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import release_info
from database import Base
from dpe_cost_allocation import DPECostAllocationRepository, DPECostAllocationValidationError
from dpe_cost_expenses import DPECostExpenseRepository
from models import Directorate, DPEAllocationRule, DPECostPeriod, DPECostPeriodOffering, DPEExpenseCategory
from security import AuthorizationContext, DirectorateScope

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    dpe = Directorate(code="DPE", name="DPE", active=True)
    db.add(dpe); db.commit(); db.refresh(dpe)
    user = AuthorizationContext(
        user_id="dev9", email="dev9@test.local", full_name="Dev9", role="editor",
        directorate_id=dpe.id, directorate_code="DPE", directorate_name="DPE",
    )
    scope = DirectorateScope(
        user=user, directorate_id=dpe.id, directorate_code="DPE", directorate_name="DPE",
        can_write=True, is_home=True,
    )
    period = DPECostPeriod(directorate_id=dpe.id, period="2026-09", status="REVIEW", created_by="test")
    direct = DPEAllocationRule(directorate_id=dpe.id, code="DIRECT", name="Direto", driver_type="DIRECT", system_defined=True, active=True)
    equal = DPEAllocationRule(directorate_id=dpe.id, code="EQUAL", name="Igual", driver_type="EQUAL", system_defined=True, active=True)
    db.add_all([period, direct, equal]); db.flush()
    category = DPEExpenseCategory(directorate_id=dpe.id, code="GERAL", name="Geral", default_rule_id=equal.id, active=True)
    offering = DPECostPeriodOffering(
        period_id=period.id, offering_id=1, included=True,
        offering_snapshot_json={"product": {"name": "Administração"}, "offering": {"shift": "Noturno"}},
        created_by="test",
    )
    db.add_all([category, offering]); db.commit()
    for row in (period, direct, equal, category, offering): db.refresh(row)
    return engine, db, scope, period, direct, equal, category, offering


def test_release_dev9_keeps_schema_48_without_fake_migration():
    assert release_info.APP_VERSION.startswith("0.13.0")
    assert release_info.SCHEMA_VERSION == 48
    assert release_info.SCHEMA_MIGRATION == "048_dpe_teacher_profiles_v0130.sql"


def test_shared_expense_cannot_use_direct_as_legacy_shortcut_anymore():
    engine, db, scope, period, direct, _equal, category, offering = _fixture()
    try:
        expenses = DPECostExpenseRepository(db, scope)
        allocation = DPECostAllocationRepository(db, scope)
        row = expenses.create_expense({
            "period_id": period.id, "description": "Energia", "amount": "1000",
            "category_id": category.id, "expense_scope": "SHARED",
        })
        with pytest.raises(DPECostAllocationValidationError, match="compartilhada não pode usar distribuição direta"):
            allocation.set_expense_config(row["id"], {
                "allocation_rule_id": direct.id,
                "targets": [{"period_offering_id": offering.id}],
            })
    finally:
        db.close(); engine.dispose()


def test_direct_expense_keeps_single_destination_and_direct_rule():
    engine, db, scope, period, direct, _equal, category, offering = _fixture()
    try:
        expenses = DPECostExpenseRepository(db, scope)
        allocation = DPECostAllocationRepository(db, scope)
        row = expenses.create_expense({
            "period_id": period.id, "description": "Laboratório exclusivo", "amount": "850",
            "category_id": category.id, "expense_scope": "DIRECT",
            "direct_period_offering_id": offering.id,
        })
        config = allocation.expense_config(row["id"])
        assert config["expense_scope"] == "DIRECT"
        assert config["rule"]["driver_type"] == "DIRECT"
        assert len(config["targets"]) == 1
        saved = allocation.set_expense_config(row["id"], {
            "allocation_rule_id": direct.id,
            "targets": [{"period_offering_id": offering.id}],
        })
        assert saved["rule"]["driver_type"] == "DIRECT"
        assert len(saved["targets"]) == 1
    finally:
        db.close(); engine.dispose()


def test_allocation_frontend_is_decision_oriented_and_hides_direct_from_shared_choices():
    js = (ROOT / "static" / "js" / "dpe_cost_allocation.js").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    section = html.split('id="section-rateio"', 1)[1].split('id="section-politicas-rateio"', 1)[0]
    assert "Como deseja distribuir esta despesa?" in js
    assert "if(scope==='DIRECT')return rule.driver_type==='DIRECT'" in js
    assert "if(rule.driver_type==='DIRECT')return false" in js
    assert "Proporcional à receita" in js
    assert "Conforme atividades do docente" in js
    assert "Se este gasto não deve chegar aos cursos" in js
    assert "allocation-policy-tools" in js
    assert "Todos os cursos presenciais" not in js
    assert "Receita líquida" not in js
    assert "Forma de distribuição" in section
    assert "Receita líquida" not in section
