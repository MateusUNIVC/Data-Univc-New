-- Data UNIVC v0.7.8 — padronização definitiva da DADM
--
-- Não apaga dados históricos. As antigas estruturas DADM de evasão, custo por
-- aluno e infraestrutura permanecem fisicamente disponíveis para auditoria,
-- mas deixam de pertencer ao catálogo operacional da Diretoria Administrativa.

update public.indicator_definitions
set active = false
where code in ('DADM-09', 'DADM-10');

update public.indicator_schedules
set active = false
where indicator_code in ('DADM-09', 'DADM-10');

insert into public.indicator_definitions(
  code, directorate_code, name, periodicity, formula_text, source_text, active
) values
(
  'DADM-01', 'DADM', 'Tempo de Resposta nos Canais de Atendimento', 'Mensal',
  '% no prazo = solicitações atendidas no prazo ÷ solicitações recebidas × 100; reabertura = reabertas ÷ concluídas × 100',
  'Registros dos canais oficiais de atendimento', true
),
(
  'DADM-02', 'DADM', 'Satisfação com o Atendimento', 'Mensal',
  'Satisfação = respostas 4 e 5 ÷ respondentes × 100; insatisfação = respostas 1 e 2 ÷ respondentes × 100; taxa de resposta = respondentes ÷ atendimentos elegíveis × 100',
  'Pesquisa pós-atendimento padronizada', true
)
on conflict(code) do update set
  directorate_code = excluded.directorate_code,
  name = excluded.name,
  periodicity = excluded.periodicity,
  formula_text = excluded.formula_text,
  source_text = excluded.source_text,
  active = true;

insert into public.indicator_schedules(
  indicator_code, reference_grain, due_business_day,
  collection_window_start_business_day, active, notes
) values
('DADM-01', 'month', 5, 1, true, 'Fechamento mensal por canal; validação do diretor até o 7º dia útil.'),
('DADM-02', 'month', 5, 1, true, 'Fechamento mensal por canal; abaixo de 25% de taxa de resposta, interpretar a satisfação como indicativa.')
on conflict(indicator_code) do update set
  reference_grain = excluded.reference_grain,
  due_business_day = excluded.due_business_day,
  collection_window_start_business_day = excluded.collection_window_start_business_day,
  active = true,
  notes = excluded.notes;
