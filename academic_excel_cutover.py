from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from academic_excel_parity import PARITY_REPORT_VERSION
from release_info import APP_VERSION, SCHEMA_VERSION


CUTOVER_MANIFEST_VERSION = 1
CUTOVER_FLAG = "ACADEMIC_EXCEL_OFFICIAL_ENABLED"
ENABLE_CONFIRMATION = "ENABLE_EXCEL_OFFICIAL"
DEFAULT_MAX_AGE_HOURS = 24.0
_ALLOWED_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class CutoverIssue:
    code: str
    message: str
    directorate: str | None = None


@dataclass(frozen=True, slots=True)
class CutoverReportEvidence:
    directorate: str
    path: str
    sha256: str
    generated_at: str
    payload_hash: str
    system_version: str
    schema_version: str
    cases: int
    failures: int
    source_kind: str
    cutover_status: str


@dataclass(frozen=True, slots=True)
class AcademicCutoverManifest:
    manifest_version: int
    manifest_id: str
    status: str
    generated_at: str
    expires_at: str | None
    app_version: str
    schema_version: str
    max_age_hours: float
    reports: tuple[CutoverReportEvidence, ...]
    issues: tuple[CutoverIssue, ...]

    @property
    def ready(self) -> bool:
        return self.status == "READY" and not self.issues

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ready"] = self.ready
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)

    def to_markdown(self) -> str:
        lines = [
            "# Academic Excel Controlled Cutover Manifest",
            "",
            f"- Status: **{self.status}**",
            f"- Manifest ID: `{self.manifest_id}`",
            f"- Generated at: `{self.generated_at}`",
            f"- Expires at: `{self.expires_at or 'n/a'}`",
            f"- App version: `{self.app_version}`",
            f"- Schema version: `{self.schema_version}`",
            f"- Evidence max age: **{self.max_age_hours:g}h**",
            "",
            "| Diretoria | Origem | Casos | Falhas | Report status | SHA-256 |",
            "|---|---|---:|---:|---|---|",
        ]
        for item in self.reports:
            lines.append(
                f"| {item.directorate} | {item.source_kind} | {item.cases} | {item.failures} | "
                f"{item.cutover_status} | `{item.sha256[:16]}...` |"
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
                    "## Gate result",
                    "",
                    "Both DTNH and DCS production reports are fresh, use the running app/schema version, "
                    "contain successful legacy/new workbook evidence, passed source quality and semantic parity, "
                    "and are individually READY.",
                ]
            )
        lines.extend(
            [
                "",
                "This manifest does not change production by itself. Activation still requires an explicit "
                f"`{ENABLE_CONFIRMATION}` confirmation and an application container restart after the env flag is written.",
                "",
            ]
        )
        return "\n".join(lines)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_parity_report(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{target}: expected a JSON object parity report")
    return data


def _summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("summary")
    return value if isinstance(value, Mapping) else {}


def _workbook_ok(report: Mapping[str, Any], key: str, expected_engine: str) -> bool:
    value = report.get(key)
    if not isinstance(value, Mapping):
        return False
    return bool(value.get("build_ok")) and str(value.get("engine") or "") == expected_engine


def _canonical_manifest_id(*, app_version: str, schema_version: str, max_age_hours: float, reports: tuple[CutoverReportEvidence, ...]) -> str:
    payload = {
        "manifest_version": CUTOVER_MANIFEST_VERSION,
        "app_version": app_version,
        "schema_version": schema_version,
        "max_age_hours": float(max_age_hours),
        "reports": [
            {
                "directorate": item.directorate,
                "sha256": item.sha256,
                "generated_at": item.generated_at,
                "payload_hash": item.payload_hash,
                "system_version": item.system_version,
                "schema_version": item.schema_version,
                "cases": item.cases,
                "failures": item.failures,
                "source_kind": item.source_kind,
                "cutover_status": item.cutover_status,
            }
            for item in reports
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_cutover_manifest(
    *,
    dtnh_report_path: str | Path,
    dcs_report_path: str | Path,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    now: datetime | None = None,
    expected_app_version: str = APP_VERSION,
    expected_schema_version: int | str = SCHEMA_VERSION,
) -> AcademicCutoverManifest:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    current = (now or _utcnow()).astimezone(timezone.utc)
    expected_schema = str(expected_schema_version)
    issues: list[CutoverIssue] = []
    evidences: list[CutoverReportEvidence] = []
    expirations: list[datetime] = []

    for code, raw_path in (("DTNH", dtnh_report_path), ("DCS", dcs_report_path)):
        path = Path(raw_path)
        try:
            report = load_parity_report(path)
        except Exception as exc:
            issues.append(CutoverIssue("report.unreadable", f"Could not read parity report: {type(exc).__name__}: {exc}", code))
            continue

        directorate = str(report.get("directorate") or "").strip().upper()
        source_kind = str(report.get("source_kind") or "").strip().lower()
        generated_text = str(report.get("generated_at") or "").strip()
        generated_at = _parse_datetime(generated_text)
        system_version = str(report.get("system_version") or "").strip()
        schema_version = str(report.get("schema_version") or "").strip()
        payload_hash = str(report.get("payload_hash") or "").strip()
        summary = _summary(report)
        failures = int(summary.get("failures") or 0)
        cases = int(summary.get("cases") or len(report.get("cases") or ()))
        cutover_status = str(summary.get("cutover_status") or "").strip().upper()

        if int(report.get("report_version") or 0) != PARITY_REPORT_VERSION:
            issues.append(CutoverIssue("report.version", f"Parity report version must be {PARITY_REPORT_VERSION}.", code))
        if directorate != code:
            issues.append(CutoverIssue("report.directorate", f"Expected report for {code}, got {directorate or 'blank'}.", code))
        if source_kind != "production":
            issues.append(CutoverIssue("report.source_kind", "Cutover evidence must come from a production snapshot.", code))
        if cutover_status != "READY":
            issues.append(CutoverIssue("report.status", f"Parity report is {cutover_status or 'UNKNOWN'}, not READY.", code))
        if failures != 0 or not bool(summary.get("semantic_passed")):
            issues.append(CutoverIssue("report.semantic", f"Semantic parity has {failures} failure(s).", code))
        if not bool(summary.get("source_quality_ok")) or not bool(report.get("source_quality_ok")):
            issues.append(CutoverIssue("report.source_quality", "Source-quality gate did not pass.", code))
        if not bool(summary.get("new_release_allowed")) or not bool(report.get("new_release_allowed")):
            issues.append(CutoverIssue("report.release_audit", "Excel Official release audit did not pass.", code))
        if not _workbook_ok(report, "legacy_workbook", "academic_v3_legacy"):
            issues.append(CutoverIssue("report.legacy_build", "Academic V3 workbook evidence is missing or failed.", code))
        if not _workbook_ok(report, "new_workbook", "excel_official_core"):
            issues.append(CutoverIssue("report.official_build", "Excel Official workbook evidence is missing or failed.", code))
        if system_version != expected_app_version:
            issues.append(CutoverIssue("report.app_version", f"Report app version {system_version or 'blank'} does not match running release {expected_app_version}.", code))
        if schema_version != expected_schema:
            issues.append(CutoverIssue("report.schema_version", f"Report schema {schema_version or 'blank'} does not match running schema {expected_schema}.", code))
        if not payload_hash:
            issues.append(CutoverIssue("report.payload_hash", "Production report must contain a payload hash.", code))
        if generated_at is None:
            issues.append(CutoverIssue("report.generated_at", "Report generated_at is missing or invalid.", code))
        else:
            age = current - generated_at
            if age < timedelta(minutes=-5):
                issues.append(CutoverIssue("report.future", "Report timestamp is more than 5 minutes in the future.", code))
            if age > timedelta(hours=max_age_hours):
                issues.append(CutoverIssue("report.stale", f"Report is older than the {max_age_hours:g}h evidence window.", code))
            expirations.append(generated_at + timedelta(hours=max_age_hours))

        evidences.append(
            CutoverReportEvidence(
                directorate=code,
                path=path.name,
                sha256=_sha256_file(path),
                generated_at=generated_text,
                payload_hash=payload_hash,
                system_version=system_version,
                schema_version=schema_version,
                cases=cases,
                failures=failures,
                source_kind=source_kind,
                cutover_status=cutover_status,
            )
        )

    if len(evidences) == 2:
        versions = {(item.system_version, item.schema_version) for item in evidences}
        if len(versions) != 1:
            issues.append(CutoverIssue("reports.version_mismatch", "DTNH and DCS reports do not use the same app/schema version."))
    else:
        issues.append(CutoverIssue("reports.missing", "Both DTNH and DCS production reports are required."))

    evidence_tuple = tuple(sorted(evidences, key=lambda item: item.directorate))
    manifest_id = _canonical_manifest_id(
        app_version=expected_app_version,
        schema_version=expected_schema,
        max_age_hours=max_age_hours,
        reports=evidence_tuple,
    )
    expires_at = min(expirations).isoformat() if len(expirations) == 2 else None
    return AcademicCutoverManifest(
        manifest_version=CUTOVER_MANIFEST_VERSION,
        manifest_id=manifest_id,
        status="READY" if not issues and len(evidence_tuple) == 2 else "BLOCKED",
        generated_at=current.isoformat(),
        expires_at=expires_at,
        app_version=expected_app_version,
        schema_version=expected_schema,
        max_age_hours=float(max_age_hours),
        reports=evidence_tuple,
        issues=tuple(issues),
    )


def write_cutover_manifest(manifest: AcademicCutoverManifest, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "academic_excel_cutover_manifest.json"
    md_path = output / "academic_excel_cutover_manifest.md"
    json_path.write_text(manifest.to_json() + "\n", encoding="utf-8")
    md_path.write_text(manifest.to_markdown(), encoding="utf-8")
    return json_path, md_path


def load_cutover_manifest(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{target}: expected a JSON object cutover manifest")
    return data


def verify_cutover_manifest(
    *,
    manifest_path: str | Path,
    dtnh_report_path: str | Path,
    dcs_report_path: str | Path,
    now: datetime | None = None,
) -> AcademicCutoverManifest:
    stored = load_cutover_manifest(manifest_path)
    if int(stored.get("manifest_version") or 0) != CUTOVER_MANIFEST_VERSION:
        raise ValueError(f"Unsupported cutover manifest version: {stored.get('manifest_version')!r}")
    max_age_hours = float(stored.get("max_age_hours") or 0)
    expected_app = str(stored.get("app_version") or "")
    expected_schema = str(stored.get("schema_version") or "")
    if expected_app != APP_VERSION or expected_schema != str(SCHEMA_VERSION):
        raise ValueError(
            f"Cutover manifest targets app/schema {expected_app}/{expected_schema}, "
            f"but this release is {APP_VERSION}/{SCHEMA_VERSION}."
        )
    refreshed = build_cutover_manifest(
        dtnh_report_path=dtnh_report_path,
        dcs_report_path=dcs_report_path,
        max_age_hours=max_age_hours,
        now=now,
        expected_app_version=APP_VERSION,
        expected_schema_version=SCHEMA_VERSION,
    )
    if not refreshed.ready:
        messages = "; ".join(f"{item.code}: {item.message}" for item in refreshed.issues)
        raise ValueError(f"Cutover gate is no longer READY: {messages}")
    if str(stored.get("status") or "") != "READY" or stored.get("ready") is not True:
        raise ValueError("Stored cutover manifest is not READY.")
    if str(stored.get("manifest_id") or "") != refreshed.manifest_id:
        raise ValueError("Cutover evidence changed after the manifest was generated; generate a new manifest.")
    return refreshed


def read_env_flag(env_path: str | Path) -> bool:
    path = Path(env_path)
    if not path.exists():
        raise FileNotFoundError(path)
    value = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() == CUTOVER_FLAG:
            value = raw_value.strip()
    return value.lower() in _ALLOWED_TRUE


def _set_env_flag(env_path: str | Path, *, enabled: bool, now: datetime | None = None) -> tuple[Path | None, bool]:
    path = Path(env_path)
    if not path.exists():
        raise FileNotFoundError(path)
    original = path.read_text(encoding="utf-8")
    target_value = "true" if enabled else "false"
    lines = original.splitlines()
    found = False
    changed = False
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped and stripped.split("=", 1)[0].strip() == CUTOVER_FLAG:
            new_line = f"{CUTOVER_FLAG}={target_value}"
            output.append(new_line)
            found = True
            if line != new_line:
                changed = True
        else:
            output.append(line)
    if not found:
        if output and output[-1] != "":
            output.append("")
        output.append(f"{CUTOVER_FLAG}={target_value}")
        changed = True
    if not changed:
        return None, False

    current = (now or _utcnow()).astimezone(timezone.utc)
    stamp = current.strftime('%Y%m%dT%H%M%SZ')
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    suffix = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{stamp}-{suffix}")
        suffix += 1
    shutil.copy2(path, backup)
    content = "\n".join(output) + ("\n" if original.endswith("\n") or output else "")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_name, stat.S_IMODE(path.stat().st_mode))
        except OSError:
            pass
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return backup, True


def activate_cutover(
    *,
    manifest_path: str | Path,
    dtnh_report_path: str | Path,
    dcs_report_path: str | Path,
    env_path: str | Path,
    confirmation: str,
    now: datetime | None = None,
) -> tuple[AcademicCutoverManifest, Path | None, bool]:
    if confirmation != ENABLE_CONFIRMATION:
        raise ValueError(f"Activation requires --confirm {ENABLE_CONFIRMATION}")
    manifest = verify_cutover_manifest(
        manifest_path=manifest_path,
        dtnh_report_path=dtnh_report_path,
        dcs_report_path=dcs_report_path,
        now=now,
    )
    backup, changed = _set_env_flag(env_path, enabled=True, now=now)
    return manifest, backup, changed


def rollback_cutover(*, env_path: str | Path, now: datetime | None = None) -> tuple[Path | None, bool]:
    return _set_env_flag(env_path, enabled=False, now=now)


__all__ = [
    "AcademicCutoverManifest",
    "CUTOVER_FLAG",
    "CUTOVER_MANIFEST_VERSION",
    "CutoverIssue",
    "CutoverReportEvidence",
    "DEFAULT_MAX_AGE_HOURS",
    "ENABLE_CONFIRMATION",
    "activate_cutover",
    "build_cutover_manifest",
    "load_cutover_manifest",
    "load_parity_report",
    "read_env_flag",
    "rollback_cutover",
    "verify_cutover_manifest",
    "write_cutover_manifest",
]
