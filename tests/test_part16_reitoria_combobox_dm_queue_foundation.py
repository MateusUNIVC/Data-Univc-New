from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reitoria_course_and_discipline_filters_use_shared_searchable_combobox():
    html = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "reitoria_academico.js").read_text(encoding="utf-8")

    assert 'id="reitoriaAcademicCourse" data-combobox-placeholder="Buscar curso..."' in html
    assert 'id="reitoriaAcademicDiscipline" data-combobox-placeholder="Buscar disciplina..."' in html
    assert "searchableSelect?.attach($('#reitoriaAcademicCourse'))" in js
    assert "searchableSelect?.attach($('#reitoriaAcademicDiscipline'))" in js
    assert "searchableSelect?.sync($('#reitoriaAcademicDiscipline'))" in js


def test_dm_roster_commit_no_longer_runs_student_lookup_inline():
    router = (ROOT / "dm_router.py").read_text(encoding="utf-8")
    start = router.index('async def dm_sei_commit(')
    end = router.index('@router.post("/api/dm/demo/reset")', start)
    commit_body = router[start:end]

    assert "lookup_student_course_dates" not in commit_body
    assert '"deferred": True' in commit_body
    assert "evitar timeout 504" in commit_body
    assert '"credentials_persisted": False' in commit_body

    refresh_start = router.index('async def dm_sei_refresh_students(')
    refresh_end = router.index('@router.post("/api/dm/sei/commit")', refresh_start)
    refresh_body = router[refresh_start:refresh_end]
    assert "lookup_student_course_dates" in refresh_body


def test_dm_ui_makes_student_enrichment_a_separate_step():
    html = (ROOT / "templates" / "dm.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "dm.js").read_text(encoding="utf-8")

    assert 'id="seiCheckStudentDates"' not in html
    assert 'id="seiStudentDatesDeferredNotice"' in html
    assert "Datas e titulação serão atualizadas em uma etapa separada" in html
    assert "consultar_datas_alunos: false" in js
    assert "Sincronizando e consultando alunos" not in js
    assert 'id="seiRefreshSyncedCohorts"' in js
    assert "openSeiRefreshModal({cohortIds:state.seiLastSelectedCohortIds})" in js
