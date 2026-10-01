-- Data UNIVC v0.13.0 - DM SEI student refresh persistent queue
-- Persists only queue state/IDs. SEI credentials remain memory-only per request.

BEGIN;

CREATE TABLE IF NOT EXISTS public.dm_sei_student_refresh_runs (
    id bigserial PRIMARY KEY,
    directorate_id integer NOT NULL REFERENCES public.directorates(id),
    status varchar(30) NOT NULL DEFAULT 'PENDING',
    scope_type varchar(30) NOT NULL DEFAULT 'students',
    scope_json text NOT NULL DEFAULT '{}',
    total_items integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    last_batch_at timestamptz,
    requested_by varchar(255),
    CONSTRAINT ck_dm_sei_student_refresh_run_status
        CHECK (status IN ('PENDING','IN_PROGRESS','COMPLETED','COMPLETED_WITH_ERRORS','CANCELLED'))
);

CREATE INDEX IF NOT EXISTS ix_dm_sei_student_refresh_run_dir_created
    ON public.dm_sei_student_refresh_runs(directorate_id, created_at);
CREATE INDEX IF NOT EXISTS ix_dm_sei_student_refresh_run_status
    ON public.dm_sei_student_refresh_runs(status, created_at);

CREATE TABLE IF NOT EXISTS public.dm_sei_student_refresh_items (
    id bigserial PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES public.dm_sei_student_refresh_runs(id) ON DELETE CASCADE,
    student_id integer NOT NULL REFERENCES public.dm_students(id) ON DELETE CASCADE,
    status varchar(20) NOT NULL DEFAULT 'PENDING',
    attempts integer NOT NULL DEFAULT 0,
    last_error_type varchar(40),
    last_error text,
    last_attempt_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT uq_dm_sei_student_refresh_run_student UNIQUE (run_id, student_id),
    CONSTRAINT ck_dm_sei_student_refresh_item_status
        CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED'))
);

CREATE INDEX IF NOT EXISTS ix_dm_sei_student_refresh_item_run_status
    ON public.dm_sei_student_refresh_items(run_id, status, id);
CREATE INDEX IF NOT EXISTS ix_dm_sei_student_refresh_item_student
    ON public.dm_sei_student_refresh_items(student_id);

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 50, '050_dm_sei_student_refresh_queue_v0130.sql', now())
ON CONFLICT (id) DO UPDATE SET
    version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;

COMMIT;
