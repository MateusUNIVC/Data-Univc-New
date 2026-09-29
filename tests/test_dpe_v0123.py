from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import Base
from dpe_cost_allocation import DPECostAllocationRepository
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_cost_economics import DPECostEconomicsRepository
from dpe_revenues import DPERevenueRepository
from dpe_cost_excel import parse_expense_workbook
from dpe_cost_expenses import DPECostExpenseRepository, DPECostExpenseValidationError
from dpe_cost_productivity import DPECostProductivityRepository
from dpe_cost_teaching import DPECostTeachingRepository
from models import (
    Course, Directorate, DPEAllocationRule, DPECostExpense, DPECostExpenseAllocationTarget,
    DPEExpenseCategory, DPERecurringExpenseTemplate,
)
from security import AuthorizationContext, DirectorateScope


class DPEV0123TestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.dpe = Directorate(code="DPE", name="DPE", active=True)
        self.dtnh = Directorate(code="DTNH", name="DTNH", active=True)
        self.db.add_all([self.dpe, self.dtnh])
        self.db.commit(); self.db.refresh(self.dpe)
        user = AuthorizationContext(user_id="v0123", email="v0123@test.local", full_name="V0123", role="editor", directorate_id=self.dpe.id, directorate_code="DPE", directorate_name="DPE")
        self.scope = DirectorateScope(user=user, directorate_id=self.dpe.id, directorate_code="DPE", directorate_name="DPE", can_write=True, is_home=True)
        self.catalog = DPECostCatalogRepository(self.db, self.scope)
        self.expenses = DPECostExpenseRepository(self.db, self.scope)
        self.economics = DPECostEconomicsRepository(self.db, self.scope)
        self.revenues = DPERevenueRepository(self.db, self.scope)
        self.teaching = DPECostTeachingRepository(self.db, self.scope)
        self.allocation = DPECostAllocationRepository(self.db, self.scope)
        self.productivity = DPECostProductivityRepository(self.db, self.scope)
        self.rule = DPEAllocationRule(directorate_id=self.dpe.id, code="EQUAL", name="Igual", driver_type="EQUAL", description="Igual", system_defined=True, active=True, created_by="test")
        self.db.add(self.rule); self.db.flush()
        self.cat = DPEExpenseCategory(directorate_id=self.dpe.id, code="GERAL", name="Despesas gerais", default_rule_id=self.rule.id, active=True, created_by="test")
        self.cat2 = DPEExpenseCategory(directorate_id=self.dpe.id, code="SOFT", name="Software", default_rule_id=self.rule.id, active=True, created_by="test")
        self.db.add_all([self.cat, self.cat2]); self.db.commit()
        self.course = Course(directorate_id=self.dtnh.id, name="Administracao", modality="Presencial", active=True, valid_from="2026-01")
        self.db.add(self.course); self.db.commit(); self.db.refresh(self.course)
        prod = self.catalog.create_product({"code":"ADM","name":"Administracao","source_course_id":self.course.id,"valid_from":"2026-01"})
        self.catalog.create_offering({"product_id":prod["id"],"code":"ADM-NOT","modality":"PRESENCIAL","shift":"Noturno","valid_from":"2026-01"})
        self.aug = self.catalog.create_period({"period":"2026-08","materialize_offerings":True})
        self.sep = self.catalog.create_period({"period":"2026-09","materialize_offerings":True})

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _xlsx(self, rows):
        wb=Workbook(); ws=wb.active; ws.title="Despesas"
        ws.append(["Descricao","Valor","Data","Categoria","Setor","Tipo","Fornecedor / beneficiario","Documento","Referencia","Chave externa","Observacoes"])
        for row in rows: ws.append(row)
        handle=tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False); handle.close(); wb.save(handle.name)
        return Path(handle.name)

    def test_excel_preview_is_non_destructive_then_commit(self):
        path=self._xlsx([["Adobe",12000,"2026-09-10","GERAL","","GENERAL","Fornecedor","NF1","Contrato","ADOBE-09",""]])
        try: parsed=parse_expense_workbook(path)
        finally: path.unlink(missing_ok=True)
        preview=self.expenses.prepare_excel_import(self.sep["id"],"despesas.xlsx",parsed)
        self.assertTrue(preview["can_commit"])
        self.assertEqual(self.db.scalar(select(DPECostExpense).where(DPECostExpense.period_id==self.sep["id"])), None)
        result=self.expenses.commit_import_batch(preview["batch"]["id"])
        self.assertEqual(result["created"],1)
        row=self.db.scalar(select(DPECostExpense).where(DPECostExpense.period_id==self.sep["id"]))
        self.assertEqual(row.description,"Adobe")
        self.assertEqual(row.source_type,"EXCEL")

    def test_excel_duplicate_blocks_commit(self):
        self.expenses.create_expense({"period_id":self.sep["id"],"description":"Adobe","amount":12000,"expense_date":"2026-09-10","category_id":self.cat.id,"source_type":"MANUAL","document_number":"NF1"})
        path=self._xlsx([["Adobe",12000,"2026-09-10","GERAL","","GENERAL","","NF1","","",""]])
        try: parsed=parse_expense_workbook(path)
        finally: path.unlink(missing_ok=True)
        preview=self.expenses.prepare_excel_import(self.sep["id"],"duplicado.xlsx",parsed)
        self.assertFalse(preview["can_commit"])
        self.assertEqual(preview["batch"]["status"],"FAILED")
        with self.assertRaises(DPECostExpenseValidationError): self.expenses.commit_import_batch(preview["batch"]["id"])

    def test_bulk_classification_updates_selected_expenses(self):
        a=self.expenses.create_expense({"period_id":self.sep["id"],"description":"A","amount":100,"category_id":self.cat.id})
        b=self.expenses.create_expense({"period_id":self.sep["id"],"description":"B","amount":200,"category_id":self.cat.id})
        out=self.expenses.bulk_classify(self.sep["id"],{"expense_ids":[a["id"],b["id"]],"category_id":self.cat2.id})
        self.assertEqual(out["updated_count"],2)
        rows=self.db.scalars(select(DPECostExpense).where(DPECostExpense.id.in_([a["id"],b["id"]]))).all()
        self.assertTrue(all(row.category_id==self.cat2.id for row in rows))

    def test_recurring_generation_is_idempotent(self):
        template=self.productivity.save_recurring_template({"name":"Energia","description":"Energia eletrica","amount":43000,"category_id":self.cat.id,"day_of_month":10})
        first=self.productivity.generate_recurring(self.sep["id"],[template["id"]])
        second=self.productivity.generate_recurring(self.sep["id"],[template["id"]])
        self.assertEqual(first["created_count"],1)
        self.assertEqual(second["created_count"],0)
        self.assertEqual(self.db.scalar(select(DPECostExpense).where(DPECostExpense.period_id==self.sep["id"])).external_key, f"RECUR-{template['id']}-2026-09")

    def test_copy_revenues_uses_stable_offering(self):
        source_off=self.aug["offerings"][0]["id"]; target_off=self.sep["offerings"][0]["id"]
        self.revenues.bulk_courses(self.aug["id"],[{"period_offering_id":source_off,"amount":90000}]); self.economics.upsert(self.aug["id"],source_off,{"active_students":100})
        preview=self.productivity.copy_preview(self.aug["id"],self.sep["id"])
        self.assertEqual(preview["revenues"]["copyable"],1)
        copied=self.productivity.copy_revenues(self.aug["id"],self.sep["id"])
        self.assertEqual(copied["copied"],1)
        target=self.economics.central_payload(period_id=self.sep["id"])["rows"][0]
        self.assertEqual(target["active_students"],100)
        self.assertEqual(target["revenue"],90000.0)

    def test_copy_teaching_roster_maps_offering(self):
        teacher=self.teaching.create_teacher({"display_name":"Maria Silva"})
        subject=self.teaching.create_subject({"code":"ADM101","name":"Gestao"})
        self.teaching.create_activity({"period_id":self.aug["id"],"teacher_id":teacher["id"],"subject_id":subject["id"],"workload_hours":40,"offering_allocations":[{"period_offering_id":self.aug["offerings"][0]["id"],"allocated_hours":40}]})
        out=self.productivity.copy_teaching(self.aug["id"],self.sep["id"])
        self.assertEqual(out["copied"],1)
        activities=self.teaching.list_activities(period_id=self.sep["id"])
        self.assertEqual(len(activities),1)
        self.assertEqual(activities[0]["allocations"][0]["period_offering_id"],self.sep["offerings"][0]["id"])

    def test_bulk_policy_application_uses_saved_suggestion(self):
        expense=self.expenses.create_expense({"period_id":self.sep["id"],"description":"Energia","amount":1000,"category_id":self.cat.id})
        self.allocation.set_expense_config(expense["id"],{"allocation_rule_id":self.rule.id,"targets":[]})
        policy=self.allocation.create_policy_from_expense(expense["id"],{"name":"Energia padrao","auto_suggest":True})
        second=self.expenses.create_expense({"period_id":self.sep["id"],"description":"Energia","amount":2000,"category_id":self.cat.id})
        preview=self.allocation.bulk_policy_preview(self.sep["id"],[second["id"]])
        self.assertEqual(preview["ready_count"],1)
        result=self.allocation.bulk_apply_suggested_policies(self.sep["id"],[second["id"]])
        self.assertEqual(result["applied_count"],1)
        config=self.allocation.expense_config(second["id"])
        self.assertEqual(config["rule"]["id"],policy["rule"]["id"])


if __name__ == "__main__": unittest.main()
