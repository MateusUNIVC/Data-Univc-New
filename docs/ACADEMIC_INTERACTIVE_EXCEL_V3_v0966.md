# Excel Interativo V3 · DTNH — v0.9.6.6

Esta release introduz um segundo formato de exportação acadêmica, em beta e inicialmente exclusivo da DTNH.

## Objetivo

O Excel V2 continua sendo o relatório estático oficial. O novo **Excel Interativo V3** funciona como uma segunda interface analítica para usuários que preferem explorar os indicadores no Excel.

O modelo segue a arquitetura aprovada a partir do `Painel_DTNH_atualizado` fornecido como referência:

`PARAMETROS → CALC → PAINEL → indicadores → MATRIZ → QUALIDADE E GOVERNANÇA`.

## Controles

A aba `PARAMETROS` permite alterar, por listas suspensas:

- semestre de referência;
- semestre de comparação;
- janela de 4, 6, 8 ou 12 semestres, além de Todo histórico;
- curso em foco;
- disciplina em foco;
- KPI exibido na MATRIZ.

Os parâmetros são expostos também como nomes Excel: `P_REF`, `P_COMP`, `P_WINDOW`, `P_COURSE`, `P_DISC`, `P_MATRIX`, `P_REF_IDX` e `P_START_IDX`.

## Indicadores atuais

O workbook usa os KPIs acadêmicos vigentes do Data UNIVC:

- DTNH-01A — NPS da Instituição · Alunos;
- DTNH-01B — NPS do Curso;
- DTNH-01C — NPS da Instituição · Docentes;
- DTNH-02 — Avaliação Docente pelo Aluno;
- DTNH-03 — Aprovação e Resultados.

O 01A contém três leituras simultâneas: tendência DTNH/curso em foco, benchmark geral da UNIVC e comparação entre cursos com classificação por meta.

## Segurança e dados

O workbook exporta apenas agregações gerenciais. Linhas individuais de alunos e respostas brutas de questionários não são exportadas. As bases técnicas ficam ocultas por padrão e o Excel não escreve dados de volta no Data UNIVC.

## Compatibilidade

O endpoint V2 `/api/excel` permanece inalterado. O beta usa `/api/excel-interativo` e só é exibido quando a diretoria ativa é DTNH.

Schema permanece 33; não há migration nova.
