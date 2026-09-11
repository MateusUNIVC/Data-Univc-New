# DADM - Prompt 2: avaliacoes individuais do Tallos

## Escopo

Esta etapa implementa somente a investigacao das avaliacoes individuais dentro de **Pessoas & Setores** do DADM V2.

Nao foram alterados nesta etapa:

- comportamento temporal de um mes versus varios meses;
- graficos de evolucao;
- cobertura de avaliacoes;
- Experiencia;
- Analise Comparativa;
- schema do banco;
- integracao de producao Supabase/Render.

Esses pontos permanecem reservados para as etapas seguintes.

## Backend

Foi criado o endpoint:

`GET /api/dadm/v2/entity/evaluations`

Parametros principais:

- `kind=employee|department`
- `entity_id`
- `from_month`
- `to_month`
- filtros globais ja existentes do DADM
- `page`
- `page_size` (maximo 100)
- `order=newest|lowest|highest`

A consulta utiliza exclusivamente `dadm_tallos_attendances`, considera apenas `rating` valido entre 1 e 10 e mantem a sessao Tallos (`source_id`) como unidade do registro. Protocolos repetidos nao sao deduplicados.

O endpoint seleciona apenas dados operacionais normalizados. `source_payload_json`, `customer_ref` e qualquer conteudo de conversa nao sao enviados ao frontend.

As restricoes de `allowed_departments` continuam aplicadas no SQL, alem da validacao explicita quando a entidade selecionada e um departamento.

## Frontend

O perfil de operador/departamento agora contem **Avaliacoes individuais**.

Operador:

- data;
- protocolo;
- nota;
- TME;
- TMA;
- canal;
- tabulacao;
- status.

Departamento inclui tambem o operador responsavel por cada sessao.

A tabela carrega sob demanda, 20 registros por pagina. Pode ser ordenada por mais recentes, menores notas ou maiores notas.

## Banco

Nenhuma migration foi criada. O schema continua em 33. Os indices existentes em `dadm_tallos_attendances` ja atendem o novo acesso por operador, departamento, data e rating.

## Validacao

Foram adicionados testes para:

- paginacao;
- exclusao de atendimentos sem avaliacao;
- preservacao de sessoes distintas com o mesmo protocolo;
- ordenacao por nota;
- exibicao do operador em perfil de departamento;
- escopo de departamento;
- ausencia de payload/identificacao do cliente na resposta;
- contrato de rota e interface.

A regressao focada do DADM executou 76 testes com sucesso.
