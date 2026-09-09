from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

DM_AREAS: dict[str, str] = {
    "CTE": "Ciência, Tecnologia e Educação",
    "SDS": "Saúde e Desigualdade Social",
}

COHORT_STATUSES = ("Planejada", "Aberta", "Em andamento", "Encerrada")
STUDENT_STATUSES = ("Ativo", "Titulado", "Desligado")
LEGACY_STUDENT_STATUS_ALIASES = {"trancado": "Desligado", "trancada": "Desligado"}
DIPLOMA_STATUSES = ("Não informado", "Pendente", "Em emissão", "Emitido")

_AREA_ALIASES = {
    "cte": "CTE",
    "ciencia tecnologia e educacao": "CTE",
    "ciencias tecnologia e educacao": "CTE",
    "ciencia tecnologia educacao": "CTE",
    "sds": "SDS",
    "saude e desigualdade social": "SDS",
    "saude e desigualdades sociais": "SDS",
    "saude desigualdade social": "SDS",
}


class DMValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _norm(value: Any) -> str:
    raw = str(value or "").strip()
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).casefold().strip()
    return re.sub(r"\s+", " ", text)


def normalize_area(value: Any) -> tuple[str, str]:
    text = str(value or "").strip().upper()
    if text in DM_AREAS:
        return text, DM_AREAS[text]
    code = _AREA_ALIASES.get(_norm(value))
    if not code:
        raise DMValidationError(
            "Área do Mestrado inválida.",
            {"area": "Use Ciência, Tecnologia e Educação ou Saúde e Desigualdade Social."},
        )
    return code, DM_AREAS[code]


def parse_date(value: Any, *, field: str, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise DMValidationError(f"Informe {field}.", {field: "Campo obrigatório."})
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise DMValidationError(
        f"{field} possui data inválida.",
        {field: "Use DD/MM/AAAA ou AAAA-MM-DD."},
    )


def positive_int(value: Any, *, field: str, required: bool = False, allow_zero: bool = False) -> int | None:
    if value in (None, ""):
        if required:
            raise DMValidationError(f"Informe {field}.", {field: "Campo obrigatório."})
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError) as exc:
        raise DMValidationError(f"{field} deve ser inteiro.", {field: "Valor inteiro inválido."}) from exc
    minimum = 0 if allow_zero else 1
    if number < minimum:
        condition = "maior ou igual a zero" if allow_zero else "maior que zero"
        raise DMValidationError(f"{field} deve ser {condition}.", {field: f"Use valor {condition}."})
    return number


def normalize_cohort_status(value: Any) -> str:
    text = str(value or "Em andamento").strip()
    for item in COHORT_STATUSES:
        if _norm(item) == _norm(text):
            return item
    raise DMValidationError("Status da turma inválido.", {"status": ", ".join(COHORT_STATUSES)})


def normalize_student_status(
    value: Any,
    *,
    defense_date: date | None = None,
) -> str:
    # Regra de domínio v0.8.29.0: uma defesa confirmada é suficiente para
    # caracterizar titulação. Nenhum fluxo deve manter um aluno Ativo/Desligado
    # quando defense_date existe.
    if defense_date:
        return "Titulado"

    text = str(value or "Ativo").strip()
    normalized = _norm(text)
    legacy = LEGACY_STUDENT_STATUS_ALIASES.get(normalized)
    if legacy:
        return legacy
    for item in STUDENT_STATUSES:
        if _norm(item) == normalized:
            return item
    raise DMValidationError("Status do aluno inválido.", {"status": ", ".join(STUDENT_STATUSES)})



def normalize_diploma_status(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for item in DIPLOMA_STATUSES:
        if _norm(item) == _norm(text):
            return item
    raise DMValidationError(
        "Situação do diploma digital inválida.",
        {"diploma_status": ", ".join(DIPLOMA_STATUSES)},
    )


def validate_cohort_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    try:
        area_code, area_name = normalize_area(payload.get("area_code") or payload.get("area"))
    except DMValidationError as exc:
        errors.update(exc.field_errors or {"area": str(exc)})
        area_code, area_name = "", ""
    try:
        cohort_number = positive_int(payload.get("cohort_number") or payload.get("turma"), field="turma", required=True)
    except DMValidationError as exc:
        errors.update(exc.field_errors)
        cohort_number = None
    try:
        opening_date = parse_date(payload.get("opening_date") or payload.get("data_abertura"), field="data_abertura", required=False)
    except DMValidationError as exc:
        errors.update(exc.field_errors)
        opening_date = None
    try:
        vacancies = positive_int(
            payload.get("vacancies_authorized") or payload.get("vagas_autorizadas"),
            field="vagas_autorizadas",
            required=False,
            allow_zero=False,
        )
    except DMValidationError as exc:
        errors.update(exc.field_errors)
        vacancies = None
    try:
        status = normalize_cohort_status(payload.get("status"))
    except DMValidationError as exc:
        errors.update(exc.field_errors)
        status = "Em andamento"
    if errors:
        raise DMValidationError("Revise os dados da turma.", errors)
    return {
        "area_code": area_code,
        "area_name": area_name,
        "cohort_number": cohort_number,
        "opening_date": opening_date,
        "vacancies_authorized": vacancies,
        "status": status,
        "notes": str(payload.get("notes") or payload.get("observacoes") or "").strip() or None,
        "source_system": str(payload.get("source_system") or ("DEMO" if payload.get("is_demo") else "MANUAL")).strip().upper(),
        "sei_raw_label": str(payload.get("sei_raw_label") or "").strip() or None,
        "is_demo": bool(payload.get("is_demo", False)),
    }


def validate_student_payload(payload: dict[str, Any], *, cohort_opening_date: date | None = None) -> dict[str, Any]:
    errors: dict[str, str] = {}
    student_code = str(payload.get("student_code") or payload.get("matricula") or "").strip()
    student_name = str(payload.get("student_name") or payload.get("nome") or "").strip()
    if not student_code:
        errors["matricula"] = "Informe a matrícula ou código institucional do aluno."
    if not student_name:
        errors["nome"] = "Informe o nome do aluno."

    raw_entry = payload.get("entry_date")
    if raw_entry in (None, ""):
        raw_entry = payload.get("data_ingresso")
    if raw_entry in (None, ""):
        entry_date = None
        entry_date_estimated = False
    else:
        try:
            entry_date = parse_date(raw_entry, field="data_ingresso", required=True)
        except DMValidationError as exc:
            errors.update(exc.field_errors)
            entry_date = None
        entry_date_estimated = bool(payload.get("entry_date_estimated", False))

    date_fields = {
        "qualification_date": ("data_qualificacao", "data_qualificacao"),
        "defense_date": ("data_defesa", "data_defesa"),
        "graduation_date": ("data_titulacao", "data_titulacao"),
        "defense_scheduled_date": ("data_defesa_marcada", "data_defesa_marcada"),
        "exit_date": ("data_saida", "data_saida"),
    }
    parsed: dict[str, date | None] = {}
    for key, (alias, label) in date_fields.items():
        raw = payload.get(key)
        if raw in (None, ""):
            raw = payload.get(alias)
        try:
            parsed[key] = parse_date(raw, field=label, required=False)
        except DMValidationError as exc:
            errors.update(exc.field_errors)
            parsed[key] = None

    if entry_date:
        for key, label in (
            ("qualification_date", "data_qualificacao"),
            ("defense_date", "data_defesa"),
            ("graduation_date", "data_titulacao"),
            ("defense_scheduled_date", "data_defesa_marcada"),
            ("exit_date", "data_saida"),
        ):
            value = parsed.get(key)
            if value and value < entry_date:
                errors[label] = "A data não pode ser anterior ao ingresso."
    if parsed.get("qualification_date") and parsed.get("defense_date") and parsed["qualification_date"] > parsed["defense_date"]:
        errors["data_qualificacao"] = "A qualificação não pode ocorrer depois da defesa."
    if parsed.get("graduation_date") and parsed.get("defense_date") and parsed["graduation_date"] < parsed["defense_date"]:
        errors["data_titulacao"] = "A titulação não pode ocorrer antes da defesa."
    try:
        status = normalize_student_status(
            payload.get("status"),
            defense_date=parsed.get("defense_date"),
        )
    except DMValidationError as exc:
        errors.update(exc.field_errors)
        status = "Ativo"
    if status == "Desligado" and not parsed.get("exit_date"):
        errors["data_saida"] = "Informe a data de saída quando ela for conhecida."
    try:
        diploma_status = normalize_diploma_status(payload.get("diploma_status") or payload.get("situacao_diploma"))
    except DMValidationError as exc:
        errors.update(exc.field_errors)
        diploma_status = None
    if parsed.get("graduation_date") and status != "Titulado":
        errors["status"] = "Aluno com data de titulação deve estar como Titulado."
    if diploma_status and diploma_status != "Não informado" and status != "Titulado":
        errors["diploma_status"] = "O acompanhamento de diploma digital é permitido somente para alunos titulados."
    if errors:
        raise DMValidationError("Revise os dados do aluno.", errors)
    return {
        "student_code": student_code,
        "student_name": student_name,
        "entry_date": entry_date,
        "qualification_date": parsed.get("qualification_date"),
        "defense_date": parsed.get("defense_date"),
        "graduation_date": parsed.get("graduation_date"),
        "defense_scheduled_date": parsed.get("defense_scheduled_date"),
        "exit_date": parsed.get("exit_date"),
        "status": status,
        "advisor": str(payload.get("advisor") or payload.get("orientador") or "").strip() or None,
        "research_line": str(payload.get("research_line") or payload.get("linha_pesquisa") or "").strip() or None,
        "diploma_status": diploma_status,
        "notes": str(payload.get("notes") or payload.get("observacoes") or "").strip() or None,
        "entry_date_estimated": entry_date_estimated,
        "source_system": str(payload.get("source_system") or ("DEMO" if payload.get("is_demo") else "MANUAL")).strip().upper(),
        "sei_raw_status": str(payload.get("sei_raw_status") or "").strip() or None,
        "is_demo": bool(payload.get("is_demo", False)),
    }


def cohort_key(area_code: str, cohort_number: int) -> str:
    return f"{area_code}-T{int(cohort_number)}"


def cohort_label(cohort_number: int) -> str:
    return f"Turma {int(cohort_number)}"


def months_between(start: date, end: date) -> float:
    # Calendar-aware approximation used consistently in the site and Excel export.
    days = (end - start).days
    return round(days / 30.4375, 2)
