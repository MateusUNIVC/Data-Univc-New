# Excel Official V1 - Dataset/Table Writer

## Purpose

The Dataset/Table Writer is the first concrete rendering primitive of the Excel Official Core. It converts a declarative `DatasetSpec` into a protected worksheet and Excel Table without moving layout responsibilities into directorate adapters.

## Main APIs

- `write_dataset_table(worksheet, dataset, ...) -> DatasetRef`
- `write_dataset_sheet(workbook, dataset, ...) -> DatasetRef`

`write_dataset_table` is the low-level primitive for writing a table at a defined anchor.

`write_dataset_sheet` creates a standardized standalone dataset sheet:

- row 1: dataset title;
- row 2: provenance or technical-layer notice;
- row 4: Excel Table header;
- row 5 onward: snapshot rows.

## DatasetRef

`DatasetRef` is library-neutral. It records:

- dataset code;
- sheet name;
- table name and table range;
- header/data row coordinates;
- physical last row;
- logical row count;
- first/last column;
- mapping from column code to Excel column letter;
- whether a structural empty row exists.

Downstream Core components should consume `DatasetRef` instead of rediscovering coordinates.

## Snapshot sizing

Tables use the actual snapshot size. The writer does not allocate thousands of empty future rows.

For a zero-record dataset, one structural blank row is created only to preserve a robust Excel Table structure. `DatasetRef.row_count` remains zero, so downstream logic must not interpret that row as a fact.

## Safety

Before mutating a worksheet, the writer validates:

- dataset has columns;
- Excel headers are unique;
- row keys are declared;
- non-nullable columns contain values;
- values match the declared `ColumnDataType`;
- the table name is not already used in the workbook.

The standalone sheet writer also checks sheet-name collisions before creating a worksheet.

Existing target cells are never silently overwritten.

## Formula injection boundary

Dataset rows are imported facts, not formulas. TEXT values beginning with `=` are stored explicitly as strings. Formula generation belongs to future calculation components, never to imported dataset rows.

## Styling and protection

The writer consumes the shared V1 design system:

- table style comes from `DEFAULT_THEME.tables`;
- imported cells use the institutional imported role;
- technical datasets/columns use the technical role;
- number formats are derived from `ColumnSpec` semantic/data types;
- technical sheets remain visible;
- standalone dataset sheets are protected against accidental editing.

## Number-format inference

When `ColumnSpec.number_format` is supplied, it wins.

Otherwise the writer can infer standard formats for:

- integer/count;
- decimal;
- percentage;
- percentage points;
- BRL currency;
- NPS / score;
- date;
- datetime.

## Architectural boundary

`contract.py`, `context.py`, `validation.py`, `theme.py` and adapters remain openpyxl-independent.

Only the rendering component imports openpyxl.

This preserves the rule:

> Adapter describes the workbook; Core renders the workbook.
