from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Directorate, Profile, UserDirectorateAccess

ROLE_REITORIA = "REITORIA"
ROLE_DIRECTORATE = "DIRECTORATE"
GLOBAL_ROLES = {ROLE_REITORIA, ROLE_DIRECTORATE}
ACCESS_READ = "READ"
ACCESS_EDIT = "EDIT"
ACCESS_LEVELS = {ACCESS_READ, ACCESS_EDIT}


@dataclass(frozen=True)
class DirectorateGrant:
    directorate_id: int
    code: str
    name: str
    access: str
    is_primary: bool = False


@dataclass(frozen=True)
class IdentityAccess:
    user_id: str
    auth_provider: str
    auth_provider_id: str
    email: str
    name: str
    global_role: str
    active: bool
    permission_version: int
    directorates: tuple[DirectorateGrant, ...]

    @property
    def global_access(self) -> bool:
        return self.global_role == ROLE_REITORIA


def _resolve_app_user(db: Session, subject: AppUser | Profile | str) -> AppUser:
    if isinstance(subject, AppUser):
        return subject
    if isinstance(subject, Profile):
        app_user = db.get(AppUser, str(subject.id))
    else:
        identifier = str(subject or "").strip()
        app_user = db.get(AppUser, identifier) if identifier else None
        if not app_user and identifier:
            app_user = db.scalar(
                select(AppUser).where(
                    AppUser.auth_provider == "SUPABASE",
                    AppUser.auth_provider_id == identifier,
                )
            )
    if not app_user:
        raise LookupError("Usuário não provisionado no Identity & Access V2.")
    return app_user


def load_identity_access(db: Session, subject: AppUser | Profile | str) -> IdentityAccess:
    """Load the canonical Identity & Access V2 source of truth.

    v0.9.5 removes the legacy profile-based authorization fallback. Profile is
    accepted only as a lookup handle for older internal callers/tests; all role,
    status and directorate decisions come from app_users + user_directorate_access.
    """
    app_user = _resolve_app_user(db, subject)
    global_role = str(app_user.global_role or ROLE_DIRECTORATE).upper()
    if global_role not in GLOBAL_ROLES:
        global_role = ROLE_DIRECTORATE

    rows = db.execute(
        select(UserDirectorateAccess, Directorate)
        .join(Directorate, Directorate.id == UserDirectorateAccess.directorate_id)
        .where(
            UserDirectorateAccess.user_id == app_user.id,
            Directorate.active.is_(True),
        )
        .order_by(UserDirectorateAccess.is_primary.desc(), Directorate.code.asc())
    ).all()
    grants: list[DirectorateGrant] = []
    for access_row, directorate in rows:
        level = str(access_row.access_level or ACCESS_READ).upper()
        if level not in ACCESS_LEVELS:
            level = ACCESS_READ
        grants.append(
            DirectorateGrant(
                directorate_id=directorate.id,
                code=directorate.code,
                name=directorate.name,
                access=level,
                is_primary=bool(access_row.is_primary),
            )
        )

    return IdentityAccess(
        user_id=str(app_user.id),
        auth_provider=str(app_user.auth_provider or "SUPABASE").upper(),
        auth_provider_id=str(app_user.auth_provider_id or ""),
        email=app_user.email or "",
        name=app_user.name or app_user.email or "Usuário",
        global_role=global_role,
        active=bool(app_user.active),
        permission_version=max(1, int(app_user.permission_version or 1)),
        directorates=tuple(grants),
    )


def primary_grant(identity: IdentityAccess, _profile: Profile | None = None) -> DirectorateGrant | None:
    """Pick the canonical primary/home directorate from V2 grants only."""
    for grant in identity.directorates:
        if grant.is_primary:
            return grant
    return identity.directorates[0] if identity.directorates else None
