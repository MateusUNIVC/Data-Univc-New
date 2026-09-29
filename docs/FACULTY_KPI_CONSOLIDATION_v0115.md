# v0.11.5 — Consolidação do KPI 02 · Favorabilidade Docente

## Objetivo

A v0.11.5 conclui a transição iniciada na v0.11.0. O KPI 02 de DTNH/DCS deixa de usar como fonte oficial a tabela histórica `teacher_evaluations` e a escala manual 0–10. O Painel Executivo, as comparações, as séries e as exportações passam a usar a Avaliação Institucional Discente → Docente importada do SEI e a favorabilidade categórica definida na v0.11.3.

## Fonte oficial

A fonte factual é a camada `faculty_*` alimentada pelo relatório `Disciplina/Professor` do SEI. A projeção executiva é construída a partir de `faculty_evaluation_contexts` e `faculty_response_aggregates`.

A tabela `teacher_evaluations` não é apagada. Ela permanece apenas para rastreabilidade histórica e leitura legada.

## Definição do indicador

A favorabilidade é calculada somente nas perguntas classificadas como avaliação do docente:

`Favorabilidade (%) = Favoráveis ÷ (Favoráveis + Intermediárias + Desfavoráveis) × 100`

Regras:

- `Não sei` e equivalentes permanecem na distribuição original, mas não entram no denominador classificado;
- perguntas contextuais, como o item sobre UNIVC EAD, não entram na síntese do professor;
- qualquer categoria não mapeada suspende o percentual sintético daquele recorte;
- a soma de respondentes entre contextos é apresentada como participações, não como alunos únicos;
- não existe conversão da escala categórica para nota 0–10.

A versão semântica da métrica é `faculty_favorability_pct_v1`.

## Painel Executivo

`DatabaseRepository.academic_dashboard_snapshot()` passa a obter `avaliacao_docente` de `SurveyRepository.faculty_dashboard_projection()`.

Cada linha projetada contém, entre outros campos:

- semestre;
- curso;
- disciplina;
- participações;
- respostas favoráveis;
- intermediárias;
- desfavoráveis;
- classificadas;
- não classificadas;
- não mapeadas;
- percentual de favorabilidade;
- status de validação;
- versão da métrica.

O motor acadêmico soma contagens antes de calcular o percentual. Portanto, não é feita média simples de percentuais entre disciplinas.

## Metas do KPI 02

A migration `040_faculty_favorability_kpi_v0115.sql` adiciona `goals.metric_version`.

Metas antigas de `DTNH-02` e `DCS-02` sem versão são marcadas como:

`legacy_score_0_10`

Essas metas continuam visíveis na governança, porém são excluídas de `get_metas()` e nunca são aplicadas ao painel percentual.

Para voltar a aplicar uma meta do KPI 02, o usuário precisa editar/cadastrar conscientemente uma meta entre 0 e 100. Ela é persistida com:

`faculty_favorability_pct_v1`

Validações adicionais:

- meta, atenção e limite superior devem estar entre 0% e 100%;
- atenção não pode ser maior que a meta;
- uma meta legada não é multiplicada por 10 nem reinterpretada automaticamente.

## Aposentadoria do CRUD legado

Os endpoints de criação, edição e exclusão de `/api/dados/avaliacao_docente` retornam HTTP 410 e direcionam o usuário para a importação oficial do SEI.

Os endpoints antigos:

- `/api/avaliacao-docente/opcoes`;
- `/api/avaliacao-docente/analise`;

também retornam HTTP 410 para impedir que integrações antigas tratem nota 0–10 como KPI oficial.

A leitura de `/api/dados/avaliacao_docente` continua disponível para auditoria e informa `legacy_metric=true`, `metric_version=legacy_score_0_10` e o endpoint do KPI oficial.

## Excel V2 e V3

As duas exportações acadêmicas foram alinhadas ao KPI oficial.

### V2

- a aba Avaliação Docente expõe contagens categóricas;
- favorabilidade e metas são exibidas em percentual;
- comparação entre cursos agrega `Favoráveis ÷ Classificadas`;
- gráfico do KPI 02 usa escala 0–100%;
- não há média ponderada de notas.

### V3

`DADOS_02` passa a armazenar:

- Participações;
- Favoráveis;
- Intermediárias;
- Desfavoráveis;
- Classificadas;
- Não classificadas;
- Não mapeadas;
- Favorabilidade;
- Meta;
- Atenção;
- Status.

As fórmulas do painel e da matriz somam as contagens categóricas e suspendem o resultado quando existem categorias não mapeadas.

## Banco e deploy

Schema esperado: **40**.

Migration obrigatória:

`database/040_faculty_favorability_kpi_v0115.sql`

Ordem:

1. manter todas as migrations anteriores até a 039 aplicadas;
2. aplicar a 040 no PostgreSQL/Supabase;
3. publicar o código v0.11.5;
4. confirmar `/api/health/ready` com `expected=40`, `current=40` e `compatible=true`;
5. revisar as metas legadas do KPI 02 e criar/editar a meta percentual desejada.

## Compatibilidade

Nenhuma resposta histórica da tabela antiga é apagada. A quebra intencional ocorre somente na interpretação operacional: a nota 0–10 deixa de ser aceita como KPI 02 vigente.
