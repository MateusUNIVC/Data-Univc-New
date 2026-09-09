from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from dadm_excel_builder import build_dadm_import_template, build_dadm_workbook
from dadm_excel_parser import DADMExcelImportError, parse_dadm_workbook
from database import get_db
from auth.data_scopes import dadm_has_full_data_access
from release_info import APP_VERSION
from management_catalog import ManagementCatalogError, catalog_payload, indicator_spec
from management_repository import ManagementRepository
from management_service import ManagementValidationError, build_management_dashboard, validate_measurement_payload
from demo_data import dadm_data
from security import DirectorateScope, require_directorate_access, require_directorate_edit
from upload_utils import save_validated_excel_upload

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("univc.dadm")
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()


def _require_dadm(scope: DirectorateScope) -> DirectorateScope:
    if scope.directorate_code != "DADM":
        raise HTTPException(404, "Esta rota pertence exclusivamente à Diretoria Administrativa.")
    return scope


def _repo(db: Session, scope: DirectorateScope) -> ManagementRepository:
    _require_dadm(scope)
    if not dadm_has_full_data_access(scope.user.email, global_access=scope.user.global_access):
        raise PermissionError("As ferramentas legadas da DADM exigem acesso completo aos dados da diretoria.")
    return ManagementRepository(db, scope)


def _translate(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DADMExcelImportError):
        raise HTTPException(
            422,
            {"erro": str(exc), "linhas": exc.errors, "importacao_parcial": False},
        ) from exc
    if isinstance(exc, (ManagementValidationError, ManagementCatalogError)):
        detail: dict[str, Any] = {"erro": str(exc)}
        if isinstance(exc, ManagementValidationError) and exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado no módulo DADM")
    raise HTTPException(500, "Ocorreu um erro interno no módulo da DADM.") from exc


@router.get("/dadm/legacy", response_class=HTMLResponse)
def dadm_legacy_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dadm.html",
        context={"app_version": APP_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/dadm/catalog")
def dadm_catalog(scope: DirectorateScope = Depends(require_directorate_access("DADM"))):
    try:
        _require_dadm(scope)
        return catalog_payload("DADM")
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/dashboard")
def dadm_dashboard(
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    indicador: str | None = Query(None),
    janela: int | None = Query(12, ge=1, le=240),
    dimensions: str | None = Query(None, description="JSON com filtros dimensionais"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        import json

        repo = _repo(db, scope)
        dimension_filters = None
        if dimensions:
            parsed = json.loads(dimensions)
            if not isinstance(parsed, dict):
                raise ManagementValidationError("O filtro de dimensões precisa ser um objeto JSON.")
            dimension_filters = {str(k): str(v) for k, v in parsed.items() if str(v).strip()}
        return build_management_dashboard(
            "DADM",
            repo.dashboard_measurements(reference=referencia, comparison=comparacao, window=janela),
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


@router.get("/api/dadm/measurements")
def dadm_measurements(
    indicador: str | None = Query(None),
    periodo: str | None = Query(None),
    dimensao: str | None = Query(None),
    busca: str | None = Query(None),
    validado: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
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


@router.post("/api/dadm/measurements")
async def dadm_measurement_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return _repo(db, scope).upsert_measurement(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dadm/measurements/{row_id}")
async def dadm_measurement_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return _repo(db, scope).update_measurement(row_id, await request.json())
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dadm/measurements/{row_id}")
def dadm_measurement_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        _repo(db, scope).delete_measurement(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/targets")
def dadm_targets(
    indicador: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        return {"items": _repo(db, scope).list_targets(indicator_code=indicador)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dadm/targets")
async def dadm_target_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return _repo(db, scope).save_target(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dadm/targets/{row_id}")
async def dadm_target_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return _repo(db, scope).save_target(await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dadm/targets/{row_id}")
def dadm_target_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        _repo(db, scope).delete_target(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/actions")
def dadm_actions(
    indicador: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        return {"items": _repo(db, scope).list_actions(indicator_code=indicador, status=status)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dadm/actions")
async def dadm_action_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return _repo(db, scope).save_action(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dadm/actions/{row_id}")
async def dadm_action_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        return _repo(db, scope).save_action(await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dadm/actions/{row_id}")
def dadm_action_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    try:
        _require_dadm(scope)
        _repo(db, scope).delete_action(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dadm/demo")
def dadm_demo(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    """Populate a deterministic DADM homologation base only when it is empty."""
    try:
        repo = _repo(db, scope)
        if repo.all_measurements():
            raise HTTPException(409, "A demonstração só pode ser criada enquanto a base de medições da DADM estiver vazia.")
        measurements, targets, actions = dadm_data()
        result = repo.bulk_upsert_measurements(measurements)
        for target in targets:
            repo.save_target(target)
        for action in actions:
            repo.save_action(action)
        return {
            **result,
            "targets": len(targets),
            "actions": len(actions),
            "mensagem": "Base demonstrativa DADM criada com os indicadores DADM-01 e DADM-02. Nenhum dado real foi substituído.",
        }
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/excel")
def dadm_excel_full(
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        repo = _repo(db, scope)
        output = build_dadm_workbook(
            repo.all_measurements(),
            repo.list_targets(),
            repo.list_actions(),
            reference=referencia,
            comparison=comparacao,
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="Painel_DADM_completo.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/excel/{indicator_code}")
def dadm_excel_indicator(
    indicator_code: str,
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        code = indicator_spec("DADM", indicator_code)["code"]
        repo = _repo(db, scope)
        output = build_dadm_workbook(
            repo.all_measurements(),
            repo.list_targets(indicator_code=code),
            repo.list_actions(indicator_code=code),
            reference=referencia,
            comparison=comparacao,
            only_indicator=code,
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="Painel_{code}_DADM.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dadm/modelo/{indicator_code}")
def dadm_excel_template(
    indicator_code: str,
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    try:
        _require_dadm(scope)
        code = indicator_spec("DADM", indicator_code)["code"]
        output = build_dadm_import_template(code)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="Modelo_importacao_{code}.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.post("/api/dadm/import")
async def dadm_excel_import(
    arquivo: UploadFile = File(...),
    indicador: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    temp_path: Path | None = None
    try:
        _require_dadm(scope)
        code = indicator_spec("DADM", indicador)["code"] if indicador else None
        suffix = Path(arquivo.filename or "importacao.xlsx").suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            raise HTTPException(400, "Envie uma planilha XLSX ou XLSM.")
        with tempfile.NamedTemporaryFile(prefix="dadm_import_", suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
        await save_validated_excel_upload(arquivo, temp_path)
        parsed = parse_dadm_workbook(temp_path, indicator_code=code)

        clean_payloads: list[dict[str, Any]] = []
        validation_errors: list[dict[str, Any]] = []
        for payload in parsed["payloads"]:
            source = payload.pop("_source", {})
            try:
                clean_payloads.append(validate_measurement_payload("DADM", payload))
            except ManagementValidationError as exc:
                if exc.field_errors:
                    for field, message in exc.field_errors.items():
                        validation_errors.append({
                            "sheet": source.get("sheet"),
                            "row": source.get("row"),
                            "field": field,
                            "error": message,
                        })
                else:
                    validation_errors.append({
                        "sheet": source.get("sheet"),
                        "row": source.get("row"),
                        "field": None,
                        "error": str(exc),
                    })
        if validation_errors:
            raise DADMExcelImportError(
                f"A importação possui {len(validation_errors)} inconsistência(s). Nenhuma linha foi gravada.",
                validation_errors,
            )
        result = _repo(db, scope).bulk_upsert_measurements(clean_payloads)
        return {
            **result,
            "abas": parsed["sheets"],
            "mensagem": f"Importação concluída: {result['created']} novo(s) e {result['updated']} atualizado(s).",
            "importacao_parcial": False,
        }
    except Exception as exc:
        _translate(exc)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
