from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from math import ceil
from statistics import median
from typing import Any, Iterable

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from auth.data_scopes import dadm_preferred_department_name
from dadm_tallos_normalization import department_display
from models import DADMTallosAttendance, DADMTallosDepartmentMap, DADMTallosSyncRun


def _float(value):
    return None if value is None else float(value)


def _valid_rating_expr():
    """SQL expression for the homologated TALLOS 1..10 evaluation scale.

    This defensive guard keeps stale historical ``rating=0`` rows out of every
    aggregate even before a migration/re-sync has repaired the local database.
    """
    return case(
        (DADMTallosAttendance.rating.between(1, 10), DADMTallosAttendance.rating),
        else_=None,
    )


def _percentile(values: list[float], p: float) -> float | None:
    values = sorted(float(value) for value in values if value is not None)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * p
    lower = int(index)
    upper = min(len(values) - 1, ceil(index))
    if lower == upper:
        return values[lower]
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _conditions(
    directorate_id: int,
    start_date: date,
    end_date: date,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
):
    conditions = [
        DADMTallosAttendance.directorate_id == directorate_id,
        DADMTallosAttendance.reference_date >= start_date,
        DADMTallosAttendance.reference_date <= end_date,
    ]
    if allowed_departments is not None:
        allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
        if not allowed:
            conditions.append(DADMTallosAttendance.id == -1)
        else:
            conditions.append(func.lower(DADMTallosAttendance.department_key).in_(allowed))
    if department:
        conditions.append(func.lower(DADMTallosAttendance.department_key) == str(department).strip().casefold())
    if employee:
        conditions.append(DADMTallosAttendance.employee_id == employee)
    if channel:
        conditions.append(DADMTallosAttendance.channel == channel)
    if status:
        conditions.append(DADMTallosAttendance.status == status)
    if tabulation:
        conditions.append(DADMTallosAttendance.tabulation == tabulation)
    return conditions


def _percentiles_for(db: Session, column, conditions: list) -> tuple[float | None, float | None]:
    dialect = (db.bind.dialect.name if db.bind is not None else "").lower()
    if dialect == "postgresql":
        row = db.execute(
            select(
                func.percentile_cont(0.5).within_group(column).label("median"),
                func.percentile_cont(0.9).within_group(column).label("p90"),
            ).where(*conditions, column.is_not(None))
        ).one()
        return _float(row.median), _float(row.p90)
    values = [float(v) for v in db.scalars(select(column).where(*conditions, column.is_not(None))).all()]
    return (median(values) if values else None, _percentile(values, 0.90))


def _summary(db: Session, conditions: list) -> dict[str, Any]:
    finalized_case = case((DADMTallosAttendance.status == "finalized", 1), else_=0)
    open_case = case((DADMTallosAttendance.status == "open", 1), else_=0)
    unknown_case = case((DADMTallosAttendance.status == "unknown", 1), else_=0)
    transferred_case = case((DADMTallosAttendance.transferred.is_(True), 1), else_=0)
    valid_rating = _valid_rating_expr()
    row = db.execute(
        select(
            func.count(DADMTallosAttendance.id).label("attendances"),
            func.count(distinct(DADMTallosAttendance.protocol)).label("protocols"),
            func.count(distinct(DADMTallosAttendance.customer_ref)).label("people"),
            func.count(distinct(DADMTallosAttendance.employee_id)).label("active_operators"),
            func.coalesce(func.sum(finalized_case), 0).label("finalized"),
            func.coalesce(func.sum(open_case), 0).label("open"),
            func.coalesce(func.sum(unknown_case), 0).label("unknown"),
            func.avg(DADMTallosAttendance.tme_seconds).label("tme_avg"),
            func.avg(DADMTallosAttendance.tma_seconds).label("tma_avg"),
            func.avg(valid_rating).label("rating_avg"),
            func.count(valid_rating).label("rating_count"),
            func.min(valid_rating).label("rating_min"),
            func.max(valid_rating).label("rating_max"),
            func.coalesce(func.sum(DADMTallosAttendance.messages_sent), 0).label("messages_sent"),
            func.coalesce(func.sum(DADMTallosAttendance.messages_received), 0).label("messages_received"),
            func.coalesce(func.sum(transferred_case), 0).label("transferred"),
        ).where(*conditions)
    ).one()
    tma_median, tma_p90 = _percentiles_for(db, DADMTallosAttendance.tma_seconds, conditions)
    tme_median, tme_p90 = _percentiles_for(db, DADMTallosAttendance.tme_seconds, conditions)
    total = int(row.attendances or 0)
    ratings = int(row.rating_count or 0)
    active_operators = int(row.active_operators or 0)
    finalized = int(row.finalized or 0)
    rating_missing = max(0, total - ratings)
    return {
        "attendances": total,
        "protocols": int(row.protocols or 0),
        "people": int(row.people or 0),
        "active_operators": active_operators,
        "attendances_per_operator": (total / active_operators) if active_operators else None,
        "finalized": finalized,
        "open": int(row.open or 0),
        "unknown": int(row.unknown or 0),
        "finalization_rate_pct": (finalized / total * 100.0) if total else None,
        "tme_avg_seconds": _float(row.tme_avg),
        "tme_median_seconds": tme_median,
        "tme_p90_seconds": tme_p90,
        "tma_avg_seconds": _float(row.tma_avg),
        "tma_median_seconds": tma_median,
        "tma_p90_seconds": tma_p90,
        "rating_avg": _float(row.rating_avg),
        "rating_count": ratings,
        "rating_min": int(row.rating_min) if row.rating_min is not None else None,
        "rating_max": int(row.rating_max) if row.rating_max is not None else None,
        "rating_scale_min": 1,
        "rating_scale_max": 10,
        "rating_missing": rating_missing,
        "rating_missing_pct": (rating_missing / total * 100.0) if total else None,
        "rating_coverage_pct": (ratings / total * 100.0) if total else None,
        # The homologated TALLOS export uses numeric evaluations from 1 to 10.
        # S/A/null and API level=0 are treated as no evaluation. We do not infer
        # an institutional satisfaction threshold without an approved rule.
        "satisfaction_pct": None,
        "dissatisfaction_pct": None,
        "satisfied": None,
        "dissatisfied": None,
        "messages_sent": int(row.messages_sent or 0),
        "messages_received": int(row.messages_received or 0),
        "messages_sent_avg": (int(row.messages_sent or 0) / total) if total else None,
        "messages_received_avg": (int(row.messages_received or 0) / total) if total else None,
        "transferred": int(row.transferred or 0),
        "transfer_rate_pct": (int(row.transferred or 0) / total * 100.0) if total else None,
    }


def _timeline(db: Session, conditions: list, *, grain: str) -> list[dict]:
    key_col = DADMTallosAttendance.reference_date if grain == "day" else DADMTallosAttendance.month_key
    finalized_case = case((DADMTallosAttendance.status == "finalized", 1), else_=0)
    open_case = case((DADMTallosAttendance.status == "open", 1), else_=0)
    valid_rating = _valid_rating_expr()
    rows = db.execute(
        select(
            key_col.label("period"),
            func.count(DADMTallosAttendance.id).label("attendances"),
            func.count(distinct(DADMTallosAttendance.protocol)).label("protocols"),
            func.count(distinct(DADMTallosAttendance.customer_ref)).label("people"),
            func.avg(DADMTallosAttendance.tme_seconds).label("tme"),
            func.avg(DADMTallosAttendance.tma_seconds).label("tma"),
            func.avg(valid_rating).label("rating"),
            func.count(valid_rating).label("rating_count"),
            func.coalesce(func.sum(finalized_case), 0).label("finalized"),
            func.coalesce(func.sum(open_case), 0).label("open"),
        )
        .where(*conditions)
        .group_by(key_col)
        .order_by(key_col)
    ).all()
    out = []
    for row in rows:
        period = row.period.isoformat() if isinstance(row.period, date) else str(row.period)
        out.append({
            "period": period,
            "attendances": int(row.attendances or 0),
            "protocols": int(row.protocols or 0),
            "people": int(row.people or 0),
            "tme_avg_seconds": _float(row.tme),
            "tma_avg_seconds": _float(row.tma),
            "rating_avg": _float(row.rating),
            "rating_count": int(row.rating_count or 0),
            "finalized": int(row.finalized or 0),
            "open": int(row.open or 0),
        })
    return out


def _rating_distribution(db: Session, conditions: list) -> list[dict]:
    rows = dict(db.execute(
        select(DADMTallosAttendance.rating, func.count(DADMTallosAttendance.id))
        .where(*conditions, DADMTallosAttendance.rating.between(1, 10))
        .group_by(DADMTallosAttendance.rating)
        .order_by(DADMTallosAttendance.rating)
    ).all())
    total = sum(int(rows.get(score, 0) or 0) for score in range(1, 11))
    return [{
        "rating": score,
        "count": int(rows.get(score, 0) or 0),
        "pct": (int(rows.get(score, 0) or 0) / total * 100.0) if total else 0.0,
    } for score in range(1, 11)]


def _category_distribution(db: Session, conditions: list, column, *, limit: int = 16) -> list[dict]:
    total = int(db.scalar(
        select(func.count(DADMTallosAttendance.id)).where(*conditions, column.is_not(None))
    ) or 0)
    rows = db.execute(
        select(column, func.count(DADMTallosAttendance.id).label("count"))
        .where(*conditions, column.is_not(None))
        .group_by(column)
        .order_by(func.count(DADMTallosAttendance.id).desc())
        .limit(limit)
    ).all()
    return [{
        "label": str(row[0]),
        "count": int(row.count or 0),
        "pct": (int(row.count or 0) / total * 100.0) if total else 0.0,
    } for row in rows]


def _operator_percentiles(db: Session, conditions: list, ids: list[str]) -> dict[str, tuple[float | None, float | None]]:
    if not ids:
        return {}
    dialect = (db.bind.dialect.name if db.bind is not None else "").lower()
    if dialect == "postgresql":
        rows = db.execute(
            select(
                DADMTallosAttendance.employee_id,
                func.percentile_cont(0.5).within_group(DADMTallosAttendance.tma_seconds).label("median"),
                func.percentile_cont(0.9).within_group(DADMTallosAttendance.tma_seconds).label("p90"),
            )
            .where(*conditions, DADMTallosAttendance.employee_id.in_(ids), DADMTallosAttendance.tma_seconds.is_not(None))
            .group_by(DADMTallosAttendance.employee_id)
        ).all()
        return {str(row.employee_id): (_float(row.median), _float(row.p90)) for row in rows}
    buckets: dict[str, list[float]] = defaultdict(list)
    for employee_id, tma in db.execute(
        select(DADMTallosAttendance.employee_id, DADMTallosAttendance.tma_seconds)
        .where(*conditions, DADMTallosAttendance.employee_id.in_(ids), DADMTallosAttendance.tma_seconds.is_not(None))
    ):
        buckets[str(employee_id)].append(float(tma))
    return {
        key: (median(values) if values else None, _percentile(values, 0.90))
        for key, values in buckets.items()
    }


def _operators(db: Session, conditions: list, *, limit: int = 100) -> list[dict]:
    valid_rating = _valid_rating_expr()
    rows = db.execute(
        select(
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
            func.count(DADMTallosAttendance.id).label("attendances"),
            func.count(distinct(DADMTallosAttendance.protocol)).label("protocols"),
            func.count(distinct(DADMTallosAttendance.customer_ref)).label("people"),
            func.avg(DADMTallosAttendance.tme_seconds).label("tme"),
            func.avg(DADMTallosAttendance.tma_seconds).label("tma"),
            func.avg(valid_rating).label("rating"),
            func.count(valid_rating).label("rating_count"),
            func.coalesce(func.sum(case((DADMTallosAttendance.status == "open", 1), else_=0)), 0).label("open"),
            func.coalesce(func.sum(case((DADMTallosAttendance.status == "finalized", 1), else_=0)), 0).label("finalized"),
        )
        .where(*conditions, DADMTallosAttendance.employee_id.is_not(None))
        .group_by(DADMTallosAttendance.employee_id, DADMTallosAttendance.employee_name)
        .order_by(func.count(DADMTallosAttendance.id).desc())
        .limit(limit)
    ).all()
    out = []
    for row in rows:
        total = int(row.attendances or 0)
        ratings = int(row.rating_count or 0)
        out.append({
            "employee_id": str(row.employee_id),
            "employee_name": row.employee_name or "Operador sem nome",
            "attendances": total,
            "protocols": int(row.protocols or 0),
            "people": int(row.people or 0),
            "tme_avg_seconds": _float(row.tme),
            "tma_avg_seconds": _float(row.tma),
            "rating_avg": _float(row.rating),
            "rating_count": ratings,
            "rating_coverage_pct": ratings / total * 100.0 if total else None,
            "open": int(row.open or 0),
            "finalized": int(row.finalized or 0),
        })
    percentiles = _operator_percentiles(db, conditions, [item["employee_id"] for item in out])
    for item in out:
        item["tma_median_seconds"], item["tma_p90_seconds"] = percentiles.get(item["employee_id"], (None, None))
    return out


def _operator_monthly(db: Session, conditions: list, *, limit: int = 1200) -> list[dict]:
    """Monthly operator facts used for managerial evaluation and time analysis.

    Averages are calculated only from rows with a value. In particular, rating
    NULL never becomes zero and never participates in the monthly mean.
    """
    valid_rating = _valid_rating_expr()
    rows = db.execute(
        select(
            DADMTallosAttendance.month_key.label("period"),
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
            func.count(DADMTallosAttendance.id).label("attendances"),
            func.count(distinct(DADMTallosAttendance.protocol)).label("protocols"),
            func.avg(DADMTallosAttendance.tme_seconds).label("tme"),
            func.avg(DADMTallosAttendance.tma_seconds).label("tma"),
            func.avg(valid_rating).label("rating"),
            func.count(valid_rating).label("rating_count"),
        )
        .where(*conditions, DADMTallosAttendance.employee_id.is_not(None))
        .group_by(
            DADMTallosAttendance.month_key,
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
        )
        .order_by(DADMTallosAttendance.month_key.desc(), DADMTallosAttendance.employee_name)
        .limit(limit)
    ).all()
    out = []
    for row in rows:
        total = int(row.attendances or 0)
        rating_count = int(row.rating_count or 0)
        out.append({
            "period": str(row.period),
            "employee_id": str(row.employee_id),
            "employee_name": row.employee_name or "Operador sem nome",
            "attendances": total,
            "protocols": int(row.protocols or 0),
            "tme_avg_seconds": _float(row.tme),
            "tma_avg_seconds": _float(row.tma),
            "rating_avg": _float(row.rating),
            "rating_count": rating_count,
            "rating_missing": max(0, total - rating_count),
            "rating_coverage_pct": rating_count / total * 100.0 if total else None,
        })
    return out


def rating_audit_payload(
    db: Session,
    directorate_id: int,
    start_date: date,
    end_date: date,
    *,
    employee: str | None = None,
    department: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    sample_limit: int = 120,
    allowed_departments: tuple[str, ...] | None = None,
) -> dict:
    """Reconcile normalized rating against sanitized TALLOS ``level``.

    This endpoint is intentionally audit-focused and is not used by the regular
    dashboard. It never exposes customer PII.
    """
    conditions = _conditions(
        directorate_id, start_date, end_date,
        department=department, employee=employee, channel=channel,
        status=status, tabulation=tabulation, allowed_departments=allowed_departments,
    )
    rows = db.execute(
        select(
            DADMTallosAttendance.source_id,
            DADMTallosAttendance.protocol,
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
            DADMTallosAttendance.reference_date,
            DADMTallosAttendance.month_key,
            DADMTallosAttendance.rating,
            DADMTallosAttendance.source_payload_json,
        )
        .where(*conditions)
        .order_by(DADMTallosAttendance.reference_date.desc(), DADMTallosAttendance.id.desc())
    ).all()

    distribution = {score: 0 for score in range(1, 11)}
    raw_zero = 0
    raw_missing = 0
    raw_other = 0
    samples: list[dict] = []

    for row in rows:
        raw_level = None
        try:
            payload = json.loads(row.source_payload_json or "{}")
            raw_level = payload.get("level")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        parsed = None
        if raw_level is not None and not isinstance(raw_level, bool):
            text = str(raw_level).strip()
            if text and text.casefold() not in {"s/a", "sa", "n/a", "na", "null", "none", "nan", "-", "--"}:
                try:
                    parsed = int(float(text.replace(",", ".")))
                except ValueError:
                    parsed = None
        if parsed == 0:
            raw_zero += 1
            classification = "sem avaliação (level=0)"
        elif parsed is not None and 1 <= parsed <= 10:
            distribution[parsed] += 1
            classification = "avaliação válida"
        elif raw_level is None or (isinstance(raw_level, str) and raw_level.strip().casefold() in {"", "s/a", "sa", "n/a", "na", "null", "none", "nan", "-", "--"}):
            raw_missing += 1
            classification = "sem avaliação"
        else:
            raw_other += 1
            classification = "valor não reconhecido"

        if len(samples) < sample_limit and (parsed == 0 or (parsed is not None and 1 <= parsed <= 10)):
            samples.append({
                "source_id": str(row.source_id),
                "protocol": row.protocol,
                "employee_id": row.employee_id,
                "employee_name": row.employee_name or "Operador sem nome",
                "reference_date": row.reference_date.isoformat() if row.reference_date else None,
                "period": str(row.month_key),
                "raw_level": raw_level,
                "normalized_rating": row.rating if row.rating is not None and 1 <= int(row.rating) <= 10 else None,
                "classification": classification,
            })

    valid_count = sum(distribution.values())
    weighted = sum(score * count for score, count in distribution.items())
    return {
        "rows": len(rows),
        "valid_count": valid_count,
        "valid_average": (weighted / valid_count) if valid_count else None,
        "raw_zero_count": raw_zero,
        "raw_missing_count": raw_missing,
        "raw_other_count": raw_other,
        "distribution": [{"rating": score, "count": distribution[score]} for score in range(1, 11)],
        "samples": samples,
        "contract": {
            "valid_min": 1,
            "valid_max": 10,
            "level_zero": "missing",
            "null_or_sa": "missing",
        },
    }


def _department_labels(db: Session, directorate_id: int) -> dict[str, str]:
    rows = db.execute(
        select(
            DADMTallosDepartmentMap.source_key,
            DADMTallosDepartmentMap.display_name,
            DADMTallosDepartmentMap.updated_by,
        )
        .where(DADMTallosDepartmentMap.directorate_id == directorate_id, DADMTallosDepartmentMap.active.is_(True))
    ).all()
    labels: dict[str, str] = {}
    for key, label, updated_by in rows:
        source_key = str(key)
        if updated_by:
            labels[source_key] = str(label)
            continue
        labels[source_key] = (
            dadm_preferred_department_name(source_key)
            or department_display(source_key)[1]
            or str(label)
        )
    return labels


def _departments(db: Session, directorate_id: int, conditions: list, *, limit: int = 100) -> list[dict]:
    valid_rating = _valid_rating_expr()
    rows = db.execute(
        select(
            DADMTallosAttendance.department_key,
            func.count(DADMTallosAttendance.id).label("attendances"),
            func.count(distinct(DADMTallosAttendance.employee_id)).label("operators"),
            func.count(distinct(DADMTallosAttendance.protocol)).label("protocols"),
            func.avg(DADMTallosAttendance.tme_seconds).label("tme"),
            func.avg(DADMTallosAttendance.tma_seconds).label("tma"),
            func.avg(valid_rating).label("rating"),
            func.count(valid_rating).label("rating_count"),
        )
        .where(*conditions, DADMTallosAttendance.department_key.is_not(None))
        .group_by(DADMTallosAttendance.department_key)
        .order_by(func.count(DADMTallosAttendance.id).desc())
        .limit(limit)
    ).all()
    labels = _department_labels(db, directorate_id)
    return [{
        "department": str(row.department_key),
        "department_name": labels.get(str(row.department_key), str(row.department_key)),
        "attendances": int(row.attendances or 0),
        "operators": int(row.operators or 0),
        "protocols": int(row.protocols or 0),
        "tme_avg_seconds": _float(row.tme),
        "tma_avg_seconds": _float(row.tma),
        "rating_avg": _float(row.rating),
        "rating_count": int(row.rating_count or 0),
    } for row in rows]


def filters_payload(
    db: Session, directorate_id: int, start_date: date, end_date: date,
    *, allowed_departments: tuple[str, ...] | None = None,
) -> dict:
    base = _conditions(directorate_id, start_date, end_date, allowed_departments=allowed_departments)

    def values(column, label_column=None):
        if label_column is None:
            rows = db.execute(select(column).where(*base, column.is_not(None)).distinct().order_by(column)).all()
            return [{"value": str(row[0]), "label": str(row[0])} for row in rows]
        rows = db.execute(
            select(column, label_column).where(*base, column.is_not(None)).distinct().order_by(label_column, column)
        ).all()
        return [{"value": str(value), "label": str(label or value)} for value, label in rows]

    departments = values(DADMTallosAttendance.department_key, DADMTallosAttendance.department_name)
    labels = _department_labels(db, directorate_id)
    for item in departments:
        item["label"] = labels.get(item["value"], item["label"])
    range_conditions = [DADMTallosAttendance.directorate_id == directorate_id]
    if allowed_departments is not None:
        allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
        range_conditions.append(func.lower(DADMTallosAttendance.department_key).in_(allowed) if allowed else DADMTallosAttendance.id == -1)
    range_row = db.execute(
        select(func.min(DADMTallosAttendance.reference_date), func.max(DADMTallosAttendance.reference_date)).where(*range_conditions)
    ).one()
    return {
        "departments": departments,
        "employees": values(DADMTallosAttendance.employee_id, DADMTallosAttendance.employee_name),
        "channels": values(DADMTallosAttendance.channel),
        "statuses": values(DADMTallosAttendance.status),
        "tabulations": values(DADMTallosAttendance.tabulation),
        "available_range": {
            "start": range_row[0].isoformat() if range_row[0] else None,
            "end": range_row[1].isoformat() if range_row[1] else None,
        },
    }


def _shift_month(value: date, months: int) -> date:
    index = value.year * 12 + (value.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    # Clamp day to destination month.
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def comparison_range(start_date: date, end_date: date, mode: str) -> tuple[date, date] | None:
    mode = (mode or "none").strip().lower()
    if mode == "none":
        return None
    if mode == "previous_period":
        days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        return previous_end - timedelta(days=days - 1), previous_end
    if mode == "previous_month":
        return _shift_month(start_date, -1), _shift_month(end_date, -1)
    if mode == "previous_year":
        try:
            return start_date.replace(year=start_date.year - 1), end_date.replace(year=end_date.year - 1)
        except ValueError:
            return _shift_month(start_date, -12), _shift_month(end_date, -12)
    raise ValueError("Modo de comparação inválido.")


def _comparison_deltas(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, float | None]:
    keys = (
        "attendances", "protocols", "people", "finalized", "open",
        "tme_avg_seconds", "tma_avg_seconds", "rating_avg", "rating_count",
        "rating_coverage_pct",
    )
    result: dict[str, float | None] = {}
    for key in keys:
        if not previous:
            result[key] = None
            continue
        a, b = current.get(key), previous.get(key)
        if a is None or b in (None, 0):
            result[key] = None
        else:
            result[key] = (float(a) - float(b)) / abs(float(b)) * 100.0
    return result


def build_tallos_dashboard(
    db: Session,
    directorate_id: int,
    start_date: date,
    end_date: date,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    comparison_mode: str = "previous_period",
    grain: str = "month",
    allowed_departments: tuple[str, ...] | None = None,
) -> dict:
    conditions = _conditions(
        directorate_id,
        start_date,
        end_date,
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
        allowed_departments=allowed_departments,
    )
    current = _summary(db, conditions)
    previous = None
    previous_period = comparison_range(start_date, end_date, comparison_mode)
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
        previous = _summary(db, previous_conditions)

    last_sync = db.scalar(
        select(DADMTallosSyncRun)
        .where(DADMTallosSyncRun.directorate_id == directorate_id, DADMTallosSyncRun.status == "completed")
        .order_by(DADMTallosSyncRun.finished_at.desc(), DADMTallosSyncRun.id.desc())
        .limit(1)
    )
    return {
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "grain": grain},
        "filters": {
            "department": department,
            "employee": employee,
            "channel": channel,
            "status": status,
            "tabulation": tabulation,
        },
        "summary": current,
        "comparison": previous,
        "comparison_mode": comparison_mode,
        "comparison_period": {
            "start": previous_period[0].isoformat(),
            "end": previous_period[1].isoformat(),
        } if previous_period else None,
        "deltas_pct": _comparison_deltas(current, previous),
        "timeline": _timeline(db, conditions, grain=grain),
        "ratings": _rating_distribution(db, conditions),
        "channels": _category_distribution(db, conditions, DADMTallosAttendance.channel),
        "tabulations": _category_distribution(db, conditions, DADMTallosAttendance.tabulation),
        "operators": _operators(db, conditions),
        "operators_monthly": _operator_monthly(db, conditions),
        "departments": _departments(db, directorate_id, conditions),
        "last_sync": {
            "id": last_sync.id,
            "finished_at": last_sync.finished_at.isoformat() if last_sync and last_sync.finished_at else None,
            "end_date": last_sync.end_date.isoformat() if last_sync else None,
        } if last_sync else None,
        "field_status": {
            "employee": "validated",
            "tma": "validated",
            "rating": "validated_1_10",
            "channel": "validated",
            "tabulation": "validated",
            "messages": "validated",
            "initiated_by": "validated",
            "tme": "provisional",
            "department": "mapping_required",
            "tmro": "experimental",
            "tmrc": "experimental",
            "status": "derived",
        },
    }


def operator_comparison(
    db: Session,
    directorate_id: int,
    start_date: date,
    end_date: date,
    employee_ids: Iterable[str],
    *,
    metric: str,
    department: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
) -> dict:
    ids = [str(value).strip() for value in employee_ids if str(value).strip()][:6]
    if not ids:
        return {"metric": metric, "series": []}
    metric = metric.strip().lower()
    metric_exprs = {
        "volume": func.count(DADMTallosAttendance.id),
        "protocols": func.count(distinct(DADMTallosAttendance.protocol)),
        "tma": func.avg(DADMTallosAttendance.tma_seconds),
        "tme": func.avg(DADMTallosAttendance.tme_seconds),
        "rating": func.avg(_valid_rating_expr()),
    }
    if metric not in metric_exprs:
        raise ValueError("Métrica de comparação inválida.")
    conditions = _conditions(
        directorate_id, start_date, end_date,
        department=department, channel=channel, status=status, tabulation=tabulation,
        allowed_departments=allowed_departments,
    )
    rows = db.execute(
        select(
            DADMTallosAttendance.month_key.label("period"),
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
            metric_exprs[metric].label("value"),
            func.count(DADMTallosAttendance.id).label("sample"),
        )
        .where(*conditions, DADMTallosAttendance.employee_id.in_(ids))
        .group_by(DADMTallosAttendance.month_key, DADMTallosAttendance.employee_id, DADMTallosAttendance.employee_name)
        .order_by(DADMTallosAttendance.month_key, DADMTallosAttendance.employee_name)
    ).all()
    return {
        "metric": metric,
        "series": [{
            "period": str(row.period),
            "employee_id": str(row.employee_id),
            "employee_name": row.employee_name or "Operador sem nome",
            "value": _float(row.value),
            "sample": int(row.sample or 0),
        } for row in rows],
    }
