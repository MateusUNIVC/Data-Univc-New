from __future__ import annotations

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import Base
from dpe_cost_catalog import DPECostCatalogRepository, DPECostCatalogValidationError
from dpe_cost_economics import DPECostEconomicsRepository, DPECostEconomicsValidationError
from dpe_revenues import DPERevenueRepository
from models import (
    Course, Directorate, DPEAcademicOffering, DPEAcademicProduct,
    DPECostOfferingEconomics, DPECostPeriod, DPECostPeriodOffering,
)
from security import AuthorizationContext, DirectorateScope


class DPEV0120TestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.dpe = Directorate(code="DPE", name="Diretoria de Planejamento Econômico e Oferta", active=True)
        self.dtnh = Directorate(code="DTNH", name="DTNH", active=True)
        self.dcs = Directorate(code="DCS", name="DCS", active=True)
        self.db.add_all([self.dpe, self.dtnh, self.dcs])
        self.db.commit()
        self.db.refresh(self.dpe)
        user = AuthorizationContext(
            user_id="test-dpe",
            email="dpe@test.local",
            full_name="DPE Test",
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

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def course(self, name: str, *, modality: str = "Presencial", active: bool = True, directorate=None) -> Course:
        row = Course(
            directorate_id=(directorate or self.dtnh).id,
            name=name,
            modality=modality,
            active=active,
            valid_from="2026-01",
            valid_to=None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def product_and_offering(self, course: Course, code: str):
        product = self.catalog.create_product({
            "code": code,
            "name": "Nome paralelo que não deve prevalecer",
            "source_course_id": course.id,
            "academic_level": "OTHER",
            "valid_from": "2025-01",
        })
        offering = self.catalog.create_offering({
            "product_id": product["id"],
            "code": f"{code}-NOT",
            "modality": "PRESENCIAL",
            "shift": "Noturno",
            "valid_from": "2026-01",
        })
        return product, offering

    def test_new_operational_product_accepts_any_official_course_modality(self):
        ead = self.course("ADS EAD", modality="EAD")
        product = self.catalog.create_product({
            "code": "ADS-EAD",
            "name": "Nome paralelo",
            "source_course_id": ead.id,
            "valid_from": "2026-01",
        })
        self.assertEqual(product["name"], "ADS EAD")
        self.assertEqual(product["source_modality"], "EAD")
        contexts = self.catalog.list_offerings(product_id=product["id"])
        self.assertEqual(len(contexts), 1)
        self.assertTrue(contexts[0]["is_default_context"])
        self.assertEqual(contexts[0]["modality"], "EAD")
        self.assertEqual(contexts[0]["label"], "ADS EAD")

        with self.assertRaises(DPECostCatalogValidationError):
            self.catalog.create_product({
                "code": "PARALELO",
                "name": "Catálogo paralelo",
                "valid_from": "2026-01",
            })

    def test_course_identity_is_official_and_additional_context_may_use_another_modality(self):
        official = self.course("Direito", modality="Presencial")
        product = self.catalog.create_product({
            "code": "DIR",
            "source_course_id": official.id,
        })
        self.assertEqual(product["name"], "Direito")
        self.assertEqual(product["academic_level"], "GRADUATION")
        context = self.catalog.create_offering({
            "product_id": product["id"],
            "code": "DIR-EAD",
            "modality": "EAD",
            "valid_from": "2026-01",
        })
        self.assertEqual(context["modality"], "EAD")
        self.assertFalse(context["is_default_context"])
        self.assertIn("EAD", context["label"])

    def test_new_period_materializes_active_official_courses_and_contexts_without_double_count(self):
        direito = self.course("Direito")
        product = self.catalog.create_product({"code": "DIR", "source_course_id": direito.id})
        custom = self.catalog.create_offering({
            "product_id": product["id"],
            "code": "DIR-NOT",
            "shift": "Noturno",
            "valid_from": "2026-01",
        })

        inactive_course = self.course("Curso inativo", active=False)
        # Legacy rows may still exist in the database; they must not enter a new period.
        from models import DPEAcademicProduct, DPEAcademicOffering
        legacy_product = DPEAcademicProduct(
            directorate_id=self.dpe.id,
            code="LEGACY",
            name="Curso inativo",
            academic_level="GRADUATION",
            source_course_id=inactive_course.id,
            active=True,
            valid_from="2026-01",
            created_by="test",
        )
        self.db.add(legacy_product)
        self.db.flush()
        self.db.add(DPEAcademicOffering(
            directorate_id=self.dpe.id,
            product_id=legacy_product.id,
            code="LEGACY-NOT",
            modality="PRESENCIAL",
            shift="Noturno",
            active=True,
            valid_from="2026-01",
            created_by="test",
        ))
        self.db.commit()

        period = self.catalog.create_period({"period": "2026-09", "materialize_offerings": True})
        included = [item for item in period["offerings"] if item["included"]]
        self.assertEqual(len(included), 1)
        self.assertEqual(included[0]["product"]["name"], "Direito")
        self.assertEqual(included[0]["offering"]["id"], custom["id"])
        self.assertFalse(included[0]["offering"]["is_default_context"])

    def test_existing_historical_snapshot_is_not_rewritten_by_current_context_rules(self):
        legacy_product = DPEAcademicProduct(
            directorate_id=self.dpe.id, code="HIST-EAD", name="Historico EAD",
            academic_level="GRADUATION", source_course_id=None, active=True,
            valid_from="2025-01", created_by="legacy",
        )
        self.db.add(legacy_product)
        self.db.flush()
        legacy_offering = DPEAcademicOffering(
            directorate_id=self.dpe.id, product_id=legacy_product.id, code="HIST-EAD-01",
            modality="EAD", shift=None, active=True, valid_from="2025-01", created_by="legacy",
        )
        self.db.add(legacy_offering)
        self.db.flush()
        period = DPECostPeriod(
            directorate_id=self.dpe.id, period="2025-12", status="CLOSED",
            opened_by="legacy", created_by="legacy", closed_by="legacy",
        )
        self.db.add(period)
        self.db.flush()
        snapshot = {
            "snapshot_version": 1,
            "product": {"id": legacy_product.id, "code": legacy_product.code, "name": legacy_product.name},
            "offering": {"id": legacy_offering.id, "code": legacy_offering.code, "modality": "EAD"},
        }
        self.db.add(DPECostPeriodOffering(
            period_id=period.id, offering_id=legacy_offering.id,
            offering_snapshot_json=snapshot, included=True, created_by="legacy",
        ))
        self.db.commit()

        historical = self.catalog.get_period(period.id)
        self.assertEqual(historical["status"], "CLOSED")
        self.assertEqual(len(historical["offerings"]), 1)
        self.assertEqual(historical["offerings"][0]["offering"]["modality"], "EAD")
        self.assertTrue(historical["offerings"][0]["included"])

    def test_revenue_ledger_and_student_economics_are_separate_and_atomic(self):
        direito = self.course("Direito")
        farmacia = self.course("Farmácia", directorate=self.dcs)
        self.product_and_offering(direito, "DIR")
        self.product_and_offering(farmacia, "FARM")
        period = self.catalog.create_period({"period": "2026-09", "materialize_offerings": True})
        ids = [item["id"] for item in period["offerings"] if item["included"]]
        self.assertEqual(len(ids), 2)

        revenue_result = self.revenues.bulk_courses(period["id"], [
            {"period_offering_id": ids[0], "amount": 85000},
            {"period_offering_id": ids[1], "amount": 85000},
        ])
        self.assertEqual(revenue_result["updated_count"], 2)
        economics_result = self.economics.upsert_many(period["id"], [
            {"period_offering_id": ids[0], "active_students": 100},
            {"period_offering_id": ids[1], "active_students": 80},
        ])
        self.assertEqual(economics_result["updated_count"], 2)
        payload = self.economics.central_payload(period_id=period["id"])
        revenues = sorted(row["revenue"] for row in payload["rows"])
        students = sorted(row["active_students"] for row in payload["rows"])
        self.assertEqual(revenues, [85000.0, 85000.0])
        self.assertEqual(students, [80, 100])

        before = {
            row.period_offering_id: row.active_students
            for row in self.db.scalars(select(DPECostOfferingEconomics)).all()
        }
        with self.assertRaises(DPECostEconomicsValidationError):
            self.economics.upsert_many(period["id"], [
                {"period_offering_id": ids[0], "active_students": 120},
                {"period_offering_id": ids[1], "active_students": 10, "gross_revenue": 1000},
            ])
        after = {
            row.period_offering_id: row.active_students
            for row in self.db.scalars(select(DPECostOfferingEconomics)).all()
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
