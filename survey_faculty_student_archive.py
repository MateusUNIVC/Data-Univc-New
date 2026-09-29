from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from survey_archive import MAX_UNCOMPRESSED_BYTES, sha256_file, validate_member_name
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import is_graduation_unit
from survey_faculty_student_parser import (
    faculty_source_path_metadata,
    parse_faculty_student_workbook,
)
from survey_parser import normalize_key


MAX_FACULTY_ARCHIVE_FILES = 2000


@dataclass
class FacultyStudentInspectedEntry:
    internal_path: str
    source_key: str
    unit_name: str | None
    course_name: str
    modality: str
    teacher_name: str
    discipline_name: str
    class_code: str
    respondent_count: int
    question_count: int
    survey_title: str | None
    questionnaire_name: str | None
    period_start: str | None
    period_end: str | None
    semester_suggested: str | None
    graduation_unit: bool
    parse_error: str | None = None
    path_unit_name: str | None = None
    scope_validation: str = "content"
    unit_scope_mismatch: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _entry(parsed: ParsedFacultyContext) -> FacultyStudentInspectedEntry:
    path_meta = faculty_source_path_metadata(parsed.source_path)
    path_unit = path_meta.get("unit_name")
    path_scope = is_graduation_unit(path_unit) if path_unit else None
    content_scope = is_graduation_unit(parsed.unit_name)
    return FacultyStudentInspectedEntry(
        internal_path=parsed.source_path,
        source_key=parsed.source_key,
        unit_name=parsed.unit_name,
        course_name=parsed.course_name,
        modality=parsed.modality,
        teacher_name=parsed.teacher_name,
        discipline_name=parsed.discipline_name,
        class_code=parsed.class_code or "",
        respondent_count=parsed.respondent_count,
        question_count=len(parsed.questions),
        survey_title=parsed.survey_title,
        questionnaire_name=parsed.questionnaire_name,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        semester_suggested=parsed.semester_suggested,
        graduation_unit=content_scope,
        path_unit_name=path_unit,
        scope_validation="content",
        unit_scope_mismatch=(path_scope is not None and path_scope != content_scope),
    )


def _clearly_outside_path_unit(unit_name: str | None) -> bool:
    """Retorna True apenas para unidades que o caminho identifica sem ambiguidade.

    O nome de pasta do SEI não é fonte de verdade: ele pode perder acentos,
    hífens e até separadores (como ``SAO_MATEUSES``). Por isso o fast reject é
    conservador. Pastas desconhecidas são abertas e validadas pelo conteúdo do
    XLSX em vez de serem descartadas antecipadamente.
    """

    if not unit_name or is_graduation_unit(unit_name):
        return False
    key = normalize_key(unit_name)
    explicit_outside_markers = (
        "semipresencial",
        "polo",
        "cursos tecnicos",
        "curso tecnico",
        "pos graduacao",
        "posgraduacao",
    )
    return any(marker in key for marker in explicit_outside_markers)


def _path_rejection(internal_path: str) -> FacultyStudentInspectedEntry | None:
    """Evita abrir XLSX somente quando o caminho prova que está fora do escopo.

    Retorna ``None`` para Graduação São Mateus e também para caminhos ambíguos;
    nesses casos o XLSX é aberto e a unidade presente no conteúdo decide.
    """

    meta = faculty_source_path_metadata(internal_path)
    unit = meta.get("unit_name")
    if not unit or not _clearly_outside_path_unit(unit):
        return None
    return FacultyStudentInspectedEntry(
        internal_path=internal_path,
        source_key=internal_path[:500],
        unit_name=unit,
        course_name=str(meta.get("course_name") or ""),
        modality="",
        teacher_name=str(meta.get("teacher_name") or ""),
        discipline_name=str(meta.get("discipline_name") or ""),
        class_code="",
        respondent_count=0,
        question_count=0,
        survey_title=None,
        questionnaire_name=None,
        period_start=None,
        period_end=None,
        semester_suggested=None,
        graduation_unit=False,
        parse_error="Unidade fora do escopo: somente Graduação São Mateus é aceita.",
        path_unit_name=unit,
        scope_validation="path_fast_reject",
    )


def inspect_faculty_student_file(path: Path) -> tuple[list[FacultyStudentInspectedEntry], dict]:
    suffix = path.suffix.casefold()
    entries: list[FacultyStudentInspectedEntry] = []
    parse_errors = 0
    skipped_by_path = 0
    opened_xlsx = 0

    if suffix == ".xlsx":
        try:
            parsed = parse_faculty_student_workbook(path, source_path=path.name)
            entries.append(_entry(parsed))
            opened_xlsx = 1
        except Exception as exc:
            raise ValueError(f"Não foi possível interpretar o XLSX docente: {exc}") from exc
        return entries, {
            "kind": "xlsx",
            "sha256": sha256_file(path),
            "file_count": 1,
            "xlsx_count": 1,
            "report_count": 1,
            "graduation_unit_count": sum(1 for item in entries if item.graduation_unit),
            "outside_unit_count": sum(1 for item in entries if not item.graduation_unit),
            "parse_error_count": 0,
            "opened_xlsx_count": opened_xlsx,
            "content_validated_count": opened_xlsx,
            "skipped_without_opening": 0,
            "unit_scope_mismatch_count": sum(1 for item in entries if item.unit_scope_mismatch),
            "audience": "faculty_student",
        }

    if suffix != ".zip":
        raise ValueError("Envie um arquivo .zip ou .xlsx")

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FACULTY_ARCHIVE_FILES:
            raise ValueError(
                f"ZIP possui {len(infos)} arquivos; o limite da Avaliação Docente é "
                f"{MAX_FACULTY_ARCHIVE_FILES}."
            )
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("ZIP excede o limite de tamanho descompactado.")

        xlsx_count = 0
        for info in infos:
            validate_member_name(info.filename)
            if info.is_dir() or not info.filename.casefold().endswith(".xlsx"):
                continue
            xlsx_count += 1

            rejected = _path_rejection(info.filename)
            if rejected is not None:
                entries.append(rejected)
                skipped_by_path += 1
                continue

            try:
                opened_xlsx += 1
                parsed = parse_faculty_student_workbook(
                    archive.read(info.filename), source_path=info.filename
                )
                entries.append(_entry(parsed))
            except Exception as exc:
                parse_errors += 1
                meta = faculty_source_path_metadata(info.filename)
                entries.append(
                    FacultyStudentInspectedEntry(
                        internal_path=info.filename,
                        source_key=info.filename[:500],
                        unit_name=meta.get("unit_name"),
                        course_name=str(meta.get("course_name") or ""),
                        modality="",
                        teacher_name=str(meta.get("teacher_name") or ""),
                        discipline_name=str(meta.get("discipline_name") or ""),
                        class_code="",
                        respondent_count=0,
                        question_count=0,
                        survey_title=None,
                        questionnaire_name=None,
                        period_start=None,
                        period_end=None,
                        semester_suggested=None,
                        graduation_unit=False,
                        parse_error=str(exc),
                        path_unit_name=meta.get("unit_name"),
                        scope_validation="content_error",
                    )
                )

    entries.sort(
        key=lambda item: (
            not item.graduation_unit,
            item.course_name.casefold(),
            item.teacher_name.casefold(),
            item.discipline_name.casefold(),
            item.internal_path.casefold(),
        )
    )
    return entries, {
        "kind": "zip",
        "sha256": sha256_file(path),
        "file_count": len(infos),
        "xlsx_count": xlsx_count,
        "report_count": len(entries),
        "graduation_unit_count": sum(1 for item in entries if item.graduation_unit),
        "outside_unit_count": sum(1 for item in entries if not item.graduation_unit),
        "parse_error_count": parse_errors,
        "opened_xlsx_count": opened_xlsx,
        "content_validated_count": opened_xlsx - parse_errors,
        "skipped_without_opening": skipped_by_path,
        "unit_scope_mismatch_count": sum(1 for item in entries if item.unit_scope_mismatch),
        "audience": "faculty_student",
    }


def read_selected_faculty_student_contexts(
    path: Path,
    selected_paths: list[str],
) -> list[ParsedFacultyContext]:
    selected = list(dict.fromkeys(selected_paths))
    if path.suffix.casefold() == ".xlsx":
        parsed = parse_faculty_student_workbook(path, source_path=path.name)
        if parsed.source_path not in selected:
            return []
        if not is_graduation_unit(parsed.unit_name):
            raise ValueError("O XLSX selecionado não pertence à Graduação São Mateus.")
        return [parsed]

    out: list[ParsedFacultyContext] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = set(selected) - names
        if missing:
            raise ValueError(f"Arquivos selecionados não existem no ZIP: {sorted(missing)[:3]}")
        for internal_path in selected:
            validate_member_name(internal_path)
            if not internal_path.casefold().endswith(".xlsx"):
                continue
            rejected = _path_rejection(internal_path)
            if rejected is not None:
                raise ValueError(
                    f"{internal_path}: unidade fora do escopo; somente Graduação São Mateus é aceita."
                )
            parsed = parse_faculty_student_workbook(
                archive.read(internal_path), source_path=internal_path
            )
            # A validação final é sempre pelo conteúdo do XLSX. O caminho serve
            # apenas como otimização conservadora e nunca autoriza uma unidade.
            if not is_graduation_unit(parsed.unit_name):
                raise ValueError(
                    f"{internal_path}: unidade fora do escopo; somente Graduação São Mateus é aceita."
                )
            out.append(parsed)
    return out
