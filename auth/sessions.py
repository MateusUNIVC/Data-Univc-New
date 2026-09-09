from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from models import AuthSession

REFRESH_TOKEN_TTL_SECONDS = max(300, int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", str(24 * 60 * 60))))
SESSION_ABSOLUTE_TTL_SECONDS = max(
    REFRESH_TOKEN_TTL_SECONDS,
    int(os.getenv("SESSION_ABSOLUTE_TTL_SECONDS", str(24 * 60 * 60))),
)
SESSION_IDLE_TTL_SECONDS = max(300, int(os.getenv("SESSION_IDLE_TTL_SECONDS", str(24 * 60 * 60))))
MAX_ACTIVE_SESSION_FAMILIES_PER_USER = max(1, int(os.getenv("MAX_ACTIVE_SESSION_FAMILIES_PER_USER", "5")))


class RefreshSessionError(ValueError):
    pass


class RefreshSessionInvalid(RefreshSessionError):
    pass


class RefreshSessionExpired(RefreshSessionError):
    pass


class RefreshSessionReused(RefreshSessionError):
    pass


@dataclass(frozen=True)
class RefreshSessionIssue:
    raw_token: str
    session: AuthSession


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def fingerprint_hash(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    # IP addresses have low entropy and a plain SHA-256 can be brute-forced.
    # Keyed HMAC keeps audit/session fingerprints stable without storing raw data.
    secret = (
        os.getenv("DATA_UNIVC_FINGERPRINT_SECRET", "").strip()
        or os.getenv("DATA_UNIVC_JWT_SECRET", "").strip()
        or "data-univc-development-fingerprint-v1"
    )
    return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def request_fingerprints(user_agent: str | None, ip_address: str | None) -> tuple[str | None, str | None]:
    return fingerprint_hash(user_agent), fingerprint_hash(ip_address)


def _new_raw_token() -> str:
    return secrets.token_urlsafe(32)


def _family_expires_at(family_created_at: datetime, current: datetime) -> datetime:
    absolute = family_created_at + timedelta(seconds=SESSION_ABSOLUTE_TTL_SECONDS)
    rolling = current + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)
    return min(absolute, rolling)


def revoke_family(db: Session, token_family: str, *, now: datetime | None = None, commit: bool = True) -> int:
    current = now or utcnow()
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.token_family == token_family, AuthSession.revoked_at.is_(None))
        .values(revoked_at=current, last_seen_at=current)
    )
    if commit:
        db.commit()
    return int(result.rowcount or 0)


def revoke_user_sessions(db: Session, user_id: str, *, now: datetime | None = None, commit: bool = True) -> int:
    current = now or utcnow()
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=current, last_seen_at=current)
    )
    if commit:
        db.commit()
    return int(result.rowcount or 0)


def revoke_session_by_id(db: Session, session_id: str, *, now: datetime | None = None) -> int:
    row = db.get(AuthSession, str(session_id))
    if not row:
        return 0
    return revoke_family(db, row.token_family, now=now)


def _active_family_rows(db: Session, user_id: str) -> list[AuthSession]:
    return list(db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.family_created_at.desc(), AuthSession.created_at.desc())
    ).all())


def enforce_session_family_limit(db: Session, user_id: str, *, now: datetime | None = None) -> int:
    current = now or utcnow()
    active = _active_family_rows(db, user_id)
    # Only one unrevoked row should exist per family. Be defensive if historical
    # data violates that invariant and deduplicate by family before limiting.
    families: list[str] = []
    seen: set[str] = set()
    for row in active:
        family = str(row.token_family)
        if family in seen:
            continue
        seen.add(family)
        families.append(family)
    revoked = 0
    for family in families[MAX_ACTIVE_SESSION_FAMILIES_PER_USER:]:
        revoked += revoke_family(db, family, now=current, commit=False)
    if revoked:
        db.commit()
    return revoked


def create_refresh_session(
    db: Session,
    *,
    user_id: str,
    user_agent_hash: str | None = None,
    ip_hash: str | None = None,
    token_family: str | None = None,
    family_created_at: datetime | None = None,
    now: datetime | None = None,
) -> RefreshSessionIssue:
    current = now or utcnow()
    family_start = _coerce_utc(family_created_at) or current
    raw = _new_raw_token()
    row = AuthSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(raw),
        token_family=token_family or str(uuid.uuid4()),
        family_created_at=family_start,
        created_at=current,
        last_seen_at=current,
        expires_at=_family_expires_at(family_start, current),
        revoked_at=None,
        user_agent_hash=user_agent_hash,
        ip_hash=ip_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    enforce_session_family_limit(db, user_id, now=current)
    return RefreshSessionIssue(raw_token=raw, session=row)


def rotate_refresh_session(
    db: Session,
    raw_token: str,
    *,
    user_agent_hash: str | None = None,
    ip_hash: str | None = None,
    now: datetime | None = None,
) -> RefreshSessionIssue:
    current = now or utcnow()
    token_hash = hash_refresh_token(raw_token)
    row = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash))
    if not row:
        raise RefreshSessionInvalid("Refresh token inválido.")

    if row.revoked_at is not None:
        revoke_family(db, row.token_family, now=current)
        raise RefreshSessionReused("Refresh token já utilizado ou revogado.")

    family_start = _coerce_utc(getattr(row, "family_created_at", None)) or _coerce_utc(row.created_at) or current
    expires_at = _coerce_utc(row.expires_at)
    last_seen = _coerce_utc(row.last_seen_at) or _coerce_utc(row.created_at) or current
    absolute_expires = family_start + timedelta(seconds=SESSION_ABSOLUTE_TTL_SECONDS)
    idle_expires = last_seen + timedelta(seconds=SESSION_IDLE_TTL_SECONDS)
    if not expires_at or expires_at <= current or absolute_expires <= current or idle_expires <= current:
        revoke_family(db, row.token_family, now=current)
        raise RefreshSessionExpired("Sessão expirada. Faça login novamente.")

    row.revoked_at = current
    row.last_seen_at = current
    raw = _new_raw_token()
    replacement = AuthSession(
        id=str(uuid.uuid4()),
        user_id=row.user_id,
        refresh_token_hash=hash_refresh_token(raw),
        token_family=row.token_family,
        family_created_at=family_start,
        created_at=current,
        last_seen_at=current,
        expires_at=_family_expires_at(family_start, current),
        revoked_at=None,
        user_agent_hash=user_agent_hash,
        ip_hash=ip_hash,
    )
    db.add(replacement)
    db.commit()
    db.refresh(replacement)
    return RefreshSessionIssue(raw_token=raw, session=replacement)


def revoke_refresh_session(db: Session, raw_token: str, *, now: datetime | None = None) -> bool:
    token_hash = hash_refresh_token(raw_token)
    row = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash))
    if not row:
        return False
    if row.revoked_at is None:
        revoke_family(db, row.token_family, now=now)
    return True


def active_session_rows(db: Session, user_id: str, *, now: datetime | None = None) -> list[AuthSession]:
    current = now or utcnow()
    rows = _active_family_rows(db, user_id)
    out: list[AuthSession] = []
    for row in rows:
        expires = _coerce_utc(row.expires_at)
        family_start = _coerce_utc(getattr(row, "family_created_at", None)) or _coerce_utc(row.created_at) or current
        last_seen = _coerce_utc(row.last_seen_at) or current
        if expires and expires > current and family_start + timedelta(seconds=SESSION_ABSOLUTE_TTL_SECONDS) > current and last_seen + timedelta(seconds=SESSION_IDLE_TTL_SECONDS) > current:
            out.append(row)
    return out
