# v0.9.6.7 — Excel Interativo V3 acadêmico · DTNH + DCS

A v0.9.6.7 generaliza o protótipo V3 aprovado na DTNH para a DCS sem criar um segundo builder.

## Princípio

DTNH e DCS compartilham `academic_excel_v3_builder.py`. A diretoria, catálogo e códigos de KPI são obtidos do payload/repositório corrente. Não existem fórmulas DCS copiadas de uma planilha DTNH nem códigos `DTNH-*` fixos no workbook da DCS.

## Experiência preservada

As duas diretorias recebem as mesmas abas visíveis:

- LEIA-ME
- PARAMETROS
- PAINEL
- NPS INSTITUICAO
- NPS CURSO
- NPS DOCENTES
- AVALIACAO DOCENTE
- APROVACAO RESULTADOS
- MATRIZ
- METAS E PLANOS
- QUALIDADE E GOVERNANCA

As bases técnicas permanecem ocultas por padrão.

## Códigos

DTNH usa `DTNH-01A`, `DTNH-01B`, `DTNH-01C`, `DTNH-02`, `DTNH-03`.
DCS usa `DCS-01A`, `DCS-01B`, `DCS-01C`, `DCS-02`, `DCS-03`.

O gráfico NPS geral UNIVC continua usando a série institucional agregada DTNH + DCS e ignora o filtro de curso. Os demais recortes usam somente o catálogo e os fatos autorizados da diretoria do workbook.

## Exportação

`GET /api/excel-interativo` aceita DTNH e DCS. O nome de download é dinâmico: `Painel_DTNH_Interativo_beta.xlsx` ou `Painel_DCS_Interativo_beta.xlsx`.

O Excel V2 (`GET /api/excel`) continua disponível em paralelo.

## Banco

Sem migration nova. Schema 33.
