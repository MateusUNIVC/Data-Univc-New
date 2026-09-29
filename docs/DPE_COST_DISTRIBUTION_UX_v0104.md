# DPE v0.10.4 — Distribuição de Custos Explicável

## Objetivo

Reduzir a carga cognitiva da antiga experiência de rateio sem alterar o motor financeiro. O usuário deve entender o efeito de cada escolha antes de salvar ou recalcular.

## Experiência principal

A área **Distribuição de custos** prioriza:

1. despesas que precisam de revisão;
2. critério atual em linguagem de negócio;
3. explicação simples do que acontece com o valor;
4. resultado distribuído por curso;
5. pendências acionáveis.

Bases técnicas e histórico de cálculos permanecem disponíveis em **Detalhes do cálculo**, recolhidos por padrão.

## Critérios apresentados ao usuário

- **Direto para um curso**: 100% do valor para uma oferta específica.
- **Pela carga horária do professor**: folha docente proporcional às aulas daquele professor no mês.
- **Pela carga horária dos cursos**: custos compartilhados proporcionais à carga acadêmica das ofertas.
- **Pelo número de alunos**: proporcional aos alunos ativos oficiais.
- **Pela receita dos cursos**: proporcional à receita líquida oficial.
- **Dividir igualmente**: parcelas iguais entre os cursos elegíveis.
- **Definir manualmente**: exceção em valor ou percentual.

Os códigos internos (`DIRECT`, `TEACHER_HOURS`, `OFFERING_HOURS`, `STUDENTS`, `REVENUE`, `EQUAL`, `MANUAL`) permanecem somente no backend.

## Prévia antes de salvar

Foi adicionada a rota read-only operacional:

`POST /api/dpe/cost-engine/expenses/{expense_id}/allocation-preview`

Ela recebe a configuração proposta e retorna:

- cursos de destino;
- base utilizada;
- numerador e denominador;
- percentual;
- valor atribuído;
- total distribuído;
- total ainda sem destino;
- pendências.

A prévia não persiste a configuração e reutiliza o mesmo algoritmo do cálculo oficial, inclusive a divisão exata de centavos.

## Sugestão e ajuste

A regra capturada no snapshot original da categoria é mostrada como **Sugestão da categoria**. Quando o usuário altera o critério, a listagem passa a sinalizar **Critério ajustado**.

## Rateio manual

O usuário escolhe explicitamente uma única forma:

- percentual; ou
- valor em reais.

A interface valida o fechamento em 100% ou no valor exato da despesa antes de permitir salvar.

## Prontidão antecipada

A Central de Distribuição passou a executar a mesma validação de cada despesa antes do recálculo. Assim, faltas de alunos, receita, conciliacão docente ou configuração aparecem como **Revisar** diretamente na lista.

## Memória do cálculo

Em **Ver composição**, cada custo atribuído a um curso pode ser rastreado até:

- despesa original;
- critério;
- base utilizada;
- percentual;
- valor atribuído.

## Banco e compatibilidade

- `SCHEMA_VERSION = 39`
- sem migration nova;
- nenhuma tabela financeira nova;
- nenhuma alteração destrutiva;
- cálculos e snapshots anteriores permanecem compatíveis.
