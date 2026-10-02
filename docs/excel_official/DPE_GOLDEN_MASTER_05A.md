# EXCEL-OFFICIAL-05A — DPE Adapter + Golden Master + First Parity

Status: **implemented in parallel; `/api/dpe/excel` remains on the current modern DPE workbook**.

## Scope

05A connects the consolidated DPE Cost Engine to the shared Excel Official Core without changing the production route.

The official snapshot fixes the selected **competência**. Offline filters are limited to dimensions that remain mathematically valid inside that snapshot:

- Curso;
- Curso / contexto;
- Centro de custo.

Changing competência requires a new official export.

## Accounting boundaries preserved

The adapter keeps three semantic layers separate:

1. **Institutional** — total ledger revenue, total official expense, institutional result and margin.
2. **Course/context** — explicitly attributed course revenue and costs from the current official Allocation Run.
3. **Cost center** — official expenses and allocated values classified by cost center.

Institutional revenue/expense is not silently pushed into course margins. The Excel Official does not infer administrative overhead from textual labels.

## Main metrics

- Receita total;
- Despesa total;
- Resultado institucional;
- Margem institucional;
- Resultado do curso/contexto;
- Margem do curso/contexto;
- Receita e custo por aluno;
- Despesa por centro de custo;
- Custo oficial distribuído;
- Cobertura da distribuição.

## Exported evidence

The workbook preserves auditable protected datasets for:

- current financial summary;
- course/context economics;
- course consolidation;
- revenue ledger;
- official expense ledger;
- official allocation memory;
- teaching/payroll reconciliation summary;
- backend management targets;
- closure checklist;
- institutional trend.

## Matrix

`MATRIZ` is Course × Financial Component using numeric currency cells:

- Receita;
- Custo docente;
- Custo direto;
- Custo compartilhado;
- Resultado.

## First parity

The 05A QA fixture uses the existing DPE Cost Engine repository fixture with two periods, two courses, revenue entries, official expenses and an official allocation run.

Parity checks recompose ledgers and the official allocation run rather than trusting pre-aggregated workbook values.

QA result: **25 cases, 0 failures, CANDIDATE_PASS**.

## Deliberate closure items for 05B

05A does not yet claim production cutover readiness. The remaining DPE closure should address:

- dynamic management targets inside KPI/matrix surfaces (the backend target evidence is already exported);
- explicit previous-period behavior on the final KPI set;
- final treatment of teaching/productivity metrics and allocation-quality indicators;
- production-data parity before route replacement.

The existing `/api/dpe/excel` remains unchanged in 05A.
