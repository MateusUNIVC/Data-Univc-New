# DPE Professores, Disciplinas e Carga Horária — v0.9.6.16

## Objetivo

Esta release adiciona a camada docente mensal do novo DPE Cost Engine. Ela prepara o rateio futuro do custo de folha com base na carga horária efetivamente atribuída às ofertas econômicas, sem calcular ou postar rateios financeiros nesta etapa.

O princípio é que o cadastro atual de um professor nunca deve reescrever o passado. Por isso, o cadastro institucional é reutilizado como fonte mestre, enquanto cada competência materializa snapshots próprios quando o professor entra em uma atividade ou é conciliado com uma despesa de folha.

## Professor mestre e aliases

A DPE reutiliza `teachers` como cadastro institucional, evitando uma segunda lista independente de docentes. A nova tabela `dpe_teacher_aliases` permite registrar variações exatas recebidas de fontes externas, por exemplo um nome abreviado da folha.

A normalização de nomes ignora acentos, caixa e pontuação. O alias é globalmente único e não pode colidir com o nome principal normalizado de outro professor.

Aliases apoiam sugestão de conciliação, mas não tornam o vínculo financeiro automático.

## Snapshot mensal do professor

`dpe_cost_period_teachers` representa o professor dentro de uma competência. O snapshot guarda o nome, identificador externo e aliases conhecidos no momento da captura.

Depois que setembro/2026 capturou “Professor João da Silva”, renomear o cadastro mestre em outubro não muda a representação histórica de setembro.

## Disciplinas e atividades docentes

`dpe_cost_subjects` mantém o catálogo econômico de disciplinas da DPE.

`dpe_cost_teaching_activities` registra, por competência:

- professor;
- disciplina;
- turma/grupo opcional;
- carga horária total;
- referência de carga opcional;
- origem (`MANUAL`, `EXCEL`, `API`, `REQUEST` ou `OTHER`);
- snapshot de contexto;
- situação ativa/estornada.

Uma atividade só pode ser criada ou editada em competências `DRAFT` ou `REVIEW`.

## Divisão da carga entre ofertas

`dpe_cost_teaching_activity_offerings` liga uma atividade a uma ou mais ofertas já incluídas na competência.

A soma das horas alocadas deve fechar a carga total da atividade, com tolerância máxima de 0,01h.

Exemplos válidos:

- Professor X: 60h de uma disciplina somente em Direito Noturno → 60h para essa oferta.
- Professor X: 60h em Direito e 45h em Administração → atividades/horas direcionadas às respectivas ofertas.
- Aula compartilhada de 90h entre duas ofertas → 45h + 45h, ou outra divisão explícita que totalize 90h.

A interface oferece divisão igual como conveniência, mas permite editar cada valor antes de salvar.

## Conciliação da folha

Despesas oficiais da Central de Despesas com `expense_kind = PAYROLL` entram na fila de conciliação da competência.

O sistema pode sugerir um professor somente quando encontra correspondência exata e única por:

- nome principal normalizado; ou
- alias ativo normalizado.

A sugestão não grava vínculo automaticamente. O usuário precisa confirmar ou escolher outro professor.

Ao confirmar, a despesa recebe:

- `period_teacher_id`;
- `teacher_match_status = CONFIRMED`;
- método de confirmação;
- snapshot mensal do professor.

Se a despesa deixar de ser `PAYROLL`, mudar de competência ou tiver o beneficiário alterado após o vínculo, a associação docente é removida e deve ser conferida novamente.

## O que esta versão ainda não faz

A v0.9.6.16 não calcula quanto da folha deve ir para cada oferta. Ela registra os insumos necessários e torna a conciliação auditável.

O motor financeiro de rateio entra na etapa seguinte e deverá utilizar os snapshots e as horas desta release como base do driver `TEACHER_HOURS`.

## Deploy

Aplicar `database/036_dpe_teaching_workload_v09616.sql` antes de publicar o código. O runtime espera `SCHEMA_VERSION = 36`.

A migration é aditiva sobre o schema 35 e não remove as tabelas financeiras ou históricas anteriores da DPE.
