from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from academic_catalog import COURSES_BY_DIRECTORATE
from database import Base
from models import Course, Directorate
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
        email="verify@univc.edu.br",
        full_name="Verifier",
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
    return db, SurveyRepository(db, scope)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida a API analitica da Avaliacao Docente v0.11.3 em banco temporario."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--directorate", choices=("DTNH", "DCS"), required=True)
    parser.add_argument("--semester", default="2026-SEM1")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    entries, meta = inspect_faculty_student_file(args.file)
    db, repo = _repo(args.directorate)
    try:
        selected: list[str] = []
        resolution_required = 0
        for entry in entries:
            if not entry.graduation_unit or entry.parse_error:
                continue
            match = repo.match_course(entry.course_name, entry.modality)
            if match.get("matched"):
                selected.append(entry.internal_path)
            elif match.get("resolution_required"):
                resolution_required += 1
            if len(selected) >= max(1, args.limit):
                break

        if not selected:
            raise SystemExit("Nenhum contexto automaticamente elegivel para o recorte informado.")
        contexts = read_selected_faculty_student_contexts(args.file, selected)
        imported = repo.import_faculty_contexts(
            sha256=meta["sha256"],
            source_filename=args.file.name,
            source_kind=meta["kind"],
            contexts=contexts,
            semester_override=args.semester,
            origin="manual",
        )
        overview = repo.faculty_analytics_overview(semester=args.semester)
        questions = repo.faculty_analytics_questions(semester=args.semester)
        payload = {
            "source_meta": meta,
            "directorate": args.directorate,
            "sample_contexts": len(contexts),
            "resolution_required_seen": resolution_required,
            "imported_contexts": len(imported["imported_contexts"]),
            "overview": overview["summary"],
            "questions": [
                {
                    "position": item["position"],
                    "scope": item["analytical_scope"],
                    "scale": item["favorability"]["scale"],
                    "mapping_complete": item["favorability"]["mapping_complete"],
                }
                for item in questions["items"]
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        if not overview["summary"]["favorability"]["mapping_complete"]:
            raise SystemExit("Ha categoria nao mapeada nas perguntas do docente.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
