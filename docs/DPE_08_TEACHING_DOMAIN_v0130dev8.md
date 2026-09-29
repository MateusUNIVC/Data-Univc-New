# DPE-08 — Docência: cadastro, vínculo, atividade e custo

Versão: `0.13.0-dev.8`  
Schema: `48` (`048_dpe_teacher_profiles_v0130.sql`)

## Objetivo

Separar quatro conceitos que antes apareciam misturados na Central de Docência:

1. **Identidade institucional do docente** — permanece em `teachers`, compartilhável com outros módulos.
2. **Cadastro DPE do docente** — novo `dpe_teacher_profiles`, que define se o docente pertence ao domínio DPE e seu vínculo padrão.
3. **Vínculo mensal** — `dpe_cost_period_teachers.relationship_type`, preservado por competência.
4. **Atividade e custo** — carga/atividade permanece independente dos lançamentos financeiros; custos continuam vindo das despesas `PAYROLL` conciliadas ao vínculo mensal.

## Regras principais

- A DPE não lista mais automaticamente todos os docentes da tabela institucional `teachers`.
- Um docente institucional existente pode ser incorporado à DPE sem duplicar sua identidade.
- Alterar o vínculo padrão do cadastro não reescreve competências históricas.
- O vínculo mensal pode ser ajustado especificamente para a competência atual.
- Alterar cadastro ou vínculo não cria, altera ou duplica despesas.
- O custo conciliado continua vindo dos lançamentos financeiros e pode ser auditado separadamente da carga docente.
- Os tipos de vínculo suportados são: Não informado, CLT/empregado, Horista, Prestador de serviço e Outro.

## Interface

A área Docência passa a ter quatro responsabilidades visíveis:

- **Atividades docentes** — docente, disciplina/atividade, carga horária e cursos/contextos atendidos.
- **Vínculos e custos** — vínculo naquela competência, carga registrada e custo financeiro conciliado.
- **Cadastro de docentes** — perfil DPE, vínculo padrão, identificador de integração, aliases e status DPE.
- **Disciplinas** — cadastro de disciplinas usado pelas atividades.

O antigo botão “Registrar aula” passa a ser **Registrar atividade**.

## Migration 048

A migration:

- cria `dpe_teacher_profiles`;
- incorpora automaticamente apenas docentes com evidência histórica de uso na DPE;
- adiciona `relationship_type` ao vínculo mensal;
- preserva snapshots e registros históricos;
- habilita RLS para o novo cadastro.

## DEMO

A base demonstrativa contém:

- 24 perfis DPE de docentes;
- 24 vínculos mensais;
- 39 atividades docentes;
- 24 custos docentes conciliados;
- R$ 171.480,00 em custos docentes conciliados;
- vínculos EMPLOYEE, HOURLY e SERVICE_PROVIDER para validação dos cenários.

## Compatibilidade

O Cost Engine, o rateio por carga docente, snapshots, despesas e fechamento foram preservados. Nomes técnicos internos relacionados a `payroll` ainda podem existir na camada de compatibilidade do motor, mas a experiência operacional passa a distinguir explicitamente vínculo, atividade e custo.

## Validação

- suíte DPE: 82 testes aprovados;
- suíte completa: 122 testes aprovados;
- Python compilado;
- JavaScript DPE validado sintaticamente;
- `/api/health/ready`: 200, schema 48 compatível;
- `/dpe`: 200;
- `/api/dpe/cost-engine/teaching-central`: 200;
- 24 docentes / 24 vínculos mensais / 39 atividades retornados na DEMO.
