from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from dpe_audit import add_dpe_audit
from dpe_course_context import snapshot_context_label
from models import DPECostPeriod, DPECostPeriodOffering, DPERevenueCategory, DPERevenueEntry
from security import DirectorateScope

CENT=Decimal('0.01')
EDITABLE=('DRAFT','REVIEW')
DEFAULT_CATEGORIES=(
 ('COURSE_REVENUE','Receita de curso','COURSE',True),
 ('ROOM_RENTAL','Aluguel de salas','INSTITUTIONAL',True),
 ('SPORTS_RENTAL','Aluguel de quadras','INSTITUTIONAL',True),
 ('STRUCTURE_USE','Utilização de estrutura','BOTH',True),
 ('BRANCH_USE','Utilização de filial','BOTH',True),
 ('SERVICES','Serviços','BOTH',True),
 ('EVENTS','Eventos','BOTH',True),
 ('OTHER','Outras receitas','BOTH',True),
)

class DPERevenueValidationError(ValueError):
    def __init__(self,message:str,fields:dict[str,str]|None=None):
        super().__init__(message); self.field_errors=fields or {}

def _money(v:Any, field='amount')->Decimal:
    try:
        if isinstance(v,str):
            x=v.strip()
            if ',' in x:x=x.replace('.','').replace(',','.')
            v=x
        out=Decimal(str(v)).quantize(CENT,rounding=ROUND_HALF_UP)
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise DPERevenueValidationError('Valor inválido.',{field:'Informe um valor válido.'}) from exc
    if out<0: raise DPERevenueValidationError('Valor inválido.',{field:'O valor não pode ser negativo.'})
    return out

def _txt(v,maxlen=255): return str(v or '').strip()[:maxlen]

def _iso(v): return v.isoformat() if v is not None and hasattr(v,'isoformat') else None

class DPERevenueRepository:
    def __init__(self,db:Session,scope:DirectorateScope):
        if scope.directorate_code!='DPE': raise PermissionError('Receitas pertencem exclusivamente à DPE.')
        self.db=db; self.scope=scope
    @property
    def directorate_id(self): return self.scope.directorate_id
    @property
    def actor(self): return self.scope.user.email or self.scope.user.full_name or self.scope.user.user_id

    def _period(self,pid:int,editable=False):
        p=self.db.scalar(select(DPECostPeriod).where(DPECostPeriod.id==int(pid),DPECostPeriod.directorate_id==self.directorate_id))
        if not p: raise LookupError('Competência não encontrada.')
        if editable and p.status not in EDITABLE: raise DPERevenueValidationError('A competência está protegida e não aceita alterações de receita.')
        return p
    def ensure_defaults(self):
        existing={x.code for x in self.db.scalars(select(DPERevenueCategory).where(DPERevenueCategory.directorate_id==self.directorate_id)).all()}
        for code,name,scope,system in DEFAULT_CATEGORIES:
            if code not in existing:self.db.add(DPERevenueCategory(directorate_id=self.directorate_id,code=code,name=name,scope=scope,active=True,system=system,created_by=self.actor))
        self.db.flush()
    def _category(self,cid:int):
        c=self.db.scalar(select(DPERevenueCategory).where(DPERevenueCategory.id==int(cid),DPERevenueCategory.directorate_id==self.directorate_id,DPERevenueCategory.active.is_(True)))
        if not c: raise DPERevenueValidationError('Categoria de receita inválida.',{'category_id':'Selecione uma categoria ativa.'})
        return c
    def _offering(self,pid:int,oid:int):
        o=self.db.scalar(select(DPECostPeriodOffering).where(DPECostPeriodOffering.id==int(oid),DPECostPeriodOffering.period_id==int(pid),DPECostPeriodOffering.included.is_(True)))
        if not o: raise DPERevenueValidationError('Curso/contexto inválido.',{'period_offering_id':'Selecione um curso/contexto incluído no mês.'})
        return o
    def _serialize(self,r:DPERevenueEntry):
        c=r.category
        return {'id':r.id,'period_id':r.period_id,'period_offering_id':r.period_offering_id,'category_id':r.category_id,'category_code':c.code if c else None,'category_name':c.name if c else None,'description':r.description,'amount':float(r.amount),'source_type':r.source_type,'source_reference':r.source_reference,'notes':r.notes,'created_at':_iso(r.created_at),'updated_at':_iso(r.updated_at)}
    def central(self,period_id:int|None=None):
        self.ensure_defaults(); self.db.commit()
        periods=self.db.scalars(select(DPECostPeriod).where(DPECostPeriod.directorate_id==self.directorate_id).order_by(DPECostPeriod.period.desc())).all()
        if not periods:return {'periods':[],'selected_period':None,'categories':[],'course_rows':[],'other_entries':[],'summary':{},'editable':False}
        p=next((x for x in periods if x.id==int(period_id or periods[0].id)),periods[0])
        cats=self.db.scalars(select(DPERevenueCategory).where(DPERevenueCategory.directorate_id==self.directorate_id,DPERevenueCategory.active.is_(True)).order_by(DPERevenueCategory.name)).all()
        offers=self.db.scalars(select(DPECostPeriodOffering).where(DPECostPeriodOffering.period_id==p.id,DPECostPeriodOffering.included.is_(True)).order_by(DPECostPeriodOffering.id)).all()
        entries=self.db.scalars(select(DPERevenueEntry).where(DPERevenueEntry.directorate_id==self.directorate_id,DPERevenueEntry.period_id==p.id).options()).all()
        # relationship may be lazy-loaded; safe inside session
        base_category_id=next((c.id for c in cats if c.code=='COURSE_REVENUE'),None)
        by_offer={}
        base_by_offer={}
        for e in entries:
            if e.period_offering_id is not None:
                by_offer[e.period_offering_id]=by_offer.get(e.period_offering_id,Decimal('0'))+Decimal(e.amount)
                if e.category_id==base_category_id:
                    base_by_offer[e.period_offering_id]=base_by_offer.get(e.period_offering_id,Decimal('0'))+Decimal(e.amount)
        course_rows=[]
        for o in offers:
            snap=dict(o.offering_snapshot_json or {}); prod=dict(snap.get('product') or {}); off=dict(snap.get('offering') or {})
            course_rows.append({'period_offering_id':o.id,'label':snapshot_context_label(snap),'product':prod,'offering':off,'amount':float(base_by_offer.get(o.id,Decimal('0'))),'total_attributed_revenue':float(by_offer.get(o.id,Decimal('0')))})
        other=[self._serialize(e) for e in entries if e.category_id!=base_category_id]
        course_total=sum(by_offer.values(),Decimal('0')); institutional_total=sum((Decimal(e.amount) for e in entries if e.period_offering_id is None),Decimal('0'))
        return {'periods':[{'id':x.id,'period':x.period,'status':x.status} for x in periods], 'selected_period':{'id':p.id,'period':p.period,'status':p.status}, 'categories':[{'id':c.id,'code':c.code,'name':c.name,'scope':c.scope,'system':c.system} for c in cats], 'course_rows':course_rows,'other_entries':other,'summary':{'course_revenue':float(course_total),'institutional_revenue':float(institutional_total),'total_revenue':float(course_total+institutional_total),'course_count':len(course_rows),'other_count':len(other)},'editable':p.status in EDITABLE}
    def bulk_courses(self,pid:int,items:list[dict]):
        self._period(pid,editable=True); self.ensure_defaults()
        cat=self.db.scalar(select(DPERevenueCategory).where(DPERevenueCategory.directorate_id==self.directorate_id,DPERevenueCategory.code=='COURSE_REVENUE'))
        updated=[]
        for item in items:
            oid=int(item.get('period_offering_id')); off=self._offering(pid,oid); amount=_money(item.get('amount',0))
            rows=self.db.scalars(select(DPERevenueEntry).where(DPERevenueEntry.directorate_id==self.directorate_id,DPERevenueEntry.period_id==pid,DPERevenueEntry.period_offering_id==oid,DPERevenueEntry.category_id==cat.id).order_by(DPERevenueEntry.id)).all()
            row=rows[0] if rows else None
            for duplicate in rows[1:]: self.db.delete(duplicate)
            if row:
                row.amount=amount; row.updated_by=self.actor
            else:
                row=DPERevenueEntry(directorate_id=self.directorate_id,period_id=pid,period_offering_id=oid,category_id=cat.id,description='Receita do curso',amount=amount,source_type='MANUAL',created_by=self.actor,updated_by=self.actor); self.db.add(row)
            self.db.flush(); updated.append(oid)
        add_dpe_audit(self.db,self.scope,action='REVENUE_COURSE_BULK_UPSERT',entity='dpe_revenue',entity_id=str(pid),period_id=pid,after={'period_offering_ids':updated})
        self.db.commit(); return {'updated_count':len(updated)}
    def create(self,pid:int,payload:dict):
        self._period(pid,editable=True); self.ensure_defaults(); c=self._category(int(payload.get('category_id')))
        oid=payload.get('period_offering_id'); oid=int(oid) if oid not in (None,'') else None
        if oid is not None:self._offering(pid,oid)
        if c.scope=='COURSE' and oid is None: raise DPERevenueValidationError('Esta categoria exige um curso/contexto.',{'period_offering_id':'Selecione um curso/contexto.'})
        if c.scope=='INSTITUTIONAL' and oid is not None: raise DPERevenueValidationError('Esta categoria é institucional e não deve ser vinculada a curso.')
        desc=_txt(payload.get('description')) or c.name
        row=DPERevenueEntry(directorate_id=self.directorate_id,period_id=pid,period_offering_id=oid,category_id=c.id,description=desc,amount=_money(payload.get('amount')),source_type='MANUAL',notes=_txt(payload.get('notes'),2000) or None,created_by=self.actor,updated_by=self.actor)
        self.db.add(row); self.db.flush()
        add_dpe_audit(self.db,self.scope,action='REVENUE_CREATE',entity='dpe_revenue_entry',entity_id=str(row.id),period_id=pid,after=self._serialize(row)); self.db.commit(); self.db.refresh(row); return self._serialize(row)
    def delete(self,eid:int):
        row=self.db.scalar(select(DPERevenueEntry).where(DPERevenueEntry.id==int(eid),DPERevenueEntry.directorate_id==self.directorate_id))
        if not row: raise LookupError('Receita não encontrada.')
        self._period(row.period_id,editable=True); before=self._serialize(row); self.db.delete(row); self.db.flush()
        add_dpe_audit(self.db,self.scope,action='REVENUE_DELETE',entity='dpe_revenue_entry',entity_id=str(eid),period_id=row.period_id,before=before); self.db.commit(); return {'deleted':True}
    def create_category(self,payload:dict):
        code=_txt(payload.get('code'),80).upper().replace(' ','_'); name=_txt(payload.get('name'),160); scope=_txt(payload.get('scope'),20).upper() or 'BOTH'
        if not code or not name: raise DPERevenueValidationError('Informe código e nome da categoria.')
        if scope not in {'COURSE','INSTITUTIONAL','BOTH'}: raise DPERevenueValidationError('Escopo inválido.')
        row=DPERevenueCategory(directorate_id=self.directorate_id,code=code,name=name,scope=scope,active=True,system=False,created_by=self.actor); self.db.add(row)
        try:self.db.commit()
        except IntegrityError as exc:self.db.rollback();raise DPERevenueValidationError('Já existe uma categoria com este código.') from exc
        self.db.refresh(row); return {'id':row.id,'code':row.code,'name':row.name,'scope':row.scope,'system':row.system}
