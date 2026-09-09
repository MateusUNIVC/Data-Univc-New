from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    AcademicOffering,
    AuditLog,
    Course,
    Discipline,
    DPEExpenseAllocation,
    FacultyEvaluationContext,
    FacultyRawResponse,
    FacultyResponseAggregate,
    NpsInstitutionFaculty,
    SurveyFacultyInstitutionContext,
    SurveyFacultyInstitutionRawResponse,
    SurveyFacultyInstitutionResponseAggregate,
    SurveyFacultyNpsSource,
    SurveyImport,
    SurveyRawResponse,
    SurveyResponseAggregate,
    SurveyRun,
    SurveyRunCourse,
    TeachingAssignment,
)

T = TypeVar("T")


class ObjectNotFound(LookupError):
    """The requested object does not exist."""


class ObjectAccessDenied(PermissionError):
    """The object exists but belongs to another authorization scope."""


def _clean_owner_ids(values: Any) -> set[int]:
    owners: set[int] = set()
    for value in values:
        if value in (None, ""):
            continue
        try:
            owners.add(int(value))
        except (TypeError, ValueError):
            continue
    return owners


def _survey_run_legacy_owner_ids(db: Session, run_id: int) -> set[int]:
    """Derive owners for pre-v0.9.3 survey runs that do not have directorate_id.

    Old survey runs could be inferred from their course rows, faculty offerings,
    NPS source links or the audit trail. The fallback is read-only metadata for
    migration compatibility; all runs created by v0.9.3+ carry an explicit owner.
    """
    owners: set[int] = set()

    owners.update(_clean_owner_ids(db.scalars(
        select(Course.directorate_id)
        .join(SurveyRunCourse, SurveyRunCourse.course_id == Course.id)
        .where(SurveyRunCourse.run_id == run_id)
    ).all()))

    owners.update(_clean_owner_ids(db.scalars(
        select(Course.directorate_id)
        .join(AcademicOffering, AcademicOffering.course_id == Course.id)
        .join(TeachingAssignment, TeachingAssignment.offering_id == AcademicOffering.id)
        .join(FacultyEvaluationContext, FacultyEvaluationContext.teaching_assignment_id == TeachingAssignment.id)
        .where(FacultyEvaluationContext.run_id == run_id)
    ).all()))

    # Survey NPS source tables with direct directorate ownership are intentionally
    # imported lazily here to keep the top-level registry focused on object types.
    from models import SurveyInstitutionNpsSource, SurveyNpsSource

    owners.update(_clean_owner_ids(db.scalars(
        select(SurveyNpsSource.directorate_id).where(SurveyNpsSource.run_id == run_id)
    ).all()))
    owners.update(_clean_owner_ids(db.scalars(
        select(SurveyInstitutionNpsSource.directorate_id).where(SurveyInstitutionNpsSource.run_id == run_id)
    ).all()))

    owners.update(_clean_owner_ids(db.scalars(
        select(AuditLog.directorate_id).where(
            AuditLog.entity.in_(("survey_run", "survey_faculty", "survey_faculty_institution")),
            AuditLog.entity_id == str(run_id),
        )
    ).all()))
    return owners


def survey_run_owner_ids(db: Session, run: SurveyRun | int) -> set[int]:
    row = db.get(SurveyRun, int(run)) if isinstance(run, int) else run
    if not row:
        return set()
    if getattr(row, "directorate_id", None) not in (None, ""):
        return {int(row.directorate_id)}
    return _survey_run_legacy_owner_ids(db, int(row.id))


def object_directorate_ids(db: Session, row: Any) -> set[int]:
    """Resolve the owning directorate(s) for a persisted Data UNIVC object.

    Most tables carry ``directorate_id`` directly. Indirect models are resolved
    through their authoritative parent relation. Returning more than one owner is
    supported only for legacy survey runs created before explicit ownership was
    introduced in v0.9.3.0.
    """
    direct = getattr(row, "directorate_id", None)
    if direct not in (None, ""):
        return {int(direct)}

    if isinstance(row, Discipline):
        owner = db.scalar(select(Course.directorate_id).where(Course.id == row.course_id))
        return _clean_owner_ids([owner])

    if isinstance(row, SurveyRun):
        return survey_run_owner_ids(db, row)

    if isinstance(row, SurveyImport):
        run = db.scalar(select(SurveyRun).where(SurveyRun.import_id == row.id))
        return survey_run_owner_ids(db, run) if run else set()

    if isinstance(row, SurveyRunCourse):
        owner = db.scalar(select(Course.directorate_id).where(Course.id == row.course_id))
        return _clean_owner_ids([owner])

    if isinstance(row, (SurveyResponseAggregate, SurveyRawResponse)):
        owner = db.scalar(select(Course.directorate_id).where(Course.id == row.course_id))
        return _clean_owner_ids([owner])

    if isinstance(row, AcademicOffering):
        owner = db.scalar(select(Course.directorate_id).where(Course.id == row.course_id))
        return _clean_owner_ids([owner])

    if isinstance(row, TeachingAssignment):
        offering = db.get(AcademicOffering, row.offering_id)
        return object_directorate_ids(db, offering) if offering else set()

    if isinstance(row, FacultyEvaluationContext):
        assignment = db.get(TeachingAssignment, row.teaching_assignment_id)
        return object_directorate_ids(db, assignment) if assignment else set()

    if isinstance(row, (FacultyResponseAggregate, FacultyRawResponse)):
        context = db.get(FacultyEvaluationContext, row.context_id)
        return object_directorate_ids(db, context) if context else set()

    if isinstance(row, SurveyFacultyInstitutionContext):
        run = db.get(SurveyRun, row.run_id)
        return survey_run_owner_ids(db, run) if run else set()

    if isinstance(row, (SurveyFacultyInstitutionResponseAggregate, SurveyFacultyInstitutionRawResponse)):
        context = db.get(SurveyFacultyInstitutionContext, row.context_id)
        return object_directorate_ids(db, context) if context else set()

    if isinstance(row, SurveyFacultyNpsSource):
        run = db.get(SurveyRun, row.run_id)
        return survey_run_owner_ids(db, run) if run else set()

    if isinstance(row, NpsInstitutionFaculty):
        if row.survey_run_id:
            run = db.get(SurveyRun, row.survey_run_id)
            return survey_run_owner_ids(db, run) if run else set()
        return set()

    if isinstance(row, DPEExpenseAllocation):
        from models import DPEExpense

        expense = db.get(DPEExpense, row.expense_id)
        return object_directorate_ids(db, expense) if expense else set()

    return set()


def require_object_for_directorate(
    db: Session,
    model: type[T],
    object_id: Any,
    directorate_id: int,
    *,
    label: str = "Recurso",
) -> T:
    """Load an object and enforce ownership against one already-authorized scope."""
    row = db.get(model, object_id)
    if row is None:
        raise ObjectNotFound(f"{label} não encontrado.")
    owners = object_directorate_ids(db, row)
    if not owners or int(directorate_id) not in owners:
        raise ObjectAccessDenied("Você não possui acesso a este recurso.")
    return row


def require_survey_run_for_directorate(
    db: Session,
    run_id: int,
    directorate_id: int,
    *,
    label: str = "Importação de questionário",
) -> SurveyRun:
    return require_object_for_directorate(
        db,
        SurveyRun,
        run_id,
        directorate_id,
        label=label,
    )


def require_question_for_run(
    db: Session,
    *,
    run: SurveyRun,
    question_id: int,
    label: str = "Pergunta",
):
    """Require a global question to be part of the authorized run questionnaire."""
    from models import SurveyQuestion, SurveyQuestionnaireQuestion

    question = db.get(SurveyQuestion, question_id)
    if not question:
        raise ObjectNotFound(f"{label} não encontrada.")
    linked = db.scalar(select(SurveyQuestionnaireQuestion.id).where(
        SurveyQuestionnaireQuestion.questionnaire_id == run.questionnaire_id,
        SurveyQuestionnaireQuestion.question_id == question.id,
    ))
    if linked is None:
        raise ObjectAccessDenied("A pergunta informada não pertence a esta importação.")
    return question
