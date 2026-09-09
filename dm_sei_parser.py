from __future__ import annotations

import hashlib
import re
import unicodedata
import warnings as py_warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from dm_catalog import DM_AREAS, DMValidationError, normalize_area, positive_int


class DMSEIParseError(ValueError):
    """Raised when the SEI synthetic roster cannot be interpreted safely."""

    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.details = details or []


@dataclass(slots=True)
class SEIStudentRow:
    area_code: str
    area_name: str
    cohort_number: int
    cohort_raw_label: str
    student_code: str
    student_name: str
    raw_status: str
    mapped_status: str | None
    row_number: int
    review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SEICohortBlock:
    area_code: str
    area_name: str
    cohort_number: int
    raw_label: str
    row_start: int
    declared_total: int | None = None
    student_count: int = 0
    is_test: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.area_code}:{self.cohort_number}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["key"] = self.key
        return payload


@dataclass(slots=True)
class DMSEIReport:
    source_name: str
    source_sha256: str
    sheet_name: str
    unit_name: str | None
    course_filter: str | None
    parsed_at: str
    cohorts: list[SEICohortBlock]
    students: list[SEIStudentRow]
    warnings: list[str]

    def to_dict(self, *, include_students: bool = True) -> dict[str, Any]:
        visible_cohorts = [row.to_dict() for row in self.cohorts]
        payload: dict[str, Any] = {
            "source_name": self.source_name,
            "source_sha256": self.source_sha256,
            "sheet_name": self.sheet_name,
            "unit_name": self.unit_name,
            "course_filter": self.course_filter,
            "parsed_at": self.parsed_at,
            "cohorts": visible_cohorts,
            "warnings": list(self.warnings),
            "summary": {
                "cohort_count": len(self.cohorts),
                "student_count": len(self.students),
                "area_counts": {
                    code: {
                        "cohorts": sum(1 for row in self.cohorts if row.area_code == code),
                        "students": sum(1 for row in self.students if row.area_code == code),
                    }
                    for code in DM_AREAS
                },
                "test_cohort_count": sum(1 for row in self.cohorts if row.is_test),
                "review_student_count": sum(1 for row in self.students if row.review_required),
            },
        }
        if include_students:
            payload["students"] = [row.to_dict() for row in self.students]
        return payload


_TEST_TOKENS = {"teste", "test", "demo", "homologacao", "homolog"}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("º", "").replace("ª", "").replace("°", "")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).casefold().strip()
    return re.sub(r"\s+", " ", text)


def _row_values(ws, row_number: int) -> list[Any]:
    return [ws.cell(row_number, col).value for col in range(1, ws.max_column + 1)]


def _first_nonempty_after(values: list[Any], start_index: int = 0) -> Any:
    for value in values[start_index:]:
        if value not in (None, ""):
            return value
    return None


def _label_value(ws, row_number: int, label: str) -> Any:
    values = _row_values(ws, row_number)
    target = _norm(label)
    for index, value in enumerate(values):
        if _norm(value).rstrip(":") == target.rstrip(":"):
            return _first_nonempty_after(values, index + 1)
    return None


def _find_header_columns(values: list[Any]) -> dict[str, int]:
    headers: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        token = _norm(value)
        if not token:
            continue
        if token in {"matricula", "codigo do aluno", "codigo aluno"}:
            headers["student_code"] = index
        elif token in {"nome do aluno", "aluno", "nome"}:
            headers["student_name"] = index
        elif token in {"situacao", "situacao academica", "status"}:
            headers["status"] = index
        elif token in {"numero", "n", "ordem"}:
            headers["ordinal"] = index
    return headers


def _map_status(value: Any) -> tuple[str | None, bool]:
    raw = str(value or "").strip()
    token = _norm(raw)
    if token in {"ativa", "ativo", "matriculada", "matriculado", "regular"}:
        return "Ativo", False
    if token in {"titulada", "titulado", "concluida", "concluido", "formada", "formado"}:
        return "Titulado", False
    if token in {
        "desligada", "desligado", "cancelada", "cancelado", "evadida", "evadido",
        "transferencia saida", "transferido", "transferida",
    }:
        return "Desligado", False
    if token in {"trancada", "trancado", "matricula trancada", "matricula trancado"}:
        return "Desligado", False
    return None, True


def _parse_cohort_number(raw_label: Any) -> int:
    text = str(raw_label or "").strip()
    match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", text)
    if not match:
        raise DMValidationError(
            "Não foi possível identificar o número da turma no relatório do SEI.",
            {"turma": f"Rótulo recebido: {text or '(vazio)'}."},
        )
    return positive_int(match.group(1), field="turma", required=True) or 0


def _is_test_label(raw_label: Any) -> bool:
    tokens = set(_norm(raw_label).split())
    return bool(tokens & _TEST_TOKENS)


def _area_from_course(course_name: Any) -> tuple[str, str]:
    try:
        return normalize_area(course_name)
    except DMValidationError as exc:
        raise DMSEIParseError(
            "O relatório contém um curso que não corresponde às duas áreas do Mestrado.",
            details=[{"field": "curso", "value": str(course_name or ""), "error": str(exc)}],
        ) from exc


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preferred_sheet(workbook) -> Any:
    for name in workbook.sheetnames:
        token = _norm(name)
        if "alunos por unidade curso turma" in token or "alunosporunidadecursoturma" in token:
            return workbook[name]
    return workbook[workbook.sheetnames[0]]


def parse_dm_sei_workbook(path: str | Path) -> DMSEIReport:
    source = Path(path)
    if not source.exists():
        raise DMSEIParseError("O arquivo do relatório do SEI não foi encontrado.")
    if source.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise DMSEIParseError("O relatório do SEI deve estar em formato XLSX ou XLSM.")

    try:
        # The workbook generated by this legacy report declares an incorrect used
        # range in some versions. Normal mode is intentional: read_only may report
        # max_row=1 even though the file contains hundreds of rows. Some reports
        # also omit the default style declaration; openpyxl can read them safely,
        # so suppress only that known, non-data warning.
        with py_warnings.catch_warnings():
            py_warnings.filterwarnings(
                "ignore",
                message="Workbook contains no default style.*",
                category=UserWarning,
            )
            workbook = load_workbook(source, data_only=True, read_only=False)
    except Exception as exc:
        raise DMSEIParseError("Não foi possível abrir o XLSX gerado pelo SEI.") from exc

    if not workbook.sheetnames:
        raise DMSEIParseError("O XLSX do SEI não possui planilhas.")
    ws = _preferred_sheet(workbook)

    unit_name = _label_value(ws, 3, "Unidade de Ensino")
    course_filter = _label_value(ws, 5, "Curso")
    warnings: list[str] = []
    cohorts: list[SEICohortBlock] = []
    students: list[SEIStudentRow] = []
    current_course: str | None = None
    current_cohort: SEICohortBlock | None = None
    header_columns: dict[str, int] = {}

    for row_number in range(1, ws.max_row + 1):
        values = _row_values(ws, row_number)
        first = _norm(values[0] if values else None)

        if first.rstrip(":") == "curso":
            value = _first_nonempty_after(values, 1)
            if value not in (None, ""):
                current_course = str(value).strip()
            continue

        if first.rstrip(":") == "turma":
            if not current_course:
                warnings.append(f"Linha {row_number}: turma encontrada antes do curso; bloco ignorado.")
                current_cohort = None
                header_columns = {}
                continue
            raw_label = str(_first_nonempty_after(values, 1) or "").strip()
            try:
                area_code, area_name = _area_from_course(current_course)
                cohort_number = _parse_cohort_number(raw_label)
            except (DMSEIParseError, DMValidationError) as exc:
                warnings.append(f"Linha {row_number}: {exc}")
                current_cohort = None
                header_columns = {}
                continue
            current_cohort = SEICohortBlock(
                area_code=area_code,
                area_name=area_name,
                cohort_number=cohort_number,
                raw_label=raw_label,
                row_start=row_number,
                is_test=_is_test_label(raw_label),
            )
            raw_token = _norm(raw_label)
            expected_marker = area_code.casefold()
            if expected_marker not in raw_token.split() and expected_marker not in raw_token:
                current_cohort.warnings.append(
                    f"O rótulo da turma não contém a sigla {area_code}; a área foi definida pelo curso do bloco."
                )
            cohorts.append(current_cohort)
            header_columns = {}
            continue

        detected_headers = _find_header_columns(values)
        if current_cohort and {"student_code", "student_name", "status"}.issubset(detected_headers):
            header_columns = detected_headers
            continue

        if first.startswith("total matriculados turma"):
            if current_cohort:
                declared = _first_nonempty_after(values, 1)
                try:
                    current_cohort.declared_total = int(float(declared)) if declared not in (None, "") else None
                except (TypeError, ValueError):
                    current_cohort.warnings.append(
                        f"Total declarado na linha {row_number} não pôde ser interpretado: {declared!r}."
                    )
                if (
                    current_cohort.declared_total is not None
                    and current_cohort.declared_total != current_cohort.student_count
                ):
                    current_cohort.warnings.append(
                        f"O SEI declarou {current_cohort.declared_total} aluno(s), mas {current_cohort.student_count} linha(s) foram lidas."
                    )
            header_columns = {}
            continue

        if not current_cohort or not header_columns:
            continue

        code = ws.cell(row_number, header_columns["student_code"]).value
        name = ws.cell(row_number, header_columns["student_name"]).value
        raw_status = ws.cell(row_number, header_columns["status"]).value
        code_text = str(code or "").strip()
        name_text = str(name or "").strip()

        # Student lines have a real institutional code and a non-empty name. This
        # avoids treating blank separators, subtotal rows or repeated headers as data.
        if not code_text or not name_text:
            continue
        if _norm(code_text) in {"matricula", "codigo do aluno"}:
            continue
        if not re.search(r"\d", code_text):
            warnings.append(
                f"Linha {row_number}: matrícula sem algarismos ignorada ({code_text!r})."
            )
            continue

        mapped_status, review_required = _map_status(raw_status)
        if review_required:
            warnings.append(
                f"Linha {row_number}: situação do SEI não reconhecida ({str(raw_status or '').strip() or 'vazia'})."
            )
        students.append(
            SEIStudentRow(
                area_code=current_cohort.area_code,
                area_name=current_cohort.area_name,
                cohort_number=current_cohort.cohort_number,
                cohort_raw_label=current_cohort.raw_label,
                student_code=code_text,
                student_name=name_text,
                raw_status=str(raw_status or "").strip(),
                mapped_status=mapped_status,
                row_number=row_number,
                review_required=review_required,
            )
        )
        current_cohort.student_count += 1

    if not cohorts:
        raise DMSEIParseError(
            "Nenhuma turma de Ciência, Tecnologia e Educação ou Saúde e Desigualdade Social foi encontrada no relatório."
        )
    if not students:
        raise DMSEIParseError("Nenhum aluno foi encontrado nos blocos de turmas do relatório do SEI.")

    cohort_keys = [row.key for row in cohorts]
    duplicate_cohorts = sorted({key for key in cohort_keys if cohort_keys.count(key) > 1})
    if duplicate_cohorts:
        raise DMSEIParseError(
            "O relatório contém blocos repetidos para a mesma área e turma.",
            details=[{"cohort_key": key, "error": "Bloco duplicado."} for key in duplicate_cohorts],
        )

    seen_students: dict[str, SEIStudentRow] = {}
    duplicate_students: list[dict[str, Any]] = []
    for row in students:
        key = row.student_code.casefold()
        previous = seen_students.get(key)
        if previous:
            duplicate_students.append(
                {
                    "student_code": row.student_code,
                    "first_row": previous.row_number,
                    "duplicate_row": row.row_number,
                    "first_cohort": f"{previous.area_code}:{previous.cohort_number}",
                    "duplicate_cohort": f"{row.area_code}:{row.cohort_number}",
                }
            )
        else:
            seen_students[key] = row
    if duplicate_students:
        raise DMSEIParseError(
            "O relatório repete uma ou mais matrículas; a sincronização foi bloqueada para evitar trocar alunos de turma indevidamente.",
            details=duplicate_students,
        )

    for cohort in cohorts:
        warnings.extend(f"{cohort.key}: {message}" for message in cohort.warnings)

    return DMSEIReport(
        source_name=source.name,
        source_sha256=_hash_file(source),
        sheet_name=ws.title,
        unit_name=str(unit_name).strip() if unit_name not in (None, "") else None,
        course_filter=str(course_filter).strip() if course_filter not in (None, "") else None,
        parsed_at=datetime.now(timezone.utc).isoformat(),
        cohorts=cohorts,
        students=students,
        warnings=warnings,
    )


def normalize_dm_sei_payload(payload: dict[str, Any]) -> DMSEIReport:
    """Validate a preview payload posted back by an authenticated editor.

    The client is allowed to submit the normalized preview because the user already
    has write permission. Every field is revalidated server-side before persistence.
    """

    try:
        cohort_rows = list(payload.get("cohorts") or [])
        student_rows = list(payload.get("students") or [])
    except AttributeError as exc:
        raise DMSEIParseError("Prévia do SEI inválida.") from exc
    if not cohort_rows or not student_rows:
        raise DMSEIParseError("A prévia do SEI não contém turmas e alunos suficientes para a sincronização.")

    cohorts: list[SEICohortBlock] = []
    keys: set[str] = set()
    for index, raw in enumerate(cohort_rows, start=1):
        try:
            area_code, area_name = normalize_area(raw.get("area_code") or raw.get("area_name"))
            number = positive_int(raw.get("cohort_number"), field="turma", required=True) or 0
        except (AttributeError, DMValidationError) as exc:
            raise DMSEIParseError(f"Turma inválida na posição {index} da prévia.") from exc
        row = SEICohortBlock(
            area_code=area_code,
            area_name=area_name,
            cohort_number=number,
            raw_label=str(raw.get("raw_label") or f"{number}-{area_code}").strip(),
            row_start=int(raw.get("row_start") or 0),
            declared_total=int(raw["declared_total"]) if raw.get("declared_total") not in (None, "") else None,
            student_count=int(raw.get("student_count") or 0),
            is_test=bool(raw.get("is_test", False)),
            warnings=[str(item) for item in (raw.get("warnings") or [])],
        )
        if row.key in keys:
            raise DMSEIParseError(f"A prévia repete a turma {row.key}.")
        keys.add(row.key)
        cohorts.append(row)

    students: list[SEIStudentRow] = []
    student_codes: set[str] = set()
    for index, raw in enumerate(student_rows, start=1):
        try:
            area_code, area_name = normalize_area(raw.get("area_code") or raw.get("area_name"))
            number = positive_int(raw.get("cohort_number"), field="turma", required=True) or 0
        except (AttributeError, DMValidationError) as exc:
            raise DMSEIParseError(f"Aluno inválido na posição {index} da prévia.") from exc
        if f"{area_code}:{number}" not in keys:
            raise DMSEIParseError(
                f"O aluno da posição {index} referencia uma turma ausente ({area_code}:{number})."
            )
        code = str(raw.get("student_code") or "").strip()
        name = str(raw.get("student_name") or "").strip()
        if not code or not name:
            raise DMSEIParseError(f"Matrícula e nome são obrigatórios para o aluno da posição {index}.")
        code_key = code.casefold()
        if code_key in student_codes:
            raise DMSEIParseError(f"A prévia repete a matrícula {code}.")
        student_codes.add(code_key)
        mapped, review = _map_status(raw.get("raw_status") or raw.get("mapped_status"))
        posted_mapped = str(raw.get("mapped_status") or "").strip()
        if posted_mapped in {"Ativo", "Titulado", "Desligado"}:
            mapped = posted_mapped
        elif _norm(posted_mapped) in {"trancado", "trancada"}:
            mapped = "Desligado"
            review = bool(raw.get("review_required", False))
        students.append(
            SEIStudentRow(
                area_code=area_code,
                area_name=area_name,
                cohort_number=number,
                cohort_raw_label=str(raw.get("cohort_raw_label") or f"{number}-{area_code}").strip(),
                student_code=code,
                student_name=name,
                raw_status=str(raw.get("raw_status") or "").strip(),
                mapped_status=mapped,
                row_number=int(raw.get("row_number") or 0),
                review_required=review,
            )
        )

    source_sha = str(payload.get("source_sha256") or "").strip()
    if source_sha and not re.fullmatch(r"[0-9a-fA-F]{64}", source_sha):
        raise DMSEIParseError("Hash do relatório do SEI inválido.")
    return DMSEIReport(
        source_name=str(payload.get("source_name") or "relatorio_sei.xlsx").strip(),
        source_sha256=source_sha.lower(),
        sheet_name=str(payload.get("sheet_name") or "").strip(),
        unit_name=str(payload.get("unit_name") or "").strip() or None,
        course_filter=str(payload.get("course_filter") or "").strip() or None,
        parsed_at=str(payload.get("parsed_at") or datetime.now(timezone.utc).isoformat()),
        cohorts=cohorts,
        students=students,
        warnings=[str(item) for item in (payload.get("warnings") or [])],
    )


def filter_report(
    report: DMSEIReport,
    *,
    exclude_test: bool = True,
    selected_cohort_keys: Iterable[str] | None = None,
) -> DMSEIReport:
    excluded_keys = {row.key for row in report.cohorts if exclude_test and row.is_test}
    selected = {str(key).strip() for key in (selected_cohort_keys or []) if str(key).strip()}
    if selected:
        known = {row.key for row in report.cohorts}
        unknown = sorted(selected - known)
        if unknown:
            raise DMSEIParseError(
                "A seleção contém turma(s) que não pertencem ao relatório do SEI.",
                details=[{"cohort_key": key, "error": "Turma ausente na prévia."} for key in unknown],
            )
    cohorts = [
        row for row in report.cohorts
        if row.key not in excluded_keys and (not selected or row.key in selected)
    ]
    visible_keys = {row.key for row in cohorts}
    students = [
        row for row in report.students
        if f"{row.area_code}:{row.cohort_number}" in visible_keys
    ]
    warnings = list(report.warnings)
    if excluded_keys:
        warnings.append(
            "Turmas marcadas como teste foram excluídas da sincronização: "
            + ", ".join(sorted(excluded_keys))
        )
    if selected:
        warnings.append(
            f"Sincronização limitada a {len(visible_keys)} turma(s) selecionada(s) pelo usuário."
        )
    return DMSEIReport(
        source_name=report.source_name,
        source_sha256=report.source_sha256,
        sheet_name=report.sheet_name,
        unit_name=report.unit_name,
        course_filter=report.course_filter,
        parsed_at=report.parsed_at,
        cohorts=cohorts,
        students=students,
        warnings=warnings,
    )
