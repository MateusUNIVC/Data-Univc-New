from pathlib import Path


def test_faculty_import_uses_only_backend_candidates_and_allows_multiple_courses():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")

    assert "candidateCourseSelectionHtml" in js
    assert "entry.course_match?.candidate_courses" in js
    assert "data-course-candidate-path" in js
    assert "Marque um ou mais" in js
    assert "preview.available_courses" not in js
    assert "Selecione o curso principal" not in js
    assert "Turmas compartilhadas · opcional" not in js

    # Um ou mais candidatos marcados viram um único contexto: o primeiro apenas
    # ancora o modelo legado e os demais são escopos, sem duplicar respostas.
    assert "resolutions[path] = courseIds[0]" in js
    assert "sharedScopes[path] = courseIds.slice(1)" in js


def test_backend_restricts_shared_scopes_to_preview_candidates():
    root = Path(__file__).resolve().parents[1]
    router = (root / "survey_router.py").read_text(encoding="utf-8")
    assert "invalid_candidates = normalized_ids - candidate_map.get(source_path, set())" in router
    assert "fora dos candidatos detectados" in router
