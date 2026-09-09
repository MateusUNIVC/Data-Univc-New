from __future__ import annotations

from collections import defaultdict
from typing import Any

from analytics import active_goal, period_key


def _valid_month(value: Any) -> bool:
    text = str(value or "")
    if len(text) != 7 or text[4] != "-":
        return False
    try:
        year, month = int(text[:4]), int(text[5:])
        return year >= 2000 and 1 <= month <= 12
    except ValueError:
        return False


def _goal(snapshot: dict[str, Any], code: str, period: str | None, scope: str | None = None) -> dict[str, Any] | None:
    if not period:
        return None
    return active_goal(snapshot.get("metas", []), code, period, scope)


def _num(goal: dict[str, Any] | None, field: str) -> float | None:
    if not goal or goal.get(field) in (None, ""):
        return None
    try:
        return float(goal[field])
    except (TypeError, ValueError):
        return None


def _higher_status(value: float | None, goal: dict[str, Any] | None) -> str:
    if value is None:
        return "Sem dados"
    target = _num(goal, "meta")
    if target is None:
        return "Sem meta"
    attention = _num(goal, "atencao")
    if attention is None or attention > target:
        attention = target
    if value >= target:
        return "Dentro da meta"
    if value >= attention:
        return "Atenção"
    return "Fora da meta"


def _range_status(value: float | None, goal: dict[str, Any] | None) -> str:
    if value is None:
        return "Sem dados"
    low = _num(goal, "meta")
    high = _num(goal, "limite_superior")
    if low is None or high is None:
        return "Sem meta"
    attention = _num(goal, "atencao")
    if attention is None or attention > low:
        attention = low
    if low <= value <= high:
        return "Dentro da meta"
    if attention <= value < low:
        return "Atenção"
    return "Fora da meta"


def _money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%".replace(".", ",")


def _all_periods(snapshot: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for key in ("resultado", "orcamento", "caixa"):
        for row in snapshot.get(key, []):
            p = str(row.get("periodo") or "")
            if _valid_month(p):
                values.add(p)
    return sorted(values, key=period_key)


def _previous(periods: list[str], reference: str | None) -> str | None:
    if not reference:
        return None
    earlier = [p for p in periods if period_key(p) < period_key(reference)]
    return earlier[-1] if earlier else None


def _effective(periods: list[str], requested: str | None) -> str | None:
    if not periods:
        return None
    if not requested:
        return periods[-1]
    eligible = [p for p in periods if period_key(p) <= period_key(requested)]
    return eligible[-1] if eligible else None


def _window(periods: list[str], start: str | None, end: str | None, window_months: int | None, reference: str | None) -> list[str]:
    out = periods
    if start and _valid_month(start):
        out = [p for p in out if period_key(p) >= period_key(start)]
    if end and _valid_month(end):
        out = [p for p in out if period_key(p) <= period_key(end)]
    if window_months and reference:
        eligible = [p for p in out if period_key(p) <= period_key(reference)]
        out = eligible[-window_months:]
    return out


def _result_rows(snapshot: dict[str, Any], period: str | None, scope_type: str | None, scope_label: str | None) -> list[dict[str, Any]]:
    rows = [r for r in snapshot.get("resultado", []) if r.get("validacao") == "OK" and (period is None or r.get("periodo") == period)]
    if scope_type:
        rows = [r for r in rows if r.get("tipo_recorte") == scope_type]
        if scope_label:
            rows = [r for r in rows if str(r.get("recorte") or "") == scope_label]
    elif scope_label:
        rows = [r for r in rows if str(r.get("recorte") or "") == scope_label]
    else:
        # Default institutional KPI avoids summing overlapping recortes.
        rows = [r for r in rows if r.get("tipo_recorte") == "Institucional" and r.get("recorte") == "TOTAL"]
    return rows


def _result_metric(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"receita": None, "despesa": None, "resultado": None, "margem": None}
    revenue = sum(float(r.get("receita_liquida") or 0) for r in rows)
    expense = sum(float(r.get("despesa_total") or 0) for r in rows)
    result = revenue - expense
    return {
        "receita": round(revenue, 2),
        "despesa": round(expense, 2),
        "resultado": round(result, 2),
        "margem": round(result / revenue * 100, 2) if revenue else None,
    }


def _budget_rows(snapshot: dict[str, Any], period: str | None, unit: str | None, cost_center: str | None) -> list[dict[str, Any]]:
    rows = [r for r in snapshot.get("orcamento", []) if r.get("validacao") == "OK" and (period is None or r.get("periodo") == period)]
    if unit:
        rows = [r for r in rows if str(r.get("unidade") or "") == unit]
    if cost_center:
        rows = [r for r in rows if str(r.get("centro_custo") or "") == cost_center]
    return rows


def _budget_metric(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"orcado": None, "realizado": None, "execucao": None, "desvio": None}
    budgeted = sum(float(r.get("despesa_orcada") or 0) for r in rows)
    actual = sum(float(r.get("despesa_realizada") or 0) for r in rows)
    return {
        "orcado": round(budgeted, 2),
        "realizado": round(actual, 2),
        "execucao": round(actual / budgeted * 100, 2) if budgeted else None,
        "desvio": round(actual - budgeted, 2),
    }


def _cash_rows(snapshot: dict[str, Any], period: str | None, account: str | None, nature: str | None) -> list[dict[str, Any]]:
    rows = [r for r in snapshot.get("caixa", []) if r.get("validacao") == "OK" and (period is None or r.get("periodo") == period)]
    if account:
        rows = [r for r in rows if str(r.get("conta") or "") == account]
    if nature:
        rows = [r for r in rows if str(r.get("natureza") or "") == nature]
    return rows


def _cash_metric(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"entradas": None, "saidas": None, "saldo": None}
    entries = sum(float(r.get("valor") or 0) for r in rows if r.get("tipo_movimento") == "Entrada")
    exits = sum(float(r.get("valor") or 0) for r in rows if r.get("tipo_movimento") == "Saída")
    return {"entradas": round(entries, 2), "saidas": round(exits, 2), "saldo": round(entries - exits, 2)}


def build_dpe_dashboard(
    snapshot: dict[str, Any],
    referencia: str | None = None,
    comparacao: str | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    tipo_recorte: str | None = None,
    recorte: str | None = None,
    unidade: str | None = None,
    centro_custo: str | None = None,
    conta: str | None = None,
    natureza: str | None = None,
    window_months: int | None = None,
) -> dict[str, Any]:
    periods = _all_periods(snapshot)
    reference = _effective(periods, referencia)
    comparison = _effective([p for p in periods if not reference or period_key(p) < period_key(reference)], comparacao) if comparacao else _previous(periods, reference)
    visible_periods = _window(periods, inicio, fim, window_months, reference)

    result = _result_metric(_result_rows(snapshot, reference, tipo_recorte, recorte))
    result_cmp = _result_metric(_result_rows(snapshot, comparison, tipo_recorte, recorte))
    budget = _budget_metric(_budget_rows(snapshot, reference, unidade, centro_custo))
    budget_cmp = _budget_metric(_budget_rows(snapshot, comparison, unidade, centro_custo))
    cash = _cash_metric(_cash_rows(snapshot, reference, conta, natureza))
    cash_cmp = _cash_metric(_cash_rows(snapshot, comparison, conta, natureza))

    result_scope = recorte or ("TOTAL" if not tipo_recorte or tipo_recorte == "Institucional" else None)
    result_goal = _goal(snapshot, "DPE-01", reference, result_scope)
    budget_goal = _goal(snapshot, "DPE-04", reference, centro_custo or unidade or "TOTAL")
    cash_goal = _goal(snapshot, "DPE-05", reference, conta or "TOTAL")
    result_status = _higher_status(result["margem"], result_goal)
    budget_status = _range_status(budget["execucao"], budget_goal)
    cash_status = _higher_status(cash["saldo"], cash_goal)

    cumulative_by_period: dict[str, float] = {}
    cumulative = 0.0
    for period in periods:
        if reference and period_key(period) > period_key(reference):
            continue
        historical_cash = _cash_metric(_cash_rows(snapshot, period, conta, natureza))
        if historical_cash["saldo"] is not None:
            cumulative += float(historical_cash["saldo"])
        cumulative_by_period[period] = round(cumulative, 2)

    result_series = []
    budget_series = []
    cash_series = []
    for period in visible_periods:
        rm = _result_metric(_result_rows(snapshot, period, tipo_recorte, recorte))
        rg = _goal(snapshot, "DPE-01", period, result_scope)
        result_series.append({"periodo": period, "valor": rm["margem"], "resultado": rm["resultado"], "receita": rm["receita"], "despesa": rm["despesa"], "meta": _num(rg, "meta"), "status": _higher_status(rm["margem"], rg)})
        bm = _budget_metric(_budget_rows(snapshot, period, unidade, centro_custo))
        bg = _goal(snapshot, "DPE-04", period, centro_custo or unidade or "TOTAL")
        budget_series.append({"periodo": period, "valor": bm["execucao"], "orcado": bm["orcado"], "realizado": bm["realizado"], "desvio": bm["desvio"], "meta": _num(bg, "meta"), "limite_superior": _num(bg, "limite_superior"), "status": _range_status(bm["execucao"], bg)})
        cm = _cash_metric(_cash_rows(snapshot, period, conta, natureza))
        cg = _goal(snapshot, "DPE-05", period, conta or "TOTAL")
        cash_series.append({"periodo": period, "valor": cm["saldo"], "entradas": cm["entradas"], "saidas": cm["saidas"], "saldo_acumulado": cumulative_by_period.get(period), "meta": _num(cg, "meta"), "status": _higher_status(cm["saldo"], cg)})

    current_result_rows = [r for r in snapshot.get("resultado", []) if r.get("periodo") == reference and r.get("validacao") == "OK"]
    result_by_cut = []
    for r in current_result_rows:
        result_by_cut.append({"label": f"{r.get('tipo_recorte')}: {r.get('recorte')}", "valor": r.get("margem_operacional"), "tipo": r.get("tipo_recorte"), "recorte": r.get("recorte")})
    result_by_cut.sort(key=lambda x: (str(x.get("tipo")), str(x.get("recorte"))))

    budget_by_unit = []
    grouped_budget: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in _budget_rows(snapshot, reference, None, centro_custo):
        grouped_budget[str(r.get("unidade") or "Sem diretoria")].append(r)
    for label, rows in sorted(grouped_budget.items()):
        m = _budget_metric(rows); budget_by_unit.append({"label": label, "valor": m["execucao"], "orcado": m["orcado"], "realizado": m["realizado"]})

    cash_by_account = []
    grouped_cash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in _cash_rows(snapshot, reference, None, natureza):
        grouped_cash[str(r.get("conta") or "Sem conta")].append(r)
    for label, rows in sorted(grouped_cash.items()):
        m = _cash_metric(rows); cash_by_account.append({"label": label, "valor": m["saldo"], "entradas": m["entradas"], "saidas": m["saidas"]})

    outflow_by_nature = []
    grouped_nature: dict[str, float] = defaultdict(float)
    for r in _cash_rows(snapshot, reference, conta, None):
        if r.get("tipo_movimento") == "Saída":
            grouped_nature[str(r.get("natureza") or "Sem natureza")] += float(r.get("valor") or 0)
    for label, value in sorted(grouped_nature.items(), key=lambda item: item[1], reverse=True):
        outflow_by_nature.append({"label": label, "valor": round(value, 2)})

    insights: list[dict[str, str]] = []
    if result["margem"] is None:
        insights.append({"nivel": "atenção", "titulo": "DPE-01 sem fechamento", "texto": "Cadastre receita líquida e despesa total do recorte para calcular o Resultado Operacional."})
    else:
        insights.append({"nivel": "positivo" if result_status == "Dentro da meta" else "atenção", "titulo": f"Resultado operacional: {result_status.lower()}", "texto": f"Margem de {_pct(result['margem'])} em {reference}, com resultado de {_money(result['resultado'])}."})
    if budget["execucao"] is None:
        insights.append({"nivel": "atenção", "titulo": "DPE-04 sem fechamento", "texto": "Cadastre orçamento e realizado por diretoria e centro de custo."})
    else:
        insights.append({"nivel": "positivo" if budget_status == "Dentro da meta" else "atenção", "titulo": f"Execução orçamentária: {budget_status.lower()}", "texto": f"Execução de {_pct(budget['execucao'])}; desvio de {_money(budget['desvio'])} entre realizado e orçado."})
    if cash["saldo"] is None:
        insights.append({"nivel": "atenção", "titulo": "DPE-05 sem fechamento", "texto": "Cadastre entradas e saídas por conta e natureza para calcular o saldo operacional."})
    else:
        insights.append({"nivel": "positivo" if cash["saldo"] > 0 else "atenção", "titulo": "Saldo operacional de caixa", "texto": f"Entradas de {_money(cash['entradas'])}, saídas de {_money(cash['saidas'])} e saldo mensal de {_money(cash['saldo'])}. A reserva mínima equivalente a uma folha depende de futura integração com a folha/DPE-06."})

    open_actions = sum(1 for a in snapshot.get("actions", []) if a.get("status") not in {"Concluído", "Cancelado"})
    overdue = sum(1 for a in snapshot.get("actions", []) if a.get("dias_prazo") is not None and a.get("dias_prazo") < 0 and a.get("status") not in {"Concluído", "Cancelado"})

    return {
        "contexto": {"diretoria": "DPE", "referencia": reference, "comparacao": comparison, "inicio": inicio, "fim": fim, "tipo_recorte": tipo_recorte, "recorte": recorte, "unidade": unidade, "centro_custo": centro_custo, "conta": conta, "natureza": natureza},
        "periodos": {"mensais": periods},
        "filtros": {
            "tipos_recorte": sorted({str(r.get("tipo_recorte")) for r in snapshot.get("resultado", []) if r.get("tipo_recorte")}) or ["Institucional", "Modalidade", "Polo", "Curso", "Programa stricto sensu"],
            "recortes": sorted({str(r.get("recorte")) for r in snapshot.get("resultado", []) if r.get("recorte")}),
            "diretorias": sorted({str(r.get("unidade")) for r in snapshot.get("orcamento", []) if r.get("unidade")}),
            "centros_custo": sorted({str(r.get("centro_custo")) for r in snapshot.get("orcamento", []) if r.get("centro_custo")}),
            "contas": sorted({str(r.get("conta")) for r in snapshot.get("caixa", []) if r.get("conta")}),
            "naturezas": sorted({str(r.get("natureza")) for r in snapshot.get("caixa", []) if r.get("natureza")}),
        },
        "cards": {
            "resultado": {**result, "valor": result["margem"], "periodo": reference, "comparacao": result_cmp["margem"], "status": result_status, "meta": _num(result_goal, "meta"), "atencao": _num(result_goal, "atencao"), "meta_texto": f"Pelo menos {_pct(_num(result_goal, 'meta'))}" if _num(result_goal, "meta") is not None else "Sem meta vigente"},
            "orcamento": {**budget, "valor": budget["execucao"], "periodo": reference, "comparacao": budget_cmp["execucao"], "status": budget_status, "meta": _num(budget_goal, "meta"), "atencao": _num(budget_goal, "atencao"), "limite_superior": _num(budget_goal, "limite_superior"), "meta_texto": f"Faixa {_pct(_num(budget_goal, 'meta'))} a {_pct(_num(budget_goal, 'limite_superior'))}" if _num(budget_goal, "meta") is not None and _num(budget_goal, "limite_superior") is not None else "Sem faixa de meta vigente"},
            "caixa": {**cash, "valor": cash["saldo"], "periodo": reference, "comparacao": cash_cmp["saldo"], "status": cash_status, "meta": _num(cash_goal, "meta"), "atencao": _num(cash_goal, "atencao"), "saldo_acumulado": cumulative_by_period.get(reference) if reference else None, "meta_texto": "Saldo mensal positivo; reserva de uma folha ainda depende da integração com DPE-06."},
            "qualidade": {"resultado": 0 if result["margem"] is not None else 1, "orcamento": 0 if budget["execucao"] is not None else 1, "caixa": 0 if cash["saldo"] is not None else 1, "total": sum([result["margem"] is None, budget["execucao"] is None, cash["saldo"] is None])},
            "planos": {"abertos": open_actions, "atrasados": overdue},
        },
        "series": {"resultado": result_series, "orcamento": budget_series, "caixa": cash_series},
        "comparacoes": {"resultado_por_recorte": result_by_cut[:20], "orcamento_por_diretoria": budget_by_unit, "caixa_por_conta": cash_by_account, "saidas_por_natureza": outflow_by_nature[:12]},
        "metas_vigentes": {
            "resultado": {"codigo": "DPE-01", "meta": _num(result_goal, "meta"), "atencao": _num(result_goal, "atencao"), "unidade": "%", "recorte": result_scope or "TOTAL", "vigencia": str(result_goal.get("vigencia") or "") if result_goal else ""},
            "orcamento": {"codigo": "DPE-04", "meta": _num(budget_goal, "meta"), "atencao": _num(budget_goal, "atencao"), "limite_superior": _num(budget_goal, "limite_superior"), "unidade": "%", "recorte": centro_custo or unidade or "TOTAL", "vigencia": str(budget_goal.get("vigencia") or "") if budget_goal else ""},
            "caixa": {"codigo": "DPE-05", "meta": _num(cash_goal, "meta"), "atencao": _num(cash_goal, "atencao"), "unidade": "R$", "recorte": conta or "TOTAL", "vigencia": str(cash_goal.get("vigencia") or "") if cash_goal else ""},
        },
        "insights": insights[:6],
    }
