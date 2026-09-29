from __future__ import annotations

from dataclasses import dataclass, field

from survey_models import ParsedQuestion


@dataclass
class ParsedFacultyContext:
    """Contrato normalizado da avaliação em que o discente avalia o docente.

    O adaptador do relatório ``Disciplina/Professor`` do SEI converte cada XLSX
    para esta estrutura. O restante da aplicação não depende das posições de
    colunas do arquivo original e trabalha apenas com o contexto acadêmico e as
    distribuições de respostas preservadas aqui.
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
