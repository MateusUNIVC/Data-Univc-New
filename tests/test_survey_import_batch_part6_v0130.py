from __future__ import annotations

import uuid

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Course,
    Directorate,
    SurveyFacultyInstitutionContext,
    SurveyFacultyInstitutionResponseAggregate,
    SurveyRawResponse,
    SurveyResponseAggregate,
    SurveyRunCourse,
)
from security import AuthorizationContext, DirectorateScope
from survey_faculty_institution_models import ParsedFacultyInstitutionWorkbook
from survey_models import OptionAggregate, ParsedQuestion, ParsedWorkbook
from survey_repository import SurveyRepository


def make_repo(course_count: int = 60):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code="DCS", name="DCS", active=True)
    db.add(directorate)
    db.flush()
    courses = []
    for index in range(course_count):
        course = Course(
            directorate_id=directorate.id,
            name=f"Curso {index:03d}",
            modality="Presencial",
            active=True,
            valid_from="2026-01",
        )
        db.add(course)
        courses.append(course)
    db.commit()
    user = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="part6@univc.edu.br",
        full_name="Part 6 Test",
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
    return engine, db, SurveyRepository(db, scope), courses


def question(*, raw: bool = False) -> ParsedQuestion:
    return ParsedQuestion(
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
        raw_responses=["Resposta aberta"] if raw else [],
    )


def generic_workbook(index: int) -> ParsedWorkbook:
    return ParsedWorkbook(
        source_path=f"NPS/curso_{index:03d}.xlsx",
        unit_name="Graduação",
        course_name=f"Curso {index:03d}",
        modality="Presencial",
        survey_title="NPS 2026.2",
        questionnaire_name="NPS Discente",
        period_start="2026-09-01",
        period_end="2026-09-20",
        semester_suggested="2026-SEM2",
        generated_at=None,
        respondent_count=10,
        questions=[question(raw=True)],
    )


def faculty_workbook(index: int) -> ParsedFacultyInstitutionWorkbook:
    return ParsedFacultyInstitutionWorkbook(
        source_path=f"NPS_DOCENTES/lote_{index:03d}.xlsx",
        unit_name="Graduação",
        survey_title="NPS Docentes 2026.2",
        questionnaire_name="NPS Institucional Docentes",
        period_start="2026-09-01",
        period_end="2026-09-20",
        semester_suggested="2026-SEM2",
        generated_at=None,
        respondent_count=10,
        questions=[question(raw=True)],
    )


def _statement_counter(engine):
    counts: dict[str, int] = {}

    @event.listens_for(engine, "before_cursor_execute")
    def count_statement(conn, cursor, statement, parameters, ctx, executemany):
        statement_type = statement.lstrip().split(None, 1)[0].upper()
        counts[statement_type] = counts.get(statement_type, 0) + 1

    return counts


def test_generic_nps_import_batches_questions_and_responses(monkeypatch):
    engine, db, repo, _ = make_repo(60)
    try:
        monkeypatch.setenv("SURVEY_IMPORT_BATCH_SIZE", "50")
        counts = _statement_counter(engine)
        result = repo.import_workbooks(
            sha256="a" * 64,
            source_filename="nps.zip",
            source_kind="zip",
            workbooks=[generic_workbook(i) for i in range(50)],
            semester_override="2026-SEM2",
            origin="manual",
        )

        assert len(result["imported_files"]) == 50
        assert result["performance"]["reports_imported"] == 50
        assert result["performance"]["questions_catalogued"] == 1
        assert result["performance"]["run_courses_inserted"] == 50
        assert result["performance"]["aggregates_inserted"] == 150
        assert result["performance"]["raw_responses_inserted"] == 50
        assert db.scalar(select(func.count(SurveyRunCourse.id))) == 50
        assert db.scalar(select(func.count(SurveyResponseAggregate.id))) == 150
        assert db.scalar(select(func.count(SurveyRawResponse.id))) == 50

        # A quantidade de SELECTs não cresce com curso x pergunta, como no fluxo
        # antigo que fazia SELECT de curso do run + pergunta + vínculo por XLSX.
        assert counts.get("SELECT", 0) <= 15
        assert counts.get("INSERT", 0) <= 15
    finally:
        db.close()


def test_generic_nps_reimport_is_idempotent():
    _, db, repo, _ = make_repo(10)
    try:
        workbooks = [generic_workbook(i) for i in range(10)]
        kwargs = dict(
            sha256="b" * 64,
            source_filename="nps.zip",
            source_kind="zip",
            workbooks=workbooks,
            semester_override="2026-SEM2",
            origin="manual",
        )
        first = repo.import_workbooks(**kwargs)
        second = repo.import_workbooks(**kwargs)
        assert len(first["imported_files"]) == 10
        assert second["imported_files"] == []
        assert len(second["skipped_files"]) == 10
        assert db.scalar(select(func.count(SurveyRunCourse.id))) == 10
        assert db.scalar(select(func.count(SurveyResponseAggregate.id))) == 30
        assert db.scalar(select(func.count(SurveyRawResponse.id))) == 10
    finally:
        db.close()


def test_faculty_institution_nps_batches_contexts_questions_and_responses(monkeypatch):
    engine, db, repo, _ = make_repo(1)
    try:
        monkeypatch.setenv("SURVEY_IMPORT_BATCH_SIZE", "50")
        counts = _statement_counter(engine)
        result = repo.import_faculty_institution_workbooks(
            sha256="c" * 64,
            source_filename="nps_docentes.zip",
            source_kind="zip",
            workbooks=[faculty_workbook(i) for i in range(50)],
            semester_override="2026-SEM2",
            origin="manual",
        )
        assert len(result["imported_files"]) == 50
        assert result["performance"]["contexts_inserted"] == 50
        assert result["performance"]["questions_catalogued"] == 1
        assert result["performance"]["aggregates_inserted"] == 150
        assert result["performance"]["raw_responses_inserted"] == 50
        assert db.scalar(select(func.count(SurveyFacultyInstitutionContext.id))) == 50
        assert db.scalar(select(func.count(SurveyFacultyInstitutionResponseAggregate.id))) == 150
        assert counts.get("SELECT", 0) <= 15
        assert counts.get("INSERT", 0) <= 20
    finally:
        db.close()
