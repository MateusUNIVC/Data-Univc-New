from __future__ import annotations

from typing import Protocol

from survey_faculty_models import ParsedFacultyContext


class FacultyReportLayoutUnknown(RuntimeError):
    """Usado enquanto ainda não há um XLSX docente real para mapear com segurança."""


class FacultyReportAdapter(Protocol):
    """Contrato do adaptador que será implementado quando houver relatório real."""

    def parse(self, content: bytes, *, source_path: str) -> list[ParsedFacultyContext]: ...
