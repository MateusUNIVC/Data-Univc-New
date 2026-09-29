from __future__ import annotations

from pathlib import Path

import release_info

ROOT = Path(__file__).resolve().parents[1]


def test_release_preserves_dev14_contract_without_schema_regression():
    assert release_info.APP_VERSION.startswith("0.13.0")
    if release_info.APP_VERSION != "0.13.0":
        assert int(release_info.APP_VERSION.rsplit(".", 1)[-1]) >= 14
    assert release_info.SCHEMA_VERSION == 48


def test_legacy_dpe_excel_import_runtime_is_removed():
    assert not (ROOT / "dpe_excel_parser.py").exists()
    assert not (ROOT / "dpe_excel_builder.py").exists()
    router = (ROOT / "dpe_router.py").read_text(encoding="utf-8")
    for route in (
        '@router.post("/api/dpe/import")',
        '@router.get("/api/dpe/modelo/{indicator_code}")',
        '@router.post("/api/dpe/demo")',
    ):
        assert route not in router
    assert "parse_dpe_workbook" not in router
    assert "build_dpe_import_template" not in router


def test_generic_management_measurement_surfaces_reject_dpe():
    source = (ROOT / "management_router.py").read_text(encoding="utf-8")
    assert "def _reject_dpe_legacy_measurements" in source
    for function_name in (
        "management_dashboard",
        "management_measurements",
        "management_measurement_create",
        "management_measurement_update",
        "management_measurement_delete",
        "management_excel",
    ):
        block = source.split(f"def {function_name}", 1)[1] if f"def {function_name}" in source else source.split(f"async def {function_name}", 1)[1]
        block = block[: block.find("\n\n@router", 1) if "\n\n@router" in block else len(block)]
        assert "_reject_dpe_legacy_measurements(scope)" in block


def test_active_dpe_frontend_has_no_old_indicator_names():
    active = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "templates/dpe.html",
            "static/js/dpe.js",
            "static/js/dpe_v2.js",
            "static/js/dpe_cost_engine.js",
            "static/js/dpe_cost_revenues.js",
            "static/js/dpe_cost_expenses.js",
            "static/js/dpe_cost_teaching.js",
            "static/js/dpe_cost_allocation.js",
            "static/js/dpe_cost_economics.js",
            "static/js/dpe_cost_productivity.js",
            "static/js/dpe_cost_closure.js",
            "static/js/dpe_cost_analytics.js",
        )
    )
    for token in ("DPE-01", "DPE-02", "DPE-03", "Histórico e legado", "Historico e legado"):
        assert token not in active


def test_generic_demo_seed_cannot_recreate_legacy_dpe_measurements():
    source = (ROOT / "demo_seed.py").read_text(encoding="utf-8")
    assert "def seed_dpe_demo" not in source
    assert "Use scripts/seed_dpe_demo.py" in source
    assert "dpe_data" not in source
