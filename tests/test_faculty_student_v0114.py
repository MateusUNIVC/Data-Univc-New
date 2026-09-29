from __future__ import annotations

import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Course, Directorate
from security import AuthorizationContext, DirectorateScope
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import FACULTY_STUDENT_GRADUATION_UNIT_NAME
from survey_models import OptionAggregate, ParsedQuestion
from survey_repository import SurveyRepository


class FacultyStudentV0114Tests(unittest.TestCase):
    def _repo(self):
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
            email="ui-test@univc.edu.br",
            full_name="UI Test",
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

    @staticmethod
    def _context():
        return ParsedFacultyContext(
            source_path="GRAD/PSICOLOGIA/PROFESSORA/ANATOMIA/1.xlsx",
            source_key="faculty-ui-1",
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
                        OptionAggregate(label="Sempre", count=7),
                        OptionAggregate(label="Quase sempre", count=2),
                        OptionAggregate(label="Nunca", count=1),
                    ],
                )
            ],
        )

    def test_import_history_reads_existing_faculty_run_without_new_schema(self):
        db, repo = self._repo()
        try:
            result = repo.import_faculty_contexts(
                sha256="f" * 64,
                source_filename="avaliacao_docente_2026.zip",
                source_kind="zip",
                contexts=[self._context()],
                semester_override="2026-SEM1",
                origin="manual",
                metadata={"faculty_course_resolutions": []},
            )
            history = repo.faculty_import_history()
            self.assertEqual(history["count"], 1)
            item = history["items"][0]
            self.assertEqual(item["import_id"], result["import_id"])
            self.assertEqual(item["semester"], "2026-SEM1")
            self.assertEqual(item["context_count"], 1)
            self.assertEqual(item["course_resolution_count"], 0)
            self.assertEqual(item["status"], "completed")
        finally:
            db.close()

    def test_frontend_replaces_legacy_score_workspace(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        start = html.index('id="section-avaliacao_docente"')
        end = html.index('id="section-resultados"', start)
        section = html[start:end]
        self.assertIn('data-faculty-view="overview"', section)
        self.assertIn('data-faculty-view="teachers"', section)
        self.assertIn('data-faculty-view="disciplines"', section)
        self.assertIn('data-faculty-view="questions"', section)
        self.assertIn('data-faculty-view="imports"', section)
        self.assertIn('id="facultyImportFile"', section)
        self.assertIn('class="faculty-source-status"', section)
        self.assertNotIn('id="meta-dtnh-02"', section)
        self.assertNotIn("nota 0–10", section)
        self.assertNotIn("média ponderada", section)
        self.assertIn('/static/js/faculty-evaluation.js', html)
        self.assertIn('/static/css/faculty-evaluation.css', html)


if __name__ == "__main__":
    unittest.main()
