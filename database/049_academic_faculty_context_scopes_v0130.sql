-- Data UNIVC v0.13.0 - Avaliacao Docente com turmas compartilhadas
-- Um unico contexto/resposta pode pertencer a mais de um curso sem duplicar respostas.

BEGIN;

CREATE TABLE IF NOT EXISTS public.faculty_evaluation_context_scopes (
    id bigserial PRIMARY KEY,
    context_id integer NOT NULL REFERENCES public.faculty_evaluation_contexts(id) ON DELETE CASCADE,
    teaching_assignment_id integer NOT NULL REFERENCES public.teaching_assignments(id) ON DELETE CASCADE,
    is_primary boolean NOT NULL DEFAULT false,
    resolution_source varchar(40) NOT NULL DEFAULT 'catalog',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by varchar(255),
    CONSTRAINT uq_faculty_context_scope_assignment UNIQUE (context_id, teaching_assignment_id)
);

CREATE INDEX IF NOT EXISTS ix_faculty_context_scope_context
    ON public.faculty_evaluation_context_scopes(context_id);
CREATE INDEX IF NOT EXISTS ix_faculty_context_scope_assignment
    ON public.faculty_evaluation_context_scopes(teaching_assignment_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_faculty_context_scope_primary
    ON public.faculty_evaluation_context_scopes(context_id)
    WHERE is_primary;

-- Todos os contextos historicos passam a ter explicitamente seu vinculo atual
-- como escopo primario. Nenhuma resposta e copiada ou recalculada.
INSERT INTO public.faculty_evaluation_context_scopes (
    context_id, teaching_assignment_id, is_primary, resolution_source, created_by
)
SELECT
    c.id, c.teaching_assignment_id, true, 'legacy_primary', 'migration:049'
FROM public.faculty_evaluation_contexts c
ON CONFLICT (context_id, teaching_assignment_id) DO NOTHING;

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 49, '049_academic_faculty_context_scopes_v0130.sql', now())
ON CONFLICT (id) DO UPDATE SET
    version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;

COMMIT;
