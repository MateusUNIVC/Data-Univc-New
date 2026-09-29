from __future__ import annotations

import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import AcademicResult, AcademicStudent, Course, Directorate, Discipline
from repository import DatabaseRepository
from security import AuthorizationContext


class AcademicResultsV01165Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = Session()
        self.directorate = Directorate(code="DTNH", name="DTNH", active=True)
        self.db.add(self.directorate); self.db.flush()
        self.course = Course(directorate_id=self.directorate.id, name="Administração", modality="Presencial", active=True, valid_from="2020-01")
        self.db.add(self.course); self.db.flush()
        self.d1 = Discipline(course_id=self.course.id, name="Gestão I", active=True, valid_from="2020-01")
        self.d2 = Discipline(course_id=self.course.id, name="Gestão II", active=True, valid_from="2020-01")
        self.db.add_all([self.d1, self.d2]); self.db.flush()
        self.user = AuthorizationContext(
            user_id=str(uuid.uuid4()), email="ux@univc.edu.br", full_name="UX Test",
            role="editor", directorate_id=self.directorate.id, directorate_code="DTNH", directorate_name="DTNH",
        )
        self.repo = DatabaseRepository(self.db, self.user)

        students = {}
        for code in "ABCDE":
            student = AcademicStudent(
                directorate_id=self.directorate.id, registration=f"M{code}", name=f"Aluno {code}",
                course_id=self.course.id, active=True,
            )
            self.db.add(student); self.db.flush(); students[code] = student

        def add(code, disc, approved, reason=None, avg=8.0, status=None):
            if status is None:
                status = "Aprovado" if approved is True else "Reprovado" if approved is False else "Em andamento"
            self.db.add(AcademicResult(
                directorate_id=self.directorate.id, period="2026-SEM1", course_id=self.course.id,
                discipline_id=disc.id, student_id=students[code].id, class_group="ADM1",
                final_average=avg, official_status=status, approved=approved, failure_reason=reason, source="test",
            ))

        # A: integralmente aprovado.
        add("A", self.d1, True); add("A", self.d2, True)
        # B: possui aprovação e reprovação por nota.
        add("B", self.d1, True); add("B", self.d2, False, "nota", 4.0)
        # C: reprova por nota e por falta em disciplinas diferentes (sobreposição intencional).
        add("C", self.d1, False, "nota", 3.0); add("C", self.d2, False, "falta", 6.0)
        # D: sem reprovação, porém ainda com uma disciplina pendente.
        add("D", self.d1, True); add("D", self.d2, None, None, None)
        # E: integralmente aprovado.
        add("E", self.d1, True); add("E", self.d2, True)
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_student_summary_reconciles_distinct_people(self):
        summary = self.repo.academic_result_student_summary({"periodo": "2026-SEM1", "curso": "Administração"})
        self.assertEqual(summary["alunos_distintos"], 5)
        self.assertEqual(summary["alunos_aprovados"], 3)
        self.assertEqual(summary["alunos_aprovados_integralmente"], 3)
        self.assertEqual(summary["alunos_com_reprovacao"], 2)
        self.assertEqual(summary["alunos_sem_fechamento"], 0)
        self.assertEqual(summary["alunos_sem_classificacao"], 0)
        self.assertEqual(summary["alunos_com_resultado_pendente"], 1)
        self.assertEqual(summary["alunos_reprovados_nota"], 2)
        self.assertEqual(summary["alunos_reprovados_falta"], 1)
        self.assertTrue(summary["reconciliado"])
        self.assertTrue(summary["motivos_podem_sobrepor"])

    def test_quick_filters_return_exact_failed_rows(self):
        grade = self.repo.list_results_page(
            {"periodo": "2026-SEM1", "curso": "Administração", "resultado": "nota"}, page=1, page_size=50,
        )
        self.assertEqual(grade["total"], 2)
        self.assertEqual({item["aluno"] for item in grade["items"]}, {"Aluno B", "Aluno C"})
        absence = self.repo.list_results_page(
            {"periodo": "2026-SEM1", "curso": "Administração", "resultado": "falta"}, page=1, page_size=50,
        )
        self.assertEqual(absence["total"], 1)
        self.assertEqual(absence["items"][0]["aluno"], "Aluno C")

    def test_student_level_filters_use_reconciled_classification(self):
        approved = self.repo.list_results_page(
            {"periodo": "2026-SEM1", "curso": "Administração", "resultado": "aluno_aprovado"}, page=1, page_size=50,
        )
        self.assertEqual({item["aluno"] for item in approved["items"]}, {"Aluno A", "Aluno D", "Aluno E"})
        failed = self.repo.list_results_page(
            {"periodo": "2026-SEM1", "curso": "Administração", "resultado": "aluno_reprovado"}, page=1, page_size=50,
        )
        self.assertEqual({item["aluno"] for item in failed["items"]}, {"Aluno B", "Aluno C"})
        self.assertTrue(all(item["aprovado"] is False for item in failed["items"]))
        pending = self.repo.list_results_page(
            {"periodo": "2026-SEM1", "curso": "Administração", "resultado": "aluno_pendente"}, page=1, page_size=50,
        )
        self.assertEqual(pending["total"], 0)

    def test_trend_exposes_distinct_student_population(self):
        trend = self.repo.academic_result_trend({"curso": "Administração"})
        self.assertEqual(len(trend), 1)
        point = trend[0]
        self.assertEqual(point["alunos_distintos"], 5)
        self.assertEqual(point["alunos_aprovados"], 3)
        self.assertEqual(point["alunos_aprovados_integralmente"], 3)
        self.assertEqual(point["alunos_com_reprovacao"], 2)
        self.assertEqual(point["alunos_sem_fechamento"], 0)
        self.assertEqual(point["alunos_com_resultado_pendente"], 1)
        # O campo legado de finalização continua disponível para consumidores anteriores.
        self.assertEqual(point["alunos_finalizados"], 5)

    def test_frontend_cards_are_actionable_and_distinguish_students_from_results(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Alunos distintos", js)
        self.assertIn("alunos_aprovados", js)
        self.assertIn("data-result-outcome", js)
        self.assertNotIn("{label:'Sem fechamento'", js)
        self.assertIn("resultado", js)
        self.assertIn("Alunos distintos — evolução", html)
        self.assertIn("Alunos e resultados são medidas diferentes", html)


if __name__ == "__main__":
    unittest.main()
