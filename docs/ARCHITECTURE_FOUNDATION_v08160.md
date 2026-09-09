# Data UNIVC v0.8.16.0 — Foundation

Esta release inicia a consolidação arquitetural sem alterar regras de negócio.

## Golden Baseline

- `baseline/golden_v0.8.15.1.json` preserva a assinatura técnica da última release antes da consolidação.
- `scripts/generate_baseline.py` gera novas baselines reproduzíveis de arquivos, rotas, migrations e testes.

## Test gate

`pytest.ini` descobre todos os arquivos `test_*.py`.

Use:

```bash
python scripts/run_test_gate.py --profile smoke
python scripts/run_test_gate.py --profile pr
python scripts/run_test_gate.py --profile release
```

- SMOKE: validação rápida dos fluxos essenciais.
- PR: suíte ampla, excluindo somente os testes Excel propositalmente pesados.
- RELEASE: todos os testes descobertos.

`scripts/run_release_checks.py` continua existindo por compatibilidade e executa RELEASE.

## Schema ledger

A migration `database/026_schema_version_baseline_v08160.sql` cria `data_univc_schema_version` e registra a versão 26.

Em produção o `/api/health/ready` exige compatibilidade entre código e schema. Se a migration não tiver sido aplicada, responde 503 com `database=schema_incompatible` em vez de permitir um deploy silenciosamente incompatível.

Local/teste não bloqueiam bancos temporários por padrão. `scripts/init_local.py` registra a versão automaticamente no SQLite local.

## Release limpa

```bash
python scripts/build_release.py --profile production
python scripts/build_release.py --profile source
```

- `production`: somente runtime/config/templates/static/migrations/docs necessários; exclui testes, bancos locais, caches e tooling de desenvolvimento.
- `source`: inclui testes, scripts e baseline, mas ainda exclui bancos locais, caches e artefatos temporários.

Todo ZIP recebe `release_manifest.json` com versão, build, schema e SHA-256 de cada arquivo incluído.
