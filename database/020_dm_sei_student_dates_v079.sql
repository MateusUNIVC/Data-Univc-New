-- Data UNIVC v0.7.9 - DM: datas individuais de curso consultadas no SEI.
-- Executar depois de 019_dadm_standardization_v078.sql.

ALTER TABLE dm_students
    ADD COLUMN IF NOT EXISTS course_completion_date date;

ALTER TABLE dm_students
    ADD COLUMN IF NOT EXISTS last_course_dates_sei_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_dm_student_dir_course_completion
    ON dm_students (directorate_id, course_completion_date);

CREATE INDEX IF NOT EXISTS ix_dm_student_dir_course_dates_sei
    ON dm_students (directorate_id, last_course_dates_sei_at);

-- As sincronizações SEI anteriores à v0.7.9 usavam a abertura da turma como
-- ingresso e marcavam esse valor como confirmado. A partir desta versão ele é
-- explicitamente provisório até a consulta individual localizar a data real.
UPDATE dm_students AS student
SET entry_date_estimated = TRUE
FROM dm_cohorts AS cohort
WHERE student.cohort_id = cohort.id
  AND student.source_system = 'SEI'
  AND student.entry_date = cohort.opening_date
  AND COALESCE(student.entry_date_estimated, FALSE) = FALSE;
