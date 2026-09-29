from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from dpe_cost_analytics import DPECostAnalyticsRepository
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_revenues import DPERevenueRepository
from models import (
    Course,
    Directorate,
    DPEAllocationRule,
    DPECostAllocationResult,
    DPECostAllocationRun,
    DPECostCenter,
    DPECostExpense,
    DPEExpenseCategory,
)
from security import AuthorizationContext, DirectorateScope


class DPEV0122TestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.dpe = Directorate(code="DPE", name="DPE", active=True)
        self.dtnh = Directorate(code="DTNH", name="DTNH", active=True)
        self.db.add_all([self.dpe, self.dtnh])
        self.db.commit()
        self.db.refresh(self.dpe)
        user = AuthorizationContext(
            user_id="test-v0122", email="v0122@test.local", full_name="Test",
            role="editor", directorate_id=self.dpe.id, directorate_code="DPE", directorate_name="DPE",
        )
        self.scope = DirectorateScope(
            user=user, directorate_id=self.dpe.id, directorate_code="DPE",
            directorate_name="DPE", can_write=True, is_home=True,
        )
        self.catalog = DPECostCatalogRepository(self.db, self.scope)
        self.economics = DPECostEconomicsRepository(self.db, self.scope)
        self.revenues = DPERevenueRepository(self.db, self.scope)
        self.analytics = DPECostAnalyticsRepository(self.db, self.scope)

        self.rules = {}
        for code, driver in [("DIRECT", "DIRECT"), ("EQUAL", "EQUAL")]:
            row = DPEAllocationRule(
                directorate_id=self.dpe.id, code=code, name=code,
                driver_type=driver, active=True, system_defined=True, created_by="test",
            )
            self.db.add(row)
            self.db.flush()
            self.rules[driver] = row
        self.center_admin = DPECostCenter(
            directorate_id=self.dpe.id, code="ADMIN", name="Administrativo",
            active=True, created_by="test",
        )
        self.center_lab = DPECostCenter(
            directorate_id=self.dpe.id, code="LAB", name="Laboratórios",
            active=True, created_by="test",
        )
        self.cat_payroll = DPEExpenseCategory(
            directorate_id=self.dpe.id, code="FOLHA", name="Folha docente",
            default_rule_id=self.rules["EQUAL"].id, active=True, created_by="test",
        )
        self.cat_software = DPEExpenseCategory(
            directorate_id=self.dpe.id, code="SOFT", name="Software",
            default_rule_id=self.rules["DIRECT"].id, active=True, created_by="test",
        )
        self.cat_energy = DPEExpenseCategory(
            directorate_id=self.dpe.id, code="ENERG", name="Energia",
            default_rule_id=self.rules["EQUAL"].id, active=True, created_by="test",
        )
        self.db.add_all([self.center_admin, self.center_lab, self.cat_payroll, self.cat_software, self.cat_energy])
        self.db.commit()

        self._course("Direito", "DIR")
        self._course("Farmácia", "FARM")
        self.aug = self.catalog.create_period({"period": "2026-08", "materialize_offerings": True})
        self.sep = self.catalog.create_period({"period": "2026-09", "materialize_offerings": True})
        self._fill_period(self.aug, factor=1.0)
        self._fill_period(self.sep, factor=1.2)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _course(self, name: str, code: str):
        course = Course(
            directorate_id=self.dtnh.id, name=name, modality="Presencial",
            active=True, valid_from="2026-01",
        )
        self.db.add(course)
        self.db.commit()
        self.db.refresh(course)
        product = self.catalog.create_product({
            "code": code, "name": name, "source_course_id": course.id, "valid_from": "2026-01",
        })
        self.catalog.create_offering({
            "product_id": product["id"], "code": f"{code}-N", "modality": "PRESENCIAL",
            "shift": "Noturno", "valid_from": "2026-01",
        })

    def _expense(self, period_id: int, description: str, amount: float, *, kind: str, category, center, driver: str):
        row = DPECostExpense(
            directorate_id=self.dpe.id, period_id=period_id, description=description,
            amount=Decimal(str(amount)), expense_kind=kind, category_id=category.id,
            cost_center_id=center.id, allocation_rule_id=self.rules[driver].id,
            source_type="MANUAL", status="ACTIVE", created_by="test", updated_by="test",
            classification_snapshot_json={
                "category": {"id": category.id, "code": category.code, "name": category.name},
                "cost_center": {"id": center.id, "code": center.code, "name": center.name},
                "allocation_rule": {"id": self.rules[driver].id, "code": self.rules[driver].code, "name": driver, "driver_type": driver},
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _fill_period(self, period_payload: dict, factor: float):
        offerings = [row for row in period_payload["offerings"] if row["included"]]
        offerings = sorted(offerings, key=lambda row: row["product"]["name"])
        self.revenues.bulk_courses(period_payload["id"], [
            {"period_offering_id": offerings[0]["id"], "amount": 108000 * factor},
            {"period_offering_id": offerings[1]["id"], "amount": 94000 * factor},
        ])
        self.economics.upsert_many(period_payload["id"], [
            {"period_offering_id": offerings[0]["id"], "active_students": 100},
            {"period_offering_id": offerings[1]["id"], "active_students": 80},
        ])
        payroll = self._expense(period_payload["id"], "Folha", 60000 * factor, kind="PAYROLL", category=self.cat_payroll, center=self.center_admin, driver="EQUAL")
        software = self._expense(period_payload["id"], "Software", 20000 * factor, kind="GENERAL", category=self.cat_software, center=self.center_lab, driver="DIRECT")
        energy = self._expense(period_payload["id"], "Energia", 30000 * factor, kind="GENERAL", category=self.cat_energy, center=self.center_admin, driver="EQUAL")
        self.db.commit()
        total = Decimal(str((60000 + 20000 + 30000) * factor))
        fingerprint = DPECostAllocationRepository(self.db, self.scope)._input_fingerprint(period_payload["id"])
        run = DPECostAllocationRun(
            directorate_id=self.dpe.id, period_id=period_payload["id"], run_number=1,
            status="OFFICIAL", input_fingerprint=fingerprint, expense_total=total, allocated_total=total, unallocated_total=Decimal("0"),
            summary_json={}, created_by="test", official_by="test",
        )
        self.db.add(run)
        self.db.flush()
        # Direito receives 60% of shared and the direct software; Farmácia 40% of shared.
        allocation = [
            (payroll, offerings[0], 36000 * factor, "EQUAL"),
            (payroll, offerings[1], 24000 * factor, "EQUAL"),
            (software, offerings[0], 20000 * factor, "DIRECT"),
            (energy, offerings[0], 18000 * factor, "EQUAL"),
            (energy, offerings[1], 12000 * factor, "EQUAL"),
        ]
        for expense, offering, amount, driver in allocation:
            snapshot = {
                "id": expense.id, "description": expense.description,
                "amount": float(expense.amount), "expense_kind": expense.expense_kind,
                "classification": dict(expense.classification_snapshot_json or {}),
                "rule": {"driver_type": driver},
            }
            self.db.add(DPECostAllocationResult(
                run_id=run.id, expense_id=expense.id, period_offering_id=offering["id"],
                allocation_rule_id=self.rules[driver].id, driver_type=driver,
                allocated_amount=Decimal(str(amount)), percentage=Decimal("0"),
                basis_json={}, expense_snapshot_json=snapshot,
                offering_snapshot_json=offering,
            ))
        self.db.commit()

    def test_cards_compare_selected_month_with_previous(self):
        data = self.analytics.dashboard(period_id=self.sep["id"], window_months=12)
        self.assertEqual(data["selected_period"]["period"], "2026-09")
        self.assertEqual(data["previous_period"]["period"], "2026-08")
        self.assertAlmostEqual(data["cards"]["total_revenue"]["value"], 242400.0)
        self.assertAlmostEqual(data["cards"]["expense_total"]["value"], 132000.0)
        self.assertAlmostEqual(data["cards"]["total_revenue"]["comparison"]["percent"], 20.0)
        self.assertEqual(len(data["trend"]), 2)

    def test_expenses_group_by_snapshot_category_and_sector(self):
        data = self.analytics.dashboard(period_id=self.sep["id"])
        categories = {row["key"]: row["amount"] for row in data["expenses_by_category"]}
        sectors = {row["key"]: row["amount"] for row in data["expenses_by_sector"]}
        self.assertEqual(categories["Folha docente"], 72000.0)
        self.assertEqual(categories["Software"], 24000.0)
        self.assertEqual(sectors["Administrativo"], 108000.0)
        self.assertEqual(sectors["Laboratórios"], 24000.0)

    def test_category_comparison_reports_current_previous_and_change(self):
        data = self.analytics.dashboard(period_id=self.sep["id"])
        row = next(item for item in data["category_comparison"] if item["key"] == "Energia")
        self.assertEqual(row["current"], 36000.0)
        self.assertEqual(row["previous"], 30000.0)
        self.assertEqual(row["change"], 6000.0)
        self.assertEqual(row["change_percent"], 20.0)

    def test_course_metrics_use_official_allocation_run(self):
        data = self.analytics.dashboard(period_id=self.sep["id"])
        direito = next(row for row in data["courses"] if row["course"] == "Direito")
        farmacia = next(row for row in data["courses"] if row["course"] == "Farmácia")
        self.assertEqual(direito["allocated_cost"], 88800.0)
        self.assertEqual(direito["teaching_cost"], 43200.0)
        self.assertEqual(direito["direct_cost"], 24000.0)
        self.assertEqual(direito["shared_cost"], 21600.0)
        self.assertEqual(farmacia["allocated_cost"], 43200.0)
        self.assertNotIn("administrative_cost", direito)

    def test_waterfall_reconciles_without_inventing_administrative_overhead(self):
        data = self.analytics.dashboard(period_id=self.sep["id"])
        wf = data["waterfall"]
        self.assertTrue(wf["reconciled"])
        self.assertEqual(wf["teaching_cost"], 72000.0)
        self.assertEqual(wf["direct_cost"], 24000.0)
        self.assertEqual(wf["shared_cost"], 36000.0)
        self.assertEqual(wf["institutional_cost"], 0.0)
        self.assertIn("resultado institucional", wf["note"])

    def test_course_history_tracks_same_official_course_across_months(self):
        initial = self.analytics.dashboard(period_id=self.sep["id"])
        key = next(row["key"] for row in initial["course_options"] if row["label"] == "Direito")
        data = self.analytics.dashboard(period_id=self.sep["id"], course_key=key)
        self.assertEqual([row["period"] for row in data["course_history"]], ["2026-08", "2026-09"])
        self.assertTrue(all(row["course"] == "Direito" for row in data["course_history"]))
        self.assertGreater(data["course_history"][1]["revenue"], data["course_history"][0]["revenue"])

    def test_stale_official_run_is_not_used_for_course_analytics(self):
        expense = self.db.query(DPECostExpense).filter(
            DPECostExpense.period_id == self.sep["id"],
            DPECostExpense.description == "Software",
        ).one()
        expense.amount = Decimal("99999.00")
        self.db.commit()
        data = self.analytics.dashboard(period_id=self.sep["id"])
        self.assertTrue(all(row["allocated_cost"] is None for row in data["courses"]))
        self.assertTrue(any("Allocation Run" in item for item in data["limitations"]))

    def test_missing_official_run_hides_course_cost_but_keeps_ledger_result(self):
        october = self.catalog.create_period({"period": "2026-10", "materialize_offerings": True})
        offers = sorted([r for r in october["offerings"] if r["included"]], key=lambda r: r["product"]["name"])
        self.revenues.bulk_courses(october["id"], [
            {"period_offering_id": offers[0]["id"], "amount": 10000},
            {"period_offering_id": offers[1]["id"], "amount": 10000},
        ])
        self.economics.upsert_many(october["id"], [
            {"period_offering_id": offers[0]["id"], "active_students": 10},
            {"period_offering_id": offers[1]["id"], "active_students": 10},
        ])
        self._expense(october["id"], "Energia outubro", 5000, kind="GENERAL", category=self.cat_energy, center=self.center_admin, driver="EQUAL")
        self.db.commit()
        data = self.analytics.dashboard(period_id=october["id"])
        self.assertEqual(data["cards"]["economic_result"]["value"], 15000.0)
        self.assertTrue(all(row["allocated_cost"] is None for row in data["courses"]))
        self.assertTrue(any("Allocation Run" in item for item in data["limitations"]))


if __name__ == "__main__":
    unittest.main()
