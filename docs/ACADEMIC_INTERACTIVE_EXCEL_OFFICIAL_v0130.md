# Excel Interativo acadêmico oficial — Data UNIVC v0.13.0

## Escopo

A Parte 7 promove o antigo Excel Interativo acadêmico de beta para produto oficial em DTNH e DCS.

A rota permanece `GET /api/excel-interativo`, enquanto `/api/excel` continua fornecendo o relatório Excel tradicional.

## Estrutura oficial

Abas visíveis:

- LEIA-ME
- PARAMETROS
- PAINEL
- QUALIDADE E GOVERNANCA
- MATRIZ
- PLANO_DE_ACAO
- NPS DISCENTES
- NPS SEMESTRAL
- NPS DOCENTES
- AVALIACAO DOCENTE
- RESULTADOS ACADEMICOS
- METAS
- CURSOS
- DISCIPLINAS
- INDICADORES
- DIM_PERIODO
- DIM_MES

Camada interna oculta:

- CALC
- LISTAS DE APOIO
- bases técnicas DADOS_*
- META_EFETIVA
- METAS_RAW
- PLANOS_RAW

As bases visíveis são tabelas Excel filtráveis e representam a camada de banco de dados gerencial do arquivo. O PostgreSQL/Data UNIVC permanece como fonte oficial; o workbook não escreve dados de volta no sistema.

## Painel

O PAINEL possui cinco gráficos executivos:

1. tendência do NPS institucional dos alunos;
2. composição de promotores, neutros e detratores no período de referência;
3. favorabilidade docente na janela;
4. taxa de aprovação na janela;
5. NPS institucional por curso no período de referência.

Nomes longos de cursos usados no gráfico por curso recebem quebra de linha controlada na camada CALC para evitar truncamento desnecessário.

## Metodologia preservada

A Parte 7 não recupera métricas antigas apenas porque existiam no workbook de referência.

Em especial, `02 · Avaliação Docente` continua usando a metodologia vigente do Data UNIVC:

`favorabilidade = respostas favoráveis / respostas classificadas`

Categorias não mapeadas continuam suspendendo o indicador conforme a regra vigente.

## Download

Nome oficial:

- `Painel_DTNH_Interativo.xlsx`
- `Painel_DCS_Interativo.xlsx`

A interface não apresenta mais `beta` ou `Gerar beta` para DTNH/DCS.

## Banco e deploy

Não há migration nova na Parte 7. O schema continua 49, acumulando a migration 049 da Parte 3 quando ela ainda não tiver sido aplicada.
