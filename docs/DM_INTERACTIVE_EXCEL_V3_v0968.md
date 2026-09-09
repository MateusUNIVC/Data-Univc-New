# DM — Excel Interativo V3 — v0.9.6.8

## Objetivo

Transformar o Excel da Diretoria de Mestrado em uma segunda interface de consulta do Data UNIVC, preservando o Excel V2 como relatorio oficial do recorte atual.

## Endpoint

- `GET /api/dm/excel`: V2 preservado.
- `GET /api/dm/excel-interativo`: V3 beta.

Os parametros `area`, `turma_id` e `data_corte` apenas iniciam os controles internos do V3. As bases factuais autorizadas sao exportadas integralmente para permitir novos recortes dentro do Excel.

## Abas visiveis

1. `LEIA-ME`
2. `PARAMETROS`
3. `PAINEL`
4. `DM-01 EVOLUCAO`
5. `DM-02 DEFESAS`
6. `TURMAS`
7. `ALUNOS E DEFESAS`
8. `MATRIZ`
9. `METAS E PLANOS`
10. `INTEGRACAO SEI`
11. `QUALIDADE E GOVERNANCA`

## Bases tecnicas ocultas

`DADOS_TURMAS`, `DADOS_ALUNOS`, `DADOS_METAS`, `DADOS_SEI`, `META_EFETIVA`, `LISTAS` e `CALC`.

## Controles

O workbook define `P_DM_AREA`, `P_DM_COHORT`, `P_DM_COMP`, `P_DM_ASOF`, `P_DM_WINDOW`, `P_DM_STATUS`, `P_DM_MATRIX`, `P_DM_PERIOD` e `P_DM_WINDOW_N`.

O filtro de status e auxiliar e nao redefine os KPIs oficiais. DM-01 continua sendo numero absoluto de membros por turma; DM-02 continua usando somente ingresso individual confirmado e defesa registrada.

## Data de corte

A data de corte recalcula alertas de prazo, limita as defesas consideradas e seleciona a vigencia das metas. O arquivo declara explicitamente que isso nao constitui reconstrucao integral de status historico quando a base nao possui todos os eventos datados necessarios.

## Dominio e privacidade

A exportacao usa somente `Ativo`, `Titulado` e `Desligado`. Data de Titulacao e Situacao do Diploma nao sao reintroduzidas. Como a DM e operacional, `ALUNOS E DEFESAS` preserva a granularidade individual e herda o mesmo controle de acesso da rota DM.

## Banco

Nenhuma alteracao de schema.
