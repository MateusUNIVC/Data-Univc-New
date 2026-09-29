from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("AUTO_CREATE_DB", "true")
os.environ.setdefault("REQUIRE_SCHEMA_VERSION", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///./univc_local_all.db")

if os.environ.get("ENVIRONMENT", "").strip().lower() in {"prod", "production"}:
    raise SystemExit("Bootstrap local bloqueado em production.")
if not os.environ.get("DATABASE_URL", "").startswith("sqlite"):
    raise SystemExit("Os launchers locais aceitam somente SQLite para não tocar produção/Supabase.")

from sqlalchemy import select
from database import Base, SessionLocal, engine
from schema_version import ensure_local_schema_version
from models import Course, Directorate, DPEAllocationRule, IndicatorDefinition, IndicatorSchedule
from academic_catalog import COURSES_BY_DIRECTORATE
from schemas import IMPLEMENTED_KPIS, KPI_META

DIRECTORATES = {
    "DTNH": "Diretoria de Tecnologia, Negócios e Humanidades",
    "DCS": "Diretoria de Ciências da Saúde",
    "DADM": "Diretoria Administrativa",
    "DPE": "Diretoria de Planejamento Econômico e Oferta",
    "DM": "Diretoria de Mestrado",
}

DPE_RULES = (
    ("DIRECT", "Direto para oferta", "DIRECT", "Despesa diretamente atribuída a uma oferta."),
    ("TEACHER_HOURS", "Carga horária docente", "TEACHER_HOURS", "Folha docente pela carga horária do professor."),
    ("OFFERING_HOURS", "Carga horária da oferta", "OFFERING_HOURS", "Custos compartilhados pela carga horária das ofertas."),
    ("STUDENTS", "Quantidade de alunos", "STUDENTS", "Custos compartilhados pela quantidade de alunos ativos."),
    ("REVENUE", "Receita da oferta", "REVENUE", "Custos compartilhados pela receita líquida."),
    ("EQUAL", "Divisão igualitária", "EQUAL", "Divisão igual entre as ofertas elegíveis."),
    ("MANUAL", "Rateio manual", "MANUAL", "Percentuais ou valores definidos manualmente."),
)

Base.metadata.create_all(bind=engine)
with engine.begin() as conn:
    ensure_local_schema_version(conn)

with SessionLocal() as db:
    for code, name in DIRECTORATES.items():
        row = db.scalar(select(Directorate).where(Directorate.code == code))
        if row is None:
            row = Directorate(code=code, name=name, active=True)
            db.add(row)
        else:
            row.name = name
            row.active = True
    db.commit()

    directors = {row.code: row for row in db.scalars(select(Directorate)).all()}

    for directorate_code, courses in COURSES_BY_DIRECTORATE.items():
        directorate = directors.get(directorate_code)
        if not directorate:
            continue
        for course_name in courses:
            exists = db.scalar(
                select(Course).where(
                    Course.directorate_id == directorate.id,
                    Course.name == course_name,
                )
            )
            if not exists:
                db.add(
                    Course(
                        directorate_id=directorate.id,
                        name=course_name,
                        modality="Presencial",
                        active=True,
                        valid_from="2026-01",
                    )
                )

    for directorate_code, codes in IMPLEMENTED_KPIS.items():
        for code in codes:
            meta = KPI_META.get(code, {})
            row = db.get(IndicatorDefinition, code)
            values = {
                "directorate_code": directorate_code,
                "name": str(meta.get("short_name") or code),
                "periodicity": str(meta.get("periodicity") or ""),
                "formula_text": str(meta.get("formula") or ""),
                "source_text": str(meta.get("source") or ""),
                "active": True,
            }
            if row is None:
                row = IndicatorDefinition(code=code, **values)
                db.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)

            schedule = db.scalar(select(IndicatorSchedule).where(IndicatorSchedule.indicator_code == code))
            if schedule is None:
                periodicity = str(meta.get("periodicity") or "").casefold()
                grain = "semester" if "semestr" in periodicity else "month"
                db.add(
                    IndicatorSchedule(
                        indicator_code=code,
                        reference_grain=grain,
                        due_business_day=5,
                        collection_window_start_business_day=1,
                        active=True,
                        notes="Estrutura local criada pelo launcher de homologação.",
                    )
                )

    dpe = directors.get("DPE")
    if dpe:
        for code, name, driver, description in DPE_RULES:
            exists = db.scalar(
                select(DPEAllocationRule).where(
                    DPEAllocationRule.directorate_id == dpe.id,
                    DPEAllocationRule.code == code,
                )
            )
            if not exists:
                db.add(
                    DPEAllocationRule(
                        directorate_id=dpe.id,
                        code=code,
                        name=name,
                        driver_type=driver,
                        description=description,
                        parameters_json={},
                        system_defined=True,
                        active=True,
                        created_by="launcher.local@univc.invalid",
                    )
                )

    db.commit()

print("Base local compartilhada pronta: DTNH, DCS, DADM, DPE, DM e suporte à Reitoria.")
