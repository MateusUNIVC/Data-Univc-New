from __future__ import annotations

import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from academic_analytics import build_academic_dashboard
from database import Base
from models import Course, Directorate, Discipline, Goal, TeacherEvaluation
from repository import DatabaseRepository, FACULTY_GOAL_METRIC_VERSION
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import FACULTY_STUDENT_GRADUATION_UNIT_NAME
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


class FacultyStudentV0115Tests(unittest.TestCase):
    def _repos(self):
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
            email="kpi02@univc.edu.br",
            full_name="KPI 02 Test",
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
        return db, DatabaseRepository(db, user), SurveyRepository(db, scope), course

    @staticmethod
    def _context() -> ParsedFacultyContext:
        return ParsedFacultyContext(
            source_path="GRAD/PSICOLOGIA/PROFESSORA/ANATOMIA/1.xlsx",
            source_key="faculty-kpi-v0115",
            unit_name=FACULTY_STUDENT_GRADUATION_UNIT_NAME,
            course_name="Psicologia",
            modality="Presencial",
            teacher_name="Professora Alpha",
            discipline_name="Anatomia",
            class_code="",
            survey_title="Avaliação Inst. Docente 2026",
            questionnaire_name="Avaliação Institucional discente 2023.2 - aluno avalia professor",
            period_start="2026-07-03",
            period_end="2026-07-24",
            respondent_count=10,
            questions=[
                ParsedQuestion(
                    text="O professor demonstra entusiasmo e motivação no desenvolvimento de suas aulas?",
                    normalized_text="o professor demonstra entusiasmo e motivacao no desenvolvimento de suas aulas",
                    position=1,
                    options=[
                        OptionAggregate(label="Sempre", count=6),
                        OptionAggregate(label="Quase sempre", count=2),
                        OptionAggregate(label="Nunca", count=2),
                    ],
                ),
                ParsedQuestion(
                    text="Como você avalia o UNIVC EAD quanto à qualidade das disciplinas oferecidas?",
                    normalized_text="como voce avalia o univc ead quanto a qualidade das disciplinas oferecidas",
                    position=9,
                    options=[
                        OptionAggregate(label="Excelente", count=0),
                        OptionAggregate(label="Insuficiente", count=10),
                    ],
                ),
            ],
        )

    def _import_official(self, survey: SurveyRepository) -> None:
        survey.import_faculty_contexts(
            sha256="5" * 64,
            source_filename="avaliacao_docente_2026.zip",
            source_kind="zip",
            contexts=[self._context()],
            semester_override="2026-SEM1",
            origin="manual",
        )

    def test_executive_snapshot_uses_official_favorability_not_legacy_score(self):
        db, repo, survey, course = self._repos()
        try:
            self._import_official(survey)
            discipline = db.scalar(select(Discipline).where(Discipline.course_id == course.id, Discipline.name == "Anatomia"))
            db.add(TeacherEvaluation(
                directorate_id=repo.directorate_id,
                period="2026-SEM1",
                course_id=course.id,
                discipline_id=discipline.id,
                teacher_name="Professora Alpha",
                respondents=10,
                average_score=1.0,
                inserted_by="legacy",
            ))
            db.commit()

            snapshot = repo.academic_dashboard_snapshot()
            rows = snapshot["avaliacao_docente"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["valor"], 80.0)
            self.assertEqual(rows[0]["favoraveis"], 8)
            self.assertEqual(rows[0]["classificados"], 10)
            self.assertEqual(rows[0]["metrica"], FACULTY_GOAL_METRIC_VERSION)
            self.assertNotIn("nota_media", rows[0])

            dashboard = build_academic_dashboard(snapshot, directorate_code="DCS", reference="2026-SEM1")
            card = dashboard["cards"]["avaliacao_docente"]
            self.assertEqual(card["valor"], 80.0)
            self.assertEqual(card["favoraveis"], 8)
            self.assertEqual(card["classificados"], 10)
            self.assertEqual(card["metrica"], FACULTY_GOAL_METRIC_VERSION)
        finally:
            db.close()

    def test_legacy_goal_is_preserved_but_not_applied_until_recreated_as_percentage(self):
        db, repo, survey, _ = self._repos()
        try:
            self._import_official(survey)
            db.add(Goal(
                directorate_id=repo.directorate_id,
                indicator_code="DCS-02",
                scope_label="TOTAL",
                valid_from="2026-SEM1",
                target=8.0,
                attention=7.0,
                justification="Meta histórica em nota",
                metric_version="legacy_score_0_10",
            ))
            db.commit()

            listed = repo.list_goals()
            self.assertEqual(len(listed), 1)
            self.assertTrue(listed[0]["legacy_metric"])
            self.assertEqual(listed[0]["unidade"], "nota")
            self.assertEqual(repo.get_metas(), [])

            snapshot = repo.academic_dashboard_snapshot()
            dashboard = build_academic_dashboard(snapshot, directorate_code="DCS", reference="2026-SEM1")
            self.assertIsNone(dashboard["cards"]["avaliacao_docente"]["meta"])

            updated = repo.update_goal(listed[0]["id"], {
                "indicador": "DCS-02",
                "recorte": "TOTAL",
                "vigencia": "2026-SEM1",
                "meta": 85,
                "atencao": 75,
                "limite_superior": 100,
                "justificativa": "Meta consciente em favorabilidade",
            })
            self.assertFalse(updated["legacy_metric"])
            self.assertEqual(updated["metric_version"], FACULTY_GOAL_METRIC_VERSION)
            self.assertEqual(updated["unidade"], "%")
            self.assertEqual(repo.get_metas()[0]["meta"], 85.0)
        finally:
            db.close()

    def test_faculty_goal_validation_rejects_score_scale_values(self):
        db, repo, _, _ = self._repos()
        try:
            with self.assertRaises(Exception) as ctx:
                repo.create_goal({
                    "indicador": "DCS-02", "recorte": "TOTAL", "vigencia": "2026-SEM1",
                    "meta": 850, "atencao": 75, "limite_superior": 100,
                })
            self.assertIn("0% e 100%", getattr(ctx.exception, "field_errors", {}).get("meta", ""))
            with self.assertRaises(Exception) as ctx:
                repo.create_goal({
                    "indicador": "DCS-02", "recorte": "TOTAL", "vigencia": "2026-SEM1",
                    "meta": 80, "atencao": 90, "limite_superior": 100,
                })
            self.assertIn("menor ou igual", getattr(ctx.exception, "field_errors", {}).get("atencao", ""))
        finally:
            db.close()

    def test_frontend_and_exports_do_not_advertise_score_as_official_kpi02(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        section = html[html.index('id="section-avaliacao_docente"'):html.index('id="section-resultados"')]
        self.assertIn("Favorabilidade", section)
        self.assertNotIn("nota 0–10", section.lower())
        app_js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("FacultyEvaluationUI?.triggerImport", app_js)
        self.assertIn("Meta legada · revisar", app_js)
        v2 = (root / "academic_excel_v2_builder.py").read_text(encoding="utf-8")
        v3 = (root / "academic_excel_v3_builder.py").read_text(encoding="utf-8")
        self.assertIn("Favorabilidade", v2)
        self.assertNotIn("Média ponderada pelos respondentes", v2)
        self.assertIn("Favorabilidade Docente", v3)
        self.assertNotIn("Média ponderada por respondentes", v3)


if __name__ == "__main__":
    unittest.main()
