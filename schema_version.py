from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from release_info import SCHEMA_MIGRATION, SCHEMA_VERSION

SCHEMA_TABLE = "data_univc_schema_version"


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
