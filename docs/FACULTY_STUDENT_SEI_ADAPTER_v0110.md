# v0.11.0 — Avaliação Docente pelo Discente · Adaptador SEI e escopo de Graduação

## Objetivo

Esta release cria a fundação de ingestão da Avaliação Docente pelo Discente para DTNH e DCS a partir do relatório real de Avaliação Institucional do SEI. O foco desta etapa é preservar corretamente o contexto acadêmico e a distribuição das respostas; o dashboard KPI 02 legado ainda não é substituído nesta versão.

## Escopo protegido do SEI

O fluxo `faculty-student` prepara o relatório com parâmetros fixos de negócio:

- nível do relatório: `AVALIADO` — **Disciplina/Professor**;
- unidade: `2` — **CENTRO UNIVERSITÁRIO VALE DO CRICARÉ - GRADUAÇÃO (SÃO MATEUS-ES)**;
- turno: `0` — **TODOS**;
- perguntas: todas as perguntas do questionário;
- questionário: localizado semanticamente por expressões equivalentes a **aluno/discente avalia professor/docente**, sem depender do ID observado no HAR.

A unidade semipresencial, pós-graduação, técnico, polos e demais unidades não são aceitas neste fluxo.

## Segunda barreira: escopo da diretoria

Mesmo dentro da unidade de Graduação, cada relatório precisa corresponder ao catálogo da diretoria que está importando:

- DTNH só aceita cursos mapeados no catálogo DTNH;
- DCS só aceita cursos mapeados no catálogo DCS;
- modalidade precisa ser compatível com o catálogo;
- relatórios não mapeados aparecem no preview e não podem ser selecionados para importação.

Nenhum curso é criado automaticamente a partir de um rótulo desconhecido do SEI.

## Contrato do XLSX Disciplina/Professor

O parser foi implementado sobre o layout real observado no relatório do SEI e procura metadados pelos rótulos do próprio arquivo. O contrato normalizado preserva:

- unidade de ensino;
- curso;
- disciplina;
- professor;
- avaliação e questionário;
- período de aplicação;
- data/hora de geração;
- pergunta;
- alternativa;
- quantidade de respostas;
- percentual informado pela fonte.

As respostas categóricas são mantidas como distribuições. A importação **não converte** automaticamente `Sempre/Quase sempre/...` ou `Ótimo/Bom/...` em uma nota 0–10 e nunca promove uma pergunta docente implicitamente a NPS.

## Relação acadêmica preservada

Cada registro importado é ligado a:

`semestre → curso → disciplina/oferta → professor → contexto de avaliação → perguntas → alternativas`

A estrutura permite, no mesmo semestre:

- um professor em várias disciplinas;
- um professor em vários cursos;
- dois ou mais professores na mesma disciplina;
- a mesma disciplina com professores diferentes em semestres distintos.

A agregação analítica soma os contadores reais de respostas dos contextos selecionados, evitando média de médias.

## Semestre

O período de aplicação do questionário não é usado para adivinhar o semestre letivo. O parser só sugere `AAAA.1`/`AAAA.2` quando essa informação estiver explicitamente escrita no título da avaliação.

Quando o SEI não identificar o semestre de forma explícita, o preview retorna `semester_confirmation_required=true` e a importação exige confirmação no formato `AAAA-SEM1` ou `AAAA-SEM2`.

Uma fonte que já possua contextos persistidos não pode ser movida silenciosamente para outro semestre em uma reimportação.

## ZIPs grandes

O relatório real pode gerar centenas de XLSX. O fluxo docente possui limite próprio de até 2.000 membros no ZIP, sem alterar o limite do importador genérico/NPS.

Quando o caminho interno do ZIP já identifica claramente uma unidade fora da Graduação, o arquivo é rejeitado antes mesmo da abertura do XLSX, reduzindo custo de inspeção.

## Endpoints introduzidos

- `POST /api/surveys/faculty-student/sei/prepare`
- `POST /api/surveys/faculty-student/sei/report/generate`
- `POST /api/surveys/faculty-student/import/inspect`
- `POST /api/surveys/faculty-student/import/process`
- `GET /api/surveys/faculty-student/scope`

O fluxo utiliza a sessão temporária do conector SEI já existente. Credenciais não são persistidas por esta release.

## Preview da importação

O preview classifica cada relatório como:

- `eligible` — pronto para a diretoria atual;
- `outside_unit` — unidade fora da Graduação São Mateus;
- `wrong_questionnaire` — questionário incompatível;
- `course_out_of_scope` — curso/modalidade fora do catálogo da diretoria;
- `invalid_report` — arquivo que não pôde ser interpretado.

Também retorna contagem de relatórios elegíveis, cursos, professores, disciplinas e respostas por contexto, além da necessidade ou não de confirmação manual do semestre.

## Persistência

A release reaproveita a fundação relacional já existente:

- `teachers`;
- `disciplines`;
- `academic_offerings`;
- `teaching_assignments`;
- `faculty_evaluation_contexts`;
- `faculty_response_aggregates`;
- `faculty_raw_responses`.

Disciplinas descobertas pela primeira importação recebem vigência inicial coerente com o semestre (`janeiro` para SEM1 e `julho` para SEM2).

A reimportação da mesma fonte é idempotente: contextos já existentes são ignorados e não duplicam respostas.

## Compatibilidade

- O KPI 02 legado baseado em `teacher_evaluations` permanece intacto nesta etapa.
- O fluxo `faculty-institution` (docente avaliando a instituição) permanece separado.
- O conector genérico de NPS não é modificado para aceitar o novo layout.
- Schema permanece em **39**; nenhuma migration nova é necessária.

## Próxima etapa

Após a validação com o ZIP real, a v0.11.1 foi dedicada ao endurecimento da ingestão e da idempotência antes de analytics. A camada analítica fica para a v0.11.2, seguida posteriormente pela migração da interface do KPI 02.
