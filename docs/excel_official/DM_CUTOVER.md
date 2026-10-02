# EXCEL-OFFICIAL-03B — DM Production Cutover

Status de desenvolvimento: **COMPLETE**.

## Objetivo

A DM passa a expor um único caminho de Excel para o usuário: `/api/dm/excel`.

- com `DM_EXCEL_OFFICIAL_ENABLED=false`, o endpoint usa o relatório V2 anterior;
- com `DM_EXCEL_OFFICIAL_ENABLED=true`, o mesmo endpoint usa `DMAdapter` + `ExcelOfficialCore`;
- `/api/dm/excel-interativo` permanece somente como alias de compatibilidade para links antigos;
- a interface da DM não apresenta mais dois Excels concorrentes.

## Gate de paridade de produção

Antes de ativar a flag, uma sessão fresca da Reitoria deve chamar:

```text
GET /api/admin/excel-official/dm/parity
```

Opcionalmente:

```text
GET /api/admin/excel-official/dm/parity?data_corte=2026-08-28
```

A resposta precisa trazer:

```json
{
  "summary": {
    "failures": 0,
    "semantic_passed": true,
    "source_quality_ok": true,
    "new_release_allowed": true,
    "cutover_status": "READY"
  }
}
```

O harness compara o backend atual com as métricas do Core nos seguintes recortes:

- DM inteira;
- cada área;
- cada turma.

E verifica:

- membros;
- alunos ativos;
- ocupação;
- tempo médio até defesa;
- defesa em até 24 meses;
- risco >30 meses sem defesa.

Também constrói o relatório V2 e o Excel Oficial para registrar evidência de build.

## Cutover

No VPS, depois de obter `READY`:

```bash
cd /opt/data-univc
nano .env.production
```

Alterar:

```env
DM_EXCEL_OFFICIAL_ENABLED=false
```

para:

```env
DM_EXCEL_OFFICIAL_ENABLED=true
```

Depois:

```bash
docker compose build app
docker compose up -d --force-recreate app
```

A rota canônica passa a responder:

```text
X-Data-UNIVC-Excel-Engine: excel_official
```

E o arquivo passa a se chamar:

```text
Excel_Oficial_DM.xlsx
```

## Smoke

Com um cookie de sessão autorizado para a DM:

```bash
export DATA_UNIVC_DM_COOKIE='...'
python scripts/smoke_dm_excel_cutover.py \
  --base-url https://datadriven.univc.com.br \
  --output dm_smoke.json
```

O resultado precisa ser `PASS` e `engine=excel_official`.

## Rollback

Se houver qualquer problema:

```bash
nano .env.production
```

Voltar para:

```env
DM_EXCEL_OFFICIAL_ENABLED=false
```

E recriar somente a aplicação:

```bash
docker compose up -d --force-recreate app
```

Nenhuma migration ou alteração de banco é necessária para este cutover.
