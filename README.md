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
- O backend expõe `build` (fingerprint) e a política `xlsx-course-field-only-v3`; o release interrompe a inicialização se a validação legada de turma voltar a aparecer em `repository.py`.
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

Rótulos observados e suportados: `Educação Física (Bac. Presencial)` → Bacharelado e `Educação Física (Lic. Presencial)` → Licenciatura. Os códigos/prefixos de turma `EFB`/`EFL` não definem a habilitação: a identidade vem do campo `Curso:` de cada bloco do XLSX, evitando falsos conflitos com códigos históricos de turma.

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

A fundação relacional já suporta professor, disciplina, curso, turma/oferta e semestre. O adaptador específico do relatório docente aguarda um XLSX/ZIP real do SEI para que o layout seja implementado sem suposições.

## Executar localmente

No Windows:

```bat
TESTAR_LOCAL.bat DTNH
TESTAR_LOCAL.bat DCS
TESTAR_LOCAL.bat DADM
TESTAR_LOCAL.bat DPE
TESTAR_LOCAL.bat DM
TESTAR_LOCAL.bat DM sei
```

Sem argumento, o padrão é `DTNH`.

O script cria/reutiliza `.venv`, instala `requirements-local.txt`, inicializa `univc_dev.db` e sobe o FastAPI em `http://127.0.0.1:8000`.

Para recriar apenas o ambiente Python local, use `RECRIAR_AMBIENTE_LOCAL.bat`.

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

## Atalhos locais por diretoria

Para testes locais no Windows, a release inclui atalhos de duplo clique:

- `TESTAR_DTNH.bat`
- `TESTAR_DCS.bat`
- `TESTAR_DADM.bat`
- `TESTAR_DPE.bat`
- `TESTAR_DM.bat`
- `TESTAR_DM_SEI.bat`

O `TESTAR_LOCAL.bat` continua disponível como inicializador genérico e aceita a diretoria por parâmetro.