# Data UNIVC v0.9.6.19 — DPE Fechamento Mensal e Auditoria

## Objetivo

A v0.9.6.19 transforma o encerramento de uma competência do DPE Cost Engine em um processo formal de governança. Calcular e oficializar um rateio não significa mais, por si só, que o mês está definitivamente encerrado. O fechamento é uma ação própria, condicionada a um checklist e registrada em uma trilha imutável.

## Estados do mês

O fluxo permanece baseado nos estados do Cost Engine:

1. `DRAFT` — preparação;
2. `REVIEW` — conferência;
3. `CALCULATED` — possui uma versão oficial de rateio apta ao fechamento;
4. `CLOSED` — competência encerrada e bloqueada para alteração.

Uma reabertura controlada move `CLOSED` para `REVIEW`. O fechamento anterior continua registrado e não é apagado.

## Checklist de fechamento

Antes de permitir o encerramento, o backend revalida os dados atuais da competência. O checklist possui três níveis:

- `PASS`: condição atendida;
- `WARNING`: informação que merece ciência, mas não impede o fechamento;
- `BLOCKER`: pendência que impede o encerramento.

São verificados:

- etapa atual da competência;
- existência de ofertas econômicas incluídas;
- existência de despesas oficiais ativas;
- prontidão de todas as despesas para rateio;
- alunos ativos em todas as ofertas incluídas;
- receita líquida em todas as ofertas incluídas;
- alunos pagantes quando há receita positiva, para sustentar o ticket médio;
- presença de receitas estimadas, exibida como alerta;
- existência de uma versão oficial do Motor de Rateio;
- atualidade do fingerprint da versão oficial;
- reconciliação integral entre despesas atuais e valores alocados;
- existência de lotes de importação ainda em staging/ready, exibida como alerta.

## Fechamento

Uma competência só pode ser fechada quando:

- está em `CALCULATED`;
- o checklist não possui bloqueadores;
- existe versão oficial atual;
- o valor alocado é igual ao total de despesas oficiais ativas;
- o valor não alocado é zero.

Ao fechar, o sistema:

- altera a competência para `CLOSED`;
- grava `closed_at` e `closed_by`;
- cria evento `CLOSED` em `dpe_cost_period_events`;
- preserva snapshot do checklist e referência à versão oficial utilizada;
- registra a ação também no log geral de auditoria.

## Reabertura controlada

Uma competência `CLOSED` pode ser reaberta por usuário com permissão de edição da DPE. A operação exige justificativa de no mínimo 10 caracteres.

A reabertura:

- cria evento `REOPENED` antes de modificar a competência;
- preserva o fechamento anterior e sua versão oficial;
- move a competência para `REVIEW`;
- limpa os campos de fechamento corrente;
- reabilita as superfícies editáveis da competência;
- exige novo ciclo de cálculo e oficialização antes de um novo fechamento.

Se qualquer dado de origem for alterado depois da reabertura, o fingerprint anterior deixa de representar os dados correntes e não pode sustentar um novo fechamento.

## Trilha de auditoria

A tabela `dpe_cost_period_events` funciona como ledger específico de governança mensal. Cada evento preserva:

- competência;
- tipo `CLOSED` ou `REOPENED`;
- status anterior e posterior;
- versão de rateio relacionada;
- motivo/observação;
- snapshot do checklist quando aplicável;
- metadata do evento;
- usuário e timestamp.

Os eventos são aditivos. Reabrir e fechar novamente gera novos eventos em vez de atualizar ou apagar os anteriores.

## Interface

A DPE ganha **Fechamento e auditoria**, contendo:

- seletor de competência;
- resumo do checklist;
- lista de verificações com PASS/WARNING/BLOCKER;
- identificação da versão oficial usada;
- indicação se o fingerprint continua atual;
- botão de fechar quando permitido;
- botão de reabrir quando a competência está fechada;
- histórico cronológico de fechamento e reabertura.

## Schema

A migration `039_dpe_month_close_audit_v09619.sql` cria `dpe_cost_period_events`, seus índices e políticas RLS e atualiza o schema esperado para `39`.

A alteração é aditiva e não remove ou reinterpreta tabelas das versões anteriores.
