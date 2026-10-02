from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from academic_excel_cutover import verify_cutover_manifest
from excel_official.constants import REQUIRED_INSTITUTIONAL_SHEETS
from release_info import APP_VERSION, SCHEMA_VERSION

FINALIZATION_REPORT_VERSION = 1


@dataclass(frozen=True, slots=True)
class FinalizationIssue:
    code: str
    message: str
    directorate: str | None = None


@dataclass(frozen=True, slots=True)
class AcademicFinalizationReport:
    report_version: int
    status: str
    generated_at: str
    manifest_id: str | None
    app_version: str
    schema_version: str
    smoke_evidence: tuple[dict[str, Any], ...]
    issues: tuple[FinalizationIssue, ...]

    @property
    def complete(self) -> bool:
        return self.status == "COMPLETE" and not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version,
            "status": self.status,
            "complete": self.complete,
            "generated_at": self.generated_at,
            "manifest_id": self.manifest_id,
            "app_version": self.app_version,
            "schema_version": self.schema_version,
            "smoke_evidence": list(self.smoke_evidence),
            "issues": [asdict(item) for item in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        lines = [
            "# Academic Excel Official — Finalization",
            "",
            f"Status: **{self.status}**",
            "",
            f"- Generated at: `{self.generated_at}`",
            f"- App version: `{self.app_version}`",
            f"- Schema version: `{self.schema_version}`",
            f"- Cutover manifest: `{self.manifest_id or 'n/a'}`",
            "",
            "## Production smoke evidence",
            "",
            "| Diretoria | Status | Engine | Bytes | SHA-256 |",
            "|---|---|---|---:|---|",
        ]
        for item in self.smoke_evidence:
            lines.append(
                f"| {item.get('directorate', '—')} | {item.get('status', '—')} | "
                f"{item.get('engine', '—')} | {item.get('bytes', 0)} | "
                f"`{str(item.get('sha256') or '')[:16]}...` |"
            )
        if self.issues:
            lines.extend(["", "## Blocking issues", ""])
            for issue in self.issues:
                scope = f" [{issue.directorate}]" if issue.directorate else ""
                lines.append(f"- `{issue.code}`{scope}: {issue.message}")
        else:
            lines.extend(
                [
                    "",
                    "## Acceptance",
                    "",
                    "DTNH and DCS passed authenticated post-cutover smoke validation while serving "
                    "`excel_official`, with the same application/schema version approved by the cutover manifest.",
                    "",
                    "The Academic migration can be considered operationally complete. Keep Academic V3 during the observation window for rollback.",
                ]
            )
        lines.append("")
        return "\n".join(lines)


def _load_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{target}: expected JSON object")
    return data


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_academic_finalization_report(
    *,
    manifest_path: str | Path,
    dtnh_report_path: str | Path,
    dcs_report_path: str | Path,
    dtnh_smoke_path: str | Path,
    dcs_smoke_path: str | Path,
    now: datetime | None = None,
) -> AcademicFinalizationReport:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issues: list[FinalizationIssue] = []
    manifest_id: str | None = None

    try:
        manifest = verify_cutover_manifest(
            manifest_path=manifest_path,
            dtnh_report_path=dtnh_report_path,
            dcs_report_path=dcs_report_path,
            now=current,
        )
        manifest_id = manifest.manifest_id
    except Exception as exc:
        issues.append(FinalizationIssue("cutover.manifest", str(exc)))

    evidence: list[dict[str, Any]] = []
    for code, path in (("DTNH", dtnh_smoke_path), ("DCS", dcs_smoke_path)):
        try:
            item = _load_json(path)
        except Exception as exc:
            issues.append(FinalizationIssue("smoke.unreadable", str(exc), code))
            continue
        evidence.append(item)
        if int(item.get("report_version") or 0) != 1:
            issues.append(FinalizationIssue("smoke.version", "Unsupported smoke report version.", code))
        if str(item.get("directorate") or "").upper() != code:
            issues.append(FinalizationIssue("smoke.directorate", "Smoke report directorate mismatch.", code))
        if str(item.get("status") or "").upper() != "PASS":
            issues.append(FinalizationIssue("smoke.status", "Smoke validation did not pass.", code))
        if str(item.get("engine") or "") != "excel_official":
            issues.append(FinalizationIssue("smoke.engine", "Route was not served by Excel Official.", code))
        if str(item.get("app_version") or "") != APP_VERSION:
            issues.append(FinalizationIssue("smoke.app_version", "Smoke app version differs from this release.", code))
        if str(item.get("schema_version") or "") != str(SCHEMA_VERSION):
            issues.append(FinalizationIssue("smoke.schema_version", "Smoke schema version differs from this release.", code))
        if item.get("external_links") not in (0, False):
            issues.append(FinalizationIssue("smoke.external_links", "Smoke workbook contains external links.", code))
        if bool(item.get("has_vba")):
            issues.append(FinalizationIssue("smoke.vba", "Smoke workbook contains VBA/macros.", code))
        sheets = item.get("sheets") or []
        missing = [name for name in REQUIRED_INSTITUTIONAL_SHEETS if name not in sheets]
        if missing:
            issues.append(FinalizationIssue("smoke.required_sheets", "Missing: " + ", ".join(missing), code))
        workbook_path = item.get("workbook_path")
        if workbook_path and Path(str(workbook_path)).exists():
            actual = _sha256_file(str(workbook_path))
            if str(item.get("sha256") or "") != actual:
                issues.append(FinalizationIssue("smoke.sha256", "Workbook bytes changed after smoke report generation.", code))

    codes = {str(item.get("directorate") or "").upper() for item in evidence}
    if codes != {"DTNH", "DCS"}:
        issues.append(FinalizationIssue("smoke.missing", "Both DTNH and DCS smoke reports are required."))

    return AcademicFinalizationReport(
        report_version=FINALIZATION_REPORT_VERSION,
        status="COMPLETE" if not issues else "BLOCKED",
        generated_at=current.isoformat(),
        manifest_id=manifest_id,
        app_version=APP_VERSION,
        schema_version=str(SCHEMA_VERSION),
        smoke_evidence=tuple(evidence),
        issues=tuple(issues),
    )


def write_academic_finalization_report(report: AcademicFinalizationReport, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "academic_excel_finalization.json"
    md_path = output / "academic_excel_finalization.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    return json_path, md_path


__all__ = [
    "AcademicFinalizationReport",
    "FINALIZATION_REPORT_VERSION",
    "FinalizationIssue",
    "build_academic_finalization_report",
    "write_academic_finalization_report",
]
