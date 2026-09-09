from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.defined_name import DefinedName

from dm_catalog import DM_AREAS
from excel_errors import ExcelExportLimitError
from release_info import APP_VERSION


GREEN_DARK = "045233"
GREEN = "0B7A54"
GREEN_MID = "13845E"
GREEN_PALE = "E8F1ED"
GREEN_LIGHT = "F2F8F5"
YELLOW_INPUT = "FFF6DC"
YELLOW_WARN = "FFF4D8"
RED_LIGHT = "FDE7E7"
GRAY_50 = "F7F9F8"
GRAY_100 = "EEF2F0"
GRAY_300 = "D8E0DC"
GRAY_600 = "6D7973"
INK = "1D2B25"
WHITE = "FFFFFF"
PURPLE = "6B5CA5"
TEAL = "008A8A"
BLUE = "2F6B9A"
ORANGE = "D98C24"
RED = "C94A4A"

THIN = Side(style="thin", color=GRAY_300)
HAIR = Side(style="hair", color=GRAY_300)
INT_FMT = '#,##0'
DECIMAL_FMT = '0.0'
PCT_FMT = '0.0%'
DATE_FMT = 'dd/mm/yyyy'
DATETIME_FMT = 'dd/mm/yyyy hh:mm'
VAR_FMT = '+0.0;-0.0;0.0'
EXCEL_MAX_ROW = 1_048_576

VISIBLE_SHEETS = [
    "LEIA-ME",
    "PARAMETROS",
    "PAINEL",
    "DM-01 EVOLUCAO",
    "DM-02 DEFESAS",
    "TURMAS",
    "ALUNOS E DEFESAS",
    "MATRIZ",
    "METAS E PLANOS",
    "INTEGRACAO SEI",
    "QUALIDADE E GOVERNANCA",
]

TECHNICAL_SHEETS = [
    "DADOS_TURMAS",
    "DADOS_ALUNOS",
    "DADOS_METAS",
    "DADOS_SEI",
    "META_EFETIVA",
    "LISTAS",
    "CALC",
]

MATRIX_OPTIONS = [
    "DM-01 | Membros por turma",
    "Ocupacao | Vagas",
    "DM-02 | Tempo medio ate defesa",
    "Defesas | Ate 24 meses",
    "Risco | >30m sem defesa",
]
WINDOW_OPTIONS: list[int | str] = [4, 6, 8, 12, "Todo historico"]
STUDENT_STATUS_OPTIONS = ["(todos)", "Ativo", "Titulado", "Desligado"]


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")[:25])
    except ValueError:
        try:
            return datetime.fromisoformat(text[:19])
        except ValueError:
            return None


def _semester_for_date(value: date) -> str:
    return f"{value.year:04d}-SEM{1 if value.month <= 6 else 2}"


def _target_for_period(
    targets: list[dict[str, Any]],
    indicator_code: str,
    metric_key: str,
    period: str,
    *,
    default: float | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    rows = [
        row for row in targets
        if str(row.get("indicator_code") or "").upper() == indicator_code
        and str(row.get("metric_key") or "") == metric_key
        and row.get("dimension_key") in (None, "", "TOTAL")
        and str(row.get("valid_from") or "") <= period
        and (not row.get("valid_to") or str(row.get("valid_to")) >= period)
    ]
    rows.sort(key=lambda row: (str(row.get("valid_from") or ""), int(row.get("id") or 0)), reverse=True)
    if not rows:
        return default, None
    value = rows[0].get("target")
    return (float(value) if value is not None else default), rows[0]


def _cohort_key(row: dict[str, Any]) -> str:
    code = str(row.get("area_code") or "").upper()
    number = int(row.get("cohort_number") or 0)
    return f"{code} | Turma {number}"


def _sort_cohorts(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            str(row.get("area_code") or ""),
            int(row.get("cohort_number") or 0),
            str(row.get("opening_date") or ""),
            int(row.get("id") or 0),
        ),
    )


def build_dm_interactive_payload(
    cohorts: Iterable[dict[str, Any]],
    students: Iterable[dict[str, Any]],
    *,
    targets: Iterable[dict[str, Any]] | None = None,
    actions: Iterable[dict[str, Any]] | None = None,
    sync_runs: Iterable[dict[str, Any]] | None = None,
    area_code: str | None = None,
    cohort_id: int | None = None,
    as_of: date | None = None,
    window_cohorts: int | str | None = None,
    student_status: str | None = None,
    matrix_kpi: str | None = None,
) -> dict[str, Any]:
    """Build the complete authorized DM dataset for the interactive workbook.

    Web filters seed PARAMETROS only. Unlike DM Excel V2, factual bases are not
    reduced by the web filter, so the workbook can be used as a second interface.
    """
    cohort_rows = _sort_cohorts(cohorts)
    student_rows = [dict(row) for row in students]
    target_rows = [dict(row) for row in (targets or [])]
    action_rows = [dict(row) for row in (actions or [])]
    sync_rows = [dict(row) for row in (sync_runs or [])]

    if len(cohort_rows) + 50 >= EXCEL_MAX_ROW:
        raise ExcelExportLimitError("A base de turmas da DM excede o limite fisico do Excel.")
    if len(student_rows) + 50 >= EXCEL_MAX_ROW:
        raise ExcelExportLimitError("A base de alunos da DM excede o limite fisico do Excel.")

    selected_area = str(area_code or "").strip().upper()
    if selected_area not in DM_AREAS:
        selected_area = "(todas)"

    selected_cohort = "(todas)"
    if cohort_id not in (None, ""):
        match = next((row for row in cohort_rows if int(row.get("id") or 0) == int(cohort_id)), None)
        if match is not None:
            selected_cohort = _cohort_key(match)
            selected_area = str(match.get("area_code") or selected_area).upper()

    if isinstance(window_cohorts, int) and window_cohorts in {4, 6, 8, 12}:
        initial_window: int | str = window_cohorts
    elif str(window_cohorts or "").strip().casefold() in {"all", "todo historico", "todo historico"}:
        initial_window = "Todo historico"
    else:
        initial_window = 6

    selected_status = str(student_status or "(todos)").strip()
    if selected_status not in STUDENT_STATUS_OPTIONS:
        selected_status = "(todos)"
    selected_matrix = str(matrix_kpi or MATRIX_OPTIONS[0]).strip()
    if selected_matrix not in MATRIX_OPTIONS:
        selected_matrix = MATRIX_OPTIONS[0]

    # Ranking is static because a cohort's identity/order does not change when
    # the workbook filter changes. Window controls select from these ranks.
    by_area: dict[str, list[dict[str, Any]]] = {}
    for row in cohort_rows:
        by_area.setdefault(str(row.get("area_code") or ""), []).append(row)
    area_rev_rank: dict[int, int] = {}
    for rows in by_area.values():
        ordered = sorted(rows, key=lambda row: (int(row.get("cohort_number") or 0), str(row.get("opening_date") or ""), int(row.get("id") or 0)), reverse=True)
        for rank, row in enumerate(ordered, 1):
            area_rev_rank[int(row.get("id") or 0)] = rank
    global_ordered = sorted(
        cohort_rows,
        key=lambda row: (str(row.get("opening_date") or ""), int(row.get("cohort_number") or 0), str(row.get("area_code") or ""), int(row.get("id") or 0)),
        reverse=True,
    )
    global_rev_rank = {int(row.get("id") or 0): rank for rank, row in enumerate(global_ordered, 1)}

    # Effective target table is pre-expanded by semester. It allows a simple
    # SUMIFS in Excel when P_DM_ASOF changes without volatile/array formulas.
    effective_targets: list[dict[str, Any]] = []
    for year in range(2000, 2101):
        for sem in (1, 2):
            period = f"{year:04d}-SEM{sem}"
            for code, metric, default in (
                ("DM-01", "cohort_members", None),
                ("DM-02", "average_months_to_defense", 24.0),
            ):
                target, source = _target_for_period(target_rows, code, metric, period, default=default)
                effective_targets.append({
                    "period": period,
                    "indicator_code": code,
                    "metric_key": metric,
                    "target": target,
                    "source_valid_from": source.get("valid_from") if source else None,
                    "source_valid_to": source.get("valid_to") if source else None,
                    "justification": source.get("justification") if source else ("Referencia padrao DM-02" if code == "DM-02" else None),
                })

    return {
        "directorate": "DM",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "cohorts": cohort_rows,
        "students": student_rows,
        "targets": target_rows,
        "actions": action_rows,
        "sync_runs": sync_rows[:100],
        "effective_targets": effective_targets,
        "area_rev_rank": area_rev_rank,
        "global_rev_rank": global_rev_rank,
        "cohort_options": [_cohort_key(row) for row in cohort_rows],
        "initial": {
            "area": selected_area,
            "cohort": selected_cohort,
            "comparison": "(nenhuma)",
            "as_of": as_of or date.today(),
            "window": initial_window,
            "student_status": selected_status,
            "matrix_kpi": selected_matrix,
        },
    }


def _setup(ws, *, freeze: str | None = None, zoom: int = 90) -> None:
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = zoom
    if freeze:
        ws.freeze_panes = freeze
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.left = 0.3
    ws.page_margins.right = 0.3
    ws.page_margins.top = 0.45
    ws.page_margins.bottom = 0.45


def _title(ws, title: str, subtitle: str = "", *, end_col: int = 12) -> int:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_col)
    c = ws.cell(1, 1, title)
    c.font = Font(name="Arial", size=15, bold=True, color=GREEN_DARK)
    c.alignment = Alignment(vertical="center")
    c.border = Border(bottom=Side(style="medium", color=GREEN))
    ws.row_dimensions[1].height = 28
    if subtitle:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end_col)
        c = ws.cell(2, 1, subtitle)
        c.font = Font(name="Arial", size=9, color=GRAY_600)
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.row_dimensions[2].height = 30
        return 4
    return 3


def _section(ws, row: int, text: str, *, end_col: int = 12) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=end_col)
    c = ws.cell(row, 1, text)
    c.fill = PatternFill("solid", fgColor=GREEN_DARK)
    c.font = Font(name="Arial", size=10, bold=True, color=WHITE)
    c.alignment = Alignment(vertical="center")
    ws.row_dimensions[row].height = 22


def _header(cell) -> None:
    cell.fill = PatternFill("solid", fgColor=GREEN)
    cell.font = Font(name="Arial", size=8, bold=True, color=WHITE)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = Border(bottom=THIN)


def _body(cell, *, imported: bool = False, formula: bool = False, wrap: bool = False) -> None:
    color = "008000" if imported else INK
    if formula:
        color = INK
    cell.font = Font(name="Arial", size=8, color=color)
    cell.alignment = Alignment(vertical="center", wrap_text=wrap)
    cell.border = Border(bottom=HAIR)


def _auto_width(ws, *, min_width: int = 10, max_width: int = 36) -> None:
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        longest = 0
        for row in range(1, min(ws.max_row, 180) + 1):
            value = ws.cell(row, col).value
            if value is not None:
                longest = max(longest, len(str(value)))
        ws.column_dimensions[letter].width = min(max(longest + 2, min_width), max_width)


def _add_table(ws, name: str, header_row: int, last_row: int, last_col: int) -> None:
    if last_row <= header_row:
        return
    table = Table(displayName=name, ref=f"A{header_row}:{get_column_letter(last_col)}{last_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium4",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)


def _named(wb: Workbook, name: str, ref: str) -> None:
    wb.defined_names.add(DefinedName(name, attr_text=ref))


def _write_simple_data(wb: Workbook, name: str, headers: list[str], rows: list[list[Any]], table_name: str) -> int:
    ws = wb.create_sheet(name)
    _setup(ws, freeze="A2", zoom=75)
    for c, label in enumerate(headers, 1):
        ws.cell(1, c, label)
        _header(ws.cell(1, c))
    for r, values in enumerate(rows, 2):
        for c, value in enumerate(values, 1):
            ws.cell(r, c, value)
            _body(ws.cell(r, c), imported=True, wrap=c in {12, 13, 15})
            if isinstance(value, date):
                ws.cell(r, c).number_format = DATE_FMT
            elif isinstance(value, datetime):
                ws.cell(r, c).number_format = DATETIME_FMT
    last = max(2, len(rows) + 1)
    _add_table(ws, table_name, 1, last, len(headers))
    _auto_width(ws)
    return last


def _write_technical_data(wb: Workbook, payload: dict[str, Any]) -> dict[str, int]:
    cohort_rows: list[list[Any]] = []
    for row in payload["cohorts"]:
        row_id = int(row.get("id") or 0)
        cohort_rows.append([
            str(row.get("area_code") or ""),
            row.get("area_name") or DM_AREAS.get(str(row.get("area_code") or ""), ""),
            row_id,
            int(row.get("cohort_number") or 0),
            _cohort_key(row),
            row.get("cohort_label") or f"Turma {int(row.get('cohort_number') or 0)}",
            _to_date(row.get("opening_date")),
            row.get("vacancies_authorized"),
            row.get("status"),
            row.get("source_system"),
            row.get("sei_raw_label"),
            _to_datetime(row.get("last_seen_sei_at")),
            row.get("notes"),
            "Sim" if row.get("is_demo") else "Nao",
            payload["area_rev_rank"].get(row_id),
            payload["global_rev_rank"].get(row_id),
        ])
    ends: dict[str, int] = {}
    ends["cohorts"] = _write_simple_data(
        wb,
        "DADOS_TURMAS",
        ["Area", "Nome da area", "Cohort ID", "Turma", "Chave", "Rotulo", "Abertura", "Vagas", "Status", "Origem", "Rotulo SEI", "Ultima leitura SEI", "Observacoes", "Demo", "Rank area", "Rank global"],
        cohort_rows,
        "tblDmV3TurmasRaw",
    )

    ws = wb.create_sheet("DADOS_ALUNOS")
    _setup(ws, freeze="A2", zoom=70)
    headers = [
        "Area", "Nome da area", "Cohort ID", "Turma", "Chave da turma", "Matricula", "Aluno",
        "Ingresso", "Qualificacao", "Defesa", "Defesa marcada", "Status", "Saida", "Orientador",
        "Linha de pesquisa", "Ingresso provisorio", "Origem", "Situacao SEI", "Ultima leitura SEI",
        "Ultima consulta de datas SEI", "Qualidade", "Observacoes", "Meses ate defesa",
        "Defesa <=24m", "Risco >18m sem qualificacao", "Risco >24m sem defesa marcada", "Risco >30m sem defesa",
    ]
    for c, label in enumerate(headers, 1):
        ws.cell(1, c, label)
        _header(ws.cell(1, c))
    for r, row in enumerate(sorted(payload["students"], key=lambda x: (str(x.get("area_code") or ""), int(x.get("cohort_number") or 0), str(x.get("student_name") or ""))), 2):
        values = [
            row.get("area_code"), row.get("area_name"), row.get("cohort_id"), row.get("cohort_number"),
            f"{str(row.get('area_code') or '').upper()} | Turma {int(row.get('cohort_number') or 0)}",
            row.get("student_code"), row.get("student_name"), _to_date(row.get("entry_date")),
            _to_date(row.get("qualification_date")), _to_date(row.get("defense_date")),
            _to_date(row.get("defense_scheduled_date")), row.get("status"), _to_date(row.get("exit_date")),
            row.get("advisor"), row.get("research_line"), "Sim" if row.get("entry_date_estimated") else "Nao",
            row.get("source_system"), row.get("sei_raw_status"), _to_datetime(row.get("last_seen_sei_at")),
            _to_datetime(row.get("last_course_dates_sei_at")), row.get("data_quality"), row.get("notes"),
        ]
        for c, value in enumerate(values, 1):
            ws.cell(r, c, value)
            _body(ws.cell(r, c), imported=True, wrap=c in {7, 14, 15, 18, 21, 22})
        for c in (8, 9, 10, 11, 13):
            ws.cell(r, c).number_format = DATE_FMT
        for c in (19, 20):
            ws.cell(r, c).number_format = DATETIME_FMT
        ws.cell(r, 23, f'=IF(OR(H{r}="",J{r}="",P{r}="Sim"),"",ROUND(YEARFRAC(H{r},J{r})*12,1))')
        ws.cell(r, 24, f'=IF(AND(W{r}<>"",J{r}<=P_DM_ASOF,W{r}<=24),1,0)')
        ws.cell(r, 25, f'=IF(AND(L{r}="Ativo",H{r}<>"",P{r}<>"Sim",I{r}="",P_DM_ASOF>=H{r},YEARFRAC(H{r},P_DM_ASOF)*12>18),1,0)')
        ws.cell(r, 26, f'=IF(AND(L{r}="Ativo",H{r}<>"",P{r}<>"Sim",J{r}="",K{r}="",P_DM_ASOF>=H{r},YEARFRAC(H{r},P_DM_ASOF)*12>24),1,0)')
        ws.cell(r, 27, f'=IF(AND(L{r}="Ativo",H{r}<>"",P{r}<>"Sim",J{r}="",P_DM_ASOF>=H{r},YEARFRAC(H{r},P_DM_ASOF)*12>30),1,0)')
        for c in range(23, 28):
            _body(ws.cell(r, c), formula=True)
        ws.cell(r, 23).number_format = DECIMAL_FMT
    ends["students"] = max(2, len(payload["students"]) + 1)
    _add_table(ws, "tblDmV3AlunosRaw", 1, ends["students"], len(headers))
    _auto_width(ws, max_width=32)

    target_rows = []
    for row in payload["targets"]:
        target_rows.append([
            row.get("indicator_code"), row.get("metric_key"), row.get("target"), row.get("valid_from"),
            row.get("valid_to"), row.get("justification"), row.get("dimension_key"), row.get("dimension_label"),
            row.get("id"), row.get("inserted_by"), _to_datetime(row.get("inserted_at")),
        ])
    ends["targets"] = _write_simple_data(
        wb,
        "DADOS_METAS",
        ["KPI", "Metrica", "Meta", "Vigencia inicial", "Vigencia final", "Justificativa", "Dimensao", "Rotulo dimensao", "ID", "Inserido por", "Inserido em"],
        target_rows,
        "tblDmV3MetasRaw",
    )

    sync_rows = []
    for row in payload["sync_runs"]:
        warnings = row.get("warnings") or []
        sync_rows.append([
            row.get("id"), row.get("source_name") or row.get("source_type"), row.get("status"),
            row.get("cohorts_detected"), row.get("cohorts_created"), row.get("cohorts_updated"),
            row.get("students_detected"), row.get("students_created"), row.get("students_updated"),
            row.get("students_unchanged"), row.get("students_not_seen"), " | ".join(map(str, warnings)),
            _to_datetime(row.get("completed_at")), _to_datetime(row.get("started_at")), row.get("inserted_by"),
        ])
    ends["sync"] = _write_simple_data(
        wb,
        "DADOS_SEI",
        ["Execucao", "Origem", "Status", "Turmas detectadas", "Turmas criadas", "Turmas atualizadas", "Alunos detectados", "Alunos criados", "Alunos atualizados", "Alunos inalterados", "Alunos nao vistos", "Observacoes", "Concluida em", "Iniciada em", "Inserido por"],
        sync_rows,
        "tblDmV3SeiRaw",
    )

    meta_rows = [[row["period"], row["indicator_code"], row["metric_key"], row["target"], row["source_valid_from"], row["source_valid_to"], row["justification"]] for row in payload["effective_targets"]]
    ends["effective_targets"] = _write_simple_data(
        wb,
        "META_EFETIVA",
        ["Periodo", "KPI", "Metrica", "Meta efetiva", "Origem vigencia inicial", "Origem vigencia final", "Justificativa"],
        meta_rows,
        "tblDmV3MetaEfetiva",
    )
    return ends


def _write_lists(wb: Workbook, payload: dict[str, Any]) -> None:
    ws = wb.create_sheet("LISTAS")
    _setup(ws, zoom=70)
    columns = {
        1: ["Areas", "(todas)", *DM_AREAS.keys()],
        2: ["Turmas", "(todas)", *payload["cohort_options"]],
        3: ["Comparacao", "(nenhuma)", *payload["cohort_options"]],
        4: ["Janela", *WINDOW_OPTIONS],
        5: ["Status aluno", *STUDENT_STATUS_OPTIONS],
        6: ["KPI matriz", *MATRIX_OPTIONS],
    }
    for col, values in columns.items():
        for row, value in enumerate(values, 1):
            ws.cell(row, col, value)
            _body(ws.cell(row, col), imported=True)
    _auto_width(ws)


def _write_parameters(wb: Workbook, payload: dict[str, Any]) -> None:
    ws = wb.create_sheet("PARAMETROS")
    _setup(ws, zoom=95)
    _title(ws, "PARAMETROS | DM", "Os filtros do site apenas iniciam estes controles. Depois da exportacao, o proprio Excel assume o recorte analitico.", end_col=8)
    _section(ws, 4, "CONTROLES INTERATIVOS", end_col=8)
    rows = [
        (6, "Area em foco", payload["initial"]["area"]),
        (7, "Turma em foco", payload["initial"]["cohort"]),
        (8, "Turma de comparacao", payload["initial"]["comparison"]),
        (9, "Data de corte", payload["initial"]["as_of"]),
        (10, "Janela de turmas", payload["initial"]["window"]),
        (11, "Status do aluno", payload["initial"]["student_status"]),
        (12, "KPI da matriz", payload["initial"]["matrix_kpi"]),
    ]
    for row, label, value in rows:
        ws.cell(row, 1, label)
        ws.cell(row, 2, value)
        ws.cell(row, 1).font = Font(name="Arial", size=9, bold=True, color=GRAY_600)
        ws.cell(row, 1).fill = PatternFill("solid", fgColor=GRAY_100)
        ws.cell(row, 2).font = Font(name="Arial", size=10, bold=True, color=INK)
        ws.cell(row, 2).fill = PatternFill("solid", fgColor=YELLOW_INPUT)
        ws.cell(row, 1).border = ws.cell(row, 2).border = Border(bottom=THIN)
    ws["B9"].number_format = DATE_FMT
    ws["A14"] = "Periodo de vigencia calculado"
    ws["B14"] = '=TEXT(P_DM_ASOF,"yyyy")&"-SEM"&IF(MONTH(P_DM_ASOF)<=6,1,2)'
    ws["A15"] = "Janela numerica"
    ws["B15"] = '=IF(P_DM_WINDOW="Todo historico",999999,P_DM_WINDOW)'
    for r in (14, 15):
        ws.cell(r, 1).font = Font(name="Arial", size=8, color=GRAY_600)
        ws.cell(r, 2).font = Font(name="Arial", size=8, bold=True, color=PURPLE)
        ws.cell(r, 2).fill = PatternFill("solid", fgColor=GRAY_50)
    _section(ws, 18, "LEITURA DOS CONTROLES", end_col=8)
    notes = [
        "Area e turma alteram cards, graficos e tabelas executivas. Se uma turma especifica for escolhida, ela prevalece sobre a janela.",
        "Status do aluno e um filtro auxiliar: ele altera a contagem 'Alunos no status em foco', mas nao redefine os KPIs oficiais DM-01/DM-02.",
        "Data de corte controla prazos, defesas consideradas e a vigencia das metas. O status atual do vinculo nao e reconstruido historicamente quando nao existe um evento datado suficiente.",
        "Metas, planos e dados cadastrais continuam sendo alterados no Data UNIVC e aparecem no Excel na proxima exportacao.",
    ]
    for i, text in enumerate(notes, 19):
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=8)
        ws.cell(i, 1, text)
        ws.cell(i, 1).font = Font(name="Arial", size=9, color=INK)
        ws.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[i].height = 28
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 42

    validations = [
        ("B6", f"LISTAS!$A$2:$A${2 + len(DM_AREAS)}"),
        ("B7", f"LISTAS!$B$2:$B${2 + len(payload['cohort_options'])}"),
        ("B8", f"LISTAS!$C$2:$C${2 + len(payload['cohort_options'])}"),
        ("B10", f"LISTAS!$D$2:$D${1 + len(WINDOW_OPTIONS)}"),
        ("B11", f"LISTAS!$E$2:$E${1 + len(STUDENT_STATUS_OPTIONS)}"),
        ("B12", f"LISTAS!$F$2:$F${1 + len(MATRIX_OPTIONS)}"),
    ]
    for cell, formula in validations:
        dv = DataValidation(type="list", formula1=formula, allow_blank=False)
        dv.error = "Selecione um valor da lista."
        dv.errorTitle = "Parametro invalido"
        ws.add_data_validation(dv)
        dv.add(ws[cell])

    _named(wb, "P_DM_AREA", "'PARAMETROS'!$B$6")
    _named(wb, "P_DM_COHORT", "'PARAMETROS'!$B$7")
    _named(wb, "P_DM_COMP", "'PARAMETROS'!$B$8")
    _named(wb, "P_DM_ASOF", "'PARAMETROS'!$B$9")
    _named(wb, "P_DM_WINDOW", "'PARAMETROS'!$B$10")
    _named(wb, "P_DM_STATUS", "'PARAMETROS'!$B$11")
    _named(wb, "P_DM_MATRIX", "'PARAMETROS'!$B$12")
    _named(wb, "P_DM_PERIOD", "'PARAMETROS'!$B$14")
    _named(wb, "P_DM_WINDOW_N", "'PARAMETROS'!$B$15")


def _range(sheet: str, col: str, end: int) -> str:
    return f"'{sheet}'!${col}$2:${col}${end}"


def _write_calc(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("CALC")
    _setup(ws, freeze="A2", zoom=65)
    headers = [
        "Area", "Nome area", "Cohort ID", "Turma", "Chave", "Abertura", "Vagas", "Status turma", "Rank area", "Rank global", "No recorte",
        "Membros", "Ativos", "Titulados", "Desligados", "Ocupacao", "Evasao", "Ingressos confirmados", "Defesas ate corte", "Media defesa", "Mediana defesa",
        "Defesas <=24m", "Risco >18m", "Risco >24m", "Risco >30m", "Ultima defesa", "Alunos no status em foco",
        "Meta DM-01", "Status DM-01", "Meta DM-02", "Status DM-02", "Valor matriz", "Unidade matriz", "Meta matriz", "Status matriz",
        "Ingressos provisorios", "Ingressos pendentes", "Reconhecidos SEI", "Datas consultadas", "Defesas confirmadas SEI",
        "Chart DM01", "Chart Meta01", "Chart DM02", "Chart Meta02", "Chart OnTime", "Chart Risco30",
    ]
    for c, label in enumerate(headers, 1):
        ws.cell(1, c, label)
        _header(ws.cell(1, c))

    s_end = ends["students"]
    t_end = ends["effective_targets"]
    cid = _range("DADOS_ALUNOS", "C", s_end)
    entry = _range("DADOS_ALUNOS", "H", s_end)
    defense = _range("DADOS_ALUNOS", "J", s_end)
    status = _range("DADOS_ALUNOS", "L", s_end)
    provisional = _range("DADOS_ALUNOS", "P", s_end)
    source = _range("DADOS_ALUNOS", "Q", s_end)
    last_seen = _range("DADOS_ALUNOS", "S", s_end)
    last_dates = _range("DADOS_ALUNOS", "T", s_end)
    duration = _range("DADOS_ALUNOS", "W", s_end)
    on_time = _range("DADOS_ALUNOS", "X", s_end)
    risk18 = _range("DADOS_ALUNOS", "Y", s_end)
    risk24 = _range("DADOS_ALUNOS", "Z", s_end)
    risk30 = _range("DADOS_ALUNOS", "AA", s_end)

    for r, cohort in enumerate(payload["cohorts"], 2):
        row_id = int(cohort.get("id") or 0)
        values = [
            cohort.get("area_code"), cohort.get("area_name") or DM_AREAS.get(str(cohort.get("area_code") or ""), ""),
            row_id, int(cohort.get("cohort_number") or 0), _cohort_key(cohort), _to_date(cohort.get("opening_date")), cohort.get("vacancies_authorized"),
            cohort.get("status"), payload["area_rev_rank"].get(row_id), payload["global_rev_rank"].get(row_id),
        ]
        for c, value in enumerate(values, 1):
            ws.cell(r, c, value)
            _body(ws.cell(r, c), imported=True)
        ws.cell(r, 6).number_format = DATE_FMT
        ws.cell(r, 11, f'=IF(P_DM_COHORT<>"(todas)",--(E{r}=P_DM_COHORT),--AND(OR(P_DM_AREA="(todas)",A{r}=P_DM_AREA),IF(P_DM_AREA="(todas)",J{r},I{r})<=P_DM_WINDOW_N))')
        ws.cell(r, 12, f'=COUNTIFS({cid},C{r})')
        ws.cell(r, 13, f'=COUNTIFS({cid},C{r},{status},"Ativo")')
        ws.cell(r, 14, f'=COUNTIFS({cid},C{r},{status},"Titulado")')
        ws.cell(r, 15, f'=COUNTIFS({cid},C{r},{status},"Desligado")')
        ws.cell(r, 16, f'=IFERROR(L{r}/G{r},"")')
        ws.cell(r, 17, f'=IFERROR(O{r}/L{r},"")')
        ws.cell(r, 18, f'=COUNTIFS({cid},C{r},{entry},"<>",{provisional},"Nao",{entry},"<="&P_DM_ASOF)')
        ws.cell(r, 19, f'=COUNTIFS({cid},C{r},{entry},"<>",{provisional},"Nao",{defense},"<>",{defense},"<="&P_DM_ASOF)')
        ws.cell(r, 20, f'=IFERROR(AVERAGEIFS({duration},{cid},C{r},{defense},"<>",{defense},"<="&P_DM_ASOF),"")')
        # AGGREGATE(12) is MEDIAN and ignores divide-by-zero errors generated by nonmatching rows.
        ws.cell(r, 21, f'=IFERROR(AGGREGATE(12,6,{duration}/(({cid}=C{r})*({defense}<>"")*({defense}<=P_DM_ASOF))),"")')
        ws.cell(r, 22, f'=IFERROR(SUMIFS({on_time},{cid},C{r})/S{r},"")')
        ws.cell(r, 23, f'=SUMIFS({risk18},{cid},C{r})')
        ws.cell(r, 24, f'=SUMIFS({risk24},{cid},C{r})')
        ws.cell(r, 25, f'=SUMIFS({risk30},{cid},C{r})')
        ws.cell(r, 26, f'=IF(S{r}=0,"",MAXIFS({defense},{cid},C{r},{defense},"<="&P_DM_ASOF))')
        ws.cell(r, 27, f'=IF(P_DM_STATUS="(todos)",L{r},COUNTIFS({cid},C{r},{status},P_DM_STATUS))')
        ws.cell(r, 28, f'=IFERROR(SUMIFS(\'META_EFETIVA\'!$D$2:$D${t_end},\'META_EFETIVA\'!$A$2:$A${t_end},P_DM_PERIOD,\'META_EFETIVA\'!$B$2:$B${t_end},"DM-01",\'META_EFETIVA\'!$C$2:$C${t_end},"cohort_members"),"")')
        ws.cell(r, 29, f'=IF(OR(H{r}="Planejada",H{r}="Aberta"),"Em formacao",IF(L{r}=0,"Sem dados",IF(AB{r}="","Sem meta",IF(L{r}>=AB{r},"Dentro da meta","Fora da meta"))))')
        ws.cell(r, 30, f'=IFERROR(SUMIFS(\'META_EFETIVA\'!$D$2:$D${t_end},\'META_EFETIVA\'!$A$2:$A${t_end},P_DM_PERIOD,\'META_EFETIVA\'!$B$2:$B${t_end},"DM-02",\'META_EFETIVA\'!$C$2:$C${t_end},"average_months_to_defense"),"")')
        ws.cell(r, 31, f'=IF(L{r}=0,"Sem dados",IF(R{r}=0,"Dados pendentes",IF(OR(H{r}="Planejada",H{r}="Aberta"),"Em acompanhamento",IF(T{r}="","Em acompanhamento",IF(AD{r}="","Sem meta",IF(T{r}<=AD{r},"Dentro da meta","Fora da meta"))))))')
        ws.cell(r, 32, f'=IF(P_DM_MATRIX="DM-01 | Membros por turma",L{r},IF(P_DM_MATRIX="Ocupacao | Vagas",P{r},IF(P_DM_MATRIX="DM-02 | Tempo medio ate defesa",T{r},IF(P_DM_MATRIX="Defesas | Ate 24 meses",V{r},Y{r}))))')
        ws.cell(r, 33, f'=IF(P_DM_MATRIX="DM-01 | Membros por turma","alunos",IF(P_DM_MATRIX="Ocupacao | Vagas","%",IF(P_DM_MATRIX="DM-02 | Tempo medio ate defesa","meses",IF(P_DM_MATRIX="Defesas | Ate 24 meses","%","alunos"))))')
        ws.cell(r, 34, f'=IF(P_DM_MATRIX="DM-01 | Membros por turma",AB{r},IF(P_DM_MATRIX="DM-02 | Tempo medio ate defesa",AD{r},IF(P_DM_MATRIX="Risco | >30m sem defesa",0,"")))')
        ws.cell(r, 35, f'=IF(P_DM_MATRIX="DM-01 | Membros por turma",AC{r},IF(P_DM_MATRIX="DM-02 | Tempo medio ate defesa",AE{r},IF(P_DM_MATRIX="Risco | >30m sem defesa",IF(Y{r}=0,"Sem risco","Atencao"),"Analitico")))')
        ws.cell(r, 36, f'=COUNTIFS({cid},C{r},{entry},"<>",{provisional},"Sim")')
        ws.cell(r, 37, f'=COUNTIFS({cid},C{r},{entry},"")')
        ws.cell(r, 38, f'=COUNTIFS({cid},C{r},{source},"*SEI*")+COUNTIFS({cid},C{r},{last_seen},"<>")-COUNTIFS({cid},C{r},{source},"*SEI*",{last_seen},"<>")')
        ws.cell(r, 39, f'=COUNTIFS({cid},C{r},{last_dates},"<>")')
        ws.cell(r, 40, f'=COUNTIFS({cid},C{r},{defense},"<>",{last_dates},"<>",{status},"Titulado")')
        ws.cell(r, 41, f'=IF(K{r}=1,L{r},NA())')
        ws.cell(r, 42, f'=IF(K{r}=1,AB{r},NA())')
        ws.cell(r, 43, f'=IF(K{r}=1,T{r},NA())')
        ws.cell(r, 44, f'=IF(K{r}=1,AD{r},NA())')
        ws.cell(r, 45, f'=IF(K{r}=1,V{r},NA())')
        ws.cell(r, 46, f'=IF(K{r}=1,Y{r},NA())')
        for c in range(11, 47):
            _body(ws.cell(r, c), formula=True)
        for c in (16, 17, 22, 45):
            ws.cell(r, c).number_format = PCT_FMT
        for c in (20, 21, 30, 43, 44):
            ws.cell(r, c).number_format = DECIMAL_FMT
        ws.cell(r, 26).number_format = DATE_FMT
    ends["calc"] = max(2, len(payload["cohorts"]) + 1)
    _add_table(ws, "tblDmV3Calc", 1, ends["calc"], len(headers))
    _auto_width(ws, max_width=24)


def _kpi_card(ws, c1: int, c2: int, row: int, label: str, formula: str, *, fmt: str = "General", fill: str = GREEN_LIGHT, note: str = "") -> None:
    for rr in range(row, row + 4):
        for cc in range(c1, c2 + 1):
            ws.cell(rr, cc).fill = PatternFill("solid", fgColor=fill)
            ws.cell(rr, cc).border = Border(left=THIN if cc == c1 else Side(style=None), right=THIN if cc == c2 else Side(style=None), top=THIN if rr == row else Side(style=None), bottom=THIN if rr == row + 3 else Side(style=None))
    ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    ws.merge_cells(start_row=row + 1, start_column=c1, end_row=row + 2, end_column=c2)
    ws.merge_cells(start_row=row + 3, start_column=c1, end_row=row + 3, end_column=c2)
    ws.cell(row, c1, label)
    ws.cell(row, c1).font = Font(name="Arial", size=8, bold=True, color=GRAY_600)
    ws.cell(row, c1).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.cell(row + 1, c1, formula)
    ws.cell(row + 1, c1).font = Font(name="Arial", size=15, bold=True, color=GREEN_DARK)
    ws.cell(row + 1, c1).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row + 1, c1).number_format = fmt
    ws.cell(row + 3, c1, note)
    ws.cell(row + 3, c1).font = Font(name="Arial", size=7, color=GRAY_600)
    ws.cell(row + 3, c1).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _chart_defaults(chart, title: str, y_title: str, *, width: float = 13.5, height: float = 7.2) -> None:
    chart.title = title
    chart.y_axis.title = y_title
    chart.width = width
    chart.height = height
    chart.legend.position = "b"
    chart.style = 13
    chart.display_blanks = "gap"
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    chart.dataLabels.showLegendKey = False
    chart.dataLabels.showCatName = False
    chart.dataLabels.showSerName = False


def _style_series(chart, colors: list[str], *, line: bool = False) -> None:
    for series, color in zip(chart.series, colors):
        if line:
            series.graphicalProperties.line.solidFill = color
            series.graphicalProperties.line.width = 22000
            series.marker.symbol = "circle"
            series.marker.size = 6
            series.marker.graphicalProperties.solidFill = color
            series.marker.graphicalProperties.line.solidFill = color
        else:
            series.graphicalProperties.solidFill = color
            series.graphicalProperties.line.solidFill = color


def _write_readme(wb: Workbook, payload: dict[str, Any]) -> None:
    ws = wb.create_sheet("LEIA-ME")
    _setup(ws, zoom=95)
    _title(ws, "EXCEL INTERATIVO | DM", "Diretoria de Mestrado | segunda interface de consulta do Data UNIVC para usuarios que trabalham melhor no Excel.", end_col=10)
    _section(ws, 4, "COMO USAR", end_col=10)
    items = [
        ("PARAMETROS", "Troque area, turma, comparacao, data de corte, janela, status auxiliar e KPI da matriz."),
        ("PAINEL", "Leitura executiva reativa dos principais indicadores e composicao do recorte."),
        ("DM-01 EVOLUCAO", "Membros por turma, composicao, ocupacao, meta e situacao."),
        ("DM-02 DEFESAS", "Tempo ate defesa, percentual ate 24 meses e alertas de prazo."),
        ("TURMAS / ALUNOS E DEFESAS", "Bases operacionais completas, com filtros nativos do Excel."),
        ("MATRIZ", "Troque o KPI em PARAMETROS e compare as turmas numa unica leitura."),
        ("METAS E PLANOS / INTEGRACAO SEI", "Governanca oficial exportada do banco do Data UNIVC."),
    ]
    for c, h in enumerate(["Aba", "Finalidade"], 1):
        ws.cell(5, c, h)
        _header(ws.cell(5, c))
    for r, (name, purpose) in enumerate(items, 6):
        ws.cell(r, 1, name)
        ws.cell(r, 2, purpose)
        _body(ws.cell(r, 1))
        _body(ws.cell(r, 2), wrap=True)
        ws.cell(r, 1).font = Font(name="Arial", size=9, bold=True, color=GREEN_DARK)
        ws.row_dimensions[r].height = 28
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 92
    _section(ws, 15, "CONTRATO DE USO", end_col=10)
    rules = [
        "O Data UNIVC continua sendo a fonte oficial. O Excel e uma interface de consulta: alteracoes cadastrais, metas e planos devem ser feitas no sistema.",
        "A exportacao V3 leva todo o historico autorizado da DM. Os filtros do site somente preenchem o estado inicial de PARAMETROS.",
        "DM-01 usa numero absoluto de membros por turma. DM-02 usa somente ingresso individual confirmado e defesa registrada.",
        "A Data de corte afeta prazos, defesas consideradas e vigencia das metas. Ela nao inventa um historico de status quando os eventos necessarios nao existem na base.",
        "ALUNOS E DEFESAS contem dados administrativos individuais e deve respeitar o mesmo escopo de acesso da Diretoria de Mestrado.",
    ]
    for r, text in enumerate(rules, 16):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        ws.cell(r, 1, text)
        ws.cell(r, 1).font = Font(name="Arial", size=9, color=INK)
        ws.cell(r, 1).alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(r, 1).fill = PatternFill("solid", fgColor=GREEN_LIGHT if r % 2 == 0 else WHITE)
        ws.row_dimensions[r].height = 30
    ws["A23"] = f"Gerado pelo Data UNIVC {payload['app_version']} em {payload['generated_at']}"
    ws["A23"].font = Font(name="Arial", size=8, color=GRAY_600)


def _write_panel(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("PAINEL")
    _setup(ws, zoom=85)
    _title(ws, "PAINEL DE GESTAO | DM", "Indicadores por turma com filtros controlados em PARAMETROS. DM-01 e DM-02 mantem suas regras oficiais.", end_col=14)
    calc_end = ends["calc"]
    ws["A4"] = "Area"
    ws["B4"] = "=P_DM_AREA"
    ws["D4"] = "Turma"
    ws["E4"] = "=P_DM_COHORT"
    ws["G4"] = "Corte"
    ws["H4"] = "=P_DM_ASOF"
    ws["H4"].number_format = DATE_FMT
    ws["J4"] = "Janela"
    ws["K4"] = "=P_DM_WINDOW"
    for c in ("A4", "D4", "G4", "J4"):
        ws[c].font = Font(name="Arial", size=8, bold=True, color=GRAY_600)
    for c in ("B4", "E4", "H4", "K4"):
        ws[c].font = Font(name="Arial", size=9, bold=True, color=INK)
        ws[c].fill = PatternFill("solid", fgColor=YELLOW_INPUT)

    visible = f"CALC!$K$2:$K${calc_end}"
    _kpi_card(ws, 1, 2, 6, "Turmas", f'=SUM({visible})', fmt=INT_FMT, note="no recorte atual")
    _kpi_card(ws, 3, 4, 6, "Membros", f'=SUMIFS(CALC!$L$2:$L${calc_end},{visible},1)', fmt=INT_FMT, fill=GREEN_PALE, note="DM-01 | todos os status")
    _kpi_card(ws, 5, 6, 6, "Ativos", f'=SUMIFS(CALC!$M$2:$M${calc_end},{visible},1)', fmt=INT_FMT, fill=GRAY_50)
    _kpi_card(ws, 7, 8, 6, "Titulados", f'=SUMIFS(CALC!$N$2:$N${calc_end},{visible},1)', fmt=INT_FMT, fill=GREEN_PALE)
    _kpi_card(ws, 9, 10, 6, "Desligados", f'=SUMIFS(CALC!$O$2:$O${calc_end},{visible},1)', fmt=INT_FMT, fill=YELLOW_WARN)
    _kpi_card(ws, 11, 12, 6, "Ocupacao", f'=IFERROR(SUMIFS(CALC!$L$2:$L${calc_end},{visible},1)/SUMIFS(CALC!$G$2:$G${calc_end},{visible},1),"")', fmt=PCT_FMT, fill=GREEN_PALE)
    _kpi_card(ws, 13, 14, 6, "Tempo medio defesa", f'=IFERROR(SUMPRODUCT(({visible}=1),CALC!$T$2:$T${calc_end},CALC!$S$2:$S${calc_end})/SUMIFS(CALC!$S$2:$S${calc_end},{visible},1),"")', fmt=DECIMAL_FMT, fill=GREEN_PALE, note="meses | ingresso confirmado")
    _kpi_card(ws, 1, 2, 11, "Alunos no status em foco", f'=SUMIFS(CALC!$AA$2:$AA${calc_end},{visible},1)', fmt=INT_FMT, fill=GRAY_50, note="filtro auxiliar de PARAMETROS")
    _kpi_card(ws, 3, 4, 11, "Defesas ate corte", f'=SUMIFS(CALC!$S$2:$S${calc_end},{visible},1)', fmt=INT_FMT, fill=GREEN_PALE)
    _kpi_card(ws, 5, 6, 11, "Defesas ate 24m", f'=IFERROR(SUMPRODUCT(({visible}=1),CALC!$V$2:$V${calc_end},CALC!$S$2:$S${calc_end})/SUMIFS(CALC!$S$2:$S${calc_end},{visible},1),"")', fmt=PCT_FMT, fill=GREEN_PALE)
    _kpi_card(ws, 7, 8, 11, "Risco >18m", f'=SUMIFS(CALC!$W$2:$W${calc_end},{visible},1)', fmt=INT_FMT, fill=YELLOW_WARN, note="sem qualificacao")
    _kpi_card(ws, 9, 10, 11, "Risco >24m", f'=SUMIFS(CALC!$X$2:$X${calc_end},{visible},1)', fmt=INT_FMT, fill=YELLOW_WARN, note="sem defesa marcada")
    _kpi_card(ws, 11, 12, 11, "Risco >30m", f'=SUMIFS(CALC!$Y$2:$Y${calc_end},{visible},1)', fmt=INT_FMT, fill=RED_LIGHT, note="sem defesa")
    _kpi_card(ws, 13, 14, 11, "Meta DM-02", f'=IFERROR(INDEX(CALC!$AD$2:$AD${calc_end},MATCH(1,{visible},0)),"")', fmt=DECIMAL_FMT, fill=GRAY_50, note="meses | vigencia do corte")

    _section(ws, 17, "EVOLUCAO POR TURMA", end_col=14)
    calc = wb["CALC"]
    if calc_end >= 2:
        chart1 = BarChart()
        chart1.type = "col"
        chart1.add_data(Reference(calc, min_col=41, max_col=42, min_row=1, max_row=calc_end), titles_from_data=True)
        chart1.set_categories(Reference(calc, min_col=5, min_row=2, max_row=calc_end))
        _chart_defaults(chart1, "DM-01 | membros x meta", "Membros", width=14, height=7.5)
        _style_series(chart1, [GREEN, GRAY_600])
        ws.add_chart(chart1, "A19")

        chart2 = LineChart()
        chart2.add_data(Reference(calc, min_col=43, max_col=44, min_row=1, max_row=calc_end), titles_from_data=True)
        chart2.set_categories(Reference(calc, min_col=5, min_row=2, max_row=calc_end))
        _chart_defaults(chart2, "DM-02 | tempo medio x meta", "Meses", width=14, height=7.5)
        _style_series(chart2, [TEAL, GRAY_600], line=True)
        ws.add_chart(chart2, "H19")

        chart3 = BarChart()
        chart3.type = "col"
        chart3.add_data(Reference(calc, min_col=46, min_row=1, max_row=calc_end), titles_from_data=True)
        chart3.set_categories(Reference(calc, min_col=5, min_row=2, max_row=calc_end))
        _chart_defaults(chart3, "Risco >30 meses sem defesa", "Alunos", width=14, height=7.5)
        _style_series(chart3, [RED])
        ws.add_chart(chart3, "A35")

    _section(ws, 51, "STATUS DOS INDICADORES OFICIAIS", end_col=14)
    headers = ["Turma", "DM-01", "Meta 01", "Situacao 01", "DM-02", "Meta 02", "Situacao 02", "No recorte"]
    for c, h in enumerate(headers, 1):
        ws.cell(52, c, h)
        _header(ws.cell(52, c))
    for out_r, calc_r in enumerate(range(2, calc_end + 1), 53):
        formulas = [f"=CALC!E{calc_r}", f"=CALC!L{calc_r}", f"=CALC!AB{calc_r}", f"=CALC!AC{calc_r}", f"=CALC!T{calc_r}", f"=CALC!AD{calc_r}", f"=CALC!AE{calc_r}", f'=IF(CALC!K{calc_r}=1,"Sim","Nao")']
        for c, formula in enumerate(formulas, 1):
            ws.cell(out_r, c, formula)
            _body(ws.cell(out_r, c), formula=True)
        ws.cell(out_r, 5).number_format = DECIMAL_FMT
        ws.cell(out_r, 6).number_format = DECIMAL_FMT
    _auto_width(ws, max_width=26)


def _write_dm01(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("DM-01 EVOLUCAO")
    _setup(ws, freeze="A8", zoom=80)
    _title(ws, "DM-01 | EVOLUCAO DAS TURMAS", "Indicador oficial: numero absoluto de membros por turma. A janela/area/turma de PARAMETROS controla o grafico e a coluna No recorte.", end_col=12)
    calc = wb["CALC"]
    end = ends["calc"]
    if end >= 2:
        chart = BarChart()
        chart.type = "col"
        chart.add_data(Reference(calc, min_col=41, max_col=42, min_row=1, max_row=end), titles_from_data=True)
        chart.set_categories(Reference(calc, min_col=5, min_row=2, max_row=end))
        _chart_defaults(chart, "Membros por turma x meta", "Membros", width=19, height=8)
        _style_series(chart, [GREEN, GRAY_600])
        ws.add_chart(chart, "A4")
    _section(ws, 21, "DETALHAMENTO", end_col=12)
    headers = ["Area", "Turma", "Abertura", "Membros", "Ativos", "Titulados", "Desligados", "Vagas", "Ocupacao", "Meta", "Situacao", "No recorte"]
    for c, h in enumerate(headers, 1):
        ws.cell(22, c, h)
        _header(ws.cell(22, c))
    for out_r, calc_r in enumerate(range(2, end + 1), 23):
        formulas = [
            f"=CALC!B{calc_r}", f"=CALC!E{calc_r}", f"=CALC!F{calc_r}", f"=CALC!L{calc_r}", f"=CALC!M{calc_r}", f"=CALC!N{calc_r}",
            f"=CALC!O{calc_r}", f"=CALC!G{calc_r}", f"=CALC!P{calc_r}", f"=CALC!AB{calc_r}", f"=CALC!AC{calc_r}", f'=IF(CALC!K{calc_r}=1,"Sim","Nao")',
        ]
        for c, formula in enumerate(formulas, 1):
            ws.cell(out_r, c, formula)
            _body(ws.cell(out_r, c), formula=True)
        ws.cell(out_r, 3).number_format = DATE_FMT
        ws.cell(out_r, 9).number_format = PCT_FMT
    _add_table(ws, "tblDmV3Dm01", 22, 22 + max(0, end - 1), 12)
    _auto_width(ws, max_width=28)


def _write_dm02(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("DM-02 DEFESAS")
    _setup(ws, freeze="A8", zoom=78)
    _title(ws, "DM-02 | DEFESAS E PRAZOS", "Somente ingresso individual confirmado entra no tempo ate defesa. A Data de corte exclui defesas posteriores e recalcula alertas.", end_col=13)
    calc = wb["CALC"]
    end = ends["calc"]
    if end >= 2:
        chart = LineChart()
        chart.add_data(Reference(calc, min_col=43, max_col=44, min_row=1, max_row=end), titles_from_data=True)
        chart.set_categories(Reference(calc, min_col=5, min_row=2, max_row=end))
        _chart_defaults(chart, "Tempo medio ate defesa x meta", "Meses", width=19, height=8)
        _style_series(chart, [TEAL, GRAY_600], line=True)
        ws.add_chart(chart, "A4")
    _section(ws, 21, "DETALHAMENTO", end_col=13)
    headers = ["Area", "Turma", "Ingressos confirmados", "Defesas", "Media", "Mediana", "Ate 24m", ">18m sem qualificacao", ">24m sem defesa marcada", ">30m sem defesa", "Meta", "Situacao", "No recorte"]
    for c, h in enumerate(headers, 1):
        ws.cell(22, c, h)
        _header(ws.cell(22, c))
    for out_r, calc_r in enumerate(range(2, end + 1), 23):
        formulas = [
            f"=CALC!B{calc_r}", f"=CALC!E{calc_r}", f"=CALC!R{calc_r}", f"=CALC!S{calc_r}", f"=CALC!T{calc_r}", f"=CALC!U{calc_r}", f"=CALC!V{calc_r}",
            f"=CALC!W{calc_r}", f"=CALC!X{calc_r}", f"=CALC!Y{calc_r}", f"=CALC!AD{calc_r}", f"=CALC!AE{calc_r}", f'=IF(CALC!K{calc_r}=1,"Sim","Nao")',
        ]
        for c, formula in enumerate(formulas, 1):
            ws.cell(out_r, c, formula)
            _body(ws.cell(out_r, c), formula=True)
        for c in (5, 6, 11):
            ws.cell(out_r, c).number_format = DECIMAL_FMT
        ws.cell(out_r, 7).number_format = PCT_FMT
    _add_table(ws, "tblDmV3Dm02", 22, 22 + max(0, end - 1), 13)
    _auto_width(ws, max_width=30)


def _write_cohorts(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("TURMAS")
    _setup(ws, freeze="A5", zoom=78)
    _title(ws, "TURMAS | DM", "Base operacional completa da exportacao. Use os filtros nativos do Excel para pesquisas adicionais.", end_col=16)
    headers = ["Area", "Nome da area", "Turma", "Abertura", "Vagas", "Status", "Membros", "Ativos", "Titulados", "Desligados", "Ocupacao", "Origem", "Rotulo SEI", "Ultima leitura SEI", "Observacoes", "Chave"]
    for c, h in enumerate(headers, 1):
        ws.cell(4, c, h)
        _header(ws.cell(4, c))
    for out_r, calc_r in enumerate(range(2, ends["calc"] + 1), 5):
        cohort = payload["cohorts"][calc_r - 2]
        values = [
            f"=CALC!A{calc_r}", f"=CALC!B{calc_r}", f"=CALC!D{calc_r}", f"=CALC!F{calc_r}", f"=CALC!G{calc_r}", f"=CALC!H{calc_r}",
            f"=CALC!L{calc_r}", f"=CALC!M{calc_r}", f"=CALC!N{calc_r}", f"=CALC!O{calc_r}", f"=CALC!P{calc_r}",
            cohort.get("source_system"), cohort.get("sei_raw_label"), _to_datetime(cohort.get("last_seen_sei_at")), cohort.get("notes"), f"=CALC!E{calc_r}",
        ]
        for c, value in enumerate(values, 1):
            ws.cell(out_r, c, value)
            _body(ws.cell(out_r, c), imported=c in {12, 13, 14, 15}, formula=isinstance(value, str) and value.startswith("="), wrap=c in {2, 13, 15})
        ws.cell(out_r, 4).number_format = DATE_FMT
        ws.cell(out_r, 11).number_format = PCT_FMT
        ws.cell(out_r, 14).number_format = DATETIME_FMT
    _add_table(ws, "tblDmV3Turmas", 4, 4 + len(payload["cohorts"]), len(headers))
    _auto_width(ws, max_width=34)


def _write_students(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("ALUNOS E DEFESAS")
    _setup(ws, freeze="A5", zoom=70)
    _title(ws, "ALUNOS E DEFESAS | DM", "Trajetoria individual completa da base autorizada. Os campos calculados usam a Data de corte de PARAMETROS.", end_col=23)
    headers = [
        "Area", "Turma", "Matricula", "Aluno", "Ingresso", "Qualificacao", "Defesa", "Defesa marcada", "Status", "Saida", "Orientador", "Linha de pesquisa",
        "Meses ate defesa", "Defesa <=24m", "Risco >18m sem qualificacao", "Risco >24m sem defesa marcada", "Risco >30m sem defesa", "Qualidade do ingresso",
        "Origem", "Situacao SEI", "Ultima leitura SEI", "Ultima consulta de datas SEI", "Observacoes",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(4, c, h)
        _header(ws.cell(4, c))
    raw = wb["DADOS_ALUNOS"]
    for out_r, raw_r in enumerate(range(2, ends["students"] + 1), 5):
        mapping = [1, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 23, 24, 25, 26, 27, 21, 17, 18, 19, 20, 22]
        for c, source_col in enumerate(mapping, 1):
            ws.cell(out_r, c, f"='DADOS_ALUNOS'!{get_column_letter(source_col)}{raw_r}")
            _body(ws.cell(out_r, c), formula=True, wrap=c in {4, 11, 12, 18, 20, 23})
        for c in (5, 6, 7, 8, 10):
            ws.cell(out_r, c).number_format = DATE_FMT
        ws.cell(out_r, 13).number_format = DECIMAL_FMT
        for c in (21, 22):
            ws.cell(out_r, c).number_format = DATETIME_FMT
    _add_table(ws, "tblDmV3Alunos", 4, 4 + len(payload["students"]), len(headers))
    _auto_width(ws, max_width=34)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3


def _write_matrix(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("MATRIZ")
    _setup(ws, freeze="A10", zoom=85)
    _title(ws, "MATRIZ | TURMAS X INDICADOR", "Escolha o KPI em PARAMETROS. A matriz permite comparar rapidamente todas as turmas e destaca o recorte atual.", end_col=10)
    ws["A4"] = "KPI selecionado"
    ws["B4"] = "=P_DM_MATRIX"
    ws["A5"] = "Turma em foco"
    ws["B5"] = "=P_DM_COHORT"
    ws["D5"] = "Comparacao"
    ws["E5"] = "=P_DM_COMP"
    for c in ("A4", "A5", "D5"):
        ws[c].font = Font(name="Arial", size=8, bold=True, color=GRAY_600)
    for c in ("B4", "B5", "E5"):
        ws[c].fill = PatternFill("solid", fgColor=YELLOW_INPUT)
        ws[c].font = Font(name="Arial", size=9, bold=True, color=INK)
    end = ends["calc"]
    ws["A7"] = "Valor foco"
    ws["B7"] = f'=IF(P_DM_COHORT="(todas)","",IFERROR(INDEX(CALC!$AF$2:$AF${end},MATCH(P_DM_COHORT,CALC!$E$2:$E${end},0)),""))'
    ws["D7"] = "Valor comparacao"
    ws["E7"] = f'=IF(P_DM_COMP="(nenhuma)","",IFERROR(INDEX(CALC!$AF$2:$AF${end},MATCH(P_DM_COMP,CALC!$E$2:$E${end},0)),""))'
    ws["G7"] = "Variacao"
    ws["H7"] = '=IF(OR(B7="",E7=""),"",B7-E7)'
    ws["H7"].number_format = VAR_FMT
    headers = ["Area", "Turma", "Valor", "Unidade", "Meta", "Status", "Abertura", "Membros", "No recorte"]
    for c, h in enumerate(headers, 1):
        ws.cell(9, c, h)
        _header(ws.cell(9, c))
    for out_r, calc_r in enumerate(range(2, end + 1), 10):
        formulas = [
            f"=CALC!B{calc_r}", f"=CALC!E{calc_r}", f"=CALC!AF{calc_r}", f"=CALC!AG{calc_r}", f"=CALC!AH{calc_r}", f"=CALC!AI{calc_r}",
            f"=CALC!F{calc_r}", f"=CALC!L{calc_r}", f'=IF(CALC!K{calc_r}=1,"Sim","Nao")',
        ]
        for c, formula in enumerate(formulas, 1):
            ws.cell(out_r, c, formula)
            _body(ws.cell(out_r, c), formula=True)
        ws.cell(out_r, 3).number_format = DECIMAL_FMT
        ws.cell(out_r, 5).number_format = DECIMAL_FMT
        ws.cell(out_r, 7).number_format = DATE_FMT
    _add_table(ws, "tblDmV3Matriz", 9, 9 + len(payload["cohorts"]), len(headers))
    _auto_width(ws, max_width=32)


def _write_goals_actions(wb: Workbook, payload: dict[str, Any]) -> None:
    ws = wb.create_sheet("METAS E PLANOS")
    _setup(ws, freeze="A6", zoom=82)
    _title(ws, "METAS E PLANOS | DM", "Metas e planos sao exportados do banco oficial. Altere-os no Data UNIVC e gere uma nova exportacao para atualizar este arquivo.", end_col=11)
    _section(ws, 4, "METAS CADASTRADAS", end_col=11)
    headers = ["KPI", "Metrica", "Vigencia inicial", "Vigencia final", "Meta", "Justificativa", "Inserido por"]
    for c, h in enumerate(headers, 1):
        ws.cell(5, c, h)
        _header(ws.cell(5, c))
    r = 6
    for item in payload["targets"]:
        values = [item.get("indicator_code"), item.get("metric_key"), item.get("valid_from"), item.get("valid_to"), item.get("target"), item.get("justification"), item.get("inserted_by")]
        for c, value in enumerate(values, 1):
            ws.cell(r, c, value)
            _body(ws.cell(r, c), imported=True, wrap=c == 6)
        r += 1
    if r == 6:
        ws.cell(r, 1, "Nenhuma meta cadastrada.")
        _body(ws.cell(r, 1))
        r += 1
    r += 2
    _section(ws, r, "PLANOS DE ACAO", end_col=11)
    r += 1
    action_header = r
    headers2 = ["KPI", "Metrica", "Periodo", "Problema", "Causa provavel", "Acao corretiva", "Responsavel", "Prazo", "Status", "Evidencia"]
    for c, h in enumerate(headers2, 1):
        ws.cell(r, c, h)
        _header(ws.cell(r, c))
    r += 1
    for item in payload["actions"]:
        values = [item.get("indicator_code"), item.get("metric_key"), item.get("period"), item.get("problem"), item.get("probable_cause"), item.get("corrective_action"), item.get("responsible"), _to_date(item.get("due_date")), item.get("status"), item.get("evidence")]
        for c, value in enumerate(values, 1):
            ws.cell(r, c, value)
            _body(ws.cell(r, c), imported=True, wrap=c in {4, 5, 6, 10})
        ws.cell(r, 8).number_format = DATE_FMT
        r += 1
    if r == action_header + 1:
        ws.cell(r, 1, "Nenhum plano de acao cadastrado.")
        _body(ws.cell(r, 1))
    _auto_width(ws, max_width=38)


def _write_sei(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("INTEGRACAO SEI")
    _setup(ws, freeze="A14", zoom=80)
    _title(ws, "INTEGRACAO SEI | DM", "Qualidade da base no recorte atual e historico institucional das sincronizacoes registradas.", end_col=13)
    end = ends["calc"]
    visible = f"CALC!$K$2:$K${end}"
    _kpi_card(ws, 1, 2, 4, "Alunos no recorte", f'=SUMIFS(CALC!$L$2:$L${end},{visible},1)', fmt=INT_FMT)
    _kpi_card(ws, 3, 4, 4, "Ingressos confirmados", f'=SUMIFS(CALC!$R$2:$R${end},{visible},1)', fmt=INT_FMT, fill=GREEN_PALE)
    _kpi_card(ws, 5, 6, 4, "Ingressos pendentes", f'=SUMIFS(CALC!$AK$2:$AK${end},{visible},1)', fmt=INT_FMT, fill=YELLOW_WARN)
    _kpi_card(ws, 7, 8, 4, "Reconhecidos pelo SEI", f'=SUMIFS(CALC!$AL$2:$AL${end},{visible},1)', fmt=INT_FMT, fill=GRAY_50)
    _kpi_card(ws, 9, 10, 4, "Datas consultadas", f'=SUMIFS(CALC!$AM$2:$AM${end},{visible},1)', fmt=INT_FMT, fill=GRAY_50)
    _kpi_card(ws, 11, 13, 4, "Defesas confirmadas SEI", f'=SUMIFS(CALC!$AN$2:$AN${end},{visible},1)', fmt=INT_FMT, fill=GREEN_PALE)
    _section(ws, 10, "HISTORICO INSTITUCIONAL DE SINCRONIZACOES", end_col=13)
    headers = ["Execucao", "Origem", "Status", "Turmas detectadas", "Turmas criadas", "Turmas atualizadas", "Alunos detectados", "Alunos criados", "Alunos atualizados", "Alunos inalterados", "Alunos nao vistos", "Observacoes", "Concluida em"]
    for c, h in enumerate(headers, 1):
        ws.cell(11, c, h)
        _header(ws.cell(11, c))
    for out_r, raw_r in enumerate(range(2, ends["sync"] + 1), 12):
        mapping = list(range(1, 14))
        for c, source_col in enumerate(mapping, 1):
            ws.cell(out_r, c, f"='DADOS_SEI'!{get_column_letter(source_col)}{raw_r}")
            _body(ws.cell(out_r, c), formula=True, wrap=c in {2, 12})
        ws.cell(out_r, 13).number_format = DATETIME_FMT
    if payload["sync_runs"]:
        _add_table(ws, "tblDmV3Sei", 11, 11 + len(payload["sync_runs"]), 13)
    _auto_width(ws, max_width=34)


def _write_quality(wb: Workbook, payload: dict[str, Any], ends: dict[str, int]) -> None:
    ws = wb.create_sheet("QUALIDADE E GOVERNANCA")
    _setup(ws, zoom=88)
    _title(ws, "QUALIDADE E GOVERNANCA", "Validacoes para interpretar a base e os indicadores da DM antes de tomar decisao.", end_col=10)
    _section(ws, 4, "VALIDACOES AUTOMATICAS DA BASE", end_col=10)
    end = ends["students"]
    cohort_end = ends["cohorts"]
    checks = [
        ("Titulados sem defesa", f'=COUNTIFS(\'DADOS_ALUNOS\'!$L$2:$L${end},"Titulado",\'DADOS_ALUNOS\'!$J$2:$J${end},"")', "Defesa registrada e o marco ativo de titulacao."),
        ("Ativos com defesa registrada", f'=COUNTIFS(\'DADOS_ALUNOS\'!$L$2:$L${end},"Ativo",\'DADOS_ALUNOS\'!$J$2:$J${end},"<>")', "Um aluno com defesa deve estar Titulado."),
        ("Defesa anterior ao ingresso", f'=SUMPRODUCT(--(\'DADOS_ALUNOS\'!$H$2:$H${end}<>""),--(\'DADOS_ALUNOS\'!$J$2:$J${end}<>""),--(\'DADOS_ALUNOS\'!$J$2:$J${end}<\'DADOS_ALUNOS\'!$H$2:$H${end}))', "A defesa nao pode preceder o ingresso."),
        ("Defesa anterior a qualificacao", f'=SUMPRODUCT(--(\'DADOS_ALUNOS\'!$I$2:$I${end}<>""),--(\'DADOS_ALUNOS\'!$J$2:$J${end}<>""),--(\'DADOS_ALUNOS\'!$J$2:$J${end}<\'DADOS_ALUNOS\'!$I$2:$I${end}))', "Quando a qualificacao existe, ela deve preceder a defesa."),
        ("Ingressos pendentes", f'=COUNTIFS(\'DADOS_ALUNOS\'!$H$2:$H${end},"")', "Sem ingresso confirmado, o aluno nao entra no tempo oficial do DM-02."),
        ("Ingressos provisorios", f'=COUNTIFS(\'DADOS_ALUNOS\'!$P$2:$P${end},"Sim")', "Ingressos provisorios ficam fora do tempo oficial do DM-02."),
        ("Alunos ativos sem orientador", f'=COUNTIFS(\'DADOS_ALUNOS\'!$L$2:$L${end},"Ativo",\'DADOS_ALUNOS\'!$N$2:$N${end},"")', "Revisar vinculo de orientacao."),
        ("Turmas sem vagas definidas", f'=COUNTIFS(\'DADOS_TURMAS\'!$H$2:$H${cohort_end},"")', "Sem vagas, a ocupacao da turma nao pode ser calculada."),
        ("Alunos nunca consultados em datas SEI", f'=COUNTIFS(\'DADOS_ALUNOS\'!$T$2:$T${end},"")', "Indica registros ainda sem consulta individual de inicio/defesa."),
    ]
    for c, h in enumerate(["Controle", "Resultado", "Leitura"], 1):
        ws.cell(5, c, h)
        _header(ws.cell(5, c))
    for r, (label, formula, note) in enumerate(checks, 6):
        ws.cell(r, 1, label)
        ws.cell(r, 2, formula)
        ws.cell(r, 3, note)
        _body(ws.cell(r, 1))
        _body(ws.cell(r, 2), formula=True)
        _body(ws.cell(r, 3), wrap=True)
        ws.cell(r, 2).number_format = INT_FMT
        ws.cell(r, 2).fill = PatternFill("solid", fgColor=GREEN_PALE)
        ws.conditional_formatting.add(f"B{r}", CellIsRule(operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor=RED_LIGHT)))
    _section(ws, 17, "PARAMETROS ATUAIS", end_col=10)
    diagnostics = [
        (18, "Area", "=P_DM_AREA"),
        (19, "Turma", "=P_DM_COHORT"),
        (20, "Comparacao", "=P_DM_COMP"),
        (21, "Data de corte", "=P_DM_ASOF"),
        (22, "Vigencia", "=P_DM_PERIOD"),
        (23, "Status auxiliar", "=P_DM_STATUS"),
        (24, "KPI matriz", "=P_DM_MATRIX"),
    ]
    for r, label, formula in diagnostics:
        ws.cell(r, 1, label)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        ws.cell(r, 2, formula)
        ws.cell(r, 1).font = Font(name="Arial", size=8, bold=True, color=GRAY_600)
        ws.cell(r, 2).font = Font(name="Arial", size=9, bold=True, color=INK)
        ws.cell(r, 2).fill = PatternFill("solid", fgColor=GRAY_100)
    ws["B21"].number_format = DATE_FMT
    _section(ws, 27, "REGRAS DE GOVERNANCA", end_col=10)
    rules = [
        "Defesa registrada confirma Titulado. O dominio ativo da DM usa somente Ativo, Titulado e Desligado.",
        "DM-01 mede membros por turma; o filtro de status do aluno nao altera a comparacao oficial com a meta.",
        "DM-02 usa somente ingresso individual confirmado. A abertura da turma nao substitui a data individual de ingresso.",
        "Data de corte recalcula prazos e exclui defesas futuras, mas nao deve ser interpretada como reconstrucao completa de status historico sem eventos datados suficientes.",
        "O historico SEI e institucional; os cartoes da aba INTEGRACAO SEI respeitam o recorte atual do workbook.",
        "Metas e planos sao somente leitura neste arquivo. A fonte oficial permanece o Data UNIVC.",
    ]
    for r, text in enumerate(rules, 28):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        ws.cell(r, 1, text)
        ws.cell(r, 1).font = Font(name="Arial", size=9, color=INK)
        ws.cell(r, 1).alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(r, 1).fill = PatternFill("solid", fgColor=GREEN_LIGHT if r % 2 == 0 else WHITE)
        ws.row_dimensions[r].height = 28
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 76


def build_dm_interactive_workbook(payload: dict[str, Any]) -> BytesIO:
    if payload.get("directorate") != "DM":
        raise ValueError("O Excel Interativo DM V3 exige payload da Diretoria de Mestrado.")
    wb = Workbook()
    wb.remove(wb.active)
    ends = _write_technical_data(wb, payload)
    _write_lists(wb, payload)
    _write_parameters(wb, payload)
    _write_calc(wb, payload, ends)
    _write_readme(wb, payload)
    _write_panel(wb, payload, ends)
    _write_dm01(wb, payload, ends)
    _write_dm02(wb, payload, ends)
    _write_cohorts(wb, payload, ends)
    _write_students(wb, payload, ends)
    _write_matrix(wb, payload, ends)
    _write_goals_actions(wb, payload)
    _write_sei(wb, payload, ends)
    _write_quality(wb, payload, ends)

    order = VISIBLE_SHEETS + [name for name in wb.sheetnames if name not in VISIBLE_SHEETS]
    wb._sheets = [wb[name] for name in order]
    for ws in wb.worksheets:
        if ws.title not in VISIBLE_SHEETS:
            ws.sheet_state = "hidden"
    wb.active = wb.sheetnames.index("PAINEL")
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = "auto"
    except Exception:
        pass
    wb.properties.title = "Data UNIVC | Excel Interativo DM"
    wb.properties.subject = "Diretoria de Mestrado | painel interativo por turma"
    wb.properties.creator = "Data UNIVC"
    wb.properties.description = "Excel Interativo V3 beta | DM"
    buffer = BytesIO()
    wb.save(buffer)
    wb.close()
    buffer.seek(0)
    return buffer


def build_dm_interactive_workbook_bytes(
    cohorts: Iterable[dict[str, Any]],
    students: Iterable[dict[str, Any]],
    **kwargs: Any,
) -> BytesIO:
    return build_dm_interactive_workbook(build_dm_interactive_payload(cohorts, students, **kwargs))
