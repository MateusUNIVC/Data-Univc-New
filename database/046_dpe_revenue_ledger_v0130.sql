-- Data UNIVC v0.13.0-dev.6 - DPE-06 revenue ledger
-- Introduces a simple revenue-entry domain. Legacy economics revenue columns
-- remain temporarily as a compatibility mirror for allocation/result modules
-- and will be retired after those consumers migrate.

create table if not exists public.dpe_revenue_categories (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  code varchar(80) not null,
  name varchar(160) not null,
  scope varchar(20) not null default 'BOTH',
  active boolean not null default true,
  system boolean not null default false,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  constraint uq_dpe_revenue_category_code unique(directorate_id, code),
  constraint ck_dpe_revenue_category_scope check(scope in ('COURSE','INSTITUTIONAL','BOTH'))
);
create index if not exists ix_dpe_revenue_categories_directorate on public.dpe_revenue_categories(directorate_id);
alter table public.dpe_revenue_categories enable row level security;

create table if not exists public.dpe_revenue_entries (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period_id bigint not null references public.dpe_cost_periods(id) on delete restrict,
  period_offering_id bigint references public.dpe_cost_period_offerings(id) on delete restrict,
  category_id bigint not null references public.dpe_revenue_categories(id) on delete restrict,
  description varchar(255) not null,
  amount numeric(18,2) not null,
  source_type varchar(20) not null default 'MANUAL',
  source_reference varchar(255),
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  constraint ck_dpe_revenue_entry_amount_nonnegative check(amount >= 0),
  constraint ck_dpe_revenue_entry_source check(source_type in ('MANUAL','IMPORT','API','SYSTEM','MIGRATION'))
);
create index if not exists ix_dpe_revenue_period on public.dpe_revenue_entries(directorate_id,period_id);
create index if not exists ix_dpe_revenue_period_offering on public.dpe_revenue_entries(period_id,period_offering_id);
alter table public.dpe_revenue_entries enable row level security;

insert into public.dpe_revenue_categories(directorate_id,code,name,scope,active,system,created_by)
select d.id,v.code,v.name,v.scope,true,true,'migration:046'
from public.directorates d
cross join (values
 ('COURSE_REVENUE','Receita de curso','COURSE'),
 ('ROOM_RENTAL','Aluguel de salas','INSTITUTIONAL'),
 ('SPORTS_RENTAL','Aluguel de quadras','INSTITUTIONAL'),
 ('STRUCTURE_USE','Utilização de estrutura','BOTH'),
 ('BRANCH_USE','Utilização de filial','BOTH'),
 ('SERVICES','Serviços','BOTH'),
 ('EVENTS','Eventos','BOTH'),
 ('OTHER','Outras receitas','BOTH')
) as v(code,name,scope)
where d.code='DPE'
on conflict(directorate_id,code) do nothing;

-- Preserve the only business value from the old revenue model: the final
-- revenue attributed to a course/context. Gross revenue, discounts, deductions
-- and paying-student mechanics are deliberately not migrated into the new domain.
insert into public.dpe_revenue_entries(
  directorate_id,period_id,period_offering_id,category_id,description,amount,
  source_type,source_reference,notes,created_by,updated_by
)
select e.directorate_id,e.period_id,e.period_offering_id,c.id,'Receita do curso',e.net_revenue,
       'MIGRATION','ECONOMICS:'||e.id::text,
       'Migrado da receita líquida histórica na adoção do ledger simplificado.',
       'migration:046','migration:046'
from public.dpe_cost_offering_economics e
join public.dpe_revenue_categories c on c.directorate_id=e.directorate_id and c.code='COURSE_REVENUE'
where e.net_revenue is not null
  and not exists (
    select 1 from public.dpe_revenue_entries r
    where r.directorate_id=e.directorate_id and r.source_reference='ECONOMICS:'||e.id::text
  );

insert into public.data_univc_schema_version (id,version,migration_name,applied_at)
values (1,46,'046_dpe_revenue_ledger_v0130.sql',now())
on conflict(id) do update set version=excluded.version,migration_name=excluded.migration_name,applied_at=excluded.applied_at;
