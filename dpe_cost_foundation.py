from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    DPEAcademicOffering,
    DPEAcademicProduct,
    DPEAllocationPolicy,
    DPEAllocationRule,
    DPECostCenter,
    DPECostPeriod,
    DPEExpenseCategory,
    DPECostExpense,
    DPECostExpenseImportBatch,
    DPECostExpenseStagingRow,
    DPECostPeriodTeacher,
    DPECostSubject,
    DPECostTeachingActivity,
    DPETeacherAlias,
    DPECostPeriodOfferingDriverValue,
    DPECostExpenseAllocationTarget,
    DPECostAllocationRun,
    DPECostAllocationResult,
    DPECostAllocationIssue,
)
from security import DirectorateScope

PERIOD_STATUSES = ("DRAFT", "REVIEW", "CALCULATED", "CLOSED")
ACADEMIC_LEVELS = ("GRADUATION", "TECHNICAL", "POSTGRADUATE", "EXTENSION", "OTHER")
ALLOCATION_DRIVERS = (
    "DIRECT",
    "TEACHER_HOURS",
    "OFFERING_HOURS",
    "STUDENTS",
    "REVENUE",
    "EQUAL",
    "MANUAL",
)
SYSTEM_ALLOCATION_RULE_CODES = ALLOCATION_DRIVERS


class DPECostFoundationRepository:
    """Read-only foundation contract for the new DPE cost domain.

    The foundation repository remains focused on metadata/readiness. Catalog and
    competence mutations are handled by dpe_cost_catalog.py from v0.9.6.14,
    keeping the legacy financial DPE isolated from the new cost engine.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("O Cost Engine pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    def _count(self, model: type[Any], *filters: Any) -> int:
        stmt = select(func.count()).select_from(model).where(model.directorate_id == self.directorate_id)
        if filters:
            stmt = stmt.where(*filters)
        return int(self.db.scalar(stmt) or 0)

    def list_allocation_rules(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        stmt = select(DPEAllocationRule).where(DPEAllocationRule.directorate_id == self.directorate_id)
        if active_only:
            stmt = stmt.where(DPEAllocationRule.active.is_(True))
        rows = self.db.scalars(stmt.order_by(DPEAllocationRule.system_defined.desc(), DPEAllocationRule.name)).all()
        return [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "driver_type": row.driver_type,
                "description": row.description,
                "parameters": dict(row.parameters_json or {}),
                "system_defined": bool(row.system_defined),
                "active": bool(row.active),
            }
            for row in rows
        ]

    def summary(self) -> dict[str, Any]:
        status_rows = self.db.execute(
            select(DPECostPeriod.status, func.count(DPECostPeriod.id))
            .where(DPECostPeriod.directorate_id == self.directorate_id)
            .group_by(DPECostPeriod.status)
        ).all()
        statuses = {status: 0 for status in PERIOD_STATUSES}
        for status, total in status_rows:
            statuses[str(status)] = int(total or 0)

        rules = self.list_allocation_rules(active_only=False)
        existing_system_codes = {row["code"] for row in rules if row["system_defined"]}
        missing_system_rules = [code for code in SYSTEM_ALLOCATION_RULE_CODES if code not in existing_system_codes]

        return {
            "engine": "DPE_COST_ENGINE",
            "foundation_version": 6,
            "write_surface_enabled": True,
            "catalog_operational": True,
            "competence_workflow": "DRAFT_REVIEW_CALCULATED",
            "expense_intake_operational": True,
            "expense_staging_adapter_neutral": True,
            "teaching_workload_operational": True,
            "teaching_activity_intramonth_validity": True,
            "allocation_engine_operational": True,
            "allocation_runs_versioned": True,
            "allocation_policies_reusable": True,
            "teacher_master_reused": "teachers",
            "teacher_history_boundary": "dpe_cost_period_teachers",
            "legacy_finance_preserved": True,
            "historical_boundary": "dpe_cost_periods",
            "cost_object": "dpe_academic_offerings",
            "period_statuses": list(PERIOD_STATUSES),
            "academic_levels": list(ACADEMIC_LEVELS),
            "allocation_drivers": list(ALLOCATION_DRIVERS),
            "counts": {
                "periods": self._count(DPECostPeriod),
                "academic_products": self._count(DPEAcademicProduct),
                "academic_offerings": self._count(DPEAcademicOffering),
                "cost_centers": self._count(DPECostCenter),
                "expense_categories": self._count(DPEExpenseCategory),
                "allocation_rules": self._count(DPEAllocationRule),
                "allocation_policies": self._count(DPEAllocationPolicy),
                "cost_expenses": self._count(DPECostExpense),
                "expense_import_batches": self._count(DPECostExpenseImportBatch),
                "expense_staging_rows": int(self.db.scalar(select(func.count()).select_from(DPECostExpenseStagingRow)) or 0),
                "period_teachers": self._count(DPECostPeriodTeacher),
                "teaching_subjects": self._count(DPECostSubject),
                "teaching_activities": self._count(DPECostTeachingActivity),
                "teacher_aliases": int(self.db.scalar(select(func.count()).select_from(DPETeacherAlias)) or 0),
                "driver_values": self._count(DPECostPeriodOfferingDriverValue),
                "allocation_targets": int(self.db.scalar(select(func.count()).select_from(DPECostExpenseAllocationTarget)) or 0),
                "allocation_runs": self._count(DPECostAllocationRun),
                "allocation_results": int(self.db.scalar(select(func.count()).select_from(DPECostAllocationResult)) or 0),
                "allocation_issues": int(self.db.scalar(select(func.count()).select_from(DPECostAllocationIssue)) or 0),
            },
            "periods_by_status": statuses,
            "system_rules": {
                "expected": list(SYSTEM_ALLOCATION_RULE_CODES),
                "missing": missing_system_rules,
                "ready": not missing_system_rules,
            },
        }
