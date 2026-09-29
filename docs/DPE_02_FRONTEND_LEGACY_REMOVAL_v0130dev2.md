# DPE-02 — Remoção do frontend legado

Versão: `0.13.0-dev.2`  
Schema: `42`  
Migration nova: nenhuma

## Objetivo

Consolidar a interface ativa da DPE no Cost Engine, retirando da navegação e do carregamento normal as implementações financeiras substituídas, sem excluir ainda backend, tabelas ou histórico.

## Removido da interface ativa

- grupo de navegação `Histórico anterior`;
- Receitas antigas;
- Despesas e folha antigas;
- Resultado por curso antigo;
- páginas DPE-01, DPE-02 e DPE-03 antigas;
- Central de arquivos antigos;
- `static/js/dpe_finance.js`;
- `measurementModal`, `importModal` e `financeModal`;
- `ensureLegacyLoaded` e listeners/fluxos associados;
- estilos CSS exclusivos desses componentes confirmados como aposentados.

## Mantido nesta etapa

- Cost Engine e todos os módulos `dpe_cost_*`;
- DPE V2/dashboard executivo;
- Metas e Planos de Ação, ainda ligados temporariamente ao catálogo de indicadores existente;
- endpoints, services, repositories e tabelas legadas no backend, para migração/remoção controlada no DPE-03;
- snapshots e trilhas de auditoria do Cost Engine.

## Validação

- sintaxe de todos os JavaScripts DPE validada;
- `python -m compileall` aprovado;
- suíte completa: 85 testes aprovados;
- `/api/health/ready`: HTTP 200, schema 42 compatível;
- `/dpe`: HTTP 200;
- HTML renderizado não carrega `dpe_finance.js` nem expõe o menu legado.

## Próxima etapa

DPE-03 deve auditar e remover o backend sem consumidores: APIs Finance v0.7.7, estruturas DPE v0.4 e demais services/repositories/tabelas legadas, criando migrations novas somente quando necessário para preservar dados reais.
