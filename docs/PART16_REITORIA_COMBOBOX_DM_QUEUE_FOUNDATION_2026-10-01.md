# Parte 16 — Reitoria com combobox + DM-QUEUE-01

Data: 2026-10-01  
Versão: Data UNIVC v0.13.0  
Schema: 49 — sem migration nova

## Reitoria

- `Curso` e `Disciplina` em `/reitoria/academico` reutilizam `DataUNIVC.searchableSelect`.
- O `<select>` nativo continua sendo a fonte de verdade, preservando contratos, eventos `change` e filtros existentes.
- A pesquisa é textual, tolera acentos e mantém o mesmo padrão já usado em DTNH/DCS.
- O combobox de disciplina continua visível somente em Avaliação Docente e Aprovação/Notas.

## DM-QUEUE-01 — separação do fluxo SEI

O `POST /api/dm/sei/commit` não executa mais `lookup_student_course_dates` para centenas de alunos após sincronizar o relatório. O commit encerra após gravar turmas/alunos e devolve metadados explícitos informando que o enriquecimento individual foi adiado.

A consulta individual permanece em `/api/dm/sei/refresh-students`, mas agora é uma operação separada. A tela também deixa de oferecer a opção de executar essa consulta dentro da sincronização do relatório.

Esse passo remove a principal causa do 504 durante a sincronização de turmas. O próximo passo (DM-QUEUE-02/03) criará fila persistente e processamento em lotes para impedir timeout também na atualização individual de grandes volumes.

## Validação

- 241 testes aprovados; 2 ignorados.
- 28/28 arquivos JavaScript aprovados por `node --check`.
- preflight verifica que o commit DM não reintroduza `lookup_student_course_dates` inline.
- preflight verifica os comboboxes pesquisáveis da Reitoria.
