from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import Base
from dpe_cost_allocation import DPECostAllocationRepository, DPECostAllocationValidationError
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_revenues import DPERevenueRepository
from models import (
    Course,
    Directorate,
    DPEAllocationPolicy,
    DPEAllocationRule,
    DPECostExpense,
    DPEExpenseCategory,
)
from security import AuthorizationContext, DirectorateScope


class DPEV0121TestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.dpe = Directorate(code="DPE", name="Diretoria de Planejamento Econômico e Oferta", active=True)
        self.dtnh = Directorate(code="DTNH", name="DTNH", active=True)
        self.db.add_all([self.dpe, self.dtnh])
        self.db.commit()
        self.db.refresh(self.dpe)
        user = AuthorizationContext(
            user_id="test-dpe-v0121",
            email="dpe-v0121@test.local",
            full_name="DPE v0.12.1 Test",
            role="editor",
            directorate_id=self.dpe.id,
            directorate_code="DPE",
            directorate_name=self.dpe.name,
        )
        self.scope = DirectorateScope(
            user=user,
            directorate_id=self.dpe.id,
            directorate_code="DPE",
            directorate_name=self.dpe.name,
            can_write=True,
            is_home=True,
        )
        self.catalog = DPECostCatalogRepository(self.db, self.scope)
        self.economics = DPECostEconomicsRepository(self.db, self.scope)
        self.revenues = DPERevenueRepository(self.db, self.scope)
        self.allocation = DPECostAllocationRepository(self.db, self.scope)

        self.rules = {}
        for code, driver, name in [
            ("EQUAL", "EQUAL", "Divisão igual"),
            ("STUDENTS", "STUDENTS", "Por alunos"),
            ("REVENUE", "REVENUE", "Por receita"),
            ("DIRECT", "DIRECT", "Destino direto"),
            ("MANUAL", "MANUAL", "Manual"),
        ]:
            row = DPEAllocationRule(
                directorate_id=self.dpe.id,
                code=code,
                name=name,
                driver_type=driver,
                description=name,
                system_defined=True,
                active=True,
                created_by="test",
            )
            self.db.add(row)
            self.db.flush()
            self.rules[driver] = row
        self.category = DPEExpenseCategory(
            directorate_id=self.dpe.id,
            code="GERAL",
            name="Despesas gerais",
            default_rule_id=self.rules["EQUAL"].id,
            active=True,
            created_by="test",
        )
        self.db.add(self.category)
        self.db.commit()

        self.course_a = self._course("Administração")
        self.course_b = self._course("Farmácia")
        self.course_c = self._course("Direito")
        self._product_and_offering(self.course_a, "ADM")
        self._product_and_offering(self.course_b, "FARM")
        self._product_and_offering(self.course_c, "DIR")
        self.period = self.catalog.create_period({"period": "2026-09", "materialize_offerings": True})
        self.offerings = [row for row in self.period["offerings"] if row["included"]]
        self.assertEqual(len(self.offerings), 3)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _course(self, name: str) -> Course:
        row = Course(
            directorate_id=self.dtnh.id,
            name=name,
            modality="Presencial",
            active=True,
            valid_from="2026-01",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _product_and_offering(self, course: Course, code: str):
        product = self.catalog.create_product({
            "code": code,
            "name": course.name,
            "source_course_id": course.id,
            "valid_from": "2026-01",
        })
        return self.catalog.create_offering({
            "product_id": product["id"],
            "code": f"{code}-NOT",
            "modality": "PRESENCIAL",
            "shift": "Noturno",
            "valid_from": "2026-01",
        })

    def _expense(self, description: str, amount: float, driver: str = "EQUAL") -> DPECostExpense:
        row = DPECostExpense(
            directorate_id=self.dpe.id,
            period_id=self.period["id"],
            description=description,
            amount=Decimal(str(amount)),
            expense_kind="GENERAL",
            expense_scope="DIRECT" if driver == "DIRECT" else "SHARED",
            category_id=self.category.id,
            allocation_rule_id=self.rules[driver].id,
            source_type="MANUAL",
            status="ACTIVE",
            classification_snapshot_json={
                "category": {"id": self.category.id, "name": self.category.name},
                "allocation_rule": {"id": self.rules[driver].id, "name": self.rules[driver].name, "driver_type": driver},
            },
            created_by="test",
            updated_by="test",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_equal_multiple_specific_targets_reconciles(self):
        expense = self._expense("Adobe", 12000, "EQUAL")
        ids = [self.offerings[0]["id"], self.offerings[1]["id"]]
        preview = self.allocation.preview_expense_config(expense.id, {
            "allocation_rule_id": self.rules["EQUAL"].id,
            "targets": [{"period_offering_id": value} for value in ids],
        })
        self.assertTrue(preview["ready"])
        self.assertEqual(preview["allocated_total"], 12000.0)
        self.assertEqual(preview["unallocated_total"], 0.0)
        self.assertEqual(sorted(row["allocated_amount"] for row in preview["results"]), [6000.0, 6000.0])

    def test_students_distribution_uses_official_active_students(self):
        expense = self._expense("Biblioteca", 1000, "STUDENTS")
        ids = [row["id"] for row in self.offerings]
        self.economics.upsert_many(self.period["id"], [
            {"period_offering_id": ids[0], "active_students": 50},
            {"period_offering_id": ids[1], "active_students": 30},
            {"period_offering_id": ids[2], "active_students": 20},
        ])
        preview = self.allocation.preview_expense_config(expense.id, {
            "allocation_rule_id": self.rules["STUDENTS"].id,
            "targets": [],
        })
        self.assertTrue(preview["ready"])
        self.assertEqual([row["allocated_amount"] for row in preview["results"]], [500.0, 300.0, 200.0])

    def test_manual_percentage_reconciles_and_policy_reuses_percentages(self):
        expense = self._expense("Contrato especializado", 10000, "MANUAL")
        targets = [
            {"period_offering_id": self.offerings[0]["id"], "manual_percentage": 50},
            {"period_offering_id": self.offerings[1]["id"], "manual_percentage": 30},
            {"period_offering_id": self.offerings[2]["id"], "manual_percentage": 20},
        ]
        self.allocation.set_expense_config(expense.id, {
            "allocation_rule_id": self.rules["MANUAL"].id,
            "targets": targets,
        })
        policy = self.allocation.create_policy_from_expense(expense.id, {"name": "Contrato 50-30-20", "auto_suggest": True})
        self.assertTrue(policy["applicable"])
        self.assertEqual(policy["scope_type"], "SPECIFIC")
        self.assertEqual(sum(item["manual_percentage"] for item in policy["targets"]), 100.0)
        resolved = self.allocation.resolve_policy_for_expense(expense.id, policy["id"])
        self.assertEqual(sum(item["manual_percentage"] for item in resolved["config"]["targets"]), 100.0)

    def test_policy_created_from_manual_amount_becomes_percentage_for_future_amounts(self):
        expense = self._expense("Serviço recorrente", 10000, "MANUAL")
        self.allocation.set_expense_config(expense.id, {
            "allocation_rule_id": self.rules["MANUAL"].id,
            "targets": [
                {"period_offering_id": self.offerings[0]["id"], "manual_amount": 7000},
                {"period_offering_id": self.offerings[1]["id"], "manual_amount": 3000},
            ],
        })
        policy = self.allocation.create_policy_from_expense(expense.id, {"name": "Serviço 70-30"})
        values = sorted(item["manual_percentage"] for item in policy["targets"])
        self.assertEqual(values, [30.0, 70.0])

    def test_policy_is_automatically_suggested_for_same_description(self):
        expense = self._expense("Energia elétrica", 9000, "EQUAL")
        self.allocation.create_policy_from_expense(expense.id, {"name": "Energia por igual", "auto_suggest": True})
        another = self._expense("  ENERGIA   ELÉTRICA ", 11000, "EQUAL")
        config = self.allocation.expense_config(another.id)
        self.assertIsNotNone(config["suggested_policy"])
        self.assertEqual(config["suggested_policy"]["name"], "Energia por igual")

    def test_policy_missing_specific_offering_in_future_period_is_not_applicable(self):
        expense = self._expense("Software laboratório", 3000, "DIRECT")
        target_id = self.offerings[0]["id"]
        self.allocation.set_expense_config(expense.id, {
            "allocation_rule_id": self.rules["DIRECT"].id,
            "targets": [{"period_offering_id": target_id}],
        })
        policy = self.allocation.create_policy_from_expense(expense.id, {"name": "Software laboratório"})

        # Build a future period with the target offering explicitly excluded after materialization.
        future = self.catalog.create_period({"period": "2026-10", "materialize_offerings": True})
        target_stable_id = next(item["offering_id"] for item in policy["targets"])
        rows = self.allocation._period_offerings(future["id"])
        target_row = next(row for row in rows if row.offering_id == target_stable_id)
        target_row.included = False
        self.db.commit()
        policies = self.allocation.list_policies(period_id=future["id"])
        loaded = next(row for row in policies if row["id"] == policy["id"])
        self.assertFalse(loaded["applicable"])
        self.assertEqual(len(loaded["missing_targets"]), 1)

    def test_month_preview_reconciles_and_combines_revenue_result_margin(self):
        expense = self._expense("Licenças", 9000, "EQUAL")
        ids = [row["id"] for row in self.offerings]
        self.revenues.bulk_courses(self.period["id"], [
            {"period_offering_id": ids[0], "amount": 20000},
            {"period_offering_id": ids[1], "amount": 15000},
            {"period_offering_id": ids[2], "amount": 10000},
        ])
        self.economics.upsert_many(self.period["id"], [
            {"period_offering_id": ids[0], "active_students": 10},
            {"period_offering_id": ids[1], "active_students": 10},
            {"period_offering_id": ids[2], "active_students": 10},
        ])
        preview = self.allocation.period_preview(self.period["id"])
        self.assertTrue(preview["summary"]["reconciled"])
        self.assertEqual(preview["summary"]["expense_total"], 9000.0)
        self.assertEqual(preview["summary"]["allocated_total"], 9000.0)
        self.assertEqual({row["preview_cost"] for row in preview["rows"]}, {3000.0})
        first = next(row for row in preview["rows"] if row["revenue"] == 20000.0)
        self.assertEqual(first["result"], 17000.0)
        self.assertEqual(first["margin"], 85.0)

    def test_policy_soft_deactivation_preserves_record(self):
        expense = self._expense("Telefonia", 5000, "EQUAL")
        policy = self.allocation.create_policy_from_expense(expense.id, {"name": "Telefonia padrão"})
        updated = self.allocation.update_policy(policy["id"], {"active": False})
        self.assertFalse(updated["active"])
        self.assertEqual(len(self.allocation.list_policies(active_only=True)), 0)
        stored = self.db.scalar(select(DPEAllocationPolicy).where(DPEAllocationPolicy.id == policy["id"]))
        self.assertIsNotNone(stored)


if __name__ == "__main__":
    unittest.main()
