from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from auth.data_scopes import dadm_preferred_department_name
from dadm_tallos_normalization import department_display
from models import DADMTallosAttendance, DADMTallosDepartmentMap, DADMTallosSyncRun
from security import DirectorateScope


class DADMTallosRepository:
    def __init__(self, db: Session, scope: DirectorateScope):
        self.db = db
        self.scope = scope

    def create_sync_run(self, start_date: date, end_date: date, *, trigger: str, requested_by: str | None) -> DADMTallosSyncRun:
        row = DADMTallosSyncRun(
            directorate_id=self.scope.directorate_id,
            start_date=start_date,
            end_date=end_date,
            trigger=trigger,
            status="queued",
            requested_by=requested_by,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def active_sync_run(self) -> DADMTallosSyncRun | None:
        return self.db.scalar(
            select(DADMTallosSyncRun)
            .where(
                DADMTallosSyncRun.directorate_id == self.scope.directorate_id,
                DADMTallosSyncRun.status.in_(["queued", "running"]),
            )
            .order_by(DADMTallosSyncRun.id.desc())
            .limit(1)
        )

    def list_sync_runs(self, limit: int = 20) -> list[dict]:
        rows = self.db.scalars(
            select(DADMTallosSyncRun)
            .where(DADMTallosSyncRun.directorate_id == self.scope.directorate_id)
            .order_by(DADMTallosSyncRun.id.desc())
            .limit(max(1, min(limit, 100)))
        ).all()
        return [self.sync_run_payload(row) for row in rows]

    @staticmethod
    def sync_run_payload(row: DADMTallosSyncRun) -> dict:
        return {
            "id": row.id,
            "start_date": row.start_date.isoformat(),
            "end_date": row.end_date.isoformat(),
            "trigger": row.trigger,
            "status": row.status,
            "total_expected": row.total_expected,
            "pages_processed": row.pages_processed,
            "records_received": row.records_received,
            "records_inserted": row.records_inserted,
            "records_updated": row.records_updated,
            "records_unchanged": row.records_unchanged,
            "records_failed": row.records_failed,
            "error_message": row.error_message,
            "requested_by": row.requested_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }


    def data_status(self, *, allowed_departments: tuple[str, ...] | None = None) -> dict:
        conditions = [DADMTallosAttendance.directorate_id == self.scope.directorate_id]
        if allowed_departments is not None:
            allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
            conditions.append(func.lower(DADMTallosAttendance.department_key).in_(allowed) if allowed else DADMTallosAttendance.id == -1)
        row = self.db.execute(
            select(
                func.count(DADMTallosAttendance.id),
                func.min(DADMTallosAttendance.reference_date),
                func.max(DADMTallosAttendance.reference_date),
            ).where(*conditions)
        ).one()
        latest = self.db.scalar(
            select(DADMTallosSyncRun)
            .where(DADMTallosSyncRun.directorate_id == self.scope.directorate_id)
            .order_by(DADMTallosSyncRun.id.desc())
            .limit(1)
        )
        return {
            "attendance_count": int(row[0] or 0),
            "available_start": row[1].isoformat() if row[1] else None,
            "available_end": row[2].isoformat() if row[2] else None,
            "latest_sync": self.sync_run_payload(latest) if latest else None,
        }

    def clear_local_analytics_data(self) -> dict[str, int]:
        attendance_count = int(self.db.scalar(select(func.count(DADMTallosAttendance.id)).where(
            DADMTallosAttendance.directorate_id == self.scope.directorate_id
        )) or 0)
        map_count = int(self.db.scalar(select(func.count(DADMTallosDepartmentMap.id)).where(
            DADMTallosDepartmentMap.directorate_id == self.scope.directorate_id
        )) or 0)
        run_count = int(self.db.scalar(select(func.count(DADMTallosSyncRun.id)).where(
            DADMTallosSyncRun.directorate_id == self.scope.directorate_id
        )) or 0)
        self.db.execute(delete(DADMTallosAttendance).where(DADMTallosAttendance.directorate_id == self.scope.directorate_id))
        self.db.execute(delete(DADMTallosDepartmentMap).where(DADMTallosDepartmentMap.directorate_id == self.scope.directorate_id))
        self.db.execute(delete(DADMTallosSyncRun).where(DADMTallosSyncRun.directorate_id == self.scope.directorate_id))
        self.db.commit()
        return {"attendances": attendance_count, "department_maps": map_count, "sync_runs": run_count}

    def _ensure_department_maps(self, payloads: list[dict]) -> dict[str, str]:
        candidates = {
            str(row["department_key"]): (
                dadm_preferred_department_name(str(row["department_key"]))
                or str(row.get("department_name") or row["department_key"])
            )
            for row in payloads
            if row.get("department_key")
        }
        if not candidates:
            return {}
        existing_rows = self.db.scalars(
            select(DADMTallosDepartmentMap).where(
                DADMTallosDepartmentMap.directorate_id == self.scope.directorate_id,
                DADMTallosDepartmentMap.source_key.in_(list(candidates)),
            )
        ).all()
        existing = {row.source_key: row for row in existing_rows}
        repaired_labels: dict[str, str] = {}
        for source_key, label in candidates.items():
            row = existing.get(source_key)
            if row is None:
                self.db.add(DADMTallosDepartmentMap(
                    directorate_id=self.scope.directorate_id,
                    source_key=source_key,
                    display_name=label,
                    active=True,
                ))
                continue
            # Auto-created labels from older normalization versions included the
            # TALLOS suffix (for example ``Financeiro 12c84``).  Repair only
            # untouched mappings; a label explicitly edited by a user wins.
            normalized_label = dadm_preferred_department_name(source_key) or department_display(source_key)[1] or label
            if not row.updated_by and row.display_name != normalized_label:
                row.display_name = normalized_label
                repaired_labels[source_key] = normalized_label
        self.db.flush()
        for source_key, label in repaired_labels.items():
            self.db.execute(
                update(DADMTallosAttendance)
                .where(
                    DADMTallosAttendance.directorate_id == self.scope.directorate_id,
                    DADMTallosAttendance.department_key == source_key,
                )
                .values(department_name=label)
            )
        rows = self.db.scalars(
            select(DADMTallosDepartmentMap).where(
                DADMTallosDepartmentMap.directorate_id == self.scope.directorate_id,
                DADMTallosDepartmentMap.source_key.in_(list(candidates)),
            )
        ).all()
        return {row.source_key: row.display_name for row in rows}

    def upsert_batch(self, rows: Iterable[dict], *, sync_run_id: int) -> dict[str, int]:
        # Defensive de-duplication inside one API page/batch. The TALLOS record ID
        # is the persistence key; if the same record appears twice, the last copy
        # wins instead of violating the unique constraint.
        by_source_id: dict[str, dict] = {}
        for payload in rows:
            source_id = str(payload.get("source_id") or "").strip()
            if source_id:
                by_source_id[source_id] = payload
        payloads = list(by_source_id.values())
        if not payloads:
            return {"inserted": 0, "updated": 0, "unchanged": 0}
        display_names = self._ensure_department_maps(payloads)
        for payload in payloads:
            key = payload.get("department_key")
            if key and key in display_names:
                payload["department_name"] = display_names[key]

        source_ids = [row["source_id"] for row in payloads]
        existing_rows = self.db.scalars(
            select(DADMTallosAttendance).where(
                DADMTallosAttendance.directorate_id == self.scope.directorate_id,
                DADMTallosAttendance.source_id.in_(source_ids),
            )
        ).all()
        existing = {row.source_id: row for row in existing_rows}
        inserted = updated = unchanged = 0
        now = datetime.now(timezone.utc)
        for payload in payloads:
            source_id = payload["source_id"]
            current = existing.get(source_id)
            if current is None:
                self.db.add(DADMTallosAttendance(
                    directorate_id=self.scope.directorate_id,
                    last_sync_run_id=sync_run_id,
                    last_seen_at=now,
                    **payload,
                ))
                inserted += 1
                continue
            current.last_sync_run_id = sync_run_id
            current.last_seen_at = now
            if current.source_hash == payload["source_hash"]:
                unchanged += 1
                continue
            for key, value in payload.items():
                setattr(current, key, value)
            updated += 1
        self.db.commit()
        return {"inserted": inserted, "updated": updated, "unchanged": unchanged}

    def list_department_maps(self, *, allowed_departments: tuple[str, ...] | None = None) -> list[dict]:
        conditions = [DADMTallosDepartmentMap.directorate_id == self.scope.directorate_id]
        if allowed_departments is not None:
            allowed = [str(item).strip().casefold() for item in allowed_departments if str(item).strip()]
            conditions.append(func.lower(DADMTallosDepartmentMap.source_key).in_(allowed) if allowed else DADMTallosDepartmentMap.id == -1)
        rows = self.db.scalars(
            select(DADMTallosDepartmentMap)
            .where(*conditions)
            .order_by(DADMTallosDepartmentMap.display_name, DADMTallosDepartmentMap.source_key)
        ).all()
        return [{
            "id": row.id,
            "source_key": row.source_key,
            "display_name": (
                row.display_name
                if row.updated_by
                else (dadm_preferred_department_name(row.source_key) or department_display(row.source_key)[1] or row.display_name)
            ),
            "active": bool(row.active),
            "notes": row.notes,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        } for row in rows]

    def update_department_map(self, source_key: str, *, display_name: str, active: bool = True, notes: str | None = None) -> dict:
        key = str(source_key or "").strip()
        label = str(display_name or "").strip()
        if not key or not label:
            raise ValueError("Informe o identificador TALLOS e o nome de exibição.")
        row = self.db.scalar(
            select(DADMTallosDepartmentMap).where(
                DADMTallosDepartmentMap.directorate_id == self.scope.directorate_id,
                DADMTallosDepartmentMap.source_key == key,
            )
        )
        if not row:
            row = DADMTallosDepartmentMap(
                directorate_id=self.scope.directorate_id,
                source_key=key,
                display_name=label,
            )
            self.db.add(row)
        row.display_name = label
        row.active = bool(active)
        row.notes = str(notes).strip() if notes else None
        row.updated_by = self.scope.user.email
        # Keep the denormalized display copy aligned without materializing all
        # attendances in Python. Analytics still groups by source_key, so changing
        # the display label never changes facts.
        self.db.execute(
            update(DADMTallosAttendance)
            .where(
                DADMTallosAttendance.directorate_id == self.scope.directorate_id,
                DADMTallosAttendance.department_key == key,
            )
            .values(department_name=label)
        )
        self.db.commit()
        self.db.refresh(row)
        return {
            "id": row.id,
            "source_key": row.source_key,
            "display_name": row.display_name,
            "active": bool(row.active),
            "notes": row.notes,
        }
