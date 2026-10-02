from __future__ import annotations

import os
from datetime import date
from typing import Any, Iterable

from dm_excel_official import build_dm_excel_official_workbook_bytes
from dm_excel_v2_builder import build_dm_v2_workbook


def dm_excel_official_enabled() -> bool:
    """Return whether the canonical DM export uses Excel Official.

    Excel Official is the normal DM export. Setting the environment flag to
    false is reserved for an explicit emergency rollback to DM V2.
    """
    return os.getenv("DM_EXCEL_OFFICIAL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def selected_dm_excel_engine() -> str:
    return "excel_official" if dm_excel_official_enabled() else "dm_v2"


def export_dm_excel(
    cohorts: Iterable[dict[str, Any]],
    students: Iterable[dict[str, Any]],
    *,
    targets: Iterable[dict[str, Any]] | None = None,
    actions: Iterable[dict[str, Any]] | None = None,
    sync_runs: Iterable[dict[str, Any]] | None = None,
    area_code: str | None = None,
    cohort_id: int | None = None,
    as_of: date | None = None,
    generated_by: str | None = None,
):
    """Generate the canonical DM workbook from the selected production engine."""
    cohort_rows = list(cohorts)
    student_rows = list(students)
    target_rows = list(targets or ())
    action_rows = list(actions or ())
    sync_rows = list(sync_runs or ())

    if selected_dm_excel_engine() == "excel_official":
        return build_dm_excel_official_workbook_bytes(
            cohort_rows,
            student_rows,
            targets=target_rows,
            actions=action_rows,
            sync_runs=sync_rows,
            area_code=area_code,
            cohort_id=cohort_id,
            as_of=as_of,
            generated_by=generated_by,
        )

    return build_dm_v2_workbook(
        cohort_rows,
        student_rows,
        targets=target_rows,
        sync_runs=sync_rows,
        area_code=area_code,
        cohort_id=cohort_id,
        as_of=as_of,
    )


__all__ = [
    "dm_excel_official_enabled",
    "export_dm_excel",
    "selected_dm_excel_engine",
]
