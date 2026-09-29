from __future__ import annotations

"""Identidade acadêmica estrita da Avaliação Docente.

A camada não tenta "corrigir" nomes por similaridade. Ela apenas estabiliza
espaços/separadores para comparação e constrói chaves reproduzíveis. Aliases de
curso continuam sendo responsabilidade do catálogo institucional; ambiguidades
precisam de resolução explícita.
"""

from survey_parser import normalize_key


def clean_identity_display(value: str | None) -> str:
    """Preserva o texto humano removendo apenas espaços redundantes."""

    return " ".join(str(value or "").split())


def teacher_identity_key(value: str | None) -> str:
    """Chave estrita de professor sem heurística/fuzzy matching."""

    return normalize_key(clean_identity_display(value))


def discipline_identity_key(value: str | None) -> str:
    """Chave estrita de disciplina dentro de um curso."""

    return normalize_key(clean_identity_display(value))


def class_group_display(value: str | None) -> str:
    return clean_identity_display(value)


def faculty_academic_identity_key(
    *,
    period: str | None,
    course_identity: str | int | None,
    teacher_name: str | None,
    discipline_name: str | None,
    class_group: str | None = "",
) -> str:
    """Identidade estável da atribuição docente no tempo.

    O período faz parte da identidade acadêmica; curso, disciplina e professor
    definem a atribuição. ``class_group`` é opcional porque o relatório atual do
    SEI é agregado por Disciplina/Professor, mas fica preparado para futuras
    exportações que tragam turma explicitamente.
    """

    return "|".join(
        (
            normalize_key(str(period or "")),
            normalize_key(str(course_identity or "")),
            teacher_identity_key(teacher_name),
            discipline_identity_key(discipline_name),
            normalize_key(class_group_display(class_group)),
        )
    )
