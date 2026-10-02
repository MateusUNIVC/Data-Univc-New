from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from excel_official import (
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
    MatrixSpec,
    MetricBinding,
    ParameterSpec,
    SnapshotSpec,
    WorkbookSpec,
    WorkbookSpecValidationError,
    assert_valid_workbook_spec,
    validate_workbook_spec,
)
from excel_official.adapters import DirectorateAdapter
from excel_official.constants import REQUIRED_INSTITUTIONAL_SHEETS


def _valid_spec() -> WorkbookSpec:
    periods = DatasetSpec(
        code="periods",
        label="Periodos",
        sheet_name="DIM_PERIODO",
        table_name="TblDimPeriodo",
        technical=True,
        columns=(
            ColumnSpec("period", "Periodo", ColumnDataType.TEXT, semantic_type="period"),
            ColumnSpec("order", "Ordem", ColumnDataType.INTEGER, technical=True),
        ),
        grain=("period",),
        rows=(
            {"period": "2026-SEM1", "order": 1},
            {"period": "2026-SEM2", "order": 2},
        ),
    )
    courses = DatasetSpec(
        code="courses",
        label="Cursos",
        sheet_name="CURSOS",
        table_name="TblCursos",
        columns=(
            ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course"),
        ),
        grain=("course",),
        rows=({"course": "Psicologia"}, {"course": "Odontologia"}),
    )
    nps = DatasetSpec(
        code="academic_nps",
        label="NPS Discentes",
        sheet_name="NPS DISCENTES",
        table_name="TblNpsDiscentes",
        columns=(
            ColumnSpec("period", "Periodo", ColumnDataType.TEXT, semantic_type="period"),
            ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course"),
            ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER),
            ColumnSpec("promoters", "Promotores", ColumnDataType.INTEGER),
            ColumnSpec("neutrals", "Neutros", ColumnDataType.INTEGER),
            ColumnSpec("detractors", "Detratores", ColumnDataType.INTEGER),
        ),
        grain=("period", "course"),
        filter_dimensions=("period", "course"),
    )
    dimensions = (
        DimensionSpec("period", "Periodo", "periods", "period", "period", sort_order_column="order"),
        DimensionSpec("course", "Curso", "courses", "course", "course"),
    )
    return WorkbookSpec(
        identity=IdentitySpec(
            workbook_title="Painel DCS",
            directorate_code="DCS",
            directorate_label="Diretoria de Ciencias da Saude",
            adapter_code="academic",
            adapter_version=1,
        ),
        snapshot=SnapshotSpec(
            export_id="test-export",
            generated_at=datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc),
            generated_by="test-user",
            authorization_scope=("DCS",),
            system_version="0.13.0",
            schema_version=49,
            adapter_version=1,
            initial_scope={"course": "Psicologia"},
        ),
        initial_state=InitialStateSpec(values={"reference_period": "2026-SEM2", "course": "Psicologia"}),
        parameters=(
            ParameterSpec("reference_period", "Periodo de referencia", "period", "2026-SEM2", required=True),
            ParameterSpec("course", "Curso", "course", "Psicologia", empty_option="(todos)"),
        ),
        datasets=(periods, courses, nps),
        dimensions=dimensions,
        metric_codes=("academic.nps",),
        metric_bindings=(
            MetricBinding(
                metric_code="academic.nps",
                dataset_code="academic_nps",
                components={
                    "respondents": "respondents",
                    "promoters": "promoters",
                    "neutrals": "neutrals",
                    "detractors": "detractors",
                },
            ),
        ),
        domain_sheets=(DomainSheetSpec("nps_students", "NPS DISCENTES", "academic_nps"),),
        dashboard=DashboardSpec(
            title="DCS",
            kpis=(KpiSpec("academic.nps", source_dataset="academic_nps"),),
            charts=(
                ChartSpec(
                    code="nps_evolution",
                    title="Evolucao do NPS",
                    metric_code="academic.nps",
                    dataset_code="academic_nps",
                    dimension_code="period",
                    series_dimension_code="course",
                    chart_type=ChartType.LINE,
                    role=ChartRole.EVOLUTION,
                ),
            ),
        ),
        matrix=MatrixSpec("academic.nps", "course", "period"),
        capabilities=AdapterCapabilities(
            supports_comparison=True,
            supports_history_window=True,
            interactive_dimensions=("period", "course"),
        ),
    )


def _error_codes(spec: WorkbookSpec) -> set[str]:
    return {issue.code for issue in validate_workbook_spec(spec) if issue.severity == "ERROR"}


def test_contract_v1_accepts_a_declarative_academic_spec():
    spec = _valid_spec()
    assert validate_workbook_spec(spec) == ()
    assert_valid_workbook_spec(spec)


def test_contract_v1_has_the_six_institutional_sheets_frozen():
    assert REQUIRED_INSTITUTIONAL_SHEETS == (
        "LEIA-ME",
        "PARAMETROS",
        "PAINEL",
        "QUALIDADE E GOVERNANÇA",
        "MATRIZ",
        "PLANO_DE_ACAO",
    )


def test_contract_rejects_chart_that_references_unknown_metric():
    spec = _valid_spec()
    bad_chart = replace(spec.dashboard.charts[0], metric_code="academic.unknown")
    spec = replace(spec, dashboard=replace(spec.dashboard, charts=(bad_chart,)))
    assert "chart.unknown_metric" in _error_codes(spec)


def test_contract_rejects_matrix_with_unknown_dimension():
    spec = _valid_spec()
    spec = replace(spec, matrix=replace(spec.matrix, row_dimension="department"))
    assert "matrix.unknown_row_dimension" in _error_codes(spec)


def test_contract_rejects_metric_binding_to_missing_component_column():
    spec = _valid_spec()
    binding = replace(
        spec.metric_bindings[0],
        components={**spec.metric_bindings[0].components, "promoters": "missing_column"},
    )
    spec = replace(spec, metric_bindings=(binding,))
    assert "metric_binding.unknown_component_column" in _error_codes(spec)


def test_contract_rejects_dataset_using_institutional_sheet_name():
    spec = _valid_spec()
    dataset = replace(spec.datasets[2], sheet_name="PAINEL")
    spec = replace(spec, datasets=(spec.datasets[0], spec.datasets[1], dataset))
    assert "dataset.institutional_sheet_reserved" in _error_codes(spec)


def test_contract_requires_technical_flag_for_technical_sheet():
    spec = _valid_spec()
    period_dataset = replace(spec.datasets[0], technical=False)
    spec = replace(spec, datasets=(period_dataset, spec.datasets[1], spec.datasets[2]))
    assert "dataset.technical_sheet_requires_flag" in _error_codes(spec)


def test_contract_rejects_invalid_excel_table_name():
    spec = _valid_spec()
    dataset = replace(spec.datasets[2], table_name="NPS DISCENTES")
    spec = replace(spec, datasets=(spec.datasets[0], spec.datasets[1], dataset))
    assert "dataset.invalid_table_name" in _error_codes(spec)


def test_contract_rejects_unknown_parameter_dependency():
    spec = _valid_spec()
    parameter = replace(spec.parameters[1], depends_on=("directorate",))
    spec = replace(spec, parameters=(spec.parameters[0], parameter))
    assert "parameter.unknown_dependency" in _error_codes(spec)


def test_contract_rejects_required_parameter_without_initial_state():
    spec = _valid_spec()
    parameter = replace(spec.parameters[0], initial_value=None)
    spec = replace(
        spec,
        parameters=(parameter, spec.parameters[1]),
        initial_state=InitialStateSpec(values={"course": "Psicologia"}),
    )
    assert "parameter.required_without_initial_value" in _error_codes(spec)


def test_contract_rejects_duplicate_dataset_codes_and_table_names():
    spec = _valid_spec()
    duplicate = replace(spec.datasets[2], sheet_name="NPS CURSOS")
    spec = replace(spec, datasets=spec.datasets + (duplicate,))
    codes = _error_codes(spec)
    assert "dataset.duplicate_code" in codes
    assert "dataset.duplicate_table_name" in codes


def test_contract_rejects_rows_with_undeclared_columns():
    spec = _valid_spec()
    courses = replace(spec.datasets[1], rows=({"course": "Psicologia", "secret": 1},))
    spec = replace(spec, datasets=(spec.datasets[0], courses, spec.datasets[2]))
    assert "dataset.row_unknown_column" in _error_codes(spec)


def test_assert_valid_raises_with_all_structural_errors():
    spec = _valid_spec()
    bad_chart = replace(spec.dashboard.charts[0], metric_code="bad")
    bad_matrix = replace(spec.matrix, row_dimension="bad")
    spec = replace(spec, dashboard=replace(spec.dashboard, charts=(bad_chart,)), matrix=bad_matrix)
    with pytest.raises(WorkbookSpecValidationError) as exc:
        assert_valid_workbook_spec(spec)
    text = str(exc.value)
    assert "chart.unknown_metric" in text
    assert "matrix.unknown_row_dimension" in text


def test_adapter_boundary_is_declarative_and_does_not_import_openpyxl():
    root = Path(__file__).resolve().parents[1] / "excel_official"
    architecture_files = [
        root / "contract.py",
        root / "context.py",
        root / "validation.py",
        root / "constants.py",
        root / "exceptions.py",
        root / "theme.py",
        root / "adapters" / "base.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in architecture_files)
    assert "import openpyxl" not in source
    assert "from openpyxl" not in source
    assert issubclass(DirectorateAdapter, object)


def test_contract_rejects_case_insensitive_sheet_and_table_collisions():
    spec = _valid_spec()
    duplicate = replace(
        spec.datasets[2],
        code="academic_nps_2",
        sheet_name="nps discentes",
        table_name="tblnpsdiscentes",
    )
    spec = replace(spec, datasets=spec.datasets + (duplicate,))
    codes = _error_codes(spec)
    assert "dataset.duplicate_sheet_name" in codes
    assert "dataset.duplicate_table_name" in codes


def test_contract_rejects_duplicate_excel_headers_and_empty_dataset_columns():
    spec = _valid_spec()
    nps = spec.datasets[2]
    duplicated_label = replace(nps.columns[1], label=nps.columns[0].label.lower())
    nps = replace(nps, columns=(nps.columns[0], duplicated_label) + nps.columns[2:])
    spec = replace(spec, datasets=(spec.datasets[0], spec.datasets[1], nps))
    assert "column.duplicate_label" in _error_codes(spec)

    empty = replace(spec.datasets[1], columns=())
    spec2 = replace(_valid_spec(), datasets=(_valid_spec().datasets[0], empty, _valid_spec().datasets[2]))
    assert "dataset.no_columns" in _error_codes(spec2)


def test_contract_rejects_table_names_that_look_like_cell_references():
    spec = _valid_spec()
    dataset = replace(spec.datasets[2], table_name="A1")
    spec = replace(spec, datasets=(spec.datasets[0], spec.datasets[1], dataset))
    assert "dataset.invalid_table_name" in _error_codes(spec)
