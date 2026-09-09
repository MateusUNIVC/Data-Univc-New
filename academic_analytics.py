from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from analytics import active_goal, goal_info, status_for


def to_semester(period: str | None) -> str | None:
    text = str(period or "").strip().upper()
    if not text:
        return None
    if "-SEM" in text and text[-1:] in {"1", "2"}:
        return f"{text[:4]}-SEM{text[-1]}"
    if len(text) >= 6:
        try:
            year = int(text[:4])
            if text[4] in {"-", "/"}:
                tail = text[5:]
                if tail in {"1", "2"}:
                    return f"{year:04d}-SEM{tail}"
                month = int(tail[:2])
                if 1 <= month <= 12:
                    return f"{year:04d}-SEM{1 if month <= 6 else 2}"
        except Exception:
            pass
    return None


def is_month_period(period: str | None) -> bool:
    text = str(period or "").strip()
    if len(text) != 7 or text[4] != "-":
        return False
    try:
        month = int(text[5:7])
        return text[:4].isdigit() and 1 <= month <= 12
    except Exception:
        return False


def is_semester_period(period: str | None) -> bool:
    text = str(period or "").strip().upper()
    return len(text) == 9 and text[4:8] == "-SEM" and text[-1] in {"1", "2"} and text[:4].isdigit()


def semester_months(semester: str | None) -> list[str]:
    sem = to_semester(semester)
    if not sem:
        return []
    year = int(sem[:4])
    first = 1 if sem.endswith("1") else 7
    return [f"{year:04d}-{month:02d}" for month in range(first, first + 6)]


def month_sort_key(period: str) -> tuple[int, int]:
    text = str(period or "")
    try:
        return int(text[:4]), int(text[5:7])
    except Exception:
        return 0, 0


def semester_sort_key(period: str) -> tuple[int, int]:
    text = to_semester(period) or "0000-SEM0"
    try:
        return int(text[:4]), int(text[-1])
    except Exception:
        return 0, 0


def _normalize_granularity(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    if text in {"mensal", "mes", "mês", "month", "monthly"}:
        return "mensal"
    return "semestral"


def _normalize_period(period: str | None, granularity: str) -> str | None:
    if not period:
        return None
    if granularity == "semestral":
        return to_semester(period)
    text = str(period).strip()
    if is_month_period(text):
        return text
    if is_semester_period(text):
        months = semester_months(text)
        return months[-1] if months else None
    sem = to_semester(text)
    if sem:
        months = semester_months(sem)
        return months[-1] if months else None
    return None


def _course_filter(rows: list[dict[str, Any]], course: str | None) -> list[dict[str, Any]]:
    if not course or course == "(todos)":
        return rows
    return [row for row in rows if str(row.get("curso") or "") == course]


def _discipline_filter(rows: list[dict[str, Any]], discipline: str | None) -> list[dict[str, Any]]:
    if not discipline or discipline == "(todas)":
        return rows
    return [row for row in rows if str(row.get("disciplina") or "") == discipline]


def _semester_rows(
    rows: list[dict[str, Any]],
    period: str | None,
    course: str | None = None,
    discipline: str | None = None,
) -> list[dict[str, Any]]:
    rows = _course_filter(rows, course)
    rows = _discipline_filter(rows, discipline)
    semester = to_semester(period)
    if not semester:
        return rows
    return [row for row in rows if to_semester(row.get("periodo")) == semester]


def summarize_nps_semesters(
    rows: list[dict[str, Any]],
    course: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize NPS into one official row per semester and course.

    The institutional source of truth is the explicit semester closing. Monthly
    records are retained for audit, but are aggregated only as a fallback when a
    course has no explicit closing for that semester. This prevents double
    counting and guarantees that dashboard, historical comparison and Excel use
    the same rule.
    """
    base = _course_filter(rows, course)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in base:
        if row.get("validacao") not in (None, "", "OK"):
            continue
        semester = to_semester(row.get("periodo"))
        course_name = str(row.get("curso") or "").strip()
        if semester and course_name:
            grouped[(semester, course_name)].append(row)

    out: list[dict[str, Any]] = []
    for (semester, course_name), course_rows in grouped.items():
        explicit = [row for row in course_rows if is_semester_period(row.get("periodo"))]
        monthly = [row for row in course_rows if is_month_period(row.get("periodo"))]
        selected = explicit if explicit else monthly
        if not selected:
            continue
        respondents = sum(int(row.get("respondentes") or 0) for row in selected)
        promoters = sum(int(row.get("promotores") or 0) for row in selected)
        neutrals = sum(int(row.get("neutros") or 0) for row in selected)
        detractors = sum(int(row.get("detratores") or 0) for row in selected)
        value = round((promoters - detractors) / respondents * 100, 2) if respondents > 0 else None
        launch_dates = [row.get("data_lancamento") for row in selected if row.get("data_lancamento")]
        source_types = {str(row.get("source_type") or "").strip() for row in selected if row.get("source_type")}
        if explicit and source_types == {"SEI_SURVEY"}:
            nps_source = "SEI · questionário oficial"
        elif explicit:
            nps_source = "Fechamento semestral"
        else:
            nps_source = "Agregado mensal (fallback)"
        out.append({
            "periodo": semester,
            "curso": course_name,
            "respondentes": respondents,
            "promotores": promoters,
            "neutros": neutrals,
            "detratores": detractors,
            "nps": value,
            "fonte_nps": nps_source,
            "linhas_fonte": len(selected),
            "data_lancamento": max(launch_dates) if launch_dates else None,
            "validacao": "OK" if respondents >= 0 and promoters + neutrals + detractors == respondents else "ERRO",
        })
    return sorted(out, key=lambda row: (semester_sort_key(str(row["periodo"])), str(row["curso"]).casefold()))


def _nps_period_rows(
    rows: list[dict[str, Any]],
    period: str | None,
    course: str | None,
    granularity: str,
) -> list[dict[str, Any]]:
    """Return the official semester NPS rows for a requested period.

    NPS is semester-native in v0.6.0. A monthly dashboard repeats the official
    semester closing across its six months. If a course lacks an explicit
    closing, its monthly records are aggregated once for that semester.
    """
    semester = to_semester(period)
    if not semester:
        return []
    return [
        row for row in summarize_nps_semesters(rows, course)
        if row.get("periodo") == semester
    ]


def aggregate_nps_details(rows: list[dict[str, Any]]) -> dict[str, Any]:
    respondents = sum(int(row.get("respondentes") or 0) for row in rows)
    promoters = sum(int(row.get("promotores") or 0) for row in rows)
    neutrals = sum(int(row.get("neutros") or 0) for row in rows)
    detractors = sum(int(row.get("detratores") or 0) for row in rows)
    sources = {str(row.get("fonte_nps") or "").strip() for row in rows if row.get("fonte_nps")}
    if not sources:
        source = None
    elif len(sources) == 1:
        source = next(iter(sources))
    else:
        source = "Misto: semestral + fallback mensal"
    return {
        "valor": round((promoters - detractors) / respondents * 100, 2) if respondents > 0 else None,
        "respondentes": respondents,
        "promotores": promoters,
        "neutros": neutrals,
        "detratores": detractors,
        "fonte": source,
        "cursos": len({str(row.get("curso") or "") for row in rows if row.get("curso")}),
    }


def _current_calendar_periods() -> tuple[str, str]:
    """Return current month/semester in the UNIVC local timezone."""
    try:
        now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        now = datetime.now()
    month = f"{now.year:04d}-{now.month:02d}"
    semester = f"{now.year:04d}-SEM{1 if now.month <= 6 else 2}"
    return month, semester


def _month_index(period: str) -> int:
    year, month = month_sort_key(period)
    return year * 12 + month - 1 if year and month else -1


def _month_from_index(index: int) -> str:
    year, zero_month = divmod(index, 12)
    return f"{year:04d}-{zero_month + 1:02d}"


def _semester_index(period: str) -> int:
    year, semester = semester_sort_key(period)
    return year * 2 + semester - 1 if year and semester else -1


def _semester_from_index(index: int) -> str:
    year, zero_semester = divmod(index, 2)
    return f"{year:04d}-SEM{zero_semester + 1}"


def _continuous(values: set[str], granularity: str) -> list[str]:
    if not values:
        return []
    if granularity == "mensal":
        indexes = sorted(i for i in (_month_index(v) for v in values) if i >= 0)
        return [_month_from_index(i) for i in range(indexes[0], indexes[-1] + 1)] if indexes else []
    indexes = sorted(i for i in (_semester_index(v) for v in values) if i >= 0)
    return [_semester_from_index(i) for i in range(indexes[0], indexes[-1] + 1)] if indexes else []


def _available_periods(
    snapshot: dict[str, Any],
    *,
    reference: str | None = None,
    comparison: str | None = None,
) -> tuple[list[str], list[str]]:
    """Build a continuous calendar domain for charts and selectors.

    Data periods alone are not enough: if a semester has a current goal but no
    result yet, the goal still has to appear on the chart. We therefore include
    the current UNIVC calendar period, historical goal vigencies and explicit
    reference/comparison requests, then fill the gaps between periods.

    Future goals do not extend the default chart into future years; they become
    visible when the user explicitly selects a future reference.
    """
    semesters: set[str] = set()
    months: set[str] = set()

    for key in ("nps", "nps_institution"):
        for row in snapshot.get(key, []):
            raw = str(row.get("periodo") or "").strip().upper()
            sem = to_semester(raw)
            if sem:
                semesters.add(sem)
            if is_month_period(raw):
                months.add(raw)
            elif is_semester_period(raw):
                months.update(semester_months(raw))

    # Teacher evaluation and academic results are semester-native in Data UNIVC.
    for key in ("avaliacao_docente", "resultados"):
        for row in snapshot.get(key, []):
            sem = to_semester(row.get("periodo"))
            if sem:
                semesters.add(sem)
                months.update(semester_months(sem))

    current_month, current_semester = _current_calendar_periods()
    months.add(current_month)
    semesters.add(current_semester)

    # Historical/current goals help define the calendar even before the first
    # result of a new semester is imported. Future goals stay out of the default
    # domain to avoid stretching the chart beyond today.
    current_month_idx = _month_index(current_month)
    for goal in snapshot.get("metas", []):
        vig = str(goal.get("vigencia") or "").strip().upper()
        sem = to_semester(vig)
        if not sem:
            continue
        start_month = semester_months(sem)[0]
        if is_month_period(vig):
            start_month = vig
        if _month_index(start_month) <= current_month_idx:
            semesters.add(sem)
            months.add(start_month)

    # Explicit requests must remain selectable even if they are outside the
    # current data range (for example, reviewing an older or planned period).
    for raw in (reference, comparison):
        raw = str(raw or "").strip().upper()
        if not raw:
            continue
        sem = to_semester(raw)
        if sem:
            semesters.add(sem)
        if is_month_period(raw):
            months.add(raw)
        elif is_semester_period(raw):
            months.update(semester_months(raw))

    # Guarantee that every historical semester represented in one domain is
    # represented in the other. For the current semester we stop at the current
    # month, so an August dashboard does not fabricate September-December as
    # already elapsed months. An explicit future month may extend this cap.
    for sem in list(semesters):
        months.update(semester_months(sem))
    for month in list(months):
        sem = to_semester(month)
        if sem:
            semesters.add(sem)

    month_cap = current_month_idx
    for raw in (reference, comparison):
        text = str(raw or "").strip().upper()
        if is_month_period(text):
            month_cap = max(month_cap, _month_index(text))
    months = {month for month in months if 0 <= _month_index(month) <= month_cap}

    return _continuous(semesters, "semestral"), _continuous(months, "mensal")


def aggregate_nps(rows: list[dict[str, Any]]) -> float | None:
    respondents = sum(int(r.get("respondentes") or 0) for r in rows)
    if respondents <= 0:
        return None
    promoters = sum(int(r.get("promotores") or 0) for r in rows)
    detractors = sum(int(r.get("detratores") or 0) for r in rows)
    return round((promoters - detractors) / respondents * 100, 2)


def aggregate_teacher_evaluation(rows: list[dict[str, Any]]) -> float | None:
    valid = [r for r in rows if r.get("nota_media") is not None]
    if not valid:
        return None
    total_resp = sum(int(r.get("respondentes") or 0) for r in valid)
    if total_resp > 0:
        return round(sum(float(r["nota_media"]) * int(r.get("respondentes") or 0) for r in valid) / total_resp, 2)
    return round(sum(float(r["nota_media"]) for r in valid) / len(valid), 2)


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    aggregated = [r for r in rows if r.get("agregado") is True]
    if aggregated and len(aggregated) == len(rows):
        finalized = sum(int(r.get("finalizados") or 0) for r in aggregated)
        approved = sum(int(r.get("aprovados") or 0) for r in aggregated)
        by_reason = {
            "nota": sum(int(r.get("reprovados_nota") or 0) for r in aggregated),
            "falta": sum(int(r.get("reprovados_falta") or 0) for r in aggregated),
            "outro": sum(int(r.get("reprovados_outro") or 0) for r in aggregated),
        }
        failed = sum(by_reason.values())
        grade_count = sum(int(r.get("notas_contagem") or 0) for r in aggregated)
        grade_sum = sum(
            float(r.get("soma_notas") or (float(r.get("media_notas") or 0) * int(r.get("notas_contagem") or 0)))
            for r in aggregated
        )
        avg_grade = round(grade_sum / grade_count, 2) if grade_count else None
        rate = round(approved / finalized * 100, 2) if finalized else None
        return {
            "taxa_aprovacao": rate,
            "media_notas": avg_grade,
            "finalizados": finalized,
            "aprovados": approved,
            "reprovados": failed,
            "reprovacoes": by_reason,
            "em_andamento": sum(int(r.get("em_andamento") or 0) for r in aggregated),
            "total_registros": sum(int(r.get("total_registros") or 0) for r in aggregated),
        }

    finalized_rows = [r for r in rows if r.get("aprovado") is not None]
    approved = sum(1 for r in finalized_rows if r.get("aprovado") is True)
    failed = sum(1 for r in finalized_rows if r.get("aprovado") is False)
    rate = round(approved / len(finalized_rows) * 100, 2) if finalized_rows else None
    grades = [float(r["media"]) for r in rows if r.get("media") is not None]
    avg_grade = round(sum(grades) / len(grades), 2) if grades else None
    by_reason = {
        "nota": sum(1 for r in finalized_rows if r.get("motivo_reprovacao") == "nota"),
        "falta": sum(1 for r in finalized_rows if r.get("motivo_reprovacao") == "falta"),
        "outro": sum(
            1 for r in finalized_rows
            if r.get("aprovado") is False and r.get("motivo_reprovacao") not in {"nota", "falta"}
        ),
    }
    return {
        "taxa_aprovacao": rate,
        "media_notas": avg_grade,
        "finalizados": len(finalized_rows),
        "aprovados": approved,
        "reprovados": failed,
        "reprovacoes": by_reason,
        "em_andamento": sum(1 for r in rows if r.get("aprovado") is None),
        "total_registros": len(rows),
    }


def _variation(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(float(current) - float(previous), 2)


def _academic_goal(
    metas: list[dict[str, Any]],
    indicator: str,
    period: str,
    course: str | None = None,
    discipline: str | None = None,
) -> dict[str, Any] | None:
    """Resolve metas acadêmicas novas com fallback seguro para o código 01 legado.

    A migration 030 converte DTNH/DCS-01 em 01B. O fallback existe para snapshots
    históricos, testes e ambientes locais ainda não migrados; novas gravações não
    aceitam mais o código legado.
    """
    goal = active_goal(metas, indicator, period, course, discipline)
    if goal or not indicator.endswith("-01B"):
        return goal
    return active_goal(metas, indicator[:-1], period, course, discipline)


def _institution_nps_details(snapshot: dict[str, Any], period: str | None) -> dict[str, Any]:
    semester = to_semester(period)
    if not semester:
        return {
            "valor": None, "respondentes": 0, "promotores": 0, "neutros": 0, "detratores": 0,
            "fonte": None, "coverage": 0, "coverage_total": 0, "complete": False,
        }
    row = next((
        item for item in snapshot.get("nps_institution", [])
        if to_semester(item.get("periodo")) == semester
    ), None)
    if not row:
        return {
            "valor": None, "respondentes": 0, "promotores": 0, "neutros": 0, "detratores": 0,
            "fonte": None, "coverage": 0, "coverage_total": 0, "complete": False,
        }
    return {
        "valor": row.get("valor"),
        "respondentes": int(row.get("respondentes") or 0),
        "promotores": int(row.get("promotores") or 0),
        "neutros": int(row.get("neutros") or 0),
        "detratores": int(row.get("detratores") or 0),
        "fonte": row.get("fonte"),
        "coverage": int(row.get("coverage") or 0),
        "coverage_total": int(row.get("coverage_total") or 0),
        "complete": bool(row.get("complete")),
    }


def _faculty_institution_nps_details(snapshot: dict[str, Any], period: str | None) -> dict[str, Any]:
    semester = to_semester(period)
    if not semester:
        return {"valor": None, "respondentes": 0, "promotores": 0, "neutros": 0, "detratores": 0, "fonte": None}
    row = next((
        item for item in snapshot.get("nps_institution_faculty", [])
        if to_semester(item.get("periodo")) == semester
    ), None)
    if not row:
        return {"valor": None, "respondentes": 0, "promotores": 0, "neutros": 0, "detratores": 0, "fonte": None}
    return {
        "valor": row.get("valor"),
        "respondentes": int(row.get("respondentes") or 0),
        "promotores": int(row.get("promotores") or 0),
        "neutros": int(row.get("neutros") or 0),
        "detratores": int(row.get("detratores") or 0),
        "fonte": row.get("fonte"),
    }


def _faculty_institution_nps_series(
    snapshot: dict[str, Any],
    periods: list[str],
    code_prefix: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    code = f"{code_prefix}-01C"
    for period in periods:
        details = _faculty_institution_nps_details(snapshot, period)
        goal = _academic_goal(snapshot.get("metas", []), code, period)
        info = goal_info(goal, code)
        out.append({
            "periodo": to_semester(period) or period,
            **details,
            "meta": info.get("meta") if info else None,
            "meta_vigencia": info.get("vigencia") if info else None,
            "meta_recorte": info.get("recorte") if info else None,
            "limite_superior": info.get("limite_superior") if info else None,
        })
    return out


def _institution_nps_series(
    snapshot: dict[str, Any],
    periods: list[str],
    code_prefix: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    code = f"{code_prefix}-01A"
    for period in periods:
        details = _institution_nps_details(snapshot, period)
        goal = _academic_goal(snapshot.get("metas", []), code, period)
        info = goal_info(goal, code)
        out.append({
            "periodo": to_semester(period) or period,
            "valor": details["valor"],
            "respondentes": details["respondentes"],
            "promotores": details["promotores"],
            "neutros": details["neutros"],
            "detratores": details["detratores"],
            "fonte": details["fonte"],
            "coverage": details["coverage"],
            "coverage_total": details["coverage_total"],
            "complete": details["complete"],
            "meta": info.get("meta") if info else None,
            "meta_vigencia": info.get("vigencia") if info else None,
            "meta_recorte": info.get("recorte") if info else None,
            "limite_superior": info.get("limite_superior") if info else None,
        })
    return out


def _period_metrics(
    snapshot: dict[str, Any],
    period: str | None,
    course: str | None,
    discipline: str | None,
    granularity: str,
) -> tuple[float | None, float | None, dict[str, Any]]:
    if not period:
        return None, None, aggregate_results([])
    nps = aggregate_nps(_nps_period_rows(snapshot.get("nps", []), period, course, granularity))
    teacher = aggregate_teacher_evaluation(
        _semester_rows(snapshot.get("avaliacao_docente", []), period, course, discipline)
    )
    result = aggregate_results(_semester_rows(snapshot.get("resultados", []), period, course, discipline))
    return nps, teacher, result


def _series(
    snapshot: dict[str, Any],
    periods: list[str],
    course: str | None,
    discipline: str | None,
    code_prefix: str,
    granularity: str,
) -> dict[str, list[dict[str, Any]]]:
    out = {"nps": [], "avaliacao_docente": [], "aprovacao": []}
    for period in periods:
        nps_rows = _nps_period_rows(snapshot.get("nps", []), period, course, granularity)
        nps_details = aggregate_nps_details(nps_rows)
        nps, teacher, result = _period_metrics(snapshot, period, course, discipline, granularity)
        goal_nps = _academic_goal(snapshot.get("metas", []), f"{code_prefix}-01B", period, course, discipline)
        goal_teacher = active_goal(snapshot.get("metas", []), f"{code_prefix}-02", period, course, discipline)
        goal_appr = active_goal(snapshot.get("metas", []), f"{code_prefix}-03", period, course, discipline)

        def goal_series_fields(goal: dict[str, Any] | None) -> dict[str, Any]:
            if not goal:
                return {"meta": None, "meta_vigencia": None, "meta_recorte": None, "limite_superior": None}
            return {
                "meta": goal.get("meta"),
                "meta_vigencia": goal.get("vigencia"),
                "meta_recorte": goal.get("recorte") or "TOTAL",
                "limite_superior": goal.get("limite_superior"),
            }

        out["nps"].append({
            "periodo": period,
            "valor": nps,
            "respondentes": nps_details["respondentes"],
            "promotores": nps_details["promotores"],
            "neutros": nps_details["neutros"],
            "detratores": nps_details["detratores"],
            "fonte": nps_details["fonte"],
            "cursos": nps_details["cursos"],
            **goal_series_fields(goal_nps),
        })
        out["avaliacao_docente"].append({"periodo": period, "valor": teacher, **goal_series_fields(goal_teacher)})
        out["aprovacao"].append({
            "periodo": period,
            "valor": result["taxa_aprovacao"],
            "media_notas": result["media_notas"],
            "aprovados": result["aprovados"],
            "reprovados_nota": result["reprovacoes"]["nota"],
            "reprovados_falta": result["reprovacoes"]["falta"],
            **goal_series_fields(goal_appr),
        })
    return out


def _overall_course_metrics(
    snapshot: dict[str, Any],
    course: str,
) -> tuple[float | None, float | None, dict[str, Any]]:
    """Aggregate one course across the whole available academic history.

    NPS needs special treatment because the database can contain a semester
    closing and real monthly measurements for the same semester. We reuse the
    semester-selection rule so the general view never double-counts both
    representations. Teacher evaluation and academic results are semester-native
    and can therefore be aggregated directly across their historical rows.
    """
    semester_values = sorted({
        sem
        for row in snapshot.get("nps", [])
        for sem in [to_semester(row.get("periodo"))]
        if sem
    }, key=semester_sort_key)
    nps_rows: list[dict[str, Any]] = []
    for semester in semester_values:
        nps_rows.extend(_nps_period_rows(snapshot.get("nps", []), semester, course, "semestral"))

    teacher_rows = _course_filter(snapshot.get("avaliacao_docente", []), course)
    result_rows = _course_filter(snapshot.get("resultados", []), course)
    return (
        aggregate_nps(nps_rows),
        aggregate_teacher_evaluation(teacher_rows),
        aggregate_results(result_rows),
    )


def _course_comparison(
    snapshot: dict[str, Any],
    period: str | None,
    metric: str,
    granularity: str,
    *,
    directorate_code: str | None = None,
) -> list[dict[str, Any]]:
    """Compare courses either for one period or for the complete history.

    Para NPS, quando existe um semestre explícito, cada curso também recebe a
    meta efetiva e o status correspondente. A camada visual pode então usar cor
    como informação gerencial, sem recalcular regra de meta no navegador.
    """
    courses = sorted({
        str(r.get("curso") or "")
        for key in ("nps", "avaliacao_docente", "resultados")
        for r in snapshot.get(key, [])
        if r.get("curso")
    })
    out = []
    overall = not period or str(period).strip().casefold() in {"geral", "(geral)", "todo historico", "todo histórico"}
    for course in courses:
        if overall:
            nps, teacher, result = _overall_course_metrics(snapshot, course)
        else:
            nps, teacher, result = _period_metrics(snapshot, period, course, None, granularity)
        value = nps if metric == "nps" else teacher if metric == "avaliacao_docente" else result["taxa_aprovacao"]
        if value is None:
            continue
        item: dict[str, Any] = {"curso": course, "valor": value}
        if metric == "nps" and directorate_code and not overall:
            code = f"{directorate_code}-01B"
            goal = _academic_goal(snapshot.get("metas", []), code, period or "", course, None)
            info = goal_info(goal, code, course, None)
            item.update({
                "meta": info.get("meta") if info else None,
                "atencao": info.get("atencao") if info else None,
                "meta_vigencia": info.get("vigencia") if info else None,
                "meta_recorte": info.get("recorte") if info else None,
                "status": status_for(value, goal, code),
            })
        out.append(item)
    return sorted(out, key=lambda x: (x["valor"], x["curso"]), reverse=True)

def _visible_period_window(
    available: list[str],
    reference: str | None,
    comparison: str | None,
    minimum_periods: int | None,
) -> list[str]:
    """Return a contiguous window that never drops reference/comparison.

    ``minimum_periods`` is a minimum size, not a hard truncation. If the user
    compares periods farther apart than the selected window (for example
    2025-SEM2 vs 2026-SEM2 with a 2-semester window), every period between them
    remains visible. This prevents the comparison point from disappearing.
    """
    if not available or not reference or reference not in available:
        return available
    if not minimum_periods:
        return available
    minimum = max(1, int(minimum_periods))
    ref_idx = available.index(reference)

    if comparison and comparison in available and comparison != reference:
        cmp_idx = available.index(comparison)
        start, end = sorted((ref_idx, cmp_idx))
        # Reach the requested minimum without hiding either selected endpoint.
        needed = minimum - (end - start + 1)
        if needed > 0:
            forward = min(needed, len(available) - 1 - end)
            end += forward
            needed -= forward
            if needed > 0:
                start = max(0, start - needed)
        return available[start:end + 1]

    start = max(0, ref_idx - minimum + 1)
    return available[start:ref_idx + 1]


def build_academic_dashboard(
    snapshot: dict[str, Any],
    course: str | None = None,
    discipline: str | None = None,
    reference: str | None = None,
    comparison: str | None = None,
    window_semesters: int | None = None,
    *,
    directorate_code: str = "DTNH",
    granularity: str | None = None,
) -> dict[str, Any]:
    course = None if course in (None, "", "(todos)") else course
    discipline = None if discipline in (None, "", "(todas)") else discipline
    granularity = _normalize_granularity(granularity)

    semesters, months = _available_periods(snapshot, reference=reference, comparison=comparison)
    available = months if granularity == "mensal" else semesters
    sort_key = month_sort_key if granularity == "mensal" else semester_sort_key

    current_month, current_semester = _current_calendar_periods()
    current_period = current_month if granularity == "mensal" else current_semester
    normalized_reference = _normalize_period(reference, granularity)
    if normalized_reference and normalized_reference in available:
        reference = normalized_reference
    elif current_period in available:
        reference = current_period
    else:
        reference = available[-1] if available else None

    normalized_comparison = _normalize_period(comparison, granularity)
    if normalized_comparison and normalized_comparison in available and normalized_comparison != reference:
        comparison = normalized_comparison
    else:
        prior = [period for period in available if reference and sort_key(period) < sort_key(reference)]
        comparison = prior[-1] if prior else None

    visible_periods = _visible_period_window(available, reference, comparison, window_semesters)

    # NPS is semester-native. Even when the dashboard is in monthly mode, its
    # comparison must be the previous semester rather than the previous month
    # from the same closing. This keeps the executive card and the chart useful
    # and prevents a misleading zero variation repeated across six months.
    nps_reference = to_semester(reference) if reference else None
    requested_nps_comparison = to_semester(comparison) if comparison else None
    if requested_nps_comparison == nps_reference:
        requested_nps_comparison = None
    if requested_nps_comparison:
        nps_comparison = requested_nps_comparison
    else:
        prior_semesters = [
            semester for semester in semesters
            if nps_reference and semester_sort_key(semester) < semester_sort_key(nps_reference)
        ]
        nps_comparison = prior_semesters[-1] if prior_semesters else None

    nps_rows_now = _nps_period_rows(snapshot.get("nps", []), nps_reference, course, "semestral") if nps_reference else []
    nps_rows_prev = _nps_period_rows(snapshot.get("nps", []), nps_comparison, course, "semestral") if nps_comparison else []
    nps_details_now = aggregate_nps_details(nps_rows_now)
    nps_details_prev = aggregate_nps_details(nps_rows_prev)
    nps_now = nps_details_now["valor"]
    nps_prev = nps_details_prev["valor"]
    institution_nps_details_now = _institution_nps_details(snapshot, nps_reference)
    institution_nps_details_prev = _institution_nps_details(snapshot, nps_comparison)
    institution_nps_now = institution_nps_details_now["valor"]
    institution_nps_prev = institution_nps_details_prev["valor"]
    faculty_nps_details_now = _faculty_institution_nps_details(snapshot, nps_reference)
    faculty_nps_details_prev = _faculty_institution_nps_details(snapshot, nps_comparison)
    faculty_nps_now = faculty_nps_details_now["valor"]
    faculty_nps_prev = faculty_nps_details_prev["valor"]
    _, teacher_now, result_now = _period_metrics(snapshot, reference, course, discipline, granularity)
    _, teacher_prev, result_prev = _period_metrics(snapshot, comparison, course, discipline, granularity)

    # Academic results are semester-native. In monthly visualization the same
    # semester summary is intentionally repeated from Jan-Jun / Jul-Dec.
    result_rows_now = _semester_rows(snapshot.get("resultados", []), reference, course, discipline) if reference else []
    discipline_summary = sorted(
        [dict(row) for row in result_rows_now if row.get("agregado") is True],
        key=lambda row: (str(row.get("curso") or "").casefold(), str(row.get("disciplina") or "").casefold()),
    )

    codes = {
        "nps_institution": f"{directorate_code}-01A",
        "nps_course": f"{directorate_code}-01B",
        "nps_faculty": f"{directorate_code}-01C",
        "avaliacao_docente": f"{directorate_code}-02",
        "aprovacao": f"{directorate_code}-03",
    }
    goals = {
        "nps_institution": _academic_goal(snapshot.get("metas", []), codes["nps_institution"], reference or ""),
        "nps_course": _academic_goal(snapshot.get("metas", []), codes["nps_course"], reference or "", course, None),
        "nps_faculty": _academic_goal(snapshot.get("metas", []), codes["nps_faculty"], reference or ""),
        "avaliacao_docente": _academic_goal(snapshot.get("metas", []), codes["avaliacao_docente"], reference or "", course, discipline),
        "aprovacao": _academic_goal(snapshot.get("metas", []), codes["aprovacao"], reference or "", course, discipline),
    }
    goal_infos = {
        "nps_institution": goal_info(goals["nps_institution"], codes["nps_institution"]),
        "nps_course": goal_info(goals["nps_course"], codes["nps_course"], course, None),
        "nps_faculty": goal_info(goals["nps_faculty"], codes["nps_faculty"]),
        "avaliacao_docente": goal_info(goals["avaliacao_docente"], codes["avaliacao_docente"], course, discipline),
        "aprovacao": goal_info(goals["aprovacao"], codes["aprovacao"], course, discipline),
    }

    series = _series(snapshot, visible_periods, course, discipline, directorate_code, granularity)
    visible_nps_semesters = sorted(
        {semester for period in visible_periods for semester in [to_semester(period)] if semester},
        key=semester_sort_key,
    )
    course_nps_series = _series(
        snapshot, visible_nps_semesters, course, discipline, directorate_code, "semestral"
    )["nps"]
    series["nps_semestral"] = course_nps_series  # alias histórico do NPS do Curso
    series["nps_course_semestral"] = course_nps_series
    series["nps_institution_semestral"] = _institution_nps_series(
        snapshot, visible_nps_semesters, directorate_code
    )
    series["nps_faculty_semestral"] = _faculty_institution_nps_series(
        snapshot, visible_nps_semesters, directorate_code
    )
    quality = {
        "nps": sum(1 for r in snapshot.get("nps", []) if r.get("validacao") not in (None, "", "OK")),
        "avaliacao_docente": sum(1 for r in snapshot.get("avaliacao_docente", []) if r.get("validacao") not in (None, "", "OK")),
        "resultados": sum(1 for r in snapshot.get("resultados", []) if r.get("validacao") not in (None, "", "OK")),
    }
    quality["total"] = sum(quality.values())

    insights: list[dict[str, str]] = []
    if not snapshot.get("resultados"):
        insights.append({
            "nivel": "atenção",
            "titulo": "Base acadêmica ainda vazia",
            "texto": "Importe um mapa de notas do SEI, uma planilha ou registre resultados manualmente. Cursos, disciplinas e alunos podem ser criados automaticamente durante a importação.",
        })
    else:
        total_links = int(snapshot.get("resultados_total") or sum(int(r.get("total_registros") or 0) for r in snapshot.get("resultados", [])))
        insights.append({
            "nivel": "positivo" if quality["total"] == 0 else "atenção",
            "titulo": "Base acadêmica processada",
            "texto": f"{total_links} vínculo(s) aluno-disciplina consolidados no banco; o painel usa agregações e não carrega as linhas individuais para cálculo.",
        })
    if granularity == "mensal" and reference:
        insights.append({
            "nivel": "informativo",
            "titulo": "Projeção mensal de dados semestrais",
            "texto": f"NPS, avaliação docente e resultados acadêmicos são tratados como fechamentos semestrais e repetidos nos seis meses de {to_semester(reference)}. Registros mensais de NPS só entram como fallback quando o curso não possui fechamento semestral.",
        })
    if result_now["reprovados"]:
        insights.append({
            "nivel": "atenção",
            "titulo": "Motivos de reprovação",
            "texto": f"No período: {result_now['reprovacoes']['nota']} por nota, {result_now['reprovacoes']['falta']} por falta e {result_now['reprovacoes']['outro']} por outros motivos.",
        })
    if result_now["media_notas"] is not None:
        insights.append({
            "nivel": "informativo",
            "titulo": "Média das notas disponíveis",
            "texto": f"A média simples das notas finais registradas no recorte é {result_now['media_notas']:.2f}. A situação oficial do SEI continua sendo a fonte para aprovado/reprovado.",
        })
    if teacher_now is None:
        insights.append({
            "nivel": "informativo",
            "titulo": "Avaliação docente sem fechamento",
            "texto": "A avaliação do docente pelo aluno pode ser lançada por professor e disciplina quando o instrumento estiver disponível.",
        })

    try:
        actions = snapshot.get("actions", [])
        overdue = sum(
            1 for a in actions
            if a.get("dias_prazo") is not None and a["dias_prazo"] < 0 and a.get("status") not in {"Concluído", "Cancelado"}
        )
        open_actions = sum(1 for a in actions if a.get("status") not in {"Concluído", "Cancelado"})
    except Exception:
        overdue, open_actions = 0, 0

    performance_semesters = sorted({
        sem
        for key in ("nps", "avaliacao_docente", "resultados")
        for row in snapshot.get(key, [])
        for sem in [to_semester(row.get("periodo"))]
        if sem
    }, key=semester_sort_key)

    return {
        "contexto": {
            "diretoria": directorate_code,
            "curso": course or "(todos)",
            "disciplina": discipline or "(todas)",
            "referencia": reference,
            "comparacao": comparison,
            "granularidade": granularity,
            "inicio": visible_periods[0] if visible_periods else None,
            "fim": visible_periods[-1] if visible_periods else None,
            "nps_referencia": nps_reference,
            "nps_comparacao": nps_comparison,
        },
        "periodos": {"semestrais": semesters, "mensais": months},
        "cards": {
            "nps_institution": {
                "valor": institution_nps_now,
                "comparacao": institution_nps_prev,
                "variacao": _variation(institution_nps_now, institution_nps_prev),
                "status": status_for(institution_nps_now, goals["nps_institution"], codes["nps_institution"]),
                "meta": goal_infos["nps_institution"].get("meta") if goal_infos["nps_institution"] else None,
                "meta_info": goal_infos["nps_institution"],
                "respondentes": institution_nps_details_now["respondentes"],
                "promotores": institution_nps_details_now["promotores"],
                "neutros": institution_nps_details_now["neutros"],
                "detratores": institution_nps_details_now["detratores"],
                "fonte": institution_nps_details_now["fonte"],
                "coverage": institution_nps_details_now["coverage"],
                "coverage_total": institution_nps_details_now["coverage_total"],
                "complete": institution_nps_details_now["complete"],
                "comparacao_respondentes": institution_nps_details_prev["respondentes"],
            },
            "nps_course": {
                "valor": nps_now,
                "comparacao": nps_prev,
                "variacao": _variation(nps_now, nps_prev),
                "status": status_for(nps_now, goals["nps_course"], codes["nps_course"]),
                "meta": goal_infos["nps_course"].get("meta") if goal_infos["nps_course"] else None,
                "meta_info": goal_infos["nps_course"],
                "respondentes": nps_details_now["respondentes"],
                "promotores": nps_details_now["promotores"],
                "neutros": nps_details_now["neutros"],
                "detratores": nps_details_now["detratores"],
                "fonte": nps_details_now["fonte"],
                "cursos": nps_details_now["cursos"],
                "comparacao_respondentes": nps_details_prev["respondentes"],
            },
            "nps_faculty": {
                "valor": faculty_nps_now,
                "comparacao": faculty_nps_prev,
                "variacao": _variation(faculty_nps_now, faculty_nps_prev),
                "status": status_for(faculty_nps_now, goals["nps_faculty"], codes["nps_faculty"]),
                "meta": goal_infos["nps_faculty"].get("meta") if goal_infos["nps_faculty"] else None,
                "meta_info": goal_infos["nps_faculty"],
                "respondentes": faculty_nps_details_now["respondentes"],
                "promotores": faculty_nps_details_now["promotores"],
                "neutros": faculty_nps_details_now["neutros"],
                "detratores": faculty_nps_details_now["detratores"],
                "fonte": faculty_nps_details_now["fonte"],
                "comparacao_respondentes": faculty_nps_details_prev["respondentes"],
            },
            # Alias temporário para integrações anteriores à divisão 01A/01B.
            "nps": {
                "valor": nps_now,
                "comparacao": nps_prev,
                "variacao": _variation(nps_now, nps_prev),
                "status": status_for(nps_now, goals["nps_course"], codes["nps_course"]),
                "meta": goal_infos["nps_course"].get("meta") if goal_infos["nps_course"] else None,
                "meta_info": goal_infos["nps_course"],
                "respondentes": nps_details_now["respondentes"],
                "promotores": nps_details_now["promotores"],
                "neutros": nps_details_now["neutros"],
                "detratores": nps_details_now["detratores"],
                "fonte": nps_details_now["fonte"],
                "cursos": nps_details_now["cursos"],
                "comparacao_respondentes": nps_details_prev["respondentes"],
            },
            "avaliacao_docente": {
                "valor": teacher_now,
                "comparacao": teacher_prev,
                "variacao": _variation(teacher_now, teacher_prev),
                "status": status_for(teacher_now, goals["avaliacao_docente"], codes["avaliacao_docente"]),
                "meta": goal_infos["avaliacao_docente"].get("meta") if goal_infos["avaliacao_docente"] else None,
                "meta_info": goal_infos["avaliacao_docente"],
            },
            "aprovacao": {
                "valor": result_now["taxa_aprovacao"],
                "comparacao": result_prev["taxa_aprovacao"],
                "variacao": _variation(result_now["taxa_aprovacao"], result_prev["taxa_aprovacao"]),
                "status": status_for(result_now["taxa_aprovacao"], goals["aprovacao"], codes["aprovacao"]),
                "meta": goal_infos["aprovacao"].get("meta") if goal_infos["aprovacao"] else None,
                "meta_info": goal_infos["aprovacao"],
                **result_now,
            },
            "qualidade": quality,
            "planos": {"abertos": open_actions, "atrasados": overdue},
        },
        "metas_vigentes": {
            "nps_institution": goal_infos["nps_institution"],
            "nps_course": goal_infos["nps_course"],
            "nps_faculty": goal_infos["nps_faculty"],
            "nps": goal_infos["nps_course"],  # alias histórico
            "avaliacao_docente": goal_infos["avaliacao_docente"],
            "aprovacao": goal_infos["aprovacao"],
        },
        "series": series,
        "resumo_disciplinas": discipline_summary,
        # A comparação executiva permanece atrelada à referência para
        # compatibilidade. A seção "Desempenho entre cursos" recebe também uma
        # visão geral histórica e recortes independentes por semestre, evitando
        # que um semestre excepcional fique escondido dentro do consolidado.
        "comparacoes": {
            "nps": _course_comparison(snapshot, reference, "nps", granularity, directorate_code=directorate_code),
            "avaliacao_docente": _course_comparison(snapshot, reference, "avaliacao_docente", granularity),
            "aprovacao": _course_comparison(snapshot, reference, "aprovacao", granularity),
        },
        "desempenho_cursos": {
            "periodos": performance_semesters,
            "geral": {
                "nps": _course_comparison(snapshot, None, "nps", "semestral"),
                "avaliacao_docente": _course_comparison(snapshot, None, "avaliacao_docente", "semestral"),
                "aprovacao": _course_comparison(snapshot, None, "aprovacao", "semestral"),
            },
            "por_semestre": {
                semester: {
                    "nps": _course_comparison(snapshot, semester, "nps", "semestral", directorate_code=directorate_code),
                    "avaliacao_docente": _course_comparison(snapshot, semester, "avaliacao_docente", "semestral"),
                    "aprovacao": _course_comparison(snapshot, semester, "aprovacao", "semestral"),
                }
                for semester in performance_semesters
            },
        },
        "insights": insights[:8],
    }
