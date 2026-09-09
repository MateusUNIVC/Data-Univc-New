-- v0.1.6 - consolida Frequência Média como KPI mensal.
-- Não converte registros históricos semestrais automaticamente, pois não há
-- base metodológica para repartir um agregado semestral entre meses.

update public.indicator_definitions
set periodicity = 'Mensal'
where code in ('DTNH-03', 'DCS-03', 'DEAD-03');

update public.indicator_schedules
set reference_grain = 'month'
where indicator_code in ('DTNH-03', 'DCS-03', 'DEAD-03');
