# EXCEL-OFFICIAL-04C — DADM Complete

Status de desenvolvimento: **COMPLETE**. Status de produção: **PENDING LIVE CUTOVER** até o gate de paridade retornar `READY` no VPS.

## Contrato de exportação

- rota canônica: `/api/dadm/excel`;
- Excel Official selecionado por `DADM_EXCEL_OFFICIAL_ENABLED=true`;
- default fail-closed: `false`;
- rollback imediato: `false` volta ao `dadm_v2` sem migration;
- filename oficial: `Excel_Oficial_DADM.xlsx`;
- observabilidade: `X-Data-UNIVC-Excel-Engine`;
- `/api/dadm/v2/report.xlsx` permanece apenas como alias de compatibilidade;
- o antigo workbook de gestão ficou em `/api/dadm/legacy/excel` e não compete pela rota canônica.

## Interface

A superfície DADM V2 usa exclusivamente `/api/dadm/excel`. Quando a flag oficial está ativa, os rótulos mudam para **Excel Oficial / Baixar Excel Oficial**. Não existe segunda opção de Excel na UI principal.

## Gate de produção

A Reitoria pode executar:

`GET /api/admin/excel-official/dadm/parity`

O endpoint usa os fatos Tallos autorizados e retorna `READY` somente quando a paridade semântica e as duas evidências de workbook passam. Fixtures/QA permanecem `CANDIDATE_PASS`.

## Smoke pós-cutover

`scripts/smoke_dadm_excel_cutover.py` valida:

- HTTP 200 e MIME XLSX;
- engine `excel_official`;
- seis abas institucionais;
- metadata `DADM`, app version e schema;
- ausência de links externos e VBA.

## Privacidade

O Excel Oficial mantém apenas o cubo agregado e evidências gerenciais. Atendimento individual, `customer_ref`, CPF/CNPJ, telefone e payload bruto não entram no workbook oficial.

## Banco

Nenhuma migration. `SCHEMA_VERSION = 53`.
