-- Data UNIVC v0.7.7 — fundação financeira única da DPE
-- Mantém management_indicator_* e todo o histórico DPE legado para auditoria.
-- A nova camada evita cadastrar receita/folha/despesas mais de uma vez.

create table if not exists public.dpe_monthly_revenues (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  net_revenue numeric(16,2) not null check (net_revenue >= 0),
  notes text,
  validated boolean not null default false,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_monthly_revenue_period unique(directorate_id, period)
);

create table if not exists public.dpe_course_revenues (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  course_id bigint not null references public.courses(id),
  allocated_revenue numeric(16,2) not null check (allocated_revenue >= 0),
  notes text,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_course_revenue_period_course unique(directorate_id, period, course_id)
);

create table if not exists public.dpe_expenses (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  description varchar(240) not null,
  amount numeric(16,2) not null check (amount > 0),
  expense_kind varchar(30) not null default 'GENERAL',
  category varchar(40) not null default 'OTHER',
  payroll_group varchar(30),
  payroll_nature varchar(30),
  is_capex boolean not null default false,
  notes text,
  validated boolean not null default false,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  updated_at timestamptz not null default now()
);

create table if not exists public.dpe_expense_allocations (
  id bigserial primary key,
  expense_id bigint not null references public.dpe_expenses(id) on delete cascade,
  course_id bigint not null references public.courses(id),
  allocated_amount numeric(16,2) not null check (allocated_amount > 0),
  notes text,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_expense_allocation_course unique(expense_id, course_id)
);

create table if not exists public.dpe_course_cost_snapshots (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  course_id bigint not null references public.courses(id),
  reported_total_cost numeric(16,2) not null check (reported_total_cost >= 0),
  details_json jsonb not null default '[]'::jsonb,
  notes text,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_course_cost_period_course unique(directorate_id, period, course_id)
);

create index if not exists ix_dpe_monthly_revenue_period on public.dpe_monthly_revenues(directorate_id, period);
create index if not exists ix_dpe_course_revenue_period on public.dpe_course_revenues(directorate_id, period);
create index if not exists ix_dpe_course_revenue_course on public.dpe_course_revenues(directorate_id, course_id, period);
create index if not exists ix_dpe_expense_period on public.dpe_expenses(directorate_id, period);
create index if not exists ix_dpe_expense_kind on public.dpe_expenses(directorate_id, expense_kind, period);
create index if not exists ix_dpe_expense_category on public.dpe_expenses(directorate_id, category, period);
create index if not exists ix_dpe_expense_allocation_expense on public.dpe_expense_allocations(expense_id);
create index if not exists ix_dpe_expense_allocation_course on public.dpe_expense_allocations(course_id);
create index if not exists ix_dpe_course_cost_period on public.dpe_course_cost_snapshots(directorate_id, period);
create index if not exists ix_dpe_course_cost_course on public.dpe_course_cost_snapshots(directorate_id, course_id, period);

alter table public.dpe_monthly_revenues enable row level security;
alter table public.dpe_course_revenues enable row level security;
alter table public.dpe_expenses enable row level security;
alter table public.dpe_expense_allocations enable row level security;
alter table public.dpe_course_cost_snapshots enable row level security;

-- O backend FastAPI continua sendo o único responsável pelo acesso operacional.
