from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class OptionAggregate:
    label: str
    count: int
    source_percentage: float | None = None
    numeric_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedQuestion:
    text: str
    normalized_text: str
    position: int
    metric_type: str = "categorical"
    nps_candidate: bool = False
    options: list[OptionAggregate] = field(default_factory=list)
    raw_responses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "normalized_text": self.normalized_text,
            "position": self.position,
            "metric_type": self.metric_type,
            "nps_candidate": self.nps_candidate,
            "options": [option.to_dict() for option in self.options],
            "raw_responses": list(self.raw_responses),
        }


@dataclass
class ParsedWorkbook:
    source_path: str
    unit_name: str | None
    course_name: str
    modality: str
    survey_title: str | None
    questionnaire_name: str | None
    period_start: str | None
    period_end: str | None
    semester_suggested: str | None
    generated_at: str | None
    respondent_count: int
    questions: list[ParsedQuestion]

    def to_dict(self, include_questions: bool = True) -> dict[str, Any]:
        payload = {
            "source_path": self.source_path,
            "unit_name": self.unit_name,
            "course_name": self.course_name,
            "modality": self.modality,
            "survey_title": self.survey_title,
            "questionnaire_name": self.questionnaire_name,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "semester_suggested": self.semester_suggested,
            "generated_at": self.generated_at,
            "respondent_count": self.respondent_count,
            "question_count": len(self.questions),
        }
        if include_questions:
            payload["questions"] = [question.to_dict() for question in self.questions]
        return payload
