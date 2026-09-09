from __future__ import annotations

from dataclasses import dataclass, field

from survey_models import ParsedQuestion


@dataclass
class ParsedFacultyContext:
    """Representação normalizada que o futuro adaptador de XLSX docente deve produzir.

    Nenhuma posição de coluna do SEI é assumida aqui. O adaptador futuro terá a
    responsabilidade exclusiva de descobrir esses campos a partir de relatório real.
    O restante da aplicação trabalha somente com esta estrutura estável.
    """

    source_key: str
    source_path: str
    unit_name: str | None
    course_name: str
    modality: str
    teacher_name: str
    discipline_name: str
    class_code: str = ""
    teacher_external_id: str | None = None
    discipline_external_id: str | None = None
    offering_external_id: str | None = None
    assignment_external_id: str | None = None
    survey_title: str | None = None
    questionnaire_name: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    semester_suggested: str | None = None
    generated_at: str | None = None
    respondent_count: int = 0
    questions: list[ParsedQuestion] = field(default_factory=list)
