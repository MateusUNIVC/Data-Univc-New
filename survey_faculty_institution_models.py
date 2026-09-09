from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from survey_models import ParsedQuestion


@dataclass
class ParsedFacultyInstitutionWorkbook:
    """Relatório institucional respondido por docentes, sem dimensão de curso.

    O SEI entrega apenas o agregado anônimo do público docente. Por isso esta
    estrutura deliberadamente não contém professor, curso, disciplina ou turma.
    """

    source_path: str
    unit_name: str | None
    survey_title: str | None
    questionnaire_name: str | None
    period_start: str | None
    period_end: str | None
    semester_suggested: str | None
    generated_at: str | None
    respondent_count: int
    questions: list[ParsedQuestion] = field(default_factory=list)

    def to_dict(self, include_questions: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_path": self.source_path,
            "unit_name": self.unit_name,
            "survey_title": self.survey_title,
            "questionnaire_name": self.questionnaire_name,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "semester_suggested": self.semester_suggested,
            "generated_at": self.generated_at,
            "respondent_count": self.respondent_count,
            "question_count": len(self.questions),
            "nps_candidate_count": sum(1 for q in self.questions if q.nps_candidate),
        }
        if include_questions:
            payload["questions"] = [question.to_dict() for question in self.questions]
        return payload
