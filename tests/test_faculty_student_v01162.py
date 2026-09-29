from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from survey_faculty_student import (
    FACULTY_STUDENT_DETAIL_VALUE,
    FACULTY_STUDENT_TURN_VALUE,
    FACULTY_STUDENT_UNIT_VALUE,
)
from survey_router import _prepare_faculty_student_sei


class FacultyStudentV01162Tests(unittest.TestCase):
    def test_faculty_direct_sei_and_manual_upload_are_distinct_actions(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        js = (root / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")

        section = html[html.index('id="section-avaliacao_docente"'):html.index('id="section-resultados"')]
        self.assertIn('id="facultyImportButton"', section)
        self.assertIn('Buscar direto no SEI', section)
        self.assertIn('id="facultyFileImportButton"', section)
        self.assertIn('Usar XLSX/ZIP já baixado', section)

        direct_start = js.index("  function triggerImport()")
        direct_end = js.index("  function renderFacultySeiLoginStep()")
        direct_body = js[direct_start:direct_end]
        self.assertIn("Buscar relatório direto no SEI", direct_body)
        self.assertNotIn("input.click()", direct_body)

        file_start = js.index("  function triggerFileImport()")
        file_end = js.index("  function triggerImport()")
        file_body = js[file_start:file_end]
        self.assertIn("input.click()", file_body)

    def test_faculty_direct_sei_flow_uses_protected_backend_contract(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")

        self.assertIn("'/api/surveys/sei/login'", js)
        self.assertIn("'/api/surveys/sei/evaluations/search'", js)
        self.assertIn("'/api/surveys/sei/evaluations/select'", js)
        self.assertIn("`${API_BASE}/sei/prepare`", js)
        self.assertIn("`${API_BASE}/sei/report/generate`", js)
        self.assertIn("Disciplina/Professor", js)
        self.assertIn("Graduação · São Mateus", js)
        self.assertIn("triggerFileImport", js)

    def test_backend_prepare_locks_faculty_report_scope(self):
        questionnaire = SimpleNamespace(
            sei_id="28",
            name="Avaliação Institucional discente 2023.2 - aluno avalia professor",
        )
        metadata = SimpleNamespace(
            questionnaires=[questionnaire],
            selected_questionnaire_id=None,
            unit_options=[SimpleNamespace(value=FACULTY_STUDENT_UNIT_VALUE, label="CENTRO UNIVERSITÁRIO VALE DO CRICARÉ - GRADUAÇÃO (SÃO MATEUS-ES)")],
            detail_options=[SimpleNamespace(value=FACULTY_STUDENT_DETAIL_VALUE, label="Disciplina/Professor")],
            turn_options=[SimpleNamespace(value=FACULTY_STUDENT_TURN_VALUE, label="TODOS")],
        )

        class FakeConnector:
            def __init__(self):
                self.metadata = metadata
                self.selected = None
                self.configured = None

            def select_questionnaire(self, questionnaire_id):
                self.selected = questionnaire_id
                self.metadata.selected_questionnaire_id = questionnaire_id
                return self.metadata

            def configure_report(self, *, detail_value, unit_value, turn_value):
                self.configured = (detail_value, unit_value, turn_value)
                return self.metadata

            def prepare_all_questions(self):
                return self.metadata

        connector = FakeConnector()
        result = _prepare_faculty_student_sei(connector)
        self.assertIs(result, metadata)
        self.assertEqual(connector.selected, "28")
        self.assertEqual(
            connector.configured,
            (FACULTY_STUDENT_DETAIL_VALUE, FACULTY_STUDENT_UNIT_VALUE, FACULTY_STUDENT_TURN_VALUE),
        )


if __name__ == "__main__":
    unittest.main()
