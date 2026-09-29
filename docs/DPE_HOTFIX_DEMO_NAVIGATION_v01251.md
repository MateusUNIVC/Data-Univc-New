# DPE v0.12.5.1 — Demo + Navigation Hotfix

## Motivo

A tela de Receitas possuia uma regra CSS especifica (`display:grid`) que continuava valendo quando a secao perdia a classe `active`. O JavaScript de navegacao trocava corretamente a aba, mas Receitas permanecia visivel e cobria a percepcao das demais telas.

## Correcao

- `revenue-operations-section` so usa `display:grid` quando tambem esta `active`.
- regra defensiva: toda `.page-section:not(.active)` permanece `display:none !important`.
- titulo da area Produtividade incluido no mapa da navegacao.
- validacao em Chromium confirma que somente a secao clicada fica visivel.

## Dados ficticios

A release local de homologacao passa a incluir `univc_dpe_demo.db` ja populado. Todos os dados sao ficticios e o modo DEMO continua isolado de producao. Use `TESTAR_DPE_DEMO.bat` no Windows ou `INICIAR_DPE_DEMO.sh` em ambiente compativel.

O seed contem 16 cursos, 19 ofertas presenciais, docentes, atividades, folha, receitas, despesas, categorias, setores, politicas de distribuicao e Allocation Run oficial/reconciliado.

## Banco

Sem migration nova. Schema 42.
