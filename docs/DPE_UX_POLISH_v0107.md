# DPE v0.10.7 — UX Polish, Responsividade e Consistência Institucional

## Objetivo

Consolidar a experiência da DPE após o rebase de UX das versões v0.10.0 a v0.10.6, eliminando pequenas inconsistências visuais, de vocabulário, acessibilidade e responsividade sem tocar no domínio financeiro.

## Ajustes principais

### Consistência
- Despesas, Docentes e Cursos usam a mesma gramática visual de navegação interna.
- Títulos, textos auxiliares, estados e ações seguem uma hierarquia mais uniforme.
- Corrigido um ID duplicado na Visão geral que podia gerar comportamento imprevisível no DOM.

### Legibilidade
- Aumentados textos auxiliares excessivamente pequenos.
- Tabelas mantêm densidade para análise financeira, mas com melhor ritmo de linha e estados vazios.
- Blocos de histórico e orientação usam o mesmo padrão visual.

### Responsividade
- Topbar móvel reorganizada para mês e diretoria ocuparem espaço previsível.
- Abas internas empilham progressivamente em telas menores.
- Modais usam melhor a altura disponível e mantêm cabeçalho/ações acessíveis.
- Rolagem horizontal de tabelas permanece disponível sem quebrar o conteúdo financeiro.

### Acessibilidade
- Tabs recebem semântica ARIA consistente.
- Alertas usam região `aria-live`.
- Modais podem ser fechados com Esc e clique no backdrop.
- Estados de foco foram reforçados e animações respeitam `prefers-reduced-motion`.

### Linguagem
- Áreas atuais evitam termos internos como Cost Engine, snapshot e competência quando não são necessários.
- Governança explica o processo em linguagem de mês, cursos, despesas e distribuição de custos.

## Compatibilidade

- Nenhuma API financeira removida.
- Nenhuma tabela alterada.
- Nenhuma migration nova.
- Schema esperado: 39.
