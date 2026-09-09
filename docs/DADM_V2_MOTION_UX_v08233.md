# DADM V2 Motion & UX — v0.8.23.3

## Escopo

Esta release aplica à DADM V2 a mesma linguagem de movimento curta e funcional usada no restante do Data UNIVC. O objetivo é melhorar continuidade visual, percepção de resposta e leitura de mudanças de estado sem alterar o contrato analítico TALLOS, filtros, relatórios, metas ou planos de ação.

## Sidebar

No desktop, `v2-sidebar-collapsed` continua sendo controlado pela fundação compartilhada `DataUNIVC.sidebar`, preservando o mesmo `localStorage` das demais diretorias. A diferença é que largura da sidebar, `margin-left` do conteúdo e posição da barra de carregamento agora usam a mesma transição de aproximadamente 240 ms.

No mobile, a sidebar mantém o `translateX` já existente e o backdrop passa a fazer fade também no fechamento, evitando desaparecimento abrupto.

## Camadas transitórias

Filtros progressivos e modais passaram a usar helpers locais de apresentação (`showLayer`, `hideLayer` e `toggleLayer`). No fechamento, a camada recebe `is-closing`, executa a animação curta e só depois recebe `hidden`. Isso vale para:

- filtros adicionais;
- seletor de período;
- relatório Excel;
- metas e planos de ação;
- backdrop da sidebar mobile;
- mensagens de sucesso/erro.

Os helpers não alteram DOM funcional ou payloads; apenas controlam o momento em que `display:none` é aplicado.

## Microinterações

Botões, cards de KPI, cards de gestão, cards mensais, controles de período e tabs recebem transições discretas de `transform`, borda e sombra. Painéis grandes não se deslocam; recebem somente refinamento de borda/sombra no hover para evitar movimento excessivo em áreas de leitura.

## Gráficos

As animações são puramente visuais e ocorrem após o HTML/SVG já ter sido calculado:

- linhas usam `pathLength=100` e `stroke-dashoffset` para desenho progressivo;
- barras SVG crescem a partir da base;
- pontos entram com fade/scale;
- barras horizontais e distribuição de avaliações usam `scaleX` mantendo a largura calculada no dado;
- snapshots preservam o `translate(-50%, -50%)` necessário para posicionamento do ponto;
- tooltips mantêm o posicionamento medido da v0.8.23.0 e recebem apenas uma transição curta de entrada.

Nenhuma escala, valor ou consulta é interpolada em JavaScript.

## Acessibilidade

`prefers-reduced-motion: reduce` reduz animações e transições a duração efetivamente instantânea. O scroll programático da troca de páginas também muda de `smooth` para `auto` nesse modo.

## Persistência e schema

- `APP_VERSION`: 0.8.23.3
- `SCHEMA_VERSION`: 29
- migration nova: nenhuma
- alterações de backend/dados: nenhuma
