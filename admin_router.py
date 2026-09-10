from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from auth.access import ACCESS_EDIT, ACCESS_READ, ROLE_DIRECTORATE, ROLE_REITORIA
from auth.audit import audit_query, log_auth_event
from auth.identity_admin import (
    IdentityAdminError,
    create_identity,
    delete_avatar,
    delete_identity,
    download_avatar,
    update_identity,
    upload_avatar,
)
from auth.sessions import active_session_rows, revoke_session_by_id, revoke_user_sessions
from database import get_db
from models import AppUser, AuthSession, Directorate, Profile, UserDirectorateAccess
from release_info import APP_VERSION
from security import (
    AuthorizationContext,
    current_context,
    is_directorate_visible,
    require_fresh_reitoria,
    visible_operating_directorate_codes,
)

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()

MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}


class DirectorateAccessInput(BaseModel):
    code: str
    access: str = ACCESS_READ
    primary: bool = False


class UserAccessInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    global_role: str = ROLE_DIRECTORATE
    active: bool = True
    directorates: list[DirectorateAccessInput] = Field(default_factory=list)


class UserProvisionInput(UserAccessInput):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)


def _iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _normalize_email(value: str | None) -> str:
    email = str(value or "").strip().casefold()
    if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(422, "Informe um e-mail válido.")
    return email


def _identity_admin_error(exc: IdentityAdminError) -> None:
    raise HTTPException(exc.status_code, exc.message) from exc


def _cleanup_rolled_back_identity_rows(db: Session, provider_id: str) -> None:
    """Remove rows left by the auth.users trigger after a rolled-back provision.

    Supabase Auth and the application database commit in separate transactions.
    If Auth successfully creates a user, database/033 may already have created
    ``app_users`` before a later local authorization step fails.  When the new
    Auth identity is deleted during rollback, ``profiles`` cascades from
    ``auth.users`` but ``app_users`` deliberately has no FK to auth.users (local
    test identities also live there).  Clean only the exact SUPABASE identity
    that was created by this request.
    """
    try:
        target = db.get(AppUser, provider_id)
        if target and (
            str(target.auth_provider or "").upper() == "SUPABASE"
            and str(target.auth_provider_id or target.id) == str(provider_id)
        ):
            db.delete(target)
        profile = db.get(Profile, provider_id)
        if profile:
            db.delete(profile)
        db.commit()
    except Exception:
        db.rollback()


def _catalog(db: Session) -> dict[str, Directorate]:
    visible_codes = visible_operating_directorate_codes()
    rows = db.scalars(
        select(Directorate).where(
            Directorate.code.in_(visible_codes),
            Directorate.active.is_(True),
        )
    ).all()
    return {row.code.upper(): row for row in rows}


def _grant_rows(db: Session, user_id: str) -> list[tuple[UserDirectorateAccess, Directorate]]:
    return list(
        db.execute(
            select(UserDirectorateAccess, Directorate)
            .join(Directorate, Directorate.id == UserDirectorateAccess.directorate_id)
            .where(UserDirectorateAccess.user_id == user_id)
            .order_by(UserDirectorateAccess.is_primary.desc(), Directorate.code.asc())
        ).all()
    )


def _grants(db: Session, user_id: str, *, include_hidden: bool = False) -> list[dict]:
    out = []
    for access, directorate in _grant_rows(db, user_id):
        hidden = not is_directorate_visible(directorate.code)
        if hidden and not include_hidden:
            continue
        out.append(
            {
                "code": directorate.code,
                "name": directorate.name,
                "access": access.access_level,
                "primary": bool(access.is_primary),
                "hidden": hidden,
            }
        )
    return out


def _avatar_url(user: AppUser) -> str:
    # Avatar objects use a deterministic private Storage path. The frontend
    # probes this URL and falls back to initials when the object does not exist.
    return f"/api/profile/avatar/{user.id}"


def _user_payload(db: Session, user: AppUser) -> dict:
    active_sessions = active_session_rows(db, user.id)
    last_seen = db.scalar(select(func.max(AuthSession.last_seen_at)).where(AuthSession.user_id == user.id))
    all_grants = _grants(db, user.id, include_hidden=True)
    visible_grants = [row for row in all_grants if not row.get("hidden")]
    hidden_grant_count = len(all_grants) - len(visible_grants)
    return {
        "id": str(user.id),
        "name": user.name or user.email or "Usuário",
        "email": user.email or "",
        "avatar_url": _avatar_url(user),
        "global_role": str(user.global_role or ROLE_DIRECTORATE).upper(),
        "active": bool(user.active),
        "permission_version": int(user.permission_version or 1),
        "directorates": visible_grants,
        "hidden_directorate_count": hidden_grant_count,
        "active_sessions": len({str(row.token_family) for row in active_sessions}),
        "last_seen_at": _iso(last_seen),
        "created_at": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
    }


def _normalize_role(value: str) -> str:
    role = str(value or "").strip().upper()
    if role not in {ROLE_REITORIA, ROLE_DIRECTORATE}:
        raise HTTPException(422, "Tipo de usuário inválido.")
    return role


def _hidden_existing_grants(db: Session, user_id: str) -> list[tuple[Directorate, str, bool]]:
    return [
        (directorate, str(access.access_level or ACCESS_READ).upper(), bool(access.is_primary))
        for access, directorate in _grant_rows(db, user_id)
        if not is_directorate_visible(directorate.code)
    ]


def _normalize_grants(
    db: Session,
    role: str,
    rows: list[DirectorateAccessInput],
    *,
    allow_empty: bool = False,
) -> list[tuple[Directorate, str, bool]]:
    if role == ROLE_REITORIA:
        return []
    catalog = _catalog(db)
    unique: dict[str, tuple[Directorate, str, bool]] = {}
    for row in rows:
        code = str(row.code or "").strip().upper()
        directorate = catalog.get(code)
        if not directorate:
            raise HTTPException(422, f"Diretoria {code or '?'} inválida, inativa ou temporariamente indisponível.")
        access = str(row.access or ACCESS_READ).strip().upper()
        if access not in {ACCESS_READ, ACCESS_EDIT}:
            raise HTTPException(422, f"Nível de acesso inválido para {code}.")
        unique[code] = (directorate, access, bool(row.primary))
    if not unique:
        if allow_empty:
            return []
        raise HTTPException(422, "Usuários de diretoria precisam de pelo menos uma diretoria disponível.")
    normalized = list(unique.values())
    primary_indexes = [idx for idx, (_, _, primary) in enumerate(normalized) if primary]
    if len(primary_indexes) > 1:
        raise HTTPException(422, "Selecione no máximo uma diretoria principal.")
    if not primary_indexes:
        directorate, access, _ = normalized[0]
        normalized[0] = (directorate, access, True)
    return normalized


def _security_snapshot(db: Session, user: AppUser) -> dict:
    return {
        "global_role": str(user.global_role or ROLE_DIRECTORATE).upper(),
        "active": bool(user.active),
        "directorates": [
            {"code": row["code"], "access": row["access"], "primary": row["primary"]}
            for row in _grants(db, user.id, include_hidden=True)
        ],
    }


def _sync_profile(db: Session, user: AppUser, visible_grants: list[tuple[Directorate, str, bool]]) -> None:
    profile = db.get(Profile, str(user.auth_provider_id or user.id)) or db.get(Profile, str(user.id))
    if not profile:
        profile = Profile(id=str(user.id))
        db.add(profile)
    profile.email = user.email
    profile.full_name = user.name
    if str(user.global_role).upper() == ROLE_REITORIA:
        profile.role = "admin"
        profile.directorate_id = None
        return
    primary = next((item for item in visible_grants if item[2]), visible_grants[0] if visible_grants else None)
    if primary:
        profile.directorate_id = primary[0].id
        profile.role = "editor" if primary[1] == ACCESS_EDIT else "viewer"


def _apply_user_update(
    db: Session,
    *,
    target: AppUser,
    payload: UserAccessInput,
    actor: AuthorizationContext,
    email: str | None = None,
    force_session_revoke: bool = False,
) -> tuple[dict, bool, int]:
    role = _normalize_role(payload.global_role)
    hidden_existing = _hidden_existing_grants(db, target.id) if role == ROLE_DIRECTORATE else []
    visible_grants = _normalize_grants(db, role, payload.directorates, allow_empty=bool(hidden_existing))
    if target.id == actor.user_id and (not payload.active or role != ROLE_REITORIA):
        raise HTTPException(409, "A Reitoria não pode bloquear ou remover o próprio acesso global por esta tela.")

    before = _security_snapshot(db, target)
    target.name = str(payload.name).strip()
    target.global_role = role
    target.active = bool(payload.active)
    if email is not None:
        target.email = email

    final_grants = list(visible_grants)
    if role == ROLE_DIRECTORATE and hidden_existing:
        has_visible = bool(visible_grants)
        for directorate, access, primary in hidden_existing:
            final_grants.append((directorate, access, False if has_visible else primary))

    db.query(UserDirectorateAccess).filter(UserDirectorateAccess.user_id == target.id).delete(synchronize_session=False)
    db.flush()
    for directorate, access, primary in final_grants:
        db.add(
            UserDirectorateAccess(
                user_id=target.id,
                directorate_id=directorate.id,
                access_level=access,
                is_primary=primary,
            )
        )
    db.flush()
    _sync_profile(db, target, visible_grants)
    after = _security_snapshot(db, target)
    security_changed = before != after
    revoked = 0
    if security_changed or force_session_revoke:
        target.permission_version = int(target.permission_version or 1) + 1
        revoked = revoke_user_sessions(db, target.id, commit=False)

    event = "PERMISSION_CHANGED" if security_changed else "IDENTITY_CHANGED"
    if before["active"] and not after["active"]:
        event = "USER_DISABLED"
    elif not before["active"] and after["active"]:
        event = "USER_ENABLED"
    log_auth_event(
        db,
        event,
        outcome="SUCCESS",
        actor_user_id=actor.user_id,
        target_user_id=target.id,
        email=target.email,
        details={
            "before": before,
            "after": after,
            "sessions_revoked": revoked,
            "identity_sensitive_change": bool(force_session_revoke),
        },
        commit=False,
    )
    db.commit()
    db.refresh(target)
    return _user_payload(db, target), security_changed or force_session_revoke, revoked


def _validate_avatar(data: bytes, content_type: str | None) -> str:
    if not data:
        raise HTTPException(400, "A foto enviada está vazia.")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "A foto de perfil deve ter no máximo 2 MB.")
    claimed = str(content_type or "").split(";")[0].strip().lower()
    detected = None
    if data.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        detected = "image/webp"
    if detected not in AVATAR_TYPES:
        raise HTTPException(415, "Use uma foto JPEG, PNG ou WEBP válida.")
    if claimed and claimed not in AVATAR_TYPES:
        raise HTTPException(415, "O tipo de arquivo informado não é permitido para foto de perfil.")
    return detected


@router.get("/reitoria", response_class=HTMLResponse)
def reitoria_page(request: Request, _ctx: AuthorizationContext = Depends(require_fresh_reitoria)):
    return templates.TemplateResponse(
        request=request,
        name="reitoria.html",
        context={"app_version": APP_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/admin/users", response_class=HTMLResponse)
def users_page(request: Request, _ctx: AuthorizationContext = Depends(require_fresh_reitoria)):
    # Backward-compatible URL: the old orphaned admin surface now renders the
    # Reitoria workspace instead of a separate page with missing CSS.
    return templates.TemplateResponse(
        request=request,
        name="reitoria.html",
        context={"app_version": APP_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/admin/users")
def list_users(
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    statement = select(AppUser)
    term = str(search or "").strip()
    if term:
        pattern = f"%{term}%"
        statement = statement.where(or_(AppUser.email.ilike(pattern), AppUser.name.ilike(pattern)))
    users = list(db.scalars(statement.order_by(AppUser.active.desc(), AppUser.name.asc(), AppUser.email.asc()).limit(500)).all())
    catalog = _catalog(db)
    visible_codes = visible_operating_directorate_codes()
    return {
        "users": [_user_payload(db, user) for user in users],
        "directorates": [
            {"code": code, "name": catalog[code].name}
            for code in visible_codes
            if code in catalog
        ],
        "actor_user_id": ctx.user_id,
    }


@router.post("/api/admin/users")
def provision_user(
    payload: UserProvisionInput,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    email = _normalize_email(payload.email)
    role = _normalize_role(payload.global_role)
    # Validate the authorization payload before creating or mutating anything
    # in the external identity provider. This keeps Supabase Auth and the local
    # Data UNIVC authorization model transactionally aligned as far as possible.
    _normalize_grants(db, role, payload.directorates, allow_empty=False)
    existing = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email))
    if existing:
        raise HTTPException(409, "Já existe um usuário com este e-mail. Abra o cadastro existente para alterá-lo.")

    profile = db.scalar(select(Profile).where(func.lower(Profile.email) == email))
    created_identity = False
    provider_id = str(profile.id) if profile else ""
    if profile and db.get(AppUser, provider_id):
        raise HTTPException(409, "A identidade deste e-mail já está vinculada ao Data UNIVC. Abra o usuário existente para alterá-lo.")
    try:
        if profile:
            update_identity(provider_id, email=email, password=payload.password, name=payload.name.strip())
        else:
            identity = create_identity(email=email, password=payload.password, name=payload.name.strip())
            provider_id = str(identity["id"])
            created_identity = True
            profile = db.get(Profile, provider_id)
            if profile is None:
                profile = Profile(id=provider_id, email=email, full_name=payload.name.strip(), role="viewer")
                db.add(profile)

        target = db.get(AppUser, provider_id)
        created_app_user = False
        if target:
            # database/033 registers an AFTER INSERT trigger on auth.users that
            # creates profiles + app_users with the same UUID.  A successful
            # Supabase Admin create therefore commonly arrives here with the
            # AppUser already materialized.  Treat that row as the expected
            # synchronization result instead of reporting a false conflict.
            provider_matches = (
                str(target.auth_provider or "SUPABASE").upper() == "SUPABASE"
                and str(target.auth_provider_id or target.id) == provider_id
            )
            target_email = str(target.email or "").strip().casefold()
            if not provider_matches or (target_email and target_email != email):
                raise HTTPException(409, "A identidade já está vinculada a outro usuário do Data UNIVC.")
        else:
            # Compatibility path for databases without the synchronization
            # trigger (for example isolated tests or an older installation).
            target = AppUser(
                id=provider_id,
                auth_provider="SUPABASE",
                auth_provider_id=provider_id,
                email=email,
                name=payload.name.strip(),
                global_role=ROLE_DIRECTORATE,
                active=True,
                permission_version=1,
            )
            db.add(target)
            db.flush()
            created_app_user = True
        result, _, _ = _apply_user_update(db, target=target, payload=payload, actor=ctx, email=email)
        log_auth_event(
            db,
            "USER_PROVISIONED",
            outcome="SUCCESS",
            actor_user_id=ctx.user_id,
            target_user_id=target.id,
            email=target.email,
            details={
                "created_auth_identity": created_identity,
                "created_app_user": created_app_user,
                "trigger_materialized_app_user": bool(created_identity and not created_app_user),
            },
            commit=True,
        )
        return result
    except IdentityAdminError as exc:
        db.rollback()
        _identity_admin_error(exc)
    except Exception:
        db.rollback()
        if created_identity and provider_id:
            identity_deleted = False
            try:
                delete_identity(provider_id)
                identity_deleted = True
            except IdentityAdminError:
                pass
            if identity_deleted:
                _cleanup_rolled_back_identity_rows(db, provider_id)
        raise


@router.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserAccessInput,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    target = db.get(AppUser, user_id)
    if not target:
        raise HTTPException(404, "Usuário não encontrado.")
    email = _normalize_email(payload.email if payload.email is not None else target.email)
    role = _normalize_role(payload.global_role)
    hidden_existing = _hidden_existing_grants(db, target.id) if role == ROLE_DIRECTORATE else []
    _normalize_grants(db, role, payload.directorates, allow_empty=bool(hidden_existing))
    if target.id == ctx.user_id and (not payload.active or role != ROLE_REITORIA):
        raise HTTPException(409, "A Reitoria não pode bloquear ou remover o próprio acesso global por esta tela.")
    duplicate = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email, AppUser.id != target.id))
    if duplicate:
        raise HTTPException(409, "Já existe outro usuário com este e-mail.")

    email_changed = email != str(target.email or "").strip().casefold()
    password_changed = bool(payload.password)
    name_changed = payload.name.strip() != str(target.name or "").strip()
    if (email_changed or password_changed or name_changed) and str(target.auth_provider or "SUPABASE").upper() == "SUPABASE":
        try:
            update_identity(
                str(target.auth_provider_id or target.id),
                email=email if email_changed else None,
                password=payload.password if password_changed else None,
                name=payload.name.strip() if name_changed else None,
            )
        except IdentityAdminError as exc:
            _identity_admin_error(exc)
    elif (email_changed or password_changed) and str(target.auth_provider or "").upper() != "SUPABASE":
        raise HTTPException(409, "E-mail e senha de identidades locais de teste são administrados pelo seed de homologação.")

    user, changed, revoked = _apply_user_update(
        db,
        target=target,
        payload=payload,
        actor=ctx,
        email=email,
        force_session_revoke=email_changed or password_changed,
    )
    return {"user": user, "security_changed": changed, "sessions_revoked": revoked}


@router.post("/api/admin/users/{user_id}/avatar")
async def set_user_avatar(
    user_id: str,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    target = db.get(AppUser, user_id)
    if not target:
        raise HTTPException(404, "Usuário não encontrado.")
    data = await avatar.read(MAX_AVATAR_BYTES + 1)
    await avatar.close()
    content_type = _validate_avatar(data, avatar.content_type)
    try:
        path = upload_avatar(user_id=user_id, data=data, content_type=content_type)
    except IdentityAdminError as exc:
        _identity_admin_error(exc)
    log_auth_event(
        db,
        "PROFILE_AVATAR_CHANGED",
        outcome="SUCCESS",
        actor_user_id=ctx.user_id,
        target_user_id=target.id,
        email=target.email,
        details={"content_type": content_type, "bytes": len(data)},
        commit=False,
    )
    db.commit()
    return {"ok": True, "avatar_url": f"{_avatar_url(target)}?v={int(datetime.now(timezone.utc).timestamp())}"}


@router.delete("/api/admin/users/{user_id}/avatar")
def remove_user_avatar(
    user_id: str,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    target = db.get(AppUser, user_id)
    if not target:
        raise HTTPException(404, "Usuário não encontrado.")
    path = f"users/{user_id}/avatar"
    try:
        delete_avatar(path)
    except IdentityAdminError as exc:
        _identity_admin_error(exc)
    log_auth_event(
        db,
        "PROFILE_AVATAR_CHANGED",
        outcome="SUCCESS",
        actor_user_id=ctx.user_id,
        target_user_id=target.id,
        email=target.email,
        details={"removed": True},
        commit=False,
    )
    db.commit()
    return {"ok": True, "avatar_url": None}


@router.get("/api/profile/avatar/{user_id}")
def user_avatar(
    user_id: str,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(current_context),
):
    if str(user_id) != str(ctx.user_id) and not ctx.global_access:
        raise HTTPException(403, "Você não pode consultar a foto de perfil de outro usuário.")
    target = db.get(AppUser, user_id)
    if not target:
        raise HTTPException(404, "Usuário não encontrado.")
    try:
        content, content_type = download_avatar(f"users/{user_id}/avatar")
    except IdentityAdminError as exc:
        _identity_admin_error(exc)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/api/admin/users/{user_id}/sessions")
def list_user_sessions(
    user_id: str,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    if not db.get(AppUser, user_id):
        raise HTTPException(404, "Usuário não encontrado.")
    rows = active_session_rows(db, user_id)
    return {
        "sessions": [
            {
                "id": str(row.id),
                "family": str(row.token_family),
                "created_at": _iso(row.family_created_at),
                "last_seen_at": _iso(row.last_seen_at),
                "expires_at": _iso(row.expires_at),
                "current": str(row.id) == str(ctx.session_id or ""),
            }
            for row in rows
        ]
    }


@router.post("/api/admin/users/{user_id}/sessions/revoke")
def revoke_all_user_sessions(
    user_id: str,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    target = db.get(AppUser, user_id)
    if not target:
        raise HTTPException(404, "Usuário não encontrado.")
    if user_id == ctx.user_id:
        raise HTTPException(409, "Use Encerrar sessão para finalizar sua própria sessão; a revogação administrativa em massa é destinada a outros usuários.")
    count = revoke_user_sessions(db, user_id, commit=False)
    log_auth_event(
        db,
        "SESSION_REVOKED",
        outcome="SUCCESS",
        actor_user_id=ctx.user_id,
        target_user_id=user_id,
        email=target.email,
        details={"scope": "all", "rows_revoked": count},
        commit=False,
    )
    db.commit()
    return {"ok": True, "sessions_revoked": count}


@router.post("/api/admin/sessions/{session_id}/revoke")
def revoke_one_session(
    session_id: str,
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    row = db.get(AuthSession, session_id)
    if not row:
        raise HTTPException(404, "Sessão não encontrada.")
    if str(row.id) == str(ctx.session_id or ""):
        raise HTTPException(409, "A sessão administrativa atual não pode ser revogada por esta ação.")
    count = revoke_session_by_id(db, session_id)
    log_auth_event(
        db,
        "SESSION_REVOKED",
        outcome="SUCCESS",
        actor_user_id=ctx.user_id,
        target_user_id=row.user_id,
        details={"scope": "family", "session_id": str(row.id), "rows_revoked": count},
    )
    return {"ok": True, "sessions_revoked": count}


@router.get("/api/admin/audit")
def list_auth_audit(
    event: str | None = Query(None),
    user_id: str | None = Query(None),
    email: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    rows = audit_query(db, event_type=event, user_id=user_id, email=email, limit=limit)
    ids = {value for row in rows for value in (row.actor_user_id, row.target_user_id) if value}
    users = {user.id: user for user in db.scalars(select(AppUser).where(AppUser.id.in_(ids))).all()} if ids else {}
    return {
        "events": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "outcome": row.outcome,
                "actor_user_id": row.actor_user_id,
                "actor_name": users.get(row.actor_user_id).name if row.actor_user_id in users else None,
                "target_user_id": row.target_user_id,
                "target_name": users.get(row.target_user_id).name if row.target_user_id in users else None,
                "email": row.email,
                "directorate_code": row.directorate_code,
                "details": row.details or {},
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ]
    }
