from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from schemas import ACADEMIC_DIRECTORATES
from security import DirectorateScope, current_scope, require_scope_write
from survey_archive import UploadStore, inspect_file, read_selected_workbooks
from survey_faculty_institution_archive import inspect_faculty_institution_file, read_selected_faculty_institution_workbooks
from survey_repository import SurveyIntegrationError, SurveyRepository
from survey_sei import SEIConnectorError
from survey_sessions import SurveySEISessionRegistry


router = APIRouter(prefix="/api/surveys", tags=["Avaliações SEI"])
SURVEY_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "data_univc_survey_uploads"
uploads = UploadStore(SURVEY_UPLOAD_ROOT)
sei_sessions = SurveySEISessionRegistry(ttl_seconds=30 * 60)


def _academic(scope: DirectorateScope) -> None:
    if scope.directorate_code not in ACADEMIC_DIRECTORATES or scope.directorate_code == "DEAD":
        raise HTTPException(404, "Avaliações institucionais estão disponíveis apenas nas diretorias acadêmicas operacionais.")


def _repo(db: Session, scope: DirectorateScope) -> SurveyRepository:
    _academic(scope)
    return SurveyRepository(db, scope)


def _connector(token: str, scope: DirectorateScope):
    try:
        return sei_sessions.get(token, owner_user_id=scope.user.user_id)
    except KeyError as exc:
        raise HTTPException(401, str(exc)) from exc


def _inspection_response(
    *,
    filename: str,
    content: bytes,
    origin: str,
    repo: SurveyRepository,
    sei_context: dict | None = None,
) -> dict:
    token, stored_path = uploads.create(filename, content)
    entries, meta = inspect_file(stored_path)
    raw_entries = [entry.to_dict() for entry in entries]
    enriched = repo.inspect_entries(raw_entries)
    manifest = {
        "token": token,
        "original_name": filename,
        "stored_name": stored_path.name,
        "origin": origin,
        "sei_context": sei_context or {},
        "meta": meta,
        "entries": raw_entries,
        "owner_user_id": repo.user.user_id,
        "directorate_id": repo.directorate_id,
    }
    uploads.save_manifest(token, manifest)
    semesters = sorted({entry.get("semester_suggested") for entry in raw_entries if entry.get("semester_suggested")})
    return {
        "token": token,
        "filename": filename,
        "origin": origin,
        "meta": meta,
        "semester_suggestions": semesters,
        "entries": enriched,
        "sei_context": sei_context or None,
    }


def _faculty_institution_inspection_response(
    *,
    filename: str,
    content: bytes,
    origin: str,
    repo: SurveyRepository,
    sei_context: dict | None = None,
) -> dict:
    token, stored_path = uploads.create(filename, content)
    entries, meta = inspect_faculty_institution_file(stored_path)
    raw_entries = [entry.to_dict() for entry in entries]
    manifest = {
        "token": token,
        "original_name": filename,
        "stored_name": stored_path.name,
        "origin": origin,
        "sei_context": sei_context or {},
        "meta": meta,
        "entries": raw_entries,
        "audience": "faculty",
        "owner_user_id": repo.user.user_id,
        "directorate_id": repo.directorate_id,
    }
    uploads.save_manifest(token, manifest)
    semesters = sorted({entry.get("semester_suggested") for entry in raw_entries if entry.get("semester_suggested")})
    return {
        "token": token,
        "filename": filename,
        "origin": origin,
        "meta": meta,
        "semester_suggestions": semesters,
        "entries": raw_entries,
        "sei_context": sei_context or None,
        "anonymous_population": True,
    }


def _require_upload_owner(manifest: dict, scope: DirectorateScope) -> None:
    if (
        str(manifest.get("owner_user_id") or "") != str(scope.user.user_id)
        or int(manifest.get("directorate_id") or 0) != int(scope.directorate_id)
    ):
        raise HTTPException(403, "Este upload temporário pertence a outro usuário ou diretoria.")


class SEILoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SEISessionRequest(BaseModel):
    session_token: str = Field(min_length=1)


class SEISearchRequest(SEISessionRequest):
    keyword: str = ""


class SEISelectEvaluationRequest(SEISessionRequest):
    source: str = Field(min_length=1)


class SEIConfigureReportRequest(SEISessionRequest):
    detail_value: str | None = None
    unit_value: str | None = None
    turn_value: str | None = None


class SEIPrepareQuestionnaireRequest(SEISessionRequest):
    questionnaire_id: str | None = None


class ProcessSurveyImportRequest(BaseModel):
    token: str = Field(min_length=1)
    selected_paths: list[str] = Field(min_length=1)
    semester_override: str | None = None


class BindNpsRequest(BaseModel):
    run_id: int
    question_id: int
    semester: str | None = None
    replace: bool = False
    nps_scope: str = "course"


@router.post("/sei/login")
def sei_login(
    payload: SEILoginRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    try:
        token = sei_sessions.create(
            payload.username.strip(),
            payload.password,
            owner_user_id=scope.user.user_id,
        )
        return {"ok": True, "session_token": token, "expires_in_minutes": 30}
    except Exception as exc:
        raise HTTPException(401, f"Não foi possível entrar no SEI: {exc}") from exc


@router.post("/sei/logout")
def sei_logout(
    payload: SEISessionRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    sei_sessions.remove(payload.session_token, owner_user_id=scope.user.user_id)
    return {"ok": True}


@router.post("/sei/evaluations/search")
def sei_search(
    payload: SEISearchRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    connector = _connector(payload.session_token, scope)
    try:
        results = connector.search_evaluations(payload.keyword)
        return {"results": [item.to_dict() for item in results], "count": len(results)}
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao consultar avaliações no SEI: {exc}") from exc


@router.post("/sei/evaluations/select")
def sei_select(
    payload: SEISelectEvaluationRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    connector = _connector(payload.session_token, scope)
    try:
        return connector.select_evaluation(payload.source).to_dict()
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao selecionar a avaliação no SEI: {exc}") from exc


@router.post("/sei/report/configure")
def sei_configure(
    payload: SEIConfigureReportRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    connector = _connector(payload.session_token, scope)
    try:
        return connector.configure_report(
            detail_value=payload.detail_value,
            unit_value=payload.unit_value,
            turn_value=payload.turn_value,
        ).to_dict()
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao configurar o relatório no SEI: {exc}") from exc


@router.post("/sei/questionnaire/prepare")
def sei_prepare(
    payload: SEIPrepareQuestionnaireRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    connector = _connector(payload.session_token, scope)
    try:
        return connector.prepare_all_questions(payload.questionnaire_id).to_dict()
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao preparar o questionário no SEI: {exc}") from exc


@router.post("/sei/report/generate")
def sei_generate(
    payload: SEISessionRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    connector = _connector(payload.session_token, scope)
    try:
        report = connector.generate_report()
        context = connector.metadata.to_dict() if connector.metadata else {}
        context.update({
            "download_path": report.download_path,
            "download_kind": report.kind,
            "progress": report.progress,
        })
        result = _inspection_response(
            filename=report.filename,
            content=report.content,
            origin="sei",
            repo=repo,
            sei_context=context,
        )
        result["download_kind"] = report.kind
        result["progress"] = report.progress
        return result
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao gerar/baixar relatório do SEI: {exc}") from exc


@router.post("/import/inspect")
async def inspect_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    filename = Path(file.filename or "upload").name
    if Path(filename).suffix.casefold() not in {".zip", ".xlsx"}:
        raise HTTPException(400, "Envie um arquivo ZIP ou XLSX gerado pelo relatório de avaliação do SEI.")
    content = await file.read()
    try:
        return _inspection_response(filename=filename, content=content, origin="manual", repo=repo)
    except Exception as exc:
        raise HTTPException(400, f"Não foi possível analisar o arquivo: {exc}") from exc


@router.post("/import/process")
def process_import(
    payload: ProcessSurveyImportRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    try:
        path, manifest = uploads.load(payload.token)
        _require_upload_owner(manifest, scope)
        allowed = {entry["internal_path"] for entry in manifest["entries"]}
        unknown = set(payload.selected_paths) - allowed
        if unknown:
            raise SurveyIntegrationError(f"A seleção contém relatórios desconhecidos: {sorted(unknown)[:3]}")
        parsed = read_selected_workbooks(path, payload.selected_paths)
        result = repo.import_workbooks(
            sha256=manifest["meta"]["sha256"],
            source_filename=manifest["original_name"],
            source_kind=manifest["meta"]["kind"],
            workbooks=parsed,
            semester_override=payload.semester_override,
            origin=manifest.get("origin", "manual"),
            metadata=manifest.get("sei_context") or None,
        )
        result["reports_selected"] = len(parsed)
        result["nps_candidates"] = repo.list_nps_candidates(int(result["run_id"]))
        return result
    except (SurveyIntegrationError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        token_dir = SURVEY_UPLOAD_ROOT / payload.token
        if token_dir.exists():
            shutil.rmtree(token_dir, ignore_errors=True)


@router.get("/nps/candidates/{run_id}")
def nps_candidates(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        return {"candidates": _repo(db, scope).list_nps_candidates(run_id)}
    except SurveyIntegrationError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/nps/bind")
def bind_nps(
    payload: BindNpsRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).bind_and_sync_nps(
            run_id=payload.run_id,
            question_id=payload.question_id,
            semester=payload.semester,
            replace=payload.replace,
            nps_scope=payload.nps_scope,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/nps/sources")
def nps_sources(
    nps_scope: str = "course",
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        return {"items": _repo(db, scope).nps_source_history(nps_scope)}
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/nps/institution/history")
def institution_nps_history(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    breakdown = repo.institution_nps_course_breakdown()
    return {
        "items": repo.institution_nps_history(),
        "by_course": breakdown,
        "courses": sorted({row.get("curso") for row in breakdown if row.get("curso")}),
    }


@router.post("/faculty-institution/sei/report/generate")
def faculty_institution_sei_generate(
    payload: SEISessionRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    connector = _connector(payload.session_token, scope)
    try:
        report = connector.generate_report()
        context = connector.metadata.to_dict() if connector.metadata else {}
        context.update({
            "download_path": report.download_path,
            "download_kind": report.kind,
            "progress": report.progress,
            "audience": "faculty",
        })
        result = _faculty_institution_inspection_response(
            filename=report.filename,
            content=report.content,
            origin="sei",
            repo=repo,
            sei_context=context,
        )
        result["download_kind"] = report.kind
        result["progress"] = report.progress
        return result
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao gerar/baixar o relatório institucional dos docentes no SEI: {exc}") from exc


@router.post("/faculty-institution/import/inspect")
async def faculty_institution_inspect_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    filename = Path(file.filename or "upload").name
    if Path(filename).suffix.casefold() not in {".zip", ".xlsx"}:
        raise HTTPException(400, "Envie um arquivo ZIP ou XLSX da Avaliação Institucional pelos docentes.")
    content = await file.read()
    try:
        return _faculty_institution_inspection_response(
            filename=filename, content=content, origin="manual", repo=repo
        )
    except Exception as exc:
        raise HTTPException(400, f"Não foi possível analisar o relatório docente: {exc}") from exc


@router.post("/faculty-institution/import/process")
def faculty_institution_process_import(
    payload: ProcessSurveyImportRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    try:
        path, manifest = uploads.load(payload.token)
        _require_upload_owner(manifest, scope)
        if manifest.get("audience") != "faculty" and (manifest.get("meta") or {}).get("audience") != "faculty":
            raise SurveyIntegrationError("Este upload não pertence ao fluxo institucional dos docentes.")
        allowed = {entry["internal_path"] for entry in manifest["entries"]}
        unknown = set(payload.selected_paths) - allowed
        if unknown:
            raise SurveyIntegrationError(f"A seleção contém relatórios desconhecidos: {sorted(unknown)[:3]}")
        parsed = read_selected_faculty_institution_workbooks(path, payload.selected_paths)
        result = repo.import_faculty_institution_workbooks(
            sha256=manifest["meta"]["sha256"],
            source_filename=manifest["original_name"],
            source_kind=manifest["meta"]["kind"],
            workbooks=parsed,
            semester_override=payload.semester_override,
            origin=manifest.get("origin", "manual"),
            metadata=manifest.get("sei_context") or None,
        )
        result["reports_selected"] = len(parsed)
        result["nps_candidates"] = repo.list_faculty_nps_candidates(int(result["run_id"]))
        return result
    except (SurveyIntegrationError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        token_dir = SURVEY_UPLOAD_ROOT / payload.token
        if token_dir.exists():
            shutil.rmtree(token_dir, ignore_errors=True)


@router.get("/nps/faculty/candidates/{run_id}")
def faculty_nps_candidates(
    run_id: int,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    try:
        return {"candidates": _repo(db, scope).list_faculty_nps_candidates(run_id)}
    except SurveyIntegrationError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/nps/faculty/bind")
def faculty_bind_nps(
    payload: BindNpsRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    try:
        return _repo(db, scope).bind_and_sync_faculty_nps(
            run_id=payload.run_id,
            question_id=payload.question_id,
            semester=payload.semester,
            replace=payload.replace,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/nps/faculty/history")
def faculty_nps_history(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    return {
        "items": _repo(db, scope).faculty_nps_history(),
        "anonymous_population": True,
        "scope": "institution",
    }


@router.get("/nps/faculty/sources")
def faculty_nps_sources(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    return {"items": _repo(db, scope).faculty_nps_source_history()}


@router.get("/faculty/readiness")
def faculty_readiness(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    return _repo(db, scope).faculty_readiness()
