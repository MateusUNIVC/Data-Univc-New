from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from dadm_tallos_analytics import (
    _conditions,
    _department_labels,
    _float,
    _valid_rating_expr,
    build_tallos_dashboard,
)
from models import DADMTallosAttendance

MAX_MONTH_WINDOW = 60


def parse_month(value: str) -> tuple[int, int]:
    text = str(value or "").strip()
    if len(text) != 7 or text[4] != "-":
        raise ValueError("O mês deve estar no formato AAAA-MM.")
    try:
        year = int(text[:4])
        month = int(text[5:])
    except ValueError as exc:
        raise ValueError("O mês deve estar no formato AAAA-MM.") from exc
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ValueError("Mês inválido.")
    return year, month


def month_start(value: str) -> date:
    year, month = parse_month(value)
    return date(year, month, 1)


def month_end(value: str) -> date:
    year, month = parse_month(value)
    return date(year, month, monthrange(year, month)[1])


def month_index(value: str) -> int:
    year, month = parse_month(value)
    return year * 12 + month - 1


def resolve_month_range(
    db: Session,
    directorate_id: int,
    from_month: str | None,
    to_month: str | None,
    *,
    allowed_departments: tuple[str, ...] | None = None,
) -> tuple[str, str, date, date]:
    scope_conditions = [DADMTallosAttendance.directorate_id == directorate_id]
    if allowed_departments is not None:
        allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
        scope_conditions.append(func.lower(DADMTallosAttendance.department_key).in_(allowed) if allowed else DADMTallosAttendance.id == -1)
    bounds = db.execute(
        select(
            func.min(DADMTallosAttendance.reference_date),
            func.max(DADMTallosAttendance.reference_date),
        ).where(*scope_conditions)
    ).one()
    latest = bounds[1] or date.today()
    fallback = f"{latest.year:04d}-{latest.month:02d}"
    start_month = (from_month or fallback).strip()
    end_month = (to_month or start_month).strip()
    start_idx = month_index(start_month)
    end_idx = month_index(end_month)
    if end_idx < start_idx:
        raise ValueError("O mês final não pode ser anterior ao mês inicial.")
    if end_idx - start_idx + 1 > MAX_MONTH_WINDOW:
        raise ValueError(f"O contexto de análise aceita no máximo {MAX_MONTH_WINDOW} meses por consulta.")
    return start_month, end_month, month_start(start_month), month_end(end_month)


def _filter_kwargs(
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
) -> dict[str, str | None]:
    return {
        "department": department,
        "employee": employee,
        "channel": channel,
        "status": status,
        "tabulation": tabulation,
    }


def _values(db: Session, conditions: list, column, label_column=None) -> list[dict[str, str]]:
    if label_column is None:
        rows = db.execute(
            select(column)
            .where(*conditions, column.is_not(None))
            .distinct()
            .order_by(column)
        ).all()
        return [{"value": str(row[0]), "label": str(row[0])} for row in rows if row[0] not in (None, "")]
    rows = db.execute(
        select(column, label_column)
        .where(*conditions, column.is_not(None))
        .distinct()
        .order_by(label_column, column)
    ).all()
    return [
        {"value": str(value), "label": str(label or value)}
        for value, label in rows
        if value not in (None, "")
    ]


def context_payload(
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
) -> dict[str, Any]:
    start_month, end_month, start_date, end_date = resolve_month_range(
        db, directorate_id, from_month, to_month, allowed_departments=allowed_departments
    )
    selected = _filter_kwargs(
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
    )

    def conditions_without(excluded: str) -> list:
        values = dict(selected)
        values[excluded] = None
        return _conditions(directorate_id, start_date, end_date, allowed_departments=allowed_departments, **values)

    departments = _values(
        db,
        conditions_without("department"),
        DADMTallosAttendance.department_key,
        DADMTallosAttendance.department_name,
    )
    labels = _department_labels(db, directorate_id)
    for item in departments:
        item["label"] = labels.get(item["value"], item["label"])

    employees = _values(
        db,
        conditions_without("employee"),
        DADMTallosAttendance.employee_id,
        DADMTallosAttendance.employee_name,
    )
    channels = _values(db, conditions_without("channel"), DADMTallosAttendance.channel)
    statuses = _values(db, conditions_without("status"), DADMTallosAttendance.status)
    tabulations = _values(db, conditions_without("tabulation"), DADMTallosAttendance.tabulation)

    bounds_conditions = [DADMTallosAttendance.directorate_id == directorate_id]
    if allowed_departments is not None:
        allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
        bounds_conditions.append(func.lower(DADMTallosAttendance.department_key).in_(allowed) if allowed else DADMTallosAttendance.id == -1)
    bounds = db.execute(
        select(
            func.min(DADMTallosAttendance.reference_date),
            func.max(DADMTallosAttendance.reference_date),
        ).where(*bounds_conditions)
    ).one()
    return {
        "period": {
            "from_month": start_month,
            "to_month": end_month,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "available_range": {
            "start": bounds[0].isoformat() if bounds[0] else None,
            "end": bounds[1].isoformat() if bounds[1] else None,
            "start_month": f"{bounds[0].year:04d}-{bounds[0].month:02d}" if bounds[0] else None,
            "end_month": f"{bounds[1].year:04d}-{bounds[1].month:02d}" if bounds[1] else None,
        },
        "selected": selected,
        "departments": departments,
        "employees": employees,
        "channels": channels,
        "statuses": statuses,
        "tabulations": tabulations,
    }


def _normalize_department_items(items: list[dict]) -> list[dict]:
    out = []
    for item in items:
        total = int(item.get("attendances") or 0)
        ratings = int(item.get("rating_count") or 0)
        out.append({
            "entity_type": "department",
            "id": item.get("department"),
            "name": item.get("department_name") or item.get("department") or "Departamento sem nome",
            "attendances": total,
            "protocols": int(item.get("protocols") or 0),
            "people": item.get("people"),
            "active_operators": int(item.get("operators") or 0),
            "tme_avg_seconds": item.get("tme_avg_seconds"),
            "tma_avg_seconds": item.get("tma_avg_seconds"),
            "rating_avg": item.get("rating_avg"),
            "rating_count": ratings,
            "rating_coverage_pct": (ratings / total * 100.0) if total else None,
            "open": int(item.get("open") or 0),
            "finalized": int(item.get("finalized") or 0),
        })
    return out


def _normalize_employee_items(items: list[dict]) -> list[dict]:
    return [{
        "entity_type": "employee",
        "id": item.get("employee_id"),
        "name": item.get("employee_name") or "Operador sem nome",
        "attendances": int(item.get("attendances") or 0),
        "protocols": int(item.get("protocols") or 0),
        "people": int(item.get("people") or 0),
        "active_operators": 1,
        "tme_avg_seconds": item.get("tme_avg_seconds"),
        "tma_avg_seconds": item.get("tma_avg_seconds"),
        "tma_median_seconds": item.get("tma_median_seconds"),
        "tma_p90_seconds": item.get("tma_p90_seconds"),
        "rating_avg": item.get("rating_avg"),
        "rating_count": int(item.get("rating_count") or 0),
        "rating_coverage_pct": item.get("rating_coverage_pct"),
        "open": int(item.get("open") or 0),
        "finalized": int(item.get("finalized") or 0),
    } for item in items]


def overview_payload(
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
    comparison_mode: str = "previous_period",
    allowed_departments: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    start_month, end_month, start_date, end_date = resolve_month_range(
        db, directorate_id, from_month, to_month, allowed_departments=allowed_departments
    )
    dashboard = build_tallos_dashboard(
        db,
        directorate_id,
        start_date,
        end_date,
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
        comparison_mode=comparison_mode,
        grain="month",
        allowed_departments=allowed_departments,
    )
    dashboard["period"]["from_month"] = start_month
    dashboard["period"]["to_month"] = end_month
    dashboard["entities"] = {
        "employees": _normalize_employee_items(dashboard.get("operators") or []),
        "departments": _normalize_department_items(dashboard.get("departments") or []),
    }
    return dashboard


def entity_profile_payload(
    db: Session,
    directorate_id: int,
    kind: str,
    entity_id: str,
    from_month: str | None = None,
    to_month: str | None = None,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    kind = str(kind or "").strip().lower()
    if kind not in {"employee", "department"}:
        raise ValueError("Tipo de entidade inválido.")
    filters = _filter_kwargs(
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
    )
    if kind == "employee":
        filters["employee"] = entity_id
    else:
        filters["department"] = entity_id
    dashboard = overview_payload(
        db,
        directorate_id,
        from_month,
        to_month,
        **filters,
        comparison_mode="previous_period",
        allowed_departments=allowed_departments,
    )

    if kind == "employee":
        entity_candidates = dashboard["entities"]["employees"]
        composition = dashboard["entities"]["departments"]
        composition_type = "department"
    else:
        entity_candidates = dashboard["entities"]["departments"]
        composition = dashboard["entities"]["employees"]
        composition_type = "employee"

    entity = entity_candidates[0] if entity_candidates else {
        "entity_type": kind,
        "id": entity_id,
        "name": entity_id,
        **dashboard["summary"],
    }
    return {
        "period": dashboard["period"],
        "entity": entity,
        "summary": dashboard["summary"],
        "deltas_pct": dashboard.get("deltas_pct") or {},
        "timeline": dashboard.get("timeline") or [],
        "ratings": dashboard.get("ratings") or [],
        "channels": dashboard.get("channels") or [],
        "tabulations": dashboard.get("tabulations") or [],
        "composition_type": composition_type,
        "composition": composition,
        "last_sync": dashboard.get("last_sync"),
    }


def entity_evaluations_payload(
    db: Session,
    directorate_id: int,
    kind: str,
    entity_id: str,
    from_month: str | None = None,
    to_month: str | None = None,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    page: int = 1,
    page_size: int = 20,
    order: str = "newest",
    allowed_departments: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return rated TALLOS sessions for one employee or department.

    The endpoint is intentionally session-based (``source_id``), not protocol-based,
    so separate TALLOS sessions that share a protocol remain independently auditable.
    Customer identity and source payload are never selected.
    """
    kind = str(kind or "").strip().lower()
    if kind not in {"employee", "department"}:
        raise ValueError("Tipo de entidade inv\u00e1lido.")
    page = int(page or 1)
    page_size = int(page_size or 20)
    if page < 1:
        raise ValueError("A p\u00e1gina deve ser maior ou igual a 1.")
    if page_size < 1 or page_size > 100:
        raise ValueError("O tamanho da p\u00e1gina deve ficar entre 1 e 100.")
    order = str(order or "newest").strip().lower()
    if order not in {"newest", "lowest", "highest"}:
        raise ValueError("Ordena\u00e7\u00e3o inv\u00e1lida.")

    start_month, end_month, start_date, end_date = resolve_month_range(
        db, directorate_id, from_month, to_month, allowed_departments=allowed_departments
    )
    filters = _filter_kwargs(
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
    )
    if kind == "employee":
        filters["employee"] = entity_id
    else:
        filters["department"] = entity_id

    conditions = _conditions(
        directorate_id,
        start_date,
        end_date,
        allowed_departments=allowed_departments,
        **filters,
    )
    conditions.append(DADMTallosAttendance.rating.between(1, 10))

    total = int(db.scalar(select(func.count(DADMTallosAttendance.id)).where(*conditions)) or 0)
    if order == "lowest":
        ordering = (
            DADMTallosAttendance.rating.asc(),
            DADMTallosAttendance.reference_at.desc(),
            DADMTallosAttendance.id.desc(),
        )
    elif order == "highest":
        ordering = (
            DADMTallosAttendance.rating.desc(),
            DADMTallosAttendance.reference_at.desc(),
            DADMTallosAttendance.id.desc(),
        )
    else:
        ordering = (
            DADMTallosAttendance.reference_at.desc(),
            DADMTallosAttendance.id.desc(),
        )

    rows = db.execute(
        select(
            DADMTallosAttendance.source_id,
            DADMTallosAttendance.protocol,
            DADMTallosAttendance.reference_at,
            DADMTallosAttendance.reference_date,
            DADMTallosAttendance.rating,
            DADMTallosAttendance.tme_seconds,
            DADMTallosAttendance.tma_seconds,
            DADMTallosAttendance.channel,
            DADMTallosAttendance.tabulation,
            DADMTallosAttendance.status,
            DADMTallosAttendance.employee_id,
            DADMTallosAttendance.employee_name,
            DADMTallosAttendance.department_key,
            DADMTallosAttendance.department_name,
        )
        .where(*conditions)
        .order_by(*ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        {
            "source_id": str(row.source_id),
            "protocol": row.protocol,
            "reference_at": row.reference_at.isoformat() if row.reference_at else None,
            "reference_date": row.reference_date.isoformat() if row.reference_date else None,
            "rating": int(row.rating),
            "tme_seconds": _float(row.tme_seconds),
            "tma_seconds": _float(row.tma_seconds),
            "channel": row.channel,
            "tabulation": row.tabulation,
            "status": row.status,
            "employee_id": row.employee_id,
            "employee_name": row.employee_name,
            "department_key": row.department_key,
            "department_name": row.department_name,
        }
        for row in rows
    ]
    pages = (total + page_size - 1) // page_size if total else 0
    return {
        "period": {"from_month": start_month, "to_month": end_month},
        "entity": {"kind": kind, "id": entity_id},
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": pages,
            "has_previous": page > 1,
            "has_next": page * page_size < total,
        },
        "order": order,
        "items": items,
    }


def experience_breakdown(
    db: Session,
    directorate_id: int,
    dimension: str,
    from_month: str | None = None,
    to_month: str | None = None,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    dashboard = overview_payload(
        db,
        directorate_id,
        from_month,
        to_month,
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
        comparison_mode="none",
        allowed_departments=allowed_departments,
    )
    dimension = str(dimension or "employee").strip().lower()
    if dimension == "employee":
        items = dashboard["entities"]["employees"]
    elif dimension == "department":
        items = dashboard["entities"]["departments"]
    elif dimension in {"channel", "tabulation"}:
        source = dashboard["channels"] if dimension == "channel" else dashboard["tabulations"]
        # Category distributions do not carry rating averages. Query them as a
        # real analytical dimension so the UX does not pretend volume equals experience.
        start_date = date.fromisoformat(dashboard["period"]["start"])
        end_date = date.fromisoformat(dashboard["period"]["end"])
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
        column = DADMTallosAttendance.channel if dimension == "channel" else DADMTallosAttendance.tabulation
        valid_rating = _valid_rating_expr()
        rows = db.execute(
            select(
                column.label("key"),
                func.count(DADMTallosAttendance.id).label("attendances"),
                func.avg(valid_rating).label("rating"),
                func.count(valid_rating).label("rating_count"),
                func.avg(DADMTallosAttendance.tme_seconds).label("tme"),
                func.avg(DADMTallosAttendance.tma_seconds).label("tma"),
            )
            .where(*conditions, column.is_not(None))
            .group_by(column)
            .order_by(func.count(DADMTallosAttendance.id).desc())
            .limit(100)
        ).all()
        items = []
        for row in rows:
            total = int(row.attendances or 0)
            ratings = int(row.rating_count or 0)
            items.append({
                "entity_type": dimension,
                "id": str(row.key),
                "name": str(row.key),
                "attendances": total,
                "rating_avg": _float(row.rating),
                "rating_count": ratings,
                "rating_coverage_pct": (ratings / total * 100.0) if total else None,
                "tme_avg_seconds": _float(row.tme),
                "tma_avg_seconds": _float(row.tma),
            })
    else:
        raise ValueError("Dimensão de experiência inválida.")
    return {
        "period": dashboard["period"],
        "dimension": dimension,
        "summary": dashboard["summary"],
        "timeline": dashboard["timeline"],
        "ratings": dashboard["ratings"],
        "items": items,
    }


def quality_payload(
    db: Session, directorate_id: int, *, allowed_departments: tuple[str, ...] | None = None
) -> dict[str, Any]:
    base = [DADMTallosAttendance.directorate_id == directorate_id]
    if allowed_departments is not None:
        allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
        base.append(func.lower(DADMTallosAttendance.department_key).in_(allowed) if allowed else DADMTallosAttendance.id == -1)
    total = db.scalar(select(func.count(DADMTallosAttendance.id)).where(*base)) or 0
    missing_employee = db.scalar(select(func.count(DADMTallosAttendance.id)).where(
        *base,
        DADMTallosAttendance.employee_id.is_(None),
    )) or 0
    missing_protocol = db.scalar(select(func.count(DADMTallosAttendance.id)).where(
        *base,
        DADMTallosAttendance.protocol.is_(None),
    )) or 0
    missing_department = db.scalar(select(func.count(DADMTallosAttendance.id)).where(
        *base,
        DADMTallosAttendance.department_key.is_(None),
    )) or 0
    invalid_rating = db.scalar(select(func.count(DADMTallosAttendance.id)).where(
        *base,
        DADMTallosAttendance.rating.is_not(None),
        ~DADMTallosAttendance.rating.between(1, 10),
    )) or 0
    invalid_time = db.scalar(select(func.count(DADMTallosAttendance.id)).where(
        *base,
        DADMTallosAttendance.finished_at.is_not(None),
        DADMTallosAttendance.started_at.is_not(None),
        DADMTallosAttendance.finished_at < DADMTallosAttendance.started_at,
    )) or 0
    return {
        "total": int(total),
        "issues": [
            {"key": "invalid_rating", "label": "Avaliações fora da escala 1–10", "count": int(invalid_rating)},
            {"key": "missing_employee", "label": "Registros sem operador", "count": int(missing_employee)},
            {"key": "missing_department", "label": "Registros sem departamento", "count": int(missing_department)},
            {"key": "missing_protocol", "label": "Atendimentos sem protocolo", "count": int(missing_protocol)},
            {"key": "invalid_time", "label": "Sessões com inconsistência temporal", "count": int(invalid_time)},
        ],
    }
