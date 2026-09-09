# Academic UI Foundation — v0.8.27.0

## Objetivo

Padronizar comportamentos transversais de DTNH e DCS sem alterar regras de NPS, metas, resultados ou persistência.

## Dialogs

O backdrop continua escuro e translúcido. O cartão `.modal` volta a ser uma superfície branca, com borda verde suave e sombra leve. A regra antiga de `ui-v2.css` que aplicava o fundo escuro diretamente ao cartão foi removida.

## Competência acadêmica

`static/js/app.js` passa a expor helpers compartilhados para competência semestral:

- `parseAcademicSemester()`
- `academicSemesterFields()`
- `academicSemesterFromForm()`

A interface mostra **Ano** e **Semestre** separadamente. O backend continua recebendo `AAAA-SEM1` ou `AAAA-SEM2`, portanto não há migration ou alteração de schema.

O componente foi aplicado aos dialogs de avaliação docente pelo aluno, resultados acadêmicos, NPS via SEI, upload XLSX/ZIP e confirmação de semestre após inspeção dos relatórios.

## Paginação

`attachPagination()` passa a oferecer:

- primeira página `«`;
- página anterior `‹`;
- páginas próximas à atual;
- próxima página `›`;
- última página `»`.

Os hooks anteriores continuam válidos e os novos botões têm `aria-label`/`title`.

## Sidebar

A lista de navegação mantém `overflow-y: auto` quando o conteúdo excede a altura disponível, mas bloqueia overflow horizontal. O `translateX(1px)` dos itens em hover foi removido para evitar scrollbar lateral provocado por um deslocamento puramente visual.

## Compatibilidade

- APP_VERSION: 0.8.27.0
- SCHEMA_VERSION: 31
- migration: nenhuma nova
- contratos de API e banco: inalterados
