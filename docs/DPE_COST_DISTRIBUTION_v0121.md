# Data UNIVC v0.12.1 — DPE Cost Distribution Workbench

## Objetivo

A v0.12.1 transforma a área **Distribuição de custos** em uma mesa de trabalho operacional, sem substituir o Allocation Engine já consolidado. O usuário passa a enxergar, antes de recalcular o mês, **qual despesa será distribuída, para quem, por qual critério, com qual resultado e se a soma reconcilia**.

Esta versão também cria **Políticas de distribuição reutilizáveis**, permitindo reaproveitar o tratamento de despesas recorrentes em competências futuras sem reescrever resultados históricos.

## Escopo desta versão

- mesa de trabalho com Despesa, Valor, Destino econômico, Critério e Situação;
- busca textual e filtro de pendências/prontas;
- múltiplos destinos apresentados em seletor pesquisável;
- explicação administrativa dos critérios já existentes;
- prévia obrigatória antes de salvar a configuração de uma despesa;
- reconciliação explícita da prévia individual;
- prévia consolidada da competência antes de gerar nova versão do rateio;
- comparação entre custo confirmado e nova prévia por curso/oferta;
- políticas reutilizáveis de distribuição;
- sugestão automática de política para despesa recorrente com a mesma descrição;
- desativação de política sem apagar histórico;
- migration 041, aditiva, para persistência das políticas;
- novos testes automatizados da v0.12.1.

## Mesa de trabalho

A tabela principal de Distribuição de custos agora apresenta diretamente:

- descrição da despesa;
- valor;
- destino econômico;
- critério;
- situação da configuração;
- ação de revisão.

O destino é resumido em linguagem administrativa:

- curso específico;
- N cursos específicos;
- todos os cursos presenciais;
- cursos do professor, quando a folha usa horas docentes;
- ainda não definido.

A busca permite localizar uma despesa por texto e o filtro permite separar itens que precisam de revisão dos itens prontos.

## Critérios preservados

O motor existente continua responsável pelos critérios:

- `DIRECT` — destino direto;
- `TEACHER_HOURS` — horas docentes;
- `OFFERING_HOURS` — carga horária da oferta;
- `STUDENTS` — alunos ativos;
- `REVENUE` — receita líquida;
- `EQUAL` — divisão igual;
- `MANUAL` — percentual ou valor definido pelo usuário.

A v0.12.1 não cria um segundo motor de rateio. A nova interface trabalha sobre `DPECostAllocationRepository` e mantém as mesmas regras de cálculo, arredondamento, fingerprint, versionamento e oficialização.

## Seleção de destinos

A configuração de uma despesa não usa mais uma lista visualmente extensa como principal interação.

Para critérios com destinos específicos, a interface disponibiliza uma seleção pesquisável. O usuário pode localizar cursos/ofertas por nome e acompanhar quantos destinos foram selecionados.

Regras principais:

- `DIRECT`: exatamente um destino;
- `MANUAL`: um ou mais destinos, com percentuais/valores reconciliados;
- critérios compartilhados: podem usar todos os cursos elegíveis ou um subconjunto explícito;
- `TEACHER_HOURS`: usa os cursos associados ao professor e não permite política em despesa que não seja folha.

## Prévia obrigatória por despesa

O endpoint existente de simulação continua sendo:

`POST /api/dpe/cost-engine/expenses/{expense_id}/allocation-preview`

A prévia é calculada sem persistir a configuração.

Antes de salvar, a interface mostra:

- despesa e valor;
- critério escolhido;
- destinos envolvidos;
- peso/percentual;
- valor por curso;
- total da despesa;
- total distribuído;
- diferença;
- pendências bloqueantes, quando existirem.

A configuração só é tratada como pronta quando a prévia reconcilia integralmente o valor da despesa.

## Prévia consolidada do mês

Novo endpoint:

`GET /api/dpe/cost-engine/periods/{period_id}/allocation-preview`

A operação simula todas as despesas ativas da competência usando suas configurações atuais, sem criar `Allocation Run`.

Para cada curso/oferta, a resposta contém:

- custo confirmado no Allocation Run oficial atual, quando existir;
- novo custo da prévia;
- variação de custo;
- receita líquida do mês;
- resultado após a nova distribuição;
- margem resultante.

A reconciliação consolidada mostra:

- despesas totais;
- total distribuído;
- diferença;
- quantidade de bloqueios;
- estado reconciliado.

A prévia serve para decisão. O cálculo versionado e a oficialização continuam sendo ações separadas.

## Políticas de distribuição

### Conceito

Uma política é uma regra administrativa reutilizável. Ela não representa um cálculo passado e não substitui o Allocation Run.

Exemplo conceitual:

`Energia → todos os cursos presenciais → quantidade de alunos`

ou:

`Software específico → cursos selecionados → divisão igual`

### Persistência

Novo model:

`DPEAllocationPolicy`

Nova tabela:

`dpe_allocation_policies`

A política armazena:

- diretoria;
- nome;
- critério de distribuição;
- escopo `ALL` ou `SPECIFIC`;
- ofertas acadêmicas estáveis utilizadas como destinos;
- percentuais manuais, quando aplicável;
- descrição utilizada para sugestão automática;
- categoria de origem como contexto;
- observações;
- estado ativo/inativo;
- usuário e datas de criação/alteração.

### Histórico

A política **não referencia diretamente os snapshots mensais como verdade futura**.

Quando é criada, destinos específicos são guardados por `offering_id` estável. Ao ser aplicada em outra competência, esses destinos são resolvidos novamente para os `DPECostPeriodOffering` daquele mês.

Isso garante que:

- a política possa ser reutilizada;
- um curso ausente no novo mês seja detectado;
- snapshots anteriores não sejam alterados;
- uma política não acople competências futuras a IDs históricos de snapshot.

### Manual

Quando uma distribuição manual é salva como política:

- percentuais permanecem percentuais;
- valores manuais são convertidos para percentuais equivalentes da despesa original.

Isso permite aplicar a mesma lógica a uma despesa recorrente cujo valor tenha mudado no mês seguinte.

### Sugestão automática

Quando `auto_suggest` está ativo, a política guarda a descrição da despesa que a originou.

Ao abrir outra despesa com a mesma descrição normalizada, a interface apresenta a política como sugestão. A política **não é aplicada silenciosamente**: o usuário escolhe aplicar, revisa a prévia e somente depois salva a configuração.

O objetivo é reduzir trabalho repetitivo sem retirar o controle administrativo.

### Desativação

Uma política pode ser desativada.

A desativação:

- impede novas sugestões/aplicações;
- mantém o registro no banco;
- não altera despesas já configuradas;
- não altera Allocation Runs;
- não altera competências encerradas.

## Endpoints novos

### Políticas

`GET /api/dpe/cost-engine/allocation-policies`

Lista políticas. Pode receber `period_id` para resolver os destinos no contexto de uma competência e `active_only`.

`POST /api/dpe/cost-engine/expenses/{expense_id}/allocation-policies`

Cria uma política a partir da configuração atual ou de uma configuração em prévia.

`PUT /api/dpe/cost-engine/allocation-policies/{policy_id}`

Atualiza metadados administrativos e permite ativar/desativar a política.

`GET /api/dpe/cost-engine/expenses/{expense_id}/allocation-policies/{policy_id}/resolve`

Resolve uma política para os snapshots da competência da despesa e devolve uma configuração pronta para prévia.

### Prévia consolidada

`GET /api/dpe/cost-engine/periods/{period_id}/allocation-preview`

Simula o mês sem persistir novo Allocation Run.

## Banco e migration

A v0.12.1 possui migration nova e obrigatória para PostgreSQL/Supabase:

`database/041_dpe_allocation_policies_v0121.sql`

- schema anterior: 40;
- schema esperado após a migration: 41;
- mudança aditiva;
- nenhuma tabela financeira histórica é removida ou reescrita;
- RLS é habilitado na nova tabela, mantendo o backend FastAPI como camada operacional responsável pelo acesso.

Em SQLite local, `Base.metadata.create_all()` cria a tabela e o mecanismo local registra o schema esperado 41.

## Estruturas preservadas

Continuam inalterados conceitualmente:

- competências e snapshots;
- despesas oficiais;
- alocação docente;
- critérios matemáticos do Allocation Engine;
- driver values;
- Allocation Runs versionados;
- fingerprints;
- resultados de rateio;
- issues;
- oficialização e supersessão;
- economics por oferta;
- fechamento e reabertura;
- autorização da DPE;
- operação somente com cursos presenciais introduzida na v0.12.0.

## Testes

Adicionado `tests/test_dpe_v0121.py` com regressões para:

- uma despesa dividida igualmente entre vários cursos;
- distribuição proporcional a alunos;
- distribuição manual por percentuais;
- reconciliação integral da despesa;
- política manual reutilizada em outro mês;
- valor manual convertido para percentual reutilizável;
- sugestão automática por descrição recorrente;
- política específica incompatível quando um curso não participa do mês futuro;
- prévia consolidada do mês com receita, resultado e margem;
- desativação lógica da política preservando seu registro.

Na base completa de homologação usada durante o desenvolvimento:

- 53 testes executados;
- 53 aprovados;
- módulos Python modificados passaram em `py_compile`;
- JavaScripts DPE modificados passaram em `node --check`;
- não foram encontrados IDs HTML duplicados em `templates/dpe.html`;
- seed demonstrativo criou 2 políticas reutilizáveis;
- página DPE, foundation, Allocation Central e endpoint de políticas responderam HTTP 200;
- a prévia consolidada via API respondeu HTTP 200;
- no seed demonstrativo, a prévia totalizou R$ 495.180,00 em despesas e R$ 495.180,00 distribuídos, com diferença R$ 0,00 e nenhum bloqueio.

## Escopo não implementado nesta versão

A v0.12.1 não antecipa:

- v0.12.2: analytics histórico, gráficos, comparações de 12 meses e waterfall;
- v0.12.3: importação real de Excel, copiar período, recorrência operacional e ações em massa;
- v0.12.4: evolução do fechamento e governança;
- v0.12.5: homologação visual final, acessibilidade e refinamentos finais.

## Linhagem do pacote

A árvore completa disponível para homologação continua sendo a v0.11.6.5 acrescida das alterações DPE da v0.12.0 e v0.12.1.

O arquivo v0.11.6.7 recebido anteriormente é um patch acadêmico sobre uma árvore completa v0.11.6.6. Para não apagar as correções acadêmicas v0.11.6.6/v0.11.6.7, a entrega desta versão também deve possuir um **patch DPE cumulativo** destinado à árvore completa v0.11.6.7.

Esse patch não substitui `repository.py`, `static/js/app.js`, `static/css/app.css` ou `templates/index.html`, que são os arquivos funcionais alterados pelo patch acadêmico v0.11.6.7.

## Homologação visual

A validação visual automatizada por Chromium local continua indisponível neste ambiente por política administrativa (`ERR_BLOCKED_BY_ADMINISTRATOR`). Foram validados contratos de API, DOM estrutural, sintaxe JS, Python, banco e regressão automatizada. A revisão visual fina no navegador real permanece parte da homologação antes do deploy de produção.
