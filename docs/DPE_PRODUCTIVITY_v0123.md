# DPE Productivity — v0.12.3

## Objetivo

A v0.12.3 reduz retrabalho no ciclo mensal da DPE sem criar uma segunda fonte financeira. As ferramentas de produtividade atuam sobre as mesmas competências, despesas, economics, atividades docentes e políticas de distribuição já usadas pelo Cost Engine.

O princípio desta versão é simples: **reaproveitar com prévia, validar antes de gravar e nunca criar duplicidade silenciosa**.

## Escopo entregue

### Importação real de Excel para despesas

A área **Despesas → Importações** agora disponibiliza um modelo XLSX e executa um fluxo real:

1. upload do arquivo;
2. leitura das linhas;
3. normalização dos cabeçalhos;
4. validação de categoria, setor, data e valor;
5. detecção de duplicatas;
6. staging das linhas;
7. prévia completa;
8. confirmação atômica;
9. criação das despesas oficiais somente após a confirmação.

O botão **Importar Excel** não registra apenas metadados. O arquivo é efetivamente lido e, após a conferência, pode alimentar o ledger oficial.

#### Colunas do modelo

Obrigatórias:

- `Descricao`;
- `Valor`;
- `Categoria`.

Opcionais:

- `Data`;
- `Setor`;
- `Tipo`;
- `Fornecedor/beneficiario`;
- `Documento`;
- `Referencia`;
- `Chave externa`;
- `Observacoes`.

Fórmulas nas células de entrada não são aceitas como valor financeiro. O arquivo deve conter valores materializados.

### Preview e validação

A prévia mostra cada linha como `VALID` ou `ERROR` e apresenta:

- descrição;
- valor;
- categoria reconhecida;
- setor reconhecido;
- erros de validação/duplicidade;
- totais válidos;
- total monetário válido.

Se existir qualquer linha bloqueante, o lote inteiro não pode ser confirmado. A v0.12.3 não ignora silenciosamente linhas inválidas.

### Proteção contra duplicatas

A importação verifica:

- `external_key` já utilizado no ledger;
- repetição da mesma chave dentro do arquivo;
- assinatura equivalente de descrição + valor + data + documento no mês;
- repetição dessa assinatura dentro do próprio arquivo.

A checagem é repetida no momento da confirmação para reduzir o risco de uma duplicidade criada entre a prévia e o commit.

## Copiar mês anterior

A nova área **Cadastros e regras → Produtividade** permite usar uma competência anterior como ponto de partida.

Antes da cópia, o sistema apresenta uma prévia informando:

- ofertas em comum entre origem e destino;
- receitas copiáveis;
- atividades docentes copiáveis;
- atividades bloqueadas por ausência da oferta correspondente.

A identidade entre meses é resolvida pela **oferta acadêmica estável**, não pelo ID do snapshot mensal.

### Receitas e alunos

Podem ser copiados:

- alunos ativos;
- alunos pagantes;
- receita bruta;
- bolsas/descontos;
- outras deduções;
- receita líquida;
- tipo de receita.

Os registros copiados recebem indicação de origem `SYSTEM` e referência ao mês de origem. Por padrão, registros já preenchidos no destino não são substituídos. A interface oferece uma opção explícita de sobrescrita.

### Quadro docente

Atividades docentes podem ser copiadas mantendo:

- professor;
- disciplina;
- turma;
- carga total;
- referência da carga;
- distribuição de horas entre cursos.

A distribuição é remapeada para os snapshots da nova competência pelas ofertas estáveis.

A chave `COPY-{origem}-{atividade}-{destino}` torna a operação idempotente: repetir a mesma ação não cria uma segunda cópia da mesma atividade.

## Políticas de distribuição em massa

As políticas da v0.12.1 continuam globais e reutilizáveis; não são duplicadas a cada competência.

A v0.12.3 adiciona:

1. **prévia em massa** das sugestões aplicáveis ao mês;
2. contagem de despesas prontas, bloqueadas e sem política;
3. aplicação em massa somente quando não existem políticas bloqueadas.

A prévia usa o mesmo motor de distribuição individual. Portanto, uma política só é considerada pronta quando consegue gerar uma distribuição válida para os dados atuais da competência.

## Despesas recorrentes

A migration 042 cria o cadastro `dpe_recurring_expense_templates`.

Cada modelo pode armazenar:

- nome;
- descrição da despesa;
- valor padrão;
- tipo da despesa;
- fornecedor/beneficiário;
- categoria;
- setor de origem;
- política de distribuição;
- dia do mês;
- observações;
- status ativo/inativo.

Ao gerar o mês, a despesa recebe uma chave externa estável:

`RECUR-{template_id}-{competencia}`

Isso garante que o mesmo modelo não crie duas despesas para a mesma competência.

Quando há uma política vinculada e ela pode ser resolvida no mês, a configuração de distribuição é aplicada à despesa criada. Se a política não puder ser resolvida, a despesa permanece registrada para revisão; o histórico não é descartado.

## Edição em massa de despesas

A tabela de lançamentos agora possui seleção múltipla e ação **Classificar selecionadas**.

A ação permite alterar em lote:

- categoria;
- setor/centro de custo.

A troca de categoria também atualiza a sugestão de regra padrão associada à categoria, sem executar um novo Allocation Run automaticamente.

## Receitas em massa

A grade de Receitas criada na v0.12.0 já utiliza gravação atômica de múltiplas linhas. A v0.12.3 preserva esse fluxo como a ferramenta oficial de edição em massa de receitas, evitando a criação de um segundo editor paralelo.

## API

### Excel

- `GET /api/dpe/cost-engine/expense-import-template.xlsx`
- `POST /api/dpe/cost-engine/periods/{period_id}/expense-imports/excel/preview`
- `POST /api/dpe/cost-engine/expense-imports/{batch_id}/commit`

### Edição em massa

- `PUT /api/dpe/cost-engine/periods/{period_id}/expenses/bulk-classify`

### Produtividade

- `GET /api/dpe/cost-engine/productivity-central`
- `GET /api/dpe/cost-engine/periods/{period_id}/copy-preview`
- `POST /api/dpe/cost-engine/periods/{period_id}/copy-previous`

### Recorrência

- `GET /api/dpe/cost-engine/recurring-expenses`
- `POST /api/dpe/cost-engine/recurring-expenses`
- `PUT /api/dpe/cost-engine/recurring-expenses/{template_id}`
- `POST /api/dpe/cost-engine/periods/{period_id}/recurring-expenses/generate`

### Políticas em massa

- `POST /api/dpe/cost-engine/periods/{period_id}/allocation-policies/bulk-preview`
- `POST /api/dpe/cost-engine/periods/{period_id}/allocation-policies/bulk-apply`

## Banco e migration

A v0.12.3 adiciona:

`database/042_dpe_productivity_v0123.sql`

O schema esperado passa de **41 para 42**.

A migration é aditiva e cria somente `dpe_recurring_expense_templates`, seus índices e RLS correspondente. As estruturas históricas de competências, despesas, economics, docência, rateio e fechamento não são substituídas.

Em PostgreSQL/Supabase, executar a migration 042 antes de subir o código v0.12.3. Ambientes ainda anteriores à v0.12.1 também precisam ter aplicado a migration 041.

## Arquivos principais

Backend:

- `dpe_cost_excel.py`;
- `dpe_cost_productivity.py`;
- `dpe_cost_expenses.py`;
- `dpe_cost_allocation.py`;
- `dpe_router.py`;
- `models.py`.

Frontend:

- `templates/dpe.html`;
- `static/js/dpe_cost_expenses.js`;
- `static/js/dpe_cost_productivity.js`;
- `static/js/dpe.js`;
- `static/css/dpe.css`.

Banco:

- `database/042_dpe_productivity_v0123.sql`.

## Testes

A suíte acumulada da base de homologação possui **68 testes aprovados**.

A cobertura específica da v0.12.3 inclui:

- preview de Excel sem alterar o ledger;
- commit real após preview válido;
- duplicata impedindo commit;
- classificação em massa;
- geração recorrente idempotente;
- cópia de receita entre snapshots diferentes da mesma oferta;
- cópia do quadro docente com remapeamento de ofertas;
- aplicação em massa de políticas sugeridas.

Também foram validados:

- `py_compile` dos módulos Python;
- `node --check` dos JavaScripts DPE;
- ausência de IDs HTML duplicados;
- seed DPE;
- endpoints da produtividade em modo local autorizado;
- XLSX real em fluxo `preview READY → commit`;
- geração recorrente repetida sem duplicação;
- cópia real de 19 economics e 39 atividades docentes no cenário demonstrativo.

## Fora do escopo

A v0.12.3 não implementa a expansão de governança da v0.12.4. Em especial, não redesenha nesta fase:

- checklist final de fechamento;
- trilha de anomalias de fechamento;
- auditoria ampliada de operações em massa;
- novas regras de reabertura.

Esses itens permanecem para a v0.12.4 conforme a estratégia progressiva do DPE.
