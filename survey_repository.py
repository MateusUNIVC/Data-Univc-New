from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from auth.objects import require_question_for_run, require_survey_run_for_directorate, survey_run_owner_ids

from models import (
    AcademicOffering,
    AuditLog,
    Course,
    Directorate,
    Discipline,
    FacultyEvaluationContext,
    FacultyRawResponse,
    FacultyResponseAggregate,
    NpsInstitution,
    NpsInstitutionFaculty,
    Goal,
    NpsStudent,
    SurveyImport,
    SurveyInstitutionNpsSource,
    SurveyFacultyInstitutionContext,
    SurveyFacultyInstitutionRawResponse,
    SurveyFacultyInstitutionResponseAggregate,
    SurveyFacultyNpsSource,
    SurveyNpsSource,
    SurveyQuestion,
    SurveyQuestionnaire,
    SurveyQuestionnaireQuestion,
    SurveyRawResponse,
    SurveyResponseAggregate,
    SurveyRun,
    SurveyRunCourse,
    Teacher,
    TeachingAssignment,
)
from security import DirectorateScope
from academic_catalog import course_aliases
from survey_metrics import distribution, metric_summary, nps_score
from analytics import active_goal, goal_info, status_for
from survey_models import ParsedQuestion, ParsedWorkbook
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_institution_models import ParsedFacultyInstitutionWorkbook
from survey_parser import normalize_key


class SurveyIntegrationError(RuntimeError):
    pass


def _semester_to_data_univc(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.endswith(".1") or text.endswith("-1") or text.endswith("/1"):
        year = text[:4]
        return f"{year}-SEM1" if year.isdigit() else None
    if text.endswith(".2") or text.endswith("-2") or text.endswith("/2"):
        year = text[:4]
        return f"{year}-SEM2" if year.isdigit() else None
    if len(text) == 9 and text[4:] in {"-SEM1", "-SEM2"} and text[:4].isdigit():
        return text
    return None


class SurveyRepository:
    """Persistência da integração de Avaliação Institucional dentro do Data UNIVC.

    A base ``survey_*`` guarda o fato próximo da fonte. ``nps_student`` continua
    sendo a projeção usada pelo painel acadêmico legado, agora reconstruível a
    partir das distribuições originais do SEI.
    """

    def __init__(self, db: Session, scope: DirectorateScope):
        self.db = db
        self.scope = scope
        self.directorate_id = scope.directorate_id
        self.directorate_code = scope.directorate_code
        self.user = scope.user

    def _audit(self, action: str, entity: str, entity_id: Any = None, details: Any = None) -> None:
        self.db.add(AuditLog(
            directorate_id=self.directorate_id,
            user_id=self.user.user_id,
            user_email=self.user.email,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=json.dumps(details, ensure_ascii=False, default=str) if details is not None else None,
        ))

    @staticmethod
    def external_import_key(origin: str, metadata: dict | None) -> str | None:
        if origin != "sei" or not metadata:
            return None
        identity = {
            "evaluation_name": metadata.get("evaluation_name"),
            "questionnaire_id": metadata.get("selected_questionnaire_id"),
            "start_date": metadata.get("start_date"),
            "end_date": metadata.get("end_date"),
            "unit_value": metadata.get("unit_value"),
            "turn_value": metadata.get("turn_value"),
            "detail_value": metadata.get("detail_value"),
        }
        if not identity["evaluation_name"] or not identity["questionnaire_id"]:
            return None
        raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sei:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _course_candidates(self) -> list[Course]:
        return list(self.db.scalars(
            select(Course).where(Course.directorate_id == self.directorate_id).order_by(Course.name)
        ).all())

    def match_course(self, name: str, modality: str | None = None) -> dict[str, Any]:
        target = normalize_key(name)
        if not target:
            return {"matched": False, "reason": "Nome do curso ausente"}
        modality_norm = normalize_key(modality or "")
        target_variants = {target}
        for suffix in (" ead", " presencial", " semipresencial", " a distancia"):
            if target.endswith(suffix):
                target_variants.add(target[: -len(suffix)].strip())
        exact: list[Course] = []
        alias_matches: list[Course] = []
        for course in self._course_candidates():
            names = [course.name, *course_aliases(course.name)]
            normalized = {normalize_key(item) for item in names if item}
            canonical = normalize_key(course.name)
            if canonical in target_variants:
                exact.append(course)
            elif normalized.intersection(target_variants):
                alias_matches.append(course)
        candidates = exact or alias_matches
        if modality_norm and candidates:
            modality_filtered = [c for c in candidates if normalize_key(c.modality or "") == modality_norm]
            if modality_filtered:
                candidates = modality_filtered
            else:
                return {
                    "matched": False,
                    "reason": f"Curso encontrado, mas a modalidade do relatório ({modality or 'não informada'}) não corresponde ao catálogo desta diretoria.",
                    "candidates": [c.name for c in candidates],
                }
        if len(candidates) == 1:
            course = candidates[0]
            return {
                "matched": True,
                "course_id": course.id,
                "course_name": course.name,
                "modality": course.modality or "Presencial",
                "match_type": "exact" if exact else "alias",
            }
        if len(candidates) > 1:
            return {
                "matched": False,
                "reason": "Mais de um curso do catálogo corresponde ao nome do relatório.",
                "candidates": [c.name for c in candidates],
            }
        return {
            "matched": False,
            "reason": "Curso não encontrado no catálogo desta diretoria.",
            "candidates": [],
        }

    def inspect_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched = []
        for item in entries:
            match = self.match_course(str(item.get("course_name") or ""), str(item.get("modality") or ""))
            enriched.append({**item, "course_match": match})
        return enriched

    def _get_or_create_questionnaire(self, name: str, sei_id: str | None) -> SurveyQuestionnaire:
        name = (name or "Questionário sem nome").strip()
        row = self.db.scalar(select(SurveyQuestionnaire).where(SurveyQuestionnaire.name == name))
        if row:
            if sei_id and not row.sei_id:
                row.sei_id = str(sei_id)
            return row
        row = SurveyQuestionnaire(name=name, sei_id=str(sei_id) if sei_id else None)
        self.db.add(row)
        self.db.flush()
        return row

    def _get_or_create_question(self, questionnaire_id: int, question: ParsedQuestion) -> SurveyQuestion:
        row = self.db.scalar(
            select(SurveyQuestion).where(SurveyQuestion.normalized_text == question.normalized_text)
        )
        if row:
            if question.nps_candidate and not row.nps_candidate:
                row.nps_candidate = True
            if row.detected_metric_type == "categorical" and question.metric_type != "categorical":
                row.detected_metric_type = question.metric_type
        else:
            row = SurveyQuestion(
                text=question.text,
                normalized_text=question.normalized_text,
                position=question.position,
                detected_metric_type=question.metric_type,
                nps_candidate=bool(question.nps_candidate),
            )
            self.db.add(row)
            self.db.flush()
        link = self.db.scalar(select(SurveyQuestionnaireQuestion).where(
            SurveyQuestionnaireQuestion.questionnaire_id == questionnaire_id,
            SurveyQuestionnaireQuestion.question_id == row.id,
        ))
        if link:
            link.position = question.position
        else:
            self.db.add(SurveyQuestionnaireQuestion(
                questionnaire_id=questionnaire_id,
                question_id=row.id,
                position=question.position,
            ))
            # A mesma pergunta costuma reaparecer em vários blocos de curso do
            # mesmo relatório. Com autoflush desabilitado, a próxima consulta não
            # enxerga este vínculo pendente e tentaria inseri-lo novamente.
            self.db.flush()
        return row

    def import_workbooks(
        self,
        *,
        sha256: str,
        source_filename: str,
        source_kind: str,
        workbooks: list[ParsedWorkbook],
        semester_override: str | None = None,
        origin: str = "manual",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        if not workbooks:
            raise SurveyIntegrationError("Nenhum relatório foi selecionado para importação.")
        metadata = metadata or {}
        first = workbooks[0]
        semester = _semester_to_data_univc(semester_override or first.semester_suggested)
        if not semester:
            raise SurveyIntegrationError("Não foi possível definir o semestre. Informe AAAA-SEM1 ou AAAA-SEM2.")

        external_key = self.external_import_key(origin, metadata)
        existing = None
        if external_key:
            existing = self.db.scalar(select(SurveyImport).where(SurveyImport.directorate_id == self.directorate_id, SurveyImport.external_key == external_key))
        if not existing:
            existing = self.db.scalar(select(SurveyImport).where(SurveyImport.directorate_id == self.directorate_id, SurveyImport.sha256 == sha256))

        if existing:
            imp = existing
            run = self.db.scalar(select(SurveyRun).where(SurveyRun.import_id == imp.id))
            if not run:
                raise SurveyIntegrationError("Importação de questionário existe sem survey_run correspondente.")
            require_survey_run_for_directorate(self.db, run.id, self.directorate_id)
            if semester_override:
                run.semester = semester
            imp.source_filename = source_filename
            imp.origin = origin
            if metadata:
                imp.metadata_json = metadata
            if external_key and not imp.external_key:
                imp.external_key = external_key
        else:
            imp = SurveyImport(
                id=uuid.uuid4().hex,
                directorate_id=self.directorate_id,
                source_filename=source_filename,
                sha256=sha256,
                source_kind=source_kind,
                origin=origin,
                external_key=external_key,
                metadata_json=metadata or None,
                status="processing",
            )
            self.db.add(imp)
            questionnaire = self._get_or_create_questionnaire(
                first.questionnaire_name or first.survey_title or "Questionário sem nome",
                metadata.get("selected_questionnaire_id"),
            )
            run = SurveyRun(
                import_id=imp.id,
                directorate_id=self.directorate_id,
                questionnaire_id=questionnaire.id,
                title=first.survey_title,
                period_start=first.period_start,
                period_end=first.period_end,
                semester=semester,
                run_kind="generic",
            )
            self.db.add(run)
            self.db.flush()

        imported: list[str] = []
        skipped: list[str] = []
        unmapped: list[dict[str, str]] = []
        for parsed in workbooks:
            match = self.match_course(parsed.course_name, parsed.modality)
            if not match.get("matched"):
                unmapped.append({"source_path": parsed.source_path, "course": parsed.course_name, "reason": match.get("reason") or "Não mapeado"})
                continue
            course_id = int(match["course_id"])
            exists = self.db.scalar(select(SurveyRunCourse).where(
                SurveyRunCourse.run_id == run.id,
                SurveyRunCourse.course_id == course_id,
            ))
            if exists:
                skipped.append(parsed.source_path)
                continue
            self.db.add(SurveyRunCourse(
                run_id=run.id,
                course_id=course_id,
                source_path=parsed.source_path,
                respondent_count=max(0, int(parsed.respondent_count or 0)),
            ))
            for question in parsed.questions:
                qrow = self._get_or_create_question(run.questionnaire_id, question)
                for option in question.options:
                    self.db.add(SurveyResponseAggregate(
                        run_id=run.id,
                        course_id=course_id,
                        question_id=qrow.id,
                        option_label=option.label,
                        option_key=normalize_key(option.label),
                        numeric_value=option.numeric_value,
                        response_count=max(0, int(option.count or 0)),
                        source_percentage=option.source_percentage,
                    ))
                for response_text in question.raw_responses:
                    self.db.add(SurveyRawResponse(
                        run_id=run.id,
                        course_id=course_id,
                        question_id=qrow.id,
                        response_text=response_text,
                        response_key=normalize_key(response_text),
                    ))
            imported.append(parsed.source_path)

        imp.status = "completed"
        self._audit("import", "survey_run", run.id, {
            "origin": origin,
            "semester": semester,
            "imported": len(imported),
            "skipped": len(skipped),
            "unmapped": len(unmapped),
        })
        self.db.commit()
        return {
            "import_id": imp.id,
            "run_id": run.id,
            "semester": semester,
            "imported_files": imported,
            "skipped_files": skipped,
            "unmapped": unmapped,
        }

    def list_nps_candidates(self, run_id: int) -> list[dict[str, Any]]:
        run = require_survey_run_for_directorate(self.db, run_id, self.directorate_id)
        course_ids = list(self.db.scalars(select(SurveyRunCourse.course_id).join(Course, Course.id == SurveyRunCourse.course_id).where(
            SurveyRunCourse.run_id == run_id,
            Course.directorate_id == self.directorate_id,
        )).all())
        if not course_ids:
            return []
        rows = self.db.execute(
            select(SurveyQuestion, SurveyQuestionnaireQuestion.position)
            .join(SurveyQuestionnaireQuestion, SurveyQuestionnaireQuestion.question_id == SurveyQuestion.id)
            .where(
                SurveyQuestionnaireQuestion.questionnaire_id == run.questionnaire_id,
                SurveyQuestion.nps_candidate.is_(True),
            )
            .order_by(SurveyQuestionnaireQuestion.position, SurveyQuestion.id)
        ).all()
        course_source = self.db.scalar(select(SurveyNpsSource).where(
            SurveyNpsSource.directorate_id == self.directorate_id,
            SurveyNpsSource.semester == run.semester,
        )) if run.semester else None
        institution_source = self.db.scalar(select(SurveyInstitutionNpsSource).where(
            SurveyInstitutionNpsSource.directorate_id == self.directorate_id,
            SurveyInstitutionNpsSource.semester == run.semester,
        )) if run.semester else None
        candidates = []
        for question, position in rows:
            has_data = self.db.scalar(select(func.count(SurveyResponseAggregate.id)).where(
                SurveyResponseAggregate.run_id == run_id,
                SurveyResponseAggregate.question_id == question.id,
                SurveyResponseAggregate.course_id.in_(course_ids),
            ))
            if not has_data:
                continue
            candidates.append({
                "id": question.id,
                "text": question.text,
                "position": position,
                "nps_candidate": True,
                "official_for_course_semester": bool(course_source and course_source.run_id == run_id and course_source.question_id == question.id),
                "official_for_institution_semester": bool(institution_source and institution_source.run_id == run_id and institution_source.question_id == question.id),
                "course_source_exists": bool(course_source),
                "institution_source_exists": bool(institution_source),
            })
        return candidates

    def _distribution_rows(
        self,
        run_id: int,
        question_id: int,
        *,
        course_id: int | None = None,
        directorate_id: int | None = None,
    ) -> list[dict[str, Any]]:
        effective_directorate_id = directorate_id or self.directorate_id
        q = select(
            SurveyResponseAggregate.option_label,
            SurveyResponseAggregate.numeric_value,
            func.sum(SurveyResponseAggregate.response_count).label("response_count"),
        ).join(Course, Course.id == SurveyResponseAggregate.course_id).where(
            SurveyResponseAggregate.run_id == run_id,
            SurveyResponseAggregate.question_id == question_id,
            Course.directorate_id == effective_directorate_id,
        )
        if course_id is not None:
            q = q.where(SurveyResponseAggregate.course_id == course_id)
        q = q.group_by(SurveyResponseAggregate.option_label, SurveyResponseAggregate.numeric_value).order_by(SurveyResponseAggregate.numeric_value)
        return [dict(row._mapping) for row in self.db.execute(q).all()]

    def _validate_nps_scale(self, run_id: int, question_id: int) -> None:
        rows = self._distribution_rows(run_id, question_id)
        values = {float(row["numeric_value"]) for row in rows if row.get("numeric_value") is not None}
        if values != {float(i) for i in range(11)}:
            raise SurveyIntegrationError("O NPS oficial precisa conter exatamente as alternativas de 0 a 10.")

    @staticmethod
    def _normalize_nps_scope(value: str | None) -> str:
        text = str(value or "course").strip().casefold()
        if text in {"course", "curso", "nps_course", "nps-curso"}:
            return "course"
        if text in {"institution", "instituicao", "instituição", "nps_institution", "nps-instituicao"}:
            return "institution"
        raise SurveyIntegrationError("Tipo de NPS inválido. Use 'course' ou 'institution'.")

    def bind_and_sync_nps(
        self,
        *,
        run_id: int,
        question_id: int,
        semester: str | None = None,
        replace: bool = False,
        nps_scope: str = "course",
    ) -> dict[str, Any]:
        scope = self._normalize_nps_scope(nps_scope)
        if scope == "institution":
            return self._bind_and_sync_institution_nps(
                run_id=run_id, question_id=question_id, semester=semester, replace=replace
            )
        return self._bind_and_sync_course_nps(
            run_id=run_id, question_id=question_id, semester=semester, replace=replace
        )

    def _nps_binding_context(self, run_id: int, question_id: int, semester: str | None) -> tuple[SurveyRun, SurveyQuestion, str]:
        run = require_survey_run_for_directorate(self.db, run_id, self.directorate_id)
        question = require_question_for_run(self.db, run=run, question_id=question_id)
        effective_semester = _semester_to_data_univc(semester or run.semester)
        if not effective_semester:
            raise SurveyIntegrationError("Informe um semestre no formato AAAA-SEM1 ou AAAA-SEM2.")
        if not question.nps_candidate:
            raise SurveyIntegrationError("A pergunta escolhida não foi detectada como escala completa de 0 a 10.")
        self._validate_nps_scale(run_id, question_id)
        run.run_kind = "student_nps"
        run.semester = effective_semester
        return run, question, effective_semester

    def _bind_and_sync_course_nps(self, *, run_id: int, question_id: int, semester: str | None, replace: bool) -> dict[str, Any]:
        run, question, effective_semester = self._nps_binding_context(run_id, question_id, semester)
        conflicting = self.db.scalar(select(SurveyInstitutionNpsSource).where(
            SurveyInstitutionNpsSource.directorate_id == self.directorate_id,
            SurveyInstitutionNpsSource.semester == effective_semester,
            SurveyInstitutionNpsSource.question_id == question_id,
        ))
        if conflicting:
            raise SurveyIntegrationError("A mesma pergunta não pode ser usada como NPS da Instituição e NPS do Curso no mesmo semestre. Escolha uma pergunta diferente.")
        source = self.db.scalar(select(SurveyNpsSource).where(
            SurveyNpsSource.directorate_id == self.directorate_id,
            SurveyNpsSource.semester == effective_semester,
        ))
        if source and (source.run_id != run_id or source.question_id != question_id) and not replace:
            raise SurveyIntegrationError("Já existe uma fonte oficial de NPS do Curso para este semestre. Confirme a substituição para trocar a origem.")
        if source:
            source.run_id = run_id
            source.question_id = question_id
            source.created_by = self.user.email
        else:
            source = SurveyNpsSource(
                directorate_id=self.directorate_id,
                semester=effective_semester,
                run_id=run_id,
                question_id=question_id,
                created_by=self.user.email,
            )
            self.db.add(source)
        self.db.flush()

        course_ids = list(self.db.scalars(
            select(SurveyRunCourse.course_id).join(Course, Course.id == SurveyRunCourse.course_id).where(
                SurveyRunCourse.run_id == run_id,
                Course.directorate_id == self.directorate_id,
            )
        ).all())
        synced: list[dict[str, Any]] = []
        for course_id in course_ids:
            dist = distribution(self._distribution_rows(run_id, question_id, course_id=course_id))
            metric = nps_score(dist["items"])
            if not metric["total"]:
                continue
            row = self.db.scalar(select(NpsStudent).where(
                NpsStudent.directorate_id == self.directorate_id,
                NpsStudent.period == effective_semester,
                NpsStudent.course_id == course_id,
            ))
            if not row:
                row = NpsStudent(
                    directorate_id=self.directorate_id,
                    period=effective_semester,
                    course_id=course_id,
                    respondents=int(metric["total"]),
                    promoters=int(metric["promoters"]),
                    neutrals=int(metric["passives"]),
                    detractors=int(metric["detractors"]),
                    inserted_by=self.user.full_name,
                    source_type="SEI_SURVEY",
                    survey_run_id=run_id,
                    survey_question_id=question_id,
                )
                self.db.add(row)
            else:
                row.respondents = int(metric["total"])
                row.promoters = int(metric["promoters"])
                row.neutrals = int(metric["passives"])
                row.detractors = int(metric["detractors"])
                row.inserted_by = self.user.full_name
                row.source_type = "SEI_SURVEY"
                row.survey_run_id = run_id
                row.survey_question_id = question_id
            course = self.db.get(Course, course_id)
            synced.append({
                "course_id": course_id,
                "course": course.name if course else str(course_id),
                "respondents": int(metric["total"]),
                "promoters": int(metric["promoters"]),
                "neutrals": int(metric["passives"]),
                "detractors": int(metric["detractors"]),
                "score": round(float(metric["score"]), 2),
            })

        stale_q = select(NpsStudent).where(
            NpsStudent.directorate_id == self.directorate_id,
            NpsStudent.period == effective_semester,
            NpsStudent.source_type == "SEI_SURVEY",
        )
        if course_ids:
            stale_q = stale_q.where(NpsStudent.course_id.not_in(course_ids))
        for row in self.db.scalars(stale_q).all():
            self.db.delete(row)

        self._audit("sync", "survey_nps_course", source.id, {
            "semester": effective_semester,
            "run_id": run_id,
            "question_id": question_id,
            "courses": len(synced),
        })
        self.db.commit()
        overall = nps_score(distribution(self._distribution_rows(run_id, question_id))["items"])
        return {
            "ok": True,
            "nps_scope": "course",
            "semester": effective_semester,
            "run_id": run_id,
            "question_id": question_id,
            "question": question.text,
            "courses_synced": synced,
            "overall": self._nps_metric_payload(overall),
        }

    @staticmethod
    def _nps_metric_payload(metric: dict[str, Any]) -> dict[str, Any]:
        return {
            "score": round(float(metric["score"]), 2) if metric.get("score") is not None else None,
            "respondents": int(metric.get("total") or 0),
            "promoters": int(metric.get("promoters") or 0),
            "neutrals": int(metric.get("passives") or 0),
            "detractors": int(metric.get("detractors") or 0),
        }

    def _bind_and_sync_institution_nps(self, *, run_id: int, question_id: int, semester: str | None, replace: bool) -> dict[str, Any]:
        run, question, effective_semester = self._nps_binding_context(run_id, question_id, semester)
        conflicting = self.db.scalar(select(SurveyNpsSource).where(
            SurveyNpsSource.directorate_id == self.directorate_id,
            SurveyNpsSource.semester == effective_semester,
            SurveyNpsSource.question_id == question_id,
        ))
        if conflicting:
            raise SurveyIntegrationError("A mesma pergunta não pode ser usada como NPS da Instituição e NPS do Curso no mesmo semestre. Escolha uma pergunta diferente.")
        source = self.db.scalar(select(SurveyInstitutionNpsSource).where(
            SurveyInstitutionNpsSource.directorate_id == self.directorate_id,
            SurveyInstitutionNpsSource.semester == effective_semester,
        ))
        if source and (source.run_id != run_id or source.question_id != question_id) and not replace:
            raise SurveyIntegrationError("Já existe uma fonte oficial de NPS da Instituição para este semestre. Confirme a substituição para trocar a origem.")
        if source:
            source.run_id = run_id
            source.question_id = question_id
            source.created_by = self.user.email
        else:
            source = SurveyInstitutionNpsSource(
                directorate_id=self.directorate_id,
                semester=effective_semester,
                run_id=run_id,
                question_id=question_id,
                created_by=self.user.email,
            )
            self.db.add(source)
        metric = nps_score(distribution(self._distribution_rows(run_id, question_id))["items"])
        if not metric["total"]:
            raise SurveyIntegrationError("A pergunta de NPS da Instituição não possui respostas válidas no recorte desta diretoria.")
        row = self.db.scalar(select(NpsInstitution).where(
            NpsInstitution.directorate_id == self.directorate_id,
            NpsInstitution.period == effective_semester,
        ))
        if not row:
            row = NpsInstitution(
                directorate_id=self.directorate_id,
                period=effective_semester,
                respondents=int(metric["total"]),
                promoters=int(metric["promoters"]),
                neutrals=int(metric["passives"]),
                detractors=int(metric["detractors"]),
                inserted_by=self.user.full_name,
                source_type="SEI_SURVEY",
                survey_run_id=run_id,
                survey_question_id=question_id,
            )
            self.db.add(row)
        else:
            row.respondents = int(metric["total"])
            row.promoters = int(metric["promoters"])
            row.neutrals = int(metric["passives"])
            row.detractors = int(metric["detractors"])
            row.inserted_by = self.user.full_name
            row.source_type = "SEI_SURVEY"
            row.survey_run_id = run_id
            row.survey_question_id = question_id
        self.db.flush()
        self._audit("sync", "survey_nps_institution", source.id, {
            "semester": effective_semester,
            "run_id": run_id,
            "question_id": question_id,
            "respondents": int(metric["total"]),
        })
        self.db.commit()
        return {
            "ok": True,
            "nps_scope": "institution",
            "semester": effective_semester,
            "run_id": run_id,
            "question_id": question_id,
            "question": question.text,
            "courses_synced": [],
            "overall": self._nps_metric_payload(metric),
        }

    def nps_source_history(self, nps_scope: str = "course") -> list[dict[str, Any]]:
        scope = self._normalize_nps_scope(nps_scope)
        SourceModel = SurveyInstitutionNpsSource if scope == "institution" else SurveyNpsSource
        rows = self.db.execute(
            select(SourceModel, SurveyRun, SurveyQuestion, SurveyQuestionnaire)
            .join(SurveyRun, SurveyRun.id == SourceModel.run_id)
            .join(SurveyQuestion, SurveyQuestion.id == SourceModel.question_id)
            .join(SurveyQuestionnaire, SurveyQuestionnaire.id == SurveyRun.questionnaire_id)
            .where(SourceModel.directorate_id == self.directorate_id)
            .order_by(SourceModel.semester.desc())
        ).all()
        return [{
            "id": source.id,
            "nps_scope": scope,
            "semester": source.semester,
            "run_id": run.id,
            "question_id": question.id,
            "question": question.text,
            "questionnaire": questionnaire.name,
            "title": run.title,
            "period_start": run.period_start,
            "period_end": run.period_end,
            "created_at": str(source.created_at) if source.created_at else None,
        } for source, run, question, questionnaire in rows]

    def institution_nps_course_breakdown(self) -> list[dict[str, Any]]:
        """Recalcula o NPS institucional por curso usando os agregados brutos do SEI.

        O total institucional oficial continua em NpsInstitution. A segmentação por
        curso é analítica e deriva da mesma pergunta institucional, pois os
        agregados de resposta preservam course_id.
        """
        # O NPS institucional oficial continua agregado entre DTNH + DCS na
        # história institucional. Este detalhamento, porém, pertence à diretoria
        # em visualização e nunca deve misturar cursos de outra diretoria.
        source_rows = list(self.db.execute(
            select(
                SurveyInstitutionNpsSource, SurveyRun, SurveyQuestion, SurveyQuestionnaire,
                Directorate.id, Directorate.code,
            )
            .join(SurveyRun, SurveyRun.id == SurveyInstitutionNpsSource.run_id)
            .join(SurveyQuestion, SurveyQuestion.id == SurveyInstitutionNpsSource.question_id)
            .join(SurveyQuestionnaire, SurveyQuestionnaire.id == SurveyRun.questionnaire_id)
            .join(Directorate, Directorate.id == SurveyInstitutionNpsSource.directorate_id)
            .where(
                SurveyInstitutionNpsSource.directorate_id == self.directorate_id,
                Directorate.active.is_(True),
            )
        ).all())
        out: list[dict[str, Any]] = []
        institution_indicator = f"{self.directorate_code}-01A"
        goal_rows = self.db.scalars(
            select(Goal).where(
                Goal.directorate_id == self.directorate_id,
                Goal.indicator_code == institution_indicator,
            )
        ).all()
        goals = [
            {
                "indicador": row.indicator_code,
                "recorte": row.scope_label,
                "vigencia": row.valid_from,
                "meta": row.target,
                "atencao": row.attention,
                "limite_superior": row.upper_limit,
                "justificativa": row.justification or "",
            }
            for row in goal_rows
        ]
        for source, run, question, questionnaire, directorate_id, directorate_code in source_rows:
            course_ids = list(self.db.scalars(
                select(SurveyRunCourse.course_id)
                .join(Course, Course.id == SurveyRunCourse.course_id)
                .where(SurveyRunCourse.run_id == run.id, Course.directorate_id == directorate_id)
            ).all())
            for course_id in course_ids:
                course = self.db.get(Course, course_id)
                if not course:
                    continue
                metric = nps_score(distribution(self._distribution_rows(
                    run.id, question.id, course_id=course_id, directorate_id=directorate_id
                ))["items"])
                if not metric.get("total"):
                    continue
                value = round(float(metric["score"]), 2) if metric.get("score") is not None else None
                goal = active_goal(goals, institution_indicator, source.semester)
                info = goal_info(goal, institution_indicator)
                out.append({
                    "id": f"{source.semester}:{course.id}",
                    "periodo": source.semester,
                    "curso_id": course.id,
                    "curso": course.name,
                    "diretoria": directorate_code,
                    "respondentes": int(metric.get("total") or 0),
                    "promotores": int(metric.get("promoters") or 0),
                    "neutros": int(metric.get("passives") or 0),
                    "detratores": int(metric.get("detractors") or 0),
                    "valor": value,
                    "fonte": "SEI · Questionário institucional",
                    "question": question.text,
                    "questionnaire": questionnaire.name,
                    "meta": info.get("meta") if info else None,
                    "atencao": info.get("atencao") if info else None,
                    "limite_superior": info.get("limite_superior") if info else None,
                    "meta_vigencia": info.get("vigencia") if info else None,
                    "meta_recorte": info.get("recorte") if info else None,
                    "meta_origem": info.get("origem") if info else None,
                    "status": status_for(value, goal, institution_indicator),
                })
        return sorted(out, key=lambda item: (item["periodo"], item["curso"]), reverse=True)

    def institution_nps_history(self) -> list[dict[str, Any]]:
        academic_codes = ("DTNH", "DCS")
        directorates = list(self.db.execute(
            select(Directorate.id, Directorate.code, Directorate.name)
            .where(Directorate.code.in_(academic_codes), Directorate.active.is_(True))
            .order_by(Directorate.code)
        ).all())
        directorate_ids = [row.id for row in directorates]
        if not directorate_ids:
            return []

        projection_rows = list(self.db.execute(
            select(NpsInstitution, Directorate.code)
            .join(Directorate, Directorate.id == NpsInstitution.directorate_id)
            .where(NpsInstitution.directorate_id.in_(directorate_ids))
            .order_by(NpsInstitution.period.desc(), Directorate.code)
        ).all())
        source_rows = list(self.db.execute(
            select(SurveyInstitutionNpsSource, SurveyRun, SurveyQuestion, SurveyQuestionnaire, Directorate.code)
            .join(SurveyRun, SurveyRun.id == SurveyInstitutionNpsSource.run_id)
            .join(SurveyQuestion, SurveyQuestion.id == SurveyInstitutionNpsSource.question_id)
            .join(SurveyQuestionnaire, SurveyQuestionnaire.id == SurveyRun.questionnaire_id)
            .join(Directorate, Directorate.id == SurveyInstitutionNpsSource.directorate_id)
            .where(SurveyInstitutionNpsSource.directorate_id.in_(directorate_ids))
        ).all())

        sources_by_period: dict[str, list[dict[str, Any]]] = {}
        for source, run, question, questionnaire, code in source_rows:
            sources_by_period.setdefault(source.semester, []).append({
                "directorate": code,
                "question": question.text,
                "questionnaire": questionnaire.name,
                "run_id": run.id,
                "question_id": question.id,
            })

        grouped: dict[str, list[tuple[NpsInstitution, str]]] = {}
        for row, code in projection_rows:
            grouped.setdefault(row.period, []).append((row, code))

        out = []
        total_directorates = len(directorates)
        for period, parts in grouped.items():
            respondents = sum(int(row.respondents or 0) for row, _ in parts)
            promoters = sum(int(row.promoters or 0) for row, _ in parts)
            neutrals = sum(int(row.neutrals or 0) for row, _ in parts)
            detractors = sum(int(row.detractors or 0) for row, _ in parts)
            score = round((promoters - detractors) / respondents * 100, 2) if respondents else None
            present_codes = sorted({code for _, code in parts})
            missing_codes = [row.code for row in directorates if row.code not in present_codes]
            sources = sources_by_period.get(period, [])
            questions = sorted({item["question"] for item in sources if item.get("question")})
            questionnaires = sorted({item["questionnaire"] for item in sources if item.get("questionnaire")})
            dates = [row.inserted_at for row, _ in parts if row.inserted_at]
            out.append({
                "id": period,
                "periodo": period,
                "respondentes": respondents,
                "promotores": promoters,
                "neutros": neutrals,
                "detratores": detractors,
                "valor": score,
                "fonte": "SEI · Questionário",
                "question": questions[0] if len(questions) == 1 else ("Perguntas divergentes entre diretorias" if questions else None),
                "questionnaire": questionnaires[0] if len(questionnaires) == 1 else ("Múltiplos questionários" if questionnaires else None),
                "directorates": present_codes,
                "missing_directorates": missing_codes,
                "coverage": len(present_codes),
                "coverage_total": total_directorates,
                "complete": len(present_codes) == total_directorates,
                "data_lancamento": str(max(dates).date()) if dates else None,
                "sources": sources,
            })
        return sorted(out, key=lambda item: item["periodo"], reverse=True)

    @staticmethod
    def faculty_institution_external_import_key(origin: str, metadata: dict | None) -> str | None:
        """Chave idempotente própria do questionário respondido por docentes.

        Não reutilizamos a chave discente para que duas aplicações diferentes
        nunca colidam apenas por compartilharem os mesmos filtros do relatório.
        """
        if origin != "sei" or not metadata:
            return None
        identity = {
            "audience": "faculty",
            "evaluation_name": metadata.get("evaluation_name"),
            "questionnaire_id": metadata.get("selected_questionnaire_id"),
            "start_date": metadata.get("start_date"),
            "end_date": metadata.get("end_date"),
            "unit_value": metadata.get("unit_value"),
            "turn_value": metadata.get("turn_value"),
            "detail_value": metadata.get("detail_value"),
        }
        if not identity["evaluation_name"] or not identity["questionnaire_id"]:
            return None
        raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sei-faculty:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _clear_faculty_institution_run(self, run_id: int) -> None:
        context_ids = list(self.db.scalars(
            select(SurveyFacultyInstitutionContext.id).where(
                SurveyFacultyInstitutionContext.run_id == run_id
            )
        ).all())
        if context_ids:
            self.db.execute(delete(SurveyFacultyInstitutionResponseAggregate).where(
                SurveyFacultyInstitutionResponseAggregate.context_id.in_(context_ids)
            ))
            self.db.execute(delete(SurveyFacultyInstitutionRawResponse).where(
                SurveyFacultyInstitutionRawResponse.context_id.in_(context_ids)
            ))
            self.db.execute(delete(SurveyFacultyInstitutionContext).where(
                SurveyFacultyInstitutionContext.id.in_(context_ids)
            ))
        self.db.flush()

    def import_faculty_institution_workbooks(
        self,
        *,
        sha256: str,
        source_filename: str,
        source_kind: str,
        workbooks: list[ParsedFacultyInstitutionWorkbook],
        semester_override: str | None = None,
        origin: str = "manual",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Persiste Avaliação Institucional respondida por docentes.

        Os relatórios reais são anônimos e não carregam curso, disciplina ou
        identificação do respondente. Toda a importação representa uma única
        população institucional de docentes no semestre informado.
        """
        if not workbooks:
            raise SurveyIntegrationError("Nenhum relatório docente foi selecionado para importação.")
        metadata = metadata or {}
        first = workbooks[0]
        semester = _semester_to_data_univc(semester_override or first.semester_suggested)
        if not semester:
            raise SurveyIntegrationError("Não foi possível definir o semestre. Informe AAAA-SEM1 ou AAAA-SEM2.")
        for parsed in workbooks:
            parsed_semester = _semester_to_data_univc(semester_override or parsed.semester_suggested or semester)
            if parsed_semester != semester:
                raise SurveyIntegrationError("Todos os relatórios docentes selecionados precisam pertencer ao mesmo semestre.")

        external_key = self.faculty_institution_external_import_key(origin, metadata)
        imp = None
        if external_key:
            imp = self.db.scalar(select(SurveyImport).where(SurveyImport.directorate_id == self.directorate_id, SurveyImport.external_key == external_key))
        if not imp:
            imp = self.db.scalar(select(SurveyImport).where(SurveyImport.directorate_id == self.directorate_id, SurveyImport.sha256 == sha256))

        refresh_existing = False
        if imp:
            run = self.db.scalar(select(SurveyRun).where(SurveyRun.import_id == imp.id))
            if not run:
                raise SurveyIntegrationError("Importação docente existente sem survey_run correspondente.")
            require_survey_run_for_directorate(self.db, run.id, self.directorate_id)
            if run.run_kind not in {"faculty_institution", "faculty_nps"}:
                raise SurveyIntegrationError("Este arquivo já pertence a outro tipo de questionário no Data UNIVC.")
            refresh_existing = bool(external_key and imp.sha256 != sha256)
            if refresh_existing:
                # A mesma aplicacao do SEI pode ser regenerada com respostas
                # diferentes. Antes de substituir os agregados, invalide a
                # projecao NPS oficial que dependia deste run para nunca deixar
                # um 01C antigo apontando para distribuicoes que ja nao existem.
                stale_sources = list(self.db.scalars(
                    select(SurveyFacultyNpsSource).where(SurveyFacultyNpsSource.run_id == run.id)
                ).all())
                for stale_source in stale_sources:
                    self.db.execute(delete(NpsInstitutionFaculty).where(
                        NpsInstitutionFaculty.period == stale_source.semester
                    ))
                    self.db.delete(stale_source)
                self._clear_faculty_institution_run(run.id)
                imp.sha256 = sha256
            run.semester = semester
            run.run_kind = "faculty_institution"
            run.title = first.survey_title or run.title
            run.period_start = first.period_start or run.period_start
            run.period_end = first.period_end or run.period_end
            imp.source_filename = source_filename
            imp.source_kind = source_kind
            imp.origin = origin
            if metadata:
                imp.metadata_json = metadata
            if external_key and not imp.external_key:
                imp.external_key = external_key
        else:
            imp = SurveyImport(
                id=uuid.uuid4().hex,
                directorate_id=self.directorate_id,
                source_filename=source_filename,
                sha256=sha256,
                source_kind=source_kind,
                origin=origin,
                external_key=external_key,
                metadata_json=metadata or None,
                status="processing",
            )
            self.db.add(imp)
            questionnaire = self._get_or_create_questionnaire(
                first.questionnaire_name or first.survey_title or "Avaliação Institucional pelos Docentes",
                metadata.get("selected_questionnaire_id"),
            )
            run = SurveyRun(
                import_id=imp.id,
                directorate_id=self.directorate_id,
                questionnaire_id=questionnaire.id,
                title=first.survey_title,
                period_start=first.period_start,
                period_end=first.period_end,
                semester=semester,
                run_kind="faculty_institution",
            )
            self.db.add(run)
            self.db.flush()

        imported: list[str] = []
        skipped: list[str] = []
        for parsed in workbooks:
            existing = self.db.scalar(select(SurveyFacultyInstitutionContext).where(
                SurveyFacultyInstitutionContext.run_id == run.id,
                SurveyFacultyInstitutionContext.source_path == parsed.source_path,
            ))
            if existing:
                skipped.append(parsed.source_path)
                continue
            context = SurveyFacultyInstitutionContext(
                run_id=run.id,
                source_path=parsed.source_path,
                unit_name=parsed.unit_name,
                respondent_count=max(0, int(parsed.respondent_count or 0)),
            )
            self.db.add(context)
            self.db.flush()
            for question in parsed.questions:
                qrow = self._get_or_create_question(run.questionnaire_id, question)
                for option in question.options:
                    self.db.add(SurveyFacultyInstitutionResponseAggregate(
                        context_id=context.id,
                        question_id=qrow.id,
                        option_label=option.label,
                        option_key=normalize_key(option.label),
                        numeric_value=option.numeric_value,
                        response_count=max(0, int(option.count or 0)),
                        source_percentage=option.source_percentage,
                    ))
                for response_text in question.raw_responses:
                    self.db.add(SurveyFacultyInstitutionRawResponse(
                        context_id=context.id,
                        question_id=qrow.id,
                        response_text=response_text,
                        response_key=normalize_key(response_text),
                    ))
            imported.append(parsed.source_path)

        imp.status = "completed"
        self._audit("import", "survey_faculty_institution", run.id, {
            "origin": origin,
            "semester": semester,
            "imported": len(imported),
            "skipped": len(skipped),
            "anonymous_population": True,
            "refresh_existing": refresh_existing,
        })
        self.db.commit()
        return {
            "import_id": imp.id,
            "run_id": run.id,
            "semester": semester,
            "imported_files": imported,
            "skipped_files": skipped,
            "anonymous_population": True,
        }

    def _faculty_institution_distribution_rows(self, run_id: int, question_id: int) -> list[dict[str, Any]]:
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
                SurveyFacultyInstitutionContext.run_id == run_id,
                SurveyFacultyInstitutionResponseAggregate.question_id == question_id,
            )
            .group_by(
                SurveyFacultyInstitutionResponseAggregate.option_label,
                SurveyFacultyInstitutionResponseAggregate.numeric_value,
            )
            .order_by(SurveyFacultyInstitutionResponseAggregate.numeric_value)
        ).all()
        return [dict(row._mapping) for row in rows]

    def list_faculty_nps_candidates(self, run_id: int) -> list[dict[str, Any]]:
        run = require_survey_run_for_directorate(self.db, run_id, self.directorate_id, label="Importação institucional docente")
        if run.run_kind not in {"faculty_institution", "faculty_nps"}:
            raise SurveyIntegrationError("Importação institucional docente não encontrada.")
        rows = self.db.execute(
            select(SurveyQuestion, SurveyQuestionnaireQuestion.position)
            .join(SurveyQuestionnaireQuestion, SurveyQuestionnaireQuestion.question_id == SurveyQuestion.id)
            .where(
                SurveyQuestionnaireQuestion.questionnaire_id == run.questionnaire_id,
                SurveyQuestion.nps_candidate.is_(True),
            )
            .order_by(SurveyQuestionnaireQuestion.position, SurveyQuestion.id)
        ).all()
        source = self.db.scalar(select(SurveyFacultyNpsSource).where(
            SurveyFacultyNpsSource.semester == run.semester
        )) if run.semester else None
        out: list[dict[str, Any]] = []
        for question, position in rows:
            has_data = int(self.db.scalar(
                select(func.count(SurveyFacultyInstitutionResponseAggregate.id))
                .join(
                    SurveyFacultyInstitutionContext,
                    SurveyFacultyInstitutionContext.id == SurveyFacultyInstitutionResponseAggregate.context_id,
                )
                .where(
                    SurveyFacultyInstitutionContext.run_id == run.id,
                    SurveyFacultyInstitutionResponseAggregate.question_id == question.id,
                )
            ) or 0)
            if not has_data:
                continue
            out.append({
                "id": question.id,
                "text": question.text,
                "position": position,
                "nps_candidate": True,
                "official_for_semester": bool(
                    source and source.run_id == run.id and source.question_id == question.id
                ),
                "source_exists": bool(source),
            })
        return out

    def bind_and_sync_faculty_nps(
        self,
        *,
        run_id: int,
        question_id: int,
        semester: str | None = None,
        replace: bool = False,
    ) -> dict[str, Any]:
        run = require_survey_run_for_directorate(self.db, run_id, self.directorate_id, label="Importação institucional docente")
        question = require_question_for_run(self.db, run=run, question_id=question_id)
        if run.run_kind not in {"faculty_institution", "faculty_nps"}:
            raise SurveyIntegrationError("Run do NPS docente não encontrado.")
        effective_semester = _semester_to_data_univc(semester or run.semester)
        if not effective_semester:
            raise SurveyIntegrationError("Informe um semestre no formato AAAA-SEM1 ou AAAA-SEM2.")
        if not question.nps_candidate:
            raise SurveyIntegrationError("A pergunta escolhida não foi detectada como escala completa de 0 a 10.")
        rows = self._faculty_institution_distribution_rows(run_id, question_id)
        values = {float(row["numeric_value"]) for row in rows if row.get("numeric_value") is not None}
        if values != {float(i) for i in range(11)}:
            raise SurveyIntegrationError("O NPS oficial dos docentes precisa conter exatamente as alternativas de 0 a 10.")

        source = self.db.scalar(select(SurveyFacultyNpsSource).where(
            SurveyFacultyNpsSource.semester == effective_semester
        ))
        if source and source.run_id != run_id:
            current_source_owners = survey_run_owner_ids(self.db, source.run_id)
            if self.directorate_id not in current_source_owners and not self.scope.user.global_access:
                from auth.objects import ObjectAccessDenied
                raise ObjectAccessDenied("A fonte oficial deste semestre pertence a outra diretoria.")
        if source and (source.run_id != run_id or source.question_id != question_id) and not replace:
            raise SurveyIntegrationError(
                "Já existe uma fonte oficial de NPS institucional dos docentes para este semestre. "
                "Confirme a substituição para trocar a origem."
            )
        if source:
            source.run_id = run_id
            source.question_id = question_id
            source.created_by = self.user.email
        else:
            source = SurveyFacultyNpsSource(
                semester=effective_semester,
                run_id=run_id,
                question_id=question_id,
                created_by=self.user.email,
            )
            self.db.add(source)

        metric = nps_score(distribution(rows)["items"])
        if not metric.get("total"):
            raise SurveyIntegrationError("A pergunta de NPS dos docentes não possui respostas válidas.")
        projection = self.db.scalar(select(NpsInstitutionFaculty).where(
            NpsInstitutionFaculty.period == effective_semester
        ))
        if not projection:
            projection = NpsInstitutionFaculty(
                period=effective_semester,
                respondents=int(metric["total"]),
                promoters=int(metric["promoters"]),
                neutrals=int(metric["passives"]),
                detractors=int(metric["detractors"]),
                inserted_by=self.user.full_name,
                source_type="SEI_SURVEY",
                survey_run_id=run_id,
                survey_question_id=question_id,
            )
            self.db.add(projection)
        else:
            projection.respondents = int(metric["total"])
            projection.promoters = int(metric["promoters"])
            projection.neutrals = int(metric["passives"])
            projection.detractors = int(metric["detractors"])
            projection.inserted_by = self.user.full_name
            projection.source_type = "SEI_SURVEY"
            projection.survey_run_id = run_id
            projection.survey_question_id = question_id
        run.run_kind = "faculty_nps"
        run.semester = effective_semester
        self.db.flush()
        self._audit("sync", "survey_nps_faculty", source.id, {
            "semester": effective_semester,
            "run_id": run_id,
            "question_id": question_id,
            "respondents": int(metric["total"]),
            "anonymous_population": True,
        })
        self.db.commit()
        return {
            "ok": True,
            "nps_scope": "faculty",
            "semester": effective_semester,
            "run_id": run_id,
            "question_id": question_id,
            "question": question.text,
            "overall": self._nps_metric_payload(metric),
            "anonymous_population": True,
        }

    def faculty_nps_history(self) -> list[dict[str, Any]]:
        rows = list(self.db.scalars(
            select(NpsInstitutionFaculty).order_by(NpsInstitutionFaculty.period.desc())
        ).all())
        source_rows = list(self.db.execute(
            select(
                SurveyFacultyNpsSource,
                SurveyRun,
                SurveyQuestion,
                SurveyQuestionnaire,
                SurveyImport,
            )
            .join(SurveyRun, SurveyRun.id == SurveyFacultyNpsSource.run_id)
            .join(SurveyQuestion, SurveyQuestion.id == SurveyFacultyNpsSource.question_id)
            .join(SurveyQuestionnaire, SurveyQuestionnaire.id == SurveyRun.questionnaire_id)
            .join(SurveyImport, SurveyImport.id == SurveyRun.import_id)
        ).all())
        sources: dict[str, dict[str, Any]] = {}
        for source, run, question, questionnaire, imp in source_rows:
            # O indicador institucional continua global, mas metadados do arquivo/run
            # só podem ser expostos à diretoria proprietária daquele objeto.
            if self.directorate_id not in survey_run_owner_ids(self.db, run):
                continue
            sources[source.semester] = {
                "run_id": run.id,
                "question_id": question.id,
                "question": question.text,
                "questionnaire": questionnaire.name,
                "title": run.title,
                "period_start": run.period_start,
                "period_end": run.period_end,
                "origin": imp.origin,
                "source_filename": imp.source_filename,
                "created_at": str(source.created_at) if source.created_at else None,
            }
        out: list[dict[str, Any]] = []
        for row in rows:
            source = sources.get(row.period, {})
            respondents = int(row.respondents or 0)
            promoters = int(row.promoters or 0)
            neutrals = int(row.neutrals or 0)
            detractors = int(row.detractors or 0)
            score = round((promoters - detractors) / respondents * 100, 2) if respondents else None
            out.append({
                "id": row.id,
                "periodo": row.period,
                "valor": score,
                "respondentes": respondents,
                "promotores": promoters,
                "neutros": neutrals,
                "detratores": detractors,
                "fonte": "SEI · NPS institucional dos docentes",
                "data_lancamento": str(row.inserted_at.date()) if row.inserted_at else None,
                "anonymous_population": True,
                **source,
            })
        return out

    def faculty_nps_source_history(self) -> list[dict[str, Any]]:
        return [
            {
                "semester": item.get("periodo"),
                "run_id": item.get("run_id"),
                "question_id": item.get("question_id"),
                "question": item.get("question"),
                "questionnaire": item.get("questionnaire"),
                "title": item.get("title"),
                "period_start": item.get("period_start"),
                "period_end": item.get("period_end"),
                "origin": item.get("origin"),
                "source_filename": item.get("source_filename"),
            }
            for item in self.faculty_nps_history()
        ]

    def _get_or_create_teacher(self, name: str, external_id: str | None = None) -> Teacher:
        display = " ".join(str(name or "").split())
        key = normalize_key(display)
        if not key:
            raise SurveyIntegrationError("O contexto docente não informou o professor.")
        row = None
        if external_id:
            row = self.db.scalar(select(Teacher).where(Teacher.external_id == str(external_id)))
        if not row:
            row = self.db.scalar(select(Teacher).where(Teacher.normalized_name == key))
        if row:
            row.display_name = display
            if external_id and not row.external_id:
                row.external_id = str(external_id)
            row.active = True
            return row
        row = Teacher(
            external_id=str(external_id) if external_id else None,
            display_name=display,
            normalized_name=key,
            active=True,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _get_or_create_discipline(self, course_id: int, name: str) -> Discipline:
        display = " ".join(str(name or "").split())
        if not display:
            raise SurveyIntegrationError("O contexto docente não informou a disciplina.")
        key = normalize_key(display)
        rows = list(self.db.scalars(select(Discipline).where(Discipline.course_id == course_id)).all())
        for row in rows:
            if normalize_key(row.name) == key:
                row.active = True
                return row
        row = Discipline(course_id=course_id, name=display, active=True)
        self.db.add(row)
        self.db.flush()
        return row

    def _get_or_create_offering(
        self,
        *,
        period: str,
        course_id: int,
        discipline_id: int,
        class_group: str,
        external_id: str | None = None,
    ) -> AcademicOffering:
        class_group = " ".join(str(class_group or "").split())
        row = None
        if external_id:
            row = self.db.scalar(select(AcademicOffering).where(AcademicOffering.external_id == str(external_id)))
        if not row:
            row = self.db.scalar(select(AcademicOffering).where(
                AcademicOffering.period == period,
                AcademicOffering.course_id == course_id,
                AcademicOffering.discipline_id == discipline_id,
                AcademicOffering.class_group == class_group,
            ))
        if row:
            if external_id and not row.external_id:
                row.external_id = str(external_id)
            return row
        row = AcademicOffering(
            period=period,
            course_id=course_id,
            discipline_id=discipline_id,
            class_group=class_group,
            external_id=str(external_id) if external_id else None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _get_or_create_assignment(
        self,
        *,
        offering_id: int,
        teacher_id: int,
        external_id: str | None = None,
    ) -> TeachingAssignment:
        row = None
        if external_id:
            row = self.db.scalar(select(TeachingAssignment).where(TeachingAssignment.external_id == str(external_id)))
        if not row:
            row = self.db.scalar(select(TeachingAssignment).where(
                TeachingAssignment.offering_id == offering_id,
                TeachingAssignment.teacher_id == teacher_id,
            ))
        if row:
            if external_id and not row.external_id:
                row.external_id = str(external_id)
            return row
        row = TeachingAssignment(
            offering_id=offering_id,
            teacher_id=teacher_id,
            external_id=str(external_id) if external_id else None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def import_faculty_contexts(
        self,
        *,
        sha256: str,
        source_filename: str,
        source_kind: str,
        contexts: list[ParsedFacultyContext],
        semester_override: str | None = None,
        origin: str = "sei",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Destino estável do futuro adaptador do relatório docente do SEI.

        O método já persiste várias combinações docente × disciplina × turma do
        mesmo curso e semestre. Nenhum layout XLSX é assumido aqui; quando um
        relatório real existir, o adaptador precisará apenas produzir
        ``ParsedFacultyContext``.
        """
        if not contexts:
            raise SurveyIntegrationError("Nenhum contexto docente foi informado.")
        metadata = metadata or {}
        first = contexts[0]
        semester = _semester_to_data_univc(semester_override or first.semester_suggested)
        if not semester:
            raise SurveyIntegrationError("A avaliação docente precisa de um semestre AAAA-SEM1 ou AAAA-SEM2.")

        external_key = self.external_import_key(origin, metadata)
        imp = None
        if external_key:
            imp = self.db.scalar(select(SurveyImport).where(SurveyImport.directorate_id == self.directorate_id, SurveyImport.external_key == external_key))
        if not imp:
            imp = self.db.scalar(select(SurveyImport).where(SurveyImport.directorate_id == self.directorate_id, SurveyImport.sha256 == sha256))

        if imp:
            run = self.db.scalar(select(SurveyRun).where(SurveyRun.import_id == imp.id))
            if not run:
                raise SurveyIntegrationError("Importação docente existente sem survey_run correspondente.")
            require_survey_run_for_directorate(self.db, run.id, self.directorate_id)
            run.semester = semester
            run.run_kind = "faculty"
            imp.source_filename = source_filename
            imp.origin = origin
            if metadata:
                imp.metadata_json = metadata
            if external_key and not imp.external_key:
                imp.external_key = external_key
        else:
            imp = SurveyImport(
                id=uuid.uuid4().hex,
                directorate_id=self.directorate_id,
                source_filename=source_filename,
                sha256=sha256,
                source_kind=source_kind,
                origin=origin,
                external_key=external_key,
                metadata_json=metadata or None,
                status="processing",
            )
            self.db.add(imp)
            questionnaire = self._get_or_create_questionnaire(
                first.questionnaire_name or first.survey_title or "Avaliação docente",
                metadata.get("selected_questionnaire_id"),
            )
            run = SurveyRun(
                import_id=imp.id,
                directorate_id=self.directorate_id,
                questionnaire_id=questionnaire.id,
                title=first.survey_title,
                period_start=first.period_start,
                period_end=first.period_end,
                semester=semester,
                run_kind="faculty",
            )
            self.db.add(run)
            self.db.flush()

        imported: list[str] = []
        skipped: list[str] = []
        unmapped: list[dict[str, str]] = []
        for parsed in contexts:
            context_semester = _semester_to_data_univc(semester_override or parsed.semester_suggested or semester)
            if context_semester != semester:
                raise SurveyIntegrationError("Todos os contextos da mesma importação docente precisam pertencer ao mesmo semestre.")
            match = self.match_course(parsed.course_name, parsed.modality)
            if not match.get("matched"):
                unmapped.append({"source_key": parsed.source_key, "course": parsed.course_name, "reason": match.get("reason") or "Não mapeado"})
                continue
            course_id = int(match["course_id"])
            discipline = self._get_or_create_discipline(course_id, parsed.discipline_name)
            teacher = self._get_or_create_teacher(parsed.teacher_name, parsed.teacher_external_id)
            offering = self._get_or_create_offering(
                period=semester,
                course_id=course_id,
                discipline_id=discipline.id,
                class_group=parsed.class_code or "",
                external_id=parsed.offering_external_id,
            )
            assignment = self._get_or_create_assignment(
                offering_id=offering.id,
                teacher_id=teacher.id,
                external_id=parsed.assignment_external_id,
            )
            existing = self.db.scalar(select(FacultyEvaluationContext).where(
                FacultyEvaluationContext.run_id == run.id,
                FacultyEvaluationContext.teaching_assignment_id == assignment.id,
                FacultyEvaluationContext.source_key == parsed.source_key,
            ))
            if existing:
                skipped.append(parsed.source_key)
                continue
            context = FacultyEvaluationContext(
                run_id=run.id,
                teaching_assignment_id=assignment.id,
                source_key=parsed.source_key,
                source_path=parsed.source_path,
                respondent_count=max(0, int(parsed.respondent_count or 0)),
            )
            self.db.add(context)
            self.db.flush()
            for question in parsed.questions:
                qrow = self._get_or_create_question(run.questionnaire_id, question)
                for option in question.options:
                    self.db.add(FacultyResponseAggregate(
                        context_id=context.id,
                        question_id=qrow.id,
                        option_label=option.label,
                        option_key=normalize_key(option.label),
                        numeric_value=option.numeric_value,
                        response_count=max(0, int(option.count or 0)),
                        source_percentage=option.source_percentage,
                    ))
                for response_text in question.raw_responses:
                    self.db.add(FacultyRawResponse(
                        context_id=context.id,
                        question_id=qrow.id,
                        response_text=response_text,
                        response_key=normalize_key(response_text),
                    ))
            imported.append(parsed.source_key)

        imp.status = "completed"
        self._audit("import", "survey_faculty", run.id, {
            "semester": semester,
            "imported": len(imported),
            "skipped": len(skipped),
            "unmapped": len(unmapped),
        })
        self.db.commit()
        return {
            "import_id": imp.id,
            "run_id": run.id,
            "semester": semester,
            "imported_contexts": imported,
            "skipped_contexts": skipped,
            "unmapped": unmapped,
        }

    def faculty_metric(
        self,
        *,
        question_id: int,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
        offering_id: int | None = None,
    ) -> dict[str, Any]:
        q = (
            select(
                FacultyResponseAggregate.option_label,
                FacultyResponseAggregate.numeric_value,
                func.sum(FacultyResponseAggregate.response_count).label("response_count"),
            )
            .join(FacultyEvaluationContext, FacultyEvaluationContext.id == FacultyResponseAggregate.context_id)
            .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContext.teaching_assignment_id)
            .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
            .join(Course, Course.id == AcademicOffering.course_id)
            .where(
                FacultyResponseAggregate.question_id == question_id,
                Course.directorate_id == self.directorate_id,
            )
        )
        if semester:
            q = q.where(AcademicOffering.period == _semester_to_data_univc(semester))
        if course_id is not None:
            q = q.where(AcademicOffering.course_id == course_id)
        if discipline_id is not None:
            q = q.where(AcademicOffering.discipline_id == discipline_id)
        if teacher_id is not None:
            q = q.where(TeachingAssignment.teacher_id == teacher_id)
        if offering_id is not None:
            q = q.where(AcademicOffering.id == offering_id)
        q = q.group_by(FacultyResponseAggregate.option_label, FacultyResponseAggregate.numeric_value)
        rows = [dict(row._mapping) for row in self.db.execute(q).all()]
        question = self.db.get(SurveyQuestion, question_id)
        if not question:
            raise SurveyIntegrationError("Pergunta docente não encontrada.")
        dist = distribution(rows)
        return {
            "question_id": question_id,
            "question": question.text,
            "detected_metric_type": question.detected_metric_type,
            "distribution": dist,
            "metric": metric_summary(question.detected_metric_type, dist),
            "filters": {
                "semester": semester,
                "course_id": course_id,
                "discipline_id": discipline_id,
                "teacher_id": teacher_id,
                "offering_id": offering_id,
            },
        }

    def faculty_readiness(self) -> dict[str, Any]:
        course_scope = Course.directorate_id == self.directorate_id
        counts = {
            "academic_offerings": int(self.db.scalar(
                select(func.count(AcademicOffering.id))
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(course_scope)
            ) or 0),
            "teaching_assignments": int(self.db.scalar(
                select(func.count(TeachingAssignment.id))
                .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(course_scope)
            ) or 0),
            "faculty_evaluation_contexts": int(self.db.scalar(
                select(func.count(FacultyEvaluationContext.id))
                .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContext.teaching_assignment_id)
                .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(course_scope)
            ) or 0),
            "faculty_response_aggregates": int(self.db.scalar(
                select(func.count(FacultyResponseAggregate.id))
                .join(FacultyEvaluationContext, FacultyEvaluationContext.id == FacultyResponseAggregate.context_id)
                .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContext.teaching_assignment_id)
                .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(course_scope)
            ) or 0),
            "faculty_raw_responses": int(self.db.scalar(
                select(func.count(FacultyRawResponse.id))
                .join(FacultyEvaluationContext, FacultyEvaluationContext.id == FacultyRawResponse.context_id)
                .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContext.teaching_assignment_id)
                .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(course_scope)
            ) or 0),
            "teachers": int(self.db.scalar(
                select(func.count(func.distinct(TeachingAssignment.teacher_id)))
                .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
                .join(Course, Course.id == AcademicOffering.course_id)
                .where(course_scope)
            ) or 0),
        }
        return {
            "status": "architecture_ready",
            "parser_adapter": "pending_real_faculty_report",
            "message": (
                "Professor, disciplina, turma/oferta, curso e semestre já possuem uma estrutura relacional. "
                "O adaptador do relatório docente permanece pendente até existir um XLSX/ZIP real do SEI."
            ),
            "counts": counts,
        }
