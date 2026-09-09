from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from dm_catalog import DM_AREAS

RNG = random.Random(73021)


def _add_months_approx(value: date, months: int) -> date:
    return value + timedelta(days=round(months * 30.4375))


def build_dm_demo_payloads() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Create deterministic demonstration data for cohort-based DM homologation.

    Turma numbers belong independently to each program area. CTE includes Turma 21,
    opened on 03/08/2026. SDS intentionally has no Turma 21.
    """
    cohort_specs = [
        ("CTE", 17, date(2022, 3, 7), 18, "Encerrada"),
        ("CTE", 18, date(2023, 3, 6), 18, "Encerrada"),
        ("CTE", 19, date(2024, 3, 4), 20, "Em andamento"),
        ("CTE", 20, date(2025, 3, 10), 20, "Em andamento"),
        ("CTE", 21, date(2026, 8, 3), 22, "Aberta"),
        ("SDS", 17, date(2022, 4, 4), 16, "Encerrada"),
        ("SDS", 18, date(2023, 4, 3), 18, "Encerrada"),
        ("SDS", 19, date(2024, 4, 8), 18, "Em andamento"),
        ("SDS", 20, date(2025, 4, 7), 20, "Em andamento"),
    ]
    cohorts: list[dict[str, Any]] = []
    students: list[dict[str, Any]] = []
    student_index = 1
    as_of = date(2026, 8, 28)

    for cohort_id, (area_code, number, opening, vacancies, status) in enumerate(cohort_specs, 1):
        cohorts.append({
            "id": cohort_id,
            "area_code": area_code,
            "area_name": DM_AREAS[area_code],
            "cohort_number": number,
            "cohort_key": f"{area_code}-T{number}",
            "cohort_label": f"Turma {number}",
            "opening_date": opening.isoformat(),
            "vacancies_authorized": vacancies,
            "status": status,
            "notes": "Base demonstrativa para homologação do painel por turmas.",
            "is_demo": True,
        })

        # Newest cohort is deliberately smaller because enrollment has just opened.
        if area_code == "CTE" and number == 21:
            count = 8
        else:
            count = max(8, vacancies - RNG.randint(1, 5))

        for position in range(1, count + 1):
            entry = opening
            elapsed_months = (as_of - entry).days / 30.4375
            student_status = "Ativo"
            qualification = None
            defense = None
            scheduled = None
            exit_date = None

            # Old cohorts have defenses and a small number of desligamentos.
            if elapsed_months >= 20:
                roll = RNG.random()
                if roll < 0.67:
                    months = RNG.randint(20, 27)
                    defense_candidate = _add_months_approx(entry, months)
                    if defense_candidate <= as_of:
                        defense = defense_candidate
                        qualification = _add_months_approx(entry, RNG.randint(12, 17))
                        student_status = "Titulado"
                elif roll < 0.76:
                    student_status = "Desligado"
                    exit_date = _add_months_approx(entry, RNG.randint(5, 16))
                elif roll < 0.82:
                    student_status = "Desligado"
                    exit_date = _add_months_approx(entry, RNG.randint(4, 14))

            if student_status == "Ativo":
                if elapsed_months >= 13 and RNG.random() < 0.78:
                    qualification = _add_months_approx(entry, RNG.randint(12, 18))
                    if qualification > as_of:
                        qualification = None
                if elapsed_months >= 22 and RNG.random() < 0.60:
                    scheduled = as_of + timedelta(days=RNG.randint(20, 150))

            area_prefix = "C" if area_code == "CTE" else "S"
            students.append({
                "id": student_index,
                "cohort_id": cohort_id,
                "area_code": area_code,
                "area_name": DM_AREAS[area_code],
                "cohort_number": number,
                "cohort_label": f"Turma {number}",
                "cohort_opening_date": opening.isoformat(),
                "student_code": f"DM{area_prefix}{number:02d}{position:03d}",
                "student_name": f"Aluno demonstrativo {student_index:03d}",
                "entry_date": entry.isoformat(),
                "qualification_date": qualification.isoformat() if qualification else None,
                "defense_date": defense.isoformat() if defense else None,
                "defense_scheduled_date": scheduled.isoformat() if scheduled else None,
                "exit_date": exit_date.isoformat() if exit_date else None,
                "status": student_status,
                "advisor": f"Docente permanente {1 + (position % 6)}",
                "research_line": (
                    "Educação, ciência e inovação" if area_code == "CTE"
                    else "Saúde, território e desigualdades"
                ),
                "notes": "Registro fictício para homologação; não representa aluno real.",
                "is_demo": True,
            })
            student_index += 1
    return cohorts, students


def cohort_import_payloads() -> list[dict[str, Any]]:
    cohorts, _ = build_dm_demo_payloads()
    return [
        {
            "area_code": row["area_code"],
            "cohort_number": row["cohort_number"],
            "opening_date": row["opening_date"],
            "vacancies_authorized": row["vacancies_authorized"],
            "status": row["status"],
            "notes": row["notes"],
            "is_demo": True,
        }
        for row in cohorts
    ]


def student_import_payloads() -> list[dict[str, Any]]:
    _, students = build_dm_demo_payloads()
    return [
        {
            "area_code": row["area_code"],
            "cohort_number": row["cohort_number"],
            "student_code": row["student_code"],
            "student_name": row["student_name"],
            "entry_date": row["entry_date"],
            "qualification_date": row["qualification_date"],
            "defense_date": row["defense_date"],
            "defense_scheduled_date": row["defense_scheduled_date"],
            "exit_date": row["exit_date"],
            "status": row["status"],
            "advisor": row["advisor"],
            "research_line": row["research_line"],
            "notes": row["notes"],
            "is_demo": True,
        }
        for row in students
    ]
