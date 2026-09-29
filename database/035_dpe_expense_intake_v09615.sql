-- Data UNIVC v0.9.6.15 -- DPE Central de Despesas / Expense Intake
-- Migration aditiva sobre schema 34.
-- Cria o ledger normalizado de despesas do novo Cost Engine e uma camada de
-- staging neutra para futuros adaptadores Excel/API/requisicao. A base
-- financeira legada dpe_expenses permanece intacta.

create table if not exists public.dpe_cost_expense_import_batches (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  source_type varchar(20) not null
    check (source_type in ('EXCEL','API','REQUEST','OTHER')),
  source_label varchar(220) not null,
  original_filename varchar(255),
  external_key varchar(180),
  status varchar(20) not null default 'STAGING'
    check (status in ('STAGING','READY','COMMITTED','FAILED','CANCELLED')),
  mapping_json jsonb not null default '{}'::jsonb,
  summary_json jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_cost_expense_batch_external
    unique (directorate_id, period_id, source_type, external_key)
);

create index if not exists ix_dpe_cost_expense_batch_period
  on public.dpe_cost_expense_import_batches(directorate_id, period_id, created_at);
create index if not exists ix_dpe_cost_expense_batch_status
  on public.dpe_cost_expense_import_batches(directorate_id, status, created_at);

create table if not exists public.dpe_cost_expenses (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  expense_date date,
  description varchar(280) not null,
  amount numeric(16,2) not null check (amount > 0),
  expense_kind varchar(20) not null default 'GENERAL'
    check (expense_kind in ('GENERAL','PAYROLL')),
  counterparty_name varchar(240),
  document_number varchar(140),
  cost_center_id bigint references public.dpe_cost_centers(id) on delete restrict,
  category_id bigint not null references public.dpe_expense_categories(id) on delete restrict,
  allocation_rule_id bigint references public.dpe_allocation_rules(id) on delete restrict,
  source_type varchar(20) not null default 'MANUAL'
    check (source_type in ('MANUAL','EXCEL','API','REQUEST','OTHER')),
  source_batch_id bigint references public.dpe_cost_expense_import_batches(id) on delete set null,
  source_reference varchar(220),
  external_key varchar(180),
  status varchar(20) not null default 'ACTIVE'
    check (status in ('ACTIVE','VOIDED')),
  classification_snapshot_json jsonb not null default '{}'::jsonb,
  source_payload_json jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  voided_at timestamptz,
  voided_by varchar(255),
  void_reason text,
  constraint uq_dpe_cost_expense_external
    unique (directorate_id, period_id, source_type, external_key)
);

create index if not exists ix_dpe_cost_expense_period
  on public.dpe_cost_expenses(directorate_id, period_id, status);
create index if not exists ix_dpe_cost_expense_category
  on public.dpe_cost_expenses(directorate_id, category_id, period_id);
create index if not exists ix_dpe_cost_expense_center
  on public.dpe_cost_expenses(directorate_id, cost_center_id, period_id);
create index if not exists ix_dpe_cost_expense_source
  on public.dpe_cost_expenses(directorate_id, source_type, period_id);
create index if not exists ix_dpe_cost_expense_date
  on public.dpe_cost_expenses(expense_date);

create table if not exists public.dpe_cost_expense_staging_rows (
  id bigserial primary key,
  batch_id bigint not null references public.dpe_cost_expense_import_batches(id) on delete cascade,
  row_number integer not null,
  raw_data_json jsonb not null default '{}'::jsonb,
  normalized_data_json jsonb not null default '{}'::jsonb,
  status varchar(20) not null default 'PENDING'
    check (status in ('PENDING','VALID','ERROR','IGNORED','COMMITTED')),
  errors_json jsonb not null default '[]'::jsonb,
  committed_expense_id bigint references public.dpe_cost_expenses(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_cost_expense_staging_row unique (batch_id, row_number)
);

create index if not exists ix_dpe_cost_expense_staging_batch
  on public.dpe_cost_expense_staging_rows(batch_id, status, row_number);
create index if not exists ix_dpe_cost_expense_staging_expense
  on public.dpe_cost_expense_staging_rows(committed_expense_id);

alter table public.dpe_cost_expense_import_batches enable row level security;
alter table public.dpe_cost_expenses enable row level security;
alter table public.dpe_cost_expense_staging_rows enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 35, '035_dpe_expense_intake_v09615.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
