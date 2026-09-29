from __future__ import annotations

from pathlib import Path

import release_info

ROOT = Path(__file__).resolve().parents[1]


def test_reconciled_release_metadata():
    assert release_info.APP_VERSION == "0.13.0"
    assert release_info.SCHEMA_VERSION == 48


def test_academic_v01167_student_classification_is_present():
    source = (ROOT / "repository.py").read_text(encoding="utf-8")
    assert '"alunos_sem_classificacao"' in source
    assert '"alunos_com_resultado_pendente"' in source
    assert '"criterio_reprovado"' in source
    assert "approved_count == 0" in source


def test_academic_v01166_v01167_assets_and_tests_are_present():
    expected = [
        "docs/ACADEMIC_RESULTS_SEI_COMPAT_v01166.md",
        "docs/ACADEMIC_RESULTS_STUDENT_CLASSIFICATION_v01167.md",
        "scripts/verify_academic_results_v01166.py",
        "scripts/verify_academic_results_v01167.py",
        "tests/test_academic_results_v01166.py",
        "tests/test_academic_results_v01167.py",
    ]
    for rel in expected:
        assert (ROOT / rel).exists(), rel


def test_dpe_legacy_lockout_is_still_present_after_academic_merge():
    for rel in ("dpe_excel_parser.py", "dpe_excel_builder.py", "static/js/dpe_finance.js"):
        assert not (ROOT / rel).exists()
    active = (ROOT / "templates/dpe.html").read_text(encoding="utf-8")
    for token in ("DPE-01", "DPE-02", "DPE-03"):
        assert token not in active
