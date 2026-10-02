from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .constants import (
    ALL_RESERVED_SHEETS,
    EXCEL_OFFICIAL_CONTRACT_VERSION,
    REQUIRED_INSTITUTIONAL_SHEETS,
    STANDARD_TECHNICAL_SHEETS,
    OPTIONAL_TECHNICAL_SHEETS,
)
from .contract import ActionPlanRowSource, MetricAggregation, WorkbookSpec
from .exceptions import SpecValidationIssue, WorkbookSpecValidationError

_INVALID_SHEET_CHARS = re.compile(r"[\\/*?:\[\]]")
_VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_A1_LIKE_NAME = re.compile(r"^[A-Za-z]{1,3}[1-9][0-9]*$")
_R1C1_LIKE_NAME = re.compile(r"^R[1-9][0-9]*C[1-9][0-9]*$", re.IGNORECASE)


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(value for value in values if value)
    return {value for value, count in counts.items() if count > 1}


def _duplicates_casefold(values: Iterable[str]) -> set[str]:
    counts = Counter(value.casefold() for value in values if value)
    return {value for value, count in counts.items() if count > 1}


def _issue(issues: list[SpecValidationIssue], code: str, path: str, message: str, severity: str = "ERROR") -> None:
    issues.append(SpecValidationIssue(code=code, path=path, message=message, severity=severity))


def _validate_sheet_name(issues: list[SpecValidationIssue], sheet_name: str, path: str) -> None:
    if not sheet_name.strip():
        _issue(issues, "sheet.empty", path, "Nome da aba nao pode ser vazio.")
    if len(sheet_name) > 31:
        _issue(issues, "sheet.too_long", path, "Nome da aba excede 31 caracteres do Excel.")
    if _INVALID_SHEET_CHARS.search(sheet_name):
        _issue(issues, "sheet.invalid_chars", path, "Nome da aba contem caractere invalido do Excel.")


def validate_workbook_spec(spec: WorkbookSpec) -> tuple[SpecValidationIssue, ...]:
    issues: list[SpecValidationIssue] = []

    if spec.identity.contract_version != EXCEL_OFFICIAL_CONTRACT_VERSION:
        _issue(
            issues,
            "contract.unsupported_version",
            "identity.contract_version",
            f"Contract V{spec.identity.contract_version} nao e suportado por este core (V{EXCEL_OFFICIAL_CONTRACT_VERSION}).",
        )
    if spec.snapshot.contract_version != spec.identity.contract_version:
        _issue(
            issues,
            "contract.version_mismatch",
            "snapshot.contract_version",
            "Versao do contrato no snapshot difere da identidade do workbook.",
        )
    if spec.snapshot.adapter_version != spec.identity.adapter_version:
        _issue(
            issues,
            "adapter.version_mismatch",
            "snapshot.adapter_version",
            "Versao do adapter no snapshot difere da identidade do workbook.",
        )

    collections = {
        "parameter": [item.code for item in spec.parameters],
        "dataset": [item.code for item in spec.datasets],
        "dimension": [item.code for item in spec.dimensions],
        "domain_sheet": [item.code for item in spec.domain_sheets],
        "metric": [item.code for item in spec.metrics] or list(spec.metric_codes),
        "metric_binding": [item.metric_code for item in spec.metric_bindings],
        "target_binding": [item.metric_code for item in spec.target_bindings],
        "chart": [item.code for item in spec.dashboard.charts],
        "quality_check": [item.code for item in spec.quality.checks],
        "limitation": [item.code for item in (spec.quality.limitations + spec.limitations)],
    }
    for kind, values in collections.items():
        for duplicate in sorted(_duplicates(values)):
            _issue(issues, f"{kind}.duplicate_code", kind, f"Codigo duplicado: {duplicate}.")

    dataset_by_code = {item.code: item for item in spec.datasets}
    dimension_by_code = {item.code: item for item in spec.dimensions}
    parameter_by_code = {item.code: item for item in spec.parameters}
    metric_by_code = {item.code: item for item in spec.metrics}
    metric_codes = set(spec.metric_codes) | set(metric_by_code)

    for metric in spec.metrics:
        path = f"metrics.{metric.code}"
        if not metric.code.strip():
            _issue(issues, "metric.empty_code", f"{path}.code", "Codigo de metrica nao pode ser vazio.")
        if not metric.label.strip():
            _issue(issues, "metric.empty_label", f"{path}.label", "Label da metrica nao pode ser vazio.")
        if metric.display_precision < 0 or metric.display_precision > 6:
            _issue(issues, "metric.invalid_display_precision", f"{path}.display_precision", "Precisao de exibicao deve estar entre 0 e 6.")
        if metric.valid_min is not None and metric.valid_max is not None and metric.valid_min > metric.valid_max:
            _issue(issues, "metric.invalid_range", path, "valid_min nao pode ser maior que valid_max.")
        for dimension_code in metric.allowed_dimensions:
            if dimension_code not in dimension_by_code:
                _issue(issues, "metric.unknown_allowed_dimension", f"{path}.allowed_dimensions", f"Dimensao inexistente: {dimension_code}.")

    table_names = [item.table_name for item in spec.datasets]
    for duplicate in sorted(_duplicates_casefold(table_names)):
        _issue(issues, "dataset.duplicate_table_name", "datasets", f"Nome de tabela Excel duplicado (case-insensitive): {duplicate}.")

    sheet_names = [item.sheet_name for item in spec.datasets]
    for duplicate in sorted(_duplicates_casefold(sheet_names)):
        _issue(issues, "dataset.duplicate_sheet_name", "datasets", f"Mais de um dataset usa a mesma aba (case-insensitive): {duplicate!r}.")

    for dataset in spec.datasets:
        path = f"datasets.{dataset.code}"
        _validate_sheet_name(issues, dataset.sheet_name, f"{path}.sheet_name")
        institutional_names = {name.casefold() for name in REQUIRED_INSTITUTIONAL_SHEETS}
        technical_names = {name.casefold() for name in STANDARD_TECHNICAL_SHEETS + OPTIONAL_TECHNICAL_SHEETS}
        if dataset.sheet_name.casefold() in institutional_names:
            _issue(issues, "dataset.institutional_sheet_reserved", f"{path}.sheet_name", "Dataset nao pode usar uma aba institucional reservada.")
        if dataset.sheet_name.casefold() in technical_names and not dataset.technical:
            _issue(issues, "dataset.technical_sheet_requires_flag", f"{path}.technical", "Dataset em aba tecnica deve declarar technical=True.")
        invalid_table = (
            not _VALID_TABLE_NAME.fullmatch(dataset.table_name)
            or len(dataset.table_name) > 255
            or bool(_A1_LIKE_NAME.fullmatch(dataset.table_name))
            or bool(_R1C1_LIKE_NAME.fullmatch(dataset.table_name))
        )
        if invalid_table:
            _issue(issues, "dataset.invalid_table_name", f"{path}.table_name", "Nome de tabela Excel invalido, excessivamente longo ou semelhante a referencia de celula.")
        if not dataset.columns:
            _issue(issues, "dataset.no_columns", f"{path}.columns", "Dataset precisa declarar ao menos uma coluna.")
        column_codes = [column.code for column in dataset.columns]
        for duplicate in sorted(_duplicates(column_codes)):
            _issue(issues, "column.duplicate_code", f"{path}.columns", f"Coluna duplicada: {duplicate}.")
        column_labels = [column.label for column in dataset.columns]
        for duplicate in sorted(_duplicates_casefold(column_labels)):
            _issue(issues, "column.duplicate_label", f"{path}.columns", f"Cabecalho Excel duplicado (case-insensitive): {duplicate}.")
        for column in dataset.columns:
            if not column.label.strip():
                _issue(issues, "column.empty_label", f"{path}.columns.{column.code}.label", "Cabecalho Excel nao pode ser vazio.")
        known_columns = set(column_codes)
        for grain_column in dataset.grain:
            if grain_column not in known_columns:
                _issue(issues, "dataset.unknown_grain_column", f"{path}.grain", f"Grain referencia coluna inexistente: {grain_column}.")
        for dimension in dataset.filter_dimensions:
            if dimension not in dimension_by_code:
                _issue(issues, "dataset.unknown_filter_dimension", f"{path}.filter_dimensions", f"Dimensao inexistente: {dimension}.")
        for dimension_code, column_code in dataset.dimension_columns.items():
            if dimension_code not in dimension_by_code:
                _issue(issues, "dataset.unknown_dimension_mapping", f"{path}.dimension_columns.{dimension_code}", f"Dimensao inexistente: {dimension_code}.")
            if column_code not in known_columns:
                _issue(issues, "dataset.unknown_dimension_column", f"{path}.dimension_columns.{dimension_code}", f"Coluna inexistente no dataset {dataset.code}: {column_code}.")
            if dataset.filter_dimensions and dimension_code not in dataset.filter_dimensions:
                _issue(issues, "dataset.dimension_mapping_not_filterable", f"{path}.dimension_columns.{dimension_code}", "Mapeamento de dimensao precisa constar em filter_dimensions quando filter_dimensions foi declarado.")
        for dimension_code in dataset.filter_dimensions:
            if dimension_code not in dataset.dimension_columns and dimension_code not in known_columns:
                _issue(issues, "dataset.missing_dimension_column", f"{path}.filter_dimensions", f"Dimensao {dimension_code!r} nao possui coluna homonima nem dimension_columns explicito.")
        for row_index, row in enumerate(dataset.rows):
            unknown_keys = sorted(set(row) - known_columns)
            if unknown_keys:
                _issue(issues, "dataset.row_unknown_column", f"{path}.rows[{row_index}]", f"Linha contem colunas nao declaradas: {', '.join(unknown_keys)}.")

    for dimension in spec.dimensions:
        path = f"dimensions.{dimension.code}"
        dataset = dataset_by_code.get(dimension.dataset_code)
        if dataset is None:
            _issue(issues, "dimension.unknown_dataset", f"{path}.dataset_code", f"Dataset inexistente: {dimension.dataset_code}.")
            continue
        columns = {column.code for column in dataset.columns}
        for attr, column_code in (
            ("key_column", dimension.key_column),
            ("label_column", dimension.label_column),
            ("sort_order_column", dimension.sort_order_column),
            ("parent_key_column", dimension.parent_key_column),
        ):
            if column_code and column_code not in columns:
                _issue(issues, "dimension.unknown_column", f"{path}.{attr}", f"Coluna inexistente no dataset {dataset.code}: {column_code}.")
        if dimension.parent_dimension:
            if dimension.parent_dimension == dimension.code:
                _issue(issues, "dimension.self_parent", f"{path}.parent_dimension", "Dimensao nao pode ser pai de si mesma.")
            elif dimension.parent_dimension not in dimension_by_code:
                _issue(issues, "dimension.unknown_parent", f"{path}.parent_dimension", f"Dimensao pai inexistente: {dimension.parent_dimension}.")
            parent_key_column = dimension.parent_key_column or dimension.parent_dimension
            if parent_key_column not in columns:
                _issue(
                    issues,
                    "dimension.missing_parent_key_column",
                    f"{path}.parent_key_column",
                    f"Dimensao filha precisa da coluna {parent_key_column!r} para relacionar membros ao pai.",
                )

    for parameter in spec.parameters:
        path = f"parameters.{parameter.code}"
        if parameter.values_source and parameter.values_source not in dimension_by_code and parameter.values_source not in dataset_by_code:
            _issue(issues, "parameter.unknown_values_source", f"{path}.values_source", f"Fonte de valores inexistente: {parameter.values_source}.")
        if parameter.values_column:
            dataset = dataset_by_code.get(parameter.values_source)
            if dataset is None:
                _issue(issues, "parameter.values_column_requires_dataset", f"{path}.values_column", "values_column so pode ser usado quando values_source referencia diretamente um dataset.")
            elif parameter.values_column not in {column.code for column in dataset.columns}:
                _issue(issues, "parameter.unknown_values_column", f"{path}.values_column", f"Coluna inexistente no dataset {dataset.code}: {parameter.values_column}.")
        if len(parameter.depends_on) > 1:
            _issue(issues, "parameter.multiple_dependencies_not_supported_v1", f"{path}.depends_on", "Contract V1 suporta no maximo uma dependencia de dropdown por parametro.")
        for dependency in parameter.depends_on:
            if dependency == parameter.code:
                _issue(issues, "parameter.self_dependency", f"{path}.depends_on", "Parametro nao pode depender de si mesmo.")
            elif dependency not in parameter_by_code:
                _issue(issues, "parameter.unknown_dependency", f"{path}.depends_on", f"Parametro dependente inexistente: {dependency}.")
        if parameter.depends_on and parameter.values_source:
            dimension = dimension_by_code.get(parameter.values_source)
            dependency = parameter_by_code.get(parameter.depends_on[0]) if parameter.depends_on else None
            if dimension is None or not dimension.parent_dimension:
                _issue(issues, "parameter.dependency_requires_child_dimension", f"{path}.values_source", "Dropdown dependente precisa usar uma dimensao filha com parent_dimension.")
            elif dependency is not None and dependency.values_source != dimension.parent_dimension:
                _issue(
                    issues,
                    "parameter.dependency_dimension_mismatch",
                    f"{path}.depends_on",
                    f"Parametro pai usa {dependency.values_source!r}, mas a dimensao filha depende de {dimension.parent_dimension!r}.",
                )
        if (
            parameter.required
            and parameter.initial_value is None
            and parameter.code not in spec.initial_state.values
            and parameter.code not in spec.snapshot.initial_scope
        ):
            _issue(issues, "parameter.required_without_initial_value", path, "Parametro obrigatorio nao possui estado inicial.")

    for key in spec.initial_state.values:
        if key not in parameter_by_code:
            _issue(issues, "initial_state.unknown_parameter", f"initial_state.{key}", f"Estado inicial referencia parametro inexistente: {key}.", severity="WARNING")

    required_components = {
        MetricAggregation.RATIO: {"numerator", "denominator"},
        MetricAggregation.AVERAGE: {"sum", "count"},
        MetricAggregation.WEIGHTED_AVERAGE: {"weighted_sum", "weight"},
        MetricAggregation.NPS: {"promoters", "detractors", "respondents"},
    }

    for binding in spec.metric_bindings:
        path = f"metric_bindings.{binding.metric_code}"
        if binding.metric_code not in metric_codes:
            _issue(issues, "metric_binding.unknown_metric", f"{path}.metric_code", f"Metrica inexistente: {binding.metric_code}.")
        metric = metric_by_code.get(binding.metric_code)
        dataset = dataset_by_code.get(binding.dataset_code)
        if dataset is None:
            _issue(issues, "metric_binding.unknown_dataset", f"{path}.dataset_code", f"Dataset inexistente: {binding.dataset_code}.")
            continue
        columns = {column.code for column in dataset.columns}
        column_by_code = {column.code: column for column in dataset.columns}
        for component, column_code in binding.components.items():
            if column_code not in columns:
                _issue(issues, "metric_binding.unknown_component_column", f"{path}.components.{component}", f"Coluna inexistente no dataset {dataset.code}: {column_code}.")
            elif column_by_code[column_code].data_type.value not in {"integer", "decimal"}:
                _issue(issues, "metric_binding.non_numeric_component", f"{path}.components.{component}", f"Componente numerico {component!r} aponta para coluna nao numerica: {column_code}.")
        if binding.value_column and binding.value_column not in columns:
            _issue(issues, "metric_binding.unknown_value_column", f"{path}.value_column", f"Coluna inexistente no dataset {dataset.code}: {binding.value_column}.")
        elif binding.value_column and column_by_code[binding.value_column].data_type.value not in {"integer", "decimal"}:
            _issue(issues, "metric_binding.non_numeric_value_column", f"{path}.value_column", f"value_column precisa ser numerica: {binding.value_column}.")
        if metric is not None:
            needed = required_components.get(metric.aggregation, set())
            missing = sorted(needed - set(binding.components))
            if missing:
                _issue(issues, "metric_binding.missing_components", f"{path}.components", f"Componentes obrigatorios ausentes para {metric.aggregation.value}: {', '.join(missing)}.")
            invalidating_missing = sorted(set(metric.invalid_when_positive_components) - set(binding.components))
            if invalidating_missing:
                _issue(
                    issues,
                    "metric_binding.missing_invalidating_components",
                    f"{path}.components",
                    "Componentes de invalidacao ausentes: " + ", ".join(invalidating_missing) + ".",
                )
            if metric.aggregation in {MetricAggregation.VALUE, MetricAggregation.SUM} and not binding.value_column:
                _issue(issues, "metric_binding.value_column_required", f"{path}.value_column", f"{metric.aggregation.value} exige value_column.")
            if metric.aggregation == MetricAggregation.COUNT and binding.components:
                _issue(issues, "metric_binding.count_components_not_supported", f"{path}.components", "COUNT V1 usa linhas filtradas ou value_column; components nao sao suportados.")
            if metric.allowed_dimensions:
                for dimension_code in binding.filter_parameters:
                    if dimension_code not in metric.allowed_dimensions:
                        _issue(issues, "metric_binding.dimension_not_allowed", f"{path}.filter_parameters.{dimension_code}", f"Metrica {metric.code} nao permite recorte por {dimension_code}.")
            if not metric.offline_recut and binding.filter_parameters:
                _issue(issues, "metric_binding.offline_recut_disabled", f"{path}.filter_parameters", "Metrica com offline_recut=False nao pode declarar filtros locais no Contract V1.")
        elif not binding.components and not binding.value_column:
            _issue(issues, "metric_binding.empty", path, "Binding deve declarar components ou value_column.")
        for dimension_code, parameter_code in binding.filter_parameters.items():
            if dimension_code not in dimension_by_code:
                _issue(issues, "metric_binding.unknown_filter_dimension", f"{path}.filter_parameters.{dimension_code}", f"Dimensao inexistente: {dimension_code}.")
                continue
            if dimension_code not in dataset.filter_dimensions:
                _issue(issues, "metric_binding.dataset_dimension_not_filterable", f"{path}.filter_parameters.{dimension_code}", f"Dataset {dataset.code} nao declara {dimension_code} em filter_dimensions.")
            parameter = parameter_by_code.get(parameter_code)
            if parameter is None:
                _issue(issues, "metric_binding.unknown_filter_parameter", f"{path}.filter_parameters.{dimension_code}", f"Parametro inexistente: {parameter_code}.")
            elif parameter.values_source != dimension_code:
                _issue(issues, "metric_binding.filter_parameter_dimension_mismatch", f"{path}.filter_parameters.{dimension_code}", f"Parametro {parameter_code} usa values_source={parameter.values_source!r}, esperado {dimension_code!r}.")

    for sheet in spec.domain_sheets:
        path = f"domain_sheets.{sheet.code}"
        _validate_sheet_name(issues, sheet.label, f"{path}.label")
        if sheet.dataset_code not in dataset_by_code:
            _issue(issues, "domain_sheet.unknown_dataset", f"{path}.dataset_code", f"Dataset inexistente: {sheet.dataset_code}.")
        if sheet.label.casefold() in {name.casefold() for name in ALL_RESERVED_SHEETS}:
            _issue(issues, "domain_sheet.reserved_name", f"{path}.label", "Aba de dominio nao pode usar nome reservado institucional/tecnico.")

    binding_by_metric = {item.metric_code: item for item in spec.metric_bindings}
    for target_binding in spec.target_bindings:
        path = f"target_bindings.{target_binding.metric_code}"
        if target_binding.metric_code not in metric_codes:
            _issue(issues, "target_binding.unknown_metric", f"{path}.metric_code", f"Metrica inexistente: {target_binding.metric_code}.")
        dataset = dataset_by_code.get(target_binding.dataset_code)
        if dataset is None:
            _issue(issues, "target_binding.unknown_dataset", f"{path}.dataset_code", f"Dataset inexistente: {target_binding.dataset_code}.")
            continue
        columns = {column.code for column in dataset.columns}
        for column_code in (target_binding.target_column, target_binding.attention_column):
            if column_code and column_code not in columns:
                _issue(issues, "target_binding.unknown_value_column", path, f"Coluna de meta inexistente: {column_code}.")
        for column_code, parameter_code in target_binding.criteria_parameters.items():
            if column_code not in columns:
                _issue(issues, "target_binding.unknown_criteria_column", f"{path}.criteria_parameters", f"Coluna inexistente: {column_code}.")
            if parameter_code not in parameter_by_code:
                _issue(issues, "target_binding.unknown_parameter", f"{path}.criteria_parameters", f"Parametro inexistente: {parameter_code}.")
        for column_code in target_binding.criteria_constants:
            if column_code not in columns:
                _issue(issues, "target_binding.unknown_criteria_column", f"{path}.criteria_constants", f"Coluna inexistente: {column_code}.")
        if target_binding.value_scale == 0:
            _issue(issues, "target_binding.invalid_scale", f"{path}.value_scale", "value_scale nao pode ser zero.")

    for kpi_index, kpi in enumerate(spec.dashboard.kpis):
        path = f"dashboard.kpis[{kpi_index}]"
        if kpi.metric_code not in metric_codes:
            _issue(issues, "kpi.unknown_metric", f"{path}.metric_code", f"Metrica inexistente: {kpi.metric_code}.")
        binding = binding_by_metric.get(kpi.metric_code)
        if kpi.source_dataset and kpi.source_dataset not in dataset_by_code:
            _issue(issues, "kpi.unknown_dataset", f"{path}.source_dataset", f"Dataset inexistente: {kpi.source_dataset}.")
        if kpi.source_dataset and binding is not None and kpi.source_dataset != binding.dataset_code:
            _issue(issues, "kpi.dataset_binding_mismatch", f"{path}.source_dataset", f"KPI usa {kpi.source_dataset}, mas MetricBinding usa {binding.dataset_code}.")
        if kpi.comparison:
            comparison_parameter = parameter_by_code.get(kpi.comparison)
            if comparison_parameter is None:
                _issue(issues, "kpi.unknown_comparison_parameter", f"{path}.comparison", f"Parametro de comparacao inexistente: {kpi.comparison}.")
            elif binding is None:
                _issue(issues, "kpi.comparison_without_binding", f"{path}.comparison", "KPI com comparacao precisa de MetricBinding.")
            else:
                dimension_code = comparison_parameter.values_source
                if not dimension_code or dimension_code not in binding.filter_parameters:
                    _issue(issues, "kpi.comparison_dimension_not_bound", f"{path}.comparison", f"Parametro de comparacao usa dimensao {dimension_code!r}, que nao participa do binding principal.")

    for chart in spec.dashboard.charts:
        path = f"dashboard.charts.{chart.code}"
        metric = metric_by_code.get(chart.metric_code)
        binding = binding_by_metric.get(chart.metric_code)
        dataset = dataset_by_code.get(chart.dataset_code)
        if chart.metric_code not in metric_codes:
            _issue(issues, "chart.unknown_metric", f"{path}.metric_code", f"Metrica inexistente: {chart.metric_code}.")
        if dataset is None:
            _issue(issues, "chart.unknown_dataset", f"{path}.dataset_code", f"Dataset inexistente: {chart.dataset_code}.")
        if binding is None and chart.metric_code in metric_codes:
            _issue(issues, "chart.metric_binding_required", f"{path}.metric_code", "Grafico precisa de MetricBinding.")
        elif binding is not None and binding.dataset_code != chart.dataset_code:
            _issue(issues, "chart.dataset_binding_mismatch", f"{path}.dataset_code", f"Grafico usa {chart.dataset_code}, mas MetricBinding usa {binding.dataset_code}.")
        if chart.dimension_code not in dimension_by_code:
            _issue(issues, "chart.unknown_dimension", f"{path}.dimension_code", f"Dimensao inexistente: {chart.dimension_code}.")
        elif metric is not None and metric.allowed_dimensions and chart.dimension_code not in metric.allowed_dimensions:
            _issue(issues, "chart.dimension_not_allowed", f"{path}.dimension_code", f"Metrica {metric.code} nao permite recorte por {chart.dimension_code}.")
        if chart.series_dimension_code and chart.series_dimension_code not in dimension_by_code:
            _issue(issues, "chart.unknown_series_dimension", f"{path}.series_dimension_code", f"Dimensao de serie inexistente: {chart.series_dimension_code}.")
        elif chart.series_dimension_code and metric is not None and metric.allowed_dimensions and chart.series_dimension_code not in metric.allowed_dimensions:
            _issue(issues, "chart.series_dimension_not_allowed", f"{path}.series_dimension_code", f"Metrica {metric.code} nao permite serie por {chart.series_dimension_code}.")
        if chart.series_dimension_code and chart.comparison:
            _issue(issues, "chart.series_and_comparison_not_supported", path, "Contract V1 nao combina serie por dimensao e comparison no mesmo grafico.")
        if chart.comparison:
            comparison_parameter = parameter_by_code.get(chart.comparison)
            if comparison_parameter is None:
                _issue(issues, "chart.unknown_comparison_parameter", f"{path}.comparison", f"Parametro inexistente: {chart.comparison}.")
            elif comparison_parameter.values_source == chart.dimension_code:
                _issue(issues, "chart.comparison_matches_category_dimension", f"{path}.comparison", "Parametro de comparacao nao pode controlar a mesma dimensao das categorias.")
            elif binding is not None and comparison_parameter.values_source not in binding.filter_parameters:
                _issue(issues, "chart.comparison_dimension_not_bound", f"{path}.comparison", f"Dimensao {comparison_parameter.values_source!r} nao participa do MetricBinding.")
        if chart.chart_type.value in {"pie", "doughnut"} and (chart.series_dimension_code or chart.comparison):
            _issue(issues, "chart.circular_multi_series_not_supported", path, "Pizza/rosca do Contract V1 aceita somente uma serie.")
        if chart.sort not in {None, "dimension_asc", "dimension_desc", "label_asc", "label_desc"}:
            _issue(issues, "chart.invalid_sort", f"{path}.sort", f"Ordenacao nao suportada no Contract V1: {chart.sort!r}.")
        if chart.top_n is not None and chart.top_n <= 0:
            _issue(issues, "chart.invalid_top_n", f"{path}.top_n", "top_n deve ser maior que zero.")
        if chart.window_parameter:
            if chart.window_parameter not in parameter_by_code:
                _issue(issues, "chart.unknown_window_parameter", f"{path}.window_parameter", f"Parametro inexistente: {chart.window_parameter}.")
            if not chart.window_reference_parameter or chart.window_reference_parameter not in parameter_by_code:
                _issue(issues, "chart.unknown_window_reference_parameter", f"{path}.window_reference_parameter", "Parametro de referencia da janela inexistente.")
            else:
                reference_parameter = parameter_by_code[chart.window_reference_parameter]
                if reference_parameter.values_source != chart.dimension_code:
                    _issue(issues, "chart.window_reference_dimension_mismatch", f"{path}.window_reference_parameter", "Parametro de referencia precisa usar a dimensao do eixo.")
            if chart.window_max_categories is not None and chart.window_max_categories <= 0:
                _issue(issues, "chart.invalid_window_max_categories", f"{path}.window_max_categories", "window_max_categories deve ser maior que zero.")
            if chart.series_dimension_code or chart.comparison:
                _issue(issues, "chart.window_multi_series_not_supported", path, "Janela dinamica V1 nao combina series/comparison.")
        if dataset is not None:
            dataset_columns = {column.code for column in dataset.columns}
            for dimension_code, field_name in ((chart.dimension_code, "dimension_code"), (chart.series_dimension_code, "series_dimension_code")):
                if not dimension_code or dimension_code not in dimension_by_code:
                    continue
                column_code = dataset.dimension_columns.get(dimension_code, dimension_code)
                if column_code not in dataset_columns:
                    _issue(issues, "chart.dimension_not_available_in_dataset", f"{path}.{field_name}", f"Dataset {dataset.code} nao possui coluna para dimensao {dimension_code}.")

    if spec.matrix is not None:
        matrix = spec.matrix
        matrix_metric_codes = [option.metric_code for option in matrix.metric_options] or [matrix.metric_code]
        metric = metric_by_code.get(matrix.metric_code)
        binding = binding_by_metric.get(matrix.metric_code)
        if matrix.metric_selector_parameter:
            if matrix.metric_selector_parameter not in parameter_by_code:
                _issue(issues, "matrix.unknown_selector_parameter", "matrix.metric_selector_parameter", f"Parametro inexistente: {matrix.metric_selector_parameter}.")
        elif len(matrix_metric_codes) > 1:
            _issue(issues, "matrix.selector_parameter_required", "matrix.metric_selector_parameter", "Matriz com multiplas metricas exige seletor.")
        selector_values = [str(option.selector_value) for option in matrix.metric_options]
        for duplicate in sorted(_duplicates(selector_values)):
            _issue(issues, "matrix.duplicate_selector_value", "matrix.metric_options", f"Valor de seletor duplicado: {duplicate}.")
        for option in matrix.metric_options:
            if option.metric_code not in metric_codes:
                _issue(issues, "matrix.unknown_option_metric", "matrix.metric_options", f"Metrica inexistente: {option.metric_code}.")
            if option.metric_code not in binding_by_metric:
                _issue(issues, "matrix.missing_option_binding", "matrix.metric_options", f"MetricBinding inexistente: {option.metric_code}.")
            if option.display_scale == 0:
                _issue(issues, "matrix.invalid_display_scale", "matrix.metric_options", "display_scale nao pode ser zero.")
            for skipped_dimension in option.skip_dimensions:
                if skipped_dimension not in dimension_by_code:
                    _issue(issues, "matrix.unknown_skipped_dimension", "matrix.metric_options", f"Dimensao inexistente: {skipped_dimension}.")
        if matrix.metric_code not in metric_codes:
            _issue(issues, "matrix.unknown_metric", "matrix.metric_code", f"Metrica inexistente: {matrix.metric_code}.")
        if binding is None:
            _issue(issues, "matrix.missing_metric_binding", "matrix.metric_code", f"MetricBinding inexistente: {matrix.metric_code}.")
        if matrix.row_dimension not in dimension_by_code:
            _issue(issues, "matrix.unknown_row_dimension", "matrix.row_dimension", f"Dimensao inexistente: {matrix.row_dimension}.")
        if matrix.column_dimension not in dimension_by_code:
            _issue(issues, "matrix.unknown_column_dimension", "matrix.column_dimension", f"Dimensao inexistente: {matrix.column_dimension}.")
        if matrix.row_dimension == matrix.column_dimension:
            _issue(issues, "matrix.same_dimensions", "matrix", "Dimensoes de linha e coluna precisam ser diferentes.")
        if matrix.sorting not in {None, "dimension_asc", "dimension_desc", "label_asc", "label_desc"}:
            _issue(issues, "matrix.invalid_sort", "matrix.sorting", f"Ordenacao nao suportada: {matrix.sorting!r}.")
        if matrix.empty_behavior not in {"blank", "zero"}:
            _issue(issues, "matrix.invalid_empty_behavior", "matrix.empty_behavior", f"empty_behavior nao suportado: {matrix.empty_behavior!r}.")
        if metric is not None:
            for dimension_code, field_name in ((matrix.row_dimension, "row_dimension"), (matrix.column_dimension, "column_dimension")):
                if dimension_code in dimension_by_code and metric.allowed_dimensions and dimension_code not in metric.allowed_dimensions:
                    _issue(issues, "matrix.dimension_not_allowed", f"matrix.{field_name}", f"Metrica {metric.code} nao permite recorte por {dimension_code}.")
        if binding is not None:
            dataset = dataset_by_code.get(binding.dataset_code)
            if dataset is not None:
                dataset_columns = {column.code for column in dataset.columns}
                for dimension_code, field_name in ((matrix.row_dimension, "row_dimension"), (matrix.column_dimension, "column_dimension")):
                    if dimension_code not in dimension_by_code:
                        continue
                    column_code = dataset.dimension_columns.get(dimension_code, dimension_code)
                    if column_code not in dataset_columns:
                        _issue(issues, "matrix.dimension_not_available_in_dataset", f"matrix.{field_name}", f"Dataset {dataset.code} nao possui coluna para dimensao {dimension_code}.")

        for option in matrix.metric_options:
            option_metric = metric_by_code.get(option.metric_code)
            option_binding = binding_by_metric.get(option.metric_code)
            if option_metric is None or option_binding is None:
                continue
            option_dataset = dataset_by_code.get(option_binding.dataset_code)
            for dimension_code, field_name in ((matrix.row_dimension, "row_dimension"), (matrix.column_dimension, "column_dimension")):
                if dimension_code in option.skip_dimensions:
                    continue
                if option_metric.allowed_dimensions and dimension_code not in option_metric.allowed_dimensions:
                    _issue(issues, "matrix.option_dimension_not_allowed", f"matrix.{field_name}", f"Metrica {option_metric.code} nao permite recorte por {dimension_code}.")
                if option_dataset is not None:
                    columns = {column.code for column in option_dataset.columns}
                    column_code = option_dataset.dimension_columns.get(dimension_code, dimension_code)
                    if column_code not in columns:
                        _issue(issues, "matrix.option_dimension_not_available", f"matrix.{field_name}", f"Dataset {option_dataset.code} nao possui coluna para dimensao {dimension_code}.")

    for dimension in spec.capabilities.interactive_dimensions:
        if dimension not in dimension_by_code:
            _issue(issues, "capability.unknown_interactive_dimension", "capabilities.interactive_dimensions", f"Dimensao interativa inexistente: {dimension}.")


    supported_quality_types = {
        "dataset_non_empty",
        "dataset_required_fields",
        "metric_has_data",
        "metric_valid_range",
        "dimension_non_empty",
        "snapshot_field_present",
    }
    snapshot_fields = {
        "export_id",
        "generated_at",
        "generated_by",
        "authorization_scope",
        "system_version",
        "schema_version",
        "adapter_version",
        "initial_scope",
        "minimum_period",
        "maximum_period",
        "payload_hash",
        "contract_version",
    }
    quality_groups = (
        ("dataset_checks", spec.quality.dataset_checks, {"dataset_non_empty", "dataset_required_fields"}),
        ("metric_checks", spec.quality.metric_checks, {"metric_has_data", "metric_valid_range"}),
        ("coverage_checks", spec.quality.coverage_checks, {"dimension_non_empty"}),
        ("snapshot_checks", spec.quality.snapshot_checks, {"snapshot_field_present"}),
    )
    for group_name, checks, allowed_types in quality_groups:
        for check in checks:
            path = f"quality.{group_name}.{check.code}"
            if not check.code.strip():
                _issue(issues, "quality.empty_code", f"{path}.code", "Codigo de quality check nao pode ser vazio.")
            if not check.label.strip():
                _issue(issues, "quality.empty_label", f"{path}.label", "Label de quality check nao pode ser vazio.")
            if check.check_type not in supported_quality_types:
                _issue(issues, "quality.unsupported_check_type", f"{path}.check_type", f"Check type nao suportado: {check.check_type!r}.")
                continue
            if check.check_type not in allowed_types:
                _issue(issues, "quality.check_group_mismatch", f"{path}.check_type", f"Check {check.check_type!r} nao pertence a {group_name}.")
            if check.check_type in {"dataset_non_empty", "dataset_required_fields"}:
                if check.source_code not in dataset_by_code:
                    _issue(issues, "quality.unknown_dataset", f"{path}.source_code", f"Dataset inexistente: {check.source_code}.")
            elif check.check_type in {"metric_has_data", "metric_valid_range"}:
                metric = metric_by_code.get(check.source_code)
                if metric is None:
                    _issue(issues, "quality.unknown_metric", f"{path}.source_code", f"Metrica inexistente: {check.source_code}.")
                elif check.check_type == "metric_valid_range" and metric.valid_min is None and metric.valid_max is None:
                    _issue(issues, "quality.metric_range_required", f"{path}.source_code", "metric_valid_range exige valid_min e/ou valid_max no MetricSpec.")
                if check.source_code not in {item.metric_code for item in spec.metric_bindings}:
                    _issue(issues, "quality.metric_binding_required", f"{path}.source_code", "Quality check de metrica exige MetricBinding.")
            elif check.check_type == "dimension_non_empty":
                if check.source_code not in dimension_by_code:
                    _issue(issues, "quality.unknown_dimension", f"{path}.source_code", f"Dimensao inexistente: {check.source_code}.")
            elif check.check_type == "snapshot_field_present":
                if check.source_code not in snapshot_fields:
                    _issue(issues, "quality.unknown_snapshot_field", f"{path}.source_code", f"Campo de snapshot inexistente: {check.source_code}.")

    for limitation in spec.quality.limitations + spec.limitations:
        path = f"limitations.{limitation.code}"
        if limitation.affected_metric and limitation.affected_metric not in metric_codes:
            _issue(issues, "limitation.unknown_metric", f"{path}.affected_metric", f"Metrica inexistente: {limitation.affected_metric}.")
        if limitation.affected_dimension and limitation.affected_dimension not in dimension_by_code:
            _issue(issues, "limitation.unknown_dimension", f"{path}.affected_dimension", f"Dimensao inexistente: {limitation.affected_dimension}.")

    action_plan = spec.action_plan
    all_action_fields = set(action_plan.fields)
    if action_plan.enabled:
        if not action_plan.fields:
            _issue(issues, "action_plan.no_fields", "action_plan.fields", "Plano de acao habilitado precisa declarar ao menos um campo.")
        for duplicate in sorted(_duplicates(action_plan.fields)):
            _issue(issues, "action_plan.duplicate_field", "action_plan.fields", f"Campo duplicado: {duplicate}.")
        for index, field_code in enumerate(action_plan.fields):
            if not str(field_code).strip():
                _issue(issues, "action_plan.empty_field", f"action_plan.fields[{index}]", "Codigo de campo nao pode ser vazio.")
        if action_plan.local_blank_rows < 0:
            _issue(issues, "action_plan.invalid_local_blank_rows", "action_plan.local_blank_rows", "local_blank_rows deve ser >= 0.")
        if not action_plan.status_options:
            _issue(issues, "action_plan.empty_status_options", "action_plan.status_options", "Plano de acao precisa declarar ao menos um status.")
        for duplicate in sorted(_duplicates_casefold(action_plan.status_options)):
            _issue(issues, "action_plan.duplicate_status", "action_plan.status_options", f"Status duplicado apos normalizacao: {duplicate}.")
        unknown_completed = sorted(set(action_plan.completed_statuses) - set(action_plan.status_options))
        if unknown_completed:
            _issue(issues, "action_plan.unknown_completed_status", "action_plan.completed_statuses", f"Status de conclusao inexistentes: {', '.join(unknown_completed)}.")
        semantic_fields = {
            "indicator_field": action_plan.indicator_field,
            "deadline_field": action_plan.deadline_field,
            "status_field": action_plan.status_field,
            "days_remaining_field": action_plan.days_remaining_field,
        }
        for attr, field_code in semantic_fields.items():
            if field_code and field_code not in all_action_fields:
                _issue(issues, "action_plan.unknown_semantic_field", f"action_plan.{attr}", f"Campo semantico inexistente: {field_code}.")

    unknown_official = sorted(set(action_plan.official_fields) - all_action_fields)
    unknown_local = sorted(set(action_plan.local_editable_fields) - all_action_fields)
    if unknown_official:
        _issue(issues, "action_plan.unknown_official_field", "action_plan.official_fields", f"Campos inexistentes: {', '.join(unknown_official)}.")
    if unknown_local:
        _issue(issues, "action_plan.unknown_local_field", "action_plan.local_editable_fields", f"Campos inexistentes: {', '.join(unknown_local)}.")
    overlap = sorted(set(action_plan.official_fields) & set(action_plan.local_editable_fields))
    if overlap:
        _issue(issues, "action_plan.field_mode_conflict", "action_plan", f"Campos nao podem ser oficiais e locais ao mesmo tempo: {', '.join(overlap)}.")
    if action_plan.days_remaining_field in set(action_plan.local_editable_fields):
        _issue(issues, "action_plan.derived_field_editable", "action_plan.local_editable_fields", "days_remaining_field e derivado e nao pode ser editavel localmente.")

    for index, row in enumerate(action_plan.rows):
        path = f"action_plan.rows[{index}]"
        if not isinstance(row.source, ActionPlanRowSource):
            _issue(issues, "action_plan.invalid_row_source", f"{path}.source", f"Origem de linha invalida: {row.source!r}.")
        unknown_values = sorted(set(row.values) - all_action_fields)
        if unknown_values:
            _issue(issues, "action_plan.row_unknown_field", f"{path}.values", f"Campos inexistentes: {', '.join(unknown_values)}.")
        if action_plan.days_remaining_field and action_plan.days_remaining_field in row.values:
            _issue(issues, "action_plan.derived_field_value", f"{path}.values", "days_remaining_field e calculado e nao deve ser fornecido pela origem.")
        status_value = row.values.get(action_plan.status_field) if action_plan.status_field else None
        if status_value not in {None, ""} and status_value not in action_plan.status_options:
            _issue(issues, "action_plan.invalid_status_value", f"{path}.values", f"Status nao declarado em status_options: {status_value!r}.")

    if action_plan.enabled and not spec.capabilities.supports_action_plan:
        _issue(issues, "action_plan.capability_disabled", "capabilities.supports_action_plan", "ActionPlanSpec esta habilitado, mas o adapter declara supports_action_plan=False.")

    return tuple(issues)


def assert_valid_workbook_spec(spec: WorkbookSpec) -> None:
    issues = tuple(issue for issue in validate_workbook_spec(spec) if issue.severity in {"ERROR", "BLOCKING"})
    if issues:
        raise WorkbookSpecValidationError(issues)
