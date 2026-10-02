from __future__ import annotations

import subprocess
import sys
from io import BytesIO
from pathlib import Path

import dpe_excel_service
from dpe_excel_cutover import audit_dpe_cutover_readiness
from dpe_excel_service import export_dpe_excel, selected_dpe_excel_engine
from tests.test_excel_official_dpe_adapter import _payload


def test_05c_dpe_flag_defaults_to_modern(monkeypatch):
    monkeypatch.delenv("DPE_EXCEL_OFFICIAL_ENABLED", raising=False)
    assert selected_dpe_excel_engine() == "dpe_modern"


def test_05c_dpe_flag_selects_excel_official(monkeypatch):
    monkeypatch.setenv("DPE_EXCEL_OFFICIAL_ENABLED", "true")
    assert selected_dpe_excel_engine() == "excel_official"


def test_05c_service_uses_official_builder_when_enabled(monkeypatch):
    sentinel = BytesIO(b"official")

    class Artifact:
        def to_bytes(self):
            return sentinel

    called = {}
    def fake_official(payload, **kwargs):
        called["payload"] = payload
        called["kwargs"] = kwargs
        return Artifact()

    payload = _payload()
    monkeypatch.setenv("DPE_EXCEL_OFFICIAL_ENABLED", "true")
    monkeypatch.setattr(dpe_excel_service, "build_dpe_excel_official_artifact_from_payload", fake_official)
    result = export_dpe_excel(payload, generated_by="qa@univc.br")
    assert result is sentinel
    assert called["payload"] is payload
    assert called["kwargs"]["generated_by"] == "qa@univc.br"
    assert called["kwargs"]["authorization_scope"] == ("DPE",)


def test_05c_service_uses_modern_builder_when_flag_is_off(monkeypatch):
    sentinel = BytesIO(b"legacy")
    payload = _payload()
    monkeypatch.setenv("DPE_EXCEL_OFFICIAL_ENABLED", "false")
    monkeypatch.setattr(dpe_excel_service, "build_dpe_operational_workbook", lambda value: sentinel)
    assert export_dpe_excel(payload) is sentinel


def test_05c_cutover_readiness_requires_semantics_builds_and_release():
    fixture = audit_dpe_cutover_readiness(_payload(), source_kind="fixture", generated_by="qa@univc.br")
    assert fixture.cutover_status == "CANDIDATE_PASS"
    assert len(fixture.semantic_report.cases) >= 55
    assert not fixture.failures
    assert fixture.legacy_workbook and fixture.legacy_workbook.build_ok
    assert fixture.new_workbook and fixture.new_workbook.build_ok
    assert fixture.new_release_allowed is True

    production = audit_dpe_cutover_readiness(_payload(), source_kind="production", generated_by="qa@univc.br")
    assert production.cutover_status == "READY"
    assert production.to_dict()["summary"]["failures"] == 0


def test_05c_cutover_blocks_semantic_drift():
    payload = _payload()
    payload["analytics"]["courses"][0]["allocated_cost"] = 99999.0
    report = audit_dpe_cutover_readiness(payload, source_kind="production", build_workbooks=False)
    assert report.cutover_status == "BLOCKED"
    assert report.failures


def test_05c_route_ui_and_reitoria_gate_are_canonical():
    root = Path(__file__).resolve().parents[1]
    router = (root / "dpe_router.py").read_text(encoding="utf-8")
    template = (root / "templates" / "dpe.html").read_text(encoding="utf-8")
    assert router.count('@router.get("/api/dpe/excel")') == 1
    assert '"X-Data-UNIVC-Excel-Engine": engine' in router
    assert 'filename = "Excel_Oficial_DPE.xlsx" if engine == "excel_official"' in router
    assert '@router.get("/api/admin/excel-official/dpe/parity")' in router
    assert "Depends(require_fresh_reitoria)" in router
    assert 'source_kind="production"' in router
    assert "dpe_excel_official" in template
    assert "Excel Oficial" in template


def test_05c_flag_is_fail_closed_in_env_examples():
    root = Path(__file__).resolve().parents[1]
    for name in (".env.example", ".env.production.example"):
        assert "DPE_EXCEL_OFFICIAL_ENABLED=false" in (root / name).read_text(encoding="utf-8")


def test_05c_smoke_cli_is_directly_executable():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_dpe_excel_cutover.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "DATA_UNIVC_DPE_COOKIE" in result.stdout
