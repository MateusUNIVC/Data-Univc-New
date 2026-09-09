from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Directorate(Base):
    __tablename__ = "directorates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    full_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), default="viewer")
    directorate_id: Mapped[int | None] = mapped_column(ForeignKey("directorates.id"), nullable=True)
    directorate: Mapped[Directorate | None] = relationship()


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("auth_provider", "auth_provider_id", name="uq_app_user_provider_identity"),
        CheckConstraint("global_role in ('REITORIA','DIRECTORATE')", name="ck_app_users_global_role"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    auth_provider: Mapped[str] = mapped_column(String(30), default="SUPABASE")
    auth_provider_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    global_role: Mapped[str] = mapped_column(String(30), default="DIRECTORATE")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    permission_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserDirectorateAccess(Base):
    __tablename__ = "user_directorate_access"
    __table_args__ = (
        CheckConstraint("access_level in ('READ','EDIT')", name="ck_user_directorate_access_level"),
        Index("ix_user_directorate_access_directorate", "directorate_id"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id", ondelete="CASCADE"), primary_key=True)
    access_level: Mapped[str] = mapped_column(String(10), default="READ")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[AppUser] = relationship()
    directorate: Mapped[Directorate] = relationship()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_token_family", "token_family"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_family: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    family_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user: Mapped[AppUser] = relationship()


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_log"
    __table_args__ = (
        Index("ix_auth_audit_event_created", "event_type", "created_at"),
        Index("ix_auth_audit_actor_created", "actor_user_id", "created_at"),
        Index("ix_auth_audit_target_created", "target_user_id", "created_at"),
        Index("ix_auth_audit_email_created", "email", "created_at"),
        Index("ix_auth_audit_ip_created", "ip_hash", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(60))
    outcome: Mapped[str] = mapped_column(String(20), default="INFO")
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True)
    target_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    directorate_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("directorate_id", "name", name="uq_course_directorate_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    modality: Mapped[str] = mapped_column(String(30), default="Presencial")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[str] = mapped_column(String(7), default="2026-01")
    valid_to: Mapped[str | None] = mapped_column(String(7), nullable=True)


class Discipline(Base):
    __tablename__ = "disciplines"
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_discipline_course_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[str] = mapped_column(String(7), default="2026-01")
    valid_to: Mapped[str | None] = mapped_column(String(7), nullable=True)
    course: Mapped[Course] = relationship()


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    directorate_code: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(220))
    periodicity: Mapped[str | None] = mapped_column(String(40))
    formula_text: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class IndicatorSchedule(Base):
    __tablename__ = "indicator_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_code: Mapped[str] = mapped_column(ForeignKey("indicator_definitions.code"), unique=True, index=True)
    reference_grain: Mapped[str] = mapped_column(String(30), default="monthly")
    due_business_day: Mapped[int] = mapped_column(Integer, default=5)
    collection_window_start_business_day: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class NpsStudent(Base):
    __tablename__ = "nps_student"
    __table_args__ = (UniqueConstraint("directorate_id", "period", "course_id", name="uq_nps_period_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    respondents: Mapped[int] = mapped_column(Integer)
    promoters: Mapped[int] = mapped_column(Integer)
    neutrals: Mapped[int] = mapped_column(Integer)
    detractors: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(30), default="manual")
    survey_run_id: Mapped[int | None] = mapped_column(ForeignKey("survey_runs.id"), nullable=True, index=True)
    survey_question_id: Mapped[int | None] = mapped_column(ForeignKey("survey_questions.id"), nullable=True, index=True)
    course: Mapped[Course] = relationship()


class NpsInstitution(Base):
    __tablename__ = "nps_institution"
    __table_args__ = (UniqueConstraint("directorate_id", "period", name="uq_nps_institution_directorate_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    respondents: Mapped[int] = mapped_column(Integer)
    promoters: Mapped[int] = mapped_column(Integer)
    neutrals: Mapped[int] = mapped_column(Integer)
    detractors: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(30), default="SEI_SURVEY")
    survey_run_id: Mapped[int | None] = mapped_column(ForeignKey("survey_runs.id"), nullable=True, index=True)
    survey_question_id: Mapped[int | None] = mapped_column(ForeignKey("survey_questions.id"), nullable=True, index=True)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("directorate_id", "period", "course_id", name="uq_enrollment_period_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    active_enrollments: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    course: Mapped[Course] = relationship()


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("directorate_id", "period", "course_id", "discipline_id", name="uq_attendance_period_course_discipline"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"), index=True)
    expected_attendance: Mapped[int] = mapped_column(Integer)
    recorded_attendance: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    course: Mapped[Course] = relationship()
    discipline: Mapped[Discipline] = relationship()


class TeacherEvaluation(Base):
    __tablename__ = "teacher_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "course_id", "discipline_id", "teacher_name",
            name="uq_teacher_eval_period_course_discipline_teacher",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"), index=True)
    teacher_name: Mapped[str] = mapped_column(String(180), index=True)
    respondents: Mapped[int] = mapped_column(Integer)
    average_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    course: Mapped[Course] = relationship()
    discipline: Mapped[Discipline] = relationship()


class AcademicStudent(Base):
    __tablename__ = "academic_students"
    __table_args__ = (UniqueConstraint("directorate_id", "registration", name="uq_academic_student_registration"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    registration: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(220), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    course: Mapped[Course] = relationship()


class AcademicResult(Base):
    __tablename__ = "academic_results"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "course_id", "discipline_id", "student_id", "class_group",
            name="uq_academic_result_student_discipline_class_period",
        ),
        Index("ix_academic_results_dir_period_course_disc", "directorate_id", "period", "course_id", "discipline_id"),
        Index("ix_academic_results_dir_period_status_reason", "directorate_id", "period", "approved", "failure_reason"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("academic_students.id"), index=True)
    class_group: Mapped[str] = mapped_column(String(120), default="")
    curriculum_period: Mapped[str | None] = mapped_column(String(80), nullable=True)
    final_average: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    official_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    course: Mapped[Course] = relationship()
    discipline: Mapped[Discipline] = relationship()
    student: Mapped[AcademicStudent] = relationship()


class DadmAttrition(Base):
    __tablename__ = "dadm_attrition"
    __table_args__ = (UniqueConstraint("directorate_id", "period", "course_id", name="uq_dadm_attrition_period_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    active_students_start: Mapped[int] = mapped_column(Integer)
    departures: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))
    course: Mapped[Course] = relationship()


class DadmActiveStudents(Base):
    __tablename__ = "dadm_active_students"
    __table_args__ = (UniqueConstraint("directorate_id", "period", "modality", name="uq_dadm_active_students_period_modality"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    modality: Mapped[str] = mapped_column(String(80))
    active_students: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))


class DadmAdministrativeCost(Base):
    __tablename__ = "dadm_administrative_costs"
    __table_args__ = (UniqueConstraint("directorate_id", "period", "cost_center", "modality", name="uq_dadm_admin_cost_period_center_modality"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    cost_center: Mapped[str] = mapped_column(String(160))
    modality: Mapped[str] = mapped_column(String(80))
    expense_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))


class DadmInfrastructure(Base):
    __tablename__ = "dadm_infrastructure"
    __table_args__ = (UniqueConstraint("directorate_id", "period", name="uq_dadm_infrastructure_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    infrastructure_expense: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    area_in_use_m2: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))


class DpeOperatingResult(Base):
    __tablename__ = "dpe_operating_results"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "scope_type", "scope_label",
            name="uq_dpe_result_period_scope",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    scope_type: Mapped[str] = mapped_column(String(60))
    scope_label: Mapped[str] = mapped_column(String(180))
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    total_expense: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))


class DpeBudgetExecution(Base):
    __tablename__ = "dpe_budget_execution"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "budget_directorate", "cost_center",
            name="uq_dpe_budget_period_unit_center",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    budget_directorate: Mapped[str] = mapped_column(String(40))
    cost_center: Mapped[str] = mapped_column(String(180))
    budgeted_expense: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    actual_expense: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))


class DpeCashMovement(Base):
    __tablename__ = "dpe_cash_movements"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "account", "movement_type", "nature",
            name="uq_dpe_cash_period_account_type_nature",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    account: Mapped[str] = mapped_column(String(180))
    movement_type: Mapped[str] = mapped_column(String(20))
    nature: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255))


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("directorate_id", "indicator_code", "scope_label", "valid_from", name="uq_goal_scope_vigency"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(30), index=True)
    scope_label: Mapped[str] = mapped_column(String(200), default="TOTAL")
    valid_from: Mapped[str] = mapped_column(String(16), index=True)
    target: Mapped[float] = mapped_column(Float)
    attention: Mapped[float] = mapped_column(Float)
    upper_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text)


class ActionPlan(Base):
    __tablename__ = "action_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    month: Mapped[str] = mapped_column(String(7), index=True)
    indicator_code: Mapped[str] = mapped_column(String(30), index=True)
    scope_label: Mapped[str] = mapped_column(String(200))
    result_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    problem: Mapped[str] = mapped_column(Text)
    probable_cause: Mapped[str | None] = mapped_column(Text)
    corrective_action: Mapped[str] = mapped_column(Text)
    responsible: Mapped[str] = mapped_column(String(180))
    due_date: Mapped[date] = mapped_column(Date)
    action_target: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int | None] = mapped_column(ForeignKey("directorates.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DmCohort(Base):
    """Turma formalmente aberta em uma das duas áreas do Mestrado.

    A turma, e não o semestre, é a unidade de acompanhamento do DM. A data de
    abertura é metadado opcional da coorte; os prazos acadêmicos usam o ingresso
    individual do estudante, confirmado manualmente ou pela consulta ao SEI.
    """

    __tablename__ = "dm_cohorts"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "area_code", "cohort_number",
            name="uq_dm_cohort_area_number",
        ),
        Index("ix_dm_cohort_dir_area_opening", "directorate_id", "area_code", "opening_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    area_code: Mapped[str] = mapped_column(String(12), index=True)
    area_name: Mapped[str] = mapped_column(String(180))
    cohort_number: Mapped[int] = mapped_column(Integer, index=True)
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    vacancies_authorized: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="Em andamento", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    sei_raw_label: Mapped[str | None] = mapped_column(String(220), nullable=True)
    last_seen_sei_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    students: Mapped[list["DmStudent"]] = relationship(back_populates="cohort")


class DmStudent(Base):
    """Estudante vinculado a uma turma do Mestrado e suas datas acadêmicas."""

    __tablename__ = "dm_students"
    __table_args__ = (
        UniqueConstraint("directorate_id", "student_code", name="uq_dm_student_code"),
        CheckConstraint("status in ('Ativo','Titulado','Desligado')", name="ck_dm_student_status"),
        CheckConstraint("defense_date is null or status = 'Titulado'", name="ck_dm_student_defense_titulated"),
        Index("ix_dm_student_dir_cohort_status", "directorate_id", "cohort_id", "status"),
        Index("ix_dm_student_dir_entry", "directorate_id", "entry_date"),
        Index("ix_dm_student_dir_defense", "directorate_id", "defense_date"),
        Index("ix_dm_student_dir_graduation", "directorate_id", "graduation_date"),
        Index("ix_dm_student_dir_diploma", "directorate_id", "diploma_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    cohort_id: Mapped[int] = mapped_column(ForeignKey("dm_cohorts.id"), index=True)
    student_code: Mapped[str] = mapped_column(String(80), index=True)
    student_name: Mapped[str] = mapped_column(String(220))
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    qualification_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    defense_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    defense_scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="Ativo", index=True)
    advisor: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    research_line: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    diploma_status: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    graduation_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    graduation_updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_date_estimated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source_system: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    sei_raw_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_seen_sei_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_course_dates_sei_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cohort: Mapped[DmCohort] = relationship(back_populates="students")


class DmGraduationEvent(Base):
    """Audit trail for individual and bulk titulation/digital-diploma changes."""

    __tablename__ = "dm_graduation_events"
    __table_args__ = (
        Index("ix_dm_grad_event_dir_created", "directorate_id", "created_at"),
        Index("ix_dm_grad_event_student_created", "student_id", "created_at"),
        Index("ix_dm_grad_event_operation", "operation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("dm_students.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[str] = mapped_column(String(64), index=True)
    operation_type: Mapped[str] = mapped_column(String(30), default="bulk")
    previous_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    previous_defense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_diploma_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(40), default="Titulado")
    new_defense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_diploma_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DmSeiSyncRun(Base):
    """Auditable summary of a DM roster synchronization with the legacy SEI.

    Credentials and student names are deliberately not stored here. The row keeps
    only operational counts, the report digest and non-sensitive warnings.
    """

    __tablename__ = "dm_sei_sync_runs"
    __table_args__ = (
        Index("ix_dm_sei_sync_dir_completed", "directorate_id", "completed_at"),
        Index("ix_dm_sei_sync_source_hash", "source_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), default="upload")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="Concluída", index=True)
    cohorts_detected: Mapped[int] = mapped_column(Integer, default=0)
    students_detected: Mapped[int] = mapped_column(Integer, default=0)
    cohorts_created: Mapped[int] = mapped_column(Integer, default=0)
    cohorts_updated: Mapped[int] = mapped_column(Integer, default=0)
    students_created: Mapped[int] = mapped_column(Integer, default=0)
    students_updated: Mapped[int] = mapped_column(Integer, default=0)
    students_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    students_not_seen: Mapped[int] = mapped_column(Integer, default=0)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ManagementMeasurement(Base):
    """Generic, auditable measurements for the redesigned DADM, DPE and DM modules.

    Raw components are persisted as JSON text instead of only the computed KPI.
    This keeps the original evidence available and lets calculation policies evolve
    without losing the data that produced an institutional indicator.
    """

    __tablename__ = "management_indicator_measurements"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "indicator_code", "period", "dimension_key",
            name="uq_management_measurement_period_dimension",
        ),
        Index(
            "ix_management_measurement_dir_indicator_period",
            "directorate_id", "indicator_code", "period",
        ),
        Index(
            "ix_management_measurement_dir_period",
            "directorate_id", "period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(30), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), default="TOTAL", index=True)
    dimension_label: Mapped[str] = mapped_column(String(240), default="TOTAL")
    dimensions_json: Mapped[str] = mapped_column(Text, default="{}")
    values_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ManagementTarget(Base):
    """Versioned targets for one metric and optional dimensional scope."""

    __tablename__ = "management_indicator_targets"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "indicator_code", "metric_key", "dimension_key", "valid_from",
            name="uq_management_target_metric_scope_vigency",
        ),
        Index(
            "ix_management_target_lookup",
            "directorate_id", "indicator_code", "metric_key", "valid_from",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(30), index=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), default="TOTAL", index=True)
    dimension_label: Mapped[str] = mapped_column(String(240), default="TOTAL")
    valid_from: Mapped[str] = mapped_column(String(16), index=True)
    valid_to: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    attention: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    attention_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    attention_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ManagementAction(Base):
    """Action plan connected to a managerial KPI and period."""

    __tablename__ = "management_indicator_actions"
    __table_args__ = (
        Index(
            "ix_management_action_dir_indicator_period",
            "directorate_id", "indicator_code", "period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(30), index=True)
    metric_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), default="TOTAL", index=True)
    dimension_label: Mapped[str] = mapped_column(String(240), default="TOTAL")
    problem: Mapped[str] = mapped_column(Text)
    probable_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str] = mapped_column(Text)
    responsible: Mapped[str] = mapped_column(String(180))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="Aberto")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DPEMonthlyRevenue(Base):
    """Official monthly institutional net revenue used by every DPE KPI.

    v0.7.7 intentionally stores the institutional revenue only once. Course
    revenue is an optional analytical allocation and never replaces this row.
    """

    __tablename__ = "dpe_monthly_revenues"
    __table_args__ = (
        UniqueConstraint("directorate_id", "period", name="uq_dpe_monthly_revenue_period"),
        Index("ix_dpe_monthly_revenue_period", "directorate_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DPECourseRevenue(Base):
    """Optional allocation of institutional revenue to an academic course.

    The sum is allowed to be lower than the institutional revenue because the
    institution also has technical, distance, hybrid, graduate and other
    revenue streams that are not represented by the current DTNH/DCS catalog.
    """

    __tablename__ = "dpe_course_revenues"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "course_id", name="uq_dpe_course_revenue_period_course"
        ),
        Index("ix_dpe_course_revenue_period", "directorate_id", "period"),
        Index("ix_dpe_course_revenue_course", "directorate_id", "course_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    allocated_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    course: Mapped[Course] = relationship()


class DPEExpense(Base):
    """Single source of truth for an institutional expense.

    Payroll is represented as ``expense_kind='PAYROLL'`` instead of living in
    a separate financial total. Course views are created by allocations, which
    prevents a payroll amount from being added again when analysing a course.
    """

    __tablename__ = "dpe_expenses"
    __table_args__ = (
        Index("ix_dpe_expense_period", "directorate_id", "period"),
        Index("ix_dpe_expense_kind", "directorate_id", "expense_kind", "period"),
        Index("ix_dpe_expense_category", "directorate_id", "category", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    description: Mapped[str] = mapped_column(String(240))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    expense_kind: Mapped[str] = mapped_column(String(30), default="GENERAL", index=True)
    category: Mapped[str] = mapped_column(String(40), default="OTHER", index=True)
    payroll_group: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    payroll_nature: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    is_capex: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DPEExpenseAllocation(Base):
    """Analytical allocation of one real expense to one course.

    Allocations never create new institutional expenditure. Their sum may be
    lower than the expense amount when part of a cost remains institutional or
    belongs to activities outside the current course catalog.
    """

    __tablename__ = "dpe_expense_allocations"
    __table_args__ = (
        UniqueConstraint("expense_id", "course_id", name="uq_dpe_expense_allocation_course"),
        Index("ix_dpe_expense_allocation_expense", "expense_id"),
        Index("ix_dpe_expense_allocation_course", "course_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("dpe_expenses.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    expense: Mapped[DPEExpense] = relationship()
    course: Mapped[Course] = relationship()


class DPECourseCostSnapshot(Base):
    """Optional management total for a course/month used for reconciliation.

    It is *not* an institutional expense. The institutional expense total comes
    exclusively from :class:`DPEExpense`. This allows the user to work with a
    known course total before every component has been allocated, without
    double counting the same payroll or shared cost.
    """

    __tablename__ = "dpe_course_cost_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "directorate_id", "period", "course_id", name="uq_dpe_course_cost_period_course"
        ),
        Index("ix_dpe_course_cost_period", "directorate_id", "period"),
        Index("ix_dpe_course_cost_course", "directorate_id", "course_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    reported_total_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    details_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    course: Mapped[Course] = relationship()

# ---------------------------------------------------------------------------
# v0.8.5 - Avaliações institucionais importadas do SEI
# ---------------------------------------------------------------------------

class SurveyImport(Base):
    __tablename__ = "survey_imports"
    __table_args__ = (
        UniqueConstraint("directorate_id", "sha256", name="uq_survey_import_directorate_sha256"),
        UniqueConstraint("directorate_id", "external_key", name="uq_survey_import_directorate_external_key"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    directorate_id: Mapped[int | None] = mapped_column(ForeignKey("directorates.id"), nullable=True, index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_kind: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(20), default="manual", index=True)
    external_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SurveyQuestionnaire(Base):
    __tablename__ = "survey_questionnaires"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    sei_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)


class SurveyRun(Base):
    __tablename__ = "survey_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int | None] = mapped_column(ForeignKey("directorates.id"), nullable=True, index=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("survey_imports.id"), unique=True, index=True)
    questionnaire_id: Mapped[int] = mapped_column(ForeignKey("survey_questionnaires.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(400), nullable=True)
    period_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    run_kind: Mapped[str] = mapped_column(String(40), default="generic", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    questionnaire: Mapped[SurveyQuestionnaire] = relationship()


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(String(800), unique=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    detected_metric_type: Mapped[str] = mapped_column(String(30), default="categorical")
    nps_candidate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class SurveyQuestionnaireQuestion(Base):
    __tablename__ = "survey_questionnaire_questions"
    __table_args__ = (
        UniqueConstraint("questionnaire_id", "question_id", name="uq_survey_questionnaire_question"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    questionnaire_id: Mapped[int] = mapped_column(ForeignKey("survey_questionnaires.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class SurveyRunCourse(Base):
    __tablename__ = "survey_run_courses"
    __table_args__ = (UniqueConstraint("run_id", "course_id", name="uq_survey_run_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    source_path: Mapped[str] = mapped_column(String(500))
    respondent_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    course: Mapped[Course] = relationship()


class SurveyResponseAggregate(Base):
    __tablename__ = "survey_response_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "course_id", "question_id", "option_key",
            name="uq_survey_response_aggregate",
        ),
        Index("ix_survey_response_run_question", "run_id", "question_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    option_label: Mapped[str] = mapped_column(String(500))
    option_key: Mapped[str] = mapped_column(String(500))
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    source_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)


class SurveyRawResponse(Base):
    __tablename__ = "survey_raw_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    response_text: Mapped[str] = mapped_column(Text)
    response_key: Mapped[str] = mapped_column(String(800), index=True)


class SurveyNpsSource(Base):
    __tablename__ = "survey_nps_sources"
    __table_args__ = (
        UniqueConstraint("directorate_id", "semester", name="uq_survey_nps_directorate_semester"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    semester: Mapped[str] = mapped_column(String(16), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SurveyInstitutionNpsSource(Base):
    __tablename__ = "survey_nps_institution_sources"
    __table_args__ = (
        UniqueConstraint("directorate_id", "semester", name="uq_survey_nps_institution_directorate_semester"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    semester: Mapped[str] = mapped_column(String(16), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SurveyFacultyInstitutionContext(Base):
    __tablename__ = "survey_faculty_institution_contexts"
    __table_args__ = (
        UniqueConstraint("run_id", "source_path", name="uq_survey_faculty_institution_context"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    source_path: Mapped[str] = mapped_column(String(500))
    unit_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    respondent_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SurveyFacultyInstitutionResponseAggregate(Base):
    __tablename__ = "survey_faculty_institution_response_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "context_id", "question_id", "option_key",
            name="uq_survey_faculty_institution_response_aggregate",
        ),
        Index("ix_survey_faculty_institution_run_question", "question_id", "context_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("survey_faculty_institution_contexts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    option_label: Mapped[str] = mapped_column(String(500))
    option_key: Mapped[str] = mapped_column(String(500))
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    source_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)


class SurveyFacultyInstitutionRawResponse(Base):
    __tablename__ = "survey_faculty_institution_raw_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("survey_faculty_institution_contexts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    response_text: Mapped[str] = mapped_column(Text)
    response_key: Mapped[str] = mapped_column(String(800), index=True)


class SurveyFacultyNpsSource(Base):
    __tablename__ = "survey_nps_faculty_sources"
    __table_args__ = (
        UniqueConstraint("semester", name="uq_survey_nps_faculty_semester"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester: Mapped[str] = mapped_column(String(16), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class NpsInstitutionFaculty(Base):
    __tablename__ = "nps_institution_faculty"
    __table_args__ = (UniqueConstraint("period", name="uq_nps_institution_faculty_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    respondents: Mapped[int] = mapped_column(Integer)
    promoters: Mapped[int] = mapped_column(Integer)
    neutrals: Mapped[int] = mapped_column(Integer)
    detractors: Mapped[int] = mapped_column(Integer)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inserted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="SEI_SURVEY")
    survey_run_id: Mapped[int | None] = mapped_column(ForeignKey("survey_runs.id"), nullable=True, index=True)
    survey_question_id: Mapped[int | None] = mapped_column(ForeignKey("survey_questions.id"), nullable=True, index=True)


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_teacher_normalized_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    display_name: Mapped[str] = mapped_column(String(220), index=True)
    normalized_name: Mapped[str] = mapped_column(String(220), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AcademicOffering(Base):
    __tablename__ = "academic_offerings"
    __table_args__ = (
        UniqueConstraint(
            "period", "course_id", "discipline_id", "class_group",
            name="uq_academic_offering_period_course_discipline_class",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"), index=True)
    class_group: Mapped[str] = mapped_column(String(120), default="")
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    course: Mapped[Course] = relationship()
    discipline: Mapped[Discipline] = relationship()


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"
    __table_args__ = (UniqueConstraint("offering_id", "teacher_id", name="uq_teaching_assignment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offering_id: Mapped[int] = mapped_column(ForeignKey("academic_offerings.id"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    offering: Mapped[AcademicOffering] = relationship()
    teacher: Mapped[Teacher] = relationship()


class FacultyEvaluationContext(Base):
    __tablename__ = "faculty_evaluation_contexts"
    __table_args__ = (
        UniqueConstraint("run_id", "teaching_assignment_id", "source_key", name="uq_faculty_context_source"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("survey_runs.id"), index=True)
    teaching_assignment_id: Mapped[int] = mapped_column(ForeignKey("teaching_assignments.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(500))
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    respondent_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FacultyResponseAggregate(Base):
    __tablename__ = "faculty_response_aggregates"
    __table_args__ = (
        UniqueConstraint("context_id", "question_id", "option_key", name="uq_faculty_response_aggregate"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("faculty_evaluation_contexts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    option_label: Mapped[str] = mapped_column(String(500))
    option_key: Mapped[str] = mapped_column(String(500))
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    source_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)


class FacultyRawResponse(Base):
    __tablename__ = "faculty_raw_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(ForeignKey("faculty_evaluation_contexts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), index=True)
    response_text: Mapped[str] = mapped_column(Text)
    response_key: Mapped[str] = mapped_column(String(800), index=True)


# ---------------------------------------------------------------------------
# v0.8.19.0 - DADM / TALLOS Analytics Center
# ---------------------------------------------------------------------------

class DADMTallosSyncRun(Base):
    """Rastreabilidade de cada sincronização de relatórios TALLOS."""

    __tablename__ = "dadm_tallos_sync_runs"
    __table_args__ = (
        Index("ix_dadm_tallos_sync_dir_created", "directorate_id", "created_at"),
        Index("ix_dadm_tallos_sync_dir_status", "directorate_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    trigger: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    total_expected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DADMTallosDepartmentMap(Base):
    """Tradução governada do identificador TALLOS para nome legível."""

    __tablename__ = "dadm_tallos_department_map"
    __table_args__ = (
        UniqueConstraint("directorate_id", "source_key", name="uq_dadm_tallos_department_source"),
        Index("ix_dadm_tallos_department_active", "directorate_id", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(240), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DADMTallosAttendance(Base):
    """Fato operacional normalizado de ``GET /v4/reports``.

    Não persiste nome, telefone, CPF ou CNPJ do cliente. ``customer_ref`` é um
    identificador opaco usado somente para contagens distintas. O JSON de
    auditoria é uma whitelist operacional sanitizada.
    """

    __tablename__ = "dadm_tallos_attendances"
    __table_args__ = (
        UniqueConstraint("directorate_id", "source_id", name="uq_dadm_tallos_attendance_source"),
        Index("ix_dadm_tallos_attendance_dir_date", "directorate_id", "reference_date"),
        Index("ix_dadm_tallos_attendance_dir_month", "directorate_id", "month_key"),
        Index("ix_dadm_tallos_attendance_dir_employee_date", "directorate_id", "employee_id", "reference_date"),
        Index("ix_dadm_tallos_attendance_dir_department_date", "directorate_id", "department_key", "reference_date"),
        Index("ix_dadm_tallos_attendance_dir_channel_date", "directorate_id", "channel", "reference_date"),
        Index("ix_dadm_tallos_attendance_dir_status_date", "directorate_id", "status", "reference_date"),
        Index("ix_dadm_tallos_attendance_dir_protocol", "directorate_id", "protocol"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 10", name="ck_dadm_tallos_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(160), index=True)
    protocol: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    customer_ref: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    employee_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    employee_name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    department_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    department_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    tabulation: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tme_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    tma_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmro_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmrc_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    messages_received: Mapped[int] = mapped_column(Integer, default=0)
    initiated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transferred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    redistribution_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_business_period: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sessions_opened: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reference_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reference_date: Mapped[date] = mapped_column(Date, index=True)
    month_key: Mapped[str] = mapped_column(String(7), index=True)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    last_sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("dadm_tallos_sync_runs.id"), nullable=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
