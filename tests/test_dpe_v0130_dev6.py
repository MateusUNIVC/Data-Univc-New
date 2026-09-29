from __future__ import annotations
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import release_info
from database import Base
from dpe_revenues import DPERevenueRepository
from models import Directorate, DPECostPeriod, DPECostPeriodOffering, DPERevenueCategory, DPERevenueEntry, DPECostOfferingEconomics
from security import AuthorizationContext, DirectorateScope

ROOT=Path(__file__).resolve().parents[1]

def _repo():
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine); db=Session(engine)
    d=Directorate(code='DPE',name='DPE',active=True); db.add(d); db.commit(); db.refresh(d)
    u=AuthorizationContext(user_id='dev6',email='dev6@test.local',full_name='Dev6',role='editor',directorate_id=d.id,directorate_code='DPE',directorate_name='DPE')
    scope=DirectorateScope(user=u,directorate_id=d.id,directorate_code='DPE',directorate_name='DPE',can_write=True,is_home=True)
    p=DPECostPeriod(directorate_id=d.id,period='2026-09',status='REVIEW',notes=None,created_by='test');db.add(p);db.flush()
    o=DPECostPeriodOffering(period_id=p.id,offering_id=1,included=True,offering_snapshot_json={'product':{'name':'Administração'},'offering':{'shift':'Noturno'}},created_by='test');db.add(o);db.commit();db.refresh(p);db.refresh(o)
    return engine,db,p,o,DPERevenueRepository(db,scope)

def test_release_retains_revenue_ledger_schema_46_migration():
    assert release_info.SCHEMA_VERSION >= 46
    sql=(ROOT/'database'/'046_dpe_revenue_ledger_v0130.sql').read_text().lower(); assert 'dpe_revenue_categories' in sql and 'dpe_revenue_entries' in sql and 'e.net_revenue' in sql

def test_course_revenue_is_direct_value_without_economics_mirror():
    engine,db,p,o,repo=_repo()
    try:
        repo.bulk_courses(p.id,[{'period_offering_id':o.id,'amount':'12345.67'}])
        entry=db.scalar(select(DPERevenueEntry).where(DPERevenueEntry.period_offering_id==o.id)); assert Decimal(entry.amount)==Decimal('12345.67')
        eco=db.scalar(select(DPECostOfferingEconomics).where(DPECostOfferingEconomics.period_offering_id==o.id)); assert eco is None
    finally: db.close();engine.dispose()

def test_institutional_revenue_does_not_bind_course():
    engine,db,p,o,repo=_repo()
    try:
        data=repo.central(p.id); cat=next(c for c in data['categories'] if c['code']=='ROOM_RENTAL')
        row=repo.create(p.id,{'category_id':cat['id'],'description':'Aluguel sala','amount':'5000'})
        assert row['period_offering_id'] is None
        refreshed=repo.central(p.id); assert refreshed['summary']['institutional_revenue']==5000.0 and refreshed['summary']['course_revenue']==0.0
    finally: db.close();engine.dispose()

def test_custom_revenue_category_is_supported():
    engine,db,p,o,repo=_repo()
    try:
        row=repo.create_category({'code':'CONVENIOS','name':'Convênios','scope':'INSTITUTIONAL'}); assert row['system'] is False
        assert db.scalar(select(DPERevenueCategory).where(DPERevenueCategory.code=='CONVENIOS')) is not None
    finally: db.close();engine.dispose()

def test_revenue_frontend_has_no_discount_or_paying_student_flow():
    html=(ROOT/'templates'/'dpe.html').read_text().lower(); js=(ROOT/'static/js/dpe_cost_revenues.js').read_text().lower()
    section=html.split('id="section-receita-operacional"',1)[1].split('id="section-central-despesas"',1)[0]
    assert 'outras receitas' in section and 'aluguel de salas' in section
    for legacy in ('bolsas / descontos','outras deduções','alunos pagantes','receita bruta','ticket líquido'):
        assert legacy not in section+js
