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
        ROOT / "static" / "js" / "reitoria_academico.js",
        ROOT / "templates" / "reitoria_academico.html",
        ROOT / "static" / "css" / "reitoria-academico.css",
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
    admin_template = (ROOT / "templates" / "reitoria.html").read_text(encoding="utf-8")
    template = (ROOT / "templates" / "reitoria_academico.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static" / "js" / "reitoria_academico.js").read_text(encoding="utf-8")
    backend = (ROOT / "reitoria_academic.py").read_text(encoding="utf-8")
    router = (ROOT / "reitoria_academic_router.py").read_text(encoding="utf-8")
    admin_router = (ROOT / "admin_router.py").read_text(encoding="utf-8")

    if 'href="/reitoria/academico"' not in admin_template:
        raise SystemExit("Reitoria admin does not link to the dedicated academic page")
    if 'reitoria_academico.js' in admin_template or 'data-univc-academic-charts.js' in admin_template:
        raise SystemExit("Reitoria admin must not load academic JavaScript")
    if 'data-reitoria-page="usuarios"' not in admin_template:
        raise SystemExit("Reitoria admin users surface missing")

    required_template = [
        '/static/css/app.css', '/static/css/ui-v2.css', '/static/css/reitoria-academico.css',
        'data-academic-section="nps-institution"', 'data-academic-section="nps-course"',
        'data-academic-section="nps-faculty"', 'data-academic-section="faculty"',
        'data-academic-section="results"', 'id="reitoriaAcademicDirectorate"',
        'id="reitoriaKpiApproval"', 'id="reitoriaChartNpsCourses"',
        'id="reitoriaChartNpsInstitutionCourses"', 'href="/reitoria"',
        'data-combobox-placeholder="Buscar curso..."',
        'data-combobox-placeholder="Buscar disciplina..."',
    ]
    missing_template = [token for token in required_template if token not in template]
    if missing_template:
        raise SystemExit("Reitoria academic template tokens missing: " + ", ".join(missing_template))
    if 'href="#nps"' in template or 'href="#notas"' in template:
        raise SystemExit("Reitoria academic navigation reverted to hash scrolling")

    required_frontend = [
        "/api/reitoria/academic/filters", "/api/reitoria/academic/overview",
        "DataUnivcAcademicCharts", "Todas · UNIVC", "function navigate(section)",
        "/reitoria/academico?secao=",
        "searchableSelect?.attach($('#reitoriaAcademicCourse'))",
        "searchableSelect?.attach($('#reitoriaAcademicDiscipline'))",
    ]
    missing_frontend = [token for token in required_frontend if token not in frontend]
    if missing_frontend:
        raise SystemExit("Reitoria academic frontend tokens missing: " + ", ".join(missing_frontend))
    if 'location.hash' in frontend:
        raise SystemExit("Reitoria academic frontend must not use location.hash navigation")
    if '@router.get("/reitoria/academico"' not in admin_router or 'name="reitoria_academico.html"' not in admin_router:
        raise SystemExit("Dedicated Reitoria academic page route is missing")

    required_backend = [
        "class ReitoriaAcademicService", "_projection_nps_history", "_nps_institution_course_comparison",
        "_faculty_summary", "_result_payload", "approved_count", "finalized_count",
    ]
    missing_backend = [token for token in required_backend if token not in backend]
    if missing_backend:
        raise SystemExit("Reitoria academic backend tokens missing: " + ", ".join(missing_backend))
    shared_charts = (ROOT / "static" / "js" / "data-univc-academic-charts.js").read_text(encoding="utf-8")
    academic_index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    required_shared = ["academic-nps-distribution", "chart-hover-card hidden", "Respondentes", "Promotores"]
    missing_shared = [token for token in required_shared if token not in shared_charts]
    if missing_shared:
        raise SystemExit("Shared academic chart contract missing: " + ", ".join(missing_shared))
    if "data-univc-academic-charts.js" not in academic_index:
        raise SystemExit("DTNH/DCS do not load the shared academic chart renderer")

    if "Depends(require_fresh_reitoria)" not in router:
        raise SystemExit("Reitoria academic endpoints are not protected by require_fresh_reitoria")



def verify_dm_split_cohort_hotfix() -> None:
    parser = (ROOT / "dm_sei_parser.py").read_text(encoding="utf-8")
    required = [
        "def _merge_split_cohort_blocks(",
        "O SEI dividiu esta turma",
        "dados conflitantes",
        "cohorts, students, merge_warnings = _merge_split_cohort_blocks",
    ]
    missing = [token for token in required if token not in parser]
    if missing:
        raise SystemExit("DM split-cohort hotfix missing: " + ", ".join(missing))


def verify_dm_queue_foundation() -> None:
    router = (ROOT / "dm_router.py").read_text(encoding="utf-8")
    template = (ROOT / "templates" / "dm.html").read_text(encoding="utf-8")
    frontend = (ROOT / "static" / "js" / "dm.js").read_text(encoding="utf-8")

    commit_start = router.index('async def dm_sei_commit(')
    commit_end = router.index('@router.post("/api/dm/demo/reset")', commit_start)
    commit_body = router[commit_start:commit_end]
    if "lookup_student_course_dates" in commit_body:
        raise SystemExit("DM roster commit reverted to inline student-by-student SEI lookup")
    required_commit = [
        '"deferred": True',
        "evitar timeout 504",
        '"credentials_persisted": False',
    ]
    missing_commit = [token for token in required_commit if token not in commit_body]
    if missing_commit:
        raise SystemExit("DM queue foundation markers missing: " + ", ".join(missing_commit))
    if 'id="seiCheckStudentDates"' in template:
        raise SystemExit("DM preview still exposes inline date enrichment checkbox")
    if 'id="seiStudentDatesDeferredNotice"' not in template:
        raise SystemExit("DM deferred student-date notice missing")
    required_frontend = [
        "consultar_datas_alunos: false",
        'id="seiRefreshSyncedCohorts"',
        "openSeiRefreshModal({cohortIds:state.seiLastSelectedCohortIds})",
    ]
    missing_frontend = [token for token in required_frontend if token not in frontend]
    if missing_frontend:
        raise SystemExit("DM queue foundation frontend markers missing: " + ", ".join(missing_frontend))


def verify_dm_persistent_batch_queue() -> None:
    router = (ROOT / "dm_router.py").read_text(encoding="utf-8")
    repository = (ROOT / "dm_repository.py").read_text(encoding="utf-8")
    models = (ROOT / "models.py").read_text(encoding="utf-8")
    sei = (ROOT / "sei_student_dates.py").read_text(encoding="utf-8")
    frontend = (ROOT / "static" / "js" / "dm.js").read_text(encoding="utf-8")
    migration = (ROOT / "database" / SCHEMA_MIGRATION).read_text(encoding="utf-8")

    required_router = [
        'DM_SEI_REFRESH_BATCH_SIZE',
        'DM_SEI_REFRESH_BATCH_BUDGET_SECONDS',
        '@router.post("/api/dm/sei/refresh-runs")',
        '@router.get("/api/dm/sei/refresh-runs/{run_id}")',
        '@router.post("/api/dm/sei/refresh-runs/{run_id}/batch")',
        'len(targets) > DM_SEI_REFRESH_BATCH_SIZE',
    ]
    missing = [token for token in required_router if token not in router]
    if missing:
        raise SystemExit("DM persistent queue router markers missing: " + ", ".join(missing))

    required_repository = [
        'create_sei_student_refresh_run', 'claim_sei_student_refresh_batch',
        'finish_sei_student_refresh_batch', 'release_sei_student_refresh_batch',
    ]
    missing = [token for token in required_repository if token not in repository]
    if missing:
        raise SystemExit("DM persistent queue repository markers missing: " + ", ".join(missing))

    for token in ('class DmSeiStudentRefreshRun', 'class DmSeiStudentRefreshItem'):
        if token not in models:
            raise SystemExit(f"DM persistent queue model missing: {token}")
    for token in ('max_seconds', 'request_timeout_seconds', 'deferred_student_ids'):
        if token not in sei:
            raise SystemExit(f"DM bounded SEI lookup marker missing: {token}")
    for token in ('/api/dm/sei/refresh-runs', 'while (run && !terminal.has(run.status)', 'Cada lote é salvo antes do próximo começar'):
        if token not in frontend:
            raise SystemExit(f"DM batch frontend marker missing: {token}")
    if 'dm_sei_student_refresh_runs' not in migration or 'dm_sei_student_refresh_items' not in migration:
        raise SystemExit("DM queue migration does not create both queue tables")
    if 'password' in migration.lower() or 'senha' in migration.lower():
        raise SystemExit("DM queue migration must never persist SEI credentials")

def main() -> int:
    verify_critical_release_files()
    verify_academic_bootstrap_helpers()
    verify_directorate_isolation_guards()
    verify_reitoria_academic_overview()
    verify_dm_split_cohort_hotfix()
    verify_dm_queue_foundation()
    verify_dm_persistent_batch_queue()

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
