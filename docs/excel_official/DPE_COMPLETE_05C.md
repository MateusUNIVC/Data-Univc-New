# DPE Excel Official · 05C Complete

## Estado final

- `/api/dpe/excel` é a rota canônica da DPE.
- `DPE_EXCEL_OFFICIAL_ENABLED=false` mantém o Excel DPE Modern como rollback imediato.
- `DPE_EXCEL_OFFICIAL_ENABLED=true` usa `DPEAdapter` + `ExcelOfficialCore` e entrega `Excel_Oficial_DPE.xlsx`.
- O schema continua **53**; não há migration nesta fase.
- A interface possui um único caminho de exportação.

## Gate de produção

Antes de ativar a flag, a Reitoria deve chamar:

`GET /api/admin/excel-official/dpe/parity?period_id=<ID>`

O corte somente deve ocorrer com:

- `cutover_status = READY`;
- `failures = 0` nos 61 casos semânticos;
- `legacy_workbook.build_ok = true`;
- `new_workbook.build_ok = true`;
- `new_release_allowed = true`.

A rota é protegida por `require_fresh_reitoria` e usa o mesmo payload autorizado do Cost Engine.

## Ativação

Em `.env.production`:

```env
DPE_EXCEL_OFFICIAL_ENABLED=true
```

Depois recrie somente a aplicação:

```bash
docker compose up -d --force-recreate app
```

Não altere o volume do PostgreSQL.

## Smoke pós-corte

```bash
export DATA_UNIVC_DPE_COOKIE='session=...'
python scripts/smoke_dpe_excel_cutover.py \
  --base-url https://datadriven.univc.com.br \
  --period-id <ID> \
  --output dpe_smoke.json
```

O smoke exige `X-Data-UNIVC-Excel-Engine: excel_official`, seis abas institucionais iniciais, metadata DPE, schema/versão corretos, zero links externos e zero VBA.

## Rollback

```env
DPE_EXCEL_OFFICIAL_ENABLED=false
```

```bash
docker compose up -d --force-recreate app
```

O mesmo `/api/dpe/excel` volta ao DPE Modern, sem mudança de banco ou schema.
