# Data UNIVC v0.11.6.1 — launchers locais por diretoria

Esta patch adiciona atalhos Windows independentes para DTNH, DCS, DADM, DPE, DM e Reitoria.

## Atalhos

- `INICIAR_DTNH.bat` → `http://127.0.0.1:8011/?diretoria=DTNH`
- `INICIAR_DCS.bat` → `http://127.0.0.1:8012/?diretoria=DCS`
- `INICIAR_DADM.bat` → `http://127.0.0.1:8013/dadm`
- `INICIAR_DPE.bat` → `http://127.0.0.1:8014/dpe`
- `INICIAR_DM.bat` → `http://127.0.0.1:8015/dm`
- `INICIAR_REITORIA.bat` → `http://127.0.0.1:8016/reitoria`

Todos chamam `_INICIAR_DATA_UNIVC_LOCAL.bat`, reutilizam a mesma `.venv` e usam `univc_local_all.db`. As portas são diferentes para permitir abrir mais de uma diretoria ao mesmo tempo sem que uma sessão local herde o perfil da outra.

## Segurança

O launcher força `ENVIRONMENT=local`, `AUTH_DISABLED=true` e `DATABASE_URL=sqlite:///./univc_local_all.db`. O bootstrap recusa qualquer banco que não seja SQLite, portanto os atalhos não podem apontar acidentalmente para Supabase/produção.

A Reitoria utiliza `LOCAL_REITORIA_MODE=true`. Esse modo só existe dentro do branch `AUTH_DISABLED`, que já é bloqueado em `production`. Ele fornece acesso global local para homologar `/reitoria` sem enfraquecer a autenticação de produção.

## Bootstrap local

`scripts/ensure_local_launcher.py` cria/reutiliza a base local, registra schema 40, garante as cinco diretorias operacionais, catálogo presencial DTNH/DCS, definições dos KPIs implementados e regras estruturais do motor de rateio DPE. Ele não cria medições, receitas, despesas ou resultados fictícios.

O antigo `TESTAR_DPE_DEMO.bat` continua disponível separadamente quando for desejado o conjunto demonstrativo da DPE.
