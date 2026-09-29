from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit
from dpe_course_context import snapshot_context_label
from dpe_revenue_facts import revenue_facts
from models import (
    DPECostAllocationResult,
    DPECostAllocationRun,
    DPECostOfferingEconomics,
    DPECostPeriod,
    DPECostPeriodOffering,
)
from security import DirectorateScope
from dpe_cost_allocation import DPECostAllocationRepository

EDITABLE_PERIOD_STATUSES = ("DRAFT", "REVIEW")
SOURCE_TYPES = ("MANUAL", "IMPORT", "API", "REQUEST", "SYSTEM")
CENT = Decimal("0.01")


class DPECostEconomicsValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _text(value: Any, *, max_length: int | None = None) -> str:
    output = str(value or "").strip()
    return output[:max_length] if max_length and len(output) > max_length else output


def _integer(value: Any, field: str, *, allow_none: bool = False) -> int | None:
    if value in (None, "") and allow_none:
        return None
    try:
        output = int(value)
    except (TypeError, ValueError) as exc:
        raise DPECostEconomicsValidationError("Valor inválido.", {field: "Informe um número inteiro válido."}) from exc
    if output < 0:
        raise DPECostEconomicsValidationError("Valor inválido.", {field: "O valor não pode ser negativo."})
    return output


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _offering_parts(snapshot: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    product = dict(snapshot.get("product") or {})
    offering = dict(snapshot.get("offering") or {})
    return snapshot_context_label(snapshot), product, offering


class DPECostEconomicsRepository:
    """Course/context results and auxiliary student facts.

    Revenue is deliberately *not* persisted here anymore. ``dpe_revenue_entries``
    is the single source of truth for revenue. This repository keeps only the
    auxiliary active-student fact and combines it read-only with revenue facts
    and the selected allocation run to present course results.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A base econômica pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    @property
    def actor(self) -> str:
        return self.scope.user.email or self.scope.user.full_name or self.scope.user.user_id

    @staticmethod
    def _audit_snapshot(row: DPECostOfferingEconomics | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "period_offering_id": row.period_offering_id,
            "active_students": row.active_students,
            "source_type": row.source_type,
            "source_reference": row.source_reference,
            "notes": row.notes,
        }

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DPECostEconomicsValidationError(
                "Não foi possível salvar os dados auxiliares porque existe um registro equivalente ou referência inválida."
            ) from exc

    def _period(self, period_id: int, *, editable: bool = False) -> DPECostPeriod:
        row = self.db.scalar(select(DPECostPeriod).where(
            DPECostPeriod.id == int(period_id),
            DPECostPeriod.directorate_id == self.directorate_id,
        ))
        if not row:
            raise LookupError("Competência do Cost Engine não encontrada.")
        if editable and row.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostEconomicsValidationError(
                "A competência já possui cálculo oficial ou está fechada e não aceita alteração de alunos."
            )
        return row

    def _period_offering(self, period_id: int, period_offering_id: int) -> DPECostPeriodOffering:
        row = self.db.scalar(select(DPECostPeriodOffering).where(
            DPECostPeriodOffering.id == int(period_offering_id),
            DPECostPeriodOffering.period_id == int(period_id),
            DPECostPeriodOffering.included.is_(True),
        ))
        if not row:
            raise DPECostEconomicsValidationError(
                "Curso/contexto inválido para esta competência.",
                {"period_offering_id": "Selecione um curso/contexto incluído no mês."},
            )
        return row

    @staticmethod
    def _period_payload(row: DPECostPeriod) -> dict[str, Any]:
        return {"id": row.id, "period": row.period, "status": row.status, "editable": row.status in EDITABLE_PERIOD_STATUSES}

    @staticmethod
    def _economics_payload(row: DPECostOfferingEconomics | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": row.id,
            "period_id": row.period_id,
            "period_offering_id": row.period_offering_id,
            "active_students": row.active_students,
            "source_type": row.source_type,
            "source_reference": row.source_reference,
            "notes": row.notes,
            "created_at": _iso(row.created_at),
            "created_by": row.created_by,
            "updated_at": _iso(row.updated_at),
            "updated_by": row.updated_by,
        }

    def list_periods(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(select(DPECostPeriod).where(
            DPECostPeriod.directorate_id == self.directorate_id
        ).order_by(DPECostPeriod.period.desc())).all()
        return [self._period_payload(row) for row in rows]

    def _selected_run(self, period_id: int, run_id: int | None = None) -> DPECostAllocationRun | None:
        if run_id:
            row = self.db.scalar(select(DPECostAllocationRun).where(
                DPECostAllocationRun.id == int(run_id),
                DPECostAllocationRun.directorate_id == self.directorate_id,
                DPECostAllocationRun.period_id == int(period_id),
            ))
            if not row:
                raise LookupError("Versão de distribuição não encontrada para esta competência.")
            return row
        official = self.db.scalar(select(DPECostAllocationRun).where(
            DPECostAllocationRun.directorate_id == self.directorate_id,
            DPECostAllocationRun.period_id == int(period_id),
            DPECostAllocationRun.status == "OFFICIAL",
        ).order_by(DPECostAllocationRun.run_number.desc()))
        if official:
            return official
        return self.db.scalar(select(DPECostAllocationRun).where(
            DPECostAllocationRun.directorate_id == self.directorate_id,
            DPECostAllocationRun.period_id == int(period_id),
        ).order_by(DPECostAllocationRun.run_number.desc()))

    def _cost_map(self, run: DPECostAllocationRun | None) -> dict[int, Decimal]:
        if not run:
            return {}
        rows = self.db.execute(select(
            DPECostAllocationResult.period_offering_id,
            func.coalesce(func.sum(DPECostAllocationResult.allocated_amount), 0),
        ).where(DPECostAllocationResult.run_id == run.id).group_by(DPECostAllocationResult.period_offering_id)).all()
        return {int(oid): Decimal(str(value or 0)).quantize(CENT) for oid, value in rows}

    def _run_is_current(self, period_id: int, run: DPECostAllocationRun | None) -> bool:
        if not run or run.status not in {"CALCULATED", "OFFICIAL"}:
            return False
        if Decimal(run.unallocated_total or 0) != Decimal("0"):
            return False
        current = DPECostAllocationRepository(self.db, self.scope)._input_fingerprint(period_id)
        return bool(run.input_fingerprint and run.input_fingerprint == current)

    def _rows(self, period: DPECostPeriod, run: DPECostAllocationRun | None, *, run_current: bool) -> list[dict[str, Any]]:
        offerings = self.db.scalars(select(DPECostPeriodOffering).where(
            DPECostPeriodOffering.period_id == period.id,
            DPECostPeriodOffering.included.is_(True),
        ).order_by(DPECostPeriodOffering.id)).all()
        economics_rows = self.db.scalars(select(DPECostOfferingEconomics).where(
            DPECostOfferingEconomics.directorate_id == self.directorate_id,
            DPECostOfferingEconomics.period_id == period.id,
        )).all()
        economics = {row.period_offering_id: row for row in economics_rows}
        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        costs = self._cost_map(run)
        cost_available = bool(run_current)
        result: list[dict[str, Any]] = []
        for offering in offerings:
            label, product, offer = _offering_parts(dict(offering.offering_snapshot_json or {}))
            eco = self._economics_payload(economics.get(offering.id))
            revenue = revenues.attributed(offering.id)
            confirmed = revenues.is_confirmed(offering.id)
            cost = costs.get(offering.id, Decimal("0.00")) if cost_available else None
            economic_result = (revenue - cost).quantize(CENT) if confirmed and cost is not None else None
            margin = (economic_result / revenue * 100).quantize(Decimal("0.01")) if economic_result is not None and revenue > 0 else None
            active = eco.get("active_students") if eco else None
            cost_per_student = (cost / active).quantize(CENT) if cost is not None and active else None
            result.append({
                "period_offering_id": offering.id,
                "offering_id": offering.offering_id,
                "label": label,
                "product": product,
                "offering": offer,
                "economics": eco,
                "active_students": active,
                "revenue": float(revenue),
                "base_course_revenue": float(revenues.base(offering.id)),
                "students_ready": active is not None,
                "revenue_ready": confirmed,
                "cost_available": cost_available,
                "allocated_cost": float(cost) if cost is not None else None,
                "cost_per_active_student": float(cost_per_student) if cost_per_student is not None else None,
                "economic_result": float(economic_result) if economic_result is not None else None,
                "margin_percent": float(margin) if margin is not None else None,
            })
        return result

    @staticmethod
    def _aggregate(rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            if dimension == "product":
                key = str(row["product"].get("name") or "Sem produto")
            elif dimension == "modality":
                key = str(row["offering"].get("modality") or "Sem modalidade")
            else:
                key = str(row["offering"].get("shift") or "Sem turno")
            bucket = buckets.setdefault(key, {
                "key": key, "offering_count": 0, "active_students": 0,
                "revenue": Decimal("0.00"), "allocated_cost": Decimal("0.00"),
                "students_complete": True, "revenue_complete": True, "cost_complete": True,
            })
            bucket["offering_count"] += 1
            if row.get("active_students") is None:
                bucket["students_complete"] = False
            else:
                bucket["active_students"] += int(row["active_students"])
            bucket["revenue"] += Decimal(str(row.get("revenue") or 0))
            if not row.get("revenue_ready"):
                bucket["revenue_complete"] = False
            if row.get("allocated_cost") is None:
                bucket["cost_complete"] = False
            else:
                bucket["allocated_cost"] += Decimal(str(row["allocated_cost"]))
        output = []
        for key in sorted(buckets):
            bucket = buckets[key]
            revenue = bucket["revenue"].quantize(CENT)
            cost = bucket["allocated_cost"].quantize(CENT)
            result = (revenue - cost).quantize(CENT) if bucket["revenue_complete"] and bucket["cost_complete"] else None
            margin = (result / revenue * 100).quantize(Decimal("0.01")) if result is not None and revenue > 0 else None
            output.append({
                "key": key,
                "offering_count": bucket["offering_count"],
                "active_students": bucket["active_students"] if bucket["students_complete"] else None,
                "revenue": float(revenue),
                "allocated_cost": float(cost) if bucket["cost_complete"] else None,
                "economic_result": float(result) if result is not None else None,
                "margin_percent": float(margin) if margin is not None else None,
                "revenue_complete": bucket["revenue_complete"],
                "cost_complete": bucket["cost_complete"],
            })
        return output

    def central_payload(self, *, period_id: int | None = None, run_id: int | None = None) -> dict[str, Any]:
        periods = self.list_periods()
        if not periods:
            return {"periods": [], "selected_period": None, "selected_run": None, "rows": [], "summary": {}, "aggregates": {"product": [], "modality": [], "shift": []}, "editable": False}
        selected_id = int(period_id or periods[0]["id"])
        period = self._period(selected_id)
        run = self._selected_run(period.id, run_id)
        run_current = self._run_is_current(period.id, run)
        rows = self._rows(period, run, run_current=run_current)
        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        complete_revenue = bool(rows) and all(row["revenue_ready"] for row in rows)
        complete_students = bool(rows) and all(row["students_ready"] for row in rows)
        total_active = sum((int(row.get("active_students") or 0) for row in rows), 0)
        cost_available = bool(rows) and all(row["cost_available"] for row in rows)
        total_cost = sum((Decimal(str(row["allocated_cost"] or 0)) for row in rows), Decimal("0.00")) if cost_available else None
        course_result = (revenues.attributed_total - total_cost).quantize(CENT) if complete_revenue and total_cost is not None else None
        margin = (course_result / revenues.attributed_total * 100).quantize(Decimal("0.01")) if course_result is not None and revenues.attributed_total > 0 else None
        return {
            "periods": periods,
            "selected_period": self._period_payload(period),
            "selected_run": None if not run else {
                "id": run.id, "run_number": run.run_number, "status": run.status,
                "expense_total": float(run.expense_total or 0), "allocated_total": float(run.allocated_total or 0),
                "unallocated_total": float(run.unallocated_total or 0), "current": run_current,
            },
            "rows": rows,
            "summary": {
                "offering_count": len(rows),
                "student_ready_count": sum(1 for row in rows if row["students_ready"]),
                "revenue_ready_count": sum(1 for row in rows if row["revenue_ready"]),
                "complete_students": complete_students,
                "complete_revenue": complete_revenue,
                "active_students": total_active if complete_students else None,
                "course_revenue": float(revenues.attributed_total),
                "institutional_revenue": float(revenues.institutional_total),
                "total_revenue": float(revenues.total_revenue),
                "allocated_cost": float(total_cost) if total_cost is not None else None,
                "economic_result": float(course_result) if course_result is not None else None,
                "margin_percent": float(margin) if margin is not None else None,
            },
            "aggregates": {
                "product": self._aggregate(rows, "product"),
                "modality": self._aggregate(rows, "modality"),
                "shift": self._aggregate(rows, "shift"),
            },
            "editable": period.status in EDITABLE_PERIOD_STATUSES,
        }

    def _apply_upsert(self, period: DPECostPeriod, period_offering_id: int, payload: dict[str, Any]) -> DPECostOfferingEconomics:
        offering = self._period_offering(period.id, period_offering_id)
        legacy_fields = ("paying_students", "gross_revenue", "scholarships_discounts", "other_deductions", "net_revenue", "revenue_type")
        if any(payload.get(key) not in (None, "", 0, 0.0) for key in legacy_fields):
            raise DPECostEconomicsValidationError(
                "Receitas são registradas exclusivamente na área Receitas.",
                {"revenue": "Use o ledger de Receitas; esta tela aceita somente alunos ativos e metadados auxiliares."},
            )
        active = _integer(payload.get("active_students"), "active_students", allow_none=True)
        source_type = _text(payload.get("source_type") or "MANUAL").upper()
        if source_type not in SOURCE_TYPES:
            raise DPECostEconomicsValidationError("Origem inválida.", {"source_type": "Origem não reconhecida."})
        row = self.db.scalar(select(DPECostOfferingEconomics).where(DPECostOfferingEconomics.period_offering_id == offering.id))
        if not row:
            row = DPECostOfferingEconomics(
                directorate_id=self.directorate_id,
                period_id=period.id,
                period_offering_id=offering.id,
                created_by=self.actor,
                updated_by=self.actor,
            )
            self.db.add(row)
        row.active_students = active
        row.source_type = source_type
        row.source_reference = _text(payload.get("source_reference"), max_length=255) or None
        row.notes = _text(payload.get("notes")) or None
        row.updated_by = self.actor
        return row

    def upsert(self, period_id: int, period_offering_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        prior = self.db.scalar(select(DPECostOfferingEconomics).where(
            DPECostOfferingEconomics.period_id == period.id,
            DPECostOfferingEconomics.period_offering_id == int(period_offering_id),
        ))
        before = self._audit_snapshot(prior)
        row = self._apply_upsert(period, period_offering_id, payload)
        self.db.flush()
        add_dpe_audit(self.db, self.scope, action="upsert_students", entity="dpe_economics", entity_id=row.id, period_id=period.id, before=before, after=self._audit_snapshot(row))
        self._commit()
        self.db.refresh(row)
        return self._economics_payload(row) or {}

    def upsert_many(self, period_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
        period = self._period(period_id, editable=True)
        if not isinstance(items, list) or not items:
            raise DPECostEconomicsValidationError("Nenhuma linha foi enviada para atualização.", {"items": "Informe ao menos um curso/contexto."})
        if len(items) > 500:
            raise DPECostEconomicsValidationError("A grade possui linhas demais para uma única atualização.", {"items": "Envie no máximo 500 linhas por operação."})
        seen: set[int] = set()
        validated: list[tuple[int, dict[str, Any]]] = []
        legacy_fields = ("paying_students", "gross_revenue", "scholarships_discounts", "other_deductions", "net_revenue", "revenue_type")
        # Preflight every row before mutating the session so the grid is atomic even
        # when a later row contains an invalid or legacy revenue payload.
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise DPECostEconomicsValidationError("Revise a grade de alunos.", {f"items.{index}": "Linha inválida."})
            try:
                oid = int(item.get("period_offering_id"))
            except (TypeError, ValueError) as exc:
                raise DPECostEconomicsValidationError("Revise a grade de alunos.", {f"items.{index}.period_offering_id": "Curso/contexto inválido."}) from exc
            if oid in seen:
                raise DPECostEconomicsValidationError("O mesmo curso/contexto apareceu mais de uma vez na grade.", {f"items.{index}.period_offering_id": "Remova a linha duplicada."})
            seen.add(oid)
            self._period_offering(period.id, oid)
            if any(item.get(key) not in (None, "", 0, 0.0) for key in legacy_fields):
                raise DPECostEconomicsValidationError(
                    "Receitas são registradas exclusivamente na área Receitas.",
                    {f"items.{index}.revenue": "Use o ledger de Receitas; esta tela aceita somente alunos ativos e metadados auxiliares."},
                )
            _integer(item.get("active_students"), "active_students", allow_none=True)
            validated.append((oid, item))

        rows: list[DPECostOfferingEconomics] = []
        before_map = {int(row.period_offering_id): self._audit_snapshot(row) for row in self.db.scalars(select(DPECostOfferingEconomics).where(
            DPECostOfferingEconomics.directorate_id == self.directorate_id,
            DPECostOfferingEconomics.period_id == period.id,
        )).all()}
        for oid, item in validated:
            rows.append(self._apply_upsert(period, oid, item))
        self.db.flush()
        add_dpe_audit(
            self.db, self.scope, action="bulk_upsert_students", entity="dpe_economics", entity_id=str(period.id), period_id=period.id,
            before={str(oid): before_map.get(oid) for oid in seen},
            after={str(row.period_offering_id): self._audit_snapshot(row) for row in rows},
        )
        self._commit()
        return {"updated_count": len(rows), "items": [self._economics_payload(row) for row in rows]}
