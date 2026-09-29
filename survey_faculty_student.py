from __future__ import annotations

import re

from survey_parser import normalize_key


FACULTY_STUDENT_DETAIL_VALUE = "AVALIADO"
FACULTY_STUDENT_UNIT_VALUE = "2"
FACULTY_STUDENT_TURN_VALUE = "0"
FACULTY_STUDENT_GRADUATION_UNIT_NAME = (
    "CENTRO UNIVERSITÁRIO VALE DO CRICARÉ - GRADUAÇÃO (SÃO MATEUS-ES)"
)
FACULTY_STUDENT_QUESTIONNAIRE_HINTS = (
    "aluno avalia professor",
    "discente avalia docente",
    "discente avalia professor",
)


def _compact_key(value: str | None) -> str:
    """Normaliza também separadores perdidos pelo nome de pasta gerado pelo SEI.

    O ZIP real de 24/09/2026 usa ``SAO_MATEUSES`` no diretório da Graduação,
    enquanto o XLSX usa ``SÃO MATEUS-ES``. Remover apenas os espaços depois da
    normalização torna essas duas representações equivalentes sem aproximar
    ``GRADUACAO SEMIPRESENCIAL`` ou polos da unidade presencial.
    """

    return normalize_key(value or "").replace(" ", "")


def is_graduation_unit(unit_name: str | None) -> bool:
    """Aceita somente a unidade de Graduação presencial de São Mateus.

    A igualdade continua estrita em conteúdo, mas tolera diferenças de acento,
    pontuação e separadores do caminho interno do ZIP. Assim, o rótulo real do
    XLSX e a pasta ``...GRADUACAO_(SAO_MATEUSES)`` são a mesma unidade, enquanto
    semipresencial, técnico e polos permanecem fora do escopo.
    """

    return bool(
        unit_name
        and _compact_key(unit_name) == _compact_key(FACULTY_STUDENT_GRADUATION_UNIT_NAME)
    )


def is_faculty_student_questionnaire(name: str | None) -> bool:
    key = normalize_key(name or "")
    return bool(
        key
        and any(
            normalize_key(hint) in key
            for hint in FACULTY_STUDENT_QUESTIONNAIRE_HINTS
        )
    )


def normalize_faculty_semester(value: str | None) -> str | None:
    """Converte as formas aceitas de semestre para ``AAAA-SEM1/AAAA-SEM2``.

    A função não infere semestre por data. Ela apenas valida uma informação
    explicitamente fornecida pelo relatório ou confirmada pelo usuário.
    """

    text = str(value or "").strip().upper()
    if not text:
        return None
    match = re.fullmatch(r"(20\d{2})(?:\s*[-./]?\s*(?:SEM)?)\s*([12])", text)
    if not match:
        return None
    return f"{match.group(1)}-SEM{match.group(2)}"


def faculty_context_semantic_key(
    course_name: str | None,
    teacher_name: str | None,
    discipline_name: str | None,
    class_group: str | None = "",
) -> str:
    """Identidade semântica de um contexto docente dentro de um survey run.

    IDs de arquivo do SEI podem mudar quando o mesmo relatório é gerado de
    novo. Para idempotência, a identidade útil é curso + professor + disciplina;
    o semestre já é propriedade do ``survey_run``/``academic_offering``.
    """

    return "|".join(
        normalize_key(str(value or ""))
        for value in (course_name, teacher_name, discipline_name, class_group)
    )
