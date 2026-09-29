from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import release_info
from dpe_domain import LEGACY_MANAGEMENT_METRIC_MAP, domain_payload
from management_catalog import indicator_spec, reload_catalog
from management_service import ManagementValidationError
from schema_version import ensure_local_schema_version

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CODES = {"DPE-RESULT", "DPE-REVENUE", "DPE-EXPENSE", "DPE-TEACHING", "DPE-ALLOCATION"}


def test_release_keeps_domain_consolidation_contract_after_schema_44():
    assert release_info.APP_VERSION.startswith("0.13.0")
    assert release_info.SCHEMA_VERSION >= 44


def test_domain_contract_has_single_canonical_vocabulary():
    payload = domain_payload()
    assert payload["legacy_measurement_contract"]["status"] == "compatibility_only"
    groups = {item["code"] for item in payload["management_groups"]}
    assert groups == CANONICAL_CODES
    entities = {item["key"] for item in payload["entities"]}
    assert {"period", "course", "revenue", "expense", "teacher", "allocation_run", "result", "target", "action_plan"}.issubset(entities)
    assert [item["code"] for item in payload["period_states"]] == ["DRAFT", "REVIEW", "CALCULATED", "CLOSED"]


def test_management_catalog_exposes_canonical_and_marks_legacy():
    catalog = reload_catalog()["directorates"]["DPE"]["indicators"]
    by_code = {item["code"]: item for item in catalog}
    assert CANONICAL_CODES.issubset(by_code)
    for code in ("DPE-01", "DPE-02", "DPE-03"):
        assert by_code[code]["legacy"] is True
        assert by_code[code]["targetable"] is False
        assert by_code[code]["actionable"] is False
    assert indicator_spec("DPE", "DPE-RESULT")["primary_metric"] == "institutional_margin_pct"


def test_legacy_mapping_does_not_guess_three_month_payroll_equivalence():
    assert ("DPE-03", "payroll_on_revenue_3m_pct") not in LEGACY_MANAGEMENT_METRIC_MAP


def test_migration_archives_before_remapping():
    sql = (ROOT / "database" / "044_dpe_domain_consolidation_v0130.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists public.dpe_domain_legacy_management_archive" in sql
    assert "alter table public.dpe_domain_legacy_management_archive enable row level security" in sql
    assert sql.index("insert into public.dpe_domain_legacy_management_archive") < sql.index("update public.management_indicator_targets")
    assert "dpe-result" in sql and "dpe-expense" in sql and "dpe-teaching" in sql
    assert "values (1, 44, '044_dpe_domain_consolidation_v0130.sql'" in sql


def test_local_schema_upgrade_archives_and_remaps_management_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'domain.sqlite'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE directorates (id INTEGER PRIMARY KEY, code TEXT)"))
        conn.execute(text("INSERT INTO directorates(id,code) VALUES (9,'DPE')"))
        conn.execute(text("CREATE TABLE management_indicator_targets (id INTEGER PRIMARY KEY, directorate_id INTEGER, indicator_code TEXT, metric_key TEXT, dimension_key TEXT, valid_from TEXT)"))
        conn.execute(text("CREATE TABLE management_indicator_actions (id INTEGER PRIMARY KEY, directorate_id INTEGER, indicator_code TEXT, metric_key TEXT)"))
        conn.execute(text("INSERT INTO management_indicator_targets VALUES (1,9,'DPE-01','net_margin_pct','ABC','2026-01')"))
        conn.execute(text("INSERT INTO management_indicator_actions VALUES (2,9,'DPE-02','coverage_index')"))
        ensure_local_schema_version(conn)
        target = conn.execute(text("SELECT indicator_code,metric_key FROM management_indicator_targets WHERE id=1")).one()
        action = conn.execute(text("SELECT indicator_code,metric_key FROM management_indicator_actions WHERE id=2")).one()
        assert target == ("DPE-RESULT", "course_margin_pct")
        assert action == ("DPE-RESULT", "coverage_index")
        archived = conn.execute(text("SELECT source_table,source_pk,payload_json FROM dpe_domain_legacy_management_archive ORDER BY source_table")).mappings().all()
        assert len(archived) == 2
        assert all(json.loads(row["payload_json"])["indicator_code"].startswith("DPE-0") for row in archived)
        ledger = conn.execute(text("SELECT version,migration_name FROM data_univc_schema_version WHERE id=1")).one()
        assert ledger == (release_info.SCHEMA_VERSION, release_info.SCHEMA_MIGRATION)
