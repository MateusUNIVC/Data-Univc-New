from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Directorate
from repository import DatabaseRepository
from schemas import ValidationError
from security import AuthorizationContext



def make_repo() -> tuple[object, DatabaseRepository]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code="DCS", name="DCS", active=True)
    db.add(directorate)
    db.commit()
    user = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="part10@univc.edu.br",
        full_name="Part 10 Audit",
        role="editor",
        directorate_id=directorate.id,
        directorate_code="DCS",
        directorate_name="DCS",
    )
    return db, DatabaseRepository(db, user)


def assert_goal_rejected(repo: DatabaseRepository, payload: dict, field: str, phrase: str) -> None:
    with pytest.raises(ValidationError) as exc:
        repo.create_goal(payload)
    assert phrase in exc.value.field_errors.get(field, "")


def test_academic_goal_domains_match_chart_semantics():
    db, repo = make_repo()
    try:
        assert_goal_rejected(repo, {
            "indicador": "DCS-03", "recorte": "TOTAL", "vigencia": "2026-SEM2",
            "meta": 101, "atencao": 80, "limite_superior": None,
        }, "meta", "0% e 100%")
        assert_goal_rejected(repo, {
            "indicador": "DCS-01B", "recorte": "TOTAL", "vigencia": "2026-SEM2",
            "meta": -101, "atencao": -20, "limite_superior": None,
        }, "meta", "-100 e 100")
        assert_goal_rejected(repo, {
            "indicador": "DCS-01A", "recorte": "TOTAL", "vigencia": "2026-SEM2",
            "meta": 40, "atencao": 50, "limite_superior": None,
        }, "atencao", "menor ou igual")
        assert_goal_rejected(repo, {
            "indicador": "DCS-03", "recorte": "TOTAL", "vigencia": "2026-SEM2",
            "meta": 85, "atencao": 80, "limite_superior": 70,
        }, "limite_superior", "maior ou igual")
    finally:
        db.close()


def test_goal_form_exposes_same_domains_before_submit():
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    assert "function goalBoundsForIndicator" in js
    assert "min:-100, max:100" in js
    assert "min:0, max:100" in js
    assert "applyGoalInputBounds" in js
    assert "Intervalo válido:" in js


def test_release_preflight_guards_previous_production_regressions():
    checks = (ROOT / "scripts/run_release_checks.py").read_text(encoding="utf-8")
    assert 'ROOT / "dpe_cost_v2.py"' in checks
    assert 'ROOT / "database" / SCHEMA_MIGRATION' in checks
    assert "verify_academic_bootstrap_helpers" in checks
    assert '"fillConfig"' in checks


def test_critical_release_assets_exist():
    required = [
        ROOT / "dpe_cost_v2.py",
        ROOT / "database" / "049_academic_faculty_context_scopes_v0130.sql",
        ROOT / "static" / "js" / "app.js",
        ROOT / "static" / "js" / "faculty-evaluation.js",
        ROOT / "static" / "js" / "data-univc-ui.js",
    ]
    assert not [path for path in required if not path.exists()]


def test_excel_executive_charts_keep_semantic_domains():
    from io import BytesIO
    from openpyxl import load_workbook
    from academic_excel_v3_builder import build_academic_interactive_workbook
    from tests.test_academic_interactive_excel_part7 import _payload

    wb = load_workbook(BytesIO(build_academic_interactive_workbook(_payload("DTNH")).getvalue()), data_only=False)
    charts = wb["PAINEL"]._charts
    assert len(charts) == 5
    # NPS temporal
    assert charts[0].y_axis.scaling.min == -100
    assert charts[0].y_axis.scaling.max == 100
    # Composição Promotores/Neutros/Detratores
    assert charts[1].y_axis.scaling.min == 0
    assert charts[1].y_axis.scaling.max == 100
    # Favorabilidade e aprovação
    assert charts[2].y_axis.scaling.min == 0 and charts[2].y_axis.scaling.max == 100
    assert charts[3].y_axis.scaling.min == 0 and charts[3].y_axis.scaling.max == 100
    # NPS por curso é barra horizontal: escala numérica está no eixo X.
    assert charts[4].x_axis.scaling.min == -100
    assert charts[4].x_axis.scaling.max == 100
    wb.close()
