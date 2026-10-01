from __future__ import annotations

from pathlib import Path

from tests.test_part17_dm_sei_persistent_batch_queue import _repo_with_students

ROOT = Path(__file__).resolve().parents[1]


def test_dm_queue_can_pause_resume_and_retry_failures():
    engine, db, repo, cohort, students = _repo_with_students(5)
    try:
        run = repo.create_sei_student_refresh_run(cohort_id=cohort.id)
        claimed = repo.claim_sei_student_refresh_batch(run["id"], batch_size=2)
        assert claimed["run"]["running"] == 2

        paused = repo.pause_sei_student_refresh_run(run["id"])
        assert paused["status"] == "PAUSED"
        assert paused["running"] == 2
        assert paused["pending"] == 3

        # The already claimed bounded batch may still finish in another request.
        ids = [item["student_id"] for item in claimed["items"]]
        paused_after_batch = repo.finish_sei_student_refresh_batch(
            run["id"],
            queue_item_ids=[item["queue_item_id"] for item in claimed["items"]],
            applied_result={"items": [{"student_id": value, "ok": True} for value in ids]},
            processed_student_ids=ids,
        )
        assert paused_after_batch["status"] == "PAUSED"
        assert paused_after_batch["completed"] == 2

        resumed = repo.resume_sei_student_refresh_run(run["id"])
        assert resumed["status"] == "IN_PROGRESS"

        claimed = repo.claim_sei_student_refresh_batch(run["id"], batch_size=2)
        ids = [item["student_id"] for item in claimed["items"]]
        progressed = repo.finish_sei_student_refresh_batch(
            run["id"],
            queue_item_ids=[item["queue_item_id"] for item in claimed["items"]],
            applied_result={
                "items": [
                    {"student_id": ids[0], "ok": True},
                    {"student_id": ids[1], "ok": False, "error_type": "lookup", "error": "Falha simulada"},
                ]
            },
            processed_student_ids=ids,
        )
        assert progressed["completed"] == 3
        assert progressed["failed"] == 1

        failed_items = repo.list_sei_student_refresh_items(run["id"], status="FAILED")
        assert len(failed_items) == 1
        assert failed_items[0]["student_name"]
        assert failed_items[0]["last_error"] == "Falha simulada"

        retried = repo.retry_failed_sei_student_refresh_run(run["id"])
        assert retried["failed"] == 0
        assert retried["pending"] == 2
        assert retried["remaining"] == 2
    finally:
        db.close()
        engine.dispose()


def test_dm_queue_recent_runs_are_listed_newest_first():
    engine, db, repo, cohort, students = _repo_with_students(2)
    try:
        first = repo.create_sei_student_refresh_run(cohort_id=cohort.id)
        second = repo.create_sei_student_refresh_run(student_ids=[students[0].id])
        rows = repo.list_sei_student_refresh_runs(limit=10)
        assert [row["id"] for row in rows[:2]] == [second["id"], first["id"]]
    finally:
        db.close()
        engine.dispose()


def test_dm_queue_ux_and_button_hardening_contracts():
    js = (ROOT / "static/js/dm.js").read_text(encoding="utf-8")
    html = (ROOT / "templates/dm.html").read_text(encoding="utf-8")
    router = (ROOT / "dm_router.py").read_text(encoding="utf-8")
    migration = (ROOT / "database/051_dm_sei_refresh_queue_controls_v0130.sql").read_text(encoding="utf-8")

    assert "bindEvents();\n  try" in js
    assert "document.body.dataset.dmEventsBound" in js
    assert "$('#studentsPrev')?.addEventListener" in js
    assert "$('#cohortForm')?.addEventListener" in js
    assert "seiRefreshPauseRequested" in js
    assert "data-sei-run-continue" in js
    assert "data-sei-run-retry" in js
    assert "showSeiRefreshRunErrors" in js
    assert 'id="seiQueueTable"' in html
    assert 'id="pauseSeiRefresh"' in html
    assert '@router.post("/api/dm/sei/refresh-runs/{run_id}/pause")' in router
    assert '@router.post("/api/dm/sei/refresh-runs/{run_id}/resume")' in router
    assert '@router.post("/api/dm/sei/refresh-runs/{run_id}/retry-failed")' in router
    assert '@router.get("/api/dm/sei/refresh-runs/{run_id}/items")' in router
    assert "PAUSED" in migration
    assert "password" not in migration.lower()
    assert "senha" not in migration.lower()
