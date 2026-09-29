# DPE-14 — Auditoria final e bloqueio do legado (v0.13.0-dev.14)

## Objetivo

Fechar a reconstrução da DPE v0.13 removendo superfícies executáveis restantes do contrato DPE-01/02/03, formalizando verificações de release e garantindo que a experiência moderna tenha uma única fonte de verdade operacional.

## Removido do runtime

- `dpe_excel_parser.py` e o importador histórico DPE-01/02/03.
- `dpe_excel_builder.py` e o workbook gerencial histórico da DPE.
- `/api/dpe/import`.
- `/api/dpe/modelo/{indicator_code}`.
- `/api/dpe/demo` baseado em `management_indicator_measurements`.
- Seed genérico de medições antigas da DPE em `demo_seed.py`/`demo_data.py`.
- Validações, rolling metrics, alertas e fallbacks DPE-01/02/03 em `management_service.py`.
- Metadados DPE-01 no catálogo genérico `schemas.py` usado pelo bootstrap antigo.

## Bloqueio de superfícies genéricas

Para escopo DPE, as rotas genéricas abaixo retornam HTTP 410 e não podem recriar medições antigas:

- `/api/management/dashboard`
- `/api/management/measurements` e mutações relacionadas
- `/api/management/excel`

Continuam disponíveis no namespace genérico apenas `catalog`, `targets` e `actions`, pois são utilizados pela gestão moderna da DPE. O valor atual dos KPIs não é persistido nessas tabelas: ele é calculado diretamente pelo Cost Engine.

## Compatibilidade histórica deliberadamente preservada

Os nomes DPE-01/02/03 ainda existem somente em artefatos necessários para atualização/auditoria de instalações antigas:

- `management_catalog` para interpretar registros históricos existentes;
- `dpe_domain.py` e `schema_version.py` para migrar metas/planos antigos com segurança;
- migrations e documentação histórica.

Essas referências não aparecem no frontend ativo e não possuem caminho de criação de novas medições DPE.

## Release checks

Foi criado `scripts/run_release_checks.py`, que executa:

1. compilação de todos os módulos Python;
2. `node --check` em todos os JavaScripts da DPE;
3. suíte pytest completa;
4. verificação da ausência de `dpe_finance.js`, `dpe_excel_parser.py` e `dpe_excel_builder.py`;
5. verificação de que DPE-01/02/03 não reapareceram no frontend ativo.

## Smoke HTTP

Na base DEMO moderna:

- `/api/health/ready` → 200, schema 48 compatível;
- `/dpe` → 200;
- `/api/dpe/excel?referencia=2026-09` → 200;
- `/api/dpe/management/overview` → 200;
- `/api/dpe/import` → 404;
- `/api/dpe/modelo/DPE-01` → 404;
- `/api/management/dashboard` no escopo DPE → 410;
- `/api/management/measurements` no escopo DPE → 410.

## Resultado da regressão

152 testes aprovados. Schema permanece 48; nenhuma migration destrutiva foi criada nesta etapa.

## Limitação de release global

A DPE v0.13 está consolidada, porém o pacote ainda identifica sua base acadêmica como v0.11.6.5. Antes de promover o sistema inteiro para produção, deve ser feita a reconciliação previamente identificada com a árvore acadêmica v0.11.6.6 + patch v0.11.6.7 e uma regressão global posterior.
