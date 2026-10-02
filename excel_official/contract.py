from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .constants import EXCEL_OFFICIAL_CONTRACT_VERSION

Scalar = str | int | float | bool | None


class ColumnDataType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"


class SheetRole(StrEnum):
    RAW_DATA = "raw_data"
    DIMENSION = "dimension"
    DOMAIN_ANALYSIS = "domain_analysis"
    TECHNICAL = "technical"
    REFERENCE = "reference"


class ChartType(StrEnum):
    LINE = "line"
    COLUMN = "column"
    BAR = "bar"
    PIE = "pie"
    DOUGHNUT = "doughnut"


class ChartRole(StrEnum):
    EVOLUTION = "evolution"
    COMPOSITION = "composition"
    COMPARISON = "comparison"
    ATTENTION = "attention"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class ActionPlanRowSource(StrEnum):
    OFFICIAL = "official"
    LOCAL = "local"


class MetricAggregation(StrEnum):
    VALUE = "value"
    SUM = "sum"
    COUNT = "count"
    RATIO = "ratio"
    AVERAGE = "average"
    WEIGHTED_AVERAGE = "weighted_average"
    NPS = "nps"


class MetricUnit(StrEnum):
    COUNT = "count"
    DECIMAL = "decimal"
    PERCENT = "percent"
    SCORE_0_10 = "score_0_10"
    NPS = "nps"
    CURRENCY_BRL = "currency_brl"
    DAYS = "days"
    MINUTES = "minutes"
    HOURS = "hours"
    MONTHS = "months"


@dataclass(frozen=True, slots=True)
class IdentitySpec:
    workbook_title: str
    directorate_code: str
    directorate_label: str
    adapter_code: str
    adapter_version: int
    system_name: str = "Data UNIVC"
    institution_label: str = "UNIVC"
    scope_label: str = ""
    contract_version: int = EXCEL_OFFICIAL_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class SnapshotSpec:
    export_id: str
    generated_at: datetime
    generated_by: str | None
    authorization_scope: tuple[str, ...]
    system_version: str
    schema_version: str | int
    adapter_version: int
    initial_scope: Mapping[str, Scalar] = field(default_factory=dict)
    minimum_period: str | None = None
    maximum_period: str | None = None
    payload_hash: str | None = None
    contract_version: int = EXCEL_OFFICIAL_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class InitialStateSpec:
    values: Mapping[str, Scalar] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    code: str
    label: str
    values_source: str
    initial_value: Scalar = None
    editable: bool = True
    required: bool = False
    description: str = ""
    depends_on: tuple[str, ...] = ()
    empty_option: str | None = None
    display_order: int = 0
    values_column: str | None = None
    data_type: ColumnDataType | None = None
    number_format: str | None = None


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    code: str
    label: str
    data_type: ColumnDataType
    semantic_type: str | None = None
    source_field: str | None = None
    nullable: bool = True
    visible: bool = True
    technical: bool = False
    number_format: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    code: str
    label: str
    sheet_name: str
    table_name: str
    columns: tuple[ColumnSpec, ...]
    grain: tuple[str, ...] = ()
    rows: tuple[Mapping[str, Any], ...] = ()
    source: str = ""
    technical: bool = False
    sensitivity: str = "internal"
    authorization_scope: tuple[str, ...] = ()
    quality_rule_codes: tuple[str, ...] = ()
    filter_dimensions: tuple[str, ...] = ()
    dimension_columns: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetRef:
    dataset_code: str
    sheet_name: str
    table_name: str
    table_ref: str
    header_row: int
    first_data_row: int
    last_data_row: int
    physical_last_row: int
    first_column: int
    last_column: int
    row_count: int
    column_letters: Mapping[str, str] = field(default_factory=dict)
    has_structural_empty_row: bool = False

    def column_letter(self, column_code: str) -> str:
        try:
            return self.column_letters[column_code]
        except KeyError as exc:
            raise KeyError(f"Coluna {column_code!r} nao existe no DatasetRef {self.dataset_code!r}.") from exc


@dataclass(frozen=True, slots=True)
class SupportListRef:
    parameter_code: str
    defined_name: str
    sheet_name: str
    value_range: str
    row_count: int
    parent_parameter_code: str | None = None
    parent_range: str | None = None
    dynamic: bool = False


@dataclass(frozen=True, slots=True)
class ParameterRef:
    parameter_code: str
    sheet_name: str
    cell_reference: str
    defined_name: str
    support_list_name: str | None = None
    editable: bool = True
    dependency_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParameterSystemRef:
    sheet_name: str
    support_sheet_name: str
    parameters: Mapping[str, ParameterRef] = field(default_factory=dict)
    support_lists: Mapping[str, SupportListRef] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DimensionSpec:
    code: str
    label: str
    dataset_code: str
    key_column: str
    label_column: str
    sort_order_column: str | None = None
    parent_dimension: str | None = None
    hierarchy: tuple[str, ...] = ()
    parent_key_column: str | None = None


@dataclass(frozen=True, slots=True)
class MetricSpec:
    code: str
    label: str
    aggregation: MetricAggregation
    unit: MetricUnit = MetricUnit.DECIMAL
    description: str = ""
    allowed_dimensions: tuple[str, ...] = ()
    offline_recut: bool = True
    valid_min: float | int | None = None
    valid_max: float | int | None = None
    display_precision: int = 1
    number_format: str | None = None
    invalid_when_positive_components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricBinding:
    metric_code: str
    dataset_code: str
    components: Mapping[str, str] = field(default_factory=dict)
    value_column: str | None = None
    filter_parameters: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TargetBindingSpec:
    metric_code: str
    dataset_code: str
    target_column: str
    attention_column: str | None = None
    criteria_parameters: Mapping[str, str] = field(default_factory=dict)
    criteria_constants: Mapping[str, Scalar] = field(default_factory=dict)
    value_scale: float = 1.0


@dataclass(frozen=True, slots=True)
class DomainSheetSpec:
    code: str
    label: str
    dataset_code: str
    purpose: str = ""
    sheet_role: SheetRole = SheetRole.DOMAIN_ANALYSIS
    visible: bool = True
    protected: bool = True
    presentation_mode: str = "table"


@dataclass(frozen=True, slots=True)
class KpiSpec:
    metric_code: str
    label_override: str | None = None
    source_dataset: str | None = None
    comparison: str | None = None
    comparison_metric_code: str | None = None
    target: float | int | None = None
    priority: int = 0


@dataclass(frozen=True, slots=True)
class ChartSpec:
    code: str
    title: str
    metric_code: str
    dataset_code: str
    dimension_code: str
    chart_type: ChartType
    role: ChartRole
    series_dimension_code: str | None = None
    comparison: str | None = None
    sort: str | None = None
    top_n: int | None = None
    window_parameter: str | None = None
    window_reference_parameter: str | None = None
    window_all_value: Scalar = "Todo histórico"
    window_max_categories: int | None = None


@dataclass(frozen=True, slots=True)
class DashboardSpec:
    title: str
    kpis: tuple[KpiSpec, ...] = ()
    charts: tuple[ChartSpec, ...] = ()
    attention_blocks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChartRef:
    code: str
    sheet_name: str
    anchor: str
    chart_type: ChartType
    calc_sheet_name: str
    calc_range: str
    category_count: int
    series_count: int


@dataclass(frozen=True, slots=True)
class ChartSystemRef:
    calc_sheet_name: str
    charts: tuple[ChartRef, ...] = ()
    next_row: int = 1


@dataclass(frozen=True, slots=True)
class KpiRef:
    metric_code: str
    label_cell: str
    value_cell: str
    card_range: str
    comparison_cell: str | None = None
    delta_cell: str | None = None
    target_cell: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardRef:
    sheet_name: str
    context_cells: Mapping[str, str] = field(default_factory=dict)
    kpis: tuple[KpiRef, ...] = ()
    chart_anchors: Mapping[str, str] = field(default_factory=dict)
    next_row: int = 1


@dataclass(frozen=True, slots=True)
class MatrixMetricOptionSpec:
    selector_value: Scalar
    metric_code: str
    display_scale: float = 1.0
    skip_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatrixSpec:
    metric_code: str
    row_dimension: str
    column_dimension: str
    target: float | int | None = None
    delta: bool = True
    sorting: str | None = None
    empty_behavior: str = "blank"
    metric_selector_parameter: str | None = None
    metric_options: tuple[MatrixMetricOptionSpec, ...] = ()
    selector_number_format: str | None = None


@dataclass(frozen=True, slots=True)
class MatrixRef:
    sheet_name: str
    metric_code: str
    row_dimension: str
    column_dimension: str
    header_row: int
    first_data_row: int
    last_data_row: int
    first_value_column: int
    last_value_column: int
    value_range: str
    target_column: int | None = None
    delta_column: int | None = None


@dataclass(frozen=True, slots=True)
class QualityCheckSpec:
    code: str
    label: str
    check_type: str
    source_code: str
    severity: QualitySeverity = QualitySeverity.WARNING
    message_ok: str = "OK"
    message_error: str = "Inconsistencia encontrada"


@dataclass(frozen=True, slots=True)
class LimitationSpec:
    code: str
    title: str
    description: str
    severity: QualitySeverity = QualitySeverity.INFO
    affected_metric: str | None = None
    affected_dimension: str | None = None


@dataclass(frozen=True, slots=True)
class QualitySpec:
    dataset_checks: tuple[QualityCheckSpec, ...] = ()
    metric_checks: tuple[QualityCheckSpec, ...] = ()
    coverage_checks: tuple[QualityCheckSpec, ...] = ()
    snapshot_checks: tuple[QualityCheckSpec, ...] = ()
    limitations: tuple[LimitationSpec, ...] = ()

    @property
    def checks(self) -> tuple[QualityCheckSpec, ...]:
        return self.dataset_checks + self.metric_checks + self.coverage_checks + self.snapshot_checks


@dataclass(frozen=True, slots=True)
class QualityCheckRef:
    code: str
    category: str
    severity: QualitySeverity
    evidence_cell: str
    result_cell: str
    message_cell: str


@dataclass(frozen=True, slots=True)
class QualityRef:
    sheet_name: str
    overall_status_cell: str
    checks: tuple[QualityCheckRef, ...] = ()
    coverage_range: str | None = None
    sources_range: str | None = None
    snapshot_range: str | None = None
    limitations_range: str | None = None


@dataclass(frozen=True, slots=True)
class ActionPlanRowSpec:
    values: Mapping[str, Any] = field(default_factory=dict)
    source: ActionPlanRowSource = ActionPlanRowSource.OFFICIAL


@dataclass(frozen=True, slots=True)
class ActionPlanSpec:
    enabled: bool = True
    fields: tuple[str, ...] = (
        "indicator",
        "problem",
        "diagnosis",
        "action",
        "owner",
        "deadline",
        "status",
        "days_remaining",
    )
    official_fields: tuple[str, ...] = ()
    local_editable_fields: tuple[str, ...] = ()
    rows: tuple[ActionPlanRowSpec, ...] = ()
    local_blank_rows: int = 12
    status_options: tuple[str, ...] = (
        "N\u00e3o iniciado",
        "Em andamento",
        "Conclu\u00eddo",
        "Suspenso",
    )
    completed_statuses: tuple[str, ...] = ("Conclu\u00eddo",)
    field_labels: Mapping[str, str] = field(default_factory=dict)
    indicator_field: str = "indicator"
    deadline_field: str = "deadline"
    status_field: str = "status"
    days_remaining_field: str = "days_remaining"
    local_notice: str = (
        "Altera\u00e7\u00f5es realizadas em linhas LOCAL permanecem somente neste arquivo e n\u00e3o s\u00e3o "
        "sincronizadas automaticamente com o Data UNIVC."
    )


@dataclass(frozen=True, slots=True)
class ActionPlanRef:
    sheet_name: str
    header_row: int
    first_data_row: int
    last_data_row: int
    table_range: str
    official_row_count: int
    local_row_count: int
    local_editable_ranges: Mapping[str, str] = field(default_factory=dict)
    status_validation_range: str | None = None
    indicator_validation_range: str | None = None
    notice_cell: str = "A2"


@dataclass(frozen=True, slots=True)
class TechnicalSpec:
    include_targets: bool = True
    include_indicators: bool = True
    include_calc: bool = True
    include_support_lists: bool = True
    include_period_dimension: bool = True
    include_month_dimension: bool = False


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    supports_comparison: bool = False
    supports_history_window: bool = False
    supports_action_plan: bool = True
    interactive_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkbookSpec:
    identity: IdentitySpec
    snapshot: SnapshotSpec
    initial_state: InitialStateSpec
    parameters: tuple[ParameterSpec, ...]
    datasets: tuple[DatasetSpec, ...]
    dimensions: tuple[DimensionSpec, ...]
    metric_codes: tuple[str, ...]
    metric_bindings: tuple[MetricBinding, ...]
    domain_sheets: tuple[DomainSheetSpec, ...]
    dashboard: DashboardSpec
    matrix: MatrixSpec | None
    quality: QualitySpec = field(default_factory=QualitySpec)
    action_plan: ActionPlanSpec = field(default_factory=ActionPlanSpec)
    technical: TechnicalSpec = field(default_factory=TechnicalSpec)
    capabilities: AdapterCapabilities = field(default_factory=AdapterCapabilities)
    limitations: tuple[LimitationSpec, ...] = ()
    metrics: tuple[MetricSpec, ...] = ()
    target_bindings: tuple[TargetBindingSpec, ...] = ()
