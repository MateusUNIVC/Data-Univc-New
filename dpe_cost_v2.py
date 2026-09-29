from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dpe_cost_closure import DPECostClosureRepository
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_cost_expenses import DPECostExpenseRepository
from models import DPECostExpense, DPECostTeachingActivity
from security import DirectorateScope


class DPEV2OverviewRepository:
    """Read-only composition layer for the DPE V2 executive experience.

    This layer deliberately does not create a second source of truth. It composes
    the canonical Cost Engine repositories introduced in v0.9.6.13-v0.9.6.19 so
    the executive screen and workflow always read the same monthly snapshots,
    economics, allocations and close checklist used by the operational screens.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("A visão DPE V2 pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @staticmethod
    def _workflow_step(
        code: str,
        label: str,
        section: str,
        status: str,
        detail: str,
        *,
        complete: bool = False,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "label": label,
            "section": section,
            "status": status,
            "detail": detail,
            "complete": bool(complete),
        }

    @staticmethod
    def _period_id(periods: list[dict[str, Any]], period_id: int | None) -> int | None:
        if period_id:
            return int(period_id)
        if periods:
            return int(periods[0]["id"])
        return None

    @staticmethod
    def _offering_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in rows:
            product = row.get("product") or {}
            offering = row.get("offering") or {}
            revenue = row.get("revenue")
            active_students = row.get("active_students")
            revenue_per_active_student = None
            if revenue is not None and active_students:
                revenue_per_active_student = float(revenue) / int(active_students)
            output.append({
                "period_offering_id": row.get("period_offering_id"),
                "label": row.get("label") or "Curso",
                "product": product.get("name") or "Sem produto",
                "modality": offering.get("modality") or "—",
                "shift": offering.get("shift") or "—",
                "location": offering.get("campus") or offering.get("unit_name") or offering.get("pole_name") or "—",
                "active_students": active_students,
                "revenue": revenue,
                "revenue_per_active_student": revenue_per_active_student,
                "allocated_cost": row.get("allocated_cost"),
                "cost_per_active_student": row.get("cost_per_active_student"),
                "economic_result": row.get("economic_result"),
                "margin_percent": row.get("margin_percent"),
                "students_ready": bool(row.get("students_ready")),
                "revenue_ready": bool(row.get("revenue_ready")),
                "cost_available": bool(row.get("cost_available")),
            })
        return sorted(output, key=lambda item: (str(item["product"]), str(item["label"])))

    def overview(self, *, period_id: int | None = None) -> dict[str, Any]:
        closure_repo = DPECostClosureRepository(self.db, self.scope)
        closure = closure_repo.central_payload(period_id=period_id)

        if not closure.get("selected_period"):
            return {
                "periods": [],
                "selected_period": None,
                "summary": {},
                "workflow": [],
                "next_action": {
                    "section": "competencias",
                    "label": "Abrir o primeiro mês",
                    "detail": "Cadastre o primeiro mês para começar a acompanhar receitas, despesas e custos por curso.",
                },
                "issues": [],
                "offerings": [],
                "aggregates": {"product": [], "modality": [], "shift": []},
                "can_write": bool(self.scope.can_write),
            }

        selected_id = int(closure["selected_period"]["id"])
        economics = DPECostEconomicsRepository(self.db, self.scope).central_payload(period_id=selected_id)
        expense_summary = DPECostExpenseRepository(self.db, self.scope).expense_summary(period_id=selected_id)

        activity_count, workload_total = self.db.execute(
            select(
                func.count(DPECostTeachingActivity.id),
                func.coalesce(func.sum(DPECostTeachingActivity.workload_hours), 0),
            ).where(
                DPECostTeachingActivity.directorate_id == self.scope.directorate_id,
                DPECostTeachingActivity.period_id == selected_id,
                DPECostTeachingActivity.status == "ACTIVE",
            )
        ).one()
        payroll_count = int(self.db.scalar(
            select(func.count(DPECostExpense.id)).where(
                DPECostExpense.directorate_id == self.scope.directorate_id,
                DPECostExpense.period_id == selected_id,
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_kind == "PAYROLL",
            )
        ) or 0)
        payroll_linked = int(self.db.scalar(
            select(func.count(DPECostExpense.id)).where(
                DPECostExpense.directorate_id == self.scope.directorate_id,
                DPECostExpense.period_id == selected_id,
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.expense_kind == "PAYROLL",
                DPECostExpense.period_teacher_id.is_not(None),
                DPECostExpense.teacher_match_status == "CONFIRMED",
            )
        ) or 0)
        teaching_summary = {
            "activity_count": int(activity_count or 0),
            "total_workload_hours": float(workload_total or 0),
            "payroll_count": payroll_count,
            "payroll_linked_count": payroll_linked,
            "payroll_pending_count": max(0, payroll_count - payroll_linked),
        }

        selected_period = closure.get("selected_period") or economics.get("selected_period")
        closure_checklist = closure.get("checklist") or {"checks": [], "summary": {}}
        closure_summary = closure_checklist.get("summary") or {}
        economics_summary = economics.get("summary") or {}
        official_run = closure.get("official_run")

        offering_count = int(economics_summary.get("offering_count") or 0)
        expense_count = int(expense_summary.get("expense_count") or 0)
        payroll_count = int(teaching_summary.get("payroll_count") or 0)
        payroll_linked = int(teaching_summary.get("payroll_linked_count") or 0)
        payroll_pending = int(teaching_summary.get("payroll_pending_count") or 0)

        offerings_complete = offering_count > 0
        expenses_complete = expense_count > 0
        teaching_complete = payroll_count == 0 or payroll_pending == 0
        economics_complete = bool(
            offering_count
            and economics_summary.get("complete_revenue")
        )
        allocation_complete = bool(
            official_run
            and official_run.get("current")
            and float(official_run.get("unallocated_total") or 0) == 0
        )
        period_closed = bool(selected_period and selected_period.get("status") == "CLOSED")
        closure_ready = bool(closure_summary.get("can_close"))
        review_pending = int(closure_summary.get("review_pending_count") or 0)
        governance_complete = review_pending == 0

        allocation_pending = next((
            int(check.get("context", {}).get("pending_count", 0) or 0)
            for check in (closure_checklist.get("checks") or [])
            if check.get("code") == "EXPENSE_CONFIGURATION"
        ), 0)

        # Executive totals intentionally use the official monthly ledger rather than
        # the amount already allocated to courses. Allocation is a distribution
        # process; it must not make the month look artificially more profitable while
        # some expenses are still pending distribution.
        total_revenue = economics_summary.get("total_revenue")
        expense_total = expense_summary.get("total_amount")
        allocatable_total = expense_summary.get("allocatable_amount")
        monthly_result = None
        monthly_margin_percent = None
        if expenses_complete and economics_summary.get("complete_revenue") and total_revenue is not None and expense_total is not None:
            monthly_result = float(total_revenue or 0) - float(expense_total or 0)
            if float(total_revenue or 0) != 0:
                monthly_margin_percent = monthly_result / float(total_revenue) * 100

        allocated_cost = economics_summary.get("allocated_cost")
        allocation_coverage_percent = None
        pending_distribution_total = None
        if expenses_complete and allocatable_total is not None:
            total = float(allocatable_total or 0)
            allocated = float(allocated_cost or 0)
            pending_distribution_total = max(0.0, total - allocated)
            allocation_coverage_percent = 100.0 if total == 0 else max(0.0, min(100.0, allocated / total * 100))
        if expense_count == 0:
            allocation_detail = "A etapa será liberada após o registro das despesas oficiais."
        elif allocation_complete:
            allocation_detail = f"Versão oficial v{official_run.get('run_number')} conciliada e atual."
        elif allocation_pending > 0:
            allocation_detail = f"{allocation_pending} despesa(s) ainda pendente(s) no motor de rateio."
        elif not official_run:
            allocation_detail = "Gere uma versão do rateio e oficialize o cálculo reconciliado."
        elif not official_run.get("current"):
            allocation_detail = "Os dados mudaram após o cálculo oficial; gere e oficialize uma nova versão."
        else:
            allocation_detail = "Revise e oficialize uma versão totalmente conciliada do rateio."

        workflow = [
            self._workflow_step(
                "COMPETENCE",
                "Cursos do mês",
                "competencias",
                "DONE" if offerings_complete else "PENDING",
                f"{offering_count} curso(s)/contexto(s) incluído(s) neste mês." if offerings_complete else "Inclua ao menos um curso/contexto neste mês.",
                complete=offerings_complete,
            ),
            self._workflow_step(
                "EXPENSES",
                "Despesas oficiais",
                "central-despesas",
                "DONE" if expenses_complete else "PENDING",
                f"{expense_count} despesa(s) oficial(is) registradas." if expenses_complete else "Registre as despesas oficiais da competência.",
                complete=expenses_complete,
            ),
            self._workflow_step(
                "TEACHING",
                "Docentes e folha",
                "docencia",
                "DONE" if teaching_complete else "ATTENTION",
                (
                    "Não há despesas de folha nesta competência."
                    if payroll_count == 0
                    else f"{payroll_linked}/{payroll_count} despesa(s) de folha conciliadas com professores."
                ),
                complete=teaching_complete,
            ),
            self._workflow_step(
                "ECONOMICS",
                "Receitas",
                "receita-operacional",
                "DONE" if economics_complete else "PENDING",
                "Receita preenchida em todos os cursos/contextos." if economics_complete else "Complete a receita dos cursos/contextos.",
                complete=economics_complete,
            ),
            self._workflow_step(
                "ALLOCATION",
                "Distribuição de custos",
                "rateio",
                "DONE" if allocation_complete else "PENDING",
                allocation_detail,
                complete=allocation_complete,
            ),
            self._workflow_step(
                "GOVERNANCE",
                "Alertas revisados",
                "fechamento",
                "DONE" if governance_complete else "ATTENTION",
                "Alertas atuais possuem registro de revisão." if governance_complete else f"{review_pending} alerta(s) atual(is) ainda precisam de revisão registrada.",
                complete=governance_complete,
            ),
            self._workflow_step(
                "CLOSE",
                "Fechamento",
                "fechamento",
                "DONE" if period_closed else ("READY" if closure_ready else "PENDING"),
                "Mês encerrado e auditado." if period_closed else ("Tudo certo: o mês está pronto para fechamento." if closure_ready else "Resolva as pendências antes do fechamento."),
                complete=period_closed,
            ),
        ]

        completed_count = sum(1 for step in workflow if step["complete"])
        progress_percent = round(completed_count / len(workflow) * 100) if workflow else 0

        next_step = next((step for step in workflow if not step["complete"]), None)
        if period_closed:
            next_action = {
                "section": "fechamento",
                "label": "Consultar fechamento e auditoria",
                "detail": "O mês está fechado. Consulte o histórico ou reabra com justificativa se precisar corrigir algum dado.",
            }
        elif next_step:
            next_action = {
                "section": next_step["section"],
                "label": next_step["label"],
                "detail": next_step["detail"],
            }
        else:
            next_action = {
                "section": "fechamento",
                "label": "Revisar fechamento mensal",
                "detail": "Os dados essenciais estão completos; faça a revisão final antes de fechar o mês.",
            }

        issue_routes = {
            "PERIOD_STATUS": ("fechamento", "Revisar fechamento"),
            "OFFERINGS": ("catalogo", "Revisar cursos"),
            "EXPENSES": ("central-despesas", "Registrar despesas"),
            "EXPENSE_CONFIGURATION": ("rateio", "Revisar distribuição"),
            "ACTIVE_STUDENTS": ("economia", "Completar alunos"),
            "COURSE_REVENUE": ("receita-operacional", "Completar receitas"),
            "OFFICIAL_RUN": ("rateio", "Atualizar distribuição"),
            "ALLOCATION_RECONCILIATION": ("rateio", "Conferir distribuição"),
            "PENDING_STAGING": ("central-despesas", "Conferir importações"),
            "TEACHING_RECONCILIATION": ("docencia", "Revisar docentes"),
            "ECONOMIC_RESULT": ("fechamento", "Revisar resultado"),
            "ANOMALY_REVIEW": ("fechamento", "Revisar alertas"),
        }
        issue_titles = {
            "PERIOD_STATUS": "O mês ainda não está pronto para fechamento",
            "OFFERINGS": "Defina os cursos que fazem parte deste mês",
            "EXPENSES": "Registre as despesas do mês",
            "EXPENSE_CONFIGURATION": "Há despesas sem critério de distribuição",
            "ACTIVE_STUDENTS": "Faltam quantidades de alunos em alguns cursos",
            "COURSE_REVENUE": "Falta confirmar a receita de alguns cursos",
            "OFFICIAL_RUN": "A distribuição de custos precisa ser atualizada",
            "ALLOCATION_RECONCILIATION": "A distribuição ainda não fecha com as despesas",
            "PENDING_STAGING": "Há importações aguardando conferência",
            "TEACHING_RECONCILIATION": "Há lançamentos de folha sem docente conciliado",
            "ECONOMIC_RESULT": "O resultado econômico ainda não está finalizado",
            "ANOMALY_REVIEW": "Há alertas atuais que ainda não foram revisados",
        }
        issues = []
        prerequisites_ready = bool(
            offerings_complete and expenses_complete and teaching_complete
            and economics_complete and allocation_pending == 0
        )
        official_current = bool(official_run and official_run.get("current"))
        for check in (closure_checklist.get("checks") or []):
            if check.get("status") not in {"BLOCKER", "WARNING"}:
                continue
            code = check.get("code")
            # PERIOD_STATUS and downstream allocation checks are consequences, not
            # independent user problems. Hiding these cascades keeps the executive
            # panel focused on the smallest set of actions that actually unlocks the
            # month.
            if code == "PERIOD_STATUS":
                continue
            if code == "OFFICIAL_RUN" and not prerequisites_ready:
                continue
            if code == "ALLOCATION_RECONCILIATION" and (not prerequisites_ready or not official_current):
                continue
            if code == "ECONOMIC_RESULT" and (not prerequisites_ready or not official_current):
                continue
            section, action_label = issue_routes.get(code, ("fechamento", "Revisar"))
            issues.append({
                "code": code,
                "label": check.get("label"),
                "title": issue_titles.get(code, check.get("label")),
                "status": check.get("status"),
                "detail": check.get("detail"),
                "section": section,
                "action_label": action_label,
            })

        # Keep blockers first, then warnings, while preserving the business order.
        issues.sort(key=lambda row: 0 if row.get("status") == "BLOCKER" else 1)

        return {
            "periods": closure.get("periods") or [],
            "selected_period": selected_period,
            "summary": {
                "offering_count": offering_count,
                "expense_count": expense_count,
                "expense_total": expense_total,
                "active_students": economics_summary.get("active_students"),
                "course_revenue": economics_summary.get("course_revenue"),
                "institutional_revenue": economics_summary.get("institutional_revenue"),
                "total_revenue": total_revenue,
                "allocated_cost": allocated_cost,
                "course_result": economics_summary.get("economic_result"),
                "course_margin_percent": economics_summary.get("margin_percent"),
                "monthly_result": monthly_result,
                "monthly_margin_percent": monthly_margin_percent,
                "allocation_coverage_percent": allocation_coverage_percent,
                "pending_distribution_total": pending_distribution_total,
                "payroll_count": payroll_count,
                "payroll_linked_count": payroll_linked,
                "payroll_pending_count": payroll_pending,
                "activity_count": teaching_summary.get("activity_count"),
                "total_workload_hours": teaching_summary.get("total_workload_hours"),
                "blocker_count": closure_summary.get("blocker_count") or 0,
                "warning_count": closure_summary.get("warning_count") or 0,
                "progress_percent": progress_percent,
                "completed_steps": completed_count,
                "total_steps": len(workflow),
            },
            "workflow": workflow,
            "next_action": next_action,
            "issues": issues,
            "offerings": self._offering_rows(economics.get("rows") or []),
            "aggregates": economics.get("aggregates") or {"product": [], "modality": [], "shift": []},
            "official_run": official_run,
            "checklist": closure_checklist,
            "event_counts": closure.get("event_counts") or {},
            "can_write": bool(self.scope.can_write),
        }
