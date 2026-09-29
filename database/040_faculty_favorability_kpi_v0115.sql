-- Data UNIVC v0.11.5 — consolidação do KPI 02 em favorabilidade categórica
--
-- O KPI 02 deixa de usar a projeção histórica em nota 0-10 e passa a usar
-- exclusivamente a favorabilidade derivada das categorias originais do SEI.
-- Metas antigas são preservadas para auditoria, porém marcadas como legadas
-- para que nunca sejam reinterpretadas silenciosamente como percentual.

alter table public.goals
  add column if not exists metric_version varchar(64);

update public.goals
set metric_version = 'legacy_score_0_10'
where indicator_code in ('DTNH-02', 'DCS-02')
  and coalesce(metric_version, '') = '';

update public.indicator_definitions
set
  name = 'Avaliação Docente pelo Aluno',
  periodicity = 'Semestral',
  formula_text = '% de respostas favoráveis entre as respostas classificadas das perguntas sobre o docente',
  source_text = 'Relatório Disciplina/Professor da Avaliação Institucional no SEI; perguntas contextuais e respostas não classificáveis ficam fora da síntese docente',
  active = true
where code in ('DTNH-02', 'DCS-02');

insert into public.data_univc_schema_version (id, version, migration_name, applied_at)
values (1, 40, '040_faculty_favorability_kpi_v0115.sql', now())
on conflict (id) do update set
  version = excluded.version,
  migration_name = excluded.migration_name,
  applied_at = excluded.applied_at;
