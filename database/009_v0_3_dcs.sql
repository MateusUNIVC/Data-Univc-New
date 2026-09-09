-- v0.3.0 · Ativação DCS e catálogo inicial de cursos acadêmicos
-- A migration é aditiva: não exclui cursos nem dados históricos existentes.

update public.directorates
set active = true, name = 'Diretoria de Ciências da Saúde'
where code = 'DCS';

-- DEAD permanece fora do fluxo operacional nesta versão.
update public.directorates
set active = false
where code = 'DEAD';

-- Os três KPIs já existem no catálogo institucional (002_seed_indicators.sql).
-- Reativamos explicitamente o trio operacional da DCS.
update public.indicator_definitions
set active = true
where code in ('DCS-01','DCS-02','DCS-03');

update public.indicator_schedules
set active = true, reference_grain = 'month'
where indicator_code in ('DCS-01','DCS-02','DCS-03');

-- DTNH · catálogo acadêmico solicitado para a v0.3.0.
with d as (select id from public.directorates where code='DTNH')
insert into public.courses(directorate_id,name,modality,active,valid_from)
select d.id, x.name, 'Presencial', true, '2026-01'
from d cross join (values
 ('Administração'),
 ('Análise e Desenvolvimento de Sistemas'),
 ('Arquitetura e Urbanismo'),
 ('Agronomia'),
 ('Ciências Contábeis'),
 ('Direito'),
 ('Engenharia de Produção'),
 ('Engenharia Mecânica'),
 ('Comunicação Social - Publicidade e Propaganda')
) as x(name)
on conflict (directorate_id,name) do update
set modality='Presencial', active=true, valid_to=null;

-- O protótipo antigo usava 'Sistemas de Informação' como curso demonstrativo.
-- O histórico é preservado, mas o cadastro deixa de aparecer como curso ativo porque
-- a lista DTNH informada para a v0.3.0 usa Análise e Desenvolvimento de Sistemas.
update public.courses
set active = false, valid_to = coalesce(valid_to, '2025-12')
where directorate_id = (select id from public.directorates where code='DTNH')
  and lower(name) = lower('Sistemas de Informação');

-- DCS · catálogo acadêmico inicial.
with d as (select id from public.directorates where code='DCS')
insert into public.courses(directorate_id,name,modality,active,valid_from)
select d.id, x.name, 'Presencial', true, '2026-01'
from d cross join (values
 ('Odontologia'),
 ('Fisioterapia'),
 ('Enfermagem'),
 ('Educação Física'),
 ('Farmácia'),
 ('Medicina Veterinária')
) as x(name)
on conflict (directorate_id,name) do update
set modality='Presencial', active=true, valid_to=null;
