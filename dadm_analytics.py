from __future__ import annotations

from typing import Any

from analytics import active_goal, period_key
from schemas import KPI_META




def _goal(snapshot: dict[str, Any], code: str, period: str | None, scope: str | None = None) -> dict[str, Any] | None:
    if not period:
        return None
    return active_goal(snapshot.get("metas", []), code, period, scope)


def _attrition_goal(snapshot: dict[str, Any], period: str | None, course_name: str | None = None) -> dict[str, Any] | None:
    return _goal(snapshot, "DADM-01", period, course_name)


def _goal_text(goal: dict[str, Any] | None, unit: str, *, lower: bool = True) -> str:
    target = _goal_number(goal, "meta")
    if target is None:
        return "Sem meta vigente cadastrada para a competência selecionada."
    vigency = str(goal.get("vigencia") or "").strip() if goal else ""
    suffix = f" · vigente desde {vigency}" if vigency else ""
    if unit.startswith("R$"):
        value = f"R$ {_pt_number(target, 2)}"
        if "/" in unit:
            value += unit[unit.index("/"):]
    elif unit == "%":
        value = f"{_pt_number(target, 1)}%"
    else:
        value = f"{_pt_number(target, 1)} {unit}".strip()
    comparator = "Até" if lower else "Pelo menos"
    return f"{comparator} {value}{suffix}"


def _goal_number(goal: dict[str, Any] | None, field: str) -> float | None:
    if not goal or goal.get(field) in (None, ""):
        return None
    try:
        return float(goal[field])
    except (TypeError, ValueError):
        return None


def _lower_is_better_status(value: float | None, goal: dict[str, Any] | None) -> str:
    if value is None:
        return "Sem dados"
    target = _goal_number(goal, "meta")
    if target is None:
        return "Sem meta"
    attention = _goal_number(goal, "atencao")
    if attention is None or attention < target:
        attention = target
    if value <= target:
        return "Dentro da meta"
    if value <= attention:
        return "Atenção"
    return "Fora da meta"


def _attrition_goal_text(goal: dict[str, Any] | None) -> str:
    text = _goal_text(goal, "%", lower=True)
    if "ao mês" in text or "%" not in text:
        return text
    if "% ·" in text:
        return text.replace("% ·", "% ao mês ·", 1)
    return text.replace("%", "% ao mês", 1)


def _valid_month(value: Any) -> bool:
    text = str(value or "")
    if len(text) != 7 or text[4] != "-":
        return False
    try:
        year, month = int(text[:4]), int(text[5:])
        return year >= 2000 and 1 <= month <= 12
    except ValueError:
        return False


def _periods(snapshot: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for key in ("evasao", "alunos", "custos", "infraestrutura"):
        for row in snapshot.get(key, []):
            period = str(row.get("periodo") or "")
            if _valid_month(period):
                values.add(period)
    return sorted(values, key=period_key)


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    course_id: int | None = None,
    modality: str | None = None,
) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("validacao") != "OK":
            continue
        if course_id is not None and int(row.get("course_id") or -1) != int(course_id):
            continue
        if modality and str(row.get("modalidade") or "") != modality:
            continue
        out.append(row)
    return out


def _rows(
    rows: list[dict[str, Any]],
    period: str | None,
    *,
    course_id: int | None = None,
    modality: str | None = None,
) -> list[dict[str, Any]]:
    if not period:
        return []
    return [
        row
        for row in _filter_rows(rows, course_id=course_id, modality=modality)
        if row.get("periodo") == period
    ]


def _effective_period(rows: list[dict[str, Any]], requested: str | None) -> str | None:
    available = sorted(
        {str(r.get("periodo")) for r in rows if _valid_month(r.get("periodo"))},
        key=period_key,
    )
    if not available:
        return None
    if not requested:
        return available[-1]
    eligible = [period for period in available if period_key(period) <= period_key(requested)]
    return eligible[-1] if eligible else None


def _previous_period(rows: list[dict[str, Any]], reference: str | None) -> str | None:
    if not reference:
        return None
    available = sorted(
        {str(r.get("periodo")) for r in rows if _valid_month(r.get("periodo"))},
        key=period_key,
    )
    earlier = [period for period in available if period_key(period) < period_key(reference)]
    return earlier[-1] if earlier else None


def _comparison_period(rows: list[dict[str, Any]], requested: str | None, reference: str | None) -> str | None:
    if requested:
        period = _effective_period(rows, requested)
        if period and (not reference or period_key(period) < period_key(reference)):
            return period
    return _previous_period(rows, reference)


def _within_window(period: str, start: str | None, end: str | None) -> bool:
    if not _valid_month(period):
        return False
    if start and _valid_month(start) and period_key(period) < period_key(start):
        return False
    if end and _valid_month(end) and period_key(period) > period_key(end):
        return False
    return True


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current / previous - 1) * 100, 2)


def _pt_number(value: float | int, decimals: int = 2) -> str:
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def attrition_rate(rows: list[dict[str, Any]]) -> float | None:
    students = sum(int(row.get("alunos_inicio") or 0) for row in rows if row.get("validacao") == "OK")
    departures = sum(int(row.get("desligamentos") or 0) for row in rows if row.get("validacao") == "OK")
    if students <= 0:
        return None
    return round(departures / students * 100, 2)


def active_students(rows: list[dict[str, Any]]) -> int | None:
    valid = [row for row in rows if row.get("validacao") == "OK"]
    if not valid:
        return None
    return sum(int(row.get("alunos_ativos") or 0) for row in valid)


def administrative_cost(rows: list[dict[str, Any]]) -> float | None:
    valid = [row for row in rows if row.get("validacao") == "OK"]
    if not valid:
        return None
    return round(sum(float(row.get("despesa") or 0) for row in valid), 2)


def cost_per_student(cost_rows: list[dict[str, Any]], student_rows: list[dict[str, Any]]) -> float | None:
    cost = administrative_cost(cost_rows)
    students = active_students(student_rows)
    if cost is None or not students:
        return None
    return round(cost / students, 2)


def infrastructure_metrics(
    infra_rows: list[dict[str, Any]],
    student_rows: list[dict[str, Any]],
) -> dict[str, float | None]:
    valid = [row for row in infra_rows if row.get("validacao") == "OK"]
    if not valid:
        return {"despesa": None, "area_m2": None, "custo_m2": None, "custo_aluno": None}
    expense = sum(float(row.get("despesa") or 0) for row in valid)
    area = sum(float(row.get("area_m2") or 0) for row in valid)
    students = active_students(student_rows)
    return {
        "despesa": round(expense, 2),
        "area_m2": round(area, 2),
        "custo_m2": round(expense / area, 2) if area else None,
        "custo_aluno": round(expense / students, 2) if students else None,
    }


def _population_series(
    snapshot: dict[str, Any],
    *,
    course_id: int | None = None,
    modality: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    scoped = _filter_rows(snapshot.get("alunos", []), course_id=course_id, modality=modality)
    periods = sorted({str(r["periodo"]) for r in scoped if _valid_month(r.get("periodo"))}, key=period_key)
    out: list[dict[str, Any]] = []
    previous: float | None = None
    for period in periods:
        if not _within_window(period, start, end):
            continue
        rows = [r for r in scoped if r.get("periodo") == period]
        value = active_students(rows)
        out.append({
            "periodo": period,
            "valor": value,
            "variacao": _pct_change(float(value) if value is not None else None, previous),
            "temporario": any(bool(r.get("temporario")) for r in rows),
            "fontes": sorted({str(r.get("origem") or "") for r in rows if r.get("origem")}),
        })
        if value is not None:
            previous = float(value)
    return out


def _attrition_series(
    snapshot: dict[str, Any],
    *,
    course_id: int | None = None,
    course_name: str | None = None,
    modality: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    scoped = _filter_rows(snapshot.get("evasao", []), course_id=course_id, modality=modality)
    periods = sorted({str(r["periodo"]) for r in scoped if _valid_month(r.get("periodo"))}, key=period_key)
    out = []
    for period in periods:
        if not _within_window(period, start, end):
            continue
        rows = [r for r in scoped if r.get("periodo") == period]
        goal = _attrition_goal(snapshot, period, course_name)
        out.append({
            "periodo": period,
            "valor": attrition_rate(rows),
            "alunos_inicio": sum(int(r.get("alunos_inicio") or 0) for r in rows),
            "desligamentos": sum(int(r.get("desligamentos") or 0) for r in rows),
            "meta": _goal_number(goal, "meta"),
            "atencao": _goal_number(goal, "atencao"),
            "meta_vigencia": str(goal.get("vigencia") or "") if goal else "",
        })
    return out


def _cost_rows(rows: list[dict[str, Any]], period: str | None, cost_center: str | None, modality: str | None) -> list[dict[str, Any]]:
    selected = _rows(rows, period, modality=modality)
    if cost_center:
        selected = [row for row in selected if str(row.get("centro_custo") or "") == cost_center]
    return selected


def _cost_series(
    snapshot: dict[str, Any],
    *,
    cost_center: str | None = None,
    modality: str | None = None,
    start: str | None = None,
    end: str | None = None,
    include_goal: bool = True,
) -> list[dict[str, Any]]:
    cost_source = _filter_rows(snapshot.get("custos", []), modality=modality)
    student_source = _filter_rows(snapshot.get("alunos", []), modality=modality)
    periods = sorted(
        {str(r["periodo"]) for r in cost_source if _valid_month(r.get("periodo"))}
        | {str(r["periodo"]) for r in student_source if _valid_month(r.get("periodo"))},
        key=period_key,
    )
    out = []
    for period in periods:
        if not _within_window(period, start, end):
            continue
        costs = _cost_rows(snapshot.get("custos", []), period, cost_center, modality)
        students = _rows(snapshot.get("alunos", []), period, modality=modality)
        value = cost_per_student(costs, students)
        goal = _goal(snapshot, "DADM-09", period) if include_goal else None
        out.append({
            "periodo": period,
            "valor": value,
            "despesa": administrative_cost(costs),
            "alunos_ativos": active_students(students),
            "meta": _goal_number(goal, "meta"),
            "atencao": _goal_number(goal, "atencao"),
            "meta_vigencia": str(goal.get("vigencia") or "") if goal else "",
            "status": _lower_is_better_status(value, goal) if include_goal else ("Sem dados" if value is None else "Recorte analítico"),
        })
    return out


def _infra_series(snapshot: dict[str, Any], start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    periods = sorted(
        {str(r["periodo"]) for r in snapshot.get("infraestrutura", []) if _valid_month(r.get("periodo"))}
        | {str(r["periodo"]) for r in snapshot.get("alunos", []) if _valid_month(r.get("periodo"))},
        key=period_key,
    )
    out = []
    for period in periods:
        if not _within_window(period, start, end):
            continue
        metrics = infrastructure_metrics(
            _rows(snapshot.get("infraestrutura", []), period),
            _rows(snapshot.get("alunos", []), period),
        )
        goal = _goal(snapshot, "DADM-10", period)
        out.append({
            "periodo": period,
            **metrics,
            "meta": _goal_number(goal, "meta"),
            "atencao": _goal_number(goal, "atencao"),
            "meta_vigencia": str(goal.get("vigencia") or "") if goal else "",
            "status": _lower_is_better_status(metrics.get("custo_m2"), goal),
        })
    return out


def _attrition_by_course(
    snapshot: dict[str, Any],
    period: str | None,
    *,
    course_id: int | None = None,
    modality: str | None = None,
) -> list[dict[str, Any]]:
    if not period:
        return []
    out = []
    for row in _rows(snapshot.get("evasao", []), period, course_id=course_id, modality=modality):
        # Temporary EAD/Semipresencial placeholders belong to the modality view only.
        # They are not real academic courses and should not pollute the course ranking.
        if row.get("temporario"):
            continue
        base = int(row.get("alunos_inicio") or 0)
        value = round(int(row.get("desligamentos") or 0) / base * 100, 2) if base else None
        if value is None:
            continue
        goal = _attrition_goal(snapshot, period, str(row.get("curso") or "") or None)
        out.append({
            "course_id": row.get("course_id"),
            "curso": row.get("curso"),
            "diretoria": row.get("diretoria_academica"),
            "modalidade": row.get("modalidade"),
            "label": f"{row.get('diretoria_academica')} · {row.get('curso')}",
            "valor": value,
            "alunos_inicio": base,
            "desligamentos": row.get("desligamentos"),
            "meta": _goal_number(goal, "meta"),
            "status": _lower_is_better_status(value, goal),
        })
    return sorted(out, key=lambda item: (-float(item["valor"]), str(item["label"])))



def _attrition_by_modality(snapshot: dict[str, Any], period: str | None) -> list[dict[str, Any]]:
    if not period:
        return []
    rows = _rows(snapshot.get("evasao", []), period)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        modality = str(row.get("modalidade") or "Presencial")
        grouped.setdefault(modality, []).append(row)
    out = []
    goal = _attrition_goal(snapshot, period, None)
    for modality, items in grouped.items():
        base = sum(int(row.get("alunos_inicio") or 0) for row in items)
        departures = sum(int(row.get("desligamentos") or 0) for row in items)
        value = round(departures / base * 100, 2) if base else None
        if value is None:
            continue
        out.append({
            "modalidade": modality,
            "curso": modality,
            "label": modality,
            "valor": value,
            "alunos_inicio": base,
            "desligamentos": departures,
            "meta": _goal_number(goal, "meta"),
            "status": _lower_is_better_status(value, goal),
            "temporario": any(bool(row.get("temporario")) for row in items),
        })
    order = {"Presencial": 0, "Semipresencial": 1, "EAD": 2}
    return sorted(out, key=lambda item: (order.get(str(item["modalidade"]), 9), str(item["modalidade"])))


def _cost_by_center(snapshot: dict[str, Any], period: str | None, modality: str | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, float] = {}
    for row in _rows(snapshot.get("custos", []), period, modality=modality):
        grouped[str(row["centro_custo"])] = grouped.get(str(row["centro_custo"]), 0.0) + float(row.get("despesa") or 0)
    return [
        {"centro_custo": center, "despesa": round(value, 2)}
        for center, value in sorted(grouped.items(), key=lambda item: item[1], reverse=True)
    ]


def build_dadm_dashboard(
    snapshot: dict[str, Any],
    referencia: str | None = None,
    comparacao: str | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    setor: str | None = None,
    course_id: int | None = None,
    modalidade: str | None = None,
    window_months: int | None = None,
) -> dict[str, Any]:
    """Build DADM using academic enrollment as the single population source.

    Filter semantics are deliberately explicit:
    - course and modality scope DADM-01 and the population trend;
    - modality and cost center scope DADM-09 because its expenses carry those cuts;
    - DADM-10 remains institutional because infrastructure expense has no course or
      modality allocation rule.
    """
    periods = _periods(snapshot)
    reference = referencia if referencia in periods else (periods[-1] if periods else None)
    comparison_requested = comparacao if comparacao in periods else None

    start = inicio if inicio in periods else (periods[0] if periods else None)
    end = fim if fim in periods else (reference or (periods[-1] if periods else None))
    if start and end and period_key(start) > period_key(end):
        start, end = end, start
    if window_months and reference in periods:
        ref_index = periods.index(reference)
        start_index = max(0, ref_index - max(1, int(window_months)) + 1)
        start = periods[start_index]
        end = reference

    available_courses = snapshot.get("cursos_academicos", [])
    selected_course = next((item for item in available_courses if int(item.get("id") or -1) == int(course_id or -1)), None)
    selected_course_id = int(selected_course["id"]) if selected_course else None

    available_modalities = sorted({
        str(row.get("modalidade") or "").strip()
        for key in ("alunos", "custos", "evasao")
        for row in snapshot.get(key, [])
        if str(row.get("modalidade") or "").strip()
    })
    selected_modality = modalidade if modalidade in available_modalities else None

    available_centers = sorted({
        str(row.get("centro_custo") or "").strip()
        for row in snapshot.get("custos", [])
        if str(row.get("centro_custo") or "").strip()
    })
    selected_center = setor if setor in available_centers else None

    attr_source = _filter_rows(snapshot.get("evasao", []), course_id=selected_course_id, modality=selected_modality)
    population_source = _filter_rows(snapshot.get("alunos", []), course_id=selected_course_id, modality=selected_modality)
    population_financial_source = _filter_rows(snapshot.get("alunos", []), modality=selected_modality)
    cost_source = _filter_rows(snapshot.get("custos", []), modality=selected_modality)
    if selected_center:
        cost_source = [row for row in cost_source if row.get("centro_custo") == selected_center]
    infra_source = _filter_rows(snapshot.get("infraestrutura", []))
    institutional_population = _filter_rows(snapshot.get("alunos", []))

    attr_period = _effective_period(attr_source, reference)
    pop_period = _effective_period(population_source, reference)
    cost_period = _effective_period(cost_source, reference)
    infra_period = _effective_period(infra_source, reference)

    attr_cmp_period = _comparison_period(attr_source, comparison_requested, attr_period)
    pop_cmp_period = _comparison_period(population_source, comparison_requested, pop_period)
    cost_cmp_period = _comparison_period(cost_source, comparison_requested, cost_period)
    infra_cmp_period = _comparison_period(infra_source, comparison_requested, infra_period)

    student_period_for_cost = _effective_period(population_financial_source, cost_period or reference)
    student_period_for_infra = _effective_period(institutional_population, infra_period or reference)

    attr_rows = _rows(snapshot.get("evasao", []), attr_period, course_id=selected_course_id, modality=selected_modality)
    attr_cmp_rows = _rows(snapshot.get("evasao", []), attr_cmp_period, course_id=selected_course_id, modality=selected_modality)
    attr_value = attrition_rate(attr_rows)
    attr_cmp = attrition_rate(attr_cmp_rows)
    attr_goal = _attrition_goal(snapshot, attr_period or reference, selected_course.get("curso") if selected_course else None)
    attr_meta = _goal_number(attr_goal, "meta")
    attr_attention = _goal_number(attr_goal, "atencao")

    pop_rows = _rows(snapshot.get("alunos", []), pop_period, course_id=selected_course_id, modality=selected_modality)
    pop_cmp_rows = _rows(snapshot.get("alunos", []), pop_cmp_period, course_id=selected_course_id, modality=selected_modality)
    pop_value = active_students(pop_rows)
    pop_cmp = active_students(pop_cmp_rows)

    cost_value = cost_per_student(
        _cost_rows(snapshot.get("custos", []), cost_period, selected_center, selected_modality),
        _rows(snapshot.get("alunos", []), student_period_for_cost, modality=selected_modality),
    )
    cost_cmp = cost_per_student(
        _cost_rows(snapshot.get("custos", []), cost_cmp_period, selected_center, selected_modality),
        _rows(snapshot.get("alunos", []), _effective_period(population_financial_source, cost_cmp_period), modality=selected_modality),
    )

    infra = infrastructure_metrics(
        _rows(snapshot.get("infraestrutura", []), infra_period),
        _rows(snapshot.get("alunos", []), student_period_for_infra),
    )
    infra_cmp = infrastructure_metrics(
        _rows(snapshot.get("infraestrutura", []), infra_cmp_period),
        _rows(snapshot.get("alunos", []), _effective_period(institutional_population, infra_cmp_period)),
    )

    attr_status = _lower_is_better_status(attr_value, attr_goal)
    population_variation = _pct_change(
        float(pop_value) if pop_value is not None else None,
        float(pop_cmp) if pop_cmp is not None else None,
    )
    cost_variation = _pct_change(cost_value, cost_cmp)
    infra_variation = _pct_change(infra.get("custo_m2"), infra_cmp.get("custo_m2"))

    # DADM-09 has an institutional target only for the consolidated KPI. A filter by
    # modality or cost center is useful for diagnosis, but comparing that partial
    # numerator with the TOTAL target would be mathematically misleading.
    cost_goal_applicable = not selected_center and not selected_modality
    cost_goal = _goal(snapshot, "DADM-09", cost_period or reference) if cost_goal_applicable else None
    infra_goal = _goal(snapshot, "DADM-10", infra_period or reference)
    cost_status = (
        _lower_is_better_status(cost_value, cost_goal)
        if cost_goal_applicable
        else ("Sem dados" if cost_value is None else "Recorte analítico")
    )
    infra_status = _lower_is_better_status(infra.get("custo_m2"), infra_goal)

    insights: list[dict[str, str]] = []
    if attr_value is not None:
        label = f" em {selected_course['curso']}" if selected_course else ""
        if attr_status == "Dentro da meta":
            insight_level, insight_title = "positivo", "Evasão dentro da meta"
        elif attr_status == "Atenção":
            insight_level, insight_title = "atenção", "Evasão em faixa de atenção"
        else:
            insight_level, insight_title = "atenção", "Evasão acima da meta"
        goal_piece = f" Meta vigente: até {_pt_number(attr_meta, 1)}%." if attr_meta is not None else ""
        insights.append({
            "nivel": insight_level,
            "titulo": insight_title,
            "texto": (f"{attr_value:.2f}%{label} em {attr_period}. A base ({sum(int(r.get('alunos_inicio') or 0) for r in attr_rows)} alunos) foi obtida automaticamente de Matrículas Ativas do mês anterior.{goal_piece}").replace(".", ",", 1),
        })
    else:
        insights.append({"nivel": "atenção", "titulo": "Evasão sem fechamento", "texto": "Faltam desligamentos ou Matrículas Ativas do mês anterior para calcular o DADM-01."})

    if pop_value is not None:
        temporary = any(bool(row.get("temporario")) for row in pop_rows)
        if population_variation is not None and population_variation <= -2:
            insights.append({
                "nivel": "atenção",
                "titulo": "Base de alunos em queda",
                "texto": f"A população ativa caiu {_pt_number(abs(population_variation))}% em relação a {pop_cmp_period}. A queda é descritiva e deve ser analisada junto de evasão e novos ingressos.",
            })
        if temporary:
            insights.append({
                "nivel": "informativo",
                "titulo": "Modalidade ainda usa base temporária",
                "texto": "EAD/Semipresencial permanecem demonstrativos enquanto a diretoria acadêmica responsável não publica Matrículas Ativas. Assim que houver fonte acadêmica, o fallback deixa de ser usado automaticamente.",
            })

    if cost_value is not None:
        variation = cost_variation
        pieces = []
        if selected_center:
            pieces.append(selected_center)
        if selected_modality:
            pieces.append(selected_modality)
        scope_text = f" ({' · '.join(pieces)})" if pieces else ""
        text = f"Custo administrativo{scope_text}: R$ {_pt_number(cost_value)}/aluno em {cost_period}."
        if variation is not None and cost_cmp_period:
            sign = "+" if variation >= 0 else ""
            text += f" Variação de {sign}{_pt_number(variation)}% contra {cost_cmp_period}."
        if cost_goal_applicable:
            target = _goal_number(cost_goal, "meta")
            if target is not None:
                text += f" Meta vigente: até R$ {_pt_number(target, 2)}/aluno."
            insight_level = "positivo" if cost_status == "Dentro da meta" else "atenção" if cost_status in {"Atenção", "Fora da meta"} else "informativo"
            insight_title = "Custo administrativo dentro da meta" if cost_status == "Dentro da meta" else "Custo administrativo fora da meta" if cost_status == "Fora da meta" else "Custo administrativo em atenção" if cost_status == "Atenção" else "Custo administrativo por aluno"
        else:
            insight_level = "informativo"
            insight_title = "Recorte analítico de custo"
            text += " A meta institucional do DADM-09 é avaliada somente no consolidado TOTAL; neste recorte ela é exibida apenas como referência de contexto."
        insights.append({"nivel": insight_level, "titulo": insight_title, "texto": text})
    else:
        insights.append({"nivel": "atenção", "titulo": "DADM-09 sem fechamento", "texto": "A competência selecionada precisa de despesas administrativas e população acadêmica ativa."})

    if selected_course:
        insights.append({
            "nivel": "informativo",
            "titulo": "Filtro de curso e custos administrativos",
            "texto": "O curso filtra evasão e população. O DADM-09 não é recalculado por curso porque ainda não existe uma regra institucional de rateio das despesas administrativas por curso.",
        })

    if infra["custo_m2"] is not None:
        text = f"Infraestrutura: R$ {_pt_number(infra['custo_m2'])}/m²"
        if infra["custo_aluno"] is not None:
            text += f" e R$ {_pt_number(infra['custo_aluno'])}/aluno"
        if infra_variation is not None and infra_cmp_period:
            sign = "+" if infra_variation >= 0 else ""
            text += f"; variação de {sign}{_pt_number(infra_variation)}% contra {infra_cmp_period}"
        infra_target = _goal_number(infra_goal, "meta")
        if infra_target is not None:
            text += f". Meta vigente: até R$ {_pt_number(infra_target, 2)}/m²"
        infra_level = "positivo" if infra_status == "Dentro da meta" else "atenção" if infra_status in {"Atenção", "Fora da meta"} else "informativo"
        infra_title = "Infraestrutura dentro da meta" if infra_status == "Dentro da meta" else "Infraestrutura fora da meta" if infra_status == "Fora da meta" else "Infraestrutura em atenção" if infra_status == "Atenção" else "Eficiência de infraestrutura"
        insights.append({"nivel": infra_level, "titulo": infra_title, "texto": text + "."})

    actions = snapshot.get("actions", [])
    overdue = sum(1 for action in actions if action.get("dias_prazo") is not None and action["dias_prazo"] < 0 and action.get("status") not in {"Concluído", "Cancelado"})
    open_actions = sum(1 for action in actions if action.get("status") not in {"Concluído", "Cancelado"})

    missing = {
        "evasao": 0 if attr_value is not None else 1,
        "custos": 0 if cost_value is not None else 1,
        "infraestrutura": 0 if infra["custo_m2"] is not None and infra["custo_aluno"] is not None else 1,
    }
    missing["total"] = sum(missing.values())

    return {
        "contexto": {
            "referencia": reference,
            "comparacao": comparison_requested,
            "inicio": start,
            "fim": end,
            "setor": selected_center,
            "curso_id": selected_course_id,
            "curso": selected_course.get("curso") if selected_course else None,
            "curso_label": selected_course.get("label") if selected_course else None,
            "modalidade": selected_modality,
            "evasao_periodo": attr_period,
            "populacao_periodo": pop_period,
            "custo_periodo": cost_period,
            "custo_populacao_periodo": student_period_for_cost,
            "infra_periodo": infra_period,
            "infra_populacao_periodo": student_period_for_infra,
        },
        "periodos": {"mensais": periods},
        "filtros": {
            "centros_custo": available_centers,
            "modalidades": available_modalities,
            "cursos": available_courses,
        },
        "cards": {
            "evasao": {
                "valor": attr_value,
                "periodo": attr_period,
                "alunos_inicio": sum(int(r.get("alunos_inicio") or 0) for r in attr_rows) if attr_rows else None,
                "desligamentos": sum(int(r.get("desligamentos") or 0) for r in attr_rows) if attr_rows else None,
                "comparacao": attr_cmp,
                "comparacao_periodo": attr_cmp_period,
                "variacao": None if attr_value is None or attr_cmp is None else round(attr_value - attr_cmp, 2),
                "status": attr_status,
                "meta": attr_meta,
                "atencao": attr_attention,
                "meta_vigencia": str(attr_goal.get("vigencia") or "") if attr_goal else "",
                "meta_texto": _attrition_goal_text(attr_goal),
            },
            "populacao": {
                "valor": pop_value,
                "periodo": pop_period,
                "comparacao": pop_cmp,
                "comparacao_periodo": pop_cmp_period,
                "variacao": population_variation,
                "temporario": any(bool(row.get("temporario")) for row in pop_rows),
            },
            "custo_administrativo": {
                "valor": cost_value,
                "periodo": cost_period,
                "populacao_periodo": student_period_for_cost,
                "comparacao": cost_cmp,
                "comparacao_periodo": cost_cmp_period,
                "variacao": cost_variation,
                "status": cost_status,
                "setor": selected_center,
                "modalidade": selected_modality,
                "curso_nao_rateado": bool(selected_course),
                "meta": _goal_number(cost_goal, "meta"),
                "atencao": _goal_number(cost_goal, "atencao"),
                "meta_vigencia": str(cost_goal.get("vigencia") or "") if cost_goal else "",
                "meta_texto": (_goal_text(cost_goal, "R$/aluno", lower=True) if cost_goal_applicable else "Meta consolidada não aplicada ao recorte atual."),
            },
            "infraestrutura": {
                **infra,
                "periodo": infra_period,
                "populacao_periodo": student_period_for_infra,
                "comparacao_custo_m2": infra_cmp.get("custo_m2"),
                "comparacao_periodo": infra_cmp_period,
                "variacao_custo_m2": infra_variation,
                "status": infra_status,
                "meta": _goal_number(infra_goal, "meta"),
                "atencao": _goal_number(infra_goal, "atencao"),
                "meta_vigencia": str(infra_goal.get("vigencia") or "") if infra_goal else "",
                "meta_texto": _goal_text(infra_goal, "R$/m²", lower=True),
            },
            "qualidade": missing,
            "planos": {"abertos": open_actions, "atrasados": overdue},
        },
        "series": {
            "populacao": _population_series(snapshot, course_id=selected_course_id, modality=selected_modality, start=start, end=end),
            "evasao": _attrition_series(
                snapshot, course_id=selected_course_id,
                course_name=selected_course.get("curso") if selected_course else None,
                modality=selected_modality, start=start, end=end,
            ),
            "custo_administrativo": _cost_series(
                snapshot, cost_center=selected_center, modality=selected_modality,
                start=start, end=end, include_goal=cost_goal_applicable,
            ),
            "infraestrutura": _infra_series(snapshot, start, end),
        },
        "comparacoes": {
            "evasao_por_curso": _attrition_by_course(snapshot, attr_period, course_id=selected_course_id, modality=selected_modality),
            "evasao_por_modalidade": _attrition_by_modality(snapshot, attr_period),
            "custos_por_centro": _cost_by_center(snapshot, cost_period, selected_modality),
        },
        "metas_vigentes": {
            "evasao": {
                "codigo": "DADM-01", "meta": attr_meta, "atencao": attr_attention, "unidade": "%",
                "recorte": str(attr_goal.get("recorte") or "TOTAL") if attr_goal else "TOTAL",
                "vigencia": str(attr_goal.get("vigencia") or "") if attr_goal else "",
                "texto": _attrition_goal_text(attr_goal),
            },
            "custo_administrativo": {
                "codigo": "DADM-09",
                "meta": _goal_number(cost_goal, "meta"),
                "atencao": _goal_number(cost_goal, "atencao"),
                "unidade": "R$/aluno",
                "recorte": selected_center or selected_modality or "TOTAL",
                "vigencia": str(cost_goal.get("vigencia") or "") if cost_goal else "",
                "texto": (_goal_text(cost_goal, "R$/aluno", lower=True) if cost_goal_applicable else "Meta TOTAL não aplicada ao recorte analítico selecionado."),
            },
            "infraestrutura": {
                "codigo": "DADM-10",
                "meta": _goal_number(infra_goal, "meta"),
                "atencao": _goal_number(infra_goal, "atencao"),
                "unidade": "R$/m²",
                "recorte": "TOTAL",
                "vigencia": str(infra_goal.get("vigencia") or "") if infra_goal else "",
                "texto": _goal_text(infra_goal, "R$/m²", lower=True),
            },
        },
        "insights": insights[:6],
    }
