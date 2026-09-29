-- Data UNIVC v0.9.6.13 -- DPE Cost Engine Foundation
-- Migration aditiva sobre schema 33.
-- Cria o novo dominio de custeio mensal da DPE sem remover ou alterar as
-- tabelas financeiras/gerenciais legadas. Nenhum rateio e calculado aqui.

create table if not exists public.dpe_cost_periods (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(7) not null,
  status varchar(20) not null default 'DRAFT'
    check (status in ('DRAFT','REVIEW','CALCULATED','CLOSED')),
  notes text,
  opened_at timestamptz not null default now(),
  opened_by varchar(255),
  closed_at timestamptz,
  closed_by varchar(255),
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint ck_dpe_cost_period_format check (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  constraint uq_dpe_cost_period unique (directorate_id, period)
);

create index if not exists ix_dpe_cost_period_status
  on public.dpe_cost_periods(directorate_id, status, period);

create table if not exists public.dpe_academic_products (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  code varchar(80) not null,
  name varchar(220) not null,
  academic_level varchar(30) not null default 'GRADUATION'
    check (academic_level in ('GRADUATION','TECHNICAL','POSTGRADUATE','EXTENSION','OTHER')),
  source_course_id bigint references public.courses(id) on delete set null,
  external_key varchar(160),
  active boolean not null default true,
  valid_from varchar(7) not null,
  valid_to varchar(7),
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint ck_dpe_academic_product_validity check (valid_to is null or valid_to >= valid_from),
  constraint uq_dpe_academic_product_code unique (directorate_id, code)
);

create index if not exists ix_dpe_academic_product_active
  on public.dpe_academic_products(directorate_id, active, name);
create index if not exists ix_dpe_academic_product_source_course
  on public.dpe_academic_products(source_course_id);

create table if not exists public.dpe_academic_offerings (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  product_id bigint not null references public.dpe_academic_products(id) on delete restrict,
  code varchar(100) not null,
  modality varchar(40) not null default 'PRESENCIAL',
  shift varchar(40),
  campus varchar(120),
  unit_name varchar(160),
  pole_name varchar(160),
  external_key varchar(180),
  active boolean not null default true,
  valid_from varchar(7) not null,
  valid_to varchar(7),
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint ck_dpe_academic_offering_validity check (valid_to is null or valid_to >= valid_from),
  constraint uq_dpe_academic_offering_code unique (directorate_id, code)
);

create index if not exists ix_dpe_academic_offering_product
  on public.dpe_academic_offerings(product_id, active);
create index if not exists ix_dpe_academic_offering_dimensions
  on public.dpe_academic_offerings(directorate_id, modality, shift, active);

create table if not exists public.dpe_cost_centers (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  code varchar(80) not null,
  name varchar(180) not null,
  parent_id bigint references public.dpe_cost_centers(id) on delete restrict,
  external_key varchar(160),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint ck_dpe_cost_center_parent check (parent_id is null or parent_id <> id),
  constraint uq_dpe_cost_center_code unique (directorate_id, code)
);

create index if not exists ix_dpe_cost_center_parent on public.dpe_cost_centers(parent_id);
create index if not exists ix_dpe_cost_center_active on public.dpe_cost_centers(directorate_id, active, name);

create table if not exists public.dpe_allocation_rules (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  code varchar(80) not null,
  name varchar(180) not null,
  driver_type varchar(30) not null
    check (driver_type in ('DIRECT','TEACHER_HOURS','OFFERING_HOURS','STUDENTS','REVENUE','EQUAL','MANUAL')),
  description text,
  parameters_json jsonb not null default '{}'::jsonb,
  system_defined boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dpe_allocation_rule_code unique (directorate_id, code)
);

create index if not exists ix_dpe_allocation_rule_driver
  on public.dpe_allocation_rules(directorate_id, driver_type, active);

create table if not exists public.dpe_expense_categories (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  code varchar(80) not null,
  name varchar(180) not null,
  parent_id bigint references public.dpe_expense_categories(id) on delete restrict,
  default_rule_id bigint references public.dpe_allocation_rules(id) on delete set null,
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint ck_dpe_expense_category_parent check (parent_id is null or parent_id <> id),
  constraint uq_dpe_expense_category_code unique (directorate_id, code)
);

create index if not exists ix_dpe_expense_category_parent on public.dpe_expense_categories(parent_id);
create index if not exists ix_dpe_expense_category_rule on public.dpe_expense_categories(default_rule_id);
create index if not exists ix_dpe_expense_category_active on public.dpe_expense_categories(directorate_id, active, name);

-- Snapshot da composicao economica de cada competencia. O cadastro mestre pode
-- mudar depois; a competencia continua sabendo quais ofertas e atributos foram
-- considerados naquele mes.
create table if not exists public.dpe_cost_period_offerings (
  id bigserial primary key,
  period_id bigint not null references public.dpe_cost_periods(id) on delete cascade,
  offering_id bigint not null references public.dpe_academic_offerings(id) on delete restrict,
  offering_snapshot_json jsonb not null default '{}'::jsonb,
  included boolean not null default true,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  constraint uq_dpe_cost_period_offering unique (period_id, offering_id)
);

create index if not exists ix_dpe_cost_period_offering_period
  on public.dpe_cost_period_offerings(period_id, included);
create index if not exists ix_dpe_cost_period_offering_offering
  on public.dpe_cost_period_offerings(offering_id);

-- Regras padrao: sao somente metadados. O motor de rateio entra em etapa futura.
insert into public.dpe_allocation_rules (
  directorate_id, code, name, driver_type, description, parameters_json, system_defined, active
)
select d.id, seed.code, seed.name, seed.driver_type, seed.description, '{}'::jsonb, true, true
from public.directorates d
cross join (
  values
    ('DIRECT', 'Direto para oferta', 'DIRECT', 'Aloca a despesa diretamente para uma ou mais ofertas informadas.'),
    ('TEACHER_HOURS', 'Carga horaria docente', 'TEACHER_HOURS', 'Rateia o custo docente conforme a carga horaria do professor por oferta.'),
    ('OFFERING_HOURS', 'Carga horaria da oferta', 'OFFERING_HOURS', 'Rateia custos compartilhados conforme a carga horaria academica de cada oferta.'),
    ('STUDENTS', 'Quantidade de alunos', 'STUDENTS', 'Rateia conforme a populacao de alunos elegivel por oferta.'),
    ('REVENUE', 'Receita da oferta', 'REVENUE', 'Rateia conforme a participacao da oferta na receita elegivel.'),
    ('EQUAL', 'Divisao igualitaria', 'EQUAL', 'Divide igualmente entre as ofertas selecionadas.'),
    ('MANUAL', 'Rateio manual', 'MANUAL', 'Permite informar percentuais ou valores manualmente, com validacao posterior.')
) as seed(code, name, driver_type, description)
where d.code = 'DPE'
on conflict (directorate_id, code) do nothing;

alter table public.dpe_cost_periods enable row level security;
alter table public.dpe_academic_products enable row level security;
alter table public.dpe_academic_offerings enable row level security;
alter table public.dpe_cost_centers enable row level security;
alter table public.dpe_allocation_rules enable row level security;
alter table public.dpe_expense_categories enable row level security;
alter table public.dpe_cost_period_offerings enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 34, '034_dpe_cost_engine_foundation_v09613.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
