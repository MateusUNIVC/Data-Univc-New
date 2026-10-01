from pathlib import Path

import release_info

ROOT = Path(__file__).resolve().parents[1]


def test_storage_audit_is_read_only_and_covers_compaction_health():
    sql = (ROOT / "scripts/tallos_storage_audit.sql").read_text(encoding="utf-8")
    required = [
        "pg_total_relation_size('public.dadm_tallos_attendances')",
        "pg_indexes_size('public.dadm_tallos_attendances')",
        "rows_with_payload",
        "rating_source_state IS NULL",
        "normalization_version IS NULL",
        "missing_source_hash",
        "n_dead_tup",
        "last_autovacuum",
        "COUNT(DISTINCT month_key)",
    ]
    for token in required:
        assert token in sql
    upper = sql.upper()
    for destructive in ("DELETE FROM", "UPDATE PUBLIC", "TRUNCATE", "DROP TABLE", "VACUUM FULL"):
        assert destructive not in upper


def test_default_maintenance_uses_safe_vacuum_and_full_requires_confirmation():
    vacuum_sql = (ROOT / "scripts/tallos_storage_vacuum.sql").read_text(encoding="utf-8")
    shell = (ROOT / "scripts/tallos_storage_maintenance.sh").read_text(encoding="utf-8")

    assert "VACUUM (ANALYZE, VERBOSE) public.dadm_tallos_attendances" in vacuum_sql
    assert "VACUUM FULL" not in vacuum_sql.upper()
    assert 'CONFIRM_TALLOS_VACUUM_FULL' in shell
    assert '!= "YES"' in shell
    assert "VACUUM (FULL, ANALYZE, VERBOSE) public.dadm_tallos_attendances" in shell
    assert "audit|vacuum|vacuum-full" in shell


def test_part22_keeps_schema_53_and_documents_operational_finish():
    doc = (ROOT / "docs/DADM_TALLOS_STORAGE_MAINTENANCE_PART22.md").read_text(encoding="utf-8")
    assert release_info.SCHEMA_VERSION == 53
    assert release_info.SCHEMA_MIGRATION == "053_dadm_tallos_payload_retirement_v0130.sql"
    assert "rows_with_payload = 0" in doc
    assert "ACCESS EXCLUSIVE" in doc
    assert "schema 53" in doc
