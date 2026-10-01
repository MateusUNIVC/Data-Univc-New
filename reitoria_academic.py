from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from models import (
    AcademicOffering,
    AcademicResult,
    Course,
    Directorate,
    Discipline,
    NpsInstitution,
    NpsInstitutionFaculty,
    NpsStudent,
    SurveyFacultyInstitutionContext,
    SurveyFacultyInstitutionResponseAggregate,
    SurveyFacultyNpsSource,
    SurveyInstitutionNpsSource,
    SurveyNpsSource,
    SurveyQuestion,
    SurveyResponseAggregate,
)
from security import AuthorizationContext, DirectorateScope
from survey_repository import SurveyRepository


ACADEMIC_DIRECTORATE_CODES = ("DTNH", "DCS")


class ReitoriaAcademicError(RuntimeError):
    pass


def _score(respondents: int, promoters: int, detractors: int) -> float | None:
    if respondents <= 0:
        return None
    return round((promoters - detractors) / respondents * 100.0, 2)


def _pct(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator) * 100.0, 2)


def _as_int(value: Any) -> int:
    return int(value or 0)


def _as_float(value: Any) -> float | None:
    return round(float(value), 2) if value is not None else None


class ReitoriaAcademicService:
    """Leitura acadêmica consolidada da Reitoria.

    A camada nunca persiste projeções novas. Ela agrega DTNH + DCS diretamente
    das bases factuais/projeções oficiais já existentes, preservando a regra de
    cada indicador e evitando média de médias.
    """

    def __init__(self, db: Session, actor: AuthorizationContext):
        self.db = db
        self.actor = actor
        self._directorates = list(self.db.scalars(
            select(Directorate)
            .where(
                Directorate.code.in_(ACADEMIC_DIRECTORATE_CODES),
                Directorate.active.is_(True),
            )
            .order_by(Directorate.code)
        ).all())
        self._directorate_by_code = {row.code: row for row in self._directorates}
        self._directorate_by_id = {int(row.id): row for row in self._directorates}

    def _selected_directorates(self, code: str | None) -> list[Directorate]:
        key = str(code or "ALL").strip().upper()
        if key in {"", "ALL", "TODAS", "UNIVC"}:
            return list(self._directorates)
        row = self._directorate_by_code.get(key)
        if not row:
            raise ReitoriaAcademicError("Diretoria acadêmica inválida. Use ALL, DTNH ou DCS.")
        return [row]

    def _course(self, course_id: int | None, selected_ids: set[int]) -> Course | None:
        if course_id is None:
            return None
        row = self.db.get(Course, int(course_id))
        if not row or int(row.directorate_id) not in selected_ids:
            raise ReitoriaAcademicError("Curso não pertence ao recorte acadêmico selecionado.")
        return row

    def _discipline(self, discipline_id: int | None, course: Course | None, selected_ids: set[int]) -> Discipline | None:
        if discipline_id is None:
            return None
        row = self.db.get(Discipline, int(discipline_id))
        if not row:
            raise ReitoriaAcademicError("Disciplina não encontrada.")
        owning_course = self.db.get(Course, int(row.course_id))
        if not owning_course or int(owning_course.directorate_id) not in selected_ids:
            raise ReitoriaAcademicError("Disciplina não pertence ao recorte acadêmico selecionado.")
        if course and int(row.course_id) != int(course.id):
            raise ReitoriaAcademicError("Disciplina não pertence ao curso selecionado.")
        return row

    def _scope_for(self, row: Directorate) -> DirectorateScope:
        return DirectorateScope(
            user=self.actor,
            directorate_id=int(row.id),
            directorate_code=row.code,
            directorate_name=row.name,
            can_write=False,
            is_home=False,
        )

    def _available_semesters(self, directorate_ids: set[int]) -> list[str]:
        periods: set[str] = set()
        sources: list[Iterable[Any]] = [
            self.db.scalars(select(NpsStudent.period).where(NpsStudent.directorate_id.in_(directorate_ids))).all(),
            self.db.scalars(select(NpsInstitution.period).where(NpsInstitution.directorate_id.in_(directorate_ids))).all(),
            self.db.scalars(select(AcademicResult.period).where(AcademicResult.directorate_id.in_(directorate_ids))).all(),
            self.db.scalars(
                select(AcademicOffering.period)
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(Course.directorate_id.in_(directorate_ids))
            ).all(),
            self.db.scalars(select(NpsInstitutionFaculty.period)).all(),
        ]
        for values in sources:
            periods.update(str(value) for value in values if value)
        return sorted(periods, reverse=True)

    def filters(
        self,
        *,
        directorate: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
    ) -> dict[str, Any]:
        selected = self._selected_directorates(directorate)
        selected_ids = {int(row.id) for row in selected}
        course = self._course(course_id, selected_ids)
        discipline = self._discipline(discipline_id, course, selected_ids)

        course_stmt = (
            select(Course, Directorate.code)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(Course.directorate_id.in_(selected_ids), Course.active.is_(True))
            .order_by(Directorate.code, Course.name)
        )
        course_rows = self.db.execute(course_stmt).all()

        discipline_stmt = (
            select(Discipline, Course, Directorate.code)
            .join(Course, Course.id == Discipline.course_id)
            .join(Directorate, Directorate.id == Course.directorate_id)
            .where(
                Course.directorate_id.in_(selected_ids),
                Course.active.is_(True),
                Discipline.active.is_(True),
            )
        )
        if course:
            discipline_stmt = discipline_stmt.where(Discipline.course_id == course.id)
        discipline_rows = self.db.execute(
            discipline_stmt.order_by(Directorate.code, Course.name, Discipline.name)
        ).all()
        semesters = self._available_semesters(selected_ids)
        return {
            "selected": {
                "directorate": str(directorate or "ALL").upper(),
                "course_id": int(course.id) if course else None,
                "discipline_id": int(discipline.id) if discipline else None,
            },
            "semesters": semesters,
            "latest_semester": semesters[0] if semesters else None,
            "directorates": [
                {"code": row.code, "name": row.name} for row in self._directorates
            ],
            "courses": [
                {
                    "id": int(row.id),
                    "name": row.name,
                    "modality": row.modality,
                    "directorate": code,
                }
                for row, code in course_rows
            ],
            "disciplines": [
                {
                    "id": int(row.id),
                    "name": row.name,
                    "course_id": int(course_row.id),
                    "course_name": course_row.name,
                    "directorate": code,
                }
                for row, course_row, code in discipline_rows
            ],
        }

    @staticmethod
    def _nps_payload(*, respondents: int, promoters: int, neutrals: int, detractors: int) -> dict[str, Any]:
        return {
            "value": _score(respondents, promoters, detractors),
            "respondents": respondents,
            "promoters": promoters,
            "neutrals": neutrals,
            "detractors": detractors,
        }

    def _projection_nps_history(
        self,
        model,
        directorate_ids: set[int],
        *,
        course_id: int | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(
            model.period.label("period"),
            func.sum(model.respondents).label("respondents"),
            func.sum(model.promoters).label("promoters"),
            func.sum(model.neutrals).label("neutrals"),
            func.sum(model.detractors).label("detractors"),
        ).where(model.directorate_id.in_(directorate_ids))
        if course_id is not None and model is NpsStudent:
            stmt = stmt.where(model.course_id == int(course_id))
        stmt = stmt.group_by(model.period).order_by(model.period)
        out = []
        for row in self.db.execute(stmt).all():
            respondents = _as_int(row.respondents)
            promoters = _as_int(row.promoters)
            neutrals = _as_int(row.neutrals)
            detractors = _as_int(row.detractors)
            out.append({
                "periodo": row.period,
                "valor": _score(respondents, promoters, detractors),
                "respondentes": respondents,
                "promotores": promoters,
                "neutros": neutrals,
                "detratores": detractors,
            })
        return out

    def _raw_nps_history_by_course(
        self,
        *,
        source_model,
        directorate_ids: set[int],
        course_id: int,
    ) -> list[dict[str, Any]]:
        source_rows = self.db.scalars(
            select(source_model)
            .where(source_model.directorate_id.in_(directorate_ids))
            .order_by(source_model.semester, source_model.directorate_id)
        ).all()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for source in source_rows:
            rows = self.db.execute(
                select(
                    SurveyResponseAggregate.option_label,
                    SurveyResponseAggregate.numeric_value,
                    func.sum(SurveyResponseAggregate.response_count).label("response_count"),
                )
                .join(Course, Course.id == SurveyResponseAggregate.course_id)
                .where(
                    SurveyResponseAggregate.run_id == source.run_id,
                    SurveyResponseAggregate.question_id == source.question_id,
                    SurveyResponseAggregate.course_id == int(course_id),
                    Course.directorate_id == source.directorate_id,
                )
                .group_by(
                    SurveyResponseAggregate.option_label,
                    SurveyResponseAggregate.numeric_value,
                )
            ).all()
            grouped[str(source.semester)].extend(dict(row._mapping) for row in rows)
        out: list[dict[str, Any]] = []
        for semester in sorted(grouped):
            payload = SurveyRepository._score_distribution_payload(grouped[semester])
            if not payload.get("available"):
                continue
            out.append({
                "periodo": semester,
                "valor": payload.get("nps"),
                "respondentes": _as_int(payload.get("total")),
                "promotores": _as_int(payload.get("promoters")),
                "neutros": _as_int(payload.get("neutrals")),
                "detratores": _as_int(payload.get("detractors")),
            })
        return out

    def _nps_course_comparison(self, directorate_ids: set[int], semester: str) -> list[dict[str, Any]]:
        stmt = (
            select(
                Course.id,
                Course.name,
                Directorate.code,
                func.sum(NpsStudent.respondents).label("respondents"),
                func.sum(NpsStudent.promoters).label("promoters"),
                func.sum(NpsStudent.neutrals).label("neutrals"),
                func.sum(NpsStudent.detractors).label("detractors"),
            )
            .join(Course, Course.id == NpsStudent.course_id)
            .join(Directorate, Directorate.id == NpsStudent.directorate_id)
            .where(
                NpsStudent.directorate_id.in_(directorate_ids),
                NpsStudent.period == semester,
            )
            .group_by(Course.id, Course.name, Directorate.code)
            .order_by(Course.name)
        )
        out = []
        for row in self.db.execute(stmt).all():
            respondents = _as_int(row.respondents)
            promoters = _as_int(row.promoters)
            neutrals = _as_int(row.neutrals)
            detractors = _as_int(row.detractors)
            out.append({
                "course_id": int(row.id),
                "curso": row.name,
                "diretoria": row.code,
                "valor": _score(respondents, promoters, detractors),
                "respondentes": respondents,
                "promotores": promoters,
                "neutros": neutrals,
                "detratores": detractors,
            })
        return out

    def _score_distribution(
        self,
        *,
        source_model,
        directorate_ids: set[int],
        semester: str,
        course_id: int | None = None,
        audience: str,
        scope_label: str,
    ) -> dict[str, Any]:
        source_rows = self.db.execute(
            select(source_model)
            .where(
                source_model.directorate_id.in_(directorate_ids),
                source_model.semester == semester,
            )
        ).scalars().all()
        rows: list[dict[str, Any]] = []
        questions: list[str] = []
        for source in source_rows:
            q = (
                select(
                    SurveyResponseAggregate.option_label,
                    SurveyResponseAggregate.numeric_value,
                    func.sum(SurveyResponseAggregate.response_count).label("response_count"),
                )
                .join(Course, Course.id == SurveyResponseAggregate.course_id)
                .where(
                    SurveyResponseAggregate.run_id == source.run_id,
                    SurveyResponseAggregate.question_id == source.question_id,
                    Course.directorate_id == source.directorate_id,
                )
            )
            if course_id is not None:
                q = q.where(SurveyResponseAggregate.course_id == int(course_id))
            q = q.group_by(
                SurveyResponseAggregate.option_label,
                SurveyResponseAggregate.numeric_value,
            )
            rows.extend(dict(row._mapping) for row in self.db.execute(q).all())
            question = self.db.get(SurveyQuestion, source.question_id)
            if question and question.text not in questions:
                questions.append(question.text)
        payload = SurveyRepository._score_distribution_payload(rows)
        return {
            **payload,
            "audience": audience,
            "semester": semester,
            "scope_label": scope_label,
            "question": questions[0] if len(questions) == 1 else ("Pergunta NPS oficial por diretoria" if questions else None),
            "sources": len(source_rows),
        }

    def _faculty_nps_history(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(select(NpsInstitutionFaculty).order_by(NpsInstitutionFaculty.period)).all()
        out = []
        for row in rows:
            respondents = _as_int(row.respondents)
            promoters = _as_int(row.promoters)
            neutrals = _as_int(row.neutrals)
            detractors = _as_int(row.detractors)
            out.append({
                "periodo": row.period,
                "valor": _score(respondents, promoters, detractors),
                "respondentes": respondents,
                "promotores": promoters,
                "neutros": neutrals,
                "detratores": detractors,
            })
        return out

    def _faculty_nps_distribution(self, semester: str) -> dict[str, Any]:
        source = self.db.scalar(select(SurveyFacultyNpsSource).where(SurveyFacultyNpsSource.semester == semester))
        if not source:
            return {
                "available": False,
                "audience": "faculty",
                "semester": semester,
                "scope_label": "Todos os docentes",
                "total": 0,
                "mean": None,
                "nps": None,
                "items": [],
            }
        rows = self.db.execute(
            select(
                SurveyFacultyInstitutionResponseAggregate.option_label,
                SurveyFacultyInstitutionResponseAggregate.numeric_value,
                func.sum(SurveyFacultyInstitutionResponseAggregate.response_count).label("response_count"),
            )
            .join(
                SurveyFacultyInstitutionContext,
                SurveyFacultyInstitutionContext.id == SurveyFacultyInstitutionResponseAggregate.context_id,
            )
            .where(
                SurveyFacultyInstitutionContext.run_id == source.run_id,
                SurveyFacultyInstitutionResponseAggregate.question_id == source.question_id,
            )
            .group_by(
                SurveyFacultyInstitutionResponseAggregate.option_label,
                SurveyFacultyInstitutionResponseAggregate.numeric_value,
            )
        ).all()
        payload = SurveyRepository._score_distribution_payload([dict(row._mapping) for row in rows])
        question = self.db.get(SurveyQuestion, source.question_id)
        return {
            **payload,
            "audience": "faculty",
            "semester": semester,
            "scope_label": "Todos os docentes",
            "question": question.text if question else None,
        }

    def _faculty_rows(
        self,
        selected: list[Directorate],
        *,
        semester: str | None,
        course: Course | None,
        discipline: Discipline | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for directorate in selected:
            if course and int(course.directorate_id) != int(directorate.id):
                continue
            repo = SurveyRepository(self.db, self._scope_for(directorate))
            rows.extend(repo._faculty_analytics_rows(
                semester=semester,
                course_id=int(course.id) if course else None,
                discipline_id=int(discipline.id) if discipline else None,
            ))
        return rows

    @staticmethod
    def _faculty_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return SurveyRepository._faculty_analytics_summary_from_rows(rows)

    def _faculty_payload(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        summary = self._faculty_summary(rows)
        favorability = summary.get("favorability") or {}
        value = favorability.get("favorable_percentage") if favorability.get("mapping_complete") is not False else None
        return {
            "value": value,
            "participations": _as_int(summary.get("respondent_participations")),
            "contexts": _as_int(summary.get("contexts")),
            "teachers": _as_int(summary.get("teachers")),
            "disciplines": _as_int(summary.get("disciplines")),
            "classified": _as_int(favorability.get("classified_total")),
            "favorable": _as_int(favorability.get("favorable")),
            "intermediate": _as_int(favorability.get("intermediate")),
            "unfavorable": _as_int(favorability.get("unfavorable")),
            "unmapped": _as_int(favorability.get("unmapped_total")),
            "mapping_complete": favorability.get("mapping_complete") is not False,
        }

    def _faculty_history(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("semester") or "")].append(row)
        out = []
        for semester in sorted(key for key in grouped if key):
            payload = self._faculty_payload(grouped[semester])
            out.append({
                "periodo": semester,
                "valor": payload["value"],
                "respondentes": payload["participations"],
                "classificados": payload["classified"],
                "favoraveis": payload["favorable"],
                "intermediarias": payload["intermediate"],
                "desfavoraveis": payload["unfavorable"],
            })
        return out

    def _faculty_course_comparison(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[int(row["course_id"])].append(row)
        out = []
        for course_id, course_rows in grouped.items():
            first = course_rows[0]
            payload = self._faculty_payload(course_rows)
            directorate = self._directorate_by_id.get(int(self.db.get(Course, course_id).directorate_id))
            out.append({
                "course_id": course_id,
                "curso": first.get("course_name"),
                "diretoria": directorate.code if directorate else "",
                "valor": payload["value"],
                "respondentes": payload["participations"],
                "classificados": payload["classified"],
                "favoraveis": payload["favorable"],
            })
        return sorted(out, key=lambda item: str(item["curso"] or "").casefold())

    def _result_conditions(
        self,
        directorate_ids: set[int],
        *,
        semester: str | None = None,
        course: Course | None = None,
        discipline: Discipline | None = None,
    ) -> list[Any]:
        conditions: list[Any] = [AcademicResult.directorate_id.in_(directorate_ids)]
        if semester:
            conditions.append(AcademicResult.period == semester)
        if course:
            conditions.append(AcademicResult.course_id == int(course.id))
        if discipline:
            conditions.append(AcademicResult.discipline_id == int(discipline.id))
        return conditions

    def _result_payload(self, directorate_ids: set[int], *, semester: str, course: Course | None, discipline: Discipline | None) -> dict[str, Any]:
        conditions = self._result_conditions(
            directorate_ids, semester=semester, course=course, discipline=discipline
        )
        finalized = case((AcademicResult.approved.is_not(None), 1), else_=0)
        approved = case((AcademicResult.approved.is_(True), 1), else_=0)
        failed_grade = case((and_(AcademicResult.approved.is_(False), AcademicResult.failure_reason == "nota"), 1), else_=0)
        failed_absence = case((and_(AcademicResult.approved.is_(False), AcademicResult.failure_reason == "falta"), 1), else_=0)
        failed_other = case((and_(
            AcademicResult.approved.is_(False),
            or_(AcademicResult.failure_reason.is_(None), ~AcademicResult.failure_reason.in_(["nota", "falta"])),
        ), 1), else_=0)
        row = self.db.execute(select(
            func.count(AcademicResult.id).label("total"),
            func.sum(finalized).label("finalized"),
            func.sum(approved).label("approved"),
            func.sum(failed_grade).label("failed_grade"),
            func.sum(failed_absence).label("failed_absence"),
            func.sum(failed_other).label("failed_other"),
            func.count(AcademicResult.final_average).label("grade_count"),
            func.sum(AcademicResult.final_average).label("grade_sum"),
            func.avg(AcademicResult.final_average).label("grade_mean"),
            func.count(func.distinct(AcademicResult.student_id)).label("students"),
        ).where(*conditions)).one()
        finalized_count = _as_int(row.finalized)
        approved_count = _as_int(row.approved)
        return {
            "approval_rate": _pct(approved_count, finalized_count),
            "average_grade": _as_float(row.grade_mean),
            "grade_count": _as_int(row.grade_count),
            "grade_sum": float(row.grade_sum or 0),
            "students": _as_int(row.students),
            "total_records": _as_int(row.total),
            "finalized": finalized_count,
            "approved": approved_count,
            "failed_grade": _as_int(row.failed_grade),
            "failed_absence": _as_int(row.failed_absence),
            "failed_other": _as_int(row.failed_other),
        }

    def _result_history(self, directorate_ids: set[int], *, course: Course | None, discipline: Discipline | None) -> list[dict[str, Any]]:
        conditions = self._result_conditions(directorate_ids, course=course, discipline=discipline)
        finalized = case((AcademicResult.approved.is_not(None), 1), else_=0)
        approved = case((AcademicResult.approved.is_(True), 1), else_=0)
        stmt = (
            select(
                AcademicResult.period.label("period"),
                func.sum(finalized).label("finalized"),
                func.sum(approved).label("approved"),
                func.count(AcademicResult.final_average).label("grade_count"),
                func.sum(AcademicResult.final_average).label("grade_sum"),
                func.avg(AcademicResult.final_average).label("grade_mean"),
                func.count(func.distinct(AcademicResult.student_id)).label("students"),
            )
            .where(*conditions)
            .group_by(AcademicResult.period)
            .order_by(AcademicResult.period)
        )
        out = []
        for row in self.db.execute(stmt).all():
            finalized_count = _as_int(row.finalized)
            approved_count = _as_int(row.approved)
            out.append({
                "periodo": row.period,
                "taxa_aprovacao": _pct(approved_count, finalized_count),
                "media_notas": _as_float(row.grade_mean),
                "notas_contagem": _as_int(row.grade_count),
                "soma_notas": float(row.grade_sum or 0),
                "alunos_distintos": _as_int(row.students),
                "finalizados": finalized_count,
                "aprovados": approved_count,
            })
        return out

    def _result_course_comparison(
        self,
        directorate_ids: set[int],
        *,
        semester: str,
        course: Course | None = None,
        discipline: Discipline | None = None,
    ) -> list[dict[str, Any]]:
        finalized = case((AcademicResult.approved.is_not(None), 1), else_=0)
        approved = case((AcademicResult.approved.is_(True), 1), else_=0)
        conditions = [
            AcademicResult.directorate_id.in_(directorate_ids),
            AcademicResult.period == semester,
        ]
        if course:
            conditions.append(AcademicResult.course_id == int(course.id))
        if discipline:
            conditions.append(AcademicResult.discipline_id == int(discipline.id))
        stmt = (
            select(
                Course.id,
                Course.name,
                Directorate.code,
                func.sum(finalized).label("finalized"),
                func.sum(approved).label("approved"),
                func.avg(AcademicResult.final_average).label("grade_mean"),
                func.count(func.distinct(AcademicResult.student_id)).label("students"),
            )
            .join(Course, Course.id == AcademicResult.course_id)
            .join(Directorate, Directorate.id == AcademicResult.directorate_id)
            .where(*conditions)
            .group_by(Course.id, Course.name, Directorate.code)
            .order_by(Course.name)
        )
        out = []
        for row in self.db.execute(stmt).all():
            finalized_count = _as_int(row.finalized)
            approved_count = _as_int(row.approved)
            out.append({
                "course_id": int(row.id),
                "curso": row.name,
                "diretoria": row.code,
                "valor": _pct(approved_count, finalized_count),
                "media_notas": _as_float(row.grade_mean),
                "alunos_distintos": _as_int(row.students),
                "finalizados": finalized_count,
                "aprovados": approved_count,
            })
        return out

    def overview(
        self,
        *,
        semester: str | None = None,
        directorate: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
    ) -> dict[str, Any]:
        selected = self._selected_directorates(directorate)
        selected_ids = {int(row.id) for row in selected}
        course = self._course(course_id, selected_ids)
        discipline = self._discipline(discipline_id, course, selected_ids)
        semesters = self._available_semesters(selected_ids)
        effective_semester = str(semester or (semesters[0] if semesters else "")).strip().upper() or None
        if effective_semester and effective_semester not in semesters:
            # O semestre pode existir somente em uma base recém-lançada e ainda
            # não constar nos filtros em uma corrida concorrente; aceitamos o
            # formato acadêmico, mas rejeitamos valores arbitrários.
            if len(effective_semester) != 9 or effective_semester[4:] not in {"-SEM1", "-SEM2"} or not effective_semester[:4].isdigit():
                raise ReitoriaAcademicError("Semestre inválido. Use AAAA-SEM1 ou AAAA-SEM2.")

        institution_history = (
            self._raw_nps_history_by_course(
                source_model=SurveyInstitutionNpsSource,
                directorate_ids=selected_ids,
                course_id=int(course.id),
            )
            if course
            else self._projection_nps_history(NpsInstitution, selected_ids)
        )
        course_nps_history = self._projection_nps_history(
            NpsStudent, selected_ids, course_id=int(course.id) if course else None
        )
        faculty_nps_history = self._faculty_nps_history()

        faculty_rows_all = self._faculty_rows(
            selected, semester=None, course=course, discipline=discipline
        )
        faculty_rows_current = [
            row for row in faculty_rows_all if not effective_semester or row.get("semester") == effective_semester
        ]
        faculty_current = self._faculty_payload(faculty_rows_current)
        faculty_history = self._faculty_history(faculty_rows_all)

        results_current = self._result_payload(
            selected_ids,
            semester=effective_semester or "",
            course=course,
            discipline=discipline,
        ) if effective_semester else {
            "approval_rate": None, "average_grade": None, "grade_count": 0, "grade_sum": 0,
            "students": 0, "total_records": 0, "finalized": 0, "approved": 0,
            "failed_grade": 0, "failed_absence": 0, "failed_other": 0,
        }
        result_history = self._result_history(selected_ids, course=course, discipline=discipline)

        institution_current = next((item for item in institution_history if item["periodo"] == effective_semester), None)
        course_nps_current = next((item for item in course_nps_history if item["periodo"] == effective_semester), None)
        faculty_nps_current = next((item for item in faculty_nps_history if item["periodo"] == effective_semester), None)

        comparisons = {
            "nps_courses": self._nps_course_comparison(selected_ids, effective_semester) if effective_semester else [],
            "faculty_courses": self._faculty_course_comparison(faculty_rows_current),
            "approval_courses": self._result_course_comparison(
                selected_ids, semester=effective_semester, course=course, discipline=discipline
            ) if effective_semester else [],
        }
        if course:
            comparisons["nps_courses"] = [row for row in comparisons["nps_courses"] if row["course_id"] == int(course.id)]
            comparisons["faculty_courses"] = [row for row in comparisons["faculty_courses"] if row["course_id"] == int(course.id)]
            comparisons["approval_courses"] = [row for row in comparisons["approval_courses"] if row["course_id"] == int(course.id)]

        institution_distribution = self._score_distribution(
            source_model=SurveyInstitutionNpsSource,
            directorate_ids=selected_ids,
            semester=effective_semester or "",
            course_id=int(course.id) if course else None,
            audience="institution",
            scope_label=course.name if course else (selected[0].code if len(selected) == 1 else "UNIVC · DTNH + DCS"),
        ) if effective_semester else {"available": False, "items": [], "total": 0}
        course_distribution = self._score_distribution(
            source_model=SurveyNpsSource,
            directorate_ids=selected_ids,
            semester=effective_semester or "",
            course_id=int(course.id) if course else None,
            audience="course",
            scope_label=course.name if course else (selected[0].code if len(selected) == 1 else "Todos os cursos"),
        ) if effective_semester else {"available": False, "items": [], "total": 0}
        faculty_nps_distribution = self._faculty_nps_distribution(effective_semester) if effective_semester else {"available": False, "items": [], "total": 0}

        return {
            "scope": {
                "semester": effective_semester,
                "directorate": str(directorate or "ALL").upper(),
                "directorates": [row.code for row in selected],
                "course_id": int(course.id) if course else None,
                "course": course.name if course else None,
                "discipline_id": int(discipline.id) if discipline else None,
                "discipline": discipline.name if discipline else None,
                "read_only": True,
            },
            "kpis": {
                "nps_institution_students": institution_current or {
                    "periodo": effective_semester, "valor": None, "respondentes": 0,
                    "promotores": 0, "neutros": 0, "detratores": 0,
                },
                "nps_courses": course_nps_current or {
                    "periodo": effective_semester, "valor": None, "respondentes": 0,
                    "promotores": 0, "neutros": 0, "detratores": 0,
                },
                "faculty_favorability": faculty_current,
                "approval": {
                    "value": results_current["approval_rate"],
                    "approved": results_current["approved"],
                    "finalized": results_current["finalized"],
                    "failed_grade": results_current["failed_grade"],
                    "failed_absence": results_current["failed_absence"],
                    "failed_other": results_current["failed_other"],
                },
                "average_grade": {
                    "value": results_current["average_grade"],
                    "grade_count": results_current["grade_count"],
                },
                "distinct_students": {
                    "value": results_current["students"],
                    "result_records": results_current["total_records"],
                },
                "nps_faculty": faculty_nps_current or {
                    "periodo": effective_semester, "valor": None, "respondentes": 0,
                    "promotores": 0, "neutros": 0, "detratores": 0,
                },
            },
            "histories": {
                "nps_institution_students": institution_history,
                "nps_courses": course_nps_history,
                "faculty_favorability": faculty_history,
                "approval": [
                    {
                        "periodo": row["periodo"], "valor": row["taxa_aprovacao"],
                        "aprovados": row["aprovados"], "finalizados": row["finalizados"],
                    }
                    for row in result_history
                ],
                "average_grade": [
                    {"periodo": row["periodo"], "valor": row["media_notas"], "notas_contagem": row["notas_contagem"]}
                    for row in result_history
                ],
                "distinct_students": [
                    {"periodo": row["periodo"], "valor": row["alunos_distintos"], "alunos_distintos": row["alunos_distintos"]}
                    for row in result_history
                ],
                "nps_faculty": faculty_nps_history,
            },
            "comparisons": comparisons,
            "distributions": {
                "nps_institution_students": institution_distribution,
                "nps_courses": course_distribution,
                "nps_faculty": faculty_nps_distribution,
            },
            "notes": {
                "nps": "NPS consolidado pelas contagens de promotores, neutros e detratores; não é média entre diretorias.",
                "faculty": "Favorabilidade consolidada pelas respostas classificadas das perguntas de docente; participações não representam alunos únicos entre contextos.",
                "results": "Aprovação usa aprovados / resultados finalizados; média usa soma e quantidade de notas válidas.",
                "institution_nps_course_filter": "Quando um curso é selecionado, o NPS institucional dos alunos é reconstruído a partir do recorte de curso preservado na fonte oficial. O filtro de disciplina não se aplica ao NPS.",
            },
        }
