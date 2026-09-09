-- Data UNIVC v0.2.0 — DADM operacional
-- Execute uma vez no Supabase > SQL Editor depois de 001..004.
-- Escopo: DADM-01, DADM-09 e DADM-10. O campus atual é único e, por isso,
-- não é modelado como uma dimensão nesta versão.

insert into public.indicator_definitions(code,directorate_code,name,periodicity,formula_text,source_text,active) values
(
  'DADM-01','DADM','Taxa de Evasão','Mensal',
  '(Desligamentos no mês ÷ Alunos ativos no início do mês) × 100',
  'Sistema acadêmico (trancamento, cancelamento e transferência) + registro de rescisão contratual',
  true
),
(
  'DADM-09','DADM','Custo Administrativo por Aluno','Mensal',
  'Despesa dos centros de custo administrativos no mês ÷ Nº de alunos ativos',
  'Setor Financeiro (centros de custo administrativos) + sistema acadêmico',
  true
),
(
  'DADM-10','DADM','Eficiência das Despesas de Infraestrutura','Mensal',
  'Despesa de infraestrutura e manutenção no mês ÷ m² em uso; e Despesa de infraestrutura ÷ Nº de alunos ativos',
  'Setor Financeiro (centro de custo de infraestrutura) + mapa de áreas e salas',
  true
)
on conflict(code) do update set
  directorate_code=excluded.directorate_code,
  name=excluded.name,
  periodicity=excluded.periodicity,
  formula_text=excluded.formula_text,
  source_text=excluded.source_text,
  active=excluded.active;

insert into public.indicator_schedules(indicator_code,reference_grain,due_business_day,collection_window_start_business_day,active)
values
('DADM-01','month',5,1,true),
('DADM-09','month',5,1,true),
('DADM-10','month',5,1,true)
on conflict(indicator_code) do update set
  reference_grain='month',
  active=true;

create table if not exists public.dadm_attrition (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  course_id bigint not null references public.courses(id),
  active_students_start integer not null check(active_students_start > 0),
  departures integer not null check(departures >= 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id, period, course_id),
  check(departures <= active_students_start)
);

create table if not exists public.dadm_active_students (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  modality varchar(80) not null,
  active_students integer not null check(active_students >= 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id, period, modality)
);

create table if not exists public.dadm_administrative_costs (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  cost_center varchar(160) not null,
  modality varchar(80) not null,
  expense_amount numeric(14,2) not null check(expense_amount >= 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id, period, cost_center, modality)
);

create table if not exists public.dadm_infrastructure (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  infrastructure_expense numeric(14,2) not null check(infrastructure_expense >= 0),
  area_in_use_m2 numeric(14,2) not null check(area_in_use_m2 > 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id, period)
);

create index if not exists ix_dadm_attrition_period
  on public.dadm_attrition(directorate_id,period);
create index if not exists ix_dadm_active_students_period
  on public.dadm_active_students(directorate_id,period);
create index if not exists ix_dadm_admin_costs_period
  on public.dadm_administrative_costs(directorate_id,period);
create index if not exists ix_dadm_infrastructure_period
  on public.dadm_infrastructure(directorate_id,period);

alter table public.dadm_attrition enable row level security;
alter table public.dadm_active_students enable row level security;
alter table public.dadm_administrative_costs enable row level security;
alter table public.dadm_infrastructure enable row level security;
