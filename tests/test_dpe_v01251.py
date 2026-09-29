from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
CORE_JS = (ROOT / "static" / "js" / "dpe.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "dpe.css").read_text(encoding="utf-8")


def test_revenue_layout_does_not_force_hidden_section_visible():
    assert ".ui-v2-dpe .revenue-operations-section{display:grid" not in CSS
    assert ".ui-v2-dpe .revenue-operations-section.active{display:grid}" in CSS
    assert ".ui-v2-dpe .page-section:not(.active){display:none!important}" in CSS


def test_primary_navigation_targets_existing_distinct_sections():
    expected = {
        "dashboard", "receita-operacional", "central-despesas", "economia",
        "docencia", "rateio", "fechamento", "produtividade", "catalogo",
        "politicas-rateio", "competencias",
    }
    nav = set(re.findall(r'data-section="([^"]+)"', TEMPLATE))
    ids = set(re.findall(r'id="section-([^"]+)"[^>]*class="page-section', TEMPLATE))
    assert expected <= nav
    assert expected <= ids
    assert len(expected) == len(set(expected))


def test_productivity_has_correct_page_title_mapping():
    assert "produtividade:{title:'Produtividade'" in CORE_JS or "produtividade:'Produtividade'" in CORE_JS


def test_preseeded_demo_database_contains_modern_dpe_data():
    path = ROOT / "univc_dpe_demo.db"
    if not path.exists():
        pytest.skip("Pacote de producao nao inclui banco DEMO local.")
    assert path.exists() and path.stat().st_size > 0
    with sqlite3.connect(path) as conn:
        checks = {
            "dpe_cost_periods": 1,
            "dpe_academic_products": 16,
            "dpe_academic_offerings": 19,
            "dpe_cost_expenses": 40,
            "dpe_cost_offering_economics": 19,
            "dpe_cost_allocation_runs": 1,
            "dpe_allocation_policies": 2,
        }
        for table, minimum in checks.items():
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count >= minimum, (table, count)
