from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import release_info
from dadm_tallos_analytics import rating_audit_payload
from dadm_tallos_normalization import TALLOS_NORMALIZATION_VERSION, normalize_report
from dadm_tallos_repository import DADMTallosRepository
from models import Base, DADMTallosAttendance, Directorate
from security import AuthorizationContext, DirectorateScope

ROOT = Path(__file__).resolve().parents[1]


def _row(level=10, *, raw_marker: str | None = None) -> dict:
    row = {
        "id": "ticket-1",
        "protocol": "P-1",
        "employee": {"id": "op-1", "name": "Operador"},
        "customer": {"id": "opaque-1", "channel": "whatsapp"},
        "to_department": "secretaria",
        "to_tabulation": "resolvido",
        "channel": "whatsapp",
        "level": level,
        "opened_at": "2026-09-20T12:00:00Z",
        "closed_at": "2026-09-20T12:05:00Z",
        "closed": True,
    }
    if raw_marker is not None:
        # Whitelisted operational source detail. Because ``closed`` is already
        # true, toggling ``opened`` does not change the normalized status, but
        # it must still participate in the source fingerprint.
        row["opened"] = raw_marker == "B"
    return row


def _repo(db: Session) -> tuple[Directorate, DADMTallosRepository]:
    directorate = Directorate(code="DADM", name="Diretoria Administrativa")
    db.add(directorate)
    db.commit()
    db.refresh(directorate)
    user = AuthorizationContext(
        user_id="tallos-compact-test",
        email="tallos@test.local",
        full_name="Tallos Compact Test",
        role="editor",
        directorate_id=directorate.id,
        directorate_code="DADM",
        directorate_name=directorate.name,
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code="DADM",
        directorate_name=directorate.name,
        can_write=True,
        is_home=True,
    )
    return directorate, DADMTallosRepository(db, scope)


def test_normalizer_hashes_raw_payload_but_does_not_persist_it():
    first = normalize_report(_row(10, raw_marker="A"), fallback_date=date(2026, 9, 20))
    second = normalize_report(_row(10, raw_marker="B"), fallback_date=date(2026, 9, 20))

    assert TALLOS_NORMALIZATION_VERSION == 5
    assert "source_payload_json" not in first
    assert "source_payload_json" not in second
    assert len(first["source_hash"]) == 64
    assert len(second["source_hash"]) == 64
    assert first["source_hash"] != second["source_hash"]
    # The analytical contract remains identical; only the raw source changed.
    for key in ("rating", "rating_source_state", "rating_source_value", "normalization_version"):
        assert first[key] == second[key]


def test_repository_persists_only_empty_payload_placeholder_and_remains_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        directorate, repo = _repo(db)
        run = repo.create_sync_run(date(2026, 9, 1), date(2026, 9, 30), trigger="manual", requested_by="test")
        payload = normalize_report(_row(9), fallback_date=date(2026, 9, 20))

        first = repo.upsert_batch([payload], sync_run_id=run.id)
        stored = db.scalar(select(DADMTallosAttendance).where(DADMTallosAttendance.directorate_id == directorate.id))
        assert stored is not None
        assert stored.source_payload_json == "{}"
        assert first == {"inserted": 1, "updated": 0, "unchanged": 0}

        second = repo.upsert_batch([normalize_report(_row(9), fallback_date=date(2026, 9, 20))], sync_run_id=run.id)
        db.refresh(stored)
        assert second == {"inserted": 0, "updated": 0, "unchanged": 1}
        assert stored.source_payload_json == "{}"


def test_rating_audit_is_identical_before_and_after_payload_cleanup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        directorate, _repo_instance = _repo(db)
        levels = (10, 0, "S/A", "abc")
        for index, level in enumerate(levels, start=1):
            payload = normalize_report(_row(level), fallback_date=date(2026, 9, 20))
            payload["source_id"] = f"ticket-{index}"
            # Simulate the pre-053 historical state: bulky JSON is still there.
            payload["source_payload_json"] = '{"level": %s, "large": "%s"}' % (
                ('"%s"' % level) if isinstance(level, str) else level,
                "x" * 2048,
            )
            db.add(DADMTallosAttendance(directorate_id=directorate.id, **payload))
        db.commit()

        before = rating_audit_payload(db, directorate.id, date(2026, 9, 1), date(2026, 9, 30))
        for row in db.scalars(select(DADMTallosAttendance)).all():
            row.source_payload_json = "{}"
        db.commit()
        after = rating_audit_payload(db, directorate.id, date(2026, 9, 1), date(2026, 9, 30))

    for key in ("rows", "valid_count", "valid_average", "raw_zero_count", "raw_missing_count", "raw_other_count", "contract"):
        assert after[key] == before[key]


def test_release_53_retires_historical_payload_and_keeps_legacy_column_as_placeholder():
    migration = (ROOT / "database/053_dadm_tallos_payload_retirement_v0130.sql").read_text(encoding="utf-8")
    normalization = (ROOT / "dadm_tallos_normalization.py").read_text(encoding="utf-8")
    analytics = (ROOT / "dadm_tallos_analytics.py").read_text(encoding="utf-8")

    assert release_info.SCHEMA_VERSION == 53
    assert release_info.SCHEMA_MIGRATION == "053_dadm_tallos_payload_retirement_v0130.sql"
    assert "SET source_payload_json = '{}'" in migration
    assert "rating_source_state IS NULL" in migration
    assert "normalization_version IS NULL" in migration
    assert "VALUES (1, 53" in migration
    assert '"source_payload_json": source_json' not in normalization
    assert "DADMTallosAttendance.source_payload_json" not in analytics
