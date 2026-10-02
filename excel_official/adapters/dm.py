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


DM_METRICS = {
    "members": "dm.cohort_members",
    "active": "dm.active_students",
    "graduated": "dm.graduated_students",
    "occupancy": "dm.occupancy_rate",
    "dropout": "dm.dropout_rate",
    "avg_defense": "dm.average_months_to_defense",
    "on_time": "dm.on_time_graduation_rate",
    "risk30": "dm.active_over_30_no_defense",
    "entry_completeness": "dm.entry_date_completeness",
}


@dataclass(frozen=True, slots=True)
class DMAdapterError(ValueError):
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


def _cohort_key(row: Mapping[str, Any]) -> str:
    existing = _text(row.get("cohort_key"))
    if existing:
        return existing
    return f"{_text(row.get('area_code')).upper()} | Turma {_as_int(row.get('cohort_number'))}"


def _area_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    dashboard = payload.get("dashboard_snapshot", {}) or {}
    rows = []
    for index, area in enumerate(dashboard.get("areas", ())):
        code = _text(area.get("area_code")).upper()
        if not code:
            continue
        rows.append({
            "area_code": code,
            "area_name": _text(area.get("area_name")) or code,
            "sort_order": index + 1,
        })
    if rows:
        return tuple(rows)
    seen: set[str] = set()
    for cohort in payload.get("cohorts", ()):
        code = _text(cohort.get("area_code")).upper()
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({"area_code": code, "area_name": _text(cohort.get("area_name")) or code, "sort_order": len(rows) + 1})
    return tuple(rows)


def _cohort_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = []
    for index, raw in enumerate(payload.get("cohorts", ())):
        area = _text(raw.get("area_code")).upper()
        number = _as_int(raw.get("cohort_number"))
        key = _cohort_key(raw)
        if not area or not number:
            continue
        rows.append({
            "area_code": area,
            "cohort_key": key,
            "cohort_label": key,
            "cohort_number": number,
            "opening_date": _as_date(raw.get("opening_date")),
            "status": _text(raw.get("status")),
            "vacancies": _as_int(raw.get("vacancies_authorized")),
            "sort_order": index + 1,
        })
    return tuple(rows)


def _cohort_number_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    numbers = sorted({_as_int(row.get("cohort_number")) for row in payload.get("cohorts", ()) if _as_int(row.get("cohort_number"))})
    return tuple({"cohort_number": number, "label": f"Turma {number}", "sort_order": number} for number in numbers)


def _cohort_metric_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    dashboard = payload.get("dashboard_snapshot", {}) or {}
    rows: list[dict[str, Any]] = []
    for area in dashboard.get("areas", ()):
        area_code = _text(area.get("area_code")).upper()
        for summary in area.get("cohorts", ()):
            total = _as_int(summary.get("total_students"))
            vacancies = _as_int(summary.get("vacancies_authorized"))
            defenses = _as_int(summary.get("defenses_count"))
            avg_defense = _as_float(summary.get("average_months_to_defense"))
            confirmed = _as_int(summary.get("confirmed_entry_dates"))
            on_time = _as_int(summary.get("graduated_within_24"))
            rows.append({
                "area_code": area_code,
                "cohort_key": _cohort_key(summary),
                "cohort_number": _as_int(summary.get("cohort_number")),
                "cohort_status": _text(summary.get("status")),
                "opening_date": _as_date(summary.get("opening_date")),
                "vacancies": vacancies,
                "total_students": total,
                "active_students": _as_int(summary.get("active_students")),
                "graduated_students": _as_int(summary.get("graduated_students")),
                "dropped_students": _as_int(summary.get("dropped_students")),
                "defenses_count": defenses,
                "defense_months_weighted": (avg_defense * defenses) if avg_defense is not None and defenses else 0.0,
                "graduated_within_24": on_time,
                "confirmed_entry_dates": confirmed,
                "risk_over_30": _as_int(summary.get("active_over_30_no_defense")),
                "entry_date_complete": confirmed,
                "last_defense_date": _as_date(summary.get("last_defense_date")),
                "dm01_status": _text(summary.get("dm01_status")),
                "dm02_status": _text(summary.get("dm02_status")),
            })
    return tuple(rows)


def _student_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = []
    for raw in payload.get("students", ()):
        rows.append({
            "area_code": _text(raw.get("area_code")).upper(),
            "cohort_key": _cohort_key(raw),
            "cohort_number": _as_int(raw.get("cohort_number")),
            "student_code": _text(raw.get("student_code")),
            "student_name": _text(raw.get("student_name")),
            "entry_date": _as_date(raw.get("entry_date")),
            "entry_estimated": bool(raw.get("entry_date_estimated")),
            "qualification_date": _as_date(raw.get("qualification_date")),
            "defense_date": _as_date(raw.get("defense_date")),
            "defense_scheduled_date": _as_date(raw.get("defense_scheduled_date")),
            "exit_date": _as_date(raw.get("exit_date")),
            "status": _text(raw.get("status")),
            "advisor": _text(raw.get("advisor")),
            "research_line": _text(raw.get("research_line")),
            "source_system": _text(raw.get("source_system")),
            "data_quality": _text(raw.get("data_quality")),
        })
    return tuple(rows)


def _target_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = []
    for raw in payload.get("effective_targets", ()):
        rows.append({
            "period": _text(raw.get("period")),
            "indicator_code": _text(raw.get("indicator_code")).upper(),
            "metric_key": _text(raw.get("metric_key")),
            "target": _as_float(raw.get("target")),
            "source_valid_from": _text(raw.get("source_valid_from")),
            "source_valid_to": _text(raw.get("source_valid_to")),
            "justification": _text(raw.get("justification")),
        })
    return tuple(rows)


def _matrix_rows() -> tuple[dict[str, Any], ...]:
    options = (
        ("DM-01 · Membros por turma", DM_METRICS["members"]),
        ("Ocupação · Vagas", DM_METRICS["occupancy"]),
        ("DM-02 · Tempo médio até defesa", DM_METRICS["avg_defense"]),
        ("Defesas · Até 24 meses", DM_METRICS["on_time"]),
        ("Risco · >30m sem defesa", DM_METRICS["risk30"]),
    )
    return tuple({"selector_value": label, "metric_code": metric, "sort_order": index} for index, (label, metric) in enumerate(options, 1))


def _action_rows(payload: Mapping[str, Any]) -> tuple[ActionPlanRowSpec, ...]:
    rows = []
    for raw in payload.get("actions", ()):
        indicator = _text(raw.get("indicator_code"))
        metric = _text(raw.get("metric_key"))
        rows.append(ActionPlanRowSpec(
            source=ActionPlanRowSource.OFFICIAL,
            values={
                "indicator": " · ".join(item for item in (indicator, metric) if item),
                "problem": _text(raw.get("problem")),
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
            code="dm_areas", label="Áreas do Mestrado", sheet_name="AREAS DM", table_name="TblDmAreasOfficial", technical=True,
            columns=(
                ColumnSpec("area_code", "Área", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("area_name", "Nome da área", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_area_rows(payload), grain=("area_code",), source="Data UNIVC · catálogo DM", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dm_cohorts", label="Turmas", sheet_name="TURMAS", table_name="TblDmCohortsOfficial",
            columns=(
                ColumnSpec("area_code", "Área", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_key", "Turma", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_label", "Rótulo", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_number", "Número", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("opening_date", "Abertura", ColumnDataType.DATE),
                ColumnSpec("status", "Status da turma", ColumnDataType.TEXT),
                ColumnSpec("vacancies", "Vagas autorizadas", ColumnDataType.INTEGER),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_cohort_rows(payload), grain=("cohort_key",), source="Data UNIVC · DM · turmas", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dm_cohort_numbers", label="Números de turma", sheet_name="DIM_TURMA", table_name="TblDmCohortNumbersOfficial", technical=True,
            columns=(
                ColumnSpec("cohort_number", "Número", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("label", "Turma", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_cohort_number_rows(payload), grain=("cohort_number",), source="Data UNIVC · dimensão de turmas", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dm_matrix_metrics", label="Indicadores da matriz DM", sheet_name="DIM_KPI_MATRIZ_DM", table_name="TblDmMatrixMetricsOfficial", technical=True,
            columns=(
                ColumnSpec("selector_value", "Indicador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("metric_code", "Código métrico", ColumnDataType.TEXT, technical=True, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_matrix_rows(), grain=("selector_value",), source="Data UNIVC · indicadores DM", authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="dm_cohort_metrics", label="Indicadores por Turma", sheet_name="INDICADORES TURMAS", table_name="TblDmCohortMetricsOfficial",
            columns=(
                ColumnSpec("area_code", "Área", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_key", "Turma", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_number", "Número", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("cohort_status", "Status turma", ColumnDataType.TEXT),
                ColumnSpec("opening_date", "Abertura", ColumnDataType.DATE),
                ColumnSpec("vacancies", "Vagas", ColumnDataType.INTEGER),
                ColumnSpec("total_students", "Membros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("active_students", "Ativos", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("graduated_students", "Titulados", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("dropped_students", "Desligados", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("defenses_count", "Defesas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("defense_months_weighted", "Meses de defesa ponderados", ColumnDataType.DECIMAL, technical=True, nullable=False),
                ColumnSpec("graduated_within_24", "Defesas até 24m", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("confirmed_entry_dates", "Ingressos confirmados", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("risk_over_30", "Risco >30m", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("entry_date_complete", "Ingressos completos", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("last_defense_date", "Última defesa", ColumnDataType.DATE),
                ColumnSpec("dm01_status", "Status DM-01", ColumnDataType.TEXT),
                ColumnSpec("dm02_status", "Status DM-02", ColumnDataType.TEXT),
            ),
            rows=_cohort_metric_rows(payload), grain=("area_code", "cohort_key"), source="Data UNIVC · DM · recomposição oficial por turma",
            authorization_scope=authorization_scope, filter_dimensions=("area", "cohort", "cohort_number"),
            dimension_columns={"area": "area_code", "cohort": "cohort_key", "cohort_number": "cohort_number"},
        ),
        DatasetSpec(
            code="dm_students", label="Alunos e Defesas", sheet_name="ALUNOS E DEFESAS", table_name="TblDmStudentsOfficial", sensitivity="restricted",
            columns=(
                ColumnSpec("area_code", "Área", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_key", "Turma", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("cohort_number", "Número", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("student_code", "Matrícula", ColumnDataType.TEXT),
                ColumnSpec("student_name", "Aluno", ColumnDataType.TEXT),
                ColumnSpec("entry_date", "Ingresso", ColumnDataType.DATE),
                ColumnSpec("entry_estimated", "Ingresso provisório", ColumnDataType.BOOLEAN),
                ColumnSpec("qualification_date", "Qualificação", ColumnDataType.DATE),
                ColumnSpec("defense_date", "Defesa", ColumnDataType.DATE),
                ColumnSpec("defense_scheduled_date", "Defesa marcada", ColumnDataType.DATE),
                ColumnSpec("exit_date", "Saída", ColumnDataType.DATE),
                ColumnSpec("status", "Status", ColumnDataType.TEXT),
                ColumnSpec("advisor", "Orientador", ColumnDataType.TEXT),
                ColumnSpec("research_line", "Linha de pesquisa", ColumnDataType.TEXT),
                ColumnSpec("source_system", "Origem", ColumnDataType.TEXT),
                ColumnSpec("data_quality", "Qualidade", ColumnDataType.TEXT),
            ),
            rows=_student_rows(payload), grain=("student_code",), source="Data UNIVC · DM · alunos/SEI", authorization_scope=authorization_scope,
            filter_dimensions=("area", "cohort", "cohort_number"), dimension_columns={"area": "area_code", "cohort": "cohort_key", "cohort_number": "cohort_number"},
        ),
        DatasetSpec(
            code="dm_targets_effective", label="Metas efetivas DM", sheet_name="BASE METAS DM", table_name="TblDmTargetsOfficial", technical=True,
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("indicator_code", "Indicador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("metric_key", "Métrica", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("target", "Meta", ColumnDataType.DECIMAL),
                ColumnSpec("source_valid_from", "Vigência início", ColumnDataType.TEXT),
                ColumnSpec("source_valid_to", "Vigência fim", ColumnDataType.TEXT),
                ColumnSpec("justification", "Justificativa", ColumnDataType.TEXT),
            ),
            rows=_target_rows(payload), grain=("period", "indicator_code", "metric_key"), source="Data UNIVC · metas gerenciais DM", authorization_scope=authorization_scope,
        ),
    )


def _metric_specs() -> tuple[MetricSpec, ...]:
    dims = ("area", "cohort", "cohort_number")
    return (
        MetricSpec(DM_METRICS["members"], "DM-01 · Membros", MetricAggregation.SUM, MetricUnit.COUNT, allowed_dimensions=dims, valid_min=0, display_precision=0),
        MetricSpec(DM_METRICS["active"], "Alunos ativos", MetricAggregation.SUM, MetricUnit.COUNT, allowed_dimensions=dims, valid_min=0, display_precision=0),
        MetricSpec(DM_METRICS["graduated"], "Titulados", MetricAggregation.SUM, MetricUnit.COUNT, allowed_dimensions=dims, valid_min=0, display_precision=0),
        MetricSpec(DM_METRICS["occupancy"], "Ocupação", MetricAggregation.RATIO, MetricUnit.PERCENT, allowed_dimensions=dims, valid_min=0, valid_max=1.5, display_precision=1),
        MetricSpec(DM_METRICS["dropout"], "Evasão", MetricAggregation.RATIO, MetricUnit.PERCENT, allowed_dimensions=dims, valid_min=0, valid_max=1, display_precision=1),
        MetricSpec(DM_METRICS["avg_defense"], "DM-02 · Tempo médio até a defesa", MetricAggregation.WEIGHTED_AVERAGE, MetricUnit.MONTHS, allowed_dimensions=dims, valid_min=0, display_precision=1),
        MetricSpec(DM_METRICS["on_time"], "Defesas em até 24 meses", MetricAggregation.RATIO, MetricUnit.PERCENT, allowed_dimensions=dims, valid_min=0, valid_max=1, display_precision=1),
        MetricSpec(DM_METRICS["risk30"], "Ativos >30m sem defesa", MetricAggregation.SUM, MetricUnit.COUNT, allowed_dimensions=dims, valid_min=0, display_precision=0),
        MetricSpec(DM_METRICS["entry_completeness"], "Completude da data de ingresso", MetricAggregation.RATIO, MetricUnit.PERCENT, allowed_dimensions=dims, valid_min=0, valid_max=1, display_precision=1),
    )


def _metric_bindings() -> tuple[MetricBinding, ...]:
    filters = {"area": "area", "cohort": "cohort"}
    dataset = "dm_cohort_metrics"
    return (
        MetricBinding(DM_METRICS["members"], dataset, value_column="total_students", filter_parameters=filters),
        MetricBinding(DM_METRICS["active"], dataset, value_column="active_students", filter_parameters=filters),
        MetricBinding(DM_METRICS["graduated"], dataset, value_column="graduated_students", filter_parameters=filters),
        MetricBinding(DM_METRICS["occupancy"], dataset, components={"numerator": "total_students", "denominator": "vacancies"}, filter_parameters=filters),
        MetricBinding(DM_METRICS["dropout"], dataset, components={"numerator": "dropped_students", "denominator": "total_students"}, filter_parameters=filters),
        MetricBinding(DM_METRICS["avg_defense"], dataset, components={"weighted_sum": "defense_months_weighted", "weight": "defenses_count"}, filter_parameters=filters),
        MetricBinding(DM_METRICS["on_time"], dataset, components={"numerator": "graduated_within_24", "denominator": "confirmed_entry_dates"}, filter_parameters=filters),
        MetricBinding(DM_METRICS["risk30"], dataset, value_column="risk_over_30", filter_parameters=filters),
        MetricBinding(DM_METRICS["entry_completeness"], dataset, components={"numerator": "entry_date_complete", "denominator": "total_students"}, filter_parameters=filters),
    )


class DMAdapter(DirectorateAdapter):
    adapter_code = "dm"
    adapter_version = 1

    def build_spec(self, adapter_input: AdapterInput) -> WorkbookSpec:
        payload = adapter_input.authorized_data
        directorate = _text(payload.get("directorate") or adapter_input.snapshot_context.directorate).upper()
        if directorate != "DM":
            raise DMAdapterError("dm.unsupported_directorate", "DMAdapter aceita somente a Diretoria de Mestrado (DM).")
        if adapter_input.snapshot_context.directorate.upper() != "DM":
            raise DMAdapterError("dm.snapshot_scope_mismatch", "Diretoria do snapshot diverge do payload DM autorizado.")

        datasets = _dataset_specs(payload, adapter_input.snapshot_context.authorization_scope)
        areas = next(item for item in datasets if item.code == "dm_areas").rows
        cohorts = next(item for item in datasets if item.code == "dm_cohorts").rows
        metric_rows = next(item for item in datasets if item.code == "dm_cohort_metrics").rows
        if not areas:
            raise DMAdapterError("dm.no_areas", "O snapshot DM não possui áreas disponíveis.")
        if not cohorts:
            raise DMAdapterError("dm.no_cohorts", "O snapshot DM não possui turmas disponíveis.")
        if not metric_rows:
            raise DMAdapterError("dm.no_metrics", "O snapshot DM não possui indicadores por turma.")

        payload_initial = payload.get("initial", {}) or {}
        requested = dict(payload_initial)
        requested.update(adapter_input.initial_state or {})
        area_values = {str(row["area_code"]) for row in areas}
        cohort_values = {str(row["cohort_key"]) for row in cohorts}

        area = _text(requested.get("area")) or "(todas)"
        if area != "(todas)" and area not in area_values:
            area = "(todas)"
        cohort = _text(requested.get("cohort")) or "(todas)"
        if cohort != "(todas)" and cohort not in cohort_values:
            cohort = "(todas)"
        if cohort != "(todas)":
            selected = next((row for row in cohorts if row["cohort_key"] == cohort), None)
            if selected:
                area = str(selected["area_code"])

        comparison = _text(requested.get("comparison")) or "(nenhuma)"
        if comparison not in cohort_values or comparison == cohort:
            comparison = "(nenhuma)"

        as_of = _as_date(requested.get("as_of") or payload_initial.get("as_of")) or date.today()
        target_period = f"{as_of.year:04d}-SEM{1 if as_of.month <= 6 else 2}"
        matrix_values = [row["selector_value"] for row in _matrix_rows()]
        matrix_metric = _text(requested.get("matrix_metric") or requested.get("matrix_kpi") or payload_initial.get("matrix_kpi"))
        if matrix_metric not in matrix_values:
            matrix_metric = matrix_values[0]

        parameters = (
            ParameterSpec("area", "Área", "area", initial_value=area, empty_option="(todas)", description="Recorta KPIs e gráficos da DM por área de mestrado.", display_order=10),
            ParameterSpec("cohort", "Turma", "cohort", initial_value=cohort, empty_option="(todas)", depends_on=("area",), description="Recorta os KPIs para uma turma específica.", display_order=20),
            ParameterSpec("comparison_cohort", "Comparar com", "cohort", initial_value=comparison, empty_option="(nenhuma)", depends_on=("area",), description="Turma usada como comparação dos KPIs quando aplicável.", display_order=30),
            ParameterSpec("as_of", "Data de corte", "", initial_value=as_of, editable=False, required=True, description="Data de corte do snapshot oficial. Para alterar, selecione outra data no site e exporte novamente.", display_order=40, data_type=ColumnDataType.DATE),
            ParameterSpec("target_period", "Competência das metas", "", initial_value=target_period, editable=False, required=True, description="Semestre correspondente à data de corte usado na vigência das metas.", display_order=50),
            ParameterSpec("matrix_metric", "KPI da matriz", "dm_matrix_metrics", values_column="selector_value", initial_value=matrix_metric, description="Indicador numérico exibido na matriz Área × Turma.", display_order=60),
        )
        initial_state = {
            "area": area,
            "cohort": cohort,
            "comparison_cohort": comparison,
            "as_of": as_of,
            "target_period": target_period,
            "matrix_metric": matrix_metric,
        }

        dimensions = (
            DimensionSpec("area", "Área", "dm_areas", "area_code", "area_name", sort_order_column="sort_order"),
            DimensionSpec("cohort", "Turma", "dm_cohorts", "cohort_key", "cohort_label", sort_order_column="sort_order", parent_dimension="area", parent_key_column="area_code"),
            DimensionSpec("cohort_number", "Turma", "dm_cohort_numbers", "cohort_number", "label", sort_order_column="sort_order"),
        )

        metrics = _metric_specs()
        bindings = _metric_bindings()
        quality = QualitySpec(
            dataset_checks=(
                QualityCheckSpec("dm_cohorts_present", "Base de turmas disponível", "dataset_non_empty", "dm_cohorts", QualitySeverity.BLOCKING, "Turmas disponíveis", "Base de turmas vazia."),
                QualityCheckSpec("dm_students_present", "Base de alunos disponível", "dataset_non_empty", "dm_students", QualitySeverity.BLOCKING, "Alunos disponíveis", "Base de alunos vazia."),
                QualityCheckSpec("dm_metrics_present", "Resumo por turma disponível", "dataset_non_empty", "dm_cohort_metrics", QualitySeverity.BLOCKING, "Indicadores por turma disponíveis", "Resumo por turma vazio."),
            ),
            metric_checks=(
                QualityCheckSpec("dm_occupancy_range", "Ocupação em faixa válida", "metric_valid_range", DM_METRICS["occupancy"], QualitySeverity.WARNING, "Ocupação válida", "Ocupação fora da faixa esperada."),
                QualityCheckSpec("dm_defense_available", "Tempo médio até defesa disponível", "metric_has_data", DM_METRICS["avg_defense"], QualitySeverity.INFO, "DM-02 disponível no recorte", "Sem defesas confirmadas no recorte."),
                QualityCheckSpec("dm_on_time_range", "Defesas em até 24 meses válidas", "metric_valid_range", DM_METRICS["on_time"], QualitySeverity.INFO, "Proporção válida", "Proporção fora de 0–100% ou indisponível."),
            ),
            coverage_checks=(
                QualityCheckSpec("dm_area_dimension", "Dimensão Área", "dimension_non_empty", "area", QualitySeverity.BLOCKING, "Áreas disponíveis", "Dimensão Área vazia."),
                QualityCheckSpec("dm_cohort_dimension", "Dimensão Turma", "dimension_non_empty", "cohort", QualitySeverity.BLOCKING, "Turmas disponíveis", "Dimensão Turma vazia."),
            ),
            snapshot_checks=(
                QualityCheckSpec("dm_export_id", "Export ID presente", "snapshot_field_present", "export_id", QualitySeverity.BLOCKING, "Export ID identificado", "Export ID ausente."),
                QualityCheckSpec("dm_authorization_scope", "Escopo autorizado presente", "snapshot_field_present", "authorization_scope", QualitySeverity.BLOCKING, "Escopo identificado", "Escopo autorizado ausente."),
            ),
        )

        limitations = (
            LimitationSpec(
                code="dm.fixed_cutoff_offline",
                title="Data de corte fixa no arquivo exportado",
                description="Os indicadores temporais são calculados para a data de corte escolhida no site. Para recalcular outra data de corte, exporte novamente o Excel Oficial.",
                severity=QualitySeverity.INFO,
                affected_metric=DM_METRICS["avg_defense"],
            ),
            LimitationSpec(
                code="dm.restricted_student_data",
                title="Base nominativa sob escopo autorizado",
                description="A aba ALUNOS E DEFESAS contém dados identificáveis da pós-graduação e deve permanecer dentro do escopo institucional autorizado.",
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
            workbook_title="Excel Oficial · Diretoria de Mestrado",
            directorate_code="DM",
            directorate_label="Diretoria de Mestrado",
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            scope_label="DM",
        )

        domain_sheets = (
            DomainSheetSpec("cohort_metrics", "Indicadores por Turma", "dm_cohort_metrics", "Recomposição oficial DM-01/DM-02 e medidas auxiliares por turma.", SheetRole.DOMAIN_ANALYSIS),
            DomainSheetSpec("cohorts", "Turmas", "dm_cohorts", "Cadastro autorizado de turmas da Diretoria de Mestrado.", SheetRole.RAW_DATA),
            DomainSheetSpec("students", "Alunos e Defesas", "dm_students", "Base autorizada de alunos, ingressos, qualificações e defesas.", SheetRole.RAW_DATA),
        )

        target_bindings = (
            TargetBindingSpec(DM_METRICS["members"], "dm_targets_effective", "target", criteria_parameters={"period": "target_period"}, criteria_constants={"indicator_code": "DM-01", "metric_key": "cohort_members"}),
            TargetBindingSpec(DM_METRICS["avg_defense"], "dm_targets_effective", "target", criteria_parameters={"period": "target_period"}, criteria_constants={"indicator_code": "DM-02", "metric_key": "average_months_to_defense"}),
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
                title="PAINEL DE GESTÃO · DM",
                kpis=(
                    KpiSpec(DM_METRICS["members"], comparison="comparison_cohort", priority=10),
                    KpiSpec(DM_METRICS["active"], comparison="comparison_cohort", priority=20),
                    KpiSpec(DM_METRICS["occupancy"], comparison="comparison_cohort", priority=30),
                    KpiSpec(DM_METRICS["avg_defense"], comparison="comparison_cohort", priority=40),
                    KpiSpec(DM_METRICS["on_time"], comparison="comparison_cohort", priority=50),
                ),
                charts=(
                    ChartSpec("dm_members_by_cohort", "DM-01 · Membros por turma", DM_METRICS["members"], "dm_cohort_metrics", "cohort", ChartType.COLUMN, ChartRole.COMPARISON, sort="dimension_asc"),
                    ChartSpec("dm_defense_by_cohort", "DM-02 · Tempo médio até a defesa", DM_METRICS["avg_defense"], "dm_cohort_metrics", "cohort", ChartType.COLUMN, ChartRole.COMPARISON, sort="dimension_asc"),
                    ChartSpec("dm_ontime_by_cohort", "Defesas em até 24 meses", DM_METRICS["on_time"], "dm_cohort_metrics", "cohort", ChartType.COLUMN, ChartRole.COMPARISON, sort="dimension_asc"),
                    ChartSpec("dm_risk30_by_cohort", "Ativos >30m sem defesa", DM_METRICS["risk30"], "dm_cohort_metrics", "cohort", ChartType.BAR, ChartRole.ATTENTION, sort="dimension_asc"),
                ),
                attention_blocks=(
                    "DM-01 é acompanhado turma a turma; quando o filtro está em (todas), o card mostra a soma dos membros do recorte.",
                    "DM-02 usa ingresso individual confirmado e defesa registrada na data de corte do snapshot.",
                    "A meta DM-01 é uma referência por turma; leia a comparação detalhada na matriz e nos dados por turma.",
                ),
            ),
            matrix=MatrixSpec(
                metric_code=DM_METRICS["members"],
                row_dimension="area",
                column_dimension="cohort_number",
                delta=True,
                sorting="dimension_asc",
                empty_behavior="blank",
                metric_selector_parameter="matrix_metric",
                metric_options=(
                    MatrixMetricOptionSpec("DM-01 · Membros por turma", DM_METRICS["members"], skip_dimensions=("cohort",)),
                    MatrixMetricOptionSpec("Ocupação · Vagas", DM_METRICS["occupancy"], display_scale=100.0, skip_dimensions=("cohort",)),
                    MatrixMetricOptionSpec("DM-02 · Tempo médio até defesa", DM_METRICS["avg_defense"], skip_dimensions=("cohort",)),
                    MatrixMetricOptionSpec("Defesas · Até 24 meses", DM_METRICS["on_time"], display_scale=100.0, skip_dimensions=("cohort",)),
                    MatrixMetricOptionSpec("Risco · >30m sem defesa", DM_METRICS["risk30"], skip_dimensions=("cohort",)),
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
                status_options=("Não iniciado", "Em andamento", "Concluído", "Suspenso", "Cancelado"),
                completed_statuses=("Concluído", "Cancelado"),
            ),
            technical=TechnicalSpec(include_targets=True, include_indicators=True, include_calc=True, include_support_lists=True, include_period_dimension=False, include_month_dimension=False),
            capabilities=AdapterCapabilities(supports_comparison=True, supports_history_window=False, supports_action_plan=True, interactive_dimensions=("area", "cohort")),
            limitations=limitations,
            metrics=metrics,
            target_bindings=target_bindings,
        )


__all__ = ["DM_METRICS", "DMAdapter", "DMAdapterError"]
