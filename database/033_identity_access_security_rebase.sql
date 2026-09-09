-- Data UNIVC v0.9.6.0 -- Identity, Session & Authorization Rebase
-- Base oficial: v0.8.33.0 / schema 32 (032_dm_domain_simplification_v08290.sql).
-- Consolida o estado final das migrations de identidade 0.9.x sem colidir com a
-- migration 032 da linha DM 0.8.33.

create table if not exists public.app_users (
  id uuid primary key,
  auth_provider text not null default 'SUPABASE',
  auth_provider_id text not null,
  email text,
  name text,
  global_role text not null default 'DIRECTORATE' check (global_role in ('REITORIA','DIRECTORATE')),
  active boolean not null default true,
  permission_version integer not null default 1 check (permission_version >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(auth_provider, auth_provider_id)
);
create index if not exists ix_app_users_email on public.app_users(email);
create index if not exists ix_app_users_active on public.app_users(active);

create table if not exists public.user_directorate_access (
  user_id uuid not null references public.app_users(id) on delete cascade,
  directorate_id bigint not null references public.directorates(id) on delete cascade,
  access_level text not null default 'READ' check (access_level in ('READ','EDIT')),
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, directorate_id)
);
create index if not exists ix_user_directorate_access_directorate on public.user_directorate_access(directorate_id);
create unique index if not exists uq_user_directorate_access_primary on public.user_directorate_access(user_id) where is_primary;

insert into public.app_users (
  id, auth_provider, auth_provider_id, email, name, global_role, active, permission_version
)
select p.id, 'SUPABASE', p.id::text, p.email, p.full_name, 'DIRECTORATE', true, 1
from public.profiles p
on conflict (id) do nothing;

insert into public.user_directorate_access (user_id, directorate_id, access_level, is_primary)
select p.id, p.directorate_id,
       case when lower(coalesce(p.role, 'viewer')) = 'viewer' then 'READ' else 'EDIT' end,
       true
from public.profiles p
where p.directorate_id is not null
on conflict (user_id, directorate_id) do nothing;

create table if not exists public.auth_sessions (
  id uuid primary key,
  user_id uuid not null references public.app_users(id) on delete cascade,
  refresh_token_hash varchar(64) not null unique,
  token_family uuid not null,
  family_created_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  user_agent_hash varchar(64),
  ip_hash varchar(64)
);
create index if not exists ix_auth_sessions_user_id on public.auth_sessions(user_id);
create index if not exists ix_auth_sessions_token_family on public.auth_sessions(token_family);
create index if not exists ix_auth_sessions_active_expiry on public.auth_sessions(expires_at) where revoked_at is null;
create index if not exists ix_auth_sessions_user_active on public.auth_sessions(user_id, revoked_at);

create table if not exists public.auth_audit_log (
  id bigserial primary key,
  event_type text not null,
  outcome text not null default 'INFO',
  actor_user_id uuid references public.app_users(id) on delete set null,
  target_user_id uuid references public.app_users(id) on delete set null,
  email text,
  directorate_code text,
  ip_hash text,
  user_agent_hash text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists ix_auth_audit_event_created on public.auth_audit_log(event_type, created_at desc);
create index if not exists ix_auth_audit_actor_created on public.auth_audit_log(actor_user_id, created_at desc);
create index if not exists ix_auth_audit_target_created on public.auth_audit_log(target_user_id, created_at desc);
create index if not exists ix_auth_audit_email_created on public.auth_audit_log(email, created_at desc);
create index if not exists ix_auth_audit_ip_created on public.auth_audit_log(ip_hash, created_at desc);

alter table public.survey_imports add column if not exists directorate_id bigint references public.directorates(id);
alter table public.survey_runs add column if not exists directorate_id bigint references public.directorates(id);

with audit_owner as (
  select entity_id::bigint as run_id, min(directorate_id) as directorate_id
  from public.audit_log
  where entity in ('survey_run', 'survey_faculty', 'survey_faculty_institution')
    and entity_id ~ '^[0-9]+$'
  group by entity_id::bigint
  having count(distinct directorate_id) = 1
)
update public.survey_runs r set directorate_id = a.directorate_id
from audit_owner a where r.id = a.run_id and r.directorate_id is null;

with course_owner as (
  select src.run_id, min(c.directorate_id) as directorate_id
  from public.survey_run_courses src join public.courses c on c.id = src.course_id
  group by src.run_id having count(distinct c.directorate_id) = 1
)
update public.survey_runs r set directorate_id = c.directorate_id
from course_owner c where r.id = c.run_id and r.directorate_id is null;

with faculty_owner as (
  select fec.run_id, min(c.directorate_id) as directorate_id
  from public.faculty_evaluation_contexts fec
  join public.teaching_assignments ta on ta.id = fec.teaching_assignment_id
  join public.academic_offerings ao on ao.id = ta.offering_id
  join public.courses c on c.id = ao.course_id
  group by fec.run_id having count(distinct c.directorate_id) = 1
)
update public.survey_runs r set directorate_id = f.directorate_id
from faculty_owner f where r.id = f.run_id and r.directorate_id is null;

with nps_owner as (
  select run_id, min(directorate_id) as directorate_id
  from (
    select run_id, directorate_id from public.survey_nps_sources
    union all
    select run_id, directorate_id from public.survey_nps_institution_sources
  ) x group by run_id having count(distinct directorate_id) = 1
)
update public.survey_runs r set directorate_id = n.directorate_id
from nps_owner n where r.id = n.run_id and r.directorate_id is null;

update public.survey_imports i set directorate_id = r.directorate_id
from public.survey_runs r
where r.import_id = i.id and i.directorate_id is null and r.directorate_id is not null;

alter table public.survey_imports drop constraint if exists survey_imports_sha256_key;
alter table public.survey_imports drop constraint if exists survey_imports_external_key_key;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'uq_survey_import_directorate_sha256') then
    alter table public.survey_imports add constraint uq_survey_import_directorate_sha256 unique (directorate_id, sha256);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'uq_survey_import_directorate_external_key') then
    alter table public.survey_imports add constraint uq_survey_import_directorate_external_key unique (directorate_id, external_key);
  end if;
end $$;
create index if not exists ix_survey_imports_directorate_id on public.survey_imports(directorate_id);
create index if not exists ix_survey_runs_directorate_id on public.survey_runs(directorate_id);

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path=public as $$
begin
  insert into public.profiles(id,email,full_name)
  values(new.id,new.email,coalesce(new.raw_user_meta_data->>'full_name',''))
  on conflict(id) do nothing;

  insert into public.app_users(id,auth_provider,auth_provider_id,email,name,global_role,active,permission_version)
  values(new.id,'SUPABASE',new.id::text,new.email,coalesce(new.raw_user_meta_data->>'full_name',''),'DIRECTORATE',true,1)
  on conflict(id) do nothing;
  return new;
end; $$;

alter table public.app_users enable row level security;
alter table public.user_directorate_access enable row level security;
alter table public.auth_sessions enable row level security;
alter table public.auth_audit_log enable row level security;

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 33, '033_identity_access_security_rebase.sql', now())
on conflict (id) do update
set version = excluded.version,
    migration_name = excluded.migration_name,
    applied_at = excluded.applied_at;
