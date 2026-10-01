-- Data UNIVC v0.13.0 - DM SEI refresh queue controls
-- Adds a persistent PAUSED state for queue UX. No credentials are stored.

BEGIN;

ALTER TABLE public.dm_sei_student_refresh_runs
    DROP CONSTRAINT IF EXISTS ck_dm_sei_student_refresh_run_status;

ALTER TABLE public.dm_sei_student_refresh_runs
    ADD CONSTRAINT ck_dm_sei_student_refresh_run_status
    CHECK (status IN ('PENDING','IN_PROGRESS','PAUSED','COMPLETED','COMPLETED_WITH_ERRORS','CANCELLED'));

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 51, '051_dm_sei_refresh_queue_controls_v0130.sql', now())
ON CONFLICT (id) DO UPDATE SET
    version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;

COMMIT;
