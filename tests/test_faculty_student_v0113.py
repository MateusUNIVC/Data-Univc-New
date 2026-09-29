from __future__ import annotations

import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Course, Directorate
from security import AuthorizationContext, DirectorateScope
from survey_faculty_analytics import classify_faculty_question, favorability_summary
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import FACULTY_STUDENT_GRADUATION_UNIT_NAME
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


class FacultyStudentV0113Tests(unittest.TestCase):
    def _repo(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        db = Session()
        directorate = Directorate(code="DCS", name="DCS", active=True)
        db.add(directorate)
        db.flush()
        courses = {}
        for name in ("Psicologia", "Enfermagem"):
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
            email="analytics@univc.edu.br",
            full_name="Analytics Test",
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

    @staticmethod
    def _questions(multiplier: int = 1):
        return [
            ParsedQuestion(
                text="O professor demonstra entusiasmo e motivação no desenvolvimento de suas aulas?",
                normalized_text="o professor demonstra entusiasmo e motivacao no desenvolvimento de suas aulas",
                position=1,
                options=[
                    OptionAggregate(label="Sempre", count=6 * multiplier),
                    OptionAggregate(label="Quase sempre", count=2 * multiplier),
                    OptionAggregate(label="Quase nunca", count=1 * multiplier),
                    OptionAggregate(label="Nunca", count=1 * multiplier),
                    OptionAggregate(label="Não sei", count=2 * multiplier),
                ],
            ),
            ParsedQuestion(
                text="Como você avalia a PONTUALIDADE nos horários de início e término das aulas do professor?",
                normalized_text="como voce avalia a pontualidade nos horarios de inicio e termino das aulas do professor",
                position=2,
                options=[
                    OptionAggregate(label="Ótimo", count=4 * multiplier),
                    OptionAggregate(label="Bom", count=4 * multiplier),
                    OptionAggregate(label="Regular", count=2 * multiplier),
                    OptionAggregate(label="Insuficiente", count=1 * multiplier),
                    OptionAggregate(label="Não sei", count=1 * multiplier),
                ],
            ),
        ]

    def _context(
        self,
        *,
        course: str,
        teacher: str,
        discipline: str,
        source_path: str,
        semester_label: str,
        respondents: int = 12,
        multiplier: int = 1,
    ) -> ParsedFacultyContext:
        return ParsedFacultyContext(
            source_key=f"{course}|{teacher}|{discipline}|{source_path}",
            source_path=source_path,
            unit_name=FACULTY_STUDENT_GRADUATION_UNIT_NAME,
            course_name=course,
            modality="PRESENCIAL",
            teacher_name=teacher,
            discipline_name=discipline,
            survey_title=f"Avaliação Inst. Docente {semester_label}",
            questionnaire_name="Avaliação Institucional discente 2023.2 - aluno avalia professor",
            period_start="2026-07-03" if "SEM1" in semester_label else "2026-12-01",
            period_end="2026-07-24" if "SEM1" in semester_label else "2026-12-15",
            respondent_count=respondents,
            questions=self._questions(multiplier),
        )


    def test_contextual_question_is_not_a_teacher_metric(self):
        self.assertEqual(
            classify_faculty_question("O professor demonstra entusiasmo e motivação?"),
            "teacher",
        )
        self.assertEqual(
            classify_faculty_question("O docente mostra-se disposto a participar de atividades?"),
            "teacher",
        )
        self.assertEqual(
            classify_faculty_question("Como você avalia o UNIVC EAD quanto à qualidade das disciplinas?"),
            "contextual",
        )

    def test_favorability_uses_explicit_denominator_and_blocks_unknown_scale(self):
        rows = [
            {"option_label": "Sempre", "response_count": 6},
            {"option_label": "Quase sempre", "response_count": 2},
            {"option_label": "Quase nunca", "response_count": 1},
            {"option_label": "Nunca", "response_count": 1},
            {"option_label": "Não sei", "response_count": 2},
        ]
        summary = favorability_summary(rows)
        self.assertTrue(summary["mapping_complete"])
        self.assertEqual(summary["source_total"], 12)
        self.assertEqual(summary["classified_total"], 10)
        self.assertEqual(summary["favorable_percentage"], 80.0)
        self.assertEqual(summary["classified_coverage_percentage"], 83.33)

        rows.append({"option_label": "Categoria futura", "response_count": 1})
        summary = favorability_summary(rows)
        self.assertFalse(summary["mapping_complete"])
        self.assertEqual(summary["unmapped_total"], 1)
        self.assertIsNone(summary["favorable_percentage"])

    def test_overview_questions_and_filters_preserve_source_semantics(self):
        db, repo, courses = self._repo()
        try:
            contexts = [
                self._context(
                    course="Psicologia",
                    teacher="Professora Alpha",
                    discipline="Anatomia",
                    source_path="GRAD/PSICOLOGIA/ALPHA/ANATOMIA/1.xlsx",
                    semester_label="2026-SEM1",
                ),
                self._context(
                    course="Enfermagem",
                    teacher="Professora Alpha",
                    discipline="Saúde Coletiva",
                    source_path="GRAD/ENFERMAGEM/ALPHA/SAUDE/2.xlsx",
                    semester_label="2026-SEM1",
                ),
                self._context(
                    course="Psicologia",
                    teacher="Professor Beta",
                    discipline="Anatomia",
                    source_path="GRAD/PSICOLOGIA/BETA/ANATOMIA/3.xlsx",
                    semester_label="2026-SEM1",
                ),
            ]
            repo.import_faculty_contexts(
                sha256="a" * 64,
                source_filename="sem1.zip",
                source_kind="zip",
                contexts=contexts,
                semester_override="2026-SEM1",
                origin="manual",
            )

            overview = repo.faculty_analytics_overview(semester="2026.1")
            self.assertEqual(overview["summary"]["contexts"], 3)
            self.assertEqual(overview["summary"]["respondent_participations"], 36)
            self.assertEqual(overview["summary"]["questions"], 2)
            self.assertEqual(overview["summary"]["teachers"], 2)
            self.assertEqual(overview["summary"]["courses"], 2)
            self.assertFalse(overview["methodology"]["is_source_score"])
            self.assertEqual(overview["summary"]["favorability_scope"], "teacher_questions_only")

            questions = repo.faculty_analytics_questions(
                semester="2026-SEM1", course_id=courses["Psicologia"].id
            )
            self.assertEqual(questions["question_count"], 2)
            self.assertEqual(questions["items"][0]["favorability"]["favorable_percentage"], 80.0)
            self.assertEqual(questions["items"][1]["favorability"]["favorable_percentage"], 72.73)
            self.assertEqual(questions["items"][0]["distribution"]["total"], 24)

            filters = repo.faculty_analytics_filters(course_id=courses["Psicologia"].id)
            self.assertEqual(filters["matching_contexts"], 2)
            self.assertEqual(len(filters["teachers"]), 2)
            self.assertEqual({item["name"] for item in filters["disciplines"]}, {"Anatomia"})
            # A faceta de curso exclui o proprio filtro e permite trocar de curso.
            self.assertEqual({item["name"] for item in filters["courses"]}, {"Psicologia", "Enfermagem"})
        finally:
            db.close()

    def test_contextual_question_remains_visible_but_does_not_change_teacher_favorability(self):
        db, repo, _ = self._repo()
        try:
            context = self._context(
                course="Psicologia",
                teacher="Professora Alpha",
                discipline="Anatomia",
                source_path="GRAD/PSICOLOGIA/ALPHA/ANATOMIA/Q9.xlsx",
                semester_label="2026-SEM1",
            )
            context.questions.append(
                ParsedQuestion(
                    text="Como você avalia o UNIVC EAD quanto a qualidade das disciplinas oferecidas?",
                    normalized_text="como voce avalia o univc ead quanto a qualidade das disciplinas oferecidas",
                    position=9,
                    options=[
                        OptionAggregate(label="Excelente", count=0),
                        OptionAggregate(label="Muito boa", count=0),
                        OptionAggregate(label="Razoável", count=0),
                        OptionAggregate(label="Insuficiente", count=10),
                        OptionAggregate(label="Não sei responder", count=2),
                    ],
                )
            )
            repo.import_faculty_contexts(
                sha256="d" * 64,
                source_filename="contextual.zip",
                source_kind="zip",
                contexts=[context],
                semester_override="2026-SEM1",
                origin="manual",
            )
            overview = repo.faculty_analytics_overview(semester="2026-SEM1")
            self.assertEqual(overview["summary"]["questions"], 3)
            self.assertEqual(overview["summary"]["teacher_questions"], 2)
            self.assertEqual(overview["summary"]["contextual_questions"], 1)
            # A pergunta contextual e propositalmente negativa; a sintese do docente
            # continua sendo calculada apenas sobre as duas perguntas de professor.
            self.assertEqual(overview["summary"]["favorability"]["favorable_percentage"], 76.19)
            questions = repo.faculty_analytics_questions(semester="2026-SEM1")
            contextual = next(item for item in questions["items"] if item["position"] == 9)
            self.assertEqual(contextual["analytical_scope"], "contextual")
            self.assertEqual(contextual["favorability"]["favorable_percentage"], 0.0)
        finally:
            db.close()

    def test_teacher_discipline_groups_and_semester_comparison(self):
        db, repo, courses = self._repo()
        try:
            sem1 = self._context(
                course="Psicologia",
                teacher="Professora Alpha",
                discipline="Anatomia",
                source_path="GRAD/PSICOLOGIA/ALPHA/ANATOMIA/1.xlsx",
                semester_label="2026-SEM1",
            )
            repo.import_faculty_contexts(
                sha256="b" * 64,
                source_filename="sem1.zip",
                source_kind="zip",
                contexts=[sem1],
                semester_override="2026-SEM1",
                origin="manual",
            )
            sem2 = self._context(
                course="Psicologia",
                teacher="Professora Alpha",
                discipline="Anatomia",
                source_path="GRAD/PSICOLOGIA/ALPHA/ANATOMIA/2.xlsx",
                semester_label="2026-SEM2",
                respondents=24,
                multiplier=2,
            )
            repo.import_faculty_contexts(
                sha256="c" * 64,
                source_filename="sem2.zip",
                source_kind="zip",
                contexts=[sem2],
                semester_override="2026-SEM2",
                origin="manual",
            )

            teachers = repo.faculty_analytics_teachers(course_id=courses["Psicologia"].id)
            self.assertEqual(len(teachers["items"]), 1)
            teacher = teachers["items"][0]
            self.assertEqual(teacher["summary"]["contexts"], 2)
            self.assertEqual(teacher["summary"]["respondent_participations"], 36)

            detail = repo.faculty_analytics_teacher_detail(teacher["id"])
            self.assertEqual(len(detail["contexts"]), 2)
            self.assertEqual(detail["questions"]["question_count"], 2)

            disciplines = repo.faculty_analytics_disciplines(teacher_id=teacher["id"])
            self.assertEqual(len(disciplines["items"]), 1)
            discipline_id = disciplines["items"][0]["id"]
            discipline = repo.faculty_analytics_discipline_detail(discipline_id)
            self.assertEqual(discipline["discipline"]["name"], "Anatomia")

            comparison = repo.faculty_analytics_semester_comparison(teacher_id=teacher["id"])
            self.assertEqual([item["semester"] for item in comparison["items"]], ["2026-SEM1", "2026-SEM2"])
            self.assertEqual(comparison["items"][0]["summary"]["respondent_participations"], 12)
            self.assertEqual(comparison["items"][1]["summary"]["respondent_participations"], 24)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
