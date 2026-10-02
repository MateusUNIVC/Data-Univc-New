from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dtnh_dcs_load_shared_academic_charts_before_app():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    shared = html.index("data-univc-academic-charts.js")
    app = html.index("/static/js/app.js")
    assert shared < app
    js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "window.DataUnivcAcademicCharts?.distribution" in js


def test_shared_nps_distribution_uses_same_visual_contract():
    js = (ROOT / "static" / "js" / "data-univc-academic-charts.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
    for token in ["academic-nps-summary", "academic-nps-distribution", "academic-nps-score", "academic-nps-groups"]:
        assert token in js
        assert f".{token}" in css


def test_reitoria_charts_have_rich_hover_tooltips():
    js = (ROOT / "static" / "js" / "data-univc-academic-charts.js").read_text(encoding="utf-8")
    assert "chart-hover-card hidden" in js
    assert "Respondentes" in js
    assert "Promotores" in js
    assert "Respostas classificadas" in js
    assert "Aprovados" in js
    assert "pointermove" in js


def test_reitoria_has_institution_nps_comparison_by_course():
    html = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "reitoria_academico.js").read_text(encoding="utf-8")
    backend = (ROOT / "reitoria_academic.py").read_text(encoding="utf-8")
    assert 'id="reitoriaChartNpsInstitutionCourses"' in html
    assert "nps_institution_courses" in js
    assert "def _nps_institution_course_comparison" in backend
    assert '"nps_institution_courses": self._nps_institution_course_comparison' in backend


def test_shared_nps_distribution_is_horizontally_scrollable_on_mobile():
    js = (ROOT / "static" / "js" / "data-univc-academic-charts.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert 'class="academic-nps-scroll"' in js
    assert 'class="academic-nps-scroll-content"' in js
    assert 'tabindex="0"' in js
    assert 'Deslize horizontalmente para ver as notas de 0 a 10' in js
    assert ".academic-nps-scroll{width:100%;max-width:100%;min-width:0;overflow-x:auto" in css
    assert ".academic-nps-scroll-content{min-width:440px}" in css
    assert ".academic-nps-distribution{min-width:520px}" not in css


def test_dtnh_dcs_and_reitoria_share_the_responsive_nps_renderer():
    index_html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    reitoria_html = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    reitoria_js = (ROOT / "static" / "js" / "reitoria_academico.js").read_text(encoding="utf-8")
    assert "data-univc-academic-charts.js" in index_html
    assert "data-univc-academic-charts.js" in reitoria_html
    assert "charts().distribution" in reitoria_js
    for host in ["npsInstitutionDistribution", "npsCourseDistribution", "npsFacultyDistribution"]:
        assert f'id="{host}"' in index_html
    for host in ["reitoriaNpsInstitutionDistribution", "reitoriaNpsCourseDistribution", "reitoriaNpsFacultyDistribution"]:
        assert f'id="{host}"' in reitoria_html


def test_reitoria_academic_assets_are_cache_busted_for_mobile_nps_fix():
    router = (ROOT / "admin_router.py").read_text(encoding="utf-8")
    assert 'f"{APP_VERSION}-npsmobile01"' in router
