from __future__ import annotations

import math
import random
from datetime import date
from typing import Any

from management_catalog import indicator_spec
from management_service import canonical_dimensions

RNG = random.Random(700)


def month_periods(start_year: int, start_month: int, count: int) -> list[str]:
    periods: list[str] = []
    year, month = start_year, start_month
    for _ in range(count):
        periods.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return periods


def semester_periods(start_year: int, start_semester: int, count: int) -> list[str]:
    result: list[str] = []
    year, semester = start_year, start_semester
    for _ in range(count):
        result.append(f"{year:04d}-SEM{semester}")
        semester += 1
        if semester > 2:
            year += 1
            semester = 1
    return result


def measurement(
    directorate: str,
    indicator: str,
    period: str,
    values: dict[str, Any],
    dimensions: dict[str, str] | None = None,
    *,
    row_id: int,
    notes: str | None = None,
) -> dict[str, Any]:
    spec = indicator_spec(directorate, indicator)
    dims, dimension_key, dimension_label = canonical_dimensions(spec, dimensions)
    return {
        "id": row_id,
        "directorate_code": directorate,
        "indicator_code": indicator,
        "period": period,
        "dimensions": dims,
        "dimension_key": dimension_key,
        "dimension_label": dimension_label,
        "values": values,
        "notes": notes,
        "source_reference": "Base demonstrativa para homologação visual",
        "validated": True,
    }


def target(
    directorate: str,
    indicator: str,
    metric: str,
    valid_from: str,
    *,
    row_id: int,
    target_value: float | None = None,
    attention: float | None = None,
    target_min: float | None = None,
    target_max: float | None = None,
    attention_min: float | None = None,
    attention_max: float | None = None,
) -> dict[str, Any]:
    return {
        "id": row_id,
        "directorate_code": directorate,
        "indicator_code": indicator,
        "metric_key": metric,
        "dimension_key": "TOTAL",
        "dimension_label": "TOTAL",
        "valid_from": valid_from,
        "valid_to": None,
        "target": target_value,
        "attention": attention,
        "target_min": target_min,
        "target_max": target_max,
        "attention_min": attention_min,
        "attention_max": attention_max,
        "justification": "Parâmetro inicial definido no documento de indicadores; sujeito à pactuação após a linha de base.",
    }


def action(
    directorate: str,
    indicator: str,
    metric: str,
    period: str,
    problem: str,
    corrective_action: str,
    *,
    row_id: int,
) -> dict[str, Any]:
    return {
        "id": row_id,
        "directorate_code": directorate,
        "indicator_code": indicator,
        "metric_key": metric,
        "period": period,
        "dimension_key": "TOTAL",
        "dimension_label": "TOTAL",
        "problem": problem,
        "probable_cause": "Hipótese demonstrativa para validação do fluxo gerencial.",
        "corrective_action": corrective_action,
        "responsible": "Ponto focal da diretoria",
        "due_date": date(2026, 10, 15).isoformat(),
        "status": "Em andamento",
        "evidence": "A anexar após a execução.",
    }


def dadm_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    periods = month_periods(2025, 1, 20)  # até 2026-08
    channels = [
        ("Mensageria", 230, 0.94, 2.8, 15.0),
        ("E-mail institucional", 155, 0.90, 6.5, 28.0),
        ("Protocolo presencial", 82, 0.93, 1.3, 12.0),
        ("Ouvidoria", 38, 0.86, 13.0, 45.0),
        ("Sistema de chamados", 115, 0.91, 4.0, 23.0),
    ]
    rows: list[dict[str, Any]] = []
    row_id = 1
    for index, period in enumerate(periods):
        seasonal = 1.0 + 0.12 * math.sin(index / 2.1)
        improvement = min(0.055, index * 0.003)
        for channel, base_volume, base_sla, first_hours, resolution_hours in channels:
            received = max(8, round(base_volume * seasonal + RNG.uniform(-18, 18)))
            sla_rate = min(0.975, max(0.72, base_sla + improvement + RNG.uniform(-0.025, 0.018)))
            within = round(received * sla_rate)
            concluded = max(0, round(received * RNG.uniform(0.91, 1.02)))
            reopened = min(concluded, round(concluded * max(0.015, 0.07 - improvement + RNG.uniform(-0.01, 0.01))))
            open_balance = max(0, round(received * max(0.025, 0.12 - improvement + RNG.uniform(-0.018, 0.018))))
            values = {
                "requests_received": received,
                "requests_within_sla": within,
                "concluded": concluded,
                "reopened": reopened,
                "open_balance": open_balance,
                "avg_first_response_hours": round(max(0.3, first_hours * (1 - improvement * 2) + RNG.uniform(-0.8, 0.8)), 2),
                "avg_resolution_hours": round(max(1.0, resolution_hours * (1 - improvement) + RNG.uniform(-3.0, 3.0)), 2),
            }
            rows.append(measurement("DADM", "DADM-01", period, values, {"channel": channel}, row_id=row_id))
            row_id += 1

            eligible = max(5, round(concluded * RNG.uniform(0.92, 1.0)))
            response_rate = min(0.42, max(0.16, 0.20 + index * 0.009 + RNG.uniform(-0.025, 0.025)))
            respondents = max(1, round(eligible * response_rate))
            satisfaction = min(0.93, max(0.62, 0.72 + improvement * 1.8 + RNG.uniform(-0.035, 0.035)))
            dissatisfied_rate = min(0.18, max(0.025, 0.12 - improvement + RNG.uniform(-0.018, 0.018)))
            satisfied = round(respondents * satisfaction)
            dissatisfied = min(respondents - satisfied, round(respondents * dissatisfied_rate))
            sat_values = {
                "eligible_interactions": eligible,
                "respondents": respondents,
                "satisfied": satisfied,
                "dissatisfied": max(0, dissatisfied),
            }
            rows.append(measurement("DADM", "DADM-02", period, sat_values, {"channel": channel}, row_id=row_id))
            row_id += 1

    targets = [
        target("DADM", "DADM-01", "sla_compliance_pct", periods[0], row_id=1, target_value=90, attention=85),
        target("DADM", "DADM-01", "reopen_rate_pct", periods[0], row_id=2, target_value=5, attention=8),
        target("DADM", "DADM-02", "satisfaction_pct", periods[0], row_id=3, target_value=80, attention=70),
        target("DADM", "DADM-02", "dissatisfaction_pct", periods[0], row_id=4, target_value=8, attention=12),
        target("DADM", "DADM-02", "response_rate_pct", periods[0], row_id=5, target_value=25, attention=15),
    ]
    actions = [
        action(
            "DADM", "DADM-01", "sla_compliance_pct", "2026-06",
            "Ouvidoria permaneceu abaixo do prazo institucional em dois fechamentos.",
            "Revisar triagem, responsáveis substitutos e alertas de vencimento por canal.", row_id=1,
        ),
        action(
            "DADM", "DADM-02", "response_rate_pct", "2026-05",
            "Taxa de resposta ainda insuficiente em parte dos canais.",
            "Automatizar o disparo e reduzir a pesquisa para uma pergunta obrigatória e uma aberta opcional.", row_id=2,
        ),
    ]
    return rows, targets, actions


def dpe_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    periods = month_periods(2024, 9, 24)  # até 2026-08
    courses = [
        ("Administração", "DTNH", 350_000, 0.75, 88),
        ("Direito", "DTNH", 510_000, 0.78, 125),
        ("Agronomia", "DTNH", 420_000, 0.83, 118),
        ("Psicologia", "DCS", 475_000, 0.79, 120),
        ("Enfermagem", "DCS", 395_000, 0.82, 104),
        ("Odontologia", "DCS", 760_000, 0.87, 142),
        ("Fisioterapia", "DCS", 360_000, 0.81, 96),
    ]
    rows: list[dict[str, Any]] = []
    row_id = 1
    for index, period in enumerate(periods):
        season = 1 + 0.09 * math.sin((index + 1) / 2.7)
        cost_pressure = 1 + index * 0.0025
        total_revenue = 0.0
        total_cost = 0.0
        for course, academic_dir, base_revenue, cost_ratio, hours in courses:
            revenue = round(base_revenue * season * (1 + index * 0.005) + RNG.uniform(-18_000, 18_000), 2)
            ratio = min(0.98, max(0.61, cost_ratio * cost_pressure + RNG.uniform(-0.018, 0.018)))
            total_course_cost = revenue * ratio
            faculty_cost = total_course_cost * 0.60
            coordination_cost = total_course_cost * 0.06
            other_direct = total_course_cost * 0.16
            indirect = total_course_cost - faculty_cost - coordination_cost - other_direct
            teacher_count = max(5, round(hours / RNG.uniform(14.0, 18.0)))
            values = {
                "net_revenue": round(revenue, 2),
                "faculty_cost": round(faculty_cost, 2),
                "coordination_cost": round(coordination_cost, 2),
                "other_direct_cost": round(other_direct, 2),
                "indirect_cost": round(indirect, 2),
                "weekly_teaching_hours": round(hours * RNG.uniform(0.97, 1.04), 2),
                "teacher_count": teacher_count,
            }
            dims = {"course": course, "academic_directorate": academic_dir}
            rows.append(measurement("DPE", "DPE-01", period, values, dims, row_id=row_id))
            row_id += 1
            total_revenue += revenue
            total_cost += total_course_cost

        # Institucional: cobertura e folha. Os componentes são mantidos em competência.
        personnel = total_cost * 0.57
        operational = total_cost * 0.18
        administrative = total_cost * 0.14
        financial = total_cost * 0.045
        coverage_values = {
            "net_revenue": round(total_revenue, 2),
            "personnel_expense": round(personnel, 2),
            "operational_expense": round(operational, 2),
            "administrative_expense": round(administrative, 2),
            "financial_expense": round(financial, 2),
            "capex": round(total_revenue * RNG.uniform(0.01, 0.035), 2),
        }
        rows.append(measurement("DPE", "DPE-02", period, coverage_values, {"cost_center": "Institucional"}, row_id=row_id))
        row_id += 1

        faculty_payroll = total_revenue * max(0.31, 0.36 - index * 0.001 + RNG.uniform(-0.006, 0.006))
        admin_payroll = total_revenue * max(0.12, 0.16 - index * 0.0005 + RNG.uniform(-0.004, 0.004))
        payroll_values = {
            "faculty_payroll": round(faculty_payroll, 2),
            "administrative_payroll": round(admin_payroll, 2),
            "gross_salaries": round((faculty_payroll + admin_payroll) * 0.72, 2),
            "charges": round((faculty_payroll + admin_payroll) * 0.18, 2),
            "provisions": round((faculty_payroll + admin_payroll) * 0.10, 2),
            "net_revenue": round(total_revenue, 2),
        }
        rows.append(measurement("DPE", "DPE-03", period, payroll_values, {"category": "Folha total"}, row_id=row_id))
        row_id += 1

    targets = [
        target("DPE", "DPE-01", "net_margin_pct", periods[0], row_id=1, target_value=15, attention=0),
        target("DPE", "DPE-01", "avg_hours_per_teacher", periods[0], row_id=2, target_min=12, target_max=20),
        target("DPE", "DPE-02", "coverage_index", periods[0], row_id=3, target_value=1.11, attention=1.05),
        target("DPE", "DPE-03", "payroll_on_revenue_pct", periods[0], row_id=4, target_value=55, attention=58),
        target("DPE", "DPE-03", "faculty_payroll_pct", periods[0], row_id=5, target_value=38),
        target("DPE", "DPE-03", "administrative_payroll_pct", periods[0], row_id=6, target_value=17),
        target("DPE", "DPE-03", "payroll_monthly_change_pct", periods[0], row_id=7, target_value=2),
    ]
    actions = [
        action(
            "DPE", "DPE-01", "net_margin_pct", "2026-06",
            "Dois cursos ficaram abaixo da margem mínima por curso.",
            "Revisar oferta, tamanho de turma, carga horária alocada e critério de rateio, sem reduzir qualidade acadêmica.", row_id=1,
        ),
        action(
            "DPE", "DPE-02", "coverage_index", "2026-04",
            "Cobertura mensal aproximou-se do limite de atenção no período sazonal.",
            "Acompanhar o acumulado de doze meses e reprogramar despesas discricionárias.", row_id=2,
        ),
    ]
    return rows, targets, actions


def dm_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    periods = semester_periods(2022, 1, 10)  # até 2026-SEM2
    lines = ["Ciência, Tecnologia e Educação", "Saúde e Desigualdades Sociais"]
    rows: list[dict[str, Any]] = []
    row_id = 1
    active_by_line = {lines[0]: 28, lines[1]: 24}
    for index, period in enumerate(periods):
        for line_index, research_line in enumerate(lines):
            active_start = active_by_line[research_line]
            entrants = 7 + ((index + line_index) % 4)
            graduates = 4 + ((index + line_index * 2) % 5)
            dropped = 0 if (index + line_index) % 4 else 1
            active_end = active_start + entrants - graduates - dropped
            active_by_line[research_line] = active_end
            vacancies = 10
            effective = min(vacancies, 8 + ((index + line_index) % 3))
            values = {
                "active_start": active_start,
                "entrants": entrants,
                "graduates": graduates,
                "dropped": dropped,
                "locked": 1 if (index + line_index) % 5 == 0 else 0,
                "vacancies_authorized": vacancies,
                "enrollments_effective": effective,
                "active_over_regulatory": 1 if index in {2, 5} and line_index == 0 else 0,
            }
            rows.append(measurement("DM", "DM-01", period, values, {"research_line": research_line}, row_id=row_id))
            row_id += 1

            defenses = max(2, graduates)
            average_months = max(20.0, 26.0 - index * 0.35 + line_index * 0.45 + RNG.uniform(-0.7, 0.7))
            median_months = max(19.0, average_months - RNG.uniform(0.2, 1.4))
            cohort_entrants = 10
            on_time = min(cohort_entrants, max(5, round(cohort_entrants * (0.61 + index * 0.018 + RNG.uniform(-0.04, 0.04)))))
            defense_values = {
                "defenses_count": defenses,
                "average_months": round(average_months, 2),
                "median_months": round(median_months, 2),
                "cohort_entrants": cohort_entrants,
                "graduated_within_24": on_time,
                "active_over_30_no_defense": 1 if index < 4 and line_index == 0 else 0,
                "active_over_18_no_qualification": 1 if index in {1, 3, 6} and line_index == 1 else 0,
                "permanent_faculty": 6,
                "active_advisees": max(20, active_end),
            }
            rows.append(measurement("DM", "DM-02", period, defense_values, {"research_line": research_line}, row_id=row_id))
            row_id += 1

    targets = [
        target("DM", "DM-01", "cohort_members", periods[0], row_id=1, target_value=10),
        target("DM", "DM-02", "average_months_to_defense", periods[0], row_id=2, target_value=24),
    ]
    actions = [
        action(
            "DM", "DM-02", "on_time_graduation_pct", "2025-SEM2",
            "Titulação em até 24 meses ainda abaixo da meta de referência.",
            "Criar marcos semestrais de qualificação, escrita e defesa por coorte e orientador.", row_id=1,
        ),
        action(
            "DM", "DM-01", "active_over_regulatory", "2025-SEM1",
            "Houve estudante ativo acima do prazo regimental.",
            "Formalizar plano individual de conclusão e monitoramento pelo colegiado.", row_id=2,
        ),
    ]
    return rows, targets, actions
