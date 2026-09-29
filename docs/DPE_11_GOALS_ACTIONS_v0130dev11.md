# DPE-11 — Metas e Planos de Ação · v0.13.0-dev.11

## Objetivo

Conectar Metas e Planos diretamente aos indicadores reais do Cost Engine, sem criar uma segunda base de medições gerenciais e sem permitir novos cadastros no contrato histórico DPE-01/DPE-02/DPE-03.

## Fonte de verdade

A avaliação usa exclusivamente fatos calculados no runtime moderno:

- ledger de receitas (`dpe_revenue_entries`);
- ledger de despesas (`dpe_cost_expenses`);
- atividades e custos docentes conciliados;
- cálculo oficial de distribuição;
- Analytics/Resultado consolidados do Cost Engine.

`management_indicator_targets` e `management_indicator_actions` continuam sendo usados somente para persistir objetivos e planos, não para duplicar os valores dos KPIs.

## Indicadores canônicos

- `DPE-RESULT`: resultado institucional, margem institucional, índice de cobertura, resultado/margem por curso;
- `DPE-REVENUE`: receita total, institucional, por curso e por aluno;
- `DPE-EXPENSE`: despesa total, institucional e custo por curso;
- `DPE-TEACHING`: custo docente e carga média por docente;
- `DPE-ALLOCATION`: despesa não distribuída e reconciliação do cálculo.

Métricas herdadas sem apuração equivalente segura continuam no catálogo somente para histórico, marcadas como `legacy_metric` e impedidas para novos cadastros.

## Avaliação automática

Para a competência selecionada, cada meta vigente recebe:

- valor atual;
- unidade;
- escopo (institucional ou curso);
- situação `Dentro da meta`, `Atenção`, `Fora da meta` ou `Sem apuração`.

Metas históricas deixam de contaminar o resumo atual.

## Planos de ação

Novos planos DPE exigem uma métrica canônica. Metas em Atenção ou Fora da meta oferecem a ação `Criar plano`, preenchendo indicador, métrica, competência, escopo e descrição inicial do desvio.

O status `Atrasado` é derivado automaticamente quando o prazo vence e o plano ainda não foi concluído/cancelado.

## Segurança de domínio

O backend bloqueia:

- novas metas/planos em DPE-01/DPE-02/DPE-03;
- novas metas/planos em métricas históricas/informativas;
- dimensões incompatíveis com a métrica;
- plano DPE sem métrica definida.

## DEMO

A demonstração inclui seis metas canônicas e um plano de ação para exercitar estados Dentro da meta, Atenção e Fora da meta.

## Schema

Nenhuma alteração estrutural de banco. Schema permanece 48 (`048_dpe_teacher_profiles_v0130.sql`).
