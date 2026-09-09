-- Data UNIVC v0.7.0 — reconstrução dos indicadores DADM/DPE e ativação da DM
-- A migração preserva as tabelas e registros legados para auditoria/rollback.
-- Os novos painéis usam as estruturas management_indicator_* abaixo.

insert into public.directorates(code,name,active) values
('DADM','Diretoria Administrativa',true),
('DPE','Diretoria de Planejamento Econômico e Oferta',true),
('DM','Diretoria de Mestrado',true)
on conflict(code) do update set name=excluded.name,active=true;

-- Retira do catálogo ativo os KPIs antigos, sem apagar definição ou histórico.
update public.indicator_definitions
set active=false
where code in ('DADM-09','DADM-10','DPE-04','DPE-05');

insert into public.indicator_definitions(code,directorate_code,name,periodicity,formula_text,source_text,active) values
('DADM-01','DADM','Tempo de Resposta nos Canais de Atendimento','Mensal','% no prazo = solicitações atendidas no prazo ÷ solicitações recebidas × 100; reabertura = reabertas ÷ concluídas × 100','Registros dos canais oficiais de atendimento',true),
('DADM-02','DADM','Satisfação com o Atendimento','Mensal','Satisfação = respostas 4 e 5 ÷ respondentes × 100; taxa de resposta = respondentes ÷ atendimentos elegíveis × 100','Pesquisa pós-atendimento padronizada',true),
('DPE-01','DPE','Margem Líquida por Curso e Carga Horária Alocada','Mensal','Margem = (receita líquida − custo total) ÷ receita líquida × 100','Financeiro por centro de custo + horários da Secretaria + folha do RH',true),
('DPE-02','DPE','Índice de Cobertura entre Receita e Despesa','Mensal','Índice = receita líquida ÷ despesa total','Demonstrativo gerencial mensal do Financeiro por competência',true),
('DPE-03','DPE','Folha de Pagamento sobre a Receita','Mensal','% folha = folha completa ÷ receita líquida × 100','Folha consolidada do RH + receita líquida do Financeiro',true),
('DM-01','DM','Evolução do Número de Alunos do Programa','Semestral','Ativos no fim = ativos no início + ingressantes − titulados − desligados','Secretaria do programa, processo seletivo e registro de defesas',true),
('DM-02','DM','Tempo Médio até a Defesa','Semestral','Tempo médio = soma dos meses entre ingresso e defesa ÷ defesas','Registro de defesas e base de coortes da Secretaria do programa',true)
on conflict(code) do update set
  directorate_code=excluded.directorate_code,
  name=excluded.name,
  periodicity=excluded.periodicity,
  formula_text=excluded.formula_text,
  source_text=excluded.source_text,
  active=true;

insert into public.indicator_schedules(indicator_code,reference_grain,due_business_day,collection_window_start_business_day,active,notes) values
('DADM-01','month',5,1,true,'Validação do diretor até o 7º dia útil.'),
('DADM-02','month',5,1,true,'Validação do diretor até o 7º dia útil.'),
('DPE-01','month',5,1,true,'Competência contábil mensal.'),
('DPE-02','month',5,1,true,'Competência contábil mensal.'),
('DPE-03','month',5,1,true,'Competência mensal com provisões apropriadas.'),
('DM-01','semester',5,1,true,'Fechamento semestral conforme orientação institucional.'),
('DM-02','semester',5,1,true,'Fechamento semestral conforme orientação institucional.')
on conflict(indicator_code) do update set
  reference_grain=excluded.reference_grain,
  due_business_day=excluded.due_business_day,
  collection_window_start_business_day=excluded.collection_window_start_business_day,
  active=true,
  notes=excluded.notes;

create table if not exists public.management_indicator_measurements (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  indicator_code varchar(30) not null,
  period varchar(16) not null,
  dimension_key varchar(64) not null default 'TOTAL',
  dimension_label varchar(240) not null default 'TOTAL',
  dimensions_json text not null default '{}',
  values_json text not null default '{}',
  notes text,
  source_reference varchar(500),
  validated boolean not null default false,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  updated_at timestamptz not null default now(),
  unique(directorate_id,indicator_code,period,dimension_key)
);

create table if not exists public.management_indicator_targets (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  indicator_code varchar(30) not null,
  metric_key varchar(80) not null,
  dimension_key varchar(64) not null default 'TOTAL',
  dimension_label varchar(240) not null default 'TOTAL',
  valid_from varchar(16) not null,
  valid_to varchar(16),
  target double precision,
  attention double precision,
  target_min double precision,
  target_max double precision,
  attention_min double precision,
  attention_max double precision,
  justification text,
  inserted_at timestamptz not null default now(),
  inserted_by varchar(255),
  unique(directorate_id,indicator_code,metric_key,dimension_key,valid_from)
);

create table if not exists public.management_indicator_actions (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id),
  indicator_code varchar(30) not null,
  metric_key varchar(80),
  period varchar(16) not null,
  dimension_key varchar(64) not null default 'TOTAL',
  dimension_label varchar(240) not null default 'TOTAL',
  problem text not null,
  probable_cause text,
  corrective_action text not null,
  responsible varchar(180) not null,
  due_date date not null,
  status varchar(40) not null default 'Aberto',
  evidence text,
  created_at timestamptz not null default now(),
  created_by varchar(255),
  updated_at timestamptz not null default now()
);

create index if not exists ix_management_measurement_dir_indicator_period
  on public.management_indicator_measurements(directorate_id,indicator_code,period);
create index if not exists ix_management_measurement_dir_period
  on public.management_indicator_measurements(directorate_id,period);
create index if not exists ix_management_measurement_dimension
  on public.management_indicator_measurements(directorate_id,indicator_code,dimension_key);
create index if not exists ix_management_target_lookup
  on public.management_indicator_targets(directorate_id,indicator_code,metric_key,valid_from);
create index if not exists ix_management_action_dir_indicator_period
  on public.management_indicator_actions(directorate_id,indicator_code,period);
create index if not exists ix_management_action_due_status
  on public.management_indicator_actions(directorate_id,status,due_date);

alter table public.management_indicator_measurements enable row level security;
alter table public.management_indicator_targets enable row level security;
alter table public.management_indicator_actions enable row level security;

-- O backend FastAPI continua sendo o único responsável pelo acesso às tabelas
-- operacionais; por isso nenhuma policy anon/authenticated é criada aqui.
