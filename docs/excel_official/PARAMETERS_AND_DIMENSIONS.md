# Excel Official V1 - Parameters, Dimensions & Validation Lists

## Purpose

Phase 01D turns the declarative `ParameterSpec` and `DimensionSpec` contracts into the first offline-interactive controls of the Excel Official Core.

The site supplies the initial state. The downloaded workbook then owns its local analytical state through `PARAMETROS`, while `LISTAS DE APOIO` carries the authorized option lists needed for offline interaction.

## Public rendering APIs

- `write_parameter_system(workbook, spec) -> ParameterSystemRef`
- `write_support_lists(workbook, spec) -> Mapping[str, SupportListRef]`
- `write_parameters_sheet(workbook, spec, support_lists) -> Mapping[str, ParameterRef]`

`write_parameter_system` is the preferred V1 orchestration API because it performs a complete preflight before mutating the workbook.

## Initial-state precedence

The effective initial parameter value is resolved in this order:

1. `WorkbookSpec.initial_state.values`;
2. `ParameterSpec.initial_value`;
3. `SnapshotSpec.initial_scope`;
4. blank when the parameter is optional.

This keeps web filters as the initial state without turning them into a permanent restriction on the workbook.

## Dimension-backed lists

A `ParameterSpec.values_source` can reference a `DimensionSpec`. The Core reads the dimension's backing `DatasetSpec`, uses the declared key/label/sort columns, removes duplicate members and writes an authorized support list.

The dimension dataset itself is still rendered by the 01C Dataset/Table Writer. For example, a `period` dimension can use a technical dataset whose sheet is `DIM_PERIODO`; 01D consumes that same declarative source to build the dropdown list instead of maintaining a second period catalogue.

## Dataset-backed lists

A parameter may point directly to a dataset. If the dataset has exactly one visible/non-technical column, that column is used automatically. Otherwise `ParameterSpec.values_column` is mandatory.

## Named ranges

V1 creates stable names from parameter codes:

- parameter cell: `P_<CODE>`;
- dropdown source: `LST_<CODE>`.

Codes are normalized to ASCII/uppercase/underscores only at the Excel-rendering boundary. The declarative contract keeps the original stable code.

Examples:

- `reference_period` -> `P_REFERENCE_PERIOD`;
- `course` -> `P_COURSE` / `LST_COURSE`;
- `discipline` -> `P_DISCIPLINE` / `LST_DISCIPLINE`.

Name collisions after normalization are rejected before workbook mutation.

## Dependent dropdowns

Contract V1 supports one dependency per parameter. A child `DimensionSpec` declares:

- `parent_dimension`;
- optionally `parent_key_column` when the child dataset's parent-key column is not named exactly like the parent dimension code.

Example:

`course -> discipline`

The support sheet groups child values by parent label. The child's defined range is dynamic and uses only Excel-2019-compatible, non-volatile functions:

`INDEX + MATCH + COUNTIF`

V1 deliberately does not use:

- `FILTER`;
- `UNIQUE`;
- `XLOOKUP`;
- `INDIRECT`;
- `OFFSET`.

When the parent has an `empty_option` such as `(todos)`, the child support block also receives a group for that option containing all authorized child values. A child `empty_option` such as `(todas)` remains the first value in each parent group.

Changing a parent control cannot automatically clear a stale child selection without VBA. Therefore the child validation input message explicitly tells the user to confirm the dependent value after changing the parent. Later Quality/Diagnostics components can surface stale combinations more prominently.

## PARAMETROS

The V1 sheet contains:

- institutional title/subtitle;
- `CONTROLES INTERATIVOS` section;
- one row per `ParameterSpec`, ordered by `display_order` and declaration order;
- editable values in the institutional INPUT style;
- locked controls in the CONTROL style;
- parameter descriptions;
- list validation when a support list exists;
- date/number formatting when declared;
- a local-editing/no-sync notice.

Only cells explicitly declared editable are unlocked. Worksheet protection is an accidental-edit guard, not an authorization boundary.

## LISTAS DE APOIO

`LISTAS DE APOIO` is visible and protected under Contract V1.

It contains only authorized snapshot values required by interactive parameters. Independent lists occupy one column; dependent lists use parent/value column pairs. It is clearly marked as `CAMADA TÉCNICA — NÃO ALTERAR`.

## Preflight guarantees

Before `write_parameter_system` creates any sheet or defined name, it validates:

- WorkbookSpec structural validity;
- reserved sheet collisions;
- generated defined-name collisions;
- existing defined-name collisions;
- parameter value types when declared;
- list-source availability;
- dependent-dimension parent membership;
- required initial values;
- initial values being inside the authorized list/current dependent parent scope.

If preflight fails, the workbook is left unchanged.

## V1 limitation

One dropdown dependency per parameter is supported in V1. The declarative field remains a tuple for forward compatibility, but more than one dependency is rejected explicitly rather than silently approximated.

## Architectural boundary

`ParameterSpec`, `DimensionSpec`, `ParameterRef`, `SupportListRef` and `ParameterSystemRef` remain openpyxl-independent.

Only `excel_official/components/` knows how to materialize them as Excel objects.
