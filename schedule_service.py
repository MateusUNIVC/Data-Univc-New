from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import IndicatorDefinition, IndicatorSchedule


def nth_business_day(year: int, month: int, n: int) -> date:
    d = date(year, month, 1); count = 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n: return d
        d += timedelta(days=1)


def schedule_status(db: Session, directorate_code: str, indicator_codes: tuple[str, ...] | list[str] | None = None):
    today = date.today()
    query = (
        select(IndicatorDefinition, IndicatorSchedule)
        .join(IndicatorSchedule, IndicatorSchedule.indicator_code == IndicatorDefinition.code)
        .where(IndicatorDefinition.directorate_code == directorate_code, IndicatorDefinition.active.is_(True), IndicatorSchedule.active.is_(True))
    )
    if indicator_codes:
        query = query.where(IndicatorDefinition.code.in_(indicator_codes))
    rows = db.execute(query.order_by(IndicatorDefinition.code)).all()
    out=[]
    for definition, schedule in rows:
        due=nth_business_day(today.year,today.month,max(1,schedule.due_business_day))
        out.append({"codigo":definition.code,"indicador":definition.name,"periodicidade":definition.periodicity,"grao_referencia":schedule.reference_grain,"abre_no_dia_util":schedule.collection_window_start_business_day,"vence_no_dia_util":schedule.due_business_day,"prazo_mes_atual":due.isoformat(),"status_calendario":"No prazo" if today<=due else "Prazo encerrado"})
    return out


