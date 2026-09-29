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
    FacultyEvaluationContextScope,
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
from academic_catalog import course_aliases, is_ambiguous_course_name
from survey_metrics import distribution, metric_summary, nps_score
from survey_faculty_analytics import (
    classify_faculty_question,
    distribution_with_classification,
    faculty_favorability_methodology,
    favorability_summary,
)
from analytics import active_goal, goal_info, status_for
from survey_models import ParsedQuestion, ParsedWorkbook
from survey_faculty_models import ParsedFacultyContext
from survey_faculty_student import faculty_context_semantic_key
from survey_faculty_identity import (
    class_group_display,
    clean_identity_display,
    discipline_identity_key,
    faculty_academic_identity_key,
    teacher_identity_key,
)
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

    def course_options(self) -> list[dict[str, Any]]:
        """Cursos ativos da diretoria disponíveis para escopos compartilhados."""
        return [self._course_payload(course) for course in self._course_candidates() if bool(course.active)]

    def match_course_for_source(
        self,
        name: str,
        modality: str | None = None,
        *,
        origin: str = "manual",
    ) -> dict[str, Any]:
        """Resolve aliases que pertencem ao contrato de uma fonte específica.

        O SEI atual passou a expor a Licenciatura de Educação Física simplesmente
        como ``Educação Física`` enquanto o Bacharelado continua identificado como
        ``Educação Física (Bac. Presencial)``. Essa regra não vira alias global:
        uploads manuais/legados continuam exigindo resolução explícita.
        """
        if (
            str(origin or "").casefold() == "sei"
            and self.directorate_code == "DCS"
            and normalize_key(name) == normalize_key("Educação Física")
        ):
            target = next(
                (course for course in self._course_candidates()
                 if normalize_key(course.name) == normalize_key("Educação Física - Licenciatura")),
                None,
            )
            if target is not None:
                modality_norm = normalize_key(modality or "")
                if modality_norm and normalize_key(target.modality or "") != modality_norm:
                    return {
                        "matched": False,
                        "reason": (
                            f"Educação Física foi reconhecida como Licenciatura pelo SEI atual, "
                            f"mas a modalidade do relatório ({modality or 'não informada'}) não corresponde ao catálogo."
                        ),
                        "candidates": [target.name],
                        "candidate_ids": [int(target.id)],
                        "candidate_courses": [self._course_payload(target)],
                        "resolution_required": False,
                    }
                return {
                    "matched": True,
                    "course_id": int(target.id),
                    "course_name": target.name,
                    "modality": target.modality or "Presencial",
                    "match_type": "source_alias",
                    "resolution_source": "sei_current_label",
                    "raw_course_name": clean_identity_display(name),
                }
        return self.match_course(name, modality)

    def _find_faculty_run_by_identity(
        self,
        *,
        survey_title: str | None,
        questionnaire_name: str | None,
        period_start: str | None,
        period_end: str | None,
        semester: str | None = None,
    ) -> SurveyRun | None:
        """Localiza uma avaliação docente já existente pela identidade lógica.

        Isso protege também o upload manual de um ZIP regenerado pelo SEI: o
        timestamp/ID interno pode alterar o SHA-256 sem criar uma nova aplicação
        de questionário. A correspondência exige questionário e título/período e
        só é aceita quando resulta em um único survey run.
        """

        questionnaire_key = normalize_key(questionnaire_name or "")
        title_key = normalize_key(survey_title or "")
        if not questionnaire_key or not (title_key or period_start or period_end):
            return None
        stmt = (
            select(SurveyRun)
            .join(SurveyQuestionnaire, SurveyQuestionnaire.id == SurveyRun.questionnaire_id)
            .where(
                SurveyRun.directorate_id == self.directorate_id,
                SurveyRun.run_kind == "faculty",
            )
        )
        if semester:
            stmt = stmt.where(SurveyRun.semester == semester)
        if period_start:
            stmt = stmt.where(SurveyRun.period_start == period_start)
        if period_end:
            stmt = stmt.where(SurveyRun.period_end == period_end)
        candidates = list(self.db.scalars(stmt).all())
        matches = [
            run
            for run in candidates
            if normalize_key(run.questionnaire.name if run.questionnaire else "") == questionnaire_key
            and (not title_key or normalize_key(run.title or "") == title_key)
        ]
        return matches[0] if len(matches) == 1 else None

    def faculty_import_state(
        self,
        *,
        sha256: str,
        origin: str = "manual",
        metadata: dict | None = None,
        survey_identity: dict | None = None,
    ) -> dict[str, Any]:
        """Retorna o estado já persistido da mesma fonte docente nesta diretoria.

        A busca usa primeiro a identidade externa do SEI, quando disponível, e
        depois o SHA-256 do upload. Os contextos são expostos também por uma
        chave semântica curso + professor + disciplina para detectar reexportações
        do mesmo relatório mesmo quando o ID/nome interno do XLSX mudar.
        """

        metadata = metadata or {}
        external_key = self.external_import_key(origin, metadata)
        imp = None
        if external_key:
            imp = self.db.scalar(select(SurveyImport).where(
                SurveyImport.directorate_id == self.directorate_id,
                SurveyImport.external_key == external_key,
            ))
        if not imp:
            imp = self.db.scalar(select(SurveyImport).where(
                SurveyImport.directorate_id == self.directorate_id,
                SurveyImport.sha256 == sha256,
            ))

        run = None
        identity = survey_identity or {}
        if not imp and identity:
            run = self._find_faculty_run_by_identity(
                survey_title=identity.get("survey_title"),
                questionnaire_name=identity.get("questionnaire_name"),
                period_start=identity.get("period_start"),
                period_end=identity.get("period_end"),
                semester=_semester_to_data_univc(identity.get("semester")),
            )
            if run:
                imp = self.db.scalar(select(SurveyImport).where(SurveyImport.id == run.import_id))
        if not imp:
            return {
                "exists": False,
                "context_count": 0,
                "source_keys": [],
                "semantic_keys": [],
            }

        if run is None:
            run = self.db.scalar(select(SurveyRun).where(SurveyRun.import_id == imp.id))
        if not run:
            return {
                "exists": True,
                "import_id": imp.id,
                "run_id": None,
                "semester": None,
                "status": imp.status,
                "context_count": 0,
                "source_keys": [],
                "semantic_keys": [],
            }
        require_survey_run_for_directorate(self.db, run.id, self.directorate_id)
        rows = self.db.execute(
            select(
                FacultyEvaluationContext.source_key,
                Course.name,
                Teacher.display_name,
                Discipline.name,
                AcademicOffering.class_group,
            )
            .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContext.teaching_assignment_id)
            .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
            .join(Course, Course.id == AcademicOffering.course_id)
            .join(Discipline, Discipline.id == AcademicOffering.discipline_id)
            .join(Teacher, Teacher.id == TeachingAssignment.teacher_id)
            .where(FacultyEvaluationContext.run_id == run.id)
        ).all()
        source_keys = sorted({str(row[0]) for row in rows if row[0]})
        semantic_keys = sorted({
            faculty_context_semantic_key(row[1], row[2], row[3], row[4])
            for row in rows
        })
        return {
            "exists": True,
            "import_id": imp.id,
            "run_id": run.id,
            "semester": run.semester,
            "status": imp.status,
            "context_count": len(rows),
            "source_keys": source_keys,
            "semantic_keys": semantic_keys,
        }

    @staticmethod
    def _course_payload(course: Course) -> dict[str, Any]:
        return {
            "course_id": int(course.id),
            "course_name": course.name,
            "modality": course.modality or "Presencial",
            "active": bool(course.active),
        }

    def match_course(self, name: str, modality: str | None = None) -> dict[str, Any]:
        """Resolve curso somente por identidade exata/alias institucional.

        Nenhuma similaridade textual ou substring ampla é usada. Quando mais de
        um curso é possível, o retorno carrega os IDs permitidos para que a
        resolução posterior seja explícita e auditável por contexto.
        """

        target = normalize_key(name)
        if not target:
            return {"matched": False, "reason": "Nome do curso ausente", "candidates": [], "candidate_courses": []}

        if is_ambiguous_course_name(name, self.directorate_code):
            candidate_rows = [
                course
                for course in self._course_candidates()
                if normalize_key(course.name).startswith(normalize_key("Educação Física"))
            ]
            payloads = [self._course_payload(course) for course in candidate_rows]
            return {
                "matched": False,
                "reason": (
                    "O relatório usa o nome ambíguo 'Educação Física'. "
                    "É necessário identificar Bacharelado ou Licenciatura antes da importação."
                ),
                "candidates": [item["course_name"] for item in payloads],
                "candidate_ids": [item["course_id"] for item in payloads],
                "candidate_courses": payloads,
                "resolution_required": True,
                "resolution_type": "course_identity",
            }

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
                payloads = [self._course_payload(course) for course in candidates]
                return {
                    "matched": False,
                    "reason": f"Curso encontrado, mas a modalidade do relatório ({modality or 'não informada'}) não corresponde ao catálogo desta diretoria.",
                    "candidates": [item["course_name"] for item in payloads],
                    "candidate_ids": [item["course_id"] for item in payloads],
                    "candidate_courses": payloads,
                    "resolution_required": False,
                }

        if len(candidates) == 1:
            course = candidates[0]
            return {
                "matched": True,
                "course_id": int(course.id),
                "course_name": course.name,
                "modality": course.modality or "Presencial",
                "match_type": "exact" if exact else "alias",
                "resolution_source": "catalog",
            }

        if len(candidates) > 1:
            payloads = [self._course_payload(course) for course in candidates]
            return {
                "matched": False,
                "reason": "Mais de um curso do catálogo corresponde ao nome do relatório.",
                "candidates": [item["course_name"] for item in payloads],
                "candidate_ids": [item["course_id"] for item in payloads],
                "candidate_courses": payloads,
                "resolution_required": True,
                "resolution_type": "course_identity",
            }

        return {
            "matched": False,
            "reason": "Curso não encontrado no catálogo desta diretoria.",
            "candidates": [],
            "candidate_ids": [],
            "candidate_courses": [],
            "resolution_required": False,
        }

    def resolve_course(
        self,
        name: str,
        modality: str | None = None,
        *,
        explicit_course_id: int | None = None,
        origin: str = "manual",
    ) -> dict[str, Any]:
        """Aplica uma resolução manual somente quando o preview a autoriza.

        O ID escolhido precisa pertencer à mesma diretoria e estar entre os
        candidatos calculados para aquele rótulo. Isso impede que um override
        transforme qualquer curso desconhecido em outro curso arbitrário.
        """

        automatic = self.match_course_for_source(name, modality, origin=origin)
        if explicit_course_id is None:
            return automatic

        try:
            requested_id = int(explicit_course_id)
        except (TypeError, ValueError) as exc:
            raise SurveyIntegrationError("A resolução manual do curso precisa informar um course_id válido.") from exc

        course = self.db.scalar(select(Course).where(
            Course.id == requested_id,
            Course.directorate_id == self.directorate_id,
        ))
        if not course:
            raise SurveyIntegrationError("O curso escolhido para resolução não pertence a esta diretoria.")

        if automatic.get("matched"):
            if int(automatic.get("course_id")) != requested_id:
                raise SurveyIntegrationError(
                    "O relatório já possui uma identidade de curso inequívoca; não é permitido substituí-la manualmente."
                )
            return {**automatic, "resolution_source": "explicit_confirmation"}

        if not automatic.get("resolution_required"):
            raise SurveyIntegrationError(
                "Este curso não possui uma ambiguidade resolvível pelo catálogo. "
                "Ajuste o catálogo/alias institucional antes de importar."
            )

        candidate_ids = {int(value) for value in automatic.get("candidate_ids") or []}
        if requested_id not in candidate_ids:
            raise SurveyIntegrationError(
                "O curso escolhido não está entre as opções permitidas para este relatório."
            )

        modality_norm = normalize_key(modality or "")
        if modality_norm and normalize_key(course.modality or "") != modality_norm:
            raise SurveyIntegrationError(
                "A modalidade do curso escolhido não corresponde à modalidade identificada no relatório."
            )

        return {
            "matched": True,
            "course_id": int(course.id),
            "course_name": course.name,
            "modality": course.modality or "Presencial",
            "match_type": "manual_resolution",
            "resolution_source": "user",
            "raw_course_name": clean_identity_display(name),
            "candidate_ids": sorted(candidate_ids),
        }

    def inspect_entries(
        self, entries: list[dict[str, Any]], *, origin: str = "manual"
    ) -> list[dict[str, Any]]:
        enriched = []
        for item in entries:
            match = self.match_course_for_source(
                str(item.get("course_name") or ""),
                str(item.get("modality") or ""),
                origin=origin,
            )
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
        course_resolutions: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        if not workbooks:
            raise SurveyIntegrationError("Nenhum relatório foi selecionado para importação.")
        metadata = metadata or {}
        course_resolutions = {str(key): int(value) for key, value in (course_resolutions or {}).items()}
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
            match = self.resolve_course(
                parsed.course_name,
                parsed.modality,
                explicit_course_id=course_resolutions.get(parsed.source_path),
                origin=origin,
            )
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
            "course_resolutions_applied": len(course_resolutions),
        })
        self.db.commit()
        return {
            "import_id": imp.id,
            "run_id": run.id,
            "semester": semester,
            "imported_files": imported,
            "skipped_files": skipped,
            "unmapped": unmapped,
            "course_resolutions_applied": len(course_resolutions),
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
        display = clean_identity_display(name)
        key = teacher_identity_key(display)
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

    def _get_or_create_discipline(self, course_id: int, name: str, period: str) -> Discipline:
        display = clean_identity_display(name)
        if not display:
            raise SurveyIntegrationError("O contexto docente não informou a disciplina.")
        key = discipline_identity_key(display)
        rows = list(self.db.scalars(select(Discipline).where(Discipline.course_id == course_id)).all())
        for row in rows:
            if discipline_identity_key(row.name) == key:
                row.active = True
                return row
        valid_from = None
        period_text = str(period or "").strip().upper()
        if len(period_text) >= 4 and period_text[:4].isdigit():
            valid_from = f"{period_text[:4]}-{'07' if period_text.endswith('SEM2') else '01'}"
        if not valid_from:
            raise SurveyIntegrationError("Não foi possível definir a vigência inicial da disciplina docente.")
        row = Discipline(course_id=course_id, name=display, active=True, valid_from=valid_from)
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
        class_group = class_group_display(class_group)
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
        course_resolutions: dict[str, int] | None = None,
        shared_course_scopes: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        """Persiste os contextos normalizados do relatório docente do SEI.

        Suporta várias combinações docente × disciplina × curso no mesmo semestre
        e preserva as distribuições das respostas por pergunta. O parser do
        relatório ``Disciplina/Professor`` é responsável apenas por produzir
        ``ParsedFacultyContext``; esta camada continua independente do layout XLSX.
        """
        if not contexts:
            raise SurveyIntegrationError("Nenhum contexto docente foi informado.")
        metadata = metadata or {}
        course_resolutions = {str(key): int(value) for key, value in (course_resolutions or {}).items()}
        shared_course_scopes = {
            str(key): sorted({int(value) for value in (values or [])})
            for key, values in (shared_course_scopes or {}).items()
        }
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
        logical_run = None
        if not imp:
            logical_run = self._find_faculty_run_by_identity(
                survey_title=first.survey_title,
                questionnaire_name=first.questionnaire_name,
                period_start=first.period_start,
                period_end=first.period_end,
                semester=semester,
            )
            if logical_run:
                imp = self.db.scalar(select(SurveyImport).where(SurveyImport.id == logical_run.import_id))

        if imp:
            run = logical_run or self.db.scalar(select(SurveyRun).where(SurveyRun.import_id == imp.id))
            if not run:
                raise SurveyIntegrationError("Importação docente existente sem survey_run correspondente.")
            require_survey_run_for_directorate(self.db, run.id, self.directorate_id)
            existing_contexts = int(self.db.scalar(
                select(func.count(FacultyEvaluationContext.id)).where(FacultyEvaluationContext.run_id == run.id)
            ) or 0)
            if existing_contexts and run.semester and run.semester != semester:
                raise SurveyIntegrationError(
                    "Esta fonte docente já foi importada em outro semestre. "
                    "Para preservar o histórico, não é permitido mover contextos existentes entre semestres."
                )
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
        unmapped: list[dict[str, Any]] = []
        applied_resolutions: list[dict[str, Any]] = []
        for parsed in contexts:
            context_semester = _semester_to_data_univc(semester_override or parsed.semester_suggested or semester)
            if context_semester != semester:
                raise SurveyIntegrationError("Todos os contextos da mesma importação docente precisam pertencer ao mesmo semestre.")
            explicit_course_id = course_resolutions.get(parsed.source_path)
            match = self.resolve_course(
                parsed.course_name,
                parsed.modality,
                explicit_course_id=explicit_course_id,
                origin=origin,
            )
            if not match.get("matched"):
                unmapped.append({
                    "source_key": parsed.source_key,
                    "source_path": parsed.source_path,
                    "course": parsed.course_name,
                    "reason": match.get("reason") or "Não mapeado",
                    "resolution_required": bool(match.get("resolution_required")),
                    "candidate_courses": match.get("candidate_courses") or [],
                })
                continue

            primary_course_id = int(match["course_id"])
            requested_extra_ids = [
                int(value) for value in shared_course_scopes.get(parsed.source_path, [])
                if int(value) != primary_course_id
            ]
            scope_courses: list[Course] = []
            for scope_course_id in [primary_course_id, *requested_extra_ids]:
                course = self.db.scalar(select(Course).where(
                    Course.id == int(scope_course_id),
                    Course.directorate_id == self.directorate_id,
                    Course.active.is_(True),
                ))
                if not course:
                    raise SurveyIntegrationError(
                        f"{parsed.source_path}: um dos cursos da turma compartilhada não pertence à diretoria ou está inativo."
                    )
                if not any(int(existing.id) == int(course.id) for existing in scope_courses):
                    scope_courses.append(course)

            if match.get("match_type") == "manual_resolution":
                applied_resolutions.append({
                    "source_path": parsed.source_path,
                    "source_key": parsed.source_key,
                    "raw_course_name": parsed.course_name,
                    "course_id": primary_course_id,
                    "course_name": match.get("course_name"),
                    "resolution_type": "primary_course",
                })

            teacher = self._get_or_create_teacher(parsed.teacher_name, parsed.teacher_external_id)
            assignments: list[tuple[Course, TeachingAssignment]] = []
            for scope_course in scope_courses:
                discipline = self._get_or_create_discipline(int(scope_course.id), parsed.discipline_name, semester)
                offering = self._get_or_create_offering(
                    period=semester,
                    course_id=int(scope_course.id),
                    discipline_id=discipline.id,
                    class_group=parsed.class_code or "",
                    external_id=parsed.offering_external_id if int(scope_course.id) == primary_course_id else None,
                )
                assignment = self._get_or_create_assignment(
                    offering_id=offering.id,
                    teacher_id=teacher.id,
                    external_id=parsed.assignment_external_id if int(scope_course.id) == primary_course_id else None,
                )
                assignments.append((scope_course, assignment))

            primary_assignment = next(
                assignment for course, assignment in assignments if int(course.id) == primary_course_id
            )
            # O vínculo principal permanece para compatibilidade. Os demais cursos
            # ficam em faculty_evaluation_context_scopes e não duplicam respostas.
            existing = self.db.scalar(select(FacultyEvaluationContext).where(
                FacultyEvaluationContext.run_id == run.id,
                FacultyEvaluationContext.teaching_assignment_id == primary_assignment.id,
            ).order_by(FacultyEvaluationContext.id))
            if existing:
                for scope_course, assignment in assignments:
                    scope_row = self.db.scalar(select(FacultyEvaluationContextScope).where(
                        FacultyEvaluationContextScope.context_id == existing.id,
                        FacultyEvaluationContextScope.teaching_assignment_id == assignment.id,
                    ))
                    if not scope_row:
                        self.db.add(FacultyEvaluationContextScope(
                            context_id=existing.id,
                            teaching_assignment_id=assignment.id,
                            is_primary=int(assignment.id) == int(primary_assignment.id),
                            resolution_source=(
                                match.get("resolution_source") or "catalog"
                                if int(assignment.id) == int(primary_assignment.id)
                                else "shared_course_user"
                            ),
                            created_by=self.user.email,
                        ))
                skipped.append(parsed.source_key)
                continue

            context = FacultyEvaluationContext(
                run_id=run.id,
                teaching_assignment_id=primary_assignment.id,
                source_key=parsed.source_key,
                source_path=parsed.source_path,
                respondent_count=max(0, int(parsed.respondent_count or 0)),
            )
            self.db.add(context)
            self.db.flush()
            for scope_course, assignment in assignments:
                self.db.add(FacultyEvaluationContextScope(
                    context_id=context.id,
                    teaching_assignment_id=assignment.id,
                    is_primary=int(assignment.id) == int(primary_assignment.id),
                    resolution_source=(
                        (match.get("resolution_source") or "catalog")
                        if int(assignment.id) == int(primary_assignment.id)
                        else "shared_course_user"
                    ),
                    created_by=self.user.email,
                ))
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
            if len(scope_courses) > 1:
                applied_resolutions.append({
                    "source_path": parsed.source_path,
                    "source_key": parsed.source_key,
                    "primary_course_id": primary_course_id,
                    "course_ids": [int(course.id) for course in scope_courses],
                    "course_names": [course.name for course in scope_courses],
                    "resolution_type": "shared_course_scope",
                })
            imported.append(parsed.source_key)

        if applied_resolutions:
            merged_metadata = dict(imp.metadata_json or {})
            merged_metadata["faculty_course_resolutions"] = applied_resolutions
            imp.metadata_json = merged_metadata

        imp.status = "completed"
        self._audit("import", "survey_faculty", run.id, {
            "semester": semester,
            "imported": len(imported),
            "skipped": len(skipped),
            "unmapped": len(unmapped),
            "course_resolutions_applied": len(applied_resolutions),
            "shared_course_contexts": sum(1 for item in applied_resolutions if item.get("resolution_type") == "shared_course_scope"),
        })
        self.db.commit()
        return {
            "import_id": imp.id,
            "run_id": run.id,
            "semester": semester,
            "imported_contexts": imported,
            "skipped_contexts": skipped,
            "unmapped": unmapped,
            "course_resolutions_applied": applied_resolutions,
            "shared_course_contexts": [
                item for item in applied_resolutions if item.get("resolution_type") == "shared_course_scope"
            ],
        }

    def faculty_import_history(self) -> dict[str, Any]:
        """Lista lotes persistidos da Avaliação Docente da diretoria atual.

        A consulta e somente leitura e reutiliza survey_imports/survey_runs; nao
        cria uma tabela paralela para o frontend. A contagem de contextos usa
        subquery correlacionada para manter compatibilidade com PostgreSQL JSON.
        """

        context_count = (
            select(func.count(FacultyEvaluationContext.id))
            .where(FacultyEvaluationContext.run_id == SurveyRun.id)
            .correlate(SurveyRun)
            .scalar_subquery()
        )
        stmt = (
            select(
                SurveyImport.id.label("import_id"),
                SurveyImport.source_filename.label("source_filename"),
                SurveyImport.source_kind.label("source_kind"),
                SurveyImport.origin.label("origin"),
                SurveyImport.status.label("status"),
                SurveyImport.created_at.label("created_at"),
                SurveyImport.metadata_json.label("metadata_json"),
                SurveyRun.id.label("run_id"),
                SurveyRun.semester.label("semester"),
                SurveyRun.title.label("title"),
                SurveyRun.period_start.label("period_start"),
                SurveyRun.period_end.label("period_end"),
                SurveyQuestionnaire.name.label("questionnaire_name"),
                context_count.label("context_count"),
            )
            .join(SurveyRun, SurveyRun.import_id == SurveyImport.id)
            .join(SurveyQuestionnaire, SurveyQuestionnaire.id == SurveyRun.questionnaire_id)
            .where(
                SurveyImport.directorate_id == self.directorate_id,
                SurveyRun.directorate_id == self.directorate_id,
                SurveyRun.run_kind == "faculty",
            )
            .order_by(SurveyImport.created_at.desc(), SurveyImport.id.desc())
        )
        history_rows = list(self.db.execute(stmt).all())
        run_ids = [str(row._mapping["run_id"]) for row in history_rows]
        audit_by_run: dict[str, list[dict[str, Any]]] = {}
        if run_ids:
            audit_stmt = (
                select(
                    AuditLog.entity_id,
                    AuditLog.user_email,
                    AuditLog.details,
                    AuditLog.created_at,
                )
                .where(
                    AuditLog.directorate_id == self.directorate_id,
                    AuditLog.action == "import",
                    AuditLog.entity == "survey_faculty",
                    AuditLog.entity_id.in_(run_ids),
                )
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            )
            for entity_id, user_email, details, created_at in self.db.execute(audit_stmt).all():
                parsed_details: dict[str, Any] = {}
                if details:
                    try:
                        loaded = json.loads(details)
                        if isinstance(loaded, dict):
                            parsed_details = loaded
                    except (TypeError, ValueError, json.JSONDecodeError):
                        parsed_details = {}
                audit_by_run.setdefault(str(entity_id), []).append({
                    "user_email": user_email,
                    "created_at": created_at,
                    "details": parsed_details,
                })

        items: list[dict[str, Any]] = []
        for row in history_rows:
            data = dict(row._mapping)
            metadata = data.pop("metadata_json") or {}
            resolutions = metadata.get("faculty_course_resolutions") or []
            resolution_count = len(resolutions) if isinstance(resolutions, (list, dict)) else 0
            created = data.get("created_at")
            data["created_at"] = created.isoformat() if created else None
            data["context_count"] = int(data.get("context_count") or 0)
            data["course_resolution_count"] = resolution_count

            audits = audit_by_run.get(str(data.get("run_id")), [])
            latest_audit = audits[0] if audits else None
            data["import_attempts"] = len(audits)
            data["last_imported_by"] = latest_audit.get("user_email") if latest_audit else None
            data["last_activity_at"] = (
                latest_audit["created_at"].isoformat()
                if latest_audit and latest_audit.get("created_at")
                else data["created_at"]
            )
            details = latest_audit.get("details", {}) if latest_audit else {}
            data["last_import_result"] = {
                "imported": int(details.get("imported") or 0),
                "skipped": int(details.get("skipped") or 0),
                "unmapped": int(details.get("unmapped") or 0),
                "course_resolutions_applied": int(details.get("course_resolutions_applied") or 0),
            }
            items.append(data)
        return {"items": items, "count": len(items)}

    def faculty_identity_catalog(self, semester: str | None = None) -> dict[str, Any]:
        """Expõe a malha acadêmica persistida que alimentará o analytics.

        A resposta é relacional e não calcula nota/favorabilidade. Ela existe
        para auditar se semestre, curso, disciplina, professor e turma foram
        conectados corretamente antes da camada analítica.
        """

        effective_semester = _semester_to_data_univc(semester) if semester else None
        if semester and not effective_semester:
            raise SurveyIntegrationError("Semestre inválido. Use AAAA-SEM1 ou AAAA-SEM2.")

        stmt = (
            select(
                FacultyEvaluationContext.id,
                FacultyEvaluationContext.run_id,
                FacultyEvaluationContext.respondent_count,
                FacultyEvaluationContext.source_key,
                FacultyEvaluationContext.source_path,
                TeachingAssignment.id,
                AcademicOffering.id,
                AcademicOffering.period,
                AcademicOffering.class_group,
                Course.id,
                Course.name,
                Course.modality,
                Discipline.id,
                Discipline.name,
                Teacher.id,
                Teacher.display_name,
                Teacher.external_id,
                FacultyEvaluationContextScope.is_primary,
                FacultyEvaluationContextScope.resolution_source,
            )
            .join(FacultyEvaluationContextScope, FacultyEvaluationContextScope.context_id == FacultyEvaluationContext.id)
            .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContextScope.teaching_assignment_id)
            .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
            .join(Course, Course.id == AcademicOffering.course_id)
            .join(Discipline, Discipline.id == AcademicOffering.discipline_id)
            .join(Teacher, Teacher.id == TeachingAssignment.teacher_id)
            .where(Course.directorate_id == self.directorate_id)
        )
        if effective_semester:
            stmt = stmt.where(AcademicOffering.period == effective_semester)
        stmt = stmt.order_by(
            AcademicOffering.period.desc(),
            Course.name,
            Discipline.name,
            Teacher.display_name,
            FacultyEvaluationContext.id,
        )

        items: list[dict[str, Any]] = []
        for row in self.db.execute(stmt).all():
            (
                context_id, run_id, respondent_count, source_key, source_path,
                assignment_id, offering_id, period, class_group,
                course_id, course_name, modality, discipline_id, discipline_name,
                teacher_id, teacher_name, teacher_external_id,
                is_primary_scope, scope_resolution_source,
            ) = row
            items.append({
                "context_id": int(context_id),
                "run_id": int(run_id),
                "assignment_id": int(assignment_id),
                "offering_id": int(offering_id),
                "semester": period,
                "course_id": int(course_id),
                "course_name": course_name,
                "modality": modality,
                "discipline_id": int(discipline_id),
                "discipline_name": discipline_name,
                "teacher_id": int(teacher_id),
                "teacher_name": teacher_name,
                "teacher_external_id": teacher_external_id,
                "is_primary_scope": bool(is_primary_scope),
                "scope_resolution_source": scope_resolution_source,
                "class_group": class_group or "",
                "respondent_count": int(respondent_count or 0),
                "source_key": source_key,
                "source_path": source_path,
                "academic_identity_key": faculty_academic_identity_key(
                    period=period,
                    course_identity=course_id,
                    teacher_name=teacher_name,
                    discipline_name=discipline_name,
                    class_group=class_group or "",
                ),
            })

        return {
            "semester": effective_semester,
            "items": items,
            "summary": {
                "contexts": len(items),
                "semesters": len({item["semester"] for item in items}),
                "courses": len({item["course_id"] for item in items}),
                "disciplines": len({item["discipline_id"] for item in items}),
                "teachers": len({item["teacher_id"] for item in items}),
                "offerings": len({item["offering_id"] for item in items}),
                "assignments": len({item["assignment_id"] for item in items}),
                "respondents_across_contexts": sum(item["respondent_count"] for item in items),
            },
        }

    def faculty_identity_quality(self, semester: str | None = None) -> dict[str, Any]:
        """Diagnóstico estrutural da identidade acadêmica já persistida."""

        catalog = self.faculty_identity_catalog(semester)
        items = catalog["items"]

        duplicate_context_groups: dict[tuple[int, int], list[int]] = {}
        by_run_assignment: dict[tuple[int, int], list[int]] = {}
        for item in items:
            by_run_assignment.setdefault(
                (int(item["run_id"]), int(item["assignment_id"])), []
            ).append(int(item["context_id"]))
        duplicate_context_groups = {
            key: ids for key, ids in by_run_assignment.items() if len(ids) > 1
        }

        discipline_rows = self.db.execute(
            select(Discipline.id, Discipline.course_id, Discipline.name, Course.name)
            .join(Course, Course.id == Discipline.course_id)
            .where(Course.directorate_id == self.directorate_id)
        ).all()
        discipline_groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for discipline_id, course_id, discipline_name, course_name in discipline_rows:
            discipline_groups.setdefault(
                (int(course_id), discipline_identity_key(discipline_name)), []
            ).append({
                "discipline_id": int(discipline_id),
                "discipline_name": discipline_name,
                "course_id": int(course_id),
                "course_name": course_name,
            })
        duplicate_disciplines = [
            group for group in discipline_groups.values() if len(group) > 1
        ]

        zero_respondent_contexts = [
            {
                "context_id": item["context_id"],
                "semester": item["semester"],
                "course_name": item["course_name"],
                "discipline_name": item["discipline_name"],
                "teacher_name": item["teacher_name"],
            }
            for item in items
            if int(item["respondent_count"] or 0) <= 0
        ]
        teachers_without_external_id = len({
            item["teacher_id"] for item in items if not item.get("teacher_external_id")
        })

        blockers: list[dict[str, Any]] = []
        if duplicate_context_groups:
            blockers.append({
                "code": "duplicate_run_assignment_context",
                "count": len(duplicate_context_groups),
                "message": "Há mais de um contexto para a mesma atribuição docente dentro do mesmo survey run.",
            })
        if duplicate_disciplines:
            blockers.append({
                "code": "duplicate_discipline_identity",
                "count": len(duplicate_disciplines),
                "message": "Há disciplinas com nomes diferentes que colapsam para a mesma identidade normalizada dentro do mesmo curso.",
            })

        warnings: list[dict[str, Any]] = []
        if zero_respondent_contexts:
            warnings.append({
                "code": "zero_respondents",
                "count": len(zero_respondent_contexts),
                "message": "Há contextos importados sem respondentes contabilizados.",
            })
        if teachers_without_external_id:
            warnings.append({
                "code": "teacher_without_external_id",
                "count": teachers_without_external_id,
                "message": "O relatório atual identifica docentes pelo nome; external_id permanece ausente nesses registros.",
            })

        return {
            "semester": catalog.get("semester"),
            "summary": catalog["summary"],
            "blocking_issue_count": sum(int(item["count"]) for item in blockers),
            "warning_count": sum(int(item["count"]) for item in warnings),
            "blockers": blockers,
            "warnings": warnings,
            "details": {
                "duplicate_run_assignment_contexts": [
                    {"run_id": key[0], "assignment_id": key[1], "context_ids": ids}
                    for key, ids in list(duplicate_context_groups.items())[:50]
                ],
                "duplicate_discipline_identities": duplicate_disciplines[:50],
                "zero_respondent_contexts": zero_respondent_contexts[:50],
            },
        }

    def _faculty_analytics_rows(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
        offering_id: int | None = None,
        question_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna o grao pergunta x alternativa preservando a fonte SEI."""

        effective_semester = _semester_to_data_univc(semester) if semester else None
        if semester and not effective_semester:
            raise SurveyIntegrationError("Semestre invalido. Use AAAA-SEM1 ou AAAA-SEM2.")

        stmt = (
            select(
                FacultyResponseAggregate.id.label("aggregate_id"),
                FacultyResponseAggregate.context_id.label("context_id"),
                FacultyResponseAggregate.question_id.label("question_id"),
                FacultyResponseAggregate.option_label.label("option_label"),
                FacultyResponseAggregate.numeric_value.label("numeric_value"),
                FacultyResponseAggregate.response_count.label("response_count"),
                FacultyEvaluationContext.run_id.label("run_id"),
                FacultyEvaluationContext.respondent_count.label("respondent_count"),
                TeachingAssignment.id.label("assignment_id"),
                FacultyEvaluationContextScope.is_primary.label("is_primary_scope"),
                FacultyEvaluationContextScope.resolution_source.label("scope_resolution_source"),
                Teacher.id.label("teacher_id"),
                Teacher.display_name.label("teacher_name"),
                AcademicOffering.id.label("offering_id"),
                AcademicOffering.period.label("semester"),
                AcademicOffering.class_group.label("class_group"),
                Course.id.label("course_id"),
                Course.name.label("course_name"),
                Course.modality.label("modality"),
                Discipline.id.label("discipline_id"),
                Discipline.name.label("discipline_name"),
                SurveyQuestion.text.label("question_text"),
                SurveyQuestion.position.label("question_position"),
            )
            .join(FacultyEvaluationContext, FacultyEvaluationContext.id == FacultyResponseAggregate.context_id)
            .join(SurveyRun, SurveyRun.id == FacultyEvaluationContext.run_id)
            .join(FacultyEvaluationContextScope, FacultyEvaluationContextScope.context_id == FacultyEvaluationContext.id)
            .join(TeachingAssignment, TeachingAssignment.id == FacultyEvaluationContextScope.teaching_assignment_id)
            .join(Teacher, Teacher.id == TeachingAssignment.teacher_id)
            .join(AcademicOffering, AcademicOffering.id == TeachingAssignment.offering_id)
            .join(Course, Course.id == AcademicOffering.course_id)
            .join(Discipline, Discipline.id == AcademicOffering.discipline_id)
            .join(SurveyQuestion, SurveyQuestion.id == FacultyResponseAggregate.question_id)
            .where(
                Course.directorate_id == self.directorate_id,
                SurveyRun.directorate_id == self.directorate_id,
                SurveyRun.run_kind == "faculty",
            )
        )
        if effective_semester:
            stmt = stmt.where(AcademicOffering.period == effective_semester)
        if course_id is not None:
            stmt = stmt.where(AcademicOffering.course_id == int(course_id))
        if discipline_id is not None:
            stmt = stmt.where(AcademicOffering.discipline_id == int(discipline_id))
        if teacher_id is not None:
            stmt = stmt.where(TeachingAssignment.teacher_id == int(teacher_id))
        if offering_id is not None:
            stmt = stmt.where(AcademicOffering.id == int(offering_id))
        if question_id is not None:
            stmt = stmt.where(FacultyResponseAggregate.question_id == int(question_id))
        stmt = stmt.order_by(
            AcademicOffering.period,
            Course.name,
            Discipline.name,
            Teacher.display_name,
            SurveyQuestion.position,
            FacultyResponseAggregate.id,
        )
        return [dict(row._mapping) for row in self.db.execute(stmt).all()]

    @staticmethod
    def _dedupe_faculty_aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove expansão por múltiplos cursos quando o cálculo é global.

        O mesmo aggregate_id pode aparecer uma vez por escopo de curso. Dentro
        de um recorte de curso isso não duplica; em visões gerais/por docente,
        a resposta precisa ser contada uma única vez.
        """
        seen: set[int] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            key = int(row.get("aggregate_id") or 0)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(row)
        return out

    @staticmethod
    def _faculty_analytics_summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
        scope_rows = list(rows)
        rows = SurveyRepository._dedupe_faculty_aggregate_rows(scope_rows)
        contexts: dict[int, dict[str, Any]] = {}
        for row in rows:
            contexts.setdefault(int(row["context_id"]), row)
        teacher_rows = [
            row for row in rows
            if classify_faculty_question(row.get("question_text")) == "teacher"
        ]
        teacher_question_ids = {int(row["question_id"]) for row in teacher_rows}
        contextual_question_ids = {
            int(row["question_id"]) for row in rows
            if classify_faculty_question(row.get("question_text")) == "contextual"
        }
        favorability = favorability_summary(teacher_rows)
        participation_total = sum(int(row.get("respondent_count") or 0) for row in contexts.values())
        return {
            "contexts": len(contexts),
            "semesters": len({row["semester"] for row in contexts.values()}),
            "courses": len({int(row["course_id"]) for row in scope_rows}),
            "disciplines": len({int(row["discipline_id"]) for row in scope_rows}),
            "teachers": len({int(row["teacher_id"]) for row in scope_rows}),
            "offerings": len({int(row["offering_id"]) for row in scope_rows}),
            "questions": len({int(row["question_id"]) for row in rows}),
            "teacher_questions": len(teacher_question_ids),
            "contextual_questions": len(contextual_question_ids),
            "respondent_participations": participation_total,
            "answer_selections": sum(max(0, int(row.get("response_count") or 0)) for row in rows),
            "teacher_answer_selections": sum(max(0, int(row.get("response_count") or 0)) for row in teacher_rows),
            "favorability": favorability,
            "favorability_scope": "teacher_questions_only",
            "respondent_participations_note": (
                "Soma dos respondentes informados em cada contexto Professor x Disciplina; "
                "nao representa alunos unicos entre diferentes contextos."
            ),
        }

    def faculty_analytics_filters(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
        offering_id: int | None = None,
    ) -> dict[str, Any]:
        """Facetas encadeadas baseadas somente em contextos realmente importados."""

        effective_semester = _semester_to_data_univc(semester) if semester else None
        if semester and not effective_semester:
            raise SurveyIntegrationError("Semestre invalido. Use AAAA-SEM1 ou AAAA-SEM2.")
        items = self.faculty_identity_catalog(None)["items"]
        selected = {
            "semester": effective_semester,
            "course_id": int(course_id) if course_id is not None else None,
            "discipline_id": int(discipline_id) if discipline_id is not None else None,
            "teacher_id": int(teacher_id) if teacher_id is not None else None,
            "offering_id": int(offering_id) if offering_id is not None else None,
        }

        def filtered(exclude: str | None = None) -> list[dict[str, Any]]:
            result = []
            for item in items:
                if exclude != "semester" and selected["semester"] and item["semester"] != selected["semester"]:
                    continue
                if exclude != "course_id" and selected["course_id"] is not None and int(item["course_id"]) != selected["course_id"]:
                    continue
                if exclude != "discipline_id" and selected["discipline_id"] is not None and int(item["discipline_id"]) != selected["discipline_id"]:
                    continue
                if exclude != "teacher_id" and selected["teacher_id"] is not None and int(item["teacher_id"]) != selected["teacher_id"]:
                    continue
                if exclude != "offering_id" and selected["offering_id"] is not None and int(item["offering_id"]) != selected["offering_id"]:
                    continue
                result.append(item)
            return result

        semester_items = filtered("semester")
        course_items = filtered("course_id")
        discipline_items = filtered("discipline_id")
        teacher_items = filtered("teacher_id")
        offering_items = filtered("offering_id")

        semesters = sorted({item["semester"] for item in semester_items}, reverse=True)
        courses = sorted(
            {
                (int(item["course_id"]), item["course_name"], item.get("modality") or "")
                for item in course_items
            },
            key=lambda row: row[1].casefold(),
        )
        disciplines = sorted(
            {
                (int(item["discipline_id"]), item["discipline_name"], int(item["course_id"]), item["course_name"])
                for item in discipline_items
            },
            key=lambda row: (row[3].casefold(), row[1].casefold()),
        )
        teachers = sorted(
            {(int(item["teacher_id"]), item["teacher_name"]) for item in teacher_items},
            key=lambda row: row[1].casefold(),
        )
        offerings = sorted(
            {
                (
                    int(item["offering_id"]), item["semester"], int(item["course_id"]), item["course_name"],
                    int(item["discipline_id"]), item["discipline_name"], item.get("class_group") or "",
                )
                for item in offering_items
            },
            key=lambda row: (row[1], row[3].casefold(), row[5].casefold(), row[6].casefold()),
        )
        active = filtered(None)
        return {
            "selected": selected,
            "semesters": semesters,
            "courses": [
                {"id": row[0], "name": row[1], "modality": row[2]} for row in courses
            ],
            "disciplines": [
                {"id": row[0], "name": row[1], "course_id": row[2], "course_name": row[3]}
                for row in disciplines
            ],
            "teachers": [{"id": row[0], "name": row[1]} for row in teachers],
            "offerings": [
                {
                    "id": row[0], "semester": row[1], "course_id": row[2], "course_name": row[3],
                    "discipline_id": row[4], "discipline_name": row[5], "class_group": row[6],
                }
                for row in offerings
            ],
            "matching_contexts": len({int(item["context_id"]) for item in active}),
        }

    def _faculty_goal_rows(self) -> list[dict[str, Any]]:
        """Retorna somente metas compatíveis com a favorabilidade oficial do KPI 02."""

        indicator = f"{self.directorate_code}-02"
        rows = self.db.scalars(
            select(Goal)
            .where(
                Goal.directorate_id == self.directorate_id,
                Goal.indicator_code == indicator,
                Goal.metric_version == "faculty_favorability_pct_v1",
            )
            .order_by(Goal.valid_from, Goal.scope_label, Goal.id)
        ).all()
        return [
            {
                "indicador": row.indicator_code,
                "recorte": row.scope_label,
                "vigencia": row.valid_from,
                "meta": row.target,
                "atencao": row.attention,
                "limite_superior": row.upper_limit,
                "justificativa": row.justification or "",
                "metric_version": row.metric_version,
            }
            for row in rows
        ]

    def _faculty_goal_scope_names(
        self,
        *,
        course_id: int | None = None,
        discipline_id: int | None = None,
    ) -> tuple[str | None, str | None]:
        course_name: str | None = None
        discipline_name: str | None = None
        resolved_course_id = int(course_id) if course_id is not None else None

        if discipline_id is not None:
            discipline = self.db.get(Discipline, int(discipline_id))
            if not discipline:
                raise SurveyIntegrationError("Disciplina não encontrada para o recorte da meta.")
            discipline_course = self.db.get(Course, int(discipline.course_id))
            if not discipline_course or int(discipline_course.directorate_id) != int(self.directorate_id):
                raise SurveyIntegrationError("Disciplina não pertence à diretoria atual.")
            discipline_name = discipline.name
            if resolved_course_id is None:
                resolved_course_id = int(discipline.course_id)
            elif int(resolved_course_id) != int(discipline.course_id):
                raise SurveyIntegrationError("Disciplina não pertence ao curso informado.")

        if resolved_course_id is not None:
            course = self.db.get(Course, int(resolved_course_id))
            if not course or int(course.directorate_id) != int(self.directorate_id):
                raise SurveyIntegrationError("Curso não pertence à diretoria atual.")
            course_name = course.name

        return course_name, discipline_name

    def _faculty_goal_state(
        self,
        *,
        period: str | None,
        value: float | None,
        course_id: int | None = None,
        discipline_id: int | None = None,
    ) -> dict[str, Any]:
        indicator = f"{self.directorate_code}-02"
        if not period:
            return {
                "indicator": indicator,
                "goal": None,
                "status": "Sem dados",
                "gap_to_goal_percentage_points": None,
            }
        course_name, discipline_name = self._faculty_goal_scope_names(
            course_id=course_id, discipline_id=discipline_id
        )
        selected = active_goal(
            self._faculty_goal_rows(),
            indicator,
            period,
            course_name,
            discipline_name,
        )
        info = goal_info(selected, indicator, course_name, discipline_name)
        target = info.get("meta") if info else None
        gap = None
        if value is not None and target is not None:
            gap = round(float(value) - float(target), 2)
        return {
            "indicator": indicator,
            "goal": info,
            "status": status_for(value, selected, indicator),
            "gap_to_goal_percentage_points": gap,
        }

    def faculty_analytics_operational_status(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
    ) -> dict[str, Any]:
        """Resumo operacional para a tela de produção da Avaliação Docente.

        O endpoint escolhe o semestre mais recente quando nenhum período é
        informado, mede a variação em pontos percentuais, aplica a meta vigente
        da mesma métrica e agrega sinais de qualidade/rastreabilidade sem criar
        uma segunda fonte de verdade.
        """

        effective_semester = _semester_to_data_univc(semester) if semester else None
        if semester and not effective_semester:
            raise SurveyIntegrationError("Semestre inválido. Use AAAA-SEM1 ou AAAA-SEM2.")

        comparison = self.faculty_analytics_semester_comparison(
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
        )
        timeline = comparison.get("items") or []
        current_period = effective_semester or (timeline[-1]["semester"] if timeline else None)
        current_item = next((item for item in timeline if item.get("semester") == current_period), None)
        current_summary = current_item.get("summary") if current_item else self._faculty_analytics_summary_from_rows([])
        current_fav = (current_summary or {}).get("favorability") or {}
        current_value = (
            current_fav.get("favorable_percentage")
            if current_fav.get("mapping_complete") is not False
            else None
        )

        previous_item = None
        if current_period:
            for item in reversed(timeline):
                if str(item.get("semester") or "") >= str(current_period):
                    continue
                previous_item = item
                break
        previous_value = None
        if previous_item:
            previous_fav = previous_item.get("summary", {}).get("favorability", {})
            if previous_fav.get("mapping_complete") is not False:
                previous_value = previous_fav.get("favorable_percentage")
        delta = None
        if current_value is not None and previous_value is not None:
            delta = round(float(current_value) - float(previous_value), 2)

        goal_state = self._faculty_goal_state(
            period=current_period,
            value=current_value,
            course_id=course_id,
            discipline_id=discipline_id,
        )
        quality = self.faculty_identity_quality(current_period) if current_period else {
            "blocking_issue_count": 0, "warning_count": 0, "summary": {}, "blockers": [], "warnings": []
        }
        history = self.faculty_import_history().get("items") or []
        latest_import = next(
            (item for item in history if not current_period or item.get("semester") == current_period),
            history[0] if history else None,
        )

        if not current_item:
            readiness = "no_data"
            readiness_message = "Não há avaliação docente importada para este semestre e recorte."
        elif current_fav.get("mapping_complete") is False:
            readiness = "blocked_scale"
            readiness_message = "Há categorias de resposta ainda não mapeadas; a favorabilidade está suspensa."
        elif int(quality.get("blocking_issue_count") or 0) > 0:
            readiness = "blocked_identity"
            readiness_message = "A malha acadêmica possui bloqueios de identidade que precisam ser revisados."
        elif not goal_state.get("goal"):
            readiness = "ready_no_goal"
            readiness_message = "Indicador calculável e identidade íntegra, mas ainda sem meta percentual vigente."
        else:
            readiness = "ready"
            readiness_message = "Indicador calculável, identidade íntegra e meta vigente disponível."

        return {
            "filters": {
                "semester": current_period,
                "course_id": course_id,
                "discipline_id": discipline_id,
                "teacher_id": teacher_id,
            },
            "current_period": current_period,
            "current_summary": current_summary,
            "current_value": current_value,
            "previous_period": previous_item.get("semester") if previous_item else None,
            "previous_value": previous_value,
            "delta_percentage_points": delta,
            "goal": goal_state.get("goal"),
            "goal_status": goal_state.get("status"),
            "gap_to_goal_percentage_points": goal_state.get("gap_to_goal_percentage_points"),
            "quality": {
                "blocking_issue_count": int(quality.get("blocking_issue_count") or 0),
                "warning_count": int(quality.get("warning_count") or 0),
                "summary": quality.get("summary") or {},
                "blockers": quality.get("blockers") or [],
                "warnings": quality.get("warnings") or [],
            },
            "latest_import": latest_import,
            "readiness": readiness,
            "readiness_message": readiness_message,
            "historical_period_count": len(timeline),
            "methodology": faculty_favorability_methodology(),
        }

    def faculty_analytics_overview(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
        offering_id: int | None = None,
    ) -> dict[str, Any]:
        rows = self._faculty_analytics_rows(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
            offering_id=offering_id,
        )
        return {
            "filters": {
                "semester": _semester_to_data_univc(semester) if semester else None,
                "course_id": course_id,
                "discipline_id": discipline_id,
                "teacher_id": teacher_id,
                "offering_id": offering_id,
            },
            "summary": self._faculty_analytics_summary_from_rows(rows),
            "methodology": faculty_favorability_methodology(),
        }

    def faculty_dashboard_projection(self) -> list[dict[str, Any]]:
        """Projeta o KPI 02 oficial para o painel executivo sem criar nota 0-10.

        O grao e semestre x curso x disciplina. A favorabilidade e reconstruida
        pelas contagens originais das perguntas classificadas como docente,
        permitindo agregacoes posteriores exatas por soma de contagens.
        """
        rows = self._faculty_analytics_rows()
        grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
        for row in rows:
            key = (str(row["semester"]), int(row["course_id"]), int(row["discipline_id"]))
            grouped.setdefault(key, []).append(row)

        out: list[dict[str, Any]] = []
        for (semester, _course_id, _discipline_id), group_rows in grouped.items():
            first = group_rows[0]
            summary = self._faculty_analytics_summary_from_rows(group_rows)
            fav = summary["favorability"]
            mapping_complete = bool(fav.get("mapping_complete"))
            classified_total = int(fav.get("classified_total") or 0)
            if not mapping_complete:
                validation = "CATEGORIA_NAO_MAPEADA"
            elif classified_total <= 0:
                validation = "SEM_RESPOSTAS_CLASSIFICADAS"
            else:
                validation = "OK"
            out.append({
                "agregado": True,
                "periodo": semester,
                "curso": first["course_name"],
                "disciplina": first["discipline_name"],
                "professor": "",
                "respondentes": int(summary.get("respondent_participations") or 0),
                "valor": fav.get("favorable_percentage") if mapping_complete else None,
                "favoraveis": int(fav.get("favorable") or 0),
                "intermediarias": int(fav.get("intermediate") or 0),
                "desfavoraveis": int(fav.get("unfavorable") or 0),
                "classificados": classified_total,
                "nao_classificados": int(fav.get("unclassified_total") or 0),
                "nao_mapeados": int(fav.get("unmapped_total") or 0),
                "respostas_docente": int(summary.get("teacher_answer_selections") or 0),
                "contextos": int(summary.get("contexts") or 0),
                "professores": int(summary.get("teachers") or 0),
                "fonte": "SEI · Avaliacao Institucional · Disciplina/Professor",
                "validacao": validation,
                "metrica": "faculty_favorability_pct_v1",
            })
        return sorted(out, key=lambda item: (str(item["periodo"]), str(item["curso"]).casefold(), str(item["disciplina"]).casefold()))

    def faculty_analytics_questions(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
        offering_id: int | None = None,
    ) -> dict[str, Any]:
        rows = self._faculty_analytics_rows(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
            offering_id=offering_id,
        )
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(int(row["question_id"]), []).append(row)
        items: list[dict[str, Any]] = []
        for question_id, qrows in grouped.items():
            qrows = self._dedupe_faculty_aggregate_rows(qrows)
            first = qrows[0]
            items.append({
                "question_id": question_id,
                "position": int(first.get("question_position") or 0),
                "question": first["question_text"],
                "analytical_scope": classify_faculty_question(first["question_text"]),
                "distribution": distribution_with_classification(qrows),
                "favorability": favorability_summary(qrows),
                "contexts": len({int(row["context_id"]) for row in qrows}),
            })
        items.sort(key=lambda item: (item["position"], item["question_id"]))
        return {
            "filters": {
                "semester": _semester_to_data_univc(semester) if semester else None,
                "course_id": course_id,
                "discipline_id": discipline_id,
                "teacher_id": teacher_id,
                "offering_id": offering_id,
            },
            "items": items,
            "question_count": len(items),
            "methodology": faculty_favorability_methodology(),
        }

    def _faculty_analytics_grouped(
        self,
        entity: str,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._faculty_analytics_rows(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
        )
        specs = {
            "teacher": ("teacher_id", "teacher_name"),
            "discipline": ("discipline_id", "discipline_name"),
            "course": ("course_id", "course_name"),
        }
        if entity not in specs:
            raise ValueError("Entidade analitica invalida.")
        id_key, name_key = specs[entity]
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(int(row[id_key]), []).append(row)
        items: list[dict[str, Any]] = []
        for entity_id, erows in grouped.items():
            first = erows[0]
            item = {
                "id": entity_id,
                "name": first[name_key],
                "summary": self._faculty_analytics_summary_from_rows(erows),
            }
            if entity == "discipline":
                item["course_id"] = int(first["course_id"])
                item["course_name"] = first["course_name"]
            if entity == "course":
                item["modality"] = first.get("modality")
            items.append(item)
        items.sort(key=lambda item: (str(item["name"]).casefold(), int(item["id"])))
        return items

    def faculty_analytics_teachers(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "items": self._faculty_analytics_grouped(
                "teacher", semester=semester, course_id=course_id, discipline_id=discipline_id
            ),
            "methodology": faculty_favorability_methodology(),
        }

    def faculty_analytics_disciplines(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        teacher_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "items": self._faculty_analytics_grouped(
                "discipline", semester=semester, course_id=course_id, teacher_id=teacher_id
            ),
            "methodology": faculty_favorability_methodology(),
        }

    def faculty_analytics_courses(
        self,
        *,
        semester: str | None = None,
        teacher_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "items": self._faculty_analytics_grouped(
                "course", semester=semester, teacher_id=teacher_id
            ),
            "methodology": faculty_favorability_methodology(),
        }

    def _faculty_identity_contexts_filtered(
        self,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
    ) -> list[dict[str, Any]]:
        effective_semester = _semester_to_data_univc(semester) if semester else None
        if semester and not effective_semester:
            raise SurveyIntegrationError("Semestre invalido. Use AAAA-SEM1 ou AAAA-SEM2.")
        result = []
        for item in self.faculty_identity_catalog(None)["items"]:
            if effective_semester and item["semester"] != effective_semester:
                continue
            if course_id is not None and int(item["course_id"]) != int(course_id):
                continue
            if discipline_id is not None and int(item["discipline_id"]) != int(discipline_id):
                continue
            if teacher_id is not None and int(item["teacher_id"]) != int(teacher_id):
                continue
            result.append(item)
        return result

    def faculty_analytics_teacher_detail(
        self,
        teacher_id: int,
        *,
        semester: str | None = None,
        course_id: int | None = None,
        discipline_id: int | None = None,
    ) -> dict[str, Any]:
        contexts = self._faculty_identity_contexts_filtered(
            semester=semester, course_id=course_id, discipline_id=discipline_id, teacher_id=teacher_id
        )
        if not contexts:
            raise SurveyIntegrationError("Docente nao possui avaliacao no escopo informado.")
        return {
            "teacher": {"id": int(teacher_id), "name": contexts[0]["teacher_name"]},
            "overview": self.faculty_analytics_overview(
                semester=semester, course_id=course_id, discipline_id=discipline_id, teacher_id=teacher_id
            ),
            "questions": self.faculty_analytics_questions(
                semester=semester, course_id=course_id, discipline_id=discipline_id, teacher_id=teacher_id
            ),
            "contexts": contexts,
        }

    def faculty_analytics_discipline_detail(
        self,
        discipline_id: int,
        *,
        semester: str | None = None,
        teacher_id: int | None = None,
    ) -> dict[str, Any]:
        contexts = self._faculty_identity_contexts_filtered(
            semester=semester, discipline_id=discipline_id, teacher_id=teacher_id
        )
        if not contexts:
            raise SurveyIntegrationError("Disciplina nao possui avaliacao no escopo informado.")
        return {
            "discipline": {
                "id": int(discipline_id),
                "name": contexts[0]["discipline_name"],
                "course_id": contexts[0]["course_id"],
                "course_name": contexts[0]["course_name"],
            },
            "overview": self.faculty_analytics_overview(
                semester=semester, discipline_id=discipline_id, teacher_id=teacher_id
            ),
            "questions": self.faculty_analytics_questions(
                semester=semester, discipline_id=discipline_id, teacher_id=teacher_id
            ),
            "contexts": contexts,
        }

    def faculty_analytics_semester_comparison(
        self,
        *,
        course_id: int | None = None,
        discipline_id: int | None = None,
        teacher_id: int | None = None,
    ) -> dict[str, Any]:
        rows = self._faculty_analytics_rows(
            course_id=course_id, discipline_id=discipline_id, teacher_id=teacher_id
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row["semester"]), []).append(row)

        items: list[dict[str, Any]] = []
        previous_value: float | None = None
        previous_period: str | None = None
        for period in sorted(grouped):
            summary = self._faculty_analytics_summary_from_rows(grouped[period])
            fav = summary.get("favorability") or {}
            value = fav.get("favorable_percentage") if fav.get("mapping_complete") is not False else None
            delta = None
            if value is not None and previous_value is not None:
                delta = round(float(value) - float(previous_value), 2)
            goal_state = self._faculty_goal_state(
                period=period,
                value=value,
                course_id=course_id,
                discipline_id=discipline_id,
            )
            items.append({
                "semester": period,
                "summary": summary,
                "previous_semester": previous_period,
                "delta_percentage_points": delta,
                "goal": goal_state.get("goal"),
                "goal_status": goal_state.get("status"),
                "gap_to_goal_percentage_points": goal_state.get("gap_to_goal_percentage_points"),
            })
            if value is not None:
                previous_value = float(value)
                previous_period = period

        return {
            "filters": {
                "course_id": course_id,
                "discipline_id": discipline_id,
                "teacher_id": teacher_id,
            },
            "items": items,
            "methodology": faculty_favorability_methodology(),
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
        rows = self._faculty_analytics_rows(
            semester=semester,
            course_id=course_id,
            discipline_id=discipline_id,
            teacher_id=teacher_id,
            offering_id=offering_id,
            question_id=question_id,
        )
        rows = self._dedupe_faculty_aggregate_rows(rows)
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
            "status": "sei_adapter_ready",
            "parser_adapter": "discipline_teacher_xlsx",
            "source_scope": "GRADUACAO_SAO_MATEUS",
            "message": (
                "A estrutura relacional e o adaptador Disciplina/Professor do SEI estão disponíveis. "
                "Professor, disciplina, curso e semestre permanecem separados e as respostas são "
                "preservadas por pergunta/opção, sem conversão implícita para nota 0–10."
            ),
            "counts": counts,
        }
