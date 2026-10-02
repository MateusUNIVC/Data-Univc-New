from __future__ import annotations

import subprocess
import sys
from io import BytesIO
from pathlib import Path

import dadm_excel_service
from dadm_excel_service import export_dadm_excel, selected_dadm_excel_engine


def test_04c_dadm_flag_defaults_to_excel_official(monkeypatch):
    monkeypatch.delenv("DADM_EXCEL_OFFICIAL_ENABLED", raising=False)
    assert selected_dadm_excel_engine() == "excel_official"


def test_04c_dadm_flag_selects_excel_official(monkeypatch):
    monkeypatch.setenv("DADM_EXCEL_OFFICIAL_ENABLED", "true")
    assert selected_dadm_excel_engine() == "excel_official"


def test_04c_service_uses_official_builder_when_enabled(monkeypatch):
    sentinel = BytesIO(b"official")
    called = {}

    def fake_official(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        return sentinel

    monkeypatch.setenv("DADM_EXCEL_OFFICIAL_ENABLED", "true")
    monkeypatch.setattr(dadm_excel_service, "build_dadm_excel_official_workbook_bytes", fake_official)
    result = export_dadm_excel(
        object(), 7, "2026-08", "2026-09",
        department="secretaria", employee="e1", channel="whatsapp",
        allowed_departments=("secretaria",), generated_by="qa@univc.br",
    )
    assert result is sentinel
    assert called["args"][1] == 7
    assert called["kwargs"]["department"] == "secretaria"
    assert called["kwargs"]["allowed_departments"] == ("secretaria",)
    assert called["kwargs"]["generated_by"] == "qa@univc.br"


def test_04c_service_uses_v2_builder_when_flag_is_off(monkeypatch):
    sentinel = BytesIO(b"legacy")
    called = {}

    def fake_v2(*args, **kwargs):
        called["kwargs"] = kwargs
        return sentinel, {"period": {}}

    monkeypatch.setenv("DADM_EXCEL_OFFICIAL_ENABLED", "false")
    monkeypatch.setattr(dadm_excel_service, "build_dadm_v2_report", fake_v2)
    result = export_dadm_excel(object(), 3, "2026-07", "2026-09", channel="email")
    assert result is sentinel
    assert called["kwargs"]["channel"] == "email"


def test_04c_dadm_ui_uses_only_canonical_excel_endpoint():
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates" / "dadm_v2.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "dadm_v2.js").read_text(encoding="utf-8")
    assert "dadm_excel_official" in template
    assert "Excel Oficial" in template
    assert "NS.buildUrl('/api/dadm/excel'" in js
    assert "/api/dadm/v2/report.xlsx" not in js


def test_04c_routes_have_engine_header_alias_and_reitoria_parity_gate():
    root = Path(__file__).resolve().parents[1]
    router = (root / "dadm_v2_router.py").read_text(encoding="utf-8")
    legacy_router = (root / "dadm_router.py").read_text(encoding="utf-8")
    assert '@router.get("/api/dadm/excel")' in router
    assert '"X-Data-UNIVC-Excel-Engine": engine' in router
    assert 'filename = "Excel_Oficial_DADM.xlsx" if engine == "excel_official" else "Relatorio_DADM_TALLOS_V2.xlsx"' in router
    assert '@router.get("/api/dadm/v2/report.xlsx")' in router
    assert "return dadm_excel(" in router
    assert '@router.get("/api/admin/excel-official/dadm/parity")' in router
    assert "Depends(require_fresh_reitoria)" in router
    assert 'source_kind="production"' in router
    assert '@router.get("/api/dadm/excel")' not in legacy_router
    assert '@router.get("/api/dadm/legacy/excel")' in legacy_router


def test_04c_excel_official_is_enabled_by_default_in_env_examples():
    root = Path(__file__).resolve().parents[1]
    for name in (".env.example", ".env.production.example"):
        text = (root / name).read_text(encoding="utf-8")
        assert "DADM_EXCEL_OFFICIAL_ENABLED=true" in text


def test_04c_smoke_cli_is_directly_executable():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_dadm_excel_cutover.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "DATA_UNIVC_DADM_COOKIE" in result.stdout
