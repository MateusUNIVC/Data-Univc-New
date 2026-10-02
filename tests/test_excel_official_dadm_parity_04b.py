from __future__ import annotations

from datetime import datetime, timezone

from excel_official import ExcelOfficialCore
from excel_official.adapters.dadm import DADMAdapter, DADM_COMPARISON_METRICS, DADM_METRICS
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
            {"period": "2026-09", "department": "financeiro", "department_name": "Financeiro", "employee": "e2", "employee_name": "Bruno", "channel": "email", "status": "finalized", "tabulation": "financeiro", "attendances": 20, "finalized": 20, "open": 0, "tme_sum_minutes": 120.0, "tme_count": 20, "tma_sum_minutes": 500.0, "tma_count": 20, "rating_sum": 90.0, "rating_count": 10, "transferred": 2, "messages_sent": 80, "messages_received": 60},
            {"period": "2026-09", "department": "secretaria", "department_name": "Secretaria", "employee": "e1", "employee_name": "Ana", "channel": "whatsapp", "status": "finalized", "tabulation": "academico", "attendances": 5, "finalized": 5, "open": 0, "tme_sum_minutes": 25.0, "tme_count": 5, "tma_sum_minutes": 100.0, "tma_count": 5, "rating_sum": 45.0, "rating_count": 5, "transferred": 0, "messages_sent": 20, "messages_received": 15},
        ],
        "summary": {
            "attendances": 35, "protocols": 33, "people": 30, "active_operators": 2,
            "finalized": 35, "open": 0, "finalization_rate_pct": 100.0,
            "tme_avg_seconds": 420.0, "tme_median_seconds": 360.0, "tme_p90_seconds": 900.0,
            "tma_avg_seconds": 1542.857, "tma_median_seconds": 1200.0, "tma_p90_seconds": 2400.0,
            "rating_avg": 9.0, "rating_count": 20, "rating_missing": 15, "rating_coverage_pct": 57.142857,
            "transferred": 3, "transfer_rate_pct": 8.571429,
        },
        "comparison": {
            "attendances": 12,
            "tme_avg_seconds": 480.0,
            "tma_avg_seconds": 1200.0,
            "rating_avg": 8.5,
            "rating_coverage_pct": 50.0,
        },
        "comparison_period": {"start": "2026-06-01", "end": "2026-07-31", "mode": "previous_period"},
        "ratings": [],
        "targets": [
            {"indicator_code": "DADM-01", "metric_key": "tme_avg_seconds", "scope_type": "TOTAL", "scope_value": "", "scope_label": "Institucional", "valid_from": "2026-01", "valid_to": "", "target": 600.0, "attention": 900.0},
            {"indicator_code": "DADM-01", "metric_key": "tme_avg_seconds", "scope_type": "channel", "scope_value": "whatsapp", "scope_label": "Canal: whatsapp", "valid_from": "2026-01", "valid_to": "", "target": 240.0, "attention": 360.0},
            {"indicator_code": "DADM-01", "metric_key": "tme_avg_seconds", "scope_type": "department", "scope_value": "secretaria", "scope_label": "Departamento: secretaria", "valid_from": "2026-01", "valid_to": "", "target": 300.0, "attention": 420.0},
            {"indicator_code": "DADM-02", "metric_key": "rating_coverage_pct", "scope_type": "TOTAL", "scope_value": "", "scope_label": "Institucional", "valid_from": "2026-01", "valid_to": "", "target": 70.0, "attention": 50.0},
        ],
        "actions": [],
    }


def _spec(initial=None):
    payload = _payload()
    ctx = SnapshotContext(
        export_id="dadm-04b",
        generated_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
        generated_by="qa@univc.br",
        directorate="DADM",
        authorization_scope=("DADM",),
        system_version="0.13.0",
        schema_version=53,
        initial_filters=payload["initial"],
        minimum_period="2026-08",
        maximum_period="2026-09",
        payload_hash="04b",
    )
    return DADMAdapter().build_spec(AdapterInput(ctx, payload, initial or {}))


def _target_row(spec, *, period, department, channel, metric_code):
    dataset = next(item for item in spec.datasets if item.code == "dadm_targets_effective")
    return next(
        row for row in dataset.rows
        if row["period_selector"] == period
        and row["department_selector"] == department
        and row["channel_selector"] == channel
        and row["metric_code"] == metric_code
    )


def test_dadm_04b_target_inheritance_matches_department_then_channel_then_total():
    spec = _spec()
    # Department wins even when a channel target also exists, matching _active_target().
    assert _target_row(spec, period="2026-09", department="secretaria", channel="whatsapp", metric_code=DADM_METRICS["tme"])["target"] == 300.0
    # Without department, the channel target becomes effective.
    assert _target_row(spec, period="2026-09", department="(todos)", channel="whatsapp", metric_code=DADM_METRICS["tme"])["target"] == 240.0
    # Without a specific department/channel target, TOTAL is inherited.
    assert _target_row(spec, period="2026-09", department="financeiro", channel="email", metric_code=DADM_METRICS["tme"])["target"] == 600.0
    # '(todos)' uses the exported end month as the management reference month.
    assert _target_row(spec, period="(todos)", department="(todos)", channel="(todos)", metric_code=DADM_METRICS["tme"])["reference_month"] == "2026-09"


def test_dadm_04b_target_scales_match_metric_units():
    spec = _spec()
    bindings = {item.metric_code: item for item in spec.target_bindings}
    assert abs(bindings[DADM_METRICS["tme"]].value_scale - (1 / 60)) < 1e-12
    assert abs(bindings[DADM_METRICS["tma"]].value_scale - (1 / 60)) < 1e-12
    assert bindings[DADM_METRICS["rating"]].value_scale == 1
    assert bindings[DADM_METRICS["rating_coverage"]].value_scale == 0.01


def test_dadm_04b_previous_period_metrics_preserve_backend_snapshot_values():
    spec = _spec()
    assert evaluate_metric(spec, DADM_COMPARISON_METRICS["attendances"]) == 12
    assert evaluate_metric(spec, DADM_COMPARISON_METRICS["tme"]) == 8.0
    assert evaluate_metric(spec, DADM_COMPARISON_METRICS["tma"]) == 20.0
    assert evaluate_metric(spec, DADM_COMPARISON_METRICS["rating"]) == 8.5
    assert evaluate_metric(spec, DADM_COMPARISON_METRICS["rating_coverage"]) == 0.5
    comparison = {item.metric_code: item.comparison_metric_code for item in spec.dashboard.kpis}
    assert comparison[DADM_METRICS["tme"]] == DADM_COMPARISON_METRICS["tme"]


def test_dadm_04b_percentiles_are_visible_backend_snapshot_not_fake_offline_metrics():
    spec = _spec()
    dataset = next(item for item in spec.datasets if item.code == "dadm_percentiles")
    assert len(dataset.rows) == 4
    assert {row["statistic"] for row in dataset.rows} == {"Mediana", "P90"}
    assert any(item.code == "dadm.percentiles_backend_only" for item in spec.limitations)
    assert all("median" not in metric.code and "p90" not in metric.code for metric in spec.metrics)


def test_dadm_04b_core_builds_dynamic_targets_and_previous_period_without_release_findings():
    spec = _spec()
    artifact = ExcelOfficialCore().build(spec)
    assert artifact.audit.release_allowed is True
    assert artifact.audit.findings == ()
    assert "METAS EFETIVAS DADM" in artifact.workbook.sheetnames
    assert "RESUMO ANTERIOR" in artifact.workbook.sheetnames
    assert "PERCENTIS BACKEND" in artifact.workbook.sheetnames
    formulas = [
        cell.value
        for ws in artifact.workbook.worksheets
        for row in ws.iter_rows()
        for cell in row
        if cell.data_type == "f" and isinstance(cell.value, str)
    ]
    assert any("RESUMO ANTERIOR" in formula for formula in formulas)
    assert any("METAS EFETIVAS DADM" in formula for formula in formulas)
