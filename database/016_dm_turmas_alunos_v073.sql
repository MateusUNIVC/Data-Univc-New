-- Data UNIVC v0.7.3 — DM orientado por turmas/coortes e áreas independentes.
-- Preserva as medições gerenciais antigas; o novo módulo utiliza dm_cohorts e dm_students.

insert into public.directorates(code,name,active) values
('DM','Diretoria de Mestrado',true)
on conflict(code) do update set name=excluded.name,active=true;

update public.indicator_definitions
set periodicity='Por turma',
    formula_text=case code
      when 'DM-01' then 'Evolução e situação acadêmica calculadas por turma e por área do programa'
      when 'DM-02' then 'Tempo entre ingresso e defesa calculado individualmente e consolidado por turma'
      else formula_text end,
    source_text='Cadastro de turmas, vínculo individual de alunos, datas de ingresso, qualificação e defesa'
where code in ('DM-01','DM-02');

update public.indicator_schedules
set reference_grain='cohort',
    notes='Acompanhamento por turma/coorte; a data de abertura é obrigatória. As duas áreas são independentes.'
where indicator_code in ('DM-01','DM-02');

create table if not exists public.dm_cohorts (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  area_code varchar(12) not null,
  area_name varchar(180) not null,
  cohort_number integer not null,
  opening_date date not null,
  vacancies_authorized integer,
  status varchar(40) not null default 'Em andamento',
  notes text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dm_cohort_area_number unique(directorate_id,area_code,cohort_number),
  constraint ck_dm_cohort_area check(area_code in ('CTE','SDS')),
  constraint ck_dm_cohort_number check(cohort_number > 0),
  constraint ck_dm_cohort_vacancies check(vacancies_authorized is null or vacancies_authorized > 0)
);

create table if not exists public.dm_students (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  cohort_id bigint not null references public.dm_cohorts(id),
  student_code varchar(80) not null,
  student_name varchar(220) not null,
  entry_date date not null,
  qualification_date date,
  defense_date date,
  defense_scheduled_date date,
  exit_date date,
  status varchar(40) not null default 'Ativo',
  advisor varchar(180),
  research_line varchar(220),
  notes text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now(),
  constraint uq_dm_student_code unique(directorate_id,student_code),
  constraint ck_dm_student_status check(status in ('Ativo','Titulado','Desligado','Trancado')),
  constraint ck_dm_student_dates check(
    (qualification_date is null or qualification_date >= entry_date) and
    (defense_date is null or defense_date >= entry_date) and
    (defense_scheduled_date is null or defense_scheduled_date >= entry_date) and
    (exit_date is null or exit_date >= entry_date)
  )
);

create index if not exists ix_dm_cohort_dir_area_opening
  on public.dm_cohorts(directorate_id,area_code,opening_date);
create index if not exists ix_dm_student_dir_cohort_status
  on public.dm_students(directorate_id,cohort_id,status);
create index if not exists ix_dm_student_dir_entry
  on public.dm_students(directorate_id,entry_date);
create index if not exists ix_dm_student_dir_defense
  on public.dm_students(directorate_id,defense_date);

alter table public.dm_cohorts enable row level security;
alter table public.dm_students enable row level security;

-- O acesso permanece exclusivamente pelo backend FastAPI; nenhuma policy pública é criada.
