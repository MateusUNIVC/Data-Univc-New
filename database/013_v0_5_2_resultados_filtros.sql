-- Data UNIVC v0.5.2 - integridade dos resultados academicos
--
-- Corrige a chave de duplicidade de academic_results para preservar ofertas
-- legitimas do mesmo aluno quando turma/oferta for diferente.
-- Nova chave: diretoria + semestre + curso + disciplina + aluno + turma.
--
-- Esta migration NAO altera nem remove dados existentes.

do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conname = 'uq_academic_result_student_discipline_period'
      and conrelid = 'public.academic_results'::regclass
  ) then
    alter table public.academic_results
      drop constraint uq_academic_result_student_discipline_period;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'uq_academic_result_student_discipline_class_period'
      and conrelid = 'public.academic_results'::regclass
  ) then
    alter table public.academic_results
      add constraint uq_academic_result_student_discipline_class_period
      unique (directorate_id, period, course_id, discipline_id, student_id, class_group);
  end if;
end $$;
