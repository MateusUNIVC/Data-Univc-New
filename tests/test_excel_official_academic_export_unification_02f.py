from __future__ import annotations

from io import BytesIO
from pathlib import Path

import academic_excel_official
import excel_service


class _Repo:
    directorate_code = "DTNH"


def test_02f_generic_academic_export_uses_excel_official(monkeypatch):
    sentinel = BytesIO(b"official")
    captured = {}

    def fake_builder(repo, **kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(academic_excel_official, "build_academic_excel_official_workbook_bytes", fake_builder)
    result = excel_service.export_formatted_excel(
        _Repo(),
        granularity="semestral",
        reference="2026/2",
        comparison="2026/1",
        course="Psicologia",
        discipline="Disciplina A",
        window_periods=6,
    )
    assert result is sentinel
    assert captured == {
        "reference": "2026/2",
        "comparison": "2026/1",
        "course": "Psicologia",
        "discipline": "Disciplina A",
        "window_periods": 6,
    }


def test_02f_academic_ui_exposes_single_official_excel_path():
    root = Path(__file__).resolve().parents[1]
    html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    section = html.split('<section id="section-arquivos"', 1)[1].split('</section>', 1)[0]

    assert 'href="/api/excel-interativo"' not in section
    assert "Snapshot" not in section
    assert "Base consolidada" not in section
    assert section.count('href="/api/excel"') == 2
    assert section.count("Baixar Excel Oficial") == 2
    assert "Excel Oficial · DTNH" in section


def test_02f_api_excel_identifies_official_academic_download():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'filename = f"Excel_Oficial_{scope.directorate_code}.xlsx"' in app
    assert 'headers["X-Data-UNIVC-Excel-Engine"] = "excel_official"' in app


def test_02f_frontend_uses_official_language_without_snapshot_copy():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "const academicExcelName = 'Excel Oficial';" in js
    assert "Baixar Excel Oficial" in js
    assert "Baixa o snapshot oficial autorizado" not in js
    assert "Excel_Oficial_" in js
