-- Data UNIVC v0.8.20.3
-- TALLOS evaluation contract after reconciliation with the official export.
-- Exported S/A means no evaluation; numeric evaluations observed are 1..10.
-- Until TALLOS documents a real score zero, API level=0 is treated as absence.


-- ============================================================
-- 1. Corrigir zeros ainda permitidos pela migration 028
-- ============================================================

UPDATE public.dadm_tallos_attendances
SET rating = NULL,
    updated_at = now()
WHERE rating = 0;


-- ============================================================
-- 2. Reconciliar valores armazenados com o payload sanitizado
--    Apenas 1..10 e considerado avaliacao valida.
-- ============================================================

WITH parsed AS (
    SELECT
        id,
        CASE
            WHEN COALESCE(source_payload_json, '') <> ''
             AND (source_payload_json::jsonb ->> 'level') ~ '^[0-9]+([.]0+)?$'
             AND ((source_payload_json::jsonb ->> 'level')::numeric)::integer BETWEEN 1 AND 10
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
  AND a.rating IS DISTINCT FROM p.parsed_rating;


-- ============================================================
-- 3. Agora que os dados foram saneados, trocar a constraint
-- ============================================================

ALTER TABLE public.dadm_tallos_attendances
    DROP CONSTRAINT IF EXISTS ck_dadm_tallos_rating;

ALTER TABLE public.dadm_tallos_attendances
    ADD CONSTRAINT ck_dadm_tallos_rating
    CHECK (rating IS NULL OR rating BETWEEN 1 AND 10);


-- ============================================================
-- 4. Registrar schema version
-- ============================================================

INSERT INTO public.data_univc_schema_version
    (id, version, migration_name, applied_at)
VALUES
    (1, 29, '029_dadm_tallos_rating_1_10_v08203.sql', now())
ON CONFLICT (id) DO UPDATE
SET version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;