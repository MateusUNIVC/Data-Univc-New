# DPE Motor de Rateio — v0.9.6.17

## Objetivo

Transformar despesas oficiais de uma competência em custos auditáveis por oferta econômica, preservando a origem do valor, a regra usada, a base matemática e a versão do cálculo.

## Vigência intramês da docência

As atividades docentes passam a aceitar `effective_start_date` e `effective_end_date`. As datas, quando informadas, precisam pertencer à própria competência e a data final não pode anteceder a inicial. Não existe restrição de unicidade por disciplina/turma: dois professores podem atuar na mesma disciplina/turma simultaneamente ou em períodos diferentes do mesmo mês.

Exemplo de substituição:

- Professor A — Anatomia — Turma A — 01/09 a 12/09 — 18h;
- Professor B — Anatomia — Turma A — 15/09 a 30/09 — 42h.

Cada professor continua com seu próprio snapshot mensal, atividade e despesa de folha.

## Drivers implementados

### DIRECT
Exige exatamente uma oferta de destino e direciona 100% da despesa a ela.

### TEACHER_HOURS
Disponível para folha conciliada. O valor é distribuído conforme as horas alocadas nas atividades daquele professor dentro da competência. Horas de outros docentes não entram no denominador.

### OFFERING_HOURS
Rateia pela carga horária total de cada oferta. Na ausência de uma base explícita, a base é derivada da soma das atividades docentes ativas vinculadas à oferta.

### STUDENTS
Rateia pela quantidade mensal de alunos informada para cada oferta elegível. Nesta release a base é explícita e auditável; a integração com o domínio de alunos será feita em etapa posterior.

### REVENUE
Rateia pela receita mensal informada para cada oferta elegível. Nesta release a base é explícita e auditável; a integração com receita/ticket médio será feita na próxima etapa.

### EQUAL
Divide igualmente entre todas as ofertas incluídas ou somente entre um subconjunto configurado para a despesa.

### MANUAL
Permite definir valores exatos ou percentuais por oferta. A soma precisa fechar exatamente o valor da despesa ou 100%.

## Precisão monetária

Rateios proporcionais trabalham em centavos e usam distribuição pelo maior resto. Isso garante que a soma dos destinos seja exatamente igual ao valor original da despesa, sem perda de centavos por arredondamento.

## Versionamento

Cada clique em calcular cria um `DPECostAllocationRun` com número sequencial. O run preserva resultados e pendências; não sobrescreve versões anteriores.

Estados:

- `BLOCKED`: existe despesa não rateada ou pendência bloqueante;
- `CALCULATED`: todos os valores fecharam e a versão pode ser candidata a oficial;
- `OFFICIAL`: versão oficial da competência;
- `SUPERSEDED`: versão oficial anterior substituída por outra, quando aplicável.

## Proteção contra cálculo obsoleto

O run guarda um fingerprint dos insumos: despesas, regras, alvos, bases mensais e atividades/cargas docentes. Se qualquer um desses dados mudar após o cálculo, a versão não pode ser oficializada; uma nova versão deve ser calculada. Além disso, somente o run mais recente pode ser oficializado.

## Rastreabilidade

Cada resultado persiste:

- despesa de origem;
- oferta de destino;
- regra/driver;
- valor alocado;
- numerador e denominador;
- percentual;
- base matemática usada;
- snapshot da despesa;
- snapshot da oferta;
- versão do cálculo.

O princípio é: nenhum custo por oferta deve existir sem uma explicação reproduzível de como foi obtido.

## Fechamento desta etapa

Ao oficializar um cálculo, a competência passa a `CALCULATED`. Reabertura governada e fechamento definitivo continuarão sendo tratados na etapa específica de workflow/auditoria.

## Banco

Aplicar `database/037_dpe_allocation_engine_v09617.sql` sobre o schema 36. O schema esperado passa a ser 37. A migration é aditiva.
