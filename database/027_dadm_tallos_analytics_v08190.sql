-- Data UNIVC v0.8.19.0
-- DADM / TALLOS Analytics Center
-- Fatos operacionais idempotentes, mapeamento governado de departamentos e
-- rastreabilidade de sincronizações. O navegador consome apenas agregados.

CREATE TABLE IF NOT EXISTS public.dadm_tallos_sync_runs (
    id serial PRIMARY KEY,
    directorate_id integer NOT NULL REFERENCES public.directorates(id),
    start_date date NOT NULL,
    end_date date NOT NULL,
    trigger varchar(30) NOT NULL DEFAULT 'manual',
    status varchar(30) NOT NULL DEFAULT 'queued',
    total_expected integer,
    pages_processed integer NOT NULL DEFAULT 0,
    records_received integer NOT NULL DEFAULT 0,
    records_inserted integer NOT NULL DEFAULT 0,
    records_updated integer NOT NULL DEFAULT 0,
    records_unchanged integer NOT NULL DEFAULT 0,
    records_failed integer NOT NULL DEFAULT 0,
    error_message text,
    requested_by varchar(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_sync_dir_created
    ON public.dadm_tallos_sync_runs(directorate_id, created_at);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_sync_dir_status
    ON public.dadm_tallos_sync_runs(directorate_id, status);

CREATE TABLE IF NOT EXISTS public.dadm_tallos_department_map (
    id serial PRIMARY KEY,
    directorate_id integer NOT NULL REFERENCES public.directorates(id),
    source_key varchar(240) NOT NULL,
    display_name varchar(240) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    notes text,
    inserted_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by varchar(255),
    CONSTRAINT uq_dadm_tallos_department_source UNIQUE (directorate_id, source_key)
);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_department_active
    ON public.dadm_tallos_department_map(directorate_id, active);

CREATE TABLE IF NOT EXISTS public.dadm_tallos_attendances (
    id serial PRIMARY KEY,
    directorate_id integer NOT NULL REFERENCES public.directorates(id),
    source_id varchar(160) NOT NULL,
    protocol varchar(160),
    customer_ref varchar(160),
    employee_id varchar(160),
    employee_name varchar(220),
    department_key varchar(240),
    department_name varchar(240),
    channel varchar(160),
    tabulation varchar(240),
    status varchar(30) NOT NULL DEFAULT 'unknown',
    rating integer,
    tme_seconds double precision,
    tma_seconds double precision,
    tmro_seconds double precision,
    tmrc_seconds double precision,
    messages_sent integer NOT NULL DEFAULT 0,
    messages_received integer NOT NULL DEFAULT 0,
    initiated_by varchar(100),
    transferred boolean NOT NULL DEFAULT false,
    redistribution_count integer NOT NULL DEFAULT 0,
    valid_business_period boolean,
    sessions_opened integer,
    opened_at timestamptz,
    started_at timestamptz,
    finished_at timestamptz,
    closed_at timestamptz,
    created_at_source timestamptz,
    reference_at timestamptz NOT NULL,
    reference_date date NOT NULL,
    month_key varchar(7) NOT NULL,
    source_hash varchar(64) NOT NULL,
    source_payload_json text NOT NULL DEFAULT '{}',
    last_sync_run_id integer REFERENCES public.dadm_tallos_sync_runs(id),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    inserted_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_dadm_tallos_attendance_source UNIQUE (directorate_id, source_id),
    CONSTRAINT ck_dadm_tallos_rating CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)
);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_date
    ON public.dadm_tallos_attendances(directorate_id, reference_date);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_month
    ON public.dadm_tallos_attendances(directorate_id, month_key);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_employee_date
    ON public.dadm_tallos_attendances(directorate_id, employee_id, reference_date);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_department_date
    ON public.dadm_tallos_attendances(directorate_id, department_key, reference_date);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_channel_date
    ON public.dadm_tallos_attendances(directorate_id, channel, reference_date);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_status_date
    ON public.dadm_tallos_attendances(directorate_id, status, reference_date);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_dir_protocol
    ON public.dadm_tallos_attendances(directorate_id, protocol);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_rating
    ON public.dadm_tallos_attendances(rating);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_tabulation
    ON public.dadm_tallos_attendances(tabulation);
CREATE INDEX IF NOT EXISTS ix_dadm_tallos_attendance_last_sync
    ON public.dadm_tallos_attendances(last_sync_run_id);

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 27, '027_dadm_tallos_analytics_v08190.sql', now())
ON CONFLICT (id) DO UPDATE
SET version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;
