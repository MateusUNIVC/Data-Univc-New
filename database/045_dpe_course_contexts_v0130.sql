-- Data UNIVC v0.13.0-dev.5 - DPE-05 course/context semantics
-- Course modality is no longer restricted to PRESENCIAL. The historical
-- dpe_academic_offerings table remains the internal cost-object table, while
-- the application treats rows as optional course contexts.

alter table public.dpe_academic_offerings
  alter column modality set default 'NAO_INFORMADA';

-- Backfill one technical base context for every existing DPE course. It stays
-- internal while the UI exposes only optional additional contexts.
insert into public.dpe_academic_offerings (
  directorate_id, product_id, code, modality, shift, campus, unit_name, pole_name,
  external_key, active, valid_from, valid_to, notes, created_by
)
select
  p.directorate_id,
  p.id,
  upper(p.code) || '-BASE',
  case
    when upper(trim(coalesce(c.modality, ''))) = 'PRESENCIAL' then 'PRESENCIAL'
    when upper(trim(coalesce(c.modality, ''))) in ('EAD', 'A DISTANCIA', 'A DISTÂNCIA', 'DISTANCIA', 'DISTÂNCIA') then 'EAD'
    when upper(trim(coalesce(c.modality, ''))) in ('SEMIPRESENCIAL', 'SEMI PRESENCIAL', 'SEMI-PRESENCIAL') then 'SEMIPRESENCIAL'
    when upper(trim(coalesce(c.modality, ''))) in ('HIBRIDO', 'HÍBRIDO', 'HYBRID') then 'HIBRIDO'
    when nullif(trim(coalesce(c.modality, '')), '') is null then 'NAO_INFORMADA'
    else upper(trim(c.modality))
  end,
  null, null, null, null, null,
  p.active, p.valid_from, p.valid_to,
  'Contexto-base automático do curso. Não representa um contexto separado.',
  'migration:045'
from public.dpe_academic_products p
left join public.courses c on c.id = p.source_course_id
where not exists (
  select 1
  from public.dpe_academic_offerings o
  where o.directorate_id = p.directorate_id
    and upper(o.code) = upper(p.code) || '-BASE'
)
on conflict (directorate_id, code) do nothing;

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 45, '045_dpe_course_contexts_v0130.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
