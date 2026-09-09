-- Data UNIVC v0.8.25.0
-- NPS da Instituicao respondido pelos docentes (01C).
-- O fato e institucional/global por semestre porque o relatorio do SEI e anonimo
-- e nao informa curso, professor ou diretoria do respondente.

create table if not exists public.survey_faculty_institution_contexts (
  id bigserial primary key,
  run_id bigint not null references public.survey_runs(id),
  source_path varchar(500) not null,
  unit_name varchar(500),
  respondent_count integer not null default 0,
  imported_at timestamptz not null default now(),
  constraint uq_survey_faculty_institution_context unique(run_id, source_path)
);

create table if not exists public.survey_faculty_institution_response_aggregates (
  id bigserial primary key,
  context_id bigint not null references public.survey_faculty_institution_contexts(id),
  question_id bigint not null references public.survey_questions(id),
  option_label varchar(500) not null,
  option_key varchar(500) not null,
  numeric_value double precision,
  response_count integer not null default 0,
  source_percentage double precision,
  constraint uq_survey_faculty_institution_response_aggregate unique(context_id, question_id, option_key)
);

create table if not exists public.survey_faculty_institution_raw_responses (
  id bigserial primary key,
  context_id bigint not null references public.survey_faculty_institution_contexts(id),
  question_id bigint not null references public.survey_questions(id),
  response_text text not null,
  response_key varchar(800) not null
);

create table if not exists public.survey_nps_faculty_sources (
  id bigserial primary key,
  semester varchar(16) not null,
  run_id bigint not null references public.survey_runs(id),
  question_id bigint not null references public.survey_questions(id),
  created_at timestamptz not null default now(),
  created_by varchar(255),
  constraint uq_survey_nps_faculty_semester unique(semester)
);

create table if not exists public.nps_institution_faculty (
  id bigserial primary key,
  period varchar(16) not null,
  respondents integer not null,
  promoters integer not null,
  neutrals integer not null,
  detractors integer not null,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  source_type varchar(30) not null default 'SEI_SURVEY',
  survey_run_id bigint references public.survey_runs(id),
  survey_question_id bigint references public.survey_questions(id),
  constraint uq_nps_institution_faculty_period unique(period)
);

create index if not exists ix_survey_faculty_institution_context_run on public.survey_faculty_institution_contexts(run_id);
create index if not exists ix_survey_faculty_institution_run_question on public.survey_faculty_institution_response_aggregates(question_id, context_id);
create index if not exists ix_survey_nps_faculty_source_semester on public.survey_nps_faculty_sources(semester);
create index if not exists ix_nps_institution_faculty_period on public.nps_institution_faculty(period);

alter table public.survey_faculty_institution_contexts enable row level security;
alter table public.survey_faculty_institution_response_aggregates enable row level security;
alter table public.survey_faculty_institution_raw_responses enable row level security;
alter table public.survey_nps_faculty_sources enable row level security;
alter table public.nps_institution_faculty enable row level security;

insert into public.indicator_definitions
  (code, directorate_code, name, periodicity, formula_text, source_text, active)
values
  ('DTNH-01C','DTNH','NPS da Instituicao - Docentes','Semestral / conforme aplicacao','% Promotores (9-10) - % Detratores (0-6)','Avaliacao Institucional pelos docentes no SEI - pergunta oficial 0-10 sobre recomendar a UNIVC',true),
  ('DCS-01C','DCS','NPS da Instituicao - Docentes','Semestral / conforme aplicacao','% Promotores (9-10) - % Detratores (0-6)','Avaliacao Institucional pelos docentes no SEI - pergunta oficial 0-10 sobre recomendar a UNIVC',true)
on conflict(code) do update set
  directorate_code = excluded.directorate_code,
  name = excluded.name,
  periodicity = excluded.periodicity,
  formula_text = excluded.formula_text,
  source_text = excluded.source_text,
  active = true;

insert into public.indicator_schedules
  (indicator_code, reference_grain, due_business_day, collection_window_start_business_day, active)
values
  ('DTNH-01C','semester',5,1,true),
  ('DCS-01C','semester',5,1,true)
on conflict(indicator_code) do update set
  reference_grain = 'semester',
  active = true;

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 31, '031_academic_faculty_nps_v08250.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
