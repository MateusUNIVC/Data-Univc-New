from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from auth.data_scopes import dadm_department_scope, dadm_has_full_data_access, department_allowed
from dadm_tallos_analytics import build_tallos_dashboard, filters_payload, operator_comparison, rating_audit_payload
from dadm_tallos_client import DADMTallosAPIError, token_configured
from dadm_tallos_local_config import (
    clear_local_token,
    environment_name,
    local_token_management_enabled,
    persist_local_token,
    test_connection,
    token_source,
)
from dadm_tallos_repository import DADMTallosRepository
from dadm_tallos_service import execute_sync_run
from security import DirectorateScope, require_directorate_access, require_directorate_edit

LOGGER = logging.getLogger("univc.dadm.tallos")
router = APIRouter()


def _require_dadm(scope: DirectorateScope) -> DirectorateScope:
    if scope.directorate_code != "DADM":
        raise HTTPException(404, "O TALLOS Analytics Center pertence à Diretoria Administrativa.")
    return scope




def _allowed_departments(scope: DirectorateScope) -> tuple[str, ...] | None:
    return dadm_department_scope(scope.user.email, global_access=scope.user.global_access)


def _require_department(scope: DirectorateScope, department: str | None) -> None:
    if department and not department_allowed(department, _allowed_departments(scope)):
        raise HTTPException(403, "Este departamento não faz parte do seu escopo de dados na DADM.")


def _require_full_dadm(scope: DirectorateScope) -> None:
    if not dadm_has_full_data_access(scope.user.email, global_access=scope.user.global_access):
        raise HTTPException(403, "Esta operação exige acesso completo aos dados da DADM.")

def _dates(start: date | None, end: date | None) -> tuple[date, date]:
    today = date.today()
    end = end or today
    start = start or (end - timedelta(days=179))
    if end < start:
        raise HTTPException(422, "A data final não pode ser anterior à data inicial.")
    if (end - start).days > 1826:
        raise HTTPException(422, "O painel aceita no máximo cinco anos por consulta.")
    return start, end


def _dashboard(
    db: Session,
    scope: DirectorateScope,
    inicio: date | None,
    fim: date | None,
    departamento: str | None,
    operador: str | None,
    canal: str | None,
    status: str | None,
    tabulacao: str | None,
    comparacao: str,
    granularidade: str,
):
    _require_dadm(scope)
    _require_department(scope, departamento)
    start, end = _dates(inicio, fim)
    try:
        return build_tallos_dashboard(
            db,
            scope.directorate_id,
            start,
            end,
            department=departamento,
            employee=operador,
            channel=canal,
            status=status,
            tabulation=tabulacao,
            comparison_mode=comparacao,
            grain=granularidade,
            allowed_departments=_allowed_departments(scope),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class TallosTokenPayload(BaseModel):
    token: str | None = None


@router.get("/api/dadm/tallos/status")
def dadm_tallos_status(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    data = DADMTallosRepository(db, scope).data_status(allowed_departments=_allowed_departments(scope))
    local_management = local_token_management_enabled()
    return {
        "configured": token_configured(),
        "source": "TALLOS / RD Station Conversas",
        "endpoint": "/v4/reports",
        "auth_test_endpoint": "/v2/employees",
        "page_limit": 49,
        "environment": environment_name(),
        "token_source": token_source(),
        "token_management_enabled": bool(local_management and scope.can_write),
        "local_reset_enabled": bool(local_management and scope.can_write and dadm_has_full_data_access(scope.user.email, global_access=scope.user.global_access)),
        "data_available": data["attendance_count"] > 0,
        **data,
    }


@router.post("/api/dadm/tallos/test-connection")
def dadm_tallos_test_connection(
    payload: TallosTokenPayload,
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    _require_dadm(scope)
    supplied = (payload.token or "").strip()
    if supplied and not local_token_management_enabled():
        raise HTTPException(403, "Em produção, o token TALLOS deve ser configurado no ambiente do servidor.")
    try:
        result = test_connection(supplied or None)
    except (ValueError, DADMTallosAPIError) as exc:
        raise HTTPException(502, f"Não foi possível validar a conexão TALLOS: {exc}") from exc
    return {
        "ok": True,
        "mensagem": "Conexão TALLOS validada com sucesso.",
        **result,
    }


@router.post("/api/dadm/tallos/config/token")
def dadm_tallos_save_local_token(
    payload: TallosTokenPayload,
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    _require_dadm(scope)
    if not local_token_management_enabled():
        raise HTTPException(403, "Em produção, configure TALLOS_API_TOKEN no ambiente do servidor.")
    token = (payload.token or "").strip()
    try:
        connection = test_connection(token)
        persist_local_token(token)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except DADMTallosAPIError as exc:
        raise HTTPException(502, f"O token não foi salvo porque a TALLOS não aceitou a conexão: {exc}") from exc
    return {
        "ok": True,
        "configured": True,
        "mensagem": "Token TALLOS validado e salvo no .env local. Ele já pode ser usado sem reiniciar a aplicação.",
        "connection": connection,
    }


@router.delete("/api/dadm/tallos/config/token")
def dadm_tallos_remove_local_token(
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    _require_dadm(scope)
    _require_full_dadm(scope)
    if not local_token_management_enabled():
        raise HTTPException(403, "Em produção, o token TALLOS é gerenciado pelo ambiente do servidor.")
    clear_local_token()
    return {"ok": True, "configured": False, "mensagem": "Token TALLOS removido da configuração local."}


@router.delete("/api/dadm/tallos/local-data")
def dadm_tallos_clear_local_data(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    _require_dadm(scope)
    _require_full_dadm(scope)
    if not local_token_management_enabled():
        raise HTTPException(403, "A limpeza da base TALLOS pela interface existe somente para homologação local.")
    repo = DADMTallosRepository(db, scope)
    active = repo.active_sync_run()
    if active:
        raise HTTPException(409, f"Aguarde a sincronização TALLOS #{active.id} terminar antes de limpar a base.")
    removed = repo.clear_local_analytics_data()
    return {
        "ok": True,
        "removed": removed,
        "mensagem": "Base TALLOS local limpa. Indicadores oficiais DADM-01/DADM-02 não foram alterados.",
    }


@router.get("/api/dadm/tallos/filters")
def dadm_tallos_filters(
    inicio: date | None = Query(None),
    fim: date | None = Query(None),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    start, end = _dates(inicio, fim)
    return filters_payload(db, scope.directorate_id, start, end, allowed_departments=_allowed_departments(scope))


@router.get("/api/dadm/tallos/dashboard")
def dadm_tallos_dashboard(
    inicio: date | None = Query(None),
    fim: date | None = Query(None),
    departamento: str | None = Query(None),
    operador: str | None = Query(None),
    canal: str | None = Query(None),
    status: str | None = Query(None),
    tabulacao: str | None = Query(None),
    comparacao: str = Query("previous_period", pattern="^(none|previous_period|previous_month|previous_year)$"),
    granularidade: str = Query("month", pattern="^(month|day)$"),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    return _dashboard(db, scope, inicio, fim, departamento, operador, canal, status, tabulacao, comparacao, granularidade)


# Focused read endpoints preserve the public contract while the current DADM UI
# deliberately uses the combined /dashboard response to minimize round-trips.
@router.get("/api/dadm/tallos/summary")
def dadm_tallos_summary(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), operador: str | None = Query(None),
    canal: str | None = Query(None), status: str | None = Query(None), tabulacao: str | None = Query(None),
    comparacao: str = Query("previous_period", pattern="^(none|previous_period|previous_month|previous_year)$"),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    payload = _dashboard(db, scope, inicio, fim, departamento, operador, canal, status, tabulacao, comparacao, "month")
    return {key: payload[key] for key in ("period", "summary", "comparison", "comparison_mode", "comparison_period", "deltas_pct", "last_sync")}


@router.get("/api/dadm/tallos/timeline")
def dadm_tallos_timeline(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), operador: str | None = Query(None),
    canal: str | None = Query(None), status: str | None = Query(None), tabulacao: str | None = Query(None),
    granularidade: str = Query("month", pattern="^(month|day)$"),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    payload = _dashboard(db, scope, inicio, fim, departamento, operador, canal, status, tabulacao, "none", granularidade)
    return {"period": payload["period"], "items": payload["timeline"]}


@router.get("/api/dadm/tallos/operators")
def dadm_tallos_operators(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), canal: str | None = Query(None),
    status: str | None = Query(None), tabulacao: str | None = Query(None),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    payload = _dashboard(db, scope, inicio, fim, departamento, None, canal, status, tabulacao, "none", "month")
    return {"period": payload["period"], "items": payload["operators"]}


@router.get("/api/dadm/tallos/departments")
def dadm_tallos_departments(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    operador: str | None = Query(None), canal: str | None = Query(None),
    status: str | None = Query(None), tabulacao: str | None = Query(None),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    payload = _dashboard(db, scope, inicio, fim, None, operador, canal, status, tabulacao, "none", "month")
    return {"period": payload["period"], "items": payload["departments"]}


@router.get("/api/dadm/tallos/ratings")
def dadm_tallos_ratings(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), operador: str | None = Query(None),
    canal: str | None = Query(None), status: str | None = Query(None), tabulacao: str | None = Query(None),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    payload = _dashboard(db, scope, inicio, fim, departamento, operador, canal, status, tabulacao, "none", "month")
    return {"period": payload["period"], "summary": payload["summary"], "items": payload["ratings"]}


@router.get("/api/dadm/tallos/rating-audit")
def dadm_tallos_rating_audit(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), operador: str | None = Query(None),
    canal: str | None = Query(None), status: str | None = Query(None),
    tabulacao: str | None = Query(None),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    _require_department(scope, departamento)
    start, end = _dates(inicio, fim)
    return rating_audit_payload(
        db, scope.directorate_id, start, end,
        employee=operador, department=departamento, channel=canal,
        status=status, tabulation=tabulacao,
        allowed_departments=_allowed_departments(scope),
    )


@router.get("/api/dadm/tallos/channels")
def dadm_tallos_channels(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), operador: str | None = Query(None),
    status: str | None = Query(None), tabulacao: str | None = Query(None),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    payload = _dashboard(db, scope, inicio, fim, departamento, operador, None, status, tabulacao, "none", "month")
    return {"period": payload["period"], "items": payload["channels"]}


@router.get("/api/dadm/tallos/operator-comparison")
def dadm_tallos_operator_comparison(
    operadores: str = Query(..., description="IDs separados por vírgula; máximo 6"),
    metrica: str = Query("tma", pattern="^(volume|protocols|tma|tme|rating)$"),
    inicio: date | None = Query(None), fim: date | None = Query(None),
    departamento: str | None = Query(None), canal: str | None = Query(None),
    status: str | None = Query(None), tabulacao: str | None = Query(None),
    db: Session = Depends(get_db), scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    _require_department(scope, departamento)
    start, end = _dates(inicio, fim)
    try:
        return operator_comparison(
            db, scope.directorate_id, start, end, operadores.split(","), metric=metrica,
            department=departamento, channel=canal, status=status, tabulation=tabulacao,
            allowed_departments=_allowed_departments(scope),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/dadm/tallos/sync-runs")
def dadm_tallos_sync_runs(
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    return {"items": DADMTallosRepository(db, scope).list_sync_runs(limit)}


@router.post("/api/dadm/tallos/sync")
def dadm_tallos_sync(
    background_tasks: BackgroundTasks,
    inicio: date = Query(...),
    fim: date = Query(...),
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    _require_dadm(scope)
    if fim < inicio:
        raise HTTPException(422, "A data final não pode ser anterior à data inicial.")
    if (fim - inicio).days > 366:
        raise HTTPException(422, "A sincronização manual aceita no máximo 367 dias por execução.")
    if not token_configured():
        raise HTTPException(503, "TALLOS_API_TOKEN não está configurado no backend.")
    repo = DADMTallosRepository(db, scope)
    active = repo.active_sync_run()
    if active:
        raise HTTPException(409, f"Já existe uma sincronização TALLOS em andamento (#{active.id}).")
    run = repo.create_sync_run(inicio, fim, trigger="manual", requested_by=scope.user.email)
    background_tasks.add_task(execute_sync_run, run.id)
    return {
        "ok": True,
        "run": repo.sync_run_payload(run),
        "mensagem": "Sincronização iniciada. Reexecutar o mesmo período é seguro: os registros usam UPSERT.",
    }


@router.get("/api/dadm/tallos/department-map")
def dadm_tallos_department_map(
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_access("DADM")),
):
    _require_dadm(scope)
    return {"items": DADMTallosRepository(db, scope).list_department_maps(allowed_departments=_allowed_departments(scope))}


@router.put("/api/dadm/tallos/department-map/{source_key:path}")
async def dadm_tallos_department_map_update(
    source_key: str,
    request: Request,
    db: Session = Depends(get_db),
    scope: DirectorateScope = Depends(require_directorate_edit("DADM")),
):
    _require_dadm(scope)
    _require_department(scope, source_key)
    payload = await request.json()
    try:
        row = DADMTallosRepository(db, scope).update_department_map(
            source_key,
            display_name=payload.get("display_name"),
            active=payload.get("active", True),
            notes=payload.get("notes"),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "item": row}
