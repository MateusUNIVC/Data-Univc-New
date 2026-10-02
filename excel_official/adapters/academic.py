from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from ..context import AdapterInput
from ..contract import (
    ActionPlanRowSource,
    ActionPlanRowSpec,
    ActionPlanSpec,
    AdapterCapabilities,
    ChartRole,
    ChartSpec,
    ChartType,
    ColumnDataType,
    ColumnSpec,
    DashboardSpec,
    DatasetSpec,
    DimensionSpec,
    DomainSheetSpec,
    IdentitySpec,
    InitialStateSpec,
    KpiSpec,
    LimitationSpec,
    MatrixMetricOptionSpec,
    MatrixSpec,
    MetricAggregation,
    MetricBinding,
    MetricSpec,
    MetricUnit,
    ParameterSpec,
    QualityCheckSpec,
    QualitySeverity,
    QualitySpec,
    SheetRole,
    SnapshotSpec,
    TargetBindingSpec,
    TechnicalSpec,
    WorkbookSpec,
)
from .base import DirectorateAdapter


ACADEMIC_METRICS = {
    "nps_institution": "academic.nps_institution_students",
    "nps_institution_course": "academic.nps_institution_students_by_course",
    "nps_course": "academic.nps_course_students",
    "nps_faculty": "academic.nps_institution_faculty",
    "teacher": "academic.faculty_favorability",
    "approval": "academic.approval_rate",
    "average_grade": "academic.average_grade",
}


@dataclass(frozen=True, slots=True)
class AcademicAdapterError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _semester_order(value: str) -> int:
    text = str(value or "").strip().upper()
    try:
        year = int(text[:4])
    except (TypeError, ValueError):
        return 0
    if "SEM2" in text or text.endswith("/2") or text.endswith("-2"):
        half = 2
    elif "SEM1" in text or text.endswith("/1") or text.endswith("-1"):
        half = 1
    else:
        half = 0
    return year * 10 + half


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _period_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    periods = [_clean_text(item) for item in payload.get("semesters", ()) if _clean_text(item)]
    unique = sorted(set(periods), key=lambda item: (_semester_order(item), item))
    return tuple(
        {
            "period": period,
            "label": period,
            "sort_order": _semester_order(period),
            "year": _as_int(period[:4]),
            "semester": 2 if "SEM2" in period.upper() else 1 if "SEM1" in period.upper() else None,
        }
        for period in unique
    )


def _course_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(payload.get("courses_catalog", ())):
        name = _clean_text(raw.get("curso"))
        if not name or name in seen or raw.get("ativo") is False:
            continue
        seen.add(name)
        rows.append({
            "course": name,
            "course_id": raw.get("id"),
            "sort_order": index + 1,
        })
    return tuple(rows)


def _discipline_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(payload.get("disciplines_catalog", ())):
        course = _clean_text(raw.get("curso"))
        discipline = _clean_text(raw.get("disciplina"))
        if not course or not discipline or raw.get("ativo") is False:
            continue
        marker = (course, discipline)
        if marker in seen:
            continue
        seen.add(marker)
        rows.append({
            "course": course,
            "discipline": discipline,
            "discipline_id": raw.get("id"),
            "sort_order": index + 1,
        })
    return tuple(rows)


def _nps_institution_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("institution_students", ()):
        period = _clean_text(raw.get("periodo"))
        if not period:
            continue
        rows.append({
            "period": period,
            "respondents": _as_int(raw.get("respondentes")),
            "promoters": _as_int(raw.get("promotores")),
            "neutrals": _as_int(raw.get("neutros")),
            "detractors": _as_int(raw.get("detratores")),
            "reported_nps": _as_float(raw.get("valor")),
            "coverage": _as_int(raw.get("coverage")),
            "coverage_total": _as_int(raw.get("coverage_total")),
            "complete": bool(raw.get("complete")),
            "source": _clean_text(raw.get("questionnaire") or raw.get("fonte") or "SEI · NPS institucional"),
        })
    return tuple(rows)


def _nps_institution_course_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("institution_students_by_course", ()):
        period = _clean_text(raw.get("periodo"))
        course = _clean_text(raw.get("curso"))
        if not period or not course:
            continue
        rows.append({
            "period": period,
            "course": course,
            "respondents": _as_int(raw.get("respondentes")),
            "promoters": _as_int(raw.get("promotores")),
            "neutrals": _as_int(raw.get("neutros")),
            "detractors": _as_int(raw.get("detratores")),
            "reported_nps": _as_float(raw.get("valor")),
            "source": _clean_text(raw.get("fonte") or "SEI · NPS institucional por curso"),
        })
    return tuple(rows)


def _history_window_rows() -> tuple[dict[str, Any], ...]:
    return tuple({"window": str(value), "sort_order": index} for index, value in enumerate((4, 6, 8, 12, "Todo histórico"), start=1))


def _matrix_metric_rows() -> tuple[dict[str, Any], ...]:
    labels = (
        ("01A · NPS Instituição · Alunos", ACADEMIC_METRICS["nps_institution_course"]),
        ("01B · NPS do Curso", ACADEMIC_METRICS["nps_course"]),
        ("02 · Avaliação Docente", ACADEMIC_METRICS["teacher"]),
        ("03 · Aprovação", ACADEMIC_METRICS["approval"]),
    )
    return tuple({"selector_value": label, "metric_code": metric_code, "sort_order": index} for index, (label, metric_code) in enumerate(labels, start=1))


def _nps_course_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("course_nps", ()):
        period = _clean_text(raw.get("periodo"))
        course = _clean_text(raw.get("curso"))
        if not period or not course:
            continue
        rows.append({
            "period": period,
            "course": course,
            "respondents": _as_int(raw.get("respondentes")),
            "promoters": _as_int(raw.get("promotores")),
            "neutrals": _as_int(raw.get("neutros")),
            "detractors": _as_int(raw.get("detratores")),
            "reported_nps": _as_float(raw.get("valor")),
            "reported_target": _as_float(raw.get("meta")),
            "reported_attention": _as_float(raw.get("atencao")),
            "reported_status": _clean_text(raw.get("status")),
            "source": _clean_text(raw.get("fonte") or "Base acadêmica"),
        })
    return tuple(rows)


def _nps_faculty_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("faculty_nps", ()):
        period = _clean_text(raw.get("periodo"))
        if not period:
            continue
        rows.append({
            "period": period,
            "respondents": _as_int(raw.get("respondentes")),
            "promoters": _as_int(raw.get("promotores")),
            "neutrals": _as_int(raw.get("neutros")),
            "detractors": _as_int(raw.get("detratores")),
            "reported_nps": _as_float(raw.get("valor")),
            "source": _clean_text(raw.get("fonte") or "SEI · NPS institucional dos docentes"),
        })
    return tuple(rows)


def _nps_distribution_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("nps_distribution_rows", ()):
        period = _clean_text(raw.get("periodo"))
        audience = _clean_text(raw.get("audiencia"))
        score = raw.get("nota")
        if not period or not audience or score is None:
            continue
        rows.append({
            "period": period,
            "audience": audience,
            "scope": _clean_text(raw.get("escopo")),
            "score": _as_int(score),
            "responses": _as_int(raw.get("respostas")),
            "percentage_points": _as_float(raw.get("percentual")),
            "respondents": _as_int(raw.get("respondentes")),
            "mean_0_10": _as_float(raw.get("media")),
            "nps": _as_float(raw.get("nps")),
        })
    return tuple(rows)


def _teacher_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("teacher", ()):
        period = _clean_text(raw.get("periodo"))
        course = _clean_text(raw.get("curso"))
        discipline = _clean_text(raw.get("disciplina"))
        if not period or not course or not discipline:
            continue
        rows.append({
            "period": period,
            "course": course,
            "discipline": discipline,
            "respondents": _as_int(raw.get("respondentes")),
            "favorable": _as_int(raw.get("favoraveis")),
            "intermediate": _as_int(raw.get("intermediarias")),
            "unfavorable": _as_int(raw.get("desfavoraveis")),
            "classified": _as_int(raw.get("classificados")),
            "unclassified": _as_int(raw.get("nao_classificados")),
            "unmapped": _as_int(raw.get("nao_mapeados")),
            "reported_favorability_points": _as_float(raw.get("favorabilidade")),
            "reported_target_points": _as_float(raw.get("meta")),
            "reported_attention_points": _as_float(raw.get("atencao")),
            "reported_status": _clean_text(raw.get("status")),
            "source": _clean_text(raw.get("fonte") or "SEI · Avaliação Institucional · Disciplina/Professor"),
        })
    return tuple(rows)


def _result_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("results", ()):
        period = _clean_text(raw.get("periodo"))
        course = _clean_text(raw.get("curso"))
        discipline = _clean_text(raw.get("disciplina"))
        if not period or not course or not discipline:
            continue
        grade_count = _as_int(raw.get("notas_contagem"))
        grade_sum = _as_float(raw.get("soma_notas"))
        if grade_sum is None:
            average = _as_float(raw.get("media_notas"))
            grade_sum = (average * grade_count) if average is not None and grade_count else 0.0
        rows.append({
            "period": period,
            "course": course,
            "discipline": discipline,
            "total_records": _as_int(raw.get("total_registros")),
            "finalized": _as_int(raw.get("finalizados")),
            "approved": _as_int(raw.get("aprovados")),
            "failed_grade": _as_int(raw.get("reprovados_nota")),
            "failed_absence": _as_int(raw.get("reprovados_falta")),
            "failed_other": _as_int(raw.get("reprovados_outro")),
            "in_progress": _as_int(raw.get("em_andamento")),
            "grade_count": grade_count,
            "grade_sum": float(grade_sum or 0.0),
            "reported_average_grade": _as_float(raw.get("media_notas")),
            "reported_target_points": _as_float(raw.get("meta")),
            "reported_attention_points": _as_float(raw.get("atencao")),
            "reported_status": _clean_text(raw.get("status")),
            "source": _clean_text(raw.get("fonte") or "SEI · resultados acadêmicos"),
        })
    return tuple(rows)


def _goal_rows(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("effective_goals", ()):
        period = _clean_text(raw.get("periodo"))
        kpi = _clean_text(raw.get("kpi"))
        if not period or not kpi:
            continue
        rows.append({
            "period": period,
            "legacy_kpi": kpi,
            "course": _clean_text(raw.get("curso") or "(todos)"),
            "discipline": _clean_text(raw.get("disciplina") or "(todas)"),
            "target_points": _as_float(raw.get("meta")),
            "attention_points": _as_float(raw.get("atencao")),
            "valid_from": _clean_text(raw.get("vigencia")),
            "scope": _clean_text(raw.get("recorte")),
        })
    return tuple(rows)


def _indicator_labels(payload: Mapping[str, Any]) -> dict[str, str]:
    codes = payload.get("codes", {})
    return {
        _clean_text(codes.get("nps_institution")): "NPS da Instituição · Alunos",
        _clean_text(codes.get("nps_course")): "NPS do Curso",
        _clean_text(codes.get("nps_faculty")): "NPS da Instituição · Docentes",
        _clean_text(codes.get("teacher")): "Avaliação Docente pelo Aluno",
        _clean_text(codes.get("approval")): "Taxa de Aprovação",
    }


def _action_rows(payload: Mapping[str, Any]) -> tuple[ActionPlanRowSpec, ...]:
    labels = _indicator_labels(payload)
    rows: list[ActionPlanRowSpec] = []
    for raw in payload.get("actions", ()):
        legacy_code = _clean_text(raw.get("indicador"))
        rows.append(ActionPlanRowSpec(
            source=ActionPlanRowSource.OFFICIAL,
            values={
                "indicator": labels.get(legacy_code, legacy_code),
                "problem": _clean_text(raw.get("problema") or raw.get("resultado_esperado")),
                "diagnosis": _clean_text(raw.get("causa") or raw.get("diagnostico")),
                "action": _clean_text(raw.get("acao")),
                "owner": _clean_text(raw.get("responsavel")),
                "deadline": _as_date(raw.get("prazo")),
                "status": _clean_text(raw.get("status")),
            },
        ))
    return tuple(rows)


def _limitations(payload: Mapping[str, Any]) -> tuple[LimitationSpec, ...]:
    limitations: list[LimitationSpec] = []
    quality = payload.get("quality", {}) or {}
    nps_bad = _as_int(quality.get("nps_inconsistent_rows"))
    result_bad = _as_int(quality.get("result_inconsistent_rows"))
    if nps_bad:
        limitations.append(LimitationSpec(
            code="academic.nps_source_inconsistency",
            title="Inconsistências detectadas na composição NPS",
            description=f"{nps_bad} linha(s) da fonte NPS não reconciliam respondentes com promotores + neutros + detratores.",
            severity=QualitySeverity.ERROR,
            affected_metric=ACADEMIC_METRICS["nps_course"],
        ))
    if result_bad:
        limitations.append(LimitationSpec(
            code="academic.results_source_inconsistency",
            title="Inconsistências detectadas nos resultados acadêmicos",
            description=f"{result_bad} linha(s) não reconciliam finalizados com aprovados e reprovações por motivo.",
            severity=QualitySeverity.ERROR,
            affected_metric=ACADEMIC_METRICS["approval"],
        ))
    return tuple(limitations)


def _dataset_specs(payload: Mapping[str, Any], authorization_scope: tuple[str, ...]) -> tuple[DatasetSpec, ...]:
    percent_points_format = '0.0"%"'
    return (
        DatasetSpec(
            code="academic_periods",
            label="Períodos acadêmicos",
            sheet_name="DIM_PERIODO",
            table_name="TblAcademicPeriodsOfficial",
            technical=True,
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("label", "Rótulo", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
                ColumnSpec("year", "Ano", ColumnDataType.INTEGER, technical=True),
                ColumnSpec("semester", "Semestre", ColumnDataType.INTEGER, technical=True),
            ),
            rows=_period_rows(payload),
            grain=("period",),
            source="Data UNIVC · períodos acadêmicos autorizados",
            authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="academic_history_windows",
            label="Janelas históricas",
            sheet_name="DIM_JANELA",
            table_name="TblAcademicHistoryWindowsOfficial",
            technical=True,
            columns=(
                ColumnSpec("window", "Janela", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_history_window_rows(),
            grain=("window",),
            source="Data UNIVC · opções institucionais de janela histórica",
            authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="academic_matrix_metrics",
            label="Indicadores da matriz acadêmica",
            sheet_name="DIM_KPI_MATRIZ",
            table_name="TblAcademicMatrixMetricsOfficial",
            technical=True,
            columns=(
                ColumnSpec("selector_value", "Indicador", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("metric_code", "Código métrico", ColumnDataType.TEXT, technical=True, nullable=False),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_matrix_metric_rows(),
            grain=("selector_value",),
            source="Data UNIVC · indicadores suportados na matriz acadêmica",
            authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="academic_courses",
            label="Cursos",
            sheet_name="CURSOS",
            table_name="TblAcademicCoursesOfficial",
            columns=(
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course", nullable=False),
                ColumnSpec("course_id", "ID", ColumnDataType.INTEGER, technical=True),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_course_rows(payload),
            grain=("course",),
            source="Data UNIVC · catálogo acadêmico",
            authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="academic_disciplines",
            label="Disciplinas",
            sheet_name="DISCIPLINAS",
            table_name="TblAcademicDisciplinesOfficial",
            columns=(
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course", nullable=False),
                ColumnSpec("discipline", "Disciplina", ColumnDataType.TEXT, semantic_type="discipline", nullable=False),
                ColumnSpec("discipline_id", "ID", ColumnDataType.INTEGER, technical=True),
                ColumnSpec("sort_order", "Ordem", ColumnDataType.INTEGER, technical=True, nullable=False),
            ),
            rows=_discipline_rows(payload),
            grain=("course", "discipline"),
            source="Data UNIVC · catálogo acadêmico",
            authorization_scope=authorization_scope,
        ),
        DatasetSpec(
            code="academic_nps_institution",
            label="NPS da Instituição · Alunos",
            sheet_name="NPS INSTITUICAO",
            table_name="TblAcademicNpsInstitutionOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("promoters", "Promotores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("neutrals", "Neutros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("detractors", "Detratores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("reported_nps", "NPS informado", ColumnDataType.DECIMAL, semantic_type="nps"),
                ColumnSpec("coverage", "Diretorias", ColumnDataType.INTEGER),
                ColumnSpec("coverage_total", "Total diretorias", ColumnDataType.INTEGER),
                ColumnSpec("complete", "Cobertura completa", ColumnDataType.BOOLEAN),
                ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ),
            rows=_nps_institution_rows(payload),
            grain=("period",),
            source="SEI · NPS institucional consolidado DTNH + DCS",
            authorization_scope=authorization_scope,
            filter_dimensions=("period",),
            dimension_columns={"period": "period"},
        ),
        DatasetSpec(
            code="academic_nps_institution_course",
            label="NPS Instituição · Alunos por Curso",
            sheet_name="NPS INST POR CURSO",
            table_name="TblAcademicNpsInstitutionCourseOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course", nullable=False),
                ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("promoters", "Promotores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("neutrals", "Neutros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("detractors", "Detratores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("reported_nps", "NPS informado", ColumnDataType.DECIMAL, semantic_type="nps"),
                ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ),
            rows=_nps_institution_course_rows(payload),
            grain=("period", "course"),
            source="Data UNIVC · NPS institucional dos alunos desagregado por curso",
            authorization_scope=authorization_scope,
            filter_dimensions=("period", "course"),
            dimension_columns={"period": "period", "course": "course"},
        ),
        DatasetSpec(
            code="academic_nps_course",
            label="NPS do Curso",
            sheet_name="NPS CURSO",
            table_name="TblAcademicNpsCourseOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course", nullable=False),
                ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("promoters", "Promotores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("neutrals", "Neutros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("detractors", "Detratores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("reported_nps", "NPS informado", ColumnDataType.DECIMAL, semantic_type="nps"),
                ColumnSpec("reported_target", "Meta informada", ColumnDataType.DECIMAL, semantic_type="nps"),
                ColumnSpec("reported_attention", "Atenção informada", ColumnDataType.DECIMAL, semantic_type="nps"),
                ColumnSpec("reported_status", "Status informado", ColumnDataType.TEXT),
                ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ),
            rows=_nps_course_rows(payload),
            grain=("period", "course"),
            source="Data UNIVC · NPS do Curso",
            authorization_scope=authorization_scope,
            filter_dimensions=("period", "course"),
            dimension_columns={"period": "period", "course": "course"},
        ),
        DatasetSpec(
            code="academic_nps_faculty",
            label="NPS da Instituição · Docentes",
            sheet_name="NPS DOCENTES",
            table_name="TblAcademicNpsFacultyOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("promoters", "Promotores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("neutrals", "Neutros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("detractors", "Detratores", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("reported_nps", "NPS informado", ColumnDataType.DECIMAL, semantic_type="nps"),
                ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ),
            rows=_nps_faculty_rows(payload),
            grain=("period",),
            source="SEI · NPS institucional dos docentes · população anônima",
            authorization_scope=authorization_scope,
            filter_dimensions=("period",),
            dimension_columns={"period": "period"},
        ),
        DatasetSpec(
            code="academic_nps_distribution",
            label="Distribuição NPS 0–10",
            sheet_name="NPS DISTRIBUICAO",
            table_name="TblAcademicNpsDistributionOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("audience", "Audiência", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("scope", "Escopo", ColumnDataType.TEXT),
                ColumnSpec("score", "Nota", ColumnDataType.INTEGER, semantic_type="score_0_10", nullable=False),
                ColumnSpec("responses", "Respostas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("percentage_points", "Percentual", ColumnDataType.DECIMAL, number_format=percent_points_format),
                ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER),
                ColumnSpec("mean_0_10", "Média 0–10", ColumnDataType.DECIMAL, semantic_type="score_0_10"),
                ColumnSpec("nps", "NPS", ColumnDataType.DECIMAL, semantic_type="nps"),
            ),
            rows=_nps_distribution_rows(payload),
            grain=("period", "audience", "score"),
            source="SEI · distribuição oficial de respostas NPS",
            authorization_scope=authorization_scope,
            filter_dimensions=("period",),
            dimension_columns={"period": "period"},
        ),
        DatasetSpec(
            code="academic_teacher",
            label="Avaliação Docente pelo Aluno",
            sheet_name="AVALIACAO DOCENTE",
            table_name="TblAcademicFacultyFavorabilityOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course", nullable=False),
                ColumnSpec("discipline", "Disciplina", ColumnDataType.TEXT, semantic_type="discipline", nullable=False),
                ColumnSpec("respondents", "Respondentes", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("favorable", "Favoráveis", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("intermediate", "Intermediárias", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("unfavorable", "Desfavoráveis", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("classified", "Classificadas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("unclassified", "Não classificadas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("unmapped", "Não mapeadas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("reported_favorability_points", "Favorabilidade informada", ColumnDataType.DECIMAL, number_format=percent_points_format),
                ColumnSpec("reported_target_points", "Meta informada", ColumnDataType.DECIMAL, number_format=percent_points_format),
                ColumnSpec("reported_attention_points", "Atenção informada", ColumnDataType.DECIMAL, number_format=percent_points_format),
                ColumnSpec("reported_status", "Status informado", ColumnDataType.TEXT),
                ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ),
            rows=_teacher_rows(payload),
            grain=("period", "course", "discipline"),
            source="SEI · Avaliação Institucional · Disciplina/Professor",
            authorization_scope=authorization_scope,
            filter_dimensions=("period", "course", "discipline"),
            dimension_columns={"period": "period", "course": "course", "discipline": "discipline"},
        ),
        DatasetSpec(
            code="academic_results",
            label="Resultados Acadêmicos",
            sheet_name="RESULTADOS ACADEMICOS",
            table_name="TblAcademicResultsOfficial",
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, semantic_type="period", nullable=False),
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, semantic_type="course", nullable=False),
                ColumnSpec("discipline", "Disciplina", ColumnDataType.TEXT, semantic_type="discipline", nullable=False),
                ColumnSpec("total_records", "Registros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("finalized", "Finalizados", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("approved", "Aprovados", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("failed_grade", "Reprovados por nota", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("failed_absence", "Reprovados por falta", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("failed_other", "Reprovados outros", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("in_progress", "Em andamento", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("grade_count", "Notas válidas", ColumnDataType.INTEGER, nullable=False),
                ColumnSpec("grade_sum", "Soma das notas", ColumnDataType.DECIMAL, nullable=False),
                ColumnSpec("reported_average_grade", "Média informada", ColumnDataType.DECIMAL, semantic_type="score_0_10"),
                ColumnSpec("reported_target_points", "Meta aprovação", ColumnDataType.DECIMAL, number_format=percent_points_format),
                ColumnSpec("reported_attention_points", "Atenção aprovação", ColumnDataType.DECIMAL, number_format=percent_points_format),
                ColumnSpec("reported_status", "Status informado", ColumnDataType.TEXT),
                ColumnSpec("source", "Fonte", ColumnDataType.TEXT),
            ),
            rows=_result_rows(payload),
            grain=("period", "course", "discipline"),
            source="Data UNIVC · agregados de resultados acadêmicos do SEI",
            authorization_scope=authorization_scope,
            filter_dimensions=("period", "course", "discipline"),
            dimension_columns={"period": "period", "course": "course", "discipline": "discipline"},
        ),
        DatasetSpec(
            code="academic_goals_base",
            label="Metas acadêmicas efetivas",
            sheet_name="BASE METAS ACADEMICAS",
            table_name="TblAcademicGoalsBaseOfficial",
            technical=True,
            columns=(
                ColumnSpec("period", "Período", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("legacy_kpi", "KPI legado", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("course", "Curso", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("discipline", "Disciplina", ColumnDataType.TEXT, nullable=False),
                ColumnSpec("target_points", "Meta", ColumnDataType.DECIMAL),
                ColumnSpec("attention_points", "Atenção", ColumnDataType.DECIMAL),
                ColumnSpec("valid_from", "Vigência", ColumnDataType.TEXT),
                ColumnSpec("scope", "Recorte", ColumnDataType.TEXT),
            ),
            rows=_goal_rows(payload),
            grain=("period", "legacy_kpi", "course", "discipline"),
            source="Data UNIVC · metas acadêmicas efetivas pré-expandidas",
            authorization_scope=authorization_scope,
        ),
    )


def _metric_specs() -> tuple[MetricSpec, ...]:
    return (
        MetricSpec(
            code=ACADEMIC_METRICS["nps_institution"],
            label="NPS da Instituição · Alunos",
            aggregation=MetricAggregation.NPS,
            unit=MetricUnit.NPS,
            description="NPS institucional dos alunos consolidado pelas contagens oficiais; não é média entre diretorias.",
            allowed_dimensions=("period",),
            valid_min=-100,
            valid_max=100,
            display_precision=1,
        ),
        MetricSpec(
            code=ACADEMIC_METRICS["nps_institution_course"],
            label="NPS da Instituição · Alunos por Curso",
            aggregation=MetricAggregation.NPS,
            unit=MetricUnit.NPS,
            description="Desdobramento do NPS institucional dos alunos por curso, usado na matriz acadêmica.",
            allowed_dimensions=("period", "course"),
            valid_min=-100,
            valid_max=100,
            display_precision=1,
        ),
        MetricSpec(
            code=ACADEMIC_METRICS["nps_course"],
            label="NPS do Curso",
            aggregation=MetricAggregation.NPS,
            unit=MetricUnit.NPS,
            description="NPS do curso recomposto por respondentes, promotores e detratores.",
            allowed_dimensions=("period", "course"),
            valid_min=-100,
            valid_max=100,
            display_precision=1,
        ),
        MetricSpec(
            code=ACADEMIC_METRICS["nps_faculty"],
            label="NPS da Instituição · Docentes",
            aggregation=MetricAggregation.NPS,
            unit=MetricUnit.NPS,
            description="NPS institucional dos docentes; população anônima sem recorte de curso/disciplina.",
            allowed_dimensions=("period",),
            valid_min=-100,
            valid_max=100,
            display_precision=1,
        ),
        MetricSpec(
            code=ACADEMIC_METRICS["teacher"],
            label="Avaliação Docente pelo Aluno",
            aggregation=MetricAggregation.RATIO,
            unit=MetricUnit.PERCENT,
            description="Favorabilidade = respostas favoráveis / respostas classificadas; indisponível se houver respostas não mapeadas.",
            allowed_dimensions=("period", "course", "discipline"),
            valid_min=0,
            valid_max=1,
            display_precision=1,
            invalid_when_positive_components=("unmapped",),
        ),
        MetricSpec(
            code=ACADEMIC_METRICS["approval"],
            label="Taxa de Aprovação",
            aggregation=MetricAggregation.RATIO,
            unit=MetricUnit.PERCENT,
            description="Aprovados / resultados finalizados no recorte.",
            allowed_dimensions=("period", "course", "discipline"),
            valid_min=0,
            valid_max=1,
            display_precision=1,
        ),
        MetricSpec(
            code=ACADEMIC_METRICS["average_grade"],
            label="Média das Notas",
            aggregation=MetricAggregation.AVERAGE,
            unit=MetricUnit.SCORE_0_10,
            description="Soma das notas finais válidas / quantidade de notas válidas; evita média de médias.",
            allowed_dimensions=("period", "course", "discipline"),
            valid_min=0,
            valid_max=10,
            display_precision=2,
        ),
    )


def _metric_bindings() -> tuple[MetricBinding, ...]:
    return (
        MetricBinding(
            metric_code=ACADEMIC_METRICS["nps_institution"],
            dataset_code="academic_nps_institution",
            components={"respondents": "respondents", "promoters": "promoters", "detractors": "detractors"},
            filter_parameters={"period": "reference_period"},
        ),
        MetricBinding(
            metric_code=ACADEMIC_METRICS["nps_institution_course"],
            dataset_code="academic_nps_institution_course",
            components={"respondents": "respondents", "promoters": "promoters", "detractors": "detractors"},
            filter_parameters={"period": "reference_period", "course": "course"},
        ),
        MetricBinding(
            metric_code=ACADEMIC_METRICS["nps_course"],
            dataset_code="academic_nps_course",
            components={"respondents": "respondents", "promoters": "promoters", "detractors": "detractors"},
            filter_parameters={"period": "reference_period", "course": "course"},
        ),
        MetricBinding(
            metric_code=ACADEMIC_METRICS["nps_faculty"],
            dataset_code="academic_nps_faculty",
            components={"respondents": "respondents", "promoters": "promoters", "detractors": "detractors"},
            filter_parameters={"period": "reference_period"},
        ),
        MetricBinding(
            metric_code=ACADEMIC_METRICS["teacher"],
            dataset_code="academic_teacher",
            components={"numerator": "favorable", "denominator": "classified", "unmapped": "unmapped"},
            filter_parameters={"period": "reference_period", "course": "course", "discipline": "discipline"},
        ),
        MetricBinding(
            metric_code=ACADEMIC_METRICS["approval"],
            dataset_code="academic_results",
            components={"numerator": "approved", "denominator": "finalized"},
            filter_parameters={"period": "reference_period", "course": "course", "discipline": "discipline"},
        ),
        MetricBinding(
            metric_code=ACADEMIC_METRICS["average_grade"],
            dataset_code="academic_results",
            components={"sum": "grade_sum", "count": "grade_count"},
            filter_parameters={"period": "reference_period", "course": "course", "discipline": "discipline"},
        ),
    )


class AcademicAdapter(DirectorateAdapter):
    """Translate the authorized Academic V3 snapshot into the Excel Official contract.

    The adapter is intentionally database/openpyxl-free. The transition provider
    may reuse the existing Academic V3 payload builder, but all workbook rendering
    is delegated to ExcelOfficialCore.
    """

    adapter_code = "academic"
    adapter_version = 2

    def build_spec(self, adapter_input: AdapterInput) -> WorkbookSpec:
        payload = adapter_input.authorized_data
        directorate = _clean_text(payload.get("directorate") or adapter_input.snapshot_context.directorate).upper()
        if directorate not in {"DTNH", "DCS"}:
            raise AcademicAdapterError("academic.unsupported_directorate", "AcademicAdapter aceita somente DTNH ou DCS.")
        if adapter_input.snapshot_context.directorate.upper() != directorate:
            raise AcademicAdapterError("academic.snapshot_scope_mismatch", "Diretoria do snapshot diverge do payload autorizado.")

        datasets = _dataset_specs(payload, adapter_input.snapshot_context.authorization_scope)
        period_rows = next(item for item in datasets if item.code == "academic_periods").rows
        course_rows = next(item for item in datasets if item.code == "academic_courses").rows
        discipline_rows = next(item for item in datasets if item.code == "academic_disciplines").rows
        if not period_rows:
            raise AcademicAdapterError("academic.no_periods", "O snapshot acadêmico não possui nenhum semestre disponível.")
        if not course_rows:
            raise AcademicAdapterError("academic.no_courses", "O snapshot acadêmico não possui cursos ativos.")

        period_values = [str(row["period"]) for row in period_rows]
        course_values = {str(row["course"]) for row in course_rows}
        discipline_pairs = {(str(row["course"]), str(row["discipline"])) for row in discipline_rows}
        payload_initial = payload.get("initial", {}) or {}
        requested = dict(payload_initial)
        requested.update(adapter_input.initial_state or {})

        reference = _clean_text(requested.get("reference_period") or requested.get("reference"))
        if reference not in period_values:
            reference = period_values[-1]
        prior = [value for value in period_values if _semester_order(value) < _semester_order(reference)]
        comparison = _clean_text(requested.get("comparison_period") or requested.get("comparison"))
        if comparison == reference or comparison not in period_values:
            comparison = prior[-1] if prior else ""

        course = _clean_text(requested.get("course")) or "(todos)"
        if course != "(todos)" and course not in course_values:
            course = "(todos)"
        discipline = _clean_text(requested.get("discipline")) or "(todas)"
        if discipline != "(todas)":
            if course == "(todos)":
                known_disciplines = {item[1] for item in discipline_pairs}
                if discipline not in known_disciplines:
                    discipline = "(todas)"
            elif (course, discipline) not in discipline_pairs:
                discipline = "(todas)"

        parameters: list[ParameterSpec] = [
            ParameterSpec(
                code="reference_period",
                label="Período de referência",
                values_source="period",
                initial_value=reference,
                editable=True,
                required=True,
                description="Semestre usado nos KPIs, metas e recortes principais.",
                display_order=10,
            ),
        ]
        initial_state: dict[str, Any] = {"reference_period": reference}
        comparison_parameter: str | None = None
        if comparison:
            comparison_parameter = "comparison_period"
            parameters.append(ParameterSpec(
                code="comparison_period",
                label="Comparar com",
                values_source="period",
                initial_value=comparison,
                editable=True,
                required=True,
                description="Semestre utilizado na comparação dos KPIs.",
                display_order=20,
            ))
            initial_state["comparison_period"] = comparison
        history_window = _clean_text(requested.get("history_window", requested.get("window", payload_initial.get("window", 6))))
        if history_window not in {"4", "6", "8", "12", "Todo histórico"}:
            history_window = "6"
        matrix_values = [row["selector_value"] for row in _matrix_metric_rows()]
        matrix_metric = _clean_text(requested.get("matrix_metric") or requested.get("matrix_kpi") or payload_initial.get("matrix_kpi"))
        if matrix_metric not in matrix_values:
            matrix_metric = matrix_values[0]
        parameters.extend((
            ParameterSpec(
                code="history_window",
                label="Janela do gráfico",
                values_source="academic_history_windows",
                values_column="window",
                initial_value=history_window,
                description="4, 6, 8, 12 semestres ou Todo histórico (limitado aos 12 últimos no gráfico).",
                display_order=30,
            ),
            ParameterSpec(
                code="matrix_metric",
                label="KPI da matriz",
                values_source="academic_matrix_metrics",
                values_column="selector_value",
                initial_value=matrix_metric,
                description="Troca o indicador numérico exibido na matriz Curso × Período.",
                display_order=40,
            ),
            ParameterSpec(
                code="course",
                label="Curso",
                values_source="course",
                initial_value=course,
                empty_option="(todos)",
                description="Recorta 01B, Avaliação Docente, Aprovação e Média das Notas. Não altera 01A/01C.",
                display_order=50,
            ),
            ParameterSpec(
                code="discipline",
                label="Disciplina",
                values_source="discipline",
                initial_value=discipline,
                empty_option="(todas)",
                depends_on=("course",),
                description="Recorta Avaliação Docente, Aprovação e Média das Notas. Não altera os NPS.",
                display_order=60,
            ),
        ))
        initial_state.update({"history_window": history_window, "matrix_metric": matrix_metric, "course": course, "discipline": discipline})

        dimensions = (
            DimensionSpec(
                code="period",
                label="Período",
                dataset_code="academic_periods",
                key_column="period",
                label_column="label",
                sort_order_column="sort_order",
            ),
            DimensionSpec(
                code="course",
                label="Curso",
                dataset_code="academic_courses",
                key_column="course",
                label_column="course",
                sort_order_column="sort_order",
            ),
            DimensionSpec(
                code="discipline",
                label="Disciplina",
                dataset_code="academic_disciplines",
                key_column="discipline",
                label_column="discipline",
                sort_order_column="sort_order",
                parent_dimension="course",
                parent_key_column="course",
            ),
        )

        metrics = _metric_specs()
        comparison_arg = comparison_parameter
        kpis = (
            KpiSpec(ACADEMIC_METRICS["nps_institution"], comparison=comparison_arg, priority=10),
            KpiSpec(ACADEMIC_METRICS["nps_course"], comparison=comparison_arg, priority=20),
            KpiSpec(ACADEMIC_METRICS["nps_faculty"], comparison=comparison_arg, priority=30),
            KpiSpec(ACADEMIC_METRICS["teacher"], comparison=comparison_arg, priority=40),
            KpiSpec(ACADEMIC_METRICS["approval"], comparison=comparison_arg, priority=50),
        )
        charts = (
            ChartSpec("academic_nps_institution_evolution", "NPS da Instituição · Alunos", ACADEMIC_METRICS["nps_institution"], "academic_nps_institution", "period", ChartType.LINE, ChartRole.EVOLUTION, window_parameter="history_window", window_reference_parameter="reference_period", window_max_categories=12),
            ChartSpec("academic_nps_course_evolution", "NPS do Curso", ACADEMIC_METRICS["nps_course"], "academic_nps_course", "period", ChartType.LINE, ChartRole.EVOLUTION, window_parameter="history_window", window_reference_parameter="reference_period", window_max_categories=12),
            ChartSpec("academic_nps_faculty_evolution", "NPS da Instituição · Docentes", ACADEMIC_METRICS["nps_faculty"], "academic_nps_faculty", "period", ChartType.LINE, ChartRole.EVOLUTION, window_parameter="history_window", window_reference_parameter="reference_period", window_max_categories=12),
            ChartSpec("academic_teacher_evolution", "Avaliação Docente pelo Aluno", ACADEMIC_METRICS["teacher"], "academic_teacher", "period", ChartType.LINE, ChartRole.EVOLUTION, window_parameter="history_window", window_reference_parameter="reference_period", window_max_categories=12),
            ChartSpec("academic_approval_evolution", "Taxa de Aprovação", ACADEMIC_METRICS["approval"], "academic_results", "period", ChartType.LINE, ChartRole.EVOLUTION, window_parameter="history_window", window_reference_parameter="reference_period", window_max_categories=12),
        )

        quality = QualitySpec(
            dataset_checks=(
                QualityCheckSpec("academic_periods_available", "Semestres disponíveis", "dataset_non_empty", "academic_periods", QualitySeverity.BLOCKING, "Períodos disponíveis", "Nenhum semestre disponível."),
                QualityCheckSpec("academic_courses_available", "Cursos ativos disponíveis", "dataset_non_empty", "academic_courses", QualitySeverity.BLOCKING, "Cursos disponíveis", "Nenhum curso ativo disponível."),
                QualityCheckSpec("academic_nps_required_fields", "Campos obrigatórios do NPS de curso", "dataset_required_fields", "academic_nps_course", QualitySeverity.ERROR, "Base NPS consistente", "Existem campos obrigatórios ausentes no NPS de curso."),
                QualityCheckSpec("academic_teacher_required_fields", "Campos obrigatórios da avaliação docente", "dataset_required_fields", "academic_teacher", QualitySeverity.ERROR, "Base docente consistente", "Existem campos obrigatórios ausentes na avaliação docente."),
                QualityCheckSpec("academic_results_required_fields", "Campos obrigatórios dos resultados", "dataset_required_fields", "academic_results", QualitySeverity.ERROR, "Resultados consistentes", "Existem campos obrigatórios ausentes nos resultados acadêmicos."),
            ),
            metric_checks=(
                QualityCheckSpec("academic_01a_has_data", "01A possui dados no recorte", "metric_has_data", ACADEMIC_METRICS["nps_institution"], QualitySeverity.WARNING, "01A disponível", "01A sem dados no período selecionado."),
                QualityCheckSpec("academic_01a_range", "01A dentro da escala NPS", "metric_valid_range", ACADEMIC_METRICS["nps_institution"], QualitySeverity.ERROR, "01A dentro da faixa", "01A fora de -100 a +100 ou indisponível."),
                QualityCheckSpec("academic_01b_range", "01B dentro da escala NPS", "metric_valid_range", ACADEMIC_METRICS["nps_course"], QualitySeverity.ERROR, "01B dentro da faixa", "01B fora de -100 a +100 ou indisponível."),
                QualityCheckSpec("academic_01c_range", "01C dentro da escala NPS", "metric_valid_range", ACADEMIC_METRICS["nps_faculty"], QualitySeverity.WARNING, "01C dentro da faixa", "01C fora de -100 a +100 ou indisponível."),
                QualityCheckSpec("academic_02_range", "Favorabilidade docente válida", "metric_valid_range", ACADEMIC_METRICS["teacher"], QualitySeverity.WARNING, "KPI 02 disponível", "KPI 02 sem valor válido; revise respostas não mapeadas ou ausência de dados."),
                QualityCheckSpec("academic_03_range", "Aprovação válida", "metric_valid_range", ACADEMIC_METRICS["approval"], QualitySeverity.WARNING, "KPI 03 disponível", "KPI 03 fora de 0–100% ou sem dados."),
            ),
            coverage_checks=(
                QualityCheckSpec("academic_period_dimension", "Dimensão Período", "dimension_non_empty", "period", QualitySeverity.BLOCKING, "Períodos disponíveis", "Dimensão Período vazia."),
                QualityCheckSpec("academic_course_dimension", "Dimensão Curso", "dimension_non_empty", "course", QualitySeverity.BLOCKING, "Cursos disponíveis", "Dimensão Curso vazia."),
                QualityCheckSpec("academic_discipline_dimension", "Dimensão Disciplina", "dimension_non_empty", "discipline", QualitySeverity.WARNING, "Disciplinas disponíveis", "Dimensão Disciplina vazia."),
            ),
            snapshot_checks=(
                QualityCheckSpec("academic_export_id", "Export ID presente", "snapshot_field_present", "export_id", QualitySeverity.BLOCKING, "Export ID identificado", "Export ID ausente."),
                QualityCheckSpec("academic_authorization_scope", "Escopo autorizado presente", "snapshot_field_present", "authorization_scope", QualitySeverity.BLOCKING, "Escopo identificado", "Escopo autorizado ausente."),
                QualityCheckSpec("academic_generated_by", "Usuário exportador identificado", "snapshot_field_present", "generated_by", QualitySeverity.INFO, "Usuário identificado", "Usuário exportador não informado."),
            ),
        )

        limitations = _limitations(payload)
        identity = IdentitySpec(
            workbook_title=f"Painel Acadêmico · {directorate}",
            directorate_code=directorate,
            directorate_label=_clean_text(payload.get("directorate_name")) or directorate,
            adapter_code=self.adapter_code,
            adapter_version=self.adapter_version,
            scope_label=directorate,
        )
        ctx = adapter_input.snapshot_context
        snapshot = SnapshotSpec(
            export_id=ctx.export_id,
            generated_at=ctx.generated_at,
            generated_by=ctx.generated_by,
            authorization_scope=ctx.authorization_scope,
            system_version=ctx.system_version,
            schema_version=ctx.schema_version,
            adapter_version=self.adapter_version,
            initial_scope=dict(ctx.initial_filters),
            minimum_period=ctx.minimum_period or period_values[0],
            maximum_period=ctx.maximum_period or period_values[-1],
            payload_hash=ctx.payload_hash,
        )

        domain_sheets = tuple(
            DomainSheetSpec(code=code, label=label, dataset_code=dataset, purpose=purpose, sheet_role=SheetRole.RAW_DATA)
            for code, label, dataset, purpose in (
                ("nps_institution", "NPS Instituição", "academic_nps_institution", "Base oficial do NPS institucional dos alunos."),
                ("nps_course", "NPS Curso", "academic_nps_course", "Base oficial do NPS por curso."),
                ("nps_faculty", "NPS Docentes", "academic_nps_faculty", "Base institucional anônima do NPS docente."),
                ("nps_distribution", "NPS Distribuição", "academic_nps_distribution", "Distribuição oficial 0–10 para auditoria do NPS."),
                ("teacher", "Avaliação Docente", "academic_teacher", "Agregados oficiais de favorabilidade docente."),
                ("results", "Resultados Acadêmicos", "academic_results", "Agregados oficiais de resultados por curso/disciplina."),
            )
        )

        return WorkbookSpec(
            identity=identity,
            snapshot=snapshot,
            initial_state=InitialStateSpec(values=initial_state),
            parameters=tuple(parameters),
            datasets=datasets,
            dimensions=dimensions,
            metric_codes=tuple(metric.code for metric in metrics),
            metric_bindings=_metric_bindings(),
            domain_sheets=domain_sheets,
            dashboard=DashboardSpec(
                title=f"PAINEL ACADÊMICO · {directorate}",
                kpis=kpis,
                charts=charts,
                attention_blocks=(
                    "01A · NPS da Instituição (alunos) é institucional e não varia com Curso/Disciplina.",
                    "01C · NPS da Instituição (docentes) usa população anônima e não varia com Curso/Disciplina.",
                    "KPI 02 · Favorabilidade Docente fica indisponível quando existirem respostas ainda não mapeadas.",
                ),
            ),
            matrix=MatrixSpec(
                metric_code=ACADEMIC_METRICS["nps_institution_course"],
                row_dimension="course",
                column_dimension="period",
                target=None,
                delta=True,
                sorting="dimension_asc",
                empty_behavior="blank",
                metric_selector_parameter="matrix_metric",
                metric_options=(
                    MatrixMetricOptionSpec("01A · NPS Instituição · Alunos", ACADEMIC_METRICS["nps_institution_course"]),
                    MatrixMetricOptionSpec("01B · NPS do Curso", ACADEMIC_METRICS["nps_course"]),
                    MatrixMetricOptionSpec("02 · Avaliação Docente", ACADEMIC_METRICS["teacher"], display_scale=100.0, skip_dimensions=("discipline",)),
                    MatrixMetricOptionSpec("03 · Aprovação", ACADEMIC_METRICS["approval"], display_scale=100.0, skip_dimensions=("discipline",)),
                ),
                selector_number_format='0.0',
            ),
            quality=quality,
            action_plan=ActionPlanSpec(
                enabled=True,
                official_fields=(),
                local_editable_fields=("indicator", "problem", "diagnosis", "action", "owner", "deadline", "status"),
                rows=_action_rows(payload),
                local_blank_rows=8,
                status_options=("Não iniciado", "Em andamento", "Concluído", "Suspenso", "Cancelado"),
                completed_statuses=("Concluído", "Cancelado"),
            ),
            technical=TechnicalSpec(
                include_targets=True,
                include_indicators=True,
                include_calc=True,
                include_support_lists=True,
                include_period_dimension=True,
                include_month_dimension=False,
            ),
            capabilities=AdapterCapabilities(
                supports_comparison=bool(comparison_parameter),
                supports_history_window=True,
                supports_action_plan=True,
                interactive_dimensions=("period", "course", "discipline"),
            ),
            limitations=limitations,
            metrics=metrics,
            target_bindings=(
                TargetBindingSpec(ACADEMIC_METRICS["nps_institution"], "academic_goals_base", "target_points", "attention_points", criteria_parameters={"period": "reference_period", "course": "course"}, criteria_constants={"legacy_kpi": payload["codes"]["nps_institution"], "discipline": "(todas)"}),
                TargetBindingSpec(ACADEMIC_METRICS["nps_institution_course"], "academic_goals_base", "target_points", "attention_points", criteria_parameters={"period": "reference_period", "course": "course"}, criteria_constants={"legacy_kpi": payload["codes"]["nps_institution"], "discipline": "(todas)"}),
                TargetBindingSpec(ACADEMIC_METRICS["nps_course"], "academic_goals_base", "target_points", "attention_points", criteria_parameters={"period": "reference_period", "course": "course"}, criteria_constants={"legacy_kpi": payload["codes"]["nps_course"], "discipline": "(todas)"}),
                TargetBindingSpec(ACADEMIC_METRICS["nps_faculty"], "academic_goals_base", "target_points", "attention_points", criteria_parameters={"period": "reference_period"}, criteria_constants={"legacy_kpi": payload["codes"]["nps_faculty"], "course": "(todos)", "discipline": "(todas)"}),
                TargetBindingSpec(ACADEMIC_METRICS["teacher"], "academic_goals_base", "target_points", "attention_points", criteria_parameters={"period": "reference_period", "course": "course", "discipline": "discipline"}, criteria_constants={"legacy_kpi": payload["codes"]["teacher"]}, value_scale=0.01),
                TargetBindingSpec(ACADEMIC_METRICS["approval"], "academic_goals_base", "target_points", "attention_points", criteria_parameters={"period": "reference_period", "course": "course", "discipline": "discipline"}, criteria_constants={"legacy_kpi": payload["codes"]["approval"]}, value_scale=0.01),
            ),
        )


__all__ = ["ACADEMIC_METRICS", "AcademicAdapter", "AcademicAdapterError"]
