from __future__ import annotations

import argparse
import json
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from academic_catalog import COURSES_BY_DIRECTORATE
from database import Base
from models import Course, Directorate, Goal
from security import AuthorizationContext, DirectorateScope
from survey_faculty_student_archive import inspect_faculty_student_file, read_selected_faculty_student_contexts
from survey_repository import SurveyRepository


def _repo(code: str):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code=code, name=code, active=True)
    db.add(directorate)
    db.flush()
    for name in COURSES_BY_DIRECTORATE[code]:
        db.add(Course(
            directorate_id=directorate.id,
            name=name,
            modality="Presencial",
            active=True,
            valid_from="2026-01",
        ))
    db.commit()
    user = AuthorizationContext(
        user_id=str(uuid.uuid4()),
        email="verify-v0116@univc.edu.br",
        full_name="Verifier v0.11.6",
        role="editor",
        directorate_id=directorate.id,
        directorate_code=code,
        directorate_name=code,
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code=code,
        directorate_name=code,
        can_write=True,
        is_home=True,
    )
    return db, SurveyRepository(db, scope), directorate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida a leitura operacional da Avaliação Docente v0.11.6 com XLSX reais."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--directorate", choices=("DTNH", "DCS"), required=True)
    parser.add_argument("--semester", default="2026-SEM1")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"), pattern="test_faculty_student_v011*.py")
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    if not result.wasSuccessful():
        return 1

    entries, meta = inspect_faculty_student_file(args.file)
    db, repo, directorate = _repo(args.directorate)
    try:
        selected: list[str] = []
        for entry in entries:
            if not entry.graduation_unit or entry.parse_error:
                continue
            match = repo.match_course(entry.course_name, entry.modality)
            if match.get("matched"):
                selected.append(entry.internal_path)
            if len(selected) >= max(1, args.limit):
                break
        if not selected:
            raise SystemExit("Nenhum contexto automaticamente elegível para o recorte informado.")

        contexts = read_selected_faculty_student_contexts(args.file, selected)
        repo.import_faculty_contexts(
            sha256=meta["sha256"],
            source_filename=args.file.name,
            source_kind=meta["kind"],
            contexts=contexts,
            semester_override=args.semester,
            origin="manual",
        )
        db.add(Goal(
            directorate_id=directorate.id,
            indicator_code=f"{args.directorate}-02",
            scope_label="TOTAL",
            valid_from=args.semester,
            target=85,
            attention=75,
            upper_limit=100,
            justification="Meta de verificação v0.11.6",
            metric_version="faculty_favorability_pct_v1",
        ))
        db.commit()

        operational = repo.faculty_analytics_operational_status(semester=args.semester)
        comparison = repo.faculty_analytics_semester_comparison()
        history = repo.faculty_import_history()
        quality = repo.faculty_identity_quality(args.semester)

        payload = {
            "source": {
                "total_reports": len(entries),
                "opened_xlsx_count": meta.get("opened_xlsx_count"),
                "content_validated_count": meta.get("content_validated_count"),
            },
            "sample_contexts": len(contexts),
            "operational": {
                "current_period": operational.get("current_period"),
                "current_value": operational.get("current_value"),
                "goal_status": operational.get("goal_status"),
                "readiness": operational.get("readiness"),
                "coverage": (operational.get("current_summary") or {}).get("favorability", {}).get("classified_coverage_percentage"),
            },
            "comparison_points": len(comparison.get("items") or []),
            "history": {
                "count": history.get("count"),
                "last_imported_by": (history.get("items") or [{}])[0].get("last_imported_by"),
                "import_attempts": (history.get("items") or [{}])[0].get("import_attempts"),
            },
            "quality": {
                "blocking_issue_count": quality.get("blocking_issue_count"),
                "warning_count": quality.get("warning_count"),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

        if operational.get("readiness") not in {"ready", "ready_no_goal"}:
            raise SystemExit("A leitura operacional não ficou pronta no recorte real.")
        if int(quality.get("blocking_issue_count") or 0) != 0:
            raise SystemExit("Há bloqueios estruturais no recorte real de verificação.")
        if not (history.get("items") or [{}])[0].get("last_imported_by"):
            raise SystemExit("A auditoria do lote não identificou o usuário da importação.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
