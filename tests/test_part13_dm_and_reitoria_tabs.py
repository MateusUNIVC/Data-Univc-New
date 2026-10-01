from __future__ import annotations

from pathlib import Path

from dm_sei_parser import parse_dm_sei_workbook

ROOT = Path(__file__).resolve().parents[1]


def test_reitoria_academic_is_split_into_dedicated_tabs_and_admin_is_separate():
    html = (ROOT / "templates" / "reitoria.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "admin_users.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "reitoria.css").read_text(encoding="utf-8")

    for target in ("nps", "avaliacao-docente", "notas", "visao", "usuarios", "auditoria"):
        assert f'data-reitoria-page="{target}"' in html
    assert 'Painel acadêmico' in html
    assert 'Administração' in html
    assert 'reitoria-academic-tabs' in html
    assert "academicTargets = new Set(['nps', 'avaliacao-docente', 'notas'])" in js
    assert "pages.forEach(page => page.classList.toggle('active'" in js
    assert '.reitoria-page{display:none}' in css
    assert '.reitoria-page.active{display:block}' in css


def test_reitoria_nps_tab_has_only_nps_family_and_results_are_separate():
    html = (ROOT / "templates" / "reitoria.html").read_text(encoding="utf-8")
    nps = html.split('<section id="nps"', 1)[1].split('<section id="avaliacao-docente"', 1)[0]
    faculty = html.split('<section id="avaliacao-docente"', 1)[1].split('<section id="notas"', 1)[0]
    results = html.split('<section id="notas"', 1)[1].split('<section id="visao"', 1)[0]

    assert 'NPS da Instituição · Alunos' in nps
    assert 'NPS da Instituição · Docentes' in nps
    assert 'NPS por curso' in nps
    assert 'Evolução da taxa de aprovação' not in nps
    assert 'Avaliação do Professor pelo Aluno' in faculty
    assert 'Notas e Aprovação' in results
    assert 'Evolução da média das notas' in results


def test_reitoria_nps_hides_discipline_filter_but_other_academic_tabs_keep_it():
    js = (ROOT / "static" / "js" / "reitoria_academic.js").read_text(encoding="utf-8")
    assert "classList.toggle('hidden', target==='nps')" in js
    assert "renderActivePage(target)" in js


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
