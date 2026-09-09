-- Data UNIVC v0.8.6 - NPS da Instituicao + NPS do Curso
-- Migration aditiva: preserva nps_student como projecao do NPS do Curso
-- e cria uma projecao separada para o NPS da Instituicao.

create table if not exists public.nps_institution (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
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
  constraint uq_nps_institution_directorate_period unique(directorate_id, period)
);

create table if not exists public.survey_nps_institution_sources (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  semester varchar(16) not null,
  run_id bigint not null references public.survey_runs(id),
  question_id bigint not null references public.survey_questions(id),
  created_at timestamptz not null default now(),
  created_by varchar(255),
  constraint uq_survey_nps_institution_directorate_semester unique(directorate_id, semester)
);

create index if not exists ix_nps_institution_period on public.nps_institution(directorate_id, period);
create index if not exists ix_survey_nps_institution_source_semester on public.survey_nps_institution_sources(directorate_id, semester);

alter table public.nps_institution enable row level security;
alter table public.survey_nps_institution_sources enable row level security;
