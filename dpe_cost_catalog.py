from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dpe_audit import add_dpe_audit
from dpe_course_context import (
    context_label, default_context_code, is_default_context, normalize_modality,
)
from models import (
    Course,
    Directorate,
    DPEAcademicOffering,
    DPEAcademicProduct,
    DPECostPeriod,
    DPECostPeriodOffering,
)
from security import DirectorateScope

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ACADEMIC_LEVELS = ("GRADUATION", "TECHNICAL", "POSTGRADUATE", "EXTENSION", "OTHER")
PERIOD_STATUSES = ("DRAFT", "REVIEW", "CALCULATED", "CLOSED")
EDITABLE_PERIOD_STATUSES = ("DRAFT", "REVIEW")
OFFICIAL_ACADEMIC_DIRECTORATES = ("DTNH", "DCS")


class DPECostCatalogValidationError(ValueError):
    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.field_errors = field_errors or {}


def _text(value: Any, *, max_length: int | None = None) -> str:
    output = str(value or "").strip()
    if max_length and len(output) > max_length:
        output = output[:max_length]
    return output


def _optional_text(value: Any, *, max_length: int | None = None) -> str | None:
    output = _text(value, max_length=max_length)
    return output or None


def _code(value: Any, *, max_length: int) -> str:
    output = _text(value, max_length=max_length).upper()
    output = re.sub(r"\s+", "-", output)
    output = re.sub(r"[^A-Z0-9._/-]+", "-", output)
    output = re.sub(r"-+", "-", output).strip("-")
    return output


def _period(value: Any, *, required: bool = True) -> str | None:
    output = _text(value)
    if not output and not required:
        return None
    if not PERIOD_RE.fullmatch(output):
        raise DPECostCatalogValidationError(
            "Competência inválida.", {"period": "Use o formato AAAA-MM, por exemplo 2026-09."}
        )
    return output


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class DPECostCatalogRepository:
    """Operational catalog and competence service for DPE Cost Engine v0.9.6.14.

    This layer deliberately does not calculate costs. It owns the economic
    catalog and the historical boundary used by future expense/allocation
    stages. Master records may evolve; competence snapshots do not change
    unless an editable competence is explicitly refreshed.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DPE":
            raise PermissionError("O Cost Engine pertence exclusivamente à DPE.")
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
            raise DPECostCatalogValidationError(
                "Não foi possível salvar porque já existe um registro com a mesma identificação ou há uma referência inválida."
            ) from exc

    def _official_course(self, course_id: int) -> Course:
        row = self.db.scalar(
            select(Course)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(
                Course.id == int(course_id),
                Course.active.is_(True),
                Directorate.code.in_(OFFICIAL_ACADEMIC_DIRECTORATES),
                Directorate.active.is_(True),
            )
        )
        if not row:
            raise DPECostCatalogValidationError(
                "O curso precisa existir e estar ativo no catálogo acadêmico oficial.",
                {"source_course_id": "Selecione um curso ativo de DTNH ou DCS."},
            )
        return row

    def _source_course_for_product(self, product: DPEAcademicProduct) -> Course:
        if not product.source_course_id:
            raise DPECostCatalogValidationError(
                "O curso econômico precisa estar vinculado ao catálogo acadêmico oficial.",
                {"source_course_id": "Revise o vínculo do curso antes de continuar."},
            )
        return self._official_course(int(product.source_course_id))

    def _default_context_for_product(self, product: DPEAcademicProduct) -> DPEAcademicOffering | None:
        rows = self.db.scalars(
            select(DPEAcademicOffering).where(
                DPEAcademicOffering.directorate_id == self.directorate_id,
                DPEAcademicOffering.product_id == product.id,
            )
        ).all()
        return next((row for row in rows if is_default_context(row, product)), None)

    def _ensure_default_context(self, product: DPEAcademicProduct, source_course: Course) -> DPEAcademicOffering:
        row = self._default_context_for_product(product)
        modality = normalize_modality(source_course.modality)
        if row is None:
            row = DPEAcademicOffering(
                directorate_id=self.directorate_id,
                product_id=product.id,
                code=default_context_code(product.code),
                modality=modality,
                shift=None,
                campus=None,
                unit_name=None,
                pole_name=None,
                external_key=None,
                active=bool(product.active),
                valid_from=product.valid_from,
                valid_to=product.valid_to,
                notes="Contexto-base automático do curso. Não representa um contexto separado.",
                created_by=self.actor,
            )
            self.db.add(row)
        else:
            row.code = default_context_code(product.code)
            row.modality = modality
            row.active = bool(product.active)
            row.valid_from = product.valid_from
            row.valid_to = product.valid_to
        self.db.flush()
        return row

    def _product(self, product_id: int) -> DPEAcademicProduct:
        row = self.db.scalar(
            select(DPEAcademicProduct).where(
                DPEAcademicProduct.id == product_id,
                DPEAcademicProduct.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Produto acadêmico econômico não encontrado.")
        return row

    def _offering(self, offering_id: int) -> DPEAcademicOffering:
        row = self.db.scalar(
            select(DPEAcademicOffering).where(
                DPEAcademicOffering.id == offering_id,
                DPEAcademicOffering.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Contexto econômico não encontrado.")
        return row

    def _period_row(self, period_id: int) -> DPECostPeriod:
        row = self.db.scalar(
            select(DPECostPeriod).where(
                DPECostPeriod.id == period_id,
                DPECostPeriod.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Competência DPE não encontrada.")
        return row

    def _snapshot(self, snapshot_id: int) -> DPECostPeriodOffering:
        row = self.db.scalar(
            select(DPECostPeriodOffering)
            .join(DPECostPeriod, DPECostPeriod.id == DPECostPeriodOffering.period_id)
            .where(
                DPECostPeriodOffering.id == snapshot_id,
                DPECostPeriod.directorate_id == self.directorate_id,
            )
        )
        if not row:
            raise LookupError("Curso/contexto da competência não encontrado.")
        return row

    def _product_payload(self, row: DPEAcademicProduct) -> dict[str, Any]:
        source = row.source_course
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "academic_level": row.academic_level,
            "source_course_id": row.source_course_id,
            "source_modality": normalize_modality(source.modality) if source else None,
            "external_key": row.external_key,
            "active": bool(row.active),
            "valid_from": row.valid_from,
            "valid_to": row.valid_to,
            "notes": row.notes,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def _offering_payload(self, row: DPEAcademicOffering, product: DPEAcademicProduct | None = None) -> dict[str, Any]:
        product = product or row.product
        product_payload = self._product_payload(product)
        offering_payload = {
            "id": row.id,
            "code": row.code,
            "modality": normalize_modality(row.modality),
            "shift": row.shift,
            "campus": row.campus,
            "unit_name": row.unit_name,
            "pole_name": row.pole_name,
            "external_key": row.external_key,
            "valid_from": row.valid_from,
            "valid_to": row.valid_to,
        }
        default_context = is_default_context(offering_payload, product_payload)
        offering_payload["is_default_context"] = default_context
        offering_payload["context_kind"] = "BASE" if default_context else "CUSTOM"
        return {
            "id": row.id,
            "product_id": row.product_id,
            "product_code": product.code,
            "product_name": product.name,
            "academic_level": product.academic_level,
            "source_modality": product_payload.get("source_modality"),
            "code": row.code,
            "label": context_label(product_payload, offering_payload),
            "modality": offering_payload["modality"],
            "shift": row.shift,
            "campus": row.campus,
            "unit_name": row.unit_name,
            "pole_name": row.pole_name,
            "external_key": row.external_key,
            "is_default_context": default_context,
            "context_kind": "BASE" if default_context else "CUSTOM",
            "active": bool(row.active),
            "valid_from": row.valid_from,
            "valid_to": row.valid_to,
            "notes": row.notes,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def _snapshot_json(self, offering: DPEAcademicOffering, product: DPEAcademicProduct) -> dict[str, Any]:
        source = product.source_course
        product_payload = {
            "id": product.id,
            "code": product.code,
            "name": product.name,
            "academic_level": product.academic_level,
            "source_course_id": product.source_course_id,
            "source_modality": normalize_modality(source.modality) if source else None,
            "external_key": product.external_key,
            "valid_from": product.valid_from,
            "valid_to": product.valid_to,
        }
        offering_payload = {
            "id": offering.id,
            "code": offering.code,
            "modality": normalize_modality(offering.modality),
            "shift": offering.shift,
            "campus": offering.campus,
            "unit_name": offering.unit_name,
            "pole_name": offering.pole_name,
            "external_key": offering.external_key,
            "valid_from": offering.valid_from,
            "valid_to": offering.valid_to,
        }
        default_context = is_default_context(offering_payload, product_payload)
        offering_payload["is_default_context"] = default_context
        offering_payload["context_kind"] = "BASE" if default_context else "CUSTOM"
        return {
            "snapshot_version": 2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "product": product_payload,
            "offering": offering_payload,
        }

    @staticmethod
    def _snapshot_payload(row: DPECostPeriodOffering) -> dict[str, Any]:
        snap = dict(row.offering_snapshot_json or {})
        product = dict(snap.get("product") or {})
        offering = dict(snap.get("offering") or {})
        return {
            "id": row.id,
            "period_id": row.period_id,
            "offering_id": row.offering_id,
            "included": bool(row.included),
            "label": context_label(product, offering),
            "product": product,
            "offering": offering,
            "snapshot_version": snap.get("snapshot_version", 1),
            "captured_at": snap.get("captured_at"),
            "created_at": _iso(row.created_at),
        }

    def list_products(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = select(DPEAcademicProduct).where(DPEAcademicProduct.directorate_id == self.directorate_id)
        if active_only:
            stmt = stmt.where(DPEAcademicProduct.active.is_(True))
        rows = self.db.scalars(stmt.order_by(DPEAcademicProduct.name, DPEAcademicProduct.code)).all()
        all_offerings = self.db.scalars(
            select(DPEAcademicOffering).where(DPEAcademicOffering.directorate_id == self.directorate_id)
        ).all()
        grouped: dict[int, list[DPEAcademicOffering]] = {}
        for offering in all_offerings:
            grouped.setdefault(int(offering.product_id), []).append(offering)
        output = []
        for row in rows:
            items = grouped.get(int(row.id), [])
            custom_count = sum(1 for item in items if not is_default_context(item, row))
            output.append({
                **self._product_payload(row),
                "offering_count": len(items),
                "context_count": custom_count,
                "has_default_context": any(is_default_context(item, row) for item in items),
            })
        return output

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = _code(payload.get("code"), max_length=80)
        source_course_id = payload.get("source_course_id") or None
        errors: dict[str, str] = {}
        source_course = None
        if not code:
            errors["code"] = "Informe um código único."
        if not source_course_id:
            errors["source_course_id"] = "Selecione o curso correspondente no catálogo acadêmico oficial."
        else:
            try:
                source_course_id = int(source_course_id)
                source_course = self._official_course(source_course_id)
            except (TypeError, ValueError):
                errors["source_course_id"] = "Curso institucional inválido."
            except DPECostCatalogValidationError as exc:
                errors.update(exc.field_errors or {"source_course_id": str(exc)})
        if errors:
            raise DPECostCatalogValidationError("Revise os dados do produto.", errors)
        assert source_course is not None
        row = DPEAcademicProduct(
            directorate_id=self.directorate_id,
            code=code,
            name=source_course.name,
            academic_level="GRADUATION",
            source_course_id=source_course.id,
            external_key=_optional_text(payload.get("external_key"), max_length=160),
            active=bool(source_course.active),
            valid_from=source_course.valid_from,
            valid_to=source_course.valid_to,
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
        )
        self.db.add(row)
        self.db.flush()
        self._ensure_default_context(row, source_course)
        self._commit()
        self.db.refresh(row)
        return self._product_payload(row)

    def update_product(self, product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._product(product_id)
        # Resolve the technical base context before changing the product code;
        # otherwise <old-code>-BASE would no longer be recognizable afterwards.
        default_context = self._default_context_for_product(row)
        merged = {**self._product_payload(row), **payload}
        code = _code(merged.get("code"), max_length=80)
        source_course_id = merged.get("source_course_id") or None
        errors: dict[str, str] = {}
        if not code:
            errors["code"] = "Informe um código único."
        if not source_course_id:
            errors["source_course_id"] = "O DPE operacional precisa estar ligado a um curso do catálogo acadêmico oficial."
        source_course = None
        if source_course_id:
            try:
                source_course_id = int(source_course_id)
                source_course = self._official_course(source_course_id)
            except (TypeError, ValueError):
                errors["source_course_id"] = "Curso institucional inválido."
            except DPECostCatalogValidationError as exc:
                errors.update(exc.field_errors or {"source_course_id": str(exc)})
        if errors:
            raise DPECostCatalogValidationError("Revise os dados do produto.", errors)
        assert source_course is not None
        row.code = code
        row.name = source_course.name
        row.academic_level = "GRADUATION"
        row.source_course_id = source_course.id
        row.external_key = _optional_text(merged.get("external_key"), max_length=160)
        row.active = bool(source_course.active)
        row.valid_from = source_course.valid_from
        row.valid_to = source_course.valid_to
        row.notes = _optional_text(merged.get("notes"))
        self.db.flush()
        if default_context is not None:
            default_context.code = default_context_code(row.code)
            default_context.modality = normalize_modality(source_course.modality)
            default_context.active = bool(row.active)
            default_context.valid_from = row.valid_from
            default_context.valid_to = row.valid_to
            self.db.flush()
        self._commit()
        self.db.refresh(row)
        return self._product_payload(row)

    def list_offerings(self, *, product_id: int | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        stmt = (
            select(DPEAcademicOffering, DPEAcademicProduct)
            .join(DPEAcademicProduct, DPEAcademicProduct.id == DPEAcademicOffering.product_id)
            .where(DPEAcademicOffering.directorate_id == self.directorate_id)
        )
        if product_id:
            stmt = stmt.where(DPEAcademicOffering.product_id == int(product_id))
        if active_only:
            stmt = stmt.where(DPEAcademicOffering.active.is_(True))
        rows = self.db.execute(
            stmt.order_by(DPEAcademicProduct.name, DPEAcademicOffering.modality, DPEAcademicOffering.shift, DPEAcademicOffering.code)
        ).all()
        return [self._offering_payload(offering, product) for offering, product in rows]

    def create_offering(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            product_id = int(payload.get("product_id"))
        except (TypeError, ValueError):
            raise DPECostCatalogValidationError("Revise os dados do contexto.", {"product_id": "Selecione um curso."})
        product = self._product(product_id)
        source_course = self._source_course_for_product(product)
        code = _code(payload.get("code"), max_length=100)
        modality = normalize_modality(payload.get("modality") or source_course.modality)
        shift = _optional_text(payload.get("shift"), max_length=40)
        campus = _optional_text(payload.get("campus"), max_length=120)
        unit_name = _optional_text(payload.get("unit_name"), max_length=160)
        pole_name = _optional_text(payload.get("pole_name"), max_length=160)
        external_key = _optional_text(payload.get("external_key"), max_length=180)
        valid_from = _period(payload.get("valid_from") or product.valid_from)
        valid_to = _period(payload.get("valid_to"), required=False)
        errors: dict[str, str] = {}
        if not code:
            errors["code"] = "Informe uma identificação para o contexto."
        if code == default_context_code(product.code):
            errors["code"] = "Esta identificação é reservada ao contexto-base automático do curso."
        if valid_to and valid_to < valid_from:
            errors["valid_to"] = "A vigência final não pode ser anterior à inicial."
        active = bool(payload.get("active", True))
        if not active and not valid_to:
            errors["valid_to"] = "Ao criar um contexto inativo, informe a última competência de vigência."
        if errors:
            raise DPECostCatalogValidationError("Revise os dados do contexto.", errors)
        row = DPEAcademicOffering(
            directorate_id=self.directorate_id,
            product_id=product.id,
            code=code,
            modality=modality,
            shift=shift,
            campus=campus,
            unit_name=unit_name,
            pole_name=pole_name,
            external_key=external_key,
            active=active,
            valid_from=valid_from,
            valid_to=valid_to,
            notes=_optional_text(payload.get("notes")),
            created_by=self.actor,
        )
        self.db.add(row)
        self._commit()
        self.db.refresh(row)
        return self._offering_payload(row, product)

    def update_offering(self, offering_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._offering(offering_id)
        product = self._product(row.product_id)
        if is_default_context(row, product):
            raise DPECostCatalogValidationError(
                "O contexto-base é mantido automaticamente pelo curso.",
                {"context": "Edite o curso principal ou crie um contexto adicional."},
            )
        current = self._offering_payload(row, product)
        merged = {**current, **payload}
        product_id = int(merged.get("product_id") or row.product_id)
        product = self._product(product_id)
        source_course = self._source_course_for_product(product)
        code = _code(merged.get("code"), max_length=100)
        modality = normalize_modality(merged.get("modality") or source_course.modality)
        shift = _optional_text(merged.get("shift"), max_length=40)
        campus = _optional_text(merged.get("campus"), max_length=120)
        unit_name = _optional_text(merged.get("unit_name"), max_length=160)
        pole_name = _optional_text(merged.get("pole_name"), max_length=160)
        external_key = _optional_text(merged.get("external_key"), max_length=180)
        valid_from = _period(merged.get("valid_from") or product.valid_from)
        valid_to = _period(merged.get("valid_to"), required=False)
        active = bool(merged.get("active", True))
        errors: dict[str, str] = {}
        if not code:
            errors["code"] = "Informe uma identificação para o contexto."
        if code == default_context_code(product.code):
            errors["code"] = "Esta identificação é reservada ao contexto-base automático do curso."
        if valid_to and valid_to < valid_from:
            errors["valid_to"] = "A vigência final não pode ser anterior à inicial."
        if not active and not valid_to:
            errors["valid_to"] = "Ao inativar um contexto, informe a última competência de vigência."
        if errors:
            raise DPECostCatalogValidationError("Revise os dados do contexto.", errors)
        row.product_id = product.id
        row.code = code
        row.modality = modality
        row.shift = shift
        row.campus = campus
        row.unit_name = unit_name
        row.pole_name = pole_name
        row.external_key = external_key
        row.active = active
        row.valid_from = valid_from
        row.valid_to = valid_to
        row.notes = _optional_text(merged.get("notes"))
        self._commit()
        self.db.refresh(row)
        return self._offering_payload(row, product)

    def list_periods(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(DPECostPeriod)
            .where(DPECostPeriod.directorate_id == self.directorate_id)
            .order_by(DPECostPeriod.period.desc())
        ).all()
        if not rows:
            return []
        ids = [row.id for row in rows]
        counts: dict[int, dict[str, int]] = {row.id: {"total": 0, "included": 0} for row in rows}
        for period_id, included, total in self.db.execute(
            select(DPECostPeriodOffering.period_id, DPECostPeriodOffering.included, func.count(DPECostPeriodOffering.id))
            .where(DPECostPeriodOffering.period_id.in_(ids))
            .group_by(DPECostPeriodOffering.period_id, DPECostPeriodOffering.included)
        ).all():
            counts[period_id]["total"] += int(total or 0)
            if included:
                counts[period_id]["included"] += int(total or 0)
        return [self._period_payload(row, counts[row.id]) for row in rows]

    def _period_payload(self, row: DPECostPeriod, counts: dict[str, int] | None = None) -> dict[str, Any]:
        counts = counts or {"total": 0, "included": 0}
        return {
            "id": row.id,
            "period": row.period,
            "status": row.status,
            "notes": row.notes,
            "opened_at": _iso(row.opened_at),
            "opened_by": row.opened_by,
            "closed_at": _iso(row.closed_at),
            "closed_by": row.closed_by,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "offering_count": int(counts.get("total", 0)),
            "included_offering_count": int(counts.get("included", 0)),
            "editable": row.status in EDITABLE_PERIOD_STATUSES,
        }

    def get_period(self, period_id: int) -> dict[str, Any]:
        row = self._period_row(period_id)
        snapshots = self.db.scalars(
            select(DPECostPeriodOffering)
            .where(DPECostPeriodOffering.period_id == row.id)
            .order_by(DPECostPeriodOffering.id)
        ).all()
        items = [self._snapshot_payload(item) for item in snapshots]
        counts = {"total": len(items), "included": sum(1 for item in items if item["included"])}
        return {**self._period_payload(row, counts), "offerings": items}

    def create_period(self, payload: dict[str, Any]) -> dict[str, Any]:
        period = _period(payload.get("period"))
        row = DPECostPeriod(
            directorate_id=self.directorate_id,
            period=period,
            status="DRAFT",
            notes=_optional_text(payload.get("notes")),
            opened_by=self.actor,
            created_by=self.actor,
        )
        self.db.add(row)
        self.db.flush()
        add_dpe_audit(
            self.db,
            self.scope,
            action="open_period",
            entity="dpe_cost_period",
            entity_id=row.id,
            period_id=row.id,
            after={"period": row.period, "status": row.status, "notes": row.notes},
        )
        self._commit()
        self.db.refresh(row)
        if bool(payload.get("materialize_offerings", True)):
            self.refresh_period_offerings(row.id)
        return self.get_period(row.id)

    def update_period(self, period_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._period_row(period_id)
        if row.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostCatalogValidationError("Esta competência já não pode ser alterada nesta etapa do Cost Engine.")
        status = _text(payload.get("status") or row.status).upper()
        if status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostCatalogValidationError(
                "Nesta versão a competência pode permanecer apenas em Preparação ou Conferência; cálculo e fechamento entram nas próximas etapas.",
                {"status": "Use DRAFT ou REVIEW."},
            )
        before = {"status": row.status, "notes": row.notes}
        row.status = status
        if "notes" in payload:
            row.notes = _optional_text(payload.get("notes"))
        add_dpe_audit(
            self.db,
            self.scope,
            action="update_period",
            entity="dpe_cost_period",
            entity_id=row.id,
            period_id=row.id,
            before=before,
            after={"status": row.status, "notes": row.notes},
        )
        self._commit()
        return self.get_period(row.id)

    def _eligible_offerings(self, period: str) -> list[tuple[DPEAcademicOffering, DPEAcademicProduct]]:
        """Return operational course contexts for a competence, regardless of modality.

        A course can operate directly through its automatic base context. When one
        or more explicit contexts are active for the competence, those contexts
        replace the base context so the course is never counted twice.
        """
        rows = self.db.execute(
            select(DPEAcademicOffering, DPEAcademicProduct)
            .join(DPEAcademicProduct, DPEAcademicProduct.id == DPEAcademicOffering.product_id)
            .join(Course, Course.id == DPEAcademicProduct.source_course_id)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(
                DPEAcademicOffering.directorate_id == self.directorate_id,
                DPEAcademicProduct.directorate_id == self.directorate_id,
                DPEAcademicOffering.active.is_(True),
                DPEAcademicProduct.active.is_(True),
                Course.active.is_(True),
                Directorate.code.in_(OFFICIAL_ACADEMIC_DIRECTORATES),
                Directorate.active.is_(True),
                DPEAcademicOffering.valid_from <= period,
                or_(DPEAcademicOffering.valid_to.is_(None), DPEAcademicOffering.valid_to >= period),
                DPEAcademicProduct.valid_from <= period,
                or_(DPEAcademicProduct.valid_to.is_(None), DPEAcademicProduct.valid_to >= period),
                Course.valid_from <= period,
                or_(Course.valid_to.is_(None), Course.valid_to >= period),
            )
            .order_by(DPEAcademicProduct.name, DPEAcademicOffering.shift, DPEAcademicOffering.code)
        ).all()
        grouped: dict[int, list[tuple[DPEAcademicOffering, DPEAcademicProduct]]] = {}
        for offering, product in rows:
            grouped.setdefault(int(product.id), []).append((offering, product))
        selected: list[tuple[DPEAcademicOffering, DPEAcademicProduct]] = []
        for items in grouped.values():
            custom = [(offering, product) for offering, product in items if not is_default_context(offering, product)]
            if custom:
                selected.extend(custom)
            else:
                selected.extend((offering, product) for offering, product in items if is_default_context(offering, product))
        return selected

    def refresh_period_offerings(self, period_id: int) -> dict[str, Any]:
        period = self._period_row(period_id)
        if period.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostCatalogValidationError("O snapshot só pode ser atualizado enquanto a competência estiver em preparação ou conferência.")
        eligible = self._eligible_offerings(period.period)
        existing = {
            row.offering_id: row
            for row in self.db.scalars(
                select(DPECostPeriodOffering).where(DPECostPeriodOffering.period_id == period.id)
            ).all()
        }
        before = {
            str(offering_id): {"snapshot_id": snapshot.id, "included": bool(snapshot.included)}
            for offering_id, snapshot in existing.items()
        }
        eligible_ids: set[int] = set()
        for offering, product in eligible:
            eligible_ids.add(offering.id)
            snapshot = existing.get(offering.id)
            if snapshot is None:
                snapshot = DPECostPeriodOffering(
                    period_id=period.id,
                    offering_id=offering.id,
                    offering_snapshot_json=self._snapshot_json(offering, product),
                    included=True,
                    created_by=self.actor,
                )
                self.db.add(snapshot)
            else:
                # Preserve explicit inclusion/exclusion choices while refreshing
                # the descriptive snapshot of an editable competence.
                snapshot.offering_snapshot_json = self._snapshot_json(offering, product)
        for offering_id, snapshot in existing.items():
            if offering_id not in eligible_ids:
                snapshot.included = False
        self.db.flush()
        current_rows = self.db.scalars(
            select(DPECostPeriodOffering).where(DPECostPeriodOffering.period_id == period.id)
        ).all()
        add_dpe_audit(
            self.db,
            self.scope,
            action="refresh_period_offerings",
            entity="dpe_period_offerings",
            entity_id=period.id,
            period_id=period.id,
            before=before,
            after={
                str(row.offering_id): {"snapshot_id": row.id, "included": bool(row.included)}
                for row in current_rows
            },
            metadata={"eligible_count": len(eligible_ids)},
        )
        self._commit()
        return self.get_period(period.id)

    def set_period_offering_included(self, period_id: int, snapshot_id: int, included: bool) -> dict[str, Any]:
        period = self._period_row(period_id)
        if period.status not in EDITABLE_PERIOD_STATUSES:
            raise DPECostCatalogValidationError("Não é possível alterar os cursos/contextos de uma competência bloqueada.")
        row = self._snapshot(snapshot_id)
        if row.period_id != period.id:
            raise LookupError("O curso/contexto informado não pertence a esta competência.")
        before = {"included": bool(row.included)}
        row.included = bool(included)
        add_dpe_audit(
            self.db,
            self.scope,
            action="set_period_offering",
            entity="dpe_period_offering",
            entity_id=row.id,
            period_id=period.id,
            before=before,
            after={"included": bool(row.included)},
            metadata={"offering_id": row.offering_id},
        )
        self._commit()
        return self.get_period(period.id)

    def summary(self) -> dict[str, Any]:
        products = self.list_products()
        offerings = self.list_offerings()
        periods = self.list_periods()
        return {
            "products": products,
            "offerings": offerings,
            "periods": periods,
            "counts": {
                "products": len(products),
                "active_products": sum(1 for item in products if item["active"]),
                "offerings": len(offerings),
                "active_offerings": sum(1 for item in offerings if item["active"]),
                "contexts": sum(1 for item in offerings if not item.get("is_default_context")),
                "active_contexts": sum(1 for item in offerings if item["active"] and not item.get("is_default_context")),
                "base_contexts": sum(1 for item in offerings if item.get("is_default_context")),
                "periods": len(periods),
                "draft_periods": sum(1 for item in periods if item["status"] == "DRAFT"),
                "review_periods": sum(1 for item in periods if item["status"] == "REVIEW"),
            },
        }
