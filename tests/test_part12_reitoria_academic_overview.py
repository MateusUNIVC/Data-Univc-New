from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    AcademicResult,
    AcademicStudent,
    Course,
    Directorate,
    Discipline,
    NpsInstitution,
    NpsStudent,
)
from reitoria_academic import ReitoriaAcademicService
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import FACULTY_STUDENT_GRADUATION_UNIT_NAME
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


ROOT = Path(__file__).resolve().parents[1]


def _question(favorable: int, unfavorable: int) -> ParsedQuestion:
    return ParsedQuestion(
        text="O professor demonstra domínio do conteúdo e conduz bem as aulas?",
        normalized_text="o professor demonstra dominio do conteudo e conduz bem as aulas",
        position=1,
        options=[
            OptionAggregate(label="Sempre", count=favorable),
            OptionAggregate(label="Nunca", count=unfavorable),
        ],
    )


def _faculty_context(course: str, teacher: str, discipline: str, favorable: int, unfavorable: int, source: str) -> ParsedFacultyContext:
    return ParsedFacultyContext(
        source_key=source,
        source_path=source,
        unit_name=FACULTY_STUDENT_GRADUATION_UNIT_NAME,
        course_name=course,
        modality="PRESENCIAL",
        teacher_name=teacher,
        discipline_name=discipline,
        survey_title="Avaliação Docente 2026/2",
        questionnaire_name="Avaliação Institucional discente - aluno avalia professor",
        period_start="2026-10-01",
        period_end="2026-10-20",
        respondent_count=favorable + unfavorable,
        questions=[_question(favorable, unfavorable)],
    )


def _scope(ctx: AuthorizationContext, directorate: Directorate) -> DirectorateScope:
    return DirectorateScope(
        user=ctx,
        directorate_id=directorate.id,
        directorate_code=directorate.code,
        directorate_name=directorate.name,
        can_write=True,
        is_home=False,
    )


def _seed():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    dtnh = Directorate(code="DTNH", name="Diretoria DTNH", active=True)
    dcs = Directorate(code="DCS", name="Diretoria DCS", active=True)
    db.add_all([dtnh, dcs]); db.flush()
    admin = Course(directorate_id=dtnh.id, name="Administração", modality="Presencial", active=True, valid_from="2026-01")
    psico = Course(directorate_id=dcs.id, name="Psicologia", modality="Presencial", active=True, valid_from="2026-01")
    db.add_all([admin, psico]); db.flush()
    gestao = Discipline(course_id=admin.id, name="Gestão", active=True, valid_from="2026-01")
    social = Discipline(course_id=psico.id, name="Psicologia Social", active=True, valid_from="2026-01")
    db.add_all([gestao, social]); db.flush()
    ctx = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="reitoria@univc.test",
        full_name="Reitoria Teste",
        role="admin",
        directorate_id=dtnh.id,
        directorate_code="DTNH",
        directorate_name=dtnh.name,
        global_role="REITORIA",
    )

    # NPS propositalmente muito diferente para detectar média de médias.
    db.add(NpsInstitution(directorate_id=dtnh.id, period="2026-SEM2", respondents=100, promoters=60, neutrals=20, detractors=20))
    db.add(NpsInstitution(directorate_id=dcs.id, period="2026-SEM2", respondents=50, promoters=10, neutrals=10, detractors=30))
    db.add(NpsStudent(directorate_id=dtnh.id, period="2026-SEM2", course_id=admin.id, respondents=100, promoters=60, neutrals=20, detractors=20))
    db.add(NpsStudent(directorate_id=dcs.id, period="2026-SEM2", course_id=psico.id, respondents=50, promoters=10, neutrals=10, detractors=30))

    # 10 resultados DTNH: 9 aprovados, média 9. 5 DCS: 1 aprovado, média 5.
    for index in range(10):
        student = AcademicStudent(directorate_id=dtnh.id, registration=f"A{index}", name=f"Aluno A{index}", course_id=admin.id, active=True)
        db.add(student); db.flush()
        db.add(AcademicResult(
            directorate_id=dtnh.id, period="2026-SEM2", course_id=admin.id, discipline_id=gestao.id,
            student_id=student.id, class_group="ADM", final_average=9, approved=index < 9,
            failure_reason=None if index < 9 else "nota",
        ))
    for index in range(5):
        student = AcademicStudent(directorate_id=dcs.id, registration=f"P{index}", name=f"Aluno P{index}", course_id=psico.id, active=True)
        db.add(student); db.flush()
        db.add(AcademicResult(
            directorate_id=dcs.id, period="2026-SEM2", course_id=psico.id, discipline_id=social.id,
            student_id=student.id, class_group="PSI", final_average=5, approved=index < 1,
            failure_reason=None if index < 1 else "nota",
        ))
    db.commit()

    SurveyRepository(db, _scope(ctx, dtnh)).import_faculty_contexts(
        sha256="a" * 64, source_filename="dtnh.zip", source_kind="zip",
        contexts=[_faculty_context("Administração", "Professor DTNH", "Gestão", 90, 10, "DTNH/1.xlsx")],
        semester_override="2026-SEM2", origin="manual",
    )
    SurveyRepository(db, _scope(ctx, dcs)).import_faculty_contexts(
        sha256="b" * 64, source_filename="dcs.zip", source_kind="zip",
        contexts=[_faculty_context("Psicologia", "Professor DCS", "Psicologia Social", 10, 40, "DCS/1.xlsx")],
        semester_override="2026-SEM2", origin="manual",
    )
    return db, ctx, dtnh, dcs, admin, psico


def test_reitoria_overview_uses_weighted_base_counts_not_mean_of_directorates():
    db, ctx, *_ = _seed()
    try:
        result = ReitoriaAcademicService(db, ctx).overview(semester="2026-SEM2")
        # NPS: (70 promotores - 50 detratores) / 150 = 13,33; média simples seria 0.
        assert result["kpis"]["nps_institution_students"]["valor"] == 13.33
        assert result["kpis"]["nps_courses"]["valor"] == 13.33
        assert result["kpis"]["nps_institution_students"]["respondentes"] == 150
        # Aprovação: 10 / 15 = 66,67%; média simples 55%.
        assert result["kpis"]["approval"]["value"] == 66.67
        # Média das notas: (10*9 + 5*5) / 15 = 7,67; média simples seria 7.
        assert result["kpis"]["average_grade"]["value"] == 7.67
        assert result["kpis"]["distinct_students"]["value"] == 15
        # Favorabilidade: 100 favoráveis / 150 classificadas = 66,67%; média simples seria 55%.
        assert result["kpis"]["faculty_favorability"]["value"] == 66.67
        assert result["kpis"]["faculty_favorability"]["classified"] == 150
    finally:
        db.close()


def test_reitoria_filters_can_reduce_to_one_directorate_and_course():
    db, ctx, dtnh, _dcs, admin, _psico = _seed()
    try:
        service = ReitoriaAcademicService(db, ctx)
        filters = service.filters(directorate="DTNH")
        assert {item["directorate"] for item in filters["courses"]} == {"DTNH"}
        result = service.overview(semester="2026-SEM2", directorate="DTNH", course_id=admin.id)
        assert result["scope"]["directorates"] == ["DTNH"]
        assert result["scope"]["course"] == "Administração"
        assert result["kpis"]["nps_courses"]["valor"] == 40.0
        assert result["kpis"]["approval"]["value"] == 90.0
        assert result["kpis"]["faculty_favorability"]["value"] == 90.0
        assert len(result["comparisons"]["approval_courses"]) == 1
    finally:
        db.close()


def test_reitoria_academic_surface_is_read_only_and_present_in_navigation():
    html = (ROOT / "templates" / "reitoria.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "reitoria_academic.js").read_text(encoding="utf-8")
    assert 'href="#academico"' in html
    assert 'id="academico"' in html
    assert 'Todas · UNIVC' in html
    assert 'Somente leitura' in js
    assert '/api/reitoria/academic/overview' in js
    assert '/api/reitoria/academic/filters' in js


def test_reitoria_charts_keep_semantic_scales():
    js = (ROOT / "static" / "js" / "data-univc-academic-charts.js").read_text(encoding="utf-8")
    assert 'percentage: {min:0,max:100' in js
    assert 'nps: {min:-100,max:100' in js
    assert 'grade: {min:0,max:10' in js
    assert "if (kind === 'count')" in js


def test_part12_is_reitoria_only_and_has_no_schema_migration():
    release = (ROOT / "release_info.py").read_text(encoding="utf-8")
    router = (ROOT / "reitoria_academic_router.py").read_text(encoding="utf-8")
    assert 'Depends(require_fresh_reitoria)' in router
    assert 'SCHEMA_VERSION = 49' in release
    assert '049_academic_faculty_context_scopes_v0130.sql' in release
