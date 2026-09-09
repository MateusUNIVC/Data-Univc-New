from __future__ import annotations

import re
import unicodedata


DTNH_COURSES = [
    "Administração",
    "Análise e Desenvolvimento de Sistemas",
    "Agronomia",
    "Arquitetura e Urbanismo",
    "Ciências Contábeis",
    "Direito",
    "Engenharia de Produção",
    "Engenharia Mecânica",
    "Comunicação Social - Publicidade e Propaganda",
]

DCS_COURSES = [
    "Educação Física - Bacharelado",
    "Educação Física - Licenciatura",
    "Enfermagem",
    "Farmácia",
    "Fisioterapia",
    "Medicina Veterinária",
    "Odontologia",
    "Psicologia",
]

EDUCACAO_FISICA_COURSES = {
    "Educação Física - Bacharelado",
    "Educação Física - Licenciatura",
}


COURSES_BY_DIRECTORATE = {
    "DTNH": tuple(DTNH_COURSES),
    "DCS": tuple(DCS_COURSES),
}

# Aliases aqui representam IDENTIDADE do curso, não termos vagos de busca.
# Por isso "Educação Física" isoladamente não é alias nem de Bacharelado nem
# de Licenciatura: essa forma seria ambígua e poderia contaminar históricos.
COURSE_ALIASES = {
    "Comunicação Social - Publicidade e Propaganda": (
        "Comunicação Social - Publicidade e Propaganda",
        "Comunicação Social - Publicidade e Propaganda - Presencial",
        "Publicidade e Propaganda",
        "Publicidade e Propaganda - Presencial",
    ),
    "Educação Física - Bacharelado": (
        "Educação Física - Bacharelado",
        "Educação Física Bacharelado",
        "Educação Física (Bac. Presencial)",
        "Educação Física (Bach. Presencial)",
        "Educação Física - Bacharelado - Presencial",
    ),
    "Educação Física - Licenciatura": (
        "Educação Física - Licenciatura",
        "Educação Física Licenciatura",
        "Educação Física (Lic. Presencial)",
        "Educação Física - Licenciatura - Presencial",
    ),
}

# Valor que o formulário principal do SEI aceita depois da seleção. O valor
# institucional permanece separado e nunca é substituído por este rótulo.
COURSE_SEI_FORM_VALUES = {
    "Comunicação Social - Publicidade e Propaganda": "Publicidade e Propaganda",
    "Educação Física - Bacharelado": "Educação Física (Bac. Presencial)",
    "Educação Física - Licenciatura": "Educação Física (Lic. Presencial)",
}

COURSE_SEARCH_TERMS = {
    "Administração": "administração",
    "Análise e Desenvolvimento de Sistemas": "análise e desenvolvimento",
    "Agronomia": "agronomia",
    "Arquitetura e Urbanismo": "arquitetura",
    "Ciências Contábeis": "ciências contábeis",
    "Direito": "direito",
    "Engenharia de Produção": "engenharia de produção",
    "Engenharia Mecânica": "engenharia mecânica",
    "Comunicação Social - Publicidade e Propaganda": "publicidade",
    # O HAR real mostra as duas habilitações na mesma consulta "Educ", com
    # Licenciatura na página 1 e Bacharelado na página 2 do DataScroller.
    "Educação Física - Bacharelado": "Educ",
    "Educação Física - Licenciatura": "Educ",
    "Enfermagem": "enfermagem",
    "Farmácia": "farmácia",
    "Fisioterapia": "fisioterapia",
    "Medicina Veterinária": "medicina veterinária",
    "Odontologia": "odontologia",
    "Psicologia": "psicologia",
}

# Alguns cursos aparecem repetidos no seletor do SEI por configuração/turno.
# Nos XLSX reais de Educação Física, INTEGRAL - NOTURNO e INTEGRAL - MATUTINO
# geram o mesmo conjunto de dados; o turno não define a habilitação. Mantemos
# NOTURNO apenas como escolha determinística de uma das configurações ativas,
# reproduzindo o fluxo manual validado no HAR mais recente.
COURSE_SEI_TURN_PREFERENCES = {
    "Educação Física - Bacharelado": "INTEGRAL - NOTURNO",
    "Educação Física - Licenciatura": "INTEGRAL - NOTURNO",
}


def normalize_course_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def course_aliases(course_name: str) -> tuple[str, ...]:
    aliases = COURSE_ALIASES.get(course_name, ())
    # Para cursos sem colisão de habilitação, aceitamos também o sufixo simples
    # de modalidade que o SEI costuma acrescentar ao rótulo.
    generated: tuple[str, ...] = ()
    if course_name not in {"Educação Física - Bacharelado", "Educação Física - Licenciatura"}:
        generated = (f"{course_name} - Presencial", f"{course_name} (Presencial)")
    return tuple(dict.fromkeys((course_name, *aliases, *generated)))


def canonical_course_name(raw_name: str, directorate_code: str | None = None) -> str:
    """Resolve um rótulo do SEI/Excel para o nome institucional do Data UNIVC.

    O casamento é por igualdade normalizada de aliases conhecidos. Substrings
    amplas não são usadas aqui, especialmente para Educação Física.
    """
    raw = str(raw_name or "").strip()
    if not raw:
        return raw
    target = normalize_course_text(raw)
    directorate = str(directorate_code or "").strip().upper()
    candidates = COURSES_BY_DIRECTORATE.get(directorate)
    if candidates is None:
        candidates = tuple(DTNH_COURSES) + tuple(DCS_COURSES)
    matches: list[str] = []
    for canonical in candidates:
        aliases = {normalize_course_text(alias) for alias in course_aliases(canonical)}
        if target in aliases:
            matches.append(canonical)
    return matches[0] if len(matches) == 1 else raw


def course_name_matches(raw_name: str, expected_course: str, directorate_code: str | None = None) -> bool:
    expected = canonical_course_name(expected_course, directorate_code)
    actual = canonical_course_name(raw_name, directorate_code)
    return bool(expected and actual and normalize_course_text(expected) == normalize_course_text(actual))



def is_ambiguous_course_name(raw_name: str, directorate_code: str | None = None) -> bool:
    return (
        str(directorate_code or "").strip().upper() == "DCS"
        and normalize_course_text(raw_name) == normalize_course_text("Educação Física")
    )
