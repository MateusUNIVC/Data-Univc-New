# v0.11.3 — Avaliação Docente pelo Discente · Motor analítico e API de consulta

## Objetivo

A v0.11.3 constrói a camada analítica sobre a ingestão e a identidade acadêmica estabilizadas nas versões v0.11.1 e v0.11.2.

Esta etapa ainda **não substitui o frontend legado do KPI 02**. O objetivo é entregar um backend confiável para que a próxima camada visual não precise recalcular indicadores no navegador nem depender de `teacher_evaluations.average_score`.

## Princípio central: preservar a fonte

O relatório real do SEI não fornece nota 0–10 para a avaliação docente. Ele fornece distribuições categóricas por pergunta, como:

- `Sempre`, `Quase sempre`, `Quase nunca`, `Nunca`, `Não sei`;
- `Ótimo/Ótima`, `Bom/Boa`, `Regular`, `Insuficiente`, `Não sei`;
- `Excelente`, `Muito boa`, `Razoável`, `Insuficiente`, `Não sei responder`.

Por isso, a v0.11.3 mantém a distribuição original como fonte de verdade e cria somente um indicador derivado e explicitamente documentado: **favorabilidade**.

Nenhuma resposta é convertida para 0–10.

## Favorabilidade

A classificação usada pelo Data UNIVC é explícita:

### Favoráveis

- Sempre
- Quase sempre
- Ótimo / Ótima
- Bom / Boa
- Excelente
- Muito boa / Muito bom

### Intermediárias

- Regular
- Razoável

### Desfavoráveis

- Quase nunca
- Nunca
- Insuficiente

### Não classificáveis

- Não sei
- Não sei responder
- Não se aplica / Não aplicável

O denominador dos percentuais favorável/intermediário/desfavorável contém somente respostas classificadas nesses três grupos. Respostas `Não sei` permanecem visíveis, mas ficam fora do denominador.

Se uma exportação futura trouxer uma categoria desconhecida, o motor marca `mapping_complete=false` e **não publica percentuais sintéticos** até que o novo rótulo seja revisado. A distribuição original continua disponível.

## Perguntas sobre o docente x perguntas contextuais

A validação dos 603 relatórios reais identificou nove perguntas.

As perguntas 1–8 citam explicitamente `professor` ou `docente` e são classificadas como `teacher`.

A pergunta 9 é:

> Como você avalia o UNIVC EAD quanto a qualidade das disciplinas oferecidas em termos de conteúdo, interação com os professores e recursos de aprendizagem online?

Ela aparece no questionário exportado inclusive em relatórios presenciais. A v0.11.3 não corrige nem remove esse texto da fonte.

Para impedir que uma pergunta institucional/contextual distorça a síntese do professor:

- a pergunta permanece visível na API e em sua distribuição original;
- recebe `analytical_scope = contextual`;
- **não compõe a favorabilidade sintética do docente**;
- a síntese geral informa `favorability_scope = teacher_questions_only`.

A classificação é conservadora: perguntas que citam explicitamente `professor` ou `docente` são `teacher`; as demais são contextuais.

## Respondentes e contagem de participação

O SEI informa quantidade de respondentes por contexto Professor × Disciplina. O backend não possui um identificador individual que permita deduplicar o mesmo estudante entre professores ou disciplinas.

Por isso a API usa o campo:

`respondent_participations`

Ele representa a soma das quantidades informadas em cada contexto e **não deve ser apresentado como quantidade de alunos únicos**.

`answer_selections` representa a soma das alternativas marcadas em todas as perguntas do recorte.

## Filtros encadeados

Endpoint:

`GET /api/surveys/faculty-student/analytics/filters`

Filtros disponíveis:

- semestre;
- curso;
- disciplina;
- professor;
- oferta/turma.

As opções são construídas apenas a partir de contextos efetivamente importados. Cada faceta exclui o próprio filtro ao calcular suas opções, permitindo ao frontend trocar uma seleção sem perder alternativas válidas das demais dimensões.

## Visão geral

Endpoint:

`GET /api/surveys/faculty-student/analytics/overview`

Retorna, no recorte selecionado:

- contextos;
- semestres;
- cursos;
- disciplinas;
- professores;
- ofertas;
- quantidade total de perguntas;
- quantidade de perguntas do docente;
- quantidade de perguntas contextuais;
- participações de respondentes;
- seleções de respostas;
- favorabilidade do docente;
- metodologia completa do cálculo.

## Perguntas

Endpoint:

`GET /api/surveys/faculty-student/analytics/questions`

Para cada pergunta retorna:

- ID e posição;
- texto original;
- escopo analítico (`teacher` ou `contextual`);
- distribuição original agregada;
- classificação de cada alternativa;
- total da fonte;
- total classificado;
- `Não sei`/não classificáveis;
- categorias não mapeadas;
- favorabilidade da própria pergunta.

## Docentes

Endpoints:

- `GET /api/surveys/faculty-student/analytics/teachers`
- `GET /api/surveys/faculty-student/analytics/teachers/{teacher_id}`

A lista oferece uma síntese por identidade global do docente. O detalhe preserva seus contextos acadêmicos e devolve overview + nove perguntas dentro dos filtros aplicados.

O mesmo docente pode aparecer em vários cursos, disciplinas e semestres sem duplicação de pessoa.

## Disciplinas

Endpoints:

- `GET /api/surveys/faculty-student/analytics/disciplines`
- `GET /api/surveys/faculty-student/analytics/disciplines/{discipline_id}`

A identidade de disciplina continua vinculada ao curso, conforme definido na v0.11.2. Disciplinas homônimas de cursos distintos não são consolidadas por nome.

## Cursos

Endpoint:

`GET /api/surveys/faculty-student/analytics/courses`

Fornece agregações por curso sobre os mesmos fatos de `faculty_response_aggregates`.

## Comparação por semestre

Endpoint:

`GET /api/surveys/faculty-student/analytics/semesters/compare`

Permite acompanhar a mesma lógica analítica em cada semestre disponível, com filtros opcionais de curso, disciplina e professor.

Nenhum semestre ausente é fabricado e nenhuma tendência é inferida quando há apenas um período.

## Compatibilidade

- schema permanece em `39`;
- nenhuma migration nova;
- `teacher_evaluations` permanece intacta;
- KPI 02 visual legado continua ativo;
- endpoints de ingestão/identidade v0.11.1/v0.11.2 permanecem compatíveis;
- NPS e Avaliação Institucional respondida por docentes não mudam de contrato.

## Validação real

A varredura das 603 planilhas da Graduação confirmou:

- 15 rótulos distintos de alternativa;
- zero alternativa não mapeada pela v0.11.3;
- perguntas 1, 2, 4, 5, 7 e 8 na escala de frequência;
- perguntas 3 e 6 na escala de qualidade;
- pergunta 9 na escala `Excelente/Muito boa/Razoável/Insuficiente`;
- oito perguntas classificadas como avaliação do docente;
- uma pergunta contextual.

Um recorte real de oito XLSX foi importado em SQLite temporário e exercitou o motor de ponta a ponta. No recorte DCS automaticamente elegível foram persistidos quatro contextos, com nove perguntas, oito de docente, uma contextual e zero categoria desconhecida.

## Testes

`tests/test_faculty_student_v0113.py` cobre:

- denominador explícito de favorabilidade;
- bloqueio de percentuais diante de categoria futura desconhecida;
- separação de pergunta docente e contextual;
- overview sem contagem falsa de alunos únicos;
- filtros encadeados;
- distribuição e favorabilidade por pergunta;
- agrupamento por professor e disciplina;
- detalhe do docente;
- comparação entre semestres.

As suítes v0.11.1, v0.11.2 e v0.11.3 devem passar em conjunto para liberar a versão.

## Próxima etapa

Com ingestão, identidade e analytics estabilizados, a v0.11.4 pode substituir a experiência visual da Avaliação Docente, consumindo exclusivamente esta API para construir as áreas Visão Geral, Docentes, Disciplinas, Perguntas e Importações.
