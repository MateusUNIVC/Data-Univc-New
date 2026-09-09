# v0.9.6.2 — DTNH/DCS Institutional NPS Benchmark

## Objetivo

Separar, no NPS institucional discente de DTNH e DCS, três leituras complementares sem remover o benchmark por curso existente.

## Gráficos

1. **NPS institucional da diretoria/curso** — usa os cursos da diretoria ativa; o filtro de curso pode restringir a série a um curso.
2. **NPS geral da UNIVC** — usa a agregação institucional DTNH + DCS por contagens reais de respostas e ignora o filtro de curso.
3. **NPS institucional por curso** — fotografia do semestre para todos os cursos da diretoria, mantendo classificação visual por meta.

## Filtros

| Gráfico | Curso | Semestre | Janela |
|---|---|---|---|
| Diretoria/curso | sim | sim | sim |
| UNIVC geral | não | sim | sim |
| Comparação por curso | não | sim | não |

O semestre selecionado também funciona como âncora da janela histórica: períodos posteriores ao semestre escolhido não entram no gráfico. A mesma regra foi aplicada às evoluções de NPS do Curso e NPS institucional dos docentes.

## Fonte oficial

Os cards separados intitulados **Fonte oficial** foram retirados do NPS institucional discente e docente. A origem e os metadados continuam preservados no banco e nos fluxos de integração; a mudança é de apresentação.

## Compatibilidade

- Autenticação e identidade frontend: preservadas da v0.9.6.1.
- Ícone SEI e normalização de botões `+`: preservados da linha DM 8.31/8.33.
- Excel V2 de DTNH, DCS e DM: preservado.
- Schema: 33, sem migration nova.
