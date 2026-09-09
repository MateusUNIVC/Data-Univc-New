-- Data UNIVC v0.7.4 — sincronização do DM com o relatório integral do SEI.
-- Não remove registros existentes e não persiste credenciais do SEI.

alter table public.dm_cohorts
  add column if not exists source_system varchar(30),
  add column if not exists sei_raw_label varchar(220),
  add column if not exists last_seen_sei_at timestamptz;

alter table public.dm_students
  add column if not exists entry_date_estimated boolean not null default false,
  add column if not exists source_system varchar(30),
  add column if not exists sei_raw_status varchar(120),
  add column if not exists last_seen_sei_at timestamptz;

create index if not exists ix_dm_cohort_last_seen_sei
  on public.dm_cohorts(directorate_id,last_seen_sei_at);
create index if not exists ix_dm_student_last_seen_sei
  on public.dm_students(directorate_id,last_seen_sei_at);
create index if not exists ix_dm_student_entry_estimated
  on public.dm_students(directorate_id,entry_date_estimated);

create table if not exists public.dm_sei_sync_runs (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  source_type varchar(30) not null default 'upload',
  source_name varchar(255),
  source_sha256 varchar(64),
  status varchar(30) not null default 'Concluída',
  cohorts_detected integer not null default 0,
  students_detected integer not null default 0,
  cohorts_created integer not null default 0,
  cohorts_updated integer not null default 0,
  students_created integer not null default 0,
  students_updated integer not null default 0,
  students_unchanged integer not null default 0,
  students_not_seen integer not null default 0,
  warnings_json text not null default '[]',
  started_at timestamptz not null default now(),
  completed_at timestamptz not null default now(),
  inserted_by varchar(255)
);

create index if not exists ix_dm_sei_sync_dir_completed
  on public.dm_sei_sync_runs(directorate_id,completed_at desc);
create index if not exists ix_dm_sei_sync_source_hash
  on public.dm_sei_sync_runs(source_sha256);

alter table public.dm_sei_sync_runs enable row level security;
-- A tabela continua acessível somente pelo backend FastAPI, como as demais tabelas do DM.
