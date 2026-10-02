from __future__ import annotations

from academic_excel_official import build_academic_excel_official_artifact_from_payload
from excel_official.adapters.academic import ACADEMIC_METRICS
from test_excel_official_academic_adapter_v1 import _payload


def _artifact():
    payload = _payload()
    payload["institution_students_by_course"] = [
        {"periodo": "2026-SEM1", "curso": "Administração", "respondentes": 80, "promotores": 48, "neutros": 20, "detratores": 12, "valor": 45.0},
        {"periodo": "2026-SEM1", "curso": "Psicologia", "respondentes": 100, "promotores": 57, "neutros": 25, "detratores": 18, "valor": 39.0},
        {"periodo": "2026-SEM2", "curso": "Administração", "respondentes": 110, "promotores": 70, "neutros": 25, "detratores": 15, "valor": 50.0},
        {"periodo": "2026-SEM2", "curso": "Psicologia", "respondentes": 90, "promotores": 50, "neutros": 20, "detratores": 20, "valor": 33.3333},
    ]
    codes = payload["codes"]
    payload["initial"].update({"window": 4, "matrix_kpi": "01A · NPS Instituição · Alunos"})
    payload["effective_goals"] = [
        {"periodo": "2026-SEM2", "kpi": codes["nps_institution"], "curso": "(todos)", "disciplina": "(todas)", "meta": 50.0, "atencao": 40.0, "vigencia": "2026-SEM2", "recorte": "TOTAL"},
        {"periodo": "2026-SEM2", "kpi": codes["nps_institution"], "curso": "Administração", "disciplina": "(todas)", "meta": 55.0, "atencao": 45.0, "vigencia": "2026-SEM2", "recorte": "Administração"},
        {"periodo": "2026-SEM2", "kpi": codes["nps_institution"], "curso": "Psicologia", "disciplina": "(todas)", "meta": 52.0, "atencao": 42.0, "vigencia": "2026-SEM2", "recorte": "Psicologia"},
        {"periodo": "2026-SEM2", "kpi": codes["nps_course"], "curso": "(todos)", "disciplina": "(todas)", "meta": 45.0, "atencao": 40.0, "vigencia": "2026-SEM2", "recorte": "TOTAL"},
        {"periodo": "2026-SEM2", "kpi": codes["nps_course"], "curso": "Administração", "disciplina": "(todas)", "meta": 48.0, "atencao": 40.0, "vigencia": "2026-SEM2", "recorte": "Administração"},
        {"periodo": "2026-SEM2", "kpi": codes["nps_course"], "curso": "Psicologia", "disciplina": "(todas)", "meta": 46.0, "atencao": 38.0, "vigencia": "2026-SEM2", "recorte": "Psicologia"},
        {"periodo": "2026-SEM2", "kpi": codes["nps_faculty"], "curso": "(todos)", "disciplina": "(todas)", "meta": 50.0, "atencao": 40.0, "vigencia": "2026-SEM2", "recorte": "TOTAL"},
        {"periodo": "2026-SEM2", "kpi": codes["teacher"], "curso": "(todos)", "disciplina": "(todas)", "meta": 80.0, "atencao": 70.0, "vigencia": "2026-SEM2", "recorte": "TOTAL"},
        {"periodo": "2026-SEM2", "kpi": codes["teacher"], "curso": "Administração", "disciplina": "(todas)", "meta": 82.0, "atencao": 72.0, "vigencia": "2026-SEM2", "recorte": "Administração"},
        {"periodo": "2026-SEM2", "kpi": codes["approval"], "curso": "(todos)", "disciplina": "(todas)", "meta": 85.0, "atencao": 75.0, "vigencia": "2026-SEM2", "recorte": "TOTAL"},
        {"periodo": "2026-SEM2", "kpi": codes["approval"], "curso": "Administração", "disciplina": "(todas)", "meta": 88.0, "atencao": 78.0, "vigencia": "2026-SEM2", "recorte": "Administração"},
    ]
    return build_academic_excel_official_artifact_from_payload(payload, generated_by="qa@univc.br", export_id="qa-academic-02b")


def test_02b_adds_history_window_and_matrix_selector_parameters():
    artifact = _artifact()
    spec = artifact.spec
    params = {item.code: item for item in spec.parameters}
    assert spec.capabilities.supports_history_window is True
    assert params["history_window"].initial_value == "4"
    assert params["matrix_metric"].initial_value == "01A · NPS Instituição · Alunos"
    assert artifact.refs.parameters.parameters["history_window"].defined_name == "P_HISTORY_WINDOW"
    assert artifact.refs.parameters.parameters["matrix_metric"].defined_name == "P_MATRIX_METRIC"


def test_02b_dashboard_targets_are_dynamic_and_use_effective_goal_base():
    artifact = _artifact()
    refs = {item.metric_code: item for item in artifact.refs.dashboard.kpis}
    assert refs[ACADEMIC_METRICS["nps_course"]].target_cell is not None
    formula = artifact.workbook["PAINEL"][refs[ACADEMIC_METRICS["nps_course"]].target_cell].value
    assert isinstance(formula, str) and formula.startswith("=")
    assert "BASE METAS ACADEMICAS" in formula
    assert "P_REFERENCE_PERIOD" in formula
    assert "P_COURSE" in formula
    # Percent targets are normalized from percentage points to the metric's 0..1 unit.
    teacher_formula = artifact.workbook["PAINEL"][refs[ACADEMIC_METRICS["teacher"]].target_cell].value
    assert "*0.01" in teacher_formula


def test_02b_charts_use_dynamic_history_window_without_dynamic_array_functions():
    artifact = _artifact()
    ws = artifact.workbook["CALC"]
    formulas = [cell.value for row in ws.iter_rows() for cell in row if isinstance(cell.value, str) and cell.value.startswith("=")]
    window_formulas = [formula for formula in formulas if "P_HISTORY_WINDOW" in formula]
    assert window_formulas
    joined = "\n".join(window_formulas).upper()
    assert "P_REFERENCE_PERIOD" in joined
    assert "VALUE(P_HISTORY_WINDOW)" in joined
    for forbidden in ("FILTER(", "XLOOKUP(", "SORT(", "UNIQUE(", "INDIRECT(", "OFFSET("):
        assert forbidden not in joined
    assert all(ref.category_count <= 12 for ref in artifact.refs.charts.charts)


def test_02b_matrix_selector_is_numeric_and_uses_distinct_01a_course_breakdown():
    artifact = _artifact()
    spec = artifact.spec
    assert ACADEMIC_METRICS["nps_institution_course"] in {item.code for item in spec.metrics}
    binding = next(item for item in spec.metric_bindings if item.metric_code == ACADEMIC_METRICS["nps_institution_course"])
    assert binding.dataset_code == "academic_nps_institution_course"

    matrix = artifact.refs.matrix
    assert matrix is not None
    ws = artifact.workbook["MATRIZ"]
    assert ws["B4"].value == "=P_MATRIX_METRIC"
    value_formula = ws.cell(matrix.first_data_row, matrix.first_value_column).value
    assert isinstance(value_formula, str) and value_formula.startswith("=")
    assert "P_MATRIX_METRIC" in value_formula
    assert "NPS INST POR CURSO" in value_formula
    assert "NPS CURSO" in value_formula
    assert "AVALIACAO DOCENTE" in value_formula
    assert "RESULTADOS ACADEMICOS" in value_formula
    assert "*100.0" in value_formula
    assert ws.cell(matrix.first_data_row, matrix.first_value_column).number_format == "0.0"


def test_02b_matrix_target_is_dynamic_by_selected_metric_and_course():
    artifact = _artifact()
    matrix = artifact.refs.matrix
    assert matrix is not None and matrix.target_column is not None
    ws = artifact.workbook["MATRIZ"]
    formula = ws.cell(matrix.first_data_row, matrix.target_column).value
    assert isinstance(formula, str) and formula.startswith("=")
    assert "P_MATRIX_METRIC" in formula
    assert "BASE METAS ACADEMICAS" in formula
    assert "Administração" in formula
    assert "*100.0" in formula


def test_02b_removes_the_three_cutover_blocker_limitations():
    spec = _artifact().spec
    codes = {item.code for item in spec.limitations}
    assert "academic.dynamic_goals_pending" not in codes
    assert "academic.history_window_pending" not in codes
    assert "academic.matrix_metric_selector_pending" not in codes
