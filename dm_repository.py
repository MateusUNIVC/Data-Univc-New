from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload

from auth.objects import require_object_for_directorate

from dm_catalog import (
    DMValidationError,
    cohort_key,
    cohort_label,
    normalize_area,
    normalize_diploma_status,
    parse_date,
    positive_int,
    validate_cohort_payload,
    validate_student_payload,
)
from dm_sei_parser import DMSEIReport, filter_report
from models import DmCohort, DmGraduationEvent, DmSeiSyncRun, DmStudent
from security import DirectorateScope


class DMRepository:
    def __init__(self, db: Session, scope: DirectorateScope):
        if scope.directorate_code != "DM":
            raise PermissionError("Esta operação pertence exclusivamente à Diretoria de Mestrado.")
        self.db = db
        self.scope = scope

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    def _require_write(self) -> None:
        if not self.scope.can_write:
            raise PermissionError("A Diretoria de Mestrado está disponível somente para leitura.")

    @staticmethod
    def cohort_to_dict(row: DmCohort, *, student_count: int | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "area_code": row.area_code,
            "area_name": row.area_name,
            "cohort_number": row.cohort_number,
            "cohort_key": cohort_key(row.area_code, row.cohort_number),
            "cohort_label": cohort_label(row.cohort_number),
            "opening_date": row.opening_date.isoformat() if row.opening_date else None,
            "vacancies_authorized": row.vacancies_authorized,
            "status": row.status,
            "notes": row.notes,
            "source_system": row.source_system or ("DEMO" if row.is_demo else "MANUAL"),
            "sei_raw_label": row.sei_raw_label,
            "last_seen_sei_at": row.last_seen_sei_at.isoformat() if row.last_seen_sei_at else None,
            "is_demo": bool(row.is_demo),
            "student_count": student_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def student_to_dict(row: DmStudent) -> dict[str, Any]:
        cohort = row.cohort
        return {
            "id": row.id,
            "cohort_id": row.cohort_id,
            "area_code": cohort.area_code if cohort else None,
            "area_name": cohort.area_name if cohort else None,
            "cohort_number": cohort.cohort_number if cohort else None,
            "cohort_label": cohort_label(cohort.cohort_number) if cohort else None,
            "cohort_opening_date": cohort.opening_date.isoformat() if cohort and cohort.opening_date else None,
            "student_code": row.student_code,
            "student_name": row.student_name,
            "entry_date": row.entry_date.isoformat() if row.entry_date else None,
            "qualification_date": row.qualification_date.isoformat() if row.qualification_date else None,
            "defense_date": row.defense_date.isoformat() if row.defense_date else None,
            "graduation_date": row.graduation_date.isoformat() if row.graduation_date else None,
            "defense_scheduled_date": row.defense_scheduled_date.isoformat() if row.defense_scheduled_date else None,
            "exit_date": row.exit_date.isoformat() if row.exit_date else None,
            "status": row.status,
            "advisor": row.advisor,
            "research_line": row.research_line,
            "diploma_status": row.diploma_status,
            "graduation_updated_at": row.graduation_updated_at.isoformat() if row.graduation_updated_at else None,
            "graduation_updated_by": row.graduation_updated_by,
            "notes": row.notes,
            "entry_date_estimated": bool(row.entry_date_estimated),
            "source_system": row.source_system or ("DEMO" if row.is_demo else "MANUAL"),
            "sei_raw_status": row.sei_raw_status,
            "last_seen_sei_at": row.last_seen_sei_at.isoformat() if row.last_seen_sei_at else None,
            "last_course_dates_sei_at": row.last_course_dates_sei_at.isoformat() if row.last_course_dates_sei_at else None,
            "data_quality": (
                "Ingresso pendente"
                if not row.entry_date
                else (
                    "Ingresso provisório"
                    if row.entry_date_estimated
                    else ("Ingresso confirmado pelo SEI" if row.last_course_dates_sei_at else "Ingresso confirmado")
                )
            ),
            "is_demo": bool(row.is_demo),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def get_cohort(self, cohort_id: int) -> DmCohort:
        return require_object_for_directorate(
            self.db, DmCohort, cohort_id, self.directorate_id, label="Turma"
        )

    def find_cohort(self, area: Any, cohort_number: Any) -> DmCohort:
        area_code, _ = normalize_area(area)
        number = positive_int(cohort_number, field="turma", required=True)
        row = self.db.scalar(
            select(DmCohort).where(
                DmCohort.directorate_id == self.directorate_id,
                DmCohort.area_code == area_code,
                DmCohort.cohort_number == number,
            )
        )
        if not row:
            raise LookupError(f"{cohort_label(number)} não cadastrada para a área informada.")
        return row

    def _reconcile_cohort_statuses(self, cohort_ids: set[int] | list[int] | tuple[int, ...]) -> dict[int, str]:
        """Reconcile cohort lifecycle from the active student domain.

        A cohort with at least one student is Encerrada when every student is
        terminal (Titulado or Desligado). If an Ativo student later exists in an
        Encerrada cohort, it returns to Em andamento. Planejada/Aberta cohorts
        with active students keep their explicit formation state.

        This method intentionally does not commit; callers compose it into their
        existing transaction.
        """
        ids = sorted({int(value) for value in cohort_ids if value not in (None, "")})
        if not ids:
            return {}
        cohorts = self.db.scalars(
            select(DmCohort).where(
                DmCohort.directorate_id == self.directorate_id,
                DmCohort.id.in_(ids),
            )
        ).all()
        changes: dict[int, str] = {}
        for cohort in cohorts:
            total = int(self.db.scalar(
                select(func.count()).select_from(DmStudent).where(
                    DmStudent.directorate_id == self.directorate_id,
                    DmStudent.cohort_id == cohort.id,
                )
            ) or 0)
            if total <= 0:
                continue
            active = int(self.db.scalar(
                select(func.count()).select_from(DmStudent).where(
                    DmStudent.directorate_id == self.directorate_id,
                    DmStudent.cohort_id == cohort.id,
                    DmStudent.status == "Ativo",
                )
            ) or 0)
            terminal = int(self.db.scalar(
                select(func.count()).select_from(DmStudent).where(
                    DmStudent.directorate_id == self.directorate_id,
                    DmStudent.cohort_id == cohort.id,
                    DmStudent.status.in_(("Titulado", "Desligado")),
                )
            ) or 0)
            desired = cohort.status
            if terminal == total:
                desired = "Encerrada"
            elif active > 0 and cohort.status == "Encerrada":
                desired = "Em andamento"
            if desired != cohort.status:
                cohort.status = desired
                changes[cohort.id] = desired
        return changes

    def list_cohorts(self, *, area_code: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        conditions = [DmCohort.directorate_id == self.directorate_id]
        if area_code:
            normalized, _ = normalize_area(area_code)
            conditions.append(DmCohort.area_code == normalized)
        if status:
            conditions.append(DmCohort.status == status)
        counts = (
            select(DmStudent.cohort_id, func.count(DmStudent.id).label("student_count"))
            .where(DmStudent.directorate_id == self.directorate_id)
            .group_by(DmStudent.cohort_id)
            .subquery()
        )
        rows = self.db.execute(
            select(DmCohort, func.coalesce(counts.c.student_count, 0))
            .outerjoin(counts, counts.c.cohort_id == DmCohort.id)
            .where(*conditions)
            .order_by(DmCohort.area_code, DmCohort.cohort_number, DmCohort.opening_date)
        ).all()
        return [self.cohort_to_dict(row, student_count=int(count)) for row, count in rows]

    def all_cohorts(self) -> list[dict[str, Any]]:
        return self.list_cohorts()

    def save_cohort(self, payload: dict[str, Any], *, row_id: int | None = None) -> dict[str, Any]:
        self._require_write()
        clean = validate_cohort_payload(payload)
        row = self.get_cohort(row_id) if row_id else None
        conflict = self.db.scalar(
            select(DmCohort).where(
                DmCohort.directorate_id == self.directorate_id,
                DmCohort.area_code == clean["area_code"],
                DmCohort.cohort_number == clean["cohort_number"],
                *([DmCohort.id != row.id] if row else []),
            )
        )
        if conflict:
            raise DMValidationError(
                "Esta turma já existe para a área selecionada.",
                {"turma": "Use outro número ou edite a turma existente."},
            )
        if row is None:
            row = DmCohort(directorate_id=self.directorate_id)
            self.db.add(row)
        elif "SEI" in str(row.source_system or "").upper() and clean["source_system"] == "MANUAL":
            clean["source_system"] = "MANUAL+SEI"
            clean["sei_raw_label"] = clean["sei_raw_label"] or row.sei_raw_label
        row.area_code = clean["area_code"]
        row.area_name = clean["area_name"]
        row.cohort_number = clean["cohort_number"]
        row.opening_date = clean["opening_date"]
        row.vacancies_authorized = clean["vacancies_authorized"]
        row.status = clean["status"]
        row.notes = clean["notes"]
        row.source_system = clean["source_system"]
        row.sei_raw_label = clean["sei_raw_label"]
        row.is_demo = clean["is_demo"]
        row.created_by = self.scope.user.email
        self.db.flush()
        self._reconcile_cohort_statuses({row.id})
        self.db.commit()
        self.db.refresh(row)
        return self.cohort_to_dict(row)

    def bulk_upsert_cohorts(self, payloads: list[dict[str, Any]]) -> dict[str, int | bool]:
        self._require_write()
        clean_rows = [validate_cohort_payload(payload) for payload in payloads]
        seen: set[tuple[str, int]] = set()
        for clean in clean_rows:
            key = (clean["area_code"], clean["cohort_number"])
            if key in seen:
                raise DMValidationError("A planilha repete a mesma turma e área.")
            seen.add(key)
        existing_rows = self.db.scalars(
            select(DmCohort).where(DmCohort.directorate_id == self.directorate_id)
        ).all()
        existing = {(row.area_code, row.cohort_number): row for row in existing_rows}
        created = 0
        updated = 0
        try:
            for clean in clean_rows:
                key = (clean["area_code"], clean["cohort_number"])
                row = existing.get(key)
                if row is None:
                    row = DmCohort(directorate_id=self.directorate_id)
                    self.db.add(row)
                    existing[key] = row
                    created += 1
                else:
                    updated += 1
                    if "SEI" in str(row.source_system or "").upper() and clean["source_system"] == "MANUAL":
                        clean["source_system"] = "MANUAL+SEI"
                        clean["sei_raw_label"] = clean["sei_raw_label"] or row.sei_raw_label
                row.area_code = clean["area_code"]
                row.area_name = clean["area_name"]
                row.cohort_number = clean["cohort_number"]
                row.opening_date = clean["opening_date"]
                row.vacancies_authorized = clean["vacancies_authorized"]
                row.status = clean["status"]
                row.notes = clean["notes"]
                row.source_system = clean["source_system"]
                row.sei_raw_label = clean["sei_raw_label"]
                row.is_demo = clean["is_demo"]
                row.created_by = self.scope.user.email
            self.db.flush()
            self._reconcile_cohort_statuses({existing[key].id for key in seen if key in existing})
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"ok": True, "created": created, "updated": updated, "total": len(clean_rows)}

    def delete_cohort(self, row_id: int) -> None:
        self._require_write()
        row = self.get_cohort(row_id)
        count = self.db.scalar(select(func.count()).select_from(DmStudent).where(DmStudent.cohort_id == row.id)) or 0
        if count:
            raise DMValidationError("A turma possui alunos vinculados e não pode ser excluída.")
        self.db.delete(row)
        self.db.commit()

    def list_students(
        self,
        *,
        area_code: str | None = None,
        cohort_id: int | None = None,
        status: str | None = None,
        document_status: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        conditions = [DmStudent.directorate_id == self.directorate_id]
        if cohort_id:
            cohort = self.get_cohort(cohort_id)
            conditions.append(DmStudent.cohort_id == cohort.id)
        if area_code:
            normalized, _ = normalize_area(area_code)
            conditions.append(DmCohort.area_code == normalized)
        if status:
            conditions.append(DmStudent.status == status)
        if document_status:
            key = str(document_status).strip().casefold()
            if key == "entry_missing":
                conditions.append(DmStudent.entry_date.is_(None))
            elif key == "defense_missing":
                conditions.extend([DmStudent.status == "Titulado", DmStudent.defense_date.is_(None)])
            elif key == "defense_present":
                conditions.append(DmStudent.defense_date.is_not(None))
            elif key == "defense_scheduled":
                conditions.extend([DmStudent.defense_scheduled_date.is_not(None), DmStudent.defense_date.is_(None)])
            elif key == "graduation_missing":
                # Compatibilidade com clientes legados; não é mais exposto pela UI ativa.
                conditions.extend([DmStudent.status == "Titulado", DmStudent.graduation_date.is_(None)])
            elif key == "graduation_present":
                # Compatibilidade com clientes legados; não é mais exposto pela UI ativa.
                conditions.append(DmStudent.graduation_date.is_not(None))
            elif key == "diploma_pending":
                conditions.append(DmStudent.diploma_status == "Pendente")
            elif key == "diploma_issuing":
                conditions.append(DmStudent.diploma_status == "Em emissão")
            elif key == "diploma_issued":
                conditions.append(DmStudent.diploma_status == "Emitido")
            elif key == "diploma_unset":
                conditions.extend([
                    DmStudent.status == "Titulado",
                    or_(DmStudent.diploma_status.is_(None), DmStudent.diploma_status == "Não informado"),
                ])
            elif key == "digital_pending":
                conditions.extend([
                    DmStudent.status == "Titulado",
                    DmStudent.graduation_date.is_not(None),
                    or_(DmStudent.diploma_status.is_(None), DmStudent.diploma_status != "Emitido"),
                ])
        if search:
            token = f"%{str(search).strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(DmStudent.student_name).like(token),
                    func.lower(DmStudent.student_code).like(token),
                    func.lower(func.coalesce(DmStudent.advisor, "")).like(token),
                )
            )
        base = (
            select(DmStudent)
            .join(DmCohort, DmCohort.id == DmStudent.cohort_id)
            .options(joinedload(DmStudent.cohort))
            .where(*conditions)
        )
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.db.scalars(
            base.order_by(DmCohort.area_code, DmCohort.cohort_number, DmStudent.student_name)
            .offset(offset)
            .limit(limit)
        ).all()
        items = [self.student_to_dict(row) for row in rows]
        return {
            "items": items,
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < int(total),
            "next_offset": offset + len(items) if offset + len(items) < int(total) else None,
        }

    def all_students(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(DmStudent)
            .join(DmCohort, DmCohort.id == DmStudent.cohort_id)
            .options(joinedload(DmStudent.cohort))
            .where(DmStudent.directorate_id == self.directorate_id)
            .order_by(DmCohort.area_code, DmCohort.cohort_number, DmStudent.student_name)
        ).all()
        return [self.student_to_dict(row) for row in rows]

    def _resolve_cohort_for_student(self, payload: dict[str, Any]) -> DmCohort:
        cohort_id = payload.get("cohort_id")
        if cohort_id not in (None, ""):
            try:
                return self.get_cohort(int(cohort_id))
            except (TypeError, ValueError) as exc:
                raise DMValidationError("Identificador da turma inválido.", {"cohort_id": "Turma inválida."}) from exc
        return self.find_cohort(
            payload.get("area_code") or payload.get("area"),
            payload.get("cohort_number") or payload.get("turma"),
        )

    def save_student(self, payload: dict[str, Any], *, row_id: int | None = None) -> dict[str, Any]:
        self._require_write()
        cohort = self._resolve_cohort_for_student(payload)
        entry_supplied = payload.get("entry_date") not in (None, "") or payload.get("data_ingresso") not in (None, "")
        graduation_supplied = any(key in payload for key in ("graduation_date", "data_titulacao"))
        diploma_supplied = any(key in payload for key in ("diploma_status", "situacao_diploma"))
        clean = validate_student_payload(payload, cohort_opening_date=cohort.opening_date)
        row = require_object_for_directorate(
            self.db, DmStudent, row_id, self.directorate_id, label="Aluno"
        ) if row_id else None
        conflict = self.db.scalar(
            select(DmStudent).where(
                DmStudent.directorate_id == self.directorate_id,
                func.lower(DmStudent.student_code) == clean["student_code"].lower(),
                *([DmStudent.id != row.id] if row else []),
            )
        )
        if conflict:
            raise DMValidationError(
                "A matrícula já está cadastrada.",
                {"matricula": "Edite o registro existente ou informe outra matrícula."},
            )
        previous_cohort_id = row.cohort_id if row is not None else None
        if row is not None:
            # graduation_date/diploma_status saíram da experiência ativa na v0.8.30.0,
            # mas valores históricos não devem ser apagados ao editar outro campo.
            if not graduation_supplied:
                clean["graduation_date"] = row.graduation_date
            if not diploma_supplied:
                clean["diploma_status"] = row.diploma_status
        if row is None:
            row = DmStudent(directorate_id=self.directorate_id)
            self.db.add(row)
        else:
            # Editing another field must never silently replace a SEI-confirmed
            # individual date while editing another field.
            if not entry_supplied:
                clean["entry_date"] = row.entry_date
                clean["entry_date_estimated"] = bool(row.entry_date_estimated)
            if "SEI" in str(row.source_system or "").upper() and clean["source_system"] == "MANUAL":
                clean["source_system"] = "MANUAL+SEI"
                clean["sei_raw_status"] = clean["sei_raw_status"] or row.sei_raw_status
        row.cohort_id = cohort.id
        for field in (
            "student_code", "student_name", "entry_date", "qualification_date", "defense_date",
            "graduation_date", "defense_scheduled_date", "exit_date", "status", "advisor", "research_line", "diploma_status", "notes",
            "entry_date_estimated", "source_system", "sei_raw_status", "is_demo",
        ):
            setattr(row, field, clean[field])
        row.created_by = self.scope.user.email
        self.db.flush()
        touched = {cohort.id}
        if previous_cohort_id:
            touched.add(previous_cohort_id)
        self._reconcile_cohort_statuses(touched)
        self.db.commit()
        self.db.refresh(row)
        row = self.db.scalar(
            select(DmStudent).options(joinedload(DmStudent.cohort)).where(DmStudent.id == row.id)
        )
        return self.student_to_dict(row)

    def bulk_upsert_students(self, payloads: list[dict[str, Any]]) -> dict[str, int | bool]:
        self._require_write()
        resolved: list[tuple[DmCohort, dict[str, Any], bool]] = []
        seen: set[str] = set()
        for payload in payloads:
            cohort = self._resolve_cohort_for_student(payload)
            entry_supplied = payload.get("entry_date") not in (None, "") or payload.get("data_ingresso") not in (None, "")
            clean = validate_student_payload(payload, cohort_opening_date=cohort.opening_date)
            key = clean["student_code"].casefold()
            if key in seen:
                raise DMValidationError(f"A planilha repete a matrícula {clean['student_code']}.")
            seen.add(key)
            resolved.append((cohort, clean, entry_supplied))
        existing_rows = self.db.scalars(
            select(DmStudent).where(DmStudent.directorate_id == self.directorate_id)
        ).all()
        existing = {row.student_code.casefold(): row for row in existing_rows}
        created = 0
        updated = 0
        touched_cohorts: set[int] = set()
        try:
            for cohort, clean, entry_supplied in resolved:
                row = existing.get(clean["student_code"].casefold())
                if row is not None and row.cohort_id:
                    touched_cohorts.add(row.cohort_id)
                touched_cohorts.add(cohort.id)
                if row is None:
                    row = DmStudent(directorate_id=self.directorate_id)
                    self.db.add(row)
                    existing[clean["student_code"].casefold()] = row
                    created += 1
                else:
                    updated += 1
                    if not entry_supplied:
                        clean["entry_date"] = row.entry_date
                        clean["entry_date_estimated"] = bool(row.entry_date_estimated)
                    if "SEI" in str(row.source_system or "").upper() and clean["source_system"] == "MANUAL":
                        clean["source_system"] = "MANUAL+SEI"
                        clean["sei_raw_status"] = clean["sei_raw_status"] or row.sei_raw_status
                row.cohort_id = cohort.id
                for field in (
                    "student_code", "student_name", "entry_date", "qualification_date", "defense_date",
                    "graduation_date", "defense_scheduled_date", "exit_date", "status", "advisor", "research_line", "diploma_status", "notes",
                    "entry_date_estimated", "source_system", "sei_raw_status", "is_demo",
                ):
                    setattr(row, field, clean[field])
                row.created_by = self.scope.user.email
            self.db.flush()
            self._reconcile_cohort_statuses(touched_cohorts)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"ok": True, "created": created, "updated": updated, "total": len(resolved)}

    def list_student_ids(
        self,
        *,
        area_code: str | None = None,
        cohort_id: int | None = None,
        status: str | None = None,
        document_status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        result = self.list_students(
            area_code=area_code,
            cohort_id=cohort_id,
            status=status,
            document_status=document_status,
            search=search,
            offset=0,
            limit=5000,
        )
        if result["total"] > 5000:
            raise DMValidationError(
                "O filtro possui mais de 5.000 alunos. Refine o recorte antes de executar uma ação em lote."
            )
        return {"ids": [int(item["id"]) for item in result["items"]], "total": int(result["total"])}

    def _graduation_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_ids = payload.get("student_ids") or []
        try:
            ids = sorted({int(value) for value in raw_ids if value not in (None, "")})
        except (TypeError, ValueError) as exc:
            raise DMValidationError("A seleção de alunos é inválida.") from exc
        if not ids:
            raise DMValidationError("Selecione pelo menos um aluno para titular.")
        if len(ids) > 5000:
            raise DMValidationError("Uma operação de titulação pode conter no máximo 5.000 alunos.")

        rows = self.db.scalars(
            select(DmStudent)
            .options(joinedload(DmStudent.cohort))
            .where(DmStudent.directorate_id == self.directorate_id, DmStudent.id.in_(ids))
            .order_by(DmStudent.student_name)
        ).all()
        by_id = {row.id: row for row in rows}
        overrides = {}
        for item in payload.get("students") or []:
            try:
                sid = int(item.get("student_id"))
            except (TypeError, ValueError):
                continue
            overrides[sid] = dict(item)

        common_defense = parse_date(payload.get("defense_date"), field="data_defesa", required=False)
        common_graduation = parse_date(payload.get("graduation_date"), field="data_titulacao", required=False)
        common_diploma = normalize_diploma_status(payload.get("diploma_status"))
        planned: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        missing_ids = [sid for sid in ids if sid not in by_id]
        for sid in missing_ids:
            errors.append({"student_id": sid, "error": "Aluno não localizado no Data UNIVC."})

        for sid in ids:
            row = by_id.get(sid)
            if row is None:
                continue
            item = overrides.get(sid, {})
            if row.status == "Desligado":
                errors.append({
                    "student_id": sid,
                    "student_code": row.student_code,
                    "student_name": row.student_name,
                    "error": f"Aluno com status {row.status} não pode ser titulado em lote.",
                })
                continue

            defense_raw = item.get("defense_date") if "defense_date" in item else common_defense
            graduation_raw = item.get("graduation_date") if "graduation_date" in item else common_graduation
            diploma_raw = item.get("diploma_status") if "diploma_status" in item else common_diploma
            try:
                defense_date = parse_date(defense_raw, field="data_defesa", required=False) if not isinstance(defense_raw, date) else defense_raw
                graduation_date = parse_date(graduation_raw, field="data_titulacao", required=False) if not isinstance(graduation_raw, date) else graduation_raw
                diploma_status = normalize_diploma_status(diploma_raw)
            except DMValidationError as exc:
                errors.append({
                    "student_id": sid, "student_code": row.student_code, "student_name": row.student_name,
                    "error": str(exc), "fields": exc.field_errors,
                })
                continue

            defense_date = defense_date or row.defense_date
            graduation_date = graduation_date or row.graduation_date
            diploma_status = diploma_status if diploma_status is not None else row.diploma_status
            # A defesa é um dado acadêmico desejável, mas pode estar indisponível
            # em registros históricos. Titulação não deve ser bloqueada pela
            # ausência desse dado; as validações cronológicas só se aplicam
            # quando a defesa é conhecida.
            chronology = None
            if defense_date and row.entry_date and defense_date < row.entry_date:
                chronology = "A defesa não pode ser anterior ao ingresso."
            elif defense_date and row.qualification_date and defense_date < row.qualification_date:
                chronology = "A defesa não pode ser anterior à qualificação registrada."
            elif defense_date and graduation_date and graduation_date < defense_date:
                chronology = "A titulação não pode ocorrer antes da defesa."
            if chronology:
                errors.append({
                    "student_id": sid, "student_code": row.student_code, "student_name": row.student_name,
                    "error": chronology,
                })
                continue
            if row.status != "Titulado" and graduation_date and not diploma_status:
                diploma_status = "Pendente"

            changed = any((
                row.status != "Titulado",
                row.defense_date != defense_date,
                row.graduation_date != graduation_date,
                row.diploma_status != diploma_status,
            ))
            planned.append({
                "student_id": row.id,
                "student_code": row.student_code,
                "student_name": row.student_name,
                "area_code": row.cohort.area_code if row.cohort else None,
                "cohort_number": row.cohort.cohort_number if row.cohort else None,
                "previous_status": row.status,
                "previous_defense_date": row.defense_date,
                "previous_graduation_date": row.graduation_date,
                "previous_diploma_status": row.diploma_status,
                "new_status": "Titulado",
                "new_defense_date": defense_date,
                "new_graduation_date": graduation_date,
                "new_diploma_status": diploma_status,
                "missing_defense": defense_date is None,
                "changed": changed,
            })

        return {
            "ok": not errors,
            "rows": planned,
            "errors": errors,
            "summary": {
                "selected": len(ids),
                "eligible": len(planned),
                "changes": sum(1 for item in planned if item["changed"]),
                "already_titled": sum(1 for item in planned if item["previous_status"] == "Titulado"),
                "without_defense": sum(1 for item in planned if item.get("missing_defense")),
                "blocked": len(errors),
            },
        }

    @staticmethod
    def _serialize_graduation_plan(plan: dict[str, Any]) -> dict[str, Any]:
        result = {**plan, "rows": [], "errors": list(plan.get("errors") or [])}
        for item in plan.get("rows") or []:
            rendered = dict(item)
            for field in ("previous_defense_date", "previous_graduation_date", "new_defense_date", "new_graduation_date"):
                value = rendered.get(field)
                rendered[field] = value.isoformat() if value else None
            result["rows"].append(rendered)
        return result

    def preview_graduation(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._serialize_graduation_plan(self._graduation_plan(payload))
        ids = []
        for value in payload.get("student_ids") or []:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        rows = self.db.scalars(
            select(DmStudent)
            .options(joinedload(DmStudent.cohort))
            .where(DmStudent.directorate_id == self.directorate_id, DmStudent.id.in_(ids))
            .order_by(DmStudent.student_name)
        ).all() if ids else []
        result["selection_rows"] = [{
            "student_id": row.id,
            "student_code": row.student_code,
            "student_name": row.student_name,
            "area_code": row.cohort.area_code if row.cohort else None,
            "cohort_number": row.cohort.cohort_number if row.cohort else None,
            "previous_status": row.status,
            "previous_defense_date": row.defense_date.isoformat() if row.defense_date else None,
            "previous_graduation_date": row.graduation_date.isoformat() if row.graduation_date else None,
            "previous_diploma_status": row.diploma_status,
            "new_defense_date": row.defense_date.isoformat() if row.defense_date else None,
            "new_graduation_date": row.graduation_date.isoformat() if row.graduation_date else None,
            "new_diploma_status": row.diploma_status,
        } for row in rows]
        return result

    def apply_graduation(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        plan = self._graduation_plan(payload)
        if plan["errors"]:
            raise DMValidationError(
                "A titulação em lote possui inconsistências. Nenhum aluno foi alterado.",
                {"alunos": "; ".join(item["error"] for item in plan["errors"][:6])},
            )
        operation_id = uuid.uuid4().hex
        operation_type = str(payload.get("operation_type") or ("individual" if len(plan["rows"]) == 1 else "bulk")).strip()[:30]
        now = datetime.now(timezone.utc)
        ids = [int(item["student_id"]) for item in plan["rows"]]
        rows = self.db.scalars(
            select(DmStudent).where(DmStudent.directorate_id == self.directorate_id, DmStudent.id.in_(ids))
        ).all()
        by_id = {row.id: row for row in rows}
        changed = 0
        try:
            for item in plan["rows"]:
                row = by_id[item["student_id"]]
                if not item["changed"]:
                    continue
                event = DmGraduationEvent(
                    directorate_id=self.directorate_id,
                    student_id=row.id,
                    operation_id=operation_id,
                    operation_type=operation_type,
                    previous_status=item["previous_status"],
                    previous_defense_date=item["previous_defense_date"],
                    previous_graduation_date=item["previous_graduation_date"],
                    previous_diploma_status=item["previous_diploma_status"],
                    new_status="Titulado",
                    new_defense_date=item["new_defense_date"],
                    new_graduation_date=item["new_graduation_date"],
                    new_diploma_status=item["new_diploma_status"],
                    created_by=self.scope.user.email,
                )
                self.db.add(event)
                row.status = "Titulado"
                row.defense_date = item["new_defense_date"]
                row.graduation_date = item["new_graduation_date"]
                row.diploma_status = item["new_diploma_status"]
                row.graduation_updated_at = now
                row.graduation_updated_by = self.scope.user.email
                changed += 1
            self.db.flush()
            self._reconcile_cohort_statuses({row.cohort_id for row in rows})
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        rendered = self._serialize_graduation_plan(plan)
        rendered.update({"operation_id": operation_id, "updated": changed})
        return rendered

    def delete_student(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(
            self.db, DmStudent, row_id, self.directorate_id, label="Aluno"
        )
        cohort_id = row.cohort_id
        self.db.delete(row)
        self.db.flush()
        self._reconcile_cohort_statuses({cohort_id})
        self.db.commit()

    def data_quality_summary(self) -> dict[str, int]:
        base = [DmStudent.directorate_id == self.directorate_id]
        total = self.db.scalar(select(func.count()).select_from(DmStudent).where(*base)) or 0
        estimated = self.db.scalar(
            select(func.count()).select_from(DmStudent).where(
                *base, DmStudent.entry_date.is_not(None), DmStudent.entry_date_estimated.is_(True)
            )
        ) or 0
        confirmed = self.db.scalar(
            select(func.count()).select_from(DmStudent).where(
                *base, DmStudent.entry_date.is_not(None), DmStudent.entry_date_estimated.is_(False)
            )
        ) or 0
        missing = max(0, int(total) - int(estimated) - int(confirmed))
        sei_students = self.db.scalar(
            select(func.count()).select_from(DmStudent).where(
                *base, DmStudent.source_system.like("%SEI%")
            )
        ) or 0
        sei_cohorts = self.db.scalar(
            select(func.count()).select_from(DmCohort).where(
                DmCohort.directorate_id == self.directorate_id,
                DmCohort.source_system.like("%SEI%"),
            )
        ) or 0
        dates_checked = self.db.scalar(
            select(func.count()).select_from(DmStudent).where(
                *base, DmStudent.last_course_dates_sei_at.is_not(None)
            )
        ) or 0
        defenses_from_sei = self.db.scalar(
            select(func.count()).select_from(DmStudent).where(
                *base,
                DmStudent.last_course_dates_sei_at.is_not(None),
                DmStudent.defense_date.is_not(None),
                DmStudent.status == "Titulado",
            )
        ) or 0
        return {
            "students_total": int(total),
            "students_with_estimated_entry": int(estimated),
            "students_with_confirmed_entry": int(confirmed),
            "students_missing_entry": int(missing),
            "students_seen_in_sei": int(sei_students),
            "students_course_dates_checked": int(dates_checked),
            "students_defense_confirmed_by_sei": int(defenses_from_sei),
            "cohorts_seen_in_sei": int(sei_cohorts),
        }

    def preview_sei_report(
        self,
        report: DMSEIReport,
        *,
        exclude_test: bool = True,
    ) -> dict[str, Any]:
        normalized = filter_report(report, exclude_test=exclude_test)
        existing_cohorts = self.db.scalars(
            select(DmCohort).where(DmCohort.directorate_id == self.directorate_id)
        ).all()
        by_key = {(row.area_code, row.cohort_number): row for row in existing_cohorts}
        existing_student_codes = {
            str(code).casefold()
            for code in self.db.scalars(
                select(DmStudent.student_code).where(
                    DmStudent.directorate_id == self.directorate_id
                )
            ).all()
        }
        cohort_items: list[dict[str, Any]] = []
        new_cohorts = 0
        for block in normalized.cohorts:
            existing = by_key.get((block.area_code, block.cohort_number))
            existing_is_demo = bool(existing and existing.is_demo)
            if existing is None or existing_is_demo:
                new_cohorts += 1
            item = block.to_dict()
            item.update(
                {
                    "existing": existing is not None and not existing_is_demo,
                    "existing_is_demo": existing_is_demo,
                    "existing_id": existing.id if existing else None,
                    "existing_opening_date": (
                        existing.opening_date.isoformat()
                        if existing and existing.opening_date and not existing_is_demo
                        else None
                    ),
                    "existing_status": existing.status if existing else None,
                    "requires_opening_date": False,
                    # O fluxo comum é adicionar apenas a turma anual nova. Turmas
                    # históricas existentes continuam desmarcadas por padrão.
                    "default_selected": existing is None or existing_is_demo,
                }
            )
            cohort_items.append(item)

        students_new = sum(
            1 for row in normalized.students
            if row.student_code.casefold() not in existing_student_codes
        )
        demo_students = self.db.scalar(
            select(func.count()).select_from(DmStudent).where(
                DmStudent.directorate_id == self.directorate_id,
                DmStudent.is_demo.is_(True),
            )
        ) or 0
        demo_cohorts = self.db.scalar(
            select(func.count()).select_from(DmCohort).where(
                DmCohort.directorate_id == self.directorate_id,
                DmCohort.is_demo.is_(True),
            )
        ) or 0
        return {
            "report": normalized.to_dict(include_students=True),
            "cohorts": cohort_items,
            "summary": {
                **normalized.to_dict(include_students=False)["summary"],
                "students_new": students_new,
                "students_existing": len(normalized.students) - students_new,
                "cohorts_new": new_cohorts,
                "cohorts_existing": len(normalized.cohorts) - new_cohorts,
                "cohorts_matching_demo": sum(
                    1 for item in cohort_items if item.get("existing_is_demo")
                ),
                "demo_students": int(demo_students),
                "demo_cohorts": int(demo_cohorts),
            },
            "missing_opening_dates": [],
            "warnings": normalized.warnings,
            "policy": {
                "absence_is_not_deletion": True,
                "manual_dates_are_preserved_until_sei_refresh": True,
                "new_student_entry_date": "unknown_until_individual_sei_lookup",
                "cohort_opening_date_required": False,
                "cohort_opening_date_used_by_dm02": False,
                "individual_start_can_be_confirmed_by_sei": True,
                "sei_completion_updates_defense_date": True,
                "sei_completion_confirms_graduation": True,
                "credentials_persisted": False,
            },
        }

    @staticmethod
    def _sync_run_to_dict(row: DmSeiSyncRun) -> dict[str, Any]:
        try:
            warnings = json.loads(row.warnings_json or "[]")
        except (TypeError, ValueError):
            warnings = []
        return {
            "id": row.id,
            "source_type": row.source_type,
            "source_name": row.source_name,
            "source_sha256": row.source_sha256,
            "status": row.status,
            "cohorts_detected": row.cohorts_detected,
            "students_detected": row.students_detected,
            "cohorts_created": row.cohorts_created,
            "cohorts_updated": row.cohorts_updated,
            "students_created": row.students_created,
            "students_updated": row.students_updated,
            "students_unchanged": row.students_unchanged,
            "students_not_seen": row.students_not_seen,
            "warnings": warnings,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "inserted_by": row.inserted_by,
        }

    def list_sei_sync_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(DmSeiSyncRun)
            .where(DmSeiSyncRun.directorate_id == self.directorate_id)
            .order_by(DmSeiSyncRun.completed_at.desc(), DmSeiSyncRun.id.desc())
            .limit(max(1, min(int(limit), 100)))
        ).all()
        return [self._sync_run_to_dict(row) for row in rows]

    def students_for_sei_dates(
        self,
        *,
        cohort_id: int | None = None,
        cohort_ids: list[int] | None = None,
        student_ids: list[int] | None = None,
        all_cohorts: bool = False,
        max_students: int = 1200,
    ) -> list[dict[str, Any]]:
        """Prepare an explicit DM selection for the individual SEI lookup.

        The normal scopes are one cohort, selected students, selected cohorts, or the
        deliberate ``all_cohorts`` action exposed in the cohort page. No implicit
        institution-wide lookup is performed.
        """

        conditions = [
            DmStudent.directorate_id == self.directorate_id,
            DmStudent.is_demo.is_(False),
        ]
        explicit_scopes = sum(bool(value) for value in (cohort_id is not None, cohort_ids, student_ids, all_cohorts))
        if explicit_scopes != 1:
            raise DMValidationError("Escolha exatamente um escopo para consultar no SEI.")

        if cohort_id is not None:
            cohort = self.get_cohort(int(cohort_id))
            conditions.append(DmStudent.cohort_id == cohort.id)
        elif cohort_ids:
            normalized_cohort_ids = sorted({int(value) for value in cohort_ids})
            authorized = self.db.scalars(
                select(DmCohort.id).where(
                    DmCohort.directorate_id == self.directorate_id,
                    DmCohort.id.in_(normalized_cohort_ids),
                )
            ).all()
            if len(authorized) != len(normalized_cohort_ids):
                raise LookupError("Uma ou mais turmas selecionadas não pertencem à Diretoria de Mestrado.")
            conditions.append(DmStudent.cohort_id.in_(normalized_cohort_ids))
        elif student_ids:
            normalized_ids = sorted({int(value) for value in student_ids})
            conditions.append(DmStudent.id.in_(normalized_ids))

        rows = self.db.scalars(
            select(DmStudent)
            .options(joinedload(DmStudent.cohort))
            .where(*conditions)
            .order_by(DmStudent.cohort_id.asc(), DmStudent.student_name.asc(), DmStudent.id.asc())
        ).all()
        if not rows:
            raise LookupError("Nenhum aluno foi encontrado para a seleção informada.")
        if len(rows) > max_students:
            raise DMValidationError(
                f"A seleção contém {len(rows)} alunos. O limite de segurança é {max_students} por atualização."
            )
        if student_ids and len(rows) != len({int(value) for value in student_ids}):
            raise LookupError("Um ou mais alunos selecionados não pertencem à Diretoria de Mestrado.")

        return [
            {
                "student_id": row.id,
                "student_code": row.student_code,
                "student_name": row.student_name,
                "cohort_opening_date": row.cohort.opening_date.isoformat() if row.cohort and row.cohort.opening_date else None,
                "area_code": row.cohort.area_code if row.cohort else None,
                "cohort_number": row.cohort.cohort_number if row.cohort else None,
            }
            for row in rows
        ]

    def student_ids_for_cohort_keys(self, cohort_keys: list[str]) -> list[int]:
        normalized_keys = {str(value or "").strip().upper() for value in cohort_keys if str(value or "").strip()}
        if not normalized_keys:
            return []
        cohorts = self.db.scalars(
            select(DmCohort).where(DmCohort.directorate_id == self.directorate_id)
        ).all()
        cohort_ids = [
            row.id
            for row in cohorts
            if f"{row.area_code}:{row.cohort_number}".upper() in normalized_keys
        ]
        if not cohort_ids:
            return []
        return list(
            self.db.scalars(
                select(DmStudent.id).where(
                    DmStudent.directorate_id == self.directorate_id,
                    DmStudent.cohort_id.in_(cohort_ids),
                    DmStudent.is_demo.is_(False),
                ).order_by(DmStudent.id.asc())
            ).all()
        )

    def apply_sei_course_dates(
        self,
        lookup_result: dict[str, Any],
        *,
        source_type: str = "sei_datas_aluno",
    ) -> dict[str, Any]:
        """Apply the individual course start and SEI completion date.

        In the DM business rule, ``dataConclusaoCurso`` in the legacy SEI is the
        date on which the defense was approved and the certificate entered
        production. It therefore updates ``defense_date`` directly and confirms
        ``Titulado``. There is no parallel completion field in the domain model.

        A non-empty SEI start is treated as the authoritative individual entry date.
        Empty values never erase dates already known in Data UNIVC.
        """

        self._require_write()
        items = list((lookup_result or {}).get("items") or [])
        if not items:
            return {
                "ok": True,
                "summary": {
                    "requested": 0, "found": 0, "updated": 0, "unchanged": 0,
                    "failed": 0, "defenses_confirmed": 0, "ambiguous": 0,
                },
                "items": [],
                "warnings": [],
            }

        ids = sorted({int(item["student_id"]) for item in items if item.get("student_id") not in (None, "")})
        rows = self.db.scalars(
            select(DmStudent)
            .options(joinedload(DmStudent.cohort))
            .where(
                DmStudent.directorate_id == self.directorate_id,
                DmStudent.id.in_(ids),
            )
        ).all() if ids else []
        by_id = {row.id: row for row in rows}
        now = datetime.now(timezone.utc)
        response_items: list[dict[str, Any]] = []
        warnings: list[str] = []
        updated = 0
        unchanged = 0
        failed = 0
        defenses_confirmed = 0
        ambiguous = 0
        lookup_errors = 0
        touched_cohorts: set[int] = set()

        try:
            for item in items:
                student_id = item.get("student_id")
                row = by_id.get(int(student_id)) if student_id not in (None, "") else None
                if row is None:
                    failed += 1
                    response_items.append({**item, "ok": False, "error": "Aluno não localizado no Data UNIVC."})
                    continue

                touched_cohorts.add(row.cohort_id)
                if not item.get("ok"):
                    failed += 1
                    if item.get("error_type") == "ambiguous":
                        ambiguous += 1
                    else:
                        lookup_errors += 1
                    response_items.append(dict(item))
                    continue

                start_date = parse_date(
                    item.get("course_start_date"), field="data_inicio_curso", required=False
                )
                sei_defense_date = parse_date(
                    item.get("defense_date") or item.get("course_completion_date"),
                    field="data_conclusao_curso",
                    required=False,
                )
                if start_date and sei_defense_date and sei_defense_date < start_date:
                    failed += 1
                    response_items.append({
                        **item,
                        "ok": False,
                        "error": "O SEI retornou uma data de defesa/conclusão anterior ao início do curso.",
                        "error_type": "validation",
                    })
                    continue

                effective_start = start_date or row.entry_date
                effective_defense = sei_defense_date or row.defense_date
                chronology_errors: list[str] = []
                if effective_start:
                    for label, academic_date in (
                        ("qualificação", row.qualification_date),
                        ("saída", row.exit_date),
                    ):
                        if academic_date and academic_date < effective_start:
                            chronology_errors.append(
                                f"a data de {label} ({academic_date.strftime('%d/%m/%Y')}) "
                                f"é anterior ao início retornado ({effective_start.strftime('%d/%m/%Y')})"
                            )
                    if effective_defense and effective_defense < effective_start:
                        chronology_errors.append(
                            f"a defesa ({effective_defense.strftime('%d/%m/%Y')}) é anterior "
                            f"ao início ({effective_start.strftime('%d/%m/%Y')})"
                        )
                if sei_defense_date and row.qualification_date and sei_defense_date < row.qualification_date:
                    chronology_errors.append(
                        f"a defesa retornada ({sei_defense_date.strftime('%d/%m/%Y')}) "
                        f"é anterior à qualificação registrada ({row.qualification_date.strftime('%d/%m/%Y')})"
                    )

                if chronology_errors:
                    failed += 1
                    response_items.append({
                        **item,
                        "ok": False,
                        "error": "Conflito cronológico: " + "; ".join(chronology_errors) + ".",
                        "error_type": "validation",
                    })
                    continue

                meaningful_change = False
                if start_date:
                    if row.entry_date != start_date:
                        if row.entry_date and not row.entry_date_estimated:
                            warnings.append(
                                f"{row.student_code}: ingresso atualizado pelo SEI de "
                                f"{row.entry_date.strftime('%d/%m/%Y')} para {start_date.strftime('%d/%m/%Y')}."
                            )
                        row.entry_date = start_date
                        meaningful_change = True
                    if row.entry_date_estimated:
                        row.entry_date_estimated = False
                        meaningful_change = True

                # Empty SEI values never erase a defense already recorded. When the
                # completion date exists, it is the authoritative defense approval date.
                if sei_defense_date:
                    if row.defense_date != sei_defense_date:
                        if row.defense_date:
                            warnings.append(
                                f"{row.student_code}: data de defesa atualizada pelo SEI de "
                                f"{row.defense_date.strftime('%d/%m/%Y')} para {sei_defense_date.strftime('%d/%m/%Y')}."
                            )
                        row.defense_date = sei_defense_date
                        meaningful_change = True
                    if row.status != "Titulado":
                        if row.status == "Desligado":
                            warnings.append(
                                f"{row.student_code}: o SEI confirmou a defesa; o status {row.status} foi substituído por Titulado."
                            )
                        row.status = "Titulado"
                        meaningful_change = True
                    defenses_confirmed += 1

                row.last_course_dates_sei_at = now
                if row.source_system in (None, ""):
                    row.source_system = "SEI"
                elif "SEI" not in str(row.source_system).upper():
                    row.source_system = f"{row.source_system}+SEI"
                row.created_by = self.scope.user.email
                if meaningful_change:
                    updated += 1
                else:
                    unchanged += 1

                response_items.append({
                    **item,
                    "entry_date_applied": row.entry_date.isoformat() if row.entry_date else None,
                    "entry_date_estimated": bool(row.entry_date_estimated),
                    "defense_date_applied": row.defense_date.isoformat() if row.defense_date else None,
                    "status_applied": row.status,
                    "updated": meaningful_change,
                })

            self.db.flush()
            self._reconcile_cohort_statuses(touched_cohorts)

            audit_warnings = []
            if ambiguous:
                audit_warnings.append(f"{ambiguous} consulta(s) ambígua(s) exigiram revisão manual.")
            if lookup_errors:
                audit_warnings.append(f"{lookup_errors} consulta(s) não retornaram dados utilizáveis.")

            sync = DmSeiSyncRun(
                directorate_id=self.directorate_id,
                source_type=str(source_type or "sei_datas_aluno")[:30],
                source_name=None,
                source_sha256=None,
                status="Concluída",
                cohorts_detected=len(touched_cohorts),
                students_detected=len(items),
                cohorts_created=0,
                cohorts_updated=0,
                students_created=0,
                students_updated=updated,
                students_unchanged=unchanged,
                students_not_seen=failed,
                warnings_json=json.dumps(audit_warnings, ensure_ascii=False),
                started_at=now,
                completed_at=now,
                inserted_by=self.scope.user.email,
            )
            self.db.add(sync)
            self.db.commit()
            self.db.refresh(sync)
        except Exception:
            self.db.rollback()
            raise

        summary = {
            "requested": len(items),
            "found": len(items) - failed,
            "updated": updated,
            "unchanged": unchanged,
            "failed": failed,
            "defenses_confirmed": defenses_confirmed,
            "ambiguous": ambiguous,
        }
        return {
            "ok": True,
            "summary": summary,
            "items": response_items,
            "warnings": warnings[:200],
            "sync": self._sync_run_to_dict(sync),
            "quality": self.data_quality_summary(),
            "credentials_persisted": False,
        }

    def sync_sei_report(
        self,
        report: DMSEIReport,
        *,
        opening_dates: dict[str, Any] | None = None,
        selected_cohort_keys: list[str] | None = None,
        exclude_test: bool = True,
        remove_demo: bool = True,
        source_type: str = "upload",
        update_existing_opening_dates: bool = False,
    ) -> dict[str, Any]:
        """Synchronize an explicitly selected subset of the SEI roster.

        The integral report is used only for discovery and roster membership; only the
        cohorts chosen by the user are committed. New cohorts and students may be saved
        without fabricated dates. The optional individual lookup then supplies the real
        entry and defense dates directly from the SEI.
        """

        self._require_write()
        if selected_cohort_keys is not None and not [value for value in selected_cohort_keys if str(value or "").strip()]:
            raise DMValidationError("Selecione pelo menos uma turma para sincronizar.")
        normalized = filter_report(
            report,
            exclude_test=exclude_test,
            selected_cohort_keys=selected_cohort_keys,
        )
        opening_dates = dict(opening_dates or {})
        now = datetime.now(timezone.utc)
        warnings = list(normalized.warnings)

        if not normalized.cohorts or not normalized.students:
            raise DMValidationError("As turmas selecionadas não contêm alunos importáveis no relatório do SEI.")

        current_cohorts = self.db.scalars(
            select(DmCohort).where(DmCohort.directorate_id == self.directorate_id)
        ).all()
        by_key = {(row.area_code, row.cohort_number): row for row in current_cohorts}
        if not remove_demo:
            demo_student_exists = self.db.scalar(
                select(DmStudent.id).where(
                    DmStudent.directorate_id == self.directorate_id,
                    DmStudent.is_demo.is_(True),
                ).limit(1)
            )
            if any(row.is_demo for row in current_cohorts) or demo_student_exists is not None:
                raise DMValidationError(
                    "A base ainda contém dados demonstrativos. Mantenha marcada a opção de removê-los para evitar misturar demonstração e dados reais do SEI.",
                    {"remover_demonstracao": "Obrigatório enquanto existirem dados demonstrativos."},
                )

        parsed_dates: dict[tuple[str, int], Any] = {}
        invalid_dates: dict[str, str] = {}
        for block in normalized.cohorts:
            key_tuple = (block.area_code, block.cohort_number)
            raw_value = opening_dates.get(block.key)
            if raw_value not in (None, ""):
                try:
                    parsed_dates[key_tuple] = parse_date(
                        raw_value,
                        field=f"data_abertura_{block.key}",
                        required=False,
                    )
                except DMValidationError as exc:
                    invalid_dates[block.key] = next(iter(exc.field_errors.values()), str(exc))
        if invalid_dates:
            raise DMValidationError("Revise as datas de abertura informadas.", invalid_dates)

        unresolved = [row for row in normalized.students if row.review_required or not row.mapped_status]
        if unresolved:
            raise DMValidationError(
                "O relatório contém situações acadêmicas que precisam ser mapeadas antes da sincronização.",
                {
                    f"linha_{row.row_number}": row.raw_status or "Situação vazia"
                    for row in unresolved[:50]
                },
            )

        try:
            if remove_demo:
                self.db.execute(
                    delete(DmStudent).where(
                        DmStudent.directorate_id == self.directorate_id,
                        DmStudent.is_demo.is_(True),
                    )
                )
                self.db.execute(
                    delete(DmCohort).where(
                        DmCohort.directorate_id == self.directorate_id,
                        DmCohort.is_demo.is_(True),
                    )
                )
                self.db.flush()

            current_cohorts = self.db.scalars(
                select(DmCohort).where(DmCohort.directorate_id == self.directorate_id)
            ).all()
            by_key = {(row.area_code, row.cohort_number): row for row in current_cohorts}
            cohort_created = 0
            cohort_updated = 0
            cohort_map: dict[tuple[str, int], DmCohort] = {}

            for block in normalized.cohorts:
                key_tuple = (block.area_code, block.cohort_number)
                row = by_key.get(key_tuple)
                changed = False
                if row is None:
                    row = DmCohort(
                        directorate_id=self.directorate_id,
                        area_code=block.area_code,
                        area_name=block.area_name,
                        cohort_number=block.cohort_number,
                        opening_date=parsed_dates.get(key_tuple),
                        vacancies_authorized=None,
                        status="Em andamento",
                        source_system="SEI",
                        sei_raw_label=block.raw_label,
                        last_seen_sei_at=now,
                        is_demo=False,
                        created_by=self.scope.user.email,
                    )
                    self.db.add(row)
                    self.db.flush()
                    by_key[key_tuple] = row
                    cohort_created += 1
                else:
                    if row.area_name != block.area_name:
                        row.area_name = block.area_name
                        changed = True
                    if row.sei_raw_label != block.raw_label:
                        row.sei_raw_label = block.raw_label
                        changed = True
                    if update_existing_opening_dates and key_tuple in parsed_dates and row.opening_date != parsed_dates[key_tuple]:
                        row.opening_date = parsed_dates[key_tuple]
                        changed = True
                    if row.source_system in (None, "", "MANUAL"):
                        row.source_system = "MANUAL+SEI" if row.source_system == "MANUAL" else "SEI"
                    row.last_seen_sei_at = now
                    if changed:
                        cohort_updated += 1
                cohort_map[key_tuple] = row

            selected_cohort_ids = {row.id for row in cohort_map.values()}
            existing_rows = self.db.scalars(
                select(DmStudent).where(DmStudent.directorate_id == self.directorate_id)
            ).all()
            existing = {row.student_code.casefold(): row for row in existing_rows}
            incoming_codes = {row.student_code.casefold() for row in normalized.students}
            created = 0
            updated = 0
            unchanged = 0
            lifecycle_cohort_ids: set[int] = set(selected_cohort_ids)

            for item in normalized.students:
                cohort = cohort_map[(item.area_code, item.cohort_number)]
                row = existing.get(item.student_code.casefold())
                if row is None:
                    status = item.mapped_status or "Ativo"
                    if status != "Ativo":
                        warnings.append(
                            f"{item.student_code}: situação {status} veio do relatório de turmas sem a data acadêmica individual; registro criado como Ativo até a consulta detalhada ao SEI."
                        )
                        status = "Ativo"
                    row = DmStudent(
                        directorate_id=self.directorate_id,
                        cohort_id=cohort.id,
                        student_code=item.student_code,
                        student_name=item.student_name,
                        entry_date=None,
                        entry_date_estimated=False,
                        qualification_date=None,
                        defense_date=None,
                        defense_scheduled_date=None,
                        exit_date=None,
                        status=status,
                        advisor=None,
                        research_line=None,
                        notes=None,
                        source_system="SEI",
                        sei_raw_status=item.raw_status,
                        last_seen_sei_at=now,
                        last_course_dates_sei_at=None,
                        is_demo=False,
                        created_by=self.scope.user.email,
                    )
                    self.db.add(row)
                    existing[item.student_code.casefold()] = row
                    created += 1
                    continue

                meaningful_change = False
                if row.cohort_id != cohort.id:
                    lifecycle_cohort_ids.add(row.cohort_id)
                    warnings.append(
                        f"{item.student_code}: vínculo de turma atualizado para {item.area_code} · Turma {item.cohort_number}."
                    )
                    row.cohort_id = cohort.id
                    meaningful_change = True
                if row.student_name.strip() != item.student_name.strip():
                    row.student_name = item.student_name
                    meaningful_change = True
                if (row.sei_raw_status or "") != item.raw_status:
                    row.sei_raw_status = item.raw_status
                    meaningful_change = True

                mapped_status = item.mapped_status or "Ativo"
                if mapped_status == "Ativo":
                    if row.status in {"Titulado", "Desligado"}:
                        warnings.append(
                            f"{item.student_code}: o relatório informa Ativa, mas o Data UNIVC mantém o status confirmado {row.status}."
                        )
                elif mapped_status == "Titulado":
                    if row.defense_date:
                        if row.status != "Titulado":
                            row.status = "Titulado"
                            meaningful_change = True
                    else:
                        warnings.append(
                            f"{item.student_code}: o relatório indica titulação; a data de defesa será confirmada pela consulta individual ao SEI."
                        )
                elif mapped_status == "Desligado":
                    if row.exit_date:
                        if row.status != "Desligado":
                            row.status = "Desligado"
                            meaningful_change = True
                    else:
                        warnings.append(
                            f"{item.student_code}: SEI indica {mapped_status}, mas não fornece a data de saída; status anterior preservado."
                        )

                if row.source_system in (None, "", "MANUAL"):
                    row.source_system = "MANUAL+SEI" if row.source_system == "MANUAL" else "SEI"
                row.last_seen_sei_at = now
                row.created_by = self.scope.user.email
                if meaningful_change:
                    updated += 1
                else:
                    unchanged += 1

            # Absence is evaluated only inside the cohorts the user explicitly chose.
            # Old cohorts outside the current selection are not considered missing.
            not_seen = sum(
                1
                for row in existing_rows
                if row.cohort_id in selected_cohort_ids
                and "SEI" in str(row.source_system or "").upper()
                and row.student_code.casefold() not in incoming_codes
            )
            if not_seen:
                warnings.append(
                    f"{not_seen} aluno(s) das turmas selecionadas não apareceram no relatório atual. Nenhum registro foi excluído ou teve o status alterado automaticamente."
                )

            self.db.flush()
            self._reconcile_cohort_statuses(lifecycle_cohort_ids)

            sensitive_codes = {row.student_code for row in normalized.students if row.student_code}
            audit_warnings: list[str] = []
            for message in warnings[:200]:
                sanitized = str(message)
                for code in sensitive_codes:
                    if code in sanitized:
                        sanitized = sanitized.replace(code, "[matrícula omitida]")
                sanitized = re.sub(
                    r"(?<![\w.-])(?=[A-Za-z0-9._-]{5,}\b)(?=[A-Za-z0-9._-]*\d)[A-Za-z0-9._-]+",
                    "[identificador omitido]",
                    sanitized,
                )
                audit_warnings.append(sanitized)

            sync = DmSeiSyncRun(
                directorate_id=self.directorate_id,
                source_type=str(source_type or "upload")[:30],
                source_name=normalized.source_name[:255] if normalized.source_name else None,
                source_sha256=normalized.source_sha256 or None,
                status="Concluída",
                cohorts_detected=len(normalized.cohorts),
                students_detected=len(normalized.students),
                cohorts_created=cohort_created,
                cohorts_updated=cohort_updated,
                students_created=created,
                students_updated=updated,
                students_unchanged=unchanged,
                students_not_seen=not_seen,
                warnings_json=json.dumps(audit_warnings, ensure_ascii=False),
                started_at=now,
                completed_at=now,
                inserted_by=self.scope.user.email,
            )
            self.db.add(sync)
            self.db.commit()
            self.db.refresh(sync)
        except Exception:
            self.db.rollback()
            raise

        selected_keys = [f"{block.area_code}:{block.cohort_number}" for block in normalized.cohorts]
        return {
            "ok": True,
            "sync": self._sync_run_to_dict(sync),
            "quality": self.data_quality_summary(),
            "selected_cohort_keys": selected_keys,
            "selected_cohort_ids": [cohort_map[(block.area_code, block.cohort_number)].id for block in normalized.cohorts],
            "message": (
                f"SEI sincronizado nas {len(selected_keys)} turma(s) selecionada(s): "
                f"{created} aluno(s) novo(s), {updated} atualizado(s) e {unchanged} sem alteração."
            ),
            "warnings": warnings[:200],
            "credentials_persisted": False,
            "absence_is_deletion": False,
        }
