-- Data UNIVC v0.5.0 — novo núcleo acadêmico DTNH/DCS
-- Indicadores operacionais:
--   xx-01 NPS Discente
--   xx-02 Avaliação Docente pelo Aluno
--   xx-03 Taxa de Aprovação e Desempenho Acadêmico
--
-- A migration é aditiva. As tabelas antigas de matrículas/frequência são
-- preservadas porque ainda podem servir de fonte auxiliar para outros processos
-- (ex.: denominadores administrativos) e para rastreabilidade histórica.
-- Nenhum curso é incluído nesta migration: o novo importador pode cadastrar
-- automaticamente curso, disciplina e aluno quando encontra um dado novo.

-- Metas acadêmicas passam a aceitar vigência semestral (AAAA-SEM1/SEM2).
alter table public.goals alter column valid_from type varchar(16);

insert into public.indicator_definitions(code,directorate_code,name,periodicity,formula_text,source_text,active) values
('DTNH-01','DTNH','NPS Discente','Semestral / conforme aplicação','% Promotores (9-10) - % Detratores (0-6)','Pesquisa institucional de satisfação segmentada por curso',true),
('DTNH-02','DTNH','Avaliação Docente pelo Aluno','Semestral','Média ponderada das notas de avaliação pelo número de respondentes','Instrumento institucional de avaliação docente pelo aluno',true),
('DTNH-03','DTNH','Taxa de Aprovação e Desempenho Acadêmico','Semestral','Alunos aprovados / alunos com resultado final x 100','Mapa de Nota do Aluno por Turma do SEI ou lançamento institucional equivalente',true),
('DCS-01','DCS','NPS Discente','Semestral / conforme aplicação','% Promotores (9-10) - % Detratores (0-6)','Pesquisa institucional de satisfação segmentada por curso',true),
('DCS-02','DCS','Avaliação Docente pelo Aluno','Semestral','Média ponderada das notas de avaliação pelo número de respondentes','Instrumento institucional de avaliação docente pelo aluno',true),
('DCS-03','DCS','Taxa de Aprovação e Desempenho Acadêmico','Semestral','Alunos aprovados / alunos com resultado final x 100','Mapa de Nota do Aluno por Turma do SEI ou lançamento institucional equivalente',true)
on conflict(code) do update set
  directorate_code=excluded.directorate_code,
  name=excluded.name,
  periodicity=excluded.periodicity,
  formula_text=excluded.formula_text,
  source_text=excluded.source_text,
  active=true;

insert into public.indicator_schedules(indicator_code,reference_grain,due_business_day,collection_window_start_business_day,active)
values
('DTNH-01','semester',5,1,true),('DTNH-02','semester',5,1,true),('DTNH-03','semester',5,1,true),
('DCS-01','semester',5,1,true),('DCS-02','semester',5,1,true),('DCS-03','semester',5,1,true)
on conflict(indicator_code) do update set reference_grain='semester', active=true;

create table if not exists public.teacher_evaluations (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(16) not null,
  course_id bigint not null references public.courses(id),
  discipline_id bigint not null references public.disciplines(id),
  teacher_name varchar(180) not null,
  respondents integer not null check(respondents > 0),
  average_score numeric(5,2) not null check(average_score >= 0 and average_score <= 10),
  inserted_at timestamptz not null default now(),
  inserted_by text,
  constraint uq_teacher_eval_period_course_discipline_teacher
    unique(directorate_id,period,course_id,discipline_id,teacher_name)
);

create table if not exists public.academic_students (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  registration varchar(80) not null,
  name varchar(220) not null,
  course_id bigint not null references public.courses(id),
  active boolean not null default true,
  inserted_at timestamptz not null default now(),
  inserted_by text,
  constraint uq_academic_student_registration unique(directorate_id,registration)
);

create table if not exists public.academic_results (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  period varchar(16) not null,
  course_id bigint not null references public.courses(id),
  discipline_id bigint not null references public.disciplines(id),
  student_id bigint not null references public.academic_students(id),
  class_group varchar(120) not null default '',
  curriculum_period varchar(80),
  final_average numeric(5,2) check(final_average is null or (final_average >= 0 and final_average <= 10)),
  official_status varchar(120),
  approved boolean,
  failure_reason varchar(40) check(failure_reason is null or failure_reason in ('nota','falta','outro')),
  source varchar(30) not null default 'manual',
  inserted_at timestamptz not null default now(),
  inserted_by text,
  constraint uq_academic_result_student_discipline_period
    unique(directorate_id,period,student_id,discipline_id)
);

create index if not exists ix_teacher_eval_period on public.teacher_evaluations(directorate_id,period);
create index if not exists ix_teacher_eval_course on public.teacher_evaluations(course_id,discipline_id);
create index if not exists ix_academic_students_directorate on public.academic_students(directorate_id,registration);
create index if not exists ix_academic_results_period on public.academic_results(directorate_id,period);
create index if not exists ix_academic_results_course on public.academic_results(course_id,discipline_id);
create index if not exists ix_academic_results_student on public.academic_results(student_id);

alter table public.teacher_evaluations enable row level security;
alter table public.academic_students enable row level security;
alter table public.academic_results enable row level security;
