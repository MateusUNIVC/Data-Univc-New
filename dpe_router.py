from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from release_info import APP_VERSION
from dpe_excel_export import DPEExcelExportRepository
from dpe_excel_cutover import audit_dpe_cutover_readiness
from dpe_excel_service import dpe_excel_official_enabled, export_dpe_excel, selected_dpe_excel_engine
from dpe_cost_foundation import DPECostFoundationRepository
from dpe_cost_catalog import DPECostCatalogRepository, DPECostCatalogValidationError
from dpe_cost_expenses import DPECostExpenseRepository, DPECostExpenseValidationError
from dpe_cost_teaching import DPECostTeachingRepository, DPECostTeachingValidationError
from dpe_cost_allocation import DPECostAllocationRepository, DPECostAllocationValidationError
from dpe_cost_economics import DPECostEconomicsRepository, DPECostEconomicsValidationError
from dpe_revenues import DPERevenueRepository, DPERevenueValidationError
from dpe_cost_closure import DPECostClosureRepository, DPECostClosureValidationError
from dpe_cost_v2 import DPEV2OverviewRepository
from dpe_cost_analytics import DPECostAnalyticsRepository
from dpe_cost_excel import DPECostExcelError, build_expense_import_template, parse_expense_workbook
from dpe_cost_productivity import DPECostProductivityRepository, DPECostProductivityValidationError
from management_catalog import ManagementCatalogError
from management_service import ManagementValidationError
from models import Course, Directorate
from security import AUTH_DISABLED, DirectorateScope, UserContext, ensure_directorate_visible, require_directorate_access, require_directorate_edit, require_fresh_reitoria, resolve_directorate_scope
from academic_catalog import DTNH_COURSES, DCS_COURSES
from dpe_domain import domain_payload
from dpe_management import DPEManagementRepository

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("univc.dpe")
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()


def _require_dpe(scope: DirectorateScope) -> DirectorateScope:
    if scope.directorate_code != "DPE":
        raise HTTPException(404, "Esta rota pertence exclusivamente à DPE.")
    return scope



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
    LOGGER.exception("Erro não tratado no módulo DPE")
    raise HTTPException(500, "Ocorreu um erro interno no módulo da DPE.") from exc


@router.get("/dpe", response_class=HTMLResponse)
def dpe_page(request: Request):
    ensure_directorate_visible("DPE")
    return templates.TemplateResponse(
        request=request,
        name="dpe.html",
        context={
            "app_version": APP_VERSION,
            "dpe_excel_official": dpe_excel_official_enabled(),
            "local_demo": (
                os.getenv("ENVIRONMENT", "").strip().lower() in {"local", "dev", "development"}
                and AUTH_DISABLED
                and os.getenv("DPE_LOCAL_DEMO", "false").strip().lower() == "true"
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/dpe/domain")
def dpe_domain_contract(
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    """Canonical DPE business vocabulary introduced by the v0.13 domain consolidation."""
    _require_dpe(scope)
    return domain_payload()


def _cost_foundation_repo(db: Session, scope: DirectorateScope) -> DPECostFoundationRepository:
    return DPECostFoundationRepository(db, _require_dpe(scope))


def _cost_catalog_repo(db: Session, scope: DirectorateScope) -> DPECostCatalogRepository:
    return DPECostCatalogRepository(db, _require_dpe(scope))


def _cost_expense_repo(db: Session, scope: DirectorateScope) -> DPECostExpenseRepository:
    return DPECostExpenseRepository(db, _require_dpe(scope))


def _cost_teaching_repo(db: Session, scope: DirectorateScope) -> DPECostTeachingRepository:
    return DPECostTeachingRepository(db, _require_dpe(scope))


def _cost_allocation_repo(db: Session, scope: DirectorateScope) -> DPECostAllocationRepository:
    return DPECostAllocationRepository(db, _require_dpe(scope))


def _cost_economics_repo(db: Session, scope: DirectorateScope) -> DPECostEconomicsRepository:
    return DPECostEconomicsRepository(db, _require_dpe(scope))

def _revenue_repo(db: Session, scope: DirectorateScope) -> DPERevenueRepository:
    return DPERevenueRepository(db, _require_dpe(scope))


def _cost_closure_repo(db: Session, scope: DirectorateScope) -> DPECostClosureRepository:
    return DPECostClosureRepository(db, _require_dpe(scope))


def _management_runtime_repo(db: Session, scope: DirectorateScope) -> DPEManagementRepository:
    return DPEManagementRepository(db, _require_dpe(scope))


def _cost_v2_repo(db: Session, scope: DirectorateScope) -> DPEV2OverviewRepository:
    return DPEV2OverviewRepository(db, _require_dpe(scope))


def _cost_analytics_repo(db: Session, scope: DirectorateScope) -> DPECostAnalyticsRepository:
    return DPECostAnalyticsRepository(db, _require_dpe(scope))


def _cost_productivity_repo(db: Session, scope: DirectorateScope) -> DPECostProductivityRepository:
    return DPECostProductivityRepository(db, _require_dpe(scope))


def _translate_cost_closure(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostClosureValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado no fechamento mensal do DPE Cost Engine")
    raise HTTPException(500, "Ocorreu um erro interno no fechamento mensal da DPE.") from exc


def _translate_revenue(exc: Exception):
    if isinstance(exc, HTTPException): raise exc
    if isinstance(exc, PermissionError): raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError): raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPERevenueValidationError):
        detail={"erro":str(exc)}
        if exc.field_errors: detail["campos"]=exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado nas receitas da DPE")
    raise HTTPException(500, "Ocorreu um erro interno nas receitas da DPE.") from exc


def _translate_cost_economics(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostEconomicsValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado na base econômica do DPE Cost Engine")
    raise HTTPException(500, "Ocorreu um erro interno na base econômica da DPE.") from exc


def _translate_cost_allocation(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostAllocationValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado no Motor de Rateio do DPE Cost Engine")
    raise HTTPException(500, "Ocorreu um erro interno no Motor de Rateio da DPE.") from exc


def _translate_cost_teaching(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostTeachingValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado em Docência e Carga Horária do DPE Cost Engine")
    raise HTTPException(500, "Ocorreu um erro interno no módulo de Docência e Carga Horária da DPE.") from exc


def _translate_cost_catalog(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostCatalogValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado no catálogo econômico DPE")
    raise HTTPException(500, "Ocorreu um erro interno no catálogo econômico da DPE.") from exc


@router.get("/api/dpe/cost-engine/foundation")
def dpe_cost_engine_foundation(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    """Expose the deployed Cost Engine foundation/readiness state."""
    try:
        return _cost_foundation_repo(db, scope).summary()
    except Exception as exc:
        if isinstance(exc, PermissionError):
            raise HTTPException(403, str(exc)) from exc
        LOGGER.exception("Erro ao consultar a fundação do DPE Cost Engine")
        raise HTTPException(500, "Não foi possível consultar a fundação do DPE Cost Engine.") from exc


@router.get("/api/dpe/cost-engine/allocation-rules")
def dpe_cost_engine_allocation_rules(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_foundation_repo(db, scope).list_allocation_rules(active_only=active_only)}
    except Exception as exc:
        if isinstance(exc, PermissionError):
            raise HTTPException(403, str(exc)) from exc
        LOGGER.exception("Erro ao consultar regras de rateio do DPE Cost Engine")
        raise HTTPException(500, "Não foi possível consultar as regras de rateio da DPE.") from exc


@router.get("/api/dpe/cost-engine/catalog")
def dpe_cost_engine_catalog(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).summary()
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.get("/api/dpe/cost-engine/products")
def dpe_cost_engine_products(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_catalog_repo(db, scope).list_products(active_only=active_only)}
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.post("/api/dpe/cost-engine/products")
def dpe_cost_engine_create_product(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).create_product(payload)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.put("/api/dpe/cost-engine/products/{product_id}")
def dpe_cost_engine_update_product(
    product_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).update_product(product_id, payload)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.get("/api/dpe/cost-engine/offerings")
def dpe_cost_engine_offerings(
    product_id: int | None = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_catalog_repo(db, scope).list_offerings(product_id=product_id, active_only=active_only)}
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.post("/api/dpe/cost-engine/offerings")
def dpe_cost_engine_create_offering(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).create_offering(payload)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.put("/api/dpe/cost-engine/offerings/{offering_id}")
def dpe_cost_engine_update_offering(
    offering_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).update_offering(offering_id, payload)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.get("/api/dpe/cost-engine/periods")
def dpe_cost_engine_periods(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_catalog_repo(db, scope).list_periods()}
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.post("/api/dpe/cost-engine/periods")
def dpe_cost_engine_create_period(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).create_period(payload)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}")
def dpe_cost_engine_period_detail(
    period_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).get_period(period_id)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.put("/api/dpe/cost-engine/periods/{period_id}")
def dpe_cost_engine_update_period(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).update_period(period_id, payload)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/refresh-offerings")
def dpe_cost_engine_refresh_period_offerings(
    period_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).refresh_period_offerings(period_id)
    except Exception as exc:
        _translate_cost_catalog(exc)


@router.put("/api/dpe/cost-engine/periods/{period_id}/offerings/{snapshot_id}")
def dpe_cost_engine_toggle_period_offering(
    period_id: int,
    snapshot_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_catalog_repo(db, scope).set_period_offering_included(period_id, snapshot_id, bool(payload.get("included")))
    except Exception as exc:
        _translate_cost_catalog(exc)


def _translate_cost_expense(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostExcelError):
        raise HTTPException(422, {"erro": str(exc), "linhas": exc.errors}) from exc
    if isinstance(exc, DPECostExpenseValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado na Central de Despesas do DPE Cost Engine")
    raise HTTPException(500, "Ocorreu um erro interno na Central de Despesas da DPE.") from exc


@router.get("/api/dpe/cost-engine/expense-central")
def dpe_cost_engine_expense_central(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).central_payload(period_id=period_id)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/cost-centers")
def dpe_cost_engine_cost_centers(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_expense_repo(db, scope).list_cost_centers(active_only=active_only)}
    except Exception as exc:
        _translate_cost_expense(exc)


@router.post("/api/dpe/cost-engine/cost-centers")
def dpe_cost_engine_create_cost_center(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).create_cost_center(payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.put("/api/dpe/cost-engine/cost-centers/{center_id}")
def dpe_cost_engine_update_cost_center(
    center_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).update_cost_center(center_id, payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/expense-categories")
def dpe_cost_engine_expense_categories(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_expense_repo(db, scope).list_categories(active_only=active_only)}
    except Exception as exc:
        _translate_cost_expense(exc)


@router.post("/api/dpe/cost-engine/expense-categories")
def dpe_cost_engine_create_expense_category(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).create_category(payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.put("/api/dpe/cost-engine/expense-categories/{category_id}")
def dpe_cost_engine_update_expense_category(
    category_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).update_category(category_id, payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/expenses")
def dpe_cost_engine_expenses(
    period_id: int | None = Query(None),
    category_id: int | None = Query(None),
    cost_center_id: int | None = Query(None),
    source_type: str | None = Query(None),
    expense_kind: str | None = Query(None),
    expense_scope: str | None = Query(None),
    status: str | None = Query("ACTIVE"),
    q: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_expense_repo(db, scope).list_expenses(
            period_id=period_id, category_id=category_id, cost_center_id=cost_center_id,
            source_type=source_type, expense_kind=expense_kind, expense_scope=expense_scope, status=status, search=q, limit=limit,
        )}
    except Exception as exc:
        _translate_cost_expense(exc)


@router.post("/api/dpe/cost-engine/expenses")
def dpe_cost_engine_create_expense(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).create_expense(payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.put("/api/dpe/cost-engine/expenses/{expense_id}")
def dpe_cost_engine_update_expense(
    expense_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).update_expense(expense_id, payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.post("/api/dpe/cost-engine/expenses/{expense_id}/void")
def dpe_cost_engine_void_expense(
    expense_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).void_expense(expense_id, reason=str(payload.get("reason") or ""))
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/expense-imports")
def dpe_cost_engine_expense_imports(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_expense_repo(db, scope).list_import_batches(period_id=period_id)}
    except Exception as exc:
        _translate_cost_expense(exc)


@router.post("/api/dpe/cost-engine/expense-imports")
def dpe_cost_engine_create_expense_import(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).create_import_batch(payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/expense-imports/{batch_id}/rows")
def dpe_cost_engine_expense_import_rows(
    batch_id: int,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_expense_repo(db, scope).list_staging_rows(batch_id, limit=limit)}
    except Exception as exc:
        _translate_cost_expense(exc)


@router.post("/api/dpe/cost-engine/expense-imports/{batch_id}/rows")
def dpe_cost_engine_stage_expense_import_rows(
    batch_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        return _cost_expense_repo(db, scope).stage_rows(batch_id, rows)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/expense-import-template.xlsx")
def dpe_cost_engine_expense_import_template(
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    _require_dpe(scope)
    output = build_expense_import_template()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Modelo_Despesas_DPE.xlsx"'},
    )


@router.post("/api/dpe/cost-engine/periods/{period_id}/expense-imports/excel/preview")
async def dpe_cost_engine_preview_expense_excel(
    period_id: int,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    suffix = Path(arquivo.filename or "despesas.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(422, "Envie um arquivo .xlsx ou .xlsm.")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="dpe_cost_expenses_", suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(await arquivo.read())
        rows = parse_expense_workbook(temp_path)
        return _cost_expense_repo(db, scope).prepare_excel_import(period_id, arquivo.filename or "despesas.xlsx", rows)
    except Exception as exc:
        _translate_cost_expense(exc)
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


@router.post("/api/dpe/cost-engine/expense-imports/{batch_id}/commit")
def dpe_cost_engine_commit_expense_import(
    batch_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).commit_import_batch(batch_id)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.put("/api/dpe/cost-engine/periods/{period_id}/expenses/bulk-classify")
def dpe_cost_engine_bulk_classify_expenses(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_expense_repo(db, scope).bulk_classify(period_id, payload)
    except Exception as exc:
        _translate_cost_expense(exc)


@router.get("/api/dpe/cost-engine/teaching-central")
def dpe_cost_engine_teaching_central(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).central_payload(period_id=period_id)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.get("/api/dpe/cost-engine/teachers")
def dpe_cost_engine_teachers(
    active_only: bool = Query(False),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_teaching_repo(db, scope).list_teachers(active_only=active_only, search=q)}
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.post("/api/dpe/cost-engine/teachers")
def dpe_cost_engine_create_teacher(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).create_teacher(payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.put("/api/dpe/cost-engine/teachers/{teacher_id}")
def dpe_cost_engine_update_teacher(
    teacher_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).update_teacher(teacher_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.put("/api/dpe/cost-engine/period-teachers/{period_teacher_id}")
def dpe_cost_engine_update_period_teacher(
    period_teacher_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).update_period_teacher(period_teacher_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.post("/api/dpe/cost-engine/teachers/{teacher_id}/aliases")
def dpe_cost_engine_create_teacher_alias(
    teacher_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).create_alias(teacher_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.put("/api/dpe/cost-engine/teacher-aliases/{alias_id}")
def dpe_cost_engine_update_teacher_alias(
    alias_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).update_alias(alias_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.get("/api/dpe/cost-engine/subjects")
def dpe_cost_engine_subjects(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_teaching_repo(db, scope).list_subjects(active_only=active_only)}
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.post("/api/dpe/cost-engine/subjects")
def dpe_cost_engine_create_subject(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).create_subject(payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.put("/api/dpe/cost-engine/subjects/{subject_id}")
def dpe_cost_engine_update_subject(
    subject_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).update_subject(subject_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.get("/api/dpe/cost-engine/teaching-activities")
def dpe_cost_engine_teaching_activities(
    period_id: int = Query(...),
    teacher_id: int | None = Query(None),
    status: str | None = Query("ACTIVE"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_teaching_repo(db, scope).list_activities(period_id=period_id, teacher_id=teacher_id, status=status)}
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.post("/api/dpe/cost-engine/teaching-activities")
def dpe_cost_engine_create_teaching_activity(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).create_activity(payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.put("/api/dpe/cost-engine/teaching-activities/{activity_id}")
def dpe_cost_engine_update_teaching_activity(
    activity_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).update_activity(activity_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.post("/api/dpe/cost-engine/teaching-activities/{activity_id}/void")
def dpe_cost_engine_void_teaching_activity(
    activity_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).void_activity(activity_id, reason=str(payload.get("reason") or ""))
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.get("/api/dpe/cost-engine/payroll-reconciliation")
def dpe_cost_engine_payroll_reconciliation(
    period_id: int = Query(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_teaching_repo(db, scope).payroll_reconciliation(period_id)}
    except Exception as exc:
        _translate_cost_teaching(exc)


@router.put("/api/dpe/cost-engine/payroll-reconciliation/{expense_id}")
def dpe_cost_engine_link_payroll_expense(
    expense_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_teaching_repo(db, scope).link_payroll_expense(expense_id, payload)
    except Exception as exc:
        _translate_cost_teaching(exc)



@router.get("/api/dpe/revenues")
def dpe_revenues(period_id: int | None = Query(None), db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DPE"))):
    try: return _revenue_repo(db, scope).central(period_id)
    except Exception as exc: _translate_revenue(exc)

@router.put("/api/dpe/revenues/periods/{period_id}/courses")
def dpe_revenues_courses(period_id: int, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_edit("DPE"))):
    try: return _revenue_repo(db, scope).bulk_courses(period_id, payload.get("items") or [])
    except Exception as exc: _translate_revenue(exc)

@router.post("/api/dpe/revenues/periods/{period_id}/entries")
def dpe_revenue_entry_create(period_id: int, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_edit("DPE"))):
    try: return _revenue_repo(db, scope).create(period_id, payload)
    except Exception as exc: _translate_revenue(exc)

@router.delete("/api/dpe/revenues/entries/{entry_id}")
def dpe_revenue_entry_delete(entry_id: int, db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_edit("DPE"))):
    try: return _revenue_repo(db, scope).delete(entry_id)
    except Exception as exc: _translate_revenue(exc)

@router.post("/api/dpe/revenues/categories")
def dpe_revenue_category_create(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_edit("DPE"))):
    try: return _revenue_repo(db, scope).create_category(payload)
    except Exception as exc: _translate_revenue(exc)

@router.get("/api/dpe/cost-engine/economics-central")
def dpe_cost_engine_economics_central(
    period_id: int | None = Query(None),
    run_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_economics_repo(db, scope).central_payload(period_id=period_id, run_id=run_id)
    except Exception as exc:
        _translate_cost_economics(exc)


@router.put("/api/dpe/cost-engine/periods/{period_id}/offerings/{period_offering_id}/economics")
def dpe_cost_engine_upsert_offering_economics(
    period_id: int,
    period_offering_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_economics_repo(db, scope).upsert(period_id, period_offering_id, payload)
    except Exception as exc:
        _translate_cost_economics(exc)


@router.put("/api/dpe/cost-engine/periods/{period_id}/economics")
def dpe_cost_engine_bulk_upsert_economics(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    """Atomically save auxiliary active-student facts for multiple course contexts."""
    try:
        return _cost_economics_repo(db, scope).upsert_many(period_id, payload.get("items") or [])
    except Exception as exc:
        _translate_cost_economics(exc)


@router.get("/api/dpe/cost-engine/allocation-central")
def dpe_cost_engine_allocation_central(
    period_id: int | None = Query(None),
    run_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).central_payload(period_id=period_id, run_id=run_id)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/allocation-policies")
def dpe_cost_engine_allocation_policies(
    period_id: int | None = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_allocation_repo(db, scope).list_policies(active_only=active_only, period_id=period_id)}
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.post("/api/dpe/cost-engine/expenses/{expense_id}/allocation-policies")
def dpe_cost_engine_create_allocation_policy_from_expense(
    expense_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).create_policy_from_expense(expense_id, payload)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.put("/api/dpe/cost-engine/allocation-policies/{policy_id}")
def dpe_cost_engine_update_allocation_policy(
    policy_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).update_policy(policy_id, payload)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/expenses/{expense_id}/allocation-policies/{policy_id}/resolve")
def dpe_cost_engine_resolve_allocation_policy(
    expense_id: int,
    policy_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).resolve_policy_for_expense(expense_id, policy_id)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}/allocation-preview")
def dpe_cost_engine_month_allocation_preview(
    period_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).period_preview(period_id)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}/driver-values")
def dpe_cost_engine_driver_values(
    period_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_allocation_repo(db, scope).list_driver_values(period_id)}
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.put("/api/dpe/cost-engine/periods/{period_id}/driver-values")
def dpe_cost_engine_upsert_driver_values(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).upsert_driver_values(period_id, payload)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/expenses/{expense_id}/allocation-config")
def dpe_cost_engine_expense_allocation_config(
    expense_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).expense_config(expense_id)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.post("/api/dpe/cost-engine/expenses/{expense_id}/allocation-preview")
def dpe_cost_engine_preview_expense_allocation(
    expense_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).preview_expense_config(expense_id, payload)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.put("/api/dpe/cost-engine/expenses/{expense_id}/allocation-config")
def dpe_cost_engine_set_expense_allocation_config(
    expense_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).set_expense_config(expense_id, payload)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/allocation-runs")
def dpe_cost_engine_allocation_runs(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_allocation_repo(db, scope).list_runs(period_id=period_id)}
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.post("/api/dpe/cost-engine/allocation-runs")
def dpe_cost_engine_calculate_allocation(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).calculate(int(payload.get("period_id") or 0))
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/allocation-runs/{run_id}")
def dpe_cost_engine_allocation_run_detail(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).get_run(run_id)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.post("/api/dpe/cost-engine/allocation-runs/{run_id}/official")
def dpe_cost_engine_make_allocation_official(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_allocation_repo(db, scope).make_official(run_id)
    except Exception as exc:
        _translate_cost_allocation(exc)


def _translate_cost_productivity(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPECostProductivityValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro nao tratado em Produtividade DPE")
    raise HTTPException(500, "Ocorreu um erro interno nas ferramentas de produtividade da DPE.") from exc


@router.get("/api/dpe/cost-engine/productivity-central")
def dpe_cost_engine_productivity_central(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_productivity_repo(db, scope).central_payload(period_id)
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}/copy-preview")
def dpe_cost_engine_copy_preview(
    period_id: int,
    source_period_id: int = Query(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_productivity_repo(db, scope).copy_preview(source_period_id, period_id)
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/copy-previous")
def dpe_cost_engine_copy_previous(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        repo = _cost_productivity_repo(db, scope)
        source_id = int(payload.get("source_period_id") or 0)
        result: dict[str, Any] = {"source_period_id": source_id, "target_period_id": period_id}
        if payload.get("copy_revenues", True):
            result["revenues"] = repo.copy_revenues(source_id, period_id, overwrite=bool(payload.get("overwrite_revenues", False)))
        if payload.get("copy_teaching", True):
            result["teaching"] = repo.copy_teaching(source_id, period_id)
        return result
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.get("/api/dpe/cost-engine/recurring-expenses")
def dpe_cost_engine_recurring_expenses(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_productivity_repo(db, scope).list_recurring_templates(active_only=active_only)}
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.post("/api/dpe/cost-engine/recurring-expenses")
def dpe_cost_engine_create_recurring_expense(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_productivity_repo(db, scope).save_recurring_template(payload)
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.put("/api/dpe/cost-engine/recurring-expenses/{template_id}")
def dpe_cost_engine_update_recurring_expense(
    template_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_productivity_repo(db, scope).save_recurring_template(payload, template_id=template_id)
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/recurring-expenses/generate")
def dpe_cost_engine_generate_recurring_expenses(
    period_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        ids = payload.get("template_ids") if isinstance(payload.get("template_ids"), list) else None
        return _cost_productivity_repo(db, scope).generate_recurring(period_id, ids)
    except Exception as exc:
        _translate_cost_productivity(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/allocation-policies/bulk-preview")
def dpe_cost_engine_bulk_policy_preview(
    period_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        ids = payload.get("expense_ids") if isinstance(payload.get("expense_ids"), list) else None
        return _cost_allocation_repo(db, scope).bulk_policy_preview(period_id, ids)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/allocation-policies/bulk-apply")
def dpe_cost_engine_bulk_policy_apply(
    period_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        ids = payload.get("expense_ids") if isinstance(payload.get("expense_ids"), list) else None
        return _cost_allocation_repo(db, scope).bulk_apply_suggested_policies(period_id, ids)
    except Exception as exc:
        _translate_cost_allocation(exc)


@router.get("/api/dpe/cost-engine/closure-central")
def dpe_cost_engine_closure_central(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_closure_repo(db, scope).central_payload(period_id=period_id)
    except Exception as exc:
        _translate_cost_closure(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}/closure-checklist")
def dpe_cost_engine_closure_checklist(
    period_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_closure_repo(db, scope).checklist(period_id)
    except Exception as exc:
        _translate_cost_closure(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}/events")
def dpe_cost_engine_period_events(
    period_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_closure_repo(db, scope).list_events(period_id)}
    except Exception as exc:
        _translate_cost_closure(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/close")
def dpe_cost_engine_close_period(
    period_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_closure_repo(db, scope).close_period(period_id, payload)
    except Exception as exc:
        _translate_cost_closure(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/reopen")
def dpe_cost_engine_reopen_period(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_closure_repo(db, scope).reopen_period(period_id, payload)
    except Exception as exc:
        _translate_cost_closure(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/return-to-review")
def dpe_cost_engine_return_period_to_review(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_closure_repo(db, scope).return_to_review(period_id, payload)
    except Exception as exc:
        _translate_cost_closure(exc)


@router.post("/api/dpe/cost-engine/periods/{period_id}/governance-reviews")
def dpe_cost_engine_review_governance_warning(
    period_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _cost_closure_repo(db, scope).review_warning(period_id, payload)
    except Exception as exc:
        _translate_cost_closure(exc)


@router.get("/api/dpe/cost-engine/periods/{period_id}/audit")
def dpe_cost_engine_period_audit(
    period_id: int,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _cost_closure_repo(db, scope).audit_trail(period_id, limit=limit)}
    except Exception as exc:
        _translate_cost_closure(exc)


@router.get("/api/dpe/cost-engine/v2-overview")
def dpe_cost_engine_v2_overview(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_v2_repo(db, scope).overview(period_id=period_id)
    except Exception as exc:
        _translate(exc)


@router.get("/api/dpe/cost-engine/analytics")
def dpe_cost_engine_analytics(
    period_id: int | None = Query(None),
    window_months: int = Query(12, ge=1, le=36),
    course_key: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return _cost_analytics_repo(db, scope).dashboard(
            period_id=period_id,
            window_months=window_months,
            course_key=course_key,
        )
    except Exception as exc:
        _translate(exc)




@router.get("/api/dpe/management/overview")
def dpe_management_overview(
    period_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    """Evaluate DPE targets against canonical Cost Engine facts for one competence."""
    try:
        return _management_runtime_repo(db, scope).overview(period_id=period_id)
    except Exception as exc:
        _translate(exc)


@router.get("/api/dpe/courses")
def dpe_courses(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    """Catálogo institucional de cursos ativos de DTNH/DCS, sem restringir modalidade."""
    _require_dpe(scope)
    rows = db.execute(
        select(Course, Directorate)
        .join(Directorate, Directorate.id == Course.directorate_id)
        .where(
            Directorate.code.in_(("DTNH", "DCS")),
            Directorate.active.is_(True),
            Course.active.is_(True),
        )
        .order_by(Directorate.code, Course.name)
    ).all()
    items = [
        {
            "id": course.id,
            "name": course.name,
            "modality": course.modality,
            "valid_from": course.valid_from,
            "valid_to": course.valid_to,
            "directorate_code": directorate.code,
            "directorate_name": directorate.name,
            "persisted": True,
        }
        for course, directorate in rows
    ]
    # Banco novo/local pode ainda não ter o catálogo acadêmico persistido. Nesse
    # caso usamos o mesmo catálogo institucional já conhecido pela integração SEI.
    existing = {(item["directorate_code"], item["name"].casefold()) for item in items}
    for code, names, label in (
        ("DTNH", DTNH_COURSES, "Diretoria de Tecnologia, Negócios e Humanidades"),
        ("DCS", DCS_COURSES, "Diretoria de Ciências da Saúde"),
    ):
        for name in names:
            if (code, str(name).casefold()) not in existing:
                items.append({"id": None, "name": str(name), "modality": "Não informada", "valid_from": None, "valid_to": None, "directorate_code": code, "directorate_name": label, "persisted": False})
    items.sort(key=lambda item: (item["directorate_code"], item["name"]))
    return {
        "items": items,
        "operational_scope": "ALL_MODALITIES",
        "source_of_truth": "courses",
        "persisted_count": sum(1 for item in items if item.get("persisted")),
    }


@router.get("/api/dpe/excel")
def dpe_excel_full(
    period_id: int | None = Query(None),
    referencia: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    """Export the modern DPE workbook from the canonical Cost Engine facts.

    ``referencia`` is kept as a compatibility alias for older bookmarks. New
    clients should send ``period_id`` so the workbook matches the exact period
    selected in the DPE interface.
    """
    try:
        payload = DPEExcelExportRepository(db, _require_dpe(scope)).payload(
            period_id=period_id,
            reference=referencia,
        )
        selected = payload.get("selected_period")
        if not selected:
            raise HTTPException(404, "Cadastre uma competência antes de exportar o Excel da DPE.")
        engine = selected_dpe_excel_engine()
        output = export_dpe_excel(payload, generated_by=scope.user.email)
        period = str(selected.get("period") or "competencia").replace("/", "-")
        filename = "Excel_Oficial_DPE.xlsx" if engine == "excel_official" else f"DPE_{period}_analitico.xlsx"
        LOGGER.info(
            "Excel DPE gerado",
            extra={"directorate": "DPE", "excel_engine": engine, "generated_by": scope.user.email},
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Data-UNIVC-Excel-Engine": engine,
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/admin/excel-official/dpe/parity")
def dpe_excel_production_parity(
    period_id: int | None = Query(None),
    referencia: str | None = Query(None),
    db: Session = Depends(get_db),
    ctx: UserContext = Depends(require_fresh_reitoria),
):
    scope = resolve_directorate_scope(db, ctx, "DPE")
    try:
        payload = DPEExcelExportRepository(db, _require_dpe(scope)).payload(period_id=period_id, reference=referencia)
        if not payload.get("selected_period"):
            raise HTTPException(404, "Cadastre uma competência antes de auditar o Excel Oficial da DPE.")
        report = audit_dpe_cutover_readiness(
            payload,
            source_kind="production",
            generated_by=ctx.email,
            build_workbooks=True,
        )
        LOGGER.info(
            "Auditoria de paridade DPE concluída",
            extra={
                "directorate": "DPE",
                "cases": len(report.semantic_report.cases),
                "failures": len(report.failures),
                "cutover_status": report.cutover_status,
            },
        )
        return JSONResponse(
            content=report.to_dict(),
            headers={"Cache-Control": "no-store", "X-Data-UNIVC-Parity-Status": report.cutover_status},
        )
    except Exception as exc:
        _translate(exc)
