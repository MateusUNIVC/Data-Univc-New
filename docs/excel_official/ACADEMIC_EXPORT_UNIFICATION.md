# Academic export unification — 02F

DTNH and DCS expose a single user-facing workbook: **Excel Oficial**.

## Canonical route

`GET /api/excel` is the canonical Academic export route. For DTNH/DCS it builds the workbook through `academic_excel_official` / `ExcelOfficialCore`, preserving the current reference, comparison, course, discipline and history-window context.

The legacy consolidated Academic report is no longer exposed by the generic Academic export button.

`/api/excel-interativo` remains only as a compatibility/cutover endpoint while legacy removal is deferred to the global cleanup phase. It is not presented as a separate workbook in the Academic UI.

## UI

The Academic file hub now contains a single featured Excel card and action: **Baixar Excel Oficial**. Snapshot/Base consolidada terminology was removed from the user-facing Academic export experience. Import templates remain separate because they serve data-entry workflows rather than analytical export.

## Observability

Academic responses from `/api/excel` use the filename `Excel_Oficial_<DIRETORIA>.xlsx` and include `X-Data-UNIVC-Excel-Engine: excel_official`.
