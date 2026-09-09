-- Data UNIVC v0.4.0 — DPE operacional
-- Escopo desta entrega: DPE-01, DPE-04 e DPE-05.
-- Não há integração adicional com base de alunos: os três indicadores são financeiros/gerenciais.

insert into public.directorates(code,name,active)
values ('DPE','Diretoria de Planejamento Econômico-Financeiro e Oferta',true)
on conflict(code) do update set active=true;

insert into public.indicator_definitions(code,directorate_code,name,periodicity,formula_text,source_text,active) values
('DPE-01','DPE','Resultado Operacional','Mensal','((Receita líquida − Despesa total) ÷ Receita líquida) × 100','Setor Financeiro — DRE gerencial mensal com centros de custo por modalidade, polo, curso e programa',true),
('DPE-04','DPE','Execução Orçamentária','Mensal','(Despesa realizada no mês ÷ Despesa orçada no mês) × 100','Orçamento anual aprovado + razão contábil',true),
('DPE-05','DPE','Saldo Operacional de Caixa','Mensal','Entradas do mês − Saídas do mês (e saldo acumulado)','Extratos e fluxo de caixa consolidado',true)
on conflict(code) do update set directorate_code=excluded.directorate_code,name=excluded.name,periodicity=excluded.periodicity,formula_text=excluded.formula_text,source_text=excluded.source_text,active=true;

insert into public.indicator_schedules(indicator_code,reference_grain,due_business_day,collection_window_start_business_day,active)
values ('DPE-01','month',5,1,true),('DPE-04','month',5,1,true),('DPE-05','month',5,1,true)
on conflict(indicator_code) do update set reference_grain='month',active=true;

create table if not exists public.dpe_operating_results (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  scope_type varchar(60) not null,
  scope_label varchar(180) not null,
  net_revenue numeric(16,2) not null check(net_revenue > 0),
  total_expense numeric(16,2) not null check(total_expense >= 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id,period,scope_type,scope_label)
);

create table if not exists public.dpe_budget_execution (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  budget_directorate varchar(40) not null,
  cost_center varchar(180) not null,
  budgeted_expense numeric(16,2) not null check(budgeted_expense > 0),
  actual_expense numeric(16,2) not null check(actual_expense >= 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id,period,budget_directorate,cost_center)
);

create table if not exists public.dpe_cash_movements (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  account varchar(180) not null,
  movement_type varchar(20) not null check(movement_type in ('Entrada','Saída')),
  nature varchar(180) not null,
  amount numeric(16,2) not null check(amount > 0),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  unique(directorate_id,period,account,movement_type,nature)
);

create index if not exists ix_dpe_result_period on public.dpe_operating_results(directorate_id,period);
create index if not exists ix_dpe_budget_period on public.dpe_budget_execution(directorate_id,period);
create index if not exists ix_dpe_cash_period on public.dpe_cash_movements(directorate_id,period);

alter table public.dpe_operating_results enable row level security;
alter table public.dpe_budget_execution enable row level security;
alter table public.dpe_cash_movements enable row level security;
