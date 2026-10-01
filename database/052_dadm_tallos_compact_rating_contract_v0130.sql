-- Data UNIVC v0.13.0 - DADM/TALLOS compact rating contract
-- Stage 1 of compact storage: persist only the small raw rating contract needed
-- by analytics/audit while retaining source_payload_json for a later verified cleanup.

BEGIN;

ALTER TABLE public.dadm_tallos_attendances
    ADD COLUMN IF NOT EXISTS rating_source_state varchar(16),
    ADD COLUMN IF NOT EXISTS rating_source_value varchar(64),
    ADD COLUMN IF NOT EXISTS normalization_version integer;

WITH source_level AS (
    SELECT
        id,
        rating,
        NULLIF(
            btrim((COALESCE(NULLIF(btrim(source_payload_json), ''), '{}')::jsonb ->> 'level')),
            ''
        ) AS raw_level
    FROM public.dadm_tallos_attendances
), classified AS (
    SELECT
        id,
        raw_level,
        rating,
        CASE
            -- Some production history may already have had the bulky payload
            -- manually cleared. Preserve valid normalized ratings in that case.
            WHEN raw_level IS NULL AND rating BETWEEN 1 AND 10
                THEN 'valid'
            WHEN raw_level IS NULL
              OR lower(raw_level) IN ('s/a','sa','n/a','na','null','none','nan','-','--')
                THEN 'missing'
            WHEN replace(raw_level, ',', '.') ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
              AND trunc((replace(raw_level, ',', '.'))::numeric) = 0
                THEN 'zero'
            WHEN replace(raw_level, ',', '.') ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
              AND trunc((replace(raw_level, ',', '.'))::numeric) BETWEEN 1 AND 10
                THEN 'valid'
            ELSE 'invalid'
        END AS source_state
    FROM source_level
)
UPDATE public.dadm_tallos_attendances AS a
SET
    rating_source_state = c.source_state,
    rating_source_value = left(COALESCE(c.raw_level, CASE WHEN c.rating BETWEEN 1 AND 10 THEN c.rating::text END), 64),
    normalization_version = 5
FROM classified AS c
WHERE c.id = a.id;

UPDATE public.dadm_tallos_attendances
SET rating_source_state = COALESCE(rating_source_state, 'missing'),
    normalization_version = COALESCE(normalization_version, 5);

ALTER TABLE public.dadm_tallos_attendances
    ALTER COLUMN rating_source_state SET DEFAULT 'missing',
    ALTER COLUMN rating_source_state SET NOT NULL,
    ALTER COLUMN normalization_version SET DEFAULT 5,
    ALTER COLUMN normalization_version SET NOT NULL;

ALTER TABLE public.dadm_tallos_attendances
    DROP CONSTRAINT IF EXISTS ck_dadm_tallos_rating_source_state;

ALTER TABLE public.dadm_tallos_attendances
    ADD CONSTRAINT ck_dadm_tallos_rating_source_state
    CHECK (rating_source_state IN ('valid','zero','missing','invalid'));

CREATE INDEX IF NOT EXISTS ix_dadm_tallos_rating_source_state
    ON public.dadm_tallos_attendances(directorate_id, rating_source_state, reference_date);

CREATE INDEX IF NOT EXISTS ix_dadm_tallos_normalization_version
    ON public.dadm_tallos_attendances(normalization_version);

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 52, '052_dadm_tallos_compact_rating_contract_v0130.sql', now())
ON CONFLICT (id) DO UPDATE SET
    version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;

COMMIT;
