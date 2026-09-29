# DPE Offering Economics — v0.9.6.18

A v0.9.6.18 adiciona a base econômica oficial por **oferta + competência** ao novo DPE Cost Engine. O objetivo é separar definitivamente a realidade econômica de cada oferta (curso/modalidade/turno/local) de valores técnicos soltos usados apenas para rateio.

## Entidade mensal

A tabela `dpe_cost_offering_economics` mantém um registro por `period_offering_id` e pode armazenar:

- alunos ativos;
- alunos pagantes;
- receita bruta;
- bolsas e descontos;
- outras deduções;
- receita líquida;
- tipo da receita (`REALIZED` ou `ESTIMATED`);
- origem (`MANUAL`, `IMPORT`, `API`, `REQUEST` ou `SYSTEM`);
- referência da origem e observações.

O registro pertence à competência e à oferta histórica materializada. Alterações posteriores no catálogo mestre não reescrevem meses anteriores.

## Ticket médio

O ticket líquido é derivado por:

`receita líquida / alunos pagantes`

Também são derivados ticket bruto, receita líquida por aluno ativo, taxa de deduções, custo por aluno ativo, resultado econômico e margem quando houver uma versão de rateio reconciliada.

## Integração com o motor de rateio

A partir desta versão:

- `STUDENTS` usa **alunos ativos** da base econômica oficial;
- `REVENUE` usa **receita líquida** da base econômica oficial;
- `OFFERING_HOURS` continua usando carga derivada da docência ou uma carga explícita;
- valores técnicos de alunos/receita gravados pela v0.9.6.17 permanecem apenas como fallback legado até a oferta receber dados na base econômica nova.

O fingerprint de uma execução de rateio inclui os dados econômicos. Se alunos ou receita mudarem depois do cálculo, a versão anterior não pode ser oficializada até um novo cálculo ser executado.

## Interface

A DPE ganha a área **Receita, alunos e ticket**, com:

- seleção de competência;
- indicadores de cobertura;
- alunos ativos e pagantes;
- receita líquida e ticket;
- custo rateado, resultado e margem por oferta;
- consolidação por produto acadêmico, modalidade e turno;
- edição protegida por status da competência.

Uma competência `CALCULATED` ou `CLOSED` é somente leitura nesta superfície.

## Migration

Aplicar, após a migration 037:

`database/038_dpe_offering_economics_v09618.sql`

A release espera `SCHEMA_VERSION = 38`.
