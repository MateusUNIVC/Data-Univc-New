from __future__ import annotations

from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student_parser import parse_faculty_student_workbook


class FacultyReportLayoutUnknown(RuntimeError):
    """Mantida por compatibilidade com chamadas antigas do foundation."""


class SEIFacultyStudentReportAdapter:
    """Adaptador validado para o relatório SEI ``Disciplina/Professor``."""

    def parse(self, content: bytes, *, source_path: str) -> list[ParsedFacultyContext]:
        return [parse_faculty_student_workbook(content, source_path=source_path)]
