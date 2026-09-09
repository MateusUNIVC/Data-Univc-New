from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from models import AuthAuditLog

LOGIN_RATE_LIMIT_ENABLED = os.getenv("LOGIN_RATE_LIMIT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
LOGIN_RATE_LIMIT_WINDOW_SECONDS = max(60, int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900")))
# If enabled later in production, default to a generous per-email threshold and
# no shared-IP hard lock. This avoids blocking a campus Wi-Fi/NAT population.
LOGIN_RATE_LIMIT_EMAIL_FAILURES = max(0, int(os.getenv("LOGIN_RATE_LIMIT_EMAIL_FAILURES", "30")))
LOGIN_RATE_LIMIT_IP_FAILURES = max(0, int(os.getenv("LOGIN_RATE_LIMIT_IP_FAILURES", "0")))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: str | None) -> str | None:
    email = str(value or "").strip().casefold()
    return email or None


def log_auth_event(
    db: Session,
    event_type: str,
    *,
    outcome: str = "INFO",
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    email: str | None = None,
    directorate_code: str | None = None,
    ip_hash: str | None = None,
    user_agent_hash: str | None = None,
    details: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuthAuditLog:
    row = AuthAuditLog(
        event_type=str(event_type or "UNKNOWN").strip().upper(),
        outcome=str(outcome or "INFO").strip().upper(),
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        email=normalize_email(email),
        directorate_code=str(directorate_code or "").strip().upper() or None,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        details=dict(details or {}),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def recent_login_failure_counts(
    db: Session,
    *,
    email: str | None,
    ip_hash: str | None,
    now: datetime | None = None,
) -> tuple[int, int]:
    current = now or utcnow()
    since = current - timedelta(seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    normalized_email = normalize_email(email)

    email_count = 0
    ip_count = 0
    if normalized_email:
        email_count = int(db.scalar(
            select(func.count(AuthAuditLog.id)).where(
                AuthAuditLog.event_type == "LOGIN_FAILED",
                AuthAuditLog.created_at >= since,
                AuthAuditLog.email == normalized_email,
            )
        ) or 0)
    if ip_hash:
        ip_count = int(db.scalar(
            select(func.count(AuthAuditLog.id)).where(
                AuthAuditLog.event_type == "LOGIN_FAILED",
                AuthAuditLog.created_at >= since,
                AuthAuditLog.ip_hash == ip_hash,
            )
        ) or 0)
    return email_count, ip_count


def login_rate_limit_exceeded(
    db: Session,
    *,
    email: str | None,
    ip_hash: str | None,
    now: datetime | None = None,
) -> bool:
    if not LOGIN_RATE_LIMIT_ENABLED:
        return False
    email_count, ip_count = recent_login_failure_counts(db, email=email, ip_hash=ip_hash, now=now)
    email_blocked = LOGIN_RATE_LIMIT_EMAIL_FAILURES > 0 and email_count >= LOGIN_RATE_LIMIT_EMAIL_FAILURES
    ip_blocked = LOGIN_RATE_LIMIT_IP_FAILURES > 0 and ip_count >= LOGIN_RATE_LIMIT_IP_FAILURES
    return email_blocked or ip_blocked


def audit_query(
    db: Session,
    *,
    event_type: str | None = None,
    user_id: str | None = None,
    email: str | None = None,
    limit: int = 100,
) -> list[AuthAuditLog]:
    statement = select(AuthAuditLog)
    if event_type:
        statement = statement.where(AuthAuditLog.event_type == str(event_type).strip().upper())
    if user_id:
        statement = statement.where(or_(AuthAuditLog.actor_user_id == user_id, AuthAuditLog.target_user_id == user_id))
    if email:
        statement = statement.where(AuthAuditLog.email == normalize_email(email))
    return list(db.scalars(statement.order_by(AuthAuditLog.created_at.desc()).limit(max(1, min(limit, 500)))).all())
