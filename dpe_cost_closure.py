from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit, list_dpe_period_audit, parse_audit_details
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_revenue_facts import revenue_facts
from models import (
    AuditLog,
    DPECostAllocationIssue,
    DPECostAllocationRun,
    DPECostExpense,
    DPECostExpenseImportBatch,
    DPECostOfferingEconomics,
    DPECostPeriod,
    DPECostPeriodEvent,
    DPECostPeriodOffering,
)
from security import DirectorateScope

CENT = Decimal("0.01")


class DPECostClosureValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _text(value: Any, *, max_length: int | None = None) -> str:
    output = str(value or "").strip()
    return output[:max_length] if max_length and len(output) > max_length else output


class DPECostClosureRepository:
    """Monthly close/reopen governance for the DPE Cost Engine.

    Closing is intentionally stricter than calculation. A competence must have
    a current official allocation run, complete economic inputs and no blocking
    readiness issue. Reopening never erases a prior close; it records an
    immutable event and returns the competence to REVIEW for controlled edits.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("O fechamento mensal pertence exclusivamente à DPE.")
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
            raise DPECostClosureValidationError(
                "Não foi possível concluir a operação de fechamento por uma inconsistência de referência."
            ) from exc

    def _period(self, period_id: int) -> DPECostPeriod:
        row = self.db.scalar(
            select(DPECostPeriod).where(
                DPECostPeriod.id == int(period_id),
                DPECostPeriod.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Competência do Cost Engine não encontrada.")
        return row

    def _official_run(self, period_id: int) -> DPECostAllocationRun | None:
        return self.db.scalar(
            select(DPECostAllocationRun).where(
                DPECostAllocationRun.directorate_id == self.directorate_id,
                DPECostAllocationRun.period_id == int(period_id),
                DPECostAllocationRun.status == "OFFICIAL",
            ).order_by(DPECostAllocationRun.run_number.desc())
        )

    def _event_payload(self, row: DPECostPeriodEvent) -> dict[str, Any]:
        run_number = None
        if row.allocation_run_id:
            run_number = self.db.scalar(
                select(DPECostAllocationRun.run_number).where(DPECostAllocationRun.id == row.allocation_run_id)
            )
        return {
            "id": row.id,
            "period_id": row.period_id,
            "event_type": row.event_type,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "allocation_run_id": row.allocation_run_id,
            "allocation_run_number": int(run_number) if run_number is not None else None,
            "reason": row.reason,
            "checklist": dict(row.checklist_json or {}),
            "metadata": dict(row.metadata_json or {}),
            "created_at": _iso(row.created_at),
            "created_by": row.created_by,
        }

    def list_events(self, period_id: int) -> list[dict[str, Any]]:
        self._period(period_id)
        rows = self.db.scalars(
            select(DPECostPeriodEvent).where(
                DPECostPeriodEvent.directorate_id == self.directorate_id,
                DPECostPeriodEvent.period_id == int(period_id),
            ).order_by(DPECostPeriodEvent.created_at.desc(), DPECostPeriodEvent.id.desc())
        ).all()
        return [self._event_payload(row) for row in rows]

    @staticmethod
    def _check(code: str, label: str, status: str, detail: str, **context: Any) -> dict[str, Any]:
        return {"code": code, "label": label, "status": status, "detail": detail, "context": context}

    @staticmethod
    def _warning_review_key(period_id: int, check: dict[str, Any]) -> str:
        payload = {
            "period_id": int(period_id),
            "code": check.get("code"),
            "context": check.get("context") or {},
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        return f"{period_id}:{check.get('code')}:{digest}"

    def _warning_review(self, review_key: str) -> dict[str, Any] | None:
        row = self.db.scalar(
            select(AuditLog).where(
                AuditLog.directorate_id == self.directorate_id,
                AuditLog.action == "review_warning",
                AuditLog.entity == "dpe_governance_warning",
                AuditLog.entity_id == review_key,
            ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        )
        if not row:
            return None
        details = parse_audit_details(row)
        return {
            "audit_id": row.id,
            "reviewed_at": _iso(row.created_at),
            "reviewed_by": row.user_email,
            "note": details.get("note"),
        }

    def checklist(self, period_id: int) -> dict[str, Any]:
        period = self._period(period_id)
        checks: list[dict[str, Any]] = []

        if period.status in {"CALCULATED", "CLOSED"}:
            checks.append(self._check(
                "PERIOD_STATUS", "Etapa da competência", "PASS",
                "Competência calculada" if period.status == "CALCULATED" else "Competência já fechada",
                period_status=period.status,
            ))
        else:
            checks.append(self._check(
                "PERIOD_STATUS", "Etapa da competência", "BLOCKER",
                "Oficialize uma versão do rateio antes de fechar a competência.",
                period_status=period.status,
            ))

        offering_count = int(self.db.scalar(
            select(func.count()).select_from(DPECostPeriodOffering).where(
                DPECostPeriodOffering.period_id == period.id,
                DPECostPeriodOffering.included.is_(True),
            )
        ) or 0)
        checks.append(self._check(
            "OFFERINGS", "Cursos/contextos econômicos", "PASS" if offering_count else "BLOCKER",
            f"{offering_count} curso(s)/contexto(s) incluído(s) na competência." if offering_count else "Nenhum curso/contexto econômico está incluído na competência.",
            offering_count=offering_count,
        ))

        expenses = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == period.id,
                DPECostExpense.status == "ACTIVE",
            )
        ).all()
        expense_total = sum((Decimal(row.amount or 0) for row in expenses), Decimal("0.00")).quantize(CENT)
        allocatable_expenses = [row for row in expenses if str(row.expense_scope or "SHARED").upper() != "INSTITUTIONAL"]
        institutional_expenses = [row for row in expenses if str(row.expense_scope or "SHARED").upper() == "INSTITUTIONAL"]
        allocatable_total = sum((Decimal(row.amount or 0) for row in allocatable_expenses), Decimal("0.00")).quantize(CENT)
        institutional_total = sum((Decimal(row.amount or 0) for row in institutional_expenses), Decimal("0.00")).quantize(CENT)
        checks.append(self._check(
            "EXPENSES", "Despesas oficiais", "PASS" if expenses else "BLOCKER",
            f"{len(expenses)} despesa(s) ativa(s), total de R$ {expense_total:,.2f}." if expenses else "Nenhuma despesa oficial ativa foi registrada neste mês.",
            expense_count=len(expenses), expense_total=float(expense_total),
            allocatable_count=len(allocatable_expenses), allocatable_total=float(allocatable_total),
            institutional_count=len(institutional_expenses), institutional_total=float(institutional_total),
        ))

        allocation_repo = DPECostAllocationRepository(self.db, self.scope)
        readiness = allocation_repo._expense_readiness(period.id) if allocatable_expenses else []
        pending = [row for row in readiness if row.get("readiness") != "READY"]
        if not allocatable_expenses:
            checks.append(self._check(
                "EXPENSE_CONFIGURATION", "Configuração de distribuição", "PASS",
                "Não há despesas diretas ou compartilhadas neste mês; despesas institucionais não precisam ser distribuídas aos cursos.",
                pending_count=0, pending_expense_ids=[], allocatable_count=0,
            ))
        else:
            checks.append(self._check(
                "EXPENSE_CONFIGURATION", "Configuração de distribuição", "PASS" if not pending else "BLOCKER",
                "Todas as despesas diretas e compartilhadas estão prontas para distribuição." if not pending else f"{len(pending)} despesa(s) distribuível(is) ainda exigem configuração ou conciliação.",
                pending_count=len(pending), pending_expense_ids=[row["id"] for row in pending[:50]], allocatable_count=len(allocatable_expenses),
            ))

        economics = self.db.scalars(
            select(DPECostOfferingEconomics).where(
                DPECostOfferingEconomics.directorate_id == self.directorate_id,
                DPECostOfferingEconomics.period_id == period.id,
            )
        ).all()
        economics_by_offering = {row.period_offering_id: row for row in economics}
        included_ids = self.db.scalars(
            select(DPECostPeriodOffering.id).where(
                DPECostPeriodOffering.period_id == period.id,
                DPECostPeriodOffering.included.is_(True),
            )
        ).all()
        revenues = revenue_facts(self.db, self.directorate_id, period.id)
        missing_students = [oid for oid in included_ids if economics_by_offering.get(oid) is None or economics_by_offering[oid].active_students is None]
        missing_revenue = [oid for oid in included_ids if not revenues.is_confirmed(oid)]
        checks.append(self._check(
            "ACTIVE_STUDENTS", "Alunos ativos por curso/contexto", "PASS",
            "Dado auxiliar disponível para todos os cursos/contextos." if not missing_students else f"{len(missing_students)} curso(s)/contexto(s) sem alunos ativos. Isso só bloqueará regras de rateio que usem quantidade de alunos.",
            missing_count=len(missing_students), offering_ids=missing_students[:50], optional=True,
        ))
        checks.append(self._check(
            "COURSE_REVENUE", "Receita confirmada por curso/contexto", "PASS" if not missing_revenue and offering_count else "BLOCKER",
            "Todos os cursos/contextos possuem uma receita confirmada no ledger, inclusive quando o valor informado é zero." if not missing_revenue and offering_count else f"{len(missing_revenue)} curso(s)/contexto(s) ainda não possuem receita confirmada.",
            missing_count=len(missing_revenue), offering_ids=missing_revenue[:50],
            course_revenue=float(revenues.attributed_total),
            institutional_revenue=float(revenues.institutional_total),
            total_revenue=float(revenues.total_revenue),
        ))

        payroll_count = int(self.db.scalar(
            select(func.count()).select_from(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == period.id,
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_kind == "PAYROLL",
            )
        ) or 0)
        payroll_pending = int(self.db.scalar(
            select(func.count()).select_from(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == period.id,
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_kind == "PAYROLL",
                (
                    DPECostExpense.period_teacher_id.is_(None)
                    | (DPECostExpense.teacher_match_status != "CONFIRMED")
                ),
            )
        ) or 0)
        checks.append(self._check(
            "TEACHING_RECONCILIATION", "Docentes reconciliados", "PASS" if payroll_pending == 0 else "BLOCKER",
            (
                "Não há despesas de folha nesta competência."
                if payroll_count == 0
                else (
                    f"{payroll_count} lançamento(s) de folha estão conciliados com docentes."
                    if payroll_pending == 0
                    else f"{payroll_pending} de {payroll_count} lançamento(s) de folha ainda precisam ser conciliados com docentes."
                )
            ),
            payroll_count=payroll_count,
            pending_count=payroll_pending,
        ))

        official = self._official_run(period.id)
        official_current = False
        blocker_issues = 0
        if official:
            official_current = bool(
                official.input_fingerprint
                and official.input_fingerprint == allocation_repo._input_fingerprint(period.id)
            )
            blocker_issues = int(self.db.scalar(
                select(func.count()).select_from(DPECostAllocationIssue).where(
                    DPECostAllocationIssue.run_id == official.id,
                    DPECostAllocationIssue.severity == "BLOCKER",
                )
            ) or 0)
        if not allocatable_expenses:
            checks.append(self._check(
                "OFFICIAL_RUN", "Cálculo de distribuição", "PASS",
                "Não há despesas diretas ou compartilhadas; um cálculo de distribuição não é necessário para fechar este mês.",
                optional=True,
            ))
        elif not official:
            checks.append(self._check(
                "OFFICIAL_RUN", "Cálculo oficial", "BLOCKER",
                "Nenhuma versão oficial da distribuição existe para as despesas diretas/compartilhadas desta competência.",
            ))
        elif not official_current:
            checks.append(self._check(
                "OFFICIAL_RUN", "Cálculo oficial", "BLOCKER",
                f"A versão oficial v{official.run_number} está desatualizada em relação às despesas distribuíveis atuais.",
                run_id=official.id, run_number=official.run_number,
            ))
        else:
            checks.append(self._check(
                "OFFICIAL_RUN", "Cálculo oficial", "PASS",
                f"Versão oficial v{official.run_number} confere com as despesas distribuíveis atuais.",
                run_id=official.id, run_number=official.run_number,
            ))

        if not allocatable_expenses:
            checks.append(self._check(
                "ALLOCATION_RECONCILIATION", "Conciliação da distribuição", "PASS",
                "Não há valor a distribuir entre cursos. As despesas institucionais permanecem somente no resultado institucional.",
                run_expense_total=0.0, allocated_total=0.0, unallocated_total=0.0,
                current_expense_total=0.0, institutional_total=float(institutional_total), blocker_issue_count=0,
            ))
            allocation_reconciled = True
        elif official:
            allocated = Decimal(official.allocated_total or 0).quantize(CENT)
            run_expense = Decimal(official.expense_total or 0).quantize(CENT)
            unallocated = Decimal(official.unallocated_total or 0).quantize(CENT)
            allocation_reconciled = unallocated == Decimal("0.00") and allocated == run_expense and run_expense == allocatable_total and blocker_issues == 0
            checks.append(self._check(
                "ALLOCATION_RECONCILIATION", "Conciliação da distribuição", "PASS" if allocation_reconciled else "BLOCKER",
                "100% das despesas diretas e compartilhadas estão distribuídas sem bloqueios." if allocation_reconciled else "O total distribuído não fecha com as despesas diretas/compartilhadas atuais ou ainda existem bloqueios.",
                run_expense_total=float(run_expense), allocated_total=float(allocated), unallocated_total=float(unallocated),
                current_expense_total=float(allocatable_total), institutional_total=float(institutional_total), blocker_issue_count=blocker_issues,
            ))
        else:
            allocation_reconciled = False
            checks.append(self._check(
                "ALLOCATION_RECONCILIATION", "Conciliação da distribuição", "BLOCKER",
                "A conciliação das despesas diretas/compartilhadas depende de uma versão oficial da distribuição.",
            ))

        result_ready = bool(
            not missing_revenue
            and offering_count
            and allocation_reconciled
            and (not allocatable_expenses or (official and official_current))
        )
        checks.append(self._check(
            "ECONOMIC_RESULT", "Resultado econômico calculado", "PASS" if result_ready else "BLOCKER",
            "Receitas e custos oficiais permitem calcular o resultado econômico do mês." if result_ready else "O resultado econômico ainda não pode ser considerado final porque receitas ou custos oficiais estão incompletos/desatualizados.",
            official_run_id=official.id if official else None,
            official_current=official_current,
            missing_revenue_count=len(missing_revenue),
        ))

        pending_batches = int(self.db.scalar(
            select(func.count()).select_from(DPECostExpenseImportBatch).where(
                DPECostExpenseImportBatch.directorate_id == self.directorate_id,
                DPECostExpenseImportBatch.period_id == period.id,
                DPECostExpenseImportBatch.status.in_(("STAGING", "READY")),
            )
        ) or 0)
        checks.append(self._check(
            "PENDING_STAGING", "Lotes de entrada em preparação", "WARNING" if pending_batches else "PASS",
            f"Existem {pending_batches} lote(s) ainda em staging/prontos e não incorporados às despesas oficiais." if pending_batches else "Nenhum lote pendente de incorporação nesta competência.",
            pending_batch_count=pending_batches,
        ))


        source_warnings = [row for row in checks if row["status"] == "WARNING"]
        review_items: list[dict[str, Any]] = []
        for warning in source_warnings:
            review_key = self._warning_review_key(period.id, warning)
            review = self._warning_review(review_key)
            review_items.append({
                "review_key": review_key,
                "code": warning["code"],
                "label": warning["label"],
                "detail": warning["detail"],
                "context": warning.get("context") or {},
                "reviewed": bool(review),
                "review": review,
            })
        pending_reviews = [row for row in review_items if not row["reviewed"]]
        checks.append(self._check(
            "ANOMALY_REVIEW", "Alertas e anomalias revisados", "PASS" if not pending_reviews else "BLOCKER",
            (
                "Não existem alertas de governança pendentes de revisão."
                if not pending_reviews
                else f"{len(pending_reviews)} alerta(s) atual(is) ainda não possuem registro de revisão."
            ),
            pending_count=len(pending_reviews),
            review_keys=[row["review_key"] for row in pending_reviews],
        ))

        blockers = sum(1 for row in checks if row["status"] == "BLOCKER")
        warnings = sum(1 for row in checks if row["status"] == "WARNING")
        passed = sum(1 for row in checks if row["status"] == "PASS")
        return {
            "period_id": period.id,
            "period": period.period,
            "period_status": period.status,
            "checks": checks,
            "summary": {
                "pass_count": passed,
                "warning_count": warnings,
                "blocker_count": blockers,
                "review_pending_count": len(pending_reviews),
                "check_count": len(checks),
                "checklist_ready": blockers == 0,
                "can_close": period.status == "CALCULATED" and blockers == 0,
                "can_reopen": period.status == "CLOSED",
                "closed_at": _iso(period.closed_at),
                "closed_by": period.closed_by,
            },
            "review_items": review_items,
            "official_run": {
                "id": official.id,
                "run_number": official.run_number,
                "status": official.status,
                "current": official_current,
                "expense_total": float(Decimal(official.expense_total or 0).quantize(CENT)),
                "allocated_total": float(Decimal(official.allocated_total or 0).quantize(CENT)),
                "unallocated_total": float(Decimal(official.unallocated_total or 0).quantize(CENT)),
                "official_at": _iso(official.official_at),
                "official_by": official.official_by,
            } if official else None,
        }

    def _audit_log(
        self,
        action: str,
        period: DPECostPeriod,
        details: dict[str, Any],
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        add_dpe_audit(
            self.db,
            self.scope,
            action=action,
            entity="dpe_cost_period",
            entity_id=period.id,
            period_id=period.id,
            before=before,
            after=after,
            metadata=details,
        )

    def close_period(self, period_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        period = self._period(period_id)
        if period.status == "CLOSED":
            raise DPECostClosureValidationError("Esta competência já está fechada.")
        if period.status != "CALCULATED":
            raise DPECostClosureValidationError(
                "A competência precisa ter uma versão oficial calculada antes do fechamento."
            )
        checklist = self.checklist(period.id)
        if not checklist["summary"]["can_close"]:
            messages = [row["detail"] for row in checklist["checks"] if row["status"] == "BLOCKER"]
            raise DPECostClosureValidationError(
                "O fechamento foi bloqueado porque ainda existem pendências críticas.",
                {"checklist": " | ".join(messages[:8])},
            )
        official = self._official_run(period.id)
        if not official:
            raise DPECostClosureValidationError("Nenhuma versão oficial foi encontrada para o fechamento.")
        note = _text((payload or {}).get("note"), max_length=2000) or None
        now = datetime.now(timezone.utc)
        event = DPECostPeriodEvent(
            directorate_id=self.directorate_id,
            period_id=period.id,
            event_type="CLOSED",
            from_status=period.status,
            to_status="CLOSED",
            allocation_run_id=official.id,
            reason=note,
            checklist_json=checklist,
            metadata_json={
                "period": period.period,
                "official_run_number": official.run_number,
                "official_run_fingerprint": official.input_fingerprint,
                "expense_total": float(Decimal(official.expense_total or 0).quantize(CENT)),
                "allocated_total": float(Decimal(official.allocated_total or 0).quantize(CENT)),
            },
            created_by=self.actor,
        )
        self.db.add(event)
        period.status = "CLOSED"
        period.closed_at = now
        period.closed_by = self.actor
        self._audit_log("close", period, {
            "period": period.period,
            "from_status": "CALCULATED",
            "to_status": "CLOSED",
            "allocation_run_id": official.id,
            "allocation_run_number": official.run_number,
            "note": note,
            "checklist_summary": checklist["summary"],
        }, before={"status": "CALCULATED"}, after={"status": "CLOSED", "closed_at": _iso(now), "closed_by": self.actor})
        self._commit()
        return self.central_payload(period_id=period.id)

    def reopen_period(self, period_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        period = self._period(period_id)
        if period.status != "CLOSED":
            raise DPECostClosureValidationError("Somente uma competência fechada pode ser reaberta.")
        reason = _text((payload or {}).get("reason"), max_length=2000)
        if len(reason) < 10:
            raise DPECostClosureValidationError(
                "Informe um motivo objetivo para reabrir a competência.",
                {"reason": "Use ao menos 10 caracteres; o motivo ficará registrado na auditoria."},
            )
        checklist = self.checklist(period.id)
        official = self._official_run(period.id)
        event = DPECostPeriodEvent(
            directorate_id=self.directorate_id,
            period_id=period.id,
            event_type="REOPENED",
            from_status="CLOSED",
            to_status="REVIEW",
            allocation_run_id=official.id if official else None,
            reason=reason,
            checklist_json=checklist,
            metadata_json={
                "period": period.period,
                "previous_closed_at": _iso(period.closed_at),
                "previous_closed_by": period.closed_by,
                "official_run_number": official.run_number if official else None,
            },
            created_by=self.actor,
        )
        self.db.add(event)
        prior_closed_at = period.closed_at
        prior_closed_by = period.closed_by
        period.status = "REVIEW"
        period.closed_at = None
        period.closed_by = None
        self._audit_log("reopen", period, {
            "period": period.period,
            "from_status": "CLOSED",
            "to_status": "REVIEW",
            "reason": reason,
            "previous_closed_at": _iso(prior_closed_at),
            "previous_closed_by": prior_closed_by,
            "allocation_run_id": official.id if official else None,
        }, before={"status": "CLOSED", "closed_at": _iso(prior_closed_at), "closed_by": prior_closed_by}, after={"status": "REVIEW"})
        self._commit()
        return self.central_payload(period_id=period.id)

    def return_to_review(self, period_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        period = self._period(period_id)
        if period.status != "CALCULATED":
            raise DPECostClosureValidationError("Somente uma competência calculada pode voltar para conferência.")
        reason = _text((payload or {}).get("reason"), max_length=2000)
        if len(reason) < 10:
            raise DPECostClosureValidationError(
                "Informe por que o cálculo oficial precisa ser liberado para correção.",
                {"reason": "Use ao menos 10 caracteres; o motivo ficará registrado na auditoria."},
            )
        official = self._official_run(period.id)
        before = {
            "status": period.status,
            "allocation_run_id": official.id if official else None,
            "allocation_run_number": official.run_number if official else None,
        }
        now = datetime.now(timezone.utc)
        if official:
            official.status = "SUPERSEDED"
            official.superseded_at = now
            official.superseded_by = self.actor
        period.status = "REVIEW"
        self._audit_log(
            "return_review",
            period,
            {"reason": reason, "allocation_run_id": official.id if official else None},
            before=before,
            after={"status": "REVIEW", "official_run_superseded": bool(official)},
        )
        self._commit()
        return self.central_payload(period_id=period.id)

    def review_warning(self, period_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        period = self._period(period_id)
        review_key = _text((payload or {}).get("review_key"), max_length=120)
        note = _text((payload or {}).get("note"), max_length=2000)
        if len(note) < 5:
            raise DPECostClosureValidationError(
                "Registre uma observação curta sobre a revisão do alerta.",
                {"note": "Use ao menos 5 caracteres."},
            )
        checklist = self.checklist(period.id)
        item = next((row for row in checklist.get("review_items", []) if row.get("review_key") == review_key), None)
        if not item:
            raise DPECostClosureValidationError("Este alerta não está mais ativo ou já mudou. Atualize o fechamento e revise novamente.")
        if item.get("reviewed"):
            return self.central_payload(period_id=period.id)
        add_dpe_audit(
            self.db,
            self.scope,
            action="review_warning",
            entity="dpe_governance_warning",
            entity_id=review_key,
            period_id=period.id,
            after={"reviewed": True},
            metadata={
                "code": item.get("code"),
                "label": item.get("label"),
                "detail": item.get("detail"),
                "context": item.get("context") or {},
                "note": note,
            },
        )
        self._commit()
        return self.central_payload(period_id=period.id)

    def audit_trail(self, period_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
        self._period(period_id)
        return list_dpe_period_audit(self.db, self.scope, period_id, limit=limit)

    def central_payload(self, *, period_id: int | None = None) -> dict[str, Any]:
        periods = self.db.scalars(
            select(DPECostPeriod).where(
                DPECostPeriod.directorate_id == self.directorate_id
            ).order_by(DPECostPeriod.period.desc())
        ).all()
        if not periods:
            return {
                "periods": [], "selected_period": None, "checklist": None,
                "events": [], "editable": False,
            }
        selected = self._period(int(period_id)) if period_id else periods[0]
        events = self.list_events(selected.id)
        checklist = self.checklist(selected.id)
        event_counts = {
            "closed": sum(1 for event in events if event["event_type"] == "CLOSED"),
            "reopened": sum(1 for event in events if event["event_type"] == "REOPENED"),
        }
        return {
            "periods": [
                {
                    "id": row.id,
                    "period": row.period,
                    "status": row.status,
                    "closed_at": _iso(row.closed_at),
                    "closed_by": row.closed_by,
                }
                for row in periods
            ],
            "selected_period": {
                "id": selected.id,
                "period": selected.period,
                "status": selected.status,
                "notes": selected.notes,
                "closed_at": _iso(selected.closed_at),
                "closed_by": selected.closed_by,
            },
            "checklist": checklist,
            "official_run": checklist.get("official_run"),
            "events": events,
            "audit_trail": self.audit_trail(selected.id),
            "event_counts": event_counts,
            "can_write": bool(self.scope.can_write),
        }
