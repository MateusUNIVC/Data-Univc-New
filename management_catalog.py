from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "config" / "management_indicators.json"
MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
SEMESTER_RE = re.compile(r"^(?P<year>\d{4})-SEM(?P<semester>[12])$")
MANAGEMENT_DIRECTORATES = ("DADM", "DPE", "DM")


class ManagementCatalogError(ValueError):
    pass


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManagementCatalogError(f"Catálogo gerencial não encontrado: {CATALOG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ManagementCatalogError(f"Catálogo gerencial inválido: {exc}") from exc
    _validate_catalog(payload)
    return payload


def reload_catalog() -> dict[str, Any]:
    load_catalog.cache_clear()
    return load_catalog()


def _validate_catalog(payload: dict[str, Any]) -> None:
    directorates = payload.get("directorates")
    if not isinstance(directorates, dict):
        raise ManagementCatalogError("O catálogo precisa conter o objeto 'directorates'.")
    codes: set[str] = set()
    for directorate_code, directorate in directorates.items():
        if directorate_code not in MANAGEMENT_DIRECTORATES:
            raise ManagementCatalogError(f"Diretoria não suportada no catálogo: {directorate_code}.")
        periodicity = directorate.get("periodicity")
        if periodicity not in {"monthly", "semester"}:
            raise ManagementCatalogError(f"Periodicidade inválida para {directorate_code}: {periodicity}.")
        indicators = directorate.get("indicators") or []
        if not indicators:
            raise ManagementCatalogError(f"A diretoria {directorate_code} não possui indicadores.")
        for indicator in indicators:
            code = str(indicator.get("code") or "").strip().upper()
            if not code or code in codes:
                raise ManagementCatalogError(f"Código de indicador ausente ou duplicado: {code!r}.")
            codes.add(code)
            if not code.startswith(directorate_code + "-"):
                raise ManagementCatalogError(f"O indicador {code} não pertence à diretoria {directorate_code}.")
            metrics = indicator.get("metrics") or []
            metric_keys = {str(metric.get("key") or "") for metric in metrics}
            if not metrics or indicator.get("primary_metric") not in metric_keys:
                raise ManagementCatalogError(f"Métrica principal inválida em {code}.")
            if indicator.get("periodicity") != periodicity:
                raise ManagementCatalogError(
                    f"Periodicidade de {code} deve coincidir com a diretoria {directorate_code}."
                )
            field_keys = {str(field.get("key") or "") for field in indicator.get("fields") or []}
            for metric in metrics:
                aggregation = metric.get("aggregation")
                if aggregation == "ratio":
                    for key in (metric.get("numerator"), metric.get("denominator")):
                        if key not in field_keys:
                            raise ManagementCatalogError(f"Campo {key!r} ausente para a métrica {metric.get('key')}.")
                if aggregation in {"sum", "weighted_average"} and metric.get("field") not in field_keys:
                    raise ManagementCatalogError(
                        f"Campo {metric.get('field')!r} ausente para a métrica {metric.get('key')}."
                    )


def directorate_spec(code: str) -> dict[str, Any]:
    code = str(code or "").strip().upper()
    try:
        return load_catalog()["directorates"][code]
    except KeyError as exc:
        raise ManagementCatalogError(f"Diretoria gerencial não encontrada: {code}.") from exc


def indicator_specs(directorate_code: str) -> list[dict[str, Any]]:
    return list(directorate_spec(directorate_code).get("indicators") or [])


def indicator_spec(directorate_code: str, indicator_code: str) -> dict[str, Any]:
    indicator_code = str(indicator_code or "").strip().upper()
    for spec in indicator_specs(directorate_code):
        if spec["code"] == indicator_code:
            return spec
    raise ManagementCatalogError(
        f"Indicador {indicator_code!r} não pertence à diretoria {str(directorate_code).upper()}."
    )


def metric_spec(directorate_code: str, indicator_code: str, metric_key: str) -> dict[str, Any]:
    for metric in indicator_spec(directorate_code, indicator_code).get("metrics") or []:
        if metric.get("key") == metric_key:
            return metric
    raise ManagementCatalogError(
        f"Métrica {metric_key!r} não encontrada em {indicator_code}."
    )


def validate_period(directorate_code: str, period: str) -> str:
    period = str(period or "").strip().upper()
    periodicity = directorate_spec(directorate_code)["periodicity"]
    if periodicity == "monthly" and not MONTH_RE.fullmatch(period):
        raise ManagementCatalogError("Use o período mensal no formato AAAA-MM.")
    if periodicity == "semester" and not SEMESTER_RE.fullmatch(period):
        raise ManagementCatalogError("Use o período semestral no formato AAAA-SEM1 ou AAAA-SEM2.")
    return period


def period_sort_key(period: str) -> int:
    text = str(period or "").strip().upper()
    month = MONTH_RE.fullmatch(text)
    if month:
        return int(month.group("year")) * 12 + int(month.group("month")) - 1
    semester = SEMESTER_RE.fullmatch(text)
    if semester:
        return int(semester.group("year")) * 2 + int(semester.group("semester")) - 1
    return -1


def previous_period(directorate_code: str, period: str) -> str:
    period = validate_period(directorate_code, period)
    if MONTH_RE.fullmatch(period):
        year, month = (int(part) for part in period.split("-"))
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        return f"{year:04d}-{month:02d}"
    year = int(period[:4])
    semester = int(period[-1])
    if semester == 1:
        return f"{year - 1:04d}-SEM2"
    return f"{year:04d}-SEM1"


def same_period_previous_year(directorate_code: str, period: str) -> str:
    period = validate_period(directorate_code, period)
    return f"{int(period[:4]) - 1:04d}{period[4:]}"


def default_comparison(directorate_code: str, period: str) -> str:
    spec = directorate_spec(directorate_code)
    policy = spec.get("comparison_policy")
    if policy in {"same_semester_previous_year", "previous_period_and_year_over_year"}:
        return same_period_previous_year(directorate_code, period)
    return previous_period(directorate_code, period)


def all_indicator_codes() -> dict[str, tuple[str, ...]]:
    return {
        code: tuple(item["code"] for item in indicator_specs(code))
        for code in MANAGEMENT_DIRECTORATES
    }


def catalog_payload(directorate_code: str | None = None) -> dict[str, Any]:
    payload = load_catalog()
    if not directorate_code:
        return payload
    code = str(directorate_code).upper()
    return {
        "version": payload.get("version"),
        "directorates": {code: directorate_spec(code)},
    }


def field_keys(spec: dict[str, Any]) -> set[str]:
    return {str(field.get("key")) for field in spec.get("fields") or []}


def dimension_keys(spec: dict[str, Any]) -> set[str]:
    return {str(key) for key in spec.get("dimensions") or []}


def metric_keys(spec: dict[str, Any]) -> set[str]:
    return {str(metric.get("key")) for metric in spec.get("metrics") or []}


def iter_metrics(directorate_code: str) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    for indicator in indicator_specs(directorate_code):
        for metric in indicator.get("metrics") or []:
            yield indicator, metric
