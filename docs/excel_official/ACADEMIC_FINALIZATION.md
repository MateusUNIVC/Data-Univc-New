# Academic Excel Official — Finalization (02E)

## State

Development for DTNH/DCS is complete. Production completion still requires fresh live evidence and post-cutover smoke validation. Academic V3 remains available for rollback during the observation window.

## Final production sequence

### 1. Deploy with the flag OFF

```bash
cd /opt/data-univc
git pull
docker compose -f docker-compose.production.yml up -d --build --force-recreate app
python scripts/manage_academic_excel_cutover.py status --env-file .env.production
```

Expected: `ACADEMIC_EXCEL_OFFICIAL_ENABLED=false`.

### 2. Prepare production evidence from Reitoria

Use a fresh authenticated Reitoria session cookie without putting it on the command line:

```bash
read -s -p "Reitoria Cookie header: " DATA_UNIVC_REITORIA_COOKIE
export DATA_UNIVC_REITORIA_COOKIE
printf '\n'

python scripts/prepare_academic_excel_cutover.py \
  --base-url http://127.0.0.1:8000 \
  --cookie-env DATA_UNIVC_REITORIA_COOKIE \
  --output-dir academic_cutover_evidence

unset DATA_UNIVC_REITORIA_COOKIE
```

This calls the Reitoria-only endpoint `/api/admin/excel-official/academic/parity` for DTNH and DCS, saves both production parity reports and builds the cutover manifest. Continue only when the manifest is `READY`.

### 3. Activate

```bash
python scripts/manage_academic_excel_cutover.py activate \
  --manifest academic_cutover_evidence/academic_excel_cutover_manifest.json \
  --dtnh-report academic_cutover_evidence/academic_parity_dtnh.json \
  --dcs-report academic_cutover_evidence/academic_parity_dcs.json \
  --env-file .env.production \
  --confirm ENABLE_EXCEL_OFFICIAL

docker compose -f docker-compose.production.yml up -d --force-recreate app
curl -fsS http://127.0.0.1:8000/api/health/ready
```

### 4. Smoke DTNH

```bash
read -s -p "DTNH Cookie header: " DTNH_SMOKE_COOKIE
export DTNH_SMOKE_COOKIE
printf '\n'

python scripts/smoke_academic_excel_cutover.py \
  --base-url http://127.0.0.1:8000 \
  --directorate DTNH \
  --cookie-env DTNH_SMOKE_COOKIE \
  --window 4 \
  --output /tmp/dtnh_excel_official.xlsx \
  --report academic_cutover_evidence/smoke_dtnh.json

unset DTNH_SMOKE_COOKIE
```

### 5. Smoke DCS

```bash
read -s -p "DCS Cookie header: " DCS_SMOKE_COOKIE
export DCS_SMOKE_COOKIE
printf '\n'

python scripts/smoke_academic_excel_cutover.py \
  --base-url http://127.0.0.1:8000 \
  --directorate DCS \
  --cookie-env DCS_SMOKE_COOKIE \
  --window 4 \
  --output /tmp/dcs_excel_official.xlsx \
  --report academic_cutover_evidence/smoke_dcs.json

unset DCS_SMOKE_COOKIE
```

### 6. Produce the final completion record

```bash
python scripts/manage_academic_excel_cutover.py finalize \
  --manifest academic_cutover_evidence/academic_excel_cutover_manifest.json \
  --dtnh-report academic_cutover_evidence/academic_parity_dtnh.json \
  --dcs-report academic_cutover_evidence/academic_parity_dcs.json \
  --dtnh-smoke academic_cutover_evidence/smoke_dtnh.json \
  --dcs-smoke academic_cutover_evidence/smoke_dcs.json \
  --output-dir academic_cutover_evidence
```

The migration is operationally complete only when this prints:

```text
Academic finalization: COMPLETE
```

and creates `academic_excel_finalization.json` / `.md`.

## UI behavior

While the legacy engine is active, the academic UI shows `Excel Interativo`. After the production flag is enabled and the app restarts, `/api/bootstrap` reports `academic_official_active=true` and the same UI automatically changes to `Excel Oficial` / `Baixar Excel Oficial`. The endpoint remains `/api/excel-interativo` during the compatibility window.

## Rollback

Rollback remains intentionally simpler than activation:

```bash
python scripts/manage_academic_excel_cutover.py rollback --env-file .env.production
docker compose -f docker-compose.production.yml up -d --force-recreate app
```

The UI returns automatically to the legacy `Excel Interativo` label after the restart.

## Legacy removal

Do not delete `academic_excel_v3_builder.py` immediately after cutover. Keep it through the observation window. Legacy removal belongs to the final project-wide cleanup phase after DM, DADM and DPE have migrated.
