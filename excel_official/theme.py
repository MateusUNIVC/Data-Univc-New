from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CellRole(StrEnum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    SECTION = "section"
    TABLE_HEADER = "table_header"
    BODY = "body"
    BODY_CENTER = "body_center"
    INPUT = "input"
    IMPORTED = "imported"
    DERIVED = "derived"
    STATIC = "static"
    CONTROL = "control"
    VISUALIZATION = "visualization"
    TECHNICAL = "technical"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    KPI_LABEL = "kpi_label"
    KPI_VALUE = "kpi_value"
    NOTE = "note"


@dataclass(frozen=True, slots=True)
class ColorPalette:
    green_dark: str = "045233"
    green: str = "0B7A54"
    green_mid: str = "13845E"
    green_pale: str = "E8F3F0"
    green_light: str = "F3F8F5"

    input_fill: str = "FFF6DC"
    warning_fill: str = "FFF4D6"
    error_fill: str = "FDE7E7"
    info_fill: str = "EAF2FA"

    gray_50: str = "F7F9F8"
    gray_100: str = "EEF2F0"
    gray_300: str = "D8E0DC"
    gray_600: str = "5A5A5A"

    ink: str = "1D2B25"
    black: str = "000000"
    white: str = "FFFFFF"

    input_text: str = "1D2B25"
    imported_text: str = "008000"
    derived_text: str = "000000"
    static_text: str = "5A5A5A"
    control_text: str = "7030A0"
    visualization_text: str = "008A8A"

    blue: str = "2F6B9A"
    teal: str = "008A8A"
    orange: str = "D98C24"
    red: str = "C94A4A"


@dataclass(frozen=True, slots=True)
class TypographyTokens:
    family: str = "Arial"
    body_size: float = 9.0
    small_size: float = 8.0
    parameter_size: float = 10.0
    section_size: float = 11.0
    title_size: float = 15.0
    kpi_value_size: float = 16.0


@dataclass(frozen=True, slots=True)
class NumberFormatTokens:
    integer: str = '#,##0'
    decimal_1: str = '0.0'
    decimal_2: str = '0.00'
    percentage: str = '0.0%'
    percentage_points: str = '0.0"%"'
    delta_1: str = '+0.0;-0.0;0.0'
    delta_2: str = '+0.00;-0.00;0.00'
    date: str = 'dd/mm/yyyy'
    datetime: str = 'dd/mm/yyyy hh:mm'
    currency_brl: str = 'R$ #,##0.00;[Red](R$ #,##0.00);-'
    accounting_number: str = '#,##0.00;[Red](#,##0.00);-'
    accounting_integer: str = '#,##0;[Red](#,##0);-'


@dataclass(frozen=True, slots=True)
class TableTokens:
    style_name: str = "TableStyleMedium4"
    show_first_column: bool = False
    show_last_column: bool = False
    show_row_stripes: bool = True
    show_column_stripes: bool = False


@dataclass(frozen=True, slots=True)
class ChartTokens:
    series_colors: tuple[str, ...] = (
        "0B7A54",
        "2F6B9A",
        "D98C24",
        "008A8A",
        "6B5CA5",
        "C94A4A",
    )
    font_family: str = "Arial"
    axis_text_color: str = "5A5A5A"
    gridline_color: str = "D8E0DC"
    width: float = 12.2
    height: float = 7.0
    legend_position: str = "r"
    line_width: int = 22000
    marker_size: int = 6
    doughnut_hole_size: int = 58


@dataclass(frozen=True, slots=True)
class DashboardTokens:
    total_columns: int = 12
    context_columns_per_item: int = 2
    context_items_per_row: int = 6
    kpis_per_row: int = 4
    kpi_columns: int = 3
    kpi_rows: int = 5
    kpi_gap_rows: int = 1
    chart_columns: int = 6
    chart_rows: int = 16


@dataclass(frozen=True, slots=True)
class LayoutTokens:
    default_zoom: int = 90
    default_row_height: float = 18.0
    title_row_height: float = 28.0
    subtitle_row_height: float = 28.0
    section_row_height: float = 22.0
    table_header_row_height: float = 30.0
    margin_left: float = 0.30
    margin_right: float = 0.30
    margin_top: float = 0.45
    margin_bottom: float = 0.45
    margin_header: float = 0.15
    margin_footer: float = 0.15
    table_min_column_width: float = 10.0
    table_max_column_width: float = 42.0
    table_column_padding: int = 2
    table_width_scan_rows: int = 250


@dataclass(frozen=True, slots=True)
class ExcelOfficialTheme:
    name: str = "Data UNIVC Excel Official V1"
    palette: ColorPalette = field(default_factory=ColorPalette)
    typography: TypographyTokens = field(default_factory=TypographyTokens)
    number_formats: NumberFormatTokens = field(default_factory=NumberFormatTokens)
    tables: TableTokens = field(default_factory=TableTokens)
    charts: ChartTokens = field(default_factory=ChartTokens)
    dashboard: DashboardTokens = field(default_factory=DashboardTokens)
    layout: LayoutTokens = field(default_factory=LayoutTokens)


DEFAULT_THEME = ExcelOfficialTheme()


__all__ = [
    "CellRole",
    "ChartTokens",
    "ColorPalette",
    "DEFAULT_THEME",
    "DashboardTokens",
    "ExcelOfficialTheme",
    "LayoutTokens",
    "NumberFormatTokens",
    "TableTokens",
    "TypographyTokens",
]
