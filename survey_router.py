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
from survey_faculty_student_archive import inspect_faculty_student_file, read_selected_faculty_student_contexts
from survey_faculty_student import (
    FACULTY_STUDENT_DETAIL_VALUE,
    FACULTY_STUDENT_GRADUATION_UNIT_NAME,
    FACULTY_STUDENT_TURN_VALUE,
    FACULTY_STUDENT_UNIT_VALUE,
    faculty_context_semantic_key,
    is_faculty_student_questionnaire,
    is_graduation_unit,
    normalize_faculty_semester,
)
from survey_repository import SurveyIntegrationError, SurveyRepository
from survey_sei import SEIConnectorError
from survey_sessions import SurveySEISessionRegistry
from survey_parser import normalize_key


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


def _prepare_faculty_student_sei(connector, questionnaire_id: str | None = None):
    metadata = connector.metadata
    if not metadata:
        raise SEIConnectorError("Selecione a avaliação docente antes de preparar o relatório.")

    candidates = [item for item in metadata.questionnaires if is_faculty_student_questionnaire(item.name)]
    selected = None
    if questionnaire_id:
        selected = next((item for item in candidates if item.sei_id == questionnaire_id), None)
        if selected is None:
            raise SEIConnectorError("O questionário informado não é o questionário de discente avaliando docente.")
    else:
        selected = next(
            (item for item in candidates if item.sei_id == metadata.selected_questionnaire_id),
            None,
        )
        if selected is None and len(candidates) == 1:
            selected = candidates[0]
        if selected is None and candidates:
            # Preferência semântica, nunca por posição/ID fixo do HAR.
            selected = sorted(candidates, key=lambda item: ("aluno avalia professor" not in normalize_key(item.name), item.name.casefold()))[0]
    if selected is None:
        raise SEIConnectorError("A avaliação selecionada não contém um questionário de discente avaliando docente.")

    metadata = connector.select_questionnaire(selected.sei_id)

    unit_option = next((item for item in metadata.unit_options if item.value == FACULTY_STUDENT_UNIT_VALUE), None)
    if unit_option is None or normalize_key(FACULTY_STUDENT_GRADUATION_UNIT_NAME) not in normalize_key(unit_option.label):
        raise SEIConnectorError("A tela atual do SEI não oferece a unidade Graduação São Mateus esperada.")
    if metadata.detail_options and not any(item.value == FACULTY_STUDENT_DETAIL_VALUE for item in metadata.detail_options):
        raise SEIConnectorError("A tela atual do SEI não oferece o nível Disciplina/Professor.")
    if metadata.turn_options and not any(item.value == FACULTY_STUDENT_TURN_VALUE for item in metadata.turn_options):
        raise SEIConnectorError("A tela atual do SEI não oferece o filtro de todos os turnos.")

    connector.configure_report(
        detail_value=FACULTY_STUDENT_DETAIL_VALUE,
        unit_value=FACULTY_STUDENT_UNIT_VALUE,
        turn_value=FACULTY_STUDENT_TURN_VALUE,
    )
    # O questionário já foi selecionado antes dos filtros. Não o reselecionamos
    # aqui, pois uma nova seleção pode restaurar valores padrão do backing bean
    # e desfazer Unidade/Disciplina-Professor antes da geração.
    metadata = connector.prepare_all_questions()
    return metadata


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
    enriched = repo.inspect_entries(raw_entries, origin=origin)
    resolvable_paths = [
        str(entry.get("internal_path") or "")
        for entry in enriched
        if (entry.get("course_match") or {}).get("resolution_required")
    ]
    course_resolution_candidates = {
        str(entry.get("internal_path") or ""): [
            int(value) for value in ((entry.get("course_match") or {}).get("candidate_ids") or [])
        ]
        for entry in enriched
        if (entry.get("course_match") or {}).get("resolution_required")
    }
    manifest = {
        "token": token,
        "original_name": filename,
        "stored_name": stored_path.name,
        "origin": origin,
        "sei_context": sei_context or {},
        "meta": meta,
        "entries": raw_entries,
        "resolvable_paths": resolvable_paths,
        "course_resolution_candidates": course_resolution_candidates,
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
        "resolvable_paths": resolvable_paths,
        "course_resolution_candidates": course_resolution_candidates,
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



def _faculty_student_inspection_response(
    *,
    filename: str,
    content: bytes,
    origin: str,
    repo: SurveyRepository,
    sei_context: dict | None = None,
) -> dict:
    token, stored_path = uploads.create(filename, content)
    entries, meta = inspect_faculty_student_file(stored_path)
    raw_entries = [entry.to_dict() for entry in entries]

    identity_entry = next(
        (
            item for item in raw_entries
            if item.get("graduation_unit") and not item.get("parse_error")
        ),
        None,
    )
    survey_identity = {
        "survey_title": (identity_entry or {}).get("survey_title"),
        "questionnaire_name": (identity_entry or {}).get("questionnaire_name"),
        "period_start": (identity_entry or {}).get("period_start"),
        "period_end": (identity_entry or {}).get("period_end"),
    }
    existing_state = repo.faculty_import_state(
        sha256=str(meta.get("sha256") or ""),
        origin=origin,
        metadata=sei_context or {},
        survey_identity=survey_identity,
    )
    existing_semantic_keys = set(existing_state.get("semantic_keys") or [])

    enriched: list[dict] = []
    eligible_paths: list[str] = []
    resolvable_paths: list[str] = []
    course_resolution_candidates: dict[str, list[int]] = {}
    for item in raw_entries:
        course_match = {"matched": False, "reason": "Curso não analisado"}
        scope_status = "outside_unit"
        scope_reason = "Somente a unidade Graduação São Mateus é aceita."
        semantic_key = ""
        already_imported = False
        if item.get("unit_name") and not is_graduation_unit(item.get("unit_name")):
            scope_status = "outside_unit"
            scope_reason = "Somente a unidade Graduação São Mateus é aceita."
        elif item.get("parse_error"):
            scope_status = "invalid_report"
            scope_reason = str(item.get("parse_error"))
        elif item.get("graduation_unit") and is_graduation_unit(item.get("unit_name")):
            if not is_faculty_student_questionnaire(item.get("questionnaire_name")):
                scope_status = "wrong_questionnaire"
                scope_reason = "O relatório não usa o questionário de discente avaliando docente."
            else:
                course_match = repo.match_course_for_source(
                    str(item.get("course_name") or ""),
                    str(item.get("modality") or ""),
                    origin=origin,
                )
                if course_match.get("matched"):
                    semantic_key = faculty_context_semantic_key(
                        str(course_match.get("course_name") or item.get("course_name") or ""),
                        str(item.get("teacher_name") or ""),
                        str(item.get("discipline_name") or ""),
                        str(item.get("class_code") or ""),
                    )
                    already_imported = semantic_key in existing_semantic_keys
                    if already_imported:
                        scope_status = "already_imported"
                        scope_reason = "Este contexto acadêmico já foi importado desta fonte."
                    else:
                        scope_status = "eligible"
                        scope_reason = "Pronto para importação nesta diretoria."
                        eligible_paths.append(str(item["internal_path"]))
                else:
                    scope_reason = str(
                        course_match.get("reason")
                        or "Curso fora do escopo da diretoria."
                    )
                    if course_match.get("resolution_required"):
                        # Uma reexportação pode continuar trazendo o rótulo ambíguo
                        # mesmo depois de o usuário ter resolvido o contexto na
                        # primeira importação. Nesse caso, comparamos cada curso
                        # candidato com a identidade já persistida e evitamos
                        # pedir a mesma decisão novamente quando houver um único
                        # candidato inequivocamente já importado.
                        existing_candidate_matches = []
                        for candidate in course_match.get("candidate_courses") or []:
                            candidate_semantic_key = faculty_context_semantic_key(
                                str(candidate.get("course_name") or ""),
                                str(item.get("teacher_name") or ""),
                                str(item.get("discipline_name") or ""),
                                str(item.get("class_code") or ""),
                            )
                            if candidate_semantic_key in existing_semantic_keys:
                                existing_candidate_matches.append(candidate)
                        if len(existing_candidate_matches) == 1:
                            already_imported = True
                            scope_status = "already_imported"
                            scope_reason = (
                                "Este contexto acadêmico ambíguo já foi resolvido e importado anteriormente."
                            )
                            semantic_key = faculty_context_semantic_key(
                                str(existing_candidate_matches[0].get("course_name") or ""),
                                str(item.get("teacher_name") or ""),
                                str(item.get("discipline_name") or ""),
                                str(item.get("class_code") or ""),
                            )
                            course_match = {
                                **course_match,
                                "existing_resolution": existing_candidate_matches[0],
                            }
                        else:
                            scope_status = "course_resolution_required"
                            resolution_path = str(item["internal_path"])
                            candidate_ids = [int(value) for value in course_match.get("candidate_ids") or []]
                            if candidate_ids:
                                resolvable_paths.append(resolution_path)
                                course_resolution_candidates[resolution_path] = candidate_ids
                    else:
                        scope_status = "course_out_of_scope"
        enriched.append({
            **item,
            "course_match": course_match,
            "semantic_key": semantic_key or None,
            "already_imported": already_imported,
            "scope_status": scope_status,
            "scope_reason": scope_reason,
            "eligible": scope_status == "eligible",
            "resolution_required": scope_status == "course_resolution_required",
            "resolution_key": str(item.get("internal_path") or "") if scope_status == "course_resolution_required" else None,
        })

    semesters = sorted({
        normalized
        for entry in enriched
        if entry.get("eligible") or entry.get("resolution_required")
        for normalized in [normalize_faculty_semester(entry.get("semester_suggested"))]
        if normalized
    })
    semester_source = "report" if semesters else None
    existing_semester = normalize_faculty_semester(existing_state.get("semester"))
    if not semesters and existing_semester:
        semesters = [existing_semester]
        semester_source = "existing_import"

    semester_confirmation_required = len(semesters) != 1
    warnings: list[str] = []
    if not semesters:
        warnings.append(
            "O relatório não identifica explicitamente o semestre letivo; confirme AAAA-SEM1 ou AAAA-SEM2 antes de importar."
        )
    elif len(semesters) > 1:
        warnings.append(
            "Foram encontrados semestres explícitos diferentes no mesmo lote; escolha um único semestre antes da importação."
        )
    if int(meta.get("unit_scope_mismatch_count") or 0):
        warnings.append(
            "Há divergência entre a unidade indicada pelo caminho do ZIP e a unidade gravada no conteúdo de pelo menos um XLSX."
        )
    unresolved_count = sum(
        1 for item in enriched
        if item.get("scope_status") == "course_resolution_required"
    )
    if unresolved_count:
        warnings.append(
            f"{unresolved_count} relatório(s) exigem resolução manual da identidade do curso antes de importar."
        )
    if existing_state.get("exists"):
        warnings.append(
            f"Esta fonte já possui {int(existing_state.get('context_count') or 0)} contexto(s) persistido(s) nesta diretoria; eles não serão duplicados."
        )

    public_existing_state = {
        key: value
        for key, value in existing_state.items()
        if key not in {"source_keys", "semantic_keys"}
    }
    manifest = {
        "token": token,
        "original_name": filename,
        "stored_name": stored_path.name,
        "origin": origin,
        "sei_context": sei_context or {},
        "meta": meta,
        "entries": raw_entries,
        "eligible_paths": eligible_paths,
        "resolvable_paths": resolvable_paths,
        "course_resolution_candidates": course_resolution_candidates,
        "available_courses": repo.course_options(),
        "existing_import": public_existing_state,
        "audience": "faculty_student",
        "owner_user_id": repo.user.user_id,
        "directorate_id": repo.directorate_id,
    }
    uploads.save_manifest(token, manifest)

    return {
        "token": token,
        "filename": filename,
        "origin": origin,
        "meta": meta,
        "semester_suggestions": semesters,
        "semester_suggestion_source": semester_source,
        "suggested_semester": semesters[0] if len(semesters) == 1 else None,
        "semester_confirmation_required": semester_confirmation_required,
        "entries": enriched,
        "eligible_paths": eligible_paths,
        "resolvable_paths": resolvable_paths,
        "course_resolution_candidates": course_resolution_candidates,
        "available_courses": repo.course_options(),
        "existing_import": public_existing_state,
        "warnings": warnings,
        "summary": {
            "total_reports": len(enriched),
            "eligible": len(eligible_paths),
            "already_imported": sum(1 for item in enriched if item["scope_status"] == "already_imported"),
            "courses": len({item.get("course_match", {}).get("course_name") for item in enriched if item.get("eligible") and item.get("course_match", {}).get("course_name")}),
            "teachers": len({normalize_key(str(item.get("teacher_name") or "")) for item in enriched if item.get("eligible") and item.get("teacher_name")}),
            "disciplines": len({normalize_key(str(item.get("discipline_name") or "")) for item in enriched if item.get("eligible") and item.get("discipline_name")}),
            "responses_across_contexts": sum(int(item.get("respondent_count") or 0) for item in enriched if item.get("eligible")),
            "outside_unit": sum(1 for item in enriched if item["scope_status"] == "outside_unit"),
            "course_out_of_scope": sum(1 for item in enriched if item["scope_status"] == "course_out_of_scope"),
            "course_resolution_required": unresolved_count,
            "resolvable": len(resolvable_paths),
            "wrong_questionnaire": sum(1 for item in enriched if item["scope_status"] == "wrong_questionnaire"),
            "invalid_report": sum(1 for item in enriched if item["scope_status"] == "invalid_report"),
            "xlsx_opened": int(meta.get("opened_xlsx_count") or 0),
            "xlsx_validated_by_content": int(meta.get("content_validated_count") or 0),
            "xlsx_fast_rejected": int(meta.get("skipped_without_opening") or 0),
        },
        "scope": {
            "unit_value": FACULTY_STUDENT_UNIT_VALUE,
            "unit_name": FACULTY_STUDENT_GRADUATION_UNIT_NAME,
            "detail_value": FACULTY_STUDENT_DETAIL_VALUE,
            "turn_value": FACULTY_STUDENT_TURN_VALUE,
            "directorate": repo.directorate_code,
        },
        "sei_context": sei_context or None,
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


class FacultyStudentSEIPrepareRequest(SEISessionRequest):
    questionnaire_id: str | None = None


class ProcessSurveyImportRequest(BaseModel):
    token: str = Field(min_length=1)
    selected_paths: list[str] = Field(min_length=1)
    semester_override: str | None = None
    # v0.11.2: resolução explícita por arquivo/contexto. A chave é o caminho
    # interno do XLSX no ZIP e o valor é um course_id permitido pelo preview.
    course_resolutions: dict[str, int] = Field(default_factory=dict)
    # Cursos adicionais atendidos pela mesma turma/contexto docente.
    shared_course_scopes: dict[str, list[int]] = Field(default_factory=dict)


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
        requested = set(payload.selected_paths)
        resolvable = set(manifest.get("resolvable_paths") or [])
        candidate_map = {
            str(key): {int(value) for value in values}
            for key, values in (manifest.get("course_resolution_candidates") or {}).items()
        }
        resolutions = {str(key): int(value) for key, value in (payload.course_resolutions or {}).items()}
        if set(resolutions) - requested:
            raise SurveyIntegrationError("Há resolução de curso para relatório que não foi selecionado.")
        unresolved = {path for path in requested if path in resolvable and path not in resolutions}
        if unresolved:
            raise SurveyIntegrationError(
                "Resolva a identidade do curso antes de importar: " + ", ".join(sorted(unresolved)[:3])
            )
        for source_path, course_id in resolutions.items():
            if source_path not in resolvable or int(course_id) not in candidate_map.get(source_path, set()):
                raise SurveyIntegrationError(
                    f"{source_path}: o curso escolhido não está entre as opções permitidas pelo preview."
                )
        parsed = read_selected_workbooks(path, payload.selected_paths)
        result = repo.import_workbooks(
            sha256=manifest["meta"]["sha256"],
            source_filename=manifest["original_name"],
            source_kind=manifest["meta"]["kind"],
            workbooks=parsed,
            semester_override=payload.semester_override,
            origin=manifest.get("origin", "manual"),
            metadata=manifest.get("sei_context") or None,
            course_resolutions=resolutions,
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


@router.post("/faculty-student/sei/prepare")
def faculty_student_sei_prepare(
    payload: FacultyStudentSEIPrepareRequest,
    scope: DirectorateScope = Depends(require_scope_write),
):
    _academic(scope)
    connector = _connector(payload.session_token, scope)
    try:
        metadata = _prepare_faculty_student_sei(connector, payload.questionnaire_id)
        return {
            **metadata.to_dict(),
            "scope_locked": True,
            "scope": {
                "detail_value": FACULTY_STUDENT_DETAIL_VALUE,
                "detail_label": "Disciplina/Professor",
                "unit_value": FACULTY_STUDENT_UNIT_VALUE,
                "unit_name": FACULTY_STUDENT_GRADUATION_UNIT_NAME,
                "turn_value": FACULTY_STUDENT_TURN_VALUE,
                "questions": "all",
            },
        }
    except SEIConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao preparar a Avaliação Docente no SEI: {exc}") from exc


@router.post("/faculty-student/sei/report/generate")
def faculty_student_sei_generate(
    payload: SEISessionRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    connector = _connector(payload.session_token, scope)
    try:
        metadata = connector.metadata
        if not metadata:
            raise SEIConnectorError("Prepare a Avaliação Docente antes de gerar o relatório.")
        if metadata.detail_value != FACULTY_STUDENT_DETAIL_VALUE or metadata.unit_value != FACULTY_STUDENT_UNIT_VALUE:
            raise SEIConnectorError("O relatório docente perdeu o escopo protegido. Execute Preparar novamente.")
        if not is_faculty_student_questionnaire(metadata.selected_questionnaire_name):
            raise SEIConnectorError("O questionário atual não é o de discente avaliando docente.")
        if metadata.question_count <= 0:
            raise SEIConnectorError("Selecione todas as perguntas antes de gerar o relatório.")

        report = connector.generate_report()
        context = metadata.to_dict()
        context.update({
            "download_path": report.download_path,
            "download_kind": report.kind,
            "progress": report.progress,
            "audience": "faculty_student",
            "scope_locked": True,
        })
        result = _faculty_student_inspection_response(
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
        raise HTTPException(502, f"Falha ao gerar/baixar a Avaliação Docente no SEI: {exc}") from exc


@router.post("/faculty-student/import/inspect")
async def faculty_student_inspect_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    filename = Path(file.filename or "upload").name
    if Path(filename).suffix.casefold() not in {".zip", ".xlsx"}:
        raise HTTPException(400, "Envie um ZIP ou XLSX do relatório Disciplina/Professor do SEI.")
    content = await file.read()
    try:
        return _faculty_student_inspection_response(
            filename=filename,
            content=content,
            origin="manual",
            repo=repo,
        )
    except Exception as exc:
        raise HTTPException(400, f"Não foi possível analisar a Avaliação Docente: {exc}") from exc


@router.post("/faculty-student/import/process")
def faculty_student_process_import(
    payload: ProcessSurveyImportRequest,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_scope_write),
):
    repo = _repo(db, scope)
    try:
        path, manifest = uploads.load(payload.token)
        _require_upload_owner(manifest, scope)
        if manifest.get("audience") != "faculty_student":
            raise SurveyIntegrationError("Este upload não pertence ao fluxo de discente avaliando docente.")

        allowed = set(manifest.get("eligible_paths") or [])
        resolvable = set(manifest.get("resolvable_paths") or [])
        candidate_map = {
            str(key): {int(value) for value in values}
            for key, values in (manifest.get("course_resolution_candidates") or {}).items()
        }
        requested = set(payload.selected_paths)
        resolutions = {str(key): int(value) for key, value in (payload.course_resolutions or {}).items()}
        shared_scopes = {
            str(key): sorted({int(value) for value in (values or [])})
            for key, values in (payload.shared_course_scopes or {}).items()
        }
        if not requested:
            raise SurveyIntegrationError("Selecione ao menos um relatório elegível.")

        unexpected_resolution = set(resolutions) - requested
        if unexpected_resolution:
            raise SurveyIntegrationError(
                "Há resolução de curso para relatório que não foi selecionado: "
                + ", ".join(sorted(unexpected_resolution)[:3])
            )

        unresolved_selected = {item for item in requested if item in resolvable and item not in resolutions}
        if unresolved_selected:
            raise SurveyIntegrationError(
                "Resolva explicitamente a identidade do curso antes de importar: "
                + ", ".join(sorted(unresolved_selected)[:3])
            )

        for source_path, course_id in resolutions.items():
            if source_path not in resolvable:
                raise SurveyIntegrationError(
                    f"{source_path}: este relatório não aceita resolução manual de curso."
                )
            if int(course_id) not in candidate_map.get(source_path, set()):
                raise SurveyIntegrationError(
                    f"{source_path}: o course_id escolhido não está entre os candidatos permitidos."
                )

        unexpected_shared = set(shared_scopes) - requested
        if unexpected_shared:
            raise SurveyIntegrationError(
                "Há escopo compartilhado para relatório que não foi selecionado: "
                + ", ".join(sorted(unexpected_shared)[:3])
            )
        allowed_course_ids = {int(item["course_id"]) for item in repo.course_options()}
        for source_path, course_ids in shared_scopes.items():
            invalid_ids = {int(value) for value in course_ids} - allowed_course_ids
            if invalid_ids:
                raise SurveyIntegrationError(
                    f"{source_path}: há curso compartilhado fora da diretoria ou inativo."
                )

        allowed_with_resolution = allowed | {
            source_path for source_path in resolvable if source_path in resolutions
        }
        outside = requested - allowed_with_resolution
        if outside:
            raise SurveyIntegrationError(
                "A seleção contém relatórios fora do escopo, não elegíveis ou já importados: "
                + ", ".join(sorted(outside)[:3])
            )

        contexts = read_selected_faculty_student_contexts(path, payload.selected_paths)
        if not contexts:
            raise SurveyIntegrationError("Nenhum contexto docente elegível foi selecionado.")
        for context in contexts:
            if not is_graduation_unit(context.unit_name):
                raise SurveyIntegrationError("Somente relatórios da Graduação São Mateus podem ser importados.")
            if not is_faculty_student_questionnaire(context.questionnaire_name):
                raise SurveyIntegrationError("Questionário incompatível com discente avaliando docente.")
            match = repo.resolve_course(
                context.course_name,
                context.modality,
                explicit_course_id=resolutions.get(context.source_path),
                origin=manifest.get("origin", "manual"),
            )
            if not match.get("matched"):
                raise SurveyIntegrationError(
                    f"Curso fora do escopo de {scope.directorate_code}: {context.course_name}. "
                    f"{match.get('reason') or ''}".strip()
                )

        # O título 2026 observado no HAR não contém .1/.2; a data de aplicação
        # (julho) nunca é usada para adivinhar o semestre letivo.
        normalized_override = normalize_faculty_semester(payload.semester_override)
        if payload.semester_override and not normalized_override:
            raise SurveyIntegrationError(
                "Semestre inválido. Use AAAA-SEM1 ou AAAA-SEM2 (ex.: 2026-SEM1)."
            )
        suggested_semesters = sorted({
            normalized
            for context in contexts
            for normalized in [normalize_faculty_semester(context.semester_suggested)]
            if normalized
        })
        existing_semester = normalize_faculty_semester(
            (manifest.get("existing_import") or {}).get("semester")
        )
        if not normalized_override:
            if len(suggested_semesters) > 1:
                raise SurveyIntegrationError(
                    "Os relatórios selecionados indicam semestres diferentes. "
                    "Confirme explicitamente um único semestre antes de importar."
                )
            if len(suggested_semesters) == 1:
                normalized_override = suggested_semesters[0]
            elif existing_semester:
                normalized_override = existing_semester
            else:
                raise SurveyIntegrationError(
                    "O SEI não identifica explicitamente o semestre letivo neste relatório. "
                    "Confirme o semestre (ex.: 2026-SEM1) antes de importar."
                )

        import_metadata = dict(manifest.get("sei_context") or {
            "audience": "faculty_student",
            "unit_value": FACULTY_STUDENT_UNIT_VALUE,
            "detail_value": FACULTY_STUDENT_DETAIL_VALUE,
            "turn_value": FACULTY_STUDENT_TURN_VALUE,
        })
        if resolutions:
            import_metadata["faculty_course_resolution_ids"] = resolutions
        if shared_scopes:
            import_metadata["faculty_shared_course_scope_ids"] = shared_scopes

        result = repo.import_faculty_contexts(
            sha256=manifest["meta"]["sha256"],
            source_filename=manifest["original_name"],
            source_kind=manifest["meta"]["kind"],
            contexts=contexts,
            semester_override=normalized_override,
            origin=manifest.get("origin", "manual"),
            metadata=import_metadata,
            course_resolutions=resolutions,
            shared_course_scopes=shared_scopes,
        )
        result["reports_selected"] = len(contexts)
        result["scope"] = {
            "unit_name": FACULTY_STUDENT_GRADUATION_UNIT_NAME,
            "directorate": scope.directorate_code,
            "detail": "Disciplina/Professor",
        }
        return result
    except (SurveyIntegrationError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        token_dir = SURVEY_UPLOAD_ROOT / payload.token
        if token_dir.exists():
            shutil.rmtree(token_dir, ignore_errors=True)


@router.get("/faculty-student/scope")
def faculty_student_scope(
    scope: DirectorateScope = Depends(current_scope),
):
    _academic(scope)
    return {
        "directorate": scope.directorate_code,
        "unit_value": FACULTY_STUDENT_UNIT_VALUE,
        "unit_name": FACULTY_STUDENT_GRADUATION_UNIT_NAME,
        "detail_value": FACULTY_STUDENT_DETAIL_VALUE,
        "detail_label": "Disciplina/Professor",
        "turn_value": FACULTY_STUDENT_TURN_VALUE,
        "questions": "all",
    }


@router.get("/faculty-student/imports")
def faculty_student_import_history(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_import_history()
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/identity/catalog")
def faculty_student_identity_catalog(
    semester: str | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_identity_catalog(semester)
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/identity/quality")
def faculty_student_identity_quality(
    semester: str | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_identity_quality(semester)
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/filters")
def faculty_student_analytics_filters(
    semester: str | None = None,
    course_id: int | None = None,
    discipline_id: int | None = None,
    teacher_id: int | None = None,
    offering_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_filters(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
            offering_id=offering_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/operational")
def faculty_student_analytics_operational(
    semester: str | None = None,
    course_id: int | None = None,
    discipline_id: int | None = None,
    teacher_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_operational_status(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/overview")
def faculty_student_analytics_overview(
    semester: str | None = None,
    course_id: int | None = None,
    discipline_id: int | None = None,
    teacher_id: int | None = None,
    offering_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_overview(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
            offering_id=offering_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/questions")
def faculty_student_analytics_questions(
    semester: str | None = None,
    course_id: int | None = None,
    discipline_id: int | None = None,
    teacher_id: int | None = None,
    offering_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_questions(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
            offering_id=offering_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/teachers")
def faculty_student_analytics_teachers(
    semester: str | None = None,
    course_id: int | None = None,
    discipline_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_teachers(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/teachers/{teacher_id}")
def faculty_student_analytics_teacher_detail(
    teacher_id: int,
    semester: str | None = None,
    course_id: int | None = None,
    discipline_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_teacher_detail(
            teacher_id,
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/faculty-student/analytics/disciplines")
def faculty_student_analytics_disciplines(
    semester: str | None = None,
    course_id: int | None = None,
    teacher_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_disciplines(
            semester=semester,
            course_id=course_id,
            teacher_id=teacher_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/disciplines/{discipline_id}")
def faculty_student_analytics_discipline_detail(
    discipline_id: int,
    semester: str | None = None,
    teacher_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_discipline_detail(
            discipline_id,
            semester=semester,
            teacher_id=teacher_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/faculty-student/analytics/courses")
def faculty_student_analytics_courses(
    semester: str | None = None,
    teacher_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_courses(semester=semester, teacher_id=teacher_id)
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/faculty-student/analytics/semesters/compare")
def faculty_student_analytics_semester_comparison(
    course_id: int | None = None,
    discipline_id: int | None = None,
    teacher_id: int | None = None,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(current_scope),
):
    repo = _repo(db, scope)
    try:
        return repo.faculty_analytics_semester_comparison(
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
        )
    except SurveyIntegrationError as exc:
        raise HTTPException(400, str(exc)) from exc


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
