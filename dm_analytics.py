from __future__ import annotations

from collections import Counter
from datetime import date
from statistics import median
from typing import Any, Iterable

from dm_catalog import DM_AREAS, months_between


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _pct(numerator: float | int, denominator: float | int) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator) * 100, 2)


def _semester_for_date(value: date) -> str:
    return f"{value.year:04d}-SEM{1 if value.month <= 6 else 2}"


def _effective_target(
    targets: list[dict[str, Any]],
    indicator_code: str,
    metric_key: str,
    as_of: date,
    *,
    default_target: float | None,
    default_attention: float | None,
) -> tuple[float | None, float | None]:
    reference = _semester_for_date(as_of)
    rows = [
        row for row in targets
        if row.get("indicator_code") == indicator_code
        and row.get("metric_key") == metric_key
        and (row.get("dimension_key") in (None, "", "TOTAL"))
        and str(row.get("valid_from") or "") <= reference
        and (not row.get("valid_to") or str(row.get("valid_to")) >= reference)
    ]
    rows.sort(key=lambda row: str(row.get("valid_from") or ""), reverse=True)
    if not rows:
        return default_target, default_attention
    row = rows[0]
    target = row.get("target")
    attention = row.get("attention")
    return (float(target) if target is not None else default_target,
            float(attention) if attention is not None else default_attention)


def _status_dm01(summary: dict[str, Any], targets: list[dict[str, Any]], as_of: date) -> str:
    """Avalia somente a meta absoluta de membros por turma."""
    if summary.get("status") in {"Planejada", "Aberta"}:
        return "Em formação"
    if summary["total_students"] == 0:
        return "Sem dados"
    target, _ = _effective_target(
        targets,
        "DM-01",
        "cohort_members",
        as_of,
        default_target=None,
        default_attention=None,
    )
    if target is None:
        return "Sem meta"
    return "Dentro da meta" if float(summary["total_students"]) >= target else "Fora da meta"


def _status_dm02(summary: dict[str, Any], targets: list[dict[str, Any]], as_of: date) -> str:
    """Avalia somente a meta de tempo médio entre ingresso confirmado e defesa."""
    if summary["total_students"] == 0:
        return "Sem dados"
    if summary.get("confirmed_entry_dates", 0) == 0:
        return "Dados pendentes"
    if summary.get("status") in {"Planejada", "Aberta"}:
        return "Em acompanhamento"
    average = summary.get("average_months_to_defense")
    if average is None:
        return "Em acompanhamento"
    target, _ = _effective_target(
        targets,
        "DM-02",
        "average_months_to_defense",
        as_of,
        default_target=24,
        default_attention=None,
    )
    if target is None:
        return "Sem meta"
    return "Dentro da meta" if float(average) <= target else "Fora da meta"

def cohort_summary(
    cohort: dict[str, Any],
    students: Iterable[dict[str, Any]],
    *,
    as_of: date | None = None,
    targets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    targets = targets or []
    rows = list(students)
    status_counts = Counter(str(row.get("status") or "Ativo") for row in rows)
    total = len(rows)
    active = status_counts.get("Ativo", 0)
    graduated = status_counts.get("Titulado", 0)
    dropped = status_counts.get("Desligado", 0)
    vacancies = cohort.get("vacancies_authorized")
    try:
        vacancies = int(vacancies) if vacancies not in (None, "") else None
    except (TypeError, ValueError):
        vacancies = None

    durations: list[float] = []
    on_time = 0
    risk_18_qualification = 0
    risk_24_no_scheduled = 0
    risk_30_no_defense = 0
    active_advisors: Counter[str] = Counter()
    last_defense: date | None = None
    confirmed_entry_dates = 0
    estimated_entry_dates = 0

    for row in rows:
        entry = _date(row.get("entry_date"))
        entry_is_estimated = bool(row.get("entry_date_estimated"))
        if entry:
            if entry_is_estimated:
                estimated_entry_dates += 1
            else:
                confirmed_entry_dates += 1
        # Prazos do DM-02 usam somente o ingresso individual confirmado. A data
        # de abertura da turma é metadado da turma e não substitui o ingresso do aluno.
        analytical_entry = entry if entry and not entry_is_estimated else None
        defense = _date(row.get("defense_date"))
        qualification = _date(row.get("qualification_date"))
        scheduled = _date(row.get("defense_scheduled_date"))
        if analytical_entry and defense:
            duration = months_between(analytical_entry, defense)
            durations.append(duration)
            if duration <= 24:
                on_time += 1
            if last_defense is None or defense > last_defense:
                last_defense = defense
        if str(row.get("status")) == "Ativo" and analytical_entry:
            elapsed = months_between(analytical_entry, as_of)
            if elapsed > 18 and not qualification:
                risk_18_qualification += 1
            if elapsed > 24 and not defense and not scheduled:
                risk_24_no_scheduled += 1
            if elapsed > 30 and not defense:
                risk_30_no_defense += 1
            advisor = str(row.get("advisor") or "").strip()
            if advisor:
                active_advisors[advisor] += 1

    average_months = round(sum(durations) / len(durations), 2) if durations else None
    median_months = round(float(median(durations)), 2) if durations else None
    advisor_count = len(active_advisors)
    advisees_per_faculty = round(active / advisor_count, 2) if advisor_count else None

    summary = {
        **cohort,
        "total_students": total,
        "active_students": active,
        "graduated_students": graduated,
        "dropped_students": dropped,
        # Compatibilidade temporária com consumidores legados. O domínio ativo
        # não possui mais status Trancado; registros históricos foram migrados
        # para Desligado.
        "locked_students": 0,
        "occupancy_pct": _pct(total, vacancies) if vacancies else None,
        "dropout_rate_pct": _pct(dropped, total),
        "average_months_to_defense": average_months,
        "median_months_to_defense": median_months,
        "defenses_count": len(durations),
        "graduated_within_24": on_time,
        "on_time_graduation_pct": _pct(on_time, confirmed_entry_dates),
        "confirmed_entry_dates": confirmed_entry_dates,
        "estimated_entry_dates": estimated_entry_dates,
        "entry_date_completeness_pct": _pct(confirmed_entry_dates, total),
        "active_over_18_no_qualification": risk_18_qualification,
        "active_over_24_no_scheduled_defense": risk_24_no_scheduled,
        "active_over_30_no_defense": risk_30_no_defense,
        "active_advisor_count": advisor_count,
        "advisees_per_faculty": advisees_per_faculty,
        "last_defense_date": last_defense.isoformat() if last_defense else None,
    }
    summary["dm01_status"] = _status_dm01(summary, targets, as_of)
    summary["dm02_status"] = _status_dm02(summary, targets, as_of)
    return summary


def _area_totals(cohorts: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(row["total_students"] for row in cohorts)
    active = sum(row["active_students"] for row in cohorts)
    graduated = sum(row["graduated_students"] for row in cohorts)
    dropped = sum(row["dropped_students"] for row in cohorts)
    vacancies = sum(int(row.get("vacancies_authorized") or 0) for row in cohorts)
    defenses = sum(row["defenses_count"] for row in cohorts)
    weighted_months = sum(
        (row.get("average_months_to_defense") or 0) * row["defenses_count"]
        for row in cohorts
    )
    on_time = sum(row["graduated_within_24"] for row in cohorts)
    advisors = sum(row["active_advisor_count"] for row in cohorts)
    confirmed_entries = sum(row.get("confirmed_entry_dates", 0) for row in cohorts)
    estimated_entries = sum(row.get("estimated_entry_dates", 0) for row in cohorts)
    return {
        "cohort_count": len(cohorts),
        "total_students": total,
        "active_students": active,
        "graduated_students": graduated,
        "dropped_students": dropped,
        # Compatibilidade temporária com consumidores legados. O domínio ativo
        # não possui mais status Trancado; registros históricos foram migrados
        # para Desligado.
        "locked_students": 0,
        "vacancies_authorized": vacancies or None,
        "occupancy_pct": _pct(total, vacancies) if vacancies else None,
        "dropout_rate_pct": _pct(dropped, total),
        "defenses_count": defenses,
        "average_months_to_defense": round(weighted_months / defenses, 2) if defenses else None,
        "on_time_graduation_pct": _pct(on_time, confirmed_entries),
        "confirmed_entry_dates": confirmed_entries,
        "estimated_entry_dates": estimated_entries,
        "entry_date_completeness_pct": _pct(confirmed_entries, total),
        "active_over_18_no_qualification": sum(row["active_over_18_no_qualification"] for row in cohorts),
        "active_over_24_no_scheduled_defense": sum(row["active_over_24_no_scheduled_defense"] for row in cohorts),
        "active_over_30_no_defense": sum(row["active_over_30_no_defense"] for row in cohorts),
        "active_advisor_count": advisors,
    }


def build_dm_dashboard(
    cohorts: Iterable[dict[str, Any]],
    students: Iterable[dict[str, Any]],
    *,
    area_code: str | None = None,
    cohort_id: int | None = None,
    as_of: date | None = None,
    targets: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cohort_rows = [dict(row) for row in cohorts]
    student_rows = [dict(row) for row in students]
    target_rows = [dict(row) for row in (targets or [])]
    as_of = as_of or date.today()
    by_cohort: dict[int, list[dict[str, Any]]] = {}
    for row in student_rows:
        try:
            key = int(row.get("cohort_id"))
        except (TypeError, ValueError):
            continue
        by_cohort.setdefault(key, []).append(row)

    areas: list[dict[str, Any]] = []
    all_summaries: list[dict[str, Any]] = []
    selected_cohort: dict[str, Any] | None = None
    for code, name in DM_AREAS.items():
        area_cohorts = [row for row in cohort_rows if row.get("area_code") == code]
        area_cohorts.sort(key=lambda row: (int(row.get("cohort_number") or 0), str(row.get("opening_date") or "")))
        summaries = [cohort_summary(row, by_cohort.get(int(row["id"]), []), as_of=as_of, targets=target_rows) for row in area_cohorts]
        all_summaries.extend(summaries)
        if cohort_id is not None:
            selected_cohort = next((row for row in summaries if int(row["id"]) == int(cohort_id)), selected_cohort)
        areas.append({
            "area_code": code,
            "area_name": name,
            "cohorts": summaries,
            "totals": _area_totals(summaries),
            "latest_cohort": summaries[-1] if summaries else None,
            "has_open_cohort": any(row.get("status") in {"Aberta", "Em andamento"} for row in summaries),
        })

    selected_area = str(area_code or "").upper() or None
    if selected_area and selected_area not in DM_AREAS:
        selected_area = None

    # The executive filters are real scopes, not only visual selectors.  This
    # mirrors the DTNH/DCS dashboard behavior: changing a filter immediately
    # changes cards, charts and totals using the same filtered population.
    if cohort_id is not None and selected_cohort is not None:
        selected_area = str(selected_cohort.get("area_code") or "").upper() or selected_area
        matching_area = next((item for item in areas if item["area_code"] == selected_area), None)
        visible_areas = []
        if matching_area:
            only = [selected_cohort]
            visible_areas = [{
                **matching_area,
                "cohorts": only,
                "totals": _area_totals(only),
                "latest_cohort": selected_cohort,
                "has_open_cohort": selected_cohort.get("status") in {"Aberta", "Em andamento"},
            }]
        filtered_summaries = [selected_cohort]
    else:
        visible_areas = [item for item in areas if not selected_area or item["area_code"] == selected_area]
        filtered_summaries = [cohort for item in visible_areas for cohort in item["cohorts"]]

    overall = _area_totals(filtered_summaries)
    overall["area_count"] = len(visible_areas)
    overall["areas_with_open_cohort"] = sum(1 for item in visible_areas if item["has_open_cohort"])

    # A DM possui somente duas metas institucionais: membros por turma e
    # tempo médio até a defesa. As demais medidas continuam analíticas.
    effective_targets = {}
    for code, metric, default_t in [
        ("DM-01", "cohort_members", None),
        ("DM-02", "average_months_to_defense", 24),
    ]:
        target, _ = _effective_target(
            target_rows, code, metric, as_of,
            default_target=default_t, default_attention=None,
        )
        effective_targets[f"{code}:{metric}"] = {"target": target}

    return {
        "areas": areas,
        "visible_areas": visible_areas,
        "selected_area": selected_area,
        "selected_cohort": selected_cohort,
        "overall": overall,
        "effective_targets": effective_targets,
        "as_of": as_of.isoformat(),
        "rules": {
            "axis": "Turma",
            "areas": DM_AREAS,
            "on_time_months": 24,
            "qualification_risk_months": 18,
            "defense_risk_months": 30,
        },
    }
