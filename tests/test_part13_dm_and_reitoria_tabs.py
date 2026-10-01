from __future__ import annotations

from pathlib import Path

from dm_sei_parser import parse_dm_sei_workbook

ROOT = Path(__file__).resolve().parents[1]


def test_reitoria_admin_and_academic_are_dedicated_routes_and_templates():
    admin_html = (ROOT / "templates" / "reitoria.html").read_text(encoding="utf-8")
    academic_html = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    admin_js = (ROOT / "static" / "js" / "admin_users.js").read_text(encoding="utf-8")
    academic_js = (ROOT / "static" / "js" / "reitoria_academico.js").read_text(encoding="utf-8")
    router = (ROOT / "admin_router.py").read_text(encoding="utf-8")

    assert 'href="/reitoria/academico"' in admin_html
    assert 'reitoria_academic.js' not in admin_html
    assert 'data-univc-academic-charts.js' not in admin_html
    assert 'data-reitoria-page="usuarios"' in admin_html
    assert "get('secao') || 'usuarios'" in admin_js
    assert '@router.get("/reitoria/academico"' in router
    assert 'name="reitoria_academico.html"' in router
    assert 'href="/reitoria"' in academic_html
    assert 'app.css' in academic_html and 'ui-v2.css' in academic_html
    assert 'data-academic-section="nps-institution"' in academic_html
    assert 'data-academic-section="results"' in academic_html
    assert "history.replaceState(null,'',`/reitoria/academico?secao=" in academic_js


def test_reitoria_academic_sections_follow_dtnh_dcs_information_architecture():
    html = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    assert 'NPS da instituição' in html
    assert 'NPS dos cursos' in html
    assert 'NPS da instituição · docentes' in html
    assert 'Avaliação docente' in html
    assert 'Aprovação e notas' in html
    assert 'id="academic-nps-institution"' in html
    assert 'id="academic-nps-course"' in html
    assert 'id="academic-nps-faculty"' in html
    assert 'id="academic-faculty"' in html
    assert 'id="academic-results"' in html


def test_reitoria_academic_navigation_does_not_use_hash_scroll():
    html = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "reitoria_academico.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "reitoria.css").read_text(encoding="utf-8")
    assert 'href="#nps"' not in html
    assert 'href="#notas"' not in html
    assert 'data-academic-section=' in html
    assert 'location.hash' not in js
    assert 'html{scroll-behavior:auto}' in css


def test_dm_split_cohort_hotfix_is_present():
    parser = (ROOT / "dm_sei_parser.py").read_text(encoding="utf-8")
    assert "def _merge_split_cohort_blocks(" in parser
    assert "O SEI dividiu esta turma" in parser
    assert "dados conflitantes" in parser


def test_dm_real_uploaded_report_can_be_parsed_when_fixture_is_available():
    candidates = [
        Path('/mnt/data/1790874693805(1).xlsx'),
        Path('/mnt/data/1790874693805.xlsx'),
    ]
    source = next((path for path in candidates if path.exists()), None)
    if source is None:
        return
    report = parse_dm_sei_workbook(source)
    cohort = next(item for item in report.cohorts if item.key == 'CTE:17')
    assert cohort.student_count == 51
    assert len(report.cohorts) == 13
    assert len(report.students) == 433
