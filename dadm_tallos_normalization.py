from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python 3.9+ in runtime
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception


def _local_timezone():
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/Sao_Paulo")
        except ZoneInfoNotFoundError:
            pass
    # Windows/Python installations without the IANA tzdata package must not
    # prevent the whole Data UNIVC from starting. Brazil has used UTC-03 with no
    # DST since 2019; TALLOS history in this project is contemporary.
    return timezone(timedelta(hours=-3), name="America/Sao_Paulo")


LOCAL_TZ = _local_timezone()
NULL_TEXT = {"", "s/a", "sa", "n/a", "na", "null", "none", "nan", "-", "--"}
TALLOS_NORMALIZATION_VERSION = 4


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "label", "title", "value", "id", "_id"):
            if value.get(key) not in (None, ""):
                text = str(value[key]).strip()
                return text or None
        return None
    text = str(value).strip()
    return None if text.casefold() in NULL_TEXT else (text or None)


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"true", "1", "sim", "yes", "y", "s"}:
        return True
    if text in {"false", "0", "nao", "não", "no", "n"}:
        return False
    return None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
            ):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc)


def parse_duration_seconds(value: Any, *, numeric_unit: str = "seconds") -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or number < 0:
            return None
        if numeric_unit == "milliseconds":
            return number / 1000.0
        if numeric_unit == "minutes":
            return number * 60.0
        if number >= 10_000_000:  # heuristic defensive for explicit ms-like magnitudes
            return number / 1000.0
        return number

    raw = str(value).strip()
    if raw.casefold() in NULL_TEXT:
        return None
    normalized = raw.replace(",", ".")
    try:
        return parse_duration_seconds(float(normalized), numeric_unit=numeric_unit)
    except ValueError:
        pass

    # D.HH:MM:SS, HH:MM:SS or MM:SS
    match = re.fullmatch(r"(?:(\d+)\.)?(\d+):(\d{1,2})(?::(\d{1,2}(?:\.\d+)?))?", normalized)
    if match:
        days = int(match.group(1) or 0)
        a = float(match.group(2))
        b = float(match.group(3))
        c = match.group(4)
        if c is None:
            hours, minutes, seconds = 0.0, a, b
        else:
            hours, minutes, seconds = a, b, float(c)
        return days * 86400 + hours * 3600 + minutes * 60 + seconds

    parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(dias?|d|horas?|h|minutos?|min|m|segundos?|seg|s)", normalized.casefold())
    if parts:
        total = 0.0
        for amount, unit in parts:
            number = float(amount)
            if unit.startswith("dia") or unit == "d":
                total += number * 86400
            elif unit.startswith("hora") or unit == "h":
                total += number * 3600
            elif unit.startswith("min") or unit == "m":
                total += number * 60
            else:
                total += number
        return total
    return None


def department_display(value: Any) -> tuple[str | None, str | None]:
    raw = _text(value)
    if not raw:
        return None, None
    key = raw
    label = raw.replace("-", "_")
    label = re.sub(r"_[0-9a-f]{5,}$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"_\d{5,}$", "", label)
    label = re.sub(r"_+", " ", label).strip()
    if label and label == label.lower():
        label = " ".join(word.capitalize() for word in label.split())
    return key, label or raw


def _local_date(dt: datetime | None) -> date | None:
    return dt.astimezone(LOCAL_TZ).date() if dt else None


def _rating(value: Any) -> int | None:
    """Normalize the TALLOS evaluation score.

    The TALLOS export used for homologation represents missing evaluations as
    ``S/A`` and observed numeric scores on a 1-10 scale. API ``level=0`` is
    therefore treated as *not evaluated* until TALLOS documents otherwise.
    Missing, zero, or non-numeric values remain ``None`` and do not participate
    in AVG/COUNT calculations.
    """
    number = _int(value)
    return number if number is not None and 1 <= number <= 10 else None


def _safe_payload(row: dict) -> dict:
    """Whitelist operacional sem nome/telefone/CPF/CNPJ do cliente."""
    employee = row.get("employee") if isinstance(row.get("employee"), dict) else {}
    customer = row.get("customer") if isinstance(row.get("customer"), dict) else {}
    metrics = row.get("operational_metrics") if isinstance(row.get("operational_metrics"), dict) else {}
    initiation = row.get("initiation_info") if isinstance(row.get("initiation_info"), dict) else {}
    return {
        "id": row.get("id") or row.get("_id") or row.get("report_id"),
        "protocol": row.get("protocol"),
        "employee": {"id": employee.get("id") or employee.get("_id"), "name": employee.get("name")},
        "customer": {"id": customer.get("id") or customer.get("_id"), "channel": customer.get("channel")},
        "to_department": row.get("to_department"),
        "to_tabulation": row.get("to_tabulation"),
        "channel": row.get("channel"),
        "tme": row.get("tme"),
        "tma": row.get("tma"),
        "operational_metrics": {"tmro": metrics.get("tmro"), "tmrc": metrics.get("tmrc")},
        "level": row.get("level"),
        "total_send_messages": row.get("total_send_messages"),
        "total_receive_messages": row.get("total_receive_messages"),
        "initiation_info": {"initiated_by": initiation.get("initiated_by")},
        "transferred": row.get("transferred"),
        "redistribution_count": row.get("redistribution_count"),
        "valid_business_period": row.get("valid_business_period"),
        "sessions_opened": row.get("sessions_opened"),
        "opened": row.get("opened"),
        "closed": row.get("closed"),
        "opened_at": row.get("opened_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "closed_at": row.get("closed_at"),
        "created_at": row.get("created_at"),
    }


def normalize_report(row: dict, *, fallback_date: date) -> dict:
    employee = row.get("employee") if isinstance(row.get("employee"), dict) else {}
    customer = row.get("customer") if isinstance(row.get("customer"), dict) else {}
    initiation = row.get("initiation_info") if isinstance(row.get("initiation_info"), dict) else {}
    metrics = row.get("operational_metrics") if isinstance(row.get("operational_metrics"), dict) else {}
    tme = row.get("tme") if isinstance(row.get("tme"), dict) else {"value": row.get("tme")}
    tma = row.get("tma") if isinstance(row.get("tma"), dict) else {"value": row.get("tma")}

    opened_at = parse_datetime(row.get("opened_at"))
    started_at = parse_datetime(row.get("started_at"))
    finished_at = parse_datetime(row.get("finished_at"))
    closed_at = parse_datetime(row.get("closed_at"))
    created_at = parse_datetime(row.get("created_at"))
    reference_at = started_at or opened_at or created_at or finished_at or closed_at
    reference_date = _local_date(reference_at) or fallback_date

    closed_flag = _bool(row.get("closed"))
    opened_flag = _bool(row.get("opened"))
    if closed_flag is True or closed_at is not None or finished_at is not None:
        status = "finalized"
    elif closed_flag is False or opened_flag is True:
        status = "open"
    else:
        status = "unknown"

    department_key, department_name = department_display(row.get("to_department"))
    channel = _text(row.get("channel")) or _text(customer.get("channel"))
    source_payload = _safe_payload(row)
    source_json = json.dumps(source_payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    # Include the normalization contract version in the hash. If a mapping rule
    # changes (for example the evaluation scale), a re-sync updates existing
    # rows even when the raw TALLOS payload itself did not change.
    source_hash = hashlib.sha256(
        f"normalization:{TALLOS_NORMALIZATION_VERSION}|{source_json}".encode("utf-8")
    ).hexdigest()

    source_id = _text(row.get("id") or row.get("_id") or row.get("report_id"))
    if not source_id:
        stable = "|".join([
            _text(row.get("protocol")) or "",
            _text(employee.get("id") or employee.get("_id")) or "",
            str(reference_at or ""),
            department_key or "",
            _text(row.get("to_tabulation")) or "",
        ])
        source_id = "synthetic:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()

    return {
        "source_id": source_id,
        "protocol": _text(row.get("protocol")),
        "customer_ref": _text(customer.get("id") or customer.get("_id")),
        "employee_id": _text(employee.get("id") or employee.get("_id")),
        "employee_name": _text(employee.get("name")),
        "department_key": department_key,
        "department_name": department_name,
        "channel": channel,
        "tabulation": _text(row.get("to_tabulation")),
        "status": status,
        "rating": _rating(row.get("level")),
        "tme_seconds": parse_duration_seconds(tme.get("value")),
        "tma_seconds": parse_duration_seconds(tma.get("value")),
        "tmro_seconds": parse_duration_seconds(metrics.get("tmro")),
        "tmrc_seconds": parse_duration_seconds(metrics.get("tmrc")),
        "messages_sent": _int(row.get("total_send_messages")) or 0,
        "messages_received": _int(row.get("total_receive_messages")) or 0,
        "initiated_by": _text(initiation.get("initiated_by")),
        "transferred": bool(_bool(row.get("transferred")) or False),
        "redistribution_count": _int(row.get("redistribution_count")) or 0,
        "valid_business_period": _bool(row.get("valid_business_period")),
        "sessions_opened": _int(row.get("sessions_opened")),
        "opened_at": opened_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "closed_at": closed_at,
        "created_at_source": created_at,
        "reference_at": reference_at or datetime.combine(reference_date, time.min, tzinfo=LOCAL_TZ).astimezone(timezone.utc),
        "reference_date": reference_date,
        "month_key": reference_date.strftime("%Y-%m"),
        "source_hash": source_hash,
        "source_payload_json": source_json,
    }
