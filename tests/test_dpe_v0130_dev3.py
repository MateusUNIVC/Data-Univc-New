from __future__ import annotations

import sqlite3

from sqlalchemy import create_engine, text
from pathlib import Path

import pytest

import release_info
from app import app
from models import Base
from schema_version import ensure_local_schema_version

ROOT = Path(__file__).resolve().parents[1]

LEGACY_TABLES = {
    "dpe_operating_results",
    "dpe_budget_execution",
    "dpe_cash_movements",
    "dpe_monthly_revenues",
    "dpe_course_revenues",
    "dpe_expenses",
    "dpe_expense_allocations",
    "dpe_course_cost_snapshots",
}


def test_backend_retirement_migration_remains_in_release_history():
    assert release_info.SCHEMA_VERSION >= 43
    assert (ROOT / "database" / "043_dpe_legacy_backend_retirement_v0130.sql").exists()


def test_legacy_finance_and_v04_modules_are_removed_from_runtime():
    for rel in (
        "dpe_finance_repository.py",
        "dpe_finance_analytics.py",
        "dpe_analytics.py",
        "assets/paineis/Painel_DPE_template.xlsx",
        "assets/modelos/Modelo_DPE_01_Resultado_Operacional.xlsx",
        "assets/modelos/Modelo_DPE_04_Execucao_Orcamentaria.xlsx",
        "assets/modelos/Modelo_DPE_05_Saldo_Operacional_Caixa.xlsx",
    ):
        assert not (ROOT / rel).exists(), rel


def test_legacy_tables_are_not_part_of_sqlalchemy_runtime_metadata():
    tables = set(Base.metadata.tables)
    assert LEGACY_TABLES.isdisjoint(tables)
    assert "dpe_cost_periods" in tables
    assert "dpe_cost_expenses" in tables


def test_legacy_api_routes_are_not_registered():
    paths = {route.path for route in app.routes}
    assert "/api/dpe/{resource}" not in paths
    assert not any(path.startswith("/api/dpe/finance") for path in paths)
    assert "/api/dpe/cost-engine/foundation" in paths
    assert "/api/dpe/cost-engine/analytics" in paths


def test_retirement_migration_archives_before_dropping():
    path = ROOT / "database" / "043_dpe_legacy_backend_retirement_v0130.sql"
    sql = path.read_text(encoding="utf-8")
    assert "create table if not exists public.dpe_legacy_retirement_archive" in sql.lower()
    assert "alter table public.dpe_legacy_retirement_archive enable row level security" in sql.lower()
    first_archive = sql.lower().index("insert into public.dpe_legacy_retirement_archive")
    first_drop = sql.lower().index("drop table if exists public.dpe_expense_allocations")
    assert first_archive < first_drop
    for table in LEGACY_TABLES:
        assert f"'{table}'" in sql
        assert f"drop table if exists public.{table}" in sql.lower()
    assert "values (1, 43, '043_dpe_legacy_backend_retirement_v0130.sql'" in sql.lower()


def test_demo_database_has_current_schema_and_no_operational_legacy_tables():
    path = ROOT / "univc_dpe_demo.db"
    if not path.exists():
        pytest.skip("Pacote de producao nao inclui banco DEMO local.")
    with sqlite3.connect(path) as conn:
        actual = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table'")
        }
        assert LEGACY_TABLES.isdisjoint(actual)
        assert "dpe_legacy_retirement_archive" in actual
        version, migration = conn.execute(
            "select version, migration_name from data_univc_schema_version where id=1"
        ).fetchone()
        assert version == release_info.SCHEMA_VERSION
        assert migration == release_info.SCHEMA_MIGRATION


def test_local_schema_upgrade_archives_nonempty_legacy_rows(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE dpe_monthly_revenues (id INTEGER PRIMARY KEY, directorate_id INTEGER, period TEXT, net_revenue NUMERIC)"))
        conn.execute(text("INSERT INTO dpe_monthly_revenues(id,directorate_id,period,net_revenue) VALUES (7,1,'2026-01',1234.56)"))
        ensure_local_schema_version(conn)
        names = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "dpe_monthly_revenues" not in names
        assert "dpe_legacy_retirement_archive" in names
        archived = conn.execute(text("SELECT source_generation,source_table,source_pk,payload_json FROM dpe_legacy_retirement_archive")).mappings().one()
        assert archived["source_generation"] == "v0.7.7"
        assert archived["source_table"] == "dpe_monthly_revenues"
        assert archived["source_pk"] == 7
        assert '"period":"2026-01"' in archived["payload_json"]
        ledger = conn.execute(text("SELECT version,migration_name FROM data_univc_schema_version WHERE id=1")).one()
        assert ledger[0] == release_info.SCHEMA_VERSION
        assert ledger[1] == release_info.SCHEMA_MIGRATION
