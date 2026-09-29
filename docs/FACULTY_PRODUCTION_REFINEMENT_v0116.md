# v0.11.6 — Avaliação Docente · Refinamento de Produção

## Objetivo

A v0.11.6 transforma a consolidação técnica do KPI 02 em uma leitura operacional para uso recorrente. A definição da favorabilidade criada nas versões anteriores não muda: esta etapa melhora período padrão, comparação longitudinal, metas, qualidade, pendências e auditoria de importações.

Não há nova fonte de dados, nova escala ou nova tabela. A camada `faculty_*` e a métrica `faculty_favorability_pct_v1` continuam sendo a fonte oficial.

## Semestre atual por padrão

Ao entrar na Avaliação Docente, a interface seleciona automaticamente o semestre mais recente que possui contextos importados para a diretoria/recorte disponível.

O usuário continua podendo selecionar **Todos os semestres** ao limpar os filtros. O comportamento inicial apenas evita que a primeira leitura misture períodos históricos em um único percentual.

## Leitura operacional

Foi criado o endpoint:

`GET /api/surveys/faculty-student/analytics/operational`

Ele combina, sem persistir uma segunda métrica:

- semestre atual do recorte;
- favorabilidade corrente;
- semestre anterior comparável;
- variação em pontos percentuais;
- meta percentual vigente;
- status em relação à meta;
- distância até a meta em pontos percentuais;
- cobertura de respostas classificadas;
- diagnóstico de identidade acadêmica;
- última importação relacionada ao período;
- estado de prontidão do indicador.

Estados possíveis de prontidão:

- `ready` — indicador calculável, identidade íntegra e meta disponível;
- `ready_no_goal` — indicador calculável, porém sem meta percentual vigente;
- `blocked_scale` — existe alternativa ainda não mapeada e a favorabilidade está suspensa;
- `blocked_identity` — existe bloqueio estrutural na malha acadêmica;
- `no_data` — não existe dado importado para o semestre/recorte.

A interface oferece ação direta conforme o estado: configurar meta, revisar importações, revisar perguntas ou importar relatório.

## Histórico longitudinal

`GET /api/surveys/faculty-student/analytics/semesters/compare` foi enriquecido. Cada semestre agora informa também:

- `previous_semester`;
- `delta_percentage_points`;
- `goal`;
- `goal_status`;
- `gap_to_goal_percentage_points`.

A variação é sempre expressa em **pontos percentuais**, não em crescimento percentual relativo.

A série visual passa a exibir a meta vigente de cada período como linha pontilhada e usa o status da meta para os pontos do gráfico.

## Metas

Somente metas `DTNH-02`/`DCS-02` com `metric_version = faculty_favorability_pct_v1` participam da leitura operacional.

Metas legadas 0–10 continuam preservadas para auditoria, mas não aparecem como meta vigente da Avaliação Docente.

A seleção segue a hierarquia já usada pelo Data UNIVC:

1. disciplina específica;
2. curso específico;
3. TOTAL da diretoria.

A meta permanece válida até que outra meta do mesmo nível entre em vigor.

## Cobertura e qualidade

A Visão Geral passa a destacar **Cobertura classificada**, calculada como a proporção das seleções das perguntas docentes que pertencem ao denominador da favorabilidade.

Isso não altera o cálculo do KPI. O objetivo é tornar visível quando existe volume relevante de `Não sei`/equivalentes ou categorias não classificáveis.

A área Importações agora apresenta os bloqueios e avisos de identidade com suas mensagens, em vez de mostrar somente contagens agregadas.

## Auditoria de importações

O histórico de lotes reutiliza `audit_log` e passa a informar:

- última atividade registrada para o lote;
- usuário/e-mail responsável pela última importação;
- número de operações de importação no mesmo run;
- quantidade importada, já existente e não mapeada na última operação;
- resoluções manuais já persistidas.

Nenhuma coluna adicional foi criada no banco.

## Banco e deploy

Schema esperado: **40**.

Não existe migration nova na v0.11.6. O ambiente precisa apenas já estar compatível com a migration 040 da v0.11.5.

## Verificação

A release inclui `scripts/verify_faculty_student_v0116.py`.

No lote real de homologação, a verificação confirmou:

- 737 relatórios encontrados;
- 603 XLSX da Graduação abertos e validados por conteúdo;
- recorte real de 12 contextos DCS importado em SQLite temporário;
- favorabilidade operacional calculável;
- meta aplicada corretamente;
- zero bloqueio estrutural de identidade no recorte;
- usuário da importação recuperado pelo audit log;
- suíte acumulada v0.11.1–v0.11.6 aprovada.
