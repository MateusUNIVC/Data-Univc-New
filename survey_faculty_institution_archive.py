from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from survey_archive import (
    MAX_ARCHIVE_FILES,
    MAX_UNCOMPRESSED_BYTES,
    sha256_file,
    validate_member_name,
)
from survey_faculty_institution_models import ParsedFacultyInstitutionWorkbook
from survey_faculty_institution_parser import parse_faculty_institution_workbook


@dataclass
class FacultyInstitutionInspectedEntry:
    internal_path: str
    unit_name: str | None
    respondent_count: int
    question_count: int
    nps_candidate_count: int
    survey_title: str | None
    questionnaire_name: str | None
    period_start: str | None
    period_end: str | None
    semester_suggested: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _entry(parsed: ParsedFacultyInstitutionWorkbook) -> FacultyInstitutionInspectedEntry:
    return FacultyInstitutionInspectedEntry(
        internal_path=parsed.source_path,
        unit_name=parsed.unit_name,
        respondent_count=parsed.respondent_count,
        question_count=len(parsed.questions),
        nps_candidate_count=sum(1 for q in parsed.questions if q.nps_candidate),
        survey_title=parsed.survey_title,
        questionnaire_name=parsed.questionnaire_name,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        semester_suggested=parsed.semester_suggested,
    )


def inspect_faculty_institution_file(path: Path) -> tuple[list[FacultyInstitutionInspectedEntry], dict]:
    suffix = path.suffix.casefold()
    entries: list[FacultyInstitutionInspectedEntry] = []

    if suffix == ".xlsx":
        parsed = parse_faculty_institution_workbook(path, source_path=path.name)
        entries.append(_entry(parsed))
        return entries, {
            "kind": "xlsx",
            "sha256": sha256_file(path),
            "file_count": 1,
            "xlsx_count": 1,
            "report_count": 1,
            "audience": "faculty",
        }

    if suffix != ".zip":
        raise ValueError("Envie um arquivo .zip ou .xlsx")

    xlsx_count = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError("ZIP possui arquivos demais para o limite de segurança.")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("ZIP excede o limite de tamanho descompactado.")
        for info in infos:
            validate_member_name(info.filename)
            if info.is_dir() or not info.filename.casefold().endswith(".xlsx"):
                continue
            xlsx_count += 1
            parsed = parse_faculty_institution_workbook(
                archive.read(info.filename), source_path=info.filename
            )
            entries.append(_entry(parsed))

    entries.sort(key=lambda item: item.internal_path.casefold())
    return entries, {
        "kind": "zip",
        "sha256": sha256_file(path),
        "file_count": len(infos),
        "xlsx_count": xlsx_count,
        "report_count": len(entries),
        "audience": "faculty",
    }


def read_selected_faculty_institution_workbooks(
    path: Path,
    selected_paths: list[str],
) -> list[ParsedFacultyInstitutionWorkbook]:
    selected = set(selected_paths)
    if path.suffix.casefold() == ".xlsx":
        parsed = parse_faculty_institution_workbook(path, source_path=path.name)
        return [parsed] if parsed.source_path in selected else []

    out: list[ParsedFacultyInstitutionWorkbook] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = selected - names
        if missing:
            raise ValueError(f"Arquivos selecionados não existem no ZIP: {sorted(missing)[:3]}")
        for internal_path in selected_paths:
            validate_member_name(internal_path)
            if not internal_path.casefold().endswith(".xlsx"):
                continue
            out.append(
                parse_faculty_institution_workbook(
                    archive.read(internal_path), source_path=internal_path
                )
            )
    return out
