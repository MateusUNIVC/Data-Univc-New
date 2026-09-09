# DM — SEI UX & Shared Action Icons — v0.8.31.0

## Escopo
Patch de UX do Prompt 3 da DM, sem alteração de domínio, banco ou Excel.

## Integração SEI
- remove o card redundante `Datas que não existem nesse relatório`;
- mantém o card de conteúdo do relatório ocupando a largura disponível;
- observações gerais de um commit bem-sucedido são verdes/informativas;
- contagens com falha e consultas individuais incompletas continuam amarelas;
- erros continuam vermelhos.

## Ícone SEI
O símbolo usado na sidebar `Integração SEI` passa a ser reutilizado nas ações SEI de DM e DTNH/DCS, enquanto atualizações puramente locais preservam seus ícones próprios.

## Botões de adição
O decorador compartilhado remove o `+` textual antes de inserir o SVG de adição. Botões como `+ KPI`, `+ Meta`, `+ Plano`, `+ Turma` e `+ Aluno` deixam de exibir `++`.

## Compatibilidade
- APP_VERSION 0.8.31.0;
- SCHEMA_VERSION 32;
- nenhuma migration nova.
