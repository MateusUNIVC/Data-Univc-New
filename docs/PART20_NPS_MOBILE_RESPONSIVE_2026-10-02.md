# Parte 20 — Responsividade mobile da distribuição NPS 0–10

Data: 2026-10-02

## Problema

A distribuição NPS 0–10 era compartilhada por DTNH, DCS e Reitoria, mas em telas pequenas o conteúdo podia ser cortado. O CSS aplicava `min-width: 520px` diretamente ao elemento que também possuía `overflow-x: auto`. Como os painéis externos usam `overflow: hidden`, o próprio container crescia além do painel e a parte excedente era ocultada em vez de criar uma área rolável.

## Correção

O renderer compartilhado `DataUnivcAcademicCharts.distribution` agora separa:

- resumo e contexto, que continuam responsivos dentro do painel;
- viewport horizontal `.academic-nps-scroll`, limitado à largura do painel e com `overflow-x: auto`;
- conteúdo interno `.academic-nps-scroll-content`, que recebe largura mínima apenas em telas pequenas;
- barras 0–10 e grupos Detratores / Neutros / Promotores dentro do mesmo conteúdo rolável.

Em telas até 760 px o conteúdo interno usa 440 px de largura mínima; até 420 px usa 420 px. O usuário pode deslizar horizontalmente sem que o painel seja cortado.

## Acessibilidade e UX

- scroll por toque com `-webkit-overflow-scrolling: touch`;
- região rolável focável por teclado (`tabindex=0`);
- `role=region` e `aria-label` descritivo;
- indicação discreta no mobile: “Deslize horizontalmente para ver as notas de 0 a 10 →”;
- foco visível ao navegar por teclado.

## Escopo

A correção é única e compartilhada por:

- DTNH — NPS Instituição, NPS Curso e NPS Docentes;
- DCS — NPS Instituição, NPS Curso e NPS Docentes;
- Reitoria Acadêmica — NPS Instituição, NPS Cursos e NPS Docentes.

Nenhuma regra de cálculo de NPS, API ou base de dados foi alterada.

## Cache

DTNH/DCS já usam fingerprint de build nos assets. A Reitoria Acadêmica recebeu revisão `npsmobile01` no query string dos assets para evitar que dispositivos móveis mantenham CSS/JS antigos após o deploy.

## Validação

- 34 testes de NPS/Reitoria aprovados;
- sintaxe de `data-univc-academic-charts.js` validada com Node;
- `admin_router.py` compilado sem erro.
