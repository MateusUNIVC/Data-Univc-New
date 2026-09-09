# DM Domain Simplification & Cohort Lifecycle — v0.8.29.0

## Objetivo

Simplificar o domínio acadêmico ativo da Diretoria de Mestrado antes das próximas etapas de UX e Excel V2.

## Status do aluno

O contrato ativo passa a aceitar somente:

- `Ativo`;
- `Titulado`;
- `Desligado`.

`Trancado/Trancada` é mantido apenas como alias de entrada para compatibilidade e normalizado para `Desligado`. Quando a origem é o SEI, o texto original continua armazenado em `sei_raw_status`.

## Defesa e titulação

`defense_date` é o marco suficiente para confirmar `Titulado`. O backend força esse estado em cadastro manual, importações e atualização SEI. `graduation_date` permanece no schema somente para compatibilidade histórica e trilha de diploma até a simplificação visual da etapa seguinte.

## Ciclo de vida da turma

A reconciliação é centralizada no repositório:

- turma com pelo menos um aluno e todos em `Titulado/Desligado` → `Encerrada`;
- turma `Encerrada` com qualquer aluno `Ativo` → `Em andamento`;
- turma sem alunos não é fechada automaticamente;
- `Planejada/Aberta` com alunos ativos mantém seu estado explícito; se todos se tornarem terminais, fecha.

A regra roda após cadastro, edição, movimentação entre turmas, importação em lote, exclusão, titulação, atualização individual de datas via SEI e sincronização de turmas/alunos pelo SEI.

## Migration 032

A migration:

1. preserva `Trancado` em `sei_raw_status` quando necessário;
2. converte registros com defesa para `Titulado`;
3. converte os demais `Trancado` para `Desligado`;
4. fortalece as constraints de status e defesa;
5. reconcilia o status das turmas existentes;
6. atualiza o ledger para schema 32.

## Compatibilidade temporária

`locked_students` permanece no payload analítico com valor zero para não quebrar consumidores legados antes do redesenho do Excel DM. Nenhum registro ativo passa a ser classificado como Trancado.
