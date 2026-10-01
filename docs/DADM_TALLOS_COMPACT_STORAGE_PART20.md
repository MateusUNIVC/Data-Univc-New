# DADM / TALLOS — Compact Storage Foundation (Parte 20)

## Objetivo

Preparar a remoção segura de `source_payload_json` sem alterar os KPIs do Centro de Analytics TALLOS.

A auditoria do código confirmou que o JSON sanitizado completo tinha somente uma dependência analítica ativa: a auditoria do campo TALLOS `level`, utilizada para distinguir avaliação válida 1–10, `level=0`, ausência/S-A e valor inválido.

## Contrato compacto

A migration 052 adiciona a `dadm_tallos_attendances`:

- `rating_source_state`: `valid`, `zero`, `missing` ou `invalid`;
- `rating_source_value`: representação textual curta do `level` original, limitada a 64 caracteres;
- `normalization_version`: versão do contrato que produziu o registro.

`rating` continua sendo a nota normalizada utilizada nos indicadores e permanece `NULL` fora do intervalo homologado 1–10.

## Compatibilidade

A migration faz backfill dos novos campos a partir do `source_payload_json` existente. Quando um histórico já teve o payload limpo manualmente, uma `rating` normalizada válida 1–10 é suficiente para recuperar o estado `valid`; registros sem payload e sem nota permanecem `missing`, pois não há informação restante para distinguir `level=0` de uma ausência original. O endpoint de auditoria passa a consultar exclusivamente as novas colunas compactas e deixa de ler o JSON.

Nesta etapa o JSON **não é apagado**. Isso é deliberado: a Parte 20 cria o substituto e permite comparar os resultados antes/depois. A limpeza histórica e a ingestão sem payload ficam para a etapa seguinte, após benchmark de equivalência.

## Resultado esperado

Após aplicar 052, dashboards e KPIs devem permanecer numericamente idênticos. Um novo sync utiliza `TALLOS_NORMALIZATION_VERSION = 5` e grava o contrato compacto junto com os campos já normalizados.
