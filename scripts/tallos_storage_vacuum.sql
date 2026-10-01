\pset pager off
\timing on
\echo 'Running safe maintenance: VACUUM (ANALYZE) public.dadm_tallos_attendances'
VACUUM (ANALYZE, VERBOSE) public.dadm_tallos_attendances;
\echo 'VACUUM (ANALYZE) completed.'
