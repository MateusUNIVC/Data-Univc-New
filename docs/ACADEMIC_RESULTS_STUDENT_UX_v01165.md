# v0.11.6.5 — Resultados Acadêmicos · leitura por aluno e filtros rápidos

## Objetivo

Separar claramente duas unidades de análise que estavam misturadas na experiência de Aprovação e Notas:

- **resultados disciplinares**: cada vínculo aluno × disciplina;
- **alunos distintos**: cada matrícula contada uma única vez no recorte selecionado.

A taxa institucional de aprovação continua sendo calculada sobre resultados disciplinares finalizados. A nova leitura por aluno não altera o KPI; ela acrescenta contexto gerencial e permite localizar rapidamente quem foi reprovado.

## Classificação por aluno

No recorte selecionado, cada aluno pertence a exatamente uma das três situações abaixo:

1. **Aprovado no recorte** — todas as disciplinas importadas estão finalizadas e aprovadas;
2. **Com reprovação** — possui ao menos uma disciplina reprovada;
3. **Sem fechamento** — não possui reprovação, mas há ao menos uma disciplina ainda sem resultado final.

Assim:

`Alunos distintos = Aprovados no recorte + Com reprovação + Sem fechamento`

Os motivos **reprovação por nota** e **reprovação por falta** contam alunos distintos, porém não são mutuamente exclusivos: um mesmo aluno pode ter uma reprovação por nota em uma disciplina e por falta em outra.

## UX

- o módulo abre por padrão no semestre mais recente disponível;
- o segundo gráfico passa a exibir **Alunos distintos — evolução**;
- o tooltip mostra total de alunos, aprovados no recorte, com reprovação e sem fechamento;
- cards mostram alunos distintos, aprovados, reprovados, reprovação por nota, reprovação por falta, pendências, taxa disciplinar e média;
- cards de situação são clicáveis e mudam automaticamente para **Registros individuais**;
- o backend aplica o filtro antes da paginação, portanto a lista continua escalável;
- um chip visível informa qual filtro rápido está ativo e permite limpá-lo.

## Banco e compatibilidade

Nenhuma migration nova. O schema permanece **40**.
