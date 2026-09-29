from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Iterable
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit
from dpe_course_context import snapshot_context_label
from dpe_revenue_facts import revenue_facts
from models import (
    DPEAllocationPolicy,
    DPEAllocationRule,
    DPECostAllocationIssue,
    DPECostAllocationResult,
    DPECostAllocationRun,
    DPECostExpense,
    DPECostExpenseAllocationTarget,
    DPECostOfferingEconomics,
    DPECostPeriod,
    DPECostPeriodOffering,
    DPECostPeriodOfferingDriverValue,
    DPECostTeachingActivity,
    DPECostTeachingActivityOffering,
    DPEExpenseCategory,
    DPERevenueEntry,
)
from security import DirectorateScope

EDITABLE_PERIOD_STATUSES = ("DRAFT", "REVIEW")
DRIVER_TYPES = ("DIRECT", "TEACHER_HOURS", "OFFERING_HOURS", "STUDENTS", "REVENUE", "EQUAL", "MANUAL")
DRIVER_METRICS = ("OFFERING_HOURS", "STUDENTS", "REVENUE")
MANUAL_DRIVER_METRICS = ("OFFERING_HOURS",)
DRIVER_SOURCES = ("MANUAL", "DERIVED", "IMPORT", "SYSTEM")
CENT = Decimal("0.01")
ONE_HUNDRED = Decimal("100")


class DPECostAllocationValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _text(value: Any, *, max_length: int | None = None) -> str:
    output = str(value or "").strip()
    return output[:max_length] if max_length and len(output) > max_length else output


def _decimal(value: Any, field: str, *, allow_none: bool = False, scale: str = "0.000001") -> Decimal | None:
    if value in (None, "") and allow_none:
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(".", "").replace(",", ".") if "," in value else value.strip()
        output = Decimal(str(value)).quantize(Decimal(scale), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DPECostAllocationValidationError("Valor inválido.", {field: "Informe um número válido."}) from exc
    if output < 0:
        raise DPECostAllocationValidationError("Valor inválido.", {field: "O valor não pode ser negativo."})
    return output


def _money(value: Any) -> Decimal:
    result = _decimal(value, "amount", scale="0.01")
    assert result is not None
    return result


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value else None)


def _policy_match_key(value: Any) -> str:
    text = " ".join(str(value or "").strip().casefold().split())
    return text[:255]


def _offering_label(snapshot: dict[str, Any]) -> str:
    return snapshot_context_label(snapshot)


def _split_amount(amount: Decimal, weights: list[tuple[int, Decimal]]) -> dict[int, Decimal]:
    """Split exact cents proportionally using the largest-remainder method."""
    amount = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    positive = [(key, Decimal(weight)) for key, weight in weights if Decimal(weight) > 0]
    denominator = sum((weight for _, weight in positive), Decimal("0"))
    if denominator <= 0:
        return {}
    cents_total = int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))
    floors: dict[int, int] = {}
    remainders: list[tuple[Decimal, int]] = []
    assigned = 0
    for key, weight in positive:
        raw = Decimal(cents_total) * weight / denominator
        floor_cents = int(raw.to_integral_value(rounding=ROUND_DOWN))
        floors[key] = floor_cents
        assigned += floor_cents
        remainders.append((raw - Decimal(floor_cents), key))
    remaining = cents_total - assigned
    remainders.sort(key=lambda item: (-item[0], item[1]))
    for _, key in remainders[:remaining]:
        floors[key] += 1
    return {key: (Decimal(cents) / Decimal(100)).quantize(CENT) for key, cents in floors.items()}


class DPECostAllocationRepository:
    """Versioned, auditable cost allocation engine for DPE competences."""

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A Distribuição de Custos pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    @property
    def actor(self) -> str:
        return self.scope.user.email or self.scope.user.full_name or self.scope.user.user_id

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DPECostAllocationValidationError(
                "Não foi possível salvar a configuração de distribuição porque existe um registro equivalente ou referência inválida."
            ) from exc

    def _period(self, period_id: int, *, editable: bool = False) -> DPECostPeriod:
        row = self.db.scalar(
            select(DPECostPeriod).where(
                DPECostPeriod.id == int(period_id),
                DPECostPeriod.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Competência do Cost Engine não encontrada.")
        if editable and row.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostAllocationValidationError(
                "A competência já possui cálculo oficial ou está fechada e não aceita nova configuração de distribuição."
            )
        return row

    def _expense(self, expense_id: int, *, editable: bool = False) -> DPECostExpense:
        row = self.db.scalar(
            select(DPECostExpense).where(
                DPECostExpense.id == int(expense_id),
                DPECostExpense.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Despesa do Cost Engine não encontrada.")
        if editable:
            self._period(row.period_id, editable=True)
            if row.status != "ACTIVE":
                raise DPECostAllocationValidationError("Uma despesa estornada não pode receber configuração de distribuição.")
        return row

    def _period_offerings(self, period_id: int) -> list[DPECostPeriodOffering]:
        return self.db.scalars(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            ).order_by(DPECostPeriodOffering.id)
        ).all()

    def _offering(self, period_id: int, period_offering_id: int) -> DPECostPeriodOffering:
        row = self.db.scalar(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.id == int(period_offering_id),
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            )
        )
        if not row:
            raise DPECostAllocationValidationError(
                "Curso/contexto inválido para a competência.", {"period_offering_id": "Selecione um curso/contexto incluído neste mês."}
            )
        return row

    def _rule(self, rule_id: int | None) -> DPEAllocationRule | None:
        if not rule_id:
            return None
        return self.db.scalar(
            select(DPEAllocationRule).where(
                DPEAllocationRule.id == int(rule_id),
                DPEAllocationRule.directorate_id == self.directorate_id,
            )
        )

    def _derived_offering_hours(self, period_id: int) -> dict[int, Decimal]:
        rows = self.db.execute(
            select(
                DPECostTeachingActivityOffering.period_offering_id,
                func.coalesce(func.sum(DPECostTeachingActivityOffering.allocated_hours), 0),
            )
            .join(
                DPECostTeachingActivity,
                DPECostTeachingActivity.id == DPECostTeachingActivityOffering.activity_id,
            )
            .where(
                DPECostTeachingActivity.directorate_id == self.directorate_id,
                DPECostTeachingActivity.period_id == int(period_id),
                DPECostTeachingActivity.status == "ACTIVE",
            )
            .group_by(DPECostTeachingActivityOffering.period_offering_id)
        ).all()
        return {int(offering_id): Decimal(str(value or 0)) for offering_id, value in rows}

    def list_driver_values(self, period_id: int) -> list[dict[str, Any]]:
        period = self._period(period_id)
        offerings = self._period_offerings(period.id)
        explicit_rows = self.db.scalars(
            select(DPECostPeriodOfferingDriverValue).where(
                DPECostPeriodOfferingDriverValue.directorate_id == self.directorate_id,
                DPECostPeriodOfferingDriverValue.period_id == period.id,
            )
        ).all()
        explicit: dict[tuple[int, str], DPECostPeriodOfferingDriverValue] = {
            (row.period_offering_id, row.metric_type): row for row in explicit_rows
        }
        economics_rows = self.db.scalars(
            select(DPECostOfferingEconomics).where(
                DPECostOfferingEconomics.directorate_id == self.directorate_id,
                DPECostOfferingEconomics.period_id == period.id,
            )
        ).all()
        economics = {row.period_offering_id: row for row in economics_rows}
        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        derived_hours = self._derived_offering_hours(period.id)
        output: list[dict[str, Any]] = []
        for offering in offerings:
            metrics: dict[str, Any] = {}
            economic = economics.get(offering.id)
            for metric in DRIVER_METRICS:
                row = explicit.get((offering.id, metric))
                derived = derived_hours.get(offering.id, Decimal("0")) if metric == "OFFERING_HOURS" else None
                official = None
                if metric == "STUDENTS" and economic and economic.active_students is not None:
                    official = Decimal(str(economic.active_students))
                elif metric == "REVENUE" and revenues.is_confirmed(offering.id):
                    official = revenues.attributed(offering.id)
                if official is not None:
                    effective = official
                    source_type = "REVENUE_LEDGER" if metric == "REVENUE" else "ECONOMIC"
                elif row and metric != "REVENUE":
                    effective = Decimal(row.value)
                    source_type = row.source_type
                else:
                    effective = derived
                    source_type = "DERIVED" if metric == "OFFERING_HOURS" else None
                metrics[metric] = {
                    "explicit_value": float(row.value) if row else None,
                    "official_value": float(official) if official is not None else None,
                    "effective_value": float(effective) if effective is not None else None,
                    "source_type": source_type,
                    "notes": row.notes if row else None,
                    "derived_value": float(derived) if derived is not None else None,
                }
            output.append({
                "period_offering_id": offering.id,
                "offering_id": offering.offering_id,
                "label": _offering_label(dict(offering.offering_snapshot_json or {})),
                "snapshot": dict(offering.offering_snapshot_json or {}),
                "metrics": metrics,
            })
        return output

    def upsert_driver_values(self, period_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        values = payload.get("values")
        if not isinstance(values, list):
            raise DPECostAllocationValidationError("Informe a lista de bases de distribuição.", {"values": "Lista obrigatória."})
        for item in values:
            if not isinstance(item, dict):
                continue
            period_offering_id = int(item.get("period_offering_id") or 0)
            offering = self._offering(period.id, period_offering_id)
            metric_type = _text(item.get("metric_type")).upper()
            if metric_type not in DRIVER_METRICS:
                raise DPECostAllocationValidationError("Base de distribuição inválida.", {"metric_type": "Indicador não reconhecido."})
            if metric_type not in MANUAL_DRIVER_METRICS:
                raise DPECostAllocationValidationError(
                    "Alunos e receita pertencem à base econômica oficial do curso/contexto.",
                    {"metric_type": "Edite estes dados em Receita, alunos e ticket médio."},
                )
            marker = item.get("value")
            existing = self.db.scalar(
                select(DPECostPeriodOfferingDriverValue).where(
                    DPECostPeriodOfferingDriverValue.period_offering_id == offering.id,
                    DPECostPeriodOfferingDriverValue.metric_type == metric_type,
                )
            )
            if marker in (None, ""):
                if existing:
                    self.db.delete(existing)
                continue
            value = _decimal(marker, "value")
            assert value is not None
            source_type = _text(item.get("source_type") or "MANUAL").upper()
            if source_type not in DRIVER_SOURCES:
                source_type = "MANUAL"
            if not existing:
                existing = DPECostPeriodOfferingDriverValue(
                    directorate_id=self.directorate_id,
                    period_id=period.id,
                    period_offering_id=offering.id,
                    metric_type=metric_type,
                    value=value,
                    source_type=source_type,
                    notes=_text(item.get("notes")) or None,
                    created_by=self.actor,
                    updated_by=self.actor,
                )
                self.db.add(existing)
            else:
                existing.value = value
                existing.source_type = source_type
                existing.notes = _text(item.get("notes")) or None
                existing.updated_by = self.actor
        self._commit()
        return {"period_id": period.id, "items": self.list_driver_values(period.id)}

    def _policy(self, policy_id: int | None) -> DPEAllocationPolicy | None:
        if not policy_id:
            return None
        return self.db.scalar(
            select(DPEAllocationPolicy).where(
                DPEAllocationPolicy.id == int(policy_id),
                DPEAllocationPolicy.directorate_id == self.directorate_id,
            )
        )

    def _policy_payload(self, policy: DPEAllocationPolicy, *, period_id: int | None = None) -> dict[str, Any]:
        rule = self._rule(policy.allocation_rule_id)
        raw_targets = list(policy.target_offerings_json or [])
        resolved_targets: list[dict[str, Any]] = []
        missing_targets: list[dict[str, Any]] = []
        labels_by_offering: dict[int, str] = {}
        period_map: dict[int, DPECostPeriodOffering] = {}
        if period_id:
            for row in self._period_offerings(period_id):
                period_map[int(row.offering_id)] = row
                labels_by_offering[int(row.offering_id)] = _offering_label(dict(row.offering_snapshot_json or {}))
        for target in raw_targets:
            if not isinstance(target, dict):
                continue
            offering_id = int(target.get("offering_id") or 0)
            if not offering_id:
                continue
            row = period_map.get(offering_id) if period_id else None
            item = {
                "offering_id": offering_id,
                "period_offering_id": row.id if row else None,
                "label": labels_by_offering.get(offering_id) or target.get("label") or f"Curso/contexto {offering_id}",
                "manual_percentage": target.get("manual_percentage"),
            }
            if period_id and not row:
                missing_targets.append(item)
            else:
                resolved_targets.append(item)
        return {
            "id": policy.id,
            "name": policy.name,
            "allocation_rule_id": policy.allocation_rule_id,
            "rule": None if not rule else {
                "id": rule.id,
                "code": rule.code,
                "name": rule.name,
                "driver_type": rule.driver_type,
                "description": rule.description,
            },
            "scope_type": policy.scope_type,
            "targets": resolved_targets,
            "missing_targets": missing_targets,
            "match_description": policy.match_description,
            "source_category_id": policy.source_category_id,
            "auto_suggest": bool(policy.auto_suggest),
            "notes": policy.notes,
            "active": bool(policy.active),
            "created_at": _iso(policy.created_at),
            "updated_at": _iso(policy.updated_at),
            "applicable": not bool(missing_targets),
        }

    def list_policies(self, *, active_only: bool = True, period_id: int | None = None) -> list[dict[str, Any]]:
        stmt = select(DPEAllocationPolicy).where(DPEAllocationPolicy.directorate_id == self.directorate_id)
        if active_only:
            stmt = stmt.where(DPEAllocationPolicy.active.is_(True))
        rows = self.db.scalars(stmt.order_by(DPEAllocationPolicy.active.desc(), DPEAllocationPolicy.name)).all()
        if period_id:
            self._period(period_id)
        return [self._policy_payload(row, period_id=period_id) for row in rows]

    def _suggested_policy(self, expense: DPECostExpense) -> DPEAllocationPolicy | None:
        key = _policy_match_key(expense.description)
        if not key:
            return None
        rows = self.db.scalars(
            select(DPEAllocationPolicy).where(
                DPEAllocationPolicy.directorate_id == self.directorate_id,
                DPEAllocationPolicy.active.is_(True),
                DPEAllocationPolicy.auto_suggest.is_(True),
            ).order_by(DPEAllocationPolicy.updated_at.desc(), DPEAllocationPolicy.id.desc())
        ).all()
        for row in rows:
            if _policy_match_key(row.match_description) == key:
                return row
        return None

    def create_policy_from_expense(self, expense_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expense = self._expense(expense_id, editable=True)
        name = _text(payload.get("name"), max_length=180)
        if not name:
            raise DPECostAllocationValidationError("Informe um nome para a política.", {"name": "Nome obrigatório."})
        draft = payload.get("config") if isinstance(payload.get("config"), dict) else None
        if draft:
            rule = self._rule(int(draft.get("allocation_rule_id") or 0) or None)
            targets = self._preview_targets(expense, draft)
        else:
            rule = self._rule(expense.allocation_rule_id)
            targets = self._targets(expense.id)
        if not rule:
            raise DPECostAllocationValidationError("Escolha um critério antes de criar a política.")
        period_offerings = {row.id: row for row in self._period_offerings(expense.period_id)}
        stored_targets: list[dict[str, Any]] = []
        scope_type = "SPECIFIC" if targets else "ALL"
        if rule.driver_type == "DIRECT" and len(targets) != 1:
            raise DPECostAllocationValidationError("Uma política de destino direto precisa ter exatamente um curso.")
        if rule.driver_type in {"OFFERING_HOURS", "STUDENTS", "REVENUE", "EQUAL"} and draft and draft.get("targets") and not targets:
            raise DPECostAllocationValidationError("A política específica precisa ter pelo menos um curso.")
        if rule.driver_type == "MANUAL":
            if not targets:
                raise DPECostAllocationValidationError("Uma política manual precisa ter cursos definidos.")
            total = Decimal("0")
            for target in targets:
                row = period_offerings.get(target.period_offering_id)
                if not row:
                    continue
                if target.manual_percentage is not None:
                    percentage = Decimal(target.manual_percentage)
                elif target.manual_amount is not None:
                    percentage = (Decimal(target.manual_amount) / Decimal(expense.amount) * ONE_HUNDRED) if Decimal(expense.amount) else Decimal("0")
                else:
                    raise DPECostAllocationValidationError("Complete a divisão manual antes de salvar como política.")
                total += percentage
                stored_targets.append({
                    "offering_id": row.offering_id,
                    "label": _offering_label(dict(row.offering_snapshot_json or {})),
                    "manual_percentage": float(percentage.quantize(Decimal("0.0001"))),
                })
            if abs(total - ONE_HUNDRED) > Decimal("0.0001"):
                raise DPECostAllocationValidationError("A política manual precisa totalizar 100%.")
        else:
            for target in targets:
                row = period_offerings.get(target.period_offering_id)
                if row:
                    stored_targets.append({
                        "offering_id": row.offering_id,
                        "label": _offering_label(dict(row.offering_snapshot_json or {})),
                    })
        if rule.driver_type == "TEACHER_HOURS":
            scope_type = "ALL"
            stored_targets = []
        auto_suggest = bool(payload.get("auto_suggest", True))
        policy = DPEAllocationPolicy(
            directorate_id=self.directorate_id,
            name=name,
            allocation_rule_id=rule.id,
            scope_type=scope_type,
            target_offerings_json=stored_targets,
            match_description=expense.description if auto_suggest else None,
            source_category_id=expense.category_id,
            auto_suggest=auto_suggest,
            notes=_text(payload.get("notes")) or None,
            active=True,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.db.add(policy)
        self.db.flush()
        add_dpe_audit(
            self.db,
            self.scope,
            action="create_policy",
            entity="dpe_allocation_policy",
            entity_id=policy.id,
            period_id=expense.period_id,
            after=self._policy_payload(policy, period_id=expense.period_id),
            metadata={"source_expense_id": expense.id},
        )
        self._commit()
        self.db.refresh(policy)
        return self._policy_payload(policy, period_id=expense.period_id)

    def update_policy(self, policy_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        policy = self._policy(policy_id)
        if not policy:
            raise LookupError("Política de distribuição não encontrada.")
        before = self._policy_payload(policy, period_id=int(payload.get("period_id") or 0) or None)
        if "name" in payload:
            name = _text(payload.get("name"), max_length=180)
            if not name:
                raise DPECostAllocationValidationError("Informe um nome para a política.", {"name": "Nome obrigatório."})
            policy.name = name
        if "active" in payload:
            policy.active = bool(payload.get("active"))
        if "auto_suggest" in payload:
            policy.auto_suggest = bool(payload.get("auto_suggest"))
            if not policy.auto_suggest:
                policy.match_description = None
        if "match_description" in payload and policy.auto_suggest:
            policy.match_description = _text(payload.get("match_description"), max_length=255) or None
        if "notes" in payload:
            policy.notes = _text(payload.get("notes")) or None
        policy.updated_by = self.actor
        add_dpe_audit(
            self.db,
            self.scope,
            action="update_policy",
            entity="dpe_allocation_policy",
            entity_id=policy.id,
            period_id=int(payload.get("period_id") or 0) or None,
            before=before,
            after=self._policy_payload(policy, period_id=int(payload.get("period_id") or 0) or None),
        )
        self._commit()
        return self._policy_payload(policy, period_id=int(payload.get("period_id") or 0) or None)

    def resolve_policy_for_expense(self, expense_id: int, policy_id: int) -> dict[str, Any]:
        expense = self._expense(expense_id)
        policy = self._policy(policy_id)
        if not policy or not policy.active:
            raise DPECostAllocationValidationError("A política selecionada não está disponível.")
        payload = self._policy_payload(policy, period_id=expense.period_id)
        if not payload["applicable"]:
            raise DPECostAllocationValidationError(
                "A política possui cursos que não fazem parte desta competência.",
                {"policy_id": "Revise a política ou os cursos incluídos no mês."},
            )
        rule = payload["rule"]
        if not rule:
            raise DPECostAllocationValidationError("O critério desta política não está mais disponível.")
        if rule["driver_type"] == "TEACHER_HOURS" and expense.expense_kind != "PAYROLL":
            raise DPECostAllocationValidationError("Esta política de horas docentes só pode ser aplicada à folha.")
        targets = []
        for item in payload["targets"]:
            targets.append({
                "period_offering_id": item["period_offering_id"],
                "manual_percentage": item.get("manual_percentage") if rule["driver_type"] == "MANUAL" else None,
                "manual_amount": None,
            })
        return {
            "policy": payload,
            "config": {"allocation_rule_id": rule["id"], "targets": targets},
        }

    def expense_config(self, expense_id: int) -> dict[str, Any]:
        expense = self._expense(expense_id)
        period = self._period(expense.period_id)
        rule = self._rule(expense.allocation_rule_id)
        targets = self.db.scalars(
            select(DPECostExpenseAllocationTarget)
            .where(DPECostExpenseAllocationTarget.expense_id == expense.id)
            .order_by(DPECostExpenseAllocationTarget.period_offering_id)
        ).all()
        offerings = {row.id: row for row in self._period_offerings(period.id)}
        rules = self.db.scalars(
            select(DPEAllocationRule).where(
                DPEAllocationRule.directorate_id == self.directorate_id,
                DPEAllocationRule.active.is_(True),
            ).order_by(DPEAllocationRule.system_defined.desc(), DPEAllocationRule.name)
        ).all()
        policies = self.list_policies(active_only=True, period_id=period.id)
        suggested_policy = self._suggested_policy(expense)
        return {
            "expense_id": expense.id,
            "period_id": period.id,
            "period": period.period,
            "editable": period.status in EDITABLE_PERIOD_STATUSES and expense.status == "ACTIVE",
            "description": expense.description,
            "amount": float(expense.amount),
            "expense_kind": expense.expense_kind,
            "expense_scope": expense.expense_scope or "SHARED",
            "allocatable": (expense.expense_scope or "SHARED") != "INSTITUTIONAL",
            "period_teacher_id": expense.period_teacher_id,
            "classification": dict(expense.classification_snapshot_json or {}),
            "suggested_rule": dict((expense.classification_snapshot_json or {}).get("allocation_rule") or {}) or None,
            "rule": None if not rule else {
                "id": rule.id,
                "code": rule.code,
                "name": rule.name,
                "driver_type": rule.driver_type,
            },
            "rules": [
                {"id": item.id, "code": item.code, "name": item.name, "driver_type": item.driver_type, "description": item.description}
                for item in rules
            ],
            "policies": policies,
            "suggested_policy": (
                self._policy_payload(suggested_policy, period_id=period.id) if suggested_policy else None
            ),
            "targets": [
                {
                    "id": target.id,
                    "period_offering_id": target.period_offering_id,
                    "label": _offering_label(dict(offerings[target.period_offering_id].offering_snapshot_json or {}))
                    if target.period_offering_id in offerings else "Curso/contexto fora da competência",
                    "manual_amount": float(target.manual_amount) if target.manual_amount is not None else None,
                    "manual_percentage": float(target.manual_percentage) if target.manual_percentage is not None else None,
                    "notes": target.notes,
                }
                for target in targets
            ],
            "offerings": [
                {
                    "period_offering_id": row.id,
                    "label": _offering_label(dict(row.offering_snapshot_json or {})),
                    "snapshot": dict(row.offering_snapshot_json or {}),
                }
                for row in offerings.values()
            ],
        }

    def _apply_expense_config_no_commit(self, expense: DPECostExpense, payload: dict[str, Any]) -> None:
        scope = str(expense.expense_scope or "SHARED").upper()
        if scope == "INSTITUTIONAL":
            raise DPECostAllocationValidationError(
                "Despesa institucional não participa da distribuição entre cursos."
            )
        if "allocation_rule_id" in payload:
            rule_id = int(payload.get("allocation_rule_id") or 0) or None
            rule = self._rule(rule_id)
            if rule_id and not rule:
                raise DPECostAllocationValidationError("Forma de distribuição não encontrada.")
            expense.allocation_rule_id = rule_id
        targets = payload.get("targets", [])
        if not isinstance(targets, list):
            raise DPECostAllocationValidationError("Configuracao de alvos invalida.", {"targets": "Informe uma lista."})
        normalized: list[tuple[DPECostPeriodOffering, Decimal | None, Decimal | None, str | None]] = []
        seen: set[int] = set()
        for item in targets:
            if not isinstance(item, dict):
                continue
            offering_id = int(item.get("period_offering_id") or 0)
            if offering_id in seen:
                raise DPECostAllocationValidationError("O mesmo curso/contexto foi selecionado mais de uma vez na distribuição.")
            seen.add(offering_id)
            offering = self._offering(expense.period_id, offering_id)
            amount = _decimal(item.get("manual_amount"), "manual_amount", allow_none=True, scale="0.01")
            percentage = _decimal(item.get("manual_percentage"), "manual_percentage", allow_none=True)
            if amount is not None and percentage is not None:
                raise DPECostAllocationValidationError(
                    "Use valor ou percentual na divisão manual, não os dois ao mesmo tempo.",
                    {"targets": "Escolha somente uma forma de divisão manual."},
                )
            normalized.append((offering, amount, percentage, _text(item.get("notes")) or None))
        effective_rule = self._rule(expense.allocation_rule_id)
        if scope == "DIRECT":
            if not effective_rule or effective_rule.driver_type != "DIRECT":
                raise DPECostAllocationValidationError("Despesa direta deve usar o critério Direto.")
            if len(normalized) != 1:
                raise DPECostAllocationValidationError(
                    "Despesa direta precisa de exatamente um curso/contexto de destino."
                )
        elif effective_rule and effective_rule.driver_type == "DIRECT":
            raise DPECostAllocationValidationError(
                "Despesa compartilhada não pode usar distribuição direta. Altere o tratamento para Direta na área Despesas."
            )
        self.db.query(DPECostExpenseAllocationTarget).filter(
            DPECostExpenseAllocationTarget.expense_id == expense.id
        ).delete(synchronize_session=False)
        self.db.flush()
        for offering, amount, percentage, notes in normalized:
            self.db.add(DPECostExpenseAllocationTarget(
                expense_id=expense.id,
                period_offering_id=offering.id,
                manual_amount=amount,
                manual_percentage=percentage,
                notes=notes,
                created_by=self.actor,
                updated_by=self.actor,
            ))
        expense.updated_by = self.actor

    def set_expense_config(self, expense_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expense = self._expense(expense_id, editable=True)
        before = self.expense_config(expense.id)
        self._apply_expense_config_no_commit(expense, payload)
        self.db.flush()
        after = self.expense_config(expense.id)
        add_dpe_audit(
            self.db,
            self.scope,
            action="configure_allocation",
            entity="dpe_expense_allocation",
            entity_id=expense.id,
            period_id=expense.period_id,
            before={"rule": before.get("rule"), "targets": before.get("targets")},
            after={"rule": after.get("rule"), "targets": after.get("targets")},
        )
        self._commit()
        return after

    def bulk_policy_preview(self, period_id: int, expense_ids: list[int] | None = None) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        stmt = select(DPECostExpense).where(
            DPECostExpense.directorate_id == self.directorate_id,
            DPECostExpense.period_id == period.id,
            DPECostExpense.status == "ACTIVE",
            DPECostExpense.expense_scope != "INSTITUTIONAL",
        )
        if expense_ids:
            stmt = stmt.where(DPECostExpense.id.in_([int(value) for value in expense_ids]))
        expenses = self.db.scalars(stmt.order_by(DPECostExpense.description, DPECostExpense.id)).all()
        items: list[dict[str, Any]] = []
        for expense in expenses:
            policy = self._suggested_policy(expense)
            if not policy:
                items.append({"expense_id": expense.id, "description": expense.description, "amount": float(expense.amount), "status": "NO_POLICY", "policy": None})
                continue
            try:
                resolved = self.resolve_policy_for_expense(expense.id, policy.id)
                preview = self.preview_expense_config(expense.id, resolved["config"])
                items.append({
                    "expense_id": expense.id,
                    "description": expense.description,
                    "amount": float(expense.amount),
                    "status": "READY" if preview.get("ready") else "BLOCKED",
                    "policy": resolved["policy"],
                    "config": resolved["config"],
                    "preview": preview,
                })
            except DPECostAllocationValidationError as exc:
                items.append({"expense_id": expense.id, "description": expense.description, "amount": float(expense.amount), "status": "BLOCKED", "policy": self._policy_payload(policy, period_id=period.id), "error": str(exc)})
        return {
            "period_id": period.id,
            "items": items,
            "ready_count": sum(1 for item in items if item["status"] == "READY"),
            "blocked_count": sum(1 for item in items if item["status"] == "BLOCKED"),
            "without_policy_count": sum(1 for item in items if item["status"] == "NO_POLICY"),
        }

    def bulk_apply_suggested_policies(self, period_id: int, expense_ids: list[int] | None = None) -> dict[str, Any]:
        preview = self.bulk_policy_preview(period_id, expense_ids)
        blocked = [item for item in preview["items"] if item["status"] == "BLOCKED"]
        if blocked:
            raise DPECostAllocationValidationError(
                "Existem despesas cuja politica sugerida nao pode ser aplicada. Revise a previa antes de confirmar.",
                {"expenses": ", ".join(str(item["expense_id"]) for item in blocked)},
            )
        ready = [item for item in preview["items"] if item["status"] == "READY"]
        try:
            for item in ready:
                expense = self._expense(item["expense_id"], editable=True)
                self._apply_expense_config_no_commit(expense, item["config"])
            add_dpe_audit(
                self.db,
                self.scope,
                action="bulk_apply_policy",
                entity="dpe_allocation_batch",
                entity_id=f"period:{period_id}",
                period_id=period_id,
                after={"expense_ids": [item["expense_id"] for item in ready]},
                metadata={"applied_count": len(ready), "without_policy_count": preview["without_policy_count"]},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {
            "period_id": int(period_id),
            "applied_count": len(ready),
            "without_policy_count": preview["without_policy_count"],
            "expense_ids": [item["expense_id"] for item in ready],
        }

    def _targets(self, expense_id: int) -> list[DPECostExpenseAllocationTarget]:
        return self.db.scalars(
            select(DPECostExpenseAllocationTarget).where(
                DPECostExpenseAllocationTarget.expense_id == int(expense_id)
            ).order_by(DPECostExpenseAllocationTarget.period_offering_id)
        ).all()

    def _metric_map(self, period_id: int, metric_type: str) -> dict[int, Decimal]:
        rows = self.db.scalars(
            select(DPECostPeriodOfferingDriverValue).where(
                DPECostPeriodOfferingDriverValue.directorate_id == self.directorate_id,
                DPECostPeriodOfferingDriverValue.period_id == int(period_id),
                DPECostPeriodOfferingDriverValue.metric_type == metric_type,
            )
        ).all()
        explicit = {row.period_offering_id: Decimal(row.value) for row in rows}
        if metric_type == "OFFERING_HOURS":
            derived = self._derived_offering_hours(period_id)
            return {**derived, **explicit}
        if metric_type == "REVENUE":
            facts = revenue_facts(self.db, self.directorate_id, int(period_id))
            return {oid: facts.attributed(oid) for oid in facts.confirmed_offering_ids}
        if metric_type == "STUDENTS":
            economics_rows = self.db.scalars(
                select(DPECostOfferingEconomics).where(
                    DPECostOfferingEconomics.directorate_id == self.directorate_id,
                    DPECostOfferingEconomics.period_id == int(period_id),
                )
            ).all()
            official = {
                row.period_offering_id: Decimal(str(row.active_students))
                for row in economics_rows if row.active_students is not None
            }
            return {**explicit, **official}
        return explicit

    def _teacher_hours(self, expense: DPECostExpense) -> dict[int, Decimal]:
        if not expense.period_teacher_id:
            return {}
        rows = self.db.execute(
            select(
                DPECostTeachingActivityOffering.period_offering_id,
                func.coalesce(func.sum(DPECostTeachingActivityOffering.allocated_hours), 0),
            )
            .join(
                DPECostTeachingActivity,
                DPECostTeachingActivity.id == DPECostTeachingActivityOffering.activity_id,
            )
            .where(
                DPECostTeachingActivity.directorate_id == self.directorate_id,
                DPECostTeachingActivity.period_id == expense.period_id,
                DPECostTeachingActivity.period_teacher_id == expense.period_teacher_id,
                DPECostTeachingActivity.status == "ACTIVE",
            )
            .group_by(DPECostTeachingActivityOffering.period_offering_id)
        ).all()
        return {int(offering_id): Decimal(str(value or 0)) for offering_id, value in rows}

    @staticmethod
    def _issue(code: str, message: str, *, expense_id: int | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "expense_id": expense_id,
            "severity": "BLOCKER",
            "code": code,
            "message": message,
            "context": context or {},
        }

    def _expense_snapshot(self, expense: DPECostExpense, rule: DPEAllocationRule | None) -> dict[str, Any]:
        classification = dict(expense.classification_snapshot_json or {})
        teacher = dict(expense.teacher_snapshot_json or {})
        return {
            "id": expense.id,
            "description": expense.description,
            "amount": float(expense.amount),
            "expense_kind": expense.expense_kind,
            "expense_scope": expense.expense_scope or "SHARED",
            "counterparty_name": expense.counterparty_name,
            "document_number": expense.document_number,
            "classification": classification,
            "teacher": teacher,
            "rule": None if not rule else {
                "id": rule.id,
                "code": rule.code,
                "name": rule.name,
                "driver_type": rule.driver_type,
            },
        }

    def _weighted_results(
        self,
        expense: DPECostExpense,
        rule: DPEAllocationRule,
        weights: dict[int, Decimal],
        offering_map: dict[int, DPECostPeriodOffering],
        *,
        basis_type: str,
        basis_meta: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        positive = {key: value for key, value in weights.items() if key in offering_map and value > 0}
        denominator = sum(positive.values(), Decimal("0"))
        if denominator <= 0:
            return [], [self._issue(
                "ZERO_DENOMINATOR",
                f"A despesa '{expense.description}' não possui dados suficientes para calcular este critério.",
                expense_id=expense.id,
                context={"driver_type": rule.driver_type},
            )]
        amounts = _split_amount(_money(expense.amount), list(positive.items()))
        results: list[dict[str, Any]] = []
        for offering_id, numerator in sorted(positive.items()):
            offering = offering_map[offering_id]
            results.append({
                "expense": expense,
                "offering": offering,
                "rule": rule,
                "driver_type": rule.driver_type,
                "amount": amounts.get(offering_id, Decimal("0.00")),
                "numerator": numerator,
                "denominator": denominator,
                "percentage": (numerator / denominator * ONE_HUNDRED),
                "basis": {
                    "basis_type": basis_type,
                    "numerator": float(numerator),
                    "denominator": float(denominator),
                    **(basis_meta or {}),
                },
            })
        return results, []

    def _allocate_expense(
        self,
        expense: DPECostExpense,
        offering_map: dict[int, DPECostPeriodOffering],
        *,
        rule_override: DPEAllocationRule | None = None,
        targets_override: list[Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rule = rule_override if rule_override is not None else self._rule(expense.allocation_rule_id)
        if not rule or not rule.active:
            return [], [self._issue(
                "RULE_MISSING",
                f"A despesa '{expense.description}' não possui uma forma de distribuição ativa.",
                expense_id=expense.id,
            )]
        driver = rule.driver_type
        if driver not in DRIVER_TYPES:
            return [], [self._issue("DRIVER_INVALID", "Forma de distribuição não reconhecida.", expense_id=expense.id)]
        targets = targets_override if targets_override is not None else self._targets(expense.id)
        target_ids = [row.period_offering_id for row in targets if row.period_offering_id in offering_map]
        eligible = target_ids or list(offering_map)
        if not eligible:
            return [], [self._issue("NO_OFFERINGS", "A competência não possui cursos/contextos elegíveis para distribuição.", expense_id=expense.id)]

        if driver == "TEACHER_HOURS":
            if expense.expense_kind != "PAYROLL":
                return [], [self._issue(
                    "TEACHER_DRIVER_NON_PAYROLL",
                    "Carga horária docente só pode ser aplicada a uma despesa de Folha/Pessoal.",
                    expense_id=expense.id,
                )]
            if not expense.period_teacher_id or expense.teacher_match_status != "CONFIRMED":
                return [], [self._issue(
                    "TEACHER_NOT_CONFIRMED",
                    "A despesa docente precisa estar conciliada com um docente antes da distribuição.",
                    expense_id=expense.id,
                )]
            weights = self._teacher_hours(expense)
            return self._weighted_results(
                expense, rule, weights, offering_map,
                basis_type="TEACHER_HOURS",
                basis_meta={"period_teacher_id": expense.period_teacher_id},
            )

        if driver == "OFFERING_HOURS":
            metric = self._metric_map(expense.period_id, "OFFERING_HOURS")
            weights = {offering_id: metric.get(offering_id, Decimal("0")) for offering_id in eligible}
            return self._weighted_results(expense, rule, weights, offering_map, basis_type="OFFERING_HOURS")

        if driver in {"STUDENTS", "REVENUE"}:
            metric = self._metric_map(expense.period_id, driver)
            missing = [offering_id for offering_id in eligible if offering_id not in metric]
            if missing:
                labels = [_offering_label(dict(offering_map[item].offering_snapshot_json or {})) for item in missing]
                return [], [self._issue(
                    f"{driver}_MISSING",
                    (f"Faltam alunos ativos para {len(missing)} curso(s) selecionado(s)." if driver == "STUDENTS" else f"Falta receita para {len(missing)} curso(s) selecionado(s)."),
                    expense_id=expense.id,
                    context={"period_offering_ids": missing, "labels": labels},
                )]
            weights = {offering_id: metric.get(offering_id, Decimal("0")) for offering_id in eligible}
            return self._weighted_results(expense, rule, weights, offering_map, basis_type=driver)

        if driver == "EQUAL":
            weights = {offering_id: Decimal("1") for offering_id in eligible}
            return self._weighted_results(expense, rule, weights, offering_map, basis_type="EQUAL")

        if driver == "DIRECT":
            if len(target_ids) != 1:
                return [], [self._issue(
                    "DIRECT_TARGET_REQUIRED",
                    "A distribuição direta exige exatamente um curso/contexto de destino configurado.",
                    expense_id=expense.id,
                )]
            offering = offering_map[target_ids[0]]
            return [{
                "expense": expense,
                "offering": offering,
                "rule": rule,
                "driver_type": driver,
                "amount": _money(expense.amount),
                "numerator": Decimal("1"),
                "denominator": Decimal("1"),
                "percentage": ONE_HUNDRED,
                "basis": {"basis_type": "DIRECT", "period_offering_id": offering.id},
            }], []

        if driver == "MANUAL":
            if not targets:
                return [], [self._issue(
                    "MANUAL_TARGETS_REQUIRED",
                    "A divisão manual exige um ou mais cursos/contextos com valor ou percentual informado.",
                    expense_id=expense.id,
                )]
            amount_mode = all(row.manual_amount is not None and row.manual_percentage is None for row in targets)
            percentage_mode = all(row.manual_percentage is not None and row.manual_amount is None for row in targets)
            if not amount_mode and not percentage_mode:
                return [], [self._issue(
                    "MANUAL_MODE_INVALID",
                    "Na divisão manual, use somente valores em todos os destinos ou somente percentuais em todos os destinos.",
                    expense_id=expense.id,
                )]
            if amount_mode:
                total = sum((Decimal(row.manual_amount or 0) for row in targets), Decimal("0")).quantize(CENT)
                if total != _money(expense.amount):
                    return [], [self._issue(
                        "MANUAL_AMOUNT_MISMATCH",
                        "A soma dos valores manuais precisa ser exatamente igual ao valor da despesa.",
                        expense_id=expense.id,
                        context={"expense_amount": float(expense.amount), "manual_total": float(total)},
                    )]
                results: list[dict[str, Any]] = []
                for row in targets:
                    if row.period_offering_id not in offering_map:
                        continue
                    value = Decimal(row.manual_amount or 0).quantize(CENT)
                    results.append({
                        "expense": expense,
                        "offering": offering_map[row.period_offering_id],
                        "rule": rule,
                        "driver_type": driver,
                        "amount": value,
                        "numerator": value,
                        "denominator": _money(expense.amount),
                        "percentage": (value / _money(expense.amount) * ONE_HUNDRED) if expense.amount else Decimal("0"),
                        "basis": {"basis_type": "MANUAL_AMOUNT", "configured_amount": float(value)},
                    })
                return results, []
            percentages = {row.period_offering_id: Decimal(row.manual_percentage or 0) for row in targets if row.period_offering_id in offering_map}
            total_percentage = sum(percentages.values(), Decimal("0"))
            if abs(total_percentage - ONE_HUNDRED) > Decimal("0.0001"):
                return [], [self._issue(
                    "MANUAL_PERCENTAGE_MISMATCH",
                    "A soma dos percentuais manuais precisa ser 100%.",
                    expense_id=expense.id,
                    context={"manual_percentage_total": float(total_percentage)},
                )]
            amounts = _split_amount(_money(expense.amount), list(percentages.items()))
            results = []
            for offering_id, percentage in sorted(percentages.items()):
                results.append({
                    "expense": expense,
                    "offering": offering_map[offering_id],
                    "rule": rule,
                    "driver_type": driver,
                    "amount": amounts.get(offering_id, Decimal("0.00")),
                    "numerator": percentage,
                    "denominator": ONE_HUNDRED,
                    "percentage": percentage,
                    "basis": {"basis_type": "MANUAL_PERCENTAGE", "configured_percentage": float(percentage)},
                })
            return results, []

        return [], [self._issue("DRIVER_NOT_IMPLEMENTED", "Forma de distribuição ainda não implementada.", expense_id=expense.id)]

    def _preview_targets(self, expense: DPECostExpense, payload: dict[str, Any]) -> list[Any]:
        raw_targets = payload.get("targets", [])
        if not isinstance(raw_targets, list):
            raise DPECostAllocationValidationError("Configuração de destinos inválida.", {"targets": "Informe uma lista."})
        normalized: list[Any] = []
        seen: set[int] = set()
        for item in raw_targets:
            if not isinstance(item, dict):
                continue
            offering_id = int(item.get("period_offering_id") or 0)
            if not offering_id:
                continue
            if offering_id in seen:
                raise DPECostAllocationValidationError("O mesmo curso/contexto foi selecionado mais de uma vez na distribuição.")
            seen.add(offering_id)
            self._offering(expense.period_id, offering_id)
            amount = _decimal(item.get("manual_amount"), "manual_amount", allow_none=True, scale="0.01")
            percentage = _decimal(item.get("manual_percentage"), "manual_percentage", allow_none=True)
            if amount is not None and percentage is not None:
                raise DPECostAllocationValidationError(
                    "Use valor ou percentual, não os dois ao mesmo tempo.",
                    {"targets": "Escolha somente uma forma de distribuição manual."},
                )
            normalized.append(SimpleNamespace(
                period_offering_id=offering_id,
                manual_amount=amount,
                manual_percentage=percentage,
                notes=_text(item.get("notes")) or None,
            ))
        return normalized

    def preview_expense_config(self, expense_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Preview one expense distribution without persisting any configuration."""
        expense = self._expense(expense_id)
        period = self._period(expense.period_id)
        rule_id = int(payload.get("allocation_rule_id") or 0) or None
        rule = self._rule(rule_id)
        if not rule:
            raise DPECostAllocationValidationError(
                "Escolha um critério de distribuição para visualizar a prévia.",
                {"allocation_rule_id": "Selecione um critério."},
            )
        targets = self._preview_targets(expense, payload)
        offering_map = {row.id: row for row in self._period_offerings(period.id)}
        results, issues = self._allocate_expense(
            expense,
            offering_map,
            rule_override=rule,
            targets_override=targets,
        )
        rows = []
        for item in results:
            basis = dict(item.get("basis") or {})
            rows.append({
                "period_offering_id": item["offering"].id,
                "label": _offering_label(dict(item["offering"].offering_snapshot_json or {})),
                "allocated_amount": float(Decimal(item["amount"]).quantize(CENT)),
                "percentage": float(Decimal(item["percentage"]).quantize(Decimal("0.0001"))),
                "numerator": float(item["numerator"]) if item.get("numerator") is not None else None,
                "denominator": float(item["denominator"]) if item.get("denominator") is not None else None,
                "basis": basis,
            })
        allocated = sum((Decimal(str(row["allocated_amount"])) for row in rows), Decimal("0.00")).quantize(CENT)
        expense_amount = _money(expense.amount)
        return {
            "expense_id": expense.id,
            "description": expense.description,
            "amount": float(expense_amount),
            "period": period.period,
            "rule": {
                "id": rule.id,
                "code": rule.code,
                "name": rule.name,
                "driver_type": rule.driver_type,
                "description": rule.description,
            },
            "results": rows,
            "issues": issues,
            "allocated_total": float(allocated),
            "unallocated_total": float((expense_amount - allocated).quantize(CENT)),
            "ready": not any(issue.get("severity") == "BLOCKER" for issue in issues) and allocated == expense_amount,
        }

    def _input_fingerprint(self, period_id: int) -> str:
        expenses = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_scope != "INSTITUTIONAL",
            ).order_by(DPECostExpense.id)
        ).all()
        targets = self.db.execute(
            select(
                DPECostExpenseAllocationTarget.expense_id,
                DPECostExpenseAllocationTarget.period_offering_id,
                DPECostExpenseAllocationTarget.manual_amount,
                DPECostExpenseAllocationTarget.manual_percentage,
            )
            .join(DPECostExpense, DPECostExpense.id == DPECostExpenseAllocationTarget.expense_id)
            .where(DPECostExpense.period_id == int(period_id))
            .order_by(DPECostExpenseAllocationTarget.expense_id, DPECostExpenseAllocationTarget.period_offering_id)
        ).all()
        metrics = self.db.execute(
            select(
                DPECostPeriodOfferingDriverValue.period_offering_id,
                DPECostPeriodOfferingDriverValue.metric_type,
                DPECostPeriodOfferingDriverValue.value,
            ).where(DPECostPeriodOfferingDriverValue.period_id == int(period_id))
            .order_by(DPECostPeriodOfferingDriverValue.period_offering_id, DPECostPeriodOfferingDriverValue.metric_type)
        ).all()
        economics = self.db.execute(
            select(
                DPECostOfferingEconomics.period_offering_id,
                DPECostOfferingEconomics.active_students,
                DPECostOfferingEconomics.updated_at,
            )
            .where(DPECostOfferingEconomics.period_id == int(period_id))
            .order_by(DPECostOfferingEconomics.period_offering_id)
        ).all()
        revenues = self.db.execute(
            select(
                DPERevenueEntry.id,
                DPERevenueEntry.period_offering_id,
                DPERevenueEntry.category_id,
                DPERevenueEntry.amount,
                DPERevenueEntry.updated_at,
            )
            .where(DPERevenueEntry.period_id == int(period_id))
            .order_by(DPERevenueEntry.id)
        ).all()
        teaching = self.db.execute(
            select(
                DPECostTeachingActivity.id,
                DPECostTeachingActivity.period_teacher_id,
                DPECostTeachingActivity.workload_hours,
                DPECostTeachingActivity.effective_start_date,
                DPECostTeachingActivity.effective_end_date,
                DPECostTeachingActivityOffering.period_offering_id,
                DPECostTeachingActivityOffering.allocated_hours,
            )
            .join(DPECostTeachingActivityOffering, DPECostTeachingActivityOffering.activity_id == DPECostTeachingActivity.id)
            .where(
                DPECostTeachingActivity.period_id == int(period_id),
                DPECostTeachingActivity.status == "ACTIVE",
            )
            .order_by(DPECostTeachingActivity.id, DPECostTeachingActivityOffering.period_offering_id)
        ).all()
        payload = {
            "expenses": [
                [row.id, str(row.amount), row.expense_scope or "SHARED", row.allocation_rule_id, row.period_teacher_id, row.teacher_match_status, row.updated_at.isoformat() if row.updated_at else None]
                for row in expenses
            ],
            "targets": [[a, b, str(c) if c is not None else None, str(d) if d is not None else None] for a, b, c, d in targets],
            "metrics": [[a, b, str(c)] for a, b, c in metrics],
            "economics": [[a, b, _iso(c)] for a, b, c in economics],
            "revenues": [[a, b, c, str(d), _iso(e)] for a, b, c, d, e in revenues],
            "teaching": [[a, b, str(c), _iso(d), _iso(e), f, str(g)] for a, b, c, d, e, f, g in teaching],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def calculate(self, period_id: int) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        offerings = self._period_offerings(period.id)
        offering_map = {row.id: row for row in offerings}
        expenses = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == period.id,
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_scope != "INSTITUTIONAL",
            ).order_by(DPECostExpense.id)
        ).all()
        run_number = int(self.db.scalar(
            select(func.coalesce(func.max(DPECostAllocationRun.run_number), 0)).where(
                DPECostAllocationRun.period_id == period.id
            )
        ) or 0) + 1
        expense_total = sum((_money(row.amount) for row in expenses), Decimal("0.00"))
        run = DPECostAllocationRun(
            directorate_id=self.directorate_id,
            period_id=period.id,
            run_number=run_number,
            status="CALCULATED",
            input_fingerprint=self._input_fingerprint(period.id),
            expense_total=expense_total,
            allocated_total=Decimal("0.00"),
            unallocated_total=expense_total,
            summary_json={},
            created_by=self.actor,
        )
        self.db.add(run)
        self.db.flush()
        issues: list[dict[str, Any]] = []
        result_rows: list[dict[str, Any]] = []
        # A month can legitimately contain only institutional expenses. In
        # that case the allocation run is a reconciled zero run; there is
        # nothing to distribute to courses.
        if expenses and not offerings:
            issues.append(self._issue("NO_OFFERINGS", "A competência possui despesas distribuíveis, mas não possui cursos/contextos econômicos incluídos."))
        if expenses and offerings:
            for expense in expenses:
                results, expense_issues = self._allocate_expense(expense, offering_map)
                result_rows.extend(results)
                issues.extend(expense_issues)
        allocated_total = sum((row["amount"] for row in result_rows), Decimal("0.00")).quantize(CENT)
        unallocated_total = (expense_total - allocated_total).quantize(CENT)
        blockers = [row for row in issues if row["severity"] == "BLOCKER"]
        if unallocated_total != Decimal("0.00") and not blockers:
            issues.append(self._issue(
                "RECONCILIATION_MISMATCH",
                "O total rateado não fecha com o total de despesas ativas.",
                context={"expense_total": float(expense_total), "allocated_total": float(allocated_total)},
            ))
            blockers = [row for row in issues if row["severity"] == "BLOCKER"]
        for item in result_rows:
            expense = item["expense"]
            offering = item["offering"]
            rule = item["rule"]
            self.db.add(DPECostAllocationResult(
                run_id=run.id,
                expense_id=expense.id,
                period_offering_id=offering.id,
                allocation_rule_id=rule.id,
                driver_type=item["driver_type"],
                allocated_amount=item["amount"],
                numerator=item["numerator"],
                denominator=item["denominator"],
                percentage=item["percentage"],
                basis_json=item["basis"],
                expense_snapshot_json=self._expense_snapshot(expense, rule),
                offering_snapshot_json=dict(offering.offering_snapshot_json or {}),
            ))
        for issue in issues:
            self.db.add(DPECostAllocationIssue(
                run_id=run.id,
                expense_id=issue.get("expense_id"),
                severity=issue["severity"],
                code=issue["code"],
                message=issue["message"],
                context_json=issue.get("context") or {},
            ))
        by_driver: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for item in result_rows:
            by_driver[item["driver_type"]] += item["amount"]
        allocated_expenses = len({row["expense"].id for row in result_rows})
        run.status = "BLOCKED" if blockers else "CALCULATED"
        run.allocated_total = allocated_total
        run.unallocated_total = unallocated_total
        run.summary_json = {
            "expense_count": len(expenses),
            "allocated_expense_count": allocated_expenses,
            "result_count": len(result_rows),
            "offering_count": len(offerings),
            "blocker_count": len(blockers),
            "warning_count": len([row for row in issues if row["severity"] == "WARNING"]),
            "by_driver": {key: float(value.quantize(CENT)) for key, value in sorted(by_driver.items())},
            "reconciled": not blockers and unallocated_total == Decimal("0.00"),
        }
        add_dpe_audit(
            self.db,
            self.scope,
            action="calculate_allocation",
            entity="dpe_allocation_run",
            entity_id=run.id,
            period_id=period.id,
            after={
                "run_number": run.run_number,
                "status": run.status,
                "expense_total": float(expense_total),
                "allocated_total": float(allocated_total),
                "unallocated_total": float(unallocated_total),
                "input_fingerprint": run.input_fingerprint,
            },
        )
        self._commit()
        return self.get_run(run.id)

    def _run(self, run_id: int) -> DPECostAllocationRun:
        row = self.db.scalar(
            select(DPECostAllocationRun).where(
                DPECostAllocationRun.id == int(run_id),
                DPECostAllocationRun.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Cálculo de distribuição não encontrado.")
        return row

    def list_runs(self, *, period_id: int | None = None) -> list[dict[str, Any]]:
        stmt = select(DPECostAllocationRun).where(DPECostAllocationRun.directorate_id == self.directorate_id)
        if period_id:
            stmt = stmt.where(DPECostAllocationRun.period_id == int(period_id))
        rows = self.db.scalars(stmt.order_by(DPECostAllocationRun.period_id.desc(), DPECostAllocationRun.run_number.desc())).all()
        return [self._run_payload(row) for row in rows]

    def _run_payload(self, row: DPECostAllocationRun) -> dict[str, Any]:
        return {
            "id": row.id,
            "period_id": row.period_id,
            "run_number": row.run_number,
            "status": row.status,
            "input_fingerprint": row.input_fingerprint,
            "expense_total": float(row.expense_total or 0),
            "allocated_total": float(row.allocated_total or 0),
            "unallocated_total": float(row.unallocated_total or 0),
            "summary": dict(row.summary_json or {}),
            "created_at": _iso(row.created_at),
            "created_by": row.created_by,
            "official_at": _iso(row.official_at),
            "official_by": row.official_by,
            "superseded_at": _iso(row.superseded_at),
            "superseded_by": row.superseded_by,
        }

    def get_run(self, run_id: int) -> dict[str, Any]:
        run = self._run(run_id)
        payload = self._run_payload(run)
        results = self.db.scalars(
            select(DPECostAllocationResult).where(DPECostAllocationResult.run_id == run.id)
            .order_by(DPECostAllocationResult.expense_id, DPECostAllocationResult.period_offering_id)
        ).all()
        issues = self.db.scalars(
            select(DPECostAllocationIssue).where(DPECostAllocationIssue.run_id == run.id)
            .order_by(DPECostAllocationIssue.severity, DPECostAllocationIssue.id)
        ).all()
        by_offering: dict[int, dict[str, Any]] = {}
        result_payload: list[dict[str, Any]] = []
        for row in results:
            snap = dict(row.offering_snapshot_json or {})
            expense_snap = dict(row.expense_snapshot_json or {})
            item = {
                "id": row.id,
                "expense_id": row.expense_id,
                "expense_description": expense_snap.get("description") or f"Despesa {row.expense_id}",
                "period_offering_id": row.period_offering_id,
                "offering_label": _offering_label(snap),
                "driver_type": row.driver_type,
                "allocated_amount": float(row.allocated_amount or 0),
                "numerator": float(row.numerator) if row.numerator is not None else None,
                "denominator": float(row.denominator) if row.denominator is not None else None,
                "percentage": float(row.percentage) if row.percentage is not None else None,
                "basis": dict(row.basis_json or {}),
                "expense_snapshot": expense_snap,
                "offering_snapshot": snap,
            }
            result_payload.append(item)
            bucket = by_offering.setdefault(row.period_offering_id, {
                "period_offering_id": row.period_offering_id,
                "label": item["offering_label"],
                "allocated_amount": Decimal("0.00"),
                "expense_count": set(),
            })
            bucket["allocated_amount"] += Decimal(row.allocated_amount or 0)
            bucket["expense_count"].add(row.expense_id)
        payload["results"] = result_payload
        payload["issues"] = [
            {
                "id": row.id,
                "expense_id": row.expense_id,
                "severity": row.severity,
                "code": row.code,
                "message": row.message,
                "context": dict(row.context_json or {}),
            }
            for row in issues
        ]
        payload["by_offering"] = [
            {
                "period_offering_id": item["period_offering_id"],
                "label": item["label"],
                "allocated_amount": float(item["allocated_amount"].quantize(CENT)),
                "expense_count": len(item["expense_count"]),
            }
            for item in sorted(by_offering.values(), key=lambda value: value["label"].casefold())
        ]
        return payload

    def make_official(self, run_id: int) -> dict[str, Any]:
        run = self._run(run_id)
        period = self._period(run.period_id, editable=True)
        if run.status != "CALCULATED":
            raise DPECostAllocationValidationError("Somente um cálculo reconciliado pode se tornar oficial.")
        latest_number = int(self.db.scalar(
            select(func.coalesce(func.max(DPECostAllocationRun.run_number), 0)).where(
                DPECostAllocationRun.period_id == period.id
            )
        ) or 0)
        if run.run_number != latest_number:
            raise DPECostAllocationValidationError("Existe um cálculo mais recente para esta competência. Oficialize a versão mais nova.")
        if run.input_fingerprint != self._input_fingerprint(period.id):
            raise DPECostAllocationValidationError(
                "Os dados da competência mudaram depois deste cálculo. Gere uma nova versão antes de oficializar."
            )
        if Decimal(run.unallocated_total or 0).quantize(CENT) != Decimal("0.00"):
            raise DPECostAllocationValidationError("O cálculo ainda possui valor não rateado.")
        blockers = int(self.db.scalar(
            select(func.count()).select_from(DPECostAllocationIssue).where(
                DPECostAllocationIssue.run_id == run.id,
                DPECostAllocationIssue.severity == "BLOCKER",
            )
        ) or 0)
        if blockers:
            raise DPECostAllocationValidationError("O cálculo possui pendências bloqueantes.")
        prior = self.db.scalars(
            select(DPECostAllocationRun).where(
                DPECostAllocationRun.period_id == period.id,
                DPECostAllocationRun.status == "OFFICIAL",
                DPECostAllocationRun.id != run.id,
            )
        ).all()
        now = datetime.now(timezone.utc)
        before = {
            "period_status": period.status,
            "run_status": run.status,
            "prior_official_run_ids": [row.id for row in prior],
        }
        for old in prior:
            old.status = "SUPERSEDED"
            old.superseded_at = now
            old.superseded_by = self.actor
        run.status = "OFFICIAL"
        run.official_at = now
        run.official_by = self.actor
        period.status = "CALCULATED"
        add_dpe_audit(
            self.db,
            self.scope,
            action="officialize_allocation",
            entity="dpe_allocation_run",
            entity_id=run.id,
            period_id=period.id,
            before=before,
            after={
                "period_status": "CALCULATED",
                "run_status": "OFFICIAL",
                "run_number": run.run_number,
                "official_at": _iso(now),
            },
        )
        self._commit()
        return self.get_run(run.id)

    def period_preview(self, period_id: int) -> dict[str, Any]:
        """Simulate the whole month with the current expense configurations without persisting a run."""
        period = self._period(period_id)
        offerings = self._period_offerings(period.id)
        offering_map = {row.id: row for row in offerings}
        expenses = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == period.id,
                DPECostExpense.status == "ACTIVE",
            ).order_by(DPECostExpense.id)
        ).all()
        preview_by_offering: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        issues: list[dict[str, Any]] = []
        allocated_total = Decimal("0.00")
        expense_total = sum((Decimal(row.amount or 0) for row in expenses), Decimal("0.00")).quantize(CENT)
        for expense in expenses:
            results, expense_issues = self._allocate_expense(expense, offering_map)
            issues.extend(expense_issues)
            for item in results:
                amount = Decimal(item["amount"] or 0).quantize(CENT)
                preview_by_offering[item["offering"].id] += amount
                allocated_total += amount
        allocated_total = allocated_total.quantize(CENT)
        unallocated_total = (expense_total - allocated_total).quantize(CENT)

        current_run = self.db.scalar(
            select(DPECostAllocationRun).where(
                DPECostAllocationRun.directorate_id == self.directorate_id,
                DPECostAllocationRun.period_id == period.id,
                DPECostAllocationRun.status == "OFFICIAL",
            ).order_by(DPECostAllocationRun.run_number.desc())
        )
        current_by_offering: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        if current_run:
            result_rows = self.db.scalars(
                select(DPECostAllocationResult).where(DPECostAllocationResult.run_id == current_run.id)
            ).all()
            for row in result_rows:
                current_by_offering[row.period_offering_id] += Decimal(row.allocated_amount or 0)

        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        rows: list[dict[str, Any]] = []
        for offering in offerings:
            revenue = revenues.attributed(offering.id)
            current_cost = current_by_offering[offering.id].quantize(CENT)
            preview_cost = preview_by_offering[offering.id].quantize(CENT)
            result = (revenue - preview_cost).quantize(CENT)
            margin = (result / revenue * ONE_HUNDRED) if revenue > 0 else None
            rows.append({
                "period_offering_id": offering.id,
                "label": _offering_label(dict(offering.offering_snapshot_json or {})),
                "current_cost": float(current_cost),
                "preview_cost": float(preview_cost),
                "cost_change": float((preview_cost - current_cost).quantize(CENT)),
                "revenue": float(revenue.quantize(CENT)),
                "result": float(result),
                "margin": float(margin.quantize(Decimal("0.01"))) if margin is not None else None,
            })
        blockers = [item for item in issues if item.get("severity") == "BLOCKER"]
        return {
            "period_id": period.id,
            "period": period.period,
            "current_run": self._run_payload(current_run) if current_run else None,
            "rows": sorted(rows, key=lambda row: row["label"].casefold()),
            "issues": issues,
            "summary": {
                "expense_total": float(expense_total),
                "allocated_total": float(allocated_total),
                "unallocated_total": float(unallocated_total),
                "difference": float(unallocated_total),
                "blocker_count": len(blockers),
                "reconciled": not blockers and unallocated_total == Decimal("0.00"),
            },
        }

    def _expense_readiness(self, period_id: int) -> list[dict[str, Any]]:
        expenses = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_scope != "INSTITUTIONAL",
            ).order_by(DPECostExpense.description, DPECostExpense.id)
        ).all()
        output: list[dict[str, Any]] = []
        offering_map = {row.id: row for row in self._period_offerings(period_id)}
        for expense in expenses:
            rule = self._rule(expense.allocation_rule_id)
            targets = self._targets(expense.id)
            classification = dict(expense.classification_snapshot_json or {})
            suggested_rule = dict(classification.get("allocation_rule") or {})
            suggested_policy = self._suggested_policy(expense)
            if not rule:
                destination_summary = "Ainda não definido"
            elif rule.driver_type == "TEACHER_HOURS":
                destination_summary = "Cursos do professor"
            elif rule.driver_type == "DIRECT" and targets:
                target = offering_map.get(targets[0].period_offering_id)
                destination_summary = _offering_label(dict(target.offering_snapshot_json or {})) if target else "1 curso"
            elif targets:
                destination_summary = f"{len(targets)} curso(s) específico(s)"
            else:
                destination_summary = "Todos os cursos/contextos elegíveis"
            status = "READY"
            detail = "Forma de distribuição pronta para cálculo"
            if not rule:
                status, detail = "BLOCKED", "Forma de distribuição não definida"
            elif rule.driver_type == "TEACHER_HOURS" and (not expense.period_teacher_id or expense.teacher_match_status != "CONFIRMED"):
                status, detail = "BLOCKED", "Folha ainda não conciliada com professor"
            elif rule.driver_type == "DIRECT" and len(targets) != 1:
                status, detail = "CONFIG", "Selecione exatamente um curso/contexto de destino"
            elif rule.driver_type == "MANUAL" and not targets:
                status, detail = "CONFIG", "Informe os cursos e a divisão manual"
            elif rule:
                _, allocation_issues = self._allocate_expense(expense, offering_map)
                blockers = [item for item in allocation_issues if item.get("severity") == "BLOCKER"]
                if blockers:
                    first = blockers[0]
                    config_codes = {"DIRECT_TARGET_REQUIRED", "MANUAL_TARGETS_REQUIRED", "MANUAL_MODE_INVALID", "MANUAL_AMOUNT_MISMATCH", "MANUAL_PERCENTAGE_MISMATCH"}
                    status = "CONFIG" if first.get("code") in config_codes else "BLOCKED"
                    detail = first.get("message") or "Revise a configuração antes de calcular"
            output.append({
                "id": expense.id,
                "description": expense.description,
                "amount": float(expense.amount),
                "expense_kind": expense.expense_kind,
                "expense_scope": expense.expense_scope or "SHARED",
                "counterparty_name": expense.counterparty_name,
                "rule_id": rule.id if rule else None,
                "rule_name": rule.name if rule else None,
                "driver_type": rule.driver_type if rule else None,
                "suggested_rule_id": suggested_rule.get("id"),
                "suggested_rule_name": suggested_rule.get("name"),
                "suggested_driver_type": suggested_rule.get("driver_type"),
                "uses_suggested_rule": bool(rule and suggested_rule.get("id") and int(suggested_rule.get("id")) == int(rule.id)),
                "target_count": len(targets),
                "destination_summary": destination_summary,
                "suggested_policy_id": suggested_policy.id if suggested_policy else None,
                "suggested_policy_name": suggested_policy.name if suggested_policy else None,
                "readiness": status,
                "readiness_detail": detail,
            })
        return output

    def central_payload(self, *, period_id: int | None = None, run_id: int | None = None) -> dict[str, Any]:
        periods = self.db.scalars(
            select(DPECostPeriod).where(DPECostPeriod.directorate_id == self.directorate_id)
            .order_by(DPECostPeriod.period.desc())
        ).all()
        selected = None
        if period_id:
            selected = self._period(int(period_id))
        elif periods:
            selected = periods[0]
        runs = self.list_runs(period_id=selected.id) if selected else []
        chosen_run = None
        if run_id:
            chosen_run = self.get_run(run_id)
        elif runs:
            chosen_run = self.get_run(runs[0]["id"])
        expenses = self._expense_readiness(selected.id) if selected else []
        drivers = self.list_driver_values(selected.id) if selected else []
        policies = self.list_policies(active_only=False, period_id=selected.id) if selected else []
        month_preview = self.period_preview(selected.id) if selected else None
        expense_total = sum((Decimal(str(row["amount"])) for row in expenses), Decimal("0.00"))
        ready_count = sum(1 for row in expenses if row["readiness"] == "READY")
        latest = runs[0] if runs else None
        return {
            "periods": [
                {"id": row.id, "period": row.period, "status": row.status, "notes": row.notes}
                for row in periods
            ],
            "selected_period": (
                {"id": selected.id, "period": selected.period, "status": selected.status, "notes": selected.notes}
                if selected else None
            ),
            "editable": bool(selected and selected.status in EDITABLE_PERIOD_STATUSES),
            "expenses": expenses,
            "driver_values": drivers,
            "policies": policies,
            "month_preview": month_preview,
            "runs": runs,
            "selected_run": chosen_run,
            "summary": {
                "expense_count": len(expenses),
                "expense_total": float(expense_total.quantize(CENT)),
                "ready_expense_count": ready_count,
                "pending_expense_count": len(expenses) - ready_count,
                "offering_count": len(drivers),
                "run_count": len(runs),
                "latest_status": latest["status"] if latest else None,
                "latest_allocated_total": latest["allocated_total"] if latest else 0,
                "latest_unallocated_total": latest["unallocated_total"] if latest else float(expense_total.quantize(CENT)),
            },
        }
