# Parte 18 — DM-QUEUE-04 e hardening dos botões

## Objetivos

1. Corrigir a regressão em que a página do DM podia aparecer carregada, mas sem eventos de clique registrados.
2. Completar a experiência operacional da fila persistente de atualização individual do SEI.

## Causa estrutural da regressão de botões

Na implementação anterior, `bindEvents()` só era chamado depois de `await loadIdentity()`. Qualquer falha de inicialização/identidade antes desse ponto interrompia o `init()` e deixava a página sem listeners. Além disso, alguns bindings usavam acesso direto sem tolerância a elementos ausentes.

A Parte 18:

- chama `bindEvents()` antes das cargas remotas;
- torna o binding idempotente;
- usa optional chaining nos elementos críticos;
- mantém erros de API isolados da navegação local;
- fornece `DM_ASSET_VERSION`, evitando cache cruzado entre patches da mesma versão 0.13.0.

## DM-QUEUE-04

A tela **Integração com o SEI** agora contém uma seção de filas persistentes. Cada fila mostra:

- ID;
- criação;
- escopo;
- progresso processados/total;
- concluídos;
- falhas;
- status;
- ações disponíveis.

Ações:

- **Abrir/Continuar fila**: pede novamente credenciais apenas em memória;
- **Pausar**: grava `PAUSED` e impede novos lotes;
- **Ver falhas**: mostra matrícula/nome/turma/tentativas/último erro;
- **Reprocessar falhas**: retorna somente itens `FAILED` para `PENDING`.

A pausa solicitada durante um lote entra em vigor após o lote atual ser persistido, evitando duplicidade entre abas/requisições concorrentes.

## Banco

Migration: `051_dm_sei_refresh_queue_controls_v0130.sql`.

Ela altera somente o `CHECK` de `dm_sei_student_refresh_runs.status`, adicionando `PAUSED`, e eleva o ledger para schema 51.

## Segurança

Usuário e senha do SEI não são gravados em tabelas, logs de fila ou migrations. Cada lote recebe as credenciais apenas na requisição corrente.

## Testes

- pausa e retomada;
- conclusão de lote que já estava em voo durante pausa;
- listagem de falhas com contexto do aluno;
- reprocessamento seletivo;
- ordenação de filas recentes;
- contratos de frontend/template/router;
- regressão completa: 248 passed, 2 skipped;
- 28/28 arquivos JavaScript válidos no preflight.
