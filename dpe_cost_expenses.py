from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit
from dpe_course_context import snapshot_context_label
from models import (
    DPEAllocationRule,
    DPECostCenter,
    DPECostExpense,
    DPECostExpenseAllocationTarget,
    DPECostExpenseImportBatch,
    DPECostExpenseStagingRow,
    DPECostPeriod,
    DPECostPeriodOffering,
    DPEExpenseCategory,
)
from security import DirectorateScope

EDITABLE_PERIOD_STATUSES = ("DRAFT", "REVIEW")
EXPENSE_KINDS = ("GENERAL", "PAYROLL")
EXPENSE_SCOPES = ("DIRECT", "SHARED", "INSTITUTIONAL")
EXPENSE_SOURCE_TYPES = ("MANUAL", "EXCEL", "API", "REQUEST", "OTHER")
BATCH_SOURCE_TYPES = ("EXCEL", "API", "REQUEST", "OTHER")
BATCH_STATUSES = ("STAGING", "READY", "COMMITTED", "FAILED", "CANCELLED")
STAGING_STATUSES = ("PENDING", "VALID", "ERROR", "IGNORED", "COMMITTED")
CODE_RE = re.compile(r"[^A-Z0-9._/-]+")


class DPECostExpenseValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _text(value: Any, *, max_length: int | None = None) -> str:
    output = str(value or "").strip()
    if max_length and len(output) > max_length:
        output = output[:max_length]
    return output


def _optional_text(value: Any, *, max_length: int | None = None) -> str | None:
    output = _text(value, max_length=max_length)
    return output or None


def _code(value: Any, *, max_length: int = 80) -> str:
    output = _text(value, max_length=max_length).upper()
    output = re.sub(r"\s+", "-", output)
    output = CODE_RE.sub("-", output)
    output = re.sub(r"-+", "-", output).strip("-")
    return output


def _money(value: Any) -> Decimal:
    try:
        if isinstance(value, str):
            raw = value.strip().replace("R$", "").replace(" ", "")
            if "," in raw and "." in raw:
                raw = raw.replace(".", "").replace(",", ".")
            elif "," in raw:
                raw = raw.replace(",", ".")
            value = raw
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise DPECostExpenseValidationError("Valor inválido.", {"amount": "Informe um valor monetário válido."})
    if amount <= 0:
        raise DPECostExpenseValidationError("Valor inválido.", {"amount": "A despesa deve ser maior que zero."})
    return amount


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise DPECostExpenseValidationError("Data inválida.", {"expense_date": "Use uma data válida."}) from exc


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value else None)


class DPECostExpenseRepository:
    """Operational expense intake for the DPE Cost Engine.

    The repository owns master classifications (cost centers/categories), the
    official normalized monthly expense ledger and the neutral staging batches
    that future adapters can populate without coupling the domain to one input
    format.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A Central de Despesas pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    @property
    def actor(self) -> str:
        return self.scope.user.email or self.scope.user.full_name or self.scope.user.user_id

    @staticmethod
    def _audit_snapshot(row: DPECostExpense) -> dict[str, Any]:
        return {
            "period_id": row.period_id,
            "description": row.description,
            "amount": float(row.amount or 0),
            "expense_date": _iso(row.expense_date),
            "expense_kind": row.expense_kind,
            "expense_scope": row.expense_scope,
            "counterparty_name": row.counterparty_name,
            "document_number": row.document_number,
            "cost_center_id": row.cost_center_id,
            "category_id": row.category_id,
            "allocation_rule_id": row.allocation_rule_id,
            "status": row.status,
            "source_type": row.source_type,
        }

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DPECostExpenseValidationError(
                "Não foi possível salvar porque já existe um registro com a mesma identificação ou há uma referência inválida."
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
            raise DPECostExpenseValidationError(
                f"A competência {row.period} está {row.status.lower()} e não aceita alterações de despesas."
            )
        return row

    def _center(self, center_id: int | None, *, required: bool = False) -> DPECostCenter | None:
        if not center_id:
            if required:
                raise DPECostExpenseValidationError("Centro de custo obrigatório.", {"cost_center_id": "Selecione um centro de custo."})
            return None
        row = self.db.scalar(
            select(DPECostCenter).where(
                DPECostCenter.id == int(center_id),
                DPECostCenter.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise DPECostExpenseValidationError("Centro de custo inválido.", {"cost_center_id": "Centro de custo não encontrado."})
        return row

    def _category(self, category_id: int | None) -> DPEExpenseCategory:
        if not category_id:
            raise DPECostExpenseValidationError("Categoria obrigatória.", {"category_id": "Selecione uma categoria de despesa."})
        row = self.db.scalar(
            select(DPEExpenseCategory).where(
                DPEExpenseCategory.id == int(category_id),
                DPEExpenseCategory.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise DPECostExpenseValidationError("Categoria inválida.", {"category_id": "Categoria não encontrada."})
        return row

    def _rule(self, rule_id: int | None) -> DPEAllocationRule | None:
        if not rule_id:
            return None
        row = self.db.scalar(
            select(DPEAllocationRule).where(
                DPEAllocationRule.id == int(rule_id),
                DPEAllocationRule.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise DPECostExpenseValidationError("Regra inválida.", {"allocation_rule_id": "Regra de rateio não encontrada."})
        return row

    def _batch(self, batch_id: int) -> DPECostExpenseImportBatch:
        row = self.db.scalar(
            select(DPECostExpenseImportBatch).where(
                DPECostExpenseImportBatch.id == int(batch_id),
                DPECostExpenseImportBatch.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Lote de preparação não encontrado.")
        return row

    def _expense(self, expense_id: int) -> DPECostExpense:
        row = self.db.scalar(
            select(DPECostExpense).where(
                DPECostExpense.id == int(expense_id),
                DPECostExpense.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Despesa do Cost Engine não encontrada.")
        return row

    def _period_offering(self, period_id: int, period_offering_id: int | None) -> DPECostPeriodOffering | None:
        if not period_offering_id:
            return None
        row = self.db.scalar(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.id == int(period_offering_id),
                DPECostPeriodOffering.period_id == int(period_id),
            )
        )
        if not row or not row.included:
            raise DPECostExpenseValidationError(
                "Curso/contexto inválido para esta competência.",
                {"direct_period_offering_id": "Selecione um curso/contexto incluído no mês."},
            )
        return row

    def _direct_rule(self) -> DPEAllocationRule:
        row = self.db.scalar(
            select(DPEAllocationRule).where(
                DPEAllocationRule.directorate_id == self.directorate_id,
                DPEAllocationRule.driver_type == "DIRECT",
                DPEAllocationRule.active.is_(True),
            ).order_by(DPEAllocationRule.system_defined.desc(), DPEAllocationRule.id).limit(1)
        )
        if not row:
            raise DPECostExpenseValidationError(
                "A regra técnica de despesa direta não está disponível.",
                {"expense_scope": "Cadastre/ative a regra DIRECT antes de usar despesas diretas."},
            )
        return row

    def _direct_target(self, expense_id: int) -> DPECostExpenseAllocationTarget | None:
        return self.db.scalar(
            select(DPECostExpenseAllocationTarget)
            .where(DPECostExpenseAllocationTarget.expense_id == int(expense_id))
            .order_by(DPECostExpenseAllocationTarget.id)
            .limit(1)
        )

    def _clear_targets(self, expense_id: int) -> None:
        self.db.query(DPECostExpenseAllocationTarget).filter(
            DPECostExpenseAllocationTarget.expense_id == int(expense_id)
        ).delete(synchronize_session=False)

    def _apply_scope_targets(
        self,
        row: DPECostExpense,
        *,
        direct_offering: DPECostPeriodOffering | None,
        previous_scope: str | None = None,
    ) -> None:
        scope = str(row.expense_scope or "SHARED").upper()
        if scope == "DIRECT":
            if direct_offering is None:
                raise DPECostExpenseValidationError(
                    "Despesa direta precisa de um curso/contexto de destino.",
                    {"direct_period_offering_id": "Selecione o curso/contexto que receberá esta despesa."},
                )
            self._clear_targets(row.id)
            self.db.add(DPECostExpenseAllocationTarget(
                expense_id=row.id,
                period_offering_id=direct_offering.id,
                manual_amount=None,
                manual_percentage=None,
                notes="Destino definido no lançamento da despesa direta.",
                created_by=self.actor,
                updated_by=self.actor,
            ))
        elif scope == "INSTITUTIONAL":
            self._clear_targets(row.id)
        elif previous_scope and previous_scope != "SHARED":
            # A direct/institutional -> shared transition starts clean; the user
            # can then configure eligibility in Distribuição if needed.
            self._clear_targets(row.id)

    # ------------------------------------------------------------------
    # Master classifications
    # ------------------------------------------------------------------

    def _assert_parent_chain(self, model: type[Any], row_id: int | None, parent_id: int | None) -> None:
        if not parent_id:
            return
        if row_id and int(parent_id) == int(row_id):
            raise DPECostExpenseValidationError("Hierarquia inválida.", {"parent_id": "Um item não pode ser pai de si mesmo."})
        seen: set[int] = set()
        current = int(parent_id)
        while current:
            if current in seen or (row_id and current == int(row_id)):
                raise DPECostExpenseValidationError("Hierarquia inválida.", {"parent_id": "A hierarquia criaria um ciclo."})
            seen.add(current)
            parent = self.db.scalar(select(model).where(model.id == current, model.directorate_id == self.directorate_id))
            if not parent:
                raise DPECostExpenseValidationError("Hierarquia inválida.", {"parent_id": "Item pai não encontrado."})
            current = int(parent.parent_id) if parent.parent_id else 0

    @staticmethod
    def _center_payload(row: DPECostCenter, parent_name: str | None = None, usage_count: int = 0) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "parent_id": row.parent_id,
            "parent_name": parent_name,
            "external_key": row.external_key,
            "active": bool(row.active),
            "notes": row.notes,
            "usage_count": int(usage_count or 0),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def list_cost_centers(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(DPECostCenter)
            .where(DPECostCenter.directorate_id == self.directorate_id)
            .order_by(DPECostCenter.name, DPECostCenter.code)
        ).all()
        if active_only:
            rows = [row for row in rows if row.active]
        names = {row.id: row.name for row in rows}
        usage = dict(
            self.db.execute(
                select(DPECostExpense.cost_center_id, func.count(DPECostExpense.id))
                .where(
                    DPECostExpense.directorate_id == self.directorate_id,
                    DPECostExpense.cost_center_id.is_not(None),
                )
                .group_by(DPECostExpense.cost_center_id)
            ).all()
        )
        return [self._center_payload(row, names.get(row.parent_id), usage.get(row.id, 0)) for row in rows]

    def create_cost_center(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = _code(payload.get("code"))
        name = _text(payload.get("name"), max_length=180)
        errors: dict[str, str] = {}
        if not code:
            errors["code"] = "Informe um código único."
        if not name:
            errors["name"] = "Informe o nome do centro de custo."
        parent_id = int(payload["parent_id"]) if payload.get("parent_id") else None
        self._assert_parent_chain(DPECostCenter, None, parent_id)
        if errors:
            raise DPECostExpenseValidationError("Revise o centro de custo.", errors)
        row = DPECostCenter(
            directorate_id=self.directorate_id,
            code=code,
            name=name,
            parent_id=parent_id,
            external_key=_optional_text(payload.get("external_key"), max_length=160),
            active=bool(payload.get("active", True)),
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
        )
        self.db.add(row)
        self.db.flush()
        add_dpe_audit(
            self.db,
            self.scope,
            action="create_cost_center",
            entity="dpe_cost_center",
            entity_id=row.id,
            after={
                "code": row.code,
                "name": row.name,
                "parent_id": row.parent_id,
                "active": bool(row.active),
            },
        )
        self._commit()
        self.db.refresh(row)
        return self._center_payload(row)

    def update_cost_center(self, center_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._center(center_id, required=True)
        assert row is not None
        code = _code(payload.get("code", row.code))
        name = _text(payload.get("name", row.name), max_length=180)
        parent_id_raw = payload.get("parent_id", row.parent_id)
        parent_id = int(parent_id_raw) if parent_id_raw else None
        self._assert_parent_chain(DPECostCenter, row.id, parent_id)
        if not code or not name:
            raise DPECostExpenseValidationError("Revise o centro de custo.", {"name": "Código e nome são obrigatórios."})
        row.code = code
        row.name = name
        row.parent_id = parent_id
        row.external_key = _optional_text(payload.get("external_key", row.external_key), max_length=160)
        row.active = bool(payload.get("active", row.active))
        row.notes = _optional_text(payload.get("notes", row.notes))
        self._commit()
        self.db.refresh(row)
        return self._center_payload(row)

    @staticmethod
    def _category_payload(
        row: DPEExpenseCategory,
        parent_name: str | None = None,
        rule: DPEAllocationRule | None = None,
        usage_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "parent_id": row.parent_id,
            "parent_name": parent_name,
            "default_rule_id": row.default_rule_id,
            "default_rule_code": rule.code if rule else None,
            "default_rule_name": rule.name if rule else None,
            "default_driver_type": rule.driver_type if rule else None,
            "active": bool(row.active),
            "notes": row.notes,
            "usage_count": int(usage_count or 0),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def list_categories(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(DPEExpenseCategory)
            .where(DPEExpenseCategory.directorate_id == self.directorate_id)
            .order_by(DPEExpenseCategory.name, DPEExpenseCategory.code)
        ).all()
        if active_only:
            rows = [row for row in rows if row.active]
        names = {row.id: row.name for row in rows}
        rule_ids = {row.default_rule_id for row in rows if row.default_rule_id}
        rules = {
            rule.id: rule
            for rule in self.db.scalars(
                select(DPEAllocationRule).where(
                    DPEAllocationRule.directorate_id == self.directorate_id,
                    DPEAllocationRule.id.in_(rule_ids) if rule_ids else False,
                )
            ).all()
        } if rule_ids else {}
        usage = dict(
            self.db.execute(
                select(DPECostExpense.category_id, func.count(DPECostExpense.id))
                .where(DPECostExpense.directorate_id == self.directorate_id)
                .group_by(DPECostExpense.category_id)
            ).all()
        )
        return [self._category_payload(row, names.get(row.parent_id), rules.get(row.default_rule_id), usage.get(row.id, 0)) for row in rows]

    def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = _code(payload.get("code"))
        name = _text(payload.get("name"), max_length=180)
        errors: dict[str, str] = {}
        if not code:
            errors["code"] = "Informe um código único."
        if not name:
            errors["name"] = "Informe o nome da categoria."
        parent_id = int(payload["parent_id"]) if payload.get("parent_id") else None
        self._assert_parent_chain(DPEExpenseCategory, None, parent_id)
        rule = self._rule(int(payload["default_rule_id"]) if payload.get("default_rule_id") else None)
        if errors:
            raise DPECostExpenseValidationError("Revise a categoria.", errors)
        row = DPEExpenseCategory(
            directorate_id=self.directorate_id,
            code=code,
            name=name,
            parent_id=parent_id,
            default_rule_id=rule.id if rule else None,
            active=bool(payload.get("active", True)),
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
        )
        self.db.add(row)
        self._commit()
        self.db.refresh(row)
        return self._category_payload(row, rule=rule)

    def update_category(self, category_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._category(category_id)
        code = _code(payload.get("code", row.code))
        name = _text(payload.get("name", row.name), max_length=180)
        parent_id_raw = payload.get("parent_id", row.parent_id)
        parent_id = int(parent_id_raw) if parent_id_raw else None
        self._assert_parent_chain(DPEExpenseCategory, row.id, parent_id)
        rule_raw = payload.get("default_rule_id", row.default_rule_id)
        rule = self._rule(int(rule_raw) if rule_raw else None)
        if not code or not name:
            raise DPECostExpenseValidationError("Revise a categoria.", {"name": "Código e nome são obrigatórios."})
        row.code = code
        row.name = name
        row.parent_id = parent_id
        row.default_rule_id = rule.id if rule else None
        row.active = bool(payload.get("active", row.active))
        row.notes = _optional_text(payload.get("notes", row.notes))
        self._commit()
        self.db.refresh(row)
        return self._category_payload(row, rule=rule)

    # ------------------------------------------------------------------
    # Official expenses
    # ------------------------------------------------------------------

    def _classification_snapshot(
        self,
        *,
        center: DPECostCenter | None,
        category: DPEExpenseCategory,
        rule: DPEAllocationRule | None,
        expense_scope: str = "SHARED",
        direct_offering: DPECostPeriodOffering | None = None,
    ) -> dict[str, Any]:
        return {
            "snapshot_version": 2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "expense_scope": expense_scope,
            "cost_center": None if not center else {"id": center.id, "code": center.code, "name": center.name},
            "category": {"id": category.id, "code": category.code, "name": category.name},
            "allocation_rule": None if not rule else {
                "id": rule.id,
                "code": rule.code,
                "name": rule.name,
                "driver_type": rule.driver_type,
            },
            "direct_destination": None if not direct_offering else {
                "period_offering_id": direct_offering.id,
                "label": snapshot_context_label(dict(direct_offering.offering_snapshot_json or {})),
                "offering_snapshot": dict(direct_offering.offering_snapshot_json or {}),
            },
        }

    def _expense_payload(
        self,
        row: DPECostExpense,
        period: DPECostPeriod,
        center: DPECostCenter | None,
        category: DPEExpenseCategory,
        rule: DPEAllocationRule | None,
    ) -> dict[str, Any]:
        target = self._direct_target(row.id) if str(row.expense_scope or "SHARED").upper() == "DIRECT" else None
        target_offering = target.period_offering if target else None
        return {
            "id": row.id,
            "period_id": row.period_id,
            "period": period.period,
            "period_status": period.status,
            "expense_date": _iso(row.expense_date),
            "description": row.description,
            "amount": float(row.amount or 0),
            "expense_kind": row.expense_kind,
            "expense_scope": row.expense_scope or "SHARED",
            "direct_period_offering_id": target.period_offering_id if target else None,
            "direct_destination_label": snapshot_context_label(dict(target_offering.offering_snapshot_json or {})) if target_offering else None,
            "counterparty_name": row.counterparty_name,
            "document_number": row.document_number,
            "cost_center_id": row.cost_center_id,
            "cost_center_code": center.code if center else None,
            "cost_center_name": center.name if center else None,
            "category_id": row.category_id,
            "category_code": category.code,
            "category_name": category.name,
            "allocation_rule_id": row.allocation_rule_id,
            "allocation_rule_code": rule.code if rule else None,
            "allocation_rule_name": rule.name if rule else None,
            "allocation_driver": rule.driver_type if rule else None,
            "source_type": row.source_type,
            "source_batch_id": row.source_batch_id,
            "source_reference": row.source_reference,
            "external_key": row.external_key,
            "status": row.status,
            "period_teacher_id": row.period_teacher_id,
            "teacher_match_status": row.teacher_match_status,
            "teacher_match_method": row.teacher_match_method,
            "teacher_snapshot": dict(row.teacher_snapshot_json or {}),
            "classification_snapshot": dict(row.classification_snapshot_json or {}),
            "source_payload": dict(row.source_payload_json or {}),
            "notes": row.notes,
            "created_at": _iso(row.created_at),
            "created_by": row.created_by,
            "updated_at": _iso(row.updated_at),
            "updated_by": row.updated_by,
            "voided_at": _iso(row.voided_at),
            "voided_by": row.voided_by,
            "void_reason": row.void_reason,
            "editable": period.status in EDITABLE_PERIOD_STATUSES and row.status == "ACTIVE",
        }

    def list_expenses(
        self,
        *,
        period_id: int | None = None,
        category_id: int | None = None,
        cost_center_id: int | None = None,
        source_type: str | None = None,
        expense_kind: str | None = None,
        expense_scope: str | None = None,
        status: str | None = "ACTIVE",
        search: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(DPECostExpense, DPECostPeriod, DPECostCenter, DPEExpenseCategory, DPEAllocationRule)
            .join(DPECostPeriod, DPECostPeriod.id == DPECostExpense.period_id)
            .outerjoin(DPECostCenter, DPECostCenter.id == DPECostExpense.cost_center_id)
            .join(DPEExpenseCategory, DPEExpenseCategory.id == DPECostExpense.category_id)
            .outerjoin(DPEAllocationRule, DPEAllocationRule.id == DPECostExpense.allocation_rule_id)
            .where(DPECostExpense.directorate_id == self.directorate_id)
        )
        if period_id:
            stmt = stmt.where(DPECostExpense.period_id == int(period_id))
        if category_id:
            stmt = stmt.where(DPECostExpense.category_id == int(category_id))
        if cost_center_id:
            stmt = stmt.where(DPECostExpense.cost_center_id == int(cost_center_id))
        if source_type:
            stmt = stmt.where(DPECostExpense.source_type == _text(source_type).upper())
        if expense_kind:
            stmt = stmt.where(DPECostExpense.expense_kind == _text(expense_kind).upper())
        if expense_scope:
            stmt = stmt.where(DPECostExpense.expense_scope == _text(expense_scope).upper())
        if status:
            stmt = stmt.where(DPECostExpense.status == _text(status).upper())
        if search:
            needle = f"%{_text(search, max_length=160)}%"
            stmt = stmt.where(
                or_(
                    DPECostExpense.description.ilike(needle),
                    DPECostExpense.counterparty_name.ilike(needle),
                    DPECostExpense.document_number.ilike(needle),
                )
            )
        rows = self.db.execute(
            stmt.order_by(DPECostPeriod.period.desc(), DPECostExpense.expense_date.desc(), DPECostExpense.id.desc()).limit(max(1, min(int(limit), 2000)))
        ).all()
        return [self._expense_payload(expense, period, center, category, rule) for expense, period, center, category, rule in rows]

    def _normalize_expense(self, payload: dict[str, Any], *, existing: DPECostExpense | None = None) -> dict[str, Any]:
        period_id = int(payload.get("period_id") or (existing.period_id if existing else 0) or 0)
        period = self._period(period_id, editable=True)
        description = _text(payload.get("description", existing.description if existing else ""), max_length=280)
        if not description:
            raise DPECostExpenseValidationError("Revise a despesa.", {"description": "Informe a descrição da despesa."})
        amount = _money(payload.get("amount", existing.amount if existing else None))
        expense_date = _date(payload.get("expense_date", existing.expense_date if existing else None))
        if expense_date and expense_date.strftime("%Y-%m") != period.period:
            raise DPECostExpenseValidationError(
                "A data da despesa não pertence à competência selecionada.",
                {"expense_date": f"Use uma data de {period.period} ou deixe a data em branco."},
            )
        kind = _text(payload.get("expense_kind", existing.expense_kind if existing else "GENERAL")).upper()
        if kind not in EXPENSE_KINDS:
            raise DPECostExpenseValidationError("Tipo de despesa inválido.", {"expense_kind": "Use GENERAL ou PAYROLL."})
        scope_raw = _text(payload.get("expense_scope", existing.expense_scope if existing else "SHARED")).upper()
        scope_aliases = {
            "DIRETA": "DIRECT", "DIRETO": "DIRECT", "DIRECT": "DIRECT",
            "COMPARTILHADA": "SHARED", "COMPARTILHADO": "SHARED", "SHARED": "SHARED",
            "INSTITUCIONAL": "INSTITUTIONAL", "INSTITUTIONAL": "INSTITUTIONAL",
        }
        expense_scope = scope_aliases.get(scope_raw, scope_raw)
        if expense_scope not in EXPENSE_SCOPES:
            raise DPECostExpenseValidationError(
                "Tratamento da despesa inválido.",
                {"expense_scope": "Use Direta, Compartilhada ou Institucional."},
            )
        source_type = _text(payload.get("source_type", existing.source_type if existing else "MANUAL")).upper()
        if source_type not in EXPENSE_SOURCE_TYPES:
            raise DPECostExpenseValidationError("Origem inválida.", {"source_type": "Origem de despesa não reconhecida."})
        center_raw = payload.get("cost_center_id", existing.cost_center_id if existing else None)
        category_raw = payload.get("category_id", existing.category_id if existing else None)
        center = self._center(int(center_raw) if center_raw else None)
        category = self._category(int(category_raw) if category_raw else None)
        direct_marker = payload.get("direct_period_offering_id", "__MISSING__")
        if direct_marker == "__MISSING__" and existing and expense_scope == "DIRECT":
            existing_target = self._direct_target(existing.id)
            direct_id = existing_target.period_offering_id if existing_target else None
        else:
            direct_id = int(direct_marker) if direct_marker not in {"__MISSING__", None, ""} else None
        direct_offering = self._period_offering(period.id, direct_id) if expense_scope == "DIRECT" else None
        if expense_scope == "DIRECT":
            if not direct_offering:
                raise DPECostExpenseValidationError(
                    "Despesa direta precisa de um curso/contexto de destino.",
                    {"direct_period_offering_id": "Selecione quem receberá o custo diretamente."},
                )
            rule = self._direct_rule()
        elif expense_scope == "INSTITUTIONAL":
            rule = None
        else:
            rule_marker = payload.get("allocation_rule_id", "__MISSING__")
            if rule_marker == "__MISSING__":
                rule_id = existing.allocation_rule_id if existing else category.default_rule_id
            else:
                rule_id = int(rule_marker) if rule_marker else category.default_rule_id
            rule = self._rule(rule_id)
            # A legacy category can still suggest DIRECT. In the new domain,
            # DIRECT is a treatment chosen explicitly with one destination.
            if rule and str(rule.driver_type or "").upper() == "DIRECT":
                rule = None
        batch_raw = payload.get("source_batch_id", existing.source_batch_id if existing else None)
        batch = self._batch(int(batch_raw)) if batch_raw else None
        if batch:
            if batch.period_id != period.id:
                raise DPECostExpenseValidationError("Lote incompatível.", {"source_batch_id": "O lote pertence a outra competência."})
            if source_type == "MANUAL" or source_type != batch.source_type:
                raise DPECostExpenseValidationError("Origem incompatível.", {"source_type": "A origem deve corresponder ao lote de preparação."})
        return {
            "period": period,
            "description": description,
            "amount": amount,
            "expense_date": expense_date,
            "expense_kind": kind,
            "expense_scope": expense_scope,
            "direct_offering": direct_offering,
            "counterparty_name": _optional_text(payload.get("counterparty_name", existing.counterparty_name if existing else None), max_length=240),
            "document_number": _optional_text(payload.get("document_number", existing.document_number if existing else None), max_length=140),
            "center": center,
            "category": category,
            "rule": rule,
            "source_type": source_type,
            "batch": batch,
            "source_reference": _optional_text(payload.get("source_reference", existing.source_reference if existing else None), max_length=220),
            "external_key": _optional_text(payload.get("external_key", existing.external_key if existing else None), max_length=180),
            "source_payload": payload.get("source_payload", dict(existing.source_payload_json or {}) if existing else {}) if isinstance(payload.get("source_payload", dict(existing.source_payload_json or {}) if existing else {}), dict) else {},
            "notes": _optional_text(payload.get("notes", existing.notes if existing else None)),
        }

    def create_expense(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._normalize_expense(payload)
        row = DPECostExpense(
            directorate_id=self.directorate_id,
            period_id=data["period"].id,
            expense_date=data["expense_date"],
            description=data["description"],
            amount=data["amount"],
            expense_kind=data["expense_kind"],
            expense_scope=data["expense_scope"],
            counterparty_name=data["counterparty_name"],
            document_number=data["document_number"],
            cost_center_id=data["center"].id if data["center"] else None,
            category_id=data["category"].id,
            allocation_rule_id=data["rule"].id if data["rule"] else None,
            source_type=data["source_type"],
            source_batch_id=data["batch"].id if data["batch"] else None,
            source_reference=data["source_reference"],
            external_key=data["external_key"],
            classification_snapshot_json=self._classification_snapshot(
                center=data["center"], category=data["category"], rule=data["rule"],
                expense_scope=data["expense_scope"], direct_offering=data["direct_offering"],
            ),
            source_payload_json=data["source_payload"],
            notes=data["notes"],
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.db.add(row)
        self.db.flush()
        self._apply_scope_targets(row, direct_offering=data["direct_offering"])
        self._commit()
        self.db.refresh(row)
        return self._expense_payload(row, data["period"], data["center"], data["category"], data["rule"])

    def update_expense(self, expense_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._expense(expense_id)
        if row.status != "ACTIVE":
            raise DPECostExpenseValidationError("Uma despesa estornada não pode ser editada.")
        self._period(row.period_id, editable=True)
        before = self._audit_snapshot(row)
        data = self._normalize_expense(payload, existing=row)
        original_period_id = row.period_id
        original_counterparty = row.counterparty_name
        original_scope = row.expense_scope or "SHARED"
        row.period_id = data["period"].id
        row.expense_date = data["expense_date"]
        row.description = data["description"]
        row.amount = data["amount"]
        row.expense_kind = data["expense_kind"]
        row.expense_scope = data["expense_scope"]
        row.counterparty_name = data["counterparty_name"]
        if (
            row.expense_kind != "PAYROLL"
            or row.period_id != original_period_id
            or (row.period_teacher_id and row.counterparty_name != original_counterparty)
        ):
            row.period_teacher_id = None
            row.teacher_match_status = None
            row.teacher_match_method = None
            row.teacher_snapshot_json = {}
        row.document_number = data["document_number"]
        row.cost_center_id = data["center"].id if data["center"] else None
        row.category_id = data["category"].id
        row.allocation_rule_id = data["rule"].id if data["rule"] else None
        row.source_type = data["source_type"]
        row.source_batch_id = data["batch"].id if data["batch"] else None
        row.source_reference = data["source_reference"]
        row.external_key = data["external_key"]
        row.classification_snapshot_json = self._classification_snapshot(
            center=data["center"], category=data["category"], rule=data["rule"],
            expense_scope=data["expense_scope"], direct_offering=data["direct_offering"],
        )
        self._apply_scope_targets(row, direct_offering=data["direct_offering"], previous_scope=original_scope)
        row.source_payload_json = data["source_payload"]
        row.notes = data["notes"]
        row.updated_by = self.actor
        add_dpe_audit(
            self.db,
            self.scope,
            action="update",
            entity="dpe_expense",
            entity_id=row.id,
            period_id=row.period_id,
            before=before,
            after=self._audit_snapshot(row),
        )
        self._commit()
        self.db.refresh(row)
        return self._expense_payload(row, data["period"], data["center"], data["category"], data["rule"])

    def void_expense(self, expense_id: int, *, reason: str) -> dict[str, Any]:
        row = self._expense(expense_id)
        period = self._period(row.period_id, editable=True)
        if row.status == "VOIDED":
            return self._expense_payload(row, period, row.cost_center, row.category, row.allocation_rule)
        before = self._audit_snapshot(row)
        reason_text = _text(reason)
        if not reason_text:
            raise DPECostExpenseValidationError("Informe o motivo do estorno.", {"reason": "O motivo é obrigatório para preservar a auditoria."})
        row.status = "VOIDED"
        row.void_reason = reason_text
        row.voided_at = datetime.now(timezone.utc)
        row.voided_by = self.actor
        row.updated_by = self.actor
        add_dpe_audit(
            self.db,
            self.scope,
            action="void",
            entity="dpe_expense",
            entity_id=row.id,
            period_id=row.period_id,
            before=before,
            after=self._audit_snapshot(row),
            metadata={"reason": reason_text},
        )
        self._commit()
        self.db.refresh(row)
        return self._expense_payload(row, period, row.cost_center, row.category, row.allocation_rule)

    def expense_summary(self, *, period_id: int | None = None) -> dict[str, Any]:
        stmt = select(DPECostExpense).where(
            DPECostExpense.directorate_id == self.directorate_id,
            DPECostExpense.status == "ACTIVE",
        )
        period = None
        if period_id:
            period = self._period(period_id)
            stmt = stmt.where(DPECostExpense.period_id == period.id)
        total_count = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        total_amount = self.db.scalar(select(func.coalesce(func.sum(stmt.subquery().c.amount), 0))) or Decimal("0")
        no_center_stmt = select(func.count(DPECostExpense.id)).where(
            DPECostExpense.directorate_id == self.directorate_id,
            DPECostExpense.status == "ACTIVE",
            DPECostExpense.cost_center_id.is_(None),
        )
        if period:
            no_center_stmt = no_center_stmt.where(DPECostExpense.period_id == period.id)
        without_center = int(self.db.scalar(no_center_stmt) or 0)
        category_count_stmt = select(func.count(func.distinct(DPECostExpense.category_id))).where(
            DPECostExpense.directorate_id == self.directorate_id,
            DPECostExpense.status == "ACTIVE",
        )
        if period:
            category_count_stmt = category_count_stmt.where(DPECostExpense.period_id == period.id)
        scope_stmt = select(DPECostExpense.expense_scope, func.count(DPECostExpense.id), func.coalesce(func.sum(DPECostExpense.amount), 0)).where(
            DPECostExpense.directorate_id == self.directorate_id,
            DPECostExpense.status == "ACTIVE",
        )
        if period:
            scope_stmt = scope_stmt.where(DPECostExpense.period_id == period.id)
        scope_rows = self.db.execute(scope_stmt.group_by(DPECostExpense.expense_scope)).all()
        scope_summary = {key: {"count": 0, "amount": 0.0} for key in EXPENSE_SCOPES}
        for scope, count, amount in scope_rows:
            key = str(scope or "SHARED").upper()
            scope_summary.setdefault(key, {"count": 0, "amount": 0.0})
            scope_summary[key] = {"count": int(count or 0), "amount": float(amount or 0)}
        return {
            "period_id": period.id if period else None,
            "period": period.period if period else None,
            "expense_count": total_count,
            "total_amount": float(total_amount),
            "without_cost_center": without_center,
            "category_count": int(self.db.scalar(category_count_stmt) or 0),
            "by_scope": scope_summary,
            "allocatable_amount": float(scope_summary["DIRECT"]["amount"] + scope_summary["SHARED"]["amount"]),
            "institutional_amount": float(scope_summary["INSTITUTIONAL"]["amount"]),
        }

    # ------------------------------------------------------------------
    # Neutral import staging
    # ------------------------------------------------------------------

    @staticmethod
    def _batch_payload(row: DPECostExpenseImportBatch, period: DPECostPeriod, row_counts: dict[str, int] | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "period_id": row.period_id,
            "period": period.period,
            "source_type": row.source_type,
            "source_label": row.source_label,
            "original_filename": row.original_filename,
            "external_key": row.external_key,
            "status": row.status,
            "mapping": dict(row.mapping_json or {}),
            "summary": dict(row.summary_json or {}),
            "row_counts": row_counts or {},
            "notes": row.notes,
            "created_at": _iso(row.created_at),
            "created_by": row.created_by,
            "updated_at": _iso(row.updated_at),
            "editable": period.status in EDITABLE_PERIOD_STATUSES and row.status in {"STAGING", "READY"},
        }

    def list_import_batches(self, *, period_id: int | None = None) -> list[dict[str, Any]]:
        stmt = (
            select(DPECostExpenseImportBatch, DPECostPeriod)
            .join(DPECostPeriod, DPECostPeriod.id == DPECostExpenseImportBatch.period_id)
            .where(DPECostExpenseImportBatch.directorate_id == self.directorate_id)
        )
        if period_id:
            stmt = stmt.where(DPECostExpenseImportBatch.period_id == int(period_id))
        rows = self.db.execute(stmt.order_by(DPECostPeriod.period.desc(), DPECostExpenseImportBatch.id.desc())).all()
        batch_ids = [batch.id for batch, _ in rows]
        count_map: dict[int, dict[str, int]] = {batch_id: {} for batch_id in batch_ids}
        if batch_ids:
            for batch_id, status, total in self.db.execute(
                select(DPECostExpenseStagingRow.batch_id, DPECostExpenseStagingRow.status, func.count(DPECostExpenseStagingRow.id))
                .where(DPECostExpenseStagingRow.batch_id.in_(batch_ids))
                .group_by(DPECostExpenseStagingRow.batch_id, DPECostExpenseStagingRow.status)
            ).all():
                count_map.setdefault(int(batch_id), {})[str(status)] = int(total or 0)
        return [self._batch_payload(batch, period, count_map.get(batch.id)) for batch, period in rows]

    def create_import_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        period = self._period(int(payload.get("period_id") or 0), editable=True)
        source_type = _text(payload.get("source_type")).upper()
        label = _text(payload.get("source_label"), max_length=220)
        errors: dict[str, str] = {}
        if source_type not in BATCH_SOURCE_TYPES:
            errors["source_type"] = "Use EXCEL, API, REQUEST ou OTHER."
        if not label:
            errors["source_label"] = "Informe uma identificação para o lote."
        if errors:
            raise DPECostExpenseValidationError("Revise o lote de preparação.", errors)
        mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else {}
        row = DPECostExpenseImportBatch(
            directorate_id=self.directorate_id,
            period_id=period.id,
            source_type=source_type,
            source_label=label,
            original_filename=_optional_text(payload.get("original_filename"), max_length=255),
            external_key=_optional_text(payload.get("external_key"), max_length=180),
            mapping_json=mapping,
            summary_json={},
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
        )
        self.db.add(row)
        self._commit()
        self.db.refresh(row)
        return self._batch_payload(row, period, {})

    def stage_rows(self, batch_id: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
        batch = self._batch(batch_id)
        period = self._period(batch.period_id, editable=True)
        if batch.status not in {"STAGING", "READY"}:
            raise DPECostExpenseValidationError("Este lote não aceita novas linhas.")
        current_max = int(self.db.scalar(select(func.max(DPECostExpenseStagingRow.row_number)).where(DPECostExpenseStagingRow.batch_id == batch.id)) or 0)
        created = 0
        for offset, payload in enumerate(rows, start=1):
            if not isinstance(payload, dict):
                continue
            row_number = int(payload.get("row_number") or (current_max + offset))
            raw = payload.get("raw_data") if isinstance(payload.get("raw_data"), dict) else dict(payload)
            normalized = payload.get("normalized_data") if isinstance(payload.get("normalized_data"), dict) else {}
            status = _text(payload.get("status") or "PENDING").upper()
            if status not in STAGING_STATUSES:
                status = "PENDING"
            errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
            self.db.add(DPECostExpenseStagingRow(
                batch_id=batch.id,
                row_number=row_number,
                raw_data_json=raw,
                normalized_data_json=normalized,
                status=status,
                errors_json=errors,
            ))
            created += 1
        if created:
            batch.status = "STAGING"
            batch.summary_json = {**dict(batch.summary_json or {}), "last_staged_at": datetime.now(timezone.utc).isoformat()}
        self._commit()
        return {"batch": self._batch_payload(batch, period), "created": created}

    def list_staging_rows(self, batch_id: int, *, limit: int = 500) -> list[dict[str, Any]]:
        batch = self._batch(batch_id)
        rows = self.db.scalars(
            select(DPECostExpenseStagingRow)
            .where(DPECostExpenseStagingRow.batch_id == batch.id)
            .order_by(DPECostExpenseStagingRow.row_number)
            .limit(max(1, min(int(limit), 2000)))
        ).all()
        return [
            {
                "id": row.id,
                "batch_id": row.batch_id,
                "row_number": row.row_number,
                "raw_data": dict(row.raw_data_json or {}),
                "normalized_data": dict(row.normalized_data_json or {}),
                "status": row.status,
                "errors": list(row.errors_json or []),
                "committed_expense_id": row.committed_expense_id,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in rows
        ]

    def _category_by_token(self, value: Any) -> DPEExpenseCategory:
        token = _text(value, max_length=180)
        if not token:
            raise DPECostExpenseValidationError("Categoria obrigatoria.", {"category": "Informe a categoria."})
        rows = self.db.scalars(
            select(DPEExpenseCategory).where(
                DPEExpenseCategory.directorate_id == self.directorate_id,
                DPEExpenseCategory.active.is_(True),
            )
        ).all()
        folded = token.casefold()
        matches = [row for row in rows if row.code.casefold() == folded or row.name.casefold() == folded]
        if len(matches) != 1:
            raise DPECostExpenseValidationError(
                "Categoria nao encontrada ou ambigua.",
                {"category": f'Use o codigo ou nome exato de uma categoria ativa: "{token}".'},
            )
        return matches[0]

    def _center_by_token(self, value: Any) -> DPECostCenter | None:
        token = _text(value, max_length=180)
        if not token:
            return None
        rows = self.db.scalars(
            select(DPECostCenter).where(
                DPECostCenter.directorate_id == self.directorate_id,
                DPECostCenter.active.is_(True),
            )
        ).all()
        folded = token.casefold()
        matches = [row for row in rows if row.code.casefold() == folded or row.name.casefold() == folded]
        if len(matches) != 1:
            raise DPECostExpenseValidationError(
                "Setor nao encontrado ou ambiguo.",
                {"cost_center": f'Use o codigo ou nome exato de um setor ativo: "{token}".'},
            )
        return matches[0]

    @staticmethod
    def _import_signature(payload: dict[str, Any]) -> tuple[str, str, str, str]:
        amount = str(payload.get("amount") or "").strip().replace("R$", "").replace(" ", "")
        if "," in amount and "." in amount:
            amount = amount.replace(".", "").replace(",", ".")
        else:
            amount = amount.replace(",", ".")
        try:
            amount = str(Decimal(amount).quantize(Decimal("0.01")))
        except Exception:
            pass
        return (
            _text(payload.get("description"), max_length=280).casefold(),
            amount,
            _text(payload.get("expense_date"), max_length=20),
            _text(payload.get("document_number"), max_length=140).casefold(),
        )

    def _existing_import_signatures(self, period_id: int) -> tuple[set[str], set[tuple[str, str, str, str]]]:
        rows = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.status == "ACTIVE",
            )
        ).all()
        keys = {_text(row.external_key, max_length=180).casefold() for row in rows if row.external_key}
        signatures = {
            self._import_signature({
                "description": row.description,
                "amount": row.amount,
                "expense_date": _iso(row.expense_date) or "",
                "document_number": row.document_number or "",
            })
            for row in rows
        }
        return keys, signatures

    def prepare_excel_import(self, period_id: int, filename: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        batch = DPECostExpenseImportBatch(
            directorate_id=self.directorate_id,
            period_id=period.id,
            source_type="EXCEL",
            source_label=f"Excel - {filename}"[:220],
            original_filename=filename[:255],
            status="STAGING",
            mapping_json={"adapter": "DPE_COST_EXCEL_V1"},
            summary_json={},
            created_by=self.actor,
        )
        self.db.add(batch)
        self.db.flush()
        existing_keys, existing_signatures = self._existing_import_signatures(period.id)
        seen_keys: set[str] = set()
        seen_signatures: set[tuple[str, str, str, str]] = set()
        counts = {"VALID": 0, "ERROR": 0}
        total_valid = Decimal("0.00")
        for item in rows:
            raw = dict(item.get("raw_data") or {})
            row_number = int(item.get("row_number") or 0)
            errors: list[dict[str, str]] = []
            normalized: dict[str, Any] = {}
            try:
                category = self._category_by_token(raw.get("category"))
                center = self._center_by_token(raw.get("cost_center"))
                kind = _text(raw.get("expense_kind") or "GENERAL").upper()
                if kind in {"COMUM", "DESPESA COMUM", "GERAL"}:
                    kind = "GENERAL"
                elif kind in {"FOLHA", "PESSOAL", "FOLHA PESSOAL"}:
                    kind = "PAYROLL"
                payload = {
                    "period_id": period.id,
                    "description": raw.get("description"),
                    "amount": raw.get("amount"),
                    "expense_date": raw.get("expense_date"),
                    "category_id": category.id,
                    "cost_center_id": center.id if center else None,
                    "expense_kind": kind,
                    "expense_scope": raw.get("expense_scope") or "SHARED",
                    "counterparty_name": raw.get("counterparty_name"),
                    "document_number": raw.get("document_number"),
                    "source_type": "EXCEL",
                    "source_batch_id": batch.id,
                    "source_reference": raw.get("source_reference") or filename,
                    "external_key": raw.get("external_key"),
                    "notes": raw.get("notes"),
                    "source_payload": {"excel_row": row_number, "filename": filename},
                }
                data = self._normalize_expense(payload)
                normalized = {
                    **payload,
                    "description": data["description"],
                    "amount": float(data["amount"]),
                    "expense_date": _iso(data["expense_date"]),
                    "category_id": data["category"].id,
                    "category_name": data["category"].name,
                    "cost_center_id": data["center"].id if data["center"] else None,
                    "cost_center_name": data["center"].name if data["center"] else None,
                    "allocation_rule_id": data["rule"].id if data["rule"] else None,
                    "expense_scope": data["expense_scope"],
                }
                external = _text(normalized.get("external_key"), max_length=180).casefold()
                signature = self._import_signature(normalized)
                if external and (external in existing_keys or external in seen_keys):
                    errors.append({"field": "external_key", "error": "Chave externa duplicada neste mes ou no proprio arquivo."})
                if signature in existing_signatures or signature in seen_signatures:
                    errors.append({"field": "row", "error": "Possivel despesa duplicada: descricao, valor, data e documento coincidem."})
                if external:
                    seen_keys.add(external)
                seen_signatures.add(signature)
            except DPECostExpenseValidationError as exc:
                if exc.field_errors:
                    errors.extend({"field": key, "error": value} for key, value in exc.field_errors.items())
                else:
                    errors.append({"field": "row", "error": str(exc)})
            status = "ERROR" if errors else "VALID"
            if status == "VALID":
                total_valid += Decimal(str(normalized.get("amount") or 0))
            counts[status] += 1
            self.db.add(DPECostExpenseStagingRow(
                batch_id=batch.id,
                row_number=row_number,
                raw_data_json=raw,
                normalized_data_json=normalized,
                status=status,
                errors_json=errors,
            ))
        batch.status = "READY" if counts["VALID"] and not counts["ERROR"] else "FAILED"
        batch.summary_json = {
            "row_count": counts["VALID"] + counts["ERROR"],
            "valid_count": counts["VALID"],
            "error_count": counts["ERROR"],
            "valid_amount": float(total_valid),
        }
        self._commit()
        return {
            "batch": self._batch_payload(batch, period, counts),
            "rows": self.list_staging_rows(batch.id),
            "can_commit": batch.status == "READY",
        }

    def commit_import_batch(self, batch_id: int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        period = self._period(batch.period_id, editable=True)
        if batch.status == "COMMITTED":
            return {"batch": self._batch_payload(batch, period), "created": 0, "already_committed": True}
        rows = self.db.scalars(
            select(DPECostExpenseStagingRow)
            .where(DPECostExpenseStagingRow.batch_id == batch.id)
            .order_by(DPECostExpenseStagingRow.row_number)
        ).all()
        if not rows:
            raise DPECostExpenseValidationError("O lote nao possui linhas para importar.")
        if any(row.status != "VALID" for row in rows):
            raise DPECostExpenseValidationError("Corrija o arquivo e gere uma nova previa antes de importar. Existem linhas invalidas ou duplicadas.")
        existing_keys, existing_signatures = self._existing_import_signatures(period.id)
        created_rows: list[DPECostExpense] = []
        try:
            for staged in rows:
                payload = dict(staged.normalized_data_json or {})
                external = _text(payload.get("external_key"), max_length=180).casefold()
                signature = self._import_signature(payload)
                if external and external in existing_keys:
                    raise DPECostExpenseValidationError(f"A linha {staged.row_number} ficou duplicada depois da previa. Gere uma nova previa.")
                if signature in existing_signatures:
                    raise DPECostExpenseValidationError(f"A linha {staged.row_number} ficou duplicada depois da previa. Gere uma nova previa.")
                data = self._normalize_expense({**payload, "source_batch_id": batch.id, "source_type": "EXCEL"})
                expense = DPECostExpense(
                    directorate_id=self.directorate_id,
                    period_id=period.id,
                    expense_date=data["expense_date"],
                    description=data["description"],
                    amount=data["amount"],
                    expense_kind=data["expense_kind"],
                    expense_scope=data["expense_scope"],
                    counterparty_name=data["counterparty_name"],
                    document_number=data["document_number"],
                    cost_center_id=data["center"].id if data["center"] else None,
                    category_id=data["category"].id,
                    allocation_rule_id=data["rule"].id if data["rule"] else None,
                    source_type="EXCEL",
                    source_batch_id=batch.id,
                    source_reference=data["source_reference"],
                    external_key=data["external_key"],
                    classification_snapshot_json=self._classification_snapshot(
                        center=data["center"], category=data["category"], rule=data["rule"],
                        expense_scope=data["expense_scope"], direct_offering=data["direct_offering"],
                    ),
                    source_payload_json=data["source_payload"],
                    notes=data["notes"],
                    created_by=self.actor,
                    updated_by=self.actor,
                )
                self.db.add(expense)
                self.db.flush()
                staged.status = "COMMITTED"
                staged.committed_expense_id = expense.id
                created_rows.append(expense)
                if external:
                    existing_keys.add(external)
                existing_signatures.add(signature)
            batch.status = "COMMITTED"
            batch.summary_json = {**dict(batch.summary_json or {}), "committed_count": len(created_rows), "committed_at": datetime.now(timezone.utc).isoformat()}
            add_dpe_audit(
                self.db,
                self.scope,
                action="import_commit",
                entity="dpe_expense_import",
                entity_id=batch.id,
                period_id=period.id,
                after={"created_count": len(created_rows), "expense_ids": [row.id for row in created_rows]},
                metadata={"filename": batch.original_filename, "source_label": batch.source_label},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"batch": self._batch_payload(batch, period, {"COMMITTED": len(created_rows)}), "created": len(created_rows)}

    def bulk_classify(self, period_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._period(period_id, editable=True)
        ids = sorted({int(value) for value in (payload.get("expense_ids") or []) if value})
        if not ids:
            raise DPECostExpenseValidationError("Selecione ao menos uma despesa.", {"expense_ids": "Selecao vazia."})
        category_marker = payload.get("category_id", "__MISSING__")
        center_marker = payload.get("cost_center_id", "__MISSING__")
        scope_marker = payload.get("expense_scope", "__MISSING__")
        if category_marker == "__MISSING__" and center_marker == "__MISSING__" and scope_marker == "__MISSING__":
            raise DPECostExpenseValidationError("Informe categoria, setor ou tratamento para aplicar em massa.")
        category = self._category(int(category_marker)) if category_marker not in {"__MISSING__", None, ""} else None
        center = self._center(int(center_marker)) if center_marker not in {"__MISSING__", None, ""} else None
        bulk_scope = None
        if scope_marker != "__MISSING__":
            raw_scope = _text(scope_marker).upper()
            aliases = {"COMPARTILHADA": "SHARED", "SHARED": "SHARED", "INSTITUCIONAL": "INSTITUTIONAL", "INSTITUTIONAL": "INSTITUTIONAL"}
            bulk_scope = aliases.get(raw_scope, raw_scope)
            if bulk_scope not in {"SHARED", "INSTITUTIONAL"}:
                raise DPECostExpenseValidationError(
                    "Tratamento em massa inválido.",
                    {"expense_scope": "Em massa, use apenas Compartilhada ou Institucional. Despesa direta exige escolher um curso individualmente."},
                )
        rows = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.id.in_(ids),
                DPECostExpense.status == "ACTIVE",
            )
        ).all()
        if len(rows) != len(ids):
            raise DPECostExpenseValidationError("Uma ou mais despesas nao pertencem ao mes selecionado ou nao estao ativas.")
        before = [self._audit_snapshot(row) for row in rows]
        for row in rows:
            previous_scope = str(row.expense_scope or "SHARED").upper()
            if bulk_scope:
                row.expense_scope = bulk_scope
                if bulk_scope == "INSTITUTIONAL":
                    row.allocation_rule_id = None
                else:
                    current_category_for_scope = category if category_marker != "__MISSING__" else self._category(row.category_id)
                    candidate = self._rule(current_category_for_scope.default_rule_id)
                    row.allocation_rule_id = None if candidate and str(candidate.driver_type or "").upper() == "DIRECT" else (candidate.id if candidate else None)
                self._apply_scope_targets(row, direct_offering=None, previous_scope=previous_scope)
            if category_marker != "__MISSING__":
                if not category:
                    raise DPECostExpenseValidationError("Categoria obrigatoria para a classificacao em massa.")
                row.category_id = category.id
                scope = str(row.expense_scope or "SHARED").upper()
                if scope == "DIRECT":
                    row.allocation_rule_id = self._direct_rule().id
                elif scope == "INSTITUTIONAL":
                    row.allocation_rule_id = None
                else:
                    candidate = self._rule(category.default_rule_id)
                    row.allocation_rule_id = None if candidate and str(candidate.driver_type or "").upper() == "DIRECT" else (candidate.id if candidate else None)
            if center_marker != "__MISSING__":
                row.cost_center_id = center.id if center else None
            current_category = category if category_marker != "__MISSING__" else self._category(row.category_id)
            current_center = center if center_marker != "__MISSING__" else self._center(row.cost_center_id)
            rule = self._rule(row.allocation_rule_id)
            direct_target = self._direct_target(row.id) if str(row.expense_scope or "SHARED").upper() == "DIRECT" else None
            row.classification_snapshot_json = self._classification_snapshot(
                center=current_center, category=current_category, rule=rule, expense_scope=row.expense_scope or "SHARED",
                direct_offering=direct_target.period_offering if direct_target else None,
            )
            row.updated_by = self.actor
        add_dpe_audit(
            self.db,
            self.scope,
            action="bulk_classify",
            entity="dpe_expense_batch",
            entity_id=f"period:{period_id}",
            period_id=period_id,
            before=before,
            after=[self._audit_snapshot(row) for row in rows],
            metadata={"expense_ids": ids, "expense_scope": bulk_scope},
        )
        self._commit()
        return {"period_id": int(period_id), "updated_count": len(rows), "expense_ids": ids}

    def _period_offering_options(self, period_id: int | None) -> list[dict[str, Any]]:
        if not period_id:
            return []
        rows = self.db.scalars(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            ).order_by(DPECostPeriodOffering.id)
        ).all()
        return [
            {
                "id": row.id,
                "label": snapshot_context_label(dict(row.offering_snapshot_json or {})),
                "snapshot": dict(row.offering_snapshot_json or {}),
            }
            for row in rows
        ]

    def central_payload(self, *, period_id: int | None = None) -> dict[str, Any]:
        return {
            "summary": self.expense_summary(period_id=period_id),
            "cost_centers": self.list_cost_centers(),
            "categories": self.list_categories(),
            "expenses": self.list_expenses(period_id=period_id, status=None),
            "import_batches": self.list_import_batches(period_id=period_id),
            "source_types": list(EXPENSE_SOURCE_TYPES),
            "batch_source_types": list(BATCH_SOURCE_TYPES),
            "expense_kinds": list(EXPENSE_KINDS),
            "expense_scopes": list(EXPENSE_SCOPES),
            "period_offerings": self._period_offering_options(period_id),
            "staging_contract": {
                "adapter_neutral": True,
                "official_expense_table": "dpe_cost_expenses",
                "staging_table": "dpe_cost_expense_staging_rows",
                "automatic_commit_enabled": True,
            },
        }
