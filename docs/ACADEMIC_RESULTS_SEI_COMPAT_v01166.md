# v0.11.6.6 — Resultados Acadêmicos · compatibilidade com XLSX bruto do SEI

## Problema corrigido

Após o hardening de memória da v0.11.6.4, a leitura passou a usar `openpyxl` em `read_only=True`. Alguns XLSX gerados por sistemas externos podem declarar no XML da planilha uma dimensão menor que a área realmente ocupada. Nesse cenário, o leitor streaming pode encerrar a iteração cedo e não alcançar os blocos `Unidade Ensino:` do relatório de notas, fazendo um arquivo válido ser rejeitado como se não fosse o relatório bruto do SEI.

A falha acontece antes da persistência e produz o sintoma de 0 registros lidos, 0 inseridos e falha em todos os cursos.

## Correção

- O parser streaming chama `reset_dimensions()` nas worksheets read-only antes de iterar.
- A leitura continua em `read_only=True`; não há retorno ao parser monolítico de alta memória.
- Inspeção e iteração usam a mesma preparação da worksheet.
- Foi adicionado teste com XLSX válido cuja dimensão XML é propositalmente adulterada para `A1:A1`.
- O teste cobre tanto a leitura quanto a persistência real via `DatabaseRepository`.

## UX da importação

A importação direta de resultados pelo SEI já possui progresso por curso dentro do modal. Por isso a chamada de cada curso passa a usar `blocking:false`, evitando o `operationOverlay` que borrava toda a tela durante a operação. O indicador inline permanece como fonte principal de progresso; a barra superior não bloqueante pode continuar aparecendo durante a requisição.

## Compatibilidade

- Schema permanece 40.
- Nenhuma migration nova.
- Batch padrão permanece 500.
- Idempotência e commits progressivos da v0.11.6.4 permanecem ativos.
- UX de alunos distintos/filtros rápidos da v0.11.6.5 é preservada.
