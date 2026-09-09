-- Data UNIVC v0.8.5 - Avaliacoes institucionais via SEI
-- Migration aditiva. A base normalizada do questionario passa a ser a fonte
-- auditavel; nps_student permanece como projecao otimizada para o painel atual.

create table if not exists public.survey_imports (
  id varchar(40) primary key,
  source_filename varchar(255) not null,
  sha256 varchar(64) not null unique,
  source_kind varchar(20) not null,
  origin varchar(20) not null default 'manual',
  external_key varchar(100) unique,
  metadata_json jsonb,
  status varchar(30) not null default 'processing',
  created_at timestamptz not null default now()
);

create table if not exists public.survey_questionnaires (
  id bigserial primary key,
  name varchar(300) not null unique,
  sei_id varchar(80)
);

create table if not exists public.survey_runs (
  id bigserial primary key,
  import_id varchar(40) not null unique references public.survey_imports(id),
  questionnaire_id bigint not null references public.survey_questionnaires(id),
  title varchar(400),
  period_start varchar(20),
  period_end varchar(20),
  semester varchar(16),
  run_kind varchar(40) not null default 'generic',
  created_at timestamptz not null default now()
);

create table if not exists public.survey_questions (
  id bigserial primary key,
  text text not null,
  normalized_text varchar(800) not null unique,
  position integer not null default 0,
  detected_metric_type varchar(30) not null default 'categorical',
  nps_candidate boolean not null default false
);

create table if not exists public.survey_questionnaire_questions (
  id bigserial primary key,
  questionnaire_id bigint not null references public.survey_questionnaires(id),
  question_id bigint not null references public.survey_questions(id),
  position integer not null default 0,
  constraint uq_survey_questionnaire_question unique(questionnaire_id, question_id)
);

create table if not exists public.survey_run_courses (
  id bigserial primary key,
  run_id bigint not null references public.survey_runs(id),
  course_id bigint not null references public.courses(id),
  source_path varchar(500) not null,
  respondent_count integer not null default 0,
  imported_at timestamptz not null default now(),
  constraint uq_survey_run_course unique(run_id, course_id)
);

create table if not exists public.survey_response_aggregates (
  id bigserial primary key,
  run_id bigint not null references public.survey_runs(id),
  course_id bigint not null references public.courses(id),
  question_id bigint not null references public.survey_questions(id),
  option_label varchar(500) not null,
  option_key varchar(500) not null,
  numeric_value double precision,
  response_count integer not null default 0,
  source_percentage double precision,
  constraint uq_survey_response_aggregate unique(run_id, course_id, question_id, option_key)
);

create table if not exists public.survey_raw_responses (
  id bigserial primary key,
  run_id bigint not null references public.survey_runs(id),
  course_id bigint not null references public.courses(id),
  question_id bigint not null references public.survey_questions(id),
  response_text text not null,
  response_key varchar(800) not null
);

create table if not exists public.survey_nps_sources (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  semester varchar(16) not null,
  run_id bigint not null references public.survey_runs(id),
  question_id bigint not null references public.survey_questions(id),
  created_at timestamptz not null default now(),
  created_by text,
  constraint uq_survey_nps_directorate_semester unique(directorate_id, semester)
);

alter table public.nps_student add column if not exists source_type varchar(30) not null default 'manual';
alter table public.nps_student add column if not exists survey_run_id bigint references public.survey_runs(id);
alter table public.nps_student add column if not exists survey_question_id bigint references public.survey_questions(id);

create table if not exists public.teachers (
  id bigserial primary key,
  external_id varchar(100) unique,
  display_name varchar(220) not null,
  normalized_name varchar(220) not null unique,
  active boolean not null default true
);

create table if not exists public.academic_offerings (
  id bigserial primary key,
  period varchar(16) not null,
  course_id bigint not null references public.courses(id),
  discipline_id bigint not null references public.disciplines(id),
  class_group varchar(120) not null default '',
  external_id varchar(120),
  constraint uq_academic_offering_period_course_discipline_class
    unique(period, course_id, discipline_id, class_group)
);

create table if not exists public.teaching_assignments (
  id bigserial primary key,
  offering_id bigint not null references public.academic_offerings(id),
  teacher_id bigint not null references public.teachers(id),
  external_id varchar(120),
  constraint uq_teaching_assignment unique(offering_id, teacher_id)
);

create table if not exists public.faculty_evaluation_contexts (
  id bigserial primary key,
  run_id bigint not null references public.survey_runs(id),
  teaching_assignment_id bigint not null references public.teaching_assignments(id),
  source_key varchar(500) not null,
  source_path varchar(500),
  respondent_count integer not null default 0,
  imported_at timestamptz not null default now(),
  constraint uq_faculty_context_source unique(run_id, teaching_assignment_id, source_key)
);

create table if not exists public.faculty_response_aggregates (
  id bigserial primary key,
  context_id bigint not null references public.faculty_evaluation_contexts(id),
  question_id bigint not null references public.survey_questions(id),
  option_label varchar(500) not null,
  option_key varchar(500) not null,
  numeric_value double precision,
  response_count integer not null default 0,
  source_percentage double precision,
  constraint uq_faculty_response_aggregate unique(context_id, question_id, option_key)
);

create table if not exists public.faculty_raw_responses (
  id bigserial primary key,
  context_id bigint not null references public.faculty_evaluation_contexts(id),
  question_id bigint not null references public.survey_questions(id),
  response_text text not null,
  response_key varchar(800) not null
);

create index if not exists ix_survey_runs_semester on public.survey_runs(semester);
create index if not exists ix_survey_response_run_question on public.survey_response_aggregates(run_id, question_id);
create index if not exists ix_survey_nps_source_semester on public.survey_nps_sources(directorate_id, semester);
create index if not exists ix_academic_offerings_period on public.academic_offerings(period, course_id, discipline_id);
create index if not exists ix_teaching_assignments_teacher on public.teaching_assignments(teacher_id, offering_id);
create index if not exists ix_faculty_contexts_assignment on public.faculty_evaluation_contexts(teaching_assignment_id, run_id);

update public.indicator_definitions
set source_text = 'Relatorio de Avaliacao Institucional do SEI, importado e normalizado automaticamente pelo Data UNIVC'
where code in ('DTNH-01','DCS-01');

alter table public.survey_imports enable row level security;
alter table public.survey_questionnaires enable row level security;
alter table public.survey_runs enable row level security;
alter table public.survey_questions enable row level security;
alter table public.survey_questionnaire_questions enable row level security;
alter table public.survey_run_courses enable row level security;
alter table public.survey_response_aggregates enable row level security;
alter table public.survey_raw_responses enable row level security;
alter table public.survey_nps_sources enable row level security;
alter table public.teachers enable row level security;
alter table public.academic_offerings enable row level security;
alter table public.teaching_assignments enable row level security;
alter table public.faculty_evaluation_contexts enable row level security;
alter table public.faculty_response_aggregates enable row level security;
alter table public.faculty_raw_responses enable row level security;
