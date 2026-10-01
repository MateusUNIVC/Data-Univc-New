from __future__ import annotations

import logging
from copy import deepcopy
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy import delete
from sqlalchemy.orm import Session

from database import get_db
from release_info import APP_VERSION
from dm_analytics import build_dm_dashboard
from dm_catalog import DM_AREAS, DMValidationError
from dm_demo import cohort_import_payloads, student_import_payloads
from dm_excel_builder import build_dm_import_template
from dm_excel_v2_builder import build_dm_v2_workbook
from dm_excel_v3_builder import build_dm_interactive_workbook_bytes
from dm_excel_parser import DMExcelImportError, parse_dm_cohorts_workbook, parse_dm_students_workbook
from dm_repository import DMRepository
from management_catalog import ManagementCatalogError, catalog_payload
from management_repository import ManagementRepository
from management_service import ManagementValidationError
from dm_sei_parser import DMSEIParseError, normalize_dm_sei_payload, parse_dm_sei_workbook
from models import DmCohort, DmStudent
from sei_stricto import download_stricto_integral_report
from sei_student_dates import SEIStudentDatesError, lookup_student_course_dates
from security import DirectorateScope, require_directorate_access, require_directorate_edit
from upload_utils import save_validated_excel_upload

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("univc.dm")
templates = Jinja2Templates(directory=ROOT / "templates")
router = APIRouter()

DM_TARGET_METRICS = {
    ("DM-01", "cohort_members"),
    ("DM-02", "average_months_to_defense"),
}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


DM_SEI_REFRESH_BATCH_SIZE = _env_int("DM_SEI_REFRESH_BATCH_SIZE", 4, minimum=1, maximum=10)
DM_SEI_REFRESH_BATCH_BUDGET_SECONDS = _env_int(
    "DM_SEI_REFRESH_BATCH_BUDGET_SECONDS", 30, minimum=10, maximum=50
)
DM_SEI_REFRESH_REQUEST_TIMEOUT_SECONDS = _env_int(
    "DM_SEI_REFRESH_REQUEST_TIMEOUT_SECONDS", 15, minimum=5, maximum=30
)
DM_ASSET_VERSION = f"{APP_VERSION}-dmq04"


def _dm_refresh_scope(payload: dict[str, Any]) -> dict[str, Any]:
    cohort_id = payload.get("cohort_id")
    raw_cohort_ids = payload.get("cohort_ids") or []
    raw_student_ids = payload.get("student_ids") or []
    return {
        "cohort_id": int(cohort_id) if cohort_id not in (None, "") else None,
        "cohort_ids": [int(value) for value in raw_cohort_ids if str(value or "").strip()],
        "student_ids": [int(value) for value in raw_student_ids if str(value or "").strip()],
        "all_cohorts": bool(payload.get("all_cohorts", False)),
    }


def _is_dm_target(indicator_code: str, metric_key: str) -> bool:
    return (str(indicator_code or "").upper(), str(metric_key or "")) in DM_TARGET_METRICS


def _dm_target_catalog_payload() -> dict[str, Any]:
    payload = deepcopy(catalog_payload("DM"))
    dm = payload["directorates"]["DM"]
    for indicator in dm.get("indicators") or []:
        indicator["metrics"] = [
            metric for metric in (indicator.get("metrics") or [])
            if _is_dm_target(indicator.get("code"), metric.get("key"))
        ]
    dm["indicators"] = [indicator for indicator in dm.get("indicators") or [] if indicator.get("metrics")]
    return payload


def _normalize_dm_target_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    code = str(normalized.get("indicator_code") or "").strip().upper()
    metric = str(normalized.get("metric_key") or "").strip()
    if not _is_dm_target(code, metric):
        raise ManagementValidationError(
            "A Diretoria de Mestrado possui somente as metas de membros por turma e tempo médio até a defesa."
        )
    normalized["indicator_code"] = code
    normalized["metric_key"] = metric
    # A DM v0.8.2 usa uma única meta por métrica, sem faixa de atenção paralela.
    for field in ("attention", "target_min", "target_max", "attention_min", "attention_max"):
        normalized[field] = None
    normalized["dimensions"] = {}
    return normalized


def _visible_dm_targets(repo: ManagementRepository, *, indicator_code: str | None = None) -> list[dict[str, Any]]:
    return [
        row for row in repo.list_targets(indicator_code=indicator_code)
        if _is_dm_target(row.get("indicator_code"), row.get("metric_key"))
    ]


def _visible_dm_actions(repo: ManagementRepository) -> list[dict[str, Any]]:
    rows = []
    for row in repo.list_actions():
        code = str(row.get("indicator_code") or "").upper()
        metric = str(row.get("metric_key") or "")
        if code not in {"DM-01", "DM-02"}:
            continue
        if metric and not _is_dm_target(code, metric):
            continue
        rows.append(row)
    return rows


def _require_dm(scope: DirectorateScope) -> DirectorateScope:
    if scope.directorate_code != "DM":
        raise HTTPException(404, "Esta rota pertence exclusivamente à Diretoria de Mestrado.")
    return scope


def _repo(db: Session, scope: DirectorateScope) -> DMRepository:
    return DMRepository(db, _require_dm(scope))


def _translate(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, DMExcelImportError):
        raise HTTPException(
            422,
            {"erro": str(exc), "linhas": exc.errors, "importacao_parcial": False},
        ) from exc
    if isinstance(exc, SEIStudentDatesError):
        raise HTTPException(502, {"erro": str(exc), "origem": "SEI"}) from exc
    if isinstance(exc, DMSEIParseError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.details:
            detail["detalhes"] = exc.details
        raise HTTPException(422, detail) from exc
    if isinstance(exc, (ManagementValidationError, ManagementCatalogError)):
        detail: dict[str, Any] = {"erro": str(exc)}
        if isinstance(exc, ManagementValidationError) and exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    if isinstance(exc, DMValidationError):
        detail: dict[str, Any] = {"erro": str(exc)}
        if exc.field_errors:
            detail["campos"] = exc.field_errors
        raise HTTPException(422, detail) from exc
    LOGGER.exception("Erro não tratado no módulo DM")
    raise HTTPException(500, "Ocorreu um erro interno no módulo da Diretoria de Mestrado.") from exc


@router.get("/dm", response_class=HTMLResponse)
def dm_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dm.html",
        context={"app_version": DM_ASSET_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/dm/sei")
def dm_sei_page():
    return RedirectResponse(url="/dm?view=sei", status_code=307)


@router.get("/api/dm/areas")
def dm_areas(scope: DirectorateScope = Depends(require_directorate_access("DM"))):
    _require_dm(scope)
    return {
        "areas": [{"codigo": code, "nome": name} for code, name in DM_AREAS.items()],
        "unidade_analise": "turma",
        "periodicidade": "por_turma",
    }


@router.get("/api/dm/dashboard")
def dm_dashboard(
    area: str | None = Query(None),
    turma_id: int | None = Query(None),
    data_corte: date | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        repo = _repo(db, scope)
        targets = ManagementRepository(db, _require_dm(scope)).list_targets()
        return build_dm_dashboard(
            repo.all_cohorts(),
            repo.all_students(),
            area_code=area,
            cohort_id=turma_id,
            as_of=data_corte,
            targets=targets,
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/target-catalog")
def dm_target_catalog(scope: DirectorateScope = Depends(require_directorate_access("DM"))):
    try:
        _require_dm(scope)
        return _dm_target_catalog_payload()
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/targets")
def dm_targets(
    indicador: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        repo = ManagementRepository(db, _require_dm(scope))
        return {"items": _visible_dm_targets(repo, indicator_code=indicador)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/targets")
async def dm_target_create(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        payload = _normalize_dm_target_payload(await request.json())
        return ManagementRepository(db, _require_dm(scope)).save_target(payload)
    except Exception as exc:
        _translate(exc)


@router.put("/api/dm/targets/{row_id}")
async def dm_target_update(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        payload = _normalize_dm_target_payload(await request.json())
        repo = ManagementRepository(db, _require_dm(scope))
        if not any(int(row["id"]) == int(row_id) for row in _visible_dm_targets(repo)):
            raise LookupError("Meta da DM não encontrada.")
        return repo.save_target(payload, row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dm/targets/{row_id}")
def dm_target_delete(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        repo = ManagementRepository(db, _require_dm(scope))
        if not any(int(row["id"]) == int(row_id) for row in _visible_dm_targets(repo)):
            raise LookupError("Meta da DM não encontrada.")
        repo.delete_target(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/cohorts")
def list_cohorts(
    area: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return {"items": _repo(db, scope).list_cohorts(area_code=area, status=status)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/cohorts")
async def create_cohort(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return _repo(db, scope).save_cohort(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dm/cohorts/{row_id}")
async def update_cohort(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return _repo(db, scope).save_cohort(await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dm/cohorts/{row_id}")
def delete_cohort(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        _repo(db, scope).delete_cohort(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/students")
def list_students(
    area: str | None = Query(None),
    turma_id: int | None = Query(None),
    status: str | None = Query(None),
    documento: str | None = Query(None),
    busca: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return _repo(db, scope).list_students(
            area_code=area,
            cohort_id=turma_id,
            status=status,
            document_status=documento,
            search=busca,
            offset=offset,
            limit=limit,
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/students/ids")
def list_student_ids(
    area: str | None = Query(None),
    turma_id: int | None = Query(None),
    status: str | None = Query(None),
    documento: str | None = Query(None),
    busca: str | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return _repo(db, scope).list_student_ids(
            area_code=area, cohort_id=turma_id, status=status,
            document_status=documento, search=busca,
        )
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/graduation/preview")
async def preview_graduation(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return _repo(db, scope).preview_graduation(await request.json())
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/graduation/commit")
async def commit_graduation(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return _repo(db, scope).apply_graduation(await request.json())
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/students")
async def create_student(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return _repo(db, scope).save_student(await request.json())
    except Exception as exc:
        _translate(exc)


@router.put("/api/dm/students/{row_id}")
async def update_student(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return _repo(db, scope).save_student(await request.json(), row_id=row_id)
    except Exception as exc:
        _translate(exc)


@router.delete("/api/dm/students/{row_id}")
def delete_student(
    row_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        _repo(db, scope).delete_student(row_id)
        return {"ok": True}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/excel")
def dm_excel(
    area: str | None = Query(None),
    turma_id: int | None = Query(None),
    data_corte: date | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        repo = _repo(db, scope)
        management = ManagementRepository(db, _require_dm(scope))
        output = build_dm_v2_workbook(
            repo.all_cohorts(),
            repo.all_students(),
            targets=_visible_dm_targets(management),
            sync_runs=repo.list_sei_sync_runs(limit=50),
            area_code=area,
            cohort_id=turma_id,
            as_of=data_corte,
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="Relatorio_DM.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/excel-interativo")
def dm_interactive_excel(
    area: str | None = Query(None),
    turma_id: int | None = Query(None),
    data_corte: date | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        repo = _repo(db, scope)
        management = ManagementRepository(db, _require_dm(scope))
        output = build_dm_interactive_workbook_bytes(
            repo.all_cohorts(),
            repo.all_students(),
            targets=_visible_dm_targets(management),
            actions=_visible_dm_actions(management),
            sync_runs=repo.list_sei_sync_runs(limit=100),
            area_code=area,
            cohort_id=turma_id,
            as_of=data_corte,
        )
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="Painel_DM_Interativo_beta.xlsx"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/modelo/{kind}")
def dm_import_model(kind: str, scope: DirectorateScope = Depends(require_directorate_access("DM"))):
    try:
        _require_dm(scope)
        normalized = str(kind).strip().lower()
        output = build_dm_import_template(normalized)
        filename = "Modelo_DM_Turmas.xlsx" if normalized == "turmas" else "Modelo_DM_Alunos.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
        )
    except Exception as exc:
        _translate(exc)


async def _save_upload(arquivo: UploadFile, prefix: str) -> Path:
    suffix = Path(arquivo.filename or "importacao.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(400, "Envie uma planilha XLSX ou XLSM.")
    handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False)
    handle.close()
    path = Path(handle.name)
    await save_validated_excel_upload(arquivo, path)
    return path


@router.post("/api/dm/import/turmas")
async def import_cohorts(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    path: Path | None = None
    try:
        _require_dm(scope)
        path = await _save_upload(arquivo, "dm_turmas_")
        payloads = parse_dm_cohorts_workbook(path)
        result = _repo(db, scope).bulk_upsert_cohorts(payloads)
        return {**result, "mensagem": "Importação de turmas concluída.", "importacao_parcial": False}
    except Exception as exc:
        _translate(exc)
    finally:
        if path:
            path.unlink(missing_ok=True)


@router.post("/api/dm/import/alunos")
async def import_students(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    path: Path | None = None
    try:
        _require_dm(scope)
        path = await _save_upload(arquivo, "dm_alunos_")
        payloads = parse_dm_students_workbook(path)
        result = _repo(db, scope).bulk_upsert_students(payloads)
        return {**result, "mensagem": "Importação de alunos concluída.", "importacao_parcial": False}
    except Exception as exc:
        _translate(exc)
    finally:
        if path:
            path.unlink(missing_ok=True)


@router.get("/api/dm/quality")
def dm_quality(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    """Return non-sensitive data-quality counters used by the DM interface."""
    try:
        return _repo(db, scope).data_quality_summary()
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/sei/history")
def dm_sei_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return {"items": _repo(db, scope).list_sei_sync_runs(limit=limit)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/preview-file")
async def dm_sei_preview_file(
    arquivo: UploadFile = File(...),
    excluir_turmas_teste: bool = Query(True),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Parse an integral SEI roster uploaded by an authorized DM editor.

    No database row is changed during preview. The temporary workbook is removed
    immediately after parsing.
    """

    path: Path | None = None
    try:
        _require_dm(scope)
        path = await _save_upload(arquivo, "dm_sei_integral_")
        report = await run_in_threadpool(parse_dm_sei_workbook, path)
        return _repo(db, scope).preview_sei_report(
            report,
            exclude_test=bool(excluir_turmas_teste),
        )
    except Exception as exc:
        _translate(exc)
    finally:
        if path:
            path.unlink(missing_ok=True)


@router.post("/api/dm/sei/preview")
async def dm_sei_preview_direct(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Download and preview the integral Stricto Sensu roster directly from SEI.

    The submitted SEI credentials exist only in local variables for the duration
    of this request. They are not written to the database, audit log or temporary
    files. The XLSX downloaded from SEI is parsed in an isolated temporary folder
    and deleted before this endpoint returns.
    """

    try:
        _require_dm(scope)
        payload = await request.json()
        username = str(payload.get("usuario") or "").strip()
        password = str(payload.get("senha") or "")
        technical_year = str(payload.get("ano_tecnico") or date.today().year).strip()
        exclude_test = bool(payload.get("excluir_turmas_teste", True))
        if not username or not password:
            raise HTTPException(422, {"erro": "Informe o usuário e a senha do SEI."})
        if not (technical_year.isdigit() and len(technical_year) == 4):
            raise HTTPException(422, {"erro": "O ano técnico deve possuir quatro dígitos."})

        # Debug is opt-in and remains disabled by default because legacy pages may
        # contain operational information. Even in debug mode, credentials are not
        # included in response files produced by the bot.
        debug_enabled = os.getenv("SEI_DM_DEBUG", "false").strip().lower() == "true"
        with tempfile.TemporaryDirectory(prefix="data_univc_dm_sei_") as temp_dir:
            temp_root = Path(temp_dir)
            destination = temp_root / "stricto_sensu_integral.xlsx"
            debug_dir = temp_root / "debug" if debug_enabled else None
            try:
                await run_in_threadpool(
                    download_stricto_integral_report,
                    username,
                    password,
                    destination,
                    year=technical_year,
                    debug_dir=debug_dir,
                )
            except HTTPException:
                raise
            except Exception as exc:
                LOGGER.warning("Falha operacional ao consultar o SEI para o DM: %s", type(exc).__name__)
                raise HTTPException(
                    502,
                    {
                        "erro": (
                            "Não foi possível gerar o relatório integral do Mestrado no SEI. "
                            "Confira as credenciais e tente novamente; como alternativa, envie o XLSX gerado pelo próprio SEI."
                        )
                    },
                ) from exc
            report = await run_in_threadpool(parse_dm_sei_workbook, destination)

        preview = _repo(db, scope).preview_sei_report(report, exclude_test=exclude_test)
        preview["source_type"] = "sei_direto"
        preview["technical_year"] = technical_year
        preview["credentials_persisted"] = False
        return preview
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/refresh-students")
async def dm_sei_refresh_students(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Refresh real entry/defense dates for one cohort, selected students, or all cohorts."""

    try:
        _require_dm(scope)
        payload = await request.json()
        username = str(payload.get("usuario") or "").strip()
        password = str(payload.get("senha") or "")
        if not username or not password:
            raise DMValidationError("Informe usuário e senha do SEI para atualizar início e defesa dos alunos.")

        scope_payload = _dm_refresh_scope(payload)

        repo = _repo(db, scope)
        targets = repo.students_for_sei_dates(
            cohort_id=scope_payload["cohort_id"],
            cohort_ids=scope_payload["cohort_ids"] or None,
            student_ids=scope_payload["student_ids"] or None,
            all_cohorts=scope_payload["all_cohorts"],
        )
        if len(targets) > DM_SEI_REFRESH_BATCH_SIZE:
            raise HTTPException(
                409,
                {
                    "erro": (
                        "A atualização em massa agora usa a fila segura do DM. "
                        "Atualize a página e inicie novamente a consulta pelo SEI."
                    ),
                    "fila_obrigatoria": True,
                    "selecionados": len(targets),
                    "limite_endpoint_legado": DM_SEI_REFRESH_BATCH_SIZE,
                },
            )
        lookup = await run_in_threadpool(
            lookup_student_course_dates,
            username,
            password,
            targets,
            max_seconds=DM_SEI_REFRESH_BATCH_BUDGET_SECONDS,
            request_timeout_seconds=DM_SEI_REFRESH_REQUEST_TIMEOUT_SECONDS,
        )
        result = repo.apply_sei_course_dates(lookup, source_type="sei_atualizacao_defesas")
        result["scope"] = scope_payload
        result["legacy_endpoint"] = True
        return result
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/refresh-runs")
async def dm_sei_create_refresh_run(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Create a persistent credential-free queue for individual SEI lookups."""

    try:
        _require_dm(scope)
        payload = await request.json()
        selection = _dm_refresh_scope(payload)
        run = _repo(db, scope).create_sei_student_refresh_run(
            cohort_id=selection["cohort_id"],
            cohort_ids=selection["cohort_ids"] or None,
            student_ids=selection["student_ids"] or None,
            all_cohorts=selection["all_cohorts"],
        )
        return {
            "ok": True,
            "run": run,
            "batch_size": DM_SEI_REFRESH_BATCH_SIZE,
            "credentials_persisted": False,
        }
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/sei/refresh-runs")
def dm_sei_refresh_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return {"ok": True, "runs": _repo(db, scope).list_sei_student_refresh_runs(limit=limit)}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/sei/refresh-runs/{run_id}")
def dm_sei_refresh_run_status(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return {"ok": True, "run": _repo(db, scope).get_sei_student_refresh_run(run_id)}
    except Exception as exc:
        _translate(exc)


@router.get("/api/dm/sei/refresh-runs/{run_id}/items")
def dm_sei_refresh_run_items(
    run_id: int,
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DM")),
):
    try:
        return {
            "ok": True,
            "items": _repo(db, scope).list_sei_student_refresh_items(run_id, status=status, limit=limit),
        }
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/refresh-runs/{run_id}/pause")
def dm_sei_pause_refresh_run(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return {"ok": True, "run": _repo(db, scope).pause_sei_student_refresh_run(run_id)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/refresh-runs/{run_id}/resume")
def dm_sei_resume_refresh_run(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return {"ok": True, "run": _repo(db, scope).resume_sei_student_refresh_run(run_id)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/refresh-runs/{run_id}/retry-failed")
def dm_sei_retry_failed_refresh_run(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    try:
        return {"ok": True, "run": _repo(db, scope).retry_failed_sei_student_refresh_run(run_id)}
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/sei/refresh-runs/{run_id}/batch")
async def dm_sei_process_refresh_batch(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Process one bounded SEI batch; credentials exist only for this request."""

    repo = _repo(db, scope)
    claimed_ids: list[int] = []
    try:
        payload = await request.json()
        username = str(payload.get("usuario") or "").strip()
        password = str(payload.get("senha") or "")
        if not username or not password:
            raise DMValidationError("Informe usuário e senha do SEI para continuar a fila.")

        requested_size = payload.get("batch_size", DM_SEI_REFRESH_BATCH_SIZE)
        try:
            batch_size = max(1, min(int(requested_size), 10, DM_SEI_REFRESH_BATCH_SIZE))
        except (TypeError, ValueError):
            batch_size = DM_SEI_REFRESH_BATCH_SIZE

        claimed = repo.claim_sei_student_refresh_batch(run_id, batch_size=batch_size)
        targets = list(claimed.get("items") or [])
        if not targets:
            return {
                "ok": True,
                "run": claimed["run"],
                "batch": {"requested": 0, "processed": 0, "deferred": 0},
                "credentials_persisted": False,
            }
        claimed_ids = [int(item["queue_item_id"]) for item in targets]

        lookup = await run_in_threadpool(
            lookup_student_course_dates,
            username,
            password,
            targets,
            max_seconds=DM_SEI_REFRESH_BATCH_BUDGET_SECONDS,
            request_timeout_seconds=DM_SEI_REFRESH_REQUEST_TIMEOUT_SECONDS,
        )
        processed_student_ids = [
            int(item["student_id"])
            for item in (lookup.get("items") or [])
            if item.get("student_id") not in (None, "")
        ]
        applied = repo.apply_sei_course_dates(lookup, source_type="sei_refresh_batch")
        run = repo.finish_sei_student_refresh_batch(
            run_id,
            queue_item_ids=claimed_ids,
            applied_result=applied,
            processed_student_ids=processed_student_ids,
        )
        return {
            "ok": True,
            "run": run,
            "batch": {
                **(applied.get("summary") or {}),
                "claimed": len(targets),
                "processed": len(processed_student_ids),
                "deferred": max(0, len(targets) - len(processed_student_ids)),
                "elapsed_seconds": lookup.get("elapsed_seconds"),
            },
            "warnings": applied.get("warnings") or [],
            "items": applied.get("items") or [],
            "credentials_persisted": False,
        }
    except Exception as exc:
        if claimed_ids:
            try:
                repo.release_sei_student_refresh_batch(
                    run_id,
                    claimed_ids,
                    decrement_attempt=True,
                )
            except Exception:
                LOGGER.exception("Falha ao devolver lote DM/SEI para a fila após erro de requisição")
        _translate(exc)


@router.post("/api/dm/sei/commit")
async def dm_sei_commit(
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Commit a previously reviewed SEI roster using a non-destructive policy."""

    try:
        _require_dm(scope)
        payload = await request.json()
        report = normalize_dm_sei_payload(payload.get("report") or {})
        source_type = str(payload.get("source_type") or "upload")[:30]
        selected_cohort_keys = [
            str(value).strip()
            for value in (payload.get("selected_cohort_keys") or [])
            if str(value or "").strip()
        ]
        if not selected_cohort_keys:
            raise DMValidationError("Selecione pelo menos uma turma para sincronizar.")

        repo = _repo(db, scope)
        result = repo.sync_sei_report(
            report,
            opening_dates=payload.get("opening_dates") or {},
            selected_cohort_keys=selected_cohort_keys,
            exclude_test=bool(payload.get("excluir_turmas_teste", True)),
            remove_demo=bool(payload.get("remover_demonstracao", True)),
            source_type=source_type,
            update_existing_opening_dates=bool(payload.get("atualizar_datas_existentes", False)),
        )

        # Student-by-student SEI enrichment is intentionally deferred.  It can take
        # several minutes for large cohorts and must not keep the roster-sync HTTP
        # request open until Nginx/Cloudflare times out.  The next queue stages will
        # process this scope in resumable batches.
        requested_inline_dates = bool(payload.get("consultar_datas_alunos", False))
        selected_ids = [
            int(value) for value in (result.get("selected_cohort_ids") or [])
            if str(value or "").strip()
        ]
        result["student_dates"] = {
            "ok": None,
            "deferred": True,
            "requested_inline": requested_inline_dates,
            "selected_cohort_ids": selected_ids,
            "credentials_persisted": False,
            "message": (
                "As turmas e os alunos foram sincronizados. A consulta individual de início, "
                "conclusão e titulação agora é executada separadamente para evitar timeout 504."
            ),
        }
        return result
    except Exception as exc:
        _translate(exc)


@router.post("/api/dm/demo/reset")
def reset_demo(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DM")),
):
    """Explicit homologation helper; real rows are never deleted or overwritten."""
    try:
        repo = _repo(db, scope)
        real_student = db.query(DmStudent.id).filter(
            DmStudent.directorate_id == repo.directorate_id, DmStudent.is_demo.is_(False)
        ).first()
        real_cohort = db.query(DmCohort.id).filter(
            DmCohort.directorate_id == repo.directorate_id, DmCohort.is_demo.is_(False)
        ).first()
        if real_student or real_cohort:
            raise HTTPException(409, "A demonstração só pode ser criada enquanto a base real do DM estiver vazia.")
        db.execute(delete(DmStudent).where(DmStudent.directorate_id == repo.directorate_id, DmStudent.is_demo.is_(True)))
        db.execute(delete(DmCohort).where(DmCohort.directorate_id == repo.directorate_id, DmCohort.is_demo.is_(True)))
        db.commit()
        cohorts = repo.bulk_upsert_cohorts(cohort_import_payloads())
        students = repo.bulk_upsert_students(student_import_payloads())
        return {
            "ok": True,
            "turmas": cohorts,
            "alunos": students,
            "mensagem": "Base demonstrativa do DM recriada. Nenhum dado real foi removido.",
        }
    except Exception as exc:
        db.rollback()
        _translate(exc)
