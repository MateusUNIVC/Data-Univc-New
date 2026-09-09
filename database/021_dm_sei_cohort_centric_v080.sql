-- Data UNIVC v0.8.0 - DM: fluxo SEI centrado em turmas.
-- Executar depois de 020_dm_sei_student_dates_v079.sql.
--
-- Regras desta versão:
-- 1) abertura da turma é metadado opcional;
-- 2) ingresso do aluno pode permanecer pendente até a consulta individual;
-- 3) dataConclusaoCurso do SEI representa a defesa aprovada e passa a alimentar
--    diretamente dm_students.defense_date;
-- 4) o campo paralelo course_completion_date deixa de existir no domínio.

ALTER TABLE public.dm_cohorts
    ALTER COLUMN opening_date DROP NOT NULL;

ALTER TABLE public.dm_students
    ALTER COLUMN entry_date DROP NOT NULL;

-- Valores que versões anteriores inferiram pela abertura da turma deixam de ser
-- tratados como datas reais. A ausência fica explícita até confirmação individual.
UPDATE public.dm_students
SET entry_date = NULL,
    entry_date_estimated = FALSE
WHERE COALESCE(entry_date_estimated, FALSE) = TRUE;

-- Compatibilidade com bancos que passaram pela v0.7.9. A coluna só é tocada se
-- existir; a data já coletada do SEI é promovida para a data oficial de defesa.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'dm_students'
          AND column_name = 'course_completion_date'
    ) THEN
        UPDATE public.dm_students
        SET defense_date = course_completion_date,
            status = 'Titulado',
            last_course_dates_sei_at = COALESCE(last_course_dates_sei_at, NOW())
        WHERE course_completion_date IS NOT NULL;

        DROP INDEX IF EXISTS public.ix_dm_student_dir_course_completion;

        ALTER TABLE public.dm_students
            DROP COLUMN course_completion_date;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_dm_student_dir_course_dates_sei
    ON public.dm_students (directorate_id, last_course_dates_sei_at);
