from __future__ import annotations

from pathlib import Path

import release_info

ROOT = Path(__file__).resolve().parents[1]


def test_release_preserves_dev12_without_schema_bump():
    assert release_info.APP_VERSION.startswith("0.13.0")
    if release_info.APP_VERSION != "0.13.0":
        assert int(release_info.APP_VERSION.rsplit(".", 1)[-1]) >= 12
    assert release_info.SCHEMA_VERSION >= 48


def test_sidebar_separates_month_flow_results_and_configuration():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    assert "Fluxo do mês" in html
    assert "Resultados e gestão" in html
    assert "Configuração e ferramentas" in html
    assert 'data-section="economia"><span class="nav-icon"></span><span>Resultado por curso</span>' in html
    assert 'data-section="metas"' in html and 'data-section="planos"' in html
    config = html.split("Configuração e ferramentas", 1)[1].split("</details>", 1)[0]
    assert 'data-section="metas"' not in config
    assert 'data-section="planos"' not in config


def test_month_workflow_strip_has_single_clear_sequence():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    flow = html.split('id="dpeWorkflowNav"', 1)[1].split("</nav>", 1)[0]
    expected = ["receita-operacional", "central-despesas", "docencia", "rateio", "fechamento"]
    positions = [flow.index(f'data-flow-section="{section}"') for section in expected]
    assert positions == sorted(positions)
    assert flow.count("data-flow-section=") == 5


def test_topbar_is_contextual_and_remembers_last_section():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "dpe.js").read_text(encoding="utf-8")
    assert 'id="dpePageSubtitle"' in html
    assert 'id="dpeQuickAdd"' in html
    assert "DPE_SECTION_META" in js
    assert "runSectionQuickAction" in js
    assert "DPE_NAV_STORAGE_KEY" in js
    assert "sessionStorage.setItem" in js
    assert "sessionStorage.getItem" in js
    assert "Resultado por curso" in js


def test_current_navigation_has_no_legacy_chevron_or_ambiguous_top_level_courses_label():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "dpe.css").read_text(encoding="utf-8")
    sidebar = html.split('<nav class="nav-list dpe-ux-nav">', 1)[1].split("</nav>", 1)[0]
    assert "legacy-chevron" not in html
    assert "legacy-chevron" not in css
    assert '<span>Cursos</span>' not in sidebar
    assert '<span>Resultado por curso</span>' in sidebar
