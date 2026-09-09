from __future__ import annotations

from sqlalchemy import func, select

from dm_demo import cohort_import_payloads, student_import_payloads
from dm_repository import DMRepository
from management_repository import ManagementRepository
from dpe_finance_repository import DPEFinanceRepository
from models import Course, Directorate, DmCohort, DPEMonthlyRevenue, ManagementMeasurement
from demo_data import dadm_data, dpe_data
from security import DirectorateScope, UserContext


def _scope(db, code: str) -> DirectorateScope:
    row = db.scalar(select(Directorate).where(Directorate.code == code))
    if not row:
        raise RuntimeError(f"Diretoria {code} não cadastrada.")
    user = UserContext(
        user_id="demo-local",
        email="demo.local@univc.invalid",
        full_name="Carga demonstrativa local",
        role="admin",
        directorate_id=row.id,
        directorate_code=code,
        directorate_name=row.name,
    )
    return DirectorateScope(
        user=user,
        directorate_id=row.id,
        directorate_code=code,
        directorate_name=row.name,
        can_write=True,
        is_home=True,
    )


def seed_dadm_demo(db) -> dict:
    scope = _scope(db, "DADM")
    existing = db.scalar(
        select(func.count(ManagementMeasurement.id)).where(
            ManagementMeasurement.directorate_id == scope.directorate_id,
            ManagementMeasurement.indicator_code.like("DADM-%"),
        )
    ) or 0
    if existing:
        return {"seeded": False, "reason": "DADM já possui medições", "measurements": int(existing)}

    rows, targets, actions = dadm_data()
    repo = ManagementRepository(db, scope)
    result = repo.bulk_upsert_measurements(rows)
    for target in targets:
        repo.save_target(target)
    for action in actions:
        repo.save_action(action)
    return {"seeded": True, "measurements": result.get("total", len(rows)), "targets": len(targets), "actions": len(actions)}


def seed_dpe_demo(db) -> dict:
    scope = _scope(db, "DPE")
    existing = db.scalar(
        select(func.count(ManagementMeasurement.id)).where(
            ManagementMeasurement.directorate_id == scope.directorate_id,
            ManagementMeasurement.indicator_code.like("DPE-%"),
        )
    ) or 0
    if existing:
        return {"seeded": False, "reason": "DPE já possui medições", "measurements": int(existing)}

    rows, targets, actions = dpe_data()
    repo = ManagementRepository(db, scope)
    result = repo.bulk_upsert_measurements(rows)
    for target in targets:
        repo.save_target(target)
    for action in actions:
        repo.save_action(action)
    return {"seeded": True, "measurements": result.get("total", len(rows)), "targets": len(targets), "actions": len(actions)}


def seed_dpe_finance_demo(db) -> dict:
    """v0.7.7 financial foundation demo.

    The institutional revenue intentionally remains only partially distributed
    to DTNH/DCS courses, representing EAD, hybrid, technical, master's and
    other revenue streams outside the current presencial course catalog.
    """
    scope = _scope(db, "DPE")
    existing = db.scalar(
        select(func.count(DPEMonthlyRevenue.id)).where(
            DPEMonthlyRevenue.directorate_id == scope.directorate_id
        )
    ) or 0
    if existing:
        return {"seeded": False, "reason": "DPE financeira já possui receitas", "months": int(existing)}

    courses = db.execute(
        select(Course, Directorate)
        .join(Directorate, Directorate.id == Course.directorate_id)
        .where(Directorate.code.in_(("DTNH", "DCS")), Course.active.is_(True))
        .order_by(Directorate.code, Course.name)
    ).all()
    if not courses:
        return {"seeded": False, "reason": "Catálogo acadêmico ainda vazio", "months": 0}

    repo = DPEFinanceRepository(db, scope)
    periods = [
        "2025-09", "2025-10", "2025-11", "2025-12",
        "2026-01", "2026-02", "2026-03", "2026-04",
        "2026-05", "2026-06", "2026-07", "2026-08",
    ]
    course_count = len(courses)
    # Stable weights create different course sizes without implying real data.
    raw_weights = [1.0 + (index % 5) * 0.18 for index in range(course_count)]
    total_weight = sum(raw_weights)

    expense_count = 0
    allocation_count = 0
    for month_index, period in enumerate(periods):
        revenue = 4_900_000 + month_index * 42_000 + ((month_index % 3) - 1) * 75_000
        repo.upsert_monthly_revenue({
            "period": period,
            "net_revenue": revenue,
            "validated": True,
            "notes": "DADO FICTÍCIO · fundação financeira v0.7.7",
        })

        # Only 68% is intentionally distributed to current presencial courses.
        presencial_pool = revenue * 0.68
        for (course, _directorate), weight in zip(courses, raw_weights):
            course_revenue = presencial_pool * weight / total_weight
            repo.upsert_course_revenue({
                "period": period,
                "course_id": course.id,
                "allocated_revenue": round(course_revenue, 2),
                "notes": "DADO FICTÍCIO · distribuição opcional da receita presencial",
            })

        # Shared faculty payroll is one expense, then analytically allocated to courses.
        faculty_payroll = 1_480_000 + month_index * 8_500
        faculty_pool = faculty_payroll * 0.82
        faculty_allocations = [
            {"course_id": course.id, "allocated_amount": round(faculty_pool * weight / total_weight, 2)}
            for (course, _), weight in zip(courses, raw_weights)
        ]
        repo.create_expense({
            "period": period,
            "description": "Folha docente consolidada",
            "amount": faculty_payroll,
            "expense_kind": "PAYROLL",
            "payroll_group": "FACULTY",
            "payroll_nature": "SALARY",
            "validated": True,
            "allocations": faculty_allocations,
            "notes": "DADO FICTÍCIO · despesa existe uma única vez e é rateada aos cursos",
        })
        expense_count += 1
        allocation_count += len(faculty_allocations)

        repo.create_expense({
            "period": period,
            "description": "Encargos e provisões docentes",
            "amount": 395_000 + month_index * 2_000,
            "expense_kind": "PAYROLL",
            "payroll_group": "FACULTY",
            "payroll_nature": "CHARGES",
            "validated": True,
        })
        repo.create_expense({
            "period": period,
            "description": "Folha administrativa",
            "amount": 685_000 + month_index * 3_500,
            "expense_kind": "PAYROLL",
            "payroll_group": "ADMINISTRATIVE",
            "payroll_nature": "SALARY",
            "validated": True,
        })
        repo.create_expense({
            "period": period,
            "description": "Encargos e provisões administrativas",
            "amount": 205_000 + month_index * 1_500,
            "expense_kind": "PAYROLL",
            "payroll_group": "ADMINISTRATIVE",
            "payroll_nature": "PROVISIONS",
            "validated": True,
        })
        expense_count += 3

        # Shared operational expense allocated partly to courses; remainder stays institutional.
        electricity = 168_000 + (month_index % 4) * 7_500
        electricity_pool = electricity * 0.60
        electricity_allocations = [
            {"course_id": course.id, "allocated_amount": round(electricity_pool / course_count, 2)}
            for course, _ in courses
        ]
        repo.create_expense({
            "period": period,
            "description": "Energia elétrica e utilidades",
            "amount": electricity,
            "category": "OPERATIONAL",
            "validated": True,
            "allocations": electricity_allocations,
            "notes": "DADO FICTÍCIO · rateio parcial entre cursos",
        })
        expense_count += 1
        allocation_count += len(electricity_allocations)

        for description, amount, category in (
            ("Serviços terceirizados e manutenção", 285_000 + month_index * 2_500, "OPERATIONAL"),
            ("Despesas administrativas gerais", 310_000 + month_index * 2_000, "ADMINISTRATIVE"),
            ("Despesas financeiras", 82_000 + (month_index % 3) * 4_000, "FINANCIAL"),
        ):
            repo.create_expense({
                "period": period,
                "description": description,
                "amount": amount,
                "category": category,
                "validated": True,
                "notes": "DADO FICTÍCIO",
            })
            expense_count += 1

        repo.create_expense({
            "period": period,
            "description": "Equipamentos e melhorias de infraestrutura",
            "amount": 135_000 + month_index * 2_000,
            "category": "OPERATIONAL",
            "is_capex": True,
            "validated": True,
            "notes": "DADO FICTÍCIO · CAPEX não entra no índice de cobertura",
        })
        expense_count += 1

        # Course total remains a reconciliation reference. It never rolls up to
        # the institutional expense total, avoiding payroll double counting.
        for (course, _directorate), weight in zip(courses, raw_weights):
            allocated_faculty = faculty_pool * weight / total_weight
            allocated_energy = electricity_pool / course_count
            reported = round(allocated_faculty + allocated_energy + (38_000 * weight), 2)
            faculty_detail = round(allocated_faculty, 2)
            energy_detail = round(allocated_energy, 2)
            # Fecha o detalhamento exatamente no total informado. Com um número
            # diferente de cursos, arredondar as três parcelas isoladamente pode
            # somar R$ 0,01 acima do total e invalidar a própria carga demo.
            other_detail = round(reported - faculty_detail - energy_detail, 2)
            repo.upsert_course_cost({
                "period": period,
                "course_id": course.id,
                "reported_total_cost": reported,
                "details": [
                    {"description": "Custo docente alocado", "amount": faculty_detail},
                    {"description": "Utilidades rateadas", "amount": energy_detail},
                    {"description": "Outros custos gerenciais", "amount": other_detail},
                ],
                "notes": "DADO FICTÍCIO · custo gerencial informado para reconciliação",
            })

    return {
        "seeded": True,
        "months": len(periods),
        "courses": course_count,
        "expenses": expense_count,
        "allocations": allocation_count,
        "course_revenue_share": 68,
    }


def seed_dm_demo(db) -> dict:
    scope = _scope(db, "DM")
    existing = db.scalar(
        select(func.count(DmCohort.id)).where(DmCohort.directorate_id == scope.directorate_id)
    ) or 0
    if existing:
        return {"seeded": False, "reason": "DM já possui turmas", "cohorts": int(existing)}

    repo = DMRepository(db, scope)
    cohorts = cohort_import_payloads()
    students = student_import_payloads()
    cohort_result = repo.bulk_upsert_cohorts(cohorts)
    student_result = repo.bulk_upsert_students(students)
    return {
        "seeded": True,
        "cohorts": cohort_result.get("total", len(cohorts)),
        "students": student_result.get("total", len(students)),
    }


def seed_operational_demo(db) -> dict:
    return {
        "DADM": seed_dadm_demo(db),
        "DPE": seed_dpe_demo(db),
        "DPE_FINANCE": seed_dpe_finance_demo(db),
        "DM": seed_dm_demo(db),
    }
