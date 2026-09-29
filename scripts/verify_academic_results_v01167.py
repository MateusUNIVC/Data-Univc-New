#!/usr/bin/env python3
from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import AcademicResult, AcademicStudent, Course, Directorate, Discipline
from repository import DatabaseRepository
from security import AuthorizationContext

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, expire_on_commit=False)
db = Session()
try:
    directorate = Directorate(code="DTNH", name="DTNH", active=True)
    db.add(directorate); db.flush()
    course = Course(directorate_id=directorate.id, name="Administração", modality="Presencial", active=True, valid_from="2020-01")
    db.add(course); db.flush()
    d1 = Discipline(course_id=course.id, name="Gestão I", active=True, valid_from="2020-01")
    d2 = Discipline(course_id=course.id, name="Gestão II", active=True, valid_from="2020-01")
    db.add_all([d1, d2]); db.flush()
    ctx = AuthorizationContext(user_id=str(uuid.uuid4()), email="verify@univc.edu.br", full_name="Verify", role="editor", directorate_id=directorate.id, directorate_code="DTNH", directorate_name="DTNH")
    repo = DatabaseRepository(db, ctx)

    a = AcademicStudent(directorate_id=directorate.id, registration="A", name="Aluno A", course_id=course.id, active=True)
    b = AcademicStudent(directorate_id=directorate.id, registration="B", name="Aluno B", course_id=course.id, active=True)
    db.add_all([a, b]); db.flush()
    db.add_all([
        AcademicResult(directorate_id=directorate.id, period="2026-SEM1", course_id=course.id, discipline_id=d1.id, student_id=a.id, class_group="ADM1", final_average=8, official_status="Aprovado", approved=True, source="verify"),
        AcademicResult(directorate_id=directorate.id, period="2026-SEM1", course_id=course.id, discipline_id=d2.id, student_id=a.id, class_group="ADM1", final_average=None, official_status="Cursando", approved=None, source="verify"),
        AcademicResult(directorate_id=directorate.id, period="2026-SEM1", course_id=course.id, discipline_id=d1.id, student_id=b.id, class_group="ADM1", final_average=4, official_status="Reprovado", approved=False, failure_reason="nota", source="verify"),
    ])
    db.commit()
    summary = repo.academic_result_student_summary({"periodo": "2026-SEM1"})
    assert summary["alunos_distintos"] == 2
    assert summary["alunos_aprovados"] == 1
    assert summary["alunos_com_reprovacao"] == 1
    assert summary["alunos_sem_classificacao"] == 0
finally:
    db.close(); engine.dispose()

print("OK v0.11.6.7: pendência parcial não cria terceiro status principal do aluno.")
