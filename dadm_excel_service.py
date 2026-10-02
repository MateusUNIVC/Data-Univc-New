from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from dadm_excel_official import build_dadm_excel_official_workbook_bytes
from dadm_v2_report import build_dadm_v2_report


def dadm_excel_official_enabled() -> bool:
    """Return whether the canonical DADM export uses Excel Official.

    Default remains false so the release can land before production parity is
    approved. Rollback is one environment-variable change back to false.
    """
    return os.getenv("DADM_EXCEL_OFFICIAL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def selected_dadm_excel_engine() -> str:
    return "excel_official" if dadm_excel_official_enabled() else "dadm_v2"


def export_dadm_excel(
    db: Session,
    directorate_id: int,
    from_month: str | None = None,
    to_month: str | None = None,
    *,
    department: str | None = None,
    employee: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    tabulation: str | None = None,
    allowed_departments: tuple[str, ...] | None = None,
    generated_by: str | None = None,
):
    """Generate the canonical DADM workbook from the selected engine."""
    if selected_dadm_excel_engine() == "excel_official":
        return build_dadm_excel_official_workbook_bytes(
            db,
            directorate_id,
            from_month,
            to_month,
            department=department,
            employee=employee,
            channel=channel,
            status=status,
            tabulation=tabulation,
            allowed_departments=allowed_departments,
            generated_by=generated_by,
            authorization_scope=("DADM",),
        )

    workbook, _ = build_dadm_v2_report(
        db,
        directorate_id,
        from_month,
        to_month,
        department=department,
        employee=employee,
        channel=channel,
        status=status,
        tabulation=tabulation,
        allowed_departments=allowed_departments,
    )
    return workbook


__all__ = [
    "dadm_excel_official_enabled",
    "export_dadm_excel",
    "selected_dadm_excel_engine",
]
