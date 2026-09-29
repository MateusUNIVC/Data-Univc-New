from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Course,
    Directorate,
    FacultyEvaluationContext,
    FacultyEvaluationContextScope,
    FacultyResponseAggregate,
    SurveyRunCourse,
)
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_models import OptionAggregate, ParsedQuestion, ParsedWorkbook
from survey_repository import SurveyRepository



def make_repo(course_names: tuple[str, ...] = ("Educação Física - Bacharelado", "Educação Física - Licenciatura")):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code="DCS", name="DCS", active=True)
    db.add(directorate)
    db.flush()
    courses: dict[str, Course] = {}
    for name in course_names:
        row = Course(
            directorate_id=directorate.id,
            name=name,
            modality="Presencial",
            active=True,
            valid_from="2026-01",
        )
        db.add(row)
        db.flush()
        courses[name] = row
    db.commit()
    user = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="part3@univc.edu.br",
        full_name="Part 3 Test",
        role="editor",
        directorate_id=directorate.id,
        directorate_code="DCS",
        directorate_name="DCS",
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code="DCS",
        directorate_name="DCS",
        can_write=True,
        is_home=True,
    )
    return db, SurveyRepository(db, scope), courses



def test_sei_current_educacao_fisica_maps_to_licenciatura_but_manual_remains_ambiguous():
    db, repo, courses = make_repo()
    try:
        manual = repo.match_course_for_source("Educação Física", "PRESENCIAL", origin="manual")
        assert manual["matched"] is False
        assert manual["resolution_required"] is True
        assert {item["course_name"] for item in manual["candidate_courses"]} == {
            "Educação Física - Bacharelado",
            "Educação Física - Licenciatura",
        }

        sei = repo.match_course_for_source("Educação Física", "PRESENCIAL", origin="sei")
        assert sei["matched"] is True
        assert sei["course_id"] == courses["Educação Física - Licenciatura"].id
        assert sei["resolution_source"] == "sei_current_label"

        bach = repo.match_course_for_source("Educação Física (Bac. Presencial)", "PRESENCIAL", origin="sei")
        assert bach["matched"] is True
        assert bach["course_id"] == courses["Educação Física - Bacharelado"].id
    finally:
        db.close()



def test_manual_nps_ambiguous_course_can_be_explicitly_resolved_to_licenciatura():
    db, repo, courses = make_repo()
    try:
        parsed = ParsedWorkbook(
            source_path="NPS/educacao_fisica.xlsx",
            unit_name="Graduação",
            course_name="Educação Física",
            modality="PRESENCIAL",
            survey_title="NPS 2026.2",
            questionnaire_name="NPS Discente",
            period_start="2026-09-01",
            period_end="2026-09-20",
            semester_suggested="2026-SEM2",
            generated_at=None,
            respondent_count=10,
            questions=[
                ParsedQuestion(
                    text="Em uma escala de 0 a 10, quanto você recomendaria o UNIVC?",
                    normalized_text="em uma escala de 0 a 10 quanto voce recomendaria o univc",
                    position=1,
                    metric_type="numeric_0_10",
                    nps_candidate=True,
                    options=[
                        OptionAggregate(label="10", count=6, numeric_value=10),
                        OptionAggregate(label="8", count=2, numeric_value=8),
                        OptionAggregate(label="6", count=2, numeric_value=6),
                    ],
                )
            ],
        )
        result = repo.import_workbooks(
            sha256="1" * 64,
            source_filename="nps.xlsx",
            source_kind="xlsx",
            workbooks=[parsed],
            semester_override="2026-SEM2",
            origin="manual",
            course_resolutions={parsed.source_path: courses["Educação Física - Licenciatura"].id},
        )
        assert result["unmapped"] == []
        link = db.scalar(select(SurveyRunCourse).where(SurveyRunCourse.run_id == result["run_id"]))
        assert link is not None
        assert link.course_id == courses["Educação Física - Licenciatura"].id
    finally:
        db.close()



def test_shared_faculty_context_is_visible_in_each_course_without_double_counting_global_results():
    db, repo, courses = make_repo(("Psicologia", "Enfermagem"))
    try:
        parsed = ParsedFacultyContext(
            source_key="shared|prof-alpha|metodologia",
            source_path="FACULTY/shared.xlsx",
            unit_name="Graduação",
            course_name="Psicologia",
            modality="PRESENCIAL",
            teacher_name="Professora Alpha",
            discipline_name="Metodologia Científica",
            survey_title="Avaliação Docente 2026.2",
            questionnaire_name="Avaliação docente",
            period_start="2026-09-01",
            period_end="2026-09-20",
            semester_suggested="2026-SEM2",
            respondent_count=10,
            questions=[
                ParsedQuestion(
                    text="O professor demonstra entusiasmo e motivação no desenvolvimento de suas aulas?",
                    normalized_text="o professor demonstra entusiasmo e motivacao no desenvolvimento de suas aulas",
                    position=1,
                    options=[
                        OptionAggregate(label="Sempre", count=8),
                        OptionAggregate(label="Nunca", count=2),
                    ],
                )
            ],
        )
        kwargs = dict(
            sha256="2" * 64,
            source_filename="faculty.zip",
            source_kind="zip",
            contexts=[parsed],
            semester_override="2026-SEM2",
            origin="manual",
            shared_course_scopes={parsed.source_path: [courses["Enfermagem"].id]},
        )
        result = repo.import_faculty_contexts(**kwargs)
        assert result["unmapped"] == []
        assert len(result["shared_course_contexts"]) == 1

        assert db.scalar(select(func.count(FacultyEvaluationContext.id))) == 1
        assert db.scalar(select(func.count(FacultyEvaluationContextScope.id))) == 2
        assert db.scalar(select(func.count(FacultyResponseAggregate.id))) == 2

        global_overview = repo.faculty_analytics_overview(semester="2026-SEM2")["summary"]
        assert global_overview["contexts"] == 1
        assert global_overview["respondent_participations"] == 10
        assert global_overview["teacher_answer_selections"] == 10
        assert global_overview["courses"] == 2

        for course in courses.values():
            scoped = repo.faculty_analytics_overview(
                semester="2026-SEM2", course_id=course.id
            )["summary"]
            assert scoped["contexts"] == 1
            assert scoped["respondent_participations"] == 10
            assert scoped["teacher_answer_selections"] == 10

        course_items = repo.faculty_analytics_courses(semester="2026-SEM2")["items"]
        assert {item["name"] for item in course_items} == {"Psicologia", "Enfermagem"}
        assert all(item["summary"]["contexts"] == 1 for item in course_items)

        # Reimportar a mesma turma não duplica contexto, respostas nem escopos.
        repeat = repo.import_faculty_contexts(**kwargs)
        assert parsed.source_key in repeat["skipped_contexts"]
        assert db.scalar(select(func.count(FacultyEvaluationContext.id))) == 1
        assert db.scalar(select(func.count(FacultyEvaluationContextScope.id))) == 2
        assert db.scalar(select(func.count(FacultyResponseAggregate.id))) == 2
    finally:
        db.close()



def test_part3_frontend_uses_human_semester_fields_shared_scope_and_nps_resolution():
    root = Path(__file__).resolve().parents[1]
    faculty_js = (root / "static/js/faculty-evaluation.js").read_text(encoding="utf-8")
    app_js = (root / "static/js/app.js").read_text(encoding="utf-8")

    assert "facultyImportYear" in faculty_js
    assert "facultyImportSemesterPart" in faculty_js
    assert "shared_course_scopes" in faculty_js
    assert "Turmas compartilhadas" in faculty_js
    assert "data-nps-course-resolution" in app_js
    assert "CSS.escape(path)" not in app_js
