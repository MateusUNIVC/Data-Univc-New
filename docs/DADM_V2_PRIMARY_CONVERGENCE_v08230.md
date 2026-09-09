# DADM V2 Primary Convergence — v0.8.23.0

## Objetivo

Transformar a DADM V2 na superfície oficial do Data UNIVC sem perder as ferramentas necessárias do frontend anterior e sem misturar o contrato analítico TALLOS com o contrato gerencial legado.

## Rotas

- `/dadm`: DADM oficial, renderizando `dadm_v2.html`.
- `/dadm/v2`: redirect 307 para `/dadm`, preservando a query string.
- `/dadm/legacy`: frontend anterior temporário para importações e rotinas históricas ainda não aposentadas.
- `/api/dadm/v2/*`: permanece como versão explícita do contrato analítico/API.

## Shell compartilhado

A DADM V2 passa a consumir `DataUNIVC.routeForDirectorate()` e `DataUNIVC.sidebar.mount()`. A sidebar continua com a arquitetura visual própria da V2, mas o comportamento transversal é compartilhado: persistência de recolhimento em `data-univc-sidebar`, troca de diretoria e modo somente leitura.

## Tooltips

O posicionamento deixa de depender de `transform` após uma largura automática potencialmente comprimida. O tooltip é renderizado, medido (`offsetWidth`/`offsetHeight`) e então posicionado com coordenadas absolutas limitadas ao container. `DADMV2.tooltipPosition()` concentra a regra testável.

## Metas TALLOS V2

Métricas oficiais deste contrato:

- `tme_avg_seconds` — DADM-01 — menor é melhor;
- `tma_avg_seconds` — DADM-01 — menor é melhor;
- `rating_avg` — DADM-02 — maior é melhor, escala 1–10;
- `rating_coverage_pct` — DADM-02 — maior é melhor, escala 0–100%.

Metas aceitam recorte institucional, departamento ou canal. Planos de ação também podem usar operador. A vigência é mensal e versionada.

Os registros V2 reutilizam `management_indicator_targets` e `management_indicator_actions`, mas usam `dimension_key` no namespace `V2:*`. O `ManagementRepository` legado ignora e bloqueia alterações nesses registros. Portanto, não há conversão automática nem risco de o editor legado reinterpretar métricas TALLOS V2.

## Histórico temporal

A timeline continua representando apenas períodos reais devolvidos para a entidade. Não são criados meses artificiais anteriores ao histórico de um operador/departamento. O limite analítico do backend continua sendo 60 meses; a interface não impõe limite de três meses.

## Governança TALLOS

O mapeamento `source_key → display_name` de departamentos foi incorporado a Dados & Integração, preservando o identificador factual e alterando apenas a apresentação.

## Migração

Não há migration nova. `SCHEMA_VERSION = 29` permanece válido.
