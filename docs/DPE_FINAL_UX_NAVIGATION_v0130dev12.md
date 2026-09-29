# DPE-12 — Final UX Navigation

Release: `0.13.0-dev.12`  
Schema: `48` (sem migration nova)

## Objetivo

Consolidar a arquitetura de informação da DPE após a reestruturação de domínio das etapas DPE-02 a DPE-11, sem alterar cálculos financeiros.

## Mudanças

- Sidebar dividida em **Fluxo do mês**, **Resultados e gestão** e **Configuração e ferramentas**.
- `Cursos` analítico renomeado para **Resultado por curso**, eliminando ambiguidade com **Cursos e contextos**.
- Metas e Planos de ação deixam de ficar escondidos dentro de cadastros/configurações.
- Faixa horizontal do fluxo mensal com 5 etapas: Receitas, Despesas, Docência, Distribuição e Fechamento.
- Título e subtítulo do topbar passam a refletir a seção atual.
- Ação principal do topbar torna-se contextual (nova despesa, atividade, meta, plano, abrir mês etc.).
- Última área visitada é preservada na sessão do navegador e restaurada após recarregar a página.
- Removida nomenclatura residual `legacy-chevron` do frontend ativo.

## Fora de escopo

- nenhuma alteração de banco;
- nenhum cálculo financeiro novo;
- nenhuma mudança no rateio;
- nenhuma alteração em outras diretorias.
