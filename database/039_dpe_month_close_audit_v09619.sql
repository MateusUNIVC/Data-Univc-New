-- Data UNIVC v0.9.6.19
-- DPE Fechamento Mensal e Auditoria
-- Additive migration from schema 38 to 39.

create table if not exists public.dpe_cost_period_events (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  event_type varchar(20) not null check (event_type in ('CLOSED','REOPENED')),
  from_status varchar(20) not null,
  to_status varchar(20) not null,
  allocation_run_id bigint references public.dpe_cost_allocation_runs(id) on delete set null,
  reason text,
  checklist_json jsonb not null default '{}'::jsonb,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  created_by varchar(255)
);

create index if not exists ix_dpe_cost_period_event_period
  on public.dpe_cost_period_events(directorate_id, period_id, created_at);
create index if not exists ix_dpe_cost_period_event_type
  on public.dpe_cost_period_events(directorate_id, event_type, created_at);

alter table public.dpe_cost_period_events enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 39, '039_dpe_month_close_audit_v09619.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
