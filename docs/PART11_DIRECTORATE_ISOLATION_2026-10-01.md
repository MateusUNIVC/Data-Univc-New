# Parte 11 — Isolamento de diretoria DTNH/DCS

Data: 01/10/2026  
Versão: Data UNIVC v0.13.0  
Schema: 49 — sem migration nova

## Objetivo

Eliminar qualquer reaproveitamento visual ou assíncrono de dados acadêmicos quando o usuário alterna entre DTNH e DCS.

O sintoma observado era especialmente visível nas áreas de NPS: após trocar de diretoria, a distribuição 0–10 ou outro conteúdo podia continuar exibindo temporariamente dados do recorte anterior.

## Causas encontradas

1. `state.npsDistributionCache` não era limpo por `resetDirectorateCaches()`.
2. A chave do cache 0–10 usava apenas audiência, semestre e curso; DTNH e DCS podiam produzir a mesma chave.
3. Requisições iniciadas antes da troca de diretoria podiam terminar depois da troca e gravar a resposta antiga no `state`.
4. A Avaliação Docente possuía `loadSerial`, mas `loadFacets()` ainda podia reconciliar/renderizar filtros antes da checagem do serial.

## Implementação

### Cache NPS

A chave passa a incluir a diretoria ativa:

`diretoria | audience | semester | course`

O cache também é zerado em `resetDirectorateCaches()`.

### Geração de diretoria

O estado global passa a manter `directorateEpoch`.

Cada troca válida de diretoria incrementa o epoch. Carregamentos acadêmicos capturam `{directorate, epoch}` antes do request e só aplicam o retorno caso o contexto ainda seja o atual.

Cobertura aplicada em:

- bootstrap acadêmico;
- dashboard acadêmico;
- NPS institucional dos alunos;
- NPS por curso;
- NPS institucional dos docentes;
- distribuição NPS 0–10;
- resumo, alunos, tendência e detalhes de Resultados Acadêmicos.

### Avaliação Docente

`loadFacets(serial)` agora valida `moduleState.loadSerial` após cada request e antes de qualquer reconciliação/renderização. `reset()` também limpa imediatamente o conteúdo renderizado.

### Limpeza visual imediata

Na troca DTNH ↔ DCS, gráficos, tabelas, resumos e distribuição NPS são substituídos imediatamente por estado de carregamento da nova diretoria. Isso impede que o conteúdo antigo permaneça visível durante a nova consulta.

## Garantias

- resposta atrasada de DTNH não grava estado se DCS já estiver ativo;
- resposta atrasada de DCS não grava estado se o usuário já tiver retornado a DTNH;
- cache 0–10 nunca é compartilhado entre diretorias;
- filtros da Avaliação Docente não são renderizados com facets da diretoria anterior;
- não altera regras de NPS, favorabilidade, aprovação ou importação;
- não altera banco de dados.

## Validação

- testes específicos Parte 11: 6 aprovados;
- regressão completa: 214 aprovados, 2 ignorados;
- `node --check` preservado para todos os JavaScripts no release preflight;
- preflight passa a exigir os guards de isolamento de diretoria.
