from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_excel_official_dashboard_v1 import _build, _spec  # noqa: E402

from excel_official import (  # noqa: E402
    CALC_SHEET,
    ChartRole,
    ChartSpec,
    ChartType,
    ChartWriteError,
    validate_workbook_spec,
    write_dashboard_charts,
)


def _with_charts(*charts: ChartSpec):
    spec = _spec()
    return replace(spec, dashboard=replace(spec.dashboard, charts=charts))


def _errors(spec) -> set[str]:
    return {item.code for item in validate_workbook_spec(spec) if item.severity == "ERROR"}


def test_01f_line_chart_uses_calc_helpers_and_fixed_nps_scale():
    chart = ChartSpec(
        code="nps_evolution",
        title="Evolucao do NPS",
        metric_code="academic.nps",
        dataset_code="academic_facts",
        dimension_code="period",
        chart_type=ChartType.LINE,
        role=ChartRole.EVOLUTION,
    )
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    chart_system = write_dashboard_charts(wb, spec, refs, params, dashboard)

    assert CALC_SHEET in wb.sheetnames
    assert wb[CALC_SHEET].sheet_state == "visible"
    assert wb[CALC_SHEET].protection.sheet is True
    assert len(wb["PAINEL"]._charts) == 1
    obj = wb["PAINEL"]._charts[0]
    assert obj.y_axis.scaling.min == -100
    assert obj.y_axis.scaling.max == 100
    assert obj.y_axis.majorUnit == 20
    assert chart_system.charts[0].category_count == 2
    assert chart_system.charts[0].series_count == 1

    formulas = [
        cell.value
        for row in wb[CALC_SHEET].iter_rows()
        for cell in row
        if cell.data_type == "f"
    ]
    assert formulas
    joined = "\n".join(formulas).upper()
    assert "P_COURSE" in joined
    assert "P_REFERENCE_PERIOD" not in joined


def test_01f_percent_score_and_count_axis_semantics_are_institutional():
    charts = (
        ChartSpec("approval", "Aprovacao", "academic.approval", "academic_facts", "course", ChartType.COLUMN, ChartRole.COMPARISON),
        ChartSpec("grades", "Media", "academic.average_grade", "academic_facts", "course", ChartType.BAR, ChartRole.COMPARISON),
        ChartSpec("students", "Alunos", "academic.active_students", "academic_facts", "course", ChartType.COLUMN, ChartRole.COMPARISON),
    )
    spec = _with_charts(*charts)
    wb, refs, params, dashboard = _build(spec)
    write_dashboard_charts(wb, spec, refs, params, dashboard)
    approval, grades, students = wb["PAINEL"]._charts
    assert approval.y_axis.scaling.min == 0
    assert approval.y_axis.scaling.max == 1
    assert approval.y_axis.numFmt.formatCode == "0%"
    assert grades.y_axis.scaling.min == 0
    assert grades.y_axis.scaling.max == 10
    assert students.y_axis.scaling.min == 0
    assert students.y_axis.scaling.max is None


def test_01f_comparison_chart_generates_reference_and_comparison_series():
    chart = ChartSpec(
        code="approval_compare",
        title="Aprovacao por curso",
        metric_code="academic.approval",
        dataset_code="academic_facts",
        dimension_code="course",
        chart_type=ChartType.COLUMN,
        role=ChartRole.COMPARISON,
        comparison="comparison_period",
    )
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    result = write_dashboard_charts(wb, spec, refs, params, dashboard)
    assert result.charts[0].series_count == 2
    formulas = [cell.value for row in wb[CALC_SHEET].iter_rows() for cell in row if cell.data_type == "f"]
    joined = "\n".join(formulas).upper()
    assert "P_REFERENCE_PERIOD" in joined
    assert "P_COMPARISON_PERIOD" in joined
    assert "P_COURSE" not in joined


def test_01f_series_dimension_creates_one_series_per_dimension_member():
    chart = ChartSpec(
        code="nps_by_course",
        title="NPS por periodo e curso",
        metric_code="academic.nps",
        dataset_code="academic_facts",
        dimension_code="period",
        series_dimension_code="course",
        chart_type=ChartType.LINE,
        role=ChartRole.EVOLUTION,
    )
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    result = write_dashboard_charts(wb, spec, refs, params, dashboard)
    assert result.charts[0].series_count == 2
    assert len(wb["PAINEL"]._charts[0].series) == 2
    formulas = [cell.value for row in wb[CALC_SHEET].iter_rows() for cell in row if cell.data_type == "f"]
    joined = "\n".join(formulas)
    assert '"Psicologia"' in joined
    assert '"Odontologia"' in joined


def test_01f_pie_and_doughnut_are_single_series_with_percentage_labels():
    for chart_type in (ChartType.PIE, ChartType.DOUGHNUT):
        chart = ChartSpec(
            code=f"students_{chart_type.value}",
            title="Composicao de alunos",
            metric_code="academic.active_students",
            dataset_code="academic_facts",
            dimension_code="course",
            chart_type=chart_type,
            role=ChartRole.COMPOSITION,
        )
        spec = _with_charts(chart)
        wb, refs, params, dashboard = _build(spec)
        write_dashboard_charts(wb, spec, refs, params, dashboard)
        obj = wb["PAINEL"]._charts[0]
        assert len(obj.series) == 1
        assert obj.dataLabels.showPercent is True
        assert len(obj.series[0].data_points) == 2


def test_01f_sort_and_top_n_affect_category_order_without_dynamic_arrays():
    chart = ChartSpec(
        code="course_top",
        title="Cursos",
        metric_code="academic.active_students",
        dataset_code="academic_facts",
        dimension_code="course",
        chart_type=ChartType.BAR,
        role=ChartRole.COMPARISON,
        sort="label_desc",
        top_n=1,
    )
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    result = write_dashboard_charts(wb, spec, refs, params, dashboard)
    assert result.charts[0].category_count == 1
    calc = wb[CALC_SHEET]
    values = [cell.value for row in calc.iter_rows() for cell in row if cell.value == "Psicologia"]
    assert values  # Psicologia sorts after Odontologia in descending label order.


def test_01f_preflight_failure_does_not_create_calc_or_chart_objects():
    chart = ChartSpec("nps", "NPS", "academic.nps", "academic_facts", "period", ChartType.LINE, ChartRole.EVOLUTION)
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    refs.pop("academic_facts")
    before = tuple(wb.sheetnames)
    with pytest.raises(ChartWriteError) as exc:
        write_dashboard_charts(wb, spec, refs, params, dashboard)
    assert exc.value.code == "chart.missing_dataset_ref"
    assert tuple(wb.sheetnames) == before
    assert CALC_SHEET not in wb.sheetnames
    assert wb["PAINEL"]._charts == []


def test_01f_contract_rejects_invalid_chart_combinations_and_sort():
    base = ChartSpec("c", "C", "academic.nps", "academic_facts", "period", ChartType.LINE, ChartRole.EVOLUTION)
    spec = _with_charts(replace(base, series_dimension_code="course", comparison="comparison_period"))
    assert "chart.series_and_comparison_not_supported" in _errors(spec)

    spec = _with_charts(replace(base, chart_type=ChartType.PIE, series_dimension_code="course"))
    assert "chart.circular_multi_series_not_supported" in _errors(spec)

    spec = _with_charts(replace(base, sort="metric_desc"))
    assert "chart.invalid_sort" in _errors(spec)


def test_01f_roundtrip_preserves_charts_calc_formulas_and_fixed_axis(tmp_path: Path):
    chart = ChartSpec("nps", "NPS", "academic.nps", "academic_facts", "period", ChartType.LINE, ChartRole.EVOLUTION)
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    write_dashboard_charts(wb, spec, refs, params, dashboard)
    path = tmp_path / "charts.xlsx"
    wb.save(path)
    reopened = load_workbook(path, data_only=False)
    assert len(reopened["PAINEL"]._charts) == 1
    assert reopened["PAINEL"]._charts[0].y_axis.scaling.min == -100
    assert reopened["PAINEL"]._charts[0].y_axis.scaling.max == 100
    assert reopened[CALC_SHEET].protection.sheet is True
    assert any(cell.data_type == "f" for row in reopened[CALC_SHEET].iter_rows() for cell in row)
    assert reopened.calculation.calcMode == "auto"
    assert reopened.calculation.fullCalcOnLoad is True
    assert reopened.calculation.forceFullCalc is True


def test_01f_calc_formulas_remain_excel_2019_compatible():
    chart = ChartSpec("nps", "NPS", "academic.nps", "academic_facts", "period", ChartType.LINE, ChartRole.EVOLUTION)
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    write_dashboard_charts(wb, spec, refs, params, dashboard)
    formulas = "\n".join(
        str(cell.value).upper()
        for row in wb[CALC_SHEET].iter_rows()
        for cell in row
        if cell.data_type == "f"
    )
    for unsupported in ("FILTER(", "XLOOKUP(", "SORT(", "UNIQUE(", "INDIRECT(", "OFFSET("):
        assert unsupported not in formulas


def test_01f_reuses_existing_calc_sheet_and_appends_without_overwriting():
    chart = ChartSpec("nps", "NPS", "academic.nps", "academic_facts", "period", ChartType.LINE, ChartRole.EVOLUTION)
    spec = _with_charts(chart)
    wb, refs, params, dashboard = _build(spec)
    calc = wb.create_sheet(CALC_SHEET)
    calc["A1"] = "EXISTING TECHNICAL CONTENT"
    calc["A4"] = "do-not-overwrite"
    result = write_dashboard_charts(wb, spec, refs, params, dashboard)
    assert wb[CALC_SHEET]["A4"].value == "do-not-overwrite"
    assert result.charts[0].calc_range.startswith("A6:")


def test_01f_no_chart_spec_does_not_create_calc_sheet():
    spec = _spec()
    wb, refs, params, dashboard = _build(spec)
    result = write_dashboard_charts(wb, spec, refs, params, dashboard)
    assert result.charts == ()
    assert CALC_SHEET not in wb.sheetnames
