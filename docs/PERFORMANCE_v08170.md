# Data UNIVC v0.8.17.0 — Cleanup e Performance I

## Escopo

Esta fase preserva regras de negócio e concentra três mudanças mensuráveis:

1. remoção do frontend DADM/DPE antigo que já não era alcançado pelo shell acadêmico;
2. eliminação do N+1 na listagem de despesas/rateios DPE;
3. ingestão em lote de Resultados Acadêmicos, mantendo o importador histórico como fallback de segurança.

Não inclui ainda Avaliação Docente server-side nem bounded dashboards; esses são os próximos blocos.

## Metodologia

Os números abaixo são de um benchmark sintético em SQLite in-memory. Eles medem principalmente **complexidade e quantidade de statements SQL**. Não devem ser interpretados como latência esperada no Render/Supabase. PostgreSQL deve ser medido separadamente com a infraestrutura real e `EXPLAIN ANALYZE`.

O benchmark reproduzível está em `scripts/benchmark_scalability.py` no pacote SOURCE.

## Importação de Resultados Acadêmicos

| Linhas | Engine legado | Engine batch | Redução de statements |
|---:|---:|---:|---:|
| 100 | 605 | 10 | 98,35% |
| 1.000 | 6.005 | 16 | 99,73% |
| 10.000 | — | 82 | — |
| 50.000 | — | ~382 | — |
| 100.000 | — | ~757 | — |

No baseline anterior, o custo era aproximadamente `6 * linhas + constante`. No caminho novo, catálogo e alunos são resolvidos em lote, duplicidades são prefetchadas em chunks e os novos fatos usam `executemany`.

### Salvaguardas preservadas

- validação ocorre antes de qualquer criação de catálogo/aluno para linhas inválidas;
- duplicidades continuam respeitando `add` versus `update`;
- a identidade do resultado continua incluindo semestre, curso, disciplina, aluno e turma;
- em `IntegrityError` inesperado, a transação batch é revertida e o importador legado é utilizado como fallback;
- auditoria registra `engine=batch` no caminho novo.

## DPE — despesas e rateios

Cenário sintético: 100 despesas, cada uma com um rateio.

| Implementação | Statements SQL |
|---|---:|
| anterior (N+1) | 101 |
| atual (prefetch) | 2 |

A consulta atual faz:

1. uma consulta para as despesas;
2. uma consulta para todos os rateios do conjunto selecionado.

O JSON retornado permanece equivalente.

## Cleanup de frontend legado

- `static/js/app.js`: 3.099 → 2.617 linhas;
- `templates/index.html`: 647 → 454 linhas.

Foram removidas somente implementações antigas DADM/DPE do shell acadêmico. Os redirects canônicos para `/dadm` e `/dpe` permanecem, e as páginas especializadas não foram alteradas funcionalmente.

## Próximas medições

1. PostgreSQL/Supabase real: import de 1k/10k e latência de rede;
2. `EXPLAIN ANALYZE` dos endpoints DPE críticos;
3. Avaliação Docente: paginação/filtros/analytics server-side;
4. dashboard acadêmico/DADM/DPE: janela aplicada no SQL;
5. memória OpenPyXL para 10k/50k/100k/500k linhas.
