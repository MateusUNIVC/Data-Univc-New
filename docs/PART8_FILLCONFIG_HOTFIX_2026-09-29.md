# Parte 8 Hotfix — fillConfig — 2026-09-29

## Sintoma

Na inicialização da aplicação o navegador exibia `Não foi possível iniciar: fillConfig is not defined`.

## Causa

Durante a remoção do frontend legado da Avaliação Docente, `fillConfig()` foi removida por estar fisicamente adjacente ao bloco antigo em `static/js/app.js`. A função, porém, não pertencia ao legado: ela continua ativa na tela Configurações e é chamada após `/api/bootstrap` e após atualização do catálogo.

## Correção

- `fillConfig()` restaurada;
- preenchimento de `configResponsavel` e `configDiretoria` preservado;
- acesso aos elementos tornado defensivo para campos eventualmente ausentes;
- frontend legado docente continua removido;
- endpoints antigos continuam HTTP 410.

## Prevenção

`tests/test_part8_faculty_legacy_and_release_hardening.py` agora verifica que todos os helpers ativos chamados no bootstrap (`renderDirectorateSelector`, `applyDirectorateUi`, `fillCourseSelectors`, `fillResultFilters` e `fillConfig`) permanecem definidos.

## Validação

- 197 testes aprovados;
- 2 ignorados;
- 26/26 JavaScripts passaram no `node --check`;
- release checks completos aprovados;
- schema 49, sem migration nova.
