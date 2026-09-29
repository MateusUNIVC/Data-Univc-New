-- Data UNIVC v0.13.0-dev.4 - DPE-04 domain consolidation
-- DPE-01/02/03 remain temporarily for historical measurements/Excel only.
-- New targets/actions use canonical domain groups. Existing management rows are
-- archived before safe remapping.

create table if not exists public.dpe_domain_legacy_management_archive (
  id bigserial primary key,
  source_table varchar(96) not null,
  source_pk bigint not null,
  payload_json jsonb not null,
  archived_at timestamptz not null default now(),
  constraint uq_dpe_domain_legacy_mgmt_source unique(source_table, source_pk)
);

alter table public.dpe_domain_legacy_management_archive enable row level security;

insert into public.dpe_domain_legacy_management_archive(source_table, source_pk, payload_json)
select 'management_indicator_targets', t.id, to_jsonb(t)
from public.management_indicator_targets t
join public.directorates d on d.id=t.directorate_id
where d.code='DPE' and t.indicator_code in ('DPE-01','DPE-02','DPE-03')
on conflict(source_table,source_pk) do nothing;

insert into public.dpe_domain_legacy_management_archive(source_table, source_pk, payload_json)
select 'management_indicator_actions', a.id, to_jsonb(a)
from public.management_indicator_actions a
join public.directorates d on d.id=a.directorate_id
where d.code='DPE' and a.indicator_code in ('DPE-01','DPE-02','DPE-03')
on conflict(source_table,source_pk) do nothing;

create temporary table dpe_domain_metric_map (
  old_code varchar(30) not null,
  old_metric varchar(80) not null,
  new_code varchar(30) not null,
  new_metric varchar(80) not null
) on commit drop;

insert into dpe_domain_metric_map(old_code,old_metric,new_code,new_metric) values
('DPE-01','net_margin_pct','DPE-RESULT','course_margin_pct'),
('DPE-01','net_margin_12m_pct','DPE-RESULT','course_margin_12m_pct'),
('DPE-01','total_cost','DPE-EXPENSE','course_total_cost'),
('DPE-01','avg_hours_per_teacher','DPE-TEACHING','avg_hours_per_teacher'),
('DPE-02','coverage_index','DPE-RESULT','coverage_index'),
('DPE-02','coverage_index_12m','DPE-RESULT','coverage_index_12m'),
('DPE-02','operating_margin_pct','DPE-RESULT','institutional_margin_pct'),
('DPE-02','operating_margin_12m_pct','DPE-RESULT','institutional_margin_12m_pct'),
('DPE-02','total_expense','DPE-EXPENSE','total_expense'),
('DPE-03','payroll_on_revenue_pct','DPE-EXPENSE','payroll_on_revenue_pct'),
('DPE-03','faculty_payroll_pct','DPE-TEACHING','faculty_payroll_pct'),
('DPE-03','administrative_payroll_pct','DPE-EXPENSE','administrative_payroll_pct'),
('DPE-03','payroll_monthly_change_pct','DPE-EXPENSE','payroll_monthly_change_pct');

-- If the canonical equivalent already exists, keep the canonical row and remove
-- only the legacy duplicate. The original legacy row is preserved in the archive.
delete from public.management_indicator_targets old
using public.directorates d, dpe_domain_metric_map m
where d.id=old.directorate_id and d.code='DPE'
  and old.indicator_code=m.old_code and old.metric_key=m.old_metric
  and exists (
    select 1 from public.management_indicator_targets n
    where n.directorate_id=old.directorate_id
      and n.indicator_code=m.new_code
      and n.metric_key=m.new_metric
      and n.dimension_key=old.dimension_key
      and n.valid_from=old.valid_from
  );

update public.management_indicator_targets t
set indicator_code=m.new_code, metric_key=m.new_metric
from public.directorates d, dpe_domain_metric_map m
where d.id=t.directorate_id and d.code='DPE'
  and t.indicator_code=m.old_code and t.metric_key=m.old_metric;

update public.management_indicator_actions a
set indicator_code=m.new_code, metric_key=m.new_metric
from public.directorates d, dpe_domain_metric_map m
where d.id=a.directorate_id and d.code='DPE'
  and a.indicator_code=m.old_code and a.metric_key=m.old_metric;

-- Rows without an exact mapping (including indicator-only plans and the old
-- 3-month payroll metric) remain historical under DPE-01/02/03. They are not
-- offered for new entry by the application.

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 44, '044_dpe_domain_consolidation_v0130.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
