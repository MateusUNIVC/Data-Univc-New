-- Data UNIVC v0.8.29.0 — DM Domain Simplification & Cohort Lifecycle.
-- Executar depois de 031_academic_faculty_nps_v08250.sql.
--
-- Domínio ativo do aluno: Ativo | Titulado | Desligado.
-- Uma defesa confirmada caracteriza Titulado.
-- Turmas com todos os alunos em estado terminal são encerradas automaticamente.

-- Preserva a situação original do SEI antes de retirar Trancado do domínio ativo.
UPDATE public.dm_students
SET sei_raw_status = COALESCE(NULLIF(sei_raw_status, ''), 'Trancado')
WHERE status = 'Trancado';

-- A defesa é o marco ativo de titulação. Corrige bases antigas inconsistentes
-- antes de fortalecer a constraint do banco.
UPDATE public.dm_students
SET status = 'Titulado'
WHERE defense_date IS NOT NULL
  AND status <> 'Titulado';

-- Registros históricos ainda em Trancado passam a Desligado. O valor bruto do
-- SEI continua preservado em sei_raw_status quando aplicável.
UPDATE public.dm_students
SET status = 'Desligado'
WHERE status = 'Trancado';

ALTER TABLE public.dm_students
  DROP CONSTRAINT IF EXISTS ck_dm_student_status;

ALTER TABLE public.dm_students
  DROP CONSTRAINT IF EXISTS ck_dm_student_defense_titulated;

ALTER TABLE public.dm_students
  ADD CONSTRAINT ck_dm_student_status
  CHECK (status IN ('Ativo','Titulado','Desligado'));

ALTER TABLE public.dm_students
  ADD CONSTRAINT ck_dm_student_defense_titulated
  CHECK (defense_date IS NULL OR status = 'Titulado');

-- Turma com alunos e sem nenhum aluno ativo permanece/torna-se Encerrada desde
-- que todos os vínculos estejam nos dois estados terminais.
UPDATE public.dm_cohorts AS cohort
SET status = 'Encerrada',
    updated_at = now()
WHERE EXISTS (
    SELECT 1 FROM public.dm_students AS student
    WHERE student.directorate_id = cohort.directorate_id
      AND student.cohort_id = cohort.id
)
AND NOT EXISTS (
    SELECT 1 FROM public.dm_students AS student
    WHERE student.directorate_id = cohort.directorate_id
      AND student.cohort_id = cohort.id
      AND student.status NOT IN ('Titulado','Desligado')
);

-- Se uma turma encerrada voltar a ter aluno Ativo, o ciclo retorna para
-- acompanhamento sem exigir correção manual do status da turma.
UPDATE public.dm_cohorts AS cohort
SET status = 'Em andamento',
    updated_at = now()
WHERE cohort.status = 'Encerrada'
AND EXISTS (
    SELECT 1 FROM public.dm_students AS student
    WHERE student.directorate_id = cohort.directorate_id
      AND student.cohort_id = cohort.id
      AND student.status = 'Ativo'
);

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 32, '032_dm_domain_simplification_v08290.sql', now())
ON CONFLICT (id) DO UPDATE
SET version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;
