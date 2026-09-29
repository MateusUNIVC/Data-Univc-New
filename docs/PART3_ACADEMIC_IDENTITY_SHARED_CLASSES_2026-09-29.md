# Parte 3 — Identidade acadêmica, turmas compartilhadas e NPS

Data: 29/09/2026

## Objetivos

Esta etapa trata três problemas relacionados à identidade acadêmica da origem:

1. simplificar a entrada de semestre da Avaliação Docente;
2. representar turmas que atendem dois ou mais cursos sem duplicar respostas;
3. resolver corretamente Educação Física no NPS, considerando a nomenclatura atual do SEI sem transformar o nome genérico em alias institucional global.

## Avaliação Docente — período

A interface deixa de exigir a digitação de `AAAA-SEMX`. O usuário informa **Ano letivo** e escolhe **1º semestre** ou **2º semestre**. O frontend continua enviando `AAAA-SEM1` ou `AAAA-SEM2`, preservando banco, APIs e histórico.

## Turmas compartilhadas

Foi adicionada a tabela `faculty_evaluation_context_scopes`.

- `faculty_evaluation_contexts.teaching_assignment_id` continua sendo o vínculo primário por compatibilidade;
- cada contexto pode possuir um ou mais escopos em cursos/ofertas diferentes;
- `faculty_response_aggregates` e respostas abertas continuam vinculados uma única vez ao contexto;
- a visão por curso inclui o contexto quando o curso está em seus escopos;
- a visão geral deduplica pelo agregado/contexto, evitando multiplicar participantes ou respostas.

A migration 049 faz backfill dos contextos já existentes, marcando o vínculo atual como `legacy_primary`.

## NPS e Educação Física

No SEI atual foi observado o seguinte contrato de origem:

- `Educação Física (Bac. Presencial)` → Bacharelado;
- `Educação Física` → Licenciatura.

Essa regra foi implementada **somente no adapter do SEI atual**. O catálogo institucional continua tratando `Educação Física` isolado como ambíguo.

Assim:

- importação direta do SEI resolve automaticamente a Licenciatura;
- upload manual/legado com nome genérico exige escolha explícita entre os candidatos permitidos;
- nenhuma regra global reinterpreta arquivos históricos silenciosamente.

## Schema

- Schema anterior: 48
- Schema novo: 49
- Migration: `database/049_academic_faculty_context_scopes_v0130.sql`

## Testes

A regressão completa desta etapa encerrou com **176 testes aprovados e 2 ignorados** antes do empacotamento final.
