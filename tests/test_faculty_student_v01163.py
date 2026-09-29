from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import requests

from survey_sei import SEIInstitutionalEvaluationConnector


def _response(text: str = "", *, content: bytes | None = None, content_type: str = "text/xml") -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = "https://sei.ivc.br/visaoAdministrativo/avaliacaoInstitucional/relatorio/avaliacaoInstitucionalRel.xhtml"
    response.headers["Content-Type"] = content_type
    response._content = content if content is not None else text.encode("utf-8")
    response.encoding = "utf-8"
    return response


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("relatorio.xlsx.placeholder", b"ok")
    return buffer.getvalue()


class FacultyStudentV01163Tests(unittest.TestCase):
    def test_har_phase2_parser_prefers_global_generate_button(self):
        text = """
        <partial-response><changes><update id="formQuestionarioSelecionar"><![CDATA[
          <form id="formQuestionarioSelecionar" name="formQuestionarioSelecionar">
            <input type="hidden" name="formQuestionarioSelecionar" value="formQuestionarioSelecionar">
            <input type="text" name="formQuestionarioSelecionar:questionarioRelVOs:j_idt290" value="">
            <input type="text" name="formQuestionarioSelecionar:questionarioRelVOs:j_idt300" value="">
            <a id="formQuestionarioSelecionar:questionarioRelVOs:0:botaoGerarRelatorioEmPDF4:botaoGerarRelatorioEmPDF4"></a>
            <a id="formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4">Gerar Relatório</a>
          </form>
        ]]></update></changes></partial-response>
        """
        self.assertEqual(
            SEIInstitutionalEvaluationConnector._bulk_report_source(text),
            "formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4",
        )
        self.assertTrue(SEIInstitutionalEvaluationConnector._has_bulk_report_stage(text))

    def test_generate_report_executes_second_sei_stage_before_zip_download(self):
        connector = SEIInstitutionalEvaluationConnector()
        connector.viewstate = "test-viewstate"
        connector.metadata = SimpleNamespace(question_count=9)
        connector._main_form_values = lambda: {"form": "form"}

        phase2_form = """
        <partial-response><changes><update id="formQuestionarioSelecionar"><![CDATA[
          <form id="formQuestionarioSelecionar" name="formQuestionarioSelecionar">
            <input type="hidden" name="formQuestionarioSelecionar" value="formQuestionarioSelecionar">
            <input type="text" name="formQuestionarioSelecionar:questionarioRelVOs:j_idt290" value="">
            <input type="text" name="formQuestionarioSelecionar:questionarioRelVOs:j_idt300" value="">
            <a id="formQuestionarioSelecionar:questionarioRelVOs:0:botaoGerarRelatorioEmPDF4:botaoGerarRelatorioEmPDF4"></a>
            <a id="formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4">Gerar Relatório</a>
          </form>
        ]]></update></changes></partial-response>
        """
        phase2_final = """
        <partial-response><changes><extension>
          <complete><![CDATA[location.href='/DownloadRelatorioSV?relatorio=AVAL_INST_TESTE.zip';]]></complete>
        </extension></changes></partial-response>
        """

        calls: list[dict[str, str]] = []
        phase = {"value": 1}

        def fake_ajax(url, data, *, referer):
            calls.append(dict(data))
            source = data.get("javax.faces.source")
            if source == "form:botaoGerarRelatorioEmExcel":
                return _response('<span class="otm-progressbar-footer-left">Item 0 de 1000000</span>')
            if source == "formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4":
                phase["value"] = 2
                return _response('<span class="otm-progressbar-footer-left">Item 0 de 82971</span>')
            if source == "statusPanelBaixa:statusPanelBaixa_pool2":
                current = "739 de 740" if phase["value"] == 2 else "1 de 1"
                return _response(f'<span class="otm-progressbar-footer-left">Item {current}</span>')
            if source == "statusPanelBaixa:statusPanelBaixa_encerrar":
                return _response("<script>executarOncomplete2();</script>")
            if source == "statusPanelBaixa:statusPanelBaixa_oncomplete2":
                return _response(phase2_form if phase["value"] == 1 else phase2_final)
            raise AssertionError(f"Unexpected SEI source: {source}")

        connector._ajax_post = fake_ajax
        file_response = _response(content=_zip_bytes(), content_type="application/octet-stream")
        file_response.url = "https://sei.ivc.br/DownloadRelatorioSV?relatorio=AVAL_INST_TESTE.zip"
        connector.session.get = Mock(return_value=file_response)

        report = connector.generate_report(max_wait_seconds=5, poll_interval=0)

        sources = [item.get("javax.faces.source") for item in calls]
        self.assertIn("form:botaoGerarRelatorioEmExcel", sources)
        self.assertIn("formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4", sources)
        self.assertEqual(sources.count("statusPanelBaixa:statusPanelBaixa_oncomplete2"), 2)
        bulk_payload = next(item for item in calls if item.get("javax.faces.source") == "formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4")
        self.assertIn("formQuestionarioSelecionar:questionarioRelVOs:j_idt290", bulk_payload)
        self.assertIn("formQuestionarioSelecionar:questionarioRelVOs:j_idt300", bulk_payload)
        self.assertEqual(report.filename, "AVAL_INST_TESTE.zip")
        self.assertEqual(report.kind, "zip")
        self.assertEqual(report.download_path, "/DownloadRelatorioSV?relatorio=AVAL_INST_TESTE.zip")
        self.assertEqual(report.progress.get("stage"), "a geração do pacote XLSX")

    def test_faculty_filters_are_searchable_comboboxes(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "index.html").read_text(encoding="utf-8")
        js = (root / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")
        shared_js = (root / "static" / "js" / "data-univc-ui.js").read_text(encoding="utf-8")
        shared_css = (root / "static" / "css" / "data-univc-foundation.css").read_text(encoding="utf-8")

        for field, placeholder in (
            ("facultyCourseFilter", "Buscar curso..."),
            ("facultyDisciplineFilter", "Buscar disciplina..."),
            ("facultyTeacherFilter", "Buscar docente..."),
        ):
            self.assertIn(f'id="{field}" data-combobox-placeholder="{placeholder}"', html)
        self.assertIn("function enhanceFacultyCombobox(select)", js)
        self.assertIn("DataUNIVC?.searchableSelect?.attach", js)
        self.assertIn("root.searchableSelect", shared_js)
        self.assertIn("const normalize = value", shared_js)
        self.assertIn("enhanceFacultyCombobox(course)", js)
        self.assertIn("enhanceFacultyCombobox(discipline)", js)
        self.assertIn("enhanceFacultyCombobox(teacher)", js)
        self.assertIn("du-combobox-menu", shared_css)
        self.assertIn("du-combobox-option", shared_css)

    def test_generate_loading_copy_mentions_two_sei_stages(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")
        self.assertIn("fará as duas etapas do SEI", js)
        self.assertIn("gerar os XLSX e baixar o ZIP final", js)


if __name__ == "__main__":
    unittest.main()
