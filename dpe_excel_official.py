from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy.orm import Session

from dpe_excel_export import DPEExcelExportRepository
from excel_official import ExcelOfficialCore
from excel_official.adapters.dpe import DPEAdapter
from excel_official.context import AdapterInput, SnapshotContext
from excel_official.contract import Scalar
from excel_official.workbook import WorkbookArtifact
from release_info import APP_VERSION, SCHEMA_VERSION
from security import DirectorateScope


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def build_dpe_snapshot_context(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None,
    export_id: str | None = None,
    authorization_scope: tuple[str, ...] | None = None,
) -> SnapshotContext:
    selected = dict(payload.get("selected_period") or {})
    analytics = dict(payload.get("analytics") or {})
    periods = [str(row.get("period") or "").strip() for row in analytics.get("periods") or () if str(row.get("period") or "").strip()]
    period = str(selected.get("period") or "").strip()
    if period and period not in periods:
        periods.append(period)
    periods = sorted(set(periods))
    initial = dict(payload.get("initial") or {})
    initial_filters: dict[str, Scalar] = {"period": period}
    for key in ("course", "context", "cost_center"):
        if initial.get(key) not in (None, ""):
            initial_filters[key] = initial[key]

    return SnapshotContext(
        export_id=export_id or f"dpe-{uuid4().hex}",
        generated_at=_generated_at(payload),
        generated_by=generated_by,
        directorate="DPE",
        authorization_scope=authorization_scope or ("DPE",),
        system_version=str(payload.get("app_version") or APP_VERSION),
        schema_version=payload.get("schema_version") or SCHEMA_VERSION,
        initial_filters=initial_filters,
        minimum_period=period or (periods[0] if periods else None),
        maximum_period=period or (periods[-1] if periods else None),
        payload_hash=_stable_payload_hash(payload),
    )


def build_dpe_excel_official_artifact_from_payload(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None = None,
    export_id: str | None = None,
    authorization_scope: tuple[str, ...] | None = None,
    initial_state: Mapping[str, Any] | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    context = build_dpe_snapshot_context(
        payload,
        generated_by=generated_by,
        export_id=export_id,
        authorization_scope=authorization_scope,
    )
    spec = DPEAdapter().build_spec(AdapterInput(context, payload, dict(initial_state or {})))
    return ExcelOfficialCore().build(spec, enforce_release=enforce_release)


def build_dpe_excel_official_artifact_from_db(
    db: Session,
    scope: DirectorateScope,
    *,
    period_id: int | None = None,
    reference: str | None = None,
    generated_by: str | None = None,
    authorization_scope: tuple[str, ...] | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    payload = DPEExcelExportRepository(db, scope).payload(period_id=period_id, reference=reference)
    if payload.get("selected_period"):
        payload["app_version"] = APP_VERSION
        payload["schema_version"] = SCHEMA_VERSION
        payload.setdefault("initial", {})
    return build_dpe_excel_official_artifact_from_payload(
        payload,
        generated_by=generated_by,
        authorization_scope=authorization_scope,
        enforce_release=enforce_release,
    )


def build_dpe_excel_official_workbook_bytes(*args, **kwargs):
    return build_dpe_excel_official_artifact_from_db(*args, **kwargs).to_bytes()


__all__ = [
    "build_dpe_excel_official_artifact_from_db",
    "build_dpe_excel_official_artifact_from_payload",
    "build_dpe_excel_official_workbook_bytes",
    "build_dpe_snapshot_context",
]
