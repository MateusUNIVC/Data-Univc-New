from __future__ import annotations

from datetime import datetime, timezone

from excel_official import ExcelOfficialCore
from excel_official.adapters.dadm import DADMAdapter, DADM_METRICS
from excel_official.audit.quality import evaluate_metric
from excel_official.context import AdapterInput, SnapshotContext


def _payload():
    return {
        "directorate": "DADM",
        "app_version": "0.13.0",
        "schema_version": 53,
        "generated_at": "2026-10-02T12:00:00+00:00",
        "period": {"from_month": "2026-08", "to_month": "2026-09", "label": "2026-08 → 2026-09"},
        "initial": {
            "period": "(todos)", "department": "(todos)", "employee": "(todos)",
            "channel": "(todos)", "status": "(todos)", "tabulation": "(todos)",
            "matrix_metric": "Atendimentos",
        },
        "cube": [
            {"period": "2026-08", "department": "secretaria", "department_name": "Secretaria", "employee": "e1", "employee_name": "Ana", "channel": "whatsapp", "status": "finalized", "tabulation": "academico", "attendances": 10, "finalized": 10, "open": 0, "tme_sum_minutes": 100.0, "tme_count": 10, "tma_sum_minutes": 300.0, "tma_count": 10, "rating_sum": 45.0, "rating_count": 5, "transferred": 1, "messages_sent": 40, "messages_received": 30},
            {"period": "2026-08", "department": "financeiro", "department_name": "Financeiro", "employee": "e2", "employee_name": "Bruno", "channel": "email", "status": "open", "tabulation": "financeiro", "attendances": 5, "finalized": 0, "open": 5, "tme_sum_minutes": 100.0, "tme_count": 5, "tma_sum_minutes": 0.0, "tma_count": 0, "rating_sum": 8.0, "rating_count": 1, "transferred": 0, "messages_sent": 10, "messages_received": 15},
            {"period": "2026-09", "department": "secretaria", "department_name": "Secretaria", "employee": "e1", "employee_name": "Ana", "channel": "whatsapp", "status": "finalized", "tabulation": "academico", "attendances": 20, "finalized": 20, "open": 0, "tme_sum_minutes": 100.0, "tme_count": 20, "tma_sum_minutes": 400.0, "tma_count": 20, "rating_sum": 81.0, "rating_count": 9, "transferred": 2, "messages_sent": 80, "messages_received": 60},
        ],
        "summary": {
            "attendances": 35, "protocols": 30, "people": 28, "active_operators": 2,
            "finalized": 30, "open": 5, "finalization_rate_pct": 85.7142857143,
            "tme_avg_seconds": 600.0, "tme_median_seconds": 480.0, "tme_p90_seconds": 1200.0,
            "tma_avg_seconds": 1400.0, "tma_median_seconds": 1200.0, "tma_p90_seconds": 2400.0,
            "rating_avg": 8.9333333333, "rating_count": 15, "rating_missing": 20, "rating_coverage_pct": 42.8571428571,
            "transferred": 3, "transfer_rate_pct": 8.5714285714,
        },
        "ratings": [{"rating": i, "count": 1 if i in (8, 9, 10) else 0, "pct": 33.333 if i in (8, 9, 10) else 0} for i in range(1, 11)],
        "targets": [],
        "actions": [],
    }


def _input(initial=None):
    payload = _payload()
    ctx = SnapshotContext(
        export_id="dadm-test-04a",
        generated_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
        generated_by="qa@univc.br",
        directorate="DADM",
        authorization_scope=("DADM",),
        system_version="0.13.0",
        schema_version=53,
        initial_filters=payload["initial"],
        minimum_period="2026-08",
        maximum_period="2026-09",
        payload_hash="abc123",
    )
    return AdapterInput(ctx, payload, initial or {})


def test_dadm_adapter_recomposes_full_snapshot_metrics_without_averaging_averages():
    spec = DADMAdapter().build_spec(_input())
    assert evaluate_metric(spec, DADM_METRICS["attendances"]) == 35
    assert abs(evaluate_metric(spec, DADM_METRICS["finalization"]) - (30 / 35)) < 1e-12
    assert abs(evaluate_metric(spec, DADM_METRICS["tme"]) - (300 / 35)) < 1e-12
    assert abs(evaluate_metric(spec, DADM_METRICS["tma"]) - (700 / 30)) < 1e-12
    assert abs(evaluate_metric(spec, DADM_METRICS["rating"]) - (134 / 15)) < 1e-12
    assert abs(evaluate_metric(spec, DADM_METRICS["rating_coverage"]) - (15 / 35)) < 1e-12


def test_dadm_adapter_filters_department_and_month_offline():
    spec = DADMAdapter().build_spec(_input({"period": "2026-09", "department": "secretaria"}))
    assert evaluate_metric(spec, DADM_METRICS["attendances"]) == 20
    assert evaluate_metric(spec, DADM_METRICS["open"]) == 0
    assert abs(evaluate_metric(spec, DADM_METRICS["tme"]) - 5.0) < 1e-12
    assert abs(evaluate_metric(spec, DADM_METRICS["rating"]) - 9.0) < 1e-12


def test_dadm_adapter_keeps_tallos_rating_scale_without_inferred_satisfaction():
    spec = DADMAdapter().build_spec(_input())
    codes = {metric.code for metric in spec.metrics}
    assert DADM_METRICS["rating"] in codes
    assert not any("satisfaction" in code for code in codes)
    assert any(item.code == "dadm.no_satisfaction_threshold_inference" for item in spec.limitations)


def test_dadm_adapter_uses_aggregated_cube_and_preserves_backend_distinct_summary():
    spec = DADMAdapter().build_spec(_input())
    cube = next(item for item in spec.datasets if item.code == "dadm_cube")
    summary = next(item for item in spec.datasets if item.code == "dadm_backend_summary")
    assert "protocol" not in {column.code for column in cube.columns}
    assert summary.rows[0]["protocols"] == 30
    assert summary.rows[0]["people"] == 28


def test_dadm_adapter_matrix_is_department_by_month_with_metric_selector():
    spec = DADMAdapter().build_spec(_input())
    assert spec.matrix is not None
    assert spec.matrix.row_dimension == "department"
    assert spec.matrix.column_dimension == "period"
    assert spec.matrix.metric_selector_parameter == "matrix_metric"
    assert len(spec.matrix.metric_options) >= 5


def test_dadm_excel_official_core_builds_release_clean_workbook():
    spec = DADMAdapter().build_spec(_input())
    artifact = ExcelOfficialCore().build(spec)
    assert artifact.audit.release_allowed is True
    assert artifact.audit.findings == ()
    assert artifact.workbook.sheetnames[:6] == [
        "LEIA-ME", "PARAMETROS", "PAINEL", "QUALIDADE E GOVERNANÇA", "MATRIZ", "PLANO_DE_ACAO"
    ]
    assert "OPERACAO TALLOS" in artifact.workbook.sheetnames
    assert "RESUMO BACKEND" in artifact.workbook.sheetnames


def test_dadm_adapter_uses_dependent_employee_dimension():
    spec = DADMAdapter().build_spec(_input())
    employee = next(item for item in spec.dimensions if item.code == "employee")
    assert employee.parent_dimension == "department"
    assert employee.parent_key_column == "department"


def test_dadm_adapter_rejects_wrong_directorate():
    adapter_input = _input()
    bad_ctx = SnapshotContext(
        export_id=adapter_input.snapshot_context.export_id,
        generated_at=adapter_input.snapshot_context.generated_at,
        generated_by=adapter_input.snapshot_context.generated_by,
        directorate="DM",
        authorization_scope=("DM",),
        system_version="0.13.0",
        schema_version=53,
    )
    try:
        DADMAdapter().build_spec(AdapterInput(bad_ctx, _payload(), {}))
    except Exception as exc:
        assert "snapshot_scope_mismatch" in str(exc)
    else:
        raise AssertionError("DADMAdapter deveria rejeitar snapshot de outra diretoria")


def test_dadm_matrix_accepts_single_month_snapshot_without_fake_delta_column():
    payload = _payload()
    payload["cube"] = [row for row in payload["cube"] if row["period"] == "2026-09"]
    payload["period"] = {"from_month": "2026-09", "to_month": "2026-09", "label": "2026-09"}
    payload["initial"]["period"] = "2026-09"
    ctx = SnapshotContext(
        export_id="dadm-test-single-month",
        generated_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
        generated_by="qa@univc.br",
        directorate="DADM",
        authorization_scope=("DADM",),
        system_version="0.13.0",
        schema_version=53,
        initial_filters=payload["initial"],
        minimum_period="2026-09",
        maximum_period="2026-09",
        payload_hash="single-month",
    )
    spec = DADMAdapter().build_spec(AdapterInput(ctx, payload, {}))
    assert spec.matrix is not None and spec.matrix.delta is False
    artifact = ExcelOfficialCore().build(spec)
    assert artifact.audit.release_allowed is True
