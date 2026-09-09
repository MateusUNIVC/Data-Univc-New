-- Data UNIVC v0.8.20.2
-- TALLOS evaluation scale correction: level is 0-10, not 1-5.

ALTER TABLE public.dadm_tallos_attendances
    DROP CONSTRAINT IF EXISTS ck_dadm_tallos_rating;

ALTER TABLE public.dadm_tallos_attendances
    ADD CONSTRAINT ck_dadm_tallos_rating
    CHECK (rating IS NULL OR rating BETWEEN 0 AND 10);

-- Repair rows already collected by v0.8.19/v0.8.20. The sanitized audit JSON
-- preserved the original TALLOS `level`, even when the previous normalizer had
-- discarded scores 0 and 6-10 as NULL.
WITH parsed AS (
    SELECT
        id,
        CASE
            WHEN COALESCE(source_payload_json, '') <> ''
             AND (source_payload_json::jsonb ->> 'level') ~ '^[0-9]+([.]0+)?$'
            THEN ((source_payload_json::jsonb ->> 'level')::numeric)::integer
            ELSE NULL
        END AS parsed_rating
    FROM public.dadm_tallos_attendances
)
UPDATE public.dadm_tallos_attendances AS a
SET rating = p.parsed_rating,
    updated_at = now()
FROM parsed AS p
WHERE a.id = p.id
  AND p.parsed_rating BETWEEN 0 AND 10
  AND a.rating IS DISTINCT FROM p.parsed_rating;

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 28, '028_dadm_tallos_rating_scale_v08201.sql', now())
ON CONFLICT (id) DO UPDATE
SET version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;
