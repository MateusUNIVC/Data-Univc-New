-- Data UNIVC v0.8.24.0
-- Formaliza a separacao do NPS academico:
--   01A = NPS da Instituicao (alunos)
--   01B = NPS do Curso
-- O antigo 01 sempre representou NPS do Curso e, portanto, migra somente para 01B.

INSERT INTO public.indicator_definitions
    (code, directorate_code, name, periodicity, formula_text, source_text, active)
VALUES
    ('DTNH-01A','DTNH','NPS da Instituicao - Alunos','Semestral / conforme aplicacao','% Promotores (9-10) - % Detratores (0-6)','Avaliacao Institucional SEI - pergunta sobre recomendar a UNIVC',true),
    ('DTNH-01B','DTNH','NPS do Curso','Semestral / conforme aplicacao','% Promotores (9-10) - % Detratores (0-6)','Avaliacao Institucional SEI - pergunta sobre recomendar o proprio curso',true),
    ('DCS-01A','DCS','NPS da Instituicao - Alunos','Semestral / conforme aplicacao','% Promotores (9-10) - % Detratores (0-6)','Avaliacao Institucional SEI - pergunta sobre recomendar a UNIVC',true),
    ('DCS-01B','DCS','NPS do Curso','Semestral / conforme aplicacao','% Promotores (9-10) - % Detratores (0-6)','Avaliacao Institucional SEI - pergunta sobre recomendar o proprio curso',true)
ON CONFLICT(code) DO UPDATE SET
    directorate_code = EXCLUDED.directorate_code,
    name = EXCLUDED.name,
    periodicity = EXCLUDED.periodicity,
    formula_text = EXCLUDED.formula_text,
    source_text = EXCLUDED.source_text,
    active = true;

INSERT INTO public.indicator_schedules
    (indicator_code, reference_grain, due_business_day, collection_window_start_business_day, active)
VALUES
    ('DTNH-01A','semester',5,1,true),
    ('DTNH-01B','semester',5,1,true),
    ('DCS-01A','semester',5,1,true),
    ('DCS-01B','semester',5,1,true)
ON CONFLICT(indicator_code) DO UPDATE SET
    reference_grain = 'semester',
    active = true;

-- Preserva eventual configuracao de prazo do antigo KPI 01 nas duas novas trilhas.
UPDATE public.indicator_schedules AS target
SET due_business_day = legacy.due_business_day,
    collection_window_start_business_day = legacy.collection_window_start_business_day
FROM public.indicator_schedules AS legacy
WHERE legacy.indicator_code = 'DTNH-01'
  AND target.indicator_code IN ('DTNH-01A','DTNH-01B');

UPDATE public.indicator_schedules AS target
SET due_business_day = legacy.due_business_day,
    collection_window_start_business_day = legacy.collection_window_start_business_day
FROM public.indicator_schedules AS legacy
WHERE legacy.indicator_code = 'DCS-01'
  AND target.indicator_code IN ('DCS-01A','DCS-01B');

-- Se algum ambiente experimental ja tiver uma meta 01B equivalente, preservamos
-- a nova e removemos apenas a duplicata antiga antes de renomear o restante.
DELETE FROM public.goals AS legacy
USING public.goals AS current
WHERE legacy.indicator_code = 'DTNH-01'
  AND current.indicator_code = 'DTNH-01B'
  AND legacy.directorate_id = current.directorate_id
  AND legacy.scope_label = current.scope_label
  AND legacy.valid_from = current.valid_from;

DELETE FROM public.goals AS legacy
USING public.goals AS current
WHERE legacy.indicator_code = 'DCS-01'
  AND current.indicator_code = 'DCS-01B'
  AND legacy.directorate_id = current.directorate_id
  AND legacy.scope_label = current.scope_label
  AND legacy.valid_from = current.valid_from;

UPDATE public.goals SET indicator_code = 'DTNH-01B' WHERE indicator_code = 'DTNH-01';
UPDATE public.goals SET indicator_code = 'DCS-01B' WHERE indicator_code = 'DCS-01';

-- Planos antigos de 01 tratavam o NPS do Curso; seguem o mesmo significado em 01B.
UPDATE public.action_plans SET indicator_code = 'DTNH-01B' WHERE indicator_code = 'DTNH-01';
UPDATE public.action_plans SET indicator_code = 'DCS-01B' WHERE indicator_code = 'DCS-01';

-- O codigo antigo permanece apenas para auditoria/historico e deixa de ser operacional.
UPDATE public.indicator_definitions SET active = false WHERE code IN ('DTNH-01','DCS-01');
UPDATE public.indicator_schedules SET active = false WHERE indicator_code IN ('DTNH-01','DCS-01');

INSERT INTO public.data_univc_schema_version (id, version, migration_name, applied_at)
VALUES (1, 30, '030_academic_nps_kpi_split_v08240.sql', now())
ON CONFLICT (id) DO UPDATE
SET version = EXCLUDED.version,
    migration_name = EXCLUDED.migration_name,
    applied_at = EXCLUDED.applied_at;
