-- Data UNIVC v0.8.13.0 - DM: titulação em lote e acompanhamento de diploma digital.
-- Executar depois de 024_dcs_educacao_fisica_habilitacoes_v088.sql.

ALTER TABLE public.dm_students ADD COLUMN IF NOT EXISTS graduation_date date;
ALTER TABLE public.dm_students ADD COLUMN IF NOT EXISTS diploma_status varchar(30);
ALTER TABLE public.dm_students ADD COLUMN IF NOT EXISTS graduation_updated_at timestamptz;
ALTER TABLE public.dm_students ADD COLUMN IF NOT EXISTS graduation_updated_by varchar(255);

CREATE INDEX IF NOT EXISTS ix_dm_student_dir_graduation ON public.dm_students(directorate_id, graduation_date);
CREATE INDEX IF NOT EXISTS ix_dm_student_dir_diploma ON public.dm_students(directorate_id, diploma_status);

CREATE TABLE IF NOT EXISTS public.dm_graduation_events (
  id bigserial primary key,
  directorate_id bigint not null references public.directorates(id) on delete cascade,
  student_id bigint not null references public.dm_students(id) on delete cascade,
  operation_id varchar(64) not null,
  operation_type varchar(30) not null default 'bulk',
  previous_status varchar(40),
  previous_defense_date date,
  previous_graduation_date date,
  previous_diploma_status varchar(30),
  new_status varchar(40) not null default 'Titulado',
  new_defense_date date,
  new_graduation_date date,
  new_diploma_status varchar(30),
  created_at timestamptz not null default now(),
  created_by varchar(255)
);
CREATE INDEX IF NOT EXISTS ix_dm_grad_event_dir_created ON public.dm_graduation_events(directorate_id, created_at);
CREATE INDEX IF NOT EXISTS ix_dm_grad_event_student_created ON public.dm_graduation_events(student_id, created_at);
CREATE INDEX IF NOT EXISTS ix_dm_grad_event_operation ON public.dm_graduation_events(operation_id);

