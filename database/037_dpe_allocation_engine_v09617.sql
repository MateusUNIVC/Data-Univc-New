-- Data UNIVC v0.9.6.17 -- DPE Motor de Rateio
-- Migration aditiva sobre schema 36.
-- Acrescenta vigencia intramensal da docencia, bases de direcionadores,
-- configuracao de alvos e execucoes versionadas/auditaveis do rateio.

alter table public.dpe_cost_teaching_activities
  add column if not exists effective_start_date date;
alter table public.dpe_cost_teaching_activities
  add column if not exists effective_end_date date;
create index if not exists ix_dpe_cost_teaching_activity_effective_dates
  on public.dpe_cost_teaching_activities(period_id, effective_start_date, effective_end_date);

create table if not exists public.dpe_cost_period_offering_driver_values (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  period_offering_id bigint not null references public.dpe_cost_period_offerings(id) on delete cascade,
  metric_type varchar(30) not null
    check (metric_type in ('OFFERING_HOURS','STUDENTS','REVENUE')),
  value numeric(20,6) not null check (value >= 0),
  source_type varchar(20) not null default 'MANUAL'
    check (source_type in ('MANUAL','DERIVED','IMPORT','SYSTEM')),
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  constraint uq_dpe_cost_driver_value_metric unique (period_offering_id, metric_type)
);
create index if not exists ix_dpe_cost_driver_value_period
  on public.dpe_cost_period_offering_driver_values(directorate_id, period_id, metric_type);

create table if not exists public.dpe_cost_expense_allocation_targets (
  id bigserial primary key,
  expense_id bigint not null references public.dpe_cost_expenses(id) on delete cascade,
  period_offering_id bigint not null references public.dpe_cost_period_offerings(id) on delete restrict,
  manual_amount numeric(16,2) check (manual_amount is null or manual_amount >= 0),
  manual_percentage numeric(10,6)
    check (manual_percentage is null or (manual_percentage >= 0 and manual_percentage <= 100)),
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  constraint uq_dpe_cost_expense_target unique (expense_id, period_offering_id)
);
create index if not exists ix_dpe_cost_expense_target_expense
  on public.dpe_cost_expense_allocation_targets(expense_id);
create index if not exists ix_dpe_cost_expense_target_offering
  on public.dpe_cost_expense_allocation_targets(period_offering_id);

create table if not exists public.dpe_cost_allocation_runs (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  run_number integer not null,
  status varchar(20) not null default 'CALCULATED'
    check (status in ('BLOCKED','CALCULATED','OFFICIAL','SUPERSEDED')),
  input_fingerprint varchar(64),
  expense_total numeric(18,2) not null default 0,
  allocated_total numeric(18,2) not null default 0,
  unallocated_total numeric(18,2) not null default 0,
  summary_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  official_at timestamptz,
  official_by varchar(255),
  superseded_at timestamptz,
  superseded_by varchar(255),
  constraint uq_dpe_cost_allocation_run_number unique (period_id, run_number)
);
create index if not exists ix_dpe_cost_allocation_run_period
  on public.dpe_cost_allocation_runs(directorate_id, period_id, run_number);
create index if not exists ix_dpe_cost_allocation_run_status
  on public.dpe_cost_allocation_runs(directorate_id, status, created_at);

create table if not exists public.dpe_cost_allocation_results (
  id bigserial primary key,
  run_id bigint not null references public.dpe_cost_allocation_runs(id) on delete cascade,
  expense_id bigint not null references public.dpe_cost_expenses(id) on delete restrict,
  period_offering_id bigint not null references public.dpe_cost_period_offerings(id) on delete restrict,
  allocation_rule_id bigint references public.dpe_allocation_rules(id) on delete set null,
  driver_type varchar(30) not null,
  allocated_amount numeric(16,2) not null check (allocated_amount >= 0),
  numerator numeric(20,6),
  denominator numeric(20,6),
  percentage numeric(14,10),
  basis_json jsonb not null default '{}'::jsonb,
  expense_snapshot_json jsonb not null default '{}'::jsonb,
  offering_snapshot_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint uq_dpe_cost_allocation_result_target unique (run_id, expense_id, period_offering_id)
);
create index if not exists ix_dpe_cost_allocation_result_run
  on public.dpe_cost_allocation_results(run_id, expense_id);
create index if not exists ix_dpe_cost_allocation_result_offering
  on public.dpe_cost_allocation_results(run_id, period_offering_id);

create table if not exists public.dpe_cost_allocation_issues (
  id bigserial primary key,
  run_id bigint not null references public.dpe_cost_allocation_runs(id) on delete cascade,
  expense_id bigint references public.dpe_cost_expenses(id) on delete set null,
  severity varchar(20) not null default 'BLOCKER'
    check (severity in ('BLOCKER','WARNING')),
  code varchar(80) not null,
  message text not null,
  context_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists ix_dpe_cost_allocation_issue_run
  on public.dpe_cost_allocation_issues(run_id, severity);
create index if not exists ix_dpe_cost_allocation_issue_expense
  on public.dpe_cost_allocation_issues(expense_id);

alter table public.dpe_cost_period_offering_driver_values enable row level security;
alter table public.dpe_cost_expense_allocation_targets enable row level security;
alter table public.dpe_cost_allocation_runs enable row level security;
alter table public.dpe_cost_allocation_results enable row level security;
alter table public.dpe_cost_allocation_issues enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 37, '037_dpe_allocation_engine_v09617.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
