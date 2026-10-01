# Parte 12 · Hotfix DM — turmas fragmentadas no relatório do SEI

Data: 2026-10-01

## Problema observado

O relatório sintético `Alunos por Unidade / Curso / Turma` do SEI pode emitir mais de um bloco físico para a mesma turma lógica. No caso real validado em 2026-10-01, a área CTE apresentou:

- `17-CTE` com 50 alunos;
- `17-CTE Mestrado Univc` com 1 aluno adicional.

Ambos representam `CTE:17`. O parser anterior entendia a repetição da chave como erro e interrompia a importação com `Bloco duplicado`.

## Correção

`dm_sei_parser.py` passa a consolidar blocos com a mesma `área + número da turma` quando pertencem ao mesmo tipo (real ou teste):

- alunos distintos são unidos;
- linhas idênticas repetidas da mesma matrícula dentro da mesma turma são deduplicadas;
- o total declarado é consolidado sem dupla contagem;
- o rótulo mais descritivo do SEI é mantido para auditoria;
- a prévia recebe aviso explícito de que o SEI fragmentou a turma.

Continuam bloqueados:

- a mesma matrícula em turmas diferentes;
- a mesma matrícula com nome/status incompatível dentro de fragmentos da mesma turma;
- colisão entre bloco real e TESTE/DEMO/HOMOLOGAÇÃO com a mesma chave.

## Validação com o arquivo real

Arquivo gerado pelo SEI: `1790874693805.xlsx`.

Resultado após o hotfix:

- 13 turmas lógicas no relatório completo;
- 433 alunos preservados;
- `CTE:17` consolidada em 51 alunos;
- com `Ignorar turmas TESTE` ativo: 12 turmas e 431 alunos;
- nenhuma matrícula real perdida na consolidação.

O HAR também confirma que o relatório foi gerado na unidade `STRICTO SENSU`, periodicidade integral e sem filtro específico de curso/turma, portanto a fragmentação é comportamento da própria saída do SEI.

## Banco

Sem migration nova. Schema permanece 49.
