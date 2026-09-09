from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, func, select, union
from sqlalchemy.orm import Session

from auth.objects import require_object_for_directorate
from models import (
    Course,
    DPECourseCostSnapshot,
    DPECourseRevenue,
    DPEExpense,
    DPEExpenseAllocation,
    DPEMonthlyRevenue,
    Directorate,
)
from security import DirectorateScope

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
EXPENSE_KINDS = {"GENERAL", "PAYROLL"}
EXPENSE_CATEGORIES = {"PERSONNEL", "OPERATIONAL", "ADMINISTRATIVE", "FINANCIAL", "OTHER"}
PAYROLL_GROUPS = {"FACULTY", "ADMINISTRATIVE", "OTHER"}
PAYROLL_NATURES = {"SALARY", "CHARGES", "PROVISIONS", "OTHER"}


class DPEFinanceValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _money(value: Any, *, field: str, allow_zero: bool = True) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DPEFinanceValidationError("Revise os valores informados.", {field: "Informe um valor numérico válido."}) from exc
    if amount < 0 or (not allow_zero and amount <= 0):
        rule = "maior que zero" if not allow_zero else "igual ou maior que zero"
        raise DPEFinanceValidationError("Revise os valores informados.", {field: f"O valor precisa ser {rule}."})
    return amount


def validate_month(period: Any) -> str:
    text = str(period or "").strip()
    if not MONTH_RE.fullmatch(text):
        raise DPEFinanceValidationError("Use a competência no formato AAAA-MM.", {"period": "Exemplo: 2026-08."})
    return text


class DPEFinanceRepository:
    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("Esta base financeira pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    def _require_write(self) -> None:
        if not self.scope.can_write:
            raise PermissionError("A DPE está disponível somente para leitura para este usuário.")

    def _audit_user(self) -> str | None:
        return self.scope.user.email or self.scope.user.user_id

    def _course(self, course_id: Any) -> tuple[Course, Directorate]:
        try:
            cid = int(course_id)
        except (TypeError, ValueError) as exc:
            raise DPEFinanceValidationError("Curso inválido.", {"course_id": "Selecione um curso do catálogo."}) from exc
        row = self.db.execute(
            select(Course, Directorate)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(
                Course.id == cid,
                Course.active.is_(True),
                Directorate.code.in_(("DTNH", "DCS")),
            )
        ).first()
        if not row:
            raise DPEFinanceValidationError(
                "Curso não encontrado no catálogo presencial da DPE.",
                {"course_id": "Use um curso ativo de DTNH ou DCS."},
            )
        return row[0], row[1]

    # ------------------------------------------------------------------
    # Revenue
    # ------------------------------------------------------------------
    def upsert_monthly_revenue(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        period = validate_month(payload.get("period"))
        amount = _money(payload.get("net_revenue"), field="net_revenue")
        row = self.db.scalar(
            select(DPEMonthlyRevenue).where(
                DPEMonthlyRevenue.directorate_id == self.directorate_id,
                DPEMonthlyRevenue.period == period,
            )
        )
        if not row:
            row = DPEMonthlyRevenue(
                directorate_id=self.directorate_id,
                period=period,
                net_revenue=amount,
                inserted_by=self._audit_user(),
            )
            self.db.add(row)
        else:
            row.net_revenue = amount
        row.notes = str(payload.get("notes") or "").strip() or None
        row.validated = bool(payload.get("validated", True))
        self.db.flush()
        # Course allocation is optional, but it can never exceed the official total.
        allocated = self.db.scalar(
            select(func.coalesce(func.sum(DPECourseRevenue.allocated_revenue), 0)).where(
                DPECourseRevenue.directorate_id == self.directorate_id,
                DPECourseRevenue.period == period,
            )
        ) or Decimal("0")
        if Decimal(allocated) > amount:
            self.db.rollback()
            raise DPEFinanceValidationError(
                "A nova receita institucional é menor que a receita já distribuída aos cursos.",
                {"net_revenue": f"Reduza as receitas por curso antes de informar um total inferior a {allocated}."},
            )
        self.db.commit()
        self.db.refresh(row)
        return self.revenue_to_dict(row)

    def list_monthly_revenues(self, *, periods: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        stmt = select(DPEMonthlyRevenue).where(DPEMonthlyRevenue.directorate_id == self.directorate_id)
        if periods is not None:
            clean_periods = [validate_month(value) for value in periods]
            if not clean_periods:
                return []
            stmt = stmt.where(DPEMonthlyRevenue.period.in_(clean_periods))
        rows = self.db.scalars(stmt.order_by(DPEMonthlyRevenue.period)).all()
        return [self.revenue_to_dict(row) for row in rows]

    def revenue_to_dict(self, row: DPEMonthlyRevenue) -> dict[str, Any]:
        return {
            "id": row.id,
            "period": row.period,
            "net_revenue": float(row.net_revenue),
            "notes": row.notes,
            "validated": bool(row.validated),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def upsert_course_revenue(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        period = validate_month(payload.get("period"))
        course, directorate = self._course(payload.get("course_id"))
        amount = _money(payload.get("allocated_revenue"), field="allocated_revenue")
        institutional = self.db.scalar(
            select(DPEMonthlyRevenue).where(
                DPEMonthlyRevenue.directorate_id == self.directorate_id,
                DPEMonthlyRevenue.period == period,
            )
        )
        if not institutional:
            raise DPEFinanceValidationError(
                "Cadastre primeiro a receita líquida institucional desta competência.",
                {"period": "A distribuição por curso é opcional, mas depende do total institucional."},
            )
        existing = self.db.scalar(
            select(DPECourseRevenue).where(
                DPECourseRevenue.directorate_id == self.directorate_id,
                DPECourseRevenue.period == period,
                DPECourseRevenue.course_id == course.id,
            )
        )
        others = self.db.scalar(
            select(func.coalesce(func.sum(DPECourseRevenue.allocated_revenue), 0)).where(
                DPECourseRevenue.directorate_id == self.directorate_id,
                DPECourseRevenue.period == period,
                DPECourseRevenue.course_id != course.id,
            )
        ) or Decimal("0")
        if Decimal(others) + amount > Decimal(institutional.net_revenue):
            available = Decimal(institutional.net_revenue) - Decimal(others)
            raise DPEFinanceValidationError(
                "A distribuição por curso não pode superar a receita institucional do mês.",
                {"allocated_revenue": f"Valor ainda disponível para distribuição: R$ {available:.2f}."},
            )
        if not existing:
            existing = DPECourseRevenue(
                directorate_id=self.directorate_id,
                period=period,
                course_id=course.id,
                allocated_revenue=amount,
                inserted_by=self._audit_user(),
            )
            self.db.add(existing)
        else:
            existing.allocated_revenue = amount
        existing.notes = str(payload.get("notes") or "").strip() or None
        self.db.commit()
        self.db.refresh(existing)
        return self.course_revenue_to_dict(existing, course=course, directorate=directorate)

    def delete_course_revenue(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(self.db, DPECourseRevenue, row_id, self.directorate_id, label="Receita por curso")
        self.db.delete(row)
        self.db.commit()

    def list_course_revenues(
        self,
        period: str | None = None,
        *,
        periods: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(DPECourseRevenue, Course, Directorate)
            .join(Course, Course.id == DPECourseRevenue.course_id)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(DPECourseRevenue.directorate_id == self.directorate_id)
        )
        if period:
            stmt = stmt.where(DPECourseRevenue.period == validate_month(period))
        elif periods is not None:
            clean_periods = [validate_month(value) for value in periods]
            if not clean_periods:
                return []
            stmt = stmt.where(DPECourseRevenue.period.in_(clean_periods))
        rows = self.db.execute(stmt.order_by(DPECourseRevenue.period, Directorate.code, Course.name)).all()
        return [self.course_revenue_to_dict(row, course=course, directorate=directorate) for row, course, directorate in rows]

    def course_revenue_to_dict(self, row: DPECourseRevenue, *, course: Course | None = None, directorate: Directorate | None = None) -> dict[str, Any]:
        if course is None or directorate is None:
            course, directorate = self._course(row.course_id)
        return {
            "id": row.id,
            "period": row.period,
            "course_id": row.course_id,
            "course_name": course.name,
            "academic_directorate": directorate.code,
            "allocated_revenue": float(row.allocated_revenue),
            "notes": row.notes,
        }

    # ------------------------------------------------------------------
    # Expenses and allocations
    # ------------------------------------------------------------------
    def create_expense(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        period = validate_month(payload.get("period"))
        description = str(payload.get("description") or "").strip()
        if not description:
            raise DPEFinanceValidationError("Informe a descrição da despesa.", {"description": "Campo obrigatório."})
        amount = _money(payload.get("amount"), field="amount", allow_zero=False)
        kind = str(payload.get("expense_kind") or "GENERAL").strip().upper()
        category = str(payload.get("category") or "OTHER").strip().upper()
        payroll_group = str(payload.get("payroll_group") or "").strip().upper() or None
        payroll_nature = str(payload.get("payroll_nature") or "").strip().upper() or None
        if kind not in EXPENSE_KINDS:
            raise DPEFinanceValidationError("Tipo de despesa inválido.", {"expense_kind": "Use GENERAL ou PAYROLL."})
        if category not in EXPENSE_CATEGORIES:
            raise DPEFinanceValidationError("Categoria inválida.", {"category": "Selecione uma categoria válida."})
        if kind == "PAYROLL":
            category = "PERSONNEL"
            if payroll_group not in PAYROLL_GROUPS:
                raise DPEFinanceValidationError("Informe o grupo da folha.", {"payroll_group": "Docente, administrativo ou outro."})
            if payroll_nature not in PAYROLL_NATURES:
                raise DPEFinanceValidationError("Informe a natureza da folha.", {"payroll_nature": "Salário, encargos, provisões ou outro."})
        else:
            payroll_group = None
            payroll_nature = None
        row = DPEExpense(
            directorate_id=self.directorate_id,
            period=period,
            description=description,
            amount=amount,
            expense_kind=kind,
            category=category,
            payroll_group=payroll_group,
            payroll_nature=payroll_nature,
            is_capex=bool(payload.get("is_capex", False)),
            notes=str(payload.get("notes") or "").strip() or None,
            validated=bool(payload.get("validated", True)),
            inserted_by=self._audit_user(),
        )
        self.db.add(row)
        self.db.flush()
        self._replace_allocations(row, payload.get("allocations") or [])
        self.db.commit()
        self.db.refresh(row)
        return self.expense_to_dict(row)

    def update_expense(self, row_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        row = require_object_for_directorate(self.db, DPEExpense, row_id, self.directorate_id, label="Despesa")
        merged = {
            "period": payload.get("period", row.period),
            "description": payload.get("description", row.description),
            "amount": payload.get("amount", row.amount),
            "expense_kind": payload.get("expense_kind", row.expense_kind),
            "category": payload.get("category", row.category),
            "payroll_group": payload.get("payroll_group", row.payroll_group),
            "payroll_nature": payload.get("payroll_nature", row.payroll_nature),
            "is_capex": payload.get("is_capex", row.is_capex),
            "notes": payload.get("notes", row.notes),
            "validated": payload.get("validated", row.validated),
        }
        period = validate_month(merged["period"])
        description = str(merged["description"] or "").strip()
        if not description:
            raise DPEFinanceValidationError("Informe a descrição da despesa.", {"description": "Campo obrigatório."})
        amount = _money(merged["amount"], field="amount", allow_zero=False)
        kind = str(merged["expense_kind"] or "GENERAL").strip().upper()
        category = str(merged["category"] or "OTHER").strip().upper()
        payroll_group = str(merged.get("payroll_group") or "").strip().upper() or None
        payroll_nature = str(merged.get("payroll_nature") or "").strip().upper() or None
        if kind not in EXPENSE_KINDS or category not in EXPENSE_CATEGORIES:
            raise DPEFinanceValidationError("Tipo ou categoria da despesa inválido.")
        if kind == "PAYROLL":
            category = "PERSONNEL"
            if payroll_group not in PAYROLL_GROUPS or payroll_nature not in PAYROLL_NATURES:
                raise DPEFinanceValidationError("Complete o grupo e a natureza da folha.")
        else:
            payroll_group = None
            payroll_nature = None
        row.period = period
        row.description = description
        row.amount = amount
        row.expense_kind = kind
        row.category = category
        row.payroll_group = payroll_group
        row.payroll_nature = payroll_nature
        row.is_capex = bool(merged["is_capex"])
        row.notes = str(merged.get("notes") or "").strip() or None
        row.validated = bool(merged.get("validated", True))
        if "allocations" in payload:
            self._replace_allocations(row, payload.get("allocations") or [])
        else:
            allocated = self.db.scalar(
                select(func.coalesce(func.sum(DPEExpenseAllocation.allocated_amount), 0)).where(
                    DPEExpenseAllocation.expense_id == row.id
                )
            ) or Decimal("0")
            if Decimal(allocated) > amount:
                raise DPEFinanceValidationError(
                    "O novo valor da despesa é menor que o total já rateado.",
                    {"amount": f"Total atualmente rateado: R$ {Decimal(allocated):.2f}."},
                )
        self.db.commit()
        self.db.refresh(row)
        return self.expense_to_dict(row)

    def _replace_allocations(self, expense: DPEExpense, allocations: list[dict[str, Any]]) -> None:
        if expense.id:
            self.db.execute(delete(DPEExpenseAllocation).where(DPEExpenseAllocation.expense_id == expense.id))
        total = Decimal("0")
        seen: set[int] = set()
        for index, item in enumerate(allocations):
            course, _ = self._course(item.get("course_id"))
            if course.id in seen:
                raise DPEFinanceValidationError(
                    "Um curso não pode aparecer duas vezes no mesmo rateio.",
                    {f"allocations.{index}.course_id": "Curso duplicado."},
                )
            seen.add(course.id)
            amount = _money(item.get("allocated_amount"), field=f"allocations.{index}.allocated_amount", allow_zero=False)
            total += amount
            self.db.add(DPEExpenseAllocation(
                expense_id=expense.id,
                course_id=course.id,
                allocated_amount=amount,
                notes=str(item.get("notes") or "").strip() or None,
                inserted_by=self._audit_user(),
            ))
        if total > Decimal(expense.amount):
            raise DPEFinanceValidationError(
                "O total rateado não pode superar o valor real da despesa.",
                {"allocations": f"Despesa: R$ {Decimal(expense.amount):.2f}; rateio: R$ {total:.2f}."},
            )

    def delete_expense(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(self.db, DPEExpense, row_id, self.directorate_id, label="Despesa")
        self.db.execute(delete(DPEExpenseAllocation).where(DPEExpenseAllocation.expense_id == row.id))
        self.db.delete(row)
        self.db.commit()

    def list_expenses(
        self,
        period: str | None = None,
        *,
        kind: str | None = None,
        periods: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(DPEExpense).where(DPEExpense.directorate_id == self.directorate_id)
        if period:
            stmt = stmt.where(DPEExpense.period == validate_month(period))
        elif periods is not None:
            clean_periods = [validate_month(value) for value in periods]
            if not clean_periods:
                return []
            stmt = stmt.where(DPEExpense.period.in_(clean_periods))
        if kind:
            stmt = stmt.where(DPEExpense.expense_kind == str(kind).upper())
        rows = self.db.scalars(stmt.order_by(DPEExpense.period.desc(), DPEExpense.id.desc())).all()
        if not rows:
            return []

        # Eager-load all allocations for the selected expense set in one query.
        # The previous implementation called expense_to_dict() once per expense and
        # executed an allocation SELECT for every row (classic N+1).
        expense_ids = [row.id for row in rows]
        allocation_rows = self.db.execute(
            select(DPEExpenseAllocation, Course, Directorate)
            .join(Course, Course.id == DPEExpenseAllocation.course_id)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(DPEExpenseAllocation.expense_id.in_(expense_ids))
            .order_by(DPEExpenseAllocation.expense_id, Directorate.code, Course.name)
        ).all()
        allocations_by_expense: dict[int, list[tuple[DPEExpenseAllocation, Course, Directorate]]] = {
            expense_id: [] for expense_id in expense_ids
        }
        for allocation, course, directorate in allocation_rows:
            allocations_by_expense.setdefault(allocation.expense_id, []).append((allocation, course, directorate))

        return [
            self.expense_to_dict(row, allocations=allocations_by_expense.get(row.id, []))
            for row in rows
        ]

    def expense_to_dict(
        self,
        row: DPEExpense,
        *,
        allocations: list[tuple[DPEExpenseAllocation, Course, Directorate]] | None = None,
    ) -> dict[str, Any]:
        if allocations is None:
            allocations = self.db.execute(
                select(DPEExpenseAllocation, Course, Directorate)
                .join(Course, Course.id == DPEExpenseAllocation.course_id)
                .join(Directorate, Directorate.id == Course.directorate_id)
                .where(DPEExpenseAllocation.expense_id == row.id)
                .order_by(Directorate.code, Course.name)
            ).all()
        allocated = sum(Decimal(a.allocated_amount) for a, _, _ in allocations)
        return {
            "id": row.id,
            "period": row.period,
            "description": row.description,
            "amount": float(row.amount),
            "expense_kind": row.expense_kind,
            "category": row.category,
            "payroll_group": row.payroll_group,
            "payroll_nature": row.payroll_nature,
            "is_capex": bool(row.is_capex),
            "notes": row.notes,
            "validated": bool(row.validated),
            "allocated_amount": float(allocated),
            "unallocated_amount": float(Decimal(row.amount) - allocated),
            "allocations": [
                {
                    "id": allocation.id,
                    "course_id": course.id,
                    "course_name": course.name,
                    "academic_directorate": directorate.code,
                    "allocated_amount": float(allocation.allocated_amount),
                    "percentage": float(Decimal(allocation.allocated_amount) / Decimal(row.amount) * 100) if row.amount else 0.0,
                }
                for allocation, course, directorate in allocations
            ],
        }

    def _course_cost_details(self, payload: dict[str, Any], total: Decimal) -> list[dict[str, Any]]:
        raw = payload.get("details") or []
        if not isinstance(raw, list):
            raise DPEFinanceValidationError(
                "Revise o detalhamento do custo.",
                {"details": "O detalhamento precisa ser uma lista de itens."},
            )
        details: list[dict[str, Any]] = []
        detail_total = Decimal("0")
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                raise DPEFinanceValidationError(
                    "Revise o detalhamento do custo.",
                    {"details": f"O item {index} é inválido."},
                )
            description = str(item.get("description") or "").strip()
            if not description:
                raise DPEFinanceValidationError(
                    "Revise o detalhamento do custo.",
                    {"details": f"Informe a descrição do item {index}."},
                )
            amount = _money(item.get("amount"), field="details", allow_zero=False)
            detail_total += amount
            details.append({"description": description[:180], "amount": float(amount)})
        if detail_total > total:
            raise DPEFinanceValidationError(
                "O detalhamento gerencial não pode superar o custo total informado do curso.",
                {"details": f"Itens somam {detail_total}, acima do total {total}."},
            )
        return details

    # ------------------------------------------------------------------
    # Course cost snapshots (reconciliation only)
    # ------------------------------------------------------------------
    def upsert_course_cost(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        period = validate_month(payload.get("period"))
        course, directorate = self._course(payload.get("course_id"))
        amount = _money(payload.get("reported_total_cost"), field="reported_total_cost")
        details = self._course_cost_details(payload, amount)
        row = self.db.scalar(
            select(DPECourseCostSnapshot).where(
                DPECourseCostSnapshot.directorate_id == self.directorate_id,
                DPECourseCostSnapshot.period == period,
                DPECourseCostSnapshot.course_id == course.id,
            )
        )
        if not row:
            row = DPECourseCostSnapshot(
                directorate_id=self.directorate_id,
                period=period,
                course_id=course.id,
                reported_total_cost=amount,
                inserted_by=self._audit_user(),
            )
            self.db.add(row)
        else:
            row.reported_total_cost = amount
        row.details_json = details
        row.notes = str(payload.get("notes") or "").strip() or None
        self.db.commit()
        self.db.refresh(row)
        return self.course_cost_to_dict(row, course=course, directorate=directorate)

    def delete_course_cost(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(self.db, DPECourseCostSnapshot, row_id, self.directorate_id, label="Custo informado do curso")
        self.db.delete(row)
        self.db.commit()

    def list_course_costs(
        self,
        period: str | None = None,
        *,
        periods: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(DPECourseCostSnapshot, Course, Directorate)
            .join(Course, Course.id == DPECourseCostSnapshot.course_id)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(DPECourseCostSnapshot.directorate_id == self.directorate_id)
        )
        if period:
            stmt = stmt.where(DPECourseCostSnapshot.period == validate_month(period))
        elif periods is not None:
            clean_periods = [validate_month(value) for value in periods]
            if not clean_periods:
                return []
            stmt = stmt.where(DPECourseCostSnapshot.period.in_(clean_periods))
        rows = self.db.execute(stmt.order_by(DPECourseCostSnapshot.period, Directorate.code, Course.name)).all()
        return [self.course_cost_to_dict(row, course=course, directorate=directorate) for row, course, directorate in rows]

    def course_cost_to_dict(self, row: DPECourseCostSnapshot, *, course: Course | None = None, directorate: Directorate | None = None) -> dict[str, Any]:
        if course is None or directorate is None:
            course, directorate = self._course(row.course_id)
        return {
            "id": row.id,
            "period": row.period,
            "course_id": row.course_id,
            "course_name": course.name,
            "academic_directorate": directorate.code,
            "reported_total_cost": float(row.reported_total_cost),
            "details": list(row.details_json or []),
            "detail_total": round(sum(float(item.get("amount") or 0) for item in (row.details_json or [])), 2),
            "notes": row.notes,
        }

    # ------------------------------------------------------------------
    # Read snapshot for analytics
    # ------------------------------------------------------------------
    def available_periods(
        self,
        *,
        reference: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Return distinct financial periods without materializing finance rows.

        Period strings use YYYY-MM, so lexical ordering is chronological.
        """
        reference_value = validate_month(reference) if reference else None

        def period_select(model):
            stmt = select(model.period.label("period")).where(model.directorate_id == self.directorate_id)
            if reference_value:
                stmt = stmt.where(model.period <= reference_value)
            return stmt

        periods_union = union(
            period_select(DPEMonthlyRevenue),
            period_select(DPECourseRevenue),
            period_select(DPEExpense),
            period_select(DPECourseCostSnapshot),
        ).subquery()
        stmt = select(periods_union.c.period).order_by(periods_union.c.period.desc())
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        return list(self.db.scalars(stmt).all())

    def snapshot(
        self,
        *,
        reference: str | None = None,
        window_months: int | None = 12,
    ) -> dict[str, Any]:
        """Build a bounded finance snapshot with enough lookback for rolling KPIs.

        The analytics layer exposes only ``window_months`` but calculates 12-month
        rolling ratios for every visible point. We therefore load at most eleven
        extra months before the visible window, rather than the entire history.
        """
        window = max(1, int(window_months or 12))
        lookback_periods = window + 11
        periods_desc = self.available_periods(reference=reference, limit=lookback_periods)
        periods = list(reversed(periods_desc))
        if not periods:
            return {"revenues": [], "course_revenues": [], "expenses": [], "course_costs": []}
        return {
            "revenues": self.list_monthly_revenues(periods=periods),
            "course_revenues": self.list_course_revenues(periods=periods),
            "expenses": self.list_expenses(periods=periods),
            "course_costs": self.list_course_costs(periods=periods),
        }
