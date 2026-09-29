-- Data UNIVC v0.9.6.16 -- DPE Professores, Disciplinas e Carga Horaria
-- Migration aditiva sobre schema 35.
-- Reutiliza public.teachers como cadastro institucional e cria snapshots mensais,
-- disciplinas economicas, atividades docentes e divisao de carga por oferta.

create table if not exists public.dpe_teacher_aliases (
  id bigserial primary key,
  teacher_id bigint not null references public.teachers(id) on delete cascade,
  alias_name varchar(240) not null,
  normalized_alias varchar(240) not null,
  source_type varchar(40),
  external_key varchar(180),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  constraint uq_dpe_teacher_alias_normalized unique (normalized_alias)
);
create index if not exists ix_dpe_teacher_alias_teacher
  on public.dpe_teacher_aliases(teacher_id, active);
create index if not exists ix_dpe_teacher_alias_external
  on public.dpe_teacher_aliases(external_key);

create table if not exists public.dpe_cost_subjects (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  code varchar(100) not null,
  name varchar(220) not null,
  external_key varchar(180),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_cost_subject_code unique (directorate_id, code)
);
create index if not exists ix_dpe_cost_subject_active
  on public.dpe_cost_subjects(directorate_id, active, name);
create index if not exists ix_dpe_cost_subject_external
  on public.dpe_cost_subjects(external_key);

create table if not exists public.dpe_cost_period_teachers (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  teacher_id bigint not null references public.teachers(id) on delete restrict,
  teacher_snapshot_json jsonb not null default '{}'::jsonb,
  included boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_cost_period_teacher unique (period_id, teacher_id)
);
create index if not exists ix_dpe_cost_period_teacher_period
  on public.dpe_cost_period_teachers(directorate_id, period_id, included);
create index if not exists ix_dpe_cost_period_teacher_teacher
  on public.dpe_cost_period_teachers(teacher_id, period_id);

create table if not exists public.dpe_cost_teaching_activities (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  period_teacher_id bigint not null references public.dpe_cost_period_teachers(id) on delete restrict,
  subject_id bigint not null references public.dpe_cost_subjects(id) on delete restrict,
  class_group varchar(160),
  workload_hours numeric(10,2) not null check (workload_hours > 0),
  workload_reference varchar(120),
  source_type varchar(20) not null default 'MANUAL'
    check (source_type in ('MANUAL','EXCEL','API','REQUEST','OTHER')),
  external_key varchar(180),
  context_snapshot_json jsonb not null default '{}'::jsonb,
  status varchar(20) not null default 'ACTIVE'
    check (status in ('ACTIVE','VOIDED')),
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  voided_at timestamptz,
  voided_by varchar(255),
  void_reason text,
  constraint uq_dpe_cost_teaching_activity_external
    unique (directorate_id, period_id, source_type, external_key)
);
create index if not exists ix_dpe_cost_teaching_activity_period
  on public.dpe_cost_teaching_activities(directorate_id, period_id, status);
create index if not exists ix_dpe_cost_teaching_activity_teacher
  on public.dpe_cost_teaching_activities(period_teacher_id, status);
create index if not exists ix_dpe_cost_teaching_activity_subject
  on public.dpe_cost_teaching_activities(subject_id, period_id);

create table if not exists public.dpe_cost_teaching_activity_offerings (
  id bigserial primary key,
  activity_id bigint not null references public.dpe_cost_teaching_activities(id) on delete cascade,
  period_offering_id bigint not null references public.dpe_cost_period_offerings(id) on delete restrict,
  allocated_hours numeric(10,2) not null check (allocated_hours > 0),
  offering_snapshot_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint uq_dpe_cost_teaching_activity_offering unique (activity_id, period_offering_id)
);
create index if not exists ix_dpe_cost_teaching_activity_offering_snapshot
  on public.dpe_cost_teaching_activity_offerings(period_offering_id);

alter table public.dpe_cost_expenses
  add column if not exists period_teacher_id bigint references public.dpe_cost_period_teachers(id) on delete set null;
alter table public.dpe_cost_expenses
  add column if not exists teacher_match_status varchar(20);
alter table public.dpe_cost_expenses
  add column if not exists teacher_match_method varchar(30);
alter table public.dpe_cost_expenses
  add column if not exists teacher_snapshot_json jsonb not null default '{}'::jsonb;

create index if not exists ix_dpe_cost_expense_period_teacher
  on public.dpe_cost_expenses(period_teacher_id);
create index if not exists ix_dpe_cost_expense_teacher_match
  on public.dpe_cost_expenses(directorate_id, period_id, expense_kind, teacher_match_status);

alter table public.dpe_teacher_aliases enable row level security;
alter table public.dpe_cost_subjects enable row level security;
alter table public.dpe_cost_period_teachers enable row level security;
alter table public.dpe_cost_teaching_activities enable row level security;
alter table public.dpe_cost_teaching_activity_offerings enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 36, '036_dpe_teaching_workload_v09616.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
