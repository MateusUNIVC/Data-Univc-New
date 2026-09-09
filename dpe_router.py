from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database import get_db
from release_info import APP_VERSION
from dpe_excel_builder import build_dpe_import_template, build_dpe_workbook
from dpe_excel_parser import DPEExcelImportError, parse_dpe_workbook
from dpe_finance_analytics import build_dpe_finance_dashboard
from dpe_finance_repository import DPEFinanceRepository, DPEFinanceValidationError
from management_catalog import ManagementCatalogError, indicator_spec
from management_repository import ManagementRepository
from models import Course, Directorate
from management_service import ManagementValidationError, validate_measurement_payload
from security import DirectorateScope, ensure_directorate_visible, require_directorate_access, require_directorate_edit
from academic_catalog import DTNH_COURSES, DCS_COURSES
from demo_data import dpe_data
from upload_utils import save_validated_excel_upload

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("univc.dpe")
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()


def _require_dpe(scope: DirectorateScope) -> DirectorateScope:
    if scope.directorate_code != "DPE":
        raise HTTPException(404, "Esta rota pertence exclusivamente à DPE.")
    return scope


def _repo(db: Session, scope: DirectorateScope) -> ManagementRepository:
    return ManagementRepository(db, _require_dpe(scope))


def _translate(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPEExcelImportError):
        raise HTTPException(422, {"erro": str(exc), "linhas": exc.errors, "importacao_parcial": False}) from exc
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
        context={"app_version": APP_VERSION},
        headers={"Cache-Control": "no-store"},
    )


def _finance_repo(db: Session, scope: DirectorateScope) -> DPEFinanceRepository:
    return DPEFinanceRepository(db, _require_dpe(scope))


def _translate_finance(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DPEFinanceValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado na base financeira DPE")
    raise HTTPException(500, "Ocorreu um erro interno na base financeira da DPE.") from exc


@router.get("/api/dpe/finance/dashboard")
def dpe_finance_dashboard(
    referencia: str | None = Query(None),
    janela: int | None = Query(12, ge=1, le=120),
    curso_id: int | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        repo = _finance_repo(db, scope)
        return build_dpe_finance_dashboard(
            repo.snapshot(reference=referencia, window_months=janela),
            reference=referencia,
            window_months=janela,
            course_id=curso_id,
        )
    except Exception as exc:
        _translate_finance(exc)


@router.get("/api/dpe/finance/revenues")
def dpe_finance_revenues(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        repo = _finance_repo(db, scope)
        return {"items": repo.list_monthly_revenues()}
    except Exception as exc:
        _translate_finance(exc)


@router.put("/api/dpe/finance/revenues")
def dpe_finance_upsert_revenue(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _finance_repo(db, scope).upsert_monthly_revenue(payload)
    except Exception as exc:
        _translate_finance(exc)


@router.get("/api/dpe/finance/course-revenues")
def dpe_finance_course_revenues(
    periodo: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _finance_repo(db, scope).list_course_revenues(period=periodo)}
    except Exception as exc:
        _translate_finance(exc)


@router.put("/api/dpe/finance/course-revenues")
def dpe_finance_upsert_course_revenue(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _finance_repo(db, scope).upsert_course_revenue(payload)
    except Exception as exc:
        _translate_finance(exc)


@router.delete("/api/dpe/finance/course-revenues/{row_id}")
def dpe_finance_delete_course_revenue(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        _finance_repo(db, scope).delete_course_revenue(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate_finance(exc)


@router.get("/api/dpe/finance/expenses")
def dpe_finance_expenses(
    periodo: str | None = Query(None),
    tipo: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _finance_repo(db, scope).list_expenses(period=periodo, kind=tipo)}
    except Exception as exc:
        _translate_finance(exc)


@router.post("/api/dpe/finance/expenses")
def dpe_finance_create_expense(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _finance_repo(db, scope).create_expense(payload)
    except Exception as exc:
        _translate_finance(exc)


@router.put("/api/dpe/finance/expenses/{row_id}")
def dpe_finance_update_expense(
    row_id: int,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _finance_repo(db, scope).update_expense(row_id, payload)
    except Exception as exc:
        _translate_finance(exc)


@router.delete("/api/dpe/finance/expenses/{row_id}")
def dpe_finance_delete_expense(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        _finance_repo(db, scope).delete_expense(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate_finance(exc)


@router.get("/api/dpe/finance/course-costs")
def dpe_finance_course_costs(
    periodo: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        return {"items": _finance_repo(db, scope).list_course_costs(period=periodo)}
    except Exception as exc:
        _translate_finance(exc)


@router.put("/api/dpe/finance/course-costs")
def dpe_finance_upsert_course_cost(
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        return _finance_repo(db, scope).upsert_course_cost(payload)
    except Exception as exc:
        _translate_finance(exc)


@router.delete("/api/dpe/finance/course-costs/{row_id}")
def dpe_finance_delete_course_cost(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    try:
        _finance_repo(db, scope).delete_course_cost(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate_finance(exc)




@router.post("/api/dpe/finance/demo")
def dpe_finance_demo(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    """Populate only the v0.7.7 financial foundation for homologation."""
    try:
        repo = _finance_repo(db, scope)
        if repo.list_monthly_revenues() or repo.list_expenses() or repo.list_course_revenues() or repo.list_course_costs():
            raise HTTPException(409, "A demonstração financeira só pode ser criada enquanto a nova base financeira estiver vazia.")
        from demo_seed import seed_dpe_finance_demo

        result = seed_dpe_finance_demo(db)
        return {
            **result,
            "mensagem": "Demonstração da base financeira v0.7.7 criada sem alterar o histórico legado da DPE.",
        }
    except Exception as exc:
        _translate_finance(exc)


@router.get("/api/dpe/courses")
def dpe_courses(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    """Catálogo institucional de cursos ativos já cadastrados em DTNH/DCS."""
    _require_dpe(scope)
    rows = db.execute(
        select(Course, Directorate)
        .join(Directorate, Directorate.id == Course.directorate_id)
        .where(Directorate.code.in_(("DTNH", "DCS")), Course.active.is_(True))
        .order_by(Directorate.code, Course.name)
    ).all()
    items = [
        {"id": course.id, "name": course.name, "directorate_code": directorate.code, "directorate_name": directorate.name}
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
                items.append({"id": None, "name": str(name), "directorate_code": code, "directorate_name": label})
    items.sort(key=lambda item: (item["directorate_code"], item["name"]))
    return {"items": items}


@router.post("/api/dpe/demo")
def dpe_demo(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    """Populate a deterministic homologation base only when DPE has no measurements."""
    try:
        repo = _repo(db, scope)
        if repo.all_measurements():
            raise HTTPException(409, "A demonstração só pode ser criada enquanto a base de medições da DPE estiver vazia.")
        measurements, _, _ = dpe_data()
        result = repo.bulk_upsert_measurements(measurements)
        from demo_seed import seed_dpe_finance_demo
        finance = seed_dpe_finance_demo(db)
        return {
            **result,
            "finance": finance,
            "mensagem": "Base demonstrativa da DPE criada, incluindo a nova fundação financeira. Nenhum dado real foi substituído.",
        }
    except Exception as exc:
        _translate(exc)

@router.get("/api/dpe/excel")
def dpe_excel_full(
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        repo = _repo(db, scope)
        output = build_dpe_workbook(
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
                "Content-Disposition": 'attachment; filename="Painel_DPE_completo.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dpe/excel/{indicator_code}")
def dpe_excel_indicator(
    indicator_code: str,
    referencia: str | None = Query(None),
    comparacao: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        code = indicator_spec("DPE", indicator_code)["code"]
        repo = _repo(db, scope)
        measurements = [row for row in repo.all_measurements() if row.get("indicator_code") == code]
        targets = repo.list_targets(indicator_code=code)
        actions = repo.list_actions(indicator_code=code)
        output = build_dpe_workbook(
            measurements,
            targets,
            actions,
            reference=referencia,
            comparison=comparacao,
            only_indicator=code,
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="Painel_{code}_DPE.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dpe/modelo/{indicator_code}")
def dpe_excel_template(
    indicator_code: str,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DPE")),
):
    try:
        code = indicator_spec("DPE", indicator_code)["code"]
        _require_dpe(scope)
        output = build_dpe_import_template(code)
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


@router.post("/api/dpe/import")
async def dpe_excel_import(
    arquivo: UploadFile = File(...),
    indicador: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DPE")),
):
    temp_path: Path | None = None
    try:
        _require_dpe(scope)
        code = indicator_spec("DPE", indicador)["code"] if indicador else None
        suffix = Path(arquivo.filename or "importacao.xlsx").suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            raise HTTPException(400, "Envie uma planilha XLSX ou XLSM.")
        with tempfile.NamedTemporaryFile(prefix="dpe_import_", suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
        await save_validated_excel_upload(arquivo, temp_path)
        parsed = parse_dpe_workbook(temp_path, indicator_code=code)

        clean_payloads: list[dict[str, Any]] = []
        validation_errors: list[dict[str, Any]] = []
        for payload in parsed["payloads"]:
            source = payload.pop("_source", {})
            try:
                if payload.get("indicator_code") == "DPE-01":
                    dims = dict(payload.get("dimensions") or {})
                    course_name = str(dims.get("course") or "").strip()
                    if course_name:
                        match = db.execute(
                            select(Course, Directorate)
                            .join(Directorate, Directorate.id == Course.directorate_id)
                            .where(
                                Directorate.code.in_(("DTNH", "DCS")),
                                Course.active.is_(True),
                                func.lower(Course.name) == course_name.lower(),
                            )
                        ).first()
                        if match:
                            dims["academic_directorate"] = match[1].code
                        elif not dims.get("academic_directorate"):
                            for dcode, names in (("DTNH", DTNH_COURSES), ("DCS", DCS_COURSES)):
                                if any(str(name).casefold() == course_name.casefold() for name in names):
                                    dims["academic_directorate"] = dcode
                                    break
                    payload["dimensions"] = dims
                clean_payloads.append(validate_measurement_payload("DPE", payload))
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
            raise DPEExcelImportError(
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
