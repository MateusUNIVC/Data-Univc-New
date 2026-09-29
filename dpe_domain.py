from __future__ import annotations

from copy import deepcopy
from typing import Any

# Canonical DPE vocabulary introduced in v0.13.0-dev.4.
# This registry describes the business domain independently from the historical
# DPE-01/02/03 measurement contract, which remains temporarily available only
# for legacy measurement/Excel compatibility.
DPE_DOMAIN_VERSION = "2026-09-v2"

DPE_ENTITIES: tuple[dict[str, Any], ...] = (
    {
        "key": "period",
        "name": "Competência",
        "description": "Período mensal que concentra lançamentos, cálculos, rateios e fechamento.",
        "source": "dpe_cost_periods",
    },
    {
        "key": "course",
        "name": "Curso",
        "description": "Produto acadêmico utilizado para análise econômica e atribuição de receitas/custos.",
        "source": "dpe_academic_products",
    },
    {
        "key": "course_context",
        "name": "Contexto do curso",
        "description": "Desdobramento operacional opcional do curso, como turno, unidade ou modalidade.",
        "source": "dpe_academic_offerings",
        "optional": True,
    },
    {
        "key": "revenue",
        "name": "Receita",
        "description": "Receita reconhecida na competência, institucional ou atribuída a curso/contexto.",
        "source": "dpe_revenue_entries",
    },
    {
        "key": "expense",
        "name": "Despesa",
        "description": "Despesa reconhecida na competência e classificada como direta, compartilhada ou institucional.",
        "source": "dpe_cost_expenses",
    },
    {
        "key": "teacher",
        "name": "Docente",
        "description": "Docente considerado na competência para cálculo e rastreabilidade de custo acadêmico.",
        "source": "dpe_teacher_profiles / dpe_cost_period_teachers",
    },
    {
        "key": "teaching_activity",
        "name": "Atividade docente",
        "description": "Atividade/carga docente ligada à competência e, quando aplicável, a curso/contexto.",
        "source": "dpe_cost_teaching_activities",
    },
    {
        "key": "allocation_rule",
        "name": "Regra de distribuição",
        "description": "Critério administrativo utilizado para distribuir despesas compartilhadas.",
        "source": "dpe_allocation_rules",
    },
    {
        "key": "allocation_run",
        "name": "Execução de rateio",
        "description": "Execução versionada e auditável de distribuição de despesas na competência.",
        "source": "dpe_cost_allocation_runs",
    },
    {
        "key": "result",
        "name": "Resultado",
        "description": "Resultado econômico calculado para curso/contexto e para a instituição.",
        "source": "dpe_revenue_entries + dpe_cost_expenses + dpe_cost_allocation_results",
    },
    {
        "key": "target",
        "name": "Meta",
        "description": "Objetivo de gestão associado a uma métrica canônica da DPE.",
        "source": "management_indicator_targets",
    },
    {
        "key": "action_plan",
        "name": "Plano de ação",
        "description": "Ação de gestão associada a uma métrica canônica e a uma competência.",
        "source": "management_indicator_actions",
    },
)

DPE_PERIOD_STATES: tuple[dict[str, str], ...] = (
    {"code": "DRAFT", "label": "Rascunho", "meaning": "Preparação inicial da competência."},
    {"code": "REVIEW", "label": "Conferência", "meaning": "Dados editáveis e em revisão administrativa."},
    {"code": "CALCULATED", "label": "Calculada", "meaning": "Resultado calculado e protegido contra alterações operacionais comuns."},
    {"code": "CLOSED", "label": "Fechada", "meaning": "Competência encerrada e preservada como histórico auditável."},
)

DPE_MANAGEMENT_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "code": "DPE-RESULT",
        "name": "Resultados",
        "description": "Resultado e margem institucional e por curso calculados pelo Cost Engine.",
        "metrics": ("institutional_result", "institutional_margin_pct", "coverage_index", "course_result", "course_margin_pct"),
    },
    {
        "code": "DPE-REVENUE",
        "name": "Receitas",
        "description": "Receitas reconhecidas diretamente no ledger oficial.",
        "metrics": ("total_revenue", "institutional_revenue", "course_revenue", "revenue_per_student"),
    },
    {
        "code": "DPE-EXPENSE",
        "name": "Despesas",
        "description": "Despesas oficiais e custos efetivamente atribuídos aos cursos.",
        "metrics": ("total_expense", "institutional_expense", "course_total_cost"),
    },
    {
        "code": "DPE-TEACHING",
        "name": "Docência",
        "description": "Custo e carga docente reconciliados com a competência.",
        "metrics": ("teaching_cost", "avg_workload_hours_per_teacher"),
    },
    {
        "code": "DPE-ALLOCATION",
        "name": "Distribuição",
        "description": "Qualidade e reconciliação do cálculo oficial de distribuição.",
        "metrics": ("unallocated_expense", "reconciliation_pct"),
    },
)

# Exact mapping used by migration 044. Mappings intentionally cover only
# semantics that are equivalent enough to migrate safely. Historical raw
# measurements remain under DPE-01/02/03 until their dedicated retirement.
LEGACY_MANAGEMENT_METRIC_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("DPE-01", "net_margin_pct"): ("DPE-RESULT", "course_margin_pct"),
    ("DPE-01", "net_margin_12m_pct"): ("DPE-RESULT", "course_margin_12m_pct"),
    ("DPE-01", "total_cost"): ("DPE-EXPENSE", "course_total_cost"),
    ("DPE-01", "avg_hours_per_teacher"): ("DPE-TEACHING", "avg_hours_per_teacher"),
    ("DPE-02", "coverage_index"): ("DPE-RESULT", "coverage_index"),
    ("DPE-02", "coverage_index_12m"): ("DPE-RESULT", "coverage_index_12m"),
    ("DPE-02", "operating_margin_pct"): ("DPE-RESULT", "institutional_margin_pct"),
    ("DPE-02", "operating_margin_12m_pct"): ("DPE-RESULT", "institutional_margin_12m_pct"),
    ("DPE-02", "total_expense"): ("DPE-EXPENSE", "total_expense"),
    ("DPE-03", "payroll_on_revenue_pct"): ("DPE-EXPENSE", "payroll_on_revenue_pct"),
    ("DPE-03", "faculty_payroll_pct"): ("DPE-TEACHING", "faculty_payroll_pct"),
    ("DPE-03", "administrative_payroll_pct"): ("DPE-EXPENSE", "administrative_payroll_pct"),
    ("DPE-03", "payroll_monthly_change_pct"): ("DPE-EXPENSE", "payroll_monthly_change_pct"),
}


def domain_payload() -> dict[str, Any]:
    return {
        "version": DPE_DOMAIN_VERSION,
        "entities": deepcopy(list(DPE_ENTITIES)),
        "period_states": deepcopy(list(DPE_PERIOD_STATES)),
        "management_groups": deepcopy(list(DPE_MANAGEMENT_GROUPS)),
        "legacy_measurement_contract": {
            "codes": ["DPE-01", "DPE-02", "DPE-03"],
            "status": "compatibility_only",
            "new_targets_allowed": False,
            "new_actions_allowed": False,
            "reason": "Mantido temporariamente apenas para medições/Excel anteriores à consolidação do domínio.",
        },
    }
