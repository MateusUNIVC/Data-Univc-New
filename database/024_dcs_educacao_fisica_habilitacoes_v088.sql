-- Data UNIVC v0.8.8
-- DCS: Educação Física - Bacharelado e Educação Física - Licenciatura
--
-- Premissa validada para esta migração: o histórico que nas versões anteriores
-- estava cadastrado como "Educação Física" pertence ao Bacharelado. Por isso o
-- registro legado é renomeado preservando o mesmo course_id e todas as FKs.

DO $$
DECLARE
    v_dcs bigint;
    v_legacy bigint;
    v_bach bigint;
    v_lic bigint;
    v_valid_from varchar(7);
BEGIN
    SELECT id INTO v_dcs FROM public.directorates WHERE code = 'DCS';
    IF v_dcs IS NULL THEN
        RETURN;
    END IF;

    SELECT id, valid_from INTO v_legacy, v_valid_from
      FROM public.courses
     WHERE directorate_id = v_dcs
       AND lower(name) = lower('Educação Física')
     LIMIT 1;

    SELECT id INTO v_bach
      FROM public.courses
     WHERE directorate_id = v_dcs
       AND lower(name) = lower('Educação Física - Bacharelado')
     LIMIT 1;

    IF v_legacy IS NOT NULL AND v_bach IS NOT NULL AND v_legacy <> v_bach THEN
        RAISE EXCEPTION
          'Migração v0.8.8 interrompida: existem simultaneamente Educação Física legado (id=%) e Bacharelado (id=%). Consolide os registros antes de aplicar a migration.',
          v_legacy, v_bach;
    END IF;

    IF v_legacy IS NOT NULL AND v_bach IS NULL THEN
        UPDATE public.courses
           SET name = 'Educação Física - Bacharelado',
               modality = 'Presencial',
               active = true,
               valid_to = NULL
         WHERE id = v_legacy;
        v_bach := v_legacy;
    END IF;

    IF v_bach IS NULL THEN
        INSERT INTO public.courses (directorate_id, name, modality, active, valid_from, valid_to)
        VALUES (v_dcs, 'Educação Física - Bacharelado', 'Presencial', true, COALESCE(v_valid_from, '2026-01'), NULL)
        RETURNING id INTO v_bach;
    ELSE
        UPDATE public.courses
           SET modality = 'Presencial', active = true, valid_to = NULL
         WHERE id = v_bach;
    END IF;

    SELECT id INTO v_lic
      FROM public.courses
     WHERE directorate_id = v_dcs
       AND lower(name) = lower('Educação Física - Licenciatura')
     LIMIT 1;

    IF v_lic IS NULL THEN
        INSERT INTO public.courses (directorate_id, name, modality, active, valid_from, valid_to)
        VALUES (v_dcs, 'Educação Física - Licenciatura', 'Presencial', true, '2026-01', NULL);
    ELSE
        UPDATE public.courses
           SET modality = 'Presencial', active = true, valid_to = NULL
         WHERE id = v_lic;
    END IF;
END $$;
