# DPE-07 — Tratamento econômico de Despesas

## Objetivo
Simplificar o lançamento de despesas sem enfraquecer o motor de distribuição. Cada despesa oficial passa a declarar explicitamente como entra no resultado.

## Tratamentos
- **Direta (`DIRECT`)**: 100% do valor pertence a um curso/contexto específico. O destino é gravado no lançamento e preservado no snapshot.
- **Compartilhada (`SHARED`)**: o valor deve ser distribuído entre cursos conforme regra configurada na área Distribuição.
- **Institucional (`INSTITUTIONAL`)**: participa somente do resultado institucional e não precisa nem pode ser rateada aos cursos.

## Migração
`047_dpe_expense_scope_v0130.sql` adiciona `expense_scope` a `dpe_cost_expenses`. Despesas históricas com regra DIRECT são classificadas como Diretas; demais registros históricos ficam Compartilhados até revisão explícita. Nenhum histórico é reescrito como Institucional por inferência.

## Compatibilidade
O motor de rateio continua utilizando as estruturas e snapshots existentes. Um consumidor antigo que configure regra DIRECT com exatamente um alvo é promovido de forma controlada para o novo tratamento Direto.

## Fechamento
A conciliação do rateio considera apenas Diretas + Compartilhadas. Institucionais permanecem no total de despesas e no resultado institucional, mas não criam pendência de distribuição. Um mês que possua apenas despesas institucionais não precisa de cálculo de rateio para fechar.

## Interface
O formulário pergunta primeiro “Como esta despesa entra no resultado?”. A listagem exibe o tratamento econômico, e a seleção em massa informa quando a competência está protegida ou quando não há linhas editáveis. Em massa é possível alternar entre Compartilhada e Institucional; Direta exige escolha individual do curso/contexto.

## Excel
O modelo de importação passa a aceitar a coluna `Tratamento`. `COMPARTILHADA` é o padrão. `INSTITUCIONAL` é aceito. Despesas `DIRETA` devem ser registradas pela tela nesta etapa porque o destino econômico é obrigatório.
