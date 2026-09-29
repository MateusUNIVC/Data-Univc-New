from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import release_info
from database import Base
from dpe_management import DPEManagementRepository
from management_catalog import indicator_spec, metric_spec, reload_catalog
from management_repository import ManagementRepository
from management_service import ManagementValidationError
from models import Directorate
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
        user_id="dev11", email="dev11@test.local", full_name="Dev11", role="editor",
        directorate_id=directorate.id, directorate_code="DPE", directorate_name="DPE",
    )
    scope = DirectorateScope(
        user=user, directorate_id=directorate.id, directorate_code="DPE",
        directorate_name="DPE", can_write=True, is_home=True,
    )
    return engine, db, scope


def test_release_preserves_dev11_management_contract_without_schema_bump():
    assert release_info.APP_VERSION.startswith("0.13.0")
    if release_info.APP_VERSION != "0.13.0":
        assert int(release_info.APP_VERSION.rsplit(".", 1)[-1]) >= 11
    assert release_info.SCHEMA_VERSION == 48


def test_canonical_management_catalog_uses_runtime_metrics_and_hides_historical_new_entries():
    dpe = reload_catalog()["directorates"]["DPE"]
    by_code = {item["code"]: item for item in dpe["indicators"]}
    assert {"DPE-RESULT", "DPE-REVENUE", "DPE-EXPENSE", "DPE-TEACHING", "DPE-ALLOCATION"}.issubset(by_code)
    assert metric_spec("DPE", "DPE-RESULT", "institutional_result")["aggregation"] == "runtime"
    assert metric_spec("DPE", "DPE-RESULT", "course_margin_12m_pct")["targetable"] is False
    assert metric_spec("DPE", "DPE-EXPENSE", "payroll_on_revenue_pct")["legacy_metric"] is True
    assert indicator_spec("DPE", "DPE-01")["legacy"] is True


def test_dpe_rejects_new_target_on_historical_metric_and_plan_without_metric():
    engine, db, scope = _context()
    try:
        repo = ManagementRepository(db, scope)
        with pytest.raises(ManagementValidationError):
            repo.save_target({
                "indicator_code": "DPE-RESULT", "metric_key": "course_margin_12m_pct",
                "valid_from": "2026-09", "target": 15, "dimensions": {},
            })
        with pytest.raises(ManagementValidationError):
            repo.save_action({
                "indicator_code": "DPE-RESULT", "metric_key": None, "period": "2026-09",
                "dimensions": {}, "problem": "Problema", "corrective_action": "Corrigir",
                "responsible": "Pessoa", "due_date": "2026-10-10", "status": "Aberto",
            })
    finally:
        db.close()
        engine.dispose()


def test_dpe_metric_dimensions_are_enforced_for_new_targets():
    engine, db, scope = _context()
    try:
        repo = ManagementRepository(db, scope)
        with pytest.raises(ManagementValidationError):
            repo.save_target({
                "indicator_code": "DPE-RESULT", "metric_key": "institutional_margin_pct",
                "valid_from": "2026-09", "target": 10,
                "dimensions": {"course": "Administração"},
            })
        created = repo.save_target({
            "indicator_code": "DPE-RESULT", "metric_key": "course_margin_pct",
            "valid_from": "2026-09", "target": 15,
            "dimensions": {"course": "Administração", "academic_directorate": "DTNH"},
        })
        assert created["dimension_label"].startswith("Curso: Administração")
    finally:
        db.close()
        engine.dispose()


def test_target_status_evaluation_uses_direction_and_attention():
    higher = {"direction": "higher"}
    lower = {"direction": "lower"}
    target_higher = {"target": 85, "attention": 80}
    target_lower = {"target": 480000, "attention": 520000}
    assert DPEManagementRepository._evaluate(higher, target_higher, 90)["key"] == "GOOD"
    assert DPEManagementRepository._evaluate(higher, target_higher, 82)["key"] == "ATTENTION"
    assert DPEManagementRepository._evaluate(higher, target_higher, 70)["key"] == "BAD"
    assert DPEManagementRepository._evaluate(lower, target_lower, 470000)["key"] == "GOOD"
    assert DPEManagementRepository._evaluate(lower, target_lower, 500000)["key"] == "ATTENTION"
    assert DPEManagementRepository._evaluate(lower, target_lower, 530000)["key"] == "BAD"


def test_dpe_management_ui_loads_runtime_overview_and_can_create_plan_from_target():
    js = (ROOT / "static" / "js" / "dpe.js").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    assert "/api/dpe/management/overview" in js
    assert "data-plan-target" in js
    assert "Valor atual" in html
    assert "targetSummary" in html and "actionSummary" in html
    assert "medições gerenciais" not in html.lower()
