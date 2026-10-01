# Parte 21 — DADM/TALLOS · retirada definitiva do payload bruto

## Objetivo

Concluir TALLOS-COMPACT-03 e TALLOS-COMPACT-04 depois da fundação criada na Parte 20.

A aplicação já possui um contrato compacto para a avaliação (`rating`, `rating_source_state`, `rating_source_value` e `normalization_version`). Portanto o JSON operacional sanitizado que antes era mantido em `source_payload_json` deixa de ter utilidade analítica e passa a ser descartado após a normalização.

## Fluxo novo de ingestão

1. O relatório TALLOS chega ao normalizador em memória.
2. `_safe_payload()` monta somente a whitelist operacional necessária ao fingerprint da origem.
3. O `source_hash` SHA-256 é calculado usando essa whitelist e `TALLOS_NORMALIZATION_VERSION = 5`.
4. Os campos normalizados são produzidos.
5. O JSON usado para o fingerprint é descartado e **não é enviado ao repositório**.
6. `source_payload_json` permanece no schema apenas como coluna legada, com valor `{}`.

Isso mantém idempotência e detecção de alteração da fonte sem reter a cópia volumosa do atendimento.

## Migration 053

`053_dadm_tallos_payload_retirement_v0130.sql` executa uma trava de segurança para confirmar que o contrato compacto da migration 052 está preenchido e, somente então, substitui payloads históricos por `{}`.

A migration é idempotente. Ela não remove atendimentos, avaliações, operadores, departamentos, tempos, protocolos, hashes nem métricas.

## Equivalência

Os testes da Parte 21 verificam que:

- a auditoria de avaliações produz os mesmos resultados antes e depois de limpar o payload;
- uma nova ingestão persiste somente `{}` na coluna legada;
- reimportar o mesmo atendimento continua retornando `unchanged` pelo `source_hash`;
- mudanças na whitelist operacional continuam alterando o `source_hash`;
- o normalizador não contém mais `source_payload_json` no payload de persistência.

## Espaço físico PostgreSQL

A migration torna o espaço das páginas antigas reutilizável pelo PostgreSQL, mas o tamanho físico do arquivo pode não cair imediatamente por causa do MVCC.

Após validar a aplicação em produção, execute `VACUUM (ANALYZE)` para manutenção normal. Caso seja necessário devolver o espaço ao sistema operacional, planeje `VACUUM FULL public.dadm_tallos_attendances;` em janela de manutenção, pois ele requer lock exclusivo da tabela.

A medição/rotina operacional de armazenamento fica para TALLOS-COMPACT-05.
