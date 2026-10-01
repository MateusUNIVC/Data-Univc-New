-- Data UNIVC v0.13.0 - DADM/TALLOS raw payload retirement
-- Stage 2 of compact storage: the compact rating contract from migration 052
-- is already the source of truth. Remove bulky historical JSON payloads while
-- keeping the legacy column as a small '{}' compatibility placeholder.

BEGIN;

-- Safety gate: migration 052 must have populated the compact contract first.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.dadm_tallos_attendances
        WHERE rating_source_state IS NULL
           OR normalization_version IS NULL
    ) THEN
        RAISE EXCEPTION 'TALLOS compact contract is incomplete; apply/repair migration 052 before payload retirement.';
    END IF;
END $$;

-- Historical payload cleanup. This is intentionally idempotent.
UPDATE public.dadm_tallos_attendances
SET source_payload_json = '{}'
WHERE COALESCE(NULLIF(btrim(source_payload_json), ''), '{}') <> '{}';

-- Keep the legacy compatibility column tiny for new rows created by any code
-- path that relies on the database default.
ALTER TABLE public.dadm_tallos_attendances
    ALTER COLUMN source_payload_json SET DEFAULT '{}';

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 53, '053_dadm_tallos_payload_retirement_v0130.sql', now())
ON CONFLICT (id) DO UPDATE SET
    version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;

COMMIT;
