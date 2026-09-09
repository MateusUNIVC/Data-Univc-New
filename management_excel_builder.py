from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import SeriesLabel
from openpyxl.chart.marker import DataPoint
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from excel_errors import ExcelExportLimitError
from management_catalog import (
    directorate_spec,
    indicator_spec,
    indicator_specs,
    metric_spec,
    period_sort_key,
    validate_period,
)
from management_service import row_dimensions, raw_components, status_for_metric

EXCEL_MAX_ROWS = 1_048_576
HEADER_ROW = 6
DATA_START_ROW = 7

GREEN = "00583F"
GREEN_2 = "0B6B4F"
LIME = "9DBC3B"
LIGHT_GREEN = "E7F1EC"
PALE_GREEN = "F4F8F6"
GOLD = "C6A15B"
DARK = "1F2933"
GRAY = "64727D"
LIGHT_GRAY = "E8ECEF"
VERY_LIGHT = "F7F9FA"
WHITE = "FFFFFF"
RED = "C0392B"
LIGHT_RED = "FCE8E6"
ORANGE = "D97706"
LIGHT_ORANGE = "FFF3D6"
BLUE = "2F6F9F"
PURPLE = "6B4E8A"

THIN_GRAY = Side(style="thin", color="D7DEE2")
MEDIUM_GREEN = Side(style="medium", color=GREEN)

STATUS_FILL = {
    "Dentro da meta": PatternFill("solid", fgColor="DFF0E6"),
    "Atenção": PatternFill("solid", fgColor=LIGHT_ORANGE),
    "Fora da meta": PatternFill("solid", fgColor=LIGHT_RED),
    "Não apurado": PatternFill("solid", fgColor=LIGHT_GRAY),
    "Sem meta": PatternFill("solid", fgColor=LIGHT_GRAY),
    "Informativo": PatternFill("solid", fgColor="E8F0FA"),
}


def _title(ws, text: str, subtitle: str | None = None, *, end_col: int = 18) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_col)
    cell = ws.cell(1, 1, text)
    cell.font = Font(name="Aptos Display", size=20, bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=GREEN)
    cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 32
    if subtitle:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end_col)
        cell = ws.cell(2, 1, subtitle)
        cell.font = Font(name="Aptos", size=10, color=GRAY, italic=True)
        cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 22


def _section(ws, row: int, text: str, *, start_col: int = 1, end_col: int = 18) -> None:
    ws.merge_cells(start_row=row, start_column=start_col, end_row=row, end_column=end_col)
    cell = ws.cell(row, start_col, text)
    cell.font = Font(name="Aptos", size=11, bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=GREEN_2)
    cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row].height = 24


def _header_row(ws, row: int, start_col: int, headers: list[str]) -> None:
    for offset, value in enumerate(headers):
        cell = ws.cell(row, start_col + offset, value)
        cell.font = Font(name="Aptos", size=9, bold=True, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=GREEN)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=MEDIUM_GREEN)
    ws.row_dimensions[row].height = 30


def _style_body(ws, start_row: int, end_row: int, start_col: int, end_col: int) -> None:
    for row in ws.iter_rows(min_row=start_row, max_row=end_row, min_col=start_col, max_col=end_col):
        for cell in row:
            cell.font = Font(name="Aptos", size=9, color=DARK)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = Border(bottom=THIN_GRAY)


def _set_widths(ws, widths: dict[int, float]) -> None:
    for column, width in widths.items():
        ws.column_dimensions[get_column_letter(column)].width = width


def _sheet_defaults(ws, *, zoom: int = 85, freeze: str | None = None, show_gridlines: bool = False) -> None:
    ws.sheet_view.showGridLines = show_gridlines
    ws.sheet_view.zoomScale = zoom
    if freeze:
        ws.freeze_panes = freeze
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.4
    ws.page_margins.bottom = 0.4
    ws.page_margins.header = 0.15
    ws.page_margins.footer = 0.15


def _unique_catalog_fields(specs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    fields: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    dimensions: list[str] = []
    seen_dimensions: set[str] = set()
    metrics: list[dict[str, Any]] = []
    seen_metrics: set[str] = set()
    for spec in specs:
        for dimension in spec.get("dimensions") or []:
            if dimension not in seen_dimensions:
                seen_dimensions.add(dimension)
                dimensions.append(dimension)
        for field in spec.get("fields") or []:
            if field["key"] not in seen_fields:
                seen_fields.add(field["key"])
                fields.append(field)
        for metric in spec.get("metrics") or []:
            compound = f"{spec['code']}::{metric['key']}"
            if compound not in seen_metrics:
                seen_metrics.add(compound)
                metrics.append({**metric, "indicator_code": spec["code"], "column_key": compound})
    return fields, dimensions, metrics


def _cell_ref(column: int, row: int, absolute: bool = False) -> str:
    letter = get_column_letter(column)
    return f"${letter}${row}" if absolute else f"{letter}{row}"


def _row_metric_formula(
    spec: dict[str, Any],
    metric: dict[str, Any],
    row: int,
    field_cols: dict[str, int],
) -> str:
    def ref(key: str) -> str:
        col = field_cols.get(key)
        return _cell_ref(col, row) if col else "0"

    aggregation = metric.get("aggregation")
    if aggregation == "ratio":
        return f'=IFERROR({ref(metric["numerator"])}/{ref(metric["denominator"])}*{float(metric.get("scale", 1)):g},"")'
    if aggregation in {"sum", "weighted_average"}:
        return f'={ref(metric["field"])}'
    if aggregation == "derived_total_cost":
        return "=" + "+".join(ref(key) for key in ("faculty_cost", "coordination_cost", "other_direct_cost", "indirect_cost"))
    if aggregation == "derived_margin":
        cost = "+".join(ref(key) for key in ("faculty_cost", "coordination_cost", "other_direct_cost", "indirect_cost"))
        return f'=IFERROR(({ref("net_revenue")}-({cost}))/{ref("net_revenue")}*100,"")'
    if aggregation == "derived_total_expense":
        return "=" + "+".join(ref(key) for key in ("personnel_expense", "operational_expense", "administrative_expense", "financial_expense"))
    if aggregation == "derived_coverage":
        expense = "+".join(ref(key) for key in ("personnel_expense", "operational_expense", "administrative_expense", "financial_expense"))
        return f'=IFERROR({ref("net_revenue")}/({expense}),"")'
    if aggregation == "derived_operating_margin":
        expense = "+".join(ref(key) for key in ("personnel_expense", "operational_expense", "administrative_expense", "financial_expense"))
        coverage = f"({ref('net_revenue')}/({expense}))"
        return f'=IFERROR((1-1/{coverage})*100,"")'
    if aggregation == "derived_payroll_ratio":
        return f'=IFERROR(({ref("faculty_payroll")}+{ref("administrative_payroll")})/{ref("net_revenue")}*100,"")'
    if aggregation == "derived_active_end":
        return f'={ref("active_start")}+{ref("entrants")}-{ref("graduates")}-{ref("dropped")}'
    if aggregation == "derived_net_change":
        end_expr = f"({ref('active_start')}+{ref('entrants')}-{ref('graduates')}-{ref('dropped')})"
        return f'=IFERROR(({end_expr}-{ref("active_start")})/{ref("active_start")}*100,"")'
    return '=""'


def _calc_metric_formula(
    spec: dict[str, Any],
    metric: dict[str, Any],
    row: int,
    component_cols: dict[str, int],
    previous_rows: list[int],
) -> str:
    def ref(key: str, target_row: int | None = None) -> str:
        col = component_cols.get(key)
        return _cell_ref(col, target_row or row) if col else "0"

    aggregation = metric.get("aggregation")
    if aggregation == "ratio":
        return f'=IFERROR({ref(metric["numerator"])}/{ref(metric["denominator"])}*{float(metric.get("scale", 1)):g},"")'
    if aggregation in {"sum", "weighted_average"}:
        return f'={ref(metric["field"])}'
    if aggregation == "derived_total_cost":
        return "=" + "+".join(ref(key) for key in ("faculty_cost", "coordination_cost", "other_direct_cost", "indirect_cost"))
    if aggregation == "derived_margin":
        total_cost = "+".join(ref(key) for key in ("faculty_cost", "coordination_cost", "other_direct_cost", "indirect_cost"))
        return f'=IFERROR(({ref("net_revenue")}-({total_cost}))/{ref("net_revenue")}*100,"")'
    if aggregation == "derived_total_expense":
        return "=" + "+".join(ref(key) for key in ("personnel_expense", "operational_expense", "administrative_expense", "financial_expense"))
    if aggregation == "derived_coverage":
        expense = "+".join(ref(key) for key in ("personnel_expense", "operational_expense", "administrative_expense", "financial_expense"))
        return f'=IFERROR({ref("net_revenue")}/({expense}),"")'
    if aggregation == "derived_operating_margin":
        expense = "+".join(ref(key) for key in ("personnel_expense", "operational_expense", "administrative_expense", "financial_expense"))
        return f'=IFERROR((1-({expense})/{ref("net_revenue")})*100,"")'
    if aggregation == "derived_payroll_ratio":
        return f'=IFERROR(({ref("faculty_payroll")}+{ref("administrative_payroll")})/{ref("net_revenue")}*100,"")'
    if aggregation == "derived_active_end":
        return f'={ref("active_start")}+{ref("entrants")}-{ref("graduates")}-{ref("dropped")}'
    if aggregation == "derived_net_change":
        active_end = f"({ref('active_start')}+{ref('entrants')}-{ref('graduates')}-{ref('dropped')})"
        return f'=IFERROR(({active_end}-{ref("active_start")})/{ref("active_start")}*100,"")'
    if aggregation == "rolling_payroll_ratio_3m":
        window = (previous_rows + [row])[-3:]
        revenues = ",".join(ref("net_revenue", target_row) for target_row in window)
        payroll = f"({ref('faculty_payroll')}+{ref('administrative_payroll')})"
        return f'=IFERROR({payroll}/AVERAGE({revenues})*100,"")'
    if aggregation == "month_over_month_payroll_change":
        if not previous_rows:
            return '=""'
        previous = previous_rows[-1]
        current_payroll = f"({ref('faculty_payroll')}+{ref('administrative_payroll')})"
        previous_payroll = f"({ref('faculty_payroll', previous)}+{ref('administrative_payroll', previous)})"
        return f'=IFERROR(({current_payroll}-{previous_payroll})/{previous_payroll}*100,"")'
    return '=""'


def _status_formula(value_ref: str, metric: dict[str, Any], target_refs: dict[str, str]) -> str:
    direction = metric.get("direction")
    if direction in {None, "context"}:
        return f'=IF({value_ref}="","Não apurado","Informativo")'
    if direction == "higher":
        target = target_refs["target"]
        attention = target_refs["attention"]
        return f'=IF({value_ref}="","Não apurado",IF({target}="","Sem meta",IF({value_ref}>={target},"Dentro da meta",IF(AND({attention}<>"",{value_ref}>={attention}),"Atenção","Fora da meta"))))'
    if direction == "lower":
        target = target_refs["target"]
        attention = target_refs["attention"]
        return f'=IF({value_ref}="","Não apurado",IF({target}="","Sem meta",IF({value_ref}<={target},"Dentro da meta",IF(AND({attention}<>"",{value_ref}<={attention}),"Atenção","Fora da meta"))))'
    if direction == "range":
        tmin, tmax = target_refs["target_min"], target_refs["target_max"]
        amin, amax = target_refs["attention_min"], target_refs["attention_max"]
        return f'=IF({value_ref}="","Não apurado",IF(OR({tmin}="",{tmax}=""),"Sem meta",IF(AND({value_ref}>={tmin},{value_ref}<={tmax}),"Dentro da meta",IF(AND({amin}<>"",{amax}<>"",{value_ref}>={amin},{value_ref}<={amax}),"Atenção","Fora da meta"))))'
    return '="Sem meta"'


def _metric_number_format(metric: dict[str, Any]) -> str:
    unit = metric.get("unit")
    if unit == "%":
        return '0.0"%"'
    if unit == "R$":
        return 'R$ #,##0.00;[Red](R$ #,##0.00);-'
    if unit in {"x", "índice"}:
        return '0.00"x"'
    if unit in {"meses", "h úteis", "h/semana", "alunos/h", "orientandos/docente"}:
        return '0.0'
    return '#,##0.0'


def _write_readme(wb: Workbook, directorate_code: str, specs: list[dict[str, Any]]) -> None:
    ws = wb["LEIA-ME"]
    directory = directorate_spec(directorate_code)
    _title(ws, f"Data UNIVC — {directorate_code}", f"Painel gerencial · {directory['name']}", end_col=10)
    _section(ws, 4, "COMO UTILIZAR", end_col=10)
    instructions = [
        "1. O banco de dados é a fonte oficial. Esta planilha é uma exportação executiva e auditável.",
        "2. DADM e DPE são alimentados mensalmente; DM é alimentado exclusivamente por semestre nesta versão.",
        "3. Use PARAMETROS para conferir o período de referência e de comparação da exportação.",
        "4. Os indicadores são calculados a partir dos componentes visíveis em LANÇAMENTOS; nenhum registro é truncado silenciosamente.",
        "5. A janela dos gráficos limita apenas a apresentação. O histórico completo permanece em LANÇAMENTOS, MATRIZ e CALC.",
        "6. Linhas sem base suficiente aparecem como não apuradas. Metas podem ser versionadas por vigência e dimensão.",
        "7. Todo indicador fora da meta deve possuir plano de ação com responsável e prazo.",
    ]
    for index, text in enumerate(instructions, start=6):
        ws.merge_cells(start_row=index, start_column=1, end_row=index, end_column=10)
        ws.cell(index, 1, text)
        ws.cell(index, 1).font = Font(name="Aptos", size=10, color=DARK)
        ws.cell(index, 1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[index].height = 30
    row = 15
    _section(ws, row, "INDICADORES ATIVOS", end_col=10)
    row += 1
    _header_row(ws, row, 1, ["Código", "Indicador", "Periodicidade", "Métrica principal", "Fonte"])
    for spec in specs:
        row += 1
        ws.cell(row, 1, spec["code"])
        ws.cell(row, 2, spec["name"])
        ws.cell(row, 3, "Mensal" if spec["periodicity"] == "monthly" else "Semestral")
        primary = next(metric for metric in spec["metrics"] if metric["key"] == spec["primary_metric"])
        ws.cell(row, 4, f"{primary['label']} ({primary['unit']})")
        ws.cell(row, 5, spec["source"])
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=10)
        ws.row_dimensions[row].height = 42
    _style_body(ws, 17, row, 1, 10)
    _set_widths(ws, {1: 13, 2: 38, 3: 16, 4: 28, 5: 18, 6: 14, 7: 14, 8: 14, 9: 14, 10: 14})
    _sheet_defaults(ws, zoom=90, freeze="A5")


def _write_parameters(
    wb: Workbook,
    directorate_code: str,
    reference: str | None,
    comparison: str | None,
    periods: list[str],
) -> None:
    ws = wb["PARAMETROS"]
    directory = directorate_spec(directorate_code)
    _title(ws, "Parâmetros da exportação", f"{directorate_code} · controles do painel", end_col=8)
    _section(ws, 4, "RECORTE", end_col=8)
    values = [
        ("Diretoria", directorate_code),
        ("Nome", directory["name"]),
        ("Periodicidade", "Mensal" if directory["periodicity"] == "monthly" else "Semestral"),
        ("Referência", reference or ""),
        ("Comparação", comparison or ""),
        ("Janela executiva", "12 meses" if directory["periodicity"] == "monthly" else "8 semestres"),
        ("Primeiro período disponível", periods[0] if periods else ""),
        ("Último período disponível", periods[-1] if periods else ""),
        ("Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M")),
    ]
    for idx, (label, value) in enumerate(values, start=6):
        ws.cell(idx, 1, label)
        ws.cell(idx, 1).font = Font(name="Aptos", size=10, bold=True, color=GREEN)
        ws.cell(idx, 2, value)
        ws.merge_cells(start_row=idx, start_column=2, end_row=idx, end_column=5)
        ws.cell(idx, 2).fill = PatternFill("solid", fgColor=PALE_GREEN)
        ws.cell(idx, 2).font = Font(name="Aptos", size=10, color=DARK)
        ws.cell(idx, 2).alignment = Alignment(vertical="center")
        ws.row_dimensions[idx].height = 24
    ws["B9"].fill = PatternFill("solid", fgColor="FFF6D5")
    ws["B10"].fill = PatternFill("solid", fgColor="FFF6D5")
    _set_widths(ws, {1: 28, 2: 23, 3: 14, 4: 14, 5: 18, 6: 14, 7: 14, 8: 14})
    _sheet_defaults(ws, zoom=95)


def _build_launch_sheet(
    wb: Workbook,
    directorate_code: str,
    specs: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    dimensions: list[str],
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    ws = wb["LANÇAMENTOS"]
    _title(ws, f"Base de lançamentos — {directorate_code}", "Componentes originais e cálculo auditável por linha", end_col=8 + len(dimensions) + len(fields) + len(metrics))
    headers = ["ID", "Indicador", "Período", "Dimensão", "Chave", "Validado", "Fonte", "Observações"]
    headers += [f"Dimensão · {key}" for key in dimensions]
    headers += [field["label"] for field in fields]
    headers += [f"{metric['indicator_code']} · {metric['label']}" for metric in metrics]
    _header_row(ws, HEADER_ROW, 1, headers)
    base_cols = {name: index + 1 for index, name in enumerate(headers)}
    dimension_cols = {key: 9 + index for index, key in enumerate(dimensions)}
    field_start = 9 + len(dimensions)
    field_cols = {field["key"]: field_start + index for index, field in enumerate(fields)}
    metric_start = field_start + len(fields)
    metric_cols = {metric["column_key"]: metric_start + index for index, metric in enumerate(metrics)}

    sorted_measurements = sorted(
        measurements,
        key=lambda row: (
            str(row.get("indicator_code")),
            period_sort_key(row.get("period")),
            str(row.get("dimension_label", "TOTAL")),
        ),
    )
    if DATA_START_ROW + len(sorted_measurements) - 1 > EXCEL_MAX_ROWS:
        raise ExcelExportLimitError(
            "A base de lançamentos ultrapassa o limite físico de linhas do Excel. "
            "A exportação foi interrompida sem truncar dados."
        )
    measurement_excel_rows: list[tuple[dict[str, Any], int]] = []
    spec_by_code = {spec["code"]: spec for spec in specs}
    for offset, item in enumerate(sorted_measurements):
        row = DATA_START_ROW + offset
        measurement_excel_rows.append((item, row))
        values = raw_components(item)
        dims = row_dimensions(item)
        ws.cell(row, 1, item.get("id"))
        ws.cell(row, 2, item.get("indicator_code"))
        ws.cell(row, 3, item.get("period"))
        ws.cell(row, 4, item.get("dimension_label") or "TOTAL")
        ws.cell(row, 5, item.get("dimension_key") or "TOTAL")
        ws.cell(row, 6, "Sim" if item.get("validated") else "Não")
        ws.cell(row, 7, item.get("source_reference"))
        ws.cell(row, 8, item.get("notes"))
        for key, col in dimension_cols.items():
            ws.cell(row, col, dims.get(key))
        for field in fields:
            cell = ws.cell(row, field_cols[field["key"]], values.get(field["key"]))
            if field.get("type") == "currency":
                cell.number_format = 'R$ #,##0.00;[Red](R$ #,##0.00);-'
            elif field.get("type") == "integer":
                cell.number_format = '#,##0'
            else:
                cell.number_format = '0.00'
        spec = spec_by_code.get(item.get("indicator_code"))
        if spec:
            for metric in spec.get("metrics") or []:
                compound = f"{spec['code']}::{metric['key']}"
                col = metric_cols[compound]
                ws.cell(row, col, _row_metric_formula(spec, metric, row, field_cols))
                ws.cell(row, col).number_format = _metric_number_format(metric)

    end_row = max(DATA_START_ROW, DATA_START_ROW + len(sorted_measurements) - 1)
    _style_body(ws, DATA_START_ROW, end_row, 1, len(headers))
    for row in range(DATA_START_ROW, end_row + 1):
        ws.cell(row, 6).alignment = Alignment(horizontal="center", vertical="center")
        if ws.cell(row, 6).value == "Sim":
            ws.cell(row, 6).fill = PatternFill("solid", fgColor="DFF0E6")
        else:
            ws.cell(row, 6).fill = PatternFill("solid", fgColor=LIGHT_ORANGE)
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(headers))}{end_row}"
    widths = {1: 9, 2: 13, 3: 14, 4: 34, 5: 16, 6: 12, 7: 24, 8: 32}
    for col in dimension_cols.values():
        widths[col] = 22
    for field in fields:
        widths[field_cols[field["key"]]] = min(26, max(14, len(field["label"]) * 0.9))
    for metric in metrics:
        widths[metric_cols[metric["column_key"]]] = 18
    _set_widths(ws, widths)
    _sheet_defaults(ws, zoom=72, freeze=f"A{DATA_START_ROW}")
    ws.sheet_properties.tabColor = GREEN
    return {
        "field_cols": field_cols,
        "metric_cols": metric_cols,
        "dimension_cols": dimension_cols,
        "start_row": DATA_START_ROW,
        "end_row": end_row,
        "measurement_rows": measurement_excel_rows,
        "header_count": len(headers),
    }


def _default_target(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": metric.get("target"),
        "attention": metric.get("attention"),
        "target_min": metric.get("target_min"),
        "target_max": metric.get("target_max"),
        "attention_min": metric.get("attention_min"),
        "attention_max": metric.get("attention_max"),
    }


def _resolve_target(
    metric: dict[str, Any],
    targets: list[dict[str, Any]],
    period: str,
    indicator_code: str,
    dimension_key: str = "TOTAL",
) -> dict[str, Any]:
    eligible = []
    period_key = period_sort_key(period)
    for item in targets:
        if item.get("indicator_code") != indicator_code or item.get("metric_key") != metric.get("key"):
            continue
        item_dimension = item.get("dimension_key") or "TOTAL"
        if item_dimension not in {dimension_key, "TOTAL"}:
            continue
        start = period_sort_key(item.get("valid_from"))
        end = period_sort_key(item.get("valid_to")) if item.get("valid_to") else 10**12
        if start <= period_key <= end:
            eligible.append((1 if item_dimension == dimension_key else 0, start, item))
    if eligible:
        return dict(max(eligible, key=lambda value: (value[0], value[1]))[2])
    return _default_target(metric)


def _build_calc_sheet(
    wb: Workbook,
    directorate_code: str,
    specs: list[dict[str, Any]],
    periods: list[str],
    fields: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    launch_info: dict[str, Any],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    ws = wb["CALC"]
    _title(ws, f"Cálculos — {directorate_code}", "Faixas auxiliares para painel, matriz e gráficos", end_col=20)
    headers = ["Indicador", "Período", "Chave", "Registros", "Validados"]
    headers += [field["label"] for field in fields]
    headers += [f"{metric['indicator_code']} · {metric['label']}" for metric in metrics]
    headers += ["Meta", "Atenção", "Meta mínima", "Meta máxima", "Atenção mínima", "Atenção máxima", "Status"]
    _header_row(ws, HEADER_ROW, 1, headers)
    component_start = 6
    component_cols = {field["key"]: component_start + index for index, field in enumerate(fields)}
    metric_start = component_start + len(fields)
    metric_cols = {metric["column_key"]: metric_start + index for index, metric in enumerate(metrics)}
    target_start = metric_start + len(metrics)
    target_cols = {
        "target": target_start,
        "attention": target_start + 1,
        "target_min": target_start + 2,
        "target_max": target_start + 3,
        "attention_min": target_start + 4,
        "attention_max": target_start + 5,
        "status": target_start + 6,
    }

    launch_start = launch_info["start_row"]
    launch_end = launch_info["end_row"]
    indicator_range = f"'LANÇAMENTOS'!$B${launch_start}:$B${launch_end}"
    period_range = f"'LANÇAMENTOS'!$C${launch_start}:$C${launch_end}"
    validated_range = f"'LANÇAMENTOS'!$F${launch_start}:$F${launch_end}"
    calc_rows: dict[tuple[str, str], int] = {}
    indicator_rows: dict[str, list[int]] = defaultdict(list)
    row = DATA_START_ROW
    spec_by_code = {spec["code"]: spec for spec in specs}
    for spec in specs:
        previous_rows: list[int] = []
        for period in periods:
            calc_rows[(spec["code"], period)] = row
            indicator_rows[spec["code"]].append(row)
            ws.cell(row, 1, spec["code"])
            ws.cell(row, 2, period)
            ws.cell(row, 3, f'={_cell_ref(1,row)}&"|"&{_cell_ref(2,row)}')
            ws.cell(row, 4, f'=COUNTIFS({indicator_range},$A{row},{period_range},$B{row})')
            ws.cell(row, 5, f'=COUNTIFS({indicator_range},$A{row},{period_range},$B{row},{validated_range},"Sim")')
            for field in fields:
                key = field["key"]
                col = component_cols[key]
                launch_col = launch_info["field_cols"][key]
                value_range = f"'LANÇAMENTOS'!${get_column_letter(launch_col)}${launch_start}:${get_column_letter(launch_col)}${launch_end}"
                weighted_metric = next(
                    (
                        metric for metric in spec.get("metrics") or []
                        if metric.get("aggregation") == "weighted_average" and metric.get("field") == key
                    ),
                    None,
                )
                if weighted_metric:
                    weight_col = launch_info["field_cols"].get(weighted_metric.get("weight"))
                    weight_range = f"'LANÇAMENTOS'!${get_column_letter(weight_col)}${launch_start}:${get_column_letter(weight_col)}${launch_end}"
                    formula = (
                        f'=IF($D{row}=0,"",IFERROR('
                        f'SUMPRODUCT(({indicator_range}=$A{row})*({period_range}=$B{row})*{value_range}*{weight_range})/'
                        f'SUMIFS({weight_range},{indicator_range},$A{row},{period_range},$B{row}),""))'
                    )
                else:
                    formula = f'=IF($D{row}=0,"",SUMIFS({value_range},{indicator_range},$A{row},{period_range},$B{row}))'
                ws.cell(row, col, formula)
                if field.get("type") == "currency":
                    ws.cell(row, col).number_format = 'R$ #,##0.00;[Red](R$ #,##0.00);-'
                elif field.get("type") == "integer":
                    ws.cell(row, col).number_format = '#,##0'
                else:
                    ws.cell(row, col).number_format = '0.00'
            for metric in spec.get("metrics") or []:
                compound = f"{spec['code']}::{metric['key']}"
                col = metric_cols[compound]
                ws.cell(row, col, _calc_metric_formula(spec, metric, row, component_cols, previous_rows))
                ws.cell(row, col).number_format = _metric_number_format(metric)
            primary = metric_spec(directorate_code, spec["code"], spec["primary_metric"])
            resolved = _resolve_target(primary, targets, period, spec["code"])
            for key in ("target", "attention", "target_min", "target_max", "attention_min", "attention_max"):
                ws.cell(row, target_cols[key], resolved.get(key))
                ws.cell(row, target_cols[key]).number_format = _metric_number_format(primary)
            primary_col = metric_cols[f"{spec['code']}::{spec['primary_metric']}"]
            refs = {key: _cell_ref(col, row) for key, col in target_cols.items() if key != "status"}
            ws.cell(row, target_cols["status"], _status_formula(_cell_ref(primary_col, row), primary, refs))
            previous_rows.append(row)
            row += 1

    end_row = max(DATA_START_ROW, row - 1)
    _style_body(ws, DATA_START_ROW, end_row, 1, len(headers))
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(headers))}{end_row}"
    _set_widths(ws, {1: 14, 2: 14, 3: 26, 4: 12, 5: 12})
    for col in range(6, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16
    _sheet_defaults(ws, zoom=65, freeze=f"A{DATA_START_ROW}")
    ws.sheet_state = "hidden"
    return {
        "component_cols": component_cols,
        "metric_cols": metric_cols,
        "target_cols": target_cols,
        "calc_rows": calc_rows,
        "indicator_rows": indicator_rows,
        "start_row": DATA_START_ROW,
        "end_row": end_row,
        "key_range": f"$C${DATA_START_ROW}:$C${end_row}",
    }


def _lookup_formula(calc_info: dict[str, Any], value_col: int, indicator_code: str, parameter_cell: str) -> str:
    """Resolve a única linha indicador/período sem depender de lookup textual frágil.

    COUNTIFS evita que SUMIFS devolva zero quando o período não existe. A fórmula
    é compatível com Excel e com o recálculo de validação usado na entrega.
    """
    start = calc_info["start_row"]
    end = calc_info["end_row"]
    value_range = f'CALC!${get_column_letter(value_col)}${start}:${get_column_letter(value_col)}${end}'
    indicator_range = f'CALC!$A${start}:$A${end}'
    period_range = f'CALC!$B${start}:$B${end}'
    return (
        f'=IF(COUNTIFS({indicator_range},"{indicator_code}",{period_range},{parameter_cell})=0,"",'
        f'SUMIFS({value_range},{indicator_range},"{indicator_code}",{period_range},{parameter_cell}))'
    )




def _target_lookup_formula(calc_info: dict[str, Any], value_col: int, indicator_code: str, parameter_cell: str) -> str:
    """Busca limiar/meta e preserva vazio quando a meta não foi definida."""
    start = calc_info["start_row"]
    end = calc_info["end_row"]
    value_range = f'CALC!${get_column_letter(value_col)}${start}:${get_column_letter(value_col)}${end}'
    indicator_range = f'CALC!$A${start}:$A${end}'
    period_range = f'CALC!$B${start}:$B${end}'
    return (
        f'=IF(COUNTIFS({indicator_range},"{indicator_code}",{period_range},{parameter_cell},'
        f'{value_range},"<>")=0,"",SUMIFS({value_range},{indicator_range},"{indicator_code}",'
        f'{period_range},{parameter_cell}))'
    )

def _add_status_conditional_formatting(ws, cell_range: str) -> None:
    ws.conditional_formatting.add(
        cell_range,
        FormulaRule(formula=[f'{cell_range.split(":")[0]}="Dentro da meta"'], fill=STATUS_FILL["Dentro da meta"]),
    )
    ws.conditional_formatting.add(
        cell_range,
        FormulaRule(formula=[f'{cell_range.split(":")[0]}="Atenção"'], fill=STATUS_FILL["Atenção"]),
    )
    ws.conditional_formatting.add(
        cell_range,
        FormulaRule(formula=[f'{cell_range.split(":")[0]}="Fora da meta"'], fill=STATUS_FILL["Fora da meta"]),
    )


def _chart_for_indicator(
    ws,
    spec: dict[str, Any],
    calc_info: dict[str, Any],
    chart_start_row: int,
    chart_end_row: int,
    anchor: str,
    *,
    chart_width: float = 15.5,
    chart_height: float = 7.0,
) -> LineChart:
    rows = calc_info["indicator_rows"][spec["code"]]
    if not rows:
        return LineChart()
    start = rows[chart_start_row]
    end = rows[chart_end_row]
    chart = LineChart()
    chart.title = f"{spec['short_name']} — evolução e meta"
    chart.style = 13
    chart.height = chart_height
    chart.width = chart_width
    chart.legend.position = "b"
    chart.y_axis.title = metric_spec(spec["code"].split("-")[0], spec["code"], spec["primary_metric"])["label"]
    chart.x_axis.title = "Período"
    chart.x_axis.tickLblPos = "low"
    chart.display_blanks = "gap"
    chart.visible_cells_only = False
    primary = next(metric for metric in spec["metrics"] if metric["key"] == spec["primary_metric"])
    primary_col = calc_info["metric_cols"][f"{spec['code']}::{spec['primary_metric']}"]
    data = Reference(ws.parent["CALC"], min_col=primary_col, min_row=start, max_row=end)
    categories = Reference(ws.parent["CALC"], min_col=2, min_row=start, max_row=end)
    chart.add_data(data, titles_from_data=False)
    chart.set_categories(categories)
    if chart.series:
        series = chart.series[0]
        series.tx = SeriesLabel(v=primary["label"])
        series.graphicalProperties.line.solidFill = GREEN
        series.graphicalProperties.line.width = 28575
        series.marker.symbol = "circle"
        series.marker.size = 7
        series.marker.graphicalProperties.solidFill = GREEN
        series.marker.graphicalProperties.line.solidFill = GREEN
        series.dLbls = DataLabelList()
        series.dLbls.showVal = True
        series.dLbls.position = "t"
        if primary.get("unit") == "%":
            series.dLbls.numFmt = "0.0"
        elif primary.get("unit") in {"x", "índice"}:
            series.dLbls.numFmt = "0.00"
        elif primary.get("unit") == "R$":
            series.dLbls.numFmt = 'R$ #,##0'
        elif primary.get("unit") in {"alunos", "solicitações"}:
            series.dLbls.numFmt = "0"
        else:
            series.dLbls.numFmt = "0.0"
    has_primary_target = primary.get("direction") != "context" and any(
        primary.get(key) is not None
        for key in ("target", "target_min", "target_max", "attention", "attention_min", "attention_max")
    )
    if has_primary_target:
        target_col = calc_info["target_cols"]["target"]
        target_data = Reference(ws.parent["CALC"], min_col=target_col, min_row=start, max_row=end)
        chart.add_data(target_data, titles_from_data=False)
        if len(chart.series) > 1:
            series = chart.series[1]
            series.tx = SeriesLabel(v="Meta")
            series.graphicalProperties.line.solidFill = GOLD
            series.graphicalProperties.line.dashStyle = "dash"
            series.graphicalProperties.line.width = 19050
            series.marker.symbol = "none"
    if primary.get("unit") == "%":
        chart.y_axis.scaling.min = min(-10, 0) if spec["code"] == "DPE-01" else 0
        chart.y_axis.scaling.max = 100
        chart.y_axis.numFmt = '0"%"'
    elif primary.get("unit") in {"x", "índice"}:
        chart.y_axis.scaling.min = 0.75
        chart.y_axis.scaling.max = 1.5
        chart.y_axis.numFmt = '0.00"x"'
    elif primary.get("unit") == "meses":
        chart.y_axis.scaling.min = 0
        chart.y_axis.scaling.max = 36
        chart.y_axis.numFmt = '0.0'
    ws.add_chart(chart, anchor)
    return chart


def _build_panel(
    wb: Workbook,
    directorate_code: str,
    specs: list[dict[str, Any]],
    calc_info: dict[str, Any],
    periods: list[str],
) -> None:
    ws = wb["PAINEL"]
    directory = directorate_spec(directorate_code)
    _title(ws, f"PAINEL DE GESTÃO — {directorate_code}", directory["name"], end_col=18)
    ws.merge_cells("A4:C4"); ws["A4"] = "Período de referência"
    ws.merge_cells("D4:F4"); ws["D4"] = "Período de comparação"
    ws.merge_cells("G4:J4"); ws["G4"] = "Periodicidade"
    ws.merge_cells("K4:R4"); ws["K4"] = "Leitura executiva"
    for cell in ("A4", "D4", "G4", "K4"):
        ws[cell].font = Font(name="Aptos", size=9, bold=True, color=GRAY)
        ws[cell].alignment = Alignment(horizontal="left")
    ws.merge_cells("A5:C5"); ws["A5"] = "=PARAMETROS!$B$9"
    ws.merge_cells("D5:F5"); ws["D5"] = "=PARAMETROS!$B$10"
    ws.merge_cells("G5:J5"); ws["G5"] = "=PARAMETROS!$B$8"
    ws.merge_cells("K5:R5"); ws["K5"] = "Todos os valores vêm de CALC. O histórico completo permanece nas abas de base."
    for cell in ("A5", "D5", "G5", "K5"):
        ws[cell].fill = PatternFill("solid", fgColor=PALE_GREEN)
        ws[cell].font = Font(name="Aptos", size=10, bold=cell != "K5", color=DARK)
        ws[cell].alignment = Alignment(horizontal="center" if cell != "K5" else "left", vertical="center", wrap_text=True)
    ws.row_dimensions[5].height = 28

    card_row = 8
    card_width = 6 if len(specs) <= 3 else 4
    for index, spec in enumerate(specs):
        start_col = 1 + index * card_width
        end_col = min(18, start_col + card_width - 1)
        ws.merge_cells(start_row=card_row, start_column=start_col, end_row=card_row, end_column=end_col)
        ws.cell(card_row, start_col, f"{spec['code']} · {spec['short_name']}")
        ws.cell(card_row, start_col).fill = PatternFill("solid", fgColor=GREEN)
        ws.cell(card_row, start_col).font = Font(name="Aptos", size=10, bold=True, color=WHITE)
        ws.cell(card_row, start_col).alignment = Alignment(horizontal="center")
        metric_col = calc_info["metric_cols"][f"{spec['code']}::{spec['primary_metric']}"]
        ws.merge_cells(start_row=card_row + 1, start_column=start_col, end_row=card_row + 2, end_column=end_col)
        ws.cell(card_row + 1, start_col, _lookup_formula(calc_info, metric_col, spec["code"], "PARAMETROS!$B$9"))
        primary = next(metric for metric in spec["metrics"] if metric["key"] == spec["primary_metric"])
        ws.cell(card_row + 1, start_col).number_format = _metric_number_format(primary)
        ws.cell(card_row + 1, start_col).font = Font(name="Aptos Display", size=24, bold=True, color=GREEN)
        ws.cell(card_row + 1, start_col).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(card_row + 1, start_col).fill = PatternFill("solid", fgColor=PALE_GREEN)
        ws.merge_cells(start_row=card_row + 3, start_column=start_col, end_row=card_row + 3, end_column=end_col)
        card_value_ref = _cell_ref(start_col, card_row + 1)
        card_target_refs = {
            key: _target_lookup_formula(calc_info, calc_info["target_cols"][key], spec["code"], "PARAMETROS!$B$9").lstrip("=")
            for key in ("target", "attention", "target_min", "target_max", "attention_min", "attention_max")
        }
        ws.cell(card_row + 3, start_col, _status_formula(card_value_ref, primary, card_target_refs))
        ws.cell(card_row + 3, start_col).font = Font(name="Aptos", size=10, bold=True, color=DARK)
        ws.cell(card_row + 3, start_col).alignment = Alignment(horizontal="center")
        _add_status_conditional_formatting(ws, f"{get_column_letter(start_col)}{card_row+3}")
        ws.merge_cells(start_row=card_row + 4, start_column=start_col, end_row=card_row + 4, end_column=end_col)
        comp_formula = _lookup_formula(calc_info, metric_col, spec["code"], "PARAMETROS!$B$10").lstrip("=")
        comparison_format = "0.0" if primary.get("unit") != "x" else "0.00"
        ws.cell(card_row + 4, start_col, f'="Comparação: "&IF({comp_formula}="","—",TEXT({comp_formula},"{comparison_format}"))')
        ws.cell(card_row + 4, start_col).font = Font(name="Aptos", size=9, color=GRAY)
        ws.cell(card_row + 4, start_col).alignment = Alignment(horizontal="center")

    chart_window = 12 if directory["periodicity"] == "monthly" else 8
    current_row = 15
    for spec_index, spec in enumerate(specs):
        _section(ws, current_row, f"{spec['code']} · {spec['name']}", end_col=18)
        rows = calc_info["indicator_rows"][spec["code"]]
        if rows:
            chart_start_index = max(0, len(rows) - chart_window)
            chart_end_index = len(rows) - 1
            _chart_for_indicator(ws, spec, calc_info, chart_start_index, chart_end_index, f"A{current_row + 2}", chart_width=16, chart_height=7.2)
        detail_col = 12
        primary = next(metric for metric in spec["metrics"] if metric["key"] == spec["primary_metric"])
        detail_headers = ["Métrica", "Referência", "Comparação", "Meta", "Status"]
        _header_row(ws, current_row + 2, detail_col, detail_headers)
        detail_row = current_row + 3
        for metric in spec.get("metrics") or []:
            ws.cell(detail_row, detail_col, metric["label"])
            metric_col = calc_info["metric_cols"][f"{spec['code']}::{metric['key']}"]
            ws.cell(detail_row, detail_col + 1, _lookup_formula(calc_info, metric_col, spec["code"], "PARAMETROS!$B$9"))
            ws.cell(detail_row, detail_col + 2, _lookup_formula(calc_info, metric_col, spec["code"], "PARAMETROS!$B$10"))
            ws.cell(detail_row, detail_col + 1).number_format = _metric_number_format(metric)
            ws.cell(detail_row, detail_col + 2).number_format = _metric_number_format(metric)
            if metric["key"] == spec["primary_metric"]:
                ws.cell(detail_row, detail_col + 3, _target_lookup_formula(calc_info, calc_info["target_cols"]["target"], spec["code"], "PARAMETROS!$B$9"))
                detail_target_refs = {
                    key: _target_lookup_formula(calc_info, calc_info["target_cols"][key], spec["code"], "PARAMETROS!$B$9").lstrip("=")
                    for key in ("target", "attention", "target_min", "target_max", "attention_min", "attention_max")
                }
                value_ref = _cell_ref(detail_col + 1, detail_row)
                ws.cell(detail_row, detail_col + 4, _status_formula(value_ref, metric, detail_target_refs))
            else:
                # Secondary thresholds live in the catalog/targets sheet. The panel
                # preserves the value and leaves target/status interpretation to MATRIZ.
                ws.cell(detail_row, detail_col + 3, "Consulte METAS")
                ws.cell(detail_row, detail_col + 4, "—")
            detail_row += 1
        _style_body(ws, current_row + 3, detail_row - 1, detail_col, detail_col + 4)
        current_row += max(24, len(spec.get("metrics") or []) + 8)

    _set_widths(ws, {
        1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 12, 7: 12, 8: 12, 9: 12,
        10: 12, 11: 2.5, 12: 30, 13: 15, 14: 15, 15: 15, 16: 16, 17: 3, 18: 3,
    })
    ws.sheet_properties.tabColor = GREEN
    ws.freeze_panes = "A7"
    ws.sheet_view.zoomScale = 78
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.print_area = f"A1:R{current_row}"
    _sheet_defaults(ws, zoom=78, freeze="A7")


def _build_matrix(
    wb: Workbook,
    directorate_code: str,
    specs: list[dict[str, Any]],
    launch_info: dict[str, Any],
    reference: str | None,
) -> None:
    ws = wb["MATRIZ"]
    _title(ws, f"Matriz executiva — {directorate_code}", "Detalhamento por dimensão no período exportado", end_col=18)
    _section(ws, 4, "RECORTE DE REFERÊNCIA", end_col=18)
    ws["A5"] = "Período"
    ws["B5"] = reference or ""
    ws["A5"].font = Font(bold=True, color=GREEN)
    ws["B5"].fill = PatternFill("solid", fgColor=PALE_GREEN)
    headers = ["Indicador", "Dimensão", "Validado"]
    max_metrics = max(len(spec.get("metrics") or []) for spec in specs)
    headers += [f"Métrica {index + 1}" for index in range(max_metrics)]
    _header_row(ws, 7, 1, headers)
    row = 8
    for item, launch_row in launch_info["measurement_rows"]:
        if reference and item.get("period") != reference:
            continue
        spec = next((value for value in specs if value["code"] == item.get("indicator_code")), None)
        if not spec:
            continue
        ws.cell(row, 1, f"='LANÇAMENTOS'!B{launch_row}")
        ws.cell(row, 2, f"='LANÇAMENTOS'!D{launch_row}")
        ws.cell(row, 3, f"='LANÇAMENTOS'!F{launch_row}")
        for index, metric in enumerate(spec.get("metrics") or []):
            col = launch_info["metric_cols"][f"{spec['code']}::{metric['key']}"]
            ws.cell(row, 4 + index, f"='LANÇAMENTOS'!{get_column_letter(col)}{launch_row}")
            ws.cell(row, 4 + index).number_format = _metric_number_format(metric)
            ws.cell(7, 4 + index, metric["label"] if ws.cell(7, 4 + index).value and ws.cell(7, 4 + index).value.startswith("Métrica") else ws.cell(7, 4 + index).value)
        row += 1
    end_row = max(8, row - 1)
    _style_body(ws, 8, end_row, 1, len(headers))
    ws.auto_filter.ref = f"A7:{get_column_letter(len(headers))}{end_row}"
    _set_widths(ws, {1: 14, 2: 42, 3: 12, **{col: 21 for col in range(4, len(headers) + 1)}})
    _sheet_defaults(ws, zoom=78, freeze="A8")
    ws.sheet_properties.tabColor = LIME


def _write_targets(wb: Workbook, directorate_code: str, specs: list[dict[str, Any]], targets: list[dict[str, Any]]) -> None:
    ws = wb["METAS"]
    _title(ws, f"Metas versionadas — {directorate_code}", "Metas específicas prevalecem sobre os parâmetros iniciais do catálogo", end_col=14)
    headers = [
        "ID", "Indicador", "Métrica", "Dimensão", "Vigência inicial", "Vigência final",
        "Meta", "Atenção", "Meta mínima", "Meta máxima", "Atenção mínima", "Atenção máxima",
        "Justificativa", "Origem",
    ]
    _header_row(ws, HEADER_ROW, 1, headers)
    rows = []
    for item in targets:
        rows.append([
            item.get("id"), item.get("indicator_code"), item.get("metric_key"),
            item.get("dimension_label") or "TOTAL", item.get("valid_from"), item.get("valid_to"),
            item.get("target"), item.get("attention"), item.get("target_min"), item.get("target_max"),
            item.get("attention_min"), item.get("attention_max"), item.get("justification"), "Banco",
        ])
    if not rows:
        for spec in specs:
            for metric in spec.get("metrics") or []:
                if metric.get("direction") == "context":
                    continue
                rows.append([
                    None, spec["code"], metric["key"], "TOTAL", "Parâmetro inicial", None,
                    metric.get("target"), metric.get("attention"), metric.get("target_min"), metric.get("target_max"),
                    metric.get("attention_min"), metric.get("attention_max"), spec.get("notes"), "Catálogo",
                ])
    for row_index, values in enumerate(rows, start=DATA_START_ROW):
        for col_index, value in enumerate(values, start=1):
            ws.cell(row_index, col_index, value)
    end_row = max(DATA_START_ROW, DATA_START_ROW + len(rows) - 1)
    _style_body(ws, DATA_START_ROW, end_row, 1, len(headers))
    for col in range(7, 13):
        for row in range(DATA_START_ROW, end_row + 1):
            ws.cell(row, col).number_format = '0.00'
    ws.auto_filter.ref = f"A{HEADER_ROW}:N{end_row}"
    _set_widths(ws, {1: 8, 2: 13, 3: 30, 4: 30, 5: 16, 6: 16, 7: 13, 8: 13, 9: 13, 10: 13, 11: 15, 12: 15, 13: 55, 14: 12})
    _sheet_defaults(ws, zoom=75, freeze="A7")


def _write_actions(wb: Workbook, directorate_code: str, actions: list[dict[str, Any]]) -> None:
    ws = wb["PLANO_DE_ACAO"]
    _title(ws, f"Planos de ação — {directorate_code}", "Todo resultado fora da meta deve possuir responsável e prazo", end_col=14)
    headers = [
        "ID", "Indicador", "Métrica", "Período", "Dimensão", "Problema", "Causa provável",
        "Ação corretiva", "Responsável", "Prazo", "Status", "Evidência", "Criado por", "Atualizado em",
    ]
    _header_row(ws, HEADER_ROW, 1, headers)
    for offset, item in enumerate(actions):
        row = DATA_START_ROW + offset
        values = [
            item.get("id"), item.get("indicator_code"), item.get("metric_key"), item.get("period"),
            item.get("dimension_label") or "TOTAL", item.get("problem"), item.get("probable_cause"),
            item.get("corrective_action"), item.get("responsible"), item.get("due_date"), item.get("status"),
            item.get("evidence"), item.get("created_by"), item.get("updated_at"),
        ]
        for col, value in enumerate(values, start=1):
            ws.cell(row, col, value)
    end_row = max(DATA_START_ROW, DATA_START_ROW + len(actions) - 1)
    _style_body(ws, DATA_START_ROW, end_row, 1, len(headers))
    ws.auto_filter.ref = f"A{HEADER_ROW}:N{end_row}"
    _set_widths(ws, {1: 8, 2: 13, 3: 26, 4: 14, 5: 30, 6: 40, 7: 35, 8: 44, 9: 24, 10: 14, 11: 16, 12: 35, 13: 25, 14: 20})
    _sheet_defaults(ws, zoom=70, freeze="A7")


def _write_indicators(wb: Workbook, directorate_code: str, specs: list[dict[str, Any]]) -> None:
    ws = wb["INDICADORES"]
    _title(ws, f"Catálogo de indicadores — {directorate_code}", "Definição institucional, fórmula, fonte e governança", end_col=12)
    headers = ["Código", "Indicador", "Métrica", "Unidade", "Direção", "Fórmula / agregação", "Periodicidade", "Fonte", "Responsável", "Objetivo", "Dimensões", "Observações"]
    _header_row(ws, HEADER_ROW, 1, headers)
    row = DATA_START_ROW
    for spec in specs:
        for metric in spec.get("metrics") or []:
            values = [
                spec["code"], spec["name"], metric["label"], metric.get("unit"), metric.get("direction"),
                spec["formula_text"] if metric["key"] == spec["primary_metric"] else metric.get("aggregation"),
                "Mensal" if spec["periodicity"] == "monthly" else "Semestral",
                spec["source"], spec["responsible"], spec["objective"], ", ".join(spec.get("dimensions") or []), spec.get("notes"),
            ]
            for col, value in enumerate(values, start=1):
                ws.cell(row, col, value)
            row += 1
    end_row = row - 1
    _style_body(ws, DATA_START_ROW, end_row, 1, len(headers))
    for row in range(DATA_START_ROW, end_row + 1):
        ws.row_dimensions[row].height = 64
    ws.auto_filter.ref = f"A{HEADER_ROW}:L{end_row}"
    _set_widths(ws, {1: 13, 2: 38, 3: 30, 4: 14, 5: 14, 6: 58, 7: 15, 8: 48, 9: 35, 10: 45, 11: 30, 12: 48})
    _sheet_defaults(ws, zoom=65, freeze="A7")


def _write_periods(wb: Workbook, directorate_code: str, periods: list[str]) -> None:
    ws = wb["DIM_PERIODO"]
    _title(ws, f"Dimensão de período — {directorate_code}", "Histórico disponível na exportação", end_col=6)
    _header_row(ws, HEADER_ROW, 1, ["Período", "Ordem", "Ano", "Mês/Semestre", "Periodicidade", "Disponível"])
    periodicity = directorate_spec(directorate_code)["periodicity"]
    for offset, period in enumerate(periods):
        row = DATA_START_ROW + offset
        ws.cell(row, 1, period)
        ws.cell(row, 2, period_sort_key(period))
        ws.cell(row, 3, int(period[:4]))
        ws.cell(row, 4, period[5:])
        ws.cell(row, 5, "Mensal" if periodicity == "monthly" else "Semestral")
        ws.cell(row, 6, "Sim")
    end_row = max(DATA_START_ROW, DATA_START_ROW + len(periods) - 1)
    _style_body(ws, DATA_START_ROW, end_row, 1, 6)
    _set_widths(ws, {1: 16, 2: 12, 3: 12, 4: 16, 5: 16, 6: 14})
    _sheet_defaults(ws, zoom=85, freeze="A7")
    ws.sheet_state = "hidden"


def _write_quality(wb: Workbook, directorate_code: str, measurements: list[dict[str, Any]], specs: list[dict[str, Any]], periods: list[str]) -> None:
    ws = wb["QUALIDADE E GOVERNANÇA"]
    _title(ws, f"Qualidade e governança — {directorate_code}", "Cobertura, validação e pontos de controle", end_col=10)
    _section(ws, 4, "RESUMO DA BASE", end_col=10)
    metrics = [
        ("Registros exportados", len(measurements)),
        ("Registros validados", sum(1 for item in measurements if item.get("validated"))),
        ("Períodos disponíveis", len(periods)),
        ("Indicadores ativos", len(specs)),
        ("Primeiro período", periods[0] if periods else "—"),
        ("Último período", periods[-1] if periods else "—"),
    ]
    for row, (label, value) in enumerate(metrics, start=6):
        ws.cell(row, 1, label)
        ws.cell(row, 2, value)
        ws.cell(row, 1).font = Font(bold=True, color=GREEN)
        ws.cell(row, 2).fill = PatternFill("solid", fgColor=PALE_GREEN)
    _section(ws, 14, "CONTROLES INSTITUCIONAIS", end_col=10)
    controls = [
        "O banco é a fonte oficial; a planilha é uma visão executiva.",
        "Nenhuma base é truncada silenciosamente. Acima do limite físico do XLSX, a exportação falha explicitamente.",
        "DADM e DPE aceitam somente AAAA-MM; DM aceita somente AAAA-SEM1 ou AAAA-SEM2.",
        "Componentes brutos ficam preservados para auditoria e recálculo futuro.",
        "Metas possuem vigência e podem ser específicas por dimensão.",
        "Resultados fora da meta devem gerar plano de ação.",
    ]
    for offset, text in enumerate(controls, start=16):
        ws.merge_cells(start_row=offset, start_column=1, end_row=offset, end_column=10)
        ws.cell(offset, 1, f"• {text}")
        ws.cell(offset, 1).alignment = Alignment(wrap_text=True)
        ws.row_dimensions[offset].height = 28
    _set_widths(ws, {1: 28, 2: 22, 3: 14, 4: 14, 5: 14, 6: 14, 7: 14, 8: 14, 9: 14, 10: 14})
    _sheet_defaults(ws, zoom=90)


def build_management_workbook(
    directorate_code: str,
    measurements: Iterable[dict[str, Any]],
    targets: Iterable[dict[str, Any]] = (),
    actions: Iterable[dict[str, Any]] = (),
    *,
    reference: str | None = None,
    comparison: str | None = None,
    only_indicator: str | None = None,
) -> BytesIO:
    if str(directorate_code).strip().upper() == "DPE":
        # A DPE possui páginas e bases próprias a partir da v0.7.1. A DADM v0.7.8
        # reutiliza este motor auditável por meio de uma camada dedicada; a DM mantém seu fluxo próprio.
        from dpe_excel_builder import build_dpe_workbook
        return build_dpe_workbook(
            measurements,
            targets,
            actions,
            reference=reference,
            comparison=comparison,
            only_indicator=only_indicator,
        )
    directorate_code = str(directorate_code).strip().upper()
    directory = directorate_spec(directorate_code)
    specs = indicator_specs(directorate_code)
    if only_indicator:
        selected_code = indicator_spec(directorate_code, only_indicator)["code"]
        specs = [spec for spec in specs if spec["code"] == selected_code]
    else:
        selected_code = None
    measurements = [dict(item) for item in measurements]
    targets = [dict(item) for item in targets]
    actions = [dict(item) for item in actions]
    if selected_code:
        measurements = [item for item in measurements if item.get("indicator_code") == selected_code]
        targets = [item for item in targets if item.get("indicator_code") == selected_code]
        actions = [item for item in actions if item.get("indicator_code") == selected_code]
    periods = sorted(
        {str(item.get("period")) for item in measurements if item.get("period")},
        key=period_sort_key,
    )
    if reference:
        reference = validate_period(directorate_code, reference)
    elif periods:
        reference = periods[-1]
    if comparison:
        comparison = validate_period(directorate_code, comparison)
    elif reference:
        # Same rule used by the web service is deliberately kept simple here.
        if directory["periodicity"] == "monthly":
            year, month = map(int, reference.split("-"))
            comparison = f"{year - 1:04d}-{month:02d}" if directory.get("comparison_policy") == "previous_period_and_year_over_year" else (
                f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"
            )
        else:
            comparison = f"{int(reference[:4]) - 1:04d}{reference[4:]}"

    fields, dimensions, metrics = _unique_catalog_fields(specs)
    wb = Workbook()
    default = wb.active
    wb.remove(default)
    for name in [
        "LEIA-ME", "PARAMETROS", "PAINEL", "QUALIDADE E GOVERNANÇA", "MATRIZ",
        "PLANO_DE_ACAO", "LANÇAMENTOS", "METAS", "INDICADORES", "DIM_PERIODO", "CALC",
    ]:
        wb.create_sheet(name)
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"

    _write_readme(wb, directorate_code, specs)
    _write_parameters(wb, directorate_code, reference, comparison, periods)
    launch_info = _build_launch_sheet(wb, directorate_code, specs, measurements, fields, dimensions, metrics)
    calc_info = _build_calc_sheet(wb, directorate_code, specs, periods, fields, metrics, launch_info, targets)
    _build_panel(wb, directorate_code, specs, calc_info, periods)
    _build_matrix(wb, directorate_code, specs, launch_info, reference)
    _write_targets(wb, directorate_code, specs, targets)
    _write_actions(wb, directorate_code, actions)
    _write_indicators(wb, directorate_code, specs)
    _write_periods(wb, directorate_code, periods)
    _write_quality(wb, directorate_code, measurements, specs, periods)

    # Workbook-level polish and tab colors.
    tab_colors = {
        "LEIA-ME": GREEN,
        "PARAMETROS": GOLD,
        "PAINEL": GREEN,
        "QUALIDADE E GOVERNANÇA": PURPLE,
        "MATRIZ": LIME,
        "PLANO_DE_ACAO": ORANGE,
        "LANÇAMENTOS": BLUE,
        "METAS": GOLD,
        "INDICADORES": GREEN_2,
        "DIM_PERIODO": GRAY,
        "CALC": GRAY,
    }
    for sheet, color in tab_colors.items():
        wb[sheet].sheet_properties.tabColor = color
    wb.active = wb.sheetnames.index("PAINEL")

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
