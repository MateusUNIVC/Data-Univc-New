\pset pager off
\timing on

\echo '=== TALLOS STORAGE AUDIT :: RELATION SIZE ==='
SELECT
    pg_size_pretty(pg_relation_size('public.dadm_tallos_attendances')) AS table_heap,
    pg_size_pretty(pg_indexes_size('public.dadm_tallos_attendances')) AS indexes,
    pg_size_pretty(
        GREATEST(
            0,
            pg_total_relation_size('public.dadm_tallos_attendances')
            - pg_relation_size('public.dadm_tallos_attendances')
            - pg_indexes_size('public.dadm_tallos_attendances')
        )
    ) AS toast_and_aux,
    pg_size_pretty(pg_total_relation_size('public.dadm_tallos_attendances')) AS total;

\echo '=== TALLOS STORAGE AUDIT :: ROW FOOTPRINT ==='
SELECT
    COUNT(*) AS attendances,
    pg_size_pretty(COALESCE(SUM(pg_column_size(a)), 0)::bigint) AS logical_row_bytes,
    ROUND(COALESCE(AVG(pg_column_size(a)), 0), 1) AS avg_row_bytes
FROM public.dadm_tallos_attendances AS a;

\echo '=== TALLOS STORAGE AUDIT :: LEGACY PAYLOAD RESIDUAL ==='
SELECT
    COUNT(*) FILTER (
        WHERE COALESCE(NULLIF(btrim(source_payload_json), ''), '{}') <> '{}'
    ) AS rows_with_payload,
    pg_size_pretty(
        COALESCE(
            SUM(octet_length(source_payload_json)) FILTER (
                WHERE COALESCE(NULLIF(btrim(source_payload_json), ''), '{}') <> '{}'
            ),
            0
        )::bigint
    ) AS residual_payload_bytes,
    ROUND(
        COALESCE(
            AVG(octet_length(source_payload_json)) FILTER (
                WHERE COALESCE(NULLIF(btrim(source_payload_json), ''), '{}') <> '{}'
            ),
            0
        ),
        1
    ) AS avg_residual_payload_bytes
FROM public.dadm_tallos_attendances;

\echo '=== TALLOS STORAGE AUDIT :: COMPACT CONTRACT HEALTH ==='
SELECT
    COUNT(*) AS attendances,
    COUNT(*) FILTER (WHERE rating_source_state IS NULL) AS missing_rating_state,
    COUNT(*) FILTER (WHERE normalization_version IS NULL) AS missing_normalization_version,
    COUNT(*) FILTER (WHERE source_hash IS NULL OR btrim(source_hash) = '') AS missing_source_hash,
    COUNT(*) FILTER (WHERE source_payload_json IS NULL OR btrim(source_payload_json) = '') AS blank_legacy_placeholder
FROM public.dadm_tallos_attendances;

\echo '=== TALLOS STORAGE AUDIT :: RATING SOURCE STATE ==='
SELECT
    COALESCE(rating_source_state, '<NULL>') AS rating_source_state,
    COUNT(*) AS rows
FROM public.dadm_tallos_attendances
GROUP BY COALESCE(rating_source_state, '<NULL>')
ORDER BY rows DESC, rating_source_state;

\echo '=== TALLOS STORAGE AUDIT :: NORMALIZATION VERSION ==='
SELECT
    COALESCE(normalization_version, -1) AS normalization_version,
    COUNT(*) AS rows
FROM public.dadm_tallos_attendances
GROUP BY COALESCE(normalization_version, -1)
ORDER BY normalization_version;

\echo '=== TALLOS STORAGE AUDIT :: VACUUM / DEAD TUPLES ==='
SELECT
    n_live_tup,
    n_dead_tup,
    CASE
        WHEN n_live_tup + n_dead_tup = 0 THEN 0
        ELSE ROUND((100.0 * n_dead_tup / (n_live_tup + n_dead_tup))::numeric, 2)
    END AS dead_tuple_pct,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND relname = 'dadm_tallos_attendances';

\echo '=== TALLOS STORAGE AUDIT :: SYNC COVERAGE ==='
SELECT
    MIN(reference_date) AS first_reference_date,
    MAX(reference_date) AS last_reference_date,
    COUNT(DISTINCT month_key) AS covered_months,
    COUNT(*) AS attendances
FROM public.dadm_tallos_attendances;
