-- Data UNIVC v0.5.1 - correcao de catalogo academico DTNH/DCS
--
-- Esta migration NAO preenche um catalogo vazio. Ela apenas corrige cadastros
-- ja existentes de versoes anteriores, preservando o teste de autocadastro via SEI.

-- DTNH: nome oficial do curso.
do $$
declare
  v_dtnh bigint;
  v_old bigint;
  v_new bigint;
begin
  select id into v_dtnh from public.directorates where code = 'DTNH';
  if v_dtnh is not null then
    select id into v_old from public.courses
      where directorate_id = v_dtnh and lower(name) = lower('Publicidade e Propaganda')
      limit 1;
    select id into v_new from public.courses
      where directorate_id = v_dtnh and lower(name) = lower('Comunicação Social - Publicidade e Propaganda')
      limit 1;

    if v_old is not null and v_new is null then
      update public.courses
      set name = 'Comunicação Social - Publicidade e Propaganda'
      where id = v_old;
    elsif v_old is not null and v_new is not null and v_old <> v_new then
      -- Nao apagamos o registro antigo para preservar eventuais referencias
      -- historicas. O nome oficial permanece ativo e o alias antigo e inativado.
      update public.courses
      set active = false, valid_to = coalesce(valid_to, '2026-08')
      where id = v_old;
      update public.courses
      set active = true, valid_to = null
      where id = v_new;
    end if;
  end if;
end $$;

-- DCS: carteira informada para a diretoria.
-- Nao ha INSERT nesta migration: se o catalogo estiver vazio, ele continua vazio
-- para que o fluxo SEI -> Data UNIVC seja testado com autocadastro real.
-- Se algum destes cursos ja existir, apenas garantimos que esteja ativo.
update public.courses
set active = true, valid_to = null
where directorate_id = (select id from public.directorates where code = 'DCS')
  and lower(name) in (
    lower('Educação Física'),
    lower('Enfermagem'),
    lower('Farmácia'),
    lower('Fisioterapia'),
    lower('Medicina Veterinária'),
    lower('Odontologia'),
    lower('Psicologia')
  );
