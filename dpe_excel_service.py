from __future__ import annotations

import os
from typing import Any, Mapping

from dpe_excel_modern import build_dpe_operational_workbook
from dpe_excel_official import build_dpe_excel_official_artifact_from_payload


def dpe_excel_official_enabled() -> bool:
    """Return whether the canonical DPE export uses Excel Official.

    Excel Official is the normal DPE export. Setting the environment flag to
    false is reserved for an explicit emergency rollback to DPE Modern.
    """
    return os.getenv("DPE_EXCEL_OFFICIAL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def selected_dpe_excel_engine() -> str:
    return "excel_official" if dpe_excel_official_enabled() else "dpe_modern"


def export_dpe_excel(payload: Mapping[str, Any], *, generated_by: str | None = None):
    """Generate the canonical DPE workbook from the selected production engine."""
    if selected_dpe_excel_engine() == "excel_official":
        return build_dpe_excel_official_artifact_from_payload(
            payload,
            generated_by=generated_by,
            authorization_scope=("DPE",),
        ).to_bytes()
    return build_dpe_operational_workbook(payload)


__all__ = ["dpe_excel_official_enabled", "export_dpe_excel", "selected_dpe_excel_engine"]
