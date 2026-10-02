from __future__ import annotations

from pathlib import Path

import dadm_excel_service
import dm_excel_service
import dpe_excel_service
import excel_service


def test_all_directorates_default_to_excel_official(monkeypatch):
    for name in (
        "ACADEMIC_EXCEL_OFFICIAL_ENABLED",
        "DM_EXCEL_OFFICIAL_ENABLED",
        "DADM_EXCEL_OFFICIAL_ENABLED",
        "DPE_EXCEL_OFFICIAL_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    assert excel_service.selected_academic_excel_engine() == "excel_official"
    assert dm_excel_service.selected_dm_excel_engine() == "excel_official"
    assert dadm_excel_service.selected_dadm_excel_engine() == "excel_official"
    assert dpe_excel_service.selected_dpe_excel_engine() == "excel_official"


def test_false_remains_explicit_rollback(monkeypatch):
    monkeypatch.setenv("ACADEMIC_EXCEL_OFFICIAL_ENABLED", "false")
    monkeypatch.setenv("DM_EXCEL_OFFICIAL_ENABLED", "false")
    monkeypatch.setenv("DADM_EXCEL_OFFICIAL_ENABLED", "false")
    monkeypatch.setenv("DPE_EXCEL_OFFICIAL_ENABLED", "false")
    assert excel_service.selected_academic_excel_engine() == "academic_v3"
    assert dm_excel_service.selected_dm_excel_engine() == "dm_v2"
    assert dadm_excel_service.selected_dadm_excel_engine() == "dadm_v2"
    assert dpe_excel_service.selected_dpe_excel_engine() == "dpe_modern"


def test_env_examples_enable_all_official_exports_by_default():
    root = Path(__file__).resolve().parents[1]
    for filename in (".env.example", ".env.production.example"):
        text = (root / filename).read_text(encoding="utf-8")
        for flag in (
            "ACADEMIC_EXCEL_OFFICIAL_ENABLED",
            "DM_EXCEL_OFFICIAL_ENABLED",
            "DADM_EXCEL_OFFICIAL_ENABLED",
            "DPE_EXCEL_OFFICIAL_ENABLED",
        ):
            assert f"{flag}=true" in text


def test_canonical_ui_routes_remain_single_primary_exports():
    root = Path(__file__).resolve().parents[1]
    dm = (root / "templates" / "dm.html").read_text(encoding="utf-8")
    dadm = (root / "static" / "js" / "dadm_v2.js").read_text(encoding="utf-8")
    dpe = (root / "static" / "js" / "dpe_v2.js").read_text(encoding="utf-8")
    academic = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert '/api/dm/excel' in dm
    assert "NS.buildUrl('/api/dadm/excel'" in dadm
    assert '/api/dpe/excel' in dpe
    assert "academicExcelUrl(baseUrl = '/api/excel')" in academic
