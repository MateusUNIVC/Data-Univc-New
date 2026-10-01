from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release_info import SCHEMA_MIGRATION


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


def verify_critical_release_files() -> None:
    required = [
        ROOT / "dpe_cost_v2.py",
        ROOT / "static" / "js" / "app.js",
        ROOT / "static" / "js" / "faculty-evaluation.js",
        ROOT / "static" / "js" / "data-univc-ui.js",
        ROOT / "static" / "js" / "data-univc-academic-charts.js",
        ROOT / "static" / "js" / "reitoria_academic.js",
        ROOT / "reitoria_academic.py",
        ROOT / "reitoria_academic_router.py",
        ROOT / "database" / SCHEMA_MIGRATION,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Critical release files missing: " + ", ".join(missing))


def verify_academic_bootstrap_helpers() -> None:
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    required_helpers = [
        "renderDirectorateSelector",
        "applyDirectorateUi",
        "fillCourseSelectors",
        "fillResultFilters",
        "fillConfig",
    ]
    missing = [helper for helper in required_helpers if f"function {helper}(" not in app_js]
    if missing:
        raise SystemExit("Academic bootstrap helpers missing: " + ", ".join(missing))



def verify_directorate_isolation_guards() -> None:
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    faculty_js = (ROOT / "static" / "js" / "faculty-evaluation.js").read_text(encoding="utf-8")
    required_app_tokens = [
        "directorateEpoch",
        "function captureDirectorateContext()",
        "function isDirectorateContextCurrent(context)",
        "function clearDirectorateAcademicSurfaces",
        "state.npsDistributionCache = {};",
        "`${state.activeDirectorate || 'GLOBAL'}|${audience}",
        "state.directorateEpoch += 1;",
    ]
    missing_app = [token for token in required_app_tokens if token not in app_js]
    if missing_app:
        raise SystemExit("Directorate isolation guards missing from app.js: " + ", ".join(missing_app))
    required_faculty_tokens = [
        "async function loadFacets(serial = moduleState.loadSerial)",
        "const facetsLoaded = await loadFacets(serial);",
        "clearRenderedState(state.activeDirectorate);",
    ]
    missing_faculty = [token for token in required_faculty_tokens if token not in faculty_js]
    if missing_faculty:
        raise SystemExit("Directorate isolation guards missing from faculty-evaluation.js: " + ", ".join(missing_faculty))



def verify_reitoria_academic_overview() -> None:
    template = (ROOT / "templates" / "reitoria.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static" / "js" / "reitoria_academic.js").read_text(encoding="utf-8")
    backend = (ROOT / "reitoria_academic.py").read_text(encoding="utf-8")
    router = (ROOT / "reitoria_academic_router.py").read_text(encoding="utf-8")
    required_template = [
        'href="#academico"', 'id="academico"', 'id="reitoriaAcademicDirectorate"',
        'id="reitoriaKpiApproval"', 'id="reitoriaChartNpsCourses"',
    ]
    missing_template = [token for token in required_template if token not in template]
    if missing_template:
        raise SystemExit("Reitoria academic template tokens missing: " + ", ".join(missing_template))
    required_frontend = [
        "/api/reitoria/academic/filters", "/api/reitoria/academic/overview",
        "DataUnivcAcademicCharts", "Todas · UNIVC",
    ]
    missing_frontend = [token for token in required_frontend if token not in frontend]
    if missing_frontend:
        raise SystemExit("Reitoria academic frontend tokens missing: " + ", ".join(missing_frontend))
    required_backend = [
        "class ReitoriaAcademicService", "_projection_nps_history", "_faculty_summary",
        "_result_payload", "approved_count", "finalized_count",
    ]
    missing_backend = [token for token in required_backend if token not in backend]
    if missing_backend:
        raise SystemExit("Reitoria academic backend tokens missing: " + ", ".join(missing_backend))
    if "Depends(require_fresh_reitoria)" not in router:
        raise SystemExit("Reitoria academic endpoints are not protected by require_fresh_reitoria")

def main() -> int:
    verify_critical_release_files()
    verify_academic_bootstrap_helpers()
    verify_directorate_isolation_guards()
    verify_reitoria_academic_overview()

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
