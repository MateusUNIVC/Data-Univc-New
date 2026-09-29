from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=ROOT, check=True)


def active_template_javascript() -> set[Path]:
    pattern = re.compile(r'''<script\b[^>]*\bsrc=["'](/static/js/[^"'?]+\.js)(?:\?[^"']*)?["']''', re.IGNORECASE)
    referenced: set[Path] = set()
    for template in (ROOT / "templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            referenced.add(ROOT / match.group(1).lstrip("/"))
    return referenced


def main() -> int:
    py_files = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts
    ]
    run("Python compile", [sys.executable, "-m", "py_compile", *py_files])

    js_files = sorted((ROOT / "static" / "js").rglob("*.js"))
    if not js_files:
        raise SystemExit("No JavaScript files found under static/js")

    referenced_js = active_template_javascript()
    missing_references = sorted(path for path in referenced_js if not path.exists())
    if missing_references:
        raise SystemExit(
            "Template JavaScript references missing from disk: "
            + ", ".join(str(path.relative_to(ROOT)) for path in missing_references)
        )

    print(f"\n== JavaScript inventory ==\n{len(js_files)} file(s) under static/js; {len(referenced_js)} referenced by templates")
    for path in js_files:
        run(f"JavaScript syntax: {path.relative_to(ROOT)}", ["node", "--check", str(path.relative_to(ROOT))])

    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    faculty_legacy_tokens = [
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
    ]
    faculty_leftovers = [token for token in faculty_legacy_tokens if token in app_js]
    if faculty_leftovers:
        raise SystemExit("Legacy faculty frontend tokens found: " + ", ".join(faculty_leftovers))

    run("Pytest", [sys.executable, "-m", "pytest", "-q"])

    forbidden_files = [ROOT / "dpe_excel_parser.py", ROOT / "dpe_excel_builder.py", ROOT / "static" / "js" / "dpe_finance.js"]
    leftovers = [str(path.relative_to(ROOT)) for path in forbidden_files if path.exists()]
    if leftovers:
        raise SystemExit("Legacy DPE files unexpectedly present: " + ", ".join(leftovers))

    active_paths = [ROOT / "templates" / "dpe.html", *sorted((ROOT / "static" / "js").glob("dpe*.js"))]
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
    forbidden_tokens = ["DPE-01", "DPE-02", "DPE-03", "Histórico e legado", "Historico e legado"]
    found = [token for token in forbidden_tokens if token in active_text]
    if found:
        raise SystemExit("Legacy DPE frontend tokens found: " + ", ".join(found))

    print("\nRelease checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
