from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from dadm_tallos_analytics import _conditions, _department_labels, _summary, _valid_rating_expr, comparison_range
from dadm_v2_analytics import resolve_month_range
from dadm_v2_management import export_management_rows
from dadm_v2_report import build_report_payload
from excel_official import ExcelOfficialCore
from excel_official.adapters.dadm import DADMAdapter
from excel_official.context import AdapterInput, SnapshotContext
from excel_official.contract import Scalar
from excel_official.workbook import WorkbookArtifact
from models import DADMTallosAttendance
from release_info import APP_VERSION, SCHEMA_VERSION


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


def _cube_rows_from_db(
    db: Session,
    directorate_id: int,
    start_date,
    end_date,
    *,
    allowed_departments: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    conditions = _conditions(
        directorate_id,
        start_date,
        end_date,
        allowed_departments=allowed_departments,
    )
    valid_rating = _valid_rating_expr()
    finalized_case = case((DADMTallosAttendance.status == "finalized", 1), else_=0)
    open_case = case((DADMTallosAttendance.status == "open", 1), else_=0)
    transferred_case = case((DADMTallosAttendance.transferred.is_(True), 1), else_=0)

    rows = db.execute(
        select(
            DADMTallosAttendance.month_key.label("period"),
            DADMTallosAttendance.department_key.label("department"),
            DADMTallosAttendance.department_name.label("department_name"),
            DADMTallosAttendance.employee_id.label("employee"),
            DADMTallosAttendance.employee_name.label("employee_name"),
            DADMTallosAttendance.channel.label("channel"),
            DADMTallosAttendance.status.label("status"),
            DADMTallosAttendance.tabulation.label("tabulation"),
            func.count(DADMTallosAttendance.id).label("attendances"),
            func.coalesce(func.sum(finalized_case), 0).label("finalized"),
            func.coalesce(func.sum(open_case), 0).label("open"),
            func.coalesce(func.sum(DADMTallosAttendance.tme_seconds), 0.0).label("tme_sum_seconds"),
            func.count(DADMTallosAttendance.tme_seconds).label("tme_count"),
            func.coalesce(func.sum(DADMTallosAttendance.tma_seconds), 0.0).label("tma_sum_seconds"),
            func.count(DADMTallosAttendance.tma_seconds).label("tma_count"),
            func.coalesce(func.sum(valid_rating), 0.0).label("rating_sum"),
            func.count(valid_rating).label("rating_count"),
            func.coalesce(func.sum(transferred_case), 0).label("transferred"),
            func.coalesce(func.sum(DADMTallosAttendance.messages_sent), 0).label("messages_sent"),
            func.coalesce(func.sum(DADMTallosAttendance.messages_received), 0).label("messages_received"),
        )
        .where(*conditions)
        .group_by(
            DADMTallosAttendance.month_key,
            DADMTallosAttendance.department_key,
            DADMTallosAttendance.department_name,
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
            DADMTallosAttendance.channel,
            DADMTallosAttendance.status,
            DADMTallosAttendance.tabulation,
        )
        .order_by(
            DADMTallosAttendance.month_key,
            DADMTallosAttendance.department_name,
            DADMTallosAttendance.employee_name,
            DADMTallosAttendance.channel,
            DADMTallosAttendance.status,
            DADMTallosAttendance.tabulation,
        )
    ).all()

    mapped_departments = _department_labels(db, directorate_id)
    result: list[dict[str, Any]] = []
    for row in rows:
        department = str(row.department or "").strip()
        result.append({
            "period": str(row.period or ""),
            "department": department,
            "department_name": str(mapped_departments.get(department) or row.department_name or department or "(sem departamento)"),
            "employee": str(row.employee or ""),
            "employee_name": str(row.employee_name or row.employee or "(sem operador)"),
            "channel": str(row.channel or ""),
            "status": str(row.status or "unknown"),
            "tabulation": str(row.tabulation or ""),
            "attendances": int(row.attendances or 0),
            "finalized": int(row.finalized or 0),
            "open": int(row.open or 0),
            "tme_sum_minutes": float(row.tme_sum_seconds or 0.0) / 60.0,
            "tme_count": int(row.tme_count or 0),
            "tma_sum_minutes": float(row.tma_sum_seconds or 0.0) / 60.0,
            "tma_count": int(row.tma_count or 0),
            "rating_sum": float(row.rating_sum or 0.0),
            "rating_count": int(row.rating_count or 0),
            "transferred": int(row.transferred or 0),
            "messages_sent": int(row.messages_sent or 0),
            "messages_received": int(row.messages_received or 0),
        })
    return result


def build_dadm_excel_official_payload_from_db(
    db: Session,
    directorate_id: int,
    from_month: str | None = None,
    to_month: str | None = None,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
    targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    actions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    start_month, end_month, start_date, end_date = resolve_month_range(
        db,
        directorate_id,
        from_month,
        to_month,
        allowed_departments=allowed_departments,
    )
    # The backend summary preserves the exact current DADM V2 semantics for the
    # selected context. The offline cube contains the whole authorized window so
    # that dimensions can be recut without exporting customer/protocol data.
    report = build_report_payload(
        db,
        directorate_id,
        start_month,
        end_month,
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
        allowed_departments=allowed_departments,
    )
    if targets is None or actions is None:
        exported_targets, exported_actions = export_management_rows(
            db,
            directorate_id,
            allowed_departments=allowed_departments,
        )
        if targets is None:
            targets = exported_targets
        if actions is None:
            actions = exported_actions
    report["cube"] = _cube_rows_from_db(
        db,
        directorate_id,
        start_date,
        end_date,
        allowed_departments=allowed_departments,
    )
    previous_period = comparison_range(start_date, end_date, "previous_period")
    if previous_period:
        previous_conditions = _conditions(
            directorate_id,
            previous_period[0],
            previous_period[1],
            department=department,
            employee=employee,
            channel=channel,
            status=status,
            tabulation=tabulation,
            allowed_departments=allowed_departments,
        )
        report["comparison"] = _summary(db, previous_conditions)
        report["comparison_period"] = {
            "start": previous_period[0].isoformat(),
            "end": previous_period[1].isoformat(),
            "mode": "previous_period",
        }
    else:
        report["comparison"] = None
        report["comparison_period"] = None
    report["targets"] = [dict(row) for row in (targets or ())]
    report["actions"] = [dict(row) for row in (actions or ())]
    report["directorate"] = "DADM"
    report["directorate_name"] = "Diretoria Administrativa"
    report["schema_version"] = SCHEMA_VERSION
    report["period"]["label"] = f"{start_month} → {end_month}" if start_month != end_month else start_month
    report["initial"] = {
        "period": start_month if start_month == end_month else "(todos)",
        "department": department or "(todos)",
        "employee": employee or "(todos)",
        "channel": channel or "(todos)",
        "status": status or "(todos)",
        "tabulation": tabulation or "(todos)",
        "matrix_metric": "Atendimentos",
    }
    return report


def build_dadm_snapshot_context(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None,
    export_id: str | None = None,
    authorization_scope: tuple[str, ...] | None = None,
) -> SnapshotContext:
    cube = [dict(row) for row in payload.get("cube", ())]
    periods = sorted({str(row.get("period") or "").strip() for row in cube if str(row.get("period") or "").strip()})
    departments = tuple(dict.fromkeys(str(row.get("department") or "").strip() for row in cube if str(row.get("department") or "").strip()))
    employees = tuple(dict.fromkeys(str(row.get("employee") or "").strip() for row in cube if str(row.get("employee") or "").strip()))
    initial = dict(payload.get("initial", {}) or {})
    initial_filters: dict[str, Scalar] = {}
    for key in ("period", "department", "employee", "channel", "status", "tabulation", "matrix_metric"):
        if initial.get(key) not in (None, ""):
            initial_filters[key] = initial[key]

    return SnapshotContext(
        export_id=export_id or f"dadm-{uuid4().hex}",
        generated_at=_generated_at(payload),
        generated_by=generated_by,
        directorate="DADM",
        authorization_scope=authorization_scope or ("DADM",),
        system_version=str(payload.get("app_version") or APP_VERSION),
        schema_version=payload.get("schema_version") or SCHEMA_VERSION,
        initial_filters=initial_filters,
        available_scope={"department": departments, "employee": employees},
        minimum_period=periods[0] if periods else None,
        maximum_period=periods[-1] if periods else None,
        payload_hash=_stable_payload_hash(payload),
    )


def build_dadm_excel_official_artifact_from_payload(
    payload: Mapping[str, Any],
    *,
    generated_by: str | None = None,
    export_id: str | None = None,
    authorization_scope: tuple[str, ...] | None = None,
    initial_state: Mapping[str, Any] | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    context = build_dadm_snapshot_context(
        payload,
        generated_by=generated_by,
        export_id=export_id,
        authorization_scope=authorization_scope,
    )
    spec = DADMAdapter().build_spec(AdapterInput(context, payload, dict(initial_state or {})))
    return ExcelOfficialCore().build(spec, enforce_release=enforce_release)


def build_dadm_excel_official_artifact_from_db(
    db: Session,
    directorate_id: int,
    from_month: str | None = None,
    to_month: str | None = None,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
    targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    actions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    generated_by: str | None = None,
    authorization_scope: tuple[str, ...] | None = None,
    enforce_release: bool = True,
) -> WorkbookArtifact:
    payload = build_dadm_excel_official_payload_from_db(
        db,
        directorate_id,
        from_month,
        to_month,
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
        allowed_departments=allowed_departments,
        targets=targets,
        actions=actions,
    )
    return build_dadm_excel_official_artifact_from_payload(
        payload,
        generated_by=generated_by,
        authorization_scope=authorization_scope,
        enforce_release=enforce_release,
    )


def build_dadm_excel_official_workbook_bytes(*args, **kwargs):
    return build_dadm_excel_official_artifact_from_db(*args, **kwargs).to_bytes()


__all__ = [
    "build_dadm_excel_official_artifact_from_db",
    "build_dadm_excel_official_artifact_from_payload",
    "build_dadm_excel_official_payload_from_db",
    "build_dadm_excel_official_workbook_bytes",
    "build_dadm_snapshot_context",
]
