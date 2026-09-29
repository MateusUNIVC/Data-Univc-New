-- Data UNIVC v0.13.0-dev.8 -- DPE-08 Teaching Domain
-- Separa identidade institucional, perfil DPE e vínculo mensal do docente.

create table if not exists public.dpe_teacher_profiles (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  teacher_id bigint not null references public.teachers(id) on delete restrict,
  default_relationship_type varchar(30) not null default 'UNSPECIFIED'
    check (default_relationship_type in ('UNSPECIFIED','EMPLOYEE','HOURLY','SERVICE_PROVIDER','OTHER')),
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  updated_by varchar(255),
  constraint uq_dpe_teacher_profile unique (directorate_id, teacher_id)
);

create index if not exists ix_dpe_teacher_profile_active
  on public.dpe_teacher_profiles(directorate_id, active);

-- Incorpora ao cadastro DPE apenas docentes que ja possuem evidencia de uso na DPE.
insert into public.dpe_teacher_profiles (
  directorate_id, teacher_id, default_relationship_type, active, notes, created_by, updated_by
)
select distinct d.id, src.teacher_id, 'UNSPECIFIED', true,
       'Perfil criado automaticamente a partir de uso historico na DPE.',
       'migration:048', 'migration:048'
from public.directorates d
join (
  select teacher_id from public.dpe_cost_period_teachers
  union
  select teacher_id from public.dpe_teacher_aliases
) src on true
where d.code = 'DPE'
on conflict (directorate_id, teacher_id) do nothing;

alter table public.dpe_cost_period_teachers
  add column if not exists relationship_type varchar(30);

update public.dpe_cost_period_teachers pt
set relationship_type = coalesce(p.default_relationship_type, 'UNSPECIFIED')
from public.dpe_teacher_profiles p
where p.directorate_id = pt.directorate_id
  and p.teacher_id = pt.teacher_id
  and (pt.relationship_type is null or btrim(pt.relationship_type) = '');

update public.dpe_cost_period_teachers
set relationship_type = 'UNSPECIFIED'
where relationship_type is null or btrim(relationship_type) = '';

alter table public.dpe_cost_period_teachers
  alter column relationship_type set default 'UNSPECIFIED';
alter table public.dpe_cost_period_teachers
  alter column relationship_type set not null;

alter table public.dpe_cost_period_teachers
  drop constraint if exists ck_dpe_cost_period_teacher_relationship;
alter table public.dpe_cost_period_teachers
  add constraint ck_dpe_cost_period_teacher_relationship
  check (relationship_type in ('UNSPECIFIED','EMPLOYEE','HOURLY','SERVICE_PROVIDER','OTHER'));

create index if not exists ix_dpe_cost_period_teacher_relationship
  on public.dpe_cost_period_teachers(directorate_id, period_id, relationship_type);

alter table public.dpe_teacher_profiles enable row level security;

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1,48,'048_dpe_teacher_profiles_v0130.sql',now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
