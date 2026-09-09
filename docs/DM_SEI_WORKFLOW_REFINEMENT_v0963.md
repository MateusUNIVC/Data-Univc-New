# v0.9.6.3 — DM SEI Workflow Refinement

## Objetivo

Simplificar a experiência de integração SEI da Diretoria de Mestrado sem alterar as regras acadêmicas consolidadas na linha 0.8.29–0.8.33.

## Tela principal

Foram removidos os blocos `Conteúdo disponível / O que o relatório do SEI fornece` e o aviso longo `Escolha o que entra no Data UNIVC`. A página mantém somente orientações operacionais, a auditoria de sincronizações e os comandos de acesso/upload.

## Prévia das turmas

A coluna `Data de abertura` passa a ter três estados:

1. turma nova sem data: `Opcional` e `Informar data`;
2. turma existente com data: data atual e `Alterar`;
3. edição ativa: campo `date` e `Cancelar`.

A abertura continua opcional. Uma turma nova pode ser sincronizada sem data.

## Proteção de dados existentes

O frontend só inclui a data no payload quando o controle da turma foi explicitamente aberto para edição. Para turmas já cadastradas, `atualizar_datas_existentes=true` só é enviado quando uma data existente realmente foi alterada.

O backend continua sendo a autoridade final e preserva a abertura existente quando `update_existing_opening_dates=False`.

## Preservações

- `DmCohort` e `DmStudent`: sem mudança de schema;
- ciclo automático de turma Encerrada/Em andamento: preservado;
- consulta individual de ingresso/defesa pelo SEI: preservada;
- DM Excel V2: preservado;
- autenticação 9.6.1 e NPS 9.6.2: preservados;
- ícones SEI e normalização de `++`: preservados da 8.31.

## Banco

`SCHEMA_VERSION = 33`. Não existe migration 034 nesta release.
