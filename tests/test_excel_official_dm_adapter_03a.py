from __future__ import annotations

from datetime import date
from pathlib import Path

from dm_analytics import build_dm_dashboard
from dm_demo import build_dm_demo_payloads
from dm_excel_official import build_dm_excel_official_artifact, build_dm_excel_official_payload
from excel_official.adapters.dm import DMAdapter, DM_METRICS


TARGETS = [
    {"id": 1, "indicator_code": "DM-01", "metric_key": "cohort_members", "target": 15, "valid_from": "2025-SEM1", "valid_to": None, "dimension_key": None, "justification": "Meta institucional"},
    {"id": 2, "indicator_code": "DM-02", "metric_key": "average_months_to_defense", "target": 24, "valid_from": "2025-SEM1", "valid_to": None, "dimension_key": None, "justification": "Meta institucional"},
]
CUTOFF = date(2026, 8, 28)


def _fixture():
    cohorts, students = build_dm_demo_payloads()
    payload = build_dm_excel_official_payload(cohorts, students, targets=TARGETS, as_of=CUTOFF)
    artifact = build_dm_excel_official_artifact(cohorts, students, targets=TARGETS, as_of=CUTOFF, generated_by="qa@univc")
    return cohorts, students, payload, artifact


def test_03a_dm_adapter_is_declarative():
    root = Path(__file__).resolve().parents[1]
    source = (root / "excel_official" / "adapters" / "dm.py").read_text(encoding="utf-8")
    assert "openpyxl" not in source
    assert DMAdapter.adapter_code == "dm"
    assert DMAdapter.adapter_version == 1


def test_03a_dm_core_build_releases_cleanly():
    _, _, _, artifact = _fixture()
    assert artifact.audit.release_allowed is True
    assert artifact.audit.findings == ()
    assert artifact.workbook.sheetnames[:6] == [
        "LEIA-ME", "PARAMETROS", "PAINEL", "QUALIDADE E GOVERNANÇA", "MATRIZ", "PLANO_DE_ACAO"
    ]
    assert "INDICADORES TURMAS" in artifact.workbook.sheetnames
    assert "ALUNOS E DEFESAS" in artifact.workbook.sheetnames


def test_03a_dm_parameters_preserve_official_cutoff_and_interactive_scope():
    _, _, _, artifact = _fixture()
    refs = artifact.refs.parameters.parameters
    assert refs["area"].editable is True
    assert refs["cohort"].editable is True
    assert refs["comparison_cohort"].editable is True
    assert refs["matrix_metric"].editable is True
    assert refs["as_of"].editable is False
    assert artifact.workbook["PARAMETROS"][refs["as_of"].cell_reference].value == CUTOFF


def test_03a_dm_dashboard_has_official_kpis_and_four_charts():
    _, _, _, artifact = _fixture()
    codes = [item.metric_code for item in artifact.refs.dashboard.kpis]
    assert codes == [
        DM_METRICS["members"], DM_METRICS["active"], DM_METRICS["occupancy"], DM_METRICS["avg_defense"], DM_METRICS["on_time"]
    ]
    assert len(artifact.refs.charts.charts) == 4


def test_03a_dm_payload_recomposes_overall_metrics_from_same_dashboard_semantics():
    cohorts, students, payload, _ = _fixture()
    dashboard = build_dm_dashboard(cohorts, students, as_of=CUTOFF, targets=TARGETS)
    rows = payload["dashboard_snapshot"]["areas"]
    summaries = [cohort for area in rows for cohort in area["cohorts"]]

    total = sum(int(row["total_students"]) for row in summaries)
    active = sum(int(row["active_students"]) for row in summaries)
    vacancies = sum(int(row.get("vacancies_authorized") or 0) for row in summaries)
    defenses = sum(int(row["defenses_count"]) for row in summaries)
    weighted_months = sum(float(row.get("average_months_to_defense") or 0) * int(row["defenses_count"]) for row in summaries)
    on_time = sum(int(row["graduated_within_24"]) for row in summaries)
    confirmed = sum(int(row["confirmed_entry_dates"]) for row in summaries)

    assert total == dashboard["overall"]["total_students"]
    assert active == dashboard["overall"]["active_students"]
    assert round(total / vacancies * 100, 2) == dashboard["overall"]["occupancy_pct"]
    expected_avg = round(weighted_months / defenses, 2) if defenses else None
    assert expected_avg == dashboard["overall"]["average_months_to_defense"]
    expected_on_time = round(on_time / confirmed * 100, 2) if confirmed else None
    assert expected_on_time == dashboard["overall"]["on_time_graduation_pct"]


def test_03a_dm_targets_use_effective_cutoff_semester():
    _, _, _, artifact = _fixture()
    ws = artifact.workbook["PARAMETROS"]
    refs = artifact.refs.parameters.parameters
    assert ws[refs["target_period"].cell_reference].value == "2026-SEM2"
    kpis = {item.metric_code: item for item in artifact.refs.dashboard.kpis}
    assert kpis[DM_METRICS["members"]].target_cell is not None
    assert kpis[DM_METRICS["avg_defense"]].target_cell is not None


def test_03a_dm_matrix_switches_between_declared_metrics():
    _, _, _, artifact = _fixture()
    ws = artifact.workbook["MATRIZ"]
    assert ws["B4"].value == "=P_MATRIX_METRIC"
    formulas = [cell.value for row in ws.iter_rows() for cell in row if cell.data_type == "f"]
    joined = "\n".join(formulas)
    assert "P_MATRIX_METRIC" in joined
    assert "DM-01 · Membros por turma" in joined
    assert "DM-02 · Tempo médio até defesa" in joined


def test_03a_dm_no_external_links_or_vba():
    _, _, _, artifact = _fixture()
    wb = artifact.workbook
    assert not getattr(wb, "_external_links", [])
    assert wb.vba_archive is None
