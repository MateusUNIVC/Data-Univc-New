# DADM V2 — Blueprint de produto e fundação técnica

## Objetivo

A DADM V2 deixa de organizar a navegação por tabelas, integrações e códigos internos e passa a organizar a experiência pelas perguntas gerenciais: **como estamos, onde mudou, quem/qual setor explica a mudança e com o que comparar**.

A V2 nasce em `/dadm/v2` e a DADM anterior permanece em `/dadm` durante a homologação.

## Arquitetura de navegação

1. **Visão geral** — Operação, Eficiência (DADM-01) e Experiência (DADM-02).
2. **Pessoas & Setores** — Explorer simétrico para Operadores e Departamentos, incluindo perfil individual.
3. **Experiência** — nota 1–10, amostra, cobertura, distribuição e análise por dimensão.
4. **Análise comparativa** — uma entidade funciona sozinha; duas ou mais viram comparação. Também permite comparar intervalos arbitrários.
5. **Dados & Integração** — conexão TALLOS, sincronização, qualidade e diagnóstico.

## Contexto de análise

O contexto é global e persiste ao navegar entre páginas:

- mês inicial;
- mês final;
- departamento;
- operador;
- canal;
- status;
- tabulação.

O período analítico é escolhido em uma grade visual de meses. O frontend mantém o contexto na URL para preservar filtros após atualizar, navegar ou compartilhar a tela.

## Semântica dos indicadores

- **Tempo Médio de Espera (TME):** tempo aguardado até o início do atendimento. A origem `tme.value` continua identificada como provisória enquanto a homologação não atingir a confiança desejada.
- **Tempo Médio de Atendimento (TMA):** duração após o início do atendimento; origem `tma.value` validada.
- **Avaliação:** somente notas válidas de 1 a 10. `S/A`, `NULL`, ausente e `level=0` são ausência e não entram no denominador.
- Toda média de avaliação é acompanhada de **quantidade de respostas** e **cobertura**.

## Contrato analítico V2

Endpoints adicionados:

- `GET /api/dadm/v2/context`
- `GET /api/dadm/v2/overview`
- `GET /api/dadm/v2/entity`
- `GET /api/dadm/v2/experience`
- `GET /api/dadm/v2/quality`

Eles reutilizam a camada de fatos TALLOS, normalização e UPSERT já homologada. Nenhuma regra crítica é calculada no navegador.

## Princípios de UI/UX

- uma ação principal por contexto;
- menos caixas e menos ícones decorativos;
- tabela para comparar números, gráfico para enxergar tendência;
- Operador e Departamento compartilham o mesmo modelo de interação;
- uma entidade pode ser estudada individualmente antes de ser comparada;
- mês/dimensão sem avaliação aparece como `—`, nunca `0/10`;
- estados vazios explicam o que está ausente;
- dados técnicos ficam fora do fluxo executivo;
- filtros globais são progressivos e cruzados.

## Fase implementada em v0.8.21.0

A fundação já contém novo shell, sidebar, contexto global, seletor visual de meses, Visão Geral, Pessoas & Setores, perfis individuais, Experiência, comparação básica e Dados & Integração. Os próximos incrementos naturais são heatmaps, drawer lateral contextual, refinamento de acessibilidade e validação visual com a base real completa.
