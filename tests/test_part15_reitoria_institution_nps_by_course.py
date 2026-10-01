from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Course,
    Directorate,
    SurveyImport,
    SurveyInstitutionNpsSource,
    SurveyQuestion,
    SurveyQuestionnaire,
    SurveyResponseAggregate,
    SurveyRun,
)
from reitoria_academic import ReitoriaAcademicService
from security import AuthorizationContext


def _add_institution_source(db, directorate, course, questionnaire, question, *, prefix: str, counts: dict[int, int]):
    imp = SurveyImport(
        id=f"imp-{prefix}",
        directorate_id=directorate.id,
        source_filename=f"{prefix}.zip",
        sha256=(prefix * 64)[:64],
        source_kind="zip",
        origin="manual",
        status="completed",
    )
    db.add(imp)
    db.flush()
    run = SurveyRun(
        directorate_id=directorate.id,
        import_id=imp.id,
        questionnaire_id=questionnaire.id,
        title="NPS Institucional",
        semester="2026-SEM2",
        run_kind="student_nps",
    )
    db.add(run)
    db.flush()
    db.add(SurveyInstitutionNpsSource(
        directorate_id=directorate.id,
        semester="2026-SEM2",
        run_id=run.id,
        question_id=question.id,
    ))
    for score, count in counts.items():
        db.add(SurveyResponseAggregate(
            run_id=run.id,
            course_id=course.id,
            question_id=question.id,
            option_label=str(score),
            option_key=f"score-{score}",
            numeric_value=float(score),
            response_count=count,
        ))


def test_institution_nps_by_course_is_rebuilt_from_institution_question_raw_counts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    try:
        dtnh = Directorate(code="DTNH", name="DTNH", active=True)
        dcs = Directorate(code="DCS", name="DCS", active=True)
        db.add_all([dtnh, dcs]); db.flush()
        admin = Course(directorate_id=dtnh.id, name="Administração", modality="Presencial", active=True, valid_from="2026-01")
        psico = Course(directorate_id=dcs.id, name="Psicologia", modality="Presencial", active=True, valid_from="2026-01")
        db.add_all([admin, psico]); db.flush()
        questionnaire = SurveyQuestionnaire(name="Questionário NPS institucional")
        question = SurveyQuestion(
            text="De 0 a 10, quanto você recomendaria a UNIVC?",
            normalized_text="de 0 a 10 quanto voce recomendaria a univc",
            position=1,
            detected_metric_type="nps",
            nps_candidate=True,
        )
        db.add_all([questionnaire, question]); db.flush()
        # Administração: 6 promotores, 2 neutros, 2 detratores => NPS +40.
        _add_institution_source(db, dtnh, admin, questionnaire, question, prefix="a", counts={10: 6, 8: 2, 5: 2})
        # Psicologia: 1 promotor, 1 neutro, 8 detratores => NPS -70.
        _add_institution_source(db, dcs, psico, questionnaire, question, prefix="b", counts={10: 1, 8: 1, 5: 8})
        db.commit()
        actor = AuthorizationContext(
            user_id=str(uuid.uuid4()), email="reitoria@univc.test", full_name="Reitoria",
            role="admin", directorate_id=dtnh.id, directorate_code="DTNH",
            directorate_name="DTNH", global_role="REITORIA",
        )
        result = ReitoriaAcademicService(db, actor).overview(semester="2026-SEM2")
        rows = {row["curso"]: row for row in result["comparisons"]["nps_institution_courses"]}
        assert rows["Administração"]["valor"] == 40.0
        assert rows["Administração"]["respondentes"] == 10
        assert rows["Psicologia"]["valor"] == -70.0
        assert rows["Psicologia"]["detratores"] == 8
    finally:
        db.close()
