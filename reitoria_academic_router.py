from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from reitoria_academic import ReitoriaAcademicError, ReitoriaAcademicService
from security import AuthorizationContext, require_fresh_reitoria


router = APIRouter(prefix="/api/reitoria/academic", tags=["reitoria-academic"])


@router.get("/filters")
def reitoria_academic_filters(
    directorate: str = Query("ALL"),
    course_id: int | None = Query(None),
    discipline_id: int | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    try:
        return ReitoriaAcademicService(db, ctx).filters(
            directorate=directorate,
            course_id=course_id,
            discipline_id=discipline_id,
        )
    except ReitoriaAcademicError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/overview")
def reitoria_academic_overview(
    semester: str | None = Query(None),
    directorate: str = Query("ALL"),
    course_id: int | None = Query(None),
    discipline_id: int | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthorizationContext = Depends(require_fresh_reitoria),
):
    try:
        return ReitoriaAcademicService(db, ctx).overview(
            semester=semester,
            directorate=directorate,
            course_id=course_id,
            discipline_id=discipline_id,
        )
    except ReitoriaAcademicError as exc:
        raise HTTPException(400, str(exc)) from exc
