# DPE UX Information Architecture - v0.10.0

Objetivo: reduzir carga cognitiva sem perder a robustez do Cost Engine.

## Navegacao principal
1. Visao geral
2. Despesas
3. Cursos
4. Docentes
5. Distribuicao de custos
6. Fechamento

## Principios
- o usuario escolhe o mes no topo; o backend continua trabalhando por competencia;
- linguagem de negocio substitui linguagem interna sempre que possivel;
- cadastros e configuracoes ficam fora do fluxo mensal principal;
- historico anterior continua disponivel, mas secundario;
- nenhuma regra financeira, tabela ou API de calculo foi removida.

## Banco
Schema 39. Sem migration nova.
