-- Data UNIVC v0.13.0-dev.3 - DPE-03 backend legacy retirement
-- Retires the operational DPE v0.4 and Finance v0.7.7 tables only after
-- preserving every row in an audit archive. DPE-01/02/03 management tables
-- remain active for the next domain-consolidation stage.

create table if not exists public.dpe_legacy_retirement_archive (
  id bigserial primary key,
  source_generation varchar(32) not null,
  source_table varchar(96) not null,
  source_pk bigint not null,
  payload_json jsonb not null,
  archived_at timestamptz not null default now(),
  constraint uq_dpe_legacy_retirement_source unique(source_table, source_pk)
);

alter table public.dpe_legacy_retirement_archive enable row level security;

-- Dynamic SQL keeps the migration safe for installations where a legacy table
-- was already retired manually while still preserving every row when present.
do $$
begin
  if to_regclass('public.dpe_operating_results') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.4','dpe_operating_results',id,to_jsonb(t) from public.dpe_operating_results t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_budget_execution') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.4','dpe_budget_execution',id,to_jsonb(t) from public.dpe_budget_execution t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_cash_movements') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.4','dpe_cash_movements',id,to_jsonb(t) from public.dpe_cash_movements t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_monthly_revenues') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.7.7','dpe_monthly_revenues',id,to_jsonb(t) from public.dpe_monthly_revenues t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_course_revenues') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.7.7','dpe_course_revenues',id,to_jsonb(t) from public.dpe_course_revenues t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_expenses') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.7.7','dpe_expenses',id,to_jsonb(t) from public.dpe_expenses t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_expense_allocations') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.7.7','dpe_expense_allocations',id,to_jsonb(t) from public.dpe_expense_allocations t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
  if to_regclass('public.dpe_course_cost_snapshots') is not null then
    execute $sql$insert into public.dpe_legacy_retirement_archive(source_generation,source_table,source_pk,payload_json)
      select 'v0.7.7','dpe_course_cost_snapshots',id,to_jsonb(t) from public.dpe_course_cost_snapshots t
      on conflict(source_table,source_pk) do nothing$sql$;
  end if;
end $$;

-- DPE-04 and DPE-05 were already removed from the active KPI catalog in v0.7.0.
update public.indicator_schedules
set active = false
where indicator_code in ('DPE-04', 'DPE-05');

-- Drop children before parents. The archive above is the rollback/audit source.
drop table if exists public.dpe_expense_allocations;
drop table if exists public.dpe_course_cost_snapshots;
drop table if exists public.dpe_course_revenues;
drop table if exists public.dpe_expenses;
drop table if exists public.dpe_monthly_revenues;
drop table if exists public.dpe_cash_movements;
drop table if exists public.dpe_budget_execution;
drop table if exists public.dpe_operating_results;

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 43, '043_dpe_legacy_backend_retirement_v0130.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
