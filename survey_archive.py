from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from survey_models import ParsedWorkbook
from survey_parser import parse_workbooks


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 500
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024


@dataclass
class InspectedEntry:
    internal_path: str
    course_name: str
    modality: str
    unit_name: str | None
    respondent_count: int
    question_count: int
    survey_title: str | None
    questionnaire_name: str | None
    period_start: str | None
    period_end: str | None
    semester_suggested: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_member_name(name: str) -> None:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Caminho inseguro no ZIP: {name}")


def _entry_from_parsed(parsed: ParsedWorkbook) -> InspectedEntry:
    return InspectedEntry(
        internal_path=parsed.source_path,
        course_name=parsed.course_name,
        modality=parsed.modality,
        unit_name=parsed.unit_name,
        respondent_count=parsed.respondent_count,
        question_count=len(parsed.questions),
        survey_title=parsed.survey_title,
        questionnaire_name=parsed.questionnaire_name,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        semester_suggested=parsed.semester_suggested,
    )


def inspect_file(path: Path) -> tuple[list[InspectedEntry], dict]:
    suffix = path.suffix.casefold()
    entries: list[InspectedEntry] = []

    if suffix == ".xlsx":
        blocks = parse_workbooks(path, source_path=path.name)
        entries.extend(_entry_from_parsed(parsed) for parsed in blocks)
        meta = {
            "kind": "xlsx",
            "sha256": sha256_file(path),
            "file_count": 1,
            "xlsx_count": 1,
            "report_count": len(entries),
        }
        return entries, meta

    if suffix != ".zip":
        raise ValueError("Envie um arquivo .zip ou .xlsx")

    xlsx_count = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError("ZIP possui arquivos demais para o limite de segurança.")

        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("ZIP excede o limite de tamanho descompactado.")

        for info in infos:
            validate_member_name(info.filename)
            if info.is_dir() or not info.filename.casefold().endswith(".xlsx"):
                continue
            xlsx_count += 1
            blocks = parse_workbooks(archive.read(info.filename), source_path=info.filename)
            entries.extend(_entry_from_parsed(parsed) for parsed in blocks)

    entries.sort(key=lambda item: (item.course_name.casefold(), item.internal_path.casefold()))
    meta = {
        "kind": "zip",
        "sha256": sha256_file(path),
        "file_count": len(infos),
        "xlsx_count": xlsx_count,
        "report_count": len(entries),
    }
    return entries, meta


def _base_path_from_selector(selector: str) -> str:
    return selector.split("::report:", 1)[0]


def read_selected_workbooks(path: Path, selected_paths: list[str]) -> list[ParsedWorkbook]:
    selected = set(selected_paths)

    if path.suffix.casefold() == ".xlsx":
        blocks = parse_workbooks(path, source_path=path.name)
        return [block for block in blocks if block.source_path in selected]

    parsed: list[ParsedWorkbook] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        required_files = {_base_path_from_selector(selector) for selector in selected}
        missing = required_files - names
        if missing:
            raise ValueError(f"Arquivos selecionados não existem no ZIP: {sorted(missing)[:3]}")

        by_file: dict[str, set[str]] = {}
        for selector in selected_paths:
            validate_member_name(_base_path_from_selector(selector))
            by_file.setdefault(_base_path_from_selector(selector), set()).add(selector)

        for internal_file, selectors in by_file.items():
            if not internal_file.casefold().endswith(".xlsx"):
                continue
            blocks = parse_workbooks(archive.read(internal_file), source_path=internal_file)
            parsed.extend(block for block in blocks if block.source_path in selectors)

    return parsed


class UploadStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, original_name: str, content: bytes) -> tuple[str, Path]:
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Arquivo acima do limite de 100 MB.")
        token = uuid.uuid4().hex
        folder = self.root / token
        folder.mkdir(parents=True, exist_ok=False)
        safe_name = Path(original_name).name
        path = folder / safe_name
        path.write_bytes(content)
        return token, path

    def save_manifest(self, token: str, manifest: dict) -> None:
        folder = self.root / token
        if not folder.exists():
            raise FileNotFoundError("Upload temporário não encontrado.")
        (folder / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, token: str) -> tuple[Path, dict]:
        if not re_token(token):
            raise ValueError("Token de upload inválido.")
        folder = self.root / token
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("Upload expirado ou inexistente.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        path = folder / manifest["stored_name"]
        if not path.exists():
            raise FileNotFoundError("Arquivo temporário não encontrado.")
        return path, manifest


def re_token(token: str) -> bool:
    return len(token) == 32 and all(ch in "0123456789abcdef" for ch in token.casefold())
