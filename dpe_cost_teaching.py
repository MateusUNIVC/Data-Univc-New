from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit
from dpe_course_context import snapshot_context_label
from models import (
    DPECostExpense,
    DPECostPeriod,
    DPECostPeriodOffering,
    DPECostPeriodTeacher,
    DPECostSubject,
    DPECostTeachingActivity,
    DPECostTeachingActivityOffering,
    DPETeacherAlias,
    DPETeacherProfile,
    Teacher,
)
from security import DirectorateScope

EDITABLE_PERIOD_STATUSES = ("DRAFT", "REVIEW")
ACTIVITY_SOURCE_TYPES = ("MANUAL", "EXCEL", "API", "REQUEST", "OTHER")
RELATIONSHIP_TYPES = ("UNSPECIFIED", "EMPLOYEE", "HOURLY", "SERVICE_PROVIDER", "OTHER")
CODE_RE = re.compile(r"[^A-Z0-9._/-]+")


class DPECostTeachingValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _text(value: Any, *, max_length: int | None = None) -> str:
    output = str(value or "").strip()
    return output[:max_length] if max_length and len(output) > max_length else output


def _optional_text(value: Any, *, max_length: int | None = None) -> str | None:
    output = _text(value, max_length=max_length)
    return output or None


def _code(value: Any, *, max_length: int = 100) -> str:
    output = _text(value, max_length=max_length).upper()
    output = re.sub(r"\s+", "-", output)
    output = CODE_RE.sub("-", output)
    return re.sub(r"-+", "-", output).strip("-")


def normalize_person_name(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _text(value).casefold())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return " ".join(raw.split())


def _hours(value: Any, field: str = "workload_hours") -> Decimal:
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise DPECostTeachingValidationError("Carga horária inválida.", {field: "Informe um número válido de horas."})
    if amount <= 0:
        raise DPECostTeachingValidationError("Carga horária inválida.", {field: "A carga horária deve ser maior que zero."})
    return amount


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value else None)


def _date_value(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise DPECostTeachingValidationError("Data inválida.", {field: "Use uma data válida no formato AAAA-MM-DD."}) from exc


def _activity_dates(period: str, start_value: Any, end_value: Any) -> tuple[date | None, date | None]:
    start = _date_value(start_value, "effective_start_date")
    end = _date_value(end_value, "effective_end_date")
    errors: dict[str, str] = {}
    for field, value in (("effective_start_date", start), ("effective_end_date", end)):
        if value and value.strftime("%Y-%m") != period:
            errors[field] = f"A data precisa pertencer à competência {period}."
    if start and end and end < start:
        errors["effective_end_date"] = "A data final não pode ser anterior à data inicial."
    if errors:
        raise DPECostTeachingValidationError("Revise a vigência da atividade docente.", errors)
    return start, end


def _decimal(value: Decimal | None) -> float:
    return float(value or 0)


def _offering_label(snapshot: dict[str, Any]) -> str:
    return snapshot_context_label(snapshot)


class DPECostTeachingRepository:
    """Monthly teachers, disciplines and workload for the DPE Cost Engine.

    The institutional ``teachers`` table remains the master identity. This
    repository creates competence snapshots before any workload/payroll link is
    used, so changes to the live teacher or subject catalog never rewrite a
    previous month.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("O módulo de Docência e Carga Horária pertence exclusivamente à DPE.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    @property
    def actor(self) -> str:
        return self.scope.user.email or self.scope.user.full_name or self.scope.user.user_id

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DPECostTeachingValidationError(
                "Não foi possível salvar porque já existe um cadastro equivalente ou há uma referência inválida."
            ) from exc

    def _period(self, period_id: int, *, editable: bool = False) -> DPECostPeriod:
        row = self.db.scalar(
            select(DPECostPeriod).where(
                DPECostPeriod.id == int(period_id),
                DPECostPeriod.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Competência do Cost Engine não encontrada.")
        if editable and row.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostTeachingValidationError(
                "A competência está calculada ou fechada e não aceita alteração de docência."
            )
        return row

    def _teacher(self, teacher_id: int) -> Teacher:
        row = self.db.scalar(select(Teacher).where(Teacher.id == int(teacher_id)))
        if not row:
            raise LookupError("Professor não encontrado.")
        return row

    def _subject(self, subject_id: int) -> DPECostSubject:
        row = self.db.scalar(
            select(DPECostSubject).where(
                DPECostSubject.id == int(subject_id),
                DPECostSubject.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Disciplina do Cost Engine não encontrada.")
        return row

    def _activity(self, activity_id: int, *, editable: bool = False) -> DPECostTeachingActivity:
        row = self.db.scalar(
            select(DPECostTeachingActivity).where(
                DPECostTeachingActivity.id == int(activity_id),
                DPECostTeachingActivity.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Atividade docente não encontrada.")
        if editable:
            self._period(row.period_id, editable=True)
            if row.status != "ACTIVE":
                raise DPECostTeachingValidationError("Uma atividade estornada não pode ser alterada.")
        return row

    def _profile(self, teacher_id: int) -> DPETeacherProfile | None:
        return self.db.scalar(
            select(DPETeacherProfile).where(
                DPETeacherProfile.directorate_id == self.directorate_id,
                DPETeacherProfile.teacher_id == int(teacher_id),
            )
        )

    @staticmethod
    def _teacher_payload(
        row: Teacher,
        profile: DPETeacherProfile | None,
        aliases: list[DPETeacherAlias] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "profile_id": profile.id if profile else None,
            "external_id": row.external_id,
            "display_name": row.display_name,
            "normalized_name": row.normalized_name,
            "active": bool(profile.active and row.active) if profile else False,
            "profile_active": bool(profile.active) if profile else False,
            "institutional_active": bool(row.active),
            "relationship_type": (profile.default_relationship_type if profile else "UNSPECIFIED"),
            "profile_notes": profile.notes if profile else None,
            "aliases": [
                {
                    "id": alias.id,
                    "alias_name": alias.alias_name,
                    "normalized_alias": alias.normalized_alias,
                    "source_type": alias.source_type,
                    "external_key": alias.external_key,
                    "active": bool(alias.active),
                }
                for alias in (aliases or [])
            ],
        }

    @staticmethod
    def _subject_payload(row: DPECostSubject) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "external_key": row.external_key,
            "active": bool(row.active),
            "notes": row.notes,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def _teacher_snapshot(self, teacher: Teacher, profile: DPETeacherProfile | None = None) -> dict[str, Any]:
        profile = profile or self._profile(teacher.id)
        aliases = self.db.scalars(
            select(DPETeacherAlias).where(
                DPETeacherAlias.teacher_id == teacher.id,
                DPETeacherAlias.active.is_(True),
            ).order_by(DPETeacherAlias.alias_name)
        ).all()
        return {
            "snapshot_version": 2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "teacher": {
                "id": teacher.id,
                "external_id": teacher.external_id,
                "display_name": teacher.display_name,
                "normalized_name": teacher.normalized_name,
                "active": bool(teacher.active),
            },
            "dpe_profile": {
                "profile_id": profile.id if profile else None,
                "relationship_type": profile.default_relationship_type if profile else "UNSPECIFIED",
                "active": bool(profile.active) if profile else False,
                "notes": profile.notes if profile else None,
            },
            "aliases": [
                {
                    "alias_name": row.alias_name,
                    "normalized_alias": row.normalized_alias,
                    "source_type": row.source_type,
                    "external_key": row.external_key,
                }
                for row in aliases
            ],
        }

    def _ensure_period_teacher(self, period_id: int, teacher_id: int) -> DPECostPeriodTeacher:
        period = self._period(period_id, editable=True)
        teacher = self._teacher(teacher_id)
        profile = self._profile(teacher.id)
        if not profile or not profile.active or not teacher.active:
            raise DPECostTeachingValidationError(
                "O docente não está ativo no cadastro da DPE.",
                {"teacher_id": "Ative ou incorpore o docente ao cadastro da DPE antes de usá-lo no mês."},
            )
        existing = self.db.scalar(
            select(DPECostPeriodTeacher).where(
                DPECostPeriodTeacher.period_id == int(period_id),
                DPECostPeriodTeacher.teacher_id == teacher.id,
                DPECostPeriodTeacher.directorate_id == self.directorate_id,
            )
        )
        if existing:
            return existing
        row = DPECostPeriodTeacher(
            directorate_id=self.directorate_id,
            period_id=int(period_id),
            teacher_id=teacher.id,
            teacher_snapshot_json=self._teacher_snapshot(teacher, profile),
            relationship_type=profile.default_relationship_type or "UNSPECIFIED",
            included=True,
            created_by=self.actor,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_teachers(self, *, active_only: bool = False, search: str | None = None) -> list[dict[str, Any]]:
        stmt = (
            select(Teacher, DPETeacherProfile)
            .join(DPETeacherProfile, DPETeacherProfile.teacher_id == Teacher.id)
            .where(DPETeacherProfile.directorate_id == self.directorate_id)
        )
        if active_only:
            stmt = stmt.where(DPETeacherProfile.active.is_(True), Teacher.active.is_(True))
        if search:
            token = f"%{_text(search).lower()}%"
            stmt = stmt.where(func.lower(Teacher.display_name).like(token))
        pairs = self.db.execute(
            stmt.order_by(DPETeacherProfile.active.desc(), Teacher.display_name)
        ).all()
        teacher_ids = [teacher.id for teacher, _profile in pairs]
        aliases = self.db.scalars(
            select(DPETeacherAlias).where(DPETeacherAlias.teacher_id.in_(teacher_ids or [-1]))
            .order_by(DPETeacherAlias.alias_name)
        ).all()
        alias_map: dict[int, list[DPETeacherAlias]] = {}
        for alias in aliases:
            alias_map.setdefault(alias.teacher_id, []).append(alias)
        return [self._teacher_payload(teacher, profile, alias_map.get(teacher.id, [])) for teacher, profile in pairs]

    def create_teacher(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = _text(payload.get("display_name"), max_length=220)
        normalized = normalize_person_name(name)
        external_id = _optional_text(payload.get("external_id"), max_length=100)
        relationship = _text(payload.get("relationship_type") or "UNSPECIFIED").upper()
        errors: dict[str, str] = {}
        if not name:
            errors["display_name"] = "Informe o nome do docente."
        if not normalized:
            errors["display_name"] = "O nome informado não pode ser normalizado."
        if relationship not in RELATIONSHIP_TYPES:
            errors["relationship_type"] = "Selecione um tipo de vínculo válido."
        existing = self.db.scalar(select(Teacher).where(Teacher.normalized_name == normalized)) if normalized else None
        if external_id:
            ext_owner = self.db.scalar(select(Teacher).where(Teacher.external_id == external_id))
            if ext_owner and (not existing or ext_owner.id != existing.id):
                errors["external_id"] = "Este identificador externo já está vinculado a outro docente."
        if existing and self._profile(existing.id):
            errors["display_name"] = "Este docente já faz parte do cadastro da DPE."
        if errors:
            raise DPECostTeachingValidationError("Revise o cadastro do docente.", errors)
        teacher = existing
        if not teacher:
            teacher = Teacher(
                external_id=external_id, display_name=name, normalized_name=normalized, active=True
            )
            self.db.add(teacher)
            self.db.flush()
        elif external_id and not teacher.external_id:
            teacher.external_id = external_id
        profile = DPETeacherProfile(
            directorate_id=self.directorate_id,
            teacher_id=teacher.id,
            default_relationship_type=relationship,
            active=bool(payload.get("active", True)),
            notes=_optional_text(payload.get("profile_notes")),
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.db.add(profile)
        self._commit()
        self.db.refresh(teacher); self.db.refresh(profile)
        return self._teacher_payload(teacher, profile, [])

    def update_teacher(self, teacher_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._teacher(teacher_id)
        profile = self._profile(row.id)
        if not profile:
            raise LookupError("Docente não faz parte do cadastro da DPE.")
        name = _text(payload.get("display_name", row.display_name), max_length=220)
        normalized = normalize_person_name(name)
        external_id = _optional_text(payload.get("external_id", row.external_id), max_length=100)
        relationship = _text(payload.get("relationship_type", profile.default_relationship_type) or "UNSPECIFIED").upper()
        duplicate = self.db.scalar(select(Teacher.id).where(Teacher.normalized_name == normalized, Teacher.id != row.id))
        if duplicate:
            raise DPECostTeachingValidationError("Revise o cadastro do docente.", {"display_name": "Já existe outro docente com este nome."})
        if external_id:
            duplicate_external = self.db.scalar(select(Teacher.id).where(Teacher.external_id == external_id, Teacher.id != row.id))
            if duplicate_external:
                raise DPECostTeachingValidationError("Revise o cadastro do docente.", {"external_id": "Identificador externo já utilizado."})
        if relationship not in RELATIONSHIP_TYPES:
            raise DPECostTeachingValidationError("Revise o cadastro do docente.", {"relationship_type": "Selecione um tipo de vínculo válido."})
        row.display_name = name
        row.normalized_name = normalized
        row.external_id = external_id
        profile.default_relationship_type = relationship
        profile.active = bool(payload.get("active", profile.active))
        profile.notes = _optional_text(payload.get("profile_notes", profile.notes))
        profile.updated_by = self.actor
        self._commit()
        aliases = self.db.scalars(select(DPETeacherAlias).where(DPETeacherAlias.teacher_id == row.id).order_by(DPETeacherAlias.alias_name)).all()
        return self._teacher_payload(row, profile, aliases)

    def create_alias(self, teacher_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        teacher = self._teacher(teacher_id)
        if not self._profile(teacher.id):
            raise DPECostTeachingValidationError("Docente não faz parte do cadastro da DPE.")
        alias_name = _text(payload.get("alias_name"), max_length=240)
        normalized = normalize_person_name(alias_name)
        if not normalized:
            raise DPECostTeachingValidationError("Revise o alias.", {"alias_name": "Informe o nome encontrado na fonte externa."})
        if normalized == teacher.normalized_name:
            raise DPECostTeachingValidationError("Este alias é igual ao nome principal do professor.")
        if self.db.scalar(select(Teacher.id).where(Teacher.normalized_name == normalized, Teacher.id != teacher.id)):
            raise DPECostTeachingValidationError("Este alias coincide com o nome principal de outro professor.")
        row = DPETeacherAlias(
            teacher_id=teacher.id,
            alias_name=alias_name,
            normalized_alias=normalized,
            source_type=_optional_text(payload.get("source_type"), max_length=40),
            external_key=_optional_text(payload.get("external_key"), max_length=180),
            active=bool(payload.get("active", True)),
            created_by=self.actor,
        )
        self.db.add(row)
        self._commit()
        self.db.refresh(row)
        return {
            "id": row.id, "teacher_id": row.teacher_id, "alias_name": row.alias_name,
            "normalized_alias": row.normalized_alias, "source_type": row.source_type,
            "external_key": row.external_key, "active": bool(row.active),
        }

    def update_alias(self, alias_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.db.scalar(select(DPETeacherAlias).where(DPETeacherAlias.id == int(alias_id)))
        if not row:
            raise LookupError("Alias do professor não encontrado.")
        alias_name = _text(payload.get("alias_name", row.alias_name), max_length=240)
        normalized = normalize_person_name(alias_name)
        teacher = self._teacher(row.teacher_id)
        if normalized == teacher.normalized_name:
            raise DPECostTeachingValidationError("Este alias é igual ao nome principal do professor.")
        if self.db.scalar(select(Teacher.id).where(Teacher.normalized_name == normalized, Teacher.id != teacher.id)):
            raise DPECostTeachingValidationError("Este alias coincide com o nome principal de outro professor.")
        row.alias_name = alias_name
        row.normalized_alias = normalized
        row.source_type = _optional_text(payload.get("source_type", row.source_type), max_length=40)
        row.external_key = _optional_text(payload.get("external_key", row.external_key), max_length=180)
        row.active = bool(payload.get("active", row.active))
        self._commit()
        return {
            "id": row.id, "teacher_id": row.teacher_id, "alias_name": row.alias_name,
            "normalized_alias": row.normalized_alias, "source_type": row.source_type,
            "external_key": row.external_key, "active": bool(row.active),
        }

    def list_subjects(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = select(DPECostSubject).where(DPECostSubject.directorate_id == self.directorate_id)
        if active_only:
            stmt = stmt.where(DPECostSubject.active.is_(True))
        rows = self.db.scalars(stmt.order_by(DPECostSubject.active.desc(), DPECostSubject.name)).all()
        return [self._subject_payload(row) for row in rows]

    def create_subject(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = _code(payload.get("code"))
        name = _text(payload.get("name"), max_length=220)
        errors: dict[str, str] = {}
        if not code:
            errors["code"] = "Informe um código estável."
        if not name:
            errors["name"] = "Informe a disciplina."
        if errors:
            raise DPECostTeachingValidationError("Revise o cadastro da disciplina.", errors)
        row = DPECostSubject(
            directorate_id=self.directorate_id,
            code=code,
            name=name,
            external_key=_optional_text(payload.get("external_key"), max_length=180),
            active=bool(payload.get("active", True)),
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
        )
        self.db.add(row)
        self._commit()
        self.db.refresh(row)
        return self._subject_payload(row)

    def update_subject(self, subject_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._subject(subject_id)
        code = _code(payload.get("code", row.code))
        name = _text(payload.get("name", row.name), max_length=220)
        if not code or not name:
            raise DPECostTeachingValidationError("Revise o cadastro da disciplina.")
        row.code = code
        row.name = name
        row.external_key = _optional_text(payload.get("external_key", row.external_key), max_length=180)
        row.active = bool(payload.get("active", row.active))
        row.notes = _optional_text(payload.get("notes", row.notes))
        self._commit()
        return self._subject_payload(row)

    def _period_teacher_payload(
        self,
        row: DPECostPeriodTeacher,
        *,
        workload_hours: Decimal = Decimal("0"),
        payroll_total: Decimal = Decimal("0"),
        payroll_count: int = 0,
    ) -> dict[str, Any]:
        snapshot = dict(row.teacher_snapshot_json or {})
        teacher = dict(snapshot.get("teacher") or {})
        return {
            "id": row.id,
            "period_id": row.period_id,
            "teacher_id": row.teacher_id,
            "teacher": teacher,
            "aliases": list(snapshot.get("aliases") or []),
            "relationship_type": row.relationship_type or dict(snapshot.get("dpe_profile") or {}).get("relationship_type") or "UNSPECIFIED",
            "included": bool(row.included),
            "notes": row.notes,
            "captured_at": snapshot.get("captured_at"),
            "workload_hours": _decimal(workload_hours),
            "payroll_total": _decimal(payroll_total),
            "payroll_count": int(payroll_count or 0),
        }

    def list_period_teachers(self, period_id: int) -> list[dict[str, Any]]:
        self._period(period_id)
        rows = self.db.scalars(
            select(DPECostPeriodTeacher).where(
                DPECostPeriodTeacher.directorate_id == self.directorate_id,
                DPECostPeriodTeacher.period_id == int(period_id),
            ).order_by(DPECostPeriodTeacher.id)
        ).all()
        workload_rows = self.db.execute(
            select(
                DPECostTeachingActivity.period_teacher_id,
                func.coalesce(func.sum(DPECostTeachingActivity.workload_hours), 0),
            ).where(
                DPECostTeachingActivity.directorate_id == self.directorate_id,
                DPECostTeachingActivity.period_id == int(period_id),
                DPECostTeachingActivity.status == "ACTIVE",
            ).group_by(DPECostTeachingActivity.period_teacher_id)
        ).all()
        workload_map = {int(key): Decimal(str(value or 0)) for key, value in workload_rows}
        payroll_rows = self.db.execute(
            select(
                DPECostExpense.period_teacher_id,
                func.coalesce(func.sum(DPECostExpense.amount), 0),
                func.count(DPECostExpense.id),
            ).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.expense_kind == "PAYROLL",
                DPECostExpense.status == "ACTIVE",
                DPECostExpense.period_teacher_id.is_not(None),
            ).group_by(DPECostExpense.period_teacher_id)
        ).all()
        payroll_map = {int(key): (Decimal(str(total or 0)), int(count or 0)) for key, total, count in payroll_rows}
        payload = []
        for row in rows:
            total, count = payroll_map.get(row.id, (Decimal("0"), 0))
            payload.append(self._period_teacher_payload(
                row, workload_hours=workload_map.get(row.id, Decimal("0")),
                payroll_total=total, payroll_count=count,
            ))
        payload.sort(key=lambda item: str(item.get("teacher", {}).get("display_name") or "").casefold())
        return payload

    def update_period_teacher(self, period_teacher_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.db.scalar(
            select(DPECostPeriodTeacher).where(
                DPECostPeriodTeacher.id == int(period_teacher_id),
                DPECostPeriodTeacher.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Vínculo mensal do docente não encontrado.")
        self._period(row.period_id, editable=True)
        relationship = _text(payload.get("relationship_type", row.relationship_type) or "UNSPECIFIED").upper()
        if relationship not in RELATIONSHIP_TYPES:
            raise DPECostTeachingValidationError("Revise o vínculo do mês.", {"relationship_type": "Selecione um tipo de vínculo válido."})
        before = self._period_teacher_payload(row)
        row.relationship_type = relationship
        row.notes = _optional_text(payload.get("notes", row.notes))
        row.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        add_dpe_audit(
            self.db, self.scope, action="update", entity="dpe_period_teacher",
            entity_id=row.id, period_id=row.period_id, before=before,
            after=self._period_teacher_payload(row),
        )
        self._commit()
        return self._period_teacher_payload(row)

    def _period_offering(self, period_id: int, period_offering_id: int) -> DPECostPeriodOffering:
        row = self.db.scalar(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.id == int(period_offering_id),
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            )
        )
        if not row:
            raise DPECostTeachingValidationError(
                "Curso/contexto inválido para esta competência.", {"offering_allocations": "Selecione apenas cursos/contextos incluídos na competência."}
            )
        return row

    def _validate_allocations(self, period_id: int, workload: Decimal, values: Any) -> list[tuple[DPECostPeriodOffering, Decimal]]:
        if not isinstance(values, list) or not values:
            raise DPECostTeachingValidationError(
                "Informe ao menos um curso/contexto beneficiado.", {"offering_allocations": "Selecione um ou mais cursos/contextos."}
            )
        output: list[tuple[DPECostPeriodOffering, Decimal]] = []
        seen: set[int] = set()
        for item in values:
            if not isinstance(item, dict):
                continue
            try:
                offering_id = int(item.get("period_offering_id"))
            except (TypeError, ValueError):
                raise DPECostTeachingValidationError("Curso/contexto inválido na divisão de carga.")
            if offering_id in seen:
                raise DPECostTeachingValidationError("O mesmo curso/contexto foi informado mais de uma vez.")
            seen.add(offering_id)
            hours = _hours(item.get("allocated_hours"), "allocated_hours")
            output.append((self._period_offering(period_id, offering_id), hours))
        total = sum((hours for _, hours in output), Decimal("0.00"))
        if abs(total - workload) > Decimal("0.01"):
            raise DPECostTeachingValidationError(
                "A divisão entre cursos/contextos precisa fechar a carga horária da atividade.",
                {"offering_allocations": f"A soma dos cursos/contextos é {total}h, mas a atividade possui {workload}h."},
            )
        return output

    def _activity_payload(self, row: DPECostTeachingActivity) -> dict[str, Any]:
        period_teacher = self.db.get(DPECostPeriodTeacher, row.period_teacher_id)
        subject = self.db.get(DPECostSubject, row.subject_id)
        context = dict(row.context_snapshot_json or {})
        allocations = self.db.scalars(
            select(DPECostTeachingActivityOffering)
            .where(DPECostTeachingActivityOffering.activity_id == row.id)
            .order_by(DPECostTeachingActivityOffering.id)
        ).all()
        teacher_snapshot = dict(period_teacher.teacher_snapshot_json or {}) if period_teacher else {}
        teacher = dict(teacher_snapshot.get("teacher") or context.get("teacher") or {})
        subject_snapshot = dict(context.get("subject") or {})
        return {
            "id": row.id,
            "period_id": row.period_id,
            "period_teacher_id": row.period_teacher_id,
            "teacher_id": period_teacher.teacher_id if period_teacher else None,
            "teacher_name": teacher.get("display_name") or "Professor",
            "subject_id": row.subject_id,
            "subject_name": subject_snapshot.get("name") or (subject.name if subject else "Disciplina"),
            "class_group": row.class_group,
            "effective_start_date": _iso(row.effective_start_date),
            "effective_end_date": _iso(row.effective_end_date),
            "workload_hours": _decimal(row.workload_hours),
            "workload_reference": row.workload_reference,
            "source_type": row.source_type,
            "external_key": row.external_key,
            "status": row.status,
            "notes": row.notes,
            "context_snapshot": context,
            "allocations": [
                {
                    "id": alloc.id,
                    "period_offering_id": alloc.period_offering_id,
                    "allocated_hours": _decimal(alloc.allocated_hours),
                    "label": _offering_label(dict(alloc.offering_snapshot_json or {})),
                    "offering_snapshot": dict(alloc.offering_snapshot_json or {}),
                }
                for alloc in allocations
            ],
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "void_reason": row.void_reason,
        }

    def list_activities(self, *, period_id: int, teacher_id: int | None = None, status: str | None = "ACTIVE") -> list[dict[str, Any]]:
        self._period(period_id)
        stmt = select(DPECostTeachingActivity).where(
            DPECostTeachingActivity.directorate_id == self.directorate_id,
            DPECostTeachingActivity.period_id == int(period_id),
        )
        if status:
            stmt = stmt.where(DPECostTeachingActivity.status == status)
        if teacher_id:
            stmt = stmt.join(DPECostPeriodTeacher, DPECostPeriodTeacher.id == DPECostTeachingActivity.period_teacher_id).where(
                DPECostPeriodTeacher.teacher_id == int(teacher_id)
            )
        rows = self.db.scalars(stmt.order_by(DPECostTeachingActivity.created_at, DPECostTeachingActivity.id)).all()
        return [self._activity_payload(row) for row in rows]

    def create_activity(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            period_id = int(payload.get("period_id"))
            teacher_id = int(payload.get("teacher_id"))
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError) as exc:
            raise DPECostTeachingValidationError("Competência, professor e disciplina são obrigatórios.") from exc
        period = self._period(period_id, editable=True)
        teacher = self._teacher(teacher_id)
        subject = self._subject(subject_id)
        workload = _hours(payload.get("workload_hours"))
        allocations = self._validate_allocations(period_id, workload, payload.get("offering_allocations"))
        source_type = _text(payload.get("source_type") or "MANUAL").upper()
        if source_type not in ACTIVITY_SOURCE_TYPES:
            raise DPECostTeachingValidationError("Origem da atividade inválida.", {"source_type": "Origem inválida."})
        effective_start_date, effective_end_date = _activity_dates(
            period.period, payload.get("effective_start_date"), payload.get("effective_end_date")
        )
        period_teacher = self._ensure_period_teacher(period_id, teacher.id)
        context = {
            "snapshot_version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "teacher": dict((period_teacher.teacher_snapshot_json or {}).get("teacher") or {}),
            "subject": self._subject_payload(subject),
            "effective_start_date": _iso(effective_start_date),
            "effective_end_date": _iso(effective_end_date),
        }
        row = DPECostTeachingActivity(
            directorate_id=self.directorate_id,
            period_id=period_id,
            period_teacher_id=period_teacher.id,
            subject_id=subject.id,
            class_group=_optional_text(payload.get("class_group"), max_length=160),
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            workload_hours=workload,
            workload_reference=_optional_text(payload.get("workload_reference"), max_length=120),
            source_type=source_type,
            external_key=_optional_text(payload.get("external_key"), max_length=180),
            context_snapshot_json=context,
            status="ACTIVE",
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.db.add(row)
        self.db.flush()
        for period_offering, allocated_hours in allocations:
            self.db.add(DPECostTeachingActivityOffering(
                activity_id=row.id,
                period_offering_id=period_offering.id,
                allocated_hours=allocated_hours,
                offering_snapshot_json=dict(period_offering.offering_snapshot_json or {}),
            ))
        self.db.flush()
        add_dpe_audit(
            self.db,
            self.scope,
            action="create",
            entity="dpe_teaching_activity",
            entity_id=row.id,
            period_id=row.period_id,
            after=self._activity_payload(row),
        )
        self._commit()
        self.db.refresh(row)
        return self._activity_payload(row)

    def update_activity(self, activity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._activity(activity_id, editable=True)
        before = self._activity_payload(row)
        teacher_id = int(payload.get("teacher_id") or self.db.get(DPECostPeriodTeacher, row.period_teacher_id).teacher_id)
        subject_id = int(payload.get("subject_id") or row.subject_id)
        teacher = self._teacher(teacher_id)
        subject = self._subject(subject_id)
        workload = _hours(payload.get("workload_hours", row.workload_hours))
        allocations = self._validate_allocations(row.period_id, workload, payload.get("offering_allocations"))
        period = self._period(row.period_id, editable=True)
        effective_start_date, effective_end_date = _activity_dates(
            period.period,
            payload.get("effective_start_date", row.effective_start_date),
            payload.get("effective_end_date", row.effective_end_date),
        )
        period_teacher = self._ensure_period_teacher(row.period_id, teacher.id)
        row.period_teacher_id = period_teacher.id
        row.subject_id = subject.id
        row.class_group = _optional_text(payload.get("class_group", row.class_group), max_length=160)
        row.effective_start_date = effective_start_date
        row.effective_end_date = effective_end_date
        row.workload_hours = workload
        row.workload_reference = _optional_text(payload.get("workload_reference", row.workload_reference), max_length=120)
        row.notes = _optional_text(payload.get("notes", row.notes))
        row.context_snapshot_json = {
            "snapshot_version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "teacher": dict((period_teacher.teacher_snapshot_json or {}).get("teacher") or {}),
            "subject": self._subject_payload(subject),
            "effective_start_date": _iso(effective_start_date),
            "effective_end_date": _iso(effective_end_date),
        }
        row.updated_by = self.actor
        self.db.query(DPECostTeachingActivityOffering).filter(
            DPECostTeachingActivityOffering.activity_id == row.id
        ).delete(synchronize_session=False)
        self.db.flush()
        for period_offering, allocated_hours in allocations:
            self.db.add(DPECostTeachingActivityOffering(
                activity_id=row.id,
                period_offering_id=period_offering.id,
                allocated_hours=allocated_hours,
                offering_snapshot_json=dict(period_offering.offering_snapshot_json or {}),
            ))
        self.db.flush()
        add_dpe_audit(
            self.db,
            self.scope,
            action="update",
            entity="dpe_teaching_activity",
            entity_id=row.id,
            period_id=row.period_id,
            before=before,
            after=self._activity_payload(row),
        )
        self._commit()
        self.db.refresh(row)
        return self._activity_payload(row)

    def void_activity(self, activity_id: int, *, reason: str) -> dict[str, Any]:
        row = self._activity(activity_id, editable=True)
        before = self._activity_payload(row)
        reason = _text(reason)
        if not reason:
            raise DPECostTeachingValidationError("Informe o motivo do estorno da atividade.", {"reason": "Motivo obrigatório."})
        row.status = "VOIDED"
        row.void_reason = reason
        row.voided_at = datetime.now(timezone.utc)
        row.voided_by = self.actor
        row.updated_by = self.actor
        add_dpe_audit(
            self.db,
            self.scope,
            action="void",
            entity="dpe_teaching_activity",
            entity_id=row.id,
            period_id=row.period_id,
            before=before,
            after=self._activity_payload(row),
            metadata={"reason": reason},
        )
        self._commit()
        return self._activity_payload(row)

    def _candidate_teacher_map(self) -> dict[str, set[int]]:
        mapping: dict[str, set[int]] = {}
        for teacher_id, normalized in self.db.execute(
            select(Teacher.id, Teacher.normalized_name)
            .join(DPETeacherProfile, DPETeacherProfile.teacher_id == Teacher.id)
            .where(
                DPETeacherProfile.directorate_id == self.directorate_id,
                DPETeacherProfile.active.is_(True),
                Teacher.active.is_(True),
            )
        ).all():
            if normalized:
                mapping.setdefault(str(normalized), set()).add(int(teacher_id))
        for teacher_id, normalized in self.db.execute(
            select(DPETeacherAlias.teacher_id, DPETeacherAlias.normalized_alias)
            .join(DPETeacherProfile, DPETeacherProfile.teacher_id == DPETeacherAlias.teacher_id)
            .where(
                DPETeacherAlias.active.is_(True),
                DPETeacherProfile.directorate_id == self.directorate_id,
                DPETeacherProfile.active.is_(True),
            )
        ).all():
            if normalized:
                mapping.setdefault(str(normalized), set()).add(int(teacher_id))
        return mapping

    def payroll_reconciliation(self, period_id: int) -> list[dict[str, Any]]:
        self._period(period_id)
        expenses = self.db.scalars(
            select(DPECostExpense).where(
                DPECostExpense.directorate_id == self.directorate_id,
                DPECostExpense.period_id == int(period_id),
                DPECostExpense.expense_kind == "PAYROLL",
                DPECostExpense.status == "ACTIVE",
            ).order_by(DPECostExpense.description, DPECostExpense.id)
        ).all()
        candidates = self._candidate_teacher_map()
        active_ids = [row[0] for row in self.db.execute(
            select(DPETeacherProfile.teacher_id).where(
                DPETeacherProfile.directorate_id == self.directorate_id,
                DPETeacherProfile.active.is_(True),
            )
        ).all()]
        teacher_cache = {row.id: row for row in self.db.scalars(select(Teacher).where(Teacher.id.in_(active_ids or [-1]))).all()}
        output: list[dict[str, Any]] = []
        for expense in expenses:
            confirmed = None
            if expense.period_teacher_id:
                period_teacher = self.db.get(DPECostPeriodTeacher, expense.period_teacher_id)
                if period_teacher and period_teacher.period_id == period_id:
                    snap = dict(period_teacher.teacher_snapshot_json or {})
                    confirmed = dict(snap.get("teacher") or {})
                    confirmed["period_teacher_id"] = period_teacher.id
            candidate = None
            candidate_method = None
            if not confirmed and expense.counterparty_name:
                normalized = normalize_person_name(expense.counterparty_name)
                ids = candidates.get(normalized, set())
                if len(ids) == 1:
                    teacher_id = next(iter(ids))
                    teacher = teacher_cache.get(teacher_id)
                    if teacher:
                        candidate = self._teacher_payload(teacher, self._profile(teacher.id), [])
                        candidate_method = "EXACT_NAME" if teacher.normalized_name == normalized else "ALIAS"
            output.append({
                "expense_id": expense.id,
                "description": expense.description,
                "amount": float(expense.amount),
                "counterparty_name": expense.counterparty_name,
                "document_number": expense.document_number,
                "confirmed_teacher": confirmed,
                "match_status": "CONFIRMED" if confirmed else "UNMATCHED",
                "match_method": expense.teacher_match_method if confirmed else None,
                "candidate_teacher": candidate,
                "candidate_method": candidate_method,
            })
        return output

    def link_payroll_expense(self, expense_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        expense = self.db.scalar(
            select(DPECostExpense).where(
                DPECostExpense.id == int(expense_id),
                DPECostExpense.directorate_id == self.directorate_id,
            )
        )
        if not expense:
            raise LookupError("Despesa de folha não encontrada.")
        if expense.expense_kind != "PAYROLL" or expense.status != "ACTIVE":
            raise DPECostTeachingValidationError("Somente despesas ativas de Folha/Pessoal podem ser vinculadas a professor.")
        self._period(expense.period_id, editable=True)
        before = {
            "period_teacher_id": expense.period_teacher_id,
            "teacher_match_status": expense.teacher_match_status,
            "teacher_match_method": expense.teacher_match_method,
        }
        teacher_id = payload.get("teacher_id")
        if teacher_id in (None, ""):
            expense.period_teacher_id = None
            expense.teacher_match_status = None
            expense.teacher_match_method = None
            expense.teacher_snapshot_json = {}
            add_dpe_audit(
                self.db,
                self.scope,
                action="unlink_payroll",
                entity="dpe_payroll_link",
                entity_id=expense.id,
                period_id=expense.period_id,
                before=before,
                after={"period_teacher_id": None, "teacher_match_status": None, "teacher_match_method": None},
            )
            self._commit()
            return {"expense_id": expense.id, "linked": False}
        teacher = self._teacher(int(teacher_id))
        period_teacher = self._ensure_period_teacher(expense.period_id, teacher.id)
        method = _text(payload.get("match_method") or "MANUAL").upper()
        if method not in {"MANUAL", "EXACT_NAME", "ALIAS", "EXTERNAL_ID"}:
            method = "MANUAL"
        expense.period_teacher_id = period_teacher.id
        expense.teacher_match_status = "CONFIRMED"
        expense.teacher_match_method = method
        expense.teacher_snapshot_json = dict(period_teacher.teacher_snapshot_json or {})
        add_dpe_audit(
            self.db,
            self.scope,
            action="link_payroll",
            entity="dpe_payroll_link",
            entity_id=expense.id,
            period_id=expense.period_id,
            before=before,
            after={
                "period_teacher_id": period_teacher.id,
                "teacher_id": teacher.id,
                "teacher_name": teacher.display_name,
                "teacher_match_status": "CONFIRMED",
                "teacher_match_method": method,
            },
        )
        self._commit()
        return {
            "expense_id": expense.id,
            "linked": True,
            "period_teacher_id": period_teacher.id,
            "teacher": dict((period_teacher.teacher_snapshot_json or {}).get("teacher") or {}),
            "match_method": method,
        }

    def period_offerings(self, period_id: int) -> list[dict[str, Any]]:
        self._period(period_id)
        rows = self.db.scalars(
            select(DPECostPeriodOffering).where(
                DPECostPeriodOffering.period_id == int(period_id),
                DPECostPeriodOffering.included.is_(True),
            ).order_by(DPECostPeriodOffering.id)
        ).all()
        return [
            {
                "id": row.id,
                "offering_id": row.offering_id,
                "label": _offering_label(dict(row.offering_snapshot_json or {})),
                "snapshot": dict(row.offering_snapshot_json or {}),
            }
            for row in rows
        ]

    def central_payload(self, *, period_id: int | None = None) -> dict[str, Any]:
        periods = self.db.scalars(
            select(DPECostPeriod).where(DPECostPeriod.directorate_id == self.directorate_id)
            .order_by(DPECostPeriod.period.desc())
        ).all()
        selected = None
        if period_id:
            selected = self._period(int(period_id))
        elif periods:
            selected = periods[0]
        activities = self.list_activities(period_id=selected.id) if selected else []
        period_teachers = self.list_period_teachers(selected.id) if selected else []
        payroll = self.payroll_reconciliation(selected.id) if selected else []
        offerings = self.period_offerings(selected.id) if selected else []
        total_hours = round(sum(float(row["workload_hours"]) for row in activities), 2)
        linked_payroll = sum(1 for row in payroll if row["match_status"] == "CONFIRMED")
        return {
            "periods": [
                {"id": row.id, "period": row.period, "status": row.status, "notes": row.notes}
                for row in periods
            ],
            "selected_period": (
                {"id": selected.id, "period": selected.period, "status": selected.status, "notes": selected.notes}
                if selected else None
            ),
            "editable": bool(selected and selected.status in EDITABLE_PERIOD_STATUSES),
            "teachers": self.list_teachers(),
            "subjects": self.list_subjects(),
            "period_teachers": period_teachers,
            "offerings": offerings,
            "activities": activities,
            "payroll": payroll,
            "summary": {
                "period_teacher_count": len(period_teachers),
                "activity_count": len(activities),
                "total_workload_hours": total_hours,
                "payroll_count": len(payroll),
                "payroll_linked_count": linked_payroll,
                "payroll_pending_count": len(payroll) - linked_payroll,
                "subject_count": len(self.list_subjects(active_only=True)),
            },
        }
