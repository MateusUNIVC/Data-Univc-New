# DM — Excel V2 — v0.8.33.0

## Objetivo

Substituir a exportação oficial legada da Diretoria de Mestrado por um relatório gerencial coerente com o modelo atual do Data UNIVC após a simplificação de domínio e a convergência visual da DM.

## Contrato oficial

`GET /api/dm/excel` gera exatamente oito abas:

1. `Resumo Executivo`
2. `DM-01 Evolução`
3. `DM-02 Defesas`
4. `Turmas`
5. `Alunos e Defesas`
6. `Metas`
7. `Integração SEI`
8. `Parâmetros`

A rota oficial não utiliza mais as abas técnicas do workbook legado (`CALC`, `MATRIZ`, `LISTAS DE APOIO`, `LEIA-ME`, `PAINEL` etc.). O builder antigo permanece apenas como compatibilidade interna para fluxos/testes históricos.

## Filtros

A exportação respeita o mesmo recorte selecionado no dashboard da DM:

- Área;
- Turma;
- Data de corte.

Os três links de exportação da DM recebem dinamicamente esses parâmetros. A aba `Parâmetros` registra o recorte utilizado e as regras de domínio aplicadas.

## Domínio atual

O relatório V2 expõe apenas os status ativos:

- `Ativo`;
- `Titulado`;
- `Desligado`.

Data de Defesa é o marco ativo de titulação. `graduation_date` e `diploma_status` históricos continuam preservados no banco para compatibilidade/auditoria, mas não são expostos no relatório V2.

## DM-01

`DM-01 Evolução` apresenta a evolução por turma com composição de alunos, total, ocupação, meta efetiva e situação. As contagens e a ocupação são derivadas por fórmulas a partir da aba visível `Alunos e Defesas`.

## DM-02

`DM-02 Defesas` utiliza somente ingresso individual confirmado para calcular tempo até a defesa. A aba possui uma tabela compacta `Turmas com tempo calculado`, usada pelos gráficos para impedir que ausência de média seja interpretada como zero. Inclui média, mediana, percentual até 24 meses e riscos de prazo.

## Alunos e Defesas

Mantém granularidade individual por ser uma área operacional da DM, mas segue exclusivamente o modelo atual: ingresso, qualificação, defesa, defesa marcada, status, saída, orientador, linha de pesquisa, qualidade/origem SEI e observações. Não contém Data de Titulação nem Situação do Diploma.

## Metas e Integração SEI

A aba `Metas` apresenta metas efetivas DM-01/DM-02 e histórico disponível. `Integração SEI` separa os indicadores do recorte exportado do histórico institucional de sincronizações, evitando atribuir um histórico institucional a uma única turma/área.

## Modelo de importação

O modelo Excel de alunos passa a usar 13 colunas do domínio ativo e valida somente `Ativo,Titulado,Desligado`. O parser continua aceitando colunas legadas opcionais para compatibilidade de arquivos antigos.

## Excel

O workbook usa:

- Excel Tables e autofiltros;
- congelamento de cabeçalhos;
- fórmulas legíveis para valores derivados;
- gráficos nativos/editáveis;
- cores semânticas;
- cálculo automático.

Na homologação da release, todas as oito abas foram recalculadas e renderizadas e o workbook foi verificado contra erros de fórmula e integridade OOXML.

## Banco

Nenhuma alteração de schema nesta etapa.

- `APP_VERSION = 0.8.33.0`
- `SCHEMA_VERSION = 32`
- migration vigente: `032_dm_domain_simplification_v08290.sql`
