from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AuditLog, DPECostPeriod
from security import DirectorateScope


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _period_label(db: Session, scope: DirectorateScope, period_id: int | None) -> str | None:
    if not period_id:
        return None
    return db.scalar(
        select(DPECostPeriod.period).where(
            DPECostPeriod.id == int(period_id),
            DPECostPeriod.directorate_id == scope.directorate_id,
        )
    )


def _safe_user_id(value: Any) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def add_dpe_audit(
    db: Session,
    scope: DirectorateScope,
    *,
    action: str,
    entity: str,
    entity_id: Any = None,
    period_id: int | None = None,
    before: Any = None,
    after: Any = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    details: dict[str, Any] = {
        "period_id": int(period_id) if period_id else None,
        "period": _period_label(db, scope, period_id),
    }
    if before is not None:
        details["before"] = _json_safe(before)
    if after is not None:
        details["after"] = _json_safe(after)
    if metadata:
        details.update(_json_safe(metadata))
    row = AuditLog(
        directorate_id=scope.directorate_id,
        user_id=_safe_user_id(scope.user.user_id),
        user_email=scope.user.email,
        action=str(action)[:40],
        entity=str(entity)[:80],
        entity_id=str(entity_id)[:80] if entity_id is not None else None,
        details=json.dumps(details, ensure_ascii=False, default=str),
    )
    db.add(row)
    return row


def parse_audit_details(row: AuditLog) -> dict[str, Any]:
    if not row.details:
        return {}
    try:
        value = json.loads(row.details)
        return value if isinstance(value, dict) else {"value": value}
    except Exception:
        return {"raw": row.details}


def list_dpe_period_audit(
    db: Session,
    scope: DirectorateScope,
    period_id: int,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    # The legacy audit table is shared by modules. DPE records use the dpe_* entity
    # namespace. Filtering period_id happens after JSON parsing to keep SQLite and
    # PostgreSQL behavior identical without vendor-specific JSON expressions.
    rows = db.scalars(
        select(AuditLog).where(
            AuditLog.directorate_id == scope.directorate_id,
            AuditLog.entity.like("dpe_%"),
        ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(max(200, min(int(limit) * 6, 1500)))
    ).all()
    output: list[dict[str, Any]] = []
    for row in rows:
        details = parse_audit_details(row)
        related = details.get("period_id")
        if related is None and row.entity == "dpe_cost_period":
            try:
                related = int(row.entity_id or 0)
            except (TypeError, ValueError):
                related = None
        if int(related or 0) != int(period_id):
            continue
        output.append({
            "id": row.id,
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "user_email": row.user_email,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "period_id": int(period_id),
            "period": details.get("period"),
            "before": details.get("before"),
            "after": details.get("after"),
            "metadata": {key: value for key, value in details.items() if key not in {"period_id", "period", "before", "after"}},
        })
        if len(output) >= max(1, min(int(limit), 500)):
            break
    return output
