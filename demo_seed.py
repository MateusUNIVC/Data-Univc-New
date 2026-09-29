from __future__ import annotations

from sqlalchemy import func, select

from dm_demo import cohort_import_payloads, student_import_payloads
from dm_repository import DMRepository
from management_repository import ManagementRepository
from models import Directorate, DmCohort, ManagementMeasurement
from demo_data import dadm_data
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
        "DPE": {"seeded": False, "reason": "Use scripts/seed_dpe_demo.py para a demonstração moderna da DPE v0.13."},
        "DM": seed_dm_demo(db),
    }
