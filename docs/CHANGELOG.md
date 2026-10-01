# 2026-10-01 — Parte 11 · isolamento DTNH/DCS

- corrige reaproveitamento da distribuição NPS 0–10 entre diretorias;
- chave do cache passa a incluir DTNH/DCS e o cache é limpo na troca;
- adiciona `directorateEpoch` para descartar respostas assíncronas da diretoria anterior;
- protege dashboard, NPS e Resultados Acadêmicos contra race conditions de troca;
- Avaliação Docente passa a validar `loadSerial` antes de reconciliar/renderizar filtros;
- superfícies acadêmicas são limpas imediatamente durante a troca;
- release preflight valida os novos guards;
- regressão completa: 214 testes aprovados e 2 ignorados;
- schema permanece 49; nenhuma migration nova.

# 2026-09-29 — Parte 8 Hotfix · restauração de fillConfig

- corrige `ReferenceError: fillConfig is not defined` introduzido na limpeza de legado da Parte 8;
- restaura somente o helper ativo da tela Configurações, sem reintroduzir o frontend legado da Avaliação Docente;
- `fillConfig()` passa a tolerar campos ausentes para não interromper o bootstrap;
- adiciona teste de regressão para os helpers ativos chamados durante bootstrap/refresh;
- regressão completa: 197 testes aprovados e 2 ignorados;
- schema permanece 49; nenhuma migration nova.

# 2026-09-29 — Parte 5 Hotfix · seleção múltipla somente entre cursos candidatos

- Avaliação Docente deixa de pedir curso principal seguido de seleção adicional entre toda a diretoria.
- Casos ambíguos mostram apenas `candidate_courses` já detectados pelo backend.
- Usuário pode marcar um, dois ou mais cursos para a mesma turma.
- Respostas continuam persistidas uma única vez; cursos adicionais usam `faculty_evaluation_context_scopes`.
- Backend rejeita escopos adicionais fora dos candidatos autorizados pelo preview.
- Schema permanece 49; nenhuma migration nova.
- Regressão completa: 184 testes aprovados e 2 ignorados.

# v0.13.0 — Patch operacional Parte 3 (29/09/2026)

- Avaliação Docente passa a aceitar turmas vinculadas a múltiplos cursos sem duplicação de respostas;
- adiciona `faculty_evaluation_context_scopes` e migration 049 com backfill do vínculo primário histórico;
- importação docente usa ano + semestre em campos humanos;
- analytics por curso respeita os novos escopos e a visão global deduplica agregados;
- NPS do SEI atual resolve `Educação Física` como Licenciatura apenas no contexto da fonte;
- uploads manuais ambíguos passam a aceitar resolução explícita do curso;
- schema esperado: 49;
- regressão completa: 176 testes aprovados, 2 ignorados.

---

# v0.13.0 — Production

- promove a árvore reconciliada v0.13.0-dev.15 para produção sem novas mudanças de domínio;
- base acadêmica oficial v0.11.6.7;
- schema 48;
- habilita rate limit de login na configuração de produção;
- mantém `AUTH_DISABLED=false`, `COOKIE_SECURE=true` e API docs desabilitadas;
- release destinada à homologação final no VPS e promoção imediata após smoke de infraestrutura.

# v0.13.0-dev.15 — Reconciliação global com base acadêmica v0.11.6.7

- integra a árvore acadêmica completa v0.11.6.7 sobre a DPE v0.13.0-dev.14;
- incorpora os ajustes v0.11.6.6 de compatibilidade SEI em Resultados Acadêmicos;
- incorpora a classificação gerencial por aluno da v0.11.6.7;
- preserva schema 48 e todas as migrations DPE 041–048;
- resolve o bloqueador global de base acadêmica identificado no DPE-01;
- adiciona regressão específica para garantir simultaneamente DPE moderna e classificação acadêmica v0.11.6.7.

---

# v0.13.0-dev.14 — DPE-14 · Auditoria final e bloqueio do legado

- remove importador, modelos de importação e builder Excel históricos da DPE;
- bloqueia superfícies genéricas de dashboard/medições/Excel para DPE;
- remove cálculos DPE-01/02/03 restantes do runtime genérico;
- impede que seeds auxiliares recriem medições antigas;
- adiciona verificador canônico de release;
- preserva referências antigas somente para migration/auditoria de dados históricos;
- schema 48 mantido; 152 testes aprovados.

Detalhes: `docs/DPE_14_FINAL_AUDIT_v0130dev14.md`.

---

# v0.13.0-dev.5 — DPE-05 · Cursos e contextos opcionais

- Remove a restrição da DPE a cursos presenciais.
- Curso passa a ser a entidade principal da experiência.
- Novo contexto-base automático permite que um curso funcione sem cadastrar uma “oferta”.
- Contextos adicionais tornam-se opcionais para turma, turno, unidade, local ou modalidade específica.
- Competências materializam contextos adicionais quando existirem e usam o contexto-base apenas quando o curso não estiver desdobrado, evitando dupla contagem.
- Snapshots preservam explicitamente o tipo de contexto para histórico.
- APIs e telas passam a trabalhar com cursos de todas as modalidades.
- Mantém `offering_id` e a tabela histórica internamente para compatibilidade com rateio, docência, economics e fechamentos já existentes.

# v0.13.0-dev.4 — DPE-04 · Consolidação do domínio

- estabelece um vocabulário canônico da DPE em `dpe_domain.py`;
- adiciona `/api/dpe/domain` com entidades, estados da competência e grupos de gestão oficiais;
- cria os grupos `DPE-RESULT`, `DPE-REVENUE`, `DPE-EXPENSE`, `DPE-TEACHING` e `DPE-ALLOCATION`;
- marca DPE-01/02/03 como contrato histórico de compatibilidade para medições/Excel;
- bloqueia novas metas e planos de ação nos códigos históricos;
- migration 044 arquiva metas/planos antigos e remapeia somente equivalências semânticas seguras;
- preserva métricas antigas sem equivalência exata como histórico em vez de converter por aproximação;
- mantém Cost Engine como fonte operacional oficial;
- schema esperado passa a 44;
- suíte completa: 98 testes aprovados.

Detalhes: `docs/DPE_04_DOMAIN_CONSOLIDATION_v0130dev4.md`.

---

# v0.13.0-dev.3 — DPE-03 · Backend legado aposentado

- remove APIs, repositories, modelos ORM e seeds da DPE v0.4 e Finance v0.7.7;
- remove o Excel v0.4 e seus templates antigos;
- cria a migration 043, que arquiva qualquer linha legada antes de excluir as oito tabelas antigas;
- remove DPE-04/DPE-05 do metadata runtime;
- preserva temporariamente DPE-01/02/03 de gestão, Metas e Planos para a próxima etapa de domínio;
- mantém Cost Engine, rateio, docência, economics, analytics, fechamento, snapshots e auditoria;
- adiciona aposentadoria equivalente para SQLite local;
- suíte completa: 92 testes aprovados.

Detalhes: `docs/DPE_03_BACKEND_LEGACY_RETIREMENT_v0130dev3.md`.

---

# v0.12.5 — DPE · Homologação e Refinamento

## v0.12.5.1 — DPE Demo + Navigation Hotfix

- Corrige a tela de Receitas permanecendo visivel ao navegar para outras areas.
- Adiciona protecao CSS para garantir que somente a `page-section.active` seja exibida.
- Entrega a base local `univc_dpe_demo.db` pre-populada para homologacao visual.
- Sem migration nova; schema 42.


- consolida acessibilidade estrutural e navegação por teclado na DPE;
- adiciona skip link, `aria-busy`, status de carregamento e feedback acessível;
- adiciona gerenciamento de foco, focus trap, Esc e devolução de foco nos modais;
- substitui diálogos nativos `confirm()`/`prompt()` por confirmação institucional com justificativa opcional/obrigatória;
- padroniza alertas, erros de formulário e estados vazios;
- refina combobox docente e abas com contratos ARIA e teclado;
- adiciona tooltips de conceitos gerenciais;
- melhora responsividade, densidade de tabelas, formulários e modais;
- preserva `prefers-reduced-motion`;
- nenhuma migration nova; schema permanece 42;
- última migration obrigatória continua sendo `042_dpe_productivity_v0123.sql`;
- suíte acumulada da base de homologação: 80 testes aprovados.

Detalhes: `docs/DPE_HOMOLOGATION_REFINEMENT_v0125.md`.

---

# v0.12.4 — DPE · Fechamento e Governança

- transforma Fechamento em checklist operacional com pendências específicas e acionáveis;
- adiciona conciliação docente e resultado econômico ao checklist;
- exige revisão explícita dos alertas atuais antes de liberar o fechamento;
- registra cada revisão de alerta no `audit_log`;
- adiciona ação controlada `CALCULATED -> REVIEW` para correção antes do fechamento, preservando o run anterior como `SUPERSEDED`;
- amplia auditoria `before/after` das operações críticas da DPE;
- exibe trilha de auditoria da competência diretamente na tela de Fechamento;
- preserva eventos imutáveis de fechamento/reabertura e bloqueio de edição em mês fechado;
- nenhuma migration nova; schema permanece 42;
- última migration obrigatória continua sendo `042_dpe_productivity_v0123.sql`;
- suíte acumulada da base de homologação: 73 testes aprovados.

Detalhes: `docs/DPE_CLOSURE_GOVERNANCE_v0124.md`.

---

# v0.12.3 — DPE · Produtividade operacional

- implementa importação real de Excel para despesas, com modelo, staging, preview, validação e commit atômico;
- bloqueia duplicatas por chave externa e assinatura econômica antes de chegar ao ledger;
- adiciona cópia controlada de receitas/alunos e quadro docente entre competências, com prévia;
- remapeia dados copiados pela oferta acadêmica estável em vez de reutilizar IDs de snapshot mensal;
- adiciona despesas recorrentes idempotentes e vinculação opcional a política de distribuição;
- adiciona classificação em massa de despesas;
- adiciona prévia e aplicação em massa de políticas reutilizáveis;
- mantém a grade atômica de Receitas como editor em massa oficial;
- adiciona migration 042 `dpe_productivity_v0123.sql`;
- schema esperado passa a 42;
- suíte acumulada da base de homologação: 68 testes aprovados.

Detalhes: `docs/DPE_PRODUCTIVITY_v0123.md`.

---

# v0.12.2 — DPE · Financial Analytics

- adiciona camada analítica somente leitura sobre a fonte oficial do Cost Engine;
- adiciona cards de Receita bruta, Receita líquida, Despesas, Resultado, Margem operacional, Ticket líquido e Alunos pagantes com comparação mensal;
- adiciona evolução de Receita líquida × Despesas × Resultado e Margem operacional;
- adiciona despesas por categoria, por setor e comparação de categorias contra o mês anterior;
- adiciona Receita, Resultado, Margem e Ticket por curso;
- adiciona Custo por aluno × Ticket e composição Docentes/Diretos/Compartilhados;
- adiciona histórico do curso com Receita × Custo × Resultado;
- adiciona waterfall reconciliado da receita bruta ao resultado;
- usa apenas Allocation Run oficial, reconciliado e com fingerprint atual para custos/resultados por curso;
- não infere overhead administrativo sem classificação contábil explícita;
- nenhuma migration nova; schema permanece 41;
- suíte acumulada da base de homologação: 61 testes aprovados.

Detalhes: `docs/DPE_ANALYTICS_v0122.md`.

---

# v0.12.1 — DPE · Distribuição de Custos · mesa de trabalho e políticas

- transforma Distribuição de custos em mesa de trabalho com destino, critério e situação visíveis;
- adiciona busca e filtro operacional de despesas;
- substitui a seleção extensa de destinos por seletor pesquisável;
- mantém prévia obrigatória antes de salvar a configuração;
- adiciona prévia consolidada da competência sem persistir novo Allocation Run;
- compara custo confirmado, nova prévia, receita, resultado e margem por curso/oferta;
- cria políticas reutilizáveis de distribuição com sugestão automática controlada pelo usuário;
- preserva histórico ao resolver destinos estáveis para os snapshots de cada competência;
- adiciona migration 041 `dpe_allocation_policies_v0121.sql`;
- schema esperado passa a 41;
- suíte acumulada da base de homologação: 53 testes aprovados.

Detalhes: `docs/DPE_COST_DISTRIBUTION_v0121.md`.

---

# v0.12.0 — DPE · Financial Operations · fluxo operacional

- restringe novas competencias da DPE a cursos oficiais ativos e presenciais de DTNH/DCS;
- transforma Receitas em area operacional propria;
- adiciona grade mensal de alunos/receitas com gravacao atomica em lote;
- preserva calculo automatico de receita liquida e ticket;
- reorganiza Cursos para leitura economica;
- redesenha distribuicao docente com curso + horas e reconciliacao em tempo real;
- adiciona busca para professor, disciplina e curso na operacao docente;
- explicita Categoria, Setor, Destino economico e Criterio na experiencia de despesas;
- preserva Allocation Engine, snapshots, fechamento, auditoria e compatibilidade SQLite/PostgreSQL;
- adiciona testes automatizados DPE;
- nenhuma migration nova; schema 40.

Detalhes: `docs/DPE_FINANCIAL_OPERATIONS_v0120.md`.

> Observacao de release: o ZIP completo de homologacao desta entrega parte da arvore completa v0.11.6.5. O patch DPE separado deve ser aplicado sobre a arvore completa v0.11.6.7 para preservar integralmente v0.11.6.6/v0.11.6.7.

---

# v0.11.6.5 — DTNH/DCS · Resultados Acadêmicos · leitura por aluno

- separa contagens de pessoas das contagens aluno-disciplina;
- adiciona resumo reconciliável de alunos distintos;
- cards de reprovação aplicam filtros server-side e abrem os registros correspondentes;
- gráfico histórico mostra alunos distintos e composição do status no tooltip;
- seleção inicial passa ao semestre mais recente;
- nenhuma migration; schema 40.

Detalhes: `docs/ACADEMIC_RESULTS_STUDENT_UX_v01165.md`.

---

# v0.11.6.4 — DTNH/DCS · Resultados Acadêmicos · importação protegida

- troca o parser monolítico do relatório de notas por inspeção + streaming em `read_only=True`;
- persiste resultados em lotes configuráveis (500 por padrão);
- libera o cache de alunos entre lotes para conter RAM;
- torna a reexecução segura por idempotência dos vínculos já gravados;
- interface SEI processa um curso por request e exibe progresso por curso;
- endpoint pesado do SEI roda fora do event loop;
- upload manual de Resultados também é deslocado para thread pool e usa lotes;
- nenhuma migration nova; schema 40.

Detalhes: `docs/ACADEMIC_RESULTS_IMPORT_HARDENING_v01164.md`.

---

# v0.11.6.3 — DTNH/DCS · Avaliação Docente · ZIP final do SEI + comboboxes

- Corrige o fluxo direto do SEI para executar a segunda geração obrigatória do relatório `Disciplina/Professor`.
- Detecta `formQuestionarioSelecionar` após a primeira conclusão e usa somente o botão global `formQuestionarioSelecionar:botaoGerarRelatorioEmPDF4`.
- Executa novo ciclo `pool2 → encerrar → oncomplete2` antes de procurar `DownloadRelatorioSV`.
- Mantém fallback compatível com relatórios que já retornem download após a primeira fase.
- Transforma Curso, Disciplina e Docente em comboboxes pesquisáveis sem alterar o contrato dos filtros encadeados.
- Adiciona busca sem acentos/caixa, teclado, limpar seleção e lista rolável.
- Adiciona testes específicos da segunda fase e dos comboboxes.
- Schema permanece 40.

Detalhes: `docs/FACULTY_SEI_PHASE2_COMBOBOX_v01163.md`.

---

# v0.11.6.2 — DTNH/DCS · Avaliação Docente · acesso direto ao SEI

- Corrige o botão da Avaliação Docente que abria o seletor de arquivos apesar de indicar importação pelo SEI.
- Separa **Buscar direto no SEI** de **Usar XLSX/ZIP já baixado**.
- Conecta a interface aos contratos `/api/surveys/sei/login`, `/api/surveys/sei/evaluations/search`, `/api/surveys/sei/evaluations/select`, `/api/surveys/faculty-student/sei/prepare` e `/api/surveys/faculty-student/sei/report/generate`.
- Mantém a prévia e a importação categórica já existentes.
- Schema permanece 40.

# v0.11.5 — Avaliação Docente · Consolidação do KPI 02 em favorabilidade

- Torna `faculty_favorability_pct_v1` a métrica oficial do KPI 02 no Painel Executivo.
- Remove `teacher_evaluations` da fonte factual do snapshot acadêmico; a tabela continua preservada para auditoria.
- Agrega o indicador por contagens de respostas favoráveis/classificadas e preserva bloqueio quando existe categoria não mapeada.
- Aposenta escrita manual e endpoints antigos de análise 0–10 com HTTP 410.
- Mantém leitura da base histórica identificada explicitamente como `legacy_score_0_10`.
- Adiciona `goals.metric_version`; metas 02 existentes são marcadas como legadas e deixam de ser aplicadas ao percentual.
- Exige novas metas 02 entre 0% e 100%, com atenção menor ou igual à meta.
- Atualiza dashboard, comparações e Excel V2/V3 para favorabilidade.
- Adiciona testes de consolidação do KPI e smoke test das duas exportações acadêmicas.
- Migration 040 obrigatória; schema 40.

Detalhes: `docs/FACULTY_KPI_CONSOLIDATION_v0115.md`.

---

# v0.11.4 — Avaliação Docente pelo Discente · Interface analítica

- Substitui, dentro da área Avaliação Docente, a experiência manual baseada em nota 0–10 pela leitura categórica da API `faculty-student`.
- Organiza a navegação em Visão Geral, Docentes, Disciplinas, Perguntas e Importações.
- Adiciona filtros encadeados por semestre, curso, disciplina e docente.
- Exibe favorabilidade como indicador derivado, mantendo a distribuição original do SEI e os avisos de metodologia.
- Abre detalhes de docente e disciplina sem perder a identidade Curso × Disciplina × Professor × Semestre.
- Integra o pipeline seguro ZIP/XLSX com prévia, confirmação de semestre e resolução controlada de curso ambíguo.
- Adiciona histórico de lotes persistidos e diagnóstico de qualidade da malha acadêmica.
- Mantém o KPI 02 legado do Painel Executivo temporariamente para compatibilidade; sua substituição integral fica para a próxima etapa.
- Adiciona testes da nova interface/contrato e verificador de ponta a ponta em banco temporário.
- Sem migration nova; schema 39 permanece canônico.

Detalhes: `docs/FACULTY_ANALYTICS_UI_v0114.md`.

---

# v0.11.3 — Avaliação Docente pelo Discente · Motor analítico e API de consulta

- Cria motor de favorabilidade sem converter respostas categóricas para nota 0–10.
- Mantém distribuição original e expõe classificação de cada alternativa.
- Exclui `Não sei` do denominador classificado, preservando sua contagem.
- Bloqueia percentuais sintéticos quando surge categoria futura ainda não mapeada.
- Separa perguntas de docente de itens contextuais; a pergunta 9 `UNIVC EAD` não compõe a síntese do professor.
- Expõe `respondent_participations` com aviso explícito de que não representa alunos únicos.
- Adiciona endpoints de filtros, overview, perguntas, professores, disciplinas, cursos e comparação por semestre.
- Adiciona testes da camada analítica e verificador em SQLite temporário.
- Varredura do lote real com 603 XLSX encontrou zero alternativa não mapeada.
- Sem migration nova; schema 39 permanece canônico.

---

# v0.11.2 — Avaliação Docente pelo Discente · Identidade acadêmica e resolução controlada

- Adiciona normalização estrita de identidade para professor, disciplina, oferta e turma sem fuzzy matching.
- Preview de cursos ambíguos passa a expor `candidate_ids` e `candidate_courses`.
- Importação aceita `course_resolutions` por caminho do XLSX e valida o ID contra a lista permitida.
- `Educação Física` continua sem alias global; cada contexto precisa de decisão explícita quando ainda não resolvido.
- Resolução aplicada fica auditada em `survey_imports.metadata_json`.
- Reimportação reconhece resolução ambígua já persistida e marca o contexto como `already_imported`.
- `faculty_context_semantic_key` passa a considerar `class_group`.
- Adiciona endpoints `faculty-student/identity/catalog` e `faculty-student/identity/quality`.
- Mantém 137 contextos automáticos DTNH, 179 DCS e 18 resolvíveis no lote real de homologação.
- Sem migration nova; schema 39 permanece canônico.

---

# v0.11.1 — Avaliação Docente pelo Discente · Ingestão endurecida e importação segura

- Corrige a classificação da pasta real `GRADUACAO_(SAO_MATEUSES)` do ZIP do SEI.
- Torna o fast reject conservador e mantém o conteúdo do XLSX como validação final de unidade.
- Preview passa a expor arquivos abertos/validados/rejeitados e divergências de escopo.
- Confirma no lote real 603 XLSX de Graduação, 134 fora da unidade e 0 erros de parser na Graduação.
- Normaliza e valida semestre explicitamente sem inferência por data.
- Marca `Educação Física` sem habilitação como resolução manual obrigatória no DCS.
- Adiciona estado `already_imported` no preview.
- Reforça idempotência por identidade lógica da avaliação e por atribuição docente, inclusive em ZIP regenerado com SHA/report ID diferentes.
- Adiciona testes de regressão e script de verificação da ingestão.
- Sem migration nova; schema 39 permanece canônico.

---

# v0.11.0 — Avaliação Docente pelo Discente · Adaptador SEI e escopo de Graduação

- Adiciona fluxo SEI `faculty-student` específico para discente avaliando docente.
- Bloqueia o relatório em Graduação São Mateus, Disciplina/Professor, todos os turnos e todas as perguntas.
- Implementa parser do XLSX real preservando contexto docente e distribuição de respostas.
- Rejeita unidade/modalidade/curso fora do escopo de DTNH ou DCS.
- Exige confirmação do semestre quando o título não identifica `.1`/`.2` explicitamente.
- Suporta ZIPs docentes grandes sem alterar limites do importador genérico.
- Corrige criação de disciplina para registrar vigência inicial no semestre importado.
- Reimportação é idempotente e não permite mover contextos existentes para outro semestre.
- KPI 02 legado permanece ativo até a camada analítica e o novo frontend serem concluídos.
- Sem migration nova; schema 39 permanece canônico.

---

# v0.10.7 — DPE UX Polish, Responsividade e Consistência Institucional

- Padroniza tabs internas de Despesas, Docentes e Cursos.
- Corrige ID duplicado da Visão geral.
- Melhora legibilidade de textos auxiliares e densidade de informação.
- Refina topbar, tabelas, formulários e modais em mobile.
- Permite fechar modais por Esc e clique no fundo.
- Humaniza termos técnicos remanescentes na governança e nos cadastros avançados.
- Adiciona ajustes de foco, ARIA e redução de movimento.
- Schema permanece 39, sem migration nova.

---

# v0.10.6 — DPE Fechamento Guiado

- Fechamento passa a responder diretamente se o mes esta pronto ou quais ajustes ainda faltam.
- Checklist principal reorganizado em etapas de negocio com botao Resolver por etapa.
- Pendencias executivas reaproveitam a deduplicacao da Visao geral e evitam cascatas tecnicas.
- Alertas nao bloqueantes ficam separados dos bloqueios.
- Calculo oficial, checklist tecnico e historico ficam em detalhes sob demanda.
- Fechar e reabrir mes mantem as mesmas regras de auditoria com linguagem simplificada.
- Sem migration nova; schema 39 permanece canonico.

# v0.10.5 — DPE Despesas com Entrada Progressiva

- Despesas dividido em Lancamentos, Importacoes e Categorias e setores.
- Novo formulario de despesa usa divulgacao progressiva e mostra somente os campos essenciais no primeiro nivel.
- Origem, documento, referencia e observacoes deixam de poluir a entrada principal.
- Distribuicao sugerida pela categoria fica explicada, mas continua sendo revisada na area Distribuicao de custos.
- Tabela mensal e filtros foram reduzidos para priorizar leitura e conferencia.
- Importacoes e cadastros estruturais ficam fora do fluxo principal de lancamento.
- Sem migration nova; schema 39 permanece canonico.

# v0.10.4 — DPE Distribuição de Custos Explicável

- Critérios de distribuição passam a ser apresentados em linguagem de negócio, com explicação, base usada e exemplo.
- Nova prévia por despesa calcula percentuais e valores por curso antes de salvar a configuração.
- Preview reaproveita o mesmo algoritmo do cálculo oficial e não persiste alterações.
- Sugestão original da categoria e ajustes posteriores ficam diferenciados na interface.
- Rateio manual separado entre modo percentual e valor, com validação de fechamento.
- Pendências reais de alunos, receita, folha ou configuração passam a aparecer na lista antes do recálculo.
- Resultado por curso ganha composição detalhada até despesa, critério, base, percentual e valor.
- Bases e histórico de cálculos ficam em divulgação progressiva dentro de Detalhes do cálculo.
- Sem migration nova; schema 39 permanece canônico.

# v0.10.3 — DPE Cursos e Receitas UX Rebuild

- Cursos separado em analise de resultado e preenchimento mensal de alunos/receita.
- Resultado passa a ser hierarquico: curso consolidado primeiro, ofertas sob demanda.
- Ticket, custo por aluno, resultado e margem deixam a tabela de entrada e permanecem como calculos.
- Cadastro de cursos/ofertas fica hierarquico e acessivel a partir da area Cursos, sem duplicar a sidebar.
- Formularios economicos escondem dados de integracao/origem em Informacoes adicionais.
- Linguagem principal troca produto economico por curso sem alterar o backend.
- Sem migration nova; schema 39 permanece canonico.

# v0.10.2 — DPE Docentes UX Rebuild

- Docentes dividido em Aulas e carga, Folha docente, Professores e Disciplinas.
- Uma unica tarefa fica visivel por vez, reduzindo carga cognitiva.
- Cadastro permanente separado das associacoes mensais professor-disciplina-turma-curso.
- Folha docente ganha estado de conferencia explicito e acoes mais claras.
- Formularios de professor, disciplina e atividade passam a esconder campos tecnicos em areas avancadas.
- Sem migration nova; schema 39 permanece canonico.

# v0.10.1 — DPE Decision-Oriented Overview

- Visão geral reduzida a quatro KPIs de decisão: receita líquida, despesas do mês, resultado e margem.
- Resultado executivo passa a considerar todas as despesas oficiais do mês, e não apenas custos já distribuídos.
- Alunos, ticket, cobertura da distribuição e conciliação da folha passam a contexto secundário.
- Pendências ganham títulos em linguagem de negócio e ações diretas para a tela correta.
- Pendências técnicas em cascata são deduplicadas para evitar vários alertas sobre a mesma causa.
- Workflow e progresso continuam disponíveis, mas ficam recolhidos por padrão em `Ver andamento do mês`.
- Sem migration nova; schema 39 permanece canônico.

# v0.10.0 — DPE UX Information Architecture Rebase

- Navegação principal reduzida a Visão geral, Despesas, Cursos, Docentes, Distribuição de custos e Fechamento.
- Mês de trabalho vira contexto global no topo.
- Cadastros, períodos, metas e governança deixam o caminho principal.
- Linguagem técnica é progressivamente substituída por termos de negócio, sem alterar o backend financeiro.
- Sem migration nova; schema 39 permanece canônico.

# v0.9.6.21 — DPE Frontend Alignment & Local Demo

- DPE V2 alinhada visualmente à fundação UI das demais diretorias.
- Ambiente local isolado com autenticação desativada somente em desenvolvimento.
- Seed fictício completo para 16 cursos/produtos, 20 ofertas, professores, docência, folha, despesas, economia e rateio.
- Scripts Windows para iniciar e restaurar a demonstração.
- Schema permanece em 39; nenhuma migration nova.

## v0.9.6.20 — DPE V2 Consolidated Experience

- Cost Engine passa a ser a navegação e o painel executivo principal da DPE.
- Nova visão mensal unificada com KPIs econômicos, progresso do workflow, próxima ação, checklist e resultado por oferta.
- Novo endpoint read-only `/api/dpe/cost-engine/v2-overview`, sem duplicar fonte de verdade.
- Competência selecionada no painel é propagada para Despesas, Docência, Economia, Rateio e Fechamento ao navegar pelo workflow.
- Base financeira, indicadores DPE-01/02/03 e arquivos anteriores ficam recolhidos em **Histórico e legado**.
- Consultas pesadas do legado passam a ser lazy-loaded apenas quando uma tela histórica é aberta.
- Governança e Central de arquivos passam a orientar explicitamente novos lançamentos para o Cost Engine.
- Sem migration nova; schema `39` permanece canônico.

## v0.9.6.19 — DPE Month Close & Audit

- Nova área **Fechamento e auditoria** na DPE.
- Checklist formal de fechamento mensal com itens PASS/WARNING/BLOCKER.
- Fechamento exige competência `CALCULATED`, versão oficial atual e rateio integralmente reconciliado.
- Alunos ativos, receita líquida e base de ticket são verificados antes do encerramento.
- Receita estimada e lotes pendentes em staging aparecem como alertas de governança.
- Fechamento cria evento imutável com snapshot do checklist e da versão oficial utilizada.
- Reabertura de competência fechada exige justificativa, volta o mês para `REVIEW` e mantém todo o histórico anterior.
- Reabertura exige novo cálculo e nova oficialização antes de um novo fechamento.
- Ações de fechar/reabrir também alimentam o log geral de auditoria.
- Migration 039 e schema 39.

## v0.9.6.18 — DPE Offering Economics

- Base econômica mensal oficial por oferta para alunos, receita e ticket médio.
- STUDENTS usa alunos ativos; REVENUE usa receita líquida.
- Consolida resultado econômico por produto, modalidade e turno sem perder o detalhe da oferta.
- Fingerprint do rateio passa a incorporar dados econômicos e bloqueia oficialização de cálculo obsoleto.
- Nova área `Receita, alunos e ticket` na DPE.
- Migration 038 e schema 38.

## v0.9.6.17 — DPE Allocation Engine

- Atividades docentes ganham vigência intramês para registrar substituições e simultaneidade de professores sem perder histórico.
- Nova área **Motor de rateio** na DPE.
- Execução dos drivers `DIRECT`, `TEACHER_HOURS`, `OFFERING_HOURS`, `STUDENTS`, `REVENUE`, `EQUAL` e `MANUAL`.
- Base de horas por oferta pode ser derivada das atividades docentes; alunos e receita já possuem base mensal auditável por oferta.
- Configuração de destinos elegíveis por despesa e suporte a valor/percentual manual.
- Cálculos versionados, imutáveis e rastreáveis até despesa + oferta + regra + base matemática.
- Pendências geram versões `BLOCKED`; somente a versão mais recente, conciliada e com fingerprint atual pode ser oficializada.
- Oficialização congela a competência em `CALCULATED`.
- Migration 037 e schema 37.

## v0.9.6.16 — DPE Teaching Workload

- Nova área operacional **Docência e carga horária** na DPE.
- Reutilização do cadastro institucional de professores (`teachers`) com aliases seguros para conciliação futura.
- Disciplinas econômicas, snapshots mensais de professor e atividades docentes por competência.
- Divisão obrigatoriamente balanceada da carga horária entre uma ou mais ofertas econômicas.
- Suporte explícito a aulas compartilhadas entre cursos/ofertas.
- Conciliação de despesas `PAYROLL` com sugestões por nome/alias e confirmação humana obrigatória.
- Vínculos de folha guardam snapshot histórico e são invalidados quando dados críticos da despesa mudam.
- Migration 036 e schema 36.

## v0.9.6.15 — DPE Expense Intake Center

- Nova Central de Despesas para o DPE Cost Engine, sem substituir a base financeira legada.
- Ledger normalizado por competência com categoria obrigatória, centro de custo opcional, tipo `GENERAL`/`PAYROLL`, origem e snapshot histórico da classificação.
- CRUD governado de centros de custo e categorias, com hierarquia e regra de rateio padrão.
- Staging neutro em lotes/linhas para futuros conectores Excel/API/requisição.
- Estorno auditável no lugar de exclusão física.
- Migration 035 e schema 35.

## v0.9.6.14 — DPE Economic Catalog & Competences

### DPE Cost Engine
- habilita a superfície de escrita do catálogo econômico;
- produtos e ofertas econômicas passam a ser administráveis pela DPE;
- oferta distingue modalidade, turno e campus/unidade/polo;
- competências mensais materializam as ofertas válidas e preservam snapshot histórico;
- exclusões manuais de oferta são preservadas ao atualizar o snapshot;
- nesta etapa o workflow fica limitado a `DRAFT`/`REVIEW`; cálculo e fechamento continuam reservados às próximas releases;
- interface ganha as áreas Competências e Catálogo econômico;
- financeiro/indicadores legados permanecem intactos.

### Schema
- sem migration nova; schema `34` permanece canônico.

## v0.9.6.13 — DPE Cost Engine Foundation

### DPE
- cria a fundação do novo motor mensal de custeio sem remover o financeiro legado;
- introduz competência, produto, oferta econômica, centro de custo, categoria e regras de rateio;
- oferta passa a distinguir modalidade, turno, campus/unidade/polo;
- `source_course_id` é opcional, removendo a dependência estrutural de DTNH/DCS para o catálogo econômico;
- snapshot mensal de ofertas prepara a preservação histórica por competência;
- cadastra sete drivers de sistema sem executar rateio nesta etapa;
- adiciona API técnica somente de leitura para homologação da fundação.

### Schema
- nova migration `034_dpe_cost_engine_foundation_v09613.sql`;
- `SCHEMA_VERSION = 34`.

## v0.9.6.12 — DPE Reactivation & Mobile Navigation

### DPE
- DPE volta a ficar visível por padrão em autenticação, seletores, Reitoria e rota `/dpe`;
- `HIDDEN_DIRECTORATE_CODES` continua existindo como feature flag, mas o valor padrão agora é vazio;
- `render.yaml` publica `HIDDEN_DIRECTORATE_CODES=""`, evitando que a ausência da variável volte a esconder DPE.

### Responsividade
- DTNH/DCS/DM/DPE recebem o mesmo contrato mobile de sidebar: abrir/fechar, backdrop, toque externo, `Esc`, fechamento ao navegar e bloqueio do scroll atrás do drawer;
- DADM V2 recebe botão explícito de fechamento e estado ARIA consistente;
- Reitoria deixa de ocultar a navegação no mobile e passa a usar drawer lateral alinhado ao padrão institucional.

### Schema
- sem migration nova; schema `33` permanece canônico.

## v0.9.6.11 - DADM Full Attendance Explorer

- Pessoas & Setores lista todos os atendimentos Tallos.
- Filtro Todos / Com avaliacao / Sem avaliacao.
- Ordenacao por maior TME e maior TMA para investigar outliers operacionais.
- Endpoint /api/dadm/v2/entity/attendances adicionado; endpoint rated-only preservado.
- Sem migration nova; schema 33 permanece canonico.

## v0.9.6.10 — Supabase Secret Key & Production Provisioning

### Supabase atual
- `SUPABASE_SECRET_KEY=sb_secret_...` passa a ser a credencial administrativa recomendada para Auth Admin e Storage;
- chaves `sb_secret_...` são enviadas em `apikey`, sem `Authorization: Bearer`;
- `SUPABASE_SERVICE_ROLE_KEY` permanece como fallback para JWT legado e não precisa ser configurada em projetos novos.

### Provisionamento pela Reitoria
- corrige o conflito entre o fluxo `/api/admin/users` e o trigger `on_auth_user_created` da migration 033;
- quando Supabase Auth cria a identidade e o trigger já materializa `profiles/app_users`, a Reitoria reaproveita o mesmo UUID e aplica nome, papel e grants;
- instalações sem o trigger continuam usando o caminho de compatibilidade que cria `AppUser` pelo backend;
- rollback de identidade recém-criada remove a linha `app_users` específica caso o Auth precise ser desfeito.

### DADM
- preserva `dadm@ivc.br` com DADM/EDIT e leitura limitada a Financeiro, Secretaria Acadêmica, Mestrado, Negociação, Prouni/Nbolsa/Fies e Estágio;
- preserva `rodrigo.ghirardelli@ivc.br` com DADM/EDIT e leitura integral de todos os departamentos da DADM.

### Deploy
- `render.yaml` usa `SUPABASE_SECRET_KEY` como segredo server-side;
- `REQUIRE_SCHEMA_VERSION=true` é explícito;
- `DATA_UNIVC_JWT_SECRET` é gerado pelo Render no primeiro Blueprint;
- schema permanece `33`; nenhuma migration `034`.

## v0.9.6.9 — Reitoria Administration & Directorate Visibility

### Reitoria
- novo workspace `/reitoria` com Visão geral, Usuários e acessos e Auditoria;
- login da Reitoria sem diretoria explícita passa a abrir a própria área administrativa;
- `/admin/users` continua aceito por compatibilidade, mas renderiza a nova interface;
- identidade visual própria em `static/css/reitoria.css`, removendo a dependência do antigo `admin-users.css` ausente.

### Identidade e usuários
- criação de usuário passa a usar Supabase Admin Auth no backend;
- novo cadastro recebe nome, e-mail, senha inicial, `REITORIA`/`DIRECTORATE`, status ativo e grants `READ`/`EDIT`;
- usuários existentes podem alterar nome, e-mail, senha, papel e grants;
- senha nunca é gravada em `app_users`, `profiles`, auditoria ou frontend;
- mudança de e-mail/senha e mudanças de autorização invalidam sessões conforme o modelo Identity & Access V2;
- validação de papel/grants ocorre antes de mutar o provedor externo.

### Foto de perfil
- avatares são armazenados em bucket privado `data-univc-avatars` (configurável);
- upload aceita JPEG/PNG/WEBP até 2 MB com validação de assinatura do arquivo;
- leitura é feita por proxy autenticado `/api/profile/avatar/{user_id}`; `SUPABASE_SERVICE_ROLE_KEY` nunca é enviada ao navegador;
- interfaces usam foto quando disponível e iniciais como fallback.

### DPE temporariamente oculta
- `HIDDEN_DIRECTORATE_CODES` centraliza visibilidade de diretorias e vem configurado como `DPE` nesta release;
- DPE deixa de aparecer em `/api/auth/me`, seletores, cards e administração de grants;
- `/dpe` e escopos/API DPE ficam indisponíveis enquanto oculta;
- grants DPE existentes permanecem no banco e são preservados mesmo quando a Reitoria edita outros acessos do usuário;
- usuários com somente grant oculto continuam editáveis sem exigir a concessão artificial de outra diretoria.

### Deploy e schema
- schema permanece `33`; sem migration nova;
- produção precisa configurar `SUPABASE_SERVICE_ROLE_KEY` no backend;
- `render.yaml` inclui `SUPABASE_AVATAR_BUCKET=data-univc-avatars` e `HIDDEN_DIRECTORATE_CODES=DPE`.

## v0.9.6.8 — DM Interactive Excel V3 Beta

- Adiciona o Excel Interativo V3 da Diretoria de Mestrado em paralelo ao relatorio V2.
- Filtros do site apenas inicializam `PARAMETROS`; o workbook recebe a base DM autorizada completa e assume os recortes localmente.
- Inclui PAINEL, DM-01, DM-02, bases operacionais de turmas/alunos, MATRIZ, metas/planos, integracao SEI e qualidade/governanca.
- Adiciona controles por area, turma, comparacao, data de corte, janela, status auxiliar e KPI da matriz, com nomes definidos `P_DM_*`.
- Mantem o dominio atual da DM e o principio de que defesa registrada confirma Titulado; nao exporta os campos legados de diploma.
- Mantem `/api/dm/excel` intacto e adiciona `/api/dm/excel-interativo`; sem alteracao de schema.

## v0.9.6.7 — Academic Interactive Excel V3 · DTNH + DCS

- Generaliza o builder V3 para DCS sem duplicar a implementação DTNH.
- Remove hardcodes `DTNH-*` de fórmulas, títulos e metadados; os códigos são derivados do payload.
- Disponibiliza o beta para DTNH e DCS na Central de arquivos, com nome de download dinâmico.
- Mantém o benchmark NPS geral UNIVC global e os demais recortes no escopo da diretoria.
- Preserva Excel V2, autenticação, DM e DADM; sem alteração de schema.

# Changelog

## v0.9.6.6 — DTNH Interactive Excel V3 Beta

- Adiciona um Excel acadêmico interativo em beta para DTNH, em paralelo ao V2.
- Controles internos de referência, comparação, janela, curso, disciplina e KPI da matriz.
- Três gráficos simultâneos no NPS institucional: DTNH/curso, UNIVC geral e cursos por meta.
- Matrizes e páginas específicas para 01A, 01B, 01C, 02 e 03.
- Bases técnicas ocultas e apenas agregadas; nenhuma linha individual de aluno é exportada.
- Sem alteração de schema.

## v0.9.6.5 — DADM TALLOS Identifier Alignment

- Alinha o escopo limitado da DADM aos `source_key` reais retornados/persistidos pela TALLOS.
- Mantém aliases curtos para compatibilidade com dados locais antigos sem reduzir o escopo real.
- Corrige a apresentação automática de departamentos que apareciam como `Financeiro 12c84`, `Estagio 80bc4`, etc.
- Preserva qualquer nome de exibição salvo manualmente no mapeamento.
- Incrementa o contrato de normalização TALLOS para v4, forçando atualização segura em re-sync.
- Sem alteração de schema.

## v0.9.6.4 — DADM Shared Ingestion & Scoped Visibility

- separa ingestão TALLOS de escopo de leitura na DADM;
- libera teste, cadastro e substituição do token TALLOS para ambos os usuários DADM com `EDIT`;
- mantém sincronização e histórico compartilhados entre `dadm@ivc.br` e `rodrigo.ghirardelli@ivc.br`;
- aplica filtro SQL aos seis setores autorizados de `dadm@ivc.br` em dashboards, filtros, relatórios e qualidade;
- restringe metas/planos e mapeamentos de departamento ao escopo autorizado;
- impede vazamento de nomes de operadores por IDs fora do escopo em relatórios;
- preserva remoção do token/limpeza total como operações de acesso completo;
- corrige o e-mail canônico do Rodrigo para `rodrigo.ghirardelli@ivc.br`;
- sem alteração de schema.

## v0.9.6.3 — DM SEI Workflow Refinement

- Remove os cards explicativos redundantes da tela Integração SEI da DM.
- Simplifica a etapa de conferência para seleção de turmas, data de abertura opcional e confirmação.
- Adiciona controle por turma para informar data de abertura somente quando desejado.
- Preserva abertura existente por padrão e exige intenção explícita para alteração.
- O frontend passa a enviar `opening_dates` e `atualizar_datas_existentes` de acordo com a edição feita na prévia.
- Mantém importção de turma nova sem abertura como fluxo válido.
- Sem alteração de schema.

## v0.9.6.2 — DTNH/DCS Institutional NPS Benchmark

- Mantém os três gráficos do NPS institucional discente sem substituições: diretoria/curso, UNIVC geral e comparação por curso.
- A série da diretoria é agregada a partir de `by_course`; a série UNIVC continua usando o histórico institucional global DTNH + DCS.
- O filtro de curso não altera o gráfico geral UNIVC nem o benchmark por curso.
- Semestre ancora as janelas de evolução; janela não altera o snapshot comparativo por curso.
- Benchmark por curso preserva `meta`, `atencao`, `limite_superior` e `status`, mantendo a legenda semântica por meta.
- Remove os cards "Fonte oficial" dos NPS institucionais discente e docente.
- Sem alteração de schema.

## v0.9.6.1 — Frontend Identity, User Administration & Local Test Harness

- integra `data-univc-auth.js` e `data-univc-identity.js` em todas as superfícies preservadas da v0.8.33;
- `/api/auth/me` passa ao contrato canônico V2 e remove aliases legados;
- bridge de `fetch` same-origin adiciona CSRF e refresh silencioso às chamadas antigas sem substituir os módulos DM/DADM/DPE mais novos;
- ativa proteção CSRF e headers de segurança;
- adiciona `/admin/users` e APIs de administração exclusivas da Reitoria;
- adiciona launcher local com sete identidades, banco de testes persistente e reset explícito;
- ambiente local usa sessão de até 24h e desabilita rate limit rígido;
- preserva DM 0.8.29–0.8.33, SEI e Excel V2;
- schema permanece **33**; não há migration 034.

## v0.9.6.0 — Identity, Session & Authorization Rebase

- rebase da arquitetura de identidade/autorização sobre a v0.8.33.0, sem substituir o domínio DM mais novo;
- adiciona sessão local Data UNIVC com access JWT e refresh opaco rotativo;
- adiciona `app_users`, grants N:N por diretoria e auditoria de autenticação;
- remove cross-read implícito da autorização e fixa routers dedicados ao próprio escopo;
- adiciona proteção por objeto/ID e ownership explícito para imports/runs de pesquisa;
- consolida as antigas migrations de auth em `033_identity_access_security_rebase.sql`, preservando `032_dm_domain_simplification_v08290.sql`;
- mantém temporariamente aliases legados de `/api/auth/me` para o frontend 8.33;
- CSRF/frontend/admin/local harness ficam deliberadamente para v0.9.6.1;
- schema sobe de 32 para **33**.

## v0.8.33.0 — DM Excel V2

- `/api/dm/excel` passa a gerar o novo relatório gerencial V2 com 8 abas alinhadas ao dashboard atual da DM.
- remove da exportação oficial `CALC`, `MATRIZ`, `LISTAS DE APOIO`, `LEIA-ME`, `PAINEL` e demais estruturas técnicas do workbook legado.
- respeita Área, Turma e Data de corte ativos na interface, inclusive nos links de exportação da topbar/dashboard/central de arquivos.
- representa somente o domínio atual de alunos: `Ativo`, `Titulado` e `Desligado`; Data de Defesa é o marco ativo de titulação e Data de Titulação/Situação do Diploma não são expostas.
- adiciona tabelas filtráveis, fórmulas derivadas, gráficos nativos e leitura de metas DM-01/DM-02.
- DM-02 alimenta os gráficos de tempo somente com turmas que possuem tempo calculável, evitando transformar ausência de dado em zero.
- Integração SEI separa indicadores do recorte exportado do histórico institucional de sincronizações.
- modelo Excel de importação de alunos é alinhado ao domínio ativo e deixa de solicitar Data de Titulação/Situação do Diploma.
- builder legado permanece apenas como compatibilidade interna; a rota oficial usa `dm_excel_v2_builder.py`.
- `SCHEMA_VERSION` permanece **32**; não há migration nova.

Detalhes técnicos: `docs/DM_EXCEL_V2_v08330.md`.

## v0.8.32.0 — DM UI Identity & Topbar Convergence

- DM: topbar passa a depender diretamente da fundação `ui-v2` compartilhada com DTNH/DCS, removendo overrides locais do seletor de diretoria.
- DM: cabeçalho usa o código curto `DM`, o seletor adota o mesmo rótulo/acessibilidade acadêmicos e todas as ações atuais são preservadas.
- DM: Exportar usa a convenção `download-link` compartilhada e mantém SEI, Exportar e Nova Turma no mesmo fluxo de ações.
- DM: DM-01, DM-02, Turmas e Alunos passam a usar o ritmo `compact-lead` da identidade acadêmica.
- Sem alterações de domínio ou schema (`SCHEMA_VERSION = 32`).

## v0.8.31.0 — SEI UX & Shared Action Icons

- DM: remove o bloco redundante `Datas que não existem nesse relatório`.
- DM: sincronizações concluídas usam feedback verde para observações informativas; amarelo fica reservado a revisão real/incompletude.
- UI compartilhada: botões de acesso direto/atualização via SEI usam o mesmo símbolo da navegação `Integração SEI`.
- UI compartilhada: rótulos de ações `add` removem o `+` textual quando o ícone de adição é injetado, eliminando `++` em DM e DTNH/DCS.
- Sem alterações de domínio ou schema (`SCHEMA_VERSION = 32`).

# v0.8.30.0 — DM Students & Defenses Simplification

- remove Data de Titulação da tabela, filtros e formulários ativos da DM;
- busca por aluno/matrícula passa a ser o primeiro e maior filtro de Alunos & Defesas;
- filtros acadêmicos ativos passam a usar ingresso e defesa, preservando aliases legados no backend;
- modal de titulação passa a ser centrado em registro de defesa, sem Data de Titulação;
- paginação de alunos ganha primeira/última página e faixa de registros;
- edições pela UI preservam `graduation_date`/`diploma_status` históricos quando esses campos não são enviados;
- schema permanece 32, sem migration nova.

# v0.8.29.0 — DM Domain Simplification & Cohort Lifecycle

- domínio de alunos da DM reduzido a `Ativo`, `Titulado` e `Desligado`;
- legado `Trancado` migra para `Desligado` com preservação do status bruto do SEI;
- qualquer `defense_date` confirma `Titulado`;
- status de turma passa a ser reconciliado automaticamente a partir dos alunos;
- turmas sem alunos ativos e com todos os vínculos terminais passam a `Encerrada`;
- uma turma encerrada volta a `Em andamento` se receber/voltar a ter aluno ativo;
- reconciliação integrada a CRUD, importação, titulação e SEI;
- migration `032_dm_domain_simplification_v08290.sql`; schema 32.

# v0.8.28.1 — Academic Executive Faculty NPS & Sidebar Groups

## v0.8.28.2 — Academic Visual Polish

- padroniza os títulos dos grupos da sidebar acadêmica com o mesmo verde-claro de `NPS Docente`;
- aplica paleta semântica à composição do NPS docente: promotores verdes, neutros âmbar e detratores vermelhos;
- nenhuma migration nova (`SCHEMA_VERSION = 31`).


- adiciona o NPS da Instituição · Docentes (01C) ao Painel Executivo de DTNH/DCS;
- expõe card executivo 01C com resultado, comparação, meta, status, respondentes e fonte;
- adiciona a série semestral 01C ao conjunto de gráficos executivos;
- mantém o 01C institucional/anônimo e sem recorte por curso, coerente com o relatório docente do SEI;
- reorganiza a sidebar acadêmica em NPS Discente, NPS Docente, Indicadores Acadêmicos, Gestão e Sistema;
- schema permanece 31, sem migration.

# v0.8.28.0 — Academic Excel V2

- substitui a exportação acadêmica oficial pela nova arquitetura gerencial de 9 abas;
- remove da rota `/api/excel` as abas técnicas do workbook legado;
- integra 01A, 01B, 01C, 02 e 03 no Resumo Executivo com metas, status, comparação e evolução;
- cria abas agregadas de NPS instituição/alunos, NPS cursos, NPS docentes, avaliação docente, aprovação/resultados e comparação de cursos;
- inclui Metas e Planos e uma aba de Parâmetros que documenta filtros e contrato de privacidade;
- respeita os filtros ativos do dashboard sem exportar nomes/matrículas de alunos ou respostas brutas;
- usa Excel Tables, gráficos nativos e fórmulas para métricas derivadas;
- mantém o builder legado apenas como implementação interna não utilizada pela rota oficial;
- schema permanece 31, sem migration.

# v0.8.27.0 — Academic UI Foundation

- corrige o conflito de CSS dos dialogs acadêmicos: backdrop escuro/translúcido e cartão branco com borda verde suave;
- cria seletor acadêmico compartilhado de Ano + Semestre, mantendo `AAAA-SEM1/SEM2` somente no payload interno;
- aplica o seletor aos lançamentos manuais de avaliação docente/resultados e aos fluxos NPS SEI/XLSX/ZIP;
- adiciona primeira e última página ao componente compartilhado de paginação, com acessibilidade por `aria-label`;
- elimina overflow horizontal da sidebar acadêmica sem remover o scroll vertical necessário;
- schema permanece 31, sem migration.

# v0.8.26.0 — Academic NPS Visualization & UX

- quebra nomes longos de cursos em até duas linhas nos gráficos comparativos, preservando o nome completo no tooltip;
- colore comparações de NPS por status de meta: verde (dentro), amarelo (atenção), vermelho (fora) e neutro (sem meta);
- NPS do Curso usa a meta efetiva 01B por curso, com fallback para TOTAL;
- detalhamento por curso do NPS Institucional usa a meta 01A institucional TOTAL;
- adiciona legenda gerencial e metadados de meta/status aos tooltips;
- tabela executiva de comparação NPS pode exibir Meta e Status no semestre selecionado;
- mantém NPS docente 01C sem comparação por curso, coerente com a fonte anônima;
- schema permanece 31, sem migration.

# v0.8.25.0 — Academic Faculty NPS 01C

- adiciona `DTNH/DCS-01C` como **NPS da Instituição · Docentes**;
- fonte factual única e institucional por semestre, sem curso/professor/disciplinas por causa do anonimato do relatório;
- metas 01C permanecem específicas de DTNH/DCS e aceitam somente recorte `TOTAL`;
- integra SEI direto e upload XLSX/ZIP ao mesmo parser institucional docente;
- preserva questionários sem pergunta NPS 0–10, mas não converte respostas categóricas em NPS;
- adiciona workspace docente com evolução, composição, fonte oficial e histórico;
- cria migration `031_academic_faculty_nps_v08250.sql` e eleva o schema para 31.

# v0.8.24.0 — Academic NPS Core 01A/01B

- formaliza `DTNH/DCS-01A` como NPS da Instituição · Alunos e `DTNH/DCS-01B` como NPS do Curso;
- migra metas e planos legados `-01` somente para `-01B`, preservando o significado histórico;
- adiciona NPS institucional ao Painel Executivo com meta, comparação, série e cobertura próprias;
- mantém o NPS institucional agregado entre DTNH + DCS pelas contagens reais;
- limita o detalhamento por curso do NPS institucional à diretoria em visualização;
- retorna meta e status na comparação executiva de NPS por curso;
- restringe metas 01A ao recorte TOTAL e 01B a TOTAL/curso ativo;
- adiciona migration `030_academic_nps_kpi_split_v08240.sql`; schema passa a 30.

# v0.8.23.3 — DADM V2 Motion & UX

- sidebar DADM passa a animar largura junto do conteúdo principal e da barra de carregamento, alinhando o comportamento a DTNH/DCS;
- filtros, modais, backdrop mobile, alertas e chips ganham entrada/saída suave;
- cards e botões recebem microinterações discretas;
- gráficos ganham animações visuais de linha, barra, ponto e preenchimento sem alterar dados ou escalas;
- navegação respeita `prefers-reduced-motion`, inclusive no scroll programático;
- nenhuma regra TALLOS, meta, plano, relatório ou filtro foi alterada;
- schema permanece 29.

# v0.8.23.2 — DADM V2 Reporting UI Integration

- conecta `/api/dadm/v2/report.xlsx` ao frontend oficial da DADM;
- reutiliza diretamente `NS.filterParams(state.filters)`, sem criar filtros paralelos para o Excel;
- adiciona confirmação do recorte antes do download e aviso explícito de exportação agregada;
- mantém relatório disponível em modo somente leitura, pois a operação não altera dados;
- aproxima a topbar da composição DTNH/DCS sem remover seletor, badge de acesso ou estado TALLOS;
- adiciona tratamento de download autenticado, nome de arquivo e erros de geração na interface;
- sem nova migration; schema permanece 29.

# v0.8.23.1 — DADM V2 Reporting Engine

- adiciona `/api/dadm/v2/report.xlsx` para exportação agregada TALLOS V2;
- respeita período, departamento, operador, canal, status e tabulação do contrato analítico;
- não exporta linhas individuais de atendimento nem dados pessoais de clientes;
- inclui Resumo, evolução mensal, totais por departamento/operador, visões entidade × mês, distribuição de avaliações e parâmetros de auditoria;
- usa tabelas e gráficos nativos do Excel e fórmulas para métricas derivadas;
- remove limites de apresentação do dashboard da consulta de relatório, sem remover limites de segurança do período;
- mantém avaliação 1–10 sem inferir percentual de satisfação;
- sem nova migration; schema permanece 29.

# v0.8.23.0 — DADM V2 Primary Convergence

- promove `dadm_v2.html` para a rota canônica `/dadm`; `/dadm/v2` vira redirect e o frontend antigo fica temporariamente em `/dadm/legacy`;
- integra seletor de diretoria, modo edição/leitura e sidebar recolhível persistente ao shell da DADM V2;
- corrige tooltips nas bordas medindo dimensões reais antes do posicionamento;
- adiciona gestão TALLOS V2 com metas versionadas para TME, TMA, avaliação média e cobertura, além de planos de ação;
- isola metas/planos V2 do contrato legado sem migration nova, usando namespace de recorte `V2:*`;
- exibe metas vigentes nos KPIs e linhas de referência nos gráficos;
- incorpora a governança de nomes de departamentos TALLOS em Dados & Integração;
- mantém histórico temporal real das entidades e comparação de períodos arbitrários;
- schema permanece 29.

# v0.8.22.0 — UI Foundation + experiência de sincronização

- congela a arquitetura de informação aprovada da DADM V2 e faz apenas convergência visual/comportamental;
- introduz a fundação compartilhada `data-univc-foundation.css` + `data-univc-ui.js`;
- unifica tokens de cor, superfícies, bordas, sombras, motion, formulários, ícones e progressos;
- move o usuário da DADM V2 para o rodapé da sidebar e padroniza token TALLOS;
- substitui placeholders/símbolos de navegação por SVGs consistentes; SEI ganha ícone de integração/sincronização;
- corrige a causa do progresso TALLOS regressivo: o cliente pré-planeja a primeira página de todos os chunks antes de processar registros e fixa `total_expected`;
- adiciona progresso compartilhado às operações SEI do DM e às operações bloqueantes do shell acadêmico (DTNH/DCS);
- usa progresso indeterminado quando não existe contrato backend de total, evitando percentuais fictícios;
- comparação DADM V2 de um mês usa snapshot horizontal em vez de linha com pontos sobrepostos;
- melhora posicionamento de tooltip nas bordas dos gráficos;
- sem migration nova; schema permanece 29.

# v0.8.21.0 — DADM V2 · fundação de experiência gerencial

- cria `/dadm/v2` em paralelo ao frontend anterior;
- reduz a navegação a cinco áreas orientadas às perguntas do gestor;
- adiciona contexto global persistente e seleção visual de mês inicial/final;
- unifica Operadores e Departamentos em um explorer simétrico com visão geral e perfil individual;
- permite analisar uma entidade sozinha e só depois adicioná-la à comparação;
- reorganiza a Visão Geral em Operação, Eficiência e Experiência;
- explicita Tempo Médio de Espera (TME) e Tempo Médio de Atendimento (TMA);
- centraliza avaliação 1–10, cobertura e amostra na área Experiência;
- adiciona comparação de entidades e períodos;
- move conexão, sincronização e qualidade para Dados & Integração;
- adiciona endpoints `/api/dadm/v2/context`, `/overview`, `/entity`, `/experience` e `/quality`;
- mantém schema 29 e a ingestão TALLOS existente.

# v0.8.20.3 — Contrato TALLOS 1–10 e leitura mensal por operador

- Reconcilia a avaliação com a exportação oficial TALLOS: `S/A` é ausência; valores numéricos válidos são 1–10; `level=0` passa a ser tratado como ausência na homologação atual.
- A exportação de referência continha 536 linhas, 32 avaliações numéricas e 504 `S/A`; distribuição observada: 24 notas 10, 4 notas 9, 1 nota 8, 1 nota 7 e 2 notas 3. Não havia nota 0.
- Corrige o motor para ignorar defensivamente qualquer `rating` fora de 1–10 em médias, contagens, distribuição, operadores, departamentos, timelines e comparações.
- Adiciona leitura **operador × mês**, mantendo mês sem avaliação como `NULL/—`.
- Preserva avaliação por sessão (`source_id`) quando um protocolo passa por vários operadores.
- Substitui presets de janela por `Mês inicial` e `Mês final`.
- DADM-01/DADM-02 passam a ter visão principal alimentada pelo TALLOS; o legado manual fica apenas em área recolhida de compatibilidade.
- Explicita **Tempo Médio de Espera (TME)** e **Tempo Médio de Atendimento (TMA)** em cards, gráficos e tabelas.
- Adiciona auditoria de avaliação bruta/normalizada e reduz controles redundantes.
- `TALLOS_NORMALIZATION_VERSION = 3`; migration 029; schema 29.

> As interpretações anteriores da v0.8.20.1/v0.8.20.2 que aceitavam nota 0 como avaliação foram superadas pela reconciliação desta release.

# v0.8.20.2 — Avaliação sem falso zero

- Corrige um erro exclusivamente de representação no frontend: em JavaScript, `Number(null) === 0`, então períodos sem avaliação podiam aparecer como `0/10` nas linhas temporais e operadores sem avaliação podiam cair no eixo zero da matriz TMA × avaliação.
- O backend já calculava `AVG(rating)` corretamente sobre apenas valores não nulos; a v0.8.20.2 preserva essa regra e agora o frontend também diferencia explicitamente `NULL` de uma nota real `0`.
- Um mês/dia com zero avaliações fica sem ponto no gráfico e quebra a linha; não é convertido em nota zero.
- Uma nota `0` continua válida somente quando a TALLOS realmente envia `level = 0`.
- Comparações, linhas temporais, barras e a matriz de operadores passam a rejeitar `null`/`undefined`/string vazia antes de converter valores numéricos.
- `SCHEMA_VERSION = 28`; nenhuma migration nova.

# v0.8.20.2 — Correção da escala TALLOS 0–10

- Corrige o erro da v0.8.20.0 que aceitava `level` apenas entre 1 e 5. Notas 0 e 6–10 eram transformadas em `NULL`, deixando a média artificialmente baixa.
- Registros realmente sem avaliação continuam `NULL` e são ignorados pela média; agora o painel exibe explicitamente avaliações válidas, cobertura e atendimentos sem avaliação.
- Toda a experiência de avaliação passa para escala 0–10: média, distribuição 0–10, barras, donut, ranking de operadores/departamentos, timeline e matriz TMA × avaliação.
- TME é identificado na interface como **Tempo Médio de Espera** (`tme.value`, provisório); TMA como **Tempo Médio de Atendimento** (`tma.value`, validado).
- Remove a conversão automática de notas TALLOS para satisfação DADM-02. A regra institucional fica separada até ser formalmente definida para a escala 0–10.
- `TALLOS_NORMALIZATION_VERSION = 2` integra o `source_hash`, permitindo que um novo sync regrave registros antigos com a normalização corrigida.
- Migration `028_dadm_tallos_rating_scale_v08201.sql` amplia a restrição de 1–5 para 0–10 e recupera avaliações já coletadas a partir do JSON sanitizado; SQLite local possui reparo equivalente no `init_local.py`.
- `SCHEMA_VERSION = 28`.

# v0.8.20.0 — DADM TALLOS Homologação Real

- ambiente DADM local isolado e sem seed demonstrativo;
- configuração guiada de token TALLOS somente fora de produção;
- teste de autenticação antes de salvar/sincronizar;
- onboarding em três etapas e sincronização de agosto/2026 como golden dataset;
- progresso/histórico de sincronização mais legível;
- limpeza controlada da base TALLOS local;
- experiência de avaliações reforçada com estrelas, donut, barras e faixas de satisfação;
- nenhum schema novo (`SCHEMA_VERSION = 27`).

## v0.8.19.0 — DADM TALLOS Analytics Center

- incorpora o TALLOS Analytics Center dentro da DADM, sem criar um aplicativo visual paralelo;
- preserva DADM-01/DADM-02 como indicadores institucionais e mantém fatos TALLOS fora de `ManagementMeasurement`;
- adiciona fatos operacionais persistentes, UPSERT idempotente, histórico de sincronizações e mapa governado de departamentos;
- adiciona filtros e comparações históricas por período, operador, departamento, canal, status e tabulação;
- adiciona TMA/TME, média/mediana/P90, volume, protocolos, pessoas, estrelas, cobertura, canais, transferências e mensagens;
- adiciona ranking e comparação de operadores e matriz TMA × avaliação;
- mantém TME como provisório e TMRO/TMRC como experimentais até validação dirigida;
- preserva privacidade excluindo nome, telefone, CPF e CNPJ da camada analítica;
- nova migration `027_dadm_tallos_analytics_v08190.sql`; schema 27;
- novo contrato técnico em `docs/DADM_TALLOS_ANALYTICS_CENTER.md`.

## v0.8.18.0 — Query Performance

- Avaliação Docente: tabela, pesquisa e filtros server-side; KPIs/evolução/comparação agregados no SQL.
- Snapshot acadêmico: avaliação docente consolidada no banco por semestre/curso/disciplina.
- DADM: dashboard substitui leitura histórica ilimitada por competências limitadas à janela + histórico técnico mínimo/comparação.
- DPE financeiro: snapshot limitado a `janela + 11` competências, preservando rolling 12 meses.
- Novos testes de regressão de bounded reads e equivalência matemática.
- `SCHEMA_VERSION` permanece 26; sem migration nova.

## v0.8.17.0 — Cleanup e Performance I

- remove frontend DADM/DPE morto do shell acadêmico, preservando redirects canônicos;
- DPE: elimina N+1 de despesas/rateios com prefetch em duas consultas;
- Resultados Acadêmicos: novo importador batch com validação pura, prefetch de catálogo/alunos/duplicidades e inserts em lote;
- fallback automático para o importador legado em colisão de integridade inesperada;
- testes de regressão impedem retorno do N+1 e do padrão SQL por linha;
- benchmark sintético: 1.000 resultados de 6.005 para 16 statements; 100 despesas de 101 para 2 statements;
- stress batch validado em 50k/100k linhas no SQLite sintético;
- build fingerprint agora cobre toda a superfície runtime;
- sem nova migration; schema permanece 26.


## v0.8.15.1 — DM simplificado
- Remove Diploma e Orientador da visão operacional de Alunos/Defesas/Titulação.
- Titulado passa a pressupor diploma concluído na interface; novas titulações registram `Emitido` internamente para compatibilidade.
- Mantém dados históricos de orientador e diploma no banco/API, sem exibi-los no fluxo principal.
- Simplifica filtros para dados acadêmicos: defesa/titulação.
- Mantém data de defesa opcional e data de titulação opcional para históricos incompletos.
## 0.8.15.1 - UI/UX full rollout

- expande `ui-v2` para DTNH/DCS, DADM, DPE e DM;
- reestiliza o workspace gerencial legado com a mesma identidade institucional;
- unifica sidebar, topbar, iconografia, filtros, KPI cards, tabelas, modais e microinterações;
- cria padrões específicos para operational analytics (DADM/DM) e financial analytics (DPE);
- reduz textos de ações recorrentes e prioriza botões compactos com contexto/tooltip;
- adiciona paridade de navegação mobile nas diretorias especializadas;
- amplia o fingerprint do build para incluir os frontends especializados;
- preserva IDs, hooks JS, endpoints e regras de negócio;
- sem alteração de schema/migration.

## 0.8.14.0 - UI/UX pilot: Design System Data UNIVC

- adiciona `static/css/ui-v2.css` e `static/js/ui-v2.js` como camada visual opt-in;
- aplica o novo shell institucional a DTNH/DCS e DM sem alterar IDs, endpoints ou regras de negócio;
- sidebar verde institucional recolhível, ícones SVG e navegação mobile equivalente no DM;
- topbar e ações compactadas;
- novo tratamento visual para dashboard acadêmico, NPS e alunos/titulação do DM;
- melhora hierarquia de KPIs, filtros, gráficos, tabelas, estados de foco e microinterações;
- adiciona `prefers-reduced-motion`;
- DADM/DPE continuam no visual atual nesta fase piloto.

## 0.8.13.1 - DM: defesa opcional para alunos titulados

- Permite status `Titulado` mesmo quando a data histórica da defesa não estiver disponível.
- Titulação individual e em lote não é mais bloqueada por defesa ausente.
- Validações cronológicas continuam sendo aplicadas quando a defesa é conhecida.
- A interface sinaliza titulados sem defesa e adiciona filtro documental específico.
- Não exige nova migração de banco; reutiliza a estrutura criada na migração 025.

## 0.8.13.0 - DM: titulação em lote e diploma digital

- Adiciona `graduation_date` e `diploma_status` ao aluno de mestrado, sem preencher artificialmente históricos antigos.
- Adiciona auditoria em `dm_graduation_events`.
- Nova prévia/commit de titulação individual e em lote, com validação de defesa, ingresso, qualificação e titulação.
- A página Alunos e defesas passa a ser **Alunos, defesas e titulação**, com barra contextual, seleção de todos os filtrados e filtros documentais.
- Turmas ganham ação **Gerenciar titulação**, abrindo os alunos ativos da turma para seleção segura.
- Exportação/importação Excel recebe Data de titulação e Situação do diploma preservando o layout histórico das primeiras colunas.
- Nova migração: `025_dm_graduation_digital_diploma_v08130.sql`.

## 0.8.11.0 - NPS analítico por semestre, curso e janela histórica

- NPS do Curso ganhou filtros combináveis por semestre e curso.
- NPS do Curso ganhou janela configurável de 4, 6, 8, 12 semestres ou todo o histórico.
- A aba exibe evolução temporal e comparação entre cursos no semestre selecionado/mais recente.
- NPS da Instituição ganhou os mesmos filtros e gráficos.
- A segmentação do NPS institucional por curso é recalculada a partir dos agregados brutos do questionário oficial do SEI; o total institucional oficial permanece inalterado.
- Tabelas e cartões respeitam os recortes selecionados e exibem contexto explícito.
- O fingerprint do build agora inclui também a integração de pesquisas e a interface acadêmica, facilitando diagnóstico de deploy.

## 0.8.10.0 - Educação Física: reconstrução do fluxo e diagnóstico de deploy

- remove definitivamente qualquer identidade por prefixo de turma (`EFB`/`EFL`);
- valida Bacharelado/Licenciatura exclusivamente pelo campo `Curso:` do XLSX;
- reproduz, apenas para Educação Física, o POST de inicialização `form:j_idt477` observado nos HARs manuais;
- valida o XLSX imediatamente após o download (curso + ano + semestre) antes de importar;
- repete uma vez todo o fluxo de Educação Física se o download revelar estado JSF cruzado;
- adiciona fingerprint de build e política de identidade à API/UI;
- adiciona invariant de startup para impedir um build misto com a validação legada;
- entrega flat ZIP para evitar que um deploy continue iniciando um `app.py` antigo na pasta raiz.

## 0.8.9.5 - SEI acadêmico: estado JSF real no imprimirExcel

- Corrige a diferença entre o navegador e o robô na geração do XLSX: após selecionar o curso, o conector serializa o formulário principal devolvido pelo RichFaces e o reutiliza no clique de `imprimirExcel`.
- Checkboxes marcados sem `value` explícito são enviados como `on`, conforme o comportamento HTML e o HAR real.
- Antes do Excel, valida que ano, semestre e curso do formulário continuam no contexto solicitado.
- Mantém Educação Física Bacharelado/Licenciatura separadas pelo campo `Curso:` do XLSX; turno e prefixos EFB/EFL continuam sem definir a habilitação.
- Sem alteração de schema/migration.

## 0.8.9.4 - Educação Física: identidade por Curso do XLSX

- Bacharelado e Licenciatura permanecem cursos distintos no Data UNIVC.
- `EFB`/`EFL` no nome da turma não são mais usados para decidir a habilitação.
- A identidade passa a ser validada exclusivamente pelo campo `Curso:` do XLSX do SEI.
- Licenciatura e Bacharelado usam `INTEGRAL - NOTURNO` apenas como escolha determinística; Matutino/Noturno geram o mesmo relatório e não definem a habilitação.
- A sincronização exibe a versão do build e o curso efetivamente encontrado no XLSX para facilitar diagnóstico de deploy/cache.

# Changelog resumido

O pacote de produção não carrega mais um arquivo de release/patch/validação para cada versão. O histórico detalhado permanece nos pacotes antigos; aqui ficam apenas os marcos arquiteturais necessários para manutenção.

## 0.8.9.3 hotfix — identidade de Educação Física no XLSX

- Licenciatura seleciona `INTEGRAL - MATUTINO` conforme o HAR real fornecido;
- Bacharelado permanece em `INTEGRAL - NOTURNO`;
- os prefixos/códigos de turma `EFB` e `EFL` deixam de definir a habilitação;
- a identidade passa a ser validada pelo campo `Curso:` de cada bloco do XLSX;
- continua proibida a importação cruzada: um bloco `Educação Física (Bac. Presencial)` não pode entrar quando Licenciatura foi solicitada, e vice-versa.

## 0.8.9.3 — Estado persistente do seletor acadêmico SEI

- toda pesquisa de curso normaliza o DataScroller RichFaces para a página 1 antes de procurar o alvo;
- corrige o cenário Bacharelado (página 2) → Licenciatura (página 1) na mesma sessão;
- a correção pertence ao núcleo acadêmico compartilhado de DTNH e DCS;
- o formulário de integração abre no semestre corrente, em vez de fixar semestre 1;
- falhas de download/seleção e de importação XLSX passam a ser reportadas por curso/etapa sem derrubar toda a sincronização.

## 0.8.9.2 — Correção do fluxo SEI de Educação Física

- validação contra respostas sanitizadas do HAR real, não apenas fixtures sintéticas;
- Bacharelado e Licenciatura passam a preferir a configuração `INTEGRAL - NOTURNO` observada no navegador;
- busca usa o mesmo termo `Educ` capturado;
- `MapaNotaAlunoPorTurmaRel_unidadeTurmaDiscSala` é enviado desde o início do fluxo;
- removido o AJAX extra de `form:tipoLayout` que não existe na sequência real;
- paginação RichFaces e melhorias de estado permanecem compartilhadas por DTNH e DCS.


## 0.8.9 — Identidade UNIVC e perfil do usuário

- Logo oficial incorporada ao login e à navegação de todos os módulos.
- Cartão de perfil no rodapé com nome, iniciais, papel e diretoria.
- DADM, DPE, DM e painel gerencial passam a compartilhar a mesma linguagem visual de identidade e sessão.
- Cache-busters dos módulos atualizados para evitar CSS antigo após deploy.

## 0.8.8 — Educação Física Bacharelado/Licenciatura + conector acadêmico compartilhado

- DCS passa de 7 para 8 cursos, separando Educação Física - Bacharelado e Educação Física - Licenciatura;
- o histórico legado de Educação Física é migrado para Bacharelado preservando o mesmo `course_id`;
- paginação do seletor de cursos do SEI passa a ser genérica e compartilhada por DTNH/DCS;
- seleção usa semanticamente a ação `Selecionar`, sem hardcode de linha ou `j_idt`;
- aliases canônicos são aplicados ao SEI, ao XLSX bruto, ao NPS de questionários e aos imports acadêmicos;
- o fluxo automático valida se o curso dentro do XLSX é realmente o curso solicitado antes de gravar;
- os XLSX reais de Bacharelado e Licenciatura foram usados somente para validação local e não são distribuídos no pacote.

## 0.8.7 — Áreas independentes de NPS

- NPS da Instituição e NPS do Curso deixam de ser subabas de uma tela única e ganham entradas próprias no menu acadêmico;
- cada área possui botão, estado vazio, histórico e formulário de atualização próprios;
- o motor SEI continua compartilhado, mas o fluxo recebe um escopo fixo (`institution` ou `course`) desde a abertura;
- o passo final mostra somente a pergunta oficial do NPS escolhido;
- backend bloqueia a mesma pergunta como fonte dos dois NPS no mesmo semestre;
- sem migration de banco: a estrutura dual criada na v0.8.6 é preservada.

## 0.8.6 — NPS da Instituição + NPS do Curso

- remoção do fluxo e do modelo Excel de **Importar legado** para NPS;
- XLSX/ZIP permanece como contingência dentro da própria integração SEI;
- duas perguntas oficiais 0–10 independentes: NPS da Instituição e NPS do Curso;
- NPS da Instituição consolidado a partir de DTNH + DCS pelas contagens reais, com indicador de cobertura do semestre;
- NPS do Curso preserva a projeção acadêmica e o histórico por curso já existentes;
- fontes oficiais das duas métricas são versionadas separadamente.

## 0.8.5 — Avaliações SEI + NPS automatizado

- integração de questionários do SEI ao Data UNIVC principal;
- XLSX/ZIP automático ou manual no mesmo pipeline;
- uma pergunta oficial 0–10 por semestre para NPS;
- preservação das distribuições e rastreabilidade da fonte;
- mapeamento de curso respeitando diretoria e modalidade;
- fundação relacional de avaliação docente.

## 0.8.4 — Resultado econômico por curso

- DPE passou a apresentar receita, custo/despesa, resultado, despesa/receita e margem;
- tratamento explícito de apuração incompleta.

## 0.8.3 — Gráficos DPE

- gráficos interativos e tooltips;
- melhoria de legibilidade e explicações das métricas.

## 0.8.2 — Metas DM simplificadas

- DM-01: membros por turma;
- DM-02: tempo médio até a defesa.

## 0.8.0–0.8.1 — DM centrado em turmas

- sincronização SEI de turmas e alunos;
- datas individuais confirmadas;
- metas próprias da diretoria.

## 0.7.7–0.7.9 — DPE/DADM/DM

- base financeira única da DPE;
- padronização dedicada da DADM;
- atualizações seletivas e datas SEI da DM.

## 0.7.3–0.7.6 — módulos dedicados e análise acadêmica

- evolução do DM por turmas;
- integração SEI do mestrado;
- padronização DTNH/DCS;
- análise acadêmica por curso, disciplina e professor.

## 0.5.x–0.6.x — fundação acadêmica e Excel

- resultados acadêmicos, filtros, catálogo de cursos;
- NPS semestral;
- importação/exportação Excel e painéis acadêmicos.

## v0.8.16.0 — Foundation arquitetural

- Runtime DADM/DPE deixou de importar módulos de `scripts/`; dados/seeds demonstrativos foram movidos para `demo_data.py` e `demo_seed.py`.

- Golden Baseline reproduzível da v0.8.15.1.
- `pytest` passa a descobrir todo `test_*.py`; perfis SMOKE / PR / RELEASE centralizados em `scripts/run_test_gate.py`.
- `run_release_checks.py` deixa de estar congelado na v0.8.10.0 e delega ao gate RELEASE atual.
- versão da aplicação centralizada em `release_info.py`.
- migration 026 introduz ledger explícito de versão do schema.
- `/api/health/ready` bloqueia produção quando código e schema divergem.
- builder de release separa artefato SOURCE de artefato PRODUCTION e elimina DBs/caches/testes do deploy produtivo.
- nenhuma regra acadêmica, DADM, DPE, DM, NPS, SEI ou financeira foi alterada.

## v0.8.19.0 — DADM / TALLOS Analytics Center

- DADM reconstruída para incorporar o TALLOS Analytics Center sem abandonar DADM-01/DADM-02, metas, planos e governança;
- fatos TALLOS persistidos em `dadm_tallos_attendances`, sem CPF/CNPJ/telefone/nome do cliente;
- sincronização idempotente por `source_id`, com UPSERT e histórico em `dadm_tallos_sync_runs`;
- filtros temporais, por operador, departamento, canal, status e tabulação executados server-side;
- comparação de período anterior, janela deslocada um mês e mesmo período do ano anterior;
- TMA, mediana/P90, avaliação, distribuição de estrelas, canais, operadores e departamentos;
- mapeamento governado de identificadores de departamento TALLOS;
- migration 027 eleva o schema esperado para 27;
- frontend permanece HTML/CSS/JS puro e reutiliza o Design System `ui-v2`.

## 2026-09-29 — Parte 7 — Excel Interativo acadêmico oficial

- promove `/api/excel-interativo` de beta para produto oficial em DTNH/DCS;
- remove `beta` do botão, fallback de download, Content-Disposition e metadados do workbook;
- reorganiza o workbook seguindo o princípio estrutural do painel institucional de referência;
- expõe banco gerencial em abas separadas e tabelas Excel filtráveis;
- mantém CALC, listas e bases técnicas como camada interna oculta;
- amplia o PAINEL para cinco gráficos executivos;
- preserva a favorabilidade docente vigente em %, sem restaurar a antiga métrica 0–10;
- mantém `/api/excel` tradicional em paralelo;
- sem migration nova; schema permanece 49.

## 2026-10-01 — Parte 10 — Auditoria final integrada

- endurece os domínios das metas acadêmicas: NPS -100/+100; favorabilidade e aprovação 0-100%;
- impede limiar de atenção acima da meta e limite superior abaixo da meta nos KPIs acadêmicos de direção positiva;
- aplica os mesmos limites no formulário web;
- fixa em 0-100% o eixo da composição Promotores/Neutros/Detratores no Excel Interativo;
- adiciona preflight explícito para `dpe_cost_v2.py`, migration 049 e helpers ativos do bootstrap;
- mantém schema 49 sem migration nova;
- regressão final: 208 testes aprovados e 2 ignorados.


## 0.13.0 · Parte 13 · 2026-10-01

- DM: consolida fragmentos seguros da mesma turma lógica no relatório SEI (`17-CTE` + `17-CTE Mestrado Univc`).
- Reitoria: painel acadêmico reconstruído em telas NPS, Avaliação Docente e Notas/Aprovação; administração separada.
- Sem migration nova; schema 49.
