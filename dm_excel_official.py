from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping
from uuid import uuid4

from dm_analytics import build_dm_dashboard
from dm_excel_v3_builder import build_dm_interactive_payload
from excel_official import ExcelOfficialCore
from excel_official.adapters.dm import DMAdapter
from excel_official.context import AdapterInput, SnapshotContext
from excel_official.contract import Scalar
from excel_official.workbook import WorkbookArtifact
from release_info import APP_VERSION, SCHEMA_VERSION


def _generated_at(payload: Mapping[str, Any]) -> datetime:
    raw = payload.get("generated_at")
    if isinstance(raw, datetime):
        value = raw
    elif raw:
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            value = datetime.now(timezone.utc)
    else:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cohort_key(row: Mapping[str, Any]) -> str:
    existing = str(row.get("cohort_key") or "").strip()
    if existing:
        return existing
    return f"{str(row.get('area_code') or '').strip().upper()} | Turma {int(row.get('cohort_number') or 0)}"


def build_dm_excel_official_payload(
    cohorts: Iterable[dict[str, Any]],
    students: Iterable[dict[str, Any]],
    *,
    targets: Iterable[dict[str, Any]] | None = None,
    actions: Iterable[dict[str, Any]] | None = None,
    sync_runs: Iterable[dict[str, Any]] | None = None,
    area_code: str | None = None,
    cohort_id: int | None = None,
    as_of: date | None = None,
    comparison_cohort: str | None = None,
    matrix_kpi: str | None = None,
) -> dict[str, Any]:
    cohort_rows = [dict(row) for row in cohorts]
    student_rows = [dict(row) for row in students]
    target_rows = [dict(row) for row in (targets or [])]
    cutoff = as_of or date.today()

    payload = build_dm_interactive_payload(
        cohort_rows,
        student_rows,
        targets=target_rows,
        actions=actions,
        sync_runs=sync_runs,
        area_code=area_code,
        cohort_id=cohort_id,
        as_of=cutoff,
        matrix_kpi=matrix_kpi,
    )
    payload["dashboard_snapshot"] = build_dm_dashboard(
        cohort_rows,
        student_rows,
        area_code=None,
        cohort_id=None,
        as_of=cutoff,
        targets=target_rows,
    )
    payload["directorate"] = "DM"
    payload["directorate_name"] = "Diretoria de Mestrado"
    payload["schema_version"] = SCHEMA_VERSION
    payload["initial"]["as_of"] = cutoff
    if comparison_cohort:
        payload["initial"]["comparison"] = comparison_cohort
    return payload


def build_dm_snapshot_context(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None,
    export_id: str | None = None,
) -> SnapshotContext:
    cohorts = [dict(row) for row in payload.get("cohorts", ())]
    areas = tuple(dict.fromkeys(str(row.get("area_code") or "").strip().upper() for row in cohorts if str(row.get("area_code") or "").strip()))
    cohort_keys = tuple(_cohort_key(row) for row in cohorts if _cohort_key(row))
    openings = sorted(str(row.get("opening_date") or "")[:10] for row in cohorts if row.get("opening_date"))
    initial = payload.get("initial", {}) or {}
    initial_filters: dict[str, Scalar] = {}
    if initial.get("area") not in (None, ""):
        initial_filters["area"] = initial.get("area")
    if initial.get("cohort") not in (None, ""):
        initial_filters["cohort"] = initial.get("cohort")
    if initial.get("comparison") not in (None, ""):
        initial_filters["comparison_cohort"] = initial.get("comparison")
    if initial.get("matrix_kpi") not in (None, ""):
        initial_filters["matrix_metric"] = initial.get("matrix_kpi")

    return SnapshotContext(
        export_id=export_id or f"dm-{uuid4().hex}",
        generated_at=_generated_at(payload),
        generated_by=generated_by,
        directorate="DM",
        authorization_scope=("DM",),
        system_version=str(payload.get("app_version") or APP_VERSION),
        schema_version=payload.get("schema_version") or SCHEMA_VERSION,
        initial_filters=initial_filters,
        available_scope={"area": areas, "cohort": cohort_keys},
        minimum_period=openings[0] if openings else None,
        maximum_period=str(initial.get("as_of") or "")[:10] or (openings[-1] if openings else None),
        payload_hash=_stable_payload_hash(payload),
    )


def build_dm_excel_official_artifact_from_payload(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None = None,
    export_id: str | None = None,
    initial_state: Mapping[str, Any] | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    context = build_dm_snapshot_context(payload, generated_by=generated_by, export_id=export_id)
    spec = DMAdapter().build_spec(AdapterInput(context, payload, dict(initial_state or {})))
    return ExcelOfficialCore().build(spec, enforce_release=enforce_release)


def build_dm_excel_official_artifact(
    cohorts: Iterable[dict[str, Any]],
    students: Iterable[dict[str, Any]],
    *,
    targets: Iterable[dict[str, Any]] | None = None,
    actions: Iterable[dict[str, Any]] | None = None,
    sync_runs: Iterable[dict[str, Any]] | None = None,
    area_code: str | None = None,
    cohort_id: int | None = None,
    as_of: date | None = None,
    comparison_cohort: str | None = None,
    matrix_kpi: str | None = None,
    generated_by: str | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    payload = build_dm_excel_official_payload(
        cohorts,
        students,
        targets=targets,
        actions=actions,
        sync_runs=sync_runs,
        area_code=area_code,
        cohort_id=cohort_id,
        as_of=as_of,
        comparison_cohort=comparison_cohort,
        matrix_kpi=matrix_kpi,
    )
    return build_dm_excel_official_artifact_from_payload(
        payload,
        generated_by=generated_by,
        enforce_release=enforce_release,
    )


def build_dm_excel_official_workbook_bytes(*args, **kwargs):
    return build_dm_excel_official_artifact(*args, **kwargs).to_bytes()


__all__ = [
    "build_dm_excel_official_artifact",
    "build_dm_excel_official_artifact_from_payload",
    "build_dm_excel_official_payload",
    "build_dm_excel_official_workbook_bytes",
    "build_dm_snapshot_context",
]
