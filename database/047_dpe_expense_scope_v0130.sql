-- Data UNIVC v0.13.0-dev.7 -- DPE-07 Expense Scope
-- Torna explicito o tratamento economico de cada despesa: direta, compartilhada ou institucional.

alter table public.dpe_cost_expenses
  add column if not exists expense_scope varchar(20);

update public.dpe_cost_expenses e
set expense_scope = case
  when exists (
    select 1 from public.dpe_allocation_rules r
    where r.id = e.allocation_rule_id and r.driver_type = 'DIRECT'
  ) then 'DIRECT'
  else 'SHARED'
end
where expense_scope is null or btrim(expense_scope) = '';

alter table public.dpe_cost_expenses
  alter column expense_scope set default 'SHARED';
alter table public.dpe_cost_expenses
  alter column expense_scope set not null;

alter table public.dpe_cost_expenses
  drop constraint if exists ck_dpe_cost_expense_scope;
alter table public.dpe_cost_expenses
  add constraint ck_dpe_cost_expense_scope
  check (expense_scope in ('DIRECT','SHARED','INSTITUTIONAL'));

create index if not exists ix_dpe_cost_expense_scope
  on public.dpe_cost_expenses(directorate_id, period_id, expense_scope, status);

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1,47,'047_dpe_expense_scope_v0130.sql',now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
