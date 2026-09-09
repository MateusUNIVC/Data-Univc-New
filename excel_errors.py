from __future__ import annotations


class ExcelExportLimitError(ValueError):
    """Raised when a complete export cannot fit inside Excel's physical limits.

    This exception is intentionally user-safe: callers may show its message to
    explain why no partial workbook was generated.
    """
