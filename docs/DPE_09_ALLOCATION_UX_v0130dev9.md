# DPE-09 — Distribution UX

Esta etapa não altera o schema. O motor de distribuição e sua memória técnica permanecem preservados.

## Princípios

- **Direta:** 100% para um curso/contexto; o tratamento é definido na área Despesas.
- **Compartilhada:** o usuário escolhe uma forma administrativa de distribuição.
- **Institucional:** não participa da distribuição aos cursos.
- **Folha/docência:** pode acompanhar automaticamente as atividades registradas do docente.

## Formas apresentadas ao usuário

- Conforme atividades do docente;
- Proporcional à carga horária;
- Proporcional ao número de alunos;
- Proporcional à receita;
- Dividir igualmente;
- Definir manualmente.

O backend mantém os `driver_type` históricos para preservar snapshots, auditoria e resultados já calculados.

## Compatibilidade removida

Uma despesa `SHARED` não pode mais escolher a regra `DIRECT`. Para um gasto de destino único, o usuário deve alterar o tratamento para `DIRECT` na área Despesas. Isso evita contradição entre classificação econômica e configuração de distribuição.
