# DPE Financial Analytics — v0.12.2

## Objetivo

A v0.12.2 transforma a Visão Geral da DPE em uma leitura gerencial do mês e do histórico, sem criar uma base analítica paralela. Os indicadores são derivados das mesmas competências, snapshots, receitas, despesas e Allocation Runs oficiais usados pelo fluxo operacional.

A implementação é **somente leitura**: abrir Analytics não cria lançamentos, não recalcula competências antigas e não altera Allocation Runs.

## Fonte de verdade

O backend analítico está em `dpe_cost_analytics.py`, exposto por:

`GET /api/dpe/cost-engine/analytics`

Parâmetros:

- `period_id`: competência selecionada;
- `window_months`: janela histórica de 1 a 36 meses (interface oferece 6, 12 e 24);
- `course_key`: curso usado no histórico individual.

As fontes canônicas são:

- `dpe_cost_periods`;
- `dpe_cost_period_offerings` e seus snapshots;
- `dpe_cost_offering_economics`;
- `dpe_cost_expenses` e seus snapshots de classificação;
- `dpe_cost_allocation_runs`;
- `dpe_cost_allocation_results`.

Não foi criada tabela agregada para Analytics.

## Regra de validade do rateio

Uma análise de custo por curso só é apresentada quando existe um Allocation Run:

1. `OFFICIAL`;
2. reconciliado, com total não alocado igual a zero;
3. cujo `input_fingerprint` ainda corresponde aos dados atuais da competência.

Se uma receita, despesa, destino, critério ou outra entrada relevante mudar depois da oficialização, os custos/resultados por curso deixam de ser exibidos como atuais até que o fluxo de distribuição seja recalculado e oficializado novamente.

A receita e o resultado institucional do livro mensal continuam disponíveis quando suas próprias fontes estiverem completas.

## KPIs

A Visão Geral apresenta, para a competência atual, comparação descritiva com o mês imediatamente anterior:

- Receita bruta;
- Receita líquida;
- Despesas;
- Resultado;
- Margem operacional;
- Ticket líquido;
- Alunos pagantes.

A comparação informa valor absoluto, percentual e direção (`UP`, `DOWN`, `FLAT`). A interface não classifica automaticamente uma alta ou queda como boa ou ruim.

### Fórmulas

**Receita líquida**

`receita bruta - bolsas/descontos - outras deduções`

quando os valores necessários estão presentes no economics oficial.

**Resultado operacional institucional**

`receita líquida - total de despesas ativas da competência`

**Margem operacional**

`resultado operacional / receita líquida`

**Ticket líquido**

`receita líquida / alunos pagantes`

**Resultado do curso**

`receita líquida do curso - custos atribuídos ao curso pelo Allocation Run oficial e atual`

**Custo por aluno**

`custos atribuídos ao curso / alunos ativos`

## Visualizações implementadas

### Evolução mensal

- Receita líquida × Despesas × Resultado;
- Margem operacional;
- janela de 6, 12 ou 24 meses na interface.

### Despesas

- Despesas por categoria;
- Despesas por setor de origem;
- Categoria atual × mês anterior.

Categoria e setor históricos são lidos dos snapshots gravados na própria despesa, evitando que uma renomeação futura reescreva a leitura de meses anteriores.

### Cursos

- Receita líquida por curso;
- Resultado por curso;
- Margem por curso;
- Ticket líquido por curso;
- Custo por aluno × Ticket;
- Composição do custo por curso;
- tabela econômica por curso;
- Receita × Custo × Resultado do curso ao longo do tempo.

A identidade histórica do curso prioriza `source_course_id` do catálogo oficial. Isso permite acompanhar o mesmo curso mesmo quando há múltiplas ofertas no mês.

## Composição de custos

A base atual permite classificar de forma segura:

- **Docentes**: despesas de `PAYROLL`;
- **Diretos**: despesas não docentes com critério `DIRECT`;
- **Compartilhados**: despesas não docentes distribuídas por outros critérios do Allocation Engine.

### Overhead administrativo

A v0.12.2 **não inventa overhead administrativo**.

O schema atual não possui uma classificação contábil explícita e confiável dizendo que uma categoria/centro de custo é overhead administrativo. Portanto, Analytics não tenta deduzir essa natureza pelo nome de setor, categoria ou descrição.

Enquanto essa classificação não existir explicitamente:

- `administrative_cost = null` nas leituras por curso e no waterfall;
- a interface apresenta a limitação ao usuário;
- o resultado institucional continua reconciliando todas as despesas do mês;
- custos não classificados por driver permanecem identificados como não classificados no waterfall.

Isso preserva a regra de não inventar números.

## Waterfall

A visualização explica, com os dados disponíveis:

1. Receita bruta;
2. Bolsas/descontos;
3. Outras deduções;
4. Receita líquida;
5. Custos docentes;
6. Custos diretos;
7. Custos compartilhados;
8. Custos ainda sem classificação de driver, quando houver;
9. Resultado.

O backend informa `reconciled=true` apenas quando a ponte entre receita líquida, custos e resultado fecha dentro da tolerância monetária.

## Estados incompletos

Analytics não converte ausência de dado em zero quando zero alteraria o significado econômico.

Exemplos:

- receita incompleta pode tornar resultado/margem indisponíveis;
- ausência de rateio oficial atual torna custos por curso indisponíveis;
- ausência de alunos pagantes torna ticket indisponível;
- ausência de alunos ativos torna custo por aluno indisponível.

A interface mostra notas explicando essas limitações.

## Frontend

Arquivos principais:

- `templates/dpe.html` — suíte Analytics dentro de Visão Geral;
- `static/js/dpe_cost_analytics.js` — carregamento e renderização;
- `static/css/dpe.css` — componentes e responsividade;
- `static/js/dpe.js` e `static/js/dpe_v2.js` — integração com competência/refresh global.

Os gráficos são SVGs locais e não adicionam dependência externa de biblioteca de gráficos.

## Banco e migration

A v0.12.2 não cria migration.

- Schema esperado: **41**;
- migration mais recente continua sendo `041_dpe_allocation_policies_v0121.sql` da v0.12.1.

Em um ambiente que ainda está na v0.12.0/schema 40, a migration 041 deve ser aplicada antes de executar v0.12.2.

## Testes e regressão

A suíte acumulada contém **61 testes aprovados**.

A v0.12.2 adiciona cobertura específica para:

- cards e comparação com mês anterior;
- categoria e setor por snapshot;
- categoria atual × mês anterior;
- resultado e composição de custos por curso;
- waterfall reconciliado sem overhead inventado;
- histórico do mesmo curso entre competências;
- ausência de Allocation Run oficial;
- rejeição de Allocation Run oficial cujo fingerprint ficou desatualizado.

Também foram validados:

- sintaxe Python (`py_compile`);
- sintaxe dos JavaScripts DPE (`node --check`);
- ausência de IDs HTML duplicados na página DPE;
- seed demonstrativo completo;
- endpoints de Overview, Analytics, Distribuição e Economics retornando HTTP 200 em modo local autorizado.

## Fora do escopo

Esta versão não implementa funcionalidades da v0.12.3:

- importação real de Excel para produtividade;
- copiar mês anterior;
- copiar quadro docente;
- recorrências operacionais adicionais;
- ações em massa além do que já existia.

Também não cria uma classificação contábil nova de overhead apenas para satisfazer visualmente um gráfico. Essa decisão deve ser modelada explicitamente em uma versão futura se a instituição definir a regra administrativa correspondente.
