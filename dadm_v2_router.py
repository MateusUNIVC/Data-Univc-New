from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from auth.data_scopes import dadm_department_scope, department_allowed
from dadm_v2_analytics import (
    context_payload,
    entity_attendances_payload,
    entity_evaluations_payload,
    entity_profile_payload,
    experience_breakdown,
    overview_payload,
    quality_payload,
)
from dadm_v2_report import build_dadm_v2_report
from dadm_v2_management import (
    delete_action,
    delete_target,
    management_payload,
    save_action,
    save_target,
)
from release_info import APP_VERSION
from security import DirectorateScope, require_directorate_access, require_directorate_edit

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()


def _require_dadm(scope: DirectorateScope) -> DirectorateScope:
    if scope.directorate_code != "DADM":
        raise HTTPException(404, "Esta rota pertence à Diretoria Administrativa.")
    return scope




def _allowed_departments(scope: DirectorateScope) -> tuple[str, ...] | None:
    return dadm_department_scope(scope.user.email, global_access=scope.user.global_access)


def _require_department(scope: DirectorateScope, department: str | None) -> None:
    if department and not department_allowed(department, _allowed_departments(scope)):
        raise HTTPException(403, "Este departamento não faz parte do seu escopo de dados na DADM.")

def _translate(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(422, str(exc)) from exc
    raise exc


@router.get("/dadm", response_class=HTMLResponse)
def dadm_page(request: Request):
    """Official DADM surface. The V2 analytics experience is now the primary UI."""
    return templates.TemplateResponse(
        request=request,
        name="dadm_v2.html",
        context={"app_version": APP_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/dadm/v2")
def dadm_v2_redirect(request: Request):
    """Keep old bookmarks working while making /dadm the canonical URL."""
    query = request.url.query
    target = "/dadm" + (f"?{query}" if query else "?diretoria=DADM")
    return RedirectResponse(target, status_code=307)


@router.get("/api/dadm/v2/context")
def dadm_v2_context(
    from_month: str | None = Query(None),
    to_month: str | None = Query(None),
    department: str | None = Query(None),
    employee: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    tabulation: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, department)
        return context_payload(
            db, scope.directorate_id, from_month, to_month,
            department=department, employee=employee, channel=channel,
            status=status, tabulation=tabulation,
            allowed_departments=_allowed_departments(scope),
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/overview")
def dadm_v2_overview(
    from_month: str | None = Query(None),
    to_month: str | None = Query(None),
    department: str | None = Query(None),
    employee: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    tabulation: str | None = Query(None),
    comparison: str = Query("previous_period", pattern="^(none|previous_period|previous_year)$"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, department)
        return overview_payload(
            db, scope.directorate_id, from_month, to_month,
            department=department, employee=employee, channel=channel,
            status=status, tabulation=tabulation, comparison_mode=comparison,
            allowed_departments=_allowed_departments(scope),
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/entity")
def dadm_v2_entity(
    kind: str = Query(..., pattern="^(employee|department)$"),
    entity_id: str = Query(..., min_length=1),
    from_month: str | None = Query(None),
    to_month: str | None = Query(None),
    department: str | None = Query(None),
    employee: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    tabulation: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, entity_id if kind == "department" else department)
        return entity_profile_payload(
            db, scope.directorate_id, kind, entity_id, from_month, to_month,
            department=department, employee=employee, channel=channel,
            status=status, tabulation=tabulation,
            allowed_departments=_allowed_departments(scope),
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/entity/attendances")
def dadm_v2_entity_attendances(
    kind: str = Query(..., pattern="^(employee|department)$"), entity_id: str = Query(..., min_length=1),
    from_month: str | None = Query(None), to_month: str | None = Query(None),
    department: str | None = Query(None), employee: str | None = Query(None),
    channel: str | None = Query(None), status: str | None = Query(None), tabulation: str | None = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    rating_filter: str = Query("all", pattern="^(all|rated|unrated)$"),
    order: str = Query("newest", pattern="^(newest|oldest|tme_high|tma_high|lowest_rating|highest_rating)$"),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, entity_id if kind == "department" else department)
        return entity_attendances_payload(
            db, scope.directorate_id, kind, entity_id, from_month, to_month, department=department, employee=employee,
            channel=channel, status=status, tabulation=tabulation, page=page, page_size=page_size,
            rating_filter=rating_filter, order=order, allowed_departments=_allowed_departments(scope),
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/entity/evaluations")
def dadm_v2_entity_evaluations(
    kind: str = Query(..., pattern="^(employee|department)$"),
    entity_id: str = Query(..., min_length=1),
    from_month: str | None = Query(None),
    to_month: str | None = Query(None),
    department: str | None = Query(None),
    employee: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    tabulation: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order: str = Query("newest", pattern="^(newest|lowest|highest)$"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, entity_id if kind == "department" else department)
        return entity_evaluations_payload(
            db, scope.directorate_id, kind, entity_id, from_month, to_month,
            department=department, employee=employee, channel=channel,
            status=status, tabulation=tabulation, page=page, page_size=page_size,
            order=order, allowed_departments=_allowed_departments(scope),
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/experience")
def dadm_v2_experience(
    dimension: str = Query("employee", pattern="^(employee|department|channel|tabulation)$"),
    from_month: str | None = Query(None),
    to_month: str | None = Query(None),
    department: str | None = Query(None),
    employee: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    tabulation: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, department)
        return experience_breakdown(
            db, scope.directorate_id, dimension, from_month, to_month,
            department=department, employee=employee, channel=channel,
            status=status, tabulation=tabulation,
            allowed_departments=_allowed_departments(scope),
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/report.xlsx")
def dadm_v2_report(
    from_month: str | None = Query(None),
    to_month: str | None = Query(None),
    department: str | None = Query(None),
    employee: str | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    tabulation: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    """Export the current DADM V2 analytical context as an aggregated XLSX.

    No individual attendance record is exported. The workbook is built from the
    same normalized TALLOS facts and filter contract used by the dashboard.
    """
    try:
        _require_dadm(scope)
        _require_department(scope, department)
        workbook, payload = build_dadm_v2_report(
            db,
            scope.directorate_id,
            from_month,
            to_month,
            department=department,
            employee=employee,
            channel=channel,
            status=status,
            tabulation=tabulation,
            allowed_departments=_allowed_departments(scope),
        )
        period = payload["period"]
        filename = f"DADM_TALLOS_{period['from_month']}_a_{period['to_month']}.xlsx"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        }
        return StreamingResponse(
            workbook,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/v2/quality")
def dadm_v2_quality(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    return quality_payload(db, scope.directorate_id, allowed_departments=_allowed_departments(scope))


@router.get("/api/dadm/v2/management")
def dadm_v2_management(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: str | None = Query(None),
    channel: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        _require_department(scope, department)
        return management_payload(db, scope, month=month, department=department, channel=channel)
    except Exception as exc:
        _translate(exc)


@router.post("/api/dadm/v2/targets")
async def dadm_v2_target_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return save_target(db, scope, await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dadm/v2/targets/{row_id}")
async def dadm_v2_target_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return save_target(db, scope, await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dadm/v2/targets/{row_id}")
def dadm_v2_target_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        delete_target(db, scope, row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dadm/v2/actions")
async def dadm_v2_action_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return save_action(db, scope, await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dadm/v2/actions/{row_id}")
async def dadm_v2_action_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return save_action(db, scope, await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dadm/v2/actions/{row_id}")
def dadm_v2_action_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        delete_action(db, scope, row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)
