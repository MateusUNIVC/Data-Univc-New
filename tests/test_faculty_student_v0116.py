from __future__ import annotations

import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Course, Directorate, Goal
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import FACULTY_STUDENT_GRADUATION_UNIT_NAME
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


class FacultyStudentV0116Tests(unittest.TestCase):
    def _repo(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        db = Session()
        directorate = Directorate(code="DCS", name="DCS", active=True)
        db.add(directorate)
        db.flush()
        db.add(Course(
            directorate_id=directorate.id,
            name="Psicologia",
            modality="Presencial",
            active=True,
            valid_from="2026-01",
        ))
        db.commit()
        user = AuthorizationContext(
            user_id=str(uuid.uuid4()),
            email="faculty-prod@univc.edu.br",
            full_name="Faculty Production",
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
        return db, SurveyRepository(db, scope), directorate

    @staticmethod
    def _context(*, semester: str, favorable: int, unfavorable: int) -> ParsedFacultyContext:
        sem = 1 if semester.endswith("SEM1") else 2
        return ParsedFacultyContext(
            source_path=f"GRAD/PSICOLOGIA/PROFESSORA/ANATOMIA/{semester}.xlsx",
            source_key=f"faculty-prod-{semester}",
            unit_name=FACULTY_STUDENT_GRADUATION_UNIT_NAME,
            course_name="Psicologia",
            modality="Presencial",
            teacher_name="Professora Alpha",
            discipline_name="Anatomia",
            class_code="",
            survey_title=f"Avaliação Inst. Docente 2026.{sem}",
            questionnaire_name="Avaliação Institucional discente 2023.2 - aluno avalia professor",
            period_start="2026-05-01" if sem == 1 else "2026-11-01",
            period_end="2026-06-30" if sem == 1 else "2026-12-10",
            respondent_count=favorable + unfavorable,
            questions=[
                ParsedQuestion(
                    text="O professor demonstra entusiasmo e motivação no desenvolvimento de suas aulas?",
                    normalized_text="o professor demonstra entusiasmo e motivacao no desenvolvimento de suas aulas",
                    position=1,
                    options=[
                        OptionAggregate(label="Sempre", count=favorable),
                        OptionAggregate(label="Nunca", count=unfavorable),
                    ],
                )
            ],
        )

    def _import(self, repo: SurveyRepository, semester: str, favorable: int, unfavorable: int):
        repo.import_faculty_contexts(
            sha256=("1" if semester.endswith("SEM1") else "2") * 64,
            source_filename=f"avaliacao_docente_{semester}.zip",
            source_kind="zip",
            contexts=[self._context(semester=semester, favorable=favorable, unfavorable=unfavorable)],
            semester_override=semester,
            origin="manual",
        )

    def test_operational_status_combines_trend_goal_quality_and_audit(self):
        db, repo, directorate = self._repo()
        try:
            self._import(repo, "2026-SEM1", 8, 2)
            self._import(repo, "2026-SEM2", 9, 1)
            db.add(Goal(
                directorate_id=directorate.id,
                indicator_code="DCS-02",
                scope_label="TOTAL",
                valid_from="2026-SEM1",
                target=85,
                attention=75,
                upper_limit=100,
                justification="Meta oficial",
                metric_version="faculty_favorability_pct_v1",
            ))
            db.commit()

            comparison = repo.faculty_analytics_semester_comparison()
            self.assertEqual([x["semester"] for x in comparison["items"]], ["2026-SEM1", "2026-SEM2"])
            self.assertIsNone(comparison["items"][0]["delta_percentage_points"])
            self.assertEqual(comparison["items"][0]["goal_status"], "Atenção")
            self.assertEqual(comparison["items"][1]["delta_percentage_points"], 10.0)
            self.assertEqual(comparison["items"][1]["goal_status"], "Dentro da meta")
            self.assertEqual(comparison["items"][1]["goal"]["meta"], 85.0)

            operational = repo.faculty_analytics_operational_status()
            self.assertEqual(operational["current_period"], "2026-SEM2")
            self.assertEqual(operational["current_value"], 90.0)
            self.assertEqual(operational["previous_period"], "2026-SEM1")
            self.assertEqual(operational["previous_value"], 80.0)
            self.assertEqual(operational["delta_percentage_points"], 10.0)
            self.assertEqual(operational["gap_to_goal_percentage_points"], 5.0)
            self.assertEqual(operational["goal_status"], "Dentro da meta")
            self.assertEqual(operational["readiness"], "ready")
            self.assertEqual(operational["quality"]["blocking_issue_count"], 0)
            self.assertEqual(operational["latest_import"]["semester"], "2026-SEM2")
            self.assertEqual(operational["latest_import"]["last_imported_by"], "faculty-prod@univc.edu.br")
            self.assertEqual(operational["latest_import"]["import_attempts"], 1)
        finally:
            db.close()

    def test_frontend_defaults_to_latest_period_and_exposes_operational_reading(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        js = (root / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")
        css = (root / "static" / "css" / "faculty-evaluation.css").read_text(encoding="utf-8")
        self.assertNotIn('id="facultyOperationalStatus"', html)
        self.assertIn('id="facultyTrendContext"', html)
        self.assertIn("<h3>Importações</h3>", html)
        self.assertNotIn("Importações e qualidade da malha", html)
        self.assertNotIn('id="facultyIdentityQuality"', html)
        self.assertNotIn('id="facultyQualityDetails"', html)
        self.assertIn("/analytics/operational", js)
        self.assertNotIn("/identity/quality", js)
        self.assertIn("periodInitialized", js)
        self.assertIn("delta_percentage_points", js)
        self.assertNotIn("Cobertura classificada", js)
        self.assertNotIn("Prontidão do indicador", js)
        self.assertNotIn(".faculty-readiness", css)


if __name__ == "__main__":
    unittest.main()
