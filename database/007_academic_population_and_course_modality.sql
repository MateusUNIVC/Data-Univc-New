-- Data UNIVC v0.2.2 — população acadêmica automática para DADM
-- Execute uma vez no Supabase > SQL Editor depois da migration 005.
--
-- Objetivos:
-- 1) registrar a modalidade no cadastro do curso para que futuras diretorias
--    acadêmicas (especialmente DEAD) alimentem a DADM sem recadastro;
-- 2) manter a coluna active_students_start do DADM-01 como snapshot histórico,
--    porém seu valor passa a ser preenchido automaticamente pelo backend a partir
--    de Matrículas Ativas do mês imediatamente anterior.
--
-- A tabela dadm_active_students permanece por compatibilidade e para a base
-- demonstrativa temporária de modalidades que ainda não possuem diretoria
-- acadêmica operacional. O frontend deixa de permitir alimentação manual.

alter table public.courses
  add column if not exists modality varchar(30) not null default 'Presencial';

update public.courses
set modality = 'Presencial'
where modality is null or btrim(modality) = '';

-- Mantemos a validação simples e explícita. Se a instituição adotar uma quarta
-- modalidade no futuro, esta constraint deve ser revisada antes do cadastro.
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'ck_courses_modality'
      and conrelid = 'public.courses'::regclass
  ) then
    alter table public.courses
      add constraint ck_courses_modality
      check (modality in ('Presencial', 'EAD', 'Semipresencial'));
  end if;
end $$;

update public.indicator_definitions
set
  formula_text = '(Desligamentos no mês ÷ alunos ativos no fechamento do mês anterior) × 100',
  source_text = 'Desligamentos oficiais + Matrículas Ativas das diretorias acadêmicas (mês anterior)'
where code = 'DADM-01';

update public.indicator_definitions
set
  formula_text = 'Despesa dos centros de custo administrativos no mês ÷ população acadêmica ativa consolidada',
  source_text = 'Setor Financeiro + Matrículas Ativas das diretorias acadêmicas'
where code = 'DADM-09';

update public.indicator_definitions
set
  source_text = 'Setor Financeiro + mapa de áreas e salas + Matrículas Ativas das diretorias acadêmicas'
where code = 'DADM-10';
