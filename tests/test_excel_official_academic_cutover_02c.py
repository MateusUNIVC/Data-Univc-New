from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import academic_excel_official
import academic_excel_parity
import academic_excel_v3_builder
import excel_service
from academic_excel_parity import AcademicCutoverReadiness, audit_academic_payload_parity
from test_excel_official_academic_adapter_v1 import _payload


def _payload_02b(directorate: str = "DTNH") -> dict:
    payload = _payload(directorate)
    payload["institution_students_by_course"] = [
        {"periodo": "2026-SEM1", "curso": "Administração", "respondentes": 80, "promotores": 48, "neutros": 20, "detratores": 12, "valor": 45.0},
        {"periodo": "2026-SEM1", "curso": "Psicologia", "respondentes": 100, "promotores": 57, "neutros": 25, "detratores": 18, "valor": 39.0},
        {"periodo": "2026-SEM2", "curso": "Administração", "respondentes": 110, "promotores": 70, "neutros": 25, "detratores": 15, "valor": 50.0},
        {"periodo": "2026-SEM2", "curso": "Psicologia", "respondentes": 90, "promotores": 50, "neutros": 20, "detratores": 20, "valor": 33.3333},
    ]
    payload["initial"].update({"window": 4, "matrix_kpi": "01A · NPS Instituição · Alunos"})
    return payload


def test_02c_fixture_parity_is_candidate_pass_not_production_ready():
    report = audit_academic_payload_parity(_payload_02b(), source_kind="fixture")
    assert report.semantic_passed is True
    assert report.source_quality_ok is True
    assert report.new_release_allowed is True
    assert report.legacy_workbook is not None and report.legacy_workbook.build_ok is True
    assert report.new_workbook is not None and report.new_workbook.build_ok is True
    assert report.cutover_status == "CANDIDATE_PASS"
    assert len(report.cases) > 30
    assert not report.failures


def test_02c_payload_reported_drift_blocks_cutover():
    payload = _payload_02b()
    payload["institution_students"][1]["valor"] = 99.0
    report = audit_academic_payload_parity(payload, source_kind="production", build_workbooks=False)
    assert report.semantic_passed is False
    assert report.cutover_status == "BLOCKED"
    assert any(item.source == "payload_reported_vs_components" for item in report.failures)


def test_02c_source_quality_failure_blocks_even_when_metrics_match():
    payload = _payload_02b()
    payload["quality"]["result_inconsistent_rows"] = 2
    report = audit_academic_payload_parity(payload, source_kind="production")
    assert report.source_quality_ok is False
    assert report.cutover_status == "BLOCKED"
    assert any("result" in item.lower() for item in report.source_quality_notes)


def test_02c_cross_directorate_ready_requires_both_production_reports_same_versions():
    dtnh = audit_academic_payload_parity(_payload_02b("DTNH"), source_kind="production")
    dcs = audit_academic_payload_parity(_payload_02b("DCS"), source_kind="production")
    readiness = AcademicCutoverReadiness((dtnh, dcs))
    assert dtnh.cutover_status == "READY"
    assert dcs.cutover_status == "READY"
    assert readiness.status == "READY"

    mismatch = replace(dcs, schema_version="999")
    assert AcademicCutoverReadiness((dtnh, mismatch)).status == "BLOCKED"
    assert AcademicCutoverReadiness((dtnh,)).status == "BLOCKED"


def test_02c_default_feature_flag_keeps_current_v3_engine(monkeypatch):
    legacy = BytesIO(b"legacy")
    new = BytesIO(b"new")
    monkeypatch.delenv("ACADEMIC_EXCEL_OFFICIAL_ENABLED", raising=False)
    monkeypatch.setattr(academic_excel_v3_builder, "build_academic_interactive_workbook_bytes", lambda repo, **kwargs: legacy)
    monkeypatch.setattr(academic_excel_official, "build_academic_excel_official_workbook_bytes", lambda repo, **kwargs: new)

    result = excel_service.export_academic_interactive_excel(object(), reference="2026-SEM2")
    assert result is legacy


def test_02c_cutover_feature_flag_selects_excel_official(monkeypatch):
    legacy = BytesIO(b"legacy")
    new = BytesIO(b"new")
    monkeypatch.setenv("ACADEMIC_EXCEL_OFFICIAL_ENABLED", "true")
    monkeypatch.setattr(academic_excel_v3_builder, "build_academic_interactive_workbook_bytes", lambda repo, **kwargs: legacy)
    monkeypatch.setattr(academic_excel_official, "build_academic_excel_official_workbook_bytes", lambda repo, **kwargs: new)

    result = excel_service.export_academic_interactive_excel(object(), course="Psicologia")
    assert result is new


def test_02c_report_serialization_contains_cutover_evidence():
    report = audit_academic_payload_parity(_payload_02b(), source_kind="fixture")
    data = report.to_dict()
    assert data["summary"]["cutover_status"] == "CANDIDATE_PASS"
    assert data["summary"]["failures"] == 0
    markdown = report.to_markdown()
    assert "Academic Excel Parity Report" in markdown
    assert "CANDIDATE_PASS" in markdown
    assert "academic_v3_legacy" in markdown
    assert "excel_official_core" in markdown
