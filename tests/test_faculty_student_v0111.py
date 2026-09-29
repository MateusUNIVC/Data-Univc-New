from __future__ import annotations

import unittest
import uuid

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from academic_catalog import DCS_COURSES
from database import Base
from models import Course, Directorate, FacultyEvaluationContext
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import (
    FACULTY_STUDENT_GRADUATION_UNIT_NAME,
    is_graduation_unit,
    normalize_faculty_semester,
)
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


class FacultyStudentV0111Tests(unittest.TestCase):
    def test_graduation_unit_accepts_real_zip_folder_variant(self):
        self.assertTrue(is_graduation_unit(FACULTY_STUDENT_GRADUATION_UNIT_NAME))
        self.assertTrue(
            is_graduation_unit(
                "CENTRO UNIVERSITARIO VALE DO CRICARE  GRADUACAO (SAO MATEUSES)"
            )
        )
        self.assertFalse(
            is_graduation_unit(
                "CENTRO UNIVERSITARIO VALE DO CRICARE GRADUACAO SEMIPRESENCIAL (SAO MATEUS ES)"
            )
        )

    def test_semester_requires_explicit_valid_value(self):
        self.assertEqual(normalize_faculty_semester("2026.1"), "2026-SEM1")
        self.assertEqual(normalize_faculty_semester("2026-SEM2"), "2026-SEM2")
        self.assertIsNone(normalize_faculty_semester("2026"))
        self.assertIsNone(normalize_faculty_semester("julho/2026"))

    def _repo(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        db = Session()
        directorate = Directorate(code="DCS", name="DCS", active=True)
        db.add(directorate)
        db.flush()
        for name in DCS_COURSES:
            db.add(
                Course(
                    directorate_id=directorate.id,
                    name=name,
                    modality="Presencial",
                    active=True,
                    valid_from="2026-01",
                )
            )
        db.commit()
        user = AuthorizationContext(
            user_id=str(uuid.uuid4()),
            email="test@univc.edu.br",
            full_name="Test User",
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
        return db, SurveyRepository(db, scope)

    def test_educacao_fisica_without_degree_is_explicitly_ambiguous(self):
        db, repo = self._repo()
        try:
            match = repo.match_course("Educação Física", "PRESENCIAL")
            self.assertFalse(match["matched"])
            self.assertTrue(match["resolution_required"])
            self.assertEqual(
                set(match["candidates"]),
                {"Educação Física - Bacharelado", "Educação Física - Licenciatura"},
            )
        finally:
            db.close()

    def test_regenerated_manual_zip_does_not_duplicate_context(self):
        db, repo = self._repo()
        try:
            question = ParsedQuestion(
                text="O professor demonstra domínio do conteúdo?",
                normalized_text="o professor demonstra dominio do conteudo",
                position=1,
                options=[OptionAggregate(label="Sempre", count=10, source_percentage=100.0)],
            )
            context = ParsedFacultyContext(
                source_key="psicologia|professor teste|anatomia|501",
                source_path="GRADUACAO/PSICOLOGIA/PROFESSOR/ANATOMIA/501.xlsx",
                unit_name=FACULTY_STUDENT_GRADUATION_UNIT_NAME,
                course_name="Psicologia",
                modality="PRESENCIAL",
                teacher_name="Professor Teste",
                discipline_name="Anatomia",
                survey_title="Avaliação Inst. Docente 2026 (discente avalia docente)",
                questionnaire_name="Avaliação Institucional discente - aluno avalia professor",
                period_start="2026-07-03",
                period_end="2026-07-24",
                respondent_count=10,
                questions=[question],
            )
            first = repo.import_faculty_contexts(
                sha256="a" * 64,
                source_filename="primeiro.zip",
                source_kind="zip",
                contexts=[context],
                semester_override="2026-SEM1",
                origin="manual",
            )
            context.source_key = "psicologia|professor teste|anatomia|999"
            second = repo.import_faculty_contexts(
                sha256="b" * 64,
                source_filename="regenerado.zip",
                source_kind="zip",
                contexts=[context],
                semester_override="2026-SEM1",
                origin="manual",
            )
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(len(first["imported_contexts"]), 1)
            self.assertEqual(len(second["imported_contexts"]), 0)
            self.assertEqual(len(second["skipped_contexts"]), 1)
            count = db.scalar(select(func.count(FacultyEvaluationContext.id)))
            self.assertEqual(count, 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
