## Parte 22 - DADM/TALLOS · benchmark e manutenção de armazenamento (01/10/2026)

- conclui `TALLOS-COMPACT-05` sem alterar o schema 53;
- adiciona auditoria reproduzível de tamanho da tabela, índices, TOAST, footprint médio, payload residual e tuplas mortas;
- valida saúde de `rating_source_state`, `normalization_version` e `source_hash`;
- adiciona `scripts/tallos_storage_maintenance.sh audit` e `vacuum`;
- `VACUUM FULL` fica protegido por confirmação explícita e reservado para janela de manutenção;
- encerra o bloco de compactação Tallos e prepara a entrada na arquitetura do Excel Oficial.

Detalhes: `docs/DADM_TALLOS_STORAGE_MAINTENANCE_PART22.md`.

## Parte 21 - DADM/TALLOS · retirada do payload e ingestão compacta (01/10/2026)

- conclui `TALLOS-COMPACT-03` + `TALLOS-COMPACT-04`;
- limpa `source_payload_json` histórico somente depois do contrato compacto da migration 052;
- novas sincronizações calculam `source_hash` em memória e não persistem mais o JSON bruto;
- a coluna legada permanece apenas como placeholder `{}` para compatibilidade;
- auditoria de avaliações permanece idêntica antes/depois da limpeza;
- reimportação idempotente continua baseada em `source_hash`;
- migration obrigatória `053_dadm_tallos_payload_retirement_v0130.sql`; schema esperado passa a **53**.

Detalhes: `docs/DADM_TALLOS_COMPACT_STORAGE_PART21.md`.

## Parte 20 - DADM/TALLOS · fundação de armazenamento compacto (01/10/2026)

- mapeada toda dependência ativa de `source_payload_json` no Centro de Analytics TALLOS;
- a auditoria de avaliações passa a usar um contrato compacto (`valid`, `zero`, `missing`, `invalid`) em vez de reler o JSON;
- adicionados `rating_source_value` e `normalization_version` para rastreabilidade sem manter o payload bruto como dependência funcional;
- registros históricos cujo payload já tenha sido limpo preservam avaliações 1–10 pela coluna normalizada `rating`;
- o payload permanece temporariamente armazenado apenas para a próxima etapa de benchmark e limpeza controlada;
- migration obrigatória `052_dadm_tallos_compact_rating_contract_v0130.sql`; schema esperado passa a **52**.

Detalhes: `docs/DADM_TALLOS_COMPACT_STORAGE_PART20.md`.

## Parte 18 - DM · fila operacional completa e hardening dos botões (01/10/2026)

- corrige a fragilidade em que um erro durante `loadIdentity()` podia impedir o registro de todos os eventos da página DM;
- `bindEvents()` agora é executado antes das cargas remotas, é idempotente e usa bindings defensivos;
- assets do DM recebem um identificador específico (`0.13.0-dmq04`) para evitar mistura de HTML novo com JavaScript antigo em cache;
- Integração com o SEI passa a exibir as filas persistentes recentes, progresso, status, concluídos e falhas;
- permite **Pausar**, **Continuar**, **Ver falhas** e **Reprocessar falhas**;
- fechar/recarregar a página não perde o progresso da fila;
- nenhuma credencial do SEI é persistida;
- migration obrigatória `051_dm_sei_refresh_queue_controls_v0130.sql`; schema esperado passa a **51**;
- regressão completa: 248 testes aprovados e 2 ignorados; 28/28 JavaScripts válidos.

Detalhes: `docs/PART18_DM_QUEUE_UX_BUTTON_HARDENING_2026-10-01.md`.

## Parte 17 - DM · fila persistente e processamento seguro em lotes (01/10/2026)

- atualização individual de início/conclusão/titulação deixa de depender de uma única requisição longa;
- nova fila persistente PostgreSQL registra execução + itens por aluno, sem armazenar credenciais SEI;
- cada chamada processa poucos alunos e grava o resultado antes do lote seguinte;
- itens não processados dentro do orçamento de tempo retornam para a fila;
- falha individual não perde o progresso dos demais alunos;
- endpoint legado bloqueia atualizações em massa para impedir retorno do 504 por clientes antigos;
- frontend atual já percorre os lotes sequencialmente; pausa/retomada avançada ficará para a próxima etapa;
- migration obrigatória `050_dm_sei_student_refresh_queue_v0130.sql`; schema esperado passa a **50**;
- regressão completa: 245 testes aprovados e 2 ignorados.

Detalhes: `docs/PART17_DM_SEI_PERSISTENT_BATCH_QUEUE_2026-10-01.md`.

## Parte 15 - convergência visual NPS e leitura institucional por curso (01/10/2026)

- DTNH, DCS e Reitoria passam a usar o mesmo componente visual de distribuição NPS 0–10;
- gráfico 0–10 de DTNH/DCS adota o mesmo padrão visual compacto da Reitoria;
- gráficos da Reitoria ganham hover detalhado com respondentes, promotores/neutros/detratores, participações e volumes acadêmicos;
- Reitoria passa a comparar o **NPS da instituição por curso**, reconstruído da pergunta institucional oficial por curso;
- o novo indicador é mantido separado do NPS do Curso para evitar confusão metodológica;
- sem migration nova; schema permanece 49;
- regressão completa: 238 testes aprovados e 2 ignorados.

Detalhes: `docs/PART15_NPS_VISUAL_CONVERGENCE_2026-10-01.md`.

## Parte 12 - visão acadêmica geral da Reitoria (01/10/2026)

- nova seção `Indicadores Acadêmicos` em `/reitoria`, somente leitura;
- recorte padrão `Todas · UNIVC`, com filtros por semestre, diretoria, curso e disciplina;
- NPS institucional/alunos, NPS dos cursos, NPS institucional/docentes, favorabilidade docente, aprovação, média das notas e alunos distintos;
- consolidação institucional recalculada pelas contagens-base, sem média de médias;
- distribuições NPS 0–10 reutilizam os agregados oficiais;
- turmas compartilhadas permanecem deduplicadas no total institucional;
- endpoints `/api/reitoria/academic/*` protegidos por `require_fresh_reitoria`;
- sem migration nova; schema permanece 49;
- regressão completa: 219 testes aprovados e 2 ignorados; 28/28 JavaScripts válidos.

Detalhes: `docs/PART12_REITORIA_ACADEMIC_OVERVIEW_2026-10-01.md`.

## Parte 11 - isolamento definitivo entre DTNH e DCS (01/10/2026)

- cache da distribuição NPS 0–10 passa a ser separado por diretoria e é zerado na troca;
- `directorateEpoch` invalida respostas assíncronas iniciadas na diretoria anterior;
- NPS, Resultados, dashboard e Avaliação Docente deixam de aceitar/renderizar respostas atrasadas de outro recorte;
- a troca de diretoria limpa imediatamente gráficos/tabelas acadêmicos e exibe o estado de carregamento da nova diretoria;
- preflight de release passa a validar os guards de isolamento;
- sem migration nova; schema permanece 49;
- regressão completa: 214 testes aprovados e 2 ignorados.

Detalhes: `docs/PART11_DIRECTORATE_ISOLATION_2026-10-01.md`.

## Parte 10 - auditoria final integrada e hardening de domínio (01/10/2026)

- metas de NPS são limitadas a -100/+100 e metas percentuais acadêmicas a 0-100%;
- limiar de atenção e limite superior recebem validações coerentes com indicadores de direção positiva;
- formulário de metas aplica os mesmos limites antes do envio;
- composição NPS no Excel passa a usar eixo 0-100%;
- preflight de release exige `dpe_cost_v2.py`, migration 049 e helpers ativos do bootstrap (`fillConfig` incluído);
- sem migration nova; schema permanece 49;
- regressão final: 208 testes aprovados e 2 ignorados.

Detalhes: `docs/PART10_FINAL_INTEGRATED_AUDIT_2026-10-01.md`.

## Patch operacional 29/09/2026 — Parte 6



## Parte 8 - limpeza de legado docente e hardening de release (29/09/2026)

A interface academica nao carrega mais a implementacao historica da Avaliacao Docente em nota 0-10. O KPI 02 permanece exclusivamente no modulo categórico oficial (`faculty-evaluation.js` / `/api/surveys/faculty-student/*`). Os endpoints antigos continuam respondendo HTTP 410 por compatibilidade. O release check agora executa `node --check` em todos os 26 JavaScripts e valida as referencias de scripts dos templates. Regressao: 196 testes aprovados e 2 ignorados. Schema permanece 49.

- importações de NPS/questionários passam a pré-carregar perguntas e vínculos em conjunto;
- cursos/contextos já importados são consultados uma única vez por run;
- agregados e respostas abertas usam escrita em lote, sem um objeto ORM por resposta;
- NPS institucional dos docentes usa `INSERT ... RETURNING` em massa para os contextos anônimos;
- `SURVEY_IMPORT_BATCH_SIZE` controla o lote (padrão 50; limite interno 10–250);
- benchmark sintético com 50 relatórios: NPS por curso de 153 SELECT + 256 INSERT para 6 SELECT + 9 INSERT;
- benchmark docente institucional: de 152 SELECT + 256 INSERT para 5 SELECT + 9 INSERT;
- metodologia NPS, Educação Física e schema 49 permanecem inalterados; sem migration nova.

Detalhes: `docs/PART6_SURVEY_NPS_BATCH_PERFORMANCE_2026-09-29.md`.

## Patch operacional 29/09/2026 — Parte 5

- importação da Avaliação Docente passa a persistir em lotes com prefetch de identidades e escrita agrupada;
- `FACULTY_IMPORT_BATCH_SIZE` controla o lote (padrão 100; limite interno 25–500);
- dimensões, contextos, escopos e respostas deixam de fazer `SELECT`/`flush` individual por contexto;
- commits por lote permitem retomar uma carga interrompida sem duplicar respostas;
- turmas compartilhadas continuam usando um único contexto de respostas;
- resposta da importação passa a expor métricas operacionais de performance;
- benchmark sintético com 50 contextos: de ~860 operações SQL para 19 SELECT + 13 INSERT + 1 UPDATE;
- schema permanece **49**, sem migration nova.

Detalhes: `docs/PART5_FACULTY_IMPORT_BATCH_PERFORMANCE_2026-09-29.md`.

## Patch operacional 29/09/2026 — Parte 4

- gráficos de NPS/comparação por curso preservam o nome completo, sem reticências após duas linhas;
- altura e margem do gráfico se adaptam ao número real de linhas do rótulo;
- tooltip e `<title>` do SVG continuam exibindo o nome integral;
- alteração compartilhada no renderer de barras, sem mudança de cálculo/API/schema.

Detalhes: `docs/PART4_NPS_LONG_COURSE_LABELS_2026-09-29.md`.

## Patch operacional 29/09/2026 — Parte 3

- Avaliação Docente passa a usar Ano letivo + Semestre na importação, preservando internamente `AAAA-SEM1/2`;
- turmas compartilhadas podem ser vinculadas a dois ou mais cursos sem duplicar respostas ou participantes;
- nova tabela `faculty_evaluation_context_scopes` preserva o vínculo principal e adiciona escopos acadêmicos;
- analytics por curso enxerga o contexto em cada curso associado, enquanto a visão global deduplica o mesmo contexto/resposta;
- NPS vindo diretamente do SEI atual interpreta `Educação Física` como Licenciatura somente no adapter da fonte;
- uploads manuais/legados com `Educação Física` continuam ambíguos e exigem resolução explícita;
- schema esperado passa a 49 com `049_academic_faculty_context_scopes_v0130.sql`.

Detalhes: `docs/PART3_ACADEMIC_IDENTITY_SHARED_CLASSES_2026-09-29.md`.

## Patch operacional 29/09/2026 — Parte 2

- filtros de disciplina pesquisáveis na Visão Geral e em Aprovações e Notas;
- componente compartilhado `DataUNIVC.searchableSelect`, também usado pela Avaliação Docente;
- pesquisa tolerante a acentos e navegação por teclado;
- cache busting de CSS/JS usando o fingerprint real do build;
- mantém o hotfix do SEI para Educação Física - Licenciatura.

Detalhes: `docs/PART2_SEARCHABLE_DISCIPLINE_FILTERS_2026-09-29.md`.

## v0.13.0 — Production

Release de produção consolidada do Data UNIVC, baseada na árvore acadêmica v0.11.6.7 e na DPE v0.13 reestruturada.

- schema esperado: 49;
- DPE moderna consolidada e legado operacional DPE-01/02/03 bloqueado;
- base acadêmica v0.11.6.7 integrada;
- autenticação obrigatória em produção;
- cookies seguros;
- rate limit de login habilitado na configuração de produção;
- API docs desabilitadas em produção;
- banco deve ser migrado antes do start da aplicação.

Consulte `docs/PRODUCTION_RELEASE_v0130.md` antes do deploy.

## v0.13.0-dev.15 — Reconciliação global com base acadêmica v0.11.6.7

- Substitui definitivamente a base acadêmica v0.11.6.5 pela árvore completa v0.11.6.7.
- Integra as correções de Resultados Acadêmicos/SEI da v0.11.6.6 e a classificação gerencial por aluno da v0.11.6.7.
- Preserva integralmente a DPE consolidada até DPE-14, incluindo o bloqueio do legado, Cost Engine, Excel moderno, Metas/Planos e testes de release.
- `repository.py` foi reconciliado por merge de três vias usando v0.11.6.5 como ancestral comum; não houve conflito textual.
- Schema permanece **48**; nenhuma migration nova é necessária para a reconciliação acadêmica.
- Esta entrega elimina o bloqueador de base acadêmica antes do release global v0.13.0.

Detalhes: `docs/BASE_RECONCILIATION_v0130dev15.md`.

## v0.13.0-dev.14 — DPE-14: Auditoria final e bloqueio do legado

- Remove importador e builder Excel históricos DPE-01/02/03 do runtime.
- Aposenta `/api/dpe/import`, `/api/dpe/modelo/{indicator_code}` e o seed antigo `/api/dpe/demo`.
- Bloqueia dashboard, medições e Excel gerenciais genéricos para o escopo DPE com HTTP 410.
- Mantém somente `catalog`, `targets` e `actions` genéricos usados pela gestão moderna; KPIs continuam calculados diretamente do Cost Engine.
- Remove cálculos DPE-01/02/03 restantes de `management_service.py` e impede a carga demonstrativa genérica de recriar medições antigas.
- Adiciona `scripts/run_release_checks.py` para compile Python, sintaxe JS, pytest e travas anti-regressão do legado.
- Frontend ativo não contém referências a DPE-01/DPE-02/DPE-03.
- Schema permanece **48**; regressão final: **152 testes aprovados**.
- O pacote ainda exige reconciliação da base acadêmica v0.11.6.5 com v0.11.6.6 + patch v0.11.6.7 antes de um release global de produção.

Detalhes: `docs/DPE_14_FINAL_AUDIT_v0130dev14.md`.

## v0.13.0-dev.13 — DPE-13: Excel analítico moderno

- A exportação completa `/api/dpe/excel` passa a ler diretamente Receita, Despesas, Docência, Distribuição, Resultado, Metas e Fechamento do Cost Engine.
- O workbook possui painéis derivados por fórmulas e bases visíveis em Excel Tables: `BASE_CURSOS`, `BASE_RECEITAS`, `BASE_DESPESAS`, `BASE_DOCENCIA` e `BASE_RATEIOS`.
- `PAINEL`, `RESULTADO` e `CURSOS` usam as próprias bases do arquivo, evitando uma segunda regra financeira dentro do Excel.
- A exportação individual antiga `/api/dpe/excel/{indicator_code}` foi aposentada; DPE-01/02/03 não alimentam o Excel moderno.
- A interface DPE ganhou botão `Exportar Excel`, sempre ligado à competência selecionada.
- Schema permanece **48** e a regressão completa encerrou com **147 testes aprovados**.
- Na DEMO 2026-09, os somatórios das bases exportadas coincidem com o sistema: R$ 2.778.568 de receitas, R$ 495.180 de despesas, R$ 467.580 distribuídos e R$ 2.283.388 de resultado institucional.

Detalhes: `docs/DPE_13_MODERN_EXCEL_v0130dev13.md`.

## v0.13.0-dev.12 — DPE-12: Navegação e UX final

A DPE foi reorganizada em três blocos claros: **Fluxo do mês**, **Resultados e gestão** e **Configuração e ferramentas**. A área analítica antes chamada apenas de “Cursos” passa a se chamar **Resultado por curso**, eliminando ambiguidade com o cadastro **Cursos e contextos**.

O fluxo mensal também ganhou uma faixa sequencial de cinco etapas — Receitas, Despesas, Docência, Distribuição e Fechamento —, enquanto o topbar passa a adaptar título, explicação e ação principal à seção atual. A última seção visitada é restaurada durante a mesma sessão do navegador. Esta etapa não altera schema nem cálculos financeiros.

## v0.13.0-dev.11 — DPE-11: Metas e Planos ligados ao Cost Engine

- Metas passam a comparar automaticamente o objetivo com o valor real da competência.
- Nova camada `dpe_management.py` compõe os mesmos dados de Receita, Despesa, Docência, Distribuição e Analytics; nenhum KPI é lançado manualmente.
- A tela mostra `Dentro da meta`, `Atenção`, `Fora da meta` e `Sem apuração`.
- Planos de ação exigem métrica canônica e podem ser criados diretamente a partir de um desvio.
- DPE-01/DPE-02/DPE-03 continuam apenas como compatibilidade histórica para medições/Excel antigos e não aparecem no fluxo gerencial atual.
- Métricas herdadas sem equivalência segura são preservadas como histórico, mas bloqueadas para novas metas/planos.
- A DEMO possui seis metas canônicas e um plano de ação.
- Schema permanece **48**; nenhuma migration nova.
- Regressão completa: **138 testes aprovados**.

Detalhes: `docs/DPE_11_GOALS_ACTIONS_v0130dev11.md`.

## v0.13.0-dev.10 — DPE-10: Resultado consolidado e fonte única de receita

- O ledger `dpe_revenue_entries` é a única fonte de verdade de receita do Cost Engine moderno.
- Economics deixa de armazenar receita no ORM/runtime e fica restrito a alunos ativos e metadados auxiliares.
- Analytics, Visão Geral V2, Fechamento, distribuição proporcional à receita e Produtividade passam a ler o ledger diretamente.
- Resultado institucional usa todas as receitas do ledger menos todas as despesas oficiais; resultado por curso usa somente receitas atribuídas ao curso menos custos atribuídos pelo cálculo oficial.
- Receita e despesa institucionais permanecem fora da margem dos cursos, salvo quando uma receita é explicitamente vinculada a um curso/contexto.
- Receita de curso igual a zero é preservada como confirmação explícita e não é confundida com ausência de preenchimento.
- A grade de alunos ativos agora é validada por completo antes de qualquer mutação, evitando atualização parcial em lotes inválidos.
- A cópia de mês anterior reaproveita separadamente receita de curso do ledger e alunos ativos, sem recriar bruto, bolsas, deduções, pagantes ou ticket.
- Não há migration nova nesta etapa: schema 48 permanece vigente. Em bancos já migrados, colunas físicas antigas da tabela Economics ficam inertes e fora do runtime até a limpeza física final.

## v0.13.0-dev.9 — DPE-09: Distribuição orientada à decisão

- Mantém o motor de distribuição existente, mas reorganiza a experiência em torno da pergunta **“Como deseja distribuir esta despesa?”**.
- Despesa **Direta** mostra somente o destino de 100%; não oferece critérios contraditórios.
- Despesa **Compartilhada** pode usar atividades do docente, carga horária, alunos, receita, divisão igual ou definição manual.
- Despesa **Institucional** continua fora da distribuição por curso.
- O backend não permite mais que uma Compartilhada use `DIRECT` como atalho para mudar silenciosamente de tratamento.
- Configurações reutilizáveis/políticas foram movidas para uma área avançada do modal.
- A prévia em reais continua obrigatória e a memória técnica do cálculo permanece preservada.
- Nenhuma migration nova: schema permanece **48**.
- Regressão completa: **126 testes aprovados**.

Detalhes: `docs/DPE_09_ALLOCATION_UX_v0130dev9.md`.

## v0.13.0-dev.8 — DPE-08: Docência por domínio

- Separa identidade institucional, cadastro DPE, vínculo mensal, atividade docente e custo conciliado.
- Novo `dpe_teacher_profiles`: a DPE passa a listar somente docentes incorporados ao próprio domínio, sem misturar automaticamente cadastros de outros módulos.
- Docente institucional existente pode ser adotado pela DPE sem duplicação.
- Vínculo padrão e vínculo da competência são independentes; alterações atuais não reescrevem o histórico.
- Custo continua vindo dos lançamentos financeiros conciliados e não é criado ao editar o docente/vínculo.
- Interface reorganizada em **Atividades docentes**, **Vínculos e custos**, **Cadastro de docentes** e **Disciplinas**.
- “Registrar aula” passa a ser **Registrar atividade**.
- Migration `048_dpe_teacher_profiles_v0130.sql`; schema 48.
- Regressão completa: **122 testes aprovados**.

Detalhes: `docs/DPE_08_TEACHING_DOMAIN_v0130dev8.md`.

## v0.13.0-dev.7 — DPE-07: Tratamento econômico de Despesas

- Despesas passam a ter tratamento explícito: **Direta**, **Compartilhada** ou **Institucional**.
- Direta exige um curso/contexto de destino e recebe 100% do valor sem distribuição adicional.
- Compartilhada segue para a área Distribuição, onde o critério entre cursos é revisado.
- Institucional participa do resultado institucional e fica fora do rateio dos cursos.
- “Selecionar visíveis” agora fica realmente desabilitado quando não há itens editáveis e explica competências protegidas.
- Importação Excel aceita tratamento Compartilhada/Institucional; Direta é registrada na tela porque exige destino individual.
- Fechamento e rateio conciliam somente despesas distribuíveis; institucionais não geram pendência artificial.
- Migration `047_dpe_expense_scope_v0130.sql`; schema 47.
- Regressão completa: **117 testes aprovados**.

Detalhes: `docs/DPE_07_EXPENSE_TREATMENT_v0130dev7.md`.

## v0.13.0-dev.6 — DPE-06: Revenue Ledger simplificado

- Nova fonte de verdade `dpe_revenue_entries` + `dpe_revenue_categories`.
- Receita por curso passa a ser um valor direto; bolsas, deduções, receita bruta, pagantes e ticket deixam de fazer parte do lançamento de Receita.
- Outras receitas podem ser institucionais ou explicitamente vinculadas a curso/contexto.
- Categorias padrão: receita de curso, aluguel de salas, aluguel de quadras, utilização de estrutura, utilização de filial, serviços, eventos e outras receitas; categorias próprias podem ser criadas.
- Migration `046_dpe_revenue_ledger_v0130.sql`; schema 46.
- A ponte `net_revenue` foi removida do runtime no DPE-10; o ledger passa a ser a fonte única do Cost Engine moderno.
- Fechamento não exige mais alunos pagantes/ticket; alunos ativos são dado auxiliar e só devem ser necessários quando uma regra específica depender deles.

## v0.13.0-dev.5 — DPE-05: Curso como entidade principal

A DPE deixa de restringir a operação a cursos presenciais. **Curso** passa a ser a entidade principal, e contextos adicionais são opcionais para separar turma, turno, unidade, local ou modalidade quando isso realmente for necessário.

- Schema esperado: **45** (`database/045_dpe_course_contexts_v0130.sql`).
- Cursos ativos de DTNH/DCS de qualquer modalidade podem ser vinculados à DPE.
- Cada curso possui um contexto-base técnico automático; ele não aparece como um cadastro adicional para o usuário.
- Contextos adicionais substituem o contexto-base na competência quando existirem, evitando dupla contagem.
- `offering_id` e `dpe_academic_offerings` permanecem apenas como infraestrutura interna compatível com docência, rateio, economics e snapshots.
- Snapshots novos registram `is_default_context` e `context_kind`.
- Regressão completa: **104 testes aprovados**.
- Smoke local: schema 45 compatível, `/dpe` e `/api/dpe/cost-engine/catalog` em 200; interface sem “Oferta presencial”.

Detalhes: `docs/DPE_05_COURSE_CONTEXTS_v0130dev5.md`.

## v0.13.0-dev.3 — DPE-03: backend legado aposentado

A DPE v0.13 está consolidada no Cost Engine também no backend. Nesta etapa foram removidas do runtime as gerações DPE v0.4 e Finance v0.7.7: APIs, repositories, modelos ORM, seeds e Excel v0.4. A migration `043_dpe_legacy_backend_retirement_v0130.sql` arquiva qualquer registro existente em `dpe_legacy_retirement_archive` antes de remover as oito tabelas operacionais antigas.

- Schema esperado: **43**.
- Cost Engine permanece como única base operacional ativa da DPE.
- DPE-01/02/03 de `management_indicator_*`, Metas e Planos continuam temporariamente para a próxima consolidação de domínio.
- SQLite local também arquiva/remove tabelas antigas ao passar pelo launcher de inicialização.
- Regressão completa: **92 testes aprovados**.
- Smoke local: `/api/health/ready`, `/dpe`, `/api/dpe/cost-engine/foundation` e `/api/dpe/cost-engine/analytics` validados; rotas Finance/v0.4 aposentadas retornam 404.

Detalhes: `docs/DPE_03_BACKEND_LEGACY_RETIREMENT_v0130dev3.md`.

## v0.12.5.1 — DPE Demo + Navigation Hotfix

- Corrige o problema em que a tela **Receitas** permanecia visível ao navegar para Despesas, Cursos, Docentes, Distribuição de custos, Fechamento e demais áreas. A causa era uma regra CSS específica de Receitas que sobrescrevia o `display:none` das seções inativas.
- A navegação agora possui uma proteção defensiva: somente a `.page-section.active` pode permanecer visível.
- Inclui `univc_dpe_demo.db` já populado para homologação local, com 16 cursos, 19 ofertas presenciais, docentes, folha, 40 despesas, alunos/receitas, políticas e rateio oficial reconciliado.
- Para abrir com dados fictícios no Windows, execute **`TESTAR_DPE_DEMO.bat`**. Para restaurar a base original fictícia, use **`RESETAR_DPE_DEMO.bat`**.
- Dados DEMO continuam isolados de produção (`DPE_LOCAL_DEMO=true` + SQLite local).
- Sem migration nova: schema 42.

## v0.12.5 — DPE Homologação e Refinamento · experiência final

A v0.12.5 encerra a sequência de reconstrução do DPE com foco em responsividade, acessibilidade e consistência de UX, sem alterar fórmulas financeiras nem criar nova migration.

- schema **42**, sem migration nova nesta versão;
- última migration obrigatória: `database/042_dpe_productivity_v0123.sql`;
- gerenciamento consistente de foco/teclado nos modais;
- confirmação institucional substitui `confirm()`/`prompt()` nas ações críticas DPE;
- estados de carregamento, alerta, erro e vazio padronizados;
- abas e combobox docente refinados para teclado/ARIA;
- tooltips administrativos em conceitos gerenciais;
- responsividade e legibilidade de tabelas/formulários refinadas;
- 80 testes acumulados aprovados na base de homologação;
- detalhes técnicos em `docs/DPE_HOMOLOGATION_REFINEMENT_v0125.md`;
- o ZIP completo desta homologação continua partindo da árvore completa v0.11.6.5; use o patch DPE cumulativo desta entrega sobre a árvore completa v0.11.6.7 para preservar as correções acadêmicas v0.11.6.6/v0.11.6.7.

---

## v0.12.4 — DPE Fechamento e Governança · fechamento rastreável

A v0.12.4 transforma o fechamento em um checklist operacional real, exige revisão explícita dos alertas atuais, amplia a auditoria das ações financeiras críticas e adiciona um fluxo seguro para voltar de `CALCULATED` para `REVIEW` sem apagar o cálculo anterior.

- schema **42**, sem migration nova nesta versão;
- última migration obrigatória: `database/042_dpe_productivity_v0123.sql`;
- checklist com docentes reconciliados, resultado econômico e governança;
- alertas atuais precisam ser revisados antes de fechar;
- ação **Voltar para conferência** com justificativa e supersessão do run oficial;
- trilha de auditoria visível na própria tela de Fechamento;
- auditoria ampliada para despesas, receitas, docentes, políticas, rateio, produtividade e competência;
- 73 testes acumulados aprovados na base de homologação;
- detalhes técnicos em `docs/DPE_CLOSURE_GOVERNANCE_v0124.md`;
- o ZIP completo desta homologação continua partindo da árvore completa v0.11.6.5; use o patch DPE cumulativo desta entrega sobre a árvore completa v0.11.6.7 para preservar as correções acadêmicas v0.11.6.6/v0.11.6.7.

---

## v0.12.3 — DPE Productivity · menos retrabalho no ciclo mensal

A v0.12.3 adiciona importação real de despesas por Excel com prévia e validação, cópia controlada de receitas/quadro docente do mês anterior, despesas recorrentes idempotentes, classificação em massa e aplicação em massa de políticas. O schema esperado passa a 42 com `database/042_dpe_productivity_v0123.sql`.

Detalhes: `docs/DPE_PRODUCTIVITY_v0123.md`.

---

## v0.12.2 — DPE Financial Analytics · leitura econômica e histórica

A Visão Geral passa a consolidar o mês e o histórico usando a mesma fonte de verdade do fluxo operacional: receitas, despesas, snapshots e Allocation Runs oficiais. A nova camada é somente leitura, não cria uma base analítica paralela e rejeita rateios oficiais cujo fingerprint tenha ficado desatualizado.

- schema **41**, sem migration nova nesta versão;
- última migration obrigatória: `database/041_dpe_allocation_policies_v0121.sql`;
- KPIs com comparação contra o mês anterior;
- evolução Receita líquida × Despesas × Resultado e Margem operacional;
- análises por categoria, setor e curso;
- Ticket, custo por aluno e composição de custos;
- histórico individual do curso e waterfall financeiro;
- overhead administrativo **não é inferido** sem classificação contábil explícita;
- 61 testes acumulados aprovados na base de homologação;
- detalhes técnicos em `docs/DPE_ANALYTICS_v0122.md`;
- o ZIP completo desta homologação continua partindo da árvore completa v0.11.6.5; use o patch DPE cumulativo desta entrega sobre a árvore completa v0.11.6.7 para preservar as correções acadêmicas v0.11.6.6/v0.11.6.7.

---

## v0.12.1 — DPE Cost Distribution Workbench · distribuição de custos

A Distribuição de custos passa a funcionar como mesa de trabalho: destino, critério e situação ficam visíveis, a prévia individual continua obrigatória e uma nova prévia consolidada mostra o impacto do mês antes de gerar outro Allocation Run. Políticas reutilizáveis permitem reaproveitar tratamentos recorrentes sem reescrever histórico.

- schema **41**;
- migration obrigatória: `database/041_dpe_allocation_policies_v0121.sql`;
- políticas reutilizáveis com aplicação sempre revisada pelo usuário;
- seletor pesquisável para múltiplos destinos;
- prévia consolidada por curso/oferta com custo, receita, resultado e margem;
- 53 testes acumulados aprovados na base de homologação;
- detalhes técnicos em `docs/DPE_COST_DISTRIBUTION_v0121.md`;
- o ZIP completo desta homologação continua partindo da árvore completa v0.11.6.5; use o patch DPE cumulativo desta entrega sobre a árvore completa v0.11.6.7 para preservar as correções acadêmicas v0.11.6.6/v0.11.6.7.

---

## v0.12.0 — DPE Financial Operations · fluxo operacional

A DPE passa a operar somente com cursos oficiais presenciais, ganha Receitas como area propria, edicao mensal em grade e uma distribuicao docente reconciliavel antes do salvamento. O motor existente de custos, rateio, snapshots e fechamento foi preservado.

- schema 40, sem migration nova;
- detalhes tecnicos em `docs/DPE_FINANCIAL_OPERATIONS_v0120.md`;
- o ZIP completo desta homologacao foi construido sobre a arvore completa v0.11.6.5; para preservar as correcoes 0.11.6.6/0.11.6.7, use o patch DPE desta entrega sobre a arvore completa v0.11.6.7.

---

## v0.11.6.5 — Resultados Acadêmicos · alunos distintos e filtros de reprovação

Refinamento de UX para separar pessoas de resultados disciplinares e permitir investigar reprovações diretamente pelos cards.

- adicionada contagem de **alunos distintos** no recorte;
- classificação reconciliável: aprovados no recorte + com reprovação + sem fechamento = total de alunos;
- reprovação por nota e por falta passam a exibir **alunos distintos**;
- cards de situação funcionam como filtros rápidos para os registros individuais;
- novo filtro server-side de aprovado/reprovado/nota/falta/pendência;
- segundo gráfico passa a mostrar a evolução da população de alunos distintos;
- semestre mais recente é selecionado por padrão na primeira abertura do módulo;
- KPI de aprovação por disciplina permanece inalterado;
- nenhuma migration nova; schema continua em **40**;
- regressão acumulada ampliada para **40 testes**.

Detalhes: `docs/ACADEMIC_RESULTS_STUDENT_UX_v01165.md`.

---

## v0.11.6.4 — Resultados Acadêmicos · importação protegida para grandes volumes

Hardening da importação de aprovação/resultados para reduzir picos de RAM e impedir que uma carga completa dependa de uma única requisição/transação.

- parser SEI em `read_only=True` com leitura streaming;
- gravação em lotes de 500 por padrão;
- cache de matrículas liberado entre lotes;
- cursos do SEI processados sequencialmente pela interface;
- cursos/lotes já concluídos permanecem persistidos após falha e podem ser reenviados sem duplicação;
- processamento pesado não bloqueia o event loop do FastAPI;
- upload manual do modelo de resultados também usa lotes;
- benchmark sintético com 10.000 vínculos reduziu o pico RSS local de ~217 MB para ~158 MB;
- nenhuma migration nova; schema continua em **40**;
- regressão acumulada ampliada para **35 testes**.

Detalhes: `docs/ACADEMIC_RESULTS_IMPORT_HARDENING_v01164.md`.

---

## v0.11.6.3 — Avaliação Docente · segunda geração SEI + comboboxes pesquisáveis

Correção do fluxo direto até o ZIP final e refinamento dos filtros da Avaliação Docente.

- O conector agora reproduz as **duas etapas de geração** observadas no HAR real do SEI.
- Após a primeira conclusão, identifica `formQuestionarioSelecionar` e aciona apenas o botão global de geração do pacote.
- Executa um segundo ciclo de `statusPanelBaixa` e só baixa quando o SEI informa `DownloadRelatorioSV`.
- Mantém compatibilidade com relatórios que eventualmente disponibilizem o download já na primeira fase.
- Curso, Disciplina e Docente passam a usar **combobox pesquisável**, com busca sem acentos, teclado e limpeza da seleção.
- A lógica encadeada dos filtros continua usando os facets oficiais do backend.
- Nenhuma migration nova; schema continua em **40**.
- Regressão completa: **30/30 testes aprovados**.

Detalhes: `docs/FACULTY_SEI_PHASE2_COMBOBOX_v01163.md`.

---

## v0.11.6.2 — Correção do acesso direto ao SEI na Avaliação Docente

Correção crítica no DTNH/DCS: o botão principal da Avaliação Docente estava rotulado como importação do SEI, mas executava o clique do input local de arquivo. A v0.11.6.2 separa explicitamente os dois caminhos.

- **Buscar direto no SEI** abre autenticação temporária, pesquisa as aplicações da Avaliação Institucional e permite selecionar a avaliação correta.
- O fluxo direto usa os endpoints já existentes para selecionar a aplicação, preparar o questionário de discente avaliando docente e gerar o relatório no SEI.
- O escopo permanece protegido no backend: **Disciplina/Professor**, **Graduação São Mateus**, **todos os turnos** e **todas as perguntas**.
- **Usar XLSX/ZIP já baixado** permanece disponível como contingência e é a única ação que abre o seletor de arquivos local.
- O relatório gerado diretamente no SEI entra na mesma prévia segura de semestre, identidade acadêmica e duplicidade antes da gravação.
- Nenhuma migration nova; schema continua em **40**.
- Incluído teste de regressão para impedir que o botão direto volte a acionar `input.click()`.

## v0.11.6 - Avaliação Docente · Refinamento de produção

Esta etapa transforma o KPI 02 consolidado em uma leitura operacional para uso recorrente, sem alterar a definição da favorabilidade.

Principais mudanças:
- a área abre no semestre mais recente com dados, evitando misturar todo o histórico na primeira leitura;
- novo resumo operacional combina resultado atual, semestre anterior, variação em pontos percentuais, meta, status, cobertura, qualidade e última importação;
- comparação semestral passa a carregar meta/status por período e variação longitudinal;
- gráfico histórico exibe a meta vigente e status de cada semestre;
- pendências passam a oferecer ação direta para Metas, Importações, Perguntas ou nova importação;
- área de Importações expõe mensagens de bloqueios/avisos e auditoria do usuário responsável pelo lote;
- histórico de importação reutiliza `audit_log`, sem nova tabela;
- nenhuma migration nova: schema permanece 40.

Detalhes: `docs/FACULTY_PRODUCTION_REFINEMENT_v0116.md`.

---

## v0.11.5 - Avaliação Docente · Consolidação do KPI 02 em favorabilidade

Esta etapa conclui a substituição do KPI 02 histórico em nota 0–10 pela favorabilidade categórica da Avaliação Institucional Discente → Docente importada do SEI.

Principais mudanças:
- Painel Executivo, séries, comparações e exportações passam a usar a projeção oficial `faculty_*`;
- a tabela `teacher_evaluations` permanece somente como histórico/auditoria e deixa de alimentar o KPI;
- favorabilidade é agregada pelas contagens `favoráveis ÷ classificadas`, nunca por média simples de percentuais;
- perguntas contextuais e respostas `Não sei` não contaminam a síntese docente;
- categorias não mapeadas suspendem o percentual do recorte;
- CRUD e endpoints analíticos antigos de nota 0–10 são aposentados para uso operacional;
- metas antigas do KPI 02 são marcadas como `legacy_score_0_10` e deixam de ser aplicadas automaticamente;
- novas metas do KPI 02 exigem percentual entre 0 e 100 e usam `faculty_favorability_pct_v1`;
- Excel V2/V3 passam a usar favorabilidade e contagens categóricas;
- migration `040_faculty_favorability_kpi_v0115.sql`; schema esperado 40.

Detalhes: `docs/FACULTY_KPI_CONSOLIDATION_v0115.md`.

---

## v0.11.3 - Avaliação Docente pelo Discente · Motor analítico e API de consulta

Esta etapa constrói o backend analítico que substituirá a lógica de nota 0–10 do KPI 02 sem alterar ainda o frontend legado.

Principais mudanças:
- distribuições categóricas do SEI permanecem como fonte de verdade; nenhuma nota 0–10 é criada;
- favorabilidade passa a existir como indicador derivado, com classificação e denominador explícitos;
- `Não sei`/`Não sei responder` ficam fora do denominador classificado, mas continuam visíveis;
- categorias futuras desconhecidas bloqueiam o percentual sintético em vez de serem ignoradas;
- perguntas 1–8 do lote real são reconhecidas como avaliação do docente; a pergunta 9 sobre `UNIVC EAD` é preservada como contextual e não entra na favorabilidade do professor;
- soma de respondentes entre contextos é exposta como `respondent_participations`, nunca como alunos únicos;
- novos endpoints analíticos para filtros, overview, perguntas, docentes, disciplinas, cursos e comparação entre semestres;
- filtros são encadeados sobre contextos realmente importados;
- validação das 603 planilhas reais encontrou zero alternativa sem mapeamento;
- nenhuma migration nova: schema 39.

Detalhes: `docs/FACULTY_ANALYTICS_ENGINE_v0113.md`.

---

## v0.11.2 - Avaliação Docente pelo Discente · Identidade acadêmica e resolução controlada

Esta etapa transforma os contextos já ingeridos em uma malha acadêmica estável antes da construção do motor analítico.

Principais mudanças:
- identidade explícita `semestre → curso → disciplina → professor → oferta/turma`;
- normalização estrita, sem fuzzy matching ou aproximações silenciosas;
- resolução de curso ambíguo por contexto/arquivo, nunca como alias global;
- preview expõe `course_id` permitidos e bloqueia qualquer override fora dos candidatos;
- resoluções manuais ficam auditadas nos metadados da importação;
- reimportação reconhece uma resolução ambígua já persistida e evita pedir a mesma decisão novamente;
- chave semântica passa a considerar `class_group`, preparando futuras exportações por turma;
- novos endpoints `identity/catalog` e `identity/quality` auditam a malha relacional antes do analytics;
- validação do lote real mantém 137 contextos automáticos de DTNH, 179 de DCS e 18 pendências explícitas de Educação Física no DCS;
- nenhuma migration nova: schema 39.

Detalhes: `docs/FACULTY_ACADEMIC_IDENTITY_v0112.md`.

---

## v0.11.1 - Avaliação Docente pelo Discente · Ingestão segura e validação do ZIP real

Esta etapa estabiliza a ingestão criada na v0.11.0 antes de iniciar analytics e novo frontend do KPI 02.

Principais mudanças:
- corrige a identificação da pasta real `...GRADUACAO_(SAO_MATEUSES)` sem ampliar o escopo para semipresencial/polos/técnico;
- caminho do ZIP passa a ser somente uma otimização conservadora; a unidade do conteúdo do XLSX decide o escopo final;
- preview informa arquivos abertos, validados por conteúdo, rejeitados por unidade e divergências caminho x conteúdo;
- validação real confirma 603 XLSX de Graduação e 134 arquivos fora da unidade no lote de homologação;
- semestre continua sem inferência por data e passa por normalização/validação explícita;
- `Educação Física` isolada é marcada como ambígua no DCS e exige Bacharelado ou Licenciatura;
- reimportação fica idempotente também quando o ZIP/report ID do SEI é regenerado;
- preview identifica contextos já importados antes da gravação;
- testes de regressão e utilitário de verificação adicionados;
- nenhuma migration nova: schema 39.

Detalhes: `docs/FACULTY_STUDENT_INGESTION_HARDENING_v0111.md`.

---

## v0.11.0 - Avaliação Docente pelo Discente · Adaptador SEI e escopo de Graduação

Primeira etapa da reconstrução do KPI 02 de DTNH/DCS, agora baseada no relatório real `Disciplina/Professor` do SEI e nas distribuições originais das respostas.

Principais mudanças:
- novo fluxo `faculty-student`, separado de NPS e de docentes avaliando a instituição;
- preparação do SEI bloqueada em Graduação São Mateus, Disciplina/Professor, todos os turnos e todas as perguntas;
- questionário de discente avaliando docente é identificado semanticamente, sem ID fixo;
- parser do XLSX real preserva curso, disciplina, professor, pergunta, alternativa, quantidade e percentual;
- cursos são filtrados pelo catálogo da diretoria e modalidade;
- unidades semipresenciais/pós/técnico/polos são rejeitadas;
- semestre precisa estar explícito no título ou ser confirmado antes da importação;
- importação suporta ZIPs docentes grandes, é idempotente e preserva múltiplos professores/disciplinas/cursos por semestre;
- agregações trabalham com contadores reais das respostas, sem conversão implícita para nota 0–10;
- KPI 02 visual legado permanece inalterado nesta etapa;
- nenhuma migration nova: schema 39.

Detalhes: `docs/FACULTY_STUDENT_SEI_ADAPTER_v0110.md`.

---

## v0.10.7 - DPE UX Polish, Responsividade e Consistência Institucional

Revisão transversal da DPE v0.10 para consolidar a experiência criada nas etapas anteriores sem alterar regras financeiras.

Principais mudanças:
- correção de inconsistências estruturais do frontend, incluindo ID duplicado na Visão geral;
- padronização visual das navegações internas de Despesas, Docentes e Cursos;
- aumento de legibilidade em textos auxiliares, estados, legendas e resultados;
- topbar móvel reorganizada para manter mês e diretoria utilizáveis sem comprimir o título;
- tabelas e formulários refinados para telas pequenas, com rolagem horizontal mais clara;
- modais longos mantêm cabeçalho e ações acessíveis durante a rolagem e podem ser fechados por Esc ou clique no fundo;
- termos técnicos remanescentes foram substituídos por linguagem de negócio nas áreas atuais e de governança;
- melhorias de foco, ARIA, estados desabilitados e suporte a `prefers-reduced-motion`;
- nenhuma regra financeira foi alterada e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_UX_POLISH_v0107.md`.

---

## v0.10.6 - DPE Fechamento Guiado

A etapa final do mes foi reconstruida para responder uma pergunta simples: o mes esta pronto para ser fechado?

Principais mudancas:
- fechamento passa a ter um painel de decisao com estado pronto, pendente ou fechado;
- checklist principal e reorganizado por tarefas de negocio: Cursos, Despesas, Docentes e folha, Alunos e receitas e Distribuicao de custos;
- cada etapa pendente possui acao Resolver que leva diretamente a tela correta;
- pendencias usam a mesma deduplicacao da Visao geral para evitar alertas tecnicos em cascata;
- alertas nao bloqueantes continuam visiveis, mas separados das pendencias criticas;
- calculo oficial, checklist tecnico e historico de fechamento ficam recolhidos em Detalhes do fechamento e auditoria;
- modais de fechar e reabrir mes usam linguagem de negocio, mantendo justificativa e trilha de auditoria;
- nenhuma regra financeira foi alterada e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_GUIDED_MONTH_CLOSE_v0106.md`.

---

## v0.10.5 - DPE Despesas com Entrada Progressiva

A Central de Despesas foi simplificada para separar lancamentos, importacoes e cadastros auxiliares, deixando detalhes tecnicos sob demanda.

Principais mudancas:
- Despesas passa a ter tres visoes internas: Lancamentos, Importacoes e Categorias e setores;
- apenas uma tarefa fica visivel por vez;
- formulario principal reduzido a descricao, valor, data, categoria, setor, tipo e fornecedor/beneficiario;
- documento, referencia de origem e observacoes ficam em Informacoes adicionais;
- origem do lancamento e preservada automaticamente e deixa de ser uma escolha recorrente;
- criterio de distribuicao aparece como sugestao explicada, mas sua revisao fica na area Distribuicao de custos;
- tabela principal reduzida para despesa, valor, categoria, setor, distribuicao e acoes;
- filtros secundarios de tipo, setor e origem ficam recolhidos em Mais filtros;
- importacoes deixam de competir visualmente com o ledger mensal e ganham uma area propria;
- centros de custo e categorias ficam em Cadastros da propria area Despesas;
- nenhuma regra financeira foi alterada e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_EXPENSE_PROGRESSIVE_UX_v0105.md`.

---

## v0.10.4 - DPE Distribuicao de Custos Explicavel

A area Distribuicao de custos foi reconstruida para explicar a decisao antes do calculo, sem expor o usuario aos codigos internos do motor.

Principais mudancas:
- cada criterio passa a explicar o que significa, quando faz sentido e qual base sera utilizada;
- configuracao de uma despesa mostra previa real por curso, em percentual e reais, antes de salvar;
- a previa usa o mesmo algoritmo do calculo oficial, inclusive arredondamento de centavos;
- regra original sugerida pela categoria fica identificada e ajustes manuais ficam visiveis;
- folha docente mostra que a divisao usa somente as aulas do professor conciliado;
- criterios por carga, alunos, receita e divisao igual permitem restringir a distribuicao a cursos especificos;
- rateio manual passa a ter escolha explicita entre percentual e valor, com validacao antes de salvar;
- lista mensal destaca despesas que realmente precisam de revisao, inclusive ausencia de alunos, receita ou conciliacao docente;
- resultado por curso ganha Ver composicao, exibindo despesa de origem, criterio, base, percentual e valor;
- dados tecnicos e historico de recalculos ficam recolhidos em Detalhes do calculo;
- endpoint de preview nao persiste dados e nao cria nova fonte financeira;
- nenhuma regra financeira foi removida e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_COST_DISTRIBUTION_UX_v0104.md`.

---

## v0.10.3 - DPE Cursos e Receitas UX Rebuild

A area Cursos foi reorganizada para separar analise, preenchimento mensal e cadastro estrutural, evitando que receita, ticket, custo, margem e configuracoes aparecam simultaneamente.

Principais mudancas:
- Cursos passa a ter Visao dos cursos e Alunos e receitas como tarefas distintas;
- curso consolidado aparece primeiro e suas ofertas ficam recolhidas ate o usuario solicitar o detalhe;
- ticket, custo por aluno, resultado e margem passam a ser apresentados somente como resultados calculados;
- tela de preenchimento mensal mostra apenas alunos, pagantes, receita e situacao;
- formulario de alunos/receita usa divulgacao progressiva para origem, referencia, observacoes e receita liquida manual;
- Cursos e ofertas deixa de se repetir na sidebar e passa a ser acessado a partir da propria area Cursos;
- cadastro estrutural apresenta Cursos primeiro e Ofertas abaixo, com acao Ver ofertas por curso;
- linguagem visivel troca produto economico por curso sem alterar o modelo interno;
- nenhuma regra financeira foi alterada e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_COURSES_REVENUE_UX_v0103.md`.

---

## v0.10.2 - DPE Docentes UX Rebuild

A area Docentes foi reorganizada para que o usuario trabalhe uma tarefa por vez, sem misturar carga mensal, folha e cadastros permanentes na mesma tela.

Principais mudancas:
- Docentes passa a ter quatro visoes internas: Aulas e carga, Folha docente, Professores e Disciplinas;
- apenas uma visao fica aberta por vez;
- resumo do mes reduzido a professores no mes, carga registrada e folha conferida;
- Aulas e carga separa professor, disciplina/turma, cursos, horas e periodo em colunas mais claras;
- Folha docente ganha aviso de pendencias e linguagem de conferencia, sem vinculos automaticos;
- Professores e Disciplinas viram cadastros permanentes independentes do trabalho mensal;
- aliases passam a ser apresentados como nomes reconhecidos na folha e deixam de poluir a tabela principal;
- formularios usam divulgacao progressiva para dados de integracao/origem/observacoes;
- nenhuma regra financeira foi alterada e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_DOCENTES_UX_REBUILD_v0102.md`.

---

## v0.10.1 - DPE Decision-Oriented Overview

A Visao geral da DPE passa a priorizar decisoes e pendencias, mantendo o processo tecnico em divulgacao progressiva.

Principais mudancas:
- topo reduzido a quatro KPIs: Receita liquida, Despesas do mes, Resultado do mes e Margem do mes;
- o resultado mensal usa todas as despesas oficiais registradas, evitando parecer mais lucrativo quando ainda ha custos aguardando distribuicao;
- alunos ativos, ticket medio, percentual de custos distribuidos e conciliacao da folha passam para uma faixa secundaria de contexto;
- pendencias recebem titulo em linguagem de negocio e botao direto para a tela onde podem ser resolvidas;
- folha docente pendente passa a aparecer explicitamente no painel de atencao;
- a proxima acao do mes recebe destaque, sem repetir a navegacao principal;
- andamento/etapas do mes continuam disponiveis, mas ficam recolhidos em "Ver andamento do mes";
- tabela por curso/oferta e consolidacao por curso continuam disponiveis abaixo das decisoes principais;
- nenhuma regra financeira foi removida e nenhuma migration nova foi criada: schema 39.

Detalhes: `docs/DPE_DECISION_OVERVIEW_v0101.md`.

---

## v0.10.0 - DPE UX Information Architecture Rebase

Esta versao inaugura a linha v0.10 da DPE. O backend financeiro, snapshots, rateios, auditoria e schema permanecem intactos; a mudanca e de arquitetura da informacao e experiencia de uso.

Principais mudancas:
- navegacao principal reduzida para Visao geral, Despesas, Cursos, Docentes, Distribuicao de custos e Fechamento;
- mes de trabalho movido para um seletor global persistente no topo;
- Competencias passa a ser Peridos e historico e fica em Cadastros e configuracoes;
- Catalogo economico passa a ser Cursos e ofertas;
- termos como Motor de rateio, driver e ledger deixam o caminho principal;
- cadastros de professores e disciplinas ficam recolhidos dentro de Docentes;
- distribuicao de custos ganha explicacao simples do fluxo sem alterar o motor;
- nenhuma migration nova: schema 39.

---

## v0.9.6.21.2 — Hotfix de compatibilidade com Python no Windows

- Corrige o caso real de Windows com `Python 3.13t` (free-threaded), que fazia `greenlet`/`pydantic-core` tentarem compilação nativa e falharem sem Visual C++ Build Tools.
- Se uma `.venv` anterior tiver sido criada com Python free-threaded, o launcher a identifica e recria automaticamente.
- Procura, em ordem, CPython convencional 3.12, 3.13 e 3.11; não usa runtimes `t/free-threaded` para esta demonstração.
- Se nenhum Python compatível existir e `winget` estiver disponível, oferece instalar Python 3.12 x64 para o usuário atual.
- A instalação das dependências usa `--only-binary=:all:`: nenhuma compilação C/C++/Rust é tentada no computador do usuário.
- `RESETAR_DPE_DEMO.bat` também detecta e corrige ambiente virtual incompatível.
- Sem migration nova: continua no schema 39.

## v0.9.6.21.1 — Hotfix do launcher local da DPE

- Corrige `TESTAR_DPE_DEMO.bat`, que anteriormente executava `pip install -q` em toda abertura e podia parecer travado por tempo indeterminado.
- Dependencias agora sao verificadas antes; o `pip install` roda somente quando faltarem pacotes e exibe o progresso.
- Configura timeout/retries do pip para impedir espera silenciosa prolongada.
- O navegador so abre depois que `/api/health/live` responder; o Uvicorn roda em uma janela separada e visivel.
- `RESETAR_DPE_DEMO.bat` encerra apenas a janela do servidor da demonstracao, recria a base e reinicia o launcher.
- Reduz a instalacao local removendo os extras opcionais de `uvicorn[standard]`; o runtime local usa `uvicorn` puro.
- Sem migration nova: continua no schema 39.

## v0.9.6.21 — DPE Frontend Alignment & Local Demo

- Padroniza a DPE V2 com a fundação visual `ui-v2` usada pelas demais diretorias, alinhando topbar, sidebar, cartões, próxima ação e a área recolhida de Histórico e legado.
- Mantém o comportamento mobile compartilhado e a navegação principal organizada em Painel executivo, Operação mensal, Cadastros, Gestão e Histórico/legado.
- Adiciona ambiente local de homologação isolado de produção, iniciado por `TESTAR_DPE_DEMO.bat` no Windows.
- O seed local cria 16 produtos acadêmicos, 20 ofertas, 24 professores com atividade, 41 atividades docentes, 40 despesas oficiais, alunos/receitas e um rateio reconciliado ainda editável.
- Inclui situações de teste como turnos distintos, ADS presencial/EAD, professor compartilhado, aula compartilhada de Direito, folha conciliada, despesas diretas/compartilhadas e lote em staging.
- `RESETAR_DPE_DEMO.bat` recria o conjunto fictício; alterações normais persistem em `univc_dpe_demo.db` entre execuções.
- O seed recusa bancos não SQLite e o backend recusa `AUTH_DISABLED=true` em `prod`/`production`.
- Sem migration nova: mantém `SCHEMA_VERSION = 39` e `039_dpe_month_close_audit_v09619.sql`.

Detalhes: `docs/DPE_LOCAL_DEMO_FRONTEND_v09621.md`.

## v0.9.6.20 — DPE V2 Consolidado

- Torna o **Cost Engine** a experiência principal da DPE; a base financeira/indicadores anteriores passam para um grupo recolhido de **Histórico e legado**.
- Substitui o painel executivo antigo por uma visão mensal unificada da competência: receita líquida, custo rateado, resultado, margem, alunos ativos, ticket e prontidão operacional.
- Adiciona endpoint leve `/api/dpe/cost-engine/v2-overview`, composto somente pelas fontes canônicas já existentes; nenhuma nova base paralela é criada.
- O painel apresenta o fluxo completo **competência → despesas → docência → economia → rateio → fechamento**, com próxima ação e pendências do checklist.
- O seletor de competência do painel acompanha o usuário ao abrir as telas operacionais, reduzindo risco de trabalhar no mês errado.
- Consolidação por produto acadêmico e tabela de resultado por oferta passam a usar exclusivamente snapshots e cálculos reconciliados do Cost Engine.
- A DPE V2 preserva todas as telas e exports legados para auditoria/compatibilidade, mas novos lançamentos ficam explicitamente direcionados ao Cost Engine.
- Dados pesados do financeiro/indicadores legados passam a ser carregados sob demanda somente ao abrir uma área histórica, reduzindo o custo inicial da DPE V2.
- A seção de Governança foi atualizada para refletir staging, snapshots, rateio versionado, fechamento e reabertura auditada do Cost Engine.
- Sem migration nova: mantém `SCHEMA_VERSION = 39` e `039_dpe_month_close_audit_v09619.sql`.

Detalhes: `docs/DPE_V2_CONSOLIDATED_v09620.md`.

## v0.9.6.19 — DPE Fechamento Mensal e Auditoria

- Cria o fluxo governado de **fechamento mensal** do DPE Cost Engine, separado do simples ato de calcular/oficializar o rateio.
- Adiciona checklist de fechamento com pendências bloqueantes e alertas para ofertas, despesas, configuração de rateio, alunos, receita, ticket, staging e versão oficial.
- A competência só pode passar de `CALCULATED` para `CLOSED` quando existe uma versão oficial, atual e 100% reconciliada do Motor de Rateio.
- Receita estimada e lotes ainda em staging aparecem como avisos explícitos sem serem ocultados do responsável pelo fechamento.
- O fechamento registra um evento imutável com snapshot do checklist, versão oficial utilizada, usuário e data.
- Competências fechadas podem ser reabertas somente com motivo obrigatório; a reabertura volta o mês para `REVIEW`, preserva o fechamento anterior e exige novo ciclo de cálculo/oficialização antes de fechar novamente.
- Adiciona a área **Fechamento e auditoria** na DPE com checklist, cálculo oficial e trilha histórica de fechamento/reabertura.
- Migration `039_dpe_month_close_audit_v09619.sql`; `SCHEMA_VERSION = 39`.

Detalhes: `docs/DPE_MONTH_CLOSE_AUDIT_v09619.md`.

## v0.9.6.18 — DPE Receita, Alunos e Ticket Médio

- Cria a base econômica oficial por **oferta + competência**, preservando alunos e receita dentro do limite histórico do mês.
- Adiciona alunos ativos, alunos pagantes, receita bruta, bolsas/descontos, outras deduções, receita líquida, tipo de receita e origem do dado.
- O ticket líquido passa a ser derivado por `receita líquida / alunos pagantes`; resultado, margem e custo por aluno aparecem quando existe uma versão de rateio reconciliada.
- `STUDENTS` passa a usar alunos ativos da base econômica oficial e `REVENUE` passa a usar receita líquida; os valores técnicos da v0.9.6.17 ficam apenas como fallback legado.
- Alterar alunos ou receita após um cálculo muda o fingerprint e impede oficializar uma versão obsoleta.
- A DPE ganha a área **Receita, alunos e ticket**, com leitura por oferta e consolidação por produto, modalidade e turno.
- Migration `038_dpe_offering_economics_v09618.sql`; `SCHEMA_VERSION = 38`.

Detalhes: `docs/DPE_OFFERING_ECONOMICS_v09618.md`.

## v0.9.6.17 — DPE Motor de Rateio

- Acrescenta vigência intramês às atividades docentes (`data inicial` / `data final`), permitindo registrar substituições de professor, dois docentes na mesma disciplina/turma e mudanças ocorridas dentro da própria competência sem reescrever histórico.
- Cria a área **Motor de rateio** no DPE Cost Engine e torna operacionais os sete drivers preparados na fundação: `DIRECT`, `TEACHER_HOURS`, `OFFERING_HOURS`, `STUDENTS`, `REVENUE`, `EQUAL` e `MANUAL`.
- O custo docente por `TEACHER_HOURS` usa exclusivamente as atividades do professor conciliado na folha daquela competência.
- `OFFERING_HOURS` usa carga horária consolidada das atividades docentes quando não existe base explícita; `STUDENTS` e `REVENUE` recebem bases mensais explícitas até a integração com o domínio de receita/alunos da próxima etapa.
- Introduz configurações de destino por despesa, valores/percentuais manuais e bases mensais por oferta.
- Cada execução cria uma **versão imutável do cálculo**, com resultados por despesa/oferta, numerador, denominador, percentual, regra, snapshots e pendências.
- Cálculos incompletos ficam `BLOCKED`; somente a versão mais recente, reconciliada, sem dados alterados após o cálculo, pode virar `OFFICIAL`.
- Ao oficializar, a competência passa para `CALCULATED` e deixa de aceitar alterações nas superfícies editáveis atuais.
- Migration `037_dpe_allocation_engine_v09617.sql`; `SCHEMA_VERSION = 37`.

Detalhes: `docs/DPE_ALLOCATION_ENGINE_v09617.md`.

## v0.9.6.16 — DPE Professores, Disciplinas e Carga Horária

- Cria a área **Docência e carga horária** no DPE Cost Engine, ainda sem executar o rateio financeiro definitivo.
- Reutiliza o cadastro institucional `teachers` como fonte mestre, permitindo cadastro/edição pela DPE e aliases para conciliação com folha/importações futuras.
- Introduz disciplinas econômicas próprias da DPE e atividades docentes mensais ligadas a uma competência.
- Cada atividade informa professor, disciplina, turma/grupo, carga horária e uma ou mais ofertas beneficiadas; a soma das horas distribuídas deve fechar exatamente a carga total da atividade.
- Suporta aula compartilhada entre cursos/ofertas, inclusive divisão igual ou manual (ex.: 90h → 45h + 45h).
- Cria snapshot mensal do professor, disciplina e oferta para que mudanças futuras no cadastro não reescrevam competências anteriores.
- Despesas `PAYROLL` ganham conciliação com professor: nomes/aliases podem gerar sugestão exata, mas o vínculo só é confirmado por ação do usuário.
- Se competência, tipo de despesa ou beneficiário mudar após um vínculo de folha, a associação é invalidada e precisa ser conferida novamente.
- Migration `036_dpe_teaching_workload_v09616.sql`; `SCHEMA_VERSION = 36`.

Detalhes: `docs/DPE_TEACHING_WORKLOAD_v09616.md`.

## v0.9.6.15 — DPE Expense Intake Center

- Cria a **Central de despesas** do novo DPE Cost Engine, separada da base financeira legada.
- Introduz o ledger oficial `dpe_cost_expenses`, sempre vinculado a uma competência mensal e com snapshot da classificação usada no lançamento.
- Torna categoria obrigatória e centro de custo/setor opcional; ambos ganham cadastro hierárquico e inativação sem apagar histórico.
- Cada categoria pode definir uma regra de rateio padrão; a despesa congela a regra preparada, mas nenhum rateio é executado nesta versão.
- Prepara despesas do tipo `PAYROLL` para a próxima etapa de professores, mantendo beneficiário/fornecedor como campo genérico.
- Cria staging neutro por lotes e linhas para futuros adaptadores Excel, API, requisição ou outras fontes, sem transformar linha bruta automaticamente em despesa oficial.
- Despesas oficiais não são excluídas: podem ser estornadas com motivo e permanecem auditáveis.
- Competências em `CALCULATED` ou `CLOSED` não aceitam criação/edição/estorno na Central.
- Migration `035_dpe_expense_intake_v09615.sql`; `SCHEMA_VERSION = 35`.

Detalhes: `docs/DPE_EXPENSE_INTAKE_v09615.md`.

## v0.9.6.14 — DPE Economic Catalog & Competences

- Torna operacional a fundação do DPE Cost Engine criada na v0.9.6.13, sem executar rateios nesta etapa.
- Adiciona CRUD governado de produtos acadêmicos econômicos e ofertas por modalidade, turno e localização.
- Abre competências mensais com materialização automática das ofertas válidas no mês.
- Permite revisar inclusão/exclusão das ofertas e mover a competência entre Preparação e Conferência.
- Preserva snapshots históricos: o cadastro mestre pode mudar sem reescrever competências já materializadas.
- Acrescenta as áreas **Competências** e **Catálogo econômico** à interface da DPE.
- Sem migration nova: mantém `SCHEMA_VERSION = 34` e `034_dpe_cost_engine_foundation_v09613.sql`.

Detalhes: `docs/DPE_ECONOMIC_CATALOG_COMPETENCES_v09614.md`.

## v0.9.6.13 — DPE Cost Engine Foundation

- Inicia a reestruturação aditiva da DPE como motor mensal de custeio por oferta acadêmica, sem remover a base financeira/indicadores atuais.
- Cria a migration `034_dpe_cost_engine_foundation_v09613.sql` e eleva `SCHEMA_VERSION` para `34`.
- Introduz competência mensal, produto acadêmico econômico, oferta por modalidade/turno/local, centros de custo, categorias de despesa e regras de rateio.
- A DPE deixa de depender conceitualmente de DTNH/DCS para representar cursos técnicos, EAD, semipresencial ou outras ofertas; a ponte com `courses` passa a ser opcional.
- Adiciona snapshot de ofertas por competência para preservar o histórico quando o cadastro mestre mudar.
- Semeia os drivers `DIRECT`, `TEACHER_HOURS`, `OFFERING_HOURS`, `STUDENTS`, `REVENUE`, `EQUAL` e `MANUAL`. Nenhum rateio automático é executado nesta release.
- Expõe endpoints técnicos somente de leitura em `/api/dpe/cost-engine/foundation` e `/api/dpe/cost-engine/allocation-rules`; a superfície de escrita do novo motor continua desabilitada.

Detalhes: `docs/DPE_COST_ENGINE_FOUNDATION_v09613.md`.

## v0.9.6.12 — DPE Reactivation & Mobile Navigation

- Reativa a DPE no produto: `HIDDEN_DIRECTORATE_CODES` passa a vir vazio no runtime e no Blueprint do Render. O fallback de segurança também deixa de ocultar DPE quando a variável não existe.
- Padroniza o menu mobile de DTNH, DCS, DM e DPE com botão explícito de fechar, backdrop, fechamento por toque externo, `Esc`, navegação e bloqueio do scroll de fundo.
- Mantém o DADM V2 e acrescenta botão explícito de fechar, foco/ARIA e bloqueio de scroll no drawer mobile.
- Reitoria ganha sidebar mobile funcional, com hamburger, drawer, backdrop, `Esc`, fechamento por navegação e linguagem visual alinhada às demais diretorias.
- Sem migration nova: schema `33` permanece canônico.

## v0.9.6.11 - DADM Full Attendance Explorer

Pessoas & Setores agora permite investigar todos os atendimentos, filtrar sessoes com/sem avaliacao e ordenar por maior TME/TMA. Mantem schema 33, o fluxo Tallos atual e nao adiciona Cron Job.

## v0.9.6.10 — Supabase Secret Key & Production Provisioning

- Atualiza a administração server-side para projetos Supabase novos com `SUPABASE_SECRET_KEY=sb_secret_...`; novas API keys ficam somente no header `apikey` e não são tratadas como JWT.
- Mantém fallback compatível com `SUPABASE_SERVICE_ROLE_KEY` legado (`eyJ...`) e aceita com segurança um `sb_secret_...` temporariamente colocado no nome legado.
- Corrige o provisionamento pela Reitoria quando o trigger da migration 033 já cria `profiles` e `app_users`: a linha sincronizada passa a ser reutilizada, em vez de gerar falso conflito após o Auth criar a identidade.
- Mantém `dadm@ivc.br` com DADM/EDIT e leitura restrita aos seis departamentos governados; `rodrigo.ghirardelli@ivc.br` permanece DADM/EDIT com leitura integral de todos os departamentos da DADM.
- `render.yaml` passa a exigir `SUPABASE_SECRET_KEY`, `DATABASE_URL`, `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY`, gera `DATA_UNIVC_JWT_SECRET` no primeiro Blueprint e exige schema 33 em produção.
- Sem migration nova: `SCHEMA_VERSION = 33` e `033_identity_access_security_rebase.sql` permanecem canônicos.

Guia de produção: `docs/SUPABASE_RENDER_PRODUCTION_v09610.md`.

## v0.9.6.9 — Reitoria Administration & Directorate Visibility

- Cria `/reitoria` como workspace administrativo próprio da Reitoria, sem depender de entrar em DTNH/DCS.
- Substitui a antiga superfície órfã de `/admin/users` pela mesma interface institucional da Reitoria e elimina a referência ao CSS inexistente.
- A Reitoria passa a criar a identidade completa no Supabase Auth pelo Data UNIVC: nome, e-mail, senha inicial, tipo de usuário e acessos `READ`/`EDIT` por diretoria.
- Usuários existentes podem ter nome, e-mail, senha, status, perfil global, diretoria principal e permissões alterados; mudanças sensíveis revogam sessões.
- Foto de perfil usa bucket privado do Supabase Storage, proxy autenticado no backend e iniciais como fallback; a senha nunca é persistida no banco do Data UNIVC.
- DPE fica temporariamente oculta por `HIDDEN_DIRECTORATE_CODES=DPE`: não aparece na navegação/seletores e suas rotas ficam indisponíveis, mas código, dados e grants existentes permanecem preservados.
- Mantém `SCHEMA_VERSION = 33` e `033_identity_access_security_rebase.sql`; não existe migration nova.

Detalhes técnicos: `docs/REITORIA_ADMIN_VISIBILITY_v0969.md`.

## v0.9.6.8 — DM Interactive Excel V3 Beta

- Adiciona `/api/dm/excel-interativo` em paralelo ao Excel V2 oficial da DM.
- A exportacao V3 leva o historico autorizado completo e usa Area, Turma e Data de corte do site somente como estado inicial de `PARAMETROS`.
- Cria 11 abas visiveis: `LEIA-ME`, `PARAMETROS`, `PAINEL`, `DM-01 EVOLUCAO`, `DM-02 DEFESAS`, `TURMAS`, `ALUNOS E DEFESAS`, `MATRIZ`, `METAS E PLANOS`, `INTEGRACAO SEI` e `QUALIDADE E GOVERNANCA`.
- Bases tecnicas `DADOS_*`, `META_EFETIVA`, `LISTAS` e `CALC` ficam ocultas por padrao.
- Mantem o dominio ativo da DM (`Ativo`, `Titulado`, `Desligado`) e nao reintroduz Data de Titulacao/Situacao do Diploma.
- Sem alteracao de schema.

## v0.9.6.7 — Academic Interactive Excel V3 · DTNH + DCS

- Generaliza o Excel Interativo V3 aprovado na DTNH para a DCS usando o mesmo builder acadêmico.
- DCS usa catálogo, metas e códigos `DCS-01A/01B/01C/02/03` sem hardcodes DTNH nas fórmulas.
- `PARAMETROS`, `PAINEL`, 3 gráficos de NPS institucional, `MATRIZ` e `QUALIDADE E GOVERNANCA` mantêm a mesma experiência nas duas diretorias.
- `/api/excel-interativo` passa a aceitar DTNH e DCS e usa nome de arquivo dinâmico por diretoria.
- Excel V2 permanece disponível em paralelo; schema 33, sem migration nova.

## v0.9.6.6 — DTNH Interactive Excel V3 Beta

- Novo Excel Interativo V3 em paralelo ao Excel V2, inicialmente exclusivo da DTNH.
- PARAMETROS controla referência, comparação, janela, curso, disciplina e KPI da MATRIZ.
- PAINEL usa os cinco KPIs acadêmicos atuais e mantém as três leituras do NPS institucional.
- Bases técnicas são exportadas ocultas e sem linhas individuais de alunos.
- Novo endpoint `/api/excel-interativo`; `/api/excel` permanece inalterado.
- Schema 33; sem migration nova.

## v0.9.6.5 — DADM TALLOS Identifier Alignment

- Corrige o escopo do `dadm@ivc.br` para usar os identificadores TALLOS reais (`financeiro_12c84`, `secretaria_academica_a967b`, `mestrado_8155e`, `negociacao_b623`, `prouni_nbolsa_fies_9bc56`, `estagio_80bc4`).
- Mantém os códigos curtos (`12c84`, `A967b`, etc.) apenas como aliases de compatibilidade com fixtures/importações antigas.
- A filtragem SQL da DADM limitada passa a encontrar os fatos realmente gravados pela TALLOS.
- Normaliza nomes automáticos removendo o sufixo técnico de 5 caracteres; nomes editados manualmente continuam prevalecendo.
- Re-sync repara mapeamentos automáticos antigos e os nomes denormalizados dos atendimentos sem apagar customizações.
- Schema permanece 33; nenhuma migration nova.

Detalhes técnicos: `docs/DADM_TALLOS_IDENTIFIER_ALIGNMENT_v0965.md`.

## v0.9.6.4 — DADM Shared Ingestion & Scoped Visibility

- `dadm@ivc.br` e `rodrigo.ghirardelli@ivc.br` podem testar/salvar/substituir o token TALLOS e iniciar sincronizações da base compartilhada.
- A ingestão grava todos os setores retornados pela TALLOS, independentemente do usuário que iniciou a carga.
- `dadm@ivc.br` visualiza somente Financeiro (`12c84`), Secretaria Acadêmica (`A967b`), Mestrado (`8155e`), Negociação (`B623`), Prouni / Nbolsa / Fies (`9bc56`) e Estágio (`80bc4`).
- Rodrigo e Reitoria continuam com leitura integral da DADM.
- Filtros, dashboards, relatórios, qualidade, mapeamento de departamentos e metas/planos respeitam o escopo de leitura no backend.
- Histórico de sincronizações é compartilhado; `requested_by` permanece somente como auditoria.
- Remoção completa do token e limpeza da base local continuam restritas ao acesso completo.
- Schema permanece 33; nenhuma migration nova.

Detalhes técnicos: `docs/DADM_SHARED_INGESTION_SCOPED_VISIBILITY_v0964.md`.

## v0.9.6.3 — DM SEI Workflow Refinement

- Remove da Integração SEI da DM os blocos explicativos longos e o aviso "Escolha o que entra no Data UNIVC".
- A prévia passa a tratar Data de abertura como metadado opcional por turma.
- Turma nova sem abertura exibe `Opcional` + `Informar data`; turma existente exibe a data preservada + `Alterar`.
- Datas existentes só são substituídas quando o usuário entra explicitamente em edição e envia uma nova data.
- Sincronização sem data de abertura continua válida.
- Ciclo automático de turmas, Alunos & Defesas, ícones SEI, autenticação e DM Excel V2 permanecem intactos.
- Schema permanece 33; nenhuma migration nova.

Detalhes técnicos: `docs/DM_SEI_WORKFLOW_REFINEMENT_v0963.md`.

## v0.9.6.2 — DTNH/DCS Institutional NPS Benchmark

- NPS institucional discente passa a exibir três gráficos simultâneos: evolução da diretoria/curso, evolução geral da UNIVC e comparação por curso.
- O gráfico geral UNIVC agrega DTNH + DCS e ignora o filtro de curso, mas respeita semestre e janela.
- O gráfico comparativo por curso mantém todos os cursos da diretoria, usa o semestre como fotografia e preserva as cores por meta.
- O semestre agora ancora a janela histórica também nos gráficos de NPS do Curso e NPS institucional dos docentes.
- Os painéis visuais "Fonte oficial" foram removidos dos NPS institucionais discente e docente.
- Ícone SEI compartilhado, autenticação 9.6.1, DM 8.33 e Excel V2 foram preservados.
- Schema permanece 33; nenhuma migration nova.

# v0.9.6.1 — Frontend Identity, User Administration & Local Test Harness

A v0.9.6.1 conecta o frontend preservado da v0.8.33 à arquitetura Identity & Authorization V2 da v0.9.6.0. Todas as páginas carregam os wrappers canônicos de autenticação/identidade, chamadas autenticadas ganham refresh silencioso e CSRF, `/api/auth/me` deixa de expor aliases legados e a Reitoria recebe `/admin/users` para administrar usuários, grants, sessões e auditoria.

O SOURCE também inclui um ambiente local de homologação com sete contas, banco `univc_test.db`, sessão de até 24h e scripts de iniciar/resetar. O provedor local é recusado em `ENVIRONMENT=production`. Não há migration nova: schema 33.

Detalhes técnicos: `docs/FRONTEND_IDENTITY_ADMIN_LOCAL_v0961.md`.

# v0.9.6.0 — Identity, Session & Authorization Rebase

Esta release nasce **diretamente da v0.8.33.0** e porta para essa base o backend final de identidade/sessão/autorização da linha v0.9.x, preservando as melhorias DM 0.8.29–0.8.33 e os Excel V2.

- Supabase Auth valida credenciais apenas no login; o Data UNIVC usa access JWT local + refresh opaco rotativo.
- `app_users` e `user_directorate_access` passam a ser a fonte canônica de autorização (`REITORIA`/`DIRECTORATE`, `READ`/`EDIT`).
- routers DM/DPE/DADM são fixados ao próprio escopo; query string não redefine a identidade do recurso.
- autorização por objeto protege cursos, disciplinas, surveys, gestão, DPE, DADM e DM contra acesso por ID de outra diretoria.
- migration consolidada `033_identity_access_security_rebase.sql` parte do **schema 32 real da v0.8.33.0** e evita a colisão histórica de migrations 032.
- DM Domain Simplification, reconciliação automática de turmas, SEI UX/ícones e DM Excel V2 permanecem os da v0.8.33.0.
- o frontend ainda é o da v0.8.33.0 nesta etapa; aliases transitórios em `/api/auth/me` permanecem até a v0.9.6.1.
- CSRF enforcement, frontend identity wrapper, painel de usuários da Reitoria e ambiente local de contas entram na v0.9.6.1.

Detalhes técnicos: `docs/IDENTITY_AUTHORIZATION_REBASE_v0960.md`.

# v0.8.33.0 — DM Excel V2

- substitui a exportação oficial da DM pelo relatório gerencial V2 de 8 abas;
- alinha exportação e modelo de importação ao domínio atual: Ativo, Titulado e Desligado, com defesa como marco de titulação;
- remove do relatório oficial as abas técnicas legadas (`CALC`, `MATRIZ`, `LISTAS DE APOIO`, `LEIA-ME` e `PAINEL` antigo);
- respeita Área, Turma e Data de corte selecionadas no dashboard;
- inclui Resumo Executivo, DM-01, DM-02, Turmas, Alunos e Defesas, Metas, Integração SEI e Parâmetros;
- usa tabelas, fórmulas e gráficos nativos/editáveis do Excel;
- schema permanece 32, sem migration nova.

Detalhes técnicos: `docs/DM_EXCEL_V2_v08330.md`.

# v0.8.32.0 — DM UI Identity & Topbar Convergence

- topbar da DM alinhada à mesma fundação visual de DTNH/DCS;
- seletor de diretoria, badge de acesso e estado do banco seguem o componente compartilhado;
- ações SEI, Exportar e Nova Turma preservadas;
- DM-01, DM-02, Turmas e Alunos adotam cabeçalhos compactos consistentes;
- schema permanece 32, sem migration nova.

# Data UNIVC — v0.8.31.0

## v0.11.4 - Avaliação Docente pelo Discente · Interface analítica

A área de Avaliação Docente passa a usar a API analítica categórica da v0.11.3 em uma interface própria, dividida em **Visão Geral, Docentes, Disciplinas, Perguntas e Importações**. O fluxo visual antigo de nota 0–10 deixa de ser utilizado nessa área. A importação ZIP/XLSX pode ser iniciada pela própria tela, sempre com prévia, confirmação explícita do semestre e resolução controlada de ambiguidades.

O KPI 02 do Painel Executivo e estruturas legadas permanecem temporariamente por compatibilidade e serão consolidados em etapa posterior. Não há migration nova; schema 39.

Detalhes: `docs/FACULTY_ANALYTICS_UI_v0114.md`.

---

## v0.8.31.0 — SEI UX & Shared Action Icons

- remove `Datas que não existem nesse relatório` da integração SEI da DM;
- usa verde para observações informativas após sincronização bem-sucedida e reserva amarelo para revisão real;
- reutiliza o símbolo SEI da sidebar em ações SEI de DM e DTNH/DCS;
- corrige a ação SEI dinâmica por aluno na DM;
- normaliza botões de adição compartilhados para impedir `++`;
- mantém `SCHEMA_VERSION = 32`; nenhuma migration nova.

Detalhes técnicos: `docs/DM_SEI_UX_SHARED_ICONS_v08310.md`.

## v0.8.30.0 — DM Students & Defenses Simplification

- remove `Data de titulação` da experiência ativa de Alunos & Defesas sem apagar valores históricos do banco;
- reorganiza filtros com busca por aluno/matrícula primeiro e com maior largura;
- substitui filtros ativos de titulação por ingresso/defesa (`entry_missing`, `defense_missing`, `defense_present`, `defense_scheduled`);
- corrige o filtro `Titulado sem data de defesa`, que antes existia na UI sem contrato efetivo no repositório;
- simplifica o modal de lote para trabalhar apenas com Data de defesa e confirmação de `Titulado`;
- adiciona primeira/última página à paginação de alunos e exibe faixa de registros;
- preserva `graduation_date` e `diploma_status` históricos quando a UI nova edita outros campos;
- mantém `SCHEMA_VERSION = 32`; nenhuma migration nova.

Detalhes técnicos: `docs/DM_STUDENTS_DEFENSES_v08300.md`.


## v0.8.29.0 — DM Domain Simplification & Cohort Lifecycle

- simplifica o domínio ativo dos alunos da DM para `Ativo`, `Titulado` e `Desligado`;
- normaliza registros legados `Trancado/Trancada` para `Desligado`, preservando `sei_raw_status` quando a origem é o SEI;
- formaliza `defense_date` como marco suficiente para status `Titulado` em todos os fluxos;
- reconcilia automaticamente a turma para `Encerrada` quando todos os alunos estão `Titulado/Desligado`;
- reabre turma `Encerrada` para `Em andamento` se voltar a existir aluno `Ativo`;
- aplica a reconciliação em cadastro/edição/importação/exclusão, titulação em lote e sincronizações SEI;
- mantém `graduation_date` e trilha de diploma no banco apenas por compatibilidade histórica nesta etapa;
- adiciona migration `032_dm_domain_simplification_v08290.sql` e eleva o schema para **32**.

Detalhes técnicos: `docs/DM_DOMAIN_SIMPLIFICATION_v08290.md`.


## v0.8.28.2 — Academic Visual Polish

- Uniformiza todos os títulos de grupos da sidebar acadêmica na mesma cor verde-clara usada por `NPS Docente`.
- O gráfico de composição do NPS docente passa a usar cores semânticas distintas: promotores em verde, neutros em âmbar e detratores em vermelho.
- Nenhuma regra de cálculo, filtro, meta ou persistência foi alterada.
- `SCHEMA_VERSION` permanece **31**; não há migration nova.

## v0.8.28.1 — Academic Executive Faculty NPS & Sidebar Groups

Esta correção completa a integração visual do NPS institucional respondido pelos docentes e reorganiza a navegação acadêmica compartilhada de DTNH/DCS.

- adiciona `DTNH/DCS-01C` ao Painel Executivo com resultado, comparação, meta, status, respondentes e série histórica;
- mantém o 01C como fato institucional/anônimo, sem criar recorte por curso que não existe na fonte do SEI;
- adiciona o terceiro gráfico de NPS no executivo, ao lado de 01A e 01B;
- reorganiza a sidebar em grupos claros: NPS Discente, NPS Docente, Indicadores Acadêmicos, Gestão e Sistema;
- mantém Avaliação Docente pelo Aluno (02) separada do NPS Docente (01C), evitando confusão entre professor respondente e professor avaliado;
- `SCHEMA_VERSION` permanece **31**; não há migration nova.

Detalhes técnicos: `docs/ACADEMIC_EXECUTIVE_FACULTY_NPS_v08281.md`.


## v0.8.28.0 — Academic Excel V2

Esta etapa substitui a exportação acadêmica oficial de DTNH/DCS pelo relatório gerencial alinhado ao dashboard atual.

- `/api/excel` passa a gerar o novo workbook acadêmico V2 com 9 abas gerenciais;
- remove da exportação oficial as abas técnicas/legadas de cálculo, matriz, listas de apoio e bases editáveis;
- inclui 01A, 01B, 01C, Avaliação Docente (02), Aprovação (03), comparação por curso e Metas/Planos;
- respeita granularidade, referência, comparação, janela, curso e disciplina selecionados na interface;
- preserva 01A como NPS institucional UNIVC e 01C como população docente institucional/anônima;
- não exporta nome/matrícula de aluno, respostas brutas de pesquisas ou linhas individuais de resultado;
- utiliza tabelas, autofiltros, gráficos nativos do Excel, fórmulas derivadas e cores de status por meta;
- atualiza o nome de download acadêmico para `Relatorio_<DIRETORIA>_Academico_<REFERENCIA>.xlsx`;
- `SCHEMA_VERSION` permanece **31**; não há migration nova.

Detalhes técnicos: `docs/ACADEMIC_EXCEL_V2_v08280.md`.


## v0.8.27.0 — Academic UI Foundation

Esta etapa padroniza a experiência compartilhada de DTNH/DCS sem alterar cálculos acadêmicos ou contratos de dados.

- dialogs acadêmicos usam cartão branco com borda verde suave, deixando o escurecimento apenas no backdrop;
- campos semestrais nos dialogs passam a ser exibidos como **Ano + Semestre**, mantendo `AAAA-SEM1/SEM2` apenas no contrato interno;
- fluxo de NPS via SEI, upload XLSX/ZIP, avaliação docente manual e resultados acadêmicos usam o mesmo seletor semestral compartilhado;
- paginação compartilhada ganha ações para primeira e última página, além de anterior/próxima e páginas numéricas;
- sidebar acadêmica bloqueia overflow horizontal e remove o deslocamento lateral do item ativo/hover, preservando scroll vertical quando necessário;
- `SCHEMA_VERSION` permanece **31**; não há migration nova.

Detalhes técnicos: `docs/ACADEMIC_UI_FOUNDATION_v08270.md`.

## v0.8.26.0 — Academic NPS Visualization & UX

Esta etapa melhora a leitura comparativa dos NPS acadêmicos de DTNH/DCS sem alterar o cálculo dos indicadores.

- nomes longos de cursos passam a quebrar em até duas linhas nos gráficos, com o nome completo preservado no tooltip;
- comparação de **NPS do Curso (01B)** usa a meta efetiva de cada curso, herdando a meta TOTAL quando não houver meta específica;
- comparação segmentada do **NPS da Instituição (01A)** usa exclusivamente a meta institucional TOTAL, sem misturar a regra do NPS do Curso;
- barras de NPS passam a usar verde, amarelo, vermelho e neutro conforme status da meta;
- nova legenda explica explicitamente o significado das cores;
- tooltips exibem meta, vigência, recorte, status e composição de respostas quando disponíveis;
- tabela executiva de comparação exibe Meta e Status quando o recorte NPS possui referência de meta;
- `SCHEMA_VERSION` permanece **31**; não há migration nova.

Detalhes técnicos: `docs/ACADEMIC_NPS_VISUALIZATION_v08260.md`.


## v0.8.25.0 — Academic Faculty NPS 01C

Esta etapa adiciona o **NPS da Instituição · Docentes** ao núcleo acadêmico compartilhado de DTNH/DCS, usando o formato real da Avaliação Institucional docente do SEI e preservando o anonimato da fonte.

- cria `DTNH-01C` e `DCS-01C` como NPS institucional respondido pelo corpo docente;
- o fato é global por semestre, pois o relatório docente não identifica curso, professor ou diretoria do respondente;
- DTNH e DCS visualizam a mesma série factual, mas mantêm metas 01C próprias e exclusivamente `TOTAL`;
- suporta geração direta pelo SEI e contingência por XLSX/ZIP no mesmo fluxo;
- parser validado no layout real dos relatórios institucionais docentes, incluindo repetição de perguntas por quebra de página;
- somente perguntas com escala completa 0–10 podem alimentar o NPS; relatórios sem essa pergunta são preservados sem fabricar resultado;
- nova área de NPS docente com histórico, composição, fonte oficial e filtros exclusivamente temporais;
- `SCHEMA_VERSION` passa a **31** com `031_academic_faculty_nps_v08250.sql`.

Detalhes técnicos: `docs/ACADEMIC_FACULTY_NPS_v08250.md`.

## v0.8.24.0 — Academic NPS Core 01A/01B

Esta etapa formaliza a separação dos dois NPS discentes no núcleo acadêmico compartilhado de DTNH/DCS, preservando o NPS institucional como indicador da UNIVC e o NPS do Curso como indicador específico da diretoria/curso.

- `DTNH/DCS-01A` passa a representar **NPS da Instituição · Alunos**;
- `DTNH/DCS-01B` passa a representar **NPS do Curso**;
- metas e planos antigos `DTNH/DCS-01` são migrados apenas para `01B`, pois o código legado sempre representou o NPS do Curso;
- o Painel Executivo passa a exibir os dois NPS, cada um com série, comparação e meta independentes;
- NPS institucional continua agregando DTNH + DCS pelas contagens reais de respostas, sem média simples entre NPS;
- detalhamento e comparação por curso do NPS institucional passam a respeitar exclusivamente a diretoria em visualização;
- comparação executiva de NPS por curso recebe meta/status por curso, preparando a camada visual orientada à meta;
- metas `01A` aceitam apenas recorte `TOTAL`; metas `01B` aceitam `TOTAL` ou curso ativo da diretoria;
- `SCHEMA_VERSION` passa a **30** com `030_academic_nps_kpi_split_v08240.sql`.

Detalhes técnicos: `docs/ACADEMIC_NPS_CORE_v08240.md`.

## v0.8.23.3 — DADM V2 Motion & UX

Esta etapa fecha a rodada de UX da DADM V2 com um motion system discreto e coerente com DTNH/DCS, sem alterar dados, métricas, filtros, relatórios ou regras de gestão.

- sidebar desktop passa a animar largura, margem do conteúdo e barra de carregamento em conjunto;
- sidebar mobile mantém o slide existente e ganha backdrop com fade de entrada/saída;
- filtros progressivos, modais de período, relatório e metas/planos passam a abrir e fechar suavemente;
- cards, botões, chips e estados de feedback ganham microinterações curtas e consistentes;
- gráficos TALLOS ganham animação puramente visual para linhas, barras, pontos, ratings e barras horizontais;
- tooltips preservam o posicionamento seguro nas bordas e recebem apenas um fade curto;
- `prefers-reduced-motion` desativa as animações/transições e também elimina o scroll suave programático;
- `SCHEMA_VERSION` permanece **29**; não há migration nova.

Detalhes técnicos: `docs/DADM_V2_MOTION_UX_v08233.md`.

## v0.8.23.2 — DADM V2 Reporting UI Integration

Esta etapa conecta o motor de relatórios TALLOS V2 à interface oficial da DADM e aproxima a topbar da mesma hierarquia visual usada em DTNH/DCS, sem iniciar ainda o motion system geral nem as melhorias de calendário.

- novo botão **Gerar relatório** no topo da DADM, disponível também em modo somente leitura;
- download usa exatamente os filtros globais ativos de período, departamento, operador, canal, status e tabulação;
- modal de confirmação mostra o recorte que será exportado e reforça que o XLSX é agregado, sem atendimento individual ou dado pessoal de cliente;
- download autenticado trata erro HTTP/JSON na própria interface e respeita o nome de arquivo retornado pelo backend;
- topbar reorganizada em **Diretoria em visualização + acesso + estado TALLOS + relatório**, seguindo a lógica acadêmica sem remover controles existentes;
- comportamento responsivo preserva o seletor e reduz a ação de relatório para ícone em larguras menores;
- `SCHEMA_VERSION` permanece **29**; não há migration nova.

Detalhes técnicos: `docs/DADM_V2_REPORTING_UI_v08232.md`.

# Data UNIVC — v0.8.23.1

## v0.8.23.1 — DADM V2 Reporting Engine

Esta etapa adiciona o motor de relatórios agregados da DADM V2 sem alterar ainda a interface, a topbar ou o motion system.

- novo endpoint de leitura **`/api/dadm/v2/report.xlsx`** com os mesmos filtros TALLOS V2 de período, departamento, operador, canal, status e tabulação;
- exportação exclusivamente agregada: nenhum atendimento individual, cliente, telefone, CPF/CNPJ ou payload bruto é levado ao Excel;
- workbook com **Resumo, Evolução mensal, Departamentos, Operadores, Departamento × mês, Operador × mês, Avaliações e Parâmetros**;
- tabelas nativas do Excel com autofiltros e gráficos editáveis;
- TME/TMA preservados como durações, avaliação na escala homologada 1–10 e ausência de avaliação preservada como ausência, nunca zero;
- cobertura e taxas derivadas permanecem fórmulas simples do Excel;
- consultas de relatório não herdam os limites visuais do dashboard (como top 100 operadores);
- `SCHEMA_VERSION` permanece **29**; não há migration nova.

Detalhes técnicos: `docs/DADM_V2_REPORTING_ENGINE_v08231.md`.

# Data UNIVC — v0.8.23.0

## v0.8.23.0 — DADM V2 Primary Convergence

Esta release promove a experiência analítica V2 para a rota oficial **`/dadm`**, mantém o painel anterior em **`/dadm/legacy`** durante a transição e fecha as principais lacunas de produto antes da aposentadoria do legado.

- corrige o tooltip dos gráficos medindo sua largura real e limitando a posição dentro do container, evitando texto comprimido verticalmente nas bordas;
- adiciona sidebar recolhível persistente e seletor de diretoria usando a fundação compartilhada do Data UNIVC;
- aplica modo somente leitura coerente às ações de escrita;
- incorpora **Metas & Planos de ação** ao DADM V2 com contrato próprio para TME, TMA, avaliação 1–10 e cobertura;
- preserva metas/planos legados sem convertê-los automaticamente e isola os registros V2 por namespace;
- adiciona linhas de meta aos gráficos e estado de meta nos KPIs;
- move o mapeamento governado de departamentos TALLOS para **Dados & Integração**;
- mantém a análise comparativa sem limite artificial de três meses e preserva o histórico real de cada entidade, sem inventar meses anteriores à sua existência;
- `/dadm/v2` passa a redirecionar para `/dadm`, preservando query string;
- `SCHEMA_VERSION` permanece **29**; não há migration nova.

Detalhes técnicos: `docs/DADM_V2_PRIMARY_CONVERGENCE_v08230.md`.

# Data UNIVC — v0.8.22.0

## v0.8.22.0 — UI Foundation + experiência de sincronização

Esta release preserva a arquitetura aprovada da **DADM V2** e inicia a convergência visual do produto inteiro, combinando a hierarquia e os filtros da V2 com a identidade institucional do `ui-v2`.

- cria `static/css/data-univc-foundation.css` e `static/js/data-univc-ui.js` como fundação compartilhada de tokens, campos, ícones, progresso, estados e motion;
- mantém intactas as cinco áreas da DADM V2 e traz o usuário de volta ao rodapé da sidebar, no mesmo padrão das demais diretorias;
- padroniza o campo local do token TALLOS, incluindo foco, ajuda e exibir/ocultar senha;
- troca ícones isolados/Unicode por uma linguagem SVG coerente, inclusive o ícone de integração **SEI**;
- sincronização TALLOS passa por fase **Preparando** antes da fase percentual: todos os blocos de até 90 dias são planejados primeiro e o denominador fica estável, evitando regressões como `71% → 67%`;
- a mesma linguagem de operação longa é usada no SEI do DM e no shell acadêmico DTNH/DCS. Quando o backend não fornece total confiável, o progresso é indeterminado em vez de inventar porcentagem;
- comparação DADM V2 de **um único mês** deixa de sobrepor pontos de linha e usa uma leitura tipo dot plot/lista, com entidade e valor sempre visíveis;
- tooltips da DADM V2 passam a escolher direção conforme a borda disponível para reduzir cortes;
- `SCHEMA_VERSION` permanece **29**; não há migration nova.

A especificação desta fase está em `docs/DATA_UNIVC_UI_FOUNDATION_v08220.md`.

# Data UNIVC — v0.8.21.0

## v0.8.21.0 — DADM V2 · fundação de experiência gerencial

- Nova experiência paralela em **`/dadm/v2`**, preservando a DADM atual em `/dadm` durante a reconstrução.
- Navegação reduzida a cinco conceitos: **Visão geral**, **Pessoas & Setores**, **Experiência**, **Análise comparativa** e **Dados & Integração**.
- Novo **Contexto de Análise** persistente, com período mensal visual, departamento, operador e filtros progressivos de canal/status/tabulação.
- O seletor de período deixa de depender de digitação `AAAA-MM`: os meses são escolhidos em uma grade visual com intervalo e atalhos.
- Operadores e departamentos passam a usar a mesma arquitetura de explorer, ranking, tabela e **perfil individual**. Uma entidade pode ser analisada sozinha antes de ser adicionada à comparação.
- Visão Geral organizada em três histórias: **operação**, **eficiência** e **experiência**, com Tempo Médio de Espera (TME) e Tempo Médio de Atendimento (TMA) escritos por extenso e explicados.
- Experiência do atendimento usa avaliação 1–10, quantidade de respostas, cobertura e distribuição; ausência continua `NULL/—` e nunca vira 0.
- Comparação aceita uma ou mais entidades e também períodos arbitrários.
- Conexão, sincronização e qualidade dos dados ficam concentradas em **Dados & Integração**, fora do fluxo executivo.
- Novo contrato analítico V2 em `/api/dadm/v2/*`, ainda sobre a camada TALLOS validada e sem nova migration.
- `SCHEMA_VERSION` permanece **29**.

> Esta é a fundação da reconstrução. A DADM antiga permanece disponível até a V2 ser homologada visual e funcionalmente.

Para testar localmente, use `TESTAR_DADM_V2.bat`. Blueprint: `docs/DADM_V2_BLUEPRINT_v08210.md`.

# Data UNIVC — v0.8.20.3

## v0.8.20.3 — DADM TALLOS · avaliação mensal reconciliada

- O contrato de avaliação TALLOS passa a ser **1–10**. `S/A`, `NULL`, campo ausente e `level=0` são ausência de avaliação e nunca entram na média.
- A reconciliação com a exportação oficial usada na homologação encontrou 536 atendimentos, 32 avaliações numéricas, 504 `S/A`, nenhuma nota 0 e média 9,28125. A menor nota observada nesse recorte foi 3.
- Toda consulta de avaliação aplica defensivamente `1 <= rating <= 10`, inclusive se existir algum zero histórico em um banco local antigo.
- O agrupamento principal de avaliação é **operador × mês**. Um mês sem avaliação retorna `—`, nunca `0/10`.
- Protocolos podem conter várias sessões; a persistência continua por `source_id`/sessão para que a avaliação permaneça associada ao operador correto.
- O filtro analítico usa **Mês inicial** e **Mês final**, sem presets de janela.
- DADM-01 passa a exibir a leitura TALLOS de **Tempo Médio de Espera (TME)** e **Tempo Médio de Atendimento (TMA)**; DADM-02 passa a exibir avaliação 1–10, distribuição, cobertura e leitura mensal por operador.
- A interface reduz ações redundantes e adiciona auditoria do `level` bruto versus avaliação normalizada.
- `TALLOS_NORMALIZATION_VERSION = 3`, `SCHEMA_VERSION = 29`, migration `database/029_dadm_tallos_rating_1_10_v08203.sql`.

> **Produção:** aplique 027, 028 e 029 em ordem antes de publicar a v0.8.20.3. Em seguida, faça uma nova sincronização do período homologado para validar a API atual contra a exportação oficial.

## v0.8.20.0 — DADM TALLOS Homologação Real

- `TESTAR_DADM.bat` agora usa `univc_dadm_homolog.db` e inicia sem dados demonstrativos, para que a primeira carga TALLOS seja real.
- A tela **Sincronização** permite, somente no ambiente local, colar o token, testar a conexão em `/v2/employees` e salvar o segredo no `.env` do backend sem expô-lo ao navegador depois.
- Estados de primeira execução orientam: conectar → sincronizar agosto/2026 → validar indicadores.
- Sincronização mostra progresso, recebidos, novos, atualizados, inalterados e falhas; inclui atalho para o golden dataset de agosto/2026.
- Avaliações ganharam representação explícita para a homologação inicial; a interpretação da escala foi corrigida na v0.8.20.2.
- Removidos do fluxo DADM o botão TALLOS redundante e o botão de carregar demonstração.
- Ferramentas locais permitem limpar apenas a base TALLOS e remover o token de homologação sem tocar DADM-01/DADM-02.
- O schema permanece 27: esta release melhora fluxo e homologação sem nova migration.

- TALLOS Analytics Center incorporado nativamente à DADM, mantendo FastAPI + SQLAlchemy + HTML/CSS/JS puro e o Design System existente.
- Persistência operacional em banco com UPSERT por ID do registro TALLOS; protocolo deixa de ser tratado como chave de sessão.
- Análises server-side por período, operador, departamento, canal, status e tabulação, sem transferir a base detalhada para o navegador.
- Visões de operadores, departamentos, canais, estrelas, TME/TMA e comparação histórica de 2/3/6/12/24/60 meses.
- Sincronização manual e CLI para carga histórica, janela recente e fechamento mensal.
- Privacidade: cliente é identificado apenas por `customer.id`; nome, telefone, CPF e CNPJ não são persistidos na camada analítica.
- Nova migration `database/027_dadm_tallos_analytics_v08190.sql`; `SCHEMA_VERSION = 27`.
- Contrato técnico e homologação: `docs/DADM_TALLOS_ANALYTICS_CENTER.md`.

> **Produção:** aplique a migration 027 antes de publicar esta versão e configure `TALLOS_API_TOKEN` somente no backend.

## v0.8.18.0 — Query Performance

- Avaliação Docente migrou para paginação, busca, filtros e agregações server-side.
- O dashboard acadêmico não materializa mais linhas por professor: avaliação docente é agregada no SQL por semestre/curso/disciplina.
- O dashboard DADM lê apenas a janela necessária e o histórico mínimo das regras de governança.
- O dashboard financeiro DPE carrega uma janela limitada com 11 meses adicionais de lookback para preservar rolling 12 meses.
- Nenhuma migration nova; `SCHEMA_VERSION = 26`.
- Benchmarks e limites: `docs/PERFORMANCE_v08180.md`.

## v0.8.17.0 — Cleanup e Performance I

Primeira release de otimização medida sobre a fundação v0.8.16.0. Mantém o schema **26** e não introduz nova migration.

Principais mudanças:

- remove do shell acadêmico as implementações antigas de DADM/DPE já substituídas por `/dadm` e `/dpe`;
- `app.js` acadêmico cai de ~3.099 para ~2.617 linhas e `index.html` de ~647 para ~454;
- elimina o N+1 da listagem de despesas/rateios DPE: 100 despesas passam de 101 para 2 statements SQL no benchmark sintético;
- Resultados Acadêmicos passam a usar validação + prefetch + `executemany` em lotes, com fallback para o importador legado em `IntegrityError`;
- 1.000 resultados caem de ~6.005 para ~16 statements SQL no benchmark sintético;
- stress sintético validado em 50k e 100k resultados;
- fingerprint de build passa a cobrir toda a superfície runtime, evitando builds iguais quando módulos antes omitidos mudarem;
- benchmark reproduzível em `scripts/benchmark_scalability.py` (SOURCE);
- detalhes e limites de interpretação em `docs/PERFORMANCE_v08170.md`.

> **Produção:** nenhuma migration nova. O banco deve continuar em `SCHEMA_VERSION = 26` (migration 026 já aplicada).

## v0.8.16.0 — fundação arquitetural e de confiabilidade

Esta release inaugura a fase de consolidação do Data UNIVC **sem alterar regras de negócio**. O objetivo é tornar as próximas refatorações mensuráveis, reversíveis e seguras antes da entrada de grandes volumes (especialmente Tallos/DADM).

Principais mudanças:

- versão/build centralizados em `release_info.py`;
- Golden Baseline preservada em `baseline/golden_v0.8.15.1.json`;
- `pytest` passa a descobrir todo `test_*.py`, com gates `SMOKE`, `PR` e `RELEASE`;
- testes executados isoladamente para evitar vazamento de estado/processos entre arquivos históricos;
- ledger de schema (`SCHEMA_VERSION = 26`) e readiness de produção incompatível com schema antigo;
- migration aditiva `database/026_schema_version_baseline_v08160.sql`;
- builder reproduzível para separar **SOURCE** de **PRODUCTION**, excluindo bancos SQLite, caches e testes do artefato produtivo;
- runtime desacoplado de `scripts/`: dados/seeds demonstrativos canônicos vivem em `demo_data.py` e `demo_seed.py`;
- nenhuma otimização de negócio, remoção de legado ou integração Tallos nesta release.

> **Produção:** aplique a migration 026 depois da 025 e antes de publicar a v0.8.16.0.

## v0.8.15.1 — redesign completo do frontend Data UNIVC

A v0.8.15.1 expande o Design System institucional para toda a plataforma: DTNH, DCS, DADM, DPE, DM e o workspace gerencial. A atualização preserva backend, endpoints, regras de negócio e contratos de DOM, mas unifica navegação, sidebar, topbar, iconografia SVG, filtros, KPIs, gráficos, tabelas, modais, feedback, responsividade e motion.

Principais direções da release:

- DTNH/DCS: dashboard executivo, NPS, Avaliação Docente, Aprovação/Notas, metas, planos, cadastros, arquivos e governança no mesmo padrão visual;
- DADM: monitoramento operacional com cards, comparação temporal, canais, tabelas e ações compactas;
- DPE: linguagem financeira própria dentro do mesmo Design System, preservando receita, despesa, cobertura, folha e resultado por curso;
- DM: dashboard, turmas, alunos/titulação, SEI, metas, arquivos e governança com linguagem operacional consistente;
- workspace gerencial legado: reestilizado para não funcionar como um sexto produto visual;
- navegação mobile e `prefers-reduced-motion` padronizados;
- sem nova migration de banco nesta release.

## v0.8.13.1 — Defesa opcional na titulação do DM

- DM: nova operação individual e em lote para transformar alunos elegíveis em **Titulados**.
- seleção existente ganhou barra contextual, seleção de todos os resultados filtrados e fluxo por turma.
- nova **Data de titulação**, separada da Data de defesa e opcional para o histórico legado.
- acompanhamento de diploma digital: **Pendente**, **Em emissão**, **Emitido** ou não informado.
- filtros documentais para localizar titulados sem data, pendências de diploma e diplomas emitidos.
- prévia obrigatória antes da confirmação em lote, com validações cronológicas e bloqueio de Trancados/Desligados.
- histórico auditável de alterações de titulação (`dm_graduation_events`).
- exportação/importação do DM preserva as colunas legadas e acrescenta Titulação/Diploma ao final.
- a sincronização do SEI continua responsável por ingresso/defesa e não sobrescreve Titulação/Diploma.
- produção PostgreSQL/Supabase: executar `database/025_dm_graduation_digital_diploma_v08130.sql`.

## v0.8.11.0 — NPS com filtros e gráficos próprios

As abas **NPS da Instituição** e **NPS do Curso** agora permitem combinar semestre e curso, controlar a janela histórica (4/6/8/12 semestres ou todo o histórico), acompanhar evolução em linha e comparar cursos no recorte. No NPS Institucional, o filtro por curso usa os agregados brutos da mesma pergunta institucional do SEI e não altera o fechamento institucional oficial.


## v0.8.10.0 — reconstrução de Educação Física

- Bacharelado e Licenciatura usam identidade explícita (`Bac.`/`Lic.`) e nunca `EFB/EFL` da turma.
- O fluxo de Educação Física reproduz também a inicialização `form:j_idt477` observada nos HARs manuais, sem alterar os demais cursos.
- Após o download, o XLSX é validado por curso e período antes da importação; em caso de estado cruzado, Educação Física repete uma vez todo o fluxo a partir de uma tela limpa.
- O backend expõe `build` (fingerprint) e a política `xlsx-course-field-plus-explicit-sei-context-v4`; o release interrompe a inicialização se a validação legada de turma voltar a aparecer em `repository.py`.
- Para evitar deploy acidental do código antigo, a entrega inclui ZIP flat com `app.py` diretamente na raiz.

## v0.8.9.5 — estado real do formulário JSF na geração do Excel

- Captura o `<form id="form">` devolvido pelo SEI depois da seleção do curso.
- Reenvia no `imprimirExcel` os controles efetivamente presentes/selecionados, inclusive checkboxes dinâmicos.
- Valida ano, semestre e curso imediatamente antes de gerar o XLSX.
- Mantém Bacharelado e Licenciatura separados pelo campo `Curso:` do relatório; EFB/EFL e turno não definem habilitação.
- Mantém fallback legado apenas se o partial-response do SEI não trouxer o formulário principal.

## v0.8.9.4 — identidade de Educação Física validada pelo XLSX

Esta correção trata um comportamento de estado do RichFaces: depois de localizar um curso em uma página posterior do seletor, uma nova pesquisa pode permanecer naquela página. O conector agora volta explicitamente à página 1 antes de varrer os resultados, permitindo consultar em sequência Bacharelado (página 2) e Licenciatura (página 1). A regra está no núcleo compartilhado de **DTNH e DCS**.

O formulário de integração acadêmica também passa a sugerir o semestre corrente, e falhas são reportadas por curso/etapa para evitar mensagens genéricas de requisição.

## Módulos atuais

- **DTNH / DCS** — NPS Discente, Avaliação Docente e resultados acadêmicos.
- **DADM** — indicadores administrativos DADM-01/DADM-02 + TALLOS Analytics Center para operação de atendimento.
- **DPE** — base financeira e resultado econômico por curso.
- **DM** — turmas, alunos, datas e metas do mestrado com integração SEI.
- **Avaliações SEI** — login temporário, busca de avaliação/questionário, geração assíncrona, download XLSX/ZIP, parsing e normalização.


## DCS — Educação Física separada por habilitação

O catálogo acadêmico agora trata **Educação Física - Bacharelado** e **Educação Física - Licenciatura** como cursos distintos em todas as camadas. O histórico legado de `Educação Física` é migrado para Bacharelado preservando o mesmo `course_id`; Licenciatura recebe identidade própria.

A integração acadêmica com o SEI foi endurecida no núcleo compartilhado por **DTNH e DCS**:

- pagina automaticamente o diálogo RichFaces de cursos, sem depender da primeira página;
- descobre semanticamente a ação **Selecionar**, sem fixar índices de linha ou `j_idt...`;
- resolve aliases do SEI para o nome institucional do Data UNIVC;
- valida o curso gravado dentro do XLSX contra o curso solicitado antes de importar;
- rejeita cruzamento entre Bacharelado e Licenciatura;
- mantém XLSX manual e busca direta no SEI no mesmo parser acadêmico.

Rótulos observados e suportados: `Educação Física (Bac. Presencial)` → Bacharelado. Em 29/09/2026 o SEI passou a apresentar a Licenciatura apenas como `Educação Física` no diálogo, em `form:nomeCurso` e no XLSX. Esse rótulo genérico só é aceito quando o fluxo curso-a-curso já solicitou explicitamente `Educação Física - Licenciatura`; uploads sem contexto continuam bloqueados como ambíguos. O alias histórico `Educação Física (Lic. Presencial)` continua suportado. Os códigos/prefixos de turma `EFB`/`EFL` não definem a habilitação.

## NPS Discente pelo SEI

O NPS não possui fluxo separado de **Importar legado**. No menu acadêmico existem agora duas áreas explícitas:

- **NPS da Instituição → Atualizar NPS da Instituição pelo SEI**;
- **NPS do Curso → Atualizar NPS dos Cursos pelo SEI**.

As duas áreas usam o mesmo conector, parser XLSX/ZIP e armazenamento normalizado, mas cada formulário nasce com seu escopo fixo e termina permitindo vincular somente a pergunta daquele indicador. Se o download automático estiver indisponível, cada fluxo aceita um XLSX/ZIP já baixado do SEI como contingência.

As perguntas oficiais permanecem distintas e ambas usam escala de 0 a 10:

### NPS da Instituição

Pergunta sobre a recomendação do **UNIVC**. Cada diretoria acadêmica sincroniza sua parcela do relatório e o Data UNIVC consolida DTNH + DCS pelas contagens reais de respostas. Quando uma das diretorias ainda não tiver sincronizado o semestre, a interface informa que a cobertura institucional está incompleta.

### NPS do Curso

Pergunta sobre a recomendação do **próprio curso**. O resultado é calculado para cada curso e também de forma geral, sempre agregando promotores, neutros e detratores antes de calcular o NPS.

Para as duas abas:

- 0–6: detratores;
- 7–8: neutros/passivos;
- 9–10: promotores;
- NPS = % promotores − % detratores.

O relatório normalizado do SEI permanece armazenado para auditoria. A tabela `nps_student` continua como projeção compatível com a análise acadêmica existente do **NPS do Curso**; o **NPS da Instituição** possui sua própria projeção e fonte oficial.

## Avaliação Docente

O fluxo Discente → Docente já possui adaptador validado no XLSX/ZIP real do SEI, ingestão segura, identidade acadêmica por semestre/curso/disciplina/professor e motor analítico categórico. A API preserva as distribuições originais e oferece favorabilidade derivada de forma explícita, sem fabricar nota 0–10. O KPI 02 visual legado permanece ativo somente até a conclusão da nova interface.

## Executar a DPE localmente com dados fictícios

A v0.9.6.21 inclui um ambiente autocontido de homologação da DPE. No Windows, execute:

```bat
TESTAR_DPE_DEMO.bat
```

O atalho cria/reutiliza `.venv`, instala `requirements-local.txt`, prepara `univc_dpe_demo.db`, habilita autenticação desativada **somente no ambiente local** e abre `http://127.0.0.1:8000/dpe`. A base contém 16 produtos acadêmicos, 20 ofertas, professores/cargas, folha, despesas gerais, alunos, receitas e um cálculo de rateio reconciliado. Todos os valores são fictícios.

Para apagar as alterações realizadas durante os testes e voltar ao conjunto original, execute:

```bat
RESETAR_DPE_DEMO.bat
```

Em Linux/macOS com as dependências já instaladas, use `./INICIAR_DPE_DEMO.sh`. O script de seed recusa bancos que não sejam SQLite, e `AUTH_DISABLED=true` é recusado quando `ENVIRONMENT=production`.

## Validação

```bash
python scripts/run_release_checks.py
```

A suíte de regressão e as fixtures sanitizadas ficam em `tests/`.

## Deploy e banco

Consulte [docs/DEPLOY.md](docs/DEPLOY.md). O histórico resumido está em [docs/CHANGELOG.md](docs/CHANGELOG.md).

## v0.8.9 — identidade visual e perfil de usuário

- logo oficial do UNIVC incorporada ao login e às barras laterais;
- mesma identidade visual nas áreas acadêmicas, DADM, DPE, DM e painel gerencial;
- perfil do usuário no rodapé com iniciais, nome, papel, diretoria e estado de sessão;
- rótulos de papel localizados (Administrador, Diretor, Editor e Consulta);
- cache-busting dos módulos especializados alinhado à release atual.

## Atalho local incluído nesta release

Para homologar a DPE no Windows, use `TESTAR_DPE_DEMO.bat`. Para apagar as alterações feitas durante os testes e recriar a base fictícia, use `RESETAR_DPE_DEMO.bat`. Ambos usam exclusivamente `univc_dpe_demo.db` e não exigem Supabase.

## v0.11.6.1 — BATs locais de todas as diretorias e Reitoria

Foram adicionados launchers Windows independentes para `DTNH`, `DCS`, `DADM`, `DPE`, `DM` e `REITORIA`. Cada perfil usa porta própria e todos compartilham o SQLite local `univc_local_all.db`, sem tocar Supabase/produção. A Reitoria ganhou em `AUTH_DISABLED` um modo global estritamente local (`LOCAL_REITORIA_MODE=true`) para homologação. O schema permanece 40 e não há migration nova. Consulte `docs/LOCAL_DIRECTORATE_LAUNCHERS_v01161.md`.

## Patch operacional — Parte 4 (2026-09-29)

- Comparativos por curso passam a preservar nomes longos integralmente no grafico.
- Os rotulos podem ocupar multiplas linhas e cada barra recebe altura dinamica.
- O tooltip e o SVG `title` mantem o nome completo do curso.
- Nenhuma regra de NPS, API ou schema foi alterada.
- Detalhes: `docs/PART4_NPS_LONG_COURSE_LABELS_2026-09-29.md`.

### Parte 7 — Excel Interativo acadêmico oficial

O Excel Interativo de DTNH/DCS deixa de ser beta. `/api/excel-interativo` gera `Painel_DTNH_Interativo.xlsx` ou `Painel_DCS_Interativo.xlsx`, com PAINEL de cinco gráficos, MATRIZ, parâmetros e bases gerenciais separadas (`NPS`, avaliação docente, resultados acadêmicos, metas, cursos, disciplinas e dimensões). CALC e listas de apoio permanecem ocultas. O Excel tradicional de `/api/excel` continua disponível em paralelo.

## Parte 9 — escalas semânticas e distribuição NPS 0–10 (2026-10-01)

Os gráficos acadêmicos passam a respeitar a natureza da métrica: percentuais usam sempre 0–100, NPS usa -100–+100 e contagens começam em zero. Isso elimina eixos de aprovação acima de 100%, contagens negativas e distorções visuais de pequenas variações. Barras negativas de NPS também deixam de invadir o nome dos cursos, pois o valor passa a ocupar uma coluna separada.

As três áreas de NPS (instituição/alunos, curso e instituição/docentes) passam a exibir a distribuição original das respostas de 0 a 10, com quantidade e percentual por nota, total de respondentes, média 0–10 complementar e NPS. O Excel Interativo oficial ganha a base visível `NPS DISTRIBUICAO`. Não há migration nova; o schema permanece 49. Consulte `docs/PART9_SEMANTIC_CHART_SCALES_NPS_DISTRIBUTION_2026-10-01.md`.

## Hotfix DM — turmas fragmentadas pelo SEI (2026-10-01)

A integração da Diretoria de Mestrado passa a consolidar automaticamente blocos físicos do relatório do SEI que apontem para a mesma área + número de turma. Isso cobre casos como `17-CTE` e `17-CTE Mestrado Univc`, que são a mesma turma lógica, sem remover as travas para matrículas em turmas diferentes ou dados conflitantes. Não há migration nova; o schema permanece 49.

## Parte 13 — Hotfix DM + Reitoria acadêmica em abas (2026-10-01)

A Diretoria de Mestrado passa a aceitar o formato real do SEI quando uma mesma turma é dividida em vários blocos físicos, consolidando com segurança os fragmentos da mesma área + número de turma. O arquivo real `1790874693805.xlsx` foi validado com 13 turmas lógicas e 433 alunos; `CTE:17` resulta em 51 alunos após a consolidação.

Na Reitoria, os indicadores acadêmicos deixam de ficar empilhados na área administrativa. O painel passa a ter telas independentes para `NPS`, `Avaliação Docente` e `Notas e Aprovação`, com Administração separada em `Visão geral`, `Usuários e acessos` e `Auditoria`. O backend institucional ponderado da Parte 12 é preservado. Consulte `docs/PART13_DM_HOTFIX_REITORIA_TABS_2026-10-01.md`.

## Parte 16 — Reitoria combobox + fundação da fila SEI da DM (2026-10-01)

A Reitoria acadêmica passa a usar comboboxes pesquisáveis nos filtros de Curso e Disciplina, reutilizando o mesmo componente compartilhado de DTNH/DCS. Na Diretoria de Mestrado, a sincronização de turmas/alunos deixa de consultar individualmente início/conclusão/titulação no mesmo request: a etapa longa foi separada para preparar o processamento persistente em lotes e evitar 504 durante o commit das turmas. Schema permanece 49.
