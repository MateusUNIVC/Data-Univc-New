from __future__ import annotations

import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import AcademicResult, AcademicStudent, Course, Directorate, Discipline
from repository import DatabaseRepository
from security import AuthorizationContext


class AcademicResultsV01167Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = Session()
        self.directorate = Directorate(code="DTNH", name="DTNH", active=True)
        self.db.add(self.directorate); self.db.flush()
        self.course = Course(directorate_id=self.directorate.id, name="Administração", modality="Presencial", active=True, valid_from="2020-01")
        self.db.add(self.course); self.db.flush()
        self.discipline = Discipline(course_id=self.course.id, name="Gestão", active=True, valid_from="2020-01")
        self.db.add(self.discipline); self.db.flush()
        self.user = AuthorizationContext(
            user_id=str(uuid.uuid4()), email="ux67@univc.edu.br", full_name="UX 67",
            role="editor", directorate_id=self.directorate.id, directorate_code="DTNH", directorate_name="DTNH",
        )
        self.repo = DatabaseRepository(self.db, self.user)

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def add_result(self, registration: str, approved):
        student = AcademicStudent(
            directorate_id=self.directorate.id, registration=registration, name=f"Aluno {registration}",
            course_id=self.course.id, active=True,
        )
        self.db.add(student); self.db.flush()
        self.db.add(AcademicResult(
            directorate_id=self.directorate.id, period="2026-SEM1", course_id=self.course.id,
            discipline_id=self.discipline.id, student_id=student.id, class_group="ADM1",
            final_average=None, official_status="Cursando", approved=approved, failure_reason=None, source="test",
        ))
        self.db.commit()
        return student

    def test_only_pending_student_is_quality_issue_not_main_status(self):
        student = self.add_result("MPEND", None)
        summary = self.repo.academic_result_student_summary({"periodo": "2026-SEM1"})
        self.assertEqual(summary["alunos_distintos"], 1)
        self.assertEqual(summary["alunos_aprovados"], 0)
        self.assertEqual(summary["alunos_com_reprovacao"], 0)
        self.assertEqual(summary["alunos_sem_classificacao"], 1)
        self.assertEqual(summary["alunos_com_resultado_pendente"], 1)
        self.assertTrue(summary["reconciliado"])
        pending = self.repo.list_results_page({"periodo": "2026-SEM1", "resultado": "aluno_pendente"}, page=1, page_size=50)
        self.assertEqual(pending["total"], 1)
        self.assertEqual(pending["items"][0]["matricula"], student.registration)

    def test_frontend_has_two_main_student_statuses(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("{label:'Aprovados'", js)
        self.assertIn("{label:'Com reprovação'", js)
        self.assertNotIn("{label:'Sem fechamento'", js)
        self.assertNotIn("alerta de qualidade", html)
        self.assertNotIn("aluno(s) ainda sem resultado classificável", js)


if __name__ == "__main__":
    unittest.main()
