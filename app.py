from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from academic_analytics import build_academic_dashboard
from dpe_analytics import build_dpe_dashboard
from database import Base, SessionLocal, engine, get_db
from excel_service import export_academic_interactive_excel, export_formatted_excel
from excel_errors import ExcelExportLimitError
from models import Directorate, IndicatorDefinition, IndicatorSchedule
from observability import configure_logging, get_request_id, reset_request_id, set_request_id
from repository import DatabaseRepository, EDUCACAO_FISICA_IDENTITY_POLICY
from schedule_service import schedule_status
from academic_catalog import DCS_COURSES, DTNH_COURSES
from sei_academic import SEIBot, baixar_cursos_sei
from schemas import ACADEMIC_DIRECTORATES, ACADEMIC_UI_DATASETS, DATASETS, IMPLEMENTED_KPIS, KPI_META, RepositoryError, ValidationError
from upload_utils import save_validated_excel_upload
from release_info import APP_VERSION, SCHEMA_VERSION
from schema_version import get_schema_status, schema_version_required
from admin_router import router as admin_router
from management_router import router as management_router
from dadm_router import router as dadm_router
from dadm_tallos_router import router as dadm_tallos_router
from dadm_v2_router import router as dadm_v2_router
from dpe_router import router as dpe_router
from dm_router import router as dm_router
from survey_router import router as survey_router
from security import (
    AUTH_DISABLED,
    DirectorateScope,
    UserContext,
    accessible_directorates,
    csrf_request_valid,
    current_context,
    current_scope,
    ensure_csrf_cookie,
    login_with_password,
    logout_session,
    refresh_session,
    request_has_v2_session,
    require_scope_write,
    require_write,
    visible_operating_directorate_codes,
)
from auth.audit import log_auth_event
from auth.sessions import request_fingerprints
from auth.data_scopes import dadm_scope_payload

ROOT = Path(__file__).resolve().parent

def _source_fingerprint() -> str:
    """Fingerprint every runtime source/asset instead of a hand-maintained file list.

    A fixed list previously omitted modules such as dpe_finance_repository.py, so
    meaningful backend changes could keep the same build identifier. The runtime
    surface is small enough to hash deterministically at startup (~a few MB).
    """
    digest = hashlib.sha256()
    paths = [path for path in ROOT.glob("*.py") if path.is_file()]
    for directory in ("assets", "auth", "config", "database", "static", "templates"):
        root = ROOT / directory
        if root.exists():
            paths.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix()):
        rel = path.relative_to(ROOT).as_posix()
        if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3"}:
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]

def _assert_education_fisica_release_invariants() -> None:
    repository_source = (ROOT / "repository.py").read_text(encoding="utf-8")
    forbidden = (
        "contradizem a habilitação de Educação Física",
        "expected_" + "class_prefix",
    )
    found = [token for token in forbidden if token in repository_source]
    if found:
        raise RuntimeError(
            "Build inconsistente: a validação legada de Educação Física ainda está presente: "
            + ", ".join(found)
        )

_assert_education_fisica_release_invariants()
BUILD_FINGERPRINT = _source_fingerprint()
configure_logging()
LOGGER = logging.getLogger("univc.app")
if os.getenv("AUTO_CREATE_DB", "false").lower() == "true":
    Base.metadata.create_all(bind=engine)

ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() == "true"
app = FastAPI(
    title="UNIVC Data Driven Cloud",
    version=APP_VERSION,
    docs_url="/api/docs" if ENABLE_API_DOCS else None,
    redoc_url=None,
)
EXCEL_EXPORT_CONCURRENCY = max(1, int(os.getenv("EXCEL_EXPORT_CONCURRENCY", "1")))
EXCEL_EXPORT_WAIT_SECONDS = max(1, int(os.getenv("EXCEL_EXPORT_WAIT_SECONDS", "10")))
_EXCEL_EXPORT_SLOTS = threading.BoundedSemaphore(EXCEL_EXPORT_CONCURRENCY)


MAX_DASHBOARD_WINDOW = max(1, int(os.getenv("MAX_DASHBOARD_WINDOW", "12000")))


def _parse_window_query(value: str | None, *, preserve_all: bool = False) -> int | str | None:
    """Parse a dashboard/export window without silently ignoring invalid input."""
    text_value = str(value or "").strip()
    if not text_value:
        return None
    if text_value.casefold() in {"all", "todo historico", "todo histórico"}:
        return "Todo histórico" if preserve_all else None
    if not text_value.isdigit():
        raise HTTPException(422, "A janela deve ser um número inteiro positivo ou 'all'.")
    parsed = int(text_value)
    if not 1 <= parsed <= MAX_DASHBOARD_WINDOW:
        raise HTTPException(
            422,
            f"A janela deve estar entre 1 e {MAX_DASHBOARD_WINDOW} períodos, ou usar 'all'.",
        )
    return parsed
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")
app.include_router(admin_router)
app.include_router(management_router)
app.include_router(dadm_router)
app.include_router(dadm_tallos_router)
app.include_router(dadm_v2_router)
app.include_router(dpe_router)
app.include_router(dm_router)
app.include_router(survey_router)


def api_error(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValidationError):
        return JSONResponse(status_code=422, content={"erro": str(exc), "campos": exc.field_errors})
    if isinstance(exc, PermissionError):
        return JSONResponse(status_code=403, content={"erro": str(exc)})
    if isinstance(exc, LookupError):
        return JSONResponse(status_code=404, content={"erro": str(exc)})
    if isinstance(exc, RepositoryError):
        return JSONResponse(status_code=400, content={"erro": str(exc)})
    if isinstance(exc, ExcelExportLimitError):
        return JSONResponse(status_code=422, content={"erro": str(exc), "exportacao_parcial": False})
    request_id = get_request_id()
    if not request_id or request_id == "-":
        request_id = uuid.uuid4().hex
    LOGGER.error(
        "Erro interno não tratado",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content={
            "erro": "Ocorreu um erro interno ao processar a solicitação.",
            "codigo": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


def repo_for(db: Session, scope: DirectorateScope) -> DatabaseRepository:
    return DatabaseRepository(
        db,
        scope.user,
        directorate_id=scope.directorate_id,
        directorate_code=scope.directorate_code,
        directorate_name=scope.directorate_name,
    )


def repo_for_user(db: Session, ctx: UserContext) -> DatabaseRepository:
    return DatabaseRepository(db, ctx)


def require_operational_directorate(scope: DirectorateScope, expected: str):
    if scope.directorate_code != expected:
        raise HTTPException(404, f"Este recurso está disponível apenas para a diretoria {expected}.")



def require_academic_directorate(scope: DirectorateScope):
    if scope.directorate_code not in ACADEMIC_DIRECTORATES or scope.directorate_code == "DEAD":
        raise HTTPException(404, "Este recurso está disponível apenas para uma diretoria acadêmica operacional.")


def dpe_list(repo: DatabaseRepository, resource: str):
    if resource == "resultado": return repo.list_dpe_results()
    if resource == "orcamento": return repo.list_dpe_budget()
    if resource == "caixa": return repo.list_dpe_cash()
    raise HTTPException(404, "Base DPE não encontrada.")


def dpe_create(repo: DatabaseRepository, resource: str, payload: dict):
    if resource == "resultado": return repo.create_dpe_result(payload)
    if resource == "orcamento": return repo.create_dpe_budget(payload)
    if resource == "caixa": return repo.create_dpe_cash(payload)
    raise HTTPException(404, "Base DPE não encontrada.")


def dpe_update(repo: DatabaseRepository, resource: str, row_id: int, payload: dict):
    if resource == "resultado": return repo.update_dpe_result(row_id, payload)
    if resource == "orcamento": return repo.update_dpe_budget(row_id, payload)
    if resource == "caixa": return repo.update_dpe_cash(row_id, payload)
    raise HTTPException(404, "Base DPE não encontrada.")


def dpe_delete(repo: DatabaseRepository, resource: str, row_id: int):
    if resource == "resultado": return repo.delete_dpe_result(row_id)
    if resource == "orcamento": return repo.delete_dpe_budget(row_id)
    if resource == "caixa": return repo.delete_dpe_cash(row_id)
    raise HTTPException(404, "Base DPE não encontrada.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort API boundary: log details server-side, never expose them."""
    return api_error(exc)


def _safe_security_audit(**kwargs) -> None:
    """Security telemetry must never turn an intended 401/403 into a 500."""
    try:
        with SessionLocal() as audit_db:
            log_auth_event(audit_db, **kwargs)
    except Exception:
        LOGGER.warning("Falha ao persistir auditoria de segurança; confirme a migration 033.")


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = set_request_id(request_id)
    started = time.perf_counter()
    response = None
    unsafe = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    try:
        if (
            unsafe
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/auth/login"
            and request_has_v2_session(request)
            and not csrf_request_valid(request)
        ):
            user_agent_hash, ip_hash = request_fingerprints(
                request.headers.get("user-agent"),
                request.client.host if request.client else None,
            )
            request.state.csrf_rejected = True
            _safe_security_audit(
                event_type="CSRF_REJECTED", outcome="DENIED",
                ip_hash=ip_hash, user_agent_hash=user_agent_hash,
                details={"method": request.method, "path": request.url.path},
            )
            response = JSONResponse(status_code=403, content={"detail": "Falha na validação CSRF. Atualize a página e tente novamente."})
        else:
            response = await call_next(request)

        ensure_csrf_cookie(request, response)
        if response.status_code == 403 and request.url.path.startswith("/api/") and not getattr(request.state, "csrf_rejected", False):
            ctx = getattr(request.state, "auth_context", None)
            user_agent_hash, ip_hash = request_fingerprints(
                request.headers.get("user-agent"),
                request.client.host if request.client else None,
            )
            _safe_security_audit(
                event_type="ACCESS_DENIED", outcome="DENIED",
                actor_user_id=getattr(ctx, "user_id", None),
                email=getattr(ctx, "email", None),
                directorate_code=getattr(ctx, "directorate_code", None),
                ip_hash=ip_hash, user_agent_hash=user_agent_hash,
                details={"method": request.method, "path": request.url.path},
            )
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        status = getattr(response, "status_code", 500)
        LOGGER.info(
            "Requisição concluída",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status": status, "duration_ms": duration_ms},
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Data-UNIVC-Build"] = f"{APP_VERSION}/{BUILD_FINGERPRINT}"
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
            response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        reset_request_id(token)


@app.get("/api/health/live")
def health_live():
    return {
        "ok": True,
        "version": APP_VERSION,
        "build": BUILD_FINGERPRINT,
        "schema_expected": SCHEMA_VERSION,
        "educacao_fisica_policy": EDUCACAO_FISICA_IDENTITY_POLICY,
    }


@app.get("/api/health/ready")
def health_ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            schema = get_schema_status(connection)
        required = schema_version_required()
        if required and not schema.compatible:
            LOGGER.error(
                "Schema incompatível com a aplicação",
                extra={
                    "schema_expected": schema.expected,
                    "schema_current": schema.current,
                    "schema_tracked": schema.tracked,
                },
            )
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "version": APP_VERSION,
                    "build": BUILD_FINGERPRINT,
                    "database": "schema_incompatible",
                    "schema": schema.as_dict(),
                    "educacao_fisica_policy": EDUCACAO_FISICA_IDENTITY_POLICY,
                },
            )
        return {
            "ok": True,
            "version": APP_VERSION,
            "build": BUILD_FINGERPRINT,
            "database": "ok",
            "schema": schema.as_dict(),
            "schema_enforced": required,
            "educacao_fisica_policy": EDUCACAO_FISICA_IDENTITY_POLICY,
        }
    except Exception as exc:
        LOGGER.warning(
            "Banco indisponível no readiness check",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "version": APP_VERSION,
                "build": BUILD_FINGERPRINT,
                "schema_expected": SCHEMA_VERSION,
                "educacao_fisica_policy": EDUCACAO_FISICA_IDENTITY_POLICY,
                "database": "unavailable",
            },
        )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"app_version": APP_VERSION}, headers={"Cache-Control": "no-store"})


@app.post("/api/auth/login")
async def auth_login(request: Request, response: Response, db: Session = Depends(get_db)):
    payload = await request.json()
    return await login_with_password(
        str(payload.get("email", "")).strip(),
        str(payload.get("password", "")),
        response,
        db,
        request,
    )


@app.post("/api/auth/refresh")
async def auth_refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    return await refresh_session(request, response, db)


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    return logout_session(request, response, db)


@app.get("/api/auth/me")
def auth_me(db: Session = Depends(get_db), ctx: UserContext = Depends(current_context)):
    available = accessible_directorates(db, ctx)
    visible_codes = set(visible_operating_directorate_codes())
    canonical_directorates = [
        {
            "code": grant.code,
            "name": grant.name,
            "access": grant.access,
            "primary": bool(grant.is_primary or grant.code == ctx.directorate_code),
        }
        for grant in ctx.directorate_access
        if grant.code in visible_codes
    ]
    canonical_available = [
        {
            "code": item["codigo"],
            "name": item["nome"],
            "access": item["nivel_acesso"],
            "primary": bool(item["principal"]),
        }
        for item in available
    ]
    canonical_home = next((item for item in canonical_available if item["primary"]), None)
    if canonical_home is None and canonical_available:
        canonical_home = canonical_available[0]
    # v0.9.6.0 keeps legacy aliases temporarily so the untouched v0.8.33
    # frontend continues to work until the frontend identity rebase in v0.9.6.1.
    return {
        "user": {"id": ctx.user_id, "name": ctx.full_name, "email": ctx.email, "avatar_url": f"/api/profile/avatar/{ctx.user_id}"},
        "role": ctx.global_role,
        "directorates": [] if ctx.global_access else canonical_directorates,
        "available_directorates": canonical_available,
        "home_directorate": canonical_home,
        "global_access": ctx.global_access,
        "permission_version": ctx.permission_version,
        "session_version": 2,
        "data_scopes": {
            "DADM": dadm_scope_payload(ctx.email, global_access=ctx.global_access)
        } if ctx.can_read("DADM") else {},
    }


@app.get("/api/auth/status")
def auth_status():
    return {"ok": True, "version": APP_VERSION}


@app.get("/api/bootstrap")
def bootstrap(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    try:
        repo = repo_for(db, scope)
        codes = IMPLEMENTED_KPIS.get(scope.directorate_code, ())
        indicators = db.scalars(
            select(IndicatorDefinition)
            .where(IndicatorDefinition.code.in_(codes), IndicatorDefinition.active.is_(True))
            .order_by(IndicatorDefinition.code)
        ).all()
        indicator_payload = []
        for item in indicators:
            meta = KPI_META.get(item.code, {})
            indicator_payload.append(
                {
                    "code": item.code,
                    "name": item.name,
                    "periodicity": item.periodicity,
                    "formula": item.formula_text or meta.get("formula"),
                    "source": item.source_text or meta.get("source"),
                    **{k: v for k, v in meta.items() if k not in {"formula", "source"}},
                }
            )

        if scope.directorate_code in {"DTNH", "DCS"}:
            # Bootstrap only needs catalog metadata. Loading the complete KPI snapshot
            # here duplicated the same large queries immediately executed by /dashboard.
            courses, disciplines = repo.course_maps(include_inactive=False)
            sei_courses = DTNH_COURSES if scope.directorate_code == "DTNH" else DCS_COURSES
            extra = {"sei_courses": list(sei_courses)}
            datasets = {k: {"label": DATASETS[k].label, "template": f"/api/modelos/{k}"} for k in ACADEMIC_UI_DATASETS}
        elif scope.directorate_code == "DADM":
            # v0.7.8: a DADM possui página e API dedicadas. O bootstrap legado
            # mantém apenas metadados mínimos para compatibilidade com o shell inicial.
            courses = []
            disciplines = {}
            extra = {}
            datasets = {}
        elif scope.directorate_code == "DPE":
            courses = []
            disciplines = {}
            extra = {"dpe": repo.dpe_reference_options()}
            datasets = {
                "dpe-resultado": {"label": "Resultado Operacional", "template": "/api/modelos/dpe-resultado"},
                "dpe-orcamento": {"label": "Execução Orçamentária", "template": "/api/modelos/dpe-orcamento"},
                "dpe-caixa": {"label": "Saldo Operacional de Caixa", "template": "/api/modelos/dpe-caixa"},
            }
        else:
            courses = []
            disciplines = {}
            extra = {}
            datasets = {}

        return {
            "config": repo.get_config(),
            "courses": courses,
            "disciplines": disciplines,
            "datasets": datasets,
            "indicators": indicator_payload,
            "actions_count": len(repo.list_actions()),
            "goals_count": len(repo.list_goals()),
            "courses_count": len(courses),
            "disciplines_count": sum(len(v) for v in disciplines.values()),
            "access": {
                "diretoria": scope.directorate_code,
                "diretoria_nome": scope.directorate_name,
                "principal": scope.is_home,
                "pode_editar": scope.can_write,
            },
            "cloud": True,
            **extra,
        }
    except Exception as exc:
        return api_error(exc)


@app.get("/api/dashboard")
def dashboard(
    curso: str | None = Query(None),
    disciplina: str | None = Query(None),
    curso_id: int | None = Query(None),
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    inicio: str | None = Query(None),
    fim: str | None = Query(None),
    setor: str | None = Query(None),
    modalidade: str | None = Query(None),
    tipo_recorte: str | None = Query(None),
    recorte: str | None = Query(None),
    unidade: str | None = Query(None),
    centro_custo: str | None = Query(None),
    conta: str | None = Query(None),
    natureza: str | None = Query(None),
    janela: str | None = Query(None),
    granularidade: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        repo = repo_for(db, scope)
        window_months = _parse_window_query(janela)
        if scope.directorate_code in {"DTNH", "DCS"}:
            snap = repo.academic_dashboard_snapshot()
            snap["actions"] = repo.list_actions()
            return build_academic_dashboard(
                snap, course=curso, discipline=disciplina, reference=referencia, comparison=comparacao,
                window_semesters=window_months, directorate_code=scope.directorate_code, granularity=granularidade,
            )
        if scope.directorate_code == "DADM":
            raise HTTPException(410, "Dashboard legado da DADM descontinuado na v0.7.8. Use /api/dadm/dashboard.")
        if scope.directorate_code == "DPE":
            return build_dpe_dashboard(
                repo.snapshot_dpe(), referencia=referencia, comparacao=comparacao,
                inicio=inicio, fim=fim, tipo_recorte=tipo_recorte, recorte=recorte,
                unidade=unidade, centro_custo=centro_custo, conta=conta,
                natureza=natureza, window_months=window_months,
            )
        raise HTTPException(501, "O painel desta diretoria ainda não foi implementado.")
    except Exception as exc:
        return api_error(exc)


@app.get("/api/cadastros")
def catalogs(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    require_academic_directorate(scope)
    repo = repo_for(db, scope)
    return {"cursos": repo.list_courses(), "disciplinas": repo.list_disciplines()}


@app.post("/api/cursos")
async def create_course(request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    try:
        return repo_for(db, scope).create_course(await request.json())
    except Exception as exc:
        return api_error(exc)


@app.put("/api/cursos/{row_id}/status")
async def course_status(row_id: int, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    try:
        payload = await request.json()
        return repo_for(db, scope).set_course_active(row_id, bool(payload.get("ativo")), payload.get("vigencia_fim"))
    except Exception as exc:
        return api_error(exc)


@app.post("/api/disciplinas")
async def create_discipline(request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    try:
        return repo_for(db, scope).create_discipline(await request.json())
    except Exception as exc:
        return api_error(exc)


@app.put("/api/disciplinas/{row_id}/status")
async def discipline_status(row_id: int, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    try:
        payload = await request.json()
        return repo_for(db, scope).set_discipline_active(row_id, bool(payload.get("ativo")), payload.get("vigencia_fim"))
    except Exception as exc:
        return api_error(exc)


@app.get("/api/dados/{dataset}")
def list_data(
    dataset: str,
    curso: str | None = None,
    disciplina: str | None = None,
    periodo: str | None = None,
    professor: str | None = None,
    busca: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    require_academic_directorate(scope)
    try:
        repo = repo_for(db, scope)
        filters = {"curso": curso or "", "disciplina": disciplina or "", "periodo": periodo or "", "professor": professor or "", "busca": busca or ""}
        if dataset == "resultados":
            return repo.list_results_page(filters, page=page, page_size=page_size)
        if dataset == "avaliacao_docente":
            return repo.list_teacher_evaluations_page(filters, page=page, page_size=page_size)
        items = repo.list_records(dataset, filters)
        return {"items": items, "total": len(items), "page": 1, "page_size": len(items) or page_size, "pages": 1}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/avaliacao-docente/opcoes")
def teacher_evaluation_options(
    curso: str | None = None,
    disciplina: str | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    require_academic_directorate(scope)
    try:
        return repo_for(db, scope).teacher_evaluation_filter_options({
            "curso": curso or "",
            "disciplina": disciplina or "",
        })
    except Exception as exc:
        return api_error(exc)


@app.get("/api/avaliacao-docente/analise")
def teacher_evaluation_analysis(
    periodo: str | None = None,
    curso: str | None = None,
    disciplina: str | None = None,
    professor: str | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    require_academic_directorate(scope)
    try:
        return repo_for(db, scope).teacher_evaluation_analysis({
            "periodo": periodo or "",
            "curso": curso or "",
            "disciplina": disciplina or "",
            "professor": professor or "",
        })
    except Exception as exc:
        return api_error(exc)


@app.get("/api/resultados/resumo")
def result_summary(
    curso: str | None = None,
    disciplina: str | None = None,
    periodo: str | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    require_academic_directorate(scope)
    try:
        items = repo_for(db, scope).academic_result_summary({
            "curso": curso or "",
            "disciplina": disciplina or "",
            "periodo": periodo or "",
        })
        return {"items": items, "total": len(items)}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/resultados/tendencia")
def result_trend(
    curso: str | None = None,
    disciplina: str | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    require_academic_directorate(scope)
    try:
        items = repo_for(db, scope).academic_result_trend({
            "curso": curso or "",
            "disciplina": disciplina or "",
        })
        return {"items": items, "total": len(items)}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/dados/{dataset}")
async def create_data(dataset: str, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    if dataset == "nps":
        raise HTTPException(410, "O NPS é alimentado exclusivamente pela integração de Avaliações SEI. Use NPS Discente > Atualizar pelo SEI; o mesmo fluxo aceita XLSX/ZIP do relatório como contingência.")
    try:
        return repo_for(db, scope).create_record(dataset, await request.json())
    except Exception as exc:
        return api_error(exc)


@app.put("/api/dados/{dataset}/{row_id}")
async def update_data(dataset: str, row_id: int, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    if dataset == "nps":
        raise HTTPException(410, "O NPS sincronizado pelo SEI é somente leitura nesta API. Para trocar a fonte oficial, faça uma nova sincronização em NPS Discente > Atualizar pelo SEI.")
    try:
        return repo_for(db, scope).update_record(dataset, row_id, await request.json())
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/dados/{dataset}/{row_id}")
def delete_data(dataset: str, row_id: int, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_academic_directorate(scope)
    if dataset == "nps":
        raise HTTPException(410, "O NPS sincronizado pelo SEI não pode ser excluído pelo CRUD legado. Troque a fonte oficial pela integração de Avaliações SEI.")
    try:
        repo_for(db, scope).delete_record(dataset, row_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/dpe/{resource}")
def list_dpe(resource: str, db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    require_operational_directorate(scope, "DPE")
    try:
        return {"items": dpe_list(repo_for(db, scope), resource)}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/dpe/{resource}")
async def create_dpe(resource: str, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_operational_directorate(scope, "DPE")
    try:
        return dpe_create(repo_for(db, scope), resource, await request.json())
    except Exception as exc:
        return api_error(exc)


@app.put("/api/dpe/{resource}/{row_id}")
async def update_dpe(resource: str, row_id: int, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_operational_directorate(scope, "DPE")
    try:
        return dpe_update(repo_for(db, scope), resource, row_id, await request.json())
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/dpe/{resource}/{row_id}")
def delete_dpe(resource: str, row_id: int, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    require_operational_directorate(scope, "DPE")
    try:
        dpe_delete(repo_for(db, scope), resource, row_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/metas")
def goals(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    return {"items": repo_for(db, scope).list_goals()}


@app.post("/api/metas")
async def create_goal(request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    try:
        return repo_for(db, scope).create_goal(await request.json())
    except Exception as exc:
        return api_error(exc)


@app.put("/api/metas/{row_id}")
async def update_goal(row_id: int, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    try:
        return repo_for(db, scope).update_goal(row_id, await request.json())
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/metas/{row_id}")
def delete_goal(row_id: int, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    try:
        repo_for(db, scope).delete_goal(row_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/planos")
def actions(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    return {"items": repo_for(db, scope).list_actions()}


@app.post("/api/planos")
async def create_action(request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    try:
        return repo_for(db, scope).create_action(await request.json())
    except Exception as exc:
        return api_error(exc)


@app.put("/api/planos/{row_id}")
async def update_action(row_id: int, request: Request, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    try:
        return repo_for(db, scope).update_action(row_id, await request.json())
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/planos/{row_id}")
def delete_action(row_id: int, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_scope_write)):
    try:
        repo_for(db, scope).delete_action(row_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/importar/{dataset}")
async def import_data(
    dataset: str,
    arquivo: UploadFile = File(...),
    modo: str = Query("add"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    if dataset == "nps":
        raise HTTPException(410, "Importação legada do NPS foi removida. Use NPS Discente > Atualizar pelo SEI; o mesmo fluxo aceita XLSX/ZIP do relatório como contingência.")
    if Path(arquivo.filename or "").suffix.lower() not in {".xlsx", ".xlsm"}:
        raise HTTPException(400, "Envie uma planilha .xlsx ou .xlsm.")
    suffix = Path(arquivo.filename or "").suffix.lower()
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    path = Path(name)
    try:
        size = await save_validated_excel_upload(arquivo, path)
        LOGGER.info(
            "Planilha validada para importação",
            extra={"dataset": dataset, "bytes": size, "directorate": scope.directorate_code},
        )
        repo = repo_for(db, scope)
        mode = "update" if modo == "update" else "add"
        if dataset.startswith("dadm-"):
            require_operational_directorate(scope, "DADM")
            raise HTTPException(410, "Importação legada da DADM descontinuada. Use /api/dadm/import com DADM-01 ou DADM-02.")
        if dataset.startswith("dpe-"):
            require_operational_directorate(scope, "DPE")
            return repo.import_dpe_file(dataset, path, mode)
        require_academic_directorate(scope)
        if dataset == "disciplinas":
            return repo.import_disciplines_file(path, mode)
        return repo.import_file(dataset, path, mode)
    except Exception as exc:
        return api_error(exc)
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/sei/importar-resultados")
async def import_results_from_sei(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    """Consulta o relatório de notas do SEI e importa os resultados no Data UNIVC.

    Credenciais são usadas somente durante esta requisição. O endpoint não as
    persiste em banco, auditoria ou arquivo de configuração.
    """
    require_academic_directorate(scope)
    try:
        payload = await request.json()
        username = str(payload.get("usuario") or "").strip()
        password = str(payload.get("senha") or "")
        year = str(payload.get("ano") or "").strip()
        semester = str(payload.get("semestre") or "").strip()
        raw_courses = payload.get("cursos") or []
        if isinstance(raw_courses, str):
            courses = [x.strip() for x in raw_courses.replace(";", "\n").splitlines() if x.strip()]
        else:
            courses = [str(x).strip() for x in raw_courses if str(x).strip()]

        field_errors = {}
        if not username: field_errors["usuario"] = "Informe o usuário do SEI."
        if not password: field_errors["senha"] = "Informe a senha do SEI."
        if not (year.isdigit() and len(year) == 4): field_errors["ano"] = "Informe um ano com quatro dígitos."
        if semester not in {"1", "2"}: field_errors["semestre"] = "Informe semestre 1 ou 2."

        if not courses:
            if scope.directorate_code == "DTNH":
                courses = list(DTNH_COURSES)
            elif scope.directorate_code == "DCS":
                courses = list(DCS_COURSES)
        if field_errors:
            raise ValidationError("Revise os campos destacados.", field_errors)

        repo = repo_for(db, scope)
        LOGGER.info(
            "Importação SEI iniciada",
            extra={"directorate": scope.directorate_code, "rows": len(courses)},
        )
        with tempfile.TemporaryDirectory(prefix="data_univc_sei_") as tmp:
            root = Path(tmp)
            bot = SEIBot(debug_dir=root / "debug")
            bot.login(username, password)
            bot.abrir_home()
            bot.abrir_menu_academico()
            bot.carregar_menu_js()
            successes, failures = baixar_cursos_sei(
                bot, ano=year, semestre=semester, output_dir=root / "relatorios", cursos=courses,
            )

            totals = {"inseridos": 0, "atualizados": 0, "ignorados": 0, "erros": []}
            imported_files = []
            parser_warnings = []
            for course_name, path in successes:
                try:
                    report = repo.import_sei_report_file(path, mode="add", expected_course=course_name)
                except Exception as exc:
                    # Uma falha de validação/importação de um curso não deve
                    # derrubar a requisição inteira nem esconder os cursos que
                    # funcionaram. O detalhe é devolvido por curso, sem
                    # credenciais/cookies, para diagnóstico objetivo.
                    failures.append((course_name, f"Importação do XLSX: {exc}"))
                    continue
                metadata = report.get("metadados") or {}
                imported_files.append({
                    "curso": course_name,
                    "arquivo": path.name,
                    "registros_lidos": report.get("registros_lidos", 0),
                    "curso_sei_xlsx": metadata.get("curso_origem_sei"),
                    "ano_xlsx": metadata.get("ano"),
                    "semestre_xlsx": metadata.get("semestre"),
                    "curso_canonico": metadata.get("curso"),
                    "identidade_validada": metadata.get("identidade_curso_validada"),
                    "identidade_validada_por": metadata.get("identidade_curso_validada_por"),
                    "alunos_unicos": metadata.get("total_alunos_unicos"),
                    "turmas": metadata.get("total_turmas"),
                })
                totals["inseridos"] += report.get("inseridos", 0)
                totals["atualizados"] += report.get("atualizados", 0)
                totals["ignorados"] += report.get("ignorados", 0)
                totals["erros"].extend(report.get("erros", []))
                parser_warnings.extend(report.get("avisos_parser", []))

        LOGGER.info(
            "Importação SEI concluída",
            extra={
                "directorate": scope.directorate_code,
                "rows": totals["inseridos"] + totals["atualizados"],
            },
        )
        # Não inclua usuário/senha em auditoria. O importador de arquivo já registra
        # o resumo de cada carga, sem credenciais.
        return {
            "ok": bool(imported_files),
            "versao": APP_VERSION,
            "build": BUILD_FINGERPRINT,
            "educacao_fisica_policy": EDUCACAO_FISICA_IDENTITY_POLICY,
            "diretoria": scope.directorate_code,
            "ano": year,
            "semestre": semester,
            "cursos_solicitados": courses,
            "relatorios_importados": imported_files,
            "falhas_sei": [{"curso": course, "erro": error} for course, error in failures],
            "avisos_parser": parser_warnings[:100],
            **totals,
        }
    except Exception as exc:
        return api_error(exc)


MODEL_FILES = {
    "avaliacao_docente": ROOT / "assets" / "modelos" / "Modelo_Avaliacao_Docente.xlsx",
    "resultados": ROOT / "assets" / "modelos" / "Modelo_Resultados_Academicos.xlsx",
    "matriculas": ROOT / "assets" / "modelos" / "Modelo_Matriculas_Ativas.xlsx",
    "frequencia": ROOT / "assets" / "modelos" / "Modelo_Frequencia_Media.xlsx",
    "disciplinas": ROOT / "assets" / "modelos" / "Modelo_Disciplinas.xlsx",
    "dpe-resultado": ROOT / "assets" / "modelos" / "Modelo_DPE_01_Resultado_Operacional.xlsx",
    "dpe-orcamento": ROOT / "assets" / "modelos" / "Modelo_DPE_04_Execucao_Orcamentaria.xlsx",
    "dpe-caixa": ROOT / "assets" / "modelos" / "Modelo_DPE_05_Saldo_Operacional_Caixa.xlsx",
}


@app.get("/api/modelos/{dataset}")
def model(
    dataset: str,
    scope: DirectorateScope = Depends(current_scope),
):
    path = MODEL_FILES.get(dataset)
    if not path or not path.exists():
        raise HTTPException(404, "Modelo não encontrado no diretório da aplicação.")
    if dataset.startswith("dpe-"):
        require_operational_directorate(scope, "DPE")
    else:
        require_academic_directorate(scope)
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )



@app.get("/api/excel-interativo")
def excel_interativo(
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    curso: str | None = Query(None),
    disciplina: str | None = Query(None),
    janela: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    if scope.directorate_code not in {"DTNH", "DCS"}:
        raise HTTPException(400, "O Excel Interativo V3 acadêmico está disponível apenas para DTNH/DCS.")
    acquired = False
    try:
        window_periods = _parse_window_query(janela, preserve_all=True)
        acquired = _EXCEL_EXPORT_SLOTS.acquire(timeout=EXCEL_EXPORT_WAIT_SECONDS)
        if not acquired:
            raise HTTPException(503, "O serviço de exportação está ocupado. Tente novamente em instantes.")
        started = time.perf_counter()
        buffer = export_academic_interactive_excel(
            repo_for(db, scope),
            reference=referencia,
            comparison=comparacao,
            course=curso,
            discipline=disciplina,
            window_periods=window_periods,
        )
        size = buffer.getbuffer().nbytes if hasattr(buffer, "getbuffer") else None
        LOGGER.info(
            "Excel interativo gerado",
            extra={
                "directorate": scope.directorate_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes": size,
            },
        )
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="Painel_{scope.directorate_code}_Interativo_beta.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        if acquired:
            _EXCEL_EXPORT_SLOTS.release()

@app.get("/api/excel")
def excel(
    granularidade: str | None = Query(None),
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    curso: str | None = Query(None),
    disciplina: str | None = Query(None),
    janela: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    acquired = False
    try:
        window_periods = _parse_window_query(janela, preserve_all=True)
        acquired = _EXCEL_EXPORT_SLOTS.acquire(timeout=EXCEL_EXPORT_WAIT_SECONDS)
        if not acquired:
            raise HTTPException(503, "O serviço de exportação está ocupado. Tente novamente em instantes.")
        started = time.perf_counter()
        buffer = export_formatted_excel(
            repo_for(db, scope),
            granularity=granularidade,
            reference=referencia,
            comparison=comparacao,
            course=curso,
            discipline=disciplina,
            window_periods=window_periods,
        )
        size = buffer.getbuffer().nbytes if hasattr(buffer, "getbuffer") else None
        LOGGER.info(
            "Excel gerado",
            extra={
                "directorate": scope.directorate_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes": size,
            },
        )
        if scope.directorate_code in {"DTNH", "DCS"}:
            reference_label = str(referencia or "atual").replace("/", "-").replace(" ", "_")
            filename = f"Relatorio_{scope.directorate_code}_Academico_{reference_label}.xlsx"
        else:
            filename = f"Painel_{scope.directorate_code}_atualizado.xlsx"
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        return api_error(exc)
    finally:
        if acquired:
            _EXCEL_EXPORT_SLOTS.release()


@app.get("/api/download/status")
def download_status(scope: DirectorateScope = Depends(current_scope)):
    template = ROOT / "assets" / "paineis" / f"Painel_{scope.directorate_code}_template.xlsx"
    return {
        "ok": True,
        "diretoria": scope.directorate_code,
        "template_excel": template.exists(),
        "modelos": {key: path.exists() for key, path in MODEL_FILES.items()},
    }


@app.get("/api/auditoria")
def audit(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    return {"items": repo_for(db, scope).recent_audit()}


@app.get("/api/cronograma")
def cronograma(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    return {"items": schedule_status(db, scope.directorate_code, IMPLEMENTED_KPIS.get(scope.directorate_code, ()))}


@app.put("/api/cronograma/{indicator_code}")
async def update_cronograma(
    indicator_code: str,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    if indicator_code not in IMPLEMENTED_KPIS.get(scope.directorate_code, ()):
        raise HTTPException(404, "KPI não implementado para esta diretoria.")
    definition = db.get(IndicatorDefinition, indicator_code)
    if not definition:
        raise HTTPException(404, "KPI não encontrado.")
    if definition.directorate_code != scope.directorate_code:
        raise HTTPException(403, "Você não possui acesso a este KPI.")
    schedule = db.scalar(select(IndicatorSchedule).where(IndicatorSchedule.indicator_code == indicator_code))
    if not schedule:
        raise HTTPException(404, "Cronograma não encontrado.")
    payload = await request.json()
    due = int(payload.get("due_business_day", schedule.due_business_day))
    start = int(payload.get("collection_window_start_business_day", schedule.collection_window_start_business_day))
    if not 1 <= due <= 23 or not 1 <= start <= 23 or start > due:
        raise HTTPException(422, "A janela deve usar dias úteis entre 1 e 23, com abertura anterior ou igual ao vencimento.")
    schedule.due_business_day = due
    schedule.collection_window_start_business_day = start
    schedule.reference_grain = str(payload.get("reference_grain", schedule.reference_grain))
    schedule.notes = str(payload.get("notes", schedule.notes or ""))
    db.commit()
    return {
        "ok": True,
        "item": next(
            (x for x in schedule_status(db, scope.directorate_code, IMPLEMENTED_KPIS.get(scope.directorate_code, ())) if x["codigo"] == indicator_code),
            None,
        ),
    }


@app.get("/api/config")
def config(db: Session = Depends(get_db), scope: DirectorateScope = Depends(current_scope)):
    return repo_for(db, scope).get_config()


@app.put("/api/config")
async def save_config(request: Request, db: Session = Depends(get_db), ctx: UserContext = Depends(require_write)):
    try:
        return repo_for_user(db, ctx).save_config(await request.json())
    except Exception as exc:
        return api_error(exc)
