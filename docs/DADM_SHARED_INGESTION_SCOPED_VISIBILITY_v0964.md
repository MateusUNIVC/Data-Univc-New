# DADM Shared Ingestion & Scoped Visibility — v0.9.6.4

## Objetivo

Separar definitivamente **capacidade de ingestão** de **escopo de leitura** na Diretoria Administrativa.

## Usuários

### dadm@ivc.br

- DADM / EDIT;
- pode testar, salvar e substituir o token TALLOS quando o ambiente permite gestão local de token;
- pode iniciar sincronizações e gravar todos os setores retornados pela API;
- pode acompanhar o histórico compartilhado de sincronizações;
- visualiza somente:
  - Financeiro — `12c84`;
  - Secretaria Acadêmica — `A967b`;
  - Mestrado — `8155e`;
  - Negociação — `B623`;
  - Prouni / Nbolsa / Fies — `9bc56`;
  - Estágio — `80bc4`.

### rodrigo.ghirardelli@ivc.br

- DADM / EDIT;
- mesmas capacidades de ingestão;
- leitura integral da DADM.

## Base compartilhada

Os fatos TALLOS pertencem à DADM, não ao usuário que iniciou a sincronização. `requested_by` é somente trilha de auditoria.

Assim, uma carga iniciada por qualquer um dos dois usuários fica imediatamente disponível para o outro, respeitando apenas o escopo de leitura no momento da consulta.

## Enforcement

O filtro de departamentos é aplicado no backend/SQL em:

- TALLOS dashboard e endpoints focados;
- filtros disponíveis e intervalo de datas;
- DADM V2 context/overview/entity/experience;
- qualidade dos dados;
- relatório XLSX DADM V2;
- mapeamentos de departamentos;
- metas e planos de ação.

IDs/queries de departamentos fora do escopo retornam `403`. O relatório não resolve nomes de operadores em departamentos não autorizados.

## Gestão de token

Ambos os usuários DADM com `EDIT` podem testar e salvar/substituir o token quando `local_token_management_enabled()` está ativo.

A remoção completa do token e a limpeza global da base TALLOS continuam exigindo acesso completo da DADM.

## Schema

Sem migration nova. `SCHEMA_VERSION = 33` e `SCHEMA_MIGRATION = 033_identity_access_security_rebase.sql`.
