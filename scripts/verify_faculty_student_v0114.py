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
        email="verify-v0114@univc.edu.br",
        full_name="Verifier v0.11.4",
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
        description="Valida o fluxo que alimenta a UI da Avaliacao Docente v0.11.4 em banco temporario."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--directorate", choices=("DTNH", "DCS"), required=True)
    parser.add_argument("--semester", default="2026-SEM1")
    parser.add_argument("--limit", type=int, default=12)
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

        filters = repo.faculty_analytics_filters(semester=args.semester)
        overview = repo.faculty_analytics_overview(semester=args.semester)
        questions = repo.faculty_analytics_questions(semester=args.semester)
        teachers = repo.faculty_analytics_teachers(semester=args.semester)
        disciplines = repo.faculty_analytics_disciplines(semester=args.semester)
        comparison = repo.faculty_analytics_semester_comparison()
        quality = repo.faculty_identity_quality(args.semester)
        history = repo.faculty_import_history()

        payload = {
            "source": {
                "kind": meta.get("kind"),
                "total_reports": len(entries),
                "opened_xlsx_count": meta.get("opened_xlsx_count"),
                "content_validated_count": meta.get("content_validated_count"),
            },
            "directorate": args.directorate,
            "semester": args.semester,
            "sample_contexts": len(contexts),
            "resolution_required_seen_before_limit": resolution_required,
            "imported_contexts": len(imported["imported_contexts"]),
            "ui_contract": {
                "matching_contexts": filters.get("matching_contexts"),
                "overview": overview.get("summary"),
                "question_count": len(questions.get("items") or []),
                "teacher_count": len(teachers.get("items") or []),
                "discipline_count": len(disciplines.get("items") or []),
                "semester_points": len(comparison.get("items") or []),
                "import_history_count": history.get("count"),
                "identity_blockers": quality.get("blocking_issue_count"),
                "identity_warnings": quality.get("warning_count"),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

        summary = overview.get("summary") or {}
        favorability = summary.get("favorability") or {}
        if not favorability.get("mapping_complete"):
            raise SystemExit("A UI receberia favorabilidade incompleta por categoria nao mapeada.")
        if int(history.get("count") or 0) != 1:
            raise SystemExit("O historico de importacao nao refletiu o lote persistido.")
        if int(quality.get("blocking_issue_count") or 0) != 0:
            raise SystemExit("A malha de identidade possui bloqueio estrutural no recorte de verificacao.")
        if not questions.get("items"):
            raise SystemExit("A API de perguntas nao retornou itens para a UI.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
