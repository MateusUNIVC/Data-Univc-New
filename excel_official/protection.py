from __future__ import annotations

from typing import Iterable

from openpyxl.cell.cell import Cell
from openpyxl.styles import Protection
from openpyxl.worksheet.worksheet import Worksheet


def lock_cell(cell: Cell) -> Cell:
    cell.protection = Protection(locked=True, hidden=cell.protection.hidden)
    return cell


def unlock_cell(cell: Cell) -> Cell:
    cell.protection = Protection(locked=False, hidden=cell.protection.hidden)
    return cell


def lock_cells(cells: Iterable[Cell]) -> None:
    for cell in cells:
        lock_cell(cell)


def unlock_cells(cells: Iterable[Cell]) -> None:
    for cell in cells:
        unlock_cell(cell)


def lock_range(worksheet: Worksheet, cell_range: str) -> None:
    for row in worksheet[cell_range]:
        lock_cells(row)


def unlock_range(worksheet: Worksheet, cell_range: str) -> None:
    for row in worksheet[cell_range]:
        unlock_cells(row)


def protect_sheet(worksheet: Worksheet, *, password: str | None = None) -> None:
    """Enable worksheet protection after individual editable cells are unlocked.

    Worksheet protection is an accidental-editing guard, not a security boundary.
    Authorization must be enforced before data enters the workbook.
    """
    worksheet.protection.sheet = True
    if password:
        worksheet.protection.set_password(password)


def unprotect_sheet(worksheet: Worksheet) -> None:
    worksheet.protection.sheet = False


__all__ = [
    "lock_cell",
    "lock_cells",
    "lock_range",
    "protect_sheet",
    "unlock_cell",
    "unlock_cells",
    "unlock_range",
    "unprotect_sheet",
]
