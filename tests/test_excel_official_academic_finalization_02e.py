from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from academic_excel_cutover import build_cutover_manifest, write_cutover_manifest
from academic_excel_finalization import build_academic_finalization_report
from academic_excel_parity import audit_academic_payload_parity
from excel_official.constants import REQUIRED_INSTITUTIONAL_SHEETS
from release_info import APP_VERSION, SCHEMA_VERSION
from test_excel_official_academic_cutover_02c import _payload_02b


def _report(tmp_path: Path, code: str) -> Path:
    report = audit_academic_payload_parity(_payload_02b(code), source_kind="production")
    path = tmp_path / f"{code.lower()}.json"
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    return path


def _manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dtnh = _report(tmp_path, "DTNH")
    dcs = _report(tmp_path, "DCS")
    manifest = build_cutover_manifest(dtnh_report_path=dtnh, dcs_report_path=dcs)
    assert manifest.ready
    manifest_path, _ = write_cutover_manifest(manifest, tmp_path / "gate")
    return manifest_path, dtnh, dcs


def _smoke(tmp_path: Path, code: str, *, engine: str = "excel_official") -> Path:
    payload = {
        "report_version": 1,
        "status": "PASS",
        "directorate": code,
        "engine": engine,
        "app_version": APP_VERSION,
        "schema_version": str(SCHEMA_VERSION),
        "bytes": 12345,
        "sha256": "a" * 64,
        "sheets": list(REQUIRED_INSTITUTIONAL_SHEETS),
        "external_links": 0,
        "has_vba": False,
        "workbook_path": None,
    }
    path = tmp_path / f"smoke_{code.lower()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_02e_finalization_requires_both_post_cutover_excel_official_smokes(tmp_path):
    manifest, dtnh, dcs = _manifest(tmp_path)
    dtnh_smoke = _smoke(tmp_path, "DTNH")
    dcs_smoke = _smoke(tmp_path, "DCS")
    report = build_academic_finalization_report(
        manifest_path=manifest,
        dtnh_report_path=dtnh,
        dcs_report_path=dcs,
        dtnh_smoke_path=dtnh_smoke,
        dcs_smoke_path=dcs_smoke,
    )
    assert report.complete is True
    assert report.status == "COMPLETE"
    assert not report.issues


def test_02e_finalization_blocks_legacy_engine_smoke(tmp_path):
    manifest, dtnh, dcs = _manifest(tmp_path)
    report = build_academic_finalization_report(
        manifest_path=manifest,
        dtnh_report_path=dtnh,
        dcs_report_path=dcs,
        dtnh_smoke_path=_smoke(tmp_path, "DTNH", engine="academic_v3"),
        dcs_smoke_path=_smoke(tmp_path, "DCS"),
    )
    assert report.complete is False
    assert report.status == "BLOCKED"
    assert any(item.code == "smoke.engine" and item.directorate == "DTNH" for item in report.issues)


def test_02e_operational_scripts_execute_directly():
    root = Path(__file__).resolve().parents[1]
    for script in (
        "scripts/prepare_academic_excel_cutover.py",
        "scripts/smoke_academic_excel_cutover.py",
        "scripts/manage_academic_excel_cutover.py",
    ):
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


def test_02e_frontend_and_bootstrap_switch_to_excel_official_without_second_deploy():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert '"academic_official_active"' in app
    assert 'Excel_Oficial_{scope.directorate_code}.xlsx' in app
    assert 'data-academic-excel-button' in html
    assert "academic_official_active" in js
    assert "Baixar Excel Oficial" in js
    assert "Excel_Oficial_" in js


def test_02e_production_parity_endpoint_is_reitoria_only_and_scoped():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/api/admin/excel-official/academic/parity")' in app
    assert "Depends(require_fresh_reitoria)" in app
    assert "resolve_directorate_scope(db, ctx, code)" in app
    assert "audit_academic_repository_parity" in app
