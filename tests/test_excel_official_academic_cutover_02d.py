from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import excel_service
from academic_excel_cutover import (
    ENABLE_CONFIRMATION,
    activate_cutover,
    build_cutover_manifest,
    read_env_flag,
    rollback_cutover,
    verify_cutover_manifest,
    write_cutover_manifest,
)
from academic_excel_parity import audit_academic_payload_parity
from test_excel_official_academic_cutover_02c import _payload_02b


def _report_file(tmp_path: Path, directorate: str, *, source_kind: str = "production") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    report = audit_academic_payload_parity(_payload_02b(directorate), source_kind=source_kind)
    path = tmp_path / f"{directorate.lower()}.json"
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    return path


def _ready_pair(tmp_path: Path) -> tuple[Path, Path]:
    return _report_file(tmp_path, "DTNH"), _report_file(tmp_path, "DCS")


def test_02d_gate_requires_fresh_ready_production_reports(tmp_path):
    dtnh, dcs = _ready_pair(tmp_path)
    manifest = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs, max_age_hours=24)
    assert manifest.ready is True
    assert manifest.status == "READY"
    assert not manifest.issues
    assert {item.directorate for item in manifest.reports} == {"DTNH", "DCS"}
    assert all(len(item.sha256) == 64 for item in manifest.reports)
    assert manifest.expires_at


def test_02d_fixture_or_stale_evidence_cannot_activate_gate(tmp_path):
    dtnh = _report_file(tmp_path, "DTNH", source_kind="fixture")
    dcs = _report_file(tmp_path, "DCS", source_kind="production")
    fixture_gate = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs)
    assert fixture_gate.status == "BLOCKED"
    assert any(item.code == "report.source_kind" and item.directorate == "DTNH" for item in fixture_gate.issues)

    dtnh, dcs = _ready_pair(tmp_path / "stale")
    for path in (dtnh, dcs):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stale_gate = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs, max_age_hours=24)
    assert stale_gate.status == "BLOCKED"
    assert sum(item.code == "report.stale" for item in stale_gate.issues) == 2


def test_02d_gate_rejects_wrong_release_version(tmp_path):
    dtnh, dcs = _ready_pair(tmp_path)
    data = json.loads(dcs.read_text(encoding="utf-8"))
    data["system_version"] = "0.12.9"
    dcs.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs)
    assert gate.status == "BLOCKED"
    assert any(item.code == "report.app_version" and item.directorate == "DCS" for item in gate.issues)


def test_02d_activation_revalidates_hashes_and_requires_explicit_confirmation(tmp_path):
    dtnh, dcs = _ready_pair(tmp_path)
    manifest = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs)
    manifest_path, _ = write_cutover_manifest(manifest, tmp_path / "gate")
    env = tmp_path / ".env.production"
    env.write_text("ENVIRONMENT=production\nACADEMIC_EXCEL_OFFICIAL_ENABLED=false\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Activation requires"):
        activate_cutover(
            manifest_path=manifest_path,
            dtnh_report_path=dtnh,
            dcs_report_path=dcs,
            env_path=env,
            confirmation="yes",
        )

    _manifest, backup, changed = activate_cutover(
        manifest_path=manifest_path,
        dtnh_report_path=dtnh,
        dcs_report_path=dcs,
        env_path=env,
        confirmation=ENABLE_CONFIRMATION,
    )
    assert changed is True
    assert backup is not None and backup.exists()
    assert read_env_flag(env) is True
    assert "ACADEMIC_EXCEL_OFFICIAL_ENABLED=false" in backup.read_text(encoding="utf-8")


def test_02d_changed_report_invalidates_existing_manifest(tmp_path):
    dtnh, dcs = _ready_pair(tmp_path)
    manifest = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs)
    manifest_path, _ = write_cutover_manifest(manifest, tmp_path / "gate")
    data = json.loads(dtnh.read_text(encoding="utf-8"))
    data["notes"] = ["changed after approval"]
    dtnh.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence changed"):
        verify_cutover_manifest(manifest_path=manifest_path, dtnh_report_path=dtnh, dcs_report_path=dcs)


def test_02d_rollback_is_always_available_and_atomic(tmp_path):
    env = tmp_path / ".env.production"
    env.write_text("ENVIRONMENT=production\nACADEMIC_EXCEL_OFFICIAL_ENABLED=true\n", encoding="utf-8")
    backup, changed = rollback_cutover(env_path=env)
    assert changed is True
    assert backup is not None and backup.exists()
    assert read_env_flag(env) is False


def test_02d_engine_name_is_observable_from_flag(monkeypatch):
    monkeypatch.delenv("ACADEMIC_EXCEL_OFFICIAL_ENABLED", raising=False)
    assert excel_service.selected_academic_excel_engine() == "excel_official"
    monkeypatch.setenv("ACADEMIC_EXCEL_OFFICIAL_ENABLED", "true")
    assert excel_service.selected_academic_excel_engine() == "excel_official"

def test_02d_management_cli_executes_directly_from_project_root(tmp_path):
    env = tmp_path / ".env.production"
    env.write_text("ACADEMIC_EXCEL_OFFICIAL_ENABLED=false\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/manage_academic_excel_cutover.py", "status", "--env-file", str(env)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ACADEMIC_EXCEL_OFFICIAL_ENABLED=false" in result.stdout


def test_02d_operational_scripts_can_be_invoked_directly():
    root = Path(__file__).resolve().parents[1]
    for script in ("scripts/audit_academic_excel_parity.py", "scripts/smoke_academic_excel_cutover.py"):
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"
        assert "usage:" in result.stdout.lower()

