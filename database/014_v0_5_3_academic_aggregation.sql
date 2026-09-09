-- Data UNIVC v0.5.3
-- Índices de apoio para consolidação acadêmica e paginação de resultados.
-- Seguro para execução repetida em PostgreSQL/Supabase.

create index if not exists ix_academic_results_dir_period_course_disc
    on public.academic_results (directorate_id, period, course_id, discipline_id);

create index if not exists ix_academic_results_dir_period_status_reason
    on public.academic_results (directorate_id, period, approved, failure_reason);
