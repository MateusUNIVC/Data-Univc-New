from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from survey_faculty_student_archive import inspect_faculty_student_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida a ingestão da Avaliação Docente v0.11.1 sem persistir dados."
    )
    parser.add_argument("file", type=Path, help="ZIP ou XLSX exportado pelo SEI")
    parser.add_argument("--expect-graduation", type=int)
    parser.add_argument("--expect-outside", type=int)
    args = parser.parse_args()

    entries, meta = inspect_faculty_student_file(args.file)
    graduation = [entry for entry in entries if entry.graduation_unit]
    payload = {
        "meta": meta,
        "graduation_question_counts": dict(Counter(entry.question_count for entry in graduation)),
        "graduation_questionnaires": dict(Counter(entry.questionnaire_name for entry in graduation)),
        "graduation_semester_suggestions": {
            str(key): value
            for key, value in Counter(entry.semester_suggested for entry in graduation).items()
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    if args.expect_graduation is not None and meta["graduation_unit_count"] != args.expect_graduation:
        raise SystemExit(
            f"Esperado Graduação={args.expect_graduation}, encontrado={meta['graduation_unit_count']}"
        )
    if args.expect_outside is not None and meta["outside_unit_count"] != args.expect_outside:
        raise SystemExit(
            f"Esperado fora do escopo={args.expect_outside}, encontrado={meta['outside_unit_count']}"
        )
    if meta["parse_error_count"]:
        raise SystemExit(f"Foram encontrados {meta['parse_error_count']} erros de parser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
