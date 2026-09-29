# Data UNIVC v0.12.0 — DPE Financial Operations

## Objetivo

A v0.12.0 inicia a reconstrução progressiva da DPE como operação econômica mensal dos cursos presenciais, preservando o Cost Engine existente. Esta versão não reconstrói rateio, fechamento, snapshots ou economics do zero; reorganiza a operação sobre essa fundação.

## Escopo desta versão

- DPE operacional restrito a cursos oficiais ativos da DTNH/DCS com modalidade Presencial;
- nova navegação principal: Visão Geral, Receitas, Despesas, Cursos, Docentes, Distribuição de custos e Fechamento;
- Receitas deixa de ficar escondida dentro de Cursos e passa a ter área operacional própria;
- edição em grade de alunos e receitas, com gravação atômica em lote;
- cálculo preservado de receita líquida e ticket pelo backend;
- Cursos passa a ser leitura econômica, não formulário de receita;
- Docentes passa a distribuir carga em linhas Curso + Horas, com Carga total / Distribuída / Restante antes de salvar;
- professor, disciplina e curso na edição docente recebem busca;
- Despesas explicita Categoria, Setor, Destino econômico e Critério como conceitos distintos;
- catálogo técnico é deslocado para Cadastros e regras;
- novos testes automatizados específicos da DPE v0.12.0.

## Catálogo acadêmico e modalidade

Novos produtos econômicos da DPE precisam estar vinculados a um registro real da tabela `courses`.

Para participar de novas competências, o curso precisa ser:

1. ativo;
2. de DTNH ou DCS ativa;
3. modalidade `Presencial`;
4. vigente no período;
5. possuir produto/oferta econômica válida.

O nome, nível acadêmico e vigência do produto passam a ser derivados do curso oficial. Código econômico, informações de integração e detalhes de oferta continuam pertencendo à DPE.

Ofertas novas ou editadas não aceitam modalidade diferente de `PRESENCIAL`.

### Histórico

A regra nova não reescreve competências históricas. Snapshots já materializados continuam preservados. A restrição é aplicada à criação/materialização operacional de novas competências e à edição de cadastros econômicos novos.

## Receitas

Nova seção principal `Receitas`.

A grade mensal exibe todas as ofertas presenciais incluídas na competência e permite editar diretamente:

- alunos ativos;
- alunos pagantes;
- receita bruta;
- bolsas/descontos;
- outras deduções.

O sistema calcula:

`receita líquida = receita bruta - bolsas/descontos - outras deduções`

`ticket líquido = receita líquida / alunos pagantes`

A gravação usa:

`PUT /api/dpe/cost-engine/periods/{period_id}/economics`

O lote é atômico: se uma linha for inválida, nenhuma linha do lote é persistida.

Validações principais:

- pagantes não podem superar ativos;
- deduções não podem superar receita bruta;
- a oferta precisa pertencer à competência;
- competência precisa continuar editável.

## Cursos

A seção Cursos passa a responder pela leitura do resultado econômico. Lançamento de receita não é mais a tarefa principal desta tela.

A origem factual continua sendo `DPECostOfferingEconomics`, combinada aos custos do Allocation Run aplicável.

## Docentes

O model/repository existente foi preservado.

A mudança é principalmente de experiência:

- professor pesquisável;
- disciplina pesquisável;
- curso/oferta pesquisável;
- somente cursos efetivamente selecionados aparecem na distribuição;
- horas são digitadas por curso;
- total, distribuído e restante são recalculados imediatamente;
- salvar só é habilitado quando a distribuição reconcilia com a carga total.

A validação server-side que já exigia reconciliação permanece como segunda camada de proteção.

## Despesas

A v0.12.0 ainda não implementa toda a mesa de distribuição prevista para a v0.12.1.

Nesta versão a experiência passa a distinguir explicitamente:

- Categoria: o que é o gasto;
- Setor: onde surgiu;
- Destino econômico: quem absorve;
- Critério: como a despesa será dividida.

Após salvar, a interface direciona conceitualmente o próximo passo para Distribuição de custos.

O Allocation Engine existente foi preservado.

## Estruturas preservadas

Não foram reconstruídos:

- `DPECostPeriod` e ciclo DRAFT/REVIEW/CALCULATED/CLOSED;
- snapshots mensais;
- `DPECostExpense`;
- `DPECostTeachingActivity` e alocações;
- Allocation Runs versionados;
- múltiplos destinos;
- drivers DIRECT, TEACHER_HOURS, OFFERING_HOURS, STUDENTS, REVENUE, EQUAL e MANUAL;
- fingerprints;
- oficialização/supersessão de runs;
- economics por oferta;
- checklist de fechamento;
- reabertura e eventos;
- autorização da DPE;
- compatibilidade SQLite/PostgreSQL.

## Banco e migration

**Não há migration nova na v0.12.0.**

- schema esperado: 40;
- migration canônica continua `040_faculty_favorability_kpi_v0115.sql`;
- a v0.12.0 usa estruturas existentes.

## Testes

Adicionado `tests/test_dpe_v0120.py` com regressões para:

- produto econômico exige curso oficial presencial;
- curso EAD é rejeitado no fluxo operacional;
- oferta não presencial é rejeitada;
- nova competência materializa somente cursos oficiais presenciais ativos;
- grade de receita calcula receita líquida corretamente;
- lote de receita é atômico em caso de erro.

Na base completa disponível durante o desenvolvimento:

- 45 testes executados;
- 45 aprovados;
- todos os JS `dpe*.js` passaram em `node --check`;
- módulos Python DPE alterados passaram em `py_compile`;
- seed demonstrativo gerou 16 produtos, 19 ofertas presenciais, 24 professores com atividade, 24 itens de folha e 16 despesas gerais;
- o Allocation Run demonstrativo ficou reconciliado;
- página DPE e os centros principais de API responderam HTTP 200;
- o novo endpoint de receitas em lote respondeu HTTP 200.

## Escopo não implementado nesta versão

Ficam para as etapas seguintes:

- v0.12.1: mesa completa de distribuição, políticas reutilizáveis e preview mensal consolidado;
- v0.12.2: analytics financeiro e waterfall;
- v0.12.3: Excel real, recorrência, cópia de período e ações em massa;
- v0.12.4: evolução do fechamento/governança;
- v0.12.5: homologação visual final, acessibilidade e refinamentos.

## Observação de linhagem do pacote recebido

O projeto completo disponibilizado para esta implementação foi a v0.11.6.5.

Também foi recebido `Data_UNIVC_v0.11.6.7_PATCH_ACADEMIC_RESULTS_STUDENT_CLASSIFICATION`, cujo próprio `PATCH_INSTRUCTIONS.txt` determina aplicação sobre **v0.11.6.6**. A árvore completa v0.11.6.6/v0.11.6.7 não estava presente.

Por segurança, as alterações acadêmicas de v0.11.6.6/v0.11.6.7 não foram simuladas nem parcialmente reconstruídas dentro do ZIP completo desta homologação.

Como os arquivos DPE modificados nesta versão não se sobrepõem aos arquivos funcionais do patch v0.11.6.7, é fornecido também um patch DPE separado para ser aplicado sobre uma árvore completa e já atualizada da v0.11.6.7.

## Homologação visual

O ambiente automatizado permitiu validar HTML, endpoints, CSS/JS estático e testes, mas bloqueou navegação do Chromium local por política administrativa (`ERR_BLOCKED_BY_ADMINISTRATOR`). Portanto, a validação visual fina em Chrome/Firefox real deve fazer parte da homologação antes do deploy de produção.
