from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.access import (
    ACCESS_EDIT,
    ACCESS_READ,
    ROLE_DIRECTORATE,
    ROLE_REITORIA,
    DirectorateGrant,
    load_identity_access,
    primary_grant,
)
from auth.audit import (
    LOGIN_RATE_LIMIT_ENABLED,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    log_auth_event,
    login_rate_limit_exceeded,
)
from auth.identity_provider import IdentityProviderError, authenticate_password
from auth.sessions import (
    REFRESH_TOKEN_TTL_SECONDS,
    RefreshSessionExpired,
    RefreshSessionInvalid,
    RefreshSessionReused,
    create_refresh_session,
    hash_refresh_token,
    request_fingerprints,
    revoke_family,
    revoke_refresh_session,
    rotate_refresh_session,
)
from auth.tokens import ACCESS_TOKEN_TTL_SECONDS, AccessTokenError, AccessTokenExpired, _keyring, decode_access_token, issue_access_token
from database import get_db
from models import AppUser, AuthSession, Directorate, Profile


load_dotenv()

AUTH_DISABLED = os.getenv("AUTH_DISABLED", "false").lower() == "true"
DEFAULT_DIRECTORATE_CODE = os.getenv("DEFAULT_DIRECTORATE_CODE", "DTNH").upper()
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

ACCESS_COOKIE_NAME = "__Host-dataunivc_access" if COOKIE_SECURE else "dataunivc_access"
REFRESH_COOKIE_NAME = "__Host-dataunivc_refresh" if COOKIE_SECURE else "dataunivc_refresh"
CSRF_COOKIE_NAME = "__Host-dataunivc_csrf" if COOKIE_SECURE else "dataunivc_csrf"
V2_ACCESS_COOKIE_NAMES = ("__Host-dataunivc_access", "dataunivc_access")
V2_REFRESH_COOKIE_NAMES = ("__Host-dataunivc_refresh", "dataunivc_refresh")
CSRF_COOKIE_NAMES = ("__Host-dataunivc_csrf", "dataunivc_csrf")
RETIRED_AUTH_COOKIE_NAMES = ("univc_access_token", "univc_refresh_token")

# Internal compatibility labels for repositories that still render a legacy
# role string. They never authorize a request.
WRITE_ROLES = {"admin", "director", "editor"}
OPERATING_DIRECTORATE_CODES: tuple[str, ...] = ("DTNH", "DCS", "DADM", "DPE", "DM")


def hidden_directorate_codes() -> tuple[str, ...]:
    raw = os.getenv("HIDDEN_DIRECTORATE_CODES", "DPE")
    hidden = []
    for item in str(raw or "").split(","):
        code = item.strip().upper()
        if code and code in OPERATING_DIRECTORATE_CODES and code not in hidden:
            hidden.append(code)
    return tuple(hidden)


def is_directorate_visible(code: str) -> bool:
    target = str(code or "").strip().upper()
    return target in OPERATING_DIRECTORATE_CODES and target not in set(hidden_directorate_codes())


def visible_operating_directorate_codes() -> tuple[str, ...]:
    hidden = set(hidden_directorate_codes())
    return tuple(code for code in OPERATING_DIRECTORATE_CODES if code not in hidden)


def ensure_directorate_visible(code: str) -> str:
    target = str(code or "").strip().upper()
    if target not in OPERATING_DIRECTORATE_CODES or not is_directorate_visible(target):
        raise HTTPException(404, "Diretoria não encontrada ou temporariamente indisponível.")
    return target


def ensure_v2_configured() -> None:
    try:
        _keyring()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc


def _new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _set_csrf_cookie(response: Response, token: str | None = None) -> str:
    value = token or _new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE_NAME,
        value,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        path="/",
    )
    return value


def csrf_request_valid(request: Request) -> bool:
    cookie = _read_cookie(request, CSRF_COOKIE_NAMES)
    header = request.headers.get("X-CSRF-Token")
    return bool(cookie and header and hmac.compare_digest(cookie, header))

def request_has_v2_session(request: Request) -> bool:
    return bool(_read_cookie(request, V2_ACCESS_COOKIE_NAMES) or _read_cookie(request, V2_REFRESH_COOKIE_NAMES))


def ensure_csrf_cookie(request: Request, response: Response) -> None:
    if request_has_v2_session(request) and not _read_cookie(request, CSRF_COOKIE_NAMES):
        _set_csrf_cookie(response)


@dataclass
class AuthorizationContext:
    """Authenticated Identity & Access V2 claims used by FastAPI."""

    user_id: str
    email: str
    full_name: str
    role: str
    directorate_id: int
    directorate_code: str
    directorate_name: str
    global_role: str = ROLE_DIRECTORATE
    permission_version: int = 1
    directorate_access: tuple[DirectorateGrant, ...] = ()
    active: bool = True
    session_id: str | None = None
    auth_provider_id: str | None = None

    @property
    def global_access(self) -> bool:
        return self.global_role == ROLE_REITORIA

    def access_for(self, code: str) -> str | None:
        target = str(code or "").strip().upper()
        for grant in self.directorate_access:
            if grant.code.upper() == target:
                return grant.access
        return None

    def can_read(self, code: str) -> bool:
        return self.global_access or self.access_for(code) in {ACCESS_READ, ACCESS_EDIT}

    def can_edit(self, code: str) -> bool:
        return self.global_access or self.access_for(code) == ACCESS_EDIT


UserContext = AuthorizationContext


@dataclass
class DirectorateScope:
    """One directorate already authorized for the current request."""

    user: AuthorizationContext
    directorate_id: int
    directorate_code: str
    directorate_name: str
    can_write: bool
    is_home: bool


def _read_cookie(request: Request, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = request.cookies.get(name)
        if value:
            return value
    return None


def _request_hashes(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return request_fingerprints(user_agent, ip_address)


def _home_grant_for_identity(db: Session, identity) -> DirectorateGrant:
    visible = set(visible_operating_directorate_codes())
    grants = [grant for grant in identity.directorates if grant.code in visible]
    grant = next((item for item in grants if item.is_primary), grants[0] if grants else None)
    if grant:
        return grant
    if identity.global_role != ROLE_REITORIA:
        raise HTTPException(403, "Seu usuário não possui nenhuma diretoria disponível no momento.")

    target = db.scalar(
        select(Directorate).where(
            Directorate.code == DEFAULT_DIRECTORATE_CODE,
            Directorate.code.in_(visible_operating_directorate_codes()),
            Directorate.active.is_(True),
        )
    )
    if not target:
        target = db.scalar(
            select(Directorate)
            .where(Directorate.code.in_(visible_operating_directorate_codes()), Directorate.active.is_(True))
            .order_by(Directorate.id)
        )
    if not target:
        raise HTTPException(500, "Nenhuma diretoria operacional visível foi configurada.")
    return DirectorateGrant(target.id, target.code, target.name, ACCESS_EDIT, True)


def _context_from_identity(db: Session, subject: AppUser | Profile | str, email: str = "") -> UserContext:
    try:
        identity = load_identity_access(db, subject)
    except LookupError as exc:
        raise HTTPException(403, "Seu usuário ainda não foi provisionado no Identity & Access V2.") from exc
    if not identity.active:
        raise HTTPException(403, "Seu usuário está bloqueado no Data UNIVC.")

    grant = _home_grant_for_identity(db, identity)
    compatibility_role = "admin" if identity.global_role == ROLE_REITORIA else ("editor" if grant.access == ACCESS_EDIT else "viewer")
    return UserContext(
        user_id=identity.user_id,
        email=email or identity.email or "",
        full_name=identity.name or email or identity.email or "Usuário",
        role=compatibility_role,
        directorate_id=grant.directorate_id,
        directorate_code=grant.code,
        directorate_name=grant.name,
        global_role=identity.global_role,
        permission_version=identity.permission_version,
        directorate_access=identity.directorates,
        active=identity.active,
        auth_provider_id=identity.auth_provider_id,
    )


def _context_from_profile(db: Session, user_id: str, email: str = "") -> UserContext:
    """Compatibility entrypoint for older internal callers; no profile fallback exists."""
    return _context_from_identity(db, str(user_id), email)


def _access_claims(ctx: UserContext, session_id: str) -> dict:
    return {
        "sub": ctx.user_id,
        "sid": session_id,
        "email": ctx.email,
        "name": ctx.full_name,
        "role": ctx.role,
        "global_role": ctx.global_role,
        "permission_version": ctx.permission_version,
        "directorates": [
            {
                "id": grant.directorate_id,
                "code": grant.code,
                "name": grant.name,
                "access": grant.access,
                "primary": grant.is_primary,
            }
            for grant in ctx.directorate_access
        ],
        "access": ACCESS_EDIT if ctx.global_access else (ctx.access_for(ctx.directorate_code) or ACCESS_READ),
        "directorate_id": ctx.directorate_id,
        "directorate_code": ctx.directorate_code,
        "directorate_name": ctx.directorate_name,
        "auth_version": 2,
        "access_model_version": 2,
    }


def _context_from_claims(claims: dict) -> UserContext:
    try:
        if int(claims.get("auth_version") or 0) != 2 or int(claims.get("access_model_version") or 0) != 2:
            raise ValueError("modelo de token aposentado")
        role = str(claims["role"])
        global_role = str(claims["global_role"]).upper()
        if global_role not in {ROLE_DIRECTORATE, ROLE_REITORIA}:
            raise ValueError("role global inválida")
        home_id = int(claims["directorate_id"])
        home_code = str(claims["directorate_code"]).upper()
        home_name = str(claims.get("directorate_name") or claims["directorate_code"])
        grants: list[DirectorateGrant] = []
        raw_directorates = claims.get("directorates")
        if isinstance(raw_directorates, list):
            for item in raw_directorates:
                if not isinstance(item, dict):
                    continue
                level = str(item.get("access") or ACCESS_READ).upper()
                if level not in {ACCESS_READ, ACCESS_EDIT}:
                    continue
                grants.append(
                    DirectorateGrant(
                        directorate_id=int(item["id"]),
                        code=str(item["code"]).upper(),
                        name=str(item.get("name") or item["code"]),
                        access=level,
                        is_primary=bool(item.get("primary", False)),
                    )
                )
        if global_role == ROLE_DIRECTORATE and not grants:
            raise ValueError("usuário de diretoria sem grants")
        return UserContext(
            user_id=str(claims["sub"]),
            email=str(claims.get("email") or ""),
            full_name=str(claims.get("name") or claims.get("email") or "Usuário"),
            role=role,
            directorate_id=home_id,
            directorate_code=home_code,
            directorate_name=home_name,
            global_role=global_role,
            permission_version=max(1, int(claims["permission_version"])),
            directorate_access=tuple(grants),
            active=True,
            session_id=str(claims["sid"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Token de acesso incompleto, antigo ou inválido.") from exc


def _set_v2_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=ACCESS_TOKEN_TTL_SECONDS,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        path="/",
    )
    _set_csrf_cookie(response)


def _delete_cookie(response: Response, name: str, *, httponly: bool = True) -> None:
    response.delete_cookie(
        name,
        path="/",
        secure=name.startswith("__Host-") or COOKIE_SECURE,
        httponly=httponly,
        samesite="lax",
    )


def _delete_all_auth_cookies(response: Response) -> None:
    for name in {*V2_ACCESS_COOKIE_NAMES, *V2_REFRESH_COOKIE_NAMES, *RETIRED_AUTH_COOKIE_NAMES}:
        _delete_cookie(response, name)
    for name in CSRF_COOKIE_NAMES:
        _delete_cookie(response, name, httponly=False)


async def current_context(request: Request, db: Session = Depends(get_db)) -> UserContext:
    if AUTH_DISABLED:
        directorate = db.scalar(select(Directorate).where(Directorate.code == DEFAULT_DIRECTORATE_CODE))
        if not directorate:
            raise HTTPException(500, f"Diretoria {DEFAULT_DIRECTORATE_CODE} não foi criada no banco.")
        ctx = UserContext(
            "dev-user",
            f"dev.{directorate.code.lower()}@univc.local",
            f"Desenvolvimento {directorate.code}",
            "admin",
            directorate.id,
            directorate.code,
            directorate.name,
            global_role=ROLE_DIRECTORATE,
            permission_version=1,
            directorate_access=(DirectorateGrant(directorate.id, directorate.code, directorate.name, ACCESS_EDIT, True),),
            session_id="dev-session",
        )
        request.state.auth_context = ctx
        return ctx

    v2_token = _read_cookie(request, V2_ACCESS_COOKIE_NAMES)
    if not v2_token:
        raise HTTPException(401, "Faça login para continuar.")
    ensure_v2_configured()
    try:
        claims = decode_access_token(v2_token)
    except AccessTokenExpired as exc:
        raise HTTPException(401, str(exc)) from exc
    except (AccessTokenError, RuntimeError) as exc:
        raise HTTPException(401, "Sessão inválida. Renove ou faça login novamente.") from exc
    ctx = _context_from_claims(claims)
    request.state.auth_context = ctx
    return ctx


def require_write(ctx: AuthorizationContext = Depends(current_context)) -> AuthorizationContext:
    """Require EDIT for the user's compatibility/home context.

    This endpoint-level helper remains for legacy user-owned operations such as
    profile configuration. Directorate resources should use `current_scope`,
    `require_scope_write`, or the fixed-directorate dependency factories below.
    """
    if not ctx.can_edit(ctx.directorate_code):
        raise HTTPException(403, "Seu perfil possui acesso somente para leitura.")
    return ctx


def require_reitoria(ctx: AuthorizationContext = Depends(current_context)) -> AuthorizationContext:
    if not ctx.global_access:
        raise HTTPException(403, "Este recurso é exclusivo da Reitoria.")
    return ctx


def require_fresh_reitoria(
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(current_context),
) -> AuthorizationContext:
    """Revalidate critical admin privileges against the database immediately.

    Normal directorate APIs remain stateless for the short access-token lifetime.
    Administration is intentionally stricter: role/status/version and the exact
    session row must still be current before any privileged operation.
    """
    if not ctx.global_access:
        raise HTTPException(403, "Este recurso é exclusivo da Reitoria.")
    app_user = db.get(AppUser, ctx.user_id)
    if not app_user or not app_user.active:
        raise HTTPException(403, "Seu usuário está bloqueado no Data UNIVC.")
    if str(app_user.global_role or "").upper() != ROLE_REITORIA:
        raise HTTPException(403, "Este recurso é exclusivo da Reitoria.")
    if int(app_user.permission_version or 1) != int(ctx.permission_version):
        raise HTTPException(401, "Suas permissões foram alteradas. Renove a sessão para continuar.")
    if ctx.session_id:
        session = db.get(AuthSession, ctx.session_id)
        if not session or session.user_id != ctx.user_id or session.revoked_at is not None:
            raise HTTPException(401, "Esta sessão administrativa foi revogada.")
    return ctx


def _directorate_by_code(db: Session, code: str) -> Directorate:
    target_code = ensure_directorate_visible(code)
    target = db.scalar(
        select(Directorate).where(Directorate.code == target_code, Directorate.active.is_(True))
    )
    if not target:
        raise HTTPException(404, "Diretoria não encontrada.")
    return target


def resolve_directorate_scope(
    db: Session,
    ctx: AuthorizationContext,
    code: str,
    *,
    require_edit: bool = False,
) -> DirectorateScope:
    """Central authorization decision for every directorate-scoped operation."""
    target = _directorate_by_code(db, code)

    if ctx.global_access:
        return DirectorateScope(
            user=ctx,
            directorate_id=target.id,
            directorate_code=target.code,
            directorate_name=target.name,
            can_write=True,
            is_home=target.code == ctx.directorate_code,
        )

    level = ctx.access_for(target.code)
    if level not in {ACCESS_READ, ACCESS_EDIT}:
        raise HTTPException(403, "Você não possui acesso a esta diretoria.")
    can_write = level == ACCESS_EDIT
    if require_edit and not can_write:
        raise HTTPException(403, "Você possui acesso somente de leitura a esta diretoria.")

    return DirectorateScope(
        user=ctx,
        directorate_id=target.id,
        directorate_code=target.code,
        directorate_name=target.name,
        can_write=can_write,
        is_home=target.code == ctx.directorate_code,
    )


def accessible_directorates(db: Session, ctx: AuthorizationContext) -> list[dict]:
    """Return only directorates currently published and authorized.

    Grants for hidden directorates remain stored in the database but are omitted
    from navigation and cannot be resolved by scoped APIs while hidden.
    """
    visible_codes = visible_operating_directorate_codes()
    if ctx.global_access:
        rows = db.scalars(
            select(Directorate)
            .where(
                Directorate.code.in_(visible_codes),
                Directorate.active.is_(True),
            )
            .order_by(Directorate.code)
        ).all()
        by_code = {row.code: row for row in rows}
        ordered = [code for code in visible_codes if code in by_code]
        principal_code = DEFAULT_DIRECTORATE_CODE if DEFAULT_DIRECTORATE_CODE in by_code else (ordered[0] if ordered else None)
        return [
            {
                "codigo": code,
                "nome": by_code[code].name,
                "principal": code == principal_code,
                "pode_editar": True,
                "nivel_acesso": ACCESS_EDIT,
            }
            for code in ordered
        ]

    out: list[dict] = []
    visible = set(visible_codes)
    for grant in ctx.directorate_access:
        if grant.code not in visible:
            continue
        row = db.get(Directorate, grant.directorate_id)
        if not row or not row.active or row.code != grant.code:
            continue
        out.append(
            {
                "codigo": row.code,
                "nome": row.name,
                "principal": bool(grant.is_primary or row.code == ctx.directorate_code),
                "pode_editar": grant.access == ACCESS_EDIT,
                "nivel_acesso": grant.access,
            }
        )
    return out


def current_scope(
    diretoria: str | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(current_context),
) -> DirectorateScope:
    target_code = str(diretoria or ctx.directorate_code).strip().upper()
    return resolve_directorate_scope(db, ctx, target_code)


def require_scope_write(scope: DirectorateScope = Depends(current_scope)) -> DirectorateScope:
    if not scope.can_write:
        raise HTTPException(403, "Você possui acesso somente de leitura a esta diretoria.")
    return scope


def require_directorate_access(code: str):
    """FastAPI dependency factory for a router bound to one directorate."""
    expected = str(code or "").strip().upper()

    def dependency(
        db: Session = Depends(get_db),
        ctx: AuthorizationContext = Depends(current_context),
    ) -> DirectorateScope:
        return resolve_directorate_scope(db, ctx, expected)

    dependency.__name__ = f"require_{expected.lower()}_access"
    return dependency


def require_directorate_edit(code: str):
    """FastAPI dependency factory requiring EDIT in one fixed directorate."""
    expected = str(code or "").strip().upper()

    def dependency(
        db: Session = Depends(get_db),
        ctx: AuthorizationContext = Depends(current_context),
    ) -> DirectorateScope:
        return resolve_directorate_scope(db, ctx, expected, require_edit=True)

    dependency.__name__ = f"require_{expected.lower()}_edit"
    return dependency


async def login_with_password(
    email: str,
    password: str,
    response: Response,
    db: Session,
    request: Request,
):
    if AUTH_DISABLED:
        return {"ok": True, "email": f"dev.{DEFAULT_DIRECTORATE_CODE.lower()}@univc.local", "session_version": 2}
    ensure_v2_configured()
    normalized_email = str(email or "").strip().casefold()
    user_agent_hash, ip_hash = _request_hashes(request)

    if LOGIN_RATE_LIMIT_ENABLED and login_rate_limit_exceeded(db, email=normalized_email, ip_hash=ip_hash):
        log_auth_event(
            db,
            "LOGIN_RATE_LIMITED",
            outcome="DENIED",
            email=normalized_email,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            details={"window_seconds": LOGIN_RATE_LIMIT_WINDOW_SECONDS},
        )
        raise HTTPException(
            429,
            "Muitas tentativas de login. Aguarde alguns minutos antes de tentar novamente.",
            headers={"Retry-After": str(LOGIN_RATE_LIMIT_WINDOW_SECONDS)},
        )

    try:
        payload = await authenticate_password(normalized_email, password)
    except IdentityProviderError as exc:
        log_auth_event(
            db,
            "LOGIN_FAILED" if exc.status_code == 401 else "LOGIN_ERROR",
            outcome="FAILURE",
            email=normalized_email,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            details={"provider_status": exc.status_code},
        )
        raise HTTPException(exc.status_code, exc.message) from exc

    auth_user = payload.get("user") or {}
    provider_id = str(auth_user.get("id") or "")
    try:
        ctx = _context_from_identity(db, provider_id, auth_user.get("email") or normalized_email)
    except HTTPException as exc:
        log_auth_event(
            db,
            "LOGIN_DENIED",
            outcome="DENIED",
            email=normalized_email,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            details={"reason": str(exc.detail)},
        )
        raise

    # Session fixation defense: a successful explicit login always replaces any
    # refresh credential already present in the browser.
    previous_refresh = _read_cookie(request, V2_REFRESH_COOKIE_NAMES)
    if previous_refresh:
        revoke_refresh_session(db, previous_refresh)

    issue = create_refresh_session(
        db,
        user_id=ctx.user_id,
        user_agent_hash=user_agent_hash,
        ip_hash=ip_hash,
    )
    access_token, _ = issue_access_token(_access_claims(ctx, issue.session.id))
    _set_v2_cookies(response, access_token, issue.raw_token)
    for retired in RETIRED_AUTH_COOKIE_NAMES:
        _delete_cookie(response, retired)
    log_auth_event(
        db,
        "LOGIN_SUCCESS",
        outcome="SUCCESS",
        actor_user_id=ctx.user_id,
        email=ctx.email,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        details={"session_id": issue.session.id},
    )
    return {"ok": True, "email": ctx.email, "session_version": 2}


async def refresh_session(request: Request, response: Response, db: Session):
    if AUTH_DISABLED:
        return {"ok": True, "session_version": 2}
    ensure_v2_configured()
    user_agent_hash, ip_hash = _request_hashes(request)
    refresh = _read_cookie(request, V2_REFRESH_COOKIE_NAMES)
    if not refresh:
        # Supabase v0.8.x refresh cookies are intentionally no longer accepted.
        _delete_all_auth_cookies(response)
        raise HTTPException(401, "Não há sessão V2 para renovar. Faça login novamente.")

    try:
        issue = rotate_refresh_session(
            db,
            refresh,
            user_agent_hash=user_agent_hash,
            ip_hash=ip_hash,
        )
    except RefreshSessionReused as exc:
        log_auth_event(
            db,
            "REFRESH_REUSE_DETECTED",
            outcome="DENIED",
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
        )
        _delete_all_auth_cookies(response)
        raise HTTPException(401, "Sessão recusada: refresh token já utilizado ou revogado.") from exc
    except RefreshSessionExpired as exc:
        log_auth_event(
            db,
            "REFRESH_EXPIRED",
            outcome="DENIED",
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
        )
        _delete_all_auth_cookies(response)
        raise HTTPException(401, str(exc)) from exc
    except RefreshSessionInvalid as exc:
        log_auth_event(
            db,
            "REFRESH_INVALID",
            outcome="DENIED",
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
        )
        _delete_all_auth_cookies(response)
        raise HTTPException(401, "Não foi possível renovar a sessão.") from exc

    try:
        ctx = _context_from_identity(db, issue.session.user_id)
    except HTTPException:
        revoke_family(db, issue.session.token_family)
        raise
    access_token, _ = issue_access_token(_access_claims(ctx, issue.session.id))
    _set_v2_cookies(response, access_token, issue.raw_token)
    log_auth_event(
        db,
        "REFRESH_SUCCESS",
        outcome="SUCCESS",
        actor_user_id=ctx.user_id,
        email=ctx.email,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        details={"session_id": issue.session.id},
    )
    return {"ok": True, "session_version": 2}


def logout_session(request: Request, response: Response, db: Session):
    actor_user_id = None
    if not AUTH_DISABLED:
        refresh = _read_cookie(request, V2_REFRESH_COOKIE_NAMES)
        if refresh:
            row = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == hash_refresh_token(refresh)))
            actor_user_id = row.user_id if row else None
            revoke_refresh_session(db, refresh)
        user_agent_hash, ip_hash = _request_hashes(request)
        log_auth_event(
            db,
            "LOGOUT",
            outcome="SUCCESS",
            actor_user_id=actor_user_id,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
        )
    _delete_all_auth_cookies(response)
    return {"ok": True}

