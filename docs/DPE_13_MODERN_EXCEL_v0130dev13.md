# DPE-13 — Excel analítico moderno

## Objetivo

Substituir a exportação financeira antiga baseada nos indicadores DPE-01/02/03 por um workbook ligado diretamente às mesmas fontes de verdade utilizadas pela DPE v0.13.

## Endpoint oficial

`GET /api/dpe/excel?period_id=<id>`

O parâmetro legado `referencia=AAAA-MM` permanece somente como alias de compatibilidade. A exportação individual `/api/dpe/excel/{indicator_code}` foi aposentada.

## Estrutura do workbook

1. **PAINEL** — KPIs e gráficos executivos.
2. **RESULTADO** — resultado por curso/contexto, calculado por fórmulas sobre as bases do próprio arquivo.
3. **CURSOS** — consolidação por curso.
4. **RECEITAS** — resumo por categoria e natureza.
5. **DESPESAS** — resumo por tratamento e categoria.
6. **DOCENCIA** — carga e custo conciliado por docente.
7. **RATEIOS** — resumo do run oficial e custo por contexto.
8. **METAS_PLANOS** — metas vigentes e planos de ação.
9. **QUALIDADE** — checklist de fechamento e limitações analíticas.
10. **BASE_CURSOS** — fatos auxiliares de curso/contexto.
11. **BASE_RECEITAS** — ledger de receitas.
12. **BASE_DESPESAS** — ledger oficial de despesas.
13. **BASE_DOCENCIA** — atividade docente por curso/contexto.
14. **BASE_RATEIOS** — memória do cálculo oficial por despesa × contexto.
15. **DICIONARIO** — descrição das abas.
16. **PARAMETROS** — contexto da exportação.

As cinco abas `BASE_*` são visíveis e usam Excel Tables com filtros. Não são abas técnicas escondidas.

## Regras de cálculo no arquivo

- Receita total = soma da `BASE_RECEITAS`.
- Despesa total = soma da `BASE_DESPESAS`.
- Resultado institucional = Receita total − Despesa total.
- Receita do contexto = `SUMIFS` sobre `BASE_RECEITAS` por Contexto ID.
- Custo do contexto = `SUMIFS` sobre `BASE_RATEIOS` por Contexto ID.
- Resultado do contexto = Receita − Custo.
- Resultado por curso = soma dos contextos do curso.
- Cobertura da distribuição = valor atribuído / despesas Diretas + Compartilhadas.

O Excel recebe fórmulas simples e legíveis; não utiliza funções de matriz dinâmica.

## Fontes de verdade

A exportação compõe diretamente:

- `DPERevenueRepository`;
- `DPECostExpenseRepository`;
- `DPECostTeachingRepository`;
- `DPECostAllocationRepository`;
- `DPECostAnalyticsRepository`;
- `DPEManagementRepository`;
- `DPECostClosureRepository`;
- `DPEV2OverviewRepository`.

Não existe uma segunda tabela de medições financeiras para alimentar o workbook moderno.

## Validação DEMO 2026-09

| Métrica | Excel | Aplicação |
|---|---:|---:|
| Receitas | R$ 2.778.568,00 | R$ 2.778.568,00 |
| Despesas | R$ 495.180,00 | R$ 495.180,00 |
| Custos distribuídos | R$ 467.580,00 | R$ 467.580,00 |
| Resultado institucional | R$ 2.283.388,00 | R$ 2.283.388,00 |

## Compatibilidade restante

Os modelos/importadores históricos DPE-01/02/03 ainda permanecem no código para dados históricos e serão avaliados na limpeza final. Eles não alimentam o novo Excel e não possuem mais endpoint de exportação individual.
