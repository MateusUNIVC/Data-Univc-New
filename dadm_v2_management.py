from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth.objects import require_object_for_directorate
from auth.data_scopes import dadm_department_scope, department_allowed

from models import ManagementAction, ManagementTarget
from security import DirectorateScope

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

DADM_V2_METRICS: dict[str, dict[str, Any]] = {
    "tme_avg_seconds": {
        "indicator_code": "DADM-01",
        "label": "Tempo Médio de Espera (TME)",
        "unit": "seconds",
        "direction": "lower",
        "description": "Tempo médio até o início do atendimento.",
    },
    "tma_avg_seconds": {
        "indicator_code": "DADM-01",
        "label": "Tempo Médio de Atendimento (TMA)",
        "unit": "seconds",
        "direction": "lower",
        "description": "Duração média após o início do atendimento.",
    },
    "rating_avg": {
        "indicator_code": "DADM-02",
        "label": "Avaliação média",
        "unit": "rating_10",
        "direction": "higher",
        "description": "Média das avaliações válidas de 1 a 10.",
    },
    "rating_coverage_pct": {
        "indicator_code": "DADM-02",
        "label": "Cobertura das avaliações",
        "unit": "percent",
        "direction": "higher",
        "description": "Percentual de atendimentos com uma avaliação válida.",
    },
}

TARGET_SCOPE_TYPES = {
    "TOTAL": "Institucional",
    "department": "Departamento",
    "channel": "Canal",
}
ACTION_SCOPE_TYPES = {
    **TARGET_SCOPE_TYPES,
    "employee": "Operador",
}
V2_METRIC_KEYS = tuple(DADM_V2_METRICS)


def _require_dadm(scope: DirectorateScope) -> None:
    if scope.directorate_code != "DADM":
        raise ValueError("Esta configuração pertence exclusivamente à DADM.")




def _allowed_departments(scope: DirectorateScope) -> tuple[str, ...] | None:
    return dadm_department_scope(scope.user.email, global_access=scope.user.global_access)


def _restricted(scope: DirectorateScope) -> bool:
    return _allowed_departments(scope) is not None


def _row_visible_to_scope(scope: DirectorateScope, dimension_key: str, dimension_label: str, *, allow_total: bool = True) -> bool:
    allowed = _allowed_departments(scope)
    if allowed is None:
        return True
    kind, value = _decode_scope(str(dimension_key or ""), str(dimension_label or ""))
    if allow_total and kind == "TOTAL":
        return True
    return kind == "department" and department_allowed(value, allowed)


def _require_department_management_scope(scope: DirectorateScope, scope_type: str, scope_value: str | None) -> None:
    allowed = _allowed_departments(scope)
    if allowed is None:
        return
    if str(scope_type or "").strip() != "department" or not department_allowed(scope_value, allowed):
        raise PermissionError("Seu acesso permite alterar metas e planos apenas nos departamentos autorizados.")

def _month(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not MONTH_RE.fullmatch(text):
        raise ValueError(f"{field} deve usar o formato AAAA-MM.")
    return text


def _optional_month(value: Any, field: str) -> str | None:
    text = str(value or "").strip()
    return _month(text, field) if text else None


def _number(value: Any, field: str, *, required: bool = False) -> float | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"Informe {field}.")
        return None
    try:
        result = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} deve ser numérico.") from exc
    if result != result or abs(result) == float("inf"):
        raise ValueError(f"{field} deve ser numérico.")
    return result


def _metric(metric_key: Any, *, indicator_code: Any | None = None) -> tuple[str, dict[str, Any]]:
    key = str(metric_key or "").strip()
    spec = DADM_V2_METRICS.get(key)
    if not spec:
        raise ValueError("Métrica TALLOS V2 inválida.")
    if indicator_code and str(indicator_code).strip().upper() != spec["indicator_code"]:
        raise ValueError("A métrica não pertence ao indicador informado.")
    return key, spec


def _scope(scope_type: Any, scope_value: Any, *, action: bool = False) -> tuple[str, str, str, str | None]:
    allowed = ACTION_SCOPE_TYPES if action else TARGET_SCOPE_TYPES
    kind = str(scope_type or "TOTAL").strip()
    if kind not in allowed:
        raise ValueError("Recorte de gestão inválido.")
    if kind == "TOTAL":
        return "V2:TOTAL", "Institucional", "TOTAL", None
    value = str(scope_value or "").strip()
    if not value:
        raise ValueError(f"Informe o valor do recorte {allowed[kind].lower()}.")
    if len(value) > 180:
        raise ValueError("O valor do recorte deve ter no máximo 180 caracteres.")
    digest = hashlib.sha256(f"dadm-v2|{kind}|{value}".encode("utf-8")).hexdigest()[:40]
    return f"V2:{kind}:{digest}", f"{allowed[kind]}: {value}", kind, value


def _decode_scope(dimension_key: str, dimension_label: str) -> tuple[str, str | None]:
    if dimension_key in {"TOTAL", "V2:TOTAL"}:
        return "TOTAL", None
    if dimension_key.startswith("V2:"):
        parts = dimension_key.split(":", 2)
        kind = parts[1] if len(parts) > 1 else "TOTAL"
        prefix = f"{ACTION_SCOPE_TYPES.get(kind, kind)}: "
        if dimension_label.startswith(prefix):
            return kind, dimension_label[len(prefix):]
        return kind, dimension_label
    return "legacy", dimension_label


def _target_dict(row: ManagementTarget) -> dict[str, Any]:
    scope_type, scope_value = _decode_scope(row.dimension_key, row.dimension_label)
    return {
        "id": row.id,
        "indicator_code": row.indicator_code,
        "metric_key": row.metric_key,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "scope_label": row.dimension_label,
        "valid_from": row.valid_from,
        "valid_to": row.valid_to,
        "target": row.target,
        "attention": row.attention,
        "justification": row.justification,
        "inserted_at": row.inserted_at.isoformat() if row.inserted_at else None,
        "inserted_by": row.inserted_by,
    }


def _action_dict(row: ManagementAction) -> dict[str, Any]:
    scope_type, scope_value = _decode_scope(row.dimension_key, row.dimension_label)
    return {
        "id": row.id,
        "indicator_code": row.indicator_code,
        "metric_key": row.metric_key,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "scope_label": row.dimension_label,
        "period": row.period,
        "problem": row.problem,
        "probable_cause": row.probable_cause,
        "corrective_action": row.corrective_action,
        "responsible": row.responsible,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "status": row.status,
        "evidence": row.evidence,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_by": row.created_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _targets(db: Session, directorate_id: int) -> list[ManagementTarget]:
    return list(db.scalars(
        select(ManagementTarget)
        .where(
            ManagementTarget.directorate_id == directorate_id,
            ManagementTarget.metric_key.in_(V2_METRIC_KEYS),
        )
        .order_by(ManagementTarget.indicator_code, ManagementTarget.metric_key, ManagementTarget.valid_from.desc())
    ).all())


def _actions(db: Session, directorate_id: int) -> list[ManagementAction]:
    return list(db.scalars(
        select(ManagementAction)
        .where(
            ManagementAction.directorate_id == directorate_id,
            ManagementAction.metric_key.in_(V2_METRIC_KEYS),
        )
        .order_by(ManagementAction.due_date, ManagementAction.id)
    ).all())


def _active_target(
    rows: list[ManagementTarget], metric_key: str, month: str,
    *, department: str | None = None, channel: str | None = None,
) -> ManagementTarget | None:
    candidate_keys = []
    if department:
        candidate_keys.append(_scope("department", department)[0])
    if channel:
        candidate_keys.append(_scope("channel", channel)[0])
    candidate_keys.extend(["V2:TOTAL", "TOTAL"])
    month_key = int(month[:4]) * 12 + int(month[5:7])
    for dimension_key in candidate_keys:
        candidates = []
        for row in rows:
            if row.metric_key != metric_key or row.dimension_key != dimension_key:
                continue
            start_key = int(row.valid_from[:4]) * 12 + int(row.valid_from[5:7])
            end_key = int(row.valid_to[:4]) * 12 + int(row.valid_to[5:7]) if row.valid_to else 10**9
            if start_key <= month_key <= end_key:
                candidates.append(row)
        if candidates:
            return max(candidates, key=lambda row: row.valid_from)
    return None


def management_payload(
    db: Session,
    scope: DirectorateScope,
    *,
    month: str,
    department: str | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    _require_dadm(scope)
    month = _month(month, "O mês de referência")
    if department and not department_allowed(department, _allowed_departments(scope)):
        raise PermissionError("Este departamento não faz parte do seu escopo de dados na DADM.")
    target_rows = _targets(db, scope.directorate_id)
    action_rows = _actions(db, scope.directorate_id)
    if _restricted(scope):
        target_rows = [row for row in target_rows if _row_visible_to_scope(scope, row.dimension_key, row.dimension_label, allow_total=True)]
        action_rows = [row for row in action_rows if _row_visible_to_scope(scope, row.dimension_key, row.dimension_label, allow_total=False)]
    active = {}
    for key in V2_METRIC_KEYS:
        row = _active_target(target_rows, key, month, department=department, channel=channel)
        active[key] = _target_dict(row) if row else None
    return {
        "catalog": {
            "metrics": [{"key": key, **spec} for key, spec in DADM_V2_METRICS.items()],
            "target_scope_types": [{"value": key, "label": label} for key, label in TARGET_SCOPE_TYPES.items()],
            "action_scope_types": [{"value": key, "label": label} for key, label in ACTION_SCOPE_TYPES.items()],
        },
        "reference_month": month,
        "active_targets": active,
        "targets": [_target_dict(row) for row in target_rows],
        "actions": [_action_dict(row) for row in action_rows],
    }


def save_target(db: Session, scope: DirectorateScope, payload: dict[str, Any], *, row_id: int | None = None) -> dict[str, Any]:
    _require_dadm(scope)
    metric_key, metric = _metric(payload.get("metric_key"), indicator_code=payload.get("indicator_code"))
    valid_from = _month(payload.get("valid_from"), "A vigência inicial")
    valid_to = _optional_month(payload.get("valid_to"), "A vigência final")
    if valid_to and valid_to < valid_from:
        raise ValueError("A vigência final não pode ser anterior à inicial.")
    scope_type = str(payload.get("scope_type") or "TOTAL").strip()
    scope_value = str(payload.get("scope_value") or "").strip() or None
    _require_department_management_scope(scope, scope_type, scope_value)
    dimension_key, dimension_label, _, _ = _scope(scope_type, scope_value)
    target = _number(payload.get("target"), "o valor da meta", required=True)
    attention = _number(payload.get("attention"), "a faixa de atenção")
    if metric["unit"] == "rating_10":
        if target is not None and not 1 <= target <= 10:
            raise ValueError("A meta de avaliação deve ficar entre 1 e 10.")
        if attention is not None and not 1 <= attention <= 10:
            raise ValueError("A faixa de atenção da avaliação deve ficar entre 1 e 10.")
    if metric["unit"] == "percent":
        if target is not None and not 0 <= target <= 100:
            raise ValueError("A meta percentual deve ficar entre 0 e 100.")
        if attention is not None and not 0 <= attention <= 100:
            raise ValueError("A faixa de atenção percentual deve ficar entre 0 e 100.")
    if metric["unit"] == "seconds":
        if target is not None and target < 0:
            raise ValueError("A meta de tempo não pode ser negativa.")
        if attention is not None and attention < 0:
            raise ValueError("A faixa de atenção de tempo não pode ser negativa.")
    if attention is not None:
        if metric["direction"] == "lower" and attention < target:
            raise ValueError("Para métricas em que menor é melhor, a faixa de atenção deve ser igual ou maior que a meta.")
        if metric["direction"] == "higher" and attention > target:
            raise ValueError("Para métricas em que maior é melhor, a faixa de atenção deve ser igual ou menor que a meta.")

    row = (
        require_object_for_directorate(db, ManagementTarget, row_id, scope.directorate_id, label="Meta TALLOS V2")
        if row_id
        else None
    )
    if row is not None and row.metric_key not in V2_METRIC_KEYS:
        raise LookupError("Meta TALLOS V2 não encontrada.")
    if row is not None and not _row_visible_to_scope(scope, row.dimension_key, row.dimension_label, allow_total=False):
        raise PermissionError("Esta meta pertence a um departamento fora do seu escopo.")
    duplicate = db.scalar(
        select(ManagementTarget).where(
            ManagementTarget.directorate_id == scope.directorate_id,
            ManagementTarget.indicator_code == metric["indicator_code"],
            ManagementTarget.metric_key == metric_key,
            ManagementTarget.dimension_key == dimension_key,
            ManagementTarget.valid_from == valid_from,
            *( [ManagementTarget.id != row.id] if row is not None else [] ),
        )
    )
    if duplicate:
        raise ValueError("Já existe uma meta para esta métrica, recorte e vigência inicial.")
    if row is None:
        row = ManagementTarget(directorate_id=scope.directorate_id)
        db.add(row)
    row.indicator_code = metric["indicator_code"]
    row.metric_key = metric_key
    row.dimension_key = dimension_key
    row.dimension_label = dimension_label
    row.valid_from = valid_from
    row.valid_to = valid_to
    row.target = target
    row.attention = attention
    row.target_min = None
    row.target_max = None
    row.attention_min = None
    row.attention_max = None
    row.justification = str(payload.get("justification") or "").strip() or None
    row.inserted_by = scope.user.email
    db.commit()
    db.refresh(row)
    return _target_dict(row)


def delete_target(db: Session, scope: DirectorateScope, row_id: int) -> None:
    _require_dadm(scope)
    row = require_object_for_directorate(db, ManagementTarget, row_id, scope.directorate_id, label="Meta TALLOS V2")
    if row.metric_key not in V2_METRIC_KEYS:
        raise LookupError("Meta TALLOS V2 não encontrada.")
    if not _row_visible_to_scope(scope, row.dimension_key, row.dimension_label, allow_total=False):
        raise PermissionError("Esta meta pertence a um departamento fora do seu escopo.")
    db.delete(row)
    db.commit()


def save_action(db: Session, scope: DirectorateScope, payload: dict[str, Any], *, row_id: int | None = None) -> dict[str, Any]:
    _require_dadm(scope)
    metric_key, metric = _metric(payload.get("metric_key"), indicator_code=payload.get("indicator_code"))
    period = _month(payload.get("period"), "O período")
    scope_type = str(payload.get("scope_type") or "TOTAL").strip()
    scope_value = str(payload.get("scope_value") or "").strip() or None
    _require_department_management_scope(scope, scope_type, scope_value)
    dimension_key, dimension_label, _, _ = _scope(scope_type, scope_value, action=True)
    required = {
        "problem": "Descreva o problema.",
        "corrective_action": "Descreva a ação corretiva.",
        "responsible": "Informe o responsável.",
        "due_date": "Informe o prazo.",
    }
    for field, message in required.items():
        if not str(payload.get(field) or "").strip():
            raise ValueError(message)
    try:
        due = date.fromisoformat(str(payload.get("due_date")))
    except ValueError as exc:
        raise ValueError("O prazo deve usar uma data válida.") from exc

    row = (
        require_object_for_directorate(db, ManagementAction, row_id, scope.directorate_id, label="Plano de ação TALLOS V2")
        if row_id
        else None
    )
    if row is not None and row.metric_key not in V2_METRIC_KEYS:
        raise LookupError("Plano de ação TALLOS V2 não encontrado.")
    if row is not None and not _row_visible_to_scope(scope, row.dimension_key, row.dimension_label, allow_total=False):
        raise PermissionError("Este plano pertence a um departamento fora do seu escopo.")
    if row is None:
        row = ManagementAction(directorate_id=scope.directorate_id)
        db.add(row)
    row.indicator_code = metric["indicator_code"]
    row.metric_key = metric_key
    row.period = period
    row.dimension_key = dimension_key
    row.dimension_label = dimension_label
    row.problem = str(payload.get("problem")).strip()
    row.probable_cause = str(payload.get("probable_cause") or "").strip() or None
    row.corrective_action = str(payload.get("corrective_action")).strip()
    row.responsible = str(payload.get("responsible")).strip()
    row.due_date = due
    status = str(payload.get("status") or "Aberto").strip()
    if status not in {"Aberto", "Em andamento", "Concluído", "Atrasado", "Cancelado"}:
        raise ValueError("Status do plano de ação inválido.")
    row.status = status
    row.evidence = str(payload.get("evidence") or "").strip() or None
    if row.created_by is None:
        row.created_by = scope.user.email
    db.commit()
    db.refresh(row)
    return _action_dict(row)


def delete_action(db: Session, scope: DirectorateScope, row_id: int) -> None:
    _require_dadm(scope)
    row = require_object_for_directorate(db, ManagementAction, row_id, scope.directorate_id, label="Plano de ação TALLOS V2")
    if row.metric_key not in V2_METRIC_KEYS:
        raise LookupError("Plano de ação TALLOS V2 não encontrado.")
    if not _row_visible_to_scope(scope, row.dimension_key, row.dimension_label, allow_total=False):
        raise PermissionError("Este plano pertence a um departamento fora do seu escopo.")
    db.delete(row)
    db.commit()
