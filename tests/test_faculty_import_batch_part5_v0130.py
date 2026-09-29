from __future__ import annotations

import uuid

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Course,
    Directorate,
    FacultyEvaluationContext,
    FacultyEvaluationContextScope,
    FacultyResponseAggregate,
    SurveyImport,
)
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


def make_repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code="DCS", name="DCS", active=True)
    db.add(directorate)
    db.flush()
    psychology = Course(
        directorate_id=directorate.id,
        name="Psicologia",
        modality="Presencial",
        active=True,
        valid_from="2026-01",
    )
    nursing = Course(
        directorate_id=directorate.id,
        name="Enfermagem",
        modality="Presencial",
        active=True,
        valid_from="2026-01",
    )
    db.add_all([psychology, nursing])
    db.commit()
    user = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="part5@univc.edu.br",
        full_name="Part 5 Test",
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
    return engine, db, SurveyRepository(db, scope), psychology, nursing


def context(index: int, *, same_identity: bool = False) -> ParsedFacultyContext:
    suffix = "shared" if same_identity else str(index)
    return ParsedFacultyContext(
        source_key=f"faculty-{index}",
        source_path=f"faculty/{index}.xlsx",
        unit_name="Graduação",
        course_name="Psicologia",
        modality="PRESENCIAL",
        teacher_name=f"Professor {suffix}",
        discipline_name=f"Disciplina {suffix}",
        class_code="A",
        survey_title="Avaliação Docente 2026.2",
        questionnaire_name="Avaliação docente",
        period_start="2026-09-01",
        period_end="2026-09-20",
        semester_suggested="2026-SEM2",
        respondent_count=10,
        questions=[
            ParsedQuestion(
                text="O professor demonstra entusiasmo?",
                normalized_text="o professor demonstra entusiasmo",
                position=1,
                options=[
                    OptionAggregate(label="Sempre", count=8),
                    OptionAggregate(label="Nunca", count=2),
                ],
            )
        ],
    )


def test_faculty_batch_reduces_statement_explosion(monkeypatch):
    engine, db, repo, _, _ = make_repo()
    try:
        monkeypatch.setenv("FACULTY_IMPORT_BATCH_SIZE", "100")
        contexts = [context(i) for i in range(50)]
        counts: dict[str, int] = {}

        @event.listens_for(engine, "before_cursor_execute")
        def count_statement(conn, cursor, statement, parameters, ctx, executemany):
            statement_type = statement.lstrip().split(None, 1)[0].upper()
            counts[statement_type] = counts.get(statement_type, 0) + 1

        result = repo.import_faculty_contexts(
            sha256="5" * 64,
            source_filename="faculty.zip",
            source_kind="zip",
            contexts=contexts,
            semester_override="2026-SEM2",
            origin="manual",
        )

        assert len(result["imported_contexts"]) == 50
        assert result["performance"]["batches"] == 1
        assert result["performance"]["batch_metrics"][0]["aggregates_inserted"] == 100
        # O contrato principal da Parte 5: leituras e writes não crescem por
        # entidade/contexto como no antigo SELECT + flush dentro do loop.
        assert counts.get("SELECT", 0) <= 25
        assert counts.get("INSERT", 0) <= 20
    finally:
        db.close()


def test_faculty_batch_resume_after_interruption_is_idempotent(monkeypatch):
    _, db, repo, _, _ = make_repo()
    try:
        monkeypatch.setenv("FACULTY_IMPORT_BATCH_SIZE", "25")
        contexts = [context(i) for i in range(60)]
        original = repo._import_faculty_context_batch
        calls = {"n": 0}

        def fail_second_batch(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("falha simulada")
            return original(**kwargs)

        repo._import_faculty_context_batch = fail_second_batch  # type: ignore[method-assign]
        try:
            repo.import_faculty_contexts(
                sha256="6" * 64,
                source_filename="faculty.zip",
                source_kind="zip",
                contexts=contexts,
                semester_override="2026-SEM2",
                origin="manual",
            )
            raise AssertionError("A falha simulada deveria interromper o segundo lote")
        except RuntimeError as exc:
            assert "falha simulada" in str(exc)

        assert db.scalar(select(func.count(FacultyEvaluationContext.id))) == 25
        imp = db.scalar(select(SurveyImport).where(SurveyImport.sha256 == "6" * 64))
        assert imp is not None
        assert imp.status == "failed"

        repo._import_faculty_context_batch = original  # type: ignore[method-assign]
        resumed = repo.import_faculty_contexts(
            sha256="6" * 64,
            source_filename="faculty.zip",
            source_kind="zip",
            contexts=contexts,
            semester_override="2026-SEM2",
            origin="manual",
        )
        assert db.scalar(select(func.count(FacultyEvaluationContext.id))) == 60
        assert db.scalar(select(func.count(FacultyResponseAggregate.id))) == 120
        assert len(resumed["imported_contexts"]) == 35
        assert len(resumed["skipped_contexts"]) == 25
        assert db.get(SurveyImport, imp.id).status == "completed"
    finally:
        db.close()


def test_duplicate_identity_inside_same_batch_keeps_one_context_and_unions_scopes(monkeypatch):
    _, db, repo, _, nursing = make_repo()
    try:
        monkeypatch.setenv("FACULTY_IMPORT_BATCH_SIZE", "100")
        first = context(1, same_identity=True)
        second = context(2, same_identity=True)
        result = repo.import_faculty_contexts(
            sha256="7" * 64,
            source_filename="faculty.zip",
            source_kind="zip",
            contexts=[first, second],
            semester_override="2026-SEM2",
            origin="manual",
            shared_course_scopes={second.source_path: [nursing.id]},
        )
        assert db.scalar(select(func.count(FacultyEvaluationContext.id))) == 1
        assert db.scalar(select(func.count(FacultyEvaluationContextScope.id))) == 2
        assert db.scalar(select(func.count(FacultyResponseAggregate.id))) == 2
        assert result["imported_contexts"] == [first.source_key]
        assert result["skipped_contexts"] == [second.source_key]
    finally:
        db.close()
