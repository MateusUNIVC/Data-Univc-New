# DPE Decision-Oriented Overview - v0.10.1

## Objetivo

Reduzir a carga cognitiva da Visao geral da DPE e fazer a primeira tela responder quatro perguntas antes de expor o processo interno:

1. Quanto entrou?
2. Quanto saiu?
3. Qual foi o resultado?
4. O que precisa ser resolvido agora?

## Hierarquia da tela

### 1. Resultado financeiro

A primeira faixa apresenta somente Receita liquida, Despesas do mes, Resultado do mes e Margem do mes. O resultado executivo usa o total de despesas oficiais do ledger mensal, e nao somente o custo ja distribuido aos cursos. Assim, despesas ainda pendentes de distribuicao nao tornam o resultado artificialmente melhor.

### 2. Contexto operacional

Alunos ativos, ticket medio, cobertura da distribuicao de custos e conciliacao da folha aparecem em uma faixa secundaria. Sao informacoes importantes, mas nao competem visualmente com o resultado financeiro.

### 3. Proximo passo e pendencias

O painel indica a proxima acao recomendada pelo estado atual do mes. Pendencias do checklist sao traduzidas para linguagem de negocio e recebem uma acao direta para Despesas, Cursos, Docentes, Distribuicao de custos ou Fechamento.

### 4. Resultado por curso

A tabela detalhada e a consolidacao por curso permanecem abaixo das decisoes principais. O custo por oferta continua dependendo da distribuicao oficial; o resultado geral do mes, por outro lado, considera todas as despesas oficiais.

### 5. Divulgacao progressiva

O fluxo de etapas e a barra de progresso continuam disponiveis em `Ver andamento do mes`, recolhidos por padrao. A interface cotidiana nao exige compreender a sequencia tecnica para interpretar o mes.

## Backend

O endpoint `/api/dpe/cost-engine/v2-overview` passa a expor tambem:

- `monthly_result`;
- `monthly_margin_percent`;
- `allocation_coverage_percent`;
- `pending_distribution_total`;
- pendencias com `title`, `section` e `action_label`.

Nenhuma nova fonte de verdade foi criada. Os dados continuam compostos a partir dos repositorios canonicos de despesas, economia, docencia, rateio e fechamento.

## Banco de dados

Sem migration nova. `SCHEMA_VERSION = 39`.
