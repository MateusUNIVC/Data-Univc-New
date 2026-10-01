from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_faculty_frontend_is_not_shipped():
    app_js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    forbidden = [
        "loadTeacherOptions",
        "loadTeacherAnalysis",
        "teacherPeriodFilter",
        "teacherCourseFilter",
        "teacherDisciplineFilter",
        "teacherProfessorFilter",
        "teacherAnalysisCards",
        "chartTeacherKpiEvolution",
        "chartTeacherKpiComparison",
        "/api/avaliacao-docente/opcoes",
        "/api/avaliacao-docente/analise",
        "Nota histórica · legado",
        "openTeacherSeiReadiness",
        "teacherSeiReadinessButton",
    ]
    assert not [token for token in forbidden if token in app_js]


def test_official_faculty_workspace_remains_wired():
    template = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/faculty-evaluation.js").read_text(encoding="utf-8")
    assert 'id="facultySemesterFilter"' in template
    assert 'id="facultyCourseFilter"' in template
    assert 'id="facultyDisciplineFilter"' in template
    assert 'id="facultyTeacherFilter"' in template
    assert "/api/surveys/faculty-student" in js
    assert "FacultyEvaluationUI" in js


def test_retired_faculty_endpoints_remain_explicit_410_contracts():
    app_py = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/api/avaliacao-docente/opcoes")' in app_py
    assert '@app.get("/api/avaliacao-docente/analise")' in app_py
    assert app_py.count("raise HTTPException(\n        410,") >= 2


def test_release_checks_cover_all_javascript_and_template_references():
    checks = (ROOT / "scripts/run_release_checks.py").read_text(encoding="utf-8")
    assert '(ROOT / "static" / "js").rglob("*.js")' in checks
    assert "active_template_javascript" in checks
    assert 'node", "--check"' in checks
    assert "Legacy faculty frontend tokens found" in checks


def test_active_bootstrap_helpers_remain_defined_after_legacy_cleanup():
    app_js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    required_helpers = [
        "renderDirectorateSelector",
        "applyDirectorateUi",
        "fillCourseSelectors",
        "fillResultFilters",
        "fillConfig",
    ]
    for helper in required_helpers:
        assert f"function {helper}(" in app_js, f"Startup helper {helper} is referenced but not defined"

    # fillConfig is part of the active Configurações workspace, not faculty legacy.
    template = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert 'id="configForm"' in template
    assert 'id="configResponsavel"' in template
    assert 'id="configDiretoria"' in template
    assert "fillConfig();" in app_js
