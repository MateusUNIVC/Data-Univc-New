from __future__ import annotations

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import Base
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_cost_closure import DPECostClosureRepository
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_revenues import DPERevenueRepository
from dpe_cost_expenses import DPECostExpenseRepository, DPECostExpenseValidationError
from models import Course, Directorate, DPEAllocationRule, DPECostAllocationRun, DPEExpenseCategory
from security import AuthorizationContext, DirectorateScope


class DPEV0124TestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.dpe = Directorate(code="DPE", name="DPE", active=True)
        self.dtnh = Directorate(code="DTNH", name="DTNH", active=True)
        self.db.add_all([self.dpe, self.dtnh])
        self.db.commit(); self.db.refresh(self.dpe)
        user = AuthorizationContext(
            user_id="v0124", email="v0124@test.local", full_name="V0124", role="editor",
            directorate_id=self.dpe.id, directorate_code="DPE", directorate_name="DPE",
        )
        self.scope = DirectorateScope(
            user=user, directorate_id=self.dpe.id, directorate_code="DPE",
            directorate_name="DPE", can_write=True, is_home=True,
        )
        self.catalog = DPECostCatalogRepository(self.db, self.scope)
        self.expenses = DPECostExpenseRepository(self.db, self.scope)
        self.economics = DPECostEconomicsRepository(self.db, self.scope)
        self.revenues = DPERevenueRepository(self.db, self.scope)
        self.allocation = DPECostAllocationRepository(self.db, self.scope)
        self.closure = DPECostClosureRepository(self.db, self.scope)
        self.rule = DPEAllocationRule(
            directorate_id=self.dpe.id, code="EQUAL", name="Igual", driver_type="EQUAL",
            description="Divisao igual", system_defined=True, active=True, created_by="test",
        )
        self.db.add(self.rule); self.db.flush()
        self.category = DPEExpenseCategory(
            directorate_id=self.dpe.id, code="GERAL", name="Geral",
            default_rule_id=self.rule.id, active=True, created_by="test",
        )
        self.db.add(self.category); self.db.commit()
        course = Course(
            directorate_id=self.dtnh.id, name="Administracao", modality="Presencial",
            active=True, valid_from="2026-01",
        )
        self.db.add(course); self.db.commit(); self.db.refresh(course)
        product = self.catalog.create_product({
            "code": "ADM", "name": "Administracao", "source_course_id": course.id, "valid_from": "2026-01",
        })
        self.catalog.create_offering({
            "product_id": product["id"], "code": "ADM-NOT", "modality": "PRESENCIAL",
            "shift": "Noturno", "valid_from": "2026-01",
        })
        self.period = self.catalog.create_period({"period": "2026-09", "materialize_offerings": True})
        self.period_id = self.period["id"]
        self.period_offering_id = self.period["offerings"][0]["id"]

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _ready_month(self, *, revenue_amount: float = 9000):
        expense = self.expenses.create_expense({
            "period_id": self.period_id, "description": "Energia", "amount": 1000,
            "category_id": self.category.id,
        })
        self.allocation.set_expense_config(expense["id"], {
            "allocation_rule_id": self.rule.id, "targets": [],
        })
        self.revenues.bulk_courses(self.period_id, [{
            "period_offering_id": self.period_offering_id, "amount": revenue_amount,
        }])
        self.economics.upsert(self.period_id, self.period_offering_id, {"active_students": 100})
        run = self.allocation.calculate(self.period_id)
        official = self.allocation.make_official(run["id"])
        return expense, official

    def test_checklist_has_teaching_result_and_governance(self):
        self._ready_month()
        checklist = self.closure.checklist(self.period_id)
        by_code = {row["code"]: row for row in checklist["checks"]}
        self.assertEqual(by_code["TEACHING_RECONCILIATION"]["status"], "PASS")
        self.assertEqual(by_code["ECONOMIC_RESULT"]["status"], "PASS")
        self.assertEqual(by_code["ANOMALY_REVIEW"]["status"], "PASS")
        self.assertTrue(checklist["summary"]["can_close"])

    def test_zero_revenue_is_confirmed_and_not_treated_as_missing(self):
        self._ready_month(revenue_amount=0)
        checklist = self.closure.checklist(self.period_id)
        by_code = {row["code"]: row for row in checklist["checks"]}
        self.assertEqual(by_code["COURSE_REVENUE"]["status"], "PASS")
        self.assertEqual(by_code["ECONOMIC_RESULT"]["status"], "PASS")
        self.assertTrue(checklist["summary"]["can_close"])


    def test_return_to_review_supersedes_official_run_and_records_reason(self):
        _, official = self._ready_month()
        self.closure.return_to_review(self.period_id, {"reason": "Corrigir uma despesa identificada na revisao final."})
        period = self.catalog.get_period(self.period_id)
        self.assertEqual(period["status"], "REVIEW")
        run = self.db.get(DPECostAllocationRun, official["id"])
        self.assertEqual(run.status, "SUPERSEDED")
        audit = self.closure.audit_trail(self.period_id)
        event = next(row for row in audit if row["action"] == "return_review")
        self.assertEqual(event["before"]["status"], "CALCULATED")
        self.assertEqual(event["after"]["status"], "REVIEW")
        self.assertIn("Corrigir", event["metadata"]["reason"])

    def test_close_blocks_edits_and_reopen_preserves_audit(self):
        self._ready_month()
        closed = self.closure.close_period(self.period_id, {"note": "Fechamento mensal conferido."})
        self.assertEqual(closed["selected_period"]["status"], "CLOSED")
        with self.assertRaises(DPECostExpenseValidationError):
            self.expenses.create_expense({
                "period_id": self.period_id, "description": "Bloqueada", "amount": 10,
                "category_id": self.category.id,
            })
        reopened = self.closure.reopen_period(self.period_id, {"reason": "Corrigir documento fiscal identificado apos fechamento."})
        self.assertEqual(reopened["selected_period"]["status"], "REVIEW")
        actions = [row["action"] for row in self.closure.audit_trail(self.period_id)]
        self.assertIn("close", actions)
        self.assertIn("reopen", actions)

    def test_expense_update_audit_preserves_before_and_after(self):
        expense = self.expenses.create_expense({
            "period_id": self.period_id, "description": "Software", "amount": 100,
            "category_id": self.category.id,
        })
        self.expenses.update_expense(expense["id"], {"amount": 150})
        audit = self.closure.audit_trail(self.period_id)
        update = next(row for row in audit if row["entity"] == "dpe_expense" and row["action"] == "update")
        self.assertEqual(update["before"]["amount"], 100.0)
        self.assertEqual(update["after"]["amount"], 150.0)


if __name__ == "__main__":
    unittest.main()
