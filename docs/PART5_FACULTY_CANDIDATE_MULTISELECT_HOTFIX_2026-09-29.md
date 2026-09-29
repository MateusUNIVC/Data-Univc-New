# Parte 5 Hotfix — seleção simples de múltiplos cursos na Avaliação Docente

Data: 2026-09-29

## Problema

A Parte 3 introduziu o suporte correto de banco para uma mesma turma docente estar vinculada a mais de um curso sem duplicar respostas. Porém, a interface de importação passou a exigir a revisão de um curso principal e, em seguida, permitia procurar cursos adicionais entre todos os cursos ativos da diretoria.

Isso tornou a importação mais complexa do que a experiência anterior, que já delimitava os cursos candidatos para um relatório ambíguo.

## Correção

A prévia continua usando `candidate_courses`, calculado pelo backend. Para cada contexto que exige resolução:

- somente os cursos candidatos detectados são exibidos;
- cada candidato aparece como checkbox;
- o usuário pode marcar um, dois ou mais cursos;
- nenhum curso fora da lista de candidatos é oferecido na interface;
- se nenhum candidato for marcado, aquele relatório não é importado naquele momento.

O conceito de curso principal permanece apenas como detalhe interno de compatibilidade do modelo. O primeiro candidato marcado ancora o contexto existente; os demais são persistidos em `faculty_evaluation_context_scopes`. As respostas e participações continuam armazenadas uma única vez.

## Segurança

O backend também restringe `shared_course_scopes` aos `candidate_ids` autorizados pelo preview quando o relatório é resolvível. Assim, um payload manual não pode adicionar arbitrariamente outro curso da diretoria a um contexto ambíguo.

## Banco

Nenhuma migration nova. Schema permanece 49.

## Validação

- 184 testes aprovados;
- 2 testes ignorados;
- `node --check static/js/faculty-evaluation.js` aprovado;
- release checks aprovados.
