from __future__ import annotations

import re
import unicodedata

from openpyxl import Workbook
from openpyxl.workbook.defined_name import DefinedName

_INVALID_NAME_CHAR = re.compile(r"[^A-Za-z0-9_]")
_MULTI_UNDERSCORE = re.compile(r"_+")
_A1_LIKE = re.compile(r"^[A-Za-z]{1,3}[1-9][0-9]*$")
_R1C1_LIKE = re.compile(r"^R[1-9][0-9]*C[1-9][0-9]*$", re.IGNORECASE)


def defined_name_token(value: str, *, prefix: str) -> str:
    """Return a stable Excel-safe defined-name token.

    Contract/user-facing codes stay library-neutral. This helper is the only
    place where they are translated into Excel defined names.
    """
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    normalized = _INVALID_NAME_CHAR.sub("_", normalized.upper())
    normalized = _MULTI_UNDERSCORE.sub("_", normalized).strip("_")
    if not normalized:
        raise ValueError(f"Nao foi possivel gerar nome definido a partir de {value!r}.")
    name = f"{prefix}_{normalized}"
    if _A1_LIKE.fullmatch(name) or _R1C1_LIKE.fullmatch(name):
        name = f"_{name}"
    return name[:255]


def parameter_defined_name(parameter_code: str) -> str:
    return defined_name_token(parameter_code, prefix="P")


def support_list_defined_name(parameter_code: str) -> str:
    return defined_name_token(parameter_code, prefix="LST")


def _defined_name_keys(workbook: Workbook) -> set[str]:
    return {str(name).casefold() for name in workbook.defined_names.keys()}


def add_defined_name(workbook: Workbook, name: str, attr_text: str) -> DefinedName:
    if name.casefold() in _defined_name_keys(workbook):
        raise ValueError(f"Nome definido Excel ja existe: {name!r}.")
    defined = DefinedName(name, attr_text=attr_text)
    workbook.defined_names.add(defined)
    return defined


__all__ = [
    "add_defined_name",
    "defined_name_token",
    "parameter_defined_name",
    "support_list_defined_name",
]
