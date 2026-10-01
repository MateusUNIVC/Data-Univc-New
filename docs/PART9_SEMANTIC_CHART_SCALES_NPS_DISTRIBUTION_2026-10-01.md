# Parte 9 — Escalas semânticas e distribuição NPS 0–10 — 2026-10-01

## Objetivo

Tornar os gráficos acadêmicos visualmente honestos e comparáveis, eliminando escalas automáticas inadequadas para percentuais, NPS e contagens e acrescentando a distribuição original de respostas 0–10 aos painéis de NPS.

## Escalas semânticas

O renderer compartilhado passa a trabalhar por natureza da métrica:

- **Percentual**: eixo fixo de 0% a 100%. Aplicado à taxa de aprovação, favorabilidade docente e demais percentuais.
- **NPS**: eixo fixo de -100 a +100.
- **Contagem**: mínimo fixo em 0 e máximo automático arredondado. Aplicado, entre outros, a alunos distintos, aprovados e matrículas.
- **Auto**: preservado apenas para métricas que não possuem limites semânticos naturais.

Isso impede que uma variação de 95% para 90% pareça uma queda extrema por causa de um eixo 89–96 e impede eixos de aprovação acima de 100% ou contagens negativas de alunos.

## Barras e NPS negativo

O valor numérico das barras passa a ser renderizado em uma coluna própria à direita da área de plotagem. Com isso, valores negativos de NPS não avançam sobre o espaço reservado ao nome do curso. Os nomes completos continuam disponíveis no SVG/tooltip e podem quebrar em múltiplas linhas.

## Distribuição das avaliações 0–10

Foi adicionado o endpoint:

`GET /api/surveys/nps/distribution`

Parâmetros principais:

- `audience=course|institution|faculty`
- `semester=AAAA-SEMX`
- `course=<nome>` quando aplicável

A resposta é reconstruída diretamente dos agregados oficiais já existentes e contém:

- notas de 0 a 10, sempre com todas as onze posições;
- quantidade por nota;
- percentual por nota;
- total de respondentes;
- média ponderada 0–10;
- NPS;
- totais de promotores, neutros e detratores.

Nenhuma resposta individual é exposta.

### Regra de interpretação

A média 0–10 é **informação complementar**. Ela não substitui o NPS. O KPI oficial continua sendo calculado como `% promotores - % detratores`.

## Painéis web

A nova visualização aparece em:

- NPS da Instituição — Alunos;
- NPS do Curso;
- NPS da Instituição — Docentes.

Cada painel mostra as onze notas, contagem, percentual, respondentes, média e NPS do recorte/semestre selecionado.

## Excel Interativo

O Excel oficial ganhou a base visível `NPS DISTRIBUICAO`, com a tabela `TblNpsDistribuicao`, mantendo os cinco gráficos executivos do `PAINEL`.

As escalas executivas já permanecem coerentes no Excel:

- aprovação/favorabilidade: 0–100;
- NPS: -100–100.

A nova base torna a distribuição 0–10 auditável no arquivo sem criar colunas físicas adicionais no banco.

## Banco de dados

- Schema permanece **49**.
- Última migration permanece `049_academic_faculty_context_scopes_v0130.sql`.
- Nenhuma migration nova nesta etapa.

## Validação

- 203 testes aprovados;
- 2 testes ignorados;
- testes de contrato para soma das 11 notas = respondentes;
- testes para escalas percentuais 0–100;
- testes para NPS -100–100;
- testes para contagens sem eixo negativo;
- teste de layout de barra negativa sem invasão do rótulo;
- Excel Interativo validado com `NPS DISTRIBUICAO` visível e `TblNpsDistribuicao`.
