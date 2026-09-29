# Parte 4 — NPS com nomes longos de cursos

Data: 2026-09-29

## Objetivo

Evitar que nomes longos de cursos sejam cortados nos gráficos comparativos de NPS e nos demais comparativos por curso que reutilizam o mesmo renderer.

## Problema encontrado

O renderer `renderBarChart` já quebrava rótulos longos, porém `wrapChartLabel` limitava o texto a duas linhas. Quando o nome exigia mais espaço, a segunda linha era truncada com `…`.

Isso fazia o gráfico perder parte do nome do curso.

## Implementação

- `wrapChartLabel` passa a preservar todas as linhas por padrão.
- palavras excepcionalmente maiores que a largura disponível também são quebradas de forma segura;
- a margem esquerda do gráfico cresce de forma responsiva dentro de limites seguros;
- a altura de cada linha do gráfico passa a depender da quantidade real de linhas do nome;
- o gráfico inteiro cresce verticalmente quando necessário, evitando sobreposição;
- o nome completo também é inserido em `<title>` no SVG;
- o tooltip já existente continua exibindo o nome integral do curso;
- o comportamento continua horizontal e responsivo em desktop/mobile.

## Escopo

A mudança foi feita no renderer compartilhado. Portanto, além do NPS, comparações por curso que usam `renderBarChart` recebem a mesma correção sem duplicação de lógica.

Nenhum cálculo, API, schema ou dado foi alterado.

## Excel Interativo

O Excel Interativo será remodelado em uma etapa própria. A correção desta parte concentra-se no painel web para não misturar a refatoração do workbook oficial com uma mudança visual de baixo risco.
