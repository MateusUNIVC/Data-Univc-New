from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Course, Directorate
from security import AuthorizationContext, DirectorateScope
from survey_faculty_institution_models import ParsedFacultyInstitutionWorkbook
from survey_models import OptionAggregate, ParsedQuestion, ParsedWorkbook
from survey_repository import SurveyRepository


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def make_repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code="DCS", name="DCS", active=True)
    db.add(directorate)
    db.flush()
    course = Course(
        directorate_id=directorate.id,
        name="Psicologia",
        modality="Presencial",
        active=True,
        valid_from="2026-01",
    )
    db.add(course)
    db.commit()
    user = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="part9@univc.edu.br",
        full_name="Part 9 Test",
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
    return db, SurveyRepository(db, scope), course


def nps_question() -> ParsedQuestion:
    counts = {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 4, 7: 1, 8: 1, 9: 2, 10: 3}
    return ParsedQuestion(
        text="Em uma escala de 0 a 10, quanto você recomendaria o UNIVC?",
        normalized_text="em uma escala de 0 a 10 quanto voce recomendaria o univc",
        position=1,
        metric_type="numeric_0_10",
        nps_candidate=True,
        options=[OptionAggregate(label=str(score), count=count, numeric_value=score) for score, count in counts.items()],
    )


def student_workbook() -> ParsedWorkbook:
    return ParsedWorkbook(
        source_path="NPS/psicologia.xlsx",
        unit_name="Graduação",
        course_name="Psicologia",
        modality="Presencial",
        survey_title="NPS 2026.2",
        questionnaire_name="NPS Discente",
        period_start="2026-09-01",
        period_end="2026-09-20",
        semester_suggested="2026-SEM2",
        generated_at=None,
        respondent_count=17,
        questions=[nps_question()],
    )


def faculty_workbook() -> ParsedFacultyInstitutionWorkbook:
    return ParsedFacultyInstitutionWorkbook(
        source_path="NPS_DOCENTES/docentes.xlsx",
        unit_name="Graduação",
        survey_title="NPS Docentes 2026.2",
        questionnaire_name="NPS Institucional Docentes",
        period_start="2026-09-01",
        period_end="2026-09-20",
        semester_suggested="2026-SEM2",
        generated_at=None,
        respondent_count=17,
        questions=[nps_question()],
    )


def test_student_nps_distribution_returns_all_scores_counts_mean_and_total():
    db, repo, _ = make_repo()
    try:
        imported = repo.import_workbooks(
            sha256="9" * 64,
            source_filename="nps.xlsx",
            source_kind="xlsx",
            workbooks=[student_workbook()],
            semester_override="2026-SEM2",
            origin="manual",
        )
        candidate = repo.list_nps_candidates(int(imported["run_id"]))[0]
        repo.bind_and_sync_nps(
            run_id=int(imported["run_id"]),
            question_id=int(candidate["id"]),
            semester="2026-SEM2",
            nps_scope="course",
        )
        payload = repo.nps_distribution(
            audience="course", semester="2026-SEM2", course="Psicologia"
        )
        assert payload["available"] is True
        assert payload["total"] == 17
        assert len(payload["items"]) == 11
        assert [item["score"] for item in payload["items"]] == list(range(11))
        assert sum(item["count"] for item in payload["items"]) == payload["total"]
        assert payload["items"][6]["count"] == 4
        assert payload["mean"] == 6.0
        assert payload["promoters"] == 5
        assert payload["neutrals"] == 2
        assert payload["detractors"] == 10
    finally:
        db.close()


def test_institution_student_distribution_uses_official_institution_source():
    db, repo, _ = make_repo()
    try:
        imported = repo.import_workbooks(
            sha256="7" * 64,
            source_filename="institution.xlsx",
            source_kind="xlsx",
            workbooks=[student_workbook()],
            semester_override="2026-SEM2",
            origin="manual",
        )
        candidate = repo.list_nps_candidates(int(imported["run_id"]))[0]
        repo.bind_and_sync_nps(
            run_id=int(imported["run_id"]),
            question_id=int(candidate["id"]),
            semester="2026-SEM2",
            nps_scope="institution",
        )
        payload = repo.nps_distribution(
            audience="institution", semester="2026-SEM2", course="Psicologia"
        )
        assert payload["available"] is True
        assert payload["course"] == "Psicologia"
        assert payload["total"] == 17
        assert payload["mean"] == 6.0
        assert sum(item["count"] for item in payload["items"]) == 17
    finally:
        db.close()


def test_faculty_nps_distribution_uses_same_zero_to_ten_contract():
    db, repo, _ = make_repo()
    try:
        imported = repo.import_faculty_institution_workbooks(
            sha256="8" * 64,
            source_filename="faculty.xlsx",
            source_kind="xlsx",
            workbooks=[faculty_workbook()],
            semester_override="2026-SEM2",
            origin="manual",
        )
        candidate = repo.list_faculty_nps_candidates(int(imported["run_id"]))[0]
        repo.bind_and_sync_faculty_nps(
            run_id=int(imported["run_id"]),
            question_id=int(candidate["id"]),
            semester="2026-SEM2",
        )
        payload = repo.nps_distribution(audience="faculty", semester="2026-SEM2")
        assert payload["available"] is True
        assert payload["scope_label"] == "Todos os docentes"
        assert payload["total"] == 17
        assert len(payload["items"]) == 11
        assert sum(item["count"] for item in payload["items"]) == 17
        assert payload["mean"] == 6.0
    finally:
        db.close()


def test_semantic_chart_scales_are_fixed_for_percent_nps_and_nonnegative_counts():
    assert "percentage: { min: 0, max: 100" in APP_JS
    assert "nps: { min: -100, max: 100" in APP_JS
    assert "if (kind === 'count')" in APP_JS
    assert "return { kind, min: 0, max, ticks, fixed: true }" in APP_JS
    assert "['alunos_distintos','alunos_aprovados','matriculas']" in APP_JS


def test_bar_values_use_separate_value_column_instead_of_invading_course_label():
    assert 'x="${width - 6}"' in APP_JS
    assert 'text-anchor="end"' in APP_JS
    assert "axisGuides" in APP_JS


def test_all_three_nps_workspaces_expose_zero_to_ten_distribution_panel():
    assert 'id="npsInstitutionDistribution"' in INDEX_HTML
    assert 'id="npsCourseDistribution"' in INDEX_HTML
    assert 'id="npsFacultyDistribution"' in INDEX_HTML
    assert "loadNpsScoreDistribution('course'" in APP_JS
    assert "loadNpsScoreDistribution('institution'" in APP_JS
    assert "loadNpsScoreDistribution('faculty'" in APP_JS
