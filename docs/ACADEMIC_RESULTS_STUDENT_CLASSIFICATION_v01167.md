# Data UNIVC v0.11.6.7 — Academic Results Student Classification

## Objetivo

Simplificar a leitura gerencial de Aprovação/Notas para trabalhar com dois status principais de aluno: **Aprovados** e **Com reprovação**.

## Regra por aluno

1. Se existir ao menos uma disciplina reprovada no recorte, o aluno fica em **Com reprovação**.
2. Se não existir reprovação e houver ao menos uma disciplina aprovada, o aluno fica em **Aprovados**, mesmo que outra disciplina ainda esteja sem situação final.
3. Se o aluno possuir somente resultados sem classificação, ele não é forçado como aprovado ou reprovado; aparece apenas como pendência de qualidade do dado.

Os motivos **reprovação por nota** e **reprovação por falta** continuam sendo contagens de alunos distintos e podem se sobrepor.

## UX

O card **Sem fechamento** deixa de existir. Permanecem:

- Alunos distintos;
- Aprovados;
- Com reprovação;
- Reprovação por nota;
- Reprovação por falta;
- Taxa de aprovação;
- Média das notas.

Se houver alunos formados somente por registros sem situação final, uma mensagem discreta de qualidade informa a quantidade sem transformar isso em um terceiro KPI.

## Compatibilidade

- sem migration nova;
- schema 40;
- importação SEI e processamento em lotes permanecem inalterados;
- campos antigos do endpoint são mantidos quando possível para não quebrar consumidores existentes.
