-- UNIVC Data Driven Cloud v0.1
-- Execute once in Supabase > SQL Editor.

create table if not exists public.directorates (
  id bigserial primary key,
  code text not null unique,
  name text not null,
  active boolean not null default true
);

insert into public.directorates(code,name) values
('REITORIA','Reitoria'),('DPE','Diretoria de Planejamento Econômico e Oferta'),('DTNH','Diretoria de Tecnologia, Negócios e Humanidades'),('DCS','Diretoria de Ciências da Saúde'),('DEAD','Diretoria de EAD, Semipresencial, Marketing e Digital'),('DADM','Diretoria Administrativa'),('DM','Diretoria de Mestrado')
on conflict (code) do update set name=excluded.name;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text,
  role text not null default 'viewer' check (role in ('admin','director','editor','viewer')),
  directorate_id bigint references public.directorates(id)
);

create or replace function public.handle_new_user() returns trigger language plpgsql security definer set search_path=public as $$
begin
  insert into public.profiles(id,email,full_name) values(new.id,new.email,coalesce(new.raw_user_meta_data->>'full_name','')) on conflict(id) do nothing;
  return new;
end; $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute procedure public.handle_new_user();

create table if not exists public.courses (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  name text not null,
  active boolean not null default true,
  valid_from varchar(7) not null,
  valid_to varchar(7),
  unique(directorate_id,name)
);
create table if not exists public.disciplines (
  id bigserial primary key,
  course_id bigint not null references public.courses(id),
  name text not null,
  active boolean not null default true,
  valid_from varchar(7) not null,
  valid_to varchar(7),
  unique(course_id,name)
);

create table if not exists public.indicator_definitions (
  code text primary key,
  directorate_code text not null,
  name text not null,
  periodicity text,
  formula_text text,
  source_text text,
  active boolean not null default true
);
create table if not exists public.indicator_schedules (
  id bigserial primary key,
  indicator_code text not null unique references public.indicator_definitions(code),
  reference_grain text not null default 'monthly',
  due_business_day int not null default 5 check(due_business_day between 1 and 23),
  collection_window_start_business_day int not null default 1,
  active boolean not null default true,
  notes text
);

create table if not exists public.nps_student (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(16) not null,
  course_id bigint not null references public.courses(id),
  respondents int not null check(respondents>0), promoters int not null check(promoters>=0), neutrals int not null check(neutrals>=0), detractors int not null check(detractors>=0),
  inserted_at timestamptz not null default now(), inserted_by text,
  unique(directorate_id,period,course_id),
  check(promoters+neutrals+detractors=respondents)
);
create table if not exists public.enrollments (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id), period varchar(16) not null, course_id bigint not null references public.courses(id), active_enrollments int not null check(active_enrollments>=0), inserted_at timestamptz not null default now(), inserted_by text,
  unique(directorate_id,period,course_id)
);
create table if not exists public.attendance (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id), period varchar(16) not null, course_id bigint not null references public.courses(id), discipline_id bigint not null references public.disciplines(id), expected_attendance int not null check(expected_attendance>0), recorded_attendance int not null check(recorded_attendance>=0), inserted_at timestamptz not null default now(), inserted_by text,
  unique(directorate_id,period,course_id,discipline_id), check(recorded_attendance<=expected_attendance)
);
create table if not exists public.goals (
  id bigserial primary key, directorate_id bigint not null references public.directorates(id), indicator_code text not null, scope_label text not null default 'TOTAL', valid_from varchar(7) not null, target double precision not null, attention double precision not null, upper_limit double precision, justification text,
  unique(directorate_id,indicator_code,scope_label,valid_from)
);
create table if not exists public.action_plans (
  id bigserial primary key, directorate_id bigint not null references public.directorates(id), number int not null, month varchar(7) not null, indicator_code text not null, scope_label text not null, result_value double precision, target_value double precision, problem text not null, probable_cause text, corrective_action text not null, responsible text not null, due_date date not null, action_target text, status text not null, created_at timestamptz not null default now(), unique(directorate_id,number)
);
create table if not exists public.audit_log (
  id bigserial primary key, directorate_id bigint references public.directorates(id), user_id uuid, user_email text, action text not null, entity text not null, entity_id text, details text, created_at timestamptz not null default now()
);
create index if not exists ix_nps_period on public.nps_student(directorate_id,period);
create index if not exists ix_enrollments_period on public.enrollments(directorate_id,period);
create index if not exists ix_attendance_period on public.attendance(directorate_id,period);
create index if not exists ix_audit_created on public.audit_log(directorate_id,created_at desc);

-- The application accesses tables through FastAPI. Lock direct browser access to these tables.
alter table public.profiles enable row level security;
alter table public.courses enable row level security;
alter table public.disciplines enable row level security;
alter table public.indicator_definitions enable row level security;
alter table public.indicator_schedules enable row level security;
alter table public.nps_student enable row level security;
alter table public.enrollments enable row level security;
alter table public.attendance enable row level security;
alter table public.goals enable row level security;
alter table public.action_plans enable row level security;
alter table public.audit_log enable row level security;

-- A logged-in user may read their own profile through Supabase APIs. Operational tables intentionally have no anon/authenticated policies because the FastAPI backend owns data access.
drop policy if exists "profile_self_read" on public.profiles;
create policy "profile_self_read" on public.profiles for select to authenticated using (id=auth.uid());
