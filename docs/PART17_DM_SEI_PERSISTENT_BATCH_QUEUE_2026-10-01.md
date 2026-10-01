# Parte 17 — DM · fila persistente e processamento em lotes do SEI

Data: 01/10/2026  
Versão: Data UNIVC v0.13.0  
Schema: 50  
Migration: `050_dm_sei_student_refresh_queue_v0130.sql`

## Objetivo

Eliminar a raiz dos timeouts 504 na atualização individual de alunos da Diretoria de Mestrado sem armazenar credenciais do SEI.

A sincronização de turmas/alunos continua separada da atualização individual. Esta etapa adiciona uma fila persistente e um processador em pequenos lotes.

## Arquitetura

### Fila persistente

Novas tabelas:

- `dm_sei_student_refresh_runs`
- `dm_sei_student_refresh_items`

A execução registra apenas:

- diretoria;
- escopo solicitado;
- IDs dos alunos;
- estado da fila;
- tentativas;
- erros por item;
- timestamps;
- usuário Data UNIVC que iniciou a operação.

Usuário e senha do SEI **não são persistidos**.

### Estados

Execução:

- `PENDING`
- `IN_PROGRESS`
- `COMPLETED`
- `COMPLETED_WITH_ERRORS`
- `CANCELLED`

Item:

- `PENDING`
- `RUNNING`
- `COMPLETED`
- `FAILED`

Itens que ficarem `RUNNING` após uma requisição interrompida podem ser recuperados automaticamente como pendentes após o intervalo de segurança.

## Endpoints

### Criar fila

`POST /api/dm/sei/refresh-runs`

Recebe um único escopo explícito:

- turma;
- conjunto de turmas;
- alunos selecionados;
- todas as turmas.

### Consultar progresso

`GET /api/dm/sei/refresh-runs/{run_id}`

Retorna totais pendentes, em processamento, concluídos e com falha.

### Processar lote

`POST /api/dm/sei/refresh-runs/{run_id}/batch`

As credenciais são recebidas apenas nessa chamada. O servidor reivindica poucos alunos, consulta o SEI, grava as alterações e encerra a requisição antes de buscar o lote seguinte.

## Limites padrão

- `DM_SEI_REFRESH_BATCH_SIZE=4`
- `DM_SEI_REFRESH_BATCH_BUDGET_SECONDS=30`
- `DM_SEI_REFRESH_REQUEST_TIMEOUT_SECONDS=15`

O lote nunca aceita mais de 10 alunos por requisição. Os valores podem ser ajustados por ambiente sem alteração de código.

## Compatibilidade defensiva

O endpoint legado `/api/dm/sei/refresh-students` continua disponível para chamadas pequenas, mas rejeita seleções maiores que o lote seguro. Isso evita que um navegador com JavaScript antigo volte a disparar centenas de consultas numa única requisição.

## Frontend

O modal atual da DM:

1. cria a fila;
2. processa lotes sequencialmente;
3. atualiza o progresso entre lotes;
4. mantém o `run_id` em memória durante a sessão;
5. não persiste a senha;
6. se uma chamada falhar, preserva a fila no banco.

A UX completa de histórico, pausa, retomada após recarregar a página e reprocessamento de falhas fica para o próximo prompt.

## Segurança e consistência

- credenciais SEI não são gravadas em nenhuma tabela;
- cada aluno aparece uma única vez por execução;
- falha individual não remove o progresso dos demais;
- resultados de cada lote são persistidos imediatamente;
- alunos não processados por orçamento de tempo voltam a `PENDING`;
- aplicação de datas continua idempotente;
- conclusão do SEI continua atualizando `defense_date` e confirmando `Titulado`.

## Validação

- fila persistente testada em SQLite com múltiplos lotes;
- lote parcial devolve itens não processados para `PENDING`;
- estado final com erro individual termina em `COMPLETED_WITH_ERRORS`;
- orçamento de tempo interrompe o lote entre alunos;
- endpoint legado tem limite de segurança;
- credenciais não aparecem na migration;
- regressão completa: 245 testes aprovados, 2 ignorados.
