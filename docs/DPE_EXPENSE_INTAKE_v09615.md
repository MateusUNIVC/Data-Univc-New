# DPE Expense Intake Center — v0.9.6.15

## Objetivo

Criar a camada operacional de entrada e classificação de despesas do novo DPE Cost Engine sem acoplar o domínio a um formato de origem ainda indefinido.

A despesa oficial passa a ser um objeto mensal próprio do Cost Engine. A base legada `dpe_expenses` continua disponível somente para compatibilidade durante a transição.

## Novas estruturas

### `dpe_cost_expenses`

Ledger oficial de despesas normalizadas. Cada lançamento pertence a `dpe_cost_periods` e contém:

- descrição e valor;
- data opcional, validada contra a competência;
- tipo `GENERAL` ou `PAYROLL`;
- beneficiário/fornecedor genérico;
- documento/referência;
- centro de custo opcional;
- categoria obrigatória;
- regra de rateio preparada;
- origem (`MANUAL`, `EXCEL`, `API`, `REQUEST`, `OTHER`);
- snapshot JSON da classificação;
- payload de origem opcional;
- trilha de criação, atualização e estorno.

Não existe exclusão física de uma despesa oficial. O cancelamento operacional é feito por `VOIDED`, com motivo, autor e data.

### Centros de custo

`dpe_cost_centers` passa a ter CRUD na DPE. Pode representar setores/áreas como Manutenção, Administrativo e Tecnologia, com hierarquia pai/filho. É opcional na despesa.

### Categorias

`dpe_expense_categories` passa a ter CRUD na DPE. É obrigatória no lançamento oficial e pode apontar para uma regra de rateio padrão.

A regra padrão é copiada para a despesa no momento do lançamento. Alterar a categoria no futuro não modifica o snapshot histórico já salvo.

### Staging neutro

Foram adicionadas:

- `dpe_cost_expense_import_batches`;
- `dpe_cost_expense_staging_rows`.

O lote identifica competência e origem. As linhas armazenam `raw_data_json` e `normalized_data_json` antes da criação de qualquer despesa oficial.

Nesta release **não existe commit automático das linhas de staging**. O adaptador definitivo será criado quando a fonte real dos dados for definida.

## Regras históricas

- somente competências `DRAFT` e `REVIEW` aceitam alterações;
- data informada deve pertencer à competência;
- categorias/setores podem ser renomeados no catálogo mestre sem alterar o snapshot de despesas antigas;
- despesas estornadas permanecem no banco para auditoria;
- nenhum rateio para ofertas/cursos é executado nesta etapa.

## Interface

A DPE passa a exibir `Central de despesas` dentro do bloco Cost Engine, com:

- filtros por competência, tipo, origem, categoria, centro e busca textual;
- cards de valor/volume do mês;
- ledger de despesas oficiais;
- cadastros de centro de custo e categoria;
- criação de lote neutro de preparação.

A antiga tela `Despesas e folha` permanece identificada como base financeira legada.

## Deploy

Aplicar `database/035_dpe_expense_intake_v09615.sql` antes de publicar o código. O runtime espera `SCHEMA_VERSION = 35`.
