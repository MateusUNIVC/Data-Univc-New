# EXCEL-OFFICIAL-04B — DADM Parity Closure

Status: **implemented in parallel; production route remains unchanged until 04C**.

04B closes the three semantic items left open by 04A without weakening the privacy-preserving aggregate model.

## Dynamic management targets

The DADM adapter now exports both the raw V2 target registry and a protected pre-expanded effective-target table. The pre-expansion mirrors the live DADM V2 `_active_target()` rule exactly:

1. Department target, when a department is selected;
2. Channel target, when no department target applies and a channel is selected;
3. Institutional/TOTAL target as fallback.

Validity (`valid_from` / `valid_to`) is evaluated by reference month. For `(todos)`, the exported end month is the management reference month. KPI and matrix target formulas use exact matches against this pre-expanded table.

Unit conversion remains explicit:

- TME/TMA targets are stored in seconds by DADM V2 and displayed in minutes in Excel;
- rating remains 1–10;
- rating coverage is stored 0–100 and displayed as a 0–1 Excel percentage.

## Previous-period comparison

DADM V2 defines `previous_period` as the immediately preceding interval with the same number of days. 04B preserves that rule exactly by computing the comparison in the backend at export time.

The comparison is stored in `RESUMO ANTERIOR` and used by the executive KPI cards. It is snapshot evidence of the export context and deliberately does not change when offline filters are changed later.

This limitation is declared in `QUALIDADE E GOVERNANÇA`; the workbook never substitutes a simpler “previous month” approximation.

## Median and P90

TME/TMA median and P90 remain backend-calculated statistics. Percentiles are not additive, so they cannot be recomputed correctly from the monthly aggregate cube.

04B surfaces them explicitly in `PERCENTIS BACKEND` for the exported context instead of creating fake interactive percentile metrics.

## Privacy

No customer-level data is added by 04B. The interactive cube remains aggregated and contains no protocol, customer reference, conversation text, phone, CPF/CNPJ or raw TALLOS payload.

## Cutover state

04B does not change `/api/dadm/excel` or the DADM frontend. Route unification, feature flag, production parity endpoint, smoke test and rollback belong to 04C.
