from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


def period_key(period: str) -> int:
    """Sortable key for AAAA-MM or AAAA-SEM1/2.

    This generic ordering keeps the historical behavior of placing a semester at
    its closing month. Goal vigencies use ``period_start_key`` instead, because a
    semester goal must become effective in January/July, not only in June/December.
    """
    period = str(period or "").strip().upper()
    try:
        if "-SEM" in period:
            year = int(period[:4])
            semester = int(period[-1])
            month = 6 if semester == 1 else 12
            return year * 12 + month - 1
        year, month = period[:7].split("-")
        return int(year) * 12 + int(month) - 1
    except Exception:
        return -1


def period_start_key(period: str | None) -> int:
    """Return the first month covered by a monthly/semester period.

    Examples:
    - 2026-SEM1 -> Jan/2026
    - 2026-SEM2 -> Jul/2026
    - 2026-08   -> Aug/2026

    This is the canonical comparison for goal vigencies. A target defined as
    2026-SEM2 is therefore active from July through December.
    """
    text = str(period or "").strip().upper()
    try:
        if "-SEM" in text and text.endswith(("SEM1", "SEM2")):
            year = int(text[:4])
            month = 1 if text.endswith("SEM1") else 7
            return year * 12 + month - 1
        year, month = text[:7].split("-")
        month_int = int(month)
        if not 1 <= month_int <= 12:
            return -1
        return int(year) * 12 + month_int - 1
    except Exception:
        return -1


def month_to_semester(period: str | None) -> str | None:
    """Convert AAAA-MM to the semester that actually contains the selected month."""
    if not period:
        return None
    text = str(period).strip().upper()
    if "-SEM" in text:
        return text if text.endswith(("SEM1", "SEM2")) else None
    try:
        year, month = text[:7].split("-")
        month_int = int(month)
        if not 1 <= month_int <= 12:
            return None
        return f"{int(year):04d}-SEM{1 if month_int <= 6 else 2}"
    except Exception:
        return None


def semester_month(period: str) -> str:
    if "-SEM1" in str(period):
        return f"{str(period)[:4]}-06"
    if "-SEM2" in str(period):
        return f"{str(period)[:4]}-12"
    return str(period)[:7]


def period_overlaps_window(period: str, start: str, end: str) -> bool:
    """True when a monthly/semester period intersects the selected monthly window."""
    text = str(period or "")
    if "-SEM" not in text:
        return period_key(start) <= period_key(text) <= period_key(end)
    try:
        year = int(text[:4])
        semester = int(text[-1])
        first_month = 1 if semester == 1 else 7
        last_month = 6 if semester == 1 else 12
        sem_start = year * 12 + first_month - 1
        sem_end = year * 12 + last_month - 1
        return sem_start <= period_key(end) and sem_end >= period_key(start)
    except Exception:
        return False




def is_month_period(period: str | None) -> bool:
    text = str(period or "").strip()
    if len(text) != 7 or text[4] != "-":
        return False
    try:
        year = int(text[:4])
        month = int(text[5:7])
        return year >= 2000 and 1 <= month <= 12
    except Exception:
        return False

def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def aggregate_nps(rows: list[dict[str, Any]]) -> float | None:
    valid = [r for r in rows if r.get("validacao") == "OK"]
    respondents = sum(int(r.get("respondentes") or 0) for r in valid)
    if not respondents:
        return None
    promoters = sum(int(r.get("promotores") or 0) for r in valid)
    detractors = sum(int(r.get("detratores") or 0) for r in valid)
    return round((promoters - detractors) / respondents * 100, 1)


def aggregate_enrollments(rows: list[dict[str, Any]]) -> int | None:
    valid = [r for r in rows if r.get("validacao") == "OK"]
    if not valid:
        return None
    return sum(int(r.get("matriculas") or 0) for r in valid)


def aggregate_attendance(rows: list[dict[str, Any]]) -> float | None:
    valid = [r for r in rows if r.get("validacao") == "OK"]
    expected = sum(int(r.get("presencas_previstas") or 0) for r in valid)
    if not expected:
        return None
    actual = sum(int(r.get("presencas_registradas") or 0) for r in valid)
    return round(actual / expected * 100, 1)


def active_goal(
    metas: list[dict[str, Any]],
    indicator: str,
    period: str,
    course: str | None = None,
    discipline: str | None = None,
) -> dict[str, Any] | None:
    """Select the goal that is effective in the requested calendar period.

    Academic inheritance is hierarchical and persistent: a discipline-specific
    goal overrides the course goal, which overrides TOTAL, until another goal at
    the same level starts. Semester vigencies use the *first* month of the
    semester (Jan/Jul), so ``2026-SEM2`` is active from July 2026.
    """
    reference_key = period_start_key(period)
    if reference_key < 0:
        return None

    exact_discipline = f"{course} » {discipline}" if course and discipline else None
    allowed = {"TOTAL"}
    if course:
        allowed.add(course)
    if exact_discipline:
        allowed.add(exact_discipline)

    def specificity(recorte: str) -> int:
        if exact_discipline and recorte == exact_discipline:
            return 2
        if course and recorte == course:
            return 1
        return 0

    matches: list[dict[str, Any]] = []
    for goal in metas:
        if str(goal.get("indicador")) != indicator:
            continue
        recorte = str(goal.get("recorte") or "TOTAL")
        if recorte not in allowed:
            continue
        start_key = period_start_key(str(goal.get("vigencia") or ""))
        if 0 <= start_key <= reference_key:
            matches.append(goal)
    if not matches:
        return None
    matches.sort(
        key=lambda goal: (
            specificity(str(goal.get("recorte") or "TOTAL")),
            period_start_key(str(goal.get("vigencia") or "")),
        ),
        reverse=True,
    )
    return matches[0]


def goal_display_value(goal: dict[str, Any] | None, indicator: str, field: str = "meta") -> float | None:
    if not goal or goal.get(field) in (None, ""):
        return None
    value = float(goal[field])
    return round(value, 4)


def goal_info(
    goal: dict[str, Any] | None,
    indicator: str,
    course: str | None = None,
    discipline: str | None = None,
) -> dict[str, Any] | None:
    if not goal:
        return None
    recorte = str(goal.get("recorte") or "TOTAL")
    try:
        from schemas import KPI_META
        unit = KPI_META.get(indicator, {}).get("unit")
    except Exception:
        unit = None
    if not unit:
        unit = "%" if indicator.endswith(("-02", "-03")) else "pontos"
    return {
        "meta": goal_display_value(goal, indicator, "meta"),
        "atencao": goal_display_value(goal, indicator, "atencao"),
        "limite_superior": goal_display_value(goal, indicator, "limite_superior"),
        "vigencia": str(goal.get("vigencia") or ""),
        "recorte": recorte,
        "origem": (
            "Meta específica da disciplina"
            if course and discipline and recorte == f"{course} » {discipline}"
            else "Meta específica do curso"
            if course and recorte == course
            else "Meta geral da diretoria"
        ),
        "justificativa": str(goal.get("justificativa") or ""),
        "unidade": unit,
    }


def status_for(value: float | None, goal: dict[str, Any] | None, indicator: str) -> str:
    if value is None:
        return "Sem dados"
    if not goal or goal.get("meta") in (None, ""):
        return "Sem meta"
    meta = float(goal["meta"])
    attention = float(goal.get("atencao")) if goal.get("atencao") not in (None, "") else meta
    normalized = value
    if normalized >= meta:
        return "Dentro da meta"
    if normalized >= attention:
        return "Atenção"
    return "Fora da meta"


def _filter(rows: list[dict[str, Any]], course: str | None = None, period: str | None = None) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if (not course or course == "(todos)" or row.get("curso") == course)
        and (not period or row.get("periodo") == period)
    ]


def _valid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("validacao") == "OK"]


def _available_months(rows: list[dict[str, Any]], course: str | None = None) -> list[str]:
    """Return monthly competencies that actually contain valid rows for the scope."""
    periods = {
        str(row.get("periodo") or "").strip()
        for row in _filter(rows, course=course)
        if row.get("validacao") == "OK" and is_month_period(row.get("periodo"))
    }
    return sorted(periods, key=period_key)


def _effective_month(rows: list[dict[str, Any]], requested: str | None, course: str | None = None) -> str | None:
    """Use the requested month when available; otherwise use the latest prior available month.

    This prevents the executive card from becoming blank merely because another KPI has
    a newer competency. The actual month used is returned to the frontend explicitly.
    """
    periods = _available_months(rows, course)
    if not periods:
        return None
    if requested and requested in periods:
        return requested
    if requested and is_month_period(requested):
        eligible = [period for period in periods if period_key(period) <= period_key(requested)]
        if eligible:
            return eligible[-1]
    return periods[-1]


def _comparison_month(rows: list[dict[str, Any]], requested: str | None, reference: str | None, course: str | None = None) -> str | None:
    """Resolve a valid comparison month strictly before the effective reference month."""
    if not reference:
        return None
    periods = [period for period in _available_months(rows, course) if period_key(period) < period_key(reference)]
    if not periods:
        return None
    if requested and requested in periods:
        return requested
    if requested and is_month_period(requested):
        eligible = [period for period in periods if period_key(period) <= period_key(requested)]
        if eligible:
            return eligible[-1]
    return periods[-1]


def _nps_details(rows: list[dict[str, Any]]) -> dict[str, int]:
    rows = _valid(rows)
    return {
        "respondentes": sum(int(r.get("respondentes") or 0) for r in rows),
        "promotores": sum(int(r.get("promotores") or 0) for r in rows),
        "neutros": sum(int(r.get("neutros") or 0) for r in rows),
        "detratores": sum(int(r.get("detratores") or 0) for r in rows),
    }


def _attendance_details(rows: list[dict[str, Any]]) -> dict[str, int]:
    rows = _valid(rows)
    return {
        "presencas_previstas": sum(int(r.get("presencas_previstas") or 0) for r in rows),
        "presencas_registradas": sum(int(r.get("presencas_registradas") or 0) for r in rows),
        "disciplinas": len(rows),
    }


def _series_for_indicator(snapshot: dict[str, Any], indicator: str, course: str | None = None) -> list[dict[str, Any]]:
    suffix = str(indicator).rsplit("-", 1)[-1]
    spec: dict[str, tuple[str, Callable[[list[dict[str, Any]]], Any]]] = {
        "01": ("nps", aggregate_nps),
        "02": ("matriculas", aggregate_enrollments),
        "03": ("frequencia", aggregate_attendance),
    }
    if suffix not in spec:
        raise KeyError(f"Indicador acadêmico não suportado: {indicator}")
    dataset, aggregate = spec[suffix]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _filter(snapshot[dataset], course=course):
        period = str(row.get("periodo") or "")
        # A partir da v0.1.6 todos os três KPIs operacionais usam competência mensal.
        # Registros semestrais antigos permanecem no banco para auditoria, mas não
        # entram nas séries executivas até serem substituídos por dados mensais.
        if not is_month_period(period):
            continue
        grouped[period].append(row)

    periods = sorted(grouped, key=period_key)
    result: list[dict[str, Any]] = []
    previous_value: float | None = None
    for period in periods:
        rows = grouped[period]
        value = aggregate(rows)
        goal = active_goal(snapshot["metas"], indicator, period, course)
        info = goal_info(goal, indicator, course)
        point: dict[str, Any] = {
            "periodo": period,
            "valor": value,
            "meta": info.get("meta") if info else None,
            "meta_vigencia": info.get("vigencia") if info else None,
            "meta_recorte": info.get("recorte") if info else None,
            "meta_origem": info.get("origem") if info else None,
        }
        if indicator.endswith("-01"):
            point.update(_nps_details(rows))
            point["status"] = status_for(value, goal, indicator)
        elif indicator.endswith("-02"):
            variation = pct_change(value, previous_value)
            point["variacao"] = round(variation, 1) if variation is not None else None
            point["valor_anterior"] = previous_value
            point["status"] = status_for(variation, goal, indicator)
            previous_value = float(value) if value is not None else previous_value
        else:
            point.update(_attendance_details(rows))
            point["status"] = status_for(value, goal, indicator)
        result.append(point)
    return result


def _comparison_by_course(
    snapshot: dict[str, Any],
    indicator: str,
    period: str,
    comparison_period: str | None = None,
    goal_period: str | None = None,
) -> list[dict[str, Any]]:
    suffix = str(indicator).rsplit("-", 1)[-1]
    spec = {
        "01": ("nps", aggregate_nps),
        "02": ("matriculas", aggregate_enrollments),
        "03": ("frequencia", aggregate_attendance),
    }[suffix]
    rows = snapshot[spec[0]]
    result: list[dict[str, Any]] = []
    for course in snapshot["courses"]:
        current_rows = _filter(rows, course=course, period=period)
        value = spec[1](current_rows)
        goal = active_goal(snapshot["metas"], indicator, goal_period or period, course)
        info = goal_info(goal, indicator, course)
        comparison_value = None
        variation = None
        status_value = value
        if comparison_period:
            comparison_value = spec[1](_filter(rows, course=course, period=comparison_period))
            if indicator.endswith("-02"):
                variation = pct_change(value, comparison_value)
                variation = round(variation, 1) if variation is not None else None
                status_value = variation
            elif indicator.endswith(("-01", "-03")) and value is not None and comparison_value is not None:
                variation = round(float(value) - float(comparison_value), 1)
        item: dict[str, Any] = {
            "curso": course,
            "valor": value,
            "comparacao": comparison_value,
            "variacao": variation,
            "status": status_for(status_value, goal, indicator),
            "meta": info.get("meta") if info else None,
            "meta_vigencia": info.get("vigencia") if info else None,
            "meta_recorte": info.get("recorte") if info else None,
            "meta_origem": info.get("origem") if info else None,
        }
        if indicator.endswith("-01"):
            item.update(_nps_details(current_rows))
        elif indicator.endswith("-03"):
            item.update(_attendance_details(current_rows))
        result.append(item)
    return result


def _trend_label(series: list[dict[str, Any]]) -> str | None:
    values = [float(point["valor"]) for point in series if point.get("valor") is not None]
    if len(values) < 3:
        return None
    last = values[-3:]
    if last[0] < last[1] < last[2]:
        return "crescimento em três períodos consecutivos"
    if last[0] > last[1] > last[2]:
        return "queda em três períodos consecutivos"
    spread = max(last) - min(last)
    base = abs(sum(last) / len(last)) or 1
    if spread / base < 0.03:
        return "estabilidade nos três últimos períodos"
    return None


def build_dashboard(
    snapshot: dict[str, Any],
    course: str | None = None,
    reference: str | None = None,
    comparison: str | None = None,
    start: str | None = None,
    end: str | None = None,
    window_months: int | None = None,
    directorate_code: str = "DTNH",
) -> dict[str, Any]:
    """Build the executive dashboard using one monthly grain for all three KPIs.

    DTNH-03 changed from the prototype's semester input to the institutional monthly
    cadence. Legacy semester records are intentionally ignored by the executive view
    because there is no defensible way to split one semester aggregate into months.
    """
    course = None if course in (None, "", "(todos)") else course
    directorate_code = str(directorate_code or "DTNH").upper()
    code_nps = f"{directorate_code}-01"
    code_mat = f"{directorate_code}-02"
    code_freq = f"{directorate_code}-03"

    nps_periods = sorted({str(r["periodo"]) for r in snapshot["nps"] if is_month_period(r.get("periodo"))}, key=period_key)
    enrollment_periods = sorted({str(r["periodo"]) for r in snapshot["matriculas"] if is_month_period(r.get("periodo"))}, key=period_key)
    attendance_periods = sorted({str(r["periodo"]) for r in snapshot["frequencia"] if is_month_period(r.get("periodo"))}, key=period_key)
    monthly_periods = sorted(set(nps_periods + enrollment_periods + attendance_periods), key=period_key)

    reference = reference if reference in monthly_periods else (monthly_periods[-1] if monthly_periods else None)
    # Comparison must always be earlier than the selected reference. This matters when
    # the user navigates back in history: keeping a previously selected future month
    # would create an inverted and misleading variation.
    earlier_periods = [p for p in monthly_periods if reference and period_key(p) < period_key(reference)]
    if comparison not in monthly_periods or (reference and comparison and period_key(comparison) >= period_key(reference)):
        comparison = earlier_periods[-1] if earlier_periods else None
    start = start if start in monthly_periods else (monthly_periods[0] if monthly_periods else None)
    end = end if end in monthly_periods else (monthly_periods[-1] if monthly_periods else None)
    if start and end and period_key(start) > period_key(end):
        start, end = end, start
    if window_months and reference in monthly_periods:
        ref_index = monthly_periods.index(reference)
        start_index = max(0, ref_index - max(1, int(window_months)) + 1)
        start = monthly_periods[start_index]
        end = reference

    nps_ref = aggregate_nps(_filter(snapshot["nps"], course, reference)) if reference else None
    nps_cmp = aggregate_nps(_filter(snapshot["nps"], course, comparison)) if comparison else None
    mat_ref = aggregate_enrollments(_filter(snapshot["matriculas"], course, reference)) if reference else None
    mat_cmp = aggregate_enrollments(_filter(snapshot["matriculas"], course, comparison)) if comparison else None
    # Frequency may legitimately close on a different monthly competency from NPS or
    # enrollments. If the global reference month has no attendance rows, use the most
    # recent valid attendance month at or before that reference and disclose it in the
    # response instead of rendering the KPI as blank.
    freq_reference = _effective_month(snapshot["frequencia"], reference, course)
    freq_comparison = _comparison_month(snapshot["frequencia"], comparison, freq_reference, course)
    freq_ref = aggregate_attendance(_filter(snapshot["frequencia"], course, freq_reference)) if freq_reference else None
    freq_cmp = aggregate_attendance(_filter(snapshot["frequencia"], course, freq_comparison)) if freq_comparison else None

    goal_nps = active_goal(snapshot["metas"], code_nps, reference or "", course)
    goal_mat = active_goal(snapshot["metas"], code_mat, reference or "", course)
    goal_freq = active_goal(snapshot["metas"], code_freq, freq_reference or reference or "", course)
    info_nps = goal_info(goal_nps, code_nps, course)
    info_mat = goal_info(goal_mat, code_mat, course)
    info_freq = goal_info(goal_freq, code_freq, course)

    mat_variation = pct_change(mat_ref, mat_cmp)
    freq_variation = None
    if freq_ref is not None and freq_cmp is not None:
        freq_variation = round(float(freq_ref) - float(freq_cmp), 1)

    series_nps = _series_for_indicator(snapshot, code_nps, course)
    series_mat = _series_for_indicator(snapshot, code_mat, course)
    series_freq = _series_for_indicator(snapshot, code_freq, course)
    if start and end:
        low, high = period_key(start), period_key(end)
        series_nps = [point for point in series_nps if low <= period_key(point["periodo"]) <= high]
        series_mat = [point for point in series_mat if low <= period_key(point["periodo"]) <= high]
        series_freq = [point for point in series_freq if low <= period_key(point["periodo"]) <= high]

    quality = {
        "nps": sum(1 for row in snapshot["nps"] if row.get("validacao") != "OK"),
        "matriculas": sum(1 for row in snapshot["matriculas"] if row.get("validacao") != "OK"),
        "frequencia": sum(1 for row in snapshot["frequencia"] if row.get("validacao") != "OK"),
    }
    quality["total"] = sum(quality.values())

    by_course_nps = _comparison_by_course(snapshot, code_nps, reference, comparison) if reference else []
    by_course_mat = _comparison_by_course(snapshot, code_mat, reference, comparison) if reference else []
    by_course_freq = _comparison_by_course(snapshot, code_freq, freq_reference, freq_comparison, goal_period=freq_reference) if freq_reference else []

    insights: list[dict[str, str]] = []
    if quality["total"]:
        insights.append({
            "nivel": "crítico",
            "titulo": "Há inconsistências de dados",
            "texto": f"Foram identificadas {quality['total']} linhas com erro. Corrija-as antes de usar os KPIs em reunião.",
        })
    else:
        insights.append({
            "nivel": "positivo",
            "titulo": "Bases validadas",
            "texto": "Os registros atualmente preenchidos passaram pelas validações estruturais.",
        })

    if reference:
        if freq_ref is None:
            insights.append({
                "nivel": "atenção",
                "titulo": f"KPI de frequência sem dados até {reference}",
                "texto": "A frequência é apurada mensalmente. Lance presenças previstas e registradas por curso e disciplina para disponibilizar a média ponderada no painel executivo.",
            })
        else:
            if freq_reference != reference:
                insights.append({
                    "nivel": "informativo",
                    "titulo": "Frequência exibida pelo último fechamento disponível",
                    "texto": f"A referência geral do painel é {reference}, mas o último mês com frequência válida é {freq_reference}. O card e o gráfico mantêm esse fechamento visível para não ocultar o KPI.",
                })
            if freq_comparison and freq_cmp is not None:
                signal = "+" if (freq_variation or 0) >= 0 else ""
                insights.append({
                    "nivel": "informativo",
                    "titulo": "Variação mensal de frequência",
                    "texto": f"{freq_comparison}: {freq_cmp}% e {freq_reference}: {freq_ref}%. Variação de {signal}{freq_variation} p.p.",
                })

    for title, series in (("NPS", series_nps), ("Matrículas", series_mat), ("Frequência", series_freq)):
        trend = _trend_label(series)
        if trend:
            insights.append({
                "nivel": "atenção" if "queda" in trend else "informativo",
                "titulo": f"Tendência do KPI {title}",
                "texto": f"A série apresenta {trend}.",
            })

    for title, data, suffix in (
        ("NPS", by_course_nps, " pontos"),
        ("matrículas", by_course_mat, ""),
        ("frequência", by_course_freq, "%"),
    ):
        valid = [item for item in data if item.get("valor") is not None]
        if valid:
            best = max(valid, key=lambda item: item["valor"])
            worst = min(valid, key=lambda item: item["valor"])
            insights.append({
                "nivel": "informativo",
                "titulo": f"Dispersão do KPI {title} entre cursos",
                "texto": f"Melhor resultado: {best['curso']} ({best['valor']}{suffix}). Menor resultado: {worst['curso']} ({worst['valor']}{suffix}).",
            })

    courses_with_nps = {r["curso"] for r in _filter(snapshot["nps"], period=reference)} if reference else set()
    missing_nps = [c for c in snapshot["courses"] if c not in courses_with_nps]
    if missing_nps:
        insights.append({
            "nivel": "atenção",
            "titulo": "Cobertura incompleta do KPI NPS",
            "texto": f"Sem lançamento no período de referência: {', '.join(missing_nps)}.",
        })

    try:
        actions = snapshot.get("actions", [])
        overdue = sum(
            1
            for action in actions
            if action.get("dias_prazo") is not None
            and action["dias_prazo"] < 0
            and action.get("status") not in {"Concluído", "Cancelado"}
        )
        open_actions = sum(1 for action in actions if action.get("status") not in {"Concluído", "Cancelado"})
    except Exception:
        overdue, open_actions = 0, 0

    legacy_attendance = sum(1 for row in snapshot["frequencia"] if row.get("periodo") and not is_month_period(row.get("periodo")))
    if legacy_attendance:
        insights.append({
            "nivel": "atenção",
            "titulo": "Registros semestrais legados preservados",
            "texto": f"Há {legacy_attendance} registro(s) antigos de frequência com competência semestral. Eles foram preservados para auditoria, mas não entram nos KPIs mensais.",
        })

    nps_status = status_for(nps_ref, goal_nps, code_nps)
    mat_status = status_for(mat_variation, goal_mat, code_mat) if comparison else "Sem comparação"
    freq_status = status_for(freq_ref, goal_freq, code_freq)

    return {
        "contexto": {
            "diretoria": directorate_code,
            "curso": course or "(todos)",
            "referencia": reference,
            "comparacao": comparison,
            "inicio": start,
            "fim": end,
            "frequencia_periodo": freq_reference,
            "frequencia_comparacao_periodo": freq_comparison,
            "frequencia_usou_fallback": bool(reference and freq_reference and freq_reference != reference),
            "frequencia_mensal": True,
        },
        "periodos": {"mensais": monthly_periods},
        "cards": {
            "nps": {
                "valor": nps_ref,
                "comparacao": nps_cmp,
                "variacao": None if nps_ref is None or nps_cmp is None else round(nps_ref - nps_cmp, 1),
                "status": nps_status,
                "meta": info_nps.get("meta") if info_nps else None,
                "meta_info": info_nps,
            },
            "matriculas": {
                "valor": mat_ref,
                "comparacao": mat_cmp,
                "variacao": round(mat_variation, 1) if mat_variation is not None else None,
                "status": mat_status,
                "meta": info_mat.get("meta") if info_mat else None,
                "meta_info": info_mat,
            },
            "frequencia": {
                "valor": freq_ref,
                "periodo": freq_reference,
                "comparacao": freq_cmp,
                "comparacao_periodo": freq_comparison,
                "variacao": freq_variation,
                "status": freq_status,
                "meta": info_freq.get("meta") if info_freq else None,
                "meta_info": info_freq,
            },
            "qualidade": quality,
            "planos": {"abertos": open_actions, "atrasados": overdue},
        },
        "metas_vigentes": {
            "nps": info_nps,
            "matriculas": info_mat,
            "frequencia": info_freq,
        },
        "series": {"nps": series_nps, "matriculas": series_mat, "frequencia": series_freq},
        "comparacoes": {"nps": by_course_nps, "matriculas": by_course_mat, "frequencia": by_course_freq},
        "insights": insights[:9],
    }

