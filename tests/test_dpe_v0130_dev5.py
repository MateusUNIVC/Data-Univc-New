from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import release_info
from database import Base
from dpe_cost_catalog import DPECostCatalogRepository
from dpe_course_context import default_context_code, normalize_modality
from models import Course, Directorate
from security import AuthorizationContext, DirectorateScope
from schema_version import ensure_local_schema_version

ROOT = Path(__file__).resolve().parents[1]


def _repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    dpe = Directorate(code="DPE", name="DPE", active=True)
    dtnh = Directorate(code="DTNH", name="DTNH", active=True)
    dcs = Directorate(code="DCS", name="DCS", active=True)
    db.add_all([dpe, dtnh, dcs])
    db.commit()
    db.refresh(dpe)
    db.refresh(dtnh)
    db.refresh(dcs)
    user = AuthorizationContext(
        user_id="dev5-test",
        email="dev5@test.local",
        full_name="Dev5 Test",
        role="editor",
        directorate_id=dpe.id,
        directorate_code="DPE",
        directorate_name="DPE",
    )
    scope = DirectorateScope(
        user=user,
        directorate_id=dpe.id,
        directorate_code="DPE",
        directorate_name="DPE",
        can_write=True,
        is_home=True,
    )
    return engine, db, dtnh, dcs, DPECostCatalogRepository(db, scope)


def _course(db: Session, directorate: Directorate, name: str, modality: str) -> Course:
    row = Course(
        directorate_id=directorate.id,
        name=name,
        modality=modality,
        active=True,
        valid_from="2026-01",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_release_retains_course_context_schema_45_migration():
    assert release_info.SCHEMA_VERSION >= 45
    sql = (ROOT / "database" / "045_dpe_course_contexts_v0130.sql").read_text(encoding="utf-8").lower()
    assert "alter column modality set default 'nao_informada'" in sql
    assert "insert into public.dpe_academic_offerings" in sql
    assert "upper(p.code) || '-base'" in sql
    assert sql.index("insert into public.dpe_academic_offerings") < sql.index("values (1, 45, '045_dpe_course_contexts_v0130.sql'")
    assert "values (1, 45, '045_dpe_course_contexts_v0130.sql'" in sql


def test_modality_normalization_does_not_enforce_presential():
    assert normalize_modality("Presencial") == "PRESENCIAL"
    assert normalize_modality("EAD") == "EAD"
    assert normalize_modality("A distância") == "EAD"
    assert normalize_modality("Semipresencial") == "SEMIPRESENCIAL"
    assert normalize_modality("Híbrido") == "HIBRIDO"
    assert normalize_modality(None) == "NAO_INFORMADA"


def test_course_is_primary_and_ead_gets_automatic_base_context():
    engine, db, dtnh, _dcs, repo = _repo()
    try:
        course = _course(db, dtnh, "ADS", "EAD")
        product = repo.create_product({"code": "ADS", "source_course_id": course.id})
        contexts = repo.list_offerings(product_id=product["id"])
        assert product["source_modality"] == "EAD"
        assert len(contexts) == 1
        base = contexts[0]
        assert base["code"] == default_context_code("ADS")
        assert base["is_default_context"] is True
        assert base["context_kind"] == "BASE"
        assert base["modality"] == "EAD"
        assert base["label"] == "ADS"

        period = repo.create_period({"period": "2026-09", "materialize_offerings": True})
        included = [row for row in period["offerings"] if row["included"]]
        assert len(included) == 1
        assert included[0]["offering"]["is_default_context"] is True
        assert included[0]["offering"]["modality"] == "EAD"
    finally:
        db.close()
        engine.dispose()


def test_additional_contexts_replace_base_for_period_without_double_counting():
    engine, db, dtnh, _dcs, repo = _repo()
    try:
        course = _course(db, dtnh, "Administração", "Presencial")
        product = repo.create_product({"code": "ADM", "source_course_id": course.id})
        base = next(row for row in repo.list_offerings(product_id=product["id"]) if row["is_default_context"])
        morning = repo.create_offering({
            "product_id": product["id"],
            "code": "ADM-MAT",
            "shift": "Matutino",
            "valid_from": "2026-01",
        })
        night = repo.create_offering({
            "product_id": product["id"],
            "code": "ADM-NOT",
            "shift": "Noturno",
            "valid_from": "2026-01",
        })
        period = repo.create_period({"period": "2026-09", "materialize_offerings": True})
        included = [row for row in period["offerings"] if row["included"]]
        assert len(included) == 2
        ids = {row["offering"]["id"] for row in included}
        assert ids == {morning["id"], night["id"]}
        assert base["id"] not in ids
        assert all(row["offering"]["context_kind"] == "CUSTOM" for row in included)
    finally:
        db.close()
        engine.dispose()


def test_frontend_uses_course_context_language_and_no_presential_restriction():
    html = (ROOT / "templates" / "dpe.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "dpe_cost_engine.js").read_text(encoding="utf-8")
    router = (ROOT / "dpe_router.py").read_text(encoding="utf-8")
    assert "Cursos e contextos" in html
    assert "Contextos opcionais" in html
    assert "Novo contexto do curso" in js
    assert "Mesma modalidade do curso" in js
    assert "operational_scope\": \"ALL_MODALITIES\"" in router
    lowered = (html + js + router).lower()
    assert "somente cursos presenciais" not in lowered
    assert "curso presencial oficial" not in lowered
    assert "oferta presencial" not in lowered


def test_local_schema_upgrade_backfills_base_context_for_existing_course(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'course-context.sqlite'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE courses (id INTEGER PRIMARY KEY, modality TEXT)"))
        conn.execute(text("INSERT INTO courses(id,modality) VALUES (7,'EAD')"))
        conn.execute(text(
            "CREATE TABLE dpe_academic_products ("
            "id INTEGER PRIMARY KEY,directorate_id INTEGER,code TEXT,source_course_id INTEGER,"
            "active BOOLEAN,valid_from TEXT,valid_to TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO dpe_academic_products VALUES (11,3,'ADS',7,1,'2026-01',NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE dpe_academic_offerings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,directorate_id INTEGER,product_id INTEGER,code TEXT,"
            "modality TEXT,shift TEXT,campus TEXT,unit_name TEXT,pole_name TEXT,external_key TEXT,"
            "active BOOLEAN,valid_from TEXT,valid_to TEXT,notes TEXT,created_by TEXT)"
        ))
        ensure_local_schema_version(conn)
        row = conn.execute(text(
            "SELECT product_id,code,modality,shift,created_by FROM dpe_academic_offerings"
        )).one()
        assert row == (11, "ADS-BASE", "EAD", None, "migration:045-local")
        ledger = conn.execute(text(
            "SELECT version,migration_name FROM data_univc_schema_version WHERE id=1"
        )).one()
        assert ledger == (release_info.SCHEMA_VERSION, release_info.SCHEMA_MIGRATION)


def test_renaming_course_code_renames_automatic_base_context():
    engine, db, dtnh, _dcs, repo = _repo()
    try:
        course = _course(db, dtnh, "Ciência da Computação", "Híbrido")
        product = repo.create_product({"code": "CC", "source_course_id": course.id})
        updated = repo.update_product(product["id"], {"code": "COMP", "source_course_id": course.id})
        assert updated["code"] == "COMP"
        contexts = repo.list_offerings(product_id=product["id"])
        bases = [row for row in contexts if row["is_default_context"]]
        assert len(bases) == 1
        assert bases[0]["code"] == "COMP-BASE"
        assert bases[0]["modality"] == "HIBRIDO"
    finally:
        db.close()
        engine.dispose()
