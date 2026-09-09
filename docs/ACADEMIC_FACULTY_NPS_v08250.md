# Data UNIVC v0.8.25.0 — NPS institucional dos docentes (01C)

## Objetivo

Esta etapa adiciona o terceiro indicador NPS do núcleo acadêmico compartilhado de DTNH/DCS:

- `DTNH-01C` — NPS da Instituição · Docentes;
- `DCS-01C` — NPS da Instituição · Docentes.

A fonte é a **Avaliação Institucional respondida pelos docentes no SEI**. O relatório real é anônimo e não informa curso, disciplina, turma ou identidade do professor respondente. Por isso o fato é institucional/global por semestre, enquanto as metas de gestão permanecem independentes por diretoria.

## Fontes suportadas

O mesmo pipeline aceita:

1. geração direta pelo conector SEI;
2. upload manual de `.xlsx` já baixado;
3. upload de `.zip` contendo um ou mais XLSX do mesmo semestre.

O parser foi construído sobre o layout real fornecido para 2023.1 e 2025.1. Nesse formato:

- coluna `D` contém a pergunta;
- coluna `I` contém a alternativa;
- coluna `M` contém o percentual;
- coluna `P` contém a quantidade;
- metadados de avaliação, período, unidade e questionário são lidos pelos respectivos rótulos do relatório.

Quebras de página que repetem o enunciado/pergunta não duplicam respostas.

## Regra NPS

O Data UNIVC só aceita como fonte oficial do 01C uma pergunta que possua a escala **completa e exata de 0 a 10**.

- 9–10: promotores;
- 7–8: neutros;
- 0–6: detratores;
- NPS = `% promotores - % detratores`.

Questionários sem uma pergunta 0–10 são importados e preservados para auditoria, mas **não geram NPS artificialmente**.

Os dois relatórios usados para validar o parser (2023.1 e 2025.1) seguem o layout esperado, porém não possuem uma pergunta NPS 0–10; portanto são preserváveis, mas não projetam o KPI 01C.

## Persistência

A migration `031_academic_faculty_nps_v08250.sql` cria:

- `survey_faculty_institution_contexts`;
- `survey_faculty_institution_response_aggregates`;
- `survey_faculty_institution_raw_responses`;
- `survey_nps_faculty_sources`;
- `nps_institution_faculty`.

A fonte oficial é única por semestre em toda a instituição. Regenerar a mesma aplicação SEI com conteúdo diferente invalida a projeção antiga antes de substituir os agregados, evitando NPS obsoleto.

## Interface

DTNH e DCS ganham a área **NPS da Instituição · Docentes**, com:

- KPI e meta 01C;
- filtro por semestre;
- janela histórica;
- NPS, respondentes, promotores e detratores;
- evolução histórica;
- composição promotores/neutros/detratores;
- pergunta/fonte oficial;
- tabela histórica;
- atualização pelo SEI ou XLSX/ZIP.

Não existem filtros por curso, professor ou disciplina porque essas dimensões não existem na fonte.

## Metas

As duas diretorias consultam a mesma série factual de docentes, mas mantêm metas próprias:

- `DTNH-01C` aceita somente recorte `TOTAL`;
- `DCS-01C` aceita somente recorte `TOTAL`.

Isso separa corretamente **fato institucional** de **referência gerencial da diretoria**.
