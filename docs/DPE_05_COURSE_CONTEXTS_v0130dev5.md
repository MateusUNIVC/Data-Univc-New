# DPE-05 — Cursos e contextos opcionais

## Objetivo

Remover “Oferta presencial” como regra de negócio e tornar **Curso** a unidade primária da DPE. A modalidade deixa de restringir a elegibilidade do curso.

## Modelo adotado

O Cost Engine ainda precisa de uma chave interna estável para receitas, docência, rateio, economics e snapshots históricos. Por isso a tabela `dpe_academic_offerings` e `offering_id` são preservados como infraestrutura técnica. Eles deixam de representar uma obrigação do usuário.

Ao vincular um curso oficial à DPE, o sistema cria automaticamente um **contexto-base** interno (`<codigo>-BASE`). Esse contexto representa o curso inteiro e não aparece como um cadastro adicional na interface.

Se for necessário separar o curso, o usuário pode criar contextos adicionais, por exemplo:

- Administração · Noturno;
- Administração · Unidade X;
- Administração · EAD;
- Administração · Turma A.

Quando há um ou mais contextos adicionais válidos na competência, o contexto-base não é materializado naquele mês. Isso impede que o mesmo curso seja contado duas vezes.

## Modalidades

Cursos ativos de DTNH e DCS podem participar independentemente de modalidade. Presencial, EAD, semipresencial e híbrido são tratados como atributos, não como filtros de elegibilidade.

## Histórico

Os snapshots registram `is_default_context` e `context_kind`. Competências históricas continuam utilizando os snapshots já armazenados e não são reescritas pela nova regra.

## Compatibilidade técnica

Os nomes internos `offering`, `period_offering_id` e a tabela histórica são mantidos nesta etapa para evitar uma migration destrutiva e desnecessária em todas as FKs do Cost Engine. A experiência e o contrato de domínio passam a utilizar Curso/Contexto.
