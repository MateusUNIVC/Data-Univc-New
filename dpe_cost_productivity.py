from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit
from dpe_cost_allocation import DPECostAllocationRepository, DPECostAllocationValidationError
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_revenues import DPERevenueRepository
from dpe_revenue_facts import revenue_facts
from dpe_cost_expenses import DPECostExpenseRepository, DPECostExpenseValidationError
from dpe_cost_teaching import DPECostTeachingRepository
from models import (
    DPEAllocationPolicy,
    DPECostCenter,
    DPECostExpense,
    DPECostOfferingEconomics,
    DPECostPeriod,
    DPECostPeriodOffering,
    DPECostTeachingActivity,
    DPECostTeachingActivityOffering,
    DPECostPeriodTeacher,
    DPEExpenseCategory,
    DPERecurringExpenseTemplate,
)
from security import DirectorateScope

EDITABLE_PERIOD_STATUSES = ("DRAFT", "REVIEW")
CENT = Decimal("0.01")


class DPECostProductivityValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _text(value: Any, max_length: int | None = None) -> str:
    result = str(value or "").strip()
    return result[:max_length] if max_length and len(result) > max_length else result


def _money(value: Any) -> Decimal:
    try:
        if isinstance(value, str):
            raw = value.strip().replace("R$", "").replace(" ", "")
            if "," in raw and "." in raw:
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", ".")
            value = raw
        output = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DPECostProductivityValidationError("Valor invalido.", {"amount": "Informe um valor monetario valido."}) from exc
    if output <= 0:
        raise DPECostProductivityValidationError("O valor deve ser maior que zero.", {"amount": "Valor invalido."})
    return output


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value else None)


class DPECostProductivityRepository:
    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A produtividade financeira pertence exclusivamente a DPE.")
        self.db = db
        self.scope = scope
        self.expenses = DPECostExpenseRepository(db, scope)
        self.economics = DPECostEconomicsRepository(db, scope)
        self.revenues = DPERevenueRepository(db, scope)
        self.teaching = DPECostTeachingRepository(db, scope)
        self.allocation = DPECostAllocationRepository(db, scope)

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
            raise DPECostProductivityValidationError("Nao foi possivel concluir a operacao por conflito de dados.") from exc

    def _period(self, period_id: int, *, editable: bool = False) -> DPECostPeriod:
        row = self.db.scalar(
            select(DPECostPeriod).where(
                DPECostPeriod.id == int(period_id),
                DPECostPeriod.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Competencia nao encontrada.")
        if editable and row.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostProductivityValidationError("O mes selecionado nao aceita alteracoes.")
        return row

    def _period_offering_map(self, period_id: int) -> dict[int, DPECostPeriodOffering]:
        rows = self.db.scalars(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            )
        ).all()
        return {int(row.offering_id): row for row in rows}

    def previous_period(self, target_period_id: int) -> dict[str, Any] | None:
        target = self._period(target_period_id)
        row = self.db.scalar(
            select(DPECostPeriod)
            .where(
                DPECostPeriod.directorate_id == self.directorate_id,
                DPECostPeriod.period < target.period,
            )
            .order_by(DPECostPeriod.period.desc())
            .limit(1)
        )
        return None if not row else {"id": row.id, "period": row.period, "status": row.status}

    def copy_preview(self, source_period_id: int, target_period_id: int) -> dict[str, Any]:
        source = self._period(source_period_id)
        target = self._period(target_period_id, editable=True)
        if source.id == target.id:
            raise DPECostProductivityValidationError("Escolha meses diferentes para copiar dados.")
        source_map = self._period_offering_map(source.id)
        target_map = self._period_offering_map(target.id)
        common_offerings = set(source_map).intersection(target_map)
        source_revenues = revenue_facts(self.db, self.directorate_id, source.id)
        source_economics = {
            row.period_offering_id: row
            for row in self.db.scalars(
                select(DPECostOfferingEconomics).where(DPECostOfferingEconomics.period_id == source.id)
            ).all()
        }
        revenue_copyable = 0
        student_copyable = 0
        for stable_id in common_offerings:
            source_period_offering = source_map[stable_id]
            if source_revenues.is_confirmed(source_period_offering.id):
                revenue_copyable += 1
            eco = source_economics.get(source_period_offering.id)
            if eco and eco.active_students is not None:
                student_copyable += 1

        activities = self.db.scalars(
            select(DPECostTeachingActivity).where(
                DPECostTeachingActivity.period_id == source.id,
                DPECostTeachingActivity.status == "ACTIVE",
            )
        ).all()
        teaching_copyable = 0
        teaching_blocked = 0
        for activity in activities:
            allocations = self.db.scalars(
                select(DPECostTeachingActivityOffering).where(DPECostTeachingActivityOffering.activity_id == activity.id)
            ).all()
            stable_ids = {
                self.db.get(DPECostPeriodOffering, alloc.period_offering_id).offering_id
                for alloc in allocations
                if self.db.get(DPECostPeriodOffering, alloc.period_offering_id)
            }
            if stable_ids and stable_ids.issubset(common_offerings):
                teaching_copyable += 1
            else:
                teaching_blocked += 1
        return {
            "source_period": {"id": source.id, "period": source.period, "status": source.status},
            "target_period": {"id": target.id, "period": target.period, "status": target.status},
            "common_offering_count": len(common_offerings),
            "source_offering_count": len(source_map),
            "target_offering_count": len(target_map),
            "revenues": {
                "copyable": revenue_copyable,
                "students_copyable": student_copyable,
                "source_count": len(source_revenues.confirmed_offering_ids),
            },
            "teaching": {"copyable": teaching_copyable, "blocked": teaching_blocked, "source_count": len(activities)},
            "warning": "Receitas de curso e alunos ativos copiados viram ponto de partida do novo mês e devem ser revisados antes do fechamento.",
        }

    def copy_revenues(self, source_period_id: int, target_period_id: int, *, overwrite: bool = False) -> dict[str, Any]:
        source = self._period(source_period_id)
        target = self._period(target_period_id, editable=True)
        source_map = self._period_offering_map(source.id)
        target_map = self._period_offering_map(target.id)
        common_offerings = set(source_map).intersection(target_map)
        source_facts = revenue_facts(self.db, self.directorate_id, source.id)
        target_facts = revenue_facts(self.db, self.directorate_id, target.id)
        source_economics = {
            row.period_offering_id: row
            for row in self.db.scalars(
                select(DPECostOfferingEconomics).where(DPECostOfferingEconomics.period_id == source.id)
            ).all()
        }
        target_economics = {
            row.period_offering_id: row
            for row in self.db.scalars(
                select(DPECostOfferingEconomics).where(DPECostOfferingEconomics.period_id == target.id)
            ).all()
        }

        revenue_items: list[dict[str, Any]] = []
        student_items: list[dict[str, Any]] = []
        revenue_skipped = 0
        student_skipped = 0
        for stable_id in common_offerings:
            source_po = source_map[stable_id]
            target_po = target_map[stable_id]
            if source_facts.is_confirmed(source_po.id):
                if target_facts.is_confirmed(target_po.id) and not overwrite:
                    revenue_skipped += 1
                else:
                    revenue_items.append({
                        "period_offering_id": target_po.id,
                        "amount": float(source_facts.base(source_po.id)),
                    })
            source_eco = source_economics.get(source_po.id)
            if source_eco and source_eco.active_students is not None:
                target_eco = target_economics.get(target_po.id)
                if target_eco and target_eco.active_students is not None and not overwrite:
                    student_skipped += 1
                else:
                    student_items.append({
                        "period_offering_id": target_po.id,
                        "active_students": source_eco.active_students,
                        "source_type": "SYSTEM",
                        "source_reference": f"Copiado de {source.period}",
                        "notes": f"Alunos ativos copiados de {source.period} como ponto de partida. Revise antes do fechamento.",
                    })

        revenue_copied = 0
        student_copied = 0
        if revenue_items:
            revenue_copied = int(self.revenues.bulk_courses(target.id, revenue_items).get("updated_count") or 0)
        if student_items:
            student_copied = int(self.economics.upsert_many(target.id, student_items).get("updated_count") or 0)
        add_dpe_audit(
            self.db,
            self.scope,
            action="copy_revenues",
            entity="dpe_productivity",
            entity_id=f"period:{target.id}",
            period_id=target.id,
            after={
                "revenue_copied": revenue_copied,
                "student_copied": student_copied,
                "revenue_skipped": revenue_skipped,
                "student_skipped": student_skipped,
            },
            metadata={"source_period_id": source.id, "source_period": source.period},
        )
        self._commit()
        return {
            "copied": revenue_copied,
            "revenue_copied": revenue_copied,
            "student_copied": student_copied,
            "skipped": revenue_skipped,
            "student_skipped": student_skipped,
            "period_id": target.id,
        }

    def copy_teaching(self, source_period_id: int, target_period_id: int) -> dict[str, Any]:
        source = self._period(source_period_id)
        target = self._period(target_period_id, editable=True)
        source_offerings = {row.id: row for row in self._period_offering_map(source.id).values()}
        target_by_stable = self._period_offering_map(target.id)
        existing_keys = {
            row.external_key for row in self.db.scalars(
                select(DPECostTeachingActivity).where(
                    DPECostTeachingActivity.period_id == target.id,
                    DPECostTeachingActivity.status == "ACTIVE",
                    DPECostTeachingActivity.external_key.is_not(None),
                )
            ).all() if row.external_key
        }
        copied = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        for activity in self.teaching.list_activities(period_id=source.id, status="ACTIVE"):
            external_key = f"COPY-{source.id}-{activity['id']}-{target.period}"
            if external_key in existing_keys:
                skipped += 1
                continue
            allocations = []
            blocked = False
            for alloc in activity.get("allocations") or []:
                source_snapshot = source_offerings.get(int(alloc["period_offering_id"]))
                if not source_snapshot or source_snapshot.offering_id not in target_by_stable:
                    blocked = True
                    break
                allocations.append({
                    "period_offering_id": target_by_stable[source_snapshot.offering_id].id,
                    "allocated_hours": alloc["allocated_hours"],
                })
            if blocked or not allocations:
                skipped += 1
                errors.append({"activity_id": activity["id"], "error": "Um curso/contexto do quadro anterior não existe no novo mês."})
                continue
            payload = {
                "period_id": target.id,
                "teacher_id": activity["teacher_id"],
                "subject_id": activity["subject_id"],
                "class_group": activity.get("class_group"),
                "workload_hours": activity["workload_hours"],
                "workload_reference": activity.get("workload_reference"),
                "source_type": "OTHER",
                "external_key": external_key,
                "offering_allocations": allocations,
                "notes": f"Quadro copiado de {source.period}. Revise antes do fechamento.",
            }
            try:
                self.teaching.create_activity(payload)
                existing_keys.add(external_key)
                copied += 1
            except Exception as exc:
                errors.append({"activity_id": activity["id"], "error": str(exc)})
        add_dpe_audit(
            self.db,
            self.scope,
            action="copy_teaching",
            entity="dpe_productivity",
            entity_id=f"period:{target.id}",
            period_id=target.id,
            after={"copied": copied, "skipped": skipped, "error_count": len(errors)},
            metadata={"source_period_id": source.id, "source_period": source.period},
        )
        self._commit()
        return {"copied": copied, "skipped": skipped, "errors": errors, "period_id": target.id}

    # ------------------------------------------------------------------
    # Recurring expense templates
    # ------------------------------------------------------------------
    def _recurring_payload(self, row: DPERecurringExpenseTemplate) -> dict[str, Any]:
        center = self.db.get(DPECostCenter, row.cost_center_id) if row.cost_center_id else None
        category = self.db.get(DPEExpenseCategory, row.category_id)
        policy = self.db.get(DPEAllocationPolicy, row.allocation_policy_id) if row.allocation_policy_id else None
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "amount": float(row.amount),
            "expense_kind": row.expense_kind,
            "counterparty_name": row.counterparty_name,
            "cost_center_id": row.cost_center_id,
            "cost_center_name": center.name if center else None,
            "category_id": row.category_id,
            "category_name": category.name if category else None,
            "allocation_policy_id": row.allocation_policy_id,
            "allocation_policy_name": policy.name if policy else None,
            "day_of_month": row.day_of_month,
            "notes": row.notes,
            "active": bool(row.active),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def list_recurring_templates(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = select(DPERecurringExpenseTemplate).where(DPERecurringExpenseTemplate.directorate_id == self.directorate_id)
        if active_only:
            stmt = stmt.where(DPERecurringExpenseTemplate.active.is_(True))
        rows = self.db.scalars(stmt.order_by(DPERecurringExpenseTemplate.name)).all()
        return [self._recurring_payload(row) for row in rows]

    def save_recurring_template(self, payload: dict[str, Any], template_id: int | None = None) -> dict[str, Any]:
        row = self.db.get(DPERecurringExpenseTemplate, int(template_id)) if template_id else None
        if row and row.directorate_id != self.directorate_id:
            raise LookupError("Modelo recorrente nao encontrado.")
        name = _text(payload.get("name", row.name if row else ""), 180)
        description = _text(payload.get("description", row.description if row else ""), 280)
        if not name or not description:
            raise DPECostProductivityValidationError("Nome e descricao sao obrigatorios.")
        amount = _money(payload.get("amount", row.amount if row else None))
        kind = _text(payload.get("expense_kind", row.expense_kind if row else "GENERAL")).upper()
        if kind not in {"GENERAL", "PAYROLL"}:
            raise DPECostProductivityValidationError("Tipo de despesa invalido.")
        category_id = int(payload.get("category_id", row.category_id if row else 0) or 0)
        category = self.db.scalar(select(DPEExpenseCategory).where(DPEExpenseCategory.id == category_id, DPEExpenseCategory.directorate_id == self.directorate_id))
        if not category:
            raise DPECostProductivityValidationError("Categoria invalida.")
        center_marker = payload.get("cost_center_id", row.cost_center_id if row else None)
        center = None
        if center_marker:
            center = self.db.scalar(select(DPECostCenter).where(DPECostCenter.id == int(center_marker), DPECostCenter.directorate_id == self.directorate_id))
            if not center:
                raise DPECostProductivityValidationError("Setor invalido.")
        policy_marker = payload.get("allocation_policy_id", row.allocation_policy_id if row else None)
        policy = None
        if policy_marker:
            policy = self.db.scalar(select(DPEAllocationPolicy).where(DPEAllocationPolicy.id == int(policy_marker), DPEAllocationPolicy.directorate_id == self.directorate_id))
            if not policy:
                raise DPECostProductivityValidationError("Politica de distribuicao invalida.")
        day_marker = payload.get("day_of_month", row.day_of_month if row else None)
        day = int(day_marker) if day_marker not in (None, "") else None
        if day is not None and not 1 <= day <= 31:
            raise DPECostProductivityValidationError("Dia do mes deve ficar entre 1 e 31.")
        before = self._recurring_payload(row) if row else None
        if not row:
            row = DPERecurringExpenseTemplate(directorate_id=self.directorate_id, created_by=self.actor)
            self.db.add(row)
        row.name = name
        row.description = description
        row.amount = amount
        row.expense_kind = kind
        row.counterparty_name = _text(payload.get("counterparty_name", row.counterparty_name if row else ""), 240) or None
        row.cost_center_id = center.id if center else None
        row.category_id = category.id
        row.allocation_policy_id = policy.id if policy else None
        row.day_of_month = day
        row.notes = _text(payload.get("notes", row.notes if row else "")) or None
        row.active = bool(payload.get("active", row.active if template_id else True))
        row.updated_by = self.actor
        self.db.flush()
        add_dpe_audit(
            self.db,
            self.scope,
            action="update_recurring_template" if before else "create_recurring_template",
            entity="dpe_recurring_template",
            entity_id=row.id,
            before=before,
            after=self._recurring_payload(row),
        )
        self._commit()
        self.db.refresh(row)
        return self._recurring_payload(row)

    def generate_recurring(self, period_id: int, template_ids: list[int] | None = None) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        stmt = select(DPERecurringExpenseTemplate).where(
            DPERecurringExpenseTemplate.directorate_id == self.directorate_id,
            DPERecurringExpenseTemplate.active.is_(True),
        )
        if template_ids:
            stmt = stmt.where(DPERecurringExpenseTemplate.id.in_([int(value) for value in template_ids]))
        templates = self.db.scalars(stmt.order_by(DPERecurringExpenseTemplate.name)).all()
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        year, month = [int(value) for value in period.period.split("-")]
        for template in templates:
            external_key = f"RECUR-{template.id}-{period.period}"
            existing = self.db.scalar(
                select(DPECostExpense).where(
                    DPECostExpense.directorate_id == self.directorate_id,
                    DPECostExpense.period_id == period.id,
                    DPECostExpense.external_key == external_key,
                    DPECostExpense.status == "ACTIVE",
                )
            )
            if existing:
                skipped.append({"template_id": template.id, "reason": "already_generated", "expense_id": existing.id})
                continue
            day = min(template.day_of_month or 1, calendar.monthrange(year, month)[1])
            policy = self.db.get(DPEAllocationPolicy, template.allocation_policy_id) if template.allocation_policy_id else None
            expense = self.expenses.create_expense({
                "period_id": period.id,
                "expense_date": date(year, month, day).isoformat(),
                "description": template.description,
                "amount": float(template.amount),
                "expense_kind": template.expense_kind,
                "counterparty_name": template.counterparty_name,
                "cost_center_id": template.cost_center_id,
                "category_id": template.category_id,
                "allocation_rule_id": policy.allocation_rule_id if policy else None,
                "source_type": "OTHER",
                "source_reference": f"Recorrencia: {template.name}",
                "external_key": external_key,
                "source_payload": {"recurring_template_id": template.id},
                "notes": template.notes,
            })
            if policy:
                try:
                    resolved = self.allocation.resolve_policy_for_expense(expense["id"], policy.id)
                    self.allocation.set_expense_config(expense["id"], resolved["config"])
                except DPECostAllocationValidationError as exc:
                    skipped.append({"template_id": template.id, "expense_id": expense["id"], "reason": "policy_not_applied", "detail": str(exc)})
            created.append(expense)
        add_dpe_audit(
            self.db,
            self.scope,
            action="generate_recurring",
            entity="dpe_productivity",
            entity_id=f"period:{period.id}",
            period_id=period.id,
            after={"created_count": len(created), "expense_ids": [row["id"] for row in created], "skipped_count": len(skipped)},
            metadata={"template_ids": [row.id for row in templates]},
        )
        self._commit()
        return {"period_id": period.id, "created_count": len(created), "created": created, "skipped": skipped}

    def central_payload(self, period_id: int | None = None) -> dict[str, Any]:
        period = self._period(period_id) if period_id else None
        previous = self.previous_period(period.id) if period else None
        return {
            "selected_period": None if not period else {"id": period.id, "period": period.period, "status": period.status},
            "previous_period": previous,
            "recurring_templates": self.list_recurring_templates(),
            "editable": bool(period and period.status in EDITABLE_PERIOD_STATUSES),
        }
