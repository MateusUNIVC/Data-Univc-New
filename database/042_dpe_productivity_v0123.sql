-- Data UNIVC v0.12.3 - DPE Productivity
-- Additive migration over schema 41.
-- Adds reusable recurring expense templates. Existing expense staging tables are reused for real Excel imports.

create table if not exists public.dpe_recurring_expense_templates (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  name varchar(180) not null,
  description varchar(280) not null,
  amount numeric(16,2) not null check (amount > 0),
  expense_kind varchar(20) not null default 'GENERAL'
    check (expense_kind in ('GENERAL','PAYROLL')),
  counterparty_name varchar(240),
  cost_center_id bigint references public.dpe_cost_centers(id) on delete restrict,
  category_id bigint not null references public.dpe_expense_categories(id) on delete restrict,
  allocation_policy_id bigint references public.dpe_allocation_policies(id) on delete set null,
  day_of_month integer check (day_of_month is null or (day_of_month >= 1 and day_of_month <= 31)),
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  constraint uq_dpe_recurring_expense_name unique (directorate_id, name)
);

create index if not exists ix_dpe_recurring_expense_active
  on public.dpe_recurring_expense_templates(directorate_id, active, name);
create index if not exists ix_dpe_recurring_expense_category
  on public.dpe_recurring_expense_templates(category_id);
create index if not exists ix_dpe_recurring_expense_center
  on public.dpe_recurring_expense_templates(cost_center_id);
create index if not exists ix_dpe_recurring_expense_policy
  on public.dpe_recurring_expense_templates(allocation_policy_id);

alter table public.dpe_recurring_expense_templates enable row level security;

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 42, '042_dpe_productivity_v0123.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
