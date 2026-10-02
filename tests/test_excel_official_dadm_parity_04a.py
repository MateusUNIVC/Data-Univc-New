from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dadm_excel_parity import audit_dadm_parity
from models import (
    Base,
    DADMTallosAttendance,
    DADMTallosDepartmentMap,
    DADMTallosSyncRun,
    Directorate,
    ManagementAction,
    ManagementTarget,
)


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Directorate.__table__,
            DADMTallosSyncRun.__table__,
            DADMTallosDepartmentMap.__table__,
            DADMTallosAttendance.__table__,
            ManagementTarget.__table__,
            ManagementAction.__table__,
        ],
    )
    db = Session(engine)
    db.add(Directorate(id=1, code="DADM", name="Diretoria Administrativa", active=True))
    db.add_all(
        [
            DADMTallosDepartmentMap(directorate_id=1, source_key="secretaria", display_name="Secretaria", active=True),
            DADMTallosDepartmentMap(directorate_id=1, source_key="financeiro", display_name="Financeiro", active=True),
        ]
    )
    db.add(
        DADMTallosSyncRun(
            id=1,
            directorate_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 9, 30),
            trigger="manual",
            status="completed",
            records_received=14,
            records_inserted=14,
            finished_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add_all(
        [
            ManagementTarget(directorate_id=1, indicator_code="DADM-01", metric_key="tme_avg_seconds", dimension_key="V2:TOTAL", dimension_label="Institucional", valid_from="2026-01", target=600.0, attention=900.0),
            ManagementTarget(directorate_id=1, indicator_code="DADM-01", metric_key="tme_avg_seconds", dimension_key="V2:department:secretaria", dimension_label="Departamento: secretaria", valid_from="2026-01", target=300.0, attention=420.0),
            ManagementTarget(directorate_id=1, indicator_code="DADM-01", metric_key="tme_avg_seconds", dimension_key="V2:channel:whatsapp", dimension_label="Canal: whatsapp", valid_from="2026-01", target=240.0, attention=360.0),
            ManagementTarget(directorate_id=1, indicator_code="DADM-02", metric_key="rating_coverage_pct", dimension_key="V2:TOTAL", dimension_label="Institucional", valid_from="2026-01", target=70.0, attention=50.0),
        ]
    )

    rows = [
        # month, dept, employee, channel, status, rating, tme, tma, transferred, protocol, customer
        # Previous-period evidence used by 04B. These rows are outside the Jul-Sep
        # export window but inside the DADM V2 previous_period comparison range.
        ("2026-06", "secretaria", "e1", "whatsapp", "finalized", 9, 180.0, 720.0, False, "p-01", "c-01"),
        ("2026-06", "financeiro", "e2", "email", "finalized", 7, 300.0, 1500.0, False, "p-02", "c-02"),
        ("2026-07", "secretaria", "e1", "whatsapp", "finalized", 10, 120.0, 600.0, False, "p01", "c01"),
        ("2026-07", "secretaria", "e1", "whatsapp", "finalized", 8, 240.0, 900.0, True, "p02", "c02"),
        ("2026-07", "financeiro", "e2", "email", "open", None, 300.0, None, False, "p03", "c03"),
        ("2026-07", "financeiro", "e3", "whatsapp", "finalized", 6, None, 1200.0, False, "p04", "c04"),
        ("2026-08", "secretaria", "e1", "whatsapp", "finalized", 9, 60.0, 300.0, False, "p05", "c05"),
        ("2026-08", "secretaria", "e4", "instagram", "open", None, 180.0, None, True, "p06", "c06"),
        ("2026-08", "financeiro", "e2", "email", "finalized", 7, 420.0, 1800.0, False, "p07", "c07"),
        ("2026-08", "financeiro", "e2", "email", "finalized", 10, 240.0, 1500.0, True, "p08", "c08"),
        ("2026-09", "secretaria", "e1", "whatsapp", "finalized", 10, 90.0, 480.0, False, "p09", "c09"),
        ("2026-09", "secretaria", "e4", "instagram", "finalized", 9, 150.0, 720.0, False, "p10", "c10"),
        ("2026-09", "financeiro", "e3", "whatsapp", "unknown", None, None, None, False, "p11", "c02"),
        ("2026-09", "financeiro", "e2", "email", "finalized", 5, 600.0, 2100.0, True, "p12", "c12"),
    ]
    day = 2
    for index, item in enumerate(rows, start=1):
        month, dept, employee, channel, status, rating, tme, tma, transferred, protocol, customer = item
        y, m = (int(part) for part in month.split("-"))
        ref_date = date(y, m, min(day + index, 25))
        ref_at = datetime(y, m, min(day + index, 25), 14, 0, tzinfo=timezone.utc)
        db.add(
            DADMTallosAttendance(
                directorate_id=1,
                source_id=f"source-{index:03d}",
                protocol=protocol,
                customer_ref=customer,
                employee_id=employee,
                employee_name={"e1": "Ana", "e2": "Bruno", "e3": "Carla", "e4": "Diego"}[employee],
                department_key=dept,
                department_name=dept.title(),
                channel=channel,
                tabulation="academico" if dept == "secretaria" else "financeiro",
                status=status,
                rating=rating,
                rating_source_state="valid" if rating is not None else "missing",
                rating_source_value=str(rating) if rating is not None else None,
                normalization_version=5,
                tme_seconds=tme,
                tma_seconds=tma,
                messages_sent=3 + index,
                messages_received=2 + index,
                transferred=transferred,
                reference_at=ref_at,
                reference_date=ref_date,
                month_key=month,
                source_hash=f"{index:064x}",
                source_payload_json="{}",
                last_sync_run_id=1,
            )
        )
    db.commit()
    return db


def test_dadm_04a_parity_matches_current_v2_semantics_across_total_department_and_month():
    db = _db()
    try:
        report = audit_dadm_parity(
            db,
            1,
            "2026-07",
            "2026-09",
            source_kind="fixture",
            generated_by="qa@univc.br",
            build_workbooks=True,
        )
        # 1 total + 2 departments + 3 months, each across 8 exactly recomposable
        # metrics, plus 5 previous-period snapshot comparisons introduced in 04B.
        assert len(report.cases) == (6 * 8) + 5
        assert report.failures == ()
        assert report.cutover_status == "CANDIDATE_PASS"
        assert report.source_quality_ok is True
        assert report.legacy_workbook is not None and report.legacy_workbook.build_ok is True
        assert report.new_workbook is not None and report.new_workbook.build_ok is True
        assert report.new_release_allowed is True
        assert report.new_workbook.sheets >= 6
        assert report.new_workbook.formulas > 0
        previous = [case for case in report.cases if case.scope == "Período anterior · recorte exportado"]
        assert len(previous) == 5
        assert any(case.expected not in (None, 0) for case in previous)
    finally:
        db.close()


def test_dadm_04a_parity_respects_authorized_department_scope():
    db = _db()
    try:
        report = audit_dadm_parity(
            db,
            1,
            "2026-07",
            "2026-09",
            allowed_departments=("secretaria",),
            source_kind="fixture",
            build_workbooks=False,
        )
        scopes = {case.scope for case in report.cases}
        assert any("Secretaria" in scope for scope in scopes)
        assert not any("Financeiro" in scope for scope in scopes)
        assert report.failures == ()
        # Workbook evidence is deliberately omitted in this lightweight audit,
        # so cutover cannot be promoted by accident.
        assert report.cutover_status == "BLOCKED"
    finally:
        db.close()


def test_dadm_04a_fixture_evidence_never_promotes_to_production_ready():
    db = _db()
    try:
        report = audit_dadm_parity(db, 1, "2026-07", "2026-09", source_kind="fixture", build_workbooks=True)
        assert report.cutover_status == "CANDIDATE_PASS"
        assert report.to_dict()["summary"]["failures"] == 0
        assert "no satisfaction threshold is inferred" in report.to_markdown()
    finally:
        db.close()


def test_dadm_04b_payload_auto_loads_management_targets_from_schema53_tables():
    from dadm_excel_official import build_dadm_excel_official_payload_from_db

    db = _db()
    try:
        payload = build_dadm_excel_official_payload_from_db(db, 1, "2026-07", "2026-09")
        assert len(payload["targets"]) == 4
        assert any(row["scope_type"] == "department" and row["scope_value"] == "secretaria" for row in payload["targets"])
        assert payload["comparison_period"]["mode"] == "previous_period"
        assert payload["comparison"]["attendances"] > 0
    finally:
        db.close()
