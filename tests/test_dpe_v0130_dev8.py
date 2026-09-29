from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import release_info
from database import Base
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_cost_expenses import DPECostExpenseRepository
from dpe_cost_teaching import DPECostTeachingRepository
from models import (
    Course,
    Directorate,
    DPEAllocationRule,
    DPECostPeriodTeacher,
    DPEExpenseCategory,
    DPETeacherProfile,
    Teacher,
)
from security import AuthorizationContext, DirectorateScope

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    dpe = Directorate(code="DPE", name="DPE", active=True)
    academic = Directorate(code="DTNH", name="DTNH", active=True)
    db.add_all([dpe, academic]); db.commit(); db.refresh(dpe); db.refresh(academic)
    user = AuthorizationContext(
        user_id="dev8", email="dev8@test.local", full_name="Dev8", role="editor",
        directorate_id=dpe.id, directorate_code="DPE", directorate_name="DPE",
    )
    scope = DirectorateScope(
        user=user, directorate_id=dpe.id, directorate_code="DPE", directorate_name="DPE",
        can_write=True, is_home=True,
    )
    catalog = DPECostCatalogRepository(db, scope)
    teaching = DPECostTeachingRepository(db, scope)
    expenses = DPECostExpenseRepository(db, scope)
    course = Course(directorate_id=academic.id, name="Administração", modality="EAD", active=True, valid_from="2026-01")
    db.add(course); db.commit(); db.refresh(course)
    product = catalog.create_product({"code": "ADM", "name": "Administração", "source_course_id": course.id, "valid_from": "2026-01"})
    period = catalog.create_period({"period": "2026-09", "materialize_offerings": True})
    catalog.update_period(period["id"], {"status": "REVIEW"})
    period = catalog.get_period(period["id"])
    rule = DPEAllocationRule(
        directorate_id=dpe.id, code="TEACHER_HOURS", name="Carga docente",
        driver_type="TEACHER_HOURS", description="Teste", system_defined=True, active=True,
    )
    db.add(rule); db.flush()
    category = DPEExpenseCategory(
        directorate_id=dpe.id, code="DOCENTE", name="Custo docente",
        default_rule_id=rule.id, active=True,
    )
    db.add(category); db.commit(); db.refresh(category)
    return engine, db, dpe, scope, catalog, teaching, expenses, period, category


def test_release_keeps_teacher_profile_schema_48_or_newer():
    assert release_info.SCHEMA_VERSION >= 48
    migration = "048_dpe_teacher_profiles_v0130.sql"
    sql = (ROOT / "database" / migration).read_text(encoding="utf-8").lower()
    assert "dpe_teacher_profiles" in sql
    assert "relationship_type" in sql
    assert "unspecified" in sql and "service_provider" in sql


def test_dpe_teacher_directory_is_scoped_and_can_adopt_existing_identity():
    engine, db, dpe, scope, _catalog, teaching, _expenses, _period, _category = _fixture()
    try:
        global_teacher = Teacher(external_id="INST-1", display_name="Maria Silva", normalized_name="maria silva", active=True)
        db.add(global_teacher); db.commit(); db.refresh(global_teacher)
        assert teaching.list_teachers() == []
        adopted = teaching.create_teacher({
            "display_name": "Maria Silva", "external_id": "INST-1",
            "relationship_type": "EMPLOYEE", "profile_notes": "Docente DPE",
        })
        assert adopted["id"] == global_teacher.id
        assert adopted["relationship_type"] == "EMPLOYEE"
        assert adopted["profile_notes"] == "Docente DPE"
        assert db.scalar(select(DPETeacherProfile).where(DPETeacherProfile.teacher_id == global_teacher.id)) is not None
        assert [row["id"] for row in teaching.list_teachers()] == [global_teacher.id]
    finally:
        db.close(); engine.dispose()


def test_monthly_relationship_is_snapshotted_and_can_be_changed_without_rewriting_profile():
    engine, db, _dpe, _scope, _catalog, teaching, _expenses, period, _category = _fixture()
    try:
        teacher = teaching.create_teacher({"display_name": "João Docente", "relationship_type": "HOURLY"})
        subject = teaching.create_subject({"code": "ADM101", "name": "Gestão"})
        offering_id = period["offerings"][0]["id"]
        teaching.create_activity({
            "period_id": period["id"], "teacher_id": teacher["id"], "subject_id": subject["id"],
            "workload_hours": 20,
            "offering_allocations": [{"period_offering_id": offering_id, "allocated_hours": 20}],
        })
        monthly = teaching.list_period_teachers(period["id"])[0]
        assert monthly["relationship_type"] == "HOURLY"
        teaching.update_teacher(teacher["id"], {"relationship_type": "EMPLOYEE"})
        assert teaching.list_teachers()[0]["relationship_type"] == "EMPLOYEE"
        assert teaching.list_period_teachers(period["id"])[0]["relationship_type"] == "HOURLY"
        teaching.update_period_teacher(monthly["id"], {"relationship_type": "SERVICE_PROVIDER", "notes": "Exceção do mês"})
        updated = teaching.list_period_teachers(period["id"])[0]
        assert updated["relationship_type"] == "SERVICE_PROVIDER"
        assert updated["notes"] == "Exceção do mês"
        assert teaching.list_teachers()[0]["relationship_type"] == "EMPLOYEE"
    finally:
        db.close(); engine.dispose()


def test_monthly_teacher_summary_separates_workload_from_reconciled_cost():
    engine, db, _dpe, _scope, _catalog, teaching, expenses, period, category = _fixture()
    try:
        teacher = teaching.create_teacher({"display_name": "Ana Docente", "relationship_type": "EMPLOYEE"})
        subject = teaching.create_subject({"code": "ADM102", "name": "Planejamento"})
        offering_id = period["offerings"][0]["id"]
        teaching.create_activity({
            "period_id": period["id"], "teacher_id": teacher["id"], "subject_id": subject["id"],
            "workload_hours": "32.5",
            "offering_allocations": [{"period_offering_id": offering_id, "allocated_hours": "32.5"}],
        })
        expense = expenses.create_expense({
            "period_id": period["id"], "description": "Custo docente - Ana", "amount": "6200",
            "expense_kind": "PAYROLL", "expense_scope": "SHARED", "category_id": category.id,
            "counterparty_name": "Ana Docente",
        })
        teaching.link_payroll_expense(expense["id"], {"teacher_id": teacher["id"], "match_method": "MANUAL"})
        monthly = teaching.list_period_teachers(period["id"])[0]
        assert monthly["workload_hours"] == 32.5
        assert monthly["payroll_total"] == 6200.0
        assert monthly["payroll_count"] == 1
        central = teaching.central_payload(period_id=period["id"])
        assert central["summary"]["period_teacher_count"] == 1
        assert central["period_teachers"][0]["payroll_total"] == 6200.0
    finally:
        db.close(); engine.dispose()


def test_frontend_separates_activity_relationship_cost_and_master_data():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "dpe_cost_teaching.js").read_text(encoding="utf-8")
    assert "Atividades docentes" in html
    assert "Vínculos e custos" in html
    assert "Cadastro de docentes" in html
    assert 'id="teachingPeriodTeachersTable"' in html
    assert "+ Registrar atividade" in html
    assert "+ Registrar aula" not in html
    assert "data-period-teacher-edit" in js
    assert "/api/dpe/cost-engine/period-teachers/" in js
    assert "relationship_type" in js
