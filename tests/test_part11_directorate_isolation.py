from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
FACULTY_JS = (ROOT / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")
RELEASE_INFO = (ROOT / "release_info.py").read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def test_nps_distribution_cache_is_scoped_and_reset_by_directorate():
    reset = _block(APP_JS, "function resetDirectorateCaches()", "function renderDirectorateSelector()")
    cache_key = _block(APP_JS, "function npsDistributionCacheKey", "async function loadNpsScoreDistribution")
    assert "state.npsDistributionCache = {};" in reset
    assert "state.activeDirectorate || 'GLOBAL'" in cache_key
    assert "`${state.activeDirectorate || 'GLOBAL'}|${audience}" in cache_key


def test_switch_increments_generation_and_clears_old_academic_surfaces():
    switch = _block(APP_JS, "async function switchDirectorate(code)", "function indicatorByCode")
    assert "state.directorateEpoch += 1;" in switch
    assert "resetDirectorateCaches();" in switch
    assert "clearDirectorateAcademicSurfaces(code);" in switch
    assert "const switchContext = captureDirectorateContext();" in switch
    assert "if (!isDirectorateContextCurrent(switchContext)) return;" in switch
    assert switch.index("state.directorateEpoch += 1;") < switch.index("resetDirectorateCaches();")


def test_old_async_responses_cannot_write_nps_dashboard_or_results_state():
    required = [
        "function captureDirectorateContext()",
        "function isDirectorateContextCurrent(context)",
        "const context = captureDirectorateContext();",
        "if (!isDirectorateContextCurrent(context)) return;",
    ]
    for token in required:
        assert token in APP_JS

    institution = _block(APP_JS, "async function loadInstitutionNps", "function fillNpsInstitutionFilters")
    faculty = _block(APP_JS, "async function loadFacultyNps", "function fillNpsFacultyFilters")
    dashboard = _block(APP_JS, "async function loadDashboard()", "function updateAcademicWindowOptions")
    distribution = _block(APP_JS, "async function loadNpsScoreDistribution", "function renderLineChart")
    result_summary = _block(APP_JS, "async function loadResultSummary", "async function loadResultStudentSummary")
    result_trend = _block(APP_JS, "async function loadResultTrend", "function renderResultTrend")
    result_details = _block(APP_JS, "async function loadResultDetails", "function renderResultDetailTable")

    for block in [institution, faculty, dashboard, distribution, result_summary, result_trend, result_details]:
        assert "captureDirectorateContext()" in block
        assert "isDirectorateContextCurrent(context)" in block


def test_result_workspace_checks_generation_after_parallel_requests_before_rendering():
    load_dataset = _block(APP_JS, "async function loadDataset(dataset, force = false)", "function renderDatasetTable")
    result_branch = load_dataset[load_dataset.index("if (dataset === 'resultados')"):]
    assert "const context = captureDirectorateContext();" in result_branch
    assert "await Promise.all([loadResultSummary(force), loadResultStudentSummary(force), loadResultTrend(force)]);" in result_branch
    assert "if (!isDirectorateContextCurrent(context)) return;" in result_branch
    assert result_branch.index("if (!isDirectorateContextCurrent(context)) return;") > result_branch.index("await Promise.all")


def test_faculty_filters_do_not_render_after_directorate_reset():
    load_facets = _block(FACULTY_JS, "async function loadFacets", "function renderFilters")
    load_current = _block(FACULTY_JS, "async function loadCurrentView", "async function load(force")
    reset = _block(FACULTY_JS, "function reset()", "function filterParams")
    assert "serial = moduleState.loadSerial" in load_facets
    assert load_facets.count("serial !== moduleState.loadSerial") >= 3
    assert "return false;" in load_facets
    assert "const facetsLoaded = await loadFacets(serial);" in load_current
    assert "if (!facetsLoaded) return;" in load_current
    assert "moduleState.loadSerial += 1;" in reset
    assert "clearRenderedState(state.activeDirectorate);" in reset


def test_part11_does_not_require_database_migration():
    assert (ROOT / 'database/049_academic_faculty_context_scopes_v0130.sql').exists()
    doc = (ROOT / 'docs/PART11_DIRECTORATE_ISOLATION_2026-10-01.md').read_text(encoding='utf-8')
    assert 'schema: 49' in doc.lower()
