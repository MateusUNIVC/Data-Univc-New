from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from .contract import Scalar


@dataclass(frozen=True, slots=True)
class SnapshotContext:
    export_id: str
    generated_at: datetime
    generated_by: str | None
    directorate: str
    authorization_scope: tuple[str, ...]
    system_version: str
    schema_version: str | int
    initial_filters: Mapping[str, Scalar] = field(default_factory=dict)
    available_scope: Mapping[str, tuple[Scalar, ...]] = field(default_factory=dict)
    minimum_period: str | None = None
    maximum_period: str | None = None
    payload_hash: str | None = None


@dataclass(frozen=True, slots=True)
class AdapterInput:
    snapshot_context: SnapshotContext
    authorized_data: Mapping[str, Any]
    initial_state: Mapping[str, Scalar] = field(default_factory=dict)
