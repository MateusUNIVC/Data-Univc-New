from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from release_info import APP_VERSION
from management_catalog import ManagementCatalogError, catalog_payload, directorate_spec
from management_excel_builder import build_management_workbook
from management_repository import ManagementRepository
from management_service import ManagementValidationError, build_management_dashboard
from security import DirectorateScope, current_scope, require_scope_write

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("univc.management")
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()


def _require_management(scope: DirectorateScope) -> None:
    if scope.directorate_code not in {"DADM", "DPE", "DM"}:
        raise HTTPException(404, "O novo módulo gerencial está disponível para DADM, DPE e DM.")


def _repo(db: Session, scope: DirectorateScope) -> ManagementRepository:
    _require_management(scope)
    return ManagementRepository(db, scope)


def _translate(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, (ManagementValidationError, ManagementCatalogError)):
        detail: dict[str, Any] = {"erro": str(exc)}
        if isinstance(exc, ManagementValidationError) and exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado no módulo gerencial")
    raise HTTPException(500, "Ocorreu um erro interno no módulo gerencial.") from exc


@router.get("/gestao-indicadores", response_class=HTMLResponse)
def management_page(request: Request):
    # DPE and DM have dedicated, standardized experiences. Old bookmarks are
    # redirected so users never fall back to the generic legacy screen.
    directorate = str(request.query_params.get("diretoria") or "").strip().upper()
    if directorate == "DADM":
        return RedirectResponse(url="/dadm?diretoria=DADM", status_code=307)
    if directorate == "DPE":
        return RedirectResponse(url="/dpe?diretoria=DPE", status_code=307)
    if directorate == "DM":
        return RedirectResponse(url="/dm?diretoria=DM", status_code=307)
    return templates.TemplateResponse(
        request=request,
        name="management.html",
        context={"app_version": APP_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/management/catalog")
def management_catalog(scope: DirectorateScope = Depends(current_scope)):
    try:
        _require_management(scope)
        return catalog_payload(scope.directorate_code)
    except Exception as exc:
        _translate(exc)


@router.get("/api/management/dashboard")
def management_dashboard(
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    indicador: str | None = Query(None),
    janela: int | None = Query(None, ge=1, le=240),
    dimensions: str | None = Query(None, description="JSON com filtros dimensionais"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        repo = _repo(db, scope)
        dimension_filters = None
        if dimensions:
            import json
            parsed = json.loads(dimensions)
            if not isinstance(parsed, dict):
                raise ManagementValidationError("O filtro de dimensões precisa ser um objeto JSON.")
            dimension_filters = {str(k): str(v) for k, v in parsed.items() if str(v).strip()}
        return build_management_dashboard(
            scope.directorate_code,
            repo.all_measurements(),
            repo.list_targets(),
            repo.list_actions(),
            reference=referencia,
            comparison=comparacao,
            indicator_code=indicador,
            dimension_filters=dimension_filters,
            window=janela,
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/management/measurements")
def management_measurements(
    indicador: str | None = Query(None),
    periodo: str | None = Query(None),
    dimensao: str | None = Query(None),
    busca: str | None = Query(None),
    validado: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        return _repo(db, scope).list_measurements(
            indicator_code=indicador,
            period=periodo,
            dimension_key=dimensao,
            dimension_search=busca,
            validated=validado,
            offset=offset,
            limit=limit,
        )
    except Exception as exc:
        _translate(exc)


@router.post("/api/management/measurements")
async def management_measurement_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).upsert_measurement(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/management/measurements/{row_id}")
async def management_measurement_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).update_measurement(row_id, await request.json())
    except Exception as exc:
        _translate(exc)


@router.delete("/api/management/measurements/{row_id}")
def management_measurement_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        _repo(db, scope).delete_measurement(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/management/targets")
def management_targets(
    indicador: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        return {"items": _repo(db, scope).list_targets(indicator_code=indicador)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/management/targets")
async def management_target_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).save_target(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/management/targets/{row_id}")
async def management_target_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).save_target(await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/management/targets/{row_id}")
def management_target_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        _repo(db, scope).delete_target(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/management/actions")
def management_actions(
    indicador: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        return {"items": _repo(db, scope).list_actions(indicator_code=indicador, status=status)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/management/actions")
async def management_action_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).save_action(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/management/actions/{row_id}")
async def management_action_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).save_action(await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/management/actions/{row_id}")
def management_action_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        _repo(db, scope).delete_action(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/management/excel")
def management_excel(
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        repo = _repo(db, scope)
        buffer = build_management_workbook(
            scope.directorate_code,
            repo.all_measurements(),
            repo.list_targets(),
            repo.list_actions(),
            reference=referencia,
            comparison=comparacao,
        )
        filename = f"Painel_{scope.directorate_code}_gerencial.xlsx"
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)
