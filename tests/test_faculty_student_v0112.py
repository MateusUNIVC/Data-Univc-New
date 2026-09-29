from __future__ import annotations

import unittest
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Course,
    Directorate,
    Discipline,
    SurveyImport,
    Teacher,
    TeachingAssignment,
    AcademicOffering,
)
from security import AuthorizationContext, DirectorateScope
from survey_faculty_identity import faculty_academic_identity_key
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import FACULTY_STUDENT_GRADUATION_UNIT_NAME
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyIntegrationError, SurveyRepository


class FacultyStudentV0112Tests(unittest.TestCase):
    def _repo(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        db = Session()
        directorate = Directorate(code="DCS", name="DCS", active=True)
        other = Directorate(code="DTNH", name="DTNH", active=True)
        db.add_all([directorate, other])
        db.flush()
        courses = {}
        for name in (
            "Educação Física - Bacharelado",
            "Educação Física - Licenciatura",
            "Psicologia",
            "Enfermagem",
        ):
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
        foreign = Course(
            directorate_id=other.id,
            name="Direito",
            modality="Presencial",
            active=True,
            valid_from="2026-01",
        )
        db.add(foreign)
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
        return db, SurveyRepository(db, scope), courses, foreign

    @staticmethod
    def _question() -> ParsedQuestion:
        return ParsedQuestion(
            text="O professor demonstra domínio do conteúdo?",
            normalized_text="o professor demonstra dominio do conteudo",
            position=1,
            options=[OptionAggregate(label="Sempre", count=10, source_percentage=100.0)],
        )

    def _context(
        self,
        *,
        course: str,
        teacher: str = "Professora Teste",
        discipline: str = "Disciplina Teste",
        source_path: str = "GRADUACAO/EDUCACAO_FISICA/PROFESSORA/DISCIPLINA/1.xlsx",
        class_code: str = "",
    ) -> ParsedFacultyContext:
        return ParsedFacultyContext(
            source_key=f"{course}|{teacher}|{discipline}|1",
            source_path=source_path,
            unit_name=FACULTY_STUDENT_GRADUATION_UNIT_NAME,
            course_name=course,
            modality="PRESENCIAL",
            teacher_name=teacher,
            discipline_name=discipline,
            class_code=class_code,
            survey_title="Avaliação Inst. Docente 2026 (discente avalia docente)",
            questionnaire_name="Avaliação Institucional discente 2023.2 - aluno avalia professor",
            period_start="2026-07-03",
            period_end="2026-07-24",
            respondent_count=10,
            questions=[self._question()],
        )

    def test_ambiguous_course_exposes_ids_and_accepts_only_allowed_resolution(self):
        db, repo, courses, foreign = self._repo()
        try:
            match = repo.match_course("Educação Física", "PRESENCIAL")
            self.assertFalse(match["matched"])
            self.assertTrue(match["resolution_required"])
            self.assertEqual(
                set(match["candidate_ids"]),
                {
                    courses["Educação Física - Bacharelado"].id,
                    courses["Educação Física - Licenciatura"].id,
                },
            )

            resolved = repo.resolve_course(
                "Educação Física",
                "PRESENCIAL",
                explicit_course_id=courses["Educação Física - Bacharelado"].id,
            )
            self.assertTrue(resolved["matched"])
            self.assertEqual(resolved["match_type"], "manual_resolution")
            self.assertEqual(resolved["course_name"], "Educação Física - Bacharelado")

            with self.assertRaises(SurveyIntegrationError):
                repo.resolve_course(
                    "Educação Física",
                    "PRESENCIAL",
                    explicit_course_id=foreign.id,
                )
        finally:
            db.close()

    def test_manual_resolution_is_persisted_and_auditable(self):
        db, repo, courses, _ = self._repo()
        try:
            context = self._context(course="Educação Física")
            target = courses["Educação Física - Licenciatura"]
            result = repo.import_faculty_contexts(
                sha256="1" * 64,
                source_filename="avaliacao.zip",
                source_kind="zip",
                contexts=[context],
                semester_override="2026-SEM1",
                origin="manual",
                course_resolutions={context.source_path: target.id},
            )
            self.assertEqual(len(result["imported_contexts"]), 1)
            self.assertEqual(len(result["course_resolutions_applied"]), 1)
            self.assertEqual(
                result["course_resolutions_applied"][0]["course_id"], target.id
            )

            imp = db.scalar(select(SurveyImport).where(SurveyImport.id == result["import_id"]))
            audit = (imp.metadata_json or {}).get("faculty_course_resolutions") or []
            self.assertEqual(audit[0]["course_name"], "Educação Física - Licenciatura")
        finally:
            db.close()

    def test_same_teacher_is_reused_across_courses_and_semester_identity_is_preserved(self):
        db, repo, courses, _ = self._repo()
        try:
            first = self._context(
                course="Psicologia",
                teacher="  Professora   Única  ",
                discipline="Psicologia Social",
                source_path="GRAD/PSICOLOGIA/PROF/PSICOLOGIA_SOCIAL/1.xlsx",
            )
            second = self._context(
                course="Enfermagem",
                teacher="Professora Unica",
                discipline="Saúde Coletiva",
                source_path="GRAD/ENFERMAGEM/PROF/SAUDE_COLETIVA/2.xlsx",
            )
            repo.import_faculty_contexts(
                sha256="2" * 64,
                source_filename="avaliacao.zip",
                source_kind="zip",
                contexts=[first, second],
                semester_override="2026-SEM1",
                origin="manual",
            )
            teachers = list(db.scalars(select(Teacher)).all())
            self.assertEqual(len(teachers), 1)

            offerings = list(db.scalars(select(AcademicOffering)).all())
            assignments = list(db.scalars(select(TeachingAssignment)).all())
            self.assertEqual(len(offerings), 2)
            self.assertEqual(len(assignments), 2)
            self.assertEqual({item.teacher_id for item in assignments}, {teachers[0].id})

            third = self._context(
                course="Psicologia",
                teacher="Professora Única",
                discipline="Psicologia Social",
                source_path="GRAD/PSICOLOGIA/PROF/PSICOLOGIA_SOCIAL/3.xlsx",
            )
            # Outra avaliação/período para permitir novo survey run lógico.
            third.survey_title = "Avaliação Inst. Docente 2026.2 (discente avalia docente)"
            third.period_start = "2026-12-01"
            third.period_end = "2026-12-15"
            repo.import_faculty_contexts(
                sha256="3" * 64,
                source_filename="avaliacao_2.zip",
                source_kind="zip",
                contexts=[third],
                semester_override="2026-SEM2",
                origin="manual",
            )
            teachers = list(db.scalars(select(Teacher)).all())
            self.assertEqual(len(teachers), 1)
            periods = {item.period for item in db.scalars(select(AcademicOffering)).all()}
            self.assertEqual(periods, {"2026-SEM1", "2026-SEM2"})
        finally:
            db.close()

    def test_same_discipline_name_in_different_courses_remains_separate(self):
        db, repo, _, _ = self._repo()
        try:
            contexts = [
                self._context(
                    course="Psicologia",
                    discipline="Metodologia Científica",
                    source_path="GRAD/PSICOLOGIA/P/METODOLOGIA/1.xlsx",
                ),
                self._context(
                    course="Enfermagem",
                    discipline="Metodologia Cientifica",
                    source_path="GRAD/ENFERMAGEM/P/METODOLOGIA/2.xlsx",
                ),
            ]
            repo.import_faculty_contexts(
                sha256="4" * 64,
                source_filename="avaliacao.zip",
                source_kind="zip",
                contexts=contexts,
                semester_override="2026-SEM1",
                origin="manual",
            )
            disciplines = list(db.scalars(select(Discipline)).all())
            self.assertEqual(len(disciplines), 2)
            self.assertEqual(len({item.course_id for item in disciplines}), 2)
        finally:
            db.close()

    def test_identity_catalog_and_quality_expose_relational_graph(self):
        db, repo, _, _ = self._repo()
        try:
            context = self._context(
                course="Psicologia",
                teacher="Professor Catálogo",
                discipline="Anatomia",
                source_path="GRAD/PSICOLOGIA/P/ANATOMIA/1.xlsx",
            )
            repo.import_faculty_contexts(
                sha256="5" * 64,
                source_filename="avaliacao.zip",
                source_kind="zip",
                contexts=[context],
                semester_override="2026-SEM1",
                origin="manual",
            )
            catalog = repo.faculty_identity_catalog("2026.1")
            self.assertEqual(catalog["summary"]["contexts"], 1)
            self.assertEqual(catalog["summary"]["teachers"], 1)
            self.assertEqual(catalog["items"][0]["course_name"], "Psicologia")

            quality = repo.faculty_identity_quality("2026-SEM1")
            self.assertEqual(quality["blocking_issue_count"], 0)
            self.assertEqual(quality["summary"]["contexts"], 1)
        finally:
            db.close()

    def test_academic_identity_key_distinguishes_class_group(self):
        base = dict(
            period="2026-SEM1",
            course_identity=10,
            teacher_name="Professor A",
            discipline_name="Disciplina X",
        )
        self.assertNotEqual(
            faculty_academic_identity_key(**base, class_group="T1"),
            faculty_academic_identity_key(**base, class_group="T2"),
        )


if __name__ == "__main__":
    unittest.main()
