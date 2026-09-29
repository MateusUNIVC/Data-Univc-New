# DPE-03 - Backend legacy retirement (v0.13.0-dev.3)

## Escopo

Esta etapa remove do runtime as duas gerações operacionais anteriores ao Cost Engine:

- DPE v0.4: Resultado Operacional, Execução Orçamentária e Caixa;
- Finance v0.7.7: receita mensal, receita por curso, despesas, alocações e snapshots de custo.

DPE-01/02/03 da camada `management_indicator_*` **não** foram removidos nesta etapa porque Metas e Planos ainda os utilizam temporariamente. Eles serão tratados na consolidação de domínio.

## Remoções de runtime

- APIs genéricas `/api/dpe/{resultado|orcamento|caixa}`;
- APIs `/api/dpe/finance/*`;
- `dpe_finance_repository.py`;
- `dpe_finance_analytics.py`;
- `dpe_analytics.py` v0.4;
- models ORM das tabelas aposentadas;
- imports/templates Excel v0.4;
- seed Finance v0.7.7;
- hooks de autorização exclusivos de `DPEExpenseAllocation`.

## Persistência

A migration `043_dpe_legacy_backend_retirement_v0130.sql` cria `dpe_legacy_retirement_archive`, arquiva cada linha das oito tabelas antigas em JSONB com indicação de origem e só então remove as tabelas operacionais.

No banco DEMO incluído, todas as oito tabelas possuíam zero registros antes da aposentadoria.

## Compatibilidade temporária

Continuam existentes:

- `/api/dpe/courses`;
- Cost Engine `/api/dpe/cost-engine/*`;
- `/api/dpe/excel*` e `/api/dpe/import` de DPE-01/02/03;
- Metas e Planos via `/api/management/*`.

Essas superfícies serão remodeladas nas próximas etapas, não no DPE-03.
