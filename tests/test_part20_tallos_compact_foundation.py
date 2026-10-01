from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import release_info
from dadm_tallos_analytics import rating_audit_payload
from dadm_tallos_normalization import TALLOS_NORMALIZATION_VERSION, normalize_report
from models import Base, DADMTallosAttendance, Directorate

ROOT = Path(__file__).resolve().parents[1]


def _row(level):
    return {
        "id": f"ticket-{str(level)}",
        "protocol": f"P-{str(level)}",
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


def test_normalizer_emits_compact_rating_contract_without_losing_hash_input():
    valid = normalize_report(_row(10), fallback_date=date(2026, 9, 20))
    zero = normalize_report(_row(0), fallback_date=date(2026, 9, 20))
    missing = normalize_report(_row("S/A"), fallback_date=date(2026, 9, 20))
    invalid = normalize_report(_row("abc"), fallback_date=date(2026, 9, 20))

    assert TALLOS_NORMALIZATION_VERSION == 5
    assert (valid["rating"], valid["rating_source_state"], valid["rating_source_value"]) == (10, "valid", "10")
    assert (zero["rating"], zero["rating_source_state"], zero["rating_source_value"]) == (None, "zero", "0")
    assert (missing["rating"], missing["rating_source_state"], missing["rating_source_value"]) == (None, "missing", "S/A")
    assert (invalid["rating"], invalid["rating_source_state"], invalid["rating_source_value"]) == (None, "invalid", "abc")
    assert valid["normalization_version"] == 5
    assert len(valid["source_hash"]) == 64
    # Part 21 retires raw payload persistence while preserving the compact contract.
    assert "source_payload_json" not in valid


def test_rating_audit_uses_compact_columns_not_source_payload_json():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        directorate = Directorate(code="DADM", name="Diretoria Administrativa")
        db.add(directorate)
        db.commit()
        db.refresh(directorate)

        payloads = [
            normalize_report(_row(10), fallback_date=date(2026, 9, 20)),
            normalize_report(_row(0), fallback_date=date(2026, 9, 20)),
            normalize_report(_row("S/A"), fallback_date=date(2026, 9, 20)),
            normalize_report(_row("abc"), fallback_date=date(2026, 9, 20)),
        ]
        for index, payload in enumerate(payloads, start=1):
            payload["source_id"] = f"ticket-{index}"
            # Deliberately erase the JSON. The audit must still remain correct.
            payload["source_payload_json"] = "{}"
            db.add(DADMTallosAttendance(directorate_id=directorate.id, **payload))
        db.commit()

        result = rating_audit_payload(
            db,
            directorate.id,
            date(2026, 9, 1),
            date(2026, 9, 30),
        )

    assert result["rows"] == 4
    assert result["valid_count"] == 1
    assert result["valid_average"] == 10
    assert result["raw_zero_count"] == 1
    assert result["raw_missing_count"] == 1
    assert result["raw_other_count"] == 1
    assert result["contract"]["source"] == "compact_columns"


def test_release_declares_compact_contract_migration_and_payload_is_not_cleaned_yet():
    migration = (ROOT / "database/052_dadm_tallos_compact_rating_contract_v0130.sql").read_text(encoding="utf-8")
    analytics = (ROOT / "dadm_tallos_analytics.py").read_text(encoding="utf-8")
    model = (ROOT / "models.py").read_text(encoding="utf-8")

    assert release_info.SCHEMA_VERSION >= 52
    assert (ROOT / "database/052_dadm_tallos_compact_rating_contract_v0130.sql").exists()
    assert "rating_source_state" in migration
    assert "rating_source_value" in migration
    assert "normalization_version" in migration
    assert "source_payload_json = '{}'" not in migration
    assert "DADMTallosAttendance.source_payload_json" not in analytics
    assert "rating_source_state" in model
