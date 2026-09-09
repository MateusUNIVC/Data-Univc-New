from __future__ import annotations

from collections import defaultdict
from typing import Any


def _period_key(period: str) -> int:
    try:
        year, month = (int(part) for part in str(period).split("-"))
        return year * 12 + month
    except Exception:
        return -1


def _pct(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator * 100, 2)


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def _rolling_periods(periods: list[str], reference: str, months: int) -> list[str]:
    eligible = [p for p in periods if _period_key(p) <= _period_key(reference)]
    return eligible[-months:]


def build_dpe_finance_dashboard(
    snapshot: dict[str, Any],
    *,
    reference: str | None = None,
    window_months: int | None = 12,
    course_id: int | None = None,
) -> dict[str, Any]:
    """Build all financial readings from one non-duplicated DPE fact base.

    The institutional expense total always comes exclusively from ``expenses``.
    Course revenue is optional. Course cost snapshots and their optional detail
    lines are reconciliation aids and never create a second institutional cost.
    """

    revenues = snapshot.get("revenues") or []
    course_revenues = snapshot.get("course_revenues") or []
    expenses = snapshot.get("expenses") or []
    course_costs = snapshot.get("course_costs") or []

    periods = sorted(
        {
            *(str(row.get("period")) for row in revenues if row.get("period")),
            *(str(row.get("period")) for row in course_revenues if row.get("period")),
            *(str(row.get("period")) for row in expenses if row.get("period")),
            *(str(row.get("period")) for row in course_costs if row.get("period")),
        },
        key=_period_key,
    )
    if not reference:
        reference = periods[-1] if periods else None
    if reference and reference not in periods:
        eligible = [p for p in periods if _period_key(p) <= _period_key(reference)]
        reference = eligible[-1] if eligible else reference

    visible_periods = periods
    if reference:
        visible_periods = [p for p in periods if _period_key(p) <= _period_key(reference)]
    if window_months and visible_periods:
        visible_periods = visible_periods[-window_months:]

    revenue_by_period = {str(row["period"]): float(row.get("net_revenue") or 0) for row in revenues}

    expense_by_period: dict[str, float] = defaultdict(float)
    payroll_by_period: dict[str, float] = defaultdict(float)
    capex_by_period: dict[str, float] = defaultdict(float)
    allocated_by_period: dict[str, float] = defaultdict(float)
    expense_category_by_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    payroll_group_by_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    payroll_nature_by_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # Course allocation views. These are analytical views of real expenses and
    # therefore do not alter expense_by_period.
    course_allocated_cost: dict[tuple[str, int], float] = defaultdict(float)
    course_allocated_capex: dict[tuple[str, int], float] = defaultdict(float)
    course_breakdown: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    course_meta: dict[int, dict[str, Any]] = {}

    for row in expenses:
        period = str(row.get("period") or "")
        amount = float(row.get("amount") or 0)
        allocated = float(row.get("allocated_amount") or 0)
        if row.get("is_capex"):
            capex_by_period[period] += amount
        else:
            expense_by_period[period] += amount
            allocated_by_period[period] += allocated
            expense_category_by_period[period][str(row.get("category") or "OTHER")] += amount
            if row.get("expense_kind") == "PAYROLL":
                payroll_by_period[period] += amount
                payroll_group_by_period[period][str(row.get("payroll_group") or "OTHER")] += amount
                payroll_nature_by_period[period][str(row.get("payroll_nature") or "OTHER")] += amount

        for allocation in row.get("allocations") or []:
            cid = int(allocation.get("course_id"))
            alloc_amount = float(allocation.get("allocated_amount") or 0)
            key = (period, cid)
            if row.get("is_capex"):
                course_allocated_capex[key] += alloc_amount
            else:
                course_allocated_cost[key] += alloc_amount
            course_breakdown[key].append(
                {
                    "expense_id": row.get("id"),
                    "description": row.get("description"),
                    "expense_kind": row.get("expense_kind"),
                    "category": row.get("category"),
                    "payroll_group": row.get("payroll_group"),
                    "allocated_amount": round(alloc_amount, 2),
                    "is_capex": bool(row.get("is_capex")),
                }
            )
            course_meta[cid] = {
                "course_id": cid,
                "course_name": allocation.get("course_name"),
                "academic_directorate": allocation.get("academic_directorate"),
            }

    course_revenue_by_period: dict[str, float] = defaultdict(float)
    course_revenue_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for row in course_revenues:
        period = str(row.get("period") or "")
        cid = int(row.get("course_id"))
        course_revenue_by_period[period] += float(row.get("allocated_revenue") or 0)
        course_revenue_lookup[(period, cid)] = row
        course_meta[cid] = {
            "course_id": cid,
            "course_name": row.get("course_name"),
            "academic_directorate": row.get("academic_directorate"),
        }

    course_cost_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for row in course_costs:
        period = str(row.get("period") or "")
        cid = int(row.get("course_id"))
        course_cost_lookup[(period, cid)] = row
        course_meta[cid] = {
            "course_id": cid,
            "course_name": row.get("course_name"),
            "academic_directorate": row.get("academic_directorate"),
        }

    def course_values(period: str, cid: int) -> dict[str, Any]:
        key = (period, cid)
        revenue_row = course_revenue_lookup.get(key)
        cost_row = course_cost_lookup.get(key)
        has_allocated_cost = key in course_allocated_cost
        allocated_cost = round(course_allocated_cost.get(key, 0.0), 2)
        reported_cost = float(cost_row.get("reported_total_cost")) if cost_row else None
        reported_details = list(cost_row.get("details") or []) if cost_row else []
        reported_detail_total = round(sum(float(item.get("amount") or 0) for item in reported_details), 2)
        has_reported_cost = cost_row is not None
        has_cost_data = has_reported_cost or has_allocated_cost
        effective_cost = (
            reported_cost
            if has_reported_cost
            else allocated_cost
            if has_allocated_cost
            else None
        )
        revenue = float(revenue_row.get("allocated_revenue")) if revenue_row else None
        has_revenue_data = revenue_row is not None
        gap = round(reported_cost - allocated_cost, 2) if has_reported_cost else None
        result_amount = (
            round(revenue - float(effective_cost), 2)
            if has_revenue_data and has_cost_data and effective_cost is not None
            else None
        )
        margin_pct = _pct(result_amount, revenue) if result_amount is not None else None
        expense_to_revenue_pct = (
            _pct(float(effective_cost), revenue)
            if has_revenue_data and has_cost_data and effective_cost is not None
            else None
        )
        data_status = (
            "Apuração completa"
            if has_revenue_data and has_cost_data
            else "Aguardando custo/despesa"
            if has_revenue_data
            else "Aguardando receita"
            if has_cost_data
            else "Sem apuração"
        )
        cost_source = (
            "Apuração gerencial"
            if has_reported_cost
            else "Despesas rateadas"
            if has_allocated_cost
            else "Pendente"
        )
        return {
            "revenue": revenue,
            "has_revenue_data": has_revenue_data,
            "reported_total_cost": reported_cost,
            "reported_details": reported_details,
            "reported_detail_total": reported_detail_total,
            "reported_undetailed_cost": (
                round(max(reported_cost - reported_detail_total, 0.0), 2)
                if reported_cost is not None
                else None
            ),
            "allocated_cost": allocated_cost,
            "has_allocated_cost": has_allocated_cost,
            "has_reported_cost": has_reported_cost,
            "has_cost_data": has_cost_data,
            "cost_source": cost_source,
            "effective_cost": round(float(effective_cost), 2) if effective_cost is not None else None,
            "result_amount": result_amount,
            "expense_to_revenue_pct": expense_to_revenue_pct,
            "margin_pct": margin_pct,
            "data_status": data_status,
            "unreconciled_cost": gap,
            "reconciliation_status": (
                "Sem total informado"
                if not has_reported_cost
                else "Reconciliado"
                if abs(gap or 0) <= 0.01
                else "Parcial"
                if gap and gap > 0
                else "Rateios acima do total informado"
            ),
            "capex_allocated": round(course_allocated_capex.get(key, 0.0), 2),
            "breakdown": sorted(
                course_breakdown.get(key, []),
                key=lambda row: (-row["allocated_amount"], str(row["description"])),
            ),
        }

    # Institutional monthly history. Rolling KPI calculations are ratios of
    # rolling totals, never averages of monthly ratios.
    series: list[dict[str, Any]] = []
    previous_payroll: float | None = None
    for period in visible_periods:
        revenue = revenue_by_period.get(period, 0.0)
        expense = expense_by_period.get(period, 0.0)
        payroll = payroll_by_period.get(period, 0.0)
        rolling12 = _rolling_periods(periods, period, 12)
        revenue12 = sum(revenue_by_period.get(p, 0.0) for p in rolling12)
        expense12 = sum(expense_by_period.get(p, 0.0) for p in rolling12)
        rolling3 = _rolling_periods(periods, period, 3)
        avg_revenue3 = sum(revenue_by_period.get(p, 0.0) for p in rolling3) / len(rolling3) if rolling3 else 0.0
        faculty_payroll = payroll_group_by_period[period].get("FACULTY", 0.0)
        administrative_payroll = payroll_group_by_period[period].get("ADMINISTRATIVE", 0.0)
        series.append(
            {
                "period": period,
                "revenue": round(revenue, 2),
                "expense": round(expense, 2),
                "payroll": round(payroll, 2),
                "coverage": _ratio(revenue, expense),
                "coverage_12m": _ratio(revenue12, expense12),
                "operating_margin_pct": _pct(revenue - expense, revenue),
                "operating_margin_12m_pct": _pct(revenue12 - expense12, revenue12),
                "payroll_on_revenue_pct": _pct(payroll, revenue),
                "payroll_on_avg_revenue_3m_pct": _pct(payroll, avg_revenue3),
                "faculty_payroll_pct": _pct(faculty_payroll, revenue),
                "administrative_payroll_pct": _pct(administrative_payroll, revenue),
                "payroll_monthly_change_pct": (
                    _pct(payroll - previous_payroll, previous_payroll)
                    if previous_payroll not in (None, 0)
                    else None
                ),
                "allocated_expense_pct": _pct(allocated_by_period.get(period, 0.0), expense),
                "course_revenue_coverage_pct": _pct(course_revenue_by_period.get(period, 0.0), revenue),
            }
        )
        previous_payroll = payroll

    # DPE-01 historical aggregate only uses courses with a complete economic
    # reading in that month. Revenue without a known course cost must not become
    # an artificial 100% margin, and cost without revenue cannot form a margin.
    course_margin_series: list[dict[str, Any]] = []
    for period in visible_periods:
        revenue_total = 0.0
        cost_total = 0.0
        courses_with_revenue = 0
        courses_with_complete_data = 0
        for cid in course_meta:
            values = course_values(period, cid)
            if values["has_revenue_data"]:
                courses_with_revenue += 1
            if not (values["has_revenue_data"] and values["has_cost_data"]):
                continue
            revenue_total += float(values["revenue"] or 0)
            cost_total += float(values["effective_cost"] or 0)
            courses_with_complete_data += 1
        has_complete = courses_with_complete_data > 0
        course_margin_series.append(
            {
                "period": period,
                "course_revenue": round(revenue_total, 2) if has_complete else None,
                "course_cost": round(cost_total, 2) if has_complete else None,
                "result_amount": round(revenue_total - cost_total, 2) if has_complete else None,
                "expense_to_revenue_pct": _pct(cost_total, revenue_total) if has_complete else None,
                "margin_pct": _pct(revenue_total - cost_total, revenue_total) if has_complete else None,
                "courses_with_revenue": courses_with_revenue,
                "courses_with_complete_data": courses_with_complete_data,
            }
        )

    course_history: list[dict[str, Any]] = []
    for cid, meta in sorted(
        course_meta.items(),
        key=lambda item: (str(item[1].get("academic_directorate")), str(item[1].get("course_name"))),
    ):
        if course_id and cid != int(course_id):
            continue
        history_rows: list[dict[str, Any]] = []
        for period in visible_periods:
            values = course_values(period, cid)
            if not (values["has_revenue_data"] or values["has_cost_data"]):
                continue
            history_rows.append(
                {
                    "period": period,
                    "revenue": values["revenue"],
                    "effective_cost": values["effective_cost"],
                    "result_amount": values["result_amount"],
                    "expense_to_revenue_pct": values["expense_to_revenue_pct"],
                    "margin_pct": values["margin_pct"],
                    "data_status": values["data_status"],
                    "cost_source": values["cost_source"],
                }
            )
        if history_rows:
            course_history.append({**meta, "series": history_rows})

    current_revenue = revenue_by_period.get(reference or "", 0.0)
    current_expense = expense_by_period.get(reference or "", 0.0)
    current_payroll = payroll_by_period.get(reference or "", 0.0)
    current_allocated = allocated_by_period.get(reference or "", 0.0)
    current_course_revenue = course_revenue_by_period.get(reference or "", 0.0)

    last12 = _rolling_periods(periods, reference, 12) if reference else []
    revenue_12 = sum(revenue_by_period.get(p, 0.0) for p in last12)
    expense_12 = sum(expense_by_period.get(p, 0.0) for p in last12)

    last3 = _rolling_periods(periods, reference, 3) if reference else []
    avg_revenue_3 = sum(revenue_by_period.get(p, 0.0) for p in last3) / len(last3) if last3 else 0.0

    previous_periods = [p for p in periods if reference and _period_key(p) < _period_key(reference)]
    previous_payroll_value = payroll_by_period.get(previous_periods[-1], 0.0) if previous_periods else 0.0

    current_faculty_payroll = payroll_group_by_period[reference or ""].get("FACULTY", 0.0)
    current_administrative_payroll = payroll_group_by_period[reference or ""].get("ADMINISTRATIVE", 0.0)

    course_rows: list[dict[str, Any]] = []
    if reference:
        for cid, meta in sorted(
            course_meta.items(),
            key=lambda item: (str(item[1].get("academic_directorate")), str(item[1].get("course_name"))),
        ):
            if course_id and cid != int(course_id):
                continue
            course_rows.append({**meta, **course_values(reference, cid)})

    expense_composition = [
        {"category": key, "value": round(value, 2)}
        for key, value in sorted(
            expense_category_by_period.get(reference or "", {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    payroll_composition = [
        {"group": key, "value": round(value, 2)}
        for key, value in sorted(
            payroll_group_by_period.get(reference or "", {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]

    warnings: list[dict[str, str]] = []
    if reference and not any(row.get("period") == reference for row in revenues):
        warnings.append(
            {
                "level": "attention",
                "title": "Receita ainda não informada",
                "text": "Cadastre a receita líquida institucional para calcular cobertura e folha sobre receita.",
            }
        )
    if current_expense == 0:
        warnings.append(
            {
                "level": "attention",
                "title": "Despesas ainda não informadas",
                "text": "O índice de cobertura só fica disponível depois do lançamento das despesas reais do mês.",
            }
        )
    if current_revenue and current_course_revenue < current_revenue:
        warnings.append(
            {
                "level": "info",
                "title": "Receita por curso é parcial e opcional",
                "text": "A diferença pode representar EAD, semipresencial, cursos técnicos, mestrado e outras receitas não distribuídas aos cursos presenciais.",
            }
        )
    if current_expense and current_allocated < current_expense:
        warnings.append(
            {
                "level": "info",
                "title": "Nem toda despesa precisa ser rateada",
                "text": "Despesas institucionais ou de áreas não representadas no catálogo podem permanecer sem alocação a cursos.",
            }
        )

    return {
        "reference": reference,
        "periods": periods,
        "cards": {
            "revenue": round(current_revenue, 2),
            "expense": round(current_expense, 2),
            "coverage": _ratio(current_revenue, current_expense),
            "coverage_12m": _ratio(revenue_12, expense_12),
            "operating_margin_pct": _pct(current_revenue - current_expense, current_revenue),
            "operating_margin_12m_pct": _pct(revenue_12 - expense_12, revenue_12),
            "payroll": round(current_payroll, 2),
            "payroll_on_revenue_pct": _pct(current_payroll, current_revenue),
            "payroll_on_avg_revenue_3m_pct": _pct(current_payroll, avg_revenue_3),
            "faculty_payroll_pct": _pct(current_faculty_payroll, current_revenue),
            "administrative_payroll_pct": _pct(current_administrative_payroll, current_revenue),
            "payroll_monthly_change_pct": (
                _pct(current_payroll - previous_payroll_value, previous_payroll_value)
                if previous_payroll_value
                else None
            ),
            "capex": round(capex_by_period.get(reference or "", 0.0), 2),
            "allocated_expense": round(current_allocated, 2),
            "allocated_expense_pct": _pct(current_allocated, current_expense),
            "course_revenue": round(current_course_revenue, 2),
            "course_revenue_unallocated": round(max(current_revenue - current_course_revenue, 0), 2),
            "course_revenue_coverage_pct": _pct(current_course_revenue, current_revenue),
        },
        "series": series,
        "course_margin_series": course_margin_series,
        "course_history": course_history,
        "expense_composition": expense_composition,
        "payroll_composition": payroll_composition,
        "payroll_nature": [
            {"nature": key, "value": round(value, 2)}
            for key, value in sorted(
                payroll_nature_by_period.get(reference or "", {}).items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ],
        "courses": course_rows,
        "warnings": warnings,
    }
