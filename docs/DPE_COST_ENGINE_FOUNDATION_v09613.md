# DPE Cost Engine Foundation — v0.9.6.13

## Objetivo

A v0.9.6.13 cria a fundação do novo motor mensal de custeio da DPE. A release é deliberadamente aditiva: a base financeira e os indicadores DPE existentes continuam intactos e nenhuma despesa, receita ou rateio legado é migrado automaticamente.

O novo domínio parte de quatro princípios:

1. a competência mensal é a fronteira histórica do cálculo;
2. o objeto econômico é uma **oferta acadêmica**, e não apenas um curso genérico;
3. despesas podem ser classificadas por centro de custo e categoria, cada categoria podendo adotar uma regra padrão de rateio;
4. todo rateio futuro deverá persistir a regra e as bases usadas para explicar o valor atribuído a cada oferta.

## Migration 034

Aplicar `database/034_dpe_cost_engine_foundation_v09613.sql` sobre o schema 33. A migration atualiza o ledger para schema 34.

### Tabelas novas

- `dpe_cost_periods`: competências mensais DPE (`DRAFT`, `REVIEW`, `CALCULATED`, `CLOSED`).
- `dpe_academic_products`: produto acadêmico econômico, independente de DTNH/DCS. Pode opcionalmente apontar para `courses`.
- `dpe_academic_offerings`: objeto real de custeio, distinguindo modalidade, turno, campus/unidade/polo.
- `dpe_cost_centers`: setores/centros de custo hierárquicos.
- `dpe_allocation_rules`: regras/driver de rateio.
- `dpe_expense_categories`: categorias hierárquicas com regra padrão opcional.
- `dpe_cost_period_offerings`: snapshot das ofertas pertencentes a uma competência.

## Oferta econômica

`Direito` é um produto. Exemplos de ofertas distintas:

- Direito / Presencial / Matutino / São Mateus;
- Direito / Presencial / Noturno / São Mateus;
- Administração / EAD / Polo X;
- curso técnico / Presencial / Noturno.

A DPE deixa, portanto, de depender da existência de um curso em DTNH/DCS para representar economicamente uma oferta. `source_course_id` é somente uma ponte opcional para o catálogo acadêmico atual.

## Histórico por competência

A competência é persistida em `dpe_cost_periods`. A composição econômica do mês será registrada em `dpe_cost_period_offerings`, que guarda um `offering_snapshot_json`.

Nas próximas etapas, ao abrir/preparar uma competência, o sistema copiará para esse snapshot os atributos relevantes da oferta. Assim, alterar o turno, polo, modalidade ou descrição do cadastro mestre em outubro não altera o retrato utilizado em setembro.

A release ainda não fecha ou reabre competências pela interface; ela apenas cria a estrutura que permitirá esse workflow com segurança.

## Drivers padrão

A migration cadastra sete regras de sistema para DPE:

- `DIRECT`: despesa diretamente atribuída a oferta(s);
- `TEACHER_HOURS`: rateio pela carga horária do professor;
- `OFFERING_HOURS`: rateio pela carga horária acadêmica da oferta;
- `STUDENTS`: rateio pela quantidade de alunos elegíveis;
- `REVENUE`: rateio pela receita elegível;
- `EQUAL`: divisão igualitária;
- `MANUAL`: percentuais/valores informados manualmente.

Essas regras são metadados nesta etapa. **Nenhum cálculo de rateio é executado na v0.9.6.13.**

## Compatibilidade

Nada é removido ou renomeado em:

- `dpe_monthly_revenues`;
- `dpe_course_revenues`;
- `dpe_expenses`;
- `dpe_expense_allocations`;
- `dpe_course_cost_snapshots`;
- indicadores gerenciais/legados da DPE.

A interface atual continua usando a base anterior até a convergência da DPE V2.

## API técnica de verificação

Duas rotas somente de leitura foram adicionadas para homologar a fundação sem habilitar edição prematura:

- `GET /api/dpe/cost-engine/foundation`
- `GET /api/dpe/cost-engine/allocation-rules`

A primeira informa contagens, status possíveis, drivers suportados e se as sete regras de sistema foram semeadas. `write_surface_enabled` permanece `false` nesta release.

## Próxima etapa planejada

A v0.9.6.14 deve criar o **Catálogo Econômico e Competências**: CRUD controlado de produtos/ofertas e abertura/preparação das competências, inclusive materialização do snapshot mensal. Ainda não deve existir motor automático de rateio antes de os cadastros e a preservação histórica estarem homologados.
