from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from dm_repository import DMRepository
from models import Directorate, DmCohort, DmStudent
from security import AuthorizationContext, DirectorateScope
import sei_student_dates

ROOT = Path(__file__).resolve().parents[1]


def _repo_with_students(count: int = 7):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    directorate = Directorate(code="DM", name="Diretoria de Mestrado", active=True)
    db.add(directorate)
    db.commit()
    db.refresh(directorate)
    user = AuthorizationContext(
        user_id="dm-queue-test",
        email="dm-queue@test.local",
        full_name="DM Queue Test",
        role="editor",
        directorate_id=directorate.id,
        directorate_code="DM",
        directorate_name=directorate.name,
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code="DM",
        directorate_name=directorate.name,
        can_write=True,
        is_home=True,
    )
    cohort = DmCohort(
        directorate_id=directorate.id,
        area_code="CTE",
        area_name="Ciência, Tecnologia e Educação",
        cohort_number=17,
        status="Em andamento",
        is_demo=False,
    )
    db.add(cohort)
    db.flush()
    students = []
    for index in range(count):
        row = DmStudent(
            directorate_id=directorate.id,
            cohort_id=cohort.id,
            student_code=f"M{index + 1:03d}",
            student_name=f"Aluno {index + 1:03d}",
            status="Ativo",
            is_demo=False,
        )
        db.add(row)
        students.append(row)
    db.commit()
    for row in students:
        db.refresh(row)
    return engine, db, DMRepository(db, scope), cohort, students


def test_persistent_queue_claims_small_batches_and_finishes_with_error_state():
    engine, db, repo, cohort, students = _repo_with_students(7)
    try:
        run = repo.create_sei_student_refresh_run(cohort_id=cohort.id)
        assert run["total"] == 7
        assert run["pending"] == 7
        assert run["credentials_persisted"] is False

        first = repo.claim_sei_student_refresh_batch(run["id"], batch_size=4)
        assert len(first["items"]) == 4
        assert first["run"]["running"] == 4
        assert first["run"]["pending"] == 3

        processed_ids = [item["student_id"] for item in first["items"]]
        applied = {
            "items": [
                {"student_id": processed_ids[0], "ok": True, "updated": True},
                {"student_id": processed_ids[1], "ok": True, "updated": False},
                {"student_id": processed_ids[2], "ok": True, "updated": False},
                {"student_id": processed_ids[3], "ok": False, "error_type": "lookup", "error": "SEI indisponível"},
            ]
        }
        progress = repo.finish_sei_student_refresh_batch(
            run["id"],
            queue_item_ids=[item["queue_item_id"] for item in first["items"]],
            applied_result=applied,
            processed_student_ids=processed_ids,
        )
        assert progress["completed"] == 3
        assert progress["failed"] == 1
        assert progress["pending"] == 3
        assert progress["remaining"] == 3
        assert progress["status"] == "IN_PROGRESS"

        second = repo.claim_sei_student_refresh_batch(run["id"], batch_size=10)
        assert len(second["items"]) == 3
        processed_ids_2 = [item["student_id"] for item in second["items"]]
        progress = repo.finish_sei_student_refresh_batch(
            run["id"],
            queue_item_ids=[item["queue_item_id"] for item in second["items"]],
            applied_result={"items": [{"student_id": value, "ok": True} for value in processed_ids_2]},
            processed_student_ids=processed_ids_2,
        )
        assert progress["processed"] == 7
        assert progress["remaining"] == 0
        assert progress["completed"] == 6
        assert progress["failed"] == 1
        assert progress["status"] == "COMPLETED_WITH_ERRORS"
        assert progress["completed_at"]
    finally:
        db.close()
        engine.dispose()


def test_unprocessed_claimed_items_return_to_pending_without_consuming_attempt():
    engine, db, repo, cohort, students = _repo_with_students(5)
    try:
        run = repo.create_sei_student_refresh_run(cohort_id=cohort.id)
        claimed = repo.claim_sei_student_refresh_batch(run["id"], batch_size=4)
        processed = [claimed["items"][0]["student_id"]]
        progress = repo.finish_sei_student_refresh_batch(
            run["id"],
            queue_item_ids=[item["queue_item_id"] for item in claimed["items"]],
            applied_result={"items": [{"student_id": processed[0], "ok": True}]},
            processed_student_ids=processed,
        )
        assert progress["completed"] == 1
        assert progress["pending"] == 4
        assert progress["running"] == 0
    finally:
        db.close()
        engine.dispose()


def test_lookup_respects_budget_between_students(monkeypatch):
    class FakeBot:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def login(self, username, password):
            assert username == "user"
            assert password == "pass"

        def consultar(self, student_name, *, expected_student_code=None):
            return {"student_name": student_name, "student_code": expected_student_code}

    monotonic_values = iter([0.0, 10.0, 10.0])
    monkeypatch.setattr(sei_student_dates, "SEIStudentDatesBot", FakeBot)
    monkeypatch.setattr(sei_student_dates.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        sei_student_dates,
        "choose_course_link",
        lambda result, target: {
            "student_id": target.student_id,
            "student_code": target.student_code,
            "student_name": target.student_name,
            "ok": True,
            "course_start_date": None,
            "defense_date": None,
        },
    )
    targets = [
        {"student_id": 1, "student_code": "1", "student_name": "A"},
        {"student_id": 2, "student_code": "2", "student_name": "B"},
        {"student_id": 3, "student_code": "3", "student_name": "C"},
    ]
    result = sei_student_dates.lookup_student_course_dates(
        "user",
        "pass",
        targets,
        max_seconds=5,
        request_timeout_seconds=12,
    )
    assert [item["student_id"] for item in result["items"]] == [1]
    assert result["deferred_student_ids"] == [2, 3]
    assert result["credentials_persisted"] is False


def test_queue_api_frontend_and_schema_contracts_are_present():
    router = (ROOT / "dm_router.py").read_text(encoding="utf-8")
    js = (ROOT / "static/js/dm.js").read_text(encoding="utf-8")
    migration = (ROOT / "database/050_dm_sei_student_refresh_queue_v0130.sql").read_text(encoding="utf-8")
    release = (ROOT / "release_info.py").read_text(encoding="utf-8")

    assert '@router.post("/api/dm/sei/refresh-runs")' in router
    assert '@router.get("/api/dm/sei/refresh-runs/{run_id}")' in router
    assert '@router.post("/api/dm/sei/refresh-runs/{run_id}/batch")' in router
    assert "DM_SEI_REFRESH_BATCH_SIZE" in router
    assert "DM_SEI_REFRESH_BATCH_BUDGET_SECONDS" in router
    assert "len(targets) > DM_SEI_REFRESH_BATCH_SIZE" in router
    assert "/api/dm/sei/refresh-runs" in js
    assert "while (run && !terminal.has(run.status)" in js
    assert "Cada lote é salvo antes do próximo começar" in js
    assert "usuario:username, senha:password" in js
    assert "password" not in migration.lower()
    assert "senha" not in migration.lower()
    assert "dm_sei_student_refresh_runs" in migration
    assert "dm_sei_student_refresh_items" in migration
    assert "SCHEMA_VERSION = 50" in release
    assert 'SCHEMA_MIGRATION = "050_dm_sei_student_refresh_queue_v0130.sql"' in release
