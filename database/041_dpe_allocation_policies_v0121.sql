-- Data UNIVC v0.12.1 -- DPE Politicas Reutilizaveis de Distribuicao
-- Migration aditiva sobre schema 40.
-- Cria politicas administrativas reutilizaveis sem alterar resultados historicos.

create table if not exists public.dpe_allocation_policies (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  name varchar(180) not null,
  allocation_rule_id bigint not null references public.dpe_allocation_rules(id) on delete restrict,
  scope_type varchar(20) not null default 'ALL'
    check (scope_type in ('ALL','SPECIFIC')),
  target_offerings_json jsonb not null default '[]'::jsonb,
  match_description varchar(255),
  source_category_id bigint references public.dpe_expense_categories(id) on delete set null,
  auto_suggest boolean not null default true,
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  constraint uq_dpe_allocation_policy_name unique (directorate_id, name)
);

create index if not exists ix_dpe_allocation_policy_active
  on public.dpe_allocation_policies(directorate_id, active, name);
create index if not exists ix_dpe_allocation_policy_match
  on public.dpe_allocation_policies(directorate_id, match_description, active);
create index if not exists ix_dpe_allocation_policy_rule
  on public.dpe_allocation_policies(allocation_rule_id);
create index if not exists ix_dpe_allocation_policy_category
  on public.dpe_allocation_policies(source_category_id);

alter table public.dpe_allocation_policies enable row level security;

-- O backend FastAPI segue como unico responsavel pelo acesso operacional.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 41, '041_dpe_allocation_policies_v0121.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
