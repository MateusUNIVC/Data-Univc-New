from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from academic_excel_v3_builder import build_academic_interactive_payload
from excel_official import ExcelOfficialCore
from excel_official.adapters.academic import AcademicAdapter
from excel_official.context import AdapterInput, SnapshotContext
from excel_official.contract import Scalar
from excel_official.workbook import WorkbookArtifact
from release_info import APP_VERSION, SCHEMA_VERSION
from repository import DatabaseRepository


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
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _initial_filters(payload: Mapping[str, Any]) -> dict[str, Scalar]:
    initial = payload.get("initial", {}) or {}
    values: dict[str, Scalar] = {}
    mapping = {
        "reference_period": "reference",
        "comparison_period": "comparison",
        "course": "course",
        "discipline": "discipline",
    }
    for target, source in mapping.items():
        value = initial.get(source)
        if value not in (None, ""):
            values[target] = value
    window = initial.get("window")
    if window not in (None, ""):
        values["history_window"] = window
    return values


def build_academic_snapshot_context(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None,
    directorate: str | None = None,
    export_id: str | None = None,
) -> SnapshotContext:
    directorate_code = str(directorate or payload.get("directorate") or "").strip().upper()
    if directorate_code not in {"DTNH", "DCS"}:
        raise ValueError("O Excel Oficial acadêmico está disponível apenas para DTNH/DCS.")

    semesters = tuple(str(item).strip() for item in payload.get("semesters", ()) if str(item).strip())
    courses = tuple(
        str(item.get("curso") or "").strip()
        for item in payload.get("courses_catalog", ())
        if str(item.get("curso") or "").strip() and item.get("ativo") is not False
    )
    disciplines = tuple(
        str(item.get("disciplina") or "").strip()
        for item in payload.get("disciplines_catalog", ())
        if str(item.get("disciplina") or "").strip() and item.get("ativo") is not False
    )

    return SnapshotContext(
        export_id=export_id or f"academic-{directorate_code.lower()}-{uuid4().hex}",
        generated_at=_generated_at(payload),
        generated_by=generated_by,
        directorate=directorate_code,
        authorization_scope=(directorate_code,),
        system_version=str(payload.get("app_version") or APP_VERSION),
        schema_version=SCHEMA_VERSION,
        initial_filters=_initial_filters(payload),
        available_scope={
            "period": semesters,
            "course": tuple(dict.fromkeys(courses)),
            "discipline": tuple(dict.fromkeys(disciplines)),
        },
        minimum_period=semesters[0] if semesters else None,
        maximum_period=semesters[-1] if semesters else None,
        payload_hash=_stable_payload_hash(payload),
    )


def build_academic_excel_official_artifact_from_payload(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None,
    directorate: str | None = None,
    export_id: str | None = None,
    initial_state: Mapping[str, Scalar] | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    context = build_academic_snapshot_context(
        payload,
        generated_by=generated_by,
        directorate=directorate,
        export_id=export_id,
    )
    adapter_input = AdapterInput(
        snapshot_context=context,
        authorized_data=payload,
        initial_state=dict(initial_state or {}),
    )
    spec = AcademicAdapter().build_spec(adapter_input)
    return ExcelOfficialCore().build(spec, enforce_release=enforce_release)


def build_academic_excel_official_artifact(
    repo: DatabaseRepository,
    *,
    reference: str | None = None,
    comparison: str | None = None,
    course: str | None = None,
    discipline: str | None = None,
    window_periods: int | str | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    payload = build_academic_interactive_payload(
        repo,
        reference=reference,
        comparison=comparison,
        course=course,
        discipline=discipline,
        window_periods=window_periods,
    )
    initial_state = {
        key: value
        for key, value in {
            "reference_period": reference,
            "comparison_period": comparison,
            "course": course,
            "discipline": discipline,
        }.items()
        if value not in (None, "")
    }
    return build_academic_excel_official_artifact_from_payload(
        payload,
        generated_by=getattr(repo.ctx, "email", None) or getattr(repo.ctx, "full_name", None),
        directorate=repo.directorate_code,
        initial_state=initial_state,
        enforce_release=enforce_release,
    )


def build_academic_excel_official_workbook_bytes(
    repo: DatabaseRepository,
    *,
    reference: str | None = None,
    comparison: str | None = None,
    course: str | None = None,
    discipline: str | None = None,
    window_periods: int | str | None = None,
):
    """Build the migration-candidate workbook without changing production routes."""
    return build_academic_excel_official_artifact(
        repo,
        reference=reference,
        comparison=comparison,
        course=course,
        discipline=discipline,
        window_periods=window_periods,
    ).to_bytes()


__all__ = [
    "build_academic_excel_official_artifact",
    "build_academic_excel_official_artifact_from_payload",
    "build_academic_excel_official_workbook_bytes",
    "build_academic_snapshot_context",
]
