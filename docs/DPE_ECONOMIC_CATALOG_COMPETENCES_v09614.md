# DPE Economic Catalog & Competences — v0.9.6.14

A v0.9.6.14 transforma a fundação do DPE Cost Engine em uma superfície operacional de catálogo e competências mensais. O objetivo desta release ainda não é calcular custos: é garantir que o objeto econômico correto exista e que cada competência preserve um retrato auditável das ofertas consideradas naquele mês.

## Catálogo econômico

O novo catálogo não depende de DTNH/DCS para representar a oferta institucional. Ele separa:

- **Produto acadêmico econômico**: por exemplo, Direito, Administração, Técnico em Enfermagem;
- **Oferta econômica**: produto + modalidade + turno + campus/unidade/polo.

Isso permite representar Direito Presencial Matutino e Direito Presencial Noturno como objetos de custeio diferentes, mesmo pertencendo ao mesmo produto acadêmico.

Os níveis suportados pela fundação são Graduação, Técnico, Pós-graduação, Extensão e Outros. O vínculo com `courses` continua opcional e poderá ser usado futuramente para integrar o catálogo econômico ao acadêmico sem tornar a DPE dependente dele.

## Competências

Cada competência nasce em `DRAFT` (Preparação) e pode avançar para `REVIEW` (Conferência) nesta etapa. Os estados `CALCULATED` e `CLOSED` permanecem reservados para as etapas do motor de rateio e fechamento mensal.

Ao abrir uma competência, o sistema pode materializar automaticamente as ofertas cuja vigência contempla o mês. O snapshot guarda os dados econômicos relevantes da oferta naquele instante.

Enquanto a competência estiver em Preparação ou Conferência, o usuário autorizado pode:

- atualizar explicitamente o snapshot;
- incluir/excluir ofertas da competência;
- alterar observações;
- mover entre Preparação e Conferência.

Uma atualização do snapshot preserva exclusões manuais já feitas. Ofertas que deixaram de ser elegíveis são mantidas no histórico da competência, porém passam a ficar excluídas.

## Histórico

Editar o catálogo mestre não altera automaticamente competências materializadas. O histórico só é atualizado por uma ação explícita enquanto a competência ainda for editável. Essa fronteira será usada nas próximas releases para despesas, atividades docentes, receita, drivers e resultados calculados.

## APIs

Leitura:

- `GET /api/dpe/cost-engine/catalog`
- `GET /api/dpe/cost-engine/products`
- `GET /api/dpe/cost-engine/offerings`
- `GET /api/dpe/cost-engine/periods`
- `GET /api/dpe/cost-engine/periods/{period_id}`

Escrita (DPE/EDIT):

- `POST /api/dpe/cost-engine/products`
- `PUT /api/dpe/cost-engine/products/{product_id}`
- `POST /api/dpe/cost-engine/offerings`
- `PUT /api/dpe/cost-engine/offerings/{offering_id}`
- `POST /api/dpe/cost-engine/periods`
- `PUT /api/dpe/cost-engine/periods/{period_id}`
- `POST /api/dpe/cost-engine/periods/{period_id}/refresh-offerings`
- `PUT /api/dpe/cost-engine/periods/{period_id}/offerings/{snapshot_id}`

## Interface

A DPE recebe duas seções novas no menu lateral:

- **Competências**;
- **Catálogo econômico**.

A base financeira e os indicadores legados continuam preservados em paralelo.

## Schema

Não existe migration nova nesta release. O schema esperado permanece **34**, introduzido pela `034_dpe_cost_engine_foundation_v09613.sql`.
