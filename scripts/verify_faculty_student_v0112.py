from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
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
from survey_faculty_student_archive import inspect_faculty_student_file
from survey_repository import SurveyRepository


def _repo(directorate_code: str):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    directorate = Directorate(code=directorate_code, name=directorate_code, active=True)
    db.add(directorate)
    db.flush()
    for name in COURSES_BY_DIRECTORATE[directorate_code]:
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
        directorate_code=directorate_code,
        directorate_name=directorate_code,
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=directorate.id,
        directorate_code=directorate_code,
        directorate_name=directorate_code,
        can_write=True,
        is_home=True,
    )
    return db, SurveyRepository(db, scope)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida ingestão e identidade acadêmica da Avaliação Docente v0.11.2 sem persistir dados."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--directorate", choices=("DTNH", "DCS"), required=True)
    args = parser.parse_args()

    entries, meta = inspect_faculty_student_file(args.file)
    db, repo = _repo(args.directorate)
    try:
        statuses = Counter()
        candidate_counts = Counter()
        for entry in entries:
            if not entry.graduation_unit or entry.parse_error:
                statuses["outside_or_invalid"] += 1
                continue
            match = repo.match_course(entry.course_name, entry.modality)
            if match.get("matched"):
                statuses["matched"] += 1
            elif match.get("resolution_required"):
                statuses["resolution_required"] += 1
                candidate_counts[tuple(match.get("candidates") or [])] += 1
            else:
                statuses["out_of_scope"] += 1
        print(json.dumps({
            "meta": meta,
            "directorate": args.directorate,
            "identity_status": dict(statuses),
            "resolution_candidate_groups": {
                " | ".join(key): value for key, value in candidate_counts.items()
            },
        }, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
