from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from ..context import AdapterInput
from ..contract import (
    ActionPlanRowSource,
    ActionPlanRowSpec,
    ActionPlanSpec,
    AdapterCapabilities,
    ChartRole,
    ChartSpec,
    ChartType,
    ColumnDataType,
    ColumnSpec,
    DashboardSpec,
    DatasetSpec,
    DimensionSpec,
    DomainSheetSpec,
    IdentitySpec,
    InitialStateSpec,
    KpiSpec,
    LimitationSpec,
    MatrixMetricOptionSpec,
    MatrixSpec,
    MetricAggregation,
    MetricBinding,
    MetricSpec,
    MetricUnit,
    ParameterSpec,
    QualityCheckSpec,
    QualitySeverity,
    QualitySpec,
    SheetRole,
    SnapshotSpec,
    TargetBindingSpec,
    TechnicalSpec,
    WorkbookSpec,
)
from .base import DirectorateAdapter


DADM_METRICS = {
    "attendances": "dadm.attendances",
    "finalization": "dadm.finalization_rate",
    "open": "dadm.open_attendances",
    "tme": "dadm.tme_avg_minutes",
    "tma": "dadm.tma_avg_minutes",
    "rating": "dadm.rating_avg",
    "rating_coverage": "dadm.rating_coverage",
    "transfer_rate": "dadm.transfer_rate",
}

DADM_COMPARISON_METRICS = {
    "attendances": "dadm.previous.attendances",
    "tme": "dadm.previous.tme_avg_minutes",
    "tma": "dadm.previous.tma_avg_minutes",
    "rating": "dadm.previous.rating_avg",
    "rating_coverage": "dadm.previous.rating_coverage",
}

_DADM_TARGET_METRIC_KEYS = {
    DADM_METRICS["tme"]: "tme_avg_seconds",
    DADM_METRICS["tma"]: "tma_avg_seconds",
    DADM_METRICS["rating"]: "rating_avg",
    DADM_METRICS["rating_coverage"]: "rating_coverage_pct",
}


@dataclass(frozen=True, slots=True)
class DADMAdapterError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _month_order(value: str) -> int:
    text = _text(value)
    try:
        return int(text[:4]) * 12 + int(text[5:7]) - 1
    except (ValueError, TypeError):
        return 0


def _dimension_value(value: Any, fallback: str) -> str:
    text = _text(value)
    return text or fallback


def _period_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    values = {_text(row.get("period")) for row in payload.get("cube", ()) if _text(row.get("period"))}
    return tuple(
        {"period": period, "label": period, "sort_order": _month_order(period)}
        for period in sorted(values, key=lambda item: (_month_order(item), item))
    )


def _department_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in payload.get("cube", ()):
        key = _dimension_value(raw.get("department"), "(sem departamento)")
        label = _dimension_value(raw.get("department_name"), key)
        rows.setdefault(key, {"department": key, "department_name": label})
    return tuple(
        {**row, "sort_order": index}
        for index, row in enumerate(sorted(rows.values(), key=lambda item: (item["department_name"].casefold(), item["department"])), 1)
    )


def _employee_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in payload.get("cube", ()):
        employee = _dimension_value(raw.get("employee"), "(sem operador)")
        department = _dimension_value(raw.get("department"), "(sem departamento)")
        label = _dimension_value(raw.get("employee_name"), employee)
        rows.setdefault((department, employee), {
            "department": department,
            "employee": employee,
            "employee_name": label,
        })
    return tuple(
        {**row, "sort_order": index}
        for index, row in enumerate(sorted(rows.values(), key=lambda item: (item["department"].casefold(), item["employee_name"].casefold(), item["employee"])), 1)
    )


def _simple_dimension_rows(payload: Mapping[str, Any], key: str, fallback: str) -> tuple[dict[str, Any], ...]:
    values = sorted({_dimension_value(row.get(key), fallback) for row in payload.get("cube", ())}, key=str.casefold)
    return tuple({key: value, "label": value, "sort_order": index} for index, value in enumerate(values, 1))


def _cube_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = []
    for raw in payload.get("cube", ()):
        period = _text(raw.get("period"))
        if not period:
            continue
        rows.append({
            "period": period,
            "department": _dimension_value(raw.get("department"), "(sem departamento)"),
            "department_name": _dimension_value(raw.get("department_name"), _dimension_value(raw.get("department"), "(sem departamento)")),
            "employee": _dimension_value(raw.get("employee"), "(sem operador)"),
            "employee_name": _dimension_value(raw.get("employee_name"), _dimension_value(raw.get("employee"), "(sem operador)")),
            "channel": _dimension_value(raw.get("channel"), "(sem canal)"),
            "status": _dimension_value(raw.get("status"), "unknown"),
            "tabulation": _dimension_value(raw.get("tabulation"), "(sem tabulação)"),
            "attendances": _as_int(raw.get("attendances")),
            "finalized": _as_int(raw.get("finalized")),
            "open": _as_int(raw.get("open")),
            "tme_sum_minutes": _as_float(raw.get("tme_sum_minutes")) or 0.0,
            "tme_count": _as_int(raw.get("tme_count")),
            "tma_sum_minutes": _as_float(raw.get("tma_sum_minutes")) or 0.0,
            "tma_count": _as_int(raw.get("tma_count")),
            "rating_sum": _as_float(raw.get("rating_sum")) or 0.0,
            "rating_count": _as_int(raw.get("rating_count")),
            "transferred": _as_int(raw.get("transferred")),
            "messages_sent": _as_int(raw.get("messages_sent")),
            "messages_received": _as_int(raw.get("messages_received")),
        })
    return tuple(rows)


def _summary_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    summary = dict(payload.get("summary", {}) or {})
    period = dict(payload.get("period", {}) or {})
    if not summary:
        return ()
    return ({
        "from_month": _text(period.get("from_month")),
        "to_month": _text(period.get("to_month")),
        "attendances": _as_int(summary.get("attendances")),
        "protocols": _as_int(summary.get("protocols")),
        "people": _as_int(summary.get("people")),
        "active_operators": _as_int(summary.get("active_operators")),
        "finalized": _as_int(summary.get("finalized")),
        "open": _as_int(summary.get("open")),
        "finalization_rate_pct": _as_float(summary.get("finalization_rate_pct")),
        "tme_avg_minutes": (_as_float(summary.get("tme_avg_seconds")) / 60.0) if _as_float(summary.get("tme_avg_seconds")) is not None else None,
        "tme_median_minutes": (_as_float(summary.get("tme_median_seconds")) / 60.0) if _as_float(summary.get("tme_median_seconds")) is not None else None,
        "tme_p90_minutes": (_as_float(summary.get("tme_p90_seconds")) / 60.0) if _as_float(summary.get("tme_p90_seconds")) is not None else None,
        "tma_avg_minutes": (_as_float(summary.get("tma_avg_seconds")) / 60.0) if _as_float(summary.get("tma_avg_seconds")) is not None else None,
        "tma_median_minutes": (_as_float(summary.get("tma_median_seconds")) / 60.0) if _as_float(summary.get("tma_median_seconds")) is not None else None,
        "tma_p90_minutes": (_as_float(summary.get("tma_p90_seconds")) / 60.0) if _as_float(summary.get("tma_p90_seconds")) is not None else None,
        "rating_avg": _as_float(summary.get("rating_avg")),
        "rating_count": _as_int(summary.get("rating_count")),
        "rating_missing": _as_int(summary.get("rating_missing")),
        "rating_coverage_pct": _as_float(summary.get("rating_coverage_pct")),
        "transferred": _as_int(summary.get("transferred")),
        "transfer_rate_pct": _as_float(summary.get("transfer_rate_pct")),
    },)


def _rating_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple({
        "rating": _as_int(raw.get("rating")),
        "count": _as_int(raw.get("count")),
        "pct": _as_float(raw.get("pct")),
    } for raw in payload.get("ratings", ()) if 1 <= _as_int(raw.get("rating")) <= 10)


def _target_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = []
    for raw in payload.get("targets", ()):
        rows.append({
            "indicator_code": _text(raw.get("indicator_code")).upper(),
            "metric_key": _text(raw.get("metric_key")),
            "scope_type": _text(raw.get("scope_type") or "TOTAL"),
            "scope_value": _text(raw.get("scope_value")),
            "scope_label": _text(raw.get("scope_label")),
            "valid_from": _text(raw.get("valid_from")),
            "valid_to": _text(raw.get("valid_to")),
            "target": _as_float(raw.get("target")),
            "attention": _as_float(raw.get("attention")),
            "justification": _text(raw.get("justification")),
        })
    return tuple(rows)


def _month_key(value: str) -> int:
    text = _text(value)
    try:
        year, month = (int(part) for part in text[:7].split("-"))
    except (TypeError, ValueError):
        return -1
    return year * 12 + month


def _target_active_for(
    rows: tuple[dict[str, Any], ...],
    metric_key: str,
    reference_month: str,
    *,
    department: str,
    channel: str,
) -> dict[str, Any] | None:
    """Mirror DADM V2 target inheritance exactly.

    The live backend gives department precedence over channel when both are
    selected, and then falls back to TOTAL.  The adapter pre-expands this rule
    so the Core can use exact-match target formulas offline.
    """
    priority: list[tuple[str, str]] = []
    if department != "(todos)":
        priority.append(("department", department))
    if channel != "(todos)":
        priority.append(("channel", channel))
    priority.append(("TOTAL", ""))
    month_value = _month_key(reference_month)
    if month_value < 0:
        return None
    for scope_type, scope_value in priority:
        candidates: list[dict[str, Any]] = []
        for row in rows:
            if _text(row.get("metric_key")) != metric_key:
                continue
            row_scope = _text(row.get("scope_type") or "TOTAL")
            row_value = _text(row.get("scope_value"))
            if row_scope != scope_type:
                continue
            if scope_type != "TOTAL" and row_value.casefold() != scope_value.casefold():
                continue
            start_key = _month_key(_text(row.get("valid_from")))
            end_text = _text(row.get("valid_to"))
            end_key = _month_key(end_text) if end_text else 10**9
            if start_key <= month_value <= end_key:
                candidates.append(row)
        if candidates:
            return max(candidates, key=lambda item: _month_key(_text(item.get("valid_from"))))
    return None


def _effective_target_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw_targets = _target_rows(payload)
    if not raw_targets:
        return ()
    months = [row["period"] for row in _period_rows(payload)]
    departments = ["(todos)", *[row["department"] for row in _department_rows(payload)]]
    channels = ["(todos)", *[row["channel"] for row in _simple_dimension_rows(payload, "channel", "(sem canal)")]]
    end_month = _text((payload.get("period") or {}).get("to_month")) or (months[-1] if months else "")
    period_selectors = ["(todos)", *months]
    rows: list[dict[str, Any]] = []
    for period_selector in period_selectors:
        reference_month = end_month if period_selector == "(todos)" else period_selector
        for department in departments:
            for channel in channels:
                for metric_code, metric_key in _DADM_TARGET_METRIC_KEYS.items():
                    active = _target_active_for(
                        raw_targets,
                        metric_key,
                        reference_month,
                        department=department,
                        channel=channel,
                    )
                    if active is None:
                        continue
                    rows.append({
                        "metric_code": metric_code,
                        "metric_key": metric_key,
                        "period_selector": period_selector,
                        "reference_month": reference_month,
                        "department_selector": department,
                        "channel_selector": channel,
                        "target": _as_float(active.get("target")),
                        "attention": _as_float(active.get("attention")),
                        "source_scope_type": _text(active.get("scope_type") or "TOTAL"),
                        "source_scope_value": _text(active.get("scope_value")),
                        "valid_from": _text(active.get("valid_from")),
                        "valid_to": _text(active.get("valid_to")),
                    })
    return tuple(rows)


def _comparison_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    summary = dict(payload.get("comparison", {}) or {})
    comparison_period = dict(payload.get("comparison_period", {}) or {})
    if not summary:
        return ()
    return ({
        "start": _text(comparison_period.get("start")),
        "end": _text(comparison_period.get("end")),
        "attendances": _as_int(summary.get("attendances")),
        "tme_avg_minutes": (_as_float(summary.get("tme_avg_seconds")) / 60.0) if _as_float(summary.get("tme_avg_seconds")) is not None else None,
        "tma_avg_minutes": (_as_float(summary.get("tma_avg_seconds")) / 60.0) if _as_float(summary.get("tma_avg_seconds")) is not None else None,
        "rating_avg": _as_float(summary.get("rating_avg")),
        "rating_coverage": (_as_float(summary.get("rating_coverage_pct")) / 100.0) if _as_float(summary.get("rating_coverage_pct")) is not None else None,
    },)


def _percentile_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    summary = dict(payload.get("summary", {}) or {})
    values = (
        ("DADM-01 · TME", "Mediana", "tme_median_seconds"),
        ("DADM-01 · TME", "P90", "tme_p90_seconds"),
        ("DADM-01 · TMA", "Mediana", "tma_median_seconds"),
        ("DADM-01 · TMA", "P90", "tma_p90_seconds"),
    )
    rows = []
    for indicator, statistic, key in values:
        value = _as_float(summary.get(key))
        rows.append({
            "indicator": indicator,
            "statistic": statistic,
            "minutes": (value / 60.0) if value is not None else None,
            "scope": "Recorte exportado",
        })
    return tuple(rows)


def _matrix_rows() -> tuple[dict[str, Any], ...]:
    values = (
        ("Atendimentos", DADM_METRICS["attendances"]),
        ("DADM-01 · TME", DADM_METRICS["tme"]),
        ("DADM-01 · TMA", DADM_METRICS["tma"]),
        ("DADM-02 · Avaliação média", DADM_METRICS["rating"]),
        ("DADM-02 · Cobertura", DADM_METRICS["rating_coverage"]),
        ("Taxa de finalização", DADM_METRICS["finalization"]),
    )
    return tuple({"selector_value": label, "metric_code": code, "sort_order": index} for index, (label, code) in enumerate(values, 1))


def _action_rows(payload: Mapping[str, Any]) -> tuple[ActionPlanRowSpec, ...]:
    rows = []
    for raw in payload.get("actions", ()):
        label = " · ".join(item for item in (_text(raw.get("indicator_code")), _text(raw.get("metric_key"))) if item)
        scope = _text(raw.get("scope_label"))
        problem = _text(raw.get("problem"))
        if scope and scope.casefold() != "institucional":
            problem = f"[{scope}] {problem}" if problem else f"[{scope}]"
        rows.append(ActionPlanRowSpec(
            source=ActionPlanRowSource.OFFICIAL,
            values={
                "indicator": label,
                "problem": problem,
                "diagnosis": _text(raw.get("probable_cause")),
                "action": _text(raw.get("corrective_action")),
                "owner": _text(raw.get("responsible")),
                "deadline": _as_date(raw.get("due_date")),
                "status": _text(raw.get("status")),
            },
        ))
    return tuple(rows)


def _dataset_specs(payload: Mapping[str, Any], authorization_scope: tuple[str, ...]) -> tuple[DatasetSpec, ...]:
    return (
        DatasetSpec(
            code="dadm_months", label="Meses", sheet_name="DIM_MES", table_name="TblDadmMonthsOfficial", technical=True,
            columns=(
                ColumnSpec("period", "Mês", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("label", "Rótulo", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ), rows=_period_rows(payload), grain=("period",), source="Data UNIVC · DADM · meses TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_departments", label="Departamentos", sheet_name="DEPARTAMENTOS", table_name="TblDadmDepartmentsOfficial", technical=True,
            columns=(
                ColumnSpec("department", "Departamento", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("department_name", "Nome", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ), rows=_department_rows(payload), grain=("department",), source="Data UNIVC · DADM · departamentos TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_employees", label="Operadores", sheet_name="OPERADORES", table_name="TblDadmEmployeesOfficial", technical=True,
            columns=(
                ColumnSpec("department", "Departamento", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("employee", "Operador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("employee_name", "Nome", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ), rows=_employee_rows(payload), grain=("department", "employee"), source="Data UNIVC · DADM · operadores TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_channels", label="Canais", sheet_name="DIM_CANAL", table_name="TblDadmChannelsOfficial", technical=True,
            columns=(ColumnSpec("channel", "Canal", ColumnDataType.TEXT, nullable=False), ColumnSpec("label", "Rótulo", ColumnDataType.TEXT, nullable=False), ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False)),
            rows=_simple_dimension_rows(payload, "channel", "(sem canal)"), grain=("channel",), source="Data UNIVC · DADM · canais TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_statuses", label="Status", sheet_name="DIM_STATUS", table_name="TblDadmStatusesOfficial", technical=True,
            columns=(ColumnSpec("status", "Status", ColumnDataType.TEXT, nullable=False), ColumnSpec("label", "Rótulo", ColumnDataType.TEXT, nullable=False), ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False)),
            rows=_simple_dimension_rows(payload, "status", "unknown"), grain=("status",), source="Data UNIVC · DADM · status TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_tabulations", label="Tabulações", sheet_name="DIM_TABULACAO", table_name="TblDadmTabulationsOfficial", technical=True,
            columns=(ColumnSpec("tabulation", "Tabulação", ColumnDataType.TEXT, nullable=False), ColumnSpec("label", "Rótulo", ColumnDataType.TEXT, nullable=False), ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False)),
            rows=_simple_dimension_rows(payload, "tabulation", "(sem tabulação)"), grain=("tabulation",), source="Data UNIVC · DADM · tabulações TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_matrix_metrics", label="Indicadores da matriz DADM", sheet_name="DIM_KPI_MATRIZ_DADM", table_name="TblDadmMatrixMetricsOfficial", technical=True,
            columns=(ColumnSpec("selector_value", "Indicador", ColumnDataType.TEXT, nullable=False), ColumnSpec("metric_code", "Código métrico", ColumnDataType.TEXT, technical=True, nullable=False), ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False)),
            rows=_matrix_rows(), grain=("selector_value",), source="Data UNIVC · DADM · indicadores", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_cube", label="Operação TALLOS Agregada", sheet_name="OPERACAO TALLOS", table_name="TblDadmCubeOfficial",
            columns=(
                ColumnSpec("period", "Mês", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("department", "Departamento", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("department_name", "Nome do departamento", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("employee", "Operador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("employee_name", "Nome do operador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("channel", "Canal", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("status", "Status", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("tabulation", "Tabulação", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("attendances", "Atendimentos", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("finalized", "Finalizados", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("open", "Em aberto", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("tme_sum_minutes", "Soma TME (min)", ColumnDataType.DECIMAL, technical=True, nullable=False),
                ColumnSpec("tme_count", "TME válidos", ColumnDataType.INTEGER, technical=True, nullable=False),
                ColumnSpec("tma_sum_minutes", "Soma TMA (min)", ColumnDataType.DECIMAL, technical=True, nullable=False),
                ColumnSpec("tma_count", "TMA válidos", ColumnDataType.INTEGER, technical=True, nullable=False),
                ColumnSpec("rating_sum", "Soma avaliações", ColumnDataType.DECIMAL, technical=True, nullable=False),
                ColumnSpec("rating_count", "Avaliações válidas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("transferred", "Transferidos", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("messages_sent", "Mensagens enviadas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("messages_received", "Mensagens recebidas", ColumnDataType.INTEGER, nullable=False),
            ),
            rows=_cube_rows(payload), grain=("period", "department", "employee", "channel", "status", "tabulation"),
            source="Data UNIVC · DADM · cubo agregado TALLOS", authorization_scope=authorization_scope,
            filter_dimensions=("period", "department", "employee", "channel", "status", "tabulation"),
            dimension_columns={"period": "period", "department": "department", "employee": "employee", "channel": "channel", "status": "status", "tabulation": "tabulation"},
        ),
        DatasetSpec(
            code="dadm_backend_summary", label="Resumo Backend", sheet_name="RESUMO BACKEND", table_name="TblDadmBackendSummaryOfficial",
            columns=(
                ColumnSpec("from_month", "Mês inicial", ColumnDataType.TEXT), ColumnSpec("to_month", "Mês final", ColumnDataType.TEXT),
                ColumnSpec("attendances", "Atendimentos", ColumnDataType.INTEGER), ColumnSpec("protocols", "Protocolos", ColumnDataType.INTEGER),
                ColumnSpec("people", "Pessoas", ColumnDataType.INTEGER), ColumnSpec("active_operators", "Operadores ativos", ColumnDataType.INTEGER),
                ColumnSpec("finalized", "Finalizados", ColumnDataType.INTEGER), ColumnSpec("open", "Em aberto", ColumnDataType.INTEGER),
                ColumnSpec("finalization_rate_pct", "Taxa finalização (%)", ColumnDataType.DECIMAL),
                ColumnSpec("tme_avg_minutes", "TME médio (min)", ColumnDataType.DECIMAL), ColumnSpec("tme_median_minutes", "TME mediana (min)", ColumnDataType.DECIMAL), ColumnSpec("tme_p90_minutes", "TME P90 (min)", ColumnDataType.DECIMAL),
                ColumnSpec("tma_avg_minutes", "TMA médio (min)", ColumnDataType.DECIMAL), ColumnSpec("tma_median_minutes", "TMA mediana (min)", ColumnDataType.DECIMAL), ColumnSpec("tma_p90_minutes", "TMA P90 (min)", ColumnDataType.DECIMAL),
                ColumnSpec("rating_avg", "Avaliação média", ColumnDataType.DECIMAL), ColumnSpec("rating_count", "Avaliações", ColumnDataType.INTEGER), ColumnSpec("rating_missing", "Sem avaliação", ColumnDataType.INTEGER), ColumnSpec("rating_coverage_pct", "Cobertura (%)", ColumnDataType.DECIMAL),
                ColumnSpec("transferred", "Transferidos", ColumnDataType.INTEGER), ColumnSpec("transfer_rate_pct", "Transferência (%)", ColumnDataType.DECIMAL),
            ), rows=_summary_rows(payload), grain=("from_month", "to_month"), source="Data UNIVC · DADM V2 · resumo backend", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_ratings", label="Distribuição de Avaliações", sheet_name="AVALIACOES", table_name="TblDadmRatingsOfficial",
            columns=(ColumnSpec("rating", "Nota", ColumnDataType.INTEGER, nullable=False), ColumnSpec("count", "Quantidade", ColumnDataType.INTEGER, nullable=False), ColumnSpec("pct", "Percentual", ColumnDataType.DECIMAL)),
            rows=_rating_rows(payload), grain=("rating",), source="Data UNIVC · DADM · avaliações TALLOS 1–10", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_targets", label="Metas DADM V2", sheet_name="BASE METAS DADM", table_name="TblDadmTargetsOfficial", technical=True,
            columns=(
                ColumnSpec("indicator_code", "Indicador", ColumnDataType.TEXT), ColumnSpec("metric_key", "Métrica", ColumnDataType.TEXT),
                ColumnSpec("scope_type", "Tipo de recorte", ColumnDataType.TEXT), ColumnSpec("scope_value", "Valor do recorte", ColumnDataType.TEXT), ColumnSpec("scope_label", "Recorte", ColumnDataType.TEXT),
                ColumnSpec("valid_from", "Vigência início", ColumnDataType.TEXT), ColumnSpec("valid_to", "Vigência fim", ColumnDataType.TEXT),
                ColumnSpec("target", "Meta", ColumnDataType.DECIMAL), ColumnSpec("attention", "Atenção", ColumnDataType.DECIMAL), ColumnSpec("justification", "Justificativa", ColumnDataType.TEXT),
            ), rows=_target_rows(payload), grain=("metric_key", "scope_type", "scope_value", "valid_from"), source="Data UNIVC · DADM V2 · metas TALLOS", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_targets_effective", label="Metas efetivas DADM", sheet_name="METAS EFETIVAS DADM", table_name="TblDadmTargetsEffectiveOfficial", technical=True,
            columns=(
                ColumnSpec("metric_code", "Código métrico", ColumnDataType.TEXT, technical=True, nullable=False),
                ColumnSpec("metric_key", "Métrica V2", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("period_selector", "Seleção de mês", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("reference_month", "Mês de referência", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("department_selector", "Seleção de departamento", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("channel_selector", "Seleção de canal", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("target", "Meta", ColumnDataType.DECIMAL),
                ColumnSpec("attention", "Atenção", ColumnDataType.DECIMAL),
                ColumnSpec("source_scope_type", "Origem do recorte", ColumnDataType.TEXT),
                ColumnSpec("source_scope_value", "Valor do recorte", ColumnDataType.TEXT),
                ColumnSpec("valid_from", "Vigência início", ColumnDataType.TEXT),
                ColumnSpec("valid_to", "Vigência fim", ColumnDataType.TEXT),
            ),
            rows=_effective_target_rows(payload),
            grain=("metric_code", "period_selector", "department_selector", "channel_selector"),
            source="Data UNIVC · DADM V2 · metas efetivas pré-expandidas",
            authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_backend_comparison", label="Período Anterior", sheet_name="RESUMO ANTERIOR", table_name="TblDadmPreviousOfficial",
            columns=(
                ColumnSpec("start", "Início", ColumnDataType.TEXT),
                ColumnSpec("end", "Fim", ColumnDataType.TEXT),
                ColumnSpec("attendances", "Atendimentos", ColumnDataType.INTEGER),
                ColumnSpec("tme_avg_minutes", "TME médio (min)", ColumnDataType.DECIMAL),
                ColumnSpec("tma_avg_minutes", "TMA médio (min)", ColumnDataType.DECIMAL),
                ColumnSpec("rating_avg", "Avaliação média", ColumnDataType.DECIMAL),
                ColumnSpec("rating_coverage", "Cobertura", ColumnDataType.DECIMAL),
            ),
            rows=_comparison_rows(payload), grain=("start", "end"), source="Data UNIVC · DADM V2 · previous_period do recorte exportado", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dadm_percentiles", label="Percentis Backend", sheet_name="PERCENTIS BACKEND", table_name="TblDadmPercentilesOfficial",
            columns=(
                ColumnSpec("indicator", "Indicador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("statistic", "Estatística", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("minutes", "Minutos", ColumnDataType.DECIMAL),
                ColumnSpec("scope", "Escopo", ColumnDataType.TEXT, nullable=False),
            ),
            rows=_percentile_rows(payload), grain=("indicator", "statistic"), source="Data UNIVC · DADM V2 · percentis calculados no backend", authorization_scope=authorization_scope,
        ),
    )


def _metric_specs() -> tuple[MetricSpec, ...]:
    dims = ("period", "department", "employee", "channel", "status", "tabulation")
    return (
        MetricSpec(DADM_METRICS["attendances"], "Atendimentos", MetricAggregation.SUM, MetricUnit.COUNT, "Quantidade de atendimentos TALLOS no recorte.", dims, True, 0, None, 0),
        MetricSpec(DADM_METRICS["finalization"], "Taxa de finalização", MetricAggregation.RATIO, MetricUnit.PERCENT, "Finalizados ÷ atendimentos.", dims, True, 0, 1, 1),
        MetricSpec(DADM_METRICS["open"], "Em aberto", MetricAggregation.SUM, MetricUnit.COUNT, "Quantidade de atendimentos ainda em aberto.", dims, True, 0, None, 0),
        MetricSpec(DADM_METRICS["tme"], "DADM-01 · Tempo Médio de Espera", MetricAggregation.AVERAGE, MetricUnit.MINUTES, "Média do TME válido, em minutos.", dims, True, 0, None, 1),
        MetricSpec(DADM_METRICS["tma"], "DADM-01 · Tempo Médio de Atendimento", MetricAggregation.AVERAGE, MetricUnit.MINUTES, "Média do TMA válido, em minutos.", dims, True, 0, None, 1),
        MetricSpec(DADM_METRICS["rating"], "DADM-02 · Avaliação média", MetricAggregation.AVERAGE, MetricUnit.SCORE_0_10, "Média das avaliações TALLOS válidas de 1 a 10.", dims, True, 1, 10, 2),
        MetricSpec(DADM_METRICS["rating_coverage"], "DADM-02 · Cobertura das avaliações", MetricAggregation.RATIO, MetricUnit.PERCENT, "Avaliações válidas ÷ atendimentos.", dims, True, 0, 1, 1),
        MetricSpec(DADM_METRICS["transfer_rate"], "Taxa de transferência", MetricAggregation.RATIO, MetricUnit.PERCENT, "Atendimentos transferidos ÷ atendimentos.", dims, True, 0, 1, 1),
        MetricSpec(DADM_COMPARISON_METRICS["attendances"], "Atendimentos · período anterior", MetricAggregation.VALUE, MetricUnit.COUNT, "Atendimentos do previous_period calculado no backend para o recorte exportado.", (), False, 0, None, 0),
        MetricSpec(DADM_COMPARISON_METRICS["tme"], "TME · período anterior", MetricAggregation.VALUE, MetricUnit.MINUTES, "TME do previous_period calculado no backend para o recorte exportado.", (), False, 0, None, 1),
        MetricSpec(DADM_COMPARISON_METRICS["tma"], "TMA · período anterior", MetricAggregation.VALUE, MetricUnit.MINUTES, "TMA do previous_period calculado no backend para o recorte exportado.", (), False, 0, None, 1),
        MetricSpec(DADM_COMPARISON_METRICS["rating"], "Avaliação · período anterior", MetricAggregation.VALUE, MetricUnit.SCORE_0_10, "Avaliação média do previous_period calculado no backend para o recorte exportado.", (), False, 1, 10, 2),
        MetricSpec(DADM_COMPARISON_METRICS["rating_coverage"], "Cobertura · período anterior", MetricAggregation.VALUE, MetricUnit.PERCENT, "Cobertura do previous_period calculado no backend para o recorte exportado.", (), False, 0, 1, 1),
    )


def _metric_bindings() -> tuple[MetricBinding, ...]:
    filters = {"period": "period", "department": "department", "employee": "employee", "channel": "channel", "status": "status", "tabulation": "tabulation"}
    dataset = "dadm_cube"
    return (
        MetricBinding(DADM_METRICS["attendances"], dataset, value_column="attendances", filter_parameters=filters),
        MetricBinding(DADM_METRICS["finalization"], dataset, components={"numerator": "finalized", "denominator": "attendances"}, filter_parameters=filters),
        MetricBinding(DADM_METRICS["open"], dataset, value_column="open", filter_parameters=filters),
        MetricBinding(DADM_METRICS["tme"], dataset, components={"sum": "tme_sum_minutes", "count": "tme_count"}, filter_parameters=filters),
        MetricBinding(DADM_METRICS["tma"], dataset, components={"sum": "tma_sum_minutes", "count": "tma_count"}, filter_parameters=filters),
        MetricBinding(DADM_METRICS["rating"], dataset, components={"sum": "rating_sum", "count": "rating_count"}, filter_parameters=filters),
        MetricBinding(DADM_METRICS["rating_coverage"], dataset, components={"numerator": "rating_count", "denominator": "attendances"}, filter_parameters=filters),
        MetricBinding(DADM_METRICS["transfer_rate"], dataset, components={"numerator": "transferred", "denominator": "attendances"}, filter_parameters=filters),
        MetricBinding(DADM_COMPARISON_METRICS["attendances"], "dadm_backend_comparison", value_column="attendances"),
        MetricBinding(DADM_COMPARISON_METRICS["tme"], "dadm_backend_comparison", value_column="tme_avg_minutes"),
        MetricBinding(DADM_COMPARISON_METRICS["tma"], "dadm_backend_comparison", value_column="tma_avg_minutes"),
        MetricBinding(DADM_COMPARISON_METRICS["rating"], "dadm_backend_comparison", value_column="rating_avg"),
        MetricBinding(DADM_COMPARISON_METRICS["rating_coverage"], "dadm_backend_comparison", value_column="rating_coverage"),
    )


class DADMAdapter(DirectorateAdapter):
    adapter_code = "dadm"
    adapter_version = 2

    def build_spec(self, adapter_input: AdapterInput) -> WorkbookSpec:
        payload = adapter_input.authorized_data
        directorate = _text(payload.get("directorate") or adapter_input.snapshot_context.directorate).upper()
        if directorate != "DADM":
            raise DADMAdapterError("dadm.unsupported_directorate", "DADMAdapter aceita somente a Diretoria Administrativa (DADM).")
        if adapter_input.snapshot_context.directorate.upper() != "DADM":
            raise DADMAdapterError("dadm.snapshot_scope_mismatch", "Diretoria do snapshot diverge do payload DADM autorizado.")

        datasets = _dataset_specs(payload, adapter_input.snapshot_context.authorization_scope)
        cube = next(item for item in datasets if item.code == "dadm_cube").rows
        periods = next(item for item in datasets if item.code == "dadm_months").rows
        departments = next(item for item in datasets if item.code == "dadm_departments").rows
        if not cube:
            raise DADMAdapterError("dadm.no_cube", "O snapshot DADM não possui fatos TALLOS agregados.")
        if not periods:
            raise DADMAdapterError("dadm.no_periods", "O snapshot DADM não possui meses disponíveis.")

        raw_initial = dict(adapter_input.snapshot_context.initial_filters)
        raw_initial.update(adapter_input.initial_state or {})
        period = _text(raw_initial.get("period")) or "(todos)"
        department = _text(raw_initial.get("department")) or "(todos)"
        employee = _text(raw_initial.get("employee")) or "(todos)"
        channel = _text(raw_initial.get("channel")) or "(todos)"
        status = _text(raw_initial.get("status")) or "(todos)"
        tabulation = _text(raw_initial.get("tabulation")) or "(todos)"
        matrix_metric = _text(raw_initial.get("matrix_metric")) or "Atendimentos"
        exported_range = _text((payload.get("period") or {}).get("label")) or f"{_text((payload.get('period') or {}).get('from_month'))} → {_text((payload.get('period') or {}).get('to_month'))}"

        parameters = (
            ParameterSpec("period", "Mês", "period", initial_value=period, empty_option="(todos)", description="Recorta os indicadores para um mês do snapshot; (todos) recompõe todo o período exportado.", display_order=10),
            ParameterSpec("department", "Departamento", "department", initial_value=department, empty_option="(todos)", description="Departamento TALLOS dentro do escopo autorizado.", display_order=20),
            ParameterSpec("employee", "Operador", "employee", initial_value=employee, empty_option="(todos)", depends_on=("department",), description="Operador TALLOS; a lista respeita o departamento selecionado.", display_order=30),
            ParameterSpec("channel", "Canal", "channel", initial_value=channel, empty_option="(todos)", description="Canal de atendimento.", display_order=40),
            ParameterSpec("status", "Status", "status", initial_value=status, empty_option="(todos)", description="Status operacional TALLOS.", display_order=50),
            ParameterSpec("tabulation", "Tabulação", "tabulation", initial_value=tabulation, empty_option="(todos)", description="Tabulação TALLOS.", display_order=60),
            ParameterSpec("export_range", "Período exportado", "", initial_value=exported_range, editable=False, required=True, description="Janela autorizada incorporada ao arquivo oficial.", display_order=70),
            ParameterSpec("matrix_metric", "KPI da matriz", "dadm_matrix_metrics", values_column="selector_value", initial_value=matrix_metric, description="Indicador numérico exibido na matriz Departamento × Mês.", display_order=80),
        )
        initial_state = {
            "period": period, "department": department, "employee": employee, "channel": channel,
            "status": status, "tabulation": tabulation, "export_range": exported_range, "matrix_metric": matrix_metric,
        }

        dimensions = (
            DimensionSpec("period", "Mês", "dadm_months", "period", "label", sort_order_column="sort_order"),
            DimensionSpec("department", "Departamento", "dadm_departments", "department", "department_name", sort_order_column="sort_order"),
            DimensionSpec("employee", "Operador", "dadm_employees", "employee", "employee_name", sort_order_column="sort_order", parent_dimension="department", parent_key_column="department"),
            DimensionSpec("channel", "Canal", "dadm_channels", "channel", "label", sort_order_column="sort_order"),
            DimensionSpec("status", "Status", "dadm_statuses", "status", "label", sort_order_column="sort_order"),
            DimensionSpec("tabulation", "Tabulação", "dadm_tabulations", "tabulation", "label", sort_order_column="sort_order"),
        )

        metrics = _metric_specs()
        bindings = _metric_bindings()
        quality = QualitySpec(
            dataset_checks=(
                QualityCheckSpec("dadm_cube_present", "Cubo operacional disponível", "dataset_non_empty", "dadm_cube", QualitySeverity.BLOCKING, "Base agregada disponível", "Cubo TALLOS vazio."),
                QualityCheckSpec("dadm_summary_present", "Resumo backend disponível", "dataset_non_empty", "dadm_backend_summary", QualitySeverity.WARNING, "Resumo backend disponível", "Resumo backend ausente."),
            ),
            metric_checks=(
                QualityCheckSpec("dadm_tme_available", "TME disponível", "metric_has_data", DADM_METRICS["tme"], QualitySeverity.INFO, "TME disponível no recorte", "Sem TME válido no recorte."),
                QualityCheckSpec("dadm_tma_available", "TMA disponível", "metric_has_data", DADM_METRICS["tma"], QualitySeverity.INFO, "TMA disponível no recorte", "Sem TMA válido no recorte."),
                QualityCheckSpec("dadm_rating_range", "Avaliação em faixa válida", "metric_valid_range", DADM_METRICS["rating"], QualitySeverity.WARNING, "Avaliação válida", "Avaliação fora da escala 1–10 ou indisponível."),
                QualityCheckSpec("dadm_rating_coverage_range", "Cobertura válida", "metric_valid_range", DADM_METRICS["rating_coverage"], QualitySeverity.WARNING, "Cobertura válida", "Cobertura fora de 0–100%."),
            ),
            coverage_checks=(
                QualityCheckSpec("dadm_period_dimension", "Dimensão Mês", "dimension_non_empty", "period", QualitySeverity.BLOCKING, "Meses disponíveis", "Dimensão Mês vazia."),
                QualityCheckSpec("dadm_department_dimension", "Dimensão Departamento", "dimension_non_empty", "department", QualitySeverity.BLOCKING, "Departamentos disponíveis", "Dimensão Departamento vazia."),
            ),
            snapshot_checks=(
                QualityCheckSpec("dadm_export_id", "Export ID presente", "snapshot_field_present", "export_id", QualitySeverity.BLOCKING, "Export ID identificado", "Export ID ausente."),
                QualityCheckSpec("dadm_authorization_scope", "Escopo autorizado presente", "snapshot_field_present", "authorization_scope", QualitySeverity.BLOCKING, "Escopo identificado", "Escopo autorizado ausente."),
            ),
        )

        limitations = (
            LimitationSpec(
                code="dadm.no_satisfaction_threshold_inference",
                title="Avaliação TALLOS não é convertida em satisfação institucional",
                description="A fonte homologada usa notas de 1 a 10. O Excel Oficial não infere automaticamente respostas 4–5, satisfação ou insatisfação sem regra institucional aprovada.",
                severity=QualitySeverity.INFO,
                affected_metric=DADM_METRICS["rating"],
            ),
            LimitationSpec(
                code="dadm.non_additive_distinct_counts",
                title="Protocolos, pessoas e operadores ativos permanecem no resumo backend",
                description="Contagens distintas não são somadas no cubo offline, pois poderiam duplicar entidades entre departamentos, operadores ou canais. O resumo original do backend permanece disponível para auditoria.",
                severity=QualitySeverity.INFO,
            ),
            LimitationSpec(
                code="dadm.aggregated_no_customer_pii",
                title="Base offline agregada e sem dados pessoais de clientes",
                description="O Excel Oficial exporta um cubo operacional agregado. Não exporta protocolo, customer_ref, conteúdo de conversas ou dados pessoais do cliente.",
                severity=QualitySeverity.INFO,
            ),
            LimitationSpec(
                code="dadm.previous_period_snapshot_context",
                title="Comparação com período anterior pertence ao recorte exportado",
                description="O previous_period mantém exatamente a semântica do DADM V2 e é calculado no backend para o recorte usado na exportação. Ao alterar filtros offline, o valor de comparação permanece como evidência do recorte exportado e não é recalculado.",
                severity=QualitySeverity.INFO,
            ),
            LimitationSpec(
                code="dadm.percentiles_backend_only",
                title="Mediana e P90 são estatísticas não aditivas",
                description="Mediana e P90 de TME/TMA são calculados no backend para o recorte exportado e permanecem na aba PERCENTIS BACKEND. Eles não são recomputados pela soma do cubo offline, pois percentis não são aditivos.",
                severity=QualitySeverity.INFO,
            ),
        )

        ctx = adapter_input.snapshot_context
        snapshot = SnapshotSpec(
            export_id=ctx.export_id,
            generated_at=ctx.generated_at,
            generated_by=ctx.generated_by,
            authorization_scope=ctx.authorization_scope,
            system_version=ctx.system_version,
            schema_version=ctx.schema_version,
            adapter_version=self.adapter_version,
            initial_scope=dict(ctx.initial_filters),
            minimum_period=ctx.minimum_period,
            maximum_period=ctx.maximum_period,
            payload_hash=ctx.payload_hash,
        )
        identity = IdentitySpec(
            workbook_title="Excel Oficial · Diretoria Administrativa",
            directorate_code="DADM",
            directorate_label="Diretoria Administrativa",
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            scope_label="DADM",
        )

        domain_sheets = (
            DomainSheetSpec("operation", "Operação TALLOS", "dadm_cube", "Cubo agregado e recomponível usado pelos filtros e indicadores offline.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("summary", "Resumo Backend", "dadm_backend_summary", "Resumo calculado pelo backend para o período exportado, incluindo contagens distintas e percentis não aditivos.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("comparison", "Resumo Anterior", "dadm_backend_comparison", "Previous period do recorte exportado, calculado pelo backend com a mesma quantidade de dias imediatamente anterior.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("percentiles", "Percentis Backend", "dadm_percentiles", "Mediana e P90 de TME/TMA calculados no backend para o recorte exportado; estatísticas não aditivas.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("ratings", "Avaliações", "dadm_ratings", "Distribuição de notas TALLOS válidas de 1 a 10.", SheetRole.DOMAIN_ANALYSIS),
        )

        target_bindings = (
            TargetBindingSpec(
                DADM_METRICS["tme"], "dadm_targets_effective", "target", "attention",
                criteria_parameters={"period_selector": "period", "department_selector": "department", "channel_selector": "channel"},
                criteria_constants={"metric_code": DADM_METRICS["tme"]}, value_scale=(1.0 / 60.0),
            ),
            TargetBindingSpec(
                DADM_METRICS["tma"], "dadm_targets_effective", "target", "attention",
                criteria_parameters={"period_selector": "period", "department_selector": "department", "channel_selector": "channel"},
                criteria_constants={"metric_code": DADM_METRICS["tma"]}, value_scale=(1.0 / 60.0),
            ),
            TargetBindingSpec(
                DADM_METRICS["rating"], "dadm_targets_effective", "target", "attention",
                criteria_parameters={"period_selector": "period", "department_selector": "department", "channel_selector": "channel"},
                criteria_constants={"metric_code": DADM_METRICS["rating"]},
            ),
            TargetBindingSpec(
                DADM_METRICS["rating_coverage"], "dadm_targets_effective", "target", "attention",
                criteria_parameters={"period_selector": "period", "department_selector": "department", "channel_selector": "channel"},
                criteria_constants={"metric_code": DADM_METRICS["rating_coverage"]}, value_scale=0.01,
            ),
        )

        return WorkbookSpec(
            identity=identity,
            snapshot=snapshot,
            initial_state=InitialStateSpec(values=initial_state),
            parameters=parameters,
            datasets=datasets,
            dimensions=dimensions,
            metric_codes=tuple(metric.code for metric in metrics),
            metric_bindings=bindings,
            domain_sheets=domain_sheets,
            dashboard=DashboardSpec(
                title="PAINEL DE GESTÃO · DADM",
                kpis=(
                    KpiSpec(DADM_METRICS["attendances"], comparison_metric_code=DADM_COMPARISON_METRICS["attendances"], priority=10),
                    KpiSpec(DADM_METRICS["tme"], comparison_metric_code=DADM_COMPARISON_METRICS["tme"], priority=20),
                    KpiSpec(DADM_METRICS["tma"], comparison_metric_code=DADM_COMPARISON_METRICS["tma"], priority=30),
                    KpiSpec(DADM_METRICS["rating"], comparison_metric_code=DADM_COMPARISON_METRICS["rating"], priority=40),
                    KpiSpec(DADM_METRICS["rating_coverage"], comparison_metric_code=DADM_COMPARISON_METRICS["rating_coverage"], priority=50),
                ),
                charts=(
                    ChartSpec("dadm_volume_by_month", "Atendimentos por mês", DADM_METRICS["attendances"], "dadm_cube", "period", ChartType.COLUMN, ChartRole.EVOLUTION, sort="dimension_asc"),
                    ChartSpec("dadm_tme_by_month", "DADM-01 · Tempo Médio de Espera", DADM_METRICS["tme"], "dadm_cube", "period", ChartType.LINE, ChartRole.EVOLUTION, sort="dimension_asc"),
                    ChartSpec("dadm_tma_by_month", "DADM-01 · Tempo Médio de Atendimento", DADM_METRICS["tma"], "dadm_cube", "period", ChartType.LINE, ChartRole.EVOLUTION, sort="dimension_asc"),
                    ChartSpec("dadm_rating_by_month", "DADM-02 · Avaliação média", DADM_METRICS["rating"], "dadm_cube", "period", ChartType.LINE, ChartRole.EVOLUTION, sort="dimension_asc"),
                ),
                attention_blocks=(
                    "TME e TMA são recompostos por soma/contagem dos valores válidos; o Excel não calcula média de médias.",
                    "Avaliação média considera exclusivamente notas TALLOS válidas de 1 a 10; ausência/level=0 não entra na média.",
                    "Protocolos, pessoas e operadores ativos são contagens distintas e permanecem no RESUMO BACKEND para evitar dupla contagem offline.",
                    "A comparação 'Período anterior' usa o previous_period do DADM V2 para o recorte exportado e permanece fixa quando filtros offline são alterados.",
                    "Mediana e P90 de TME/TMA permanecem em PERCENTIS BACKEND; percentis não são aditivos e não são recalculados pelo cubo offline.",
                ),
            ),
            matrix=MatrixSpec(
                metric_code=DADM_METRICS["attendances"],
                row_dimension="department",
                column_dimension="period",
                delta=False,
                sorting="label_asc",
                empty_behavior="blank",
                metric_selector_parameter="matrix_metric",
                metric_options=(
                    MatrixMetricOptionSpec("Atendimentos", DADM_METRICS["attendances"]),
                    MatrixMetricOptionSpec("DADM-01 · TME", DADM_METRICS["tme"]),
                    MatrixMetricOptionSpec("DADM-01 · TMA", DADM_METRICS["tma"]),
                    MatrixMetricOptionSpec("DADM-02 · Avaliação média", DADM_METRICS["rating"]),
                    MatrixMetricOptionSpec("DADM-02 · Cobertura", DADM_METRICS["rating_coverage"], display_scale=100.0),
                    MatrixMetricOptionSpec("Taxa de finalização", DADM_METRICS["finalization"], display_scale=100.0),
                ),
                selector_number_format="0.0",
            ),
            quality=quality,
            action_plan=ActionPlanSpec(
                enabled=True,
                official_fields=(),
                local_editable_fields=("indicator", "problem", "diagnosis", "action", "owner", "deadline", "status"),
                rows=_action_rows(payload),
                local_blank_rows=8,
                status_options=("Aberto", "Em andamento", "Concluído", "Atrasado", "Cancelado"),
                completed_statuses=("Concluído", "Cancelado"),
            ),
            technical=TechnicalSpec(include_targets=True, include_indicators=True, include_calc=True, include_support_lists=True, include_period_dimension=False, include_month_dimension=False),
            capabilities=AdapterCapabilities(supports_comparison=True, supports_history_window=False, supports_action_plan=True, interactive_dimensions=("period", "department", "employee", "channel", "status", "tabulation")),
            limitations=limitations,
            metrics=metrics,
            target_bindings=target_bindings,
        )


__all__ = ["DADM_COMPARISON_METRICS", "DADM_METRICS", "DADMAdapter", "DADMAdapterError"]
