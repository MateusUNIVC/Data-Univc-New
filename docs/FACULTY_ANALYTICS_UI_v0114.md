# v0.11.4 — Avaliação Docente pelo Discente · Interface analítica

## Objetivo

A v0.11.4 conecta a experiência de **Avaliação Docente pelo Aluno** ao motor analítico categórico criado na v0.11.3. A tela deixa de usar a projeção manual de nota 0–10 e passa a consumir exclusivamente as APIs `faculty-student` para leitura, filtros, detalhes e novas importações.

Esta etapa **não remove as estruturas legadas do banco nem troca ainda o KPI 02 do Painel Executivo**. A retirada definitiva da projeção antiga fica para a etapa de consolidação seguinte, depois da validação do histórico e das metas.

## Estrutura da tela

A área foi separada em cinco visões, evitando concentrar professor, disciplina, pergunta e ingestão em uma única aba:

1. **Visão Geral** — favorabilidade derivada, participações, docentes, disciplinas, composição e tendência semestral.
2. **Docentes** — lista pesquisável e detalhe do docente preservando curso, disciplina e semestre.
3. **Disciplinas** — lista pesquisável e detalhe da disciplina dentro da identidade do curso.
4. **Perguntas** — distribuição original das alternativas do SEI e filtro entre perguntas de docente e contextuais.
5. **Importações** — qualidade da malha acadêmica, histórico dos lotes e início de um novo fluxo ZIP/XLSX.

## Regras analíticas preservadas

- Não existe conversão implícita para nota 0–10.
- A distribuição original de cada pergunta continua disponível.
- Favorabilidade é um indicador derivado, identificado como tal na interface.
- `Não sei`/`Não sei responder` permanecem visíveis e ficam fora do denominador classificado.
- Categorias desconhecidas suspendem a favorabilidade sintética no recorte.
- Perguntas contextuais continuam consultáveis, mas não entram na síntese do docente.
- `respondent_participations` é apresentado como **participações**, não como quantidade de alunos únicos.

## Filtros

Os filtros são encadeados e vêm do backend:

- semestre;
- curso;
- disciplina;
- docente.

Ao alterar um filtro, opções incompatíveis deixam de ser selecionadas automaticamente. A contagem de contextos mostra o tamanho do recorte corrente.

## Importação na própria área

O novo botão de importação usa o pipeline seguro das v0.11.1/v0.11.2:

1. upload ZIP/XLSX;
2. inspeção sem gravação;
3. resumo de elegíveis, duplicados e descartados;
4. confirmação explícita do semestre quando a fonte não o informa;
5. resolução controlada de curso ambíguo apenas entre candidatos autorizados pelo backend;
6. persistência;
7. atualização do histórico e do diagnóstico de identidade.

A opção padrão em um caso ambíguo é **não importar aquele relatório agora**. O sistema não força Bacharelado/Licenciatura nem cria aliases globais a partir dessa decisão.

## Histórico de importações

Foi adicionado o endpoint somente leitura:

`GET /api/surveys/faculty-student/imports`

Ele reutiliza `survey_imports`, `survey_runs` e `faculty_evaluation_contexts`; nenhuma tabela paralela foi criada. Para cada lote, retorna arquivo, origem, status, semestre, período, questionário, contextos persistidos e quantidade de resoluções manuais.

## Compatibilidade e banco

- Schema canônico: **39**.
- Nenhuma migration nova.
- O frontend legado de Avaliação Docente deixa de ser usado pela navegação dessa área, mas suas funções/tabelas permanecem disponíveis temporariamente para compatibilidade.
- O Painel Executivo ainda pode usar a projeção histórica do KPI 02; sua substituição integral é etapa posterior.

## Verificação

A release inclui `scripts/verify_faculty_student_v0114.py`, que usa SQLite temporário e um XLSX/ZIP real para validar o contrato consumido pela UI: filtros, overview, perguntas, docentes, disciplinas, comparação semestral, qualidade de identidade e histórico de importação.
