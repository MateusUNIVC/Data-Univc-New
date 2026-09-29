# DPE V2 Consolidado — v0.9.6.20

## Objetivo

Consolidar as entregas v0.9.6.13–v0.9.6.19 em uma única experiência operacional da Diretoria de Planejamento Econômico e Oferta. Esta release não cria uma nova fonte financeira: ela compõe as tabelas, snapshots e cálculos já canônicos do DPE Cost Engine.

## Painel executivo

A tela inicial da DPE passa a ser orientada à competência mensal e apresenta:

- receita líquida;
- custo oficialmente rateado;
- resultado econômico e margem;
- alunos ativos e ticket líquido;
- progresso do workflow;
- pendências do checklist;
- resultado detalhado por oferta;
- consolidação por produto acadêmico.

Valores de custo só aparecem quando existe uma execução de rateio reconciliada e atual. O painel não reutiliza o financeiro legado para preencher lacunas do Cost Engine.

## Workflow

O fluxo visual é composto pelas etapas:

1. Competência e ofertas;
2. Despesas oficiais;
3. Folha e docência;
4. Alunos e receita;
5. Rateio oficial;
6. Fechamento mensal.

A próxima ação é derivada do primeiro ponto ainda incompleto. Ao abrir uma etapa a partir do painel, a competência selecionada é propagada para a respectiva tela operacional sempre que a API daquela tela suporta seleção por competência.

## Legado

Receitas, despesas, resultado por curso, DPE-01/02/03 e Central de arquivos anteriores permanecem acessíveis para auditoria e transição, dentro do grupo recolhido **Histórico e legado**. Nenhuma tabela ou endpoint legado foi removido nesta release. As consultas pesadas do legado são inicializadas sob demanda ao abrir uma tela histórica, em vez de atrasarem a primeira renderização do painel V2.

## API

`GET /api/dpe/cost-engine/v2-overview?period_id=<id>`

O endpoint é somente leitura e agrega resumos dos repositórios de fechamento, economia e despesas, além de contagens leves de docência/folha. Ele não persiste cópias dos resultados. A área de Governança também passa a documentar o ciclo real do Cost Engine: staging, conciliação, rateio versionado, fechamento e reabertura auditada.

## Schema

Não há migration nova. A aplicação continua exigindo:

- `SCHEMA_VERSION = 39`;
- `039_dpe_month_close_audit_v09619.sql`.
