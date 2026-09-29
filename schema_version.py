from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from release_info import SCHEMA_MIGRATION, SCHEMA_VERSION
from dpe_domain import LEGACY_MANAGEMENT_METRIC_MAP
from dpe_course_context import default_context_code, normalize_modality

SCHEMA_TABLE = "data_univc_schema_version"


DPE_RETIRED_LOCAL_TABLES: tuple[tuple[str, str], ...] = (
    ("v0.4", "dpe_operating_results"),
    ("v0.4", "dpe_budget_execution"),
    ("v0.4", "dpe_cash_movements"),
    ("v0.7.7", "dpe_monthly_revenues"),
    ("v0.7.7", "dpe_course_revenues"),
    ("v0.7.7", "dpe_expenses"),
    ("v0.7.7", "dpe_expense_allocations"),
    ("v0.7.7", "dpe_course_cost_snapshots"),
)


def retire_local_dpe_legacy_tables(connection: Connection) -> None:
    """Archive and remove retired DPE tables from local SQLite databases.

    Production uses migration 043. Local launchers do not replay PostgreSQL SQL
    migrations, so this mirrors the same retirement semantics before advancing
    the local schema ledger.
    """
    if connection.dialect.name != "sqlite":
        return
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    legacy = [(generation, table) for generation, table in DPE_RETIRED_LOCAL_TABLES if table in existing]

    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS dpe_legacy_retirement_archive ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "source_generation TEXT NOT NULL, "
        "source_table TEXT NOT NULL, "
        "source_pk INTEGER NOT NULL, "
        "payload_json TEXT NOT NULL, "
        "archived_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "UNIQUE(source_table, source_pk))"
    ))
    if not legacy:
        return
    for generation, table in legacy:
        rows = connection.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
        for row in rows:
            source_pk = int(row.get("id") or 0)
            payload = json.dumps(dict(row), ensure_ascii=False, default=str, separators=(",", ":"))
            connection.execute(
                text(
                    "INSERT INTO dpe_legacy_retirement_archive "
                    "(source_generation, source_table, source_pk, payload_json) "
                    "VALUES (:generation, :table, :source_pk, :payload) "
                    "ON CONFLICT(source_table, source_pk) DO NOTHING"
                ),
                {"generation": generation, "table": table, "source_pk": source_pk, "payload": payload},
            )
    # Child table first; SQLite may enforce the old foreign key.
    for _generation, table in reversed(legacy):
        connection.execute(text(f'DROP TABLE IF EXISTS "{table}"'))


def migrate_local_dpe_management_domain(connection: Connection) -> None:
    """Archive/remap legacy DPE targets and actions for local SQLite databases."""
    if connection.dialect.name != "sqlite":
        return
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required = {"directorates", "management_indicator_targets", "management_indicator_actions"}
    if not required.issubset(tables):
        return
    dpe_id = connection.execute(text("SELECT id FROM directorates WHERE code='DPE' LIMIT 1")).scalar()
    if dpe_id is None:
        return
    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS dpe_domain_legacy_management_archive ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "source_table TEXT NOT NULL, source_pk INTEGER NOT NULL, payload_json TEXT NOT NULL, "
        "archived_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(source_table, source_pk))"
    ))
    for table in ("management_indicator_targets", "management_indicator_actions"):
        rows = connection.execute(
            text(f"SELECT * FROM {table} WHERE directorate_id=:dpe_id AND indicator_code IN ('DPE-01','DPE-02','DPE-03')"),
            {"dpe_id": dpe_id},
        ).mappings().all()
        for row in rows:
            payload = json.dumps(dict(row), ensure_ascii=False, default=str, separators=(",", ":"))
            connection.execute(
                text("INSERT INTO dpe_domain_legacy_management_archive(source_table,source_pk,payload_json) "
                     "VALUES (:table,:pk,:payload) ON CONFLICT(source_table,source_pk) DO NOTHING"),
                {"table": table, "pk": int(row["id"]), "payload": payload},
            )
    # Targets have a uniqueness constraint. Resolve an existing canonical row first.
    target_rows = connection.execute(
        text("SELECT id,indicator_code,metric_key,dimension_key,valid_from FROM management_indicator_targets "
             "WHERE directorate_id=:dpe_id AND indicator_code IN ('DPE-01','DPE-02','DPE-03')"),
        {"dpe_id": dpe_id},
    ).mappings().all()
    for row in target_rows:
        mapped = LEGACY_MANAGEMENT_METRIC_MAP.get((row["indicator_code"], row["metric_key"]))
        if not mapped or (row["indicator_code"], row["metric_key"]) == ("DPE-03", "payroll_on_revenue_3m_pct"):
            continue
        new_code, new_metric = mapped
        exists = connection.execute(
            text("SELECT id FROM management_indicator_targets WHERE directorate_id=:dpe_id "
                 "AND indicator_code=:code AND metric_key=:metric AND dimension_key=:dim AND valid_from=:valid LIMIT 1"),
            {"dpe_id": dpe_id, "code": new_code, "metric": new_metric, "dim": row["dimension_key"], "valid": row["valid_from"]},
        ).scalar()
        if exists is not None:
            connection.execute(text("DELETE FROM management_indicator_targets WHERE id=:id"), {"id": row["id"]})
        else:
            connection.execute(
                text("UPDATE management_indicator_targets SET indicator_code=:code, metric_key=:metric WHERE id=:id"),
                {"code": new_code, "metric": new_metric, "id": row["id"]},
            )
    action_rows = connection.execute(
        text("SELECT id,indicator_code,metric_key FROM management_indicator_actions "
             "WHERE directorate_id=:dpe_id AND indicator_code IN ('DPE-01','DPE-02','DPE-03')"),
        {"dpe_id": dpe_id},
    ).mappings().all()
    for row in action_rows:
        mapped = LEGACY_MANAGEMENT_METRIC_MAP.get((row["indicator_code"], row["metric_key"])) if row["metric_key"] else None
        if not mapped:
            continue
        connection.execute(
            text("UPDATE management_indicator_actions SET indicator_code=:code, metric_key=:metric WHERE id=:id"),
            {"code": mapped[0], "metric": mapped[1], "id": row["id"]},
        )


def ensure_local_dpe_course_base_contexts(connection: Connection) -> None:
    """Backfill internal base contexts for existing DPE courses on local SQLite."""
    if connection.dialect.name != "sqlite":
        return
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if not {"dpe_academic_products", "dpe_academic_offerings"}.issubset(tables):
        return

    has_courses = "courses" in tables
    if has_courses:
        rows = connection.execute(text(
            "SELECT p.id,p.directorate_id,p.code,p.active,p.valid_from,p.valid_to,c.modality "
            "FROM dpe_academic_products p LEFT JOIN courses c ON c.id=p.source_course_id"
        )).mappings().all()
    else:
        rows = connection.execute(text(
            "SELECT id,directorate_id,code,active,valid_from,valid_to,NULL AS modality "
            "FROM dpe_academic_products"
        )).mappings().all()

    for row in rows:
        code = default_context_code(row["code"])
        exists = connection.execute(
            text("SELECT id FROM dpe_academic_offerings WHERE directorate_id=:directorate_id AND upper(code)=upper(:code) LIMIT 1"),
            {"directorate_id": row["directorate_id"], "code": code},
        ).scalar()
        if exists is not None:
            continue
        connection.execute(
            text(
                "INSERT INTO dpe_academic_offerings "
                "(directorate_id,product_id,code,modality,shift,campus,unit_name,pole_name,external_key,active,valid_from,valid_to,notes,created_by) "
                "VALUES (:directorate_id,:product_id,:code,:modality,NULL,NULL,NULL,NULL,NULL,:active,:valid_from,:valid_to,:notes,:created_by)"
            ),
            {
                "directorate_id": row["directorate_id"],
                "product_id": row["id"],
                "code": code,
                "modality": normalize_modality(row.get("modality")),
                "active": bool(row["active"]),
                "valid_from": row["valid_from"],
                "valid_to": row["valid_to"],
                "notes": "Contexto-base automático do curso. Não representa um contexto separado.",
                "created_by": "migration:045-local",
            },
        )


def migrate_local_dpe_revenue_ledger(connection: Connection) -> None:
    """Seed default revenue categories and backfill historical net revenue on local SQLite."""
    if connection.dialect.name != "sqlite":
        return
    tables=set(inspect(connection).get_table_names())
    required={"directorates","dpe_revenue_categories","dpe_revenue_entries","dpe_cost_offering_economics"}
    if not required.issubset(tables):
        return
    dpe_id=connection.execute(text("SELECT id FROM directorates WHERE code='DPE' LIMIT 1")).scalar()
    if dpe_id is None:
        return
    defaults=(
        ("COURSE_REVENUE","Receita de curso","COURSE"),
        ("ROOM_RENTAL","Aluguel de salas","INSTITUTIONAL"),
        ("SPORTS_RENTAL","Aluguel de quadras","INSTITUTIONAL"),
        ("STRUCTURE_USE","Utilização de estrutura","BOTH"),
        ("BRANCH_USE","Utilização de filial","BOTH"),
        ("SERVICES","Serviços","BOTH"),
        ("EVENTS","Eventos","BOTH"),
        ("OTHER","Outras receitas","BOTH"),
    )
    for code,name,scope in defaults:
        connection.execute(text("INSERT INTO dpe_revenue_categories(directorate_id,code,name,scope,active,system,created_by) VALUES(:d,:c,:n,:s,1,1,'migration:046-local') ON CONFLICT(directorate_id,code) DO NOTHING"),{"d":dpe_id,"c":code,"n":name,"s":scope})
    cat_id=connection.execute(text("SELECT id FROM dpe_revenue_categories WHERE directorate_id=:d AND code='COURSE_REVENUE'"),{"d":dpe_id}).scalar()
    economics_columns={row["name"] for row in inspect(connection).get_columns("dpe_cost_offering_economics")}
    if "net_revenue" not in economics_columns:
        return
    rows=connection.execute(text("SELECT id,directorate_id,period_id,period_offering_id,net_revenue FROM dpe_cost_offering_economics WHERE directorate_id=:d AND net_revenue IS NOT NULL"),{"d":dpe_id}).mappings().all()
    for row in rows:
        ref=f"ECONOMICS:{row['id']}"
        exists=connection.execute(text("SELECT id FROM dpe_revenue_entries WHERE directorate_id=:d AND source_reference=:r LIMIT 1"),{"d":dpe_id,"r":ref}).scalar()
        if exists is None:
            connection.execute(text("INSERT INTO dpe_revenue_entries(directorate_id,period_id,period_offering_id,category_id,description,amount,source_type,source_reference,notes,created_by,updated_by) VALUES(:d,:p,:o,:c,'Receita do curso',:a,'MIGRATION',:r,'Migrado da receita líquida histórica na adoção do ledger simplificado.','migration:046-local','migration:046-local')"),{"d":row['directorate_id'],"p":row['period_id'],"o":row['period_offering_id'],"c":cat_id,"a":row['net_revenue'],"r":ref})


def migrate_local_dpe_expense_scope(connection: Connection) -> None:
    """Add/backfill the DPE expense treatment field on existing local SQLite bases."""
    if connection.dialect.name != "sqlite":
        return
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "dpe_cost_expenses" not in tables:
        return
    columns = {row["name"] for row in inspector.get_columns("dpe_cost_expenses")}
    if "expense_scope" not in columns:
        connection.execute(text(
            "ALTER TABLE dpe_cost_expenses ADD COLUMN expense_scope VARCHAR(20) DEFAULT 'SHARED'"
        ))
    # Existing DIRECT allocations are semantically direct; every other historical
    # expense remains shared until a user explicitly marks it institutional.
    if "dpe_allocation_rules" in tables:
        connection.execute(text(
            "UPDATE dpe_cost_expenses SET expense_scope='DIRECT' "
            "WHERE allocation_rule_id IN (SELECT id FROM dpe_allocation_rules WHERE driver_type='DIRECT')"
        ))
    connection.execute(text(
        "UPDATE dpe_cost_expenses SET expense_scope='SHARED' "
        "WHERE expense_scope IS NULL OR trim(expense_scope)=''"
    ))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_dpe_cost_expense_scope "
        "ON dpe_cost_expenses(directorate_id, period_id, expense_scope, status)"
    ))


def migrate_local_dpe_teacher_profiles(connection: Connection) -> None:
    """Backfill DPE teacher profiles and monthly relationship type on SQLite."""
    if connection.dialect.name != "sqlite":
        return
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required = {"directorates", "teachers", "dpe_teacher_profiles", "dpe_cost_period_teachers"}
    if not required.issubset(tables):
        return
    dpe_id = connection.execute(text("SELECT id FROM directorates WHERE code='DPE' LIMIT 1")).scalar()
    if dpe_id is None:
        return
    columns = {row["name"] for row in inspector.get_columns("dpe_cost_period_teachers")}
    if "relationship_type" not in columns:
        connection.execute(text(
            "ALTER TABLE dpe_cost_period_teachers ADD COLUMN relationship_type VARCHAR(30) DEFAULT 'UNSPECIFIED'"
        ))
    evidence_ids: set[int] = set()
    evidence_ids.update(int(row[0]) for row in connection.execute(
        text("SELECT DISTINCT teacher_id FROM dpe_cost_period_teachers WHERE directorate_id=:d"), {"d": dpe_id}
    ).all())
    if "dpe_teacher_aliases" in tables:
        evidence_ids.update(int(row[0]) for row in connection.execute(
            text("SELECT DISTINCT teacher_id FROM dpe_teacher_aliases")
        ).all())
    for teacher_id in sorted(evidence_ids):
        connection.execute(text(
            "INSERT INTO dpe_teacher_profiles "
            "(directorate_id,teacher_id,default_relationship_type,active,notes,created_by,updated_by) "
            "VALUES (:d,:t,'UNSPECIFIED',1,'Perfil criado automaticamente a partir de uso historico na DPE.','migration:048-local','migration:048-local') "
            "ON CONFLICT(directorate_id,teacher_id) DO NOTHING"
        ), {"d": dpe_id, "t": teacher_id})
    connection.execute(text(
        "UPDATE dpe_cost_period_teachers SET relationship_type='UNSPECIFIED' "
        "WHERE relationship_type IS NULL OR trim(relationship_type)=''"
    ))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_dpe_cost_period_teacher_relationship "
        "ON dpe_cost_period_teachers(directorate_id, period_id, relationship_type)"
    ))


@dataclass(frozen=True)
class SchemaStatus:
    expected: int
    current: int | None
    compatible: bool
    tracked: bool
    migration: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "current": self.current,
            "compatible": self.compatible,
            "tracked": self.tracked,
            "migration": self.migration,
        }


def schema_version_required() -> bool:
    explicit = os.getenv("REQUIRE_SCHEMA_VERSION")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("ENVIRONMENT", "").strip().lower() in {"prod", "production"}


def get_schema_status(connection: Connection) -> SchemaStatus:
    inspector = inspect(connection)
    if not inspector.has_table(SCHEMA_TABLE):
        return SchemaStatus(
            expected=SCHEMA_VERSION,
            current=None,
            compatible=False,
            tracked=False,
            migration=None,
        )

    row = connection.execute(
        text(
            f"SELECT version, migration_name FROM {SCHEMA_TABLE} "
            "WHERE id = 1"
        )
    ).mappings().first()
    if not row:
        return SchemaStatus(
            expected=SCHEMA_VERSION,
            current=None,
            compatible=False,
            tracked=True,
            migration=None,
        )

    current = int(row["version"])
    return SchemaStatus(
        expected=SCHEMA_VERSION,
        current=current,
        compatible=current == SCHEMA_VERSION,
        tracked=True,
        migration=str(row.get("migration_name") or "") or None,
    )


def ensure_local_schema_version(connection: Connection) -> None:
    """Create/update the schema ledger for local SQLite bootstrap only.

    Production must apply the numbered SQL migration explicitly; this helper is
    intentionally used only by scripts/init_local.py.
    """
    retire_local_dpe_legacy_tables(connection)
    migrate_local_dpe_management_domain(connection)
    ensure_local_dpe_course_base_contexts(connection)
    migrate_local_dpe_revenue_ledger(connection)
    migrate_local_dpe_expense_scope(connection)
    migrate_local_dpe_teacher_profiles(connection)
    connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} ("
            "id INTEGER PRIMARY KEY, "
            "version INTEGER NOT NULL, "
            "migration_name VARCHAR(255) NOT NULL, "
            "applied_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )
    dialect = connection.dialect.name
    if dialect == "sqlite":
        connection.execute(
            text(
                f"INSERT INTO {SCHEMA_TABLE} (id, version, migration_name, applied_at) "
                "VALUES (1, :version, :migration, CURRENT_TIMESTAMP) "
                "ON CONFLICT(id) DO UPDATE SET "
                "version = excluded.version, migration_name = excluded.migration_name, "
                "applied_at = CURRENT_TIMESTAMP"
            ),
            {"version": SCHEMA_VERSION, "migration": SCHEMA_MIGRATION},
        )
    else:
        raise RuntimeError("ensure_local_schema_version is only for SQLite local bootstrap")
