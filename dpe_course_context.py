from __future__ import annotations

import re
import unicodedata
from typing import Any

BASE_CONTEXT_SUFFIX = "-BASE"


def _ascii_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", "_", text).upper()


def normalize_modality(value: Any) -> str:
    """Normalize an academic modality without restricting the DPE to one modality."""
    key = _ascii_key(value)
    aliases = {
        "PRESENCIAL": "PRESENCIAL",
        "EAD": "EAD",
        "A_DISTANCIA": "EAD",
        "DISTANCIA": "EAD",
        "SEMIPRESENCIAL": "SEMIPRESENCIAL",
        "SEMI_PRESENCIAL": "SEMIPRESENCIAL",
        "HIBRIDO": "HIBRIDO",
        "HYBRID": "HIBRIDO",
        "OTHER": "OUTRA",
        "OUTRO": "OUTRA",
        "OUTRA": "OUTRA",
    }
    return aliases.get(key, key or "NAO_INFORMADA")


def default_context_code(product_code: Any) -> str:
    return f"{str(product_code or '').strip().upper()}{BASE_CONTEXT_SUFFIX}"


def location_of(offering: dict[str, Any]) -> str | None:
    value = offering.get("pole_name") or offering.get("unit_name") or offering.get("campus")
    return str(value).strip() if value else None


def is_default_context(offering: Any, product: Any | None = None) -> bool:
    if isinstance(offering, dict):
        explicit = offering.get("is_default_context")
        if explicit is not None:
            return bool(explicit)
        if str(offering.get("context_kind") or "").upper() == "BASE":
            return True
        code = str(offering.get("code") or "").upper()
        product_code = str((product or {}).get("code") or "").upper() if isinstance(product, dict) else ""
        return bool(product_code and code == default_context_code(product_code))

    explicit = getattr(offering, "is_default_context", None)
    if explicit is not None:
        return bool(explicit)
    code = str(getattr(offering, "code", "") or "").upper()
    product_code = str(getattr(product, "code", "") or "").upper() if product is not None else ""
    return bool(product_code and code == default_context_code(product_code))


def context_descriptor(product: dict[str, Any], offering: dict[str, Any]) -> list[str]:
    if is_default_context(offering, product):
        return []
    parts: list[str] = []
    modality = normalize_modality(offering.get("modality"))
    source_modality = normalize_modality(product.get("source_modality")) if product.get("source_modality") else ""
    if modality and modality != "NAO_INFORMADA" and (not source_modality or modality != source_modality):
        parts.append(modality.title() if modality not in {"EAD"} else modality)
    if offering.get("shift"):
        parts.append(str(offering["shift"]))
    location = location_of(offering)
    if location:
        parts.append(location)
    if not parts and offering.get("code"):
        parts.append(str(offering["code"]))
    return parts


def context_label(product: dict[str, Any], offering: dict[str, Any]) -> str:
    name = str(product.get("name") or "Curso").strip()
    parts = [name, *context_descriptor(product, offering)]
    return " · ".join(part for part in parts if part)


def snapshot_context_label(snapshot: dict[str, Any]) -> str:
    product = dict(snapshot.get("product") or {})
    offering = dict(snapshot.get("offering") or {})
    return context_label(product, offering)
