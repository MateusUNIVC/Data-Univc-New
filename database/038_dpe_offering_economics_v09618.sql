-- Data UNIVC v0.9.6.18
-- DPE Receita, Alunos e Ticket Medio / Offering Economics
-- Additive migration from schema 37 to 38.

create table if not exists public.dpe_cost_offering_economics (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  period_offering_id bigint not null references public.dpe_cost_period_offerings(id) on delete restrict,
  active_students integer null,
  paying_students integer null,
  gross_revenue numeric(18,2) null,
  scholarships_discounts numeric(18,2) not null default 0,
  other_deductions numeric(18,2) not null default 0,
  net_revenue numeric(18,2) null,
  revenue_type varchar(20) not null default 'REALIZED',
  source_type varchar(20) not null default 'MANUAL',
  source_reference varchar(255) null,
  notes text null,
  created_at timestamptz not null default now(),
  created_by varchar(255) null,
  updated_at timestamptz not null default now(),
  updated_by varchar(255) null,
  constraint uq_dpe_cost_offering_economics_snapshot unique(period_offering_id),
  constraint ck_dpe_cost_economics_active_students check(active_students is null or active_students >= 0),
  constraint ck_dpe_cost_economics_paying_students check(paying_students is null or paying_students >= 0),
  constraint ck_dpe_cost_economics_paying_le_active check(active_students is null or paying_students is null or paying_students <= active_students),
  constraint ck_dpe_cost_economics_gross_nonnegative check(gross_revenue is null or gross_revenue >= 0),
  constraint ck_dpe_cost_economics_discounts_nonnegative check(scholarships_discounts >= 0),
  constraint ck_dpe_cost_economics_deductions_nonnegative check(other_deductions >= 0),
  constraint ck_dpe_cost_economics_net_nonnegative check(net_revenue is null or net_revenue >= 0),
  constraint ck_dpe_cost_economics_revenue_type check(revenue_type in ('REALIZED','ESTIMATED')),
  constraint ck_dpe_cost_economics_source_type check(source_type in ('MANUAL','IMPORT','API','REQUEST','SYSTEM'))
);

create index if not exists ix_dpe_cost_economics_period
  on public.dpe_cost_offering_economics(directorate_id, period_id, period_offering_id);

alter table public.dpe_cost_offering_economics enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 38, '038_dpe_offering_economics_v09618.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
