-- Data UNIVC v0.8.16.0
-- Baseline formal de versão do schema.
-- Execute após todas as migrations anteriores, incluindo 025.

CREATE TABLE IF NOT EXISTS public.data_univc_schema_version (
    id smallint PRIMARY KEY CHECK (id = 1),
    version integer NOT NULL,
    migration_name varchar(255) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 26, '026_schema_version_baseline_v08160.sql', now())
ON CONFLICT (id) DO UPDATE
SET version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;
