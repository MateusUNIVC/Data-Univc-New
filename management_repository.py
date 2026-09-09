from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from management_catalog import (
    ManagementCatalogError,
    default_comparison,
    directorate_spec,
    indicator_spec,
    metric_spec,
    period_sort_key,
    validate_period,
)
from management_service import ManagementValidationError, canonical_dimensions, validate_measurement_payload
from auth.objects import require_object_for_directorate
from models import ManagementAction, ManagementMeasurement, ManagementTarget
from security import DirectorateScope


class ManagementRepository:
    def __init__(self, db: Session, scope: DirectorateScope):
        self.db = db
        self.scope = scope
        if scope.directorate_code not in {"DADM", "DPE", "DM"}:
            raise ManagementCatalogError("O módulo gerencial está disponível apenas para DADM, DPE e DM.")

    @property
    def directorate_id(self) -> int:
        return self.scope.directorate_id

    @property
    def directorate_code(self) -> str:
        return self.scope.directorate_code

    def _require_write(self) -> None:
        if not self.scope.can_write:
            raise PermissionError("A diretoria selecionada está disponível somente para leitura.")

    @staticmethod
    def _loads(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def measurement_to_dict(self, row: ManagementMeasurement) -> dict[str, Any]:
        return {
            "id": row.id,
            "directorate_code": self.directorate_code,
            "indicator_code": row.indicator_code,
            "period": row.period,
            "dimension_key": row.dimension_key,
            "dimension_label": row.dimension_label,
            "dimensions": self._loads(row.dimensions_json),
            "values": self._loads(row.values_json),
            "notes": row.notes,
            "source_reference": row.source_reference,
            "validated": bool(row.validated),
            "inserted_at": row.inserted_at.isoformat() if row.inserted_at else None,
            "inserted_by": row.inserted_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def target_to_dict(self, row: ManagementTarget) -> dict[str, Any]:
        return {
            "id": row.id,
            "directorate_code": self.directorate_code,
            "indicator_code": row.indicator_code,
            "metric_key": row.metric_key,
            "dimension_key": row.dimension_key,
            "dimension_label": row.dimension_label,
            "valid_from": row.valid_from,
            "valid_to": row.valid_to,
            "target": row.target,
            "attention": row.attention,
            "target_min": row.target_min,
            "target_max": row.target_max,
            "attention_min": row.attention_min,
            "attention_max": row.attention_max,
            "justification": row.justification,
            "inserted_at": row.inserted_at.isoformat() if row.inserted_at else None,
            "inserted_by": row.inserted_by,
        }

    def action_to_dict(self, row: ManagementAction) -> dict[str, Any]:
        return {
            "id": row.id,
            "directorate_code": self.directorate_code,
            "indicator_code": row.indicator_code,
            "metric_key": row.metric_key,
            "period": row.period,
            "dimension_key": row.dimension_key,
            "dimension_label": row.dimension_label,
            "problem": row.problem,
            "probable_cause": row.probable_cause,
            "corrective_action": row.corrective_action,
            "responsible": row.responsible,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "status": row.status,
            "evidence": row.evidence,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by": row.created_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def list_measurements(
        self,
        *,
        indicator_code: str | None = None,
        period: str | None = None,
        dimension_key: str | None = None,
        dimension_search: str | None = None,
        validated: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        conditions = [ManagementMeasurement.directorate_id == self.directorate_id]
        if indicator_code:
            indicator_spec(self.directorate_code, indicator_code)
            conditions.append(ManagementMeasurement.indicator_code == indicator_code.upper())
        if period:
            conditions.append(ManagementMeasurement.period == validate_period(self.directorate_code, period))
        if dimension_key:
            conditions.append(ManagementMeasurement.dimension_key == dimension_key)
        if dimension_search:
            conditions.append(ManagementMeasurement.dimension_label.ilike(f"%{dimension_search.strip()}%"))
        if validated is not None:
            conditions.append(ManagementMeasurement.validated.is_(validated))

        total = self.db.scalar(
            select(func.count(ManagementMeasurement.id)).where(*conditions)
        ) or 0
        rows = self.db.scalars(
            select(ManagementMeasurement)
            .where(*conditions)
            .order_by(
                ManagementMeasurement.period.desc(),
                ManagementMeasurement.indicator_code,
                ManagementMeasurement.dimension_label,
            )
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
        ).all()
        items = [self.measurement_to_dict(row) for row in rows]
        return {
            "items": items,
            "total": int(total),
            "offset": max(0, offset),
            "limit": max(1, min(limit, 500)),
            "has_more": offset + len(items) < int(total),
            "next_offset": offset + len(items) if offset + len(items) < int(total) else None,
        }

    def all_measurements(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(ManagementMeasurement)
            .where(ManagementMeasurement.directorate_id == self.directorate_id)
            .order_by(ManagementMeasurement.period, ManagementMeasurement.indicator_code)
        ).all()
        return [self.measurement_to_dict(row) for row in rows]

    def dashboard_measurements(
        self,
        *,
        reference: str | None = None,
        comparison: str | None = None,
        window: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return only periods that can affect the management dashboard.

        Raw management measurements are already KPI facts, but loading every
        historical period on every dashboard request makes cost grow forever.
        The dashboard needs the requested series window plus a small amount of
        history for governance/rolling rules and the explicit comparison period.
        """
        reference_value = validate_period(self.directorate_code, reference) if reference else None
        comparison_value = validate_period(self.directorate_code, comparison) if comparison else None

        requested_window = max(1, int(window or 12))
        minimum_history = 12 if self.directorate_code == "DPE" else 3 if self.directorate_code == "DADM" else 1
        history_limit = max(requested_window, minimum_history)

        period_conditions = [ManagementMeasurement.directorate_id == self.directorate_id]
        if reference_value:
            # Both supported period formats are lexicographically chronological:
            # YYYY-MM and YYYY-SEM1/YYYY-SEM2.
            period_conditions.append(ManagementMeasurement.period <= reference_value)

        periods = list(self.db.scalars(
            select(ManagementMeasurement.period)
            .where(*period_conditions)
            .distinct()
            .order_by(ManagementMeasurement.period.desc())
            .limit(history_limit)
        ).all())

        effective_reference = reference_value or (periods[0] if periods else None)
        effective_comparison = comparison_value
        if effective_comparison is None and effective_reference:
            effective_comparison = default_comparison(self.directorate_code, effective_reference)

        selected_periods = set(periods)
        if effective_comparison:
            selected_periods.add(effective_comparison)
        if not selected_periods:
            return []

        rows = self.db.scalars(
            select(ManagementMeasurement)
            .where(
                ManagementMeasurement.directorate_id == self.directorate_id,
                ManagementMeasurement.period.in_(selected_periods),
            )
            .order_by(ManagementMeasurement.period, ManagementMeasurement.indicator_code)
        ).all()
        return [self.measurement_to_dict(row) for row in rows]

    def upsert_measurement(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        clean = validate_measurement_payload(self.directorate_code, payload)
        row = self.db.scalar(
            select(ManagementMeasurement).where(
                ManagementMeasurement.directorate_id == self.directorate_id,
                ManagementMeasurement.indicator_code == clean["indicator_code"],
                ManagementMeasurement.period == clean["period"],
                ManagementMeasurement.dimension_key == clean["dimension_key"],
            )
        )
        if row is None:
            row = ManagementMeasurement(
                directorate_id=self.directorate_id,
                indicator_code=clean["indicator_code"],
                period=clean["period"],
                dimension_key=clean["dimension_key"],
            )
            self.db.add(row)
        row.dimension_label = clean["dimension_label"]
        row.dimensions_json = json.dumps(clean["dimensions"], ensure_ascii=False, sort_keys=True)
        row.values_json = json.dumps(clean["values"], ensure_ascii=False, sort_keys=True)
        row.notes = clean["notes"]
        row.source_reference = clean["source_reference"]
        row.validated = clean["validated"]
        row.inserted_by = self.scope.user.email
        self.db.commit()
        self.db.refresh(row)
        return self.measurement_to_dict(row)

    def bulk_upsert_measurements(self, payloads: list[dict[str, Any]]) -> dict[str, Any]:
        """Valida e grava uma importação inteira em uma única transação.

        Nenhuma linha é confirmada se uma das medições for inválida. Linhas
        repetidas dentro do mesmo arquivo são rejeitadas para impedir que a
        última ocorrência sobrescreva silenciosamente a primeira.
        """
        self._require_write()
        clean_rows = [validate_measurement_payload(self.directorate_code, payload) for payload in payloads]
        seen: set[tuple[str, str, str]] = set()
        for clean in clean_rows:
            key = (clean["indicator_code"], clean["period"], clean["dimension_key"])
            if key in seen:
                raise ManagementValidationError(
                    "A planilha contém mais de uma linha para o mesmo indicador, período e dimensão."
                )
            seen.add(key)

        existing_rows = self.db.scalars(
            select(ManagementMeasurement).where(
                ManagementMeasurement.directorate_id == self.directorate_id,
            )
        ).all()
        existing = {
            (row.indicator_code, row.period, row.dimension_key): row
            for row in existing_rows
        }
        created = 0
        updated = 0
        touched: list[ManagementMeasurement] = []
        try:
            for clean in clean_rows:
                key = (clean["indicator_code"], clean["period"], clean["dimension_key"])
                row = existing.get(key)
                if row is None:
                    row = ManagementMeasurement(
                        directorate_id=self.directorate_id,
                        indicator_code=clean["indicator_code"],
                        period=clean["period"],
                        dimension_key=clean["dimension_key"],
                    )
                    self.db.add(row)
                    existing[key] = row
                    created += 1
                else:
                    updated += 1
                row.dimension_label = clean["dimension_label"]
                row.dimensions_json = json.dumps(clean["dimensions"], ensure_ascii=False, sort_keys=True)
                row.values_json = json.dumps(clean["values"], ensure_ascii=False, sort_keys=True)
                row.notes = clean["notes"]
                row.source_reference = clean["source_reference"]
                row.validated = clean["validated"]
                row.inserted_by = self.scope.user.email
                touched.append(row)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "total": len(clean_rows),
        }

    def update_measurement(self, row_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_write()
        row = require_object_for_directorate(self.db, ManagementMeasurement, row_id, self.directorate_id, label="Medição")
        merged = self.measurement_to_dict(row)
        for key in ("indicator_code", "period", "dimensions", "values", "notes", "source_reference", "validated"):
            if key in payload:
                merged[key] = payload[key]
        clean = validate_measurement_payload(self.directorate_code, merged)
        conflict = self.db.scalar(
            select(ManagementMeasurement).where(
                ManagementMeasurement.directorate_id == self.directorate_id,
                ManagementMeasurement.indicator_code == clean["indicator_code"],
                ManagementMeasurement.period == clean["period"],
                ManagementMeasurement.dimension_key == clean["dimension_key"],
                ManagementMeasurement.id != row.id,
            )
        )
        if conflict:
            raise ManagementValidationError("Já existe uma medição para o mesmo indicador, período e dimensão.")
        row.indicator_code = clean["indicator_code"]
        row.period = clean["period"]
        row.dimension_key = clean["dimension_key"]
        row.dimension_label = clean["dimension_label"]
        row.dimensions_json = json.dumps(clean["dimensions"], ensure_ascii=False, sort_keys=True)
        row.values_json = json.dumps(clean["values"], ensure_ascii=False, sort_keys=True)
        row.notes = clean["notes"]
        row.source_reference = clean["source_reference"]
        row.validated = clean["validated"]
        self.db.commit()
        self.db.refresh(row)
        return self.measurement_to_dict(row)

    def delete_measurement(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(self.db, ManagementMeasurement, row_id, self.directorate_id, label="Medição")
        self.db.delete(row)
        self.db.commit()

    def list_targets(self, *, indicator_code: str | None = None) -> list[dict[str, Any]]:
        conditions = [ManagementTarget.directorate_id == self.directorate_id]
        if self.directorate_code == "DADM":
            conditions.append(~ManagementTarget.dimension_key.like("V2:%"))
        if indicator_code:
            indicator_spec(self.directorate_code, indicator_code)
            conditions.append(ManagementTarget.indicator_code == indicator_code.upper())
        rows = self.db.scalars(
            select(ManagementTarget)
            .where(*conditions)
            .order_by(ManagementTarget.indicator_code, ManagementTarget.metric_key, ManagementTarget.valid_from.desc())
        ).all()
        return [self.target_to_dict(row) for row in rows]

    def save_target(self, payload: dict[str, Any], row_id: int | None = None) -> dict[str, Any]:
        self._require_write()
        indicator_code = str(payload.get("indicator_code") or "").strip().upper()
        metric_key = str(payload.get("metric_key") or "").strip()
        spec = indicator_spec(self.directorate_code, indicator_code)
        metric = metric_spec(self.directorate_code, indicator_code, metric_key)
        valid_from = validate_period(self.directorate_code, payload.get("valid_from"))
        valid_to = payload.get("valid_to")
        if valid_to:
            valid_to = validate_period(self.directorate_code, valid_to)
            if period_sort_key(valid_to) < period_sort_key(valid_from):
                raise ManagementValidationError("A vigência final não pode ser anterior à inicial.")
        dimensions, dimension_key, dimension_label = canonical_dimensions(spec, payload.get("dimensions"))
        numeric_fields = {
            key: self._optional_float(payload.get(key))
            for key in (
                "target", "attention", "target_min", "target_max", "attention_min", "attention_max"
            )
        }
        if metric.get("direction") == "range":
            if numeric_fields["target_min"] is None or numeric_fields["target_max"] is None:
                raise ManagementValidationError("Informe o limite mínimo e o máximo da meta.")
        elif metric.get("direction") not in {"context"} and numeric_fields["target"] is None:
            raise ManagementValidationError("Informe o valor da meta.")

        row = require_object_for_directorate(self.db, ManagementTarget, row_id, self.directorate_id, label="Meta") if row_id else None
        if row is not None and self.directorate_code == "DADM" and str(row.dimension_key or "").startswith("V2:"):
            raise LookupError("Meta não encontrada no contrato legado.")
        if row is None:
            row = ManagementTarget(directorate_id=self.directorate_id)
            self.db.add(row)
        row.indicator_code = indicator_code
        row.metric_key = metric_key
        row.dimension_key = dimension_key
        row.dimension_label = dimension_label
        row.valid_from = valid_from
        row.valid_to = valid_to
        for key, value in numeric_fields.items():
            setattr(row, key, value)
        row.justification = str(payload.get("justification") or "").strip() or None
        row.inserted_by = self.scope.user.email
        self.db.commit()
        self.db.refresh(row)
        return self.target_to_dict(row)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            number = float(str(value).replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise ManagementValidationError("Meta numérica inválida.") from exc
        if not (number == number and abs(number) != float("inf")):
            raise ManagementValidationError("Meta numérica inválida.")
        return number

    def delete_target(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(self.db, ManagementTarget, row_id, self.directorate_id, label="Meta")
        if self.directorate_code == "DADM" and str(row.dimension_key or "").startswith("V2:"):
            raise LookupError("Meta não encontrada no contrato legado.")
        self.db.delete(row)
        self.db.commit()

    def list_actions(self, *, indicator_code: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        conditions = [ManagementAction.directorate_id == self.directorate_id]
        if self.directorate_code == "DADM":
            conditions.append(~ManagementAction.dimension_key.like("V2:%"))
        if indicator_code:
            indicator_spec(self.directorate_code, indicator_code)
            conditions.append(ManagementAction.indicator_code == indicator_code.upper())
        if status:
            conditions.append(ManagementAction.status == status)
        rows = self.db.scalars(
            select(ManagementAction)
            .where(*conditions)
            .order_by(ManagementAction.due_date, ManagementAction.id)
        ).all()
        return [self.action_to_dict(row) for row in rows]

    def save_action(self, payload: dict[str, Any], row_id: int | None = None) -> dict[str, Any]:
        self._require_write()
        indicator_code = str(payload.get("indicator_code") or "").strip().upper()
        spec = indicator_spec(self.directorate_code, indicator_code)
        metric_key = str(payload.get("metric_key") or "").strip() or None
        if metric_key:
            metric_spec(self.directorate_code, indicator_code, metric_key)
        period = validate_period(self.directorate_code, payload.get("period"))
        _, dimension_key, dimension_label = canonical_dimensions(spec, payload.get("dimensions"))
        required = {
            "problem": "Descreva o problema.",
            "corrective_action": "Descreva a ação corretiva.",
            "responsible": "Informe o responsável.",
            "due_date": "Informe o prazo.",
        }
        errors = {key: message for key, message in required.items() if not str(payload.get(key) or "").strip()}
        if errors:
            raise ManagementValidationError("Revise o plano de ação.", errors)
        try:
            due_date = date.fromisoformat(str(payload["due_date"]))
        except ValueError as exc:
            raise ManagementValidationError("Prazo inválido.", {"due_date": "Use AAAA-MM-DD."}) from exc
        row = (
            require_object_for_directorate(
                self.db, ManagementAction, row_id, self.directorate_id, label="Plano de ação"
            )
            if row_id
            else None
        )
        if row is not None and self.directorate_code == "DADM" and str(row.dimension_key or "").startswith("V2:"):
            raise LookupError("Plano de ação não encontrado no contrato legado.")
        if row is None:
            row = ManagementAction(directorate_id=self.directorate_id)
            self.db.add(row)
        row.indicator_code = indicator_code
        row.metric_key = metric_key
        row.period = period
        row.dimension_key = dimension_key
        row.dimension_label = dimension_label
        row.problem = str(payload["problem"]).strip()
        row.probable_cause = str(payload.get("probable_cause") or "").strip() or None
        row.corrective_action = str(payload["corrective_action"]).strip()
        row.responsible = str(payload["responsible"]).strip()
        row.due_date = due_date
        row.status = str(payload.get("status") or "Aberto").strip()
        row.evidence = str(payload.get("evidence") or "").strip() or None
        row.created_by = self.scope.user.email
        self.db.commit()
        self.db.refresh(row)
        return self.action_to_dict(row)

    def delete_action(self, row_id: int) -> None:
        self._require_write()
        row = require_object_for_directorate(
            self.db, ManagementAction, row_id, self.directorate_id, label="Plano de ação"
        )
        if self.directorate_code == "DADM" and str(row.dimension_key or "").startswith("V2:"):
            raise LookupError("Plano de ação não encontrado no contrato legado.")
        self.db.delete(row)
        self.db.commit()
