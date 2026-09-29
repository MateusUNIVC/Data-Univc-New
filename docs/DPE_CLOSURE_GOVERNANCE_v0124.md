# DPE Fechamento e Governança — v0.12.4

## Objetivo

A v0.12.4 transforma o fechamento mensal da DPE em uma etapa de governança operacional, e não apenas em uma troca de status. O mês só pode ser encerrado quando os dados críticos estão reconciliados e todos os alertas atuais foram explicitamente revisados.

A versão também amplia a rastreabilidade das operações financeiras usando o `audit_log` institucional já existente. Não foi criada uma segunda trilha de auditoria e nenhuma tabela nova foi necessária.

## Checklist operacional

A área **Fechamento** passa a consolidar, em uma única leitura, as condições necessárias para encerrar a competência:

- etapa/status da competência;
- ofertas econômicas incluídas;
- despesas oficiais;
- configuração das despesas para distribuição;
- alunos ativos;
- receita líquida;
- base do ticket médio;
- receitas estimadas;
- conciliação dos lançamentos de folha com docentes;
- existência e atualidade do Allocation Run oficial;
- reconciliação do rateio;
- resultado econômico calculável;
- lotes de entrada ainda em staging/READY;
- revisão dos alertas e anomalias atuais.

Cada item retorna `PASS`, `WARNING` ou `BLOCKER`, com contexto suficiente para a interface direcionar o usuário à área correta.

## Alertas precisam ser revisados

Alertas não são tratados como erros automaticamente. Um mês pode, por exemplo, possuir receita estimada ou um lote ainda não incorporado ao ledger oficial. Entretanto, a v0.12.4 não permite que esse fato seja ignorado silenciosamente.

Para cada `WARNING`, o sistema gera uma chave de revisão baseada no conteúdo atual do alerta. O gestor precisa registrar uma nota de revisão. Enquanto existir um alerta atual ainda não revisado, o item **Alertas e anomalias revisados** permanece `BLOCKER` e `can_close=false`.

Se o contexto do alerta mudar, a chave muda e a revisão anterior deixa de satisfazer o novo estado. Assim, uma revisão não funciona como autorização permanente para situações futuras diferentes.

A revisão registra:

- usuário/e-mail;
- data e hora;
- competência;
- código e contexto do alerta;
- nota informada pelo usuário.

## Conciliação docente no fechamento

O checklist passa a verificar diretamente os lançamentos ativos de folha (`PAYROLL`).

Quando houver folha:

- todos os lançamentos precisam estar ligados a um `period_teacher`;
- `teacher_match_status` precisa estar `CONFIRMED`.

Pendências aparecem como bloqueio específico de **Docentes reconciliados**, permitindo ao usuário seguir para a área de Docentes em vez de receber uma mensagem genérica de erro.

## Resultado econômico calculado

O fechamento também exige que o resultado econômico seja tecnicamente calculável. Para isso:

- deve existir Allocation Run oficial;
- o fingerprint do run precisa corresponder aos dados atuais;
- receitas precisam estar preenchidas;
- o rateio deve estar totalmente reconciliado.

Se qualquer uma dessas condições deixar de ser verdadeira, o resultado econômico deixa de ser considerado final e o fechamento é bloqueado.

## Voltar para conferência

Antes da v0.12.4, oficializar o rateio colocava a competência em `CALCULATED`, restringindo novas edições. Caso um erro fosse percebido antes do fechamento, não existia um fluxo administrativo claro para liberar correção.

A ação **Voltar para conferência** resolve esse caso.

Regras:

1. disponível apenas em `CALCULATED`;
2. exige justificativa com no mínimo 10 caracteres;
3. a versão oficial atual não é apagada;
4. ela passa para `SUPERSEDED`;
5. a competência retorna para `REVIEW`;
6. motivo, estado anterior e estado novo ficam registrados na auditoria.

Depois da correção, um novo cálculo precisa ser executado e oficializado normalmente.

## Fechamento

O fechamento continua exigindo competência em `CALCULATED`, mas agora usa o checklist ampliado.

Para fechar:

- nenhum item pode estar `BLOCKER`;
- alertas atuais precisam ter revisão registrada;
- o Allocation Run oficial precisa estar atual e reconciliado;
- o resultado econômico precisa estar calculável.

O fechamento registra no evento histórico e no `audit_log`:

- status anterior e novo;
- usuário;
- data/hora;
- Allocation Run utilizado;
- resumo do checklist;
- totais reconciliados;
- observação de fechamento, quando informada.

Uma competência `CLOSED` continua bloqueando alterações operacionais.

## Reabertura

A reabertura continua controlada e exige motivo objetivo.

Ao reabrir:

- a competência muda de `CLOSED` para `REVIEW`;
- `closed_at` e `closed_by` atuais são limpos da linha de estado;
- o evento de fechamento anterior permanece imutável;
- um novo evento `REOPENED` é criado;
- a auditoria preserva o fechamento anterior, motivo, usuário e transição.

Nenhum histórico é apagado.

## Auditoria ampliada

A v0.12.4 adiciona `dpe_audit.py`, uma camada comum sobre o `audit_log` já existente.

Operações críticas da DPE passam a registrar, quando aplicável:

- ação;
- entidade;
- identificador;
- competência;
- usuário/e-mail;
- data/hora;
- estado anterior (`before`);
- estado posterior (`after`);
- contexto adicional (`metadata`).

A trilha cobre, entre outras operações:

- abertura/alteração de competência e ofertas do mês;
- criação, edição e estorno de despesas;
- confirmação de importações e classificação em massa;
- receitas/economics individuais e em massa;
- atividades docentes e vínculos de folha;
- configuração de distribuição;
- criação/alteração/aplicação de políticas;
- cálculo e oficialização de Allocation Runs;
- cópia entre competências e geração recorrente;
- revisão de alertas;
- retorno para conferência;
- fechamento;
- reabertura.

## Trilhas na interface

A tela **Fechamento** possui uma nova tabela de auditoria da competência com:

- data/hora;
- operação;
- item/entidade;
- usuário;
- mudança ou contexto relevante.

Isso permite investigar o mês sem acessar banco ou código.

## API

### Fechamento e governança

- `GET /api/dpe/cost-engine/closure-central?period_id={id}`
- `POST /api/dpe/cost-engine/periods/{period_id}/close`
- `POST /api/dpe/cost-engine/periods/{period_id}/reopen`
- `POST /api/dpe/cost-engine/periods/{period_id}/return-to-review`
- `POST /api/dpe/cost-engine/periods/{period_id}/governance-reviews`
- `GET /api/dpe/cost-engine/periods/{period_id}/audit`

## Banco e migration

A v0.12.4 **não cria migration nova**.

O schema esperado permanece **42** e a última migration obrigatória continua sendo:

`database/042_dpe_productivity_v0123.sql`

A governança reutiliza estruturas existentes:

- `dpe_cost_periods`;
- `dpe_cost_period_events`;
- `dpe_cost_allocation_runs`;
- `audit_log`.

Isso evita duplicar a fonte de auditoria ou criar tabelas agregadas de governança.

## Arquivos principais

Backend:

- `dpe_audit.py`;
- `dpe_cost_closure.py`;
- `dpe_cost_v2.py`;
- `dpe_cost_catalog.py`;
- `dpe_cost_expenses.py`;
- `dpe_cost_economics.py`;
- `dpe_cost_teaching.py`;
- `dpe_cost_allocation.py`;
- `dpe_cost_productivity.py`;
- `dpe_router.py`.

Frontend:

- `templates/dpe.html`;
- `static/js/dpe_cost_closure.js`;
- `static/css/dpe.css`.

Testes:

- `tests/test_dpe_v0124.py`.

## Validação da release

A suíte acumulada possui **73 testes aprovados**.

A cobertura específica da v0.12.4 inclui:

- checklist com conciliação docente, resultado e governança;
- bloqueio do fechamento enquanto um alerta atual não for revisado;
- revisão de alerta registrada em auditoria;
- retorno de `CALCULATED` para `REVIEW` sem apagar o run anterior;
- fechamento bloqueando novas edições;
- reabertura preservando trilha histórica;
- alteração de despesa registrando valor anterior e novo.

Na validação integrada com o seed demonstrativo:

- a competência ficou `CALCULATED` com um alerta de staging;
- `can_close=false` antes da revisão;
- após revisão registrada, `can_close=true`;
- fechamento retornou `CLOSED`;
- auditoria expôs a sequência de revisão e fechamento;
- reabertura retornou a competência para `REVIEW` preservando o histórico.

## Compatibilidade

A v0.12.4 permanece concentrada na DPE. Não altera a lógica de DTNH, DCS, DADM, DM, Avaliação Docente ou Resultados Acadêmicos.

O pacote completo de homologação continua partindo da última árvore completa disponível durante o desenvolvimento (v0.11.6.5). Para uma árvore completa que já contenha v0.11.6.6/v0.11.6.7, utilizar o patch cumulativo DPE v0.12.4, que evita substituir os arquivos acadêmicos compartilhados alterados nesses patches.
