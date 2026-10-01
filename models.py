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
    valid_from: Mapped[str] = mapped_column(String(7))
    valid_to: Mapped[str | None] = mapped_column(String(7), nullable=True)


class Discipline(Base):
    __tablename__ = "disciplines"
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_discipline_course_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[str] = mapped_column(String(7))
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
    metric_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


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


class DmSeiStudentRefreshRun(Base):
    """Persistent queue header for the DM student-by-student SEI refresh.

    Credentials are deliberately never persisted.  A run only stores the selected
    scope, operational counters/timestamps and the requesting Data UNIVC user.
    """

    __tablename__ = "dm_sei_student_refresh_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('PENDING','IN_PROGRESS','PAUSED','COMPLETED','COMPLETED_WITH_ERRORS','CANCELLED')",
            name="ck_dm_sei_student_refresh_run_status",
        ),
        Index("ix_dm_sei_student_refresh_run_dir_created", "directorate_id", "created_at"),
        Index("ix_dm_sei_student_refresh_run_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    scope_type: Mapped[str] = mapped_column(String(30), default="students")
    scope_json: Mapped[str] = mapped_column(Text, default="{}")
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_batch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DmSeiStudentRefreshItem(Base):
    """One persisted student in a DM SEI refresh queue run."""

    __tablename__ = "dm_sei_student_refresh_items"
    __table_args__ = (
        UniqueConstraint("run_id", "student_id", name="uq_dm_sei_student_refresh_run_student"),
        CheckConstraint(
            "status in ('PENDING','RUNNING','COMPLETED','FAILED')",
            name="ck_dm_sei_student_refresh_item_status",
        ),
        Index("ix_dm_sei_student_refresh_item_run_status", "run_id", "status", "id"),
        Index("ix_dm_sei_student_refresh_item_student", "student_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("dm_sei_student_refresh_runs.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("dm_students.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


# ---------------------------------------------------------------------------
# v0.9.6.13 - DPE Cost Engine Foundation
# ---------------------------------------------------------------------------


class DPECostPeriod(Base):
    """Monthly accounting/costing competence for the DPE cost engine.

    A competence is the historical boundary of the new DPE domain. Later
    stages attach expenses, academic snapshots and calculation runs to this
    record so changes in the live catalog never rewrite a closed month.
    """

    __tablename__ = "dpe_cost_periods"
    __table_args__ = (
        UniqueConstraint("directorate_id", "period", name="uq_dpe_cost_period"),
        CheckConstraint(
            "status in ('DRAFT','REVIEW','CALCULATED','CLOSED')",
            name="ck_dpe_cost_period_status",
        ),
        Index("ix_dpe_cost_period_status", "directorate_id", "status", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    opened_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()


class DPEAcademicProduct(Base):
    """DPE course identity linked to the official DTNH/DCS academic catalog.

    The course is the primary business entity. Internal economic contexts may
    distinguish shift, unit, location or modality only when separate analysis is
    actually required.
    """

    __tablename__ = "dpe_academic_products"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_academic_product_code"),
        CheckConstraint(
            "academic_level in ('GRADUATION','TECHNICAL','POSTGRADUATE','EXTENSION','OTHER')",
            name="ck_dpe_academic_product_level",
        ),
        CheckConstraint("valid_to is null or valid_to >= valid_from", name="ck_dpe_academic_product_validity"),
        Index("ix_dpe_academic_product_active", "directorate_id", "active", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(220), index=True)
    academic_level: Mapped[str] = mapped_column(String(30), default="GRADUATION")
    source_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    valid_from: Mapped[str] = mapped_column(String(7))
    valid_to: Mapped[str | None] = mapped_column(String(7), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()
    source_course: Mapped[Course | None] = relationship()


class DPEAcademicOffering(Base):
    """Internal economic context used as the DPE cost object.

    Every course can operate through an automatic base context. Additional
    contexts are optional and exist only when shift, unit, location or modality
    must be analyzed separately. The historical table name is preserved to avoid
    breaking cost-engine foreign keys.
    """

    __tablename__ = "dpe_academic_offerings"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_academic_offering_code"),
        CheckConstraint("valid_to is null or valid_to >= valid_from", name="ck_dpe_academic_offering_validity"),
        Index("ix_dpe_academic_offering_product", "product_id", "active"),
        Index("ix_dpe_academic_offering_dimensions", "directorate_id", "modality", "shift", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_academic_products.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(100))
    modality: Mapped[str] = mapped_column(String(40), default="NAO_INFORMADA", index=True)
    shift: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    campus: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pole_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    valid_from: Mapped[str] = mapped_column(String(7))
    valid_to: Mapped[str | None] = mapped_column(String(7), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()
    product: Mapped[DPEAcademicProduct] = relationship()


class DPECostCenter(Base):
    """Hierarchical sector/cost-center classification for DPE expenses."""

    __tablename__ = "dpe_cost_centers"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_cost_center_code"),
        CheckConstraint("parent_id is null or parent_id <> id", name="ck_dpe_cost_center_parent"),
        Index("ix_dpe_cost_center_active", "directorate_id", "active", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_centers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    external_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()
    parent: Mapped[DPECostCenter | None] = relationship(remote_side="DPECostCenter.id")


class DPEAllocationRule(Base):
    """Named allocation policy executed by the DPE cost allocation engine."""

    __tablename__ = "dpe_allocation_rules"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_allocation_rule_code"),
        CheckConstraint(
            "driver_type in ('DIRECT','TEACHER_HOURS','OFFERING_HOURS','STUDENTS','REVENUE','EQUAL','MANUAL')",
            name="ck_dpe_allocation_rule_driver",
        ),
        Index("ix_dpe_allocation_rule_driver", "directorate_id", "driver_type", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    driver_type: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    system_defined: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()


class DPEAllocationPolicy(Base):
    """Reusable administrative policy for applying an allocation rule and scope across months.

    Policies reference stable academic offerings, while each monthly expense keeps its own
    period-specific targets. This preserves historical snapshots and lets a recurring expense
    reuse the same treatment without coupling future months to past period rows.
    """

    __tablename__ = "dpe_allocation_policies"
    __table_args__ = (
        UniqueConstraint("directorate_id", "name", name="uq_dpe_allocation_policy_name"),
        CheckConstraint("scope_type in ('ALL','SPECIFIC')", name="ck_dpe_allocation_policy_scope"),
        Index("ix_dpe_allocation_policy_active", "directorate_id", "active", "name"),
        Index("ix_dpe_allocation_policy_match", "directorate_id", "match_description", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    allocation_rule_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_allocation_rules.id", ondelete="RESTRICT"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(20), default="ALL")
    target_offerings_json: Mapped[list] = mapped_column(JSON, default=list)
    match_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_expense_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    auto_suggest: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    directorate: Mapped[Directorate] = relationship()
    allocation_rule: Mapped[DPEAllocationRule] = relationship()


class DPEExpenseCategory(Base):
    """Hierarchical expense category with an optional default allocation rule."""

    __tablename__ = "dpe_expense_categories"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_expense_category_code"),
        CheckConstraint("parent_id is null or parent_id <> id", name="ck_dpe_expense_category_parent"),
        Index("ix_dpe_expense_category_active", "directorate_id", "active", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_expense_categories.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    default_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_allocation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()
    parent: Mapped[DPEExpenseCategory | None] = relationship(remote_side="DPEExpenseCategory.id")
    default_rule: Mapped[DPEAllocationRule | None] = relationship()


class DPERecurringExpenseTemplate(Base):
    """Reusable template for generating a recurring expense once per competence."""

    __tablename__ = "dpe_recurring_expense_templates"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_dpe_recurring_expense_amount_positive"),
        CheckConstraint("expense_kind in ('GENERAL','PAYROLL')", name="ck_dpe_recurring_expense_kind"),
        CheckConstraint("day_of_month is null or (day_of_month >= 1 and day_of_month <= 31)", name="ck_dpe_recurring_expense_day"),
        UniqueConstraint("directorate_id", "name", name="uq_dpe_recurring_expense_name"),
        Index("ix_dpe_recurring_expense_active", "directorate_id", "active", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(String(280))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    expense_kind: Mapped[str] = mapped_column(String(20), default="GENERAL", index=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    cost_center_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_centers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_expense_categories.id", ondelete="RESTRICT"), index=True
    )
    allocation_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_allocation_policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    directorate: Mapped[Directorate] = relationship()
    cost_center: Mapped[DPECostCenter | None] = relationship()
    category: Mapped[DPEExpenseCategory] = relationship()
    allocation_policy: Mapped[DPEAllocationPolicy | None] = relationship()


class DPECostPeriodOffering(Base):
    """Historical snapshot of an offering included in a monthly competence."""

    __tablename__ = "dpe_cost_period_offerings"
    __table_args__ = (
        UniqueConstraint("period_id", "offering_id", name="uq_dpe_cost_period_offering"),
        Index("ix_dpe_cost_period_offering_period", "period_id", "included"),
        Index("ix_dpe_cost_period_offering_offering", "offering_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_periods.id", ondelete="CASCADE"), index=True
    )
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_academic_offerings.id", ondelete="RESTRICT"), index=True
    )
    offering_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    included: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period: Mapped[DPECostPeriod] = relationship()
    offering: Mapped[DPEAcademicOffering] = relationship()


# ---------------------------------------------------------------------------
# v0.9.6.15 - DPE Central de Despesas / Expense Intake
# ---------------------------------------------------------------------------


class DPECostExpenseImportBatch(Base):
    """Neutral staging batch for future Excel/API/request adapters.

    A batch is deliberately source-agnostic. Raw source rows can be staged and
    validated before they become official expenses, so a malformed integration
    never contaminates the monthly cost ledger.
    """

    __tablename__ = "dpe_cost_expense_import_batches"
    __table_args__ = (
        CheckConstraint(
            "source_type in ('EXCEL','API','REQUEST','OTHER')",
            name="ck_dpe_cost_expense_batch_source",
        ),
        CheckConstraint(
            "status in ('STAGING','READY','COMMITTED','FAILED','CANCELLED')",
            name="ck_dpe_cost_expense_batch_status",
        ),
        UniqueConstraint(
            "directorate_id", "period_id", "source_type", "external_key",
            name="uq_dpe_cost_expense_batch_external",
        ),
        Index("ix_dpe_cost_expense_batch_period", "directorate_id", "period_id", "created_at"),
        Index("ix_dpe_cost_expense_batch_status", "directorate_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), index=True)
    source_label: Mapped[str] = mapped_column(String(220))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="STAGING", index=True)
    mapping_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()
    period: Mapped[DPECostPeriod] = relationship()


class DPECostExpense(Base):
    """Official normalized monthly expense used by the new DPE Cost Engine.

    This is the official expense table for the Cost Engine. An official
    expense always belongs to a cost competence and preserves a
    classification snapshot so later catalog edits cannot rewrite the history.
    """

    __tablename__ = "dpe_cost_expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_dpe_cost_expense_amount_positive"),
        CheckConstraint(
            "expense_kind in ('GENERAL','PAYROLL')",
            name="ck_dpe_cost_expense_kind",
        ),
        CheckConstraint(
            "expense_scope in ('DIRECT','SHARED','INSTITUTIONAL')",
            name="ck_dpe_cost_expense_scope",
        ),
        CheckConstraint(
            "source_type in ('MANUAL','EXCEL','API','REQUEST','OTHER')",
            name="ck_dpe_cost_expense_source",
        ),
        CheckConstraint(
            "status in ('ACTIVE','VOIDED')",
            name="ck_dpe_cost_expense_status",
        ),
        UniqueConstraint(
            "directorate_id", "period_id", "source_type", "external_key",
            name="uq_dpe_cost_expense_external",
        ),
        Index("ix_dpe_cost_expense_period", "directorate_id", "period_id", "status"),
        Index("ix_dpe_cost_expense_category", "directorate_id", "category_id", "period_id"),
        Index("ix_dpe_cost_expense_center", "directorate_id", "cost_center_id", "period_id"),
        Index("ix_dpe_cost_expense_source", "directorate_id", "source_type", "period_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(280), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    expense_kind: Mapped[str] = mapped_column(String(20), default="GENERAL", index=True)
    expense_scope: Mapped[str] = mapped_column(String(20), default="SHARED", index=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    document_number: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    cost_center_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_centers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_expense_categories.id", ondelete="RESTRICT"), index=True
    )
    allocation_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_allocation_rules.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(20), default="MANUAL", index=True)
    source_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_expense_import_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_reference: Mapped[str | None] = mapped_column(String(220), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    period_teacher_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_period_teachers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    teacher_match_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    teacher_match_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    teacher_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    classification_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    directorate: Mapped[Directorate] = relationship()
    period: Mapped[DPECostPeriod] = relationship()
    cost_center: Mapped[DPECostCenter | None] = relationship()
    category: Mapped[DPEExpenseCategory] = relationship()
    allocation_rule: Mapped[DPEAllocationRule | None] = relationship()
    source_batch: Mapped[DPECostExpenseImportBatch | None] = relationship()
    period_teacher: Mapped[DPECostPeriodTeacher | None] = relationship()


# ---------------------------------------------------------------------------
# v0.9.6.16 - DPE Docencia, disciplinas e carga horaria
# ---------------------------------------------------------------------------


class DPETeacherProfile(Base):
    """DPE-specific participation profile for an institutional teacher identity."""

    __tablename__ = "dpe_teacher_profiles"
    __table_args__ = (
        UniqueConstraint("directorate_id", "teacher_id", name="uq_dpe_teacher_profile"),
        CheckConstraint(
            "default_relationship_type in ('UNSPECIFIED','EMPLOYEE','HOURLY','SERVICE_PROVIDER','OTHER')",
            name="ck_dpe_teacher_profile_relationship",
        ),
        Index("ix_dpe_teacher_profile_active", "directorate_id", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    default_relationship_type: Mapped[str] = mapped_column(String(30), default="UNSPECIFIED")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    directorate: Mapped[Directorate] = relationship()
    teacher: Mapped[Teacher] = relationship()


class DPETeacherAlias(Base):
    """Alternative teacher identifier used to reconcile payroll/import names."""

    __tablename__ = "dpe_teacher_aliases"
    __table_args__ = (
        UniqueConstraint("normalized_alias", name="uq_dpe_teacher_alias_normalized"),
        Index("ix_dpe_teacher_alias_teacher", "teacher_id", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    alias_name: Mapped[str] = mapped_column(String(240))
    normalized_alias: Mapped[str] = mapped_column(String(240), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher: Mapped[Teacher] = relationship()


class DPECostSubject(Base):
    """Course-independent discipline/subject master for DPE costing."""

    __tablename__ = "dpe_cost_subjects"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_cost_subject_code"),
        Index("ix_dpe_cost_subject_active", "directorate_id", "active", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(220), index=True)
    external_key: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()


class DPECostPeriodTeacher(Base):
    """Historical teacher snapshot attached to one costing competence."""

    __tablename__ = "dpe_cost_period_teachers"
    __table_args__ = (
        UniqueConstraint("period_id", "teacher_id", name="uq_dpe_cost_period_teacher"),
        CheckConstraint(
            "relationship_type in ('UNSPECIFIED','EMPLOYEE','HOURLY','SERVICE_PROVIDER','OTHER')",
            name="ck_dpe_cost_period_teacher_relationship",
        ),
        Index("ix_dpe_cost_period_teacher_period", "directorate_id", "period_id", "included"),
        Index("ix_dpe_cost_period_teacher_relationship", "directorate_id", "period_id", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    teacher_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    relationship_type: Mapped[str] = mapped_column(String(30), default="UNSPECIFIED", index=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    directorate: Mapped[Directorate] = relationship()
    period: Mapped[DPECostPeriod] = relationship()
    teacher: Mapped[Teacher] = relationship()


class DPECostTeachingActivity(Base):
    """Monthly teaching workload used as the teacher-cost allocation basis."""

    __tablename__ = "dpe_cost_teaching_activities"
    __table_args__ = (
        CheckConstraint("workload_hours > 0", name="ck_dpe_cost_teaching_activity_hours"),
        CheckConstraint(
            "source_type in ('MANUAL','EXCEL','API','REQUEST','OTHER')",
            name="ck_dpe_cost_teaching_activity_source",
        ),
        CheckConstraint("status in ('ACTIVE','VOIDED')", name="ck_dpe_cost_teaching_activity_status"),
        UniqueConstraint(
            "directorate_id", "period_id", "source_type", "external_key",
            name="uq_dpe_cost_teaching_activity_external",
        ),
        Index("ix_dpe_cost_teaching_activity_period", "directorate_id", "period_id", "status"),
        Index("ix_dpe_cost_teaching_activity_teacher", "period_teacher_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    period_teacher_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_period_teachers.id", ondelete="RESTRICT"), index=True
    )
    subject_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_subjects.id", ondelete="RESTRICT"), index=True)
    class_group: Mapped[str | None] = mapped_column(String(160), nullable=True)
    effective_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    effective_end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    workload_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    workload_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="MANUAL", index=True)
    external_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    context_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    directorate: Mapped[Directorate] = relationship()
    period: Mapped[DPECostPeriod] = relationship()
    period_teacher: Mapped[DPECostPeriodTeacher] = relationship()
    subject: Mapped[DPECostSubject] = relationship()


class DPECostTeachingActivityOffering(Base):
    """Split of one teaching activity across one or more monthly offerings."""

    __tablename__ = "dpe_cost_teaching_activity_offerings"
    __table_args__ = (
        CheckConstraint("allocated_hours > 0", name="ck_dpe_cost_teaching_activity_offering_hours"),
        UniqueConstraint("activity_id", "period_offering_id", name="uq_dpe_cost_teaching_activity_offering"),
        Index("ix_dpe_cost_teaching_activity_offering_snapshot", "period_offering_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_teaching_activities.id", ondelete="CASCADE"), index=True
    )
    period_offering_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_period_offerings.id", ondelete="RESTRICT"), index=True
    )
    allocated_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    offering_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activity: Mapped[DPECostTeachingActivity] = relationship()
    period_offering: Mapped[DPECostPeriodOffering] = relationship()


# ---------------------------------------------------------------------------
# v0.9.6.17 - DPE Cost Allocation Engine
# ---------------------------------------------------------------------------


class DPECostPeriodOfferingDriverValue(Base):
    """Monthly driver basis attached to an offering snapshot.

    OFFERING_HOURS can be derived from teaching activities when no explicit
    value exists. STUDENTS and REVENUE are explicit inputs in this release and
    will be connected to the richer revenue/student domain in the next stage.
    """

    __tablename__ = "dpe_cost_period_offering_driver_values"
    __table_args__ = (
        CheckConstraint(
            "metric_type in ('OFFERING_HOURS','STUDENTS','REVENUE')",
            name="ck_dpe_cost_driver_value_metric",
        ),
        CheckConstraint(
            "source_type in ('MANUAL','DERIVED','IMPORT','SYSTEM')",
            name="ck_dpe_cost_driver_value_source",
        ),
        CheckConstraint("value >= 0", name="ck_dpe_cost_driver_value_nonnegative"),
        UniqueConstraint("period_offering_id", "metric_type", name="uq_dpe_cost_driver_value_metric"),
        Index("ix_dpe_cost_driver_value_period", "directorate_id", "period_id", "metric_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    period_offering_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_period_offerings.id", ondelete="CASCADE"), index=True
    )
    metric_type: Mapped[str] = mapped_column(String(30), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    source_type: Mapped[str] = mapped_column(String(20), default="MANUAL")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period: Mapped[DPECostPeriod] = relationship()
    period_offering: Mapped[DPECostPeriodOffering] = relationship()


class DPECostExpenseAllocationTarget(Base):
    """Optional eligibility/manual target configuration for one expense.

    Absence of rows means all included offerings are eligible for shared
    drivers. DIRECT requires one selected target; MANUAL requires values or
    percentages on the selected targets.
    """

    __tablename__ = "dpe_cost_expense_allocation_targets"
    __table_args__ = (
        CheckConstraint("manual_amount is null or manual_amount >= 0", name="ck_dpe_cost_target_amount"),
        CheckConstraint(
            "manual_percentage is null or (manual_percentage >= 0 and manual_percentage <= 100)",
            name="ck_dpe_cost_target_percentage",
        ),
        UniqueConstraint("expense_id", "period_offering_id", name="uq_dpe_cost_expense_target"),
        Index("ix_dpe_cost_expense_target_expense", "expense_id"),
        Index("ix_dpe_cost_expense_target_offering", "period_offering_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_expenses.id", ondelete="CASCADE"), index=True
    )
    period_offering_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_period_offerings.id", ondelete="RESTRICT"), index=True
    )
    manual_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    manual_percentage: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expense: Mapped[DPECostExpense] = relationship()
    period_offering: Mapped[DPECostPeriodOffering] = relationship()


class DPECostAllocationRun(Base):
    """Immutable calculation attempt for one competence."""

    __tablename__ = "dpe_cost_allocation_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('BLOCKED','CALCULATED','OFFICIAL','SUPERSEDED')",
            name="ck_dpe_cost_allocation_run_status",
        ),
        UniqueConstraint("period_id", "run_number", name="uq_dpe_cost_allocation_run_number"),
        Index("ix_dpe_cost_allocation_run_period", "directorate_id", "period_id", "run_number"),
        Index("ix_dpe_cost_allocation_run_status", "directorate_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="CALCULATED", index=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    expense_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    allocated_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    unallocated_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    official_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    official_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period: Mapped[DPECostPeriod] = relationship()


class DPECostAllocationResult(Base):
    """Traceable expense-to-offering result generated by a calculation run."""

    __tablename__ = "dpe_cost_allocation_results"
    __table_args__ = (
        CheckConstraint("allocated_amount >= 0", name="ck_dpe_cost_allocation_result_amount"),
        UniqueConstraint(
            "run_id", "expense_id", "period_offering_id",
            name="uq_dpe_cost_allocation_result_target",
        ),
        Index("ix_dpe_cost_allocation_result_run", "run_id", "expense_id"),
        Index("ix_dpe_cost_allocation_result_offering", "run_id", "period_offering_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_allocation_runs.id", ondelete="CASCADE"), index=True
    )
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_expenses.id", ondelete="RESTRICT"), index=True
    )
    period_offering_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_period_offerings.id", ondelete="RESTRICT"), index=True
    )
    allocation_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_allocation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    driver_type: Mapped[str] = mapped_column(String(30), index=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    numerator: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    denominator: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(14, 10), nullable=True)
    basis_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expense_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    offering_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run: Mapped[DPECostAllocationRun] = relationship()
    expense: Mapped[DPECostExpense] = relationship()
    period_offering: Mapped[DPECostPeriodOffering] = relationship()
    allocation_rule: Mapped[DPEAllocationRule | None] = relationship()


class DPECostAllocationIssue(Base):
    """Persisted blocker/warning explaining why a run is incomplete."""

    __tablename__ = "dpe_cost_allocation_issues"
    __table_args__ = (
        CheckConstraint("severity in ('BLOCKER','WARNING')", name="ck_dpe_cost_allocation_issue_severity"),
        Index("ix_dpe_cost_allocation_issue_run", "run_id", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_allocation_runs.id", ondelete="CASCADE"), index=True
    )
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_expenses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    severity: Mapped[str] = mapped_column(String(20), default="BLOCKER", index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run: Mapped[DPECostAllocationRun] = relationship()
    expense: Mapped[DPECostExpense | None] = relationship()


# ---------------------------------------------------------------------------
# v0.9.6.18 - DPE Receita, Alunos e Ticket Medio
# ---------------------------------------------------------------------------


class DPECostOfferingEconomics(Base):
    """Monthly auxiliary facts for one historical course/context snapshot.

    Revenue no longer lives in this table at runtime. The canonical source is
    ``dpe_revenue_entries``. This model intentionally keeps only active-student
    facts and their source metadata because students may be used by analytics
    and allocation rules independently from revenue.
    """

    __tablename__ = "dpe_cost_offering_economics"
    __table_args__ = (
        CheckConstraint(
            "active_students is null or active_students >= 0",
            name="ck_dpe_cost_economics_active_students",
        ),
        CheckConstraint(
            "source_type in ('MANUAL','IMPORT','API','REQUEST','SYSTEM')",
            name="ck_dpe_cost_economics_source_type",
        ),
        UniqueConstraint(
            "period_offering_id", name="uq_dpe_cost_offering_economics_snapshot"
        ),
        Index(
            "ix_dpe_cost_economics_period",
            "directorate_id", "period_id", "period_offering_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True
    )
    period_offering_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_period_offerings.id", ondelete="RESTRICT"), index=True
    )
    active_students: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="MANUAL", index=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period: Mapped[DPECostPeriod] = relationship()
    period_offering: Mapped[DPECostPeriodOffering] = relationship()


# ---------------------------------------------------------------------------
# v0.13.0-dev.6 - DPE Revenue Ledger
# ---------------------------------------------------------------------------


class DPERevenueCategory(Base):
    __tablename__ = "dpe_revenue_categories"
    __table_args__ = (
        UniqueConstraint("directorate_id", "code", name="uq_dpe_revenue_category_code"),
        CheckConstraint("scope in ('COURSE','INSTITUTIONAL','BOTH')", name="ck_dpe_revenue_category_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    scope: Mapped[str] = mapped_column(String(20), default="BOTH", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DPERevenueEntry(Base):
    __tablename__ = "dpe_revenue_entries"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_dpe_revenue_entry_amount_nonnegative"),
        CheckConstraint("source_type in ('MANUAL','IMPORT','API','SYSTEM','MIGRATION')", name="ck_dpe_revenue_entry_source"),
        Index("ix_dpe_revenue_period", "directorate_id", "period_id"),
        Index("ix_dpe_revenue_period_offering", "period_id", "period_offering_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True)
    period_offering_id: Mapped[int | None] = mapped_column(ForeignKey("dpe_cost_period_offerings.id", ondelete="RESTRICT"), nullable=True, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("dpe_revenue_categories.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    source_type: Mapped[str] = mapped_column(String(20), default="MANUAL", index=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[DPERevenueCategory] = relationship()
    period: Mapped[DPECostPeriod] = relationship()
    period_offering: Mapped[DPECostPeriodOffering | None] = relationship()


# ---------------------------------------------------------------------------
# v0.9.6.19 - DPE Fechamento Mensal e Auditoria
# ---------------------------------------------------------------------------


class DPECostPeriodEvent(Base):
    """Immutable governance event for competence close/reopen operations.

    The period row stores only the current state. This event ledger preserves
    every closure and controlled reopening with the checklist snapshot and the
    allocation version that supported the decision.
    """

    __tablename__ = "dpe_cost_period_events"
    __table_args__ = (
        CheckConstraint(
            "event_type in ('CLOSED','REOPENED')",
            name="ck_dpe_cost_period_event_type",
        ),
        Index(
            "ix_dpe_cost_period_event_period",
            "directorate_id", "period_id", "created_at",
        ),
        Index(
            "ix_dpe_cost_period_event_type",
            "directorate_id", "event_type", "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directorate_id: Mapped[int] = mapped_column(ForeignKey("directorates.id"), index=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_periods.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    allocation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_allocation_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period: Mapped[DPECostPeriod] = relationship()
    allocation_run: Mapped[DPECostAllocationRun | None] = relationship()


class DPECostExpenseStagingRow(Base):
    """Raw/normalized row waiting for an adapter-specific validation step."""

    __tablename__ = "dpe_cost_expense_staging_rows"
    __table_args__ = (
        CheckConstraint(
            "status in ('PENDING','VALID','ERROR','IGNORED','COMMITTED')",
            name="ck_dpe_cost_expense_staging_status",
        ),
        UniqueConstraint("batch_id", "row_number", name="uq_dpe_cost_expense_staging_row"),
        Index("ix_dpe_cost_expense_staging_batch", "batch_id", "status", "row_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("dpe_cost_expense_import_batches.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized_data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    errors_json: Mapped[list] = mapped_column(JSON, default=list)
    committed_expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("dpe_cost_expenses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    batch: Mapped[DPECostExpenseImportBatch] = relationship()
    committed_expense: Mapped[DPECostExpense | None] = relationship()


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


class FacultyEvaluationContextScope(Base):
    """Curso/oferta associado a um contexto docente sem duplicar respostas.

    ``FacultyEvaluationContext.teaching_assignment_id`` permanece como o vínculo
    primário por compatibilidade. Esta tabela permite que a mesma turma avaliada
    pertença legitimamente a dois ou mais cursos, mantendo as respostas em um
    único contexto.
    """

    __tablename__ = "faculty_evaluation_context_scopes"
    __table_args__ = (
        UniqueConstraint("context_id", "teaching_assignment_id", name="uq_faculty_context_scope_assignment"),
        Index("ix_faculty_context_scope_context", "context_id"),
        Index("ix_faculty_context_scope_assignment", "teaching_assignment_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    context_id: Mapped[int] = mapped_column(
        ForeignKey("faculty_evaluation_contexts.id", ondelete="CASCADE"), index=True
    )
    teaching_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_assignments.id", ondelete="CASCADE"), index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolution_source: Mapped[str] = mapped_column(String(40), default="catalog")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context: Mapped[FacultyEvaluationContext] = relationship()
    teaching_assignment: Mapped[TeachingAssignment] = relationship()


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
    identificador opaco usado somente para contagens distintas. O payload bruto
    TALLOS não é persistido; ``source_payload_json`` permanece apenas como coluna
    legada de compatibilidade e deve conter ``{}``.
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
        CheckConstraint(
            "rating_source_state IN ('valid','zero','missing','invalid')",
            name="ck_dadm_tallos_rating_source_state",
        ),
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
    rating_source_state: Mapped[str] = mapped_column(String(16), default="missing", index=True)
    rating_source_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalization_version: Mapped[int] = mapped_column(Integer, default=5, index=True)
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
