(function(){
  if(!state.costAllocation){state.costAllocation={periodId:null,runId:null,data:null,loaded:false,expenseSearch:'',expenseStatus:'ALL'};}

  const DRIVER_LABELS={
    DIRECT:'100% para um curso',
    TEACHER_HOURS:'Conforme atividades do docente',
    OFFERING_HOURS:'Proporcional à carga horária',
    STUDENTS:'Proporcional ao número de alunos',
    REVENUE:'Proporcional à receita',
    EQUAL:'Dividir igualmente',
    MANUAL:'Definir manualmente'
  };
  const DRIVER_ORDER=['TEACHER_HOURS','OFFERING_HOURS','STUDENTS','REVENUE','EQUAL','MANUAL','DIRECT'];
  const DRIVER_GUIDE={
    DIRECT:{short:'O valor inteiro pertence a um único curso/contexto.',detail:'A despesa já foi classificada como Direta. Nesta etapa você apenas confere qual curso/contexto recebe 100% do valor.',basis:'Um único curso/contexto de destino.',example:'Ex.: material específico de Odontologia → 100% para Odontologia.'},
    TEACHER_HOURS:{short:'O custo acompanha as atividades registradas do docente.',detail:'Indicado para custos docentes conciliados. O sistema usa as atividades do docente no mês e distribui o valor conforme as horas atribuídas a cada curso.',basis:'Carga horária mensal do docente por curso/contexto.',example:'Ex.: 60h em Administração e 40h em Contábeis → 60% / 40%.'},
    OFFERING_HOURS:{short:'O custo acompanha a carga horária dos cursos.',detail:'Indicado para gastos compartilhados relacionados ao volume de atividade acadêmica.',basis:'Carga horária total de cada curso/contexto no mês.',example:'Ex.: 2.000h contra 1.000h → 66,7% / 33,3%.'},
    STUDENTS:{short:'O custo acompanha a quantidade de alunos ativos.',detail:'Indicado quando o gasto cresce principalmente conforme o número de estudantes atendidos.',basis:'Alunos ativos informados para cada curso/contexto.',example:'Ex.: 300 alunos contra 100 → 75% / 25%.'},
    REVENUE:{short:'O custo acompanha a participação de cada curso na receita.',detail:'Use quando fizer sentido distribuir um gasto conforme a participação econômica dos cursos no mês.',basis:'Receita atribuída a cada curso/contexto.',example:'Ex.: R$ 300 mil contra R$ 100 mil → 75% / 25%.'},
    EQUAL:{short:'Todos os cursos participantes recebem a mesma parcela.',detail:'Útil quando o gasto beneficia os cursos de forma equivalente e não existe uma base proporcional melhor.',basis:'Quantidade de cursos/contextos participantes.',example:'Ex.: R$ 12 mil para 3 cursos → R$ 4 mil para cada.'},
    MANUAL:{short:'Você define exatamente quanto cada curso recebe.',detail:'Use em exceções quando a divisão já foi definida administrativamente ou não pode ser representada por outro critério.',basis:'Valores ou percentuais informados manualmente.',example:'Ex.: 50% Direito, 30% Administração e 20% Contábeis.'}
  };
  const EXPENSE_SCOPE_LABELS={DIRECT:'Direta',SHARED:'Compartilhada',INSTITUTIONAL:'Institucional'};
  const RUN_LABELS={BLOCKED:'Com pendências',CALCULATED:'Pronto para confirmar',OFFICIAL:'Confirmado',SUPERSEDED:'Substituído'};
  const PERIOD_LABELS={DRAFT:'Preparação',REVIEW:'Conferência',CALCULATED:'Calculada',CLOSED:'Fechada'};
  const ISSUE_TITLES={
    RULE_MISSING:'Escolha como distribuir',
    TEACHER_NOT_CONFIRMED:'Concilie o professor',
    TEACHER_DRIVER_NON_PAYROLL:'Critério incompatível',
    DIRECT_TARGET_REQUIRED:'Escolha um curso',
    MANUAL_TARGETS_REQUIRED:'Escolha os cursos',
    MANUAL_MODE_INVALID:'Complete a divisão manual',
    MANUAL_AMOUNT_MISMATCH:'Os valores não fecham',
    MANUAL_PERCENTAGE_MISMATCH:'Os percentuais não fecham',
    STUDENTS_MISSING:'Complete os alunos dos cursos',
    REVENUE_MISSING:'Complete as receitas dos cursos',
    ZERO_DENOMINATOR:'A base do cálculo está vazia',
    NO_OFFERINGS:'Nenhum curso disponível'
  };

  let modalContext=null;
  let previewTimer=null;
  let previewSequence=0;

  function money(value){return Number(value||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:2,maximumFractionDigits:2});}
  function number(value,digits=2){return Number(value||0).toLocaleString('pt-BR',{minimumFractionDigits:0,maximumFractionDigits:digits});}
  function data(){return state.costAllocation.data||{periods:[],expenses:[],driver_values:[],runs:[],summary:{}};}
  function selectedPeriod(){return data().selected_period||null;}
  function selectedRun(){return data().selected_run||null;}
  function currentPeriodId(){return state.costAllocation.periodId||selectedPeriod()?.id||null;}
  function editable(){return Boolean(data().editable&&state.access?.canEdit);}
  function modalOpen(title,subtitle,body,eyebrow='DPE · DISTRIBUIÇÃO DE CUSTOS'){$('#costEngineModalEyebrow').textContent=eyebrow;$('#costEngineModalTitle').textContent=title;$('#costEngineModalSubtitle').textContent=subtitle||'';$('#costEngineModalBody').innerHTML=body;openDPEModal('costEngineModal');}
  function modalClose(){closeDPEModal('costEngineModal');modalContext=null;if(previewTimer)clearTimeout(previewTimer);}
  function formError(error){const detail=error?.payload?.detail;const fields=detail?.campos||{};return [error.message,...Object.entries(fields).map(([key,value])=>`${key}: ${value}`)].filter(Boolean).join('\n');}
  function showFormError(error){const box=$('#allocationFormErrors');if(box){focusInlineError(box,formError(error));}else showAlert(error.message,'error',0);}
  function guide(driver){return DRIVER_GUIDE[driver]||{short:'Defina como o valor deve chegar aos cursos.',detail:'Escolha o critério que melhor representa a relação entre a despesa e os cursos.',basis:'Base definida pelo critério.',example:''};}
  function chip(status){const css=status==='READY'||status==='OFFICIAL'||status==='CALCULATED'?'good':status==='CONFIG'?'info':'attention';const label={READY:'Pronto',CONFIG:'Revisar',BLOCKED:'Revisar',OFFICIAL:'Confirmado',CALCULATED:'Calculado',SUPERSEDED:'Substituído'}[status]||RUN_LABELS[status]||status;return `<span class="status-chip ${css}">${escapeHtml(label||'—')}</span>`;}
  function card(label,value,sub,icon,tone='info'){return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-sub">${escapeHtml(sub)}</span><span class="status-chip ${tone}">Distribuição</span></article>`;}

  function renderPeriodFilter(){
    const el=$('#allocationPeriodFilter'); if(!el)return;
    const rows=data().periods||[];
    el.innerHTML=rows.length?rows.map(row=>option(row.id,`${row.period} · ${PERIOD_LABELS[row.status]||row.status}`,String(row.id)===String(currentPeriodId()))).join(''):'<option value="">Abra um mês primeiro</option>';
    if(currentPeriodId())el.value=String(currentPeriodId());
  }
  function renderRunFilter(){
    const el=$('#allocationRunFilter'); if(!el)return;
    const rows=data().runs||[]; const current=selectedRun()?.id||state.costAllocation.runId||'';
    el.innerHTML='<option value="">Nenhum cálculo</option>'+rows.map(row=>option(row.id,`Cálculo ${row.run_number} · ${RUN_LABELS[row.status]||row.status}`,String(row.id)===String(current))).join('');
    if(current)el.value=String(current);
  }
  function renderCards(){
    const s=data().summary||{},run=selectedRun(),period=selectedPeriod();
    const pending=Number(s.pending_expense_count||0);
    $('#allocationCards').innerHTML=[
      card('Custos a distribuir',money(s.expense_total||0),`${s.expense_count||0} despesa(s) direta(s) ou compartilhada(s)`,'R$'),
      card('Precisam configurar',String(pending),pending?'revise antes de atualizar os custos':'todas as despesas prontas','!',pending?'attention':'good'),
      card('Distribuído no cálculo',money(run?.allocated_total||0),run?`cálculo ${run.run_number}`:'ainda não calculado','↗'),
      card('Ainda não distribuído',money(run?.unallocated_total??s.expense_total??0),run?(Number(run?.unallocated_total||0)>0?'revise as pendências':'valor totalmente distribuído'):'aguardando atualização','•',Number(run?.unallocated_total??s.expense_total??0)>0?'attention':'good')
    ].join('');
    $('#allocationContext').textContent=period?`${period.period} · ${PERIOD_LABELS[period.status]||period.status} · ${editable()?'edição liberada':'histórico protegido'}`:'Selecione um mês para começar';
    const calc=$('#calculateAllocationRun'),drivers=$('#editAllocationDrivers'); if(calc)calc.disabled=!editable(); if(drivers)drivers.disabled=!editable();
  }
  function readinessText(row){
    if(row.readiness==='READY')return 'Pronto para o próximo cálculo.';
    const detail=String(row.readiness_detail||'Revise a configuração antes de calcular.');
    return detail.replace(/rateio/gi,'distribuição').replace(/direcionador/gi,'critério');
  }
  function renderExpenses(){
    const search=String(state.costAllocation.expenseSearch||'').trim().toLocaleLowerCase('pt-BR');
    const status=state.costAllocation.expenseStatus||'ALL';
    const all=[...(data().expenses||[])].sort((a,b)=>{const rank={BLOCKED:0,CONFIG:1,READY:2};return (rank[a.readiness]??3)-(rank[b.readiness]??3)||String(a.description).localeCompare(String(b.description),'pt-BR');});
    const rows=all.filter(row=>{
      if(status==='PENDING'&&row.readiness==='READY')return false;
      if(status==='READY'&&row.readiness!=='READY')return false;
      if(search&&!`${row.description||''} ${row.counterparty_name||''} ${row.destination_summary||''} ${row.rule_name||''}`.toLocaleLowerCase('pt-BR').includes(search))return false;
      return true;
    });
    const pending=all.filter(row=>row.readiness!=='READY').length;
    $('#allocationExpenseContext').textContent=pending?`${pending} para configurar · ${all.length} distribuíveis`:`${all.length} despesas distribuíveis · tudo pronto`;
    $('#allocationExpensesTable').innerHTML=rows.length?rows.map(row=>{
      const g=guide(row.driver_type);
      const treatment=EXPENSE_SCOPE_LABELS[row.expense_scope]||row.expense_scope||'Compartilhada';
      const source=row.driver_type?(row.uses_suggested_rule?'<span class="allocation-rule-origin suggested">Sugestão aplicada</span>':'<span class="allocation-rule-origin adjusted">Definição atual</span>'):'<span class="allocation-rule-origin missing">Ainda não definida</span>';
      const policy=row.suggested_policy_name?`<span class="allocation-policy-hint">Configuração reutilizável disponível: ${escapeHtml(row.suggested_policy_name)}</span>`:'';
      const method=row.expense_scope==='DIRECT'
        ? `<strong>100% para um curso</strong><span class="allocation-effect-text">${escapeHtml(row.destination_summary||'Escolha o curso de destino')}</span>`
        : row.driver_type?`<strong>${escapeHtml(DRIVER_LABELS[row.driver_type]||row.rule_name||row.driver_type)}</strong><span class="allocation-effect-text">${escapeHtml(g.short)}</span>${source}`:'<span class="status-chip attention">Escolha como distribuir</span>';
      return `<tr class="${row.readiness==='READY'?'':'allocation-row-needs-review'}"><td><strong>${escapeHtml(row.description)}</strong><span class="cost-cell-sub">${escapeHtml(row.expense_kind==='PAYROLL'?(row.counterparty_name||'Custo docente'):'Despesa geral')}</span>${policy}</td><td><strong>${money(row.amount)}</strong><span class="cost-cell-sub">${escapeHtml(treatment)}</span></td><td><strong>${escapeHtml(row.destination_summary||'Ainda não definido')}</strong><span class="cost-cell-sub">${row.target_count?`${row.target_count} destino(s)`:row.driver_type?'escopo calculado automaticamente':'aguardando definição'}</span></td><td>${method}</td><td>${chip(row.readiness)}<span class="cost-cell-sub">${escapeHtml(readinessText(row))}</span></td><td>${editable()?`<button class="table-action" data-allocation-config="${row.id}">${row.readiness==='READY'?'Conferir':'Configurar'}</button>`:'—'}</td></tr>`;
    }).join(''):dpeEmptyRow(6,all.length?'Nenhuma despesa corresponde aos filtros':'Nenhuma despesa precisa ser distribuída neste mês',all.length?'Altere a busca ou os filtros para ver outras despesas.':'Despesas institucionais ficam no resultado geral e não aparecem nesta etapa.');
  }

  function renderMonthPreview(){
    const preview=data().month_preview,table=$('#allocationMonthPreviewTable'),context=$('#allocationMonthPreviewContext'),recon=$('#allocationMonthReconciliation');
    if(!table||!context||!recon)return;
    if(!preview){table.innerHTML=dpeEmptyRow(7,'Selecione um mês','A prévia consolidada aparecerá quando houver um período selecionado.');context.textContent='';recon.innerHTML='';return;}
    const rows=preview.rows||[],summary=preview.summary||{};
    context.textContent=preview.current_run?`Comparando com cálculo confirmado ${preview.current_run.run_number}`:'Ainda sem cálculo confirmado';
    table.innerHTML=rows.length?rows.map(row=>{
      const change=Number(row.cost_change||0);const changeLabel=`${change>0?'+':''}${money(change)}`;
      return `<tr><td><strong>${escapeHtml(row.label)}</strong></td><td>${money(row.current_cost)}</td><td><strong>${money(row.preview_cost)}</strong></td><td><span class="allocation-delta ${change>0?'up':change<0?'down':'neutral'}">${escapeHtml(changeLabel)}</span></td><td>${money(row.revenue)}</td><td><strong>${money(row.result)}</strong></td><td>${row.margin===null||row.margin===undefined?'—':`${number(row.margin,2)}%`}</td></tr>`;
    }).join(''):dpeEmptyRow(7,'Nenhum curso incluído','Revise os cursos/contextos do período antes de distribuir custos.');
    const ok=Boolean(summary.reconciled);
    recon.innerHTML=`<div><span>Despesas totais</span><strong>${money(summary.expense_total||0)}</strong></div><div><span>Total distribuído na prévia</span><strong>${money(summary.allocated_total||0)}</strong></div><div><span>Diferença</span><strong>${money(summary.difference||0)}</strong></div><div class="allocation-reconcile-state ${ok?'ready':'pending'}"><strong>${ok?'✓ Distribuição reconciliada':'⚠ Prévia ainda não reconciliada'}</strong><span>${ok?'Todos os valores fecharam.':`${summary.blocker_count||0} pendência(s) bloqueante(s).`}</span></div>`;
  }

  function renderPolicies(){
    const rows=data().policies||[],table=$('#allocationPoliciesTable'),context=$('#allocationPolicyContext');if(!table||!context)return;
    context.textContent=rows.length?`${rows.filter(row=>row.active).length} ativa(s) · ${rows.length} cadastrada(s)`:'Nenhuma política cadastrada';
    table.innerHTML=rows.length?rows.map(row=>{
      const labels=(row.targets||[]).map(item=>item.label);const missing=(row.missing_targets||[]).length;
      const scope=row.scope_type==='ALL'?'Todos os cursos/contextos do mês':labels.length?`${labels.slice(0,2).join(', ')}${labels.length>2?` +${labels.length-2}`:''}`:'Cursos específicos';
      const auto=row.auto_suggest&&row.match_description?`Mesma descrição: “${row.match_description}”`:'Não';
      return `<tr><td><strong>${escapeHtml(row.name)}</strong>${row.notes?`<span class="cost-cell-sub">${escapeHtml(row.notes)}</span>`:''}</td><td><strong>${escapeHtml(DRIVER_LABELS[row.rule?.driver_type]||row.rule?.name||'—')}</strong></td><td>${escapeHtml(scope)}${missing?`<span class="allocation-policy-warning">${missing} curso(s) fora do mês atual</span>`:''}</td><td>${escapeHtml(auto)}</td><td>${row.active?'<span class="status-chip good">Ativa</span>':'<span class="status-chip info">Inativa</span>'}</td><td>${state.access?.canEdit?`<button class="table-action" data-policy-toggle="${row.id}" data-policy-active="${row.active?'1':'0'}">${row.active?'Desativar':'Ativar'}</button>`:'—'}</td></tr>`;
    }).join(''):dpeEmptyRow(6,'Nenhuma política cadastrada','Configure uma despesa e use “Salvar como política” para reaproveitar a regra nos próximos meses.');
  }

  function metricText(metric,type){
    if(!metric||metric.effective_value===null||metric.effective_value===undefined)return '<span class="status-chip attention">Não informado</span>';
    const suffix=type==='OFFERING_HOURS'?' h':type==='REVENUE'?'':'';
    const value=type==='REVENUE'?money(metric.effective_value):`${number(metric.effective_value,2)}${suffix}`;
    const source=metric.source_type==='DERIVED'?'derivado das aulas':metric.source_type==='ECONOMIC'?'dados oficiais do curso':metric.source_type?metric.source_type.toLowerCase():'sem fonte';
    return `<strong>${escapeHtml(value)}</strong><span class="cost-cell-sub">${escapeHtml(source)}</span>`;
  }
  function renderDrivers(){
    const rows=data().driver_values||[];
    $('#allocationDriversTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.label)}</strong></td><td>${metricText(row.metrics?.OFFERING_HOURS,'OFFERING_HOURS')}</td><td>${metricText(row.metrics?.STUDENTS,'STUDENTS')}</td><td>${metricText(row.metrics?.REVENUE,'REVENUE')}</td></tr>`).join(''):dpeEmptyRow(4,'Nenhum curso incluído neste mês','Revise o período e os cursos/contextos antes de atualizar a distribuição.');
  }
  function renderRuns(){
    const rows=data().runs||[]; $('#allocationRunContext').textContent=rows.length?`${rows.length} atualização(ões) registrada(s)`:'Nenhuma atualização realizada';
    $('#allocationRunsTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>Cálculo ${row.run_number}</strong><span class="cost-cell-sub">${row.created_at?new Date(row.created_at).toLocaleString('pt-BR'):'—'}</span></td><td>${chip(row.status)}</td><td>${money(row.expense_total)}</td><td>${money(row.allocated_total)}</td><td>${money(row.unallocated_total)}</td><td><button class="table-action" data-allocation-run="${row.id}">Exibir</button></td></tr>`).join(''):dpeEmptyRow(6,'Nenhuma distribuição calculada','Revise os critérios e clique em “Atualizar distribuição”.');
  }
  function issueTitle(issue){return ISSUE_TITLES[issue?.code]||'Precisa de atenção';}
  function renderResult(){
    const run=selectedRun();
    $('#allocationResultContext').textContent=run?`Cálculo ${run.run_number} · ${RUN_LABELS[run.status]||run.status}`:'Ainda não calculado';
    const rows=run?.by_offering||[];
    $('#allocationByOfferingTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.label)}</strong></td><td><strong>${money(row.allocated_amount)}</strong></td><td>${row.expense_count}</td><td><button class="table-action" data-allocation-offering-detail="${row.period_offering_id}">Ver composição</button></td></tr>`).join(''):dpeEmptyRow(4,'Custos por curso ainda indisponíveis','Atualize a distribuição para calcular quanto cada curso absorve.');
    const issues=run?.issues||[],box=$('#allocationIssuesList'),official=$('#makeAllocationOfficial');
    if(!run){box.innerHTML='<div class="cost-engine-empty"><strong>Nenhum cálculo ainda</strong><span>Depois de revisar os critérios, clique em “Atualizar distribuição”.</span></div>';official?.classList.add('hidden');return;}
    box.innerHTML=issues.length?issues.map(issue=>`<div class="allocation-issue ${issue.severity==='BLOCKER'?'is-blocker':'is-warning'}"><strong>${escapeHtml(issueTitle(issue))}</strong><span>${escapeHtml(String(issue.message||'').replace(/rateio/gi,'distribuição').replace(/direcionador/gi,'critério'))}</span></div>`).join(''):'<div class="allocation-ok"><strong>Distribuição completa</strong><span>Todas as despesas deste cálculo foram atribuídas aos cursos e o total fecha com as despesas do mês.</span></div>';
    if(official){official.classList.toggle('hidden',!(editable()&&run.status==='CALCULATED'&&Number(run.unallocated_total||0)===0));official.dataset.runId=run.id;}
  }
  function renderAll(){renderPeriodFilter();renderRunFilter();renderCards();renderExpenses();renderMonthPreview();renderPolicies();renderDrivers();renderRuns();renderResult();}

  async function refresh({periodId=null,runId=null}={}){
    const pid=periodId||state.costAllocation.periodId||state.costEngine?.selectedPeriodId||null;
    const rid=runId||state.costAllocation.runId||null;
    const params={}; if(pid)params.period_id=pid;if(rid)params.run_id=rid;
    const payload=await api('/api/dpe/cost-engine/allocation-central',{},params);
    state.costAllocation.data=payload; state.costAllocation.periodId=payload.selected_period?.id||null; state.costAllocation.runId=payload.selected_run?.id||null; state.costAllocation.loaded=true; renderAll(); return payload;
  }

  function ruleForId(config,id){return (config.rules||[]).find(item=>String(item.id)===String(id))||null;}
  function availableRules(config){
    const scope=String(config.expense_scope||'SHARED').toUpperCase();
    return (config.rules||[]).filter(rule=>{
      if(scope==='DIRECT')return rule.driver_type==='DIRECT';
      if(rule.driver_type==='DIRECT')return false;
      if(rule.driver_type==='TEACHER_HOURS'&&config.expense_kind!=='PAYROLL')return false;
      return true;
    });
  }
  function selectedRule(){if(!modalContext)return null;return ruleForId(modalContext.config,modalContext.ruleId);}
  function sortedRules(config){return [...availableRules(config)].sort((a,b)=>DRIVER_ORDER.indexOf(a.driver_type)-DRIVER_ORDER.indexOf(b.driver_type)||String(a.name).localeCompare(String(b.name),'pt-BR'));}
  function initialRuleId(config){
    const allowed=availableRules(config);const ids=new Set(allowed.map(rule=>String(rule.id)));
    if(config.rule?.id&&ids.has(String(config.rule.id)))return Number(config.rule.id);
    if(config.suggested_rule?.id&&ids.has(String(config.suggested_rule.id)))return Number(config.suggested_rule.id);
    if(config.expense_kind==='PAYROLL'){
      const teacher=allowed.find(rule=>rule.driver_type==='TEACHER_HOURS');if(teacher)return Number(teacher.id);
    }
    if(String(config.expense_scope||'').toUpperCase()==='DIRECT'){
      const direct=allowed.find(rule=>rule.driver_type==='DIRECT');if(direct)return Number(direct.id);
    }
    return null;
  }
  function initializeModalContext(config){
    const targets=new Map((config.targets||[]).map(row=>[String(row.period_offering_id),{selected:true,manual_amount:row.manual_amount,manual_percentage:row.manual_percentage}]));
    const manualAmount=(config.targets||[]).some(row=>row.manual_amount!==null&&row.manual_amount!==undefined);
    modalContext={config,ruleId:initialRuleId(config),targets,restrict:(config.targets||[]).length>0,manualMode:manualAmount?'amount':'percentage'};
  }
  function syncModalDraft(){
    if(!modalContext)return;
    $$('[data-allocation-target-input]','#allocationConfigForm').forEach(input=>{
      const id=String(input.dataset.allocationTargetInput);const current=modalContext.targets.get(id)||{};
      current.selected=Boolean(input.checked);modalContext.targets.set(id,current);
    });
    $$('[data-allocation-manual-value]','#allocationConfigForm').forEach(input=>{
      const id=String(input.dataset.allocationManualValue);const current=modalContext.targets.get(id)||{};
      if(modalContext.manualMode==='amount')current.manual_amount=input.value===''?null:Number(input.value);else current.manual_percentage=input.value===''?null:Number(input.value);modalContext.targets.set(id,current);
    });
    const restrict=$('#allocationRestrictScope');if(restrict)modalContext.restrict=restrict.checked;
    const manualMode=$('[name="allocationManualMode"]:checked','#allocationConfigForm');if(manualMode)modalContext.manualMode=manualMode.value;
  }
  function ruleCards(config){
    const suggestedId=config.suggested_rule?.id;
    return sortedRules(config).map(rule=>{
      const g=guide(rule.driver_type);const selected=String(rule.id)===String(modalContext.ruleId);
      const recommendation=String(rule.id)===String(suggestedId)||(!config.rule&&config.expense_kind==='PAYROLL'&&rule.driver_type==='TEACHER_HOURS');
      return `<label class="allocation-rule-card ${selected?'selected':''}"><input type="radio" name="allocationRuleChoice" value="${rule.id}" ${selected?'checked':''}><span class="allocation-rule-card-main"><strong>${escapeHtml(DRIVER_LABELS[rule.driver_type]||rule.name)}</strong><small>${escapeHtml(g.short)}</small></span><span class="allocation-rule-card-meta">${recommendation?'<span class="status-chip good">Recomendado</span>':''}</span></label>`;
    }).join('');
  }
  function guidePanel(rule){
    if(!rule)return '<div class="allocation-guide-empty">Escolha um critério para ver como ele funciona.</div>';
    const g=guide(rule.driver_type);
    return `<div class="allocation-guide-content"><div><span>O que significa</span><strong>${escapeHtml(g.detail)}</strong></div><div><span>Base utilizada</span><strong>${escapeHtml(g.basis)}</strong></div><div><span>Exemplo</span><strong>${escapeHtml(g.example)}</strong></div></div>`;
  }
  function targetInput(row,driver){
    const current=modalContext.targets.get(String(row.period_offering_id))||{};const selected=Boolean(current.selected);
    if(driver==='DIRECT')return `<label class="allocation-simple-target ${selected?'selected':''}"><input type="radio" name="allocationDirectTarget" data-allocation-target-input="${row.period_offering_id}" ${selected?'checked':''}><span>${escapeHtml(row.label)}</span></label>`;
    const manual=driver==='MANUAL';const value=modalContext.manualMode==='amount'?(current.manual_amount??''):(current.manual_percentage??'');const suffix=modalContext.manualMode==='amount'?'R$':'%';
    return `<div class="allocation-simple-target ${selected?'selected':''}"><label><input type="checkbox" data-allocation-target-input="${row.period_offering_id}" ${selected?'checked':''}><span>${escapeHtml(row.label)}</span></label>${manual?`<div class="allocation-manual-input"><span>${suffix}</span><input type="number" min="0" ${modalContext.manualMode==='percentage'?'max="100"':''} step="${modalContext.manualMode==='amount'?'0.01':'0.0001'}" data-allocation-manual-value="${row.period_offering_id}" value="${value}" ${selected?'':'disabled'}></div>`:''}</div>`;
  }
  function searchableTargetList(driver,{hidden=false,id=''}={}){
    const rows=modalContext.config.offerings||[];const selected=[...modalContext.targets.values()].filter(value=>value.selected).length;
    return `<details ${id?`id="${id}"`:''} class="allocation-target-combobox ${hidden?'hidden':''}" open><summary><span>Selecionar cursos</span><strong data-allocation-target-count>${selected} selecionado(s)</strong></summary><div class="allocation-target-combobox-body"><label class="allocation-target-search"><span>Buscar curso</span><input type="search" data-allocation-target-search placeholder="Digite o nome do curso, turno ou campus"></label><div class="allocation-target-simple-list">${rows.map(row=>targetInput(row,driver)).join('')}</div></div></details>`;
  }
  function updateTargetCounts(){
    $$('.allocation-target-combobox','#allocationConfigForm').forEach(box=>{const count=$$('[data-allocation-target-input]:checked',box).length;const label=$('[data-allocation-target-count]',box);if(label)label.textContent=`${count} selecionado(s)`;});
  }
  function renderTargetEditor(){
    const box=$('#allocationTargetArea');if(!box||!modalContext)return;const rule=selectedRule();if(!rule){box.innerHTML='';return;}const driver=rule.driver_type;
    if(driver==='TEACHER_HOURS'){
      box.innerHTML='<div class="allocation-auto-note"><strong>Nenhum curso precisa ser escolhido.</strong><span>O sistema usa automaticamente as aulas do professor conciliado nesta despesa de folha.</span></div>';return;
    }
    if(driver==='DIRECT'){
      box.innerHTML=`<div class="allocation-step-heading"><span>1</span><div><strong>Confirme o curso de destino</strong><small>Como esta despesa é Direta, 100% do valor irá para um único curso/contexto.</small></div></div>${searchableTargetList(driver)}`;bindTargetEvents();return;
    }
    if(driver==='MANUAL'){
      box.innerHTML=`<div class="allocation-step-heading"><span>2</span><div><strong>Defina a divisão manual</strong><small>Escolha uma única forma de preenchimento para todos os cursos.</small></div></div><div class="allocation-manual-mode"><label><input type="radio" name="allocationManualMode" value="percentage" ${modalContext.manualMode==='percentage'?'checked':''}> Percentual (%)</label><label><input type="radio" name="allocationManualMode" value="amount" ${modalContext.manualMode==='amount'?'checked':''}> Valor (R$)</label></div>${searchableTargetList(driver)}`;bindTargetEvents();return;
    }
    box.innerHTML=`<div class="allocation-step-heading"><span>2</span><div><strong>Quais cursos entram nesta divisão?</strong><small>Normalmente todos os cursos/contextos do mês participam. Restrinja somente quando o gasto não beneficiar todos.</small></div></div><label class="allocation-restrict-toggle"><input id="allocationRestrictScope" type="checkbox" ${modalContext.restrict?'checked':''}><span>Distribuir somente entre cursos específicos</span></label>${searchableTargetList(driver,{hidden:!modalContext.restrict,id:'allocationRestrictedTargets'})}`;bindTargetEvents();
  }
  function bindTargetEvents(){
    $('#allocationRestrictScope')?.addEventListener('change',event=>{modalContext.restrict=event.target.checked;$('#allocationRestrictedTargets')?.classList.toggle('hidden',!event.target.checked);schedulePreview();});
    $$('[name="allocationManualMode"]','#allocationConfigForm').forEach(input=>input.addEventListener('change',event=>{syncModalDraft();modalContext.manualMode=event.target.value;renderTargetEditor();schedulePreview();}));
    $$('[data-allocation-target-input]','#allocationConfigForm').forEach(input=>input.addEventListener('change',event=>{
      const id=String(event.target.dataset.allocationTargetInput);if(event.target.type==='radio')modalContext.targets.forEach(value=>value.selected=false);const current=modalContext.targets.get(id)||{};current.selected=event.target.checked;modalContext.targets.set(id,current);
      const row=event.target.closest('.allocation-simple-target');if(row)row.classList.toggle('selected',event.target.checked);const manual=row?.querySelector('[data-allocation-manual-value]');if(manual)manual.disabled=!event.target.checked;updateTargetCounts();schedulePreview();
    }));
    $$('[data-allocation-manual-value]','#allocationConfigForm').forEach(input=>input.addEventListener('input',()=>{syncModalDraft();schedulePreview();}));
    $$('[data-allocation-target-search]','#allocationConfigForm').forEach(input=>input.addEventListener('input',event=>{
      const term=event.target.value.trim().toLocaleLowerCase('pt-BR');const box=event.target.closest('.allocation-target-combobox');
      $$('.allocation-simple-target',box).forEach(row=>row.classList.toggle('hidden',Boolean(term)&&!row.textContent.toLocaleLowerCase('pt-BR').includes(term)));
    }));
  }
  function updateRuleUI(){
    if(!modalContext)return;syncModalDraft();const checked=$('[name="allocationRuleChoice"]:checked','#allocationConfigForm');modalContext.ruleId=checked?Number(checked.value):null;
    $$('.allocation-rule-card','#allocationConfigForm').forEach(card=>card.classList.toggle('selected',Boolean(card.querySelector('input:checked'))));
    $('#allocationGuide').innerHTML=guidePanel(selectedRule());renderTargetEditor();schedulePreview();
  }
  function collectPayload(){
    if(!modalContext||!modalContext.ruleId)return {allocation_rule_id:null,targets:[],client_error:'Escolha como distribuir esta despesa.'};syncModalDraft();const rule=selectedRule(),driver=rule?.driver_type;let targets=[];
    if(driver==='TEACHER_HOURS')return {allocation_rule_id:Number(modalContext.ruleId),targets:[]};
    if(['OFFERING_HOURS','STUDENTS','REVENUE','EQUAL'].includes(driver)&&!modalContext.restrict)return {allocation_rule_id:Number(modalContext.ruleId),targets:[]};
    modalContext.targets.forEach((value,id)=>{if(!value.selected)return;targets.push({period_offering_id:Number(id),manual_amount:driver==='MANUAL'&&modalContext.manualMode==='amount'?(value.manual_amount??null):null,manual_percentage:driver==='MANUAL'&&modalContext.manualMode==='percentage'?(value.manual_percentage??null):null});});
    if(driver==='DIRECT'&&targets.length!==1)return {allocation_rule_id:Number(modalContext.ruleId),targets,client_error:'Escolha exatamente um curso para receber esta despesa.'};
    if(['OFFERING_HOURS','STUDENTS','REVENUE','EQUAL'].includes(driver)&&modalContext.restrict&&targets.length===0)return {allocation_rule_id:Number(modalContext.ruleId),targets,client_error:'Selecione pelo menos um curso ou desative a restrição.'};
    if(driver==='MANUAL'){
      if(!targets.length)return {allocation_rule_id:Number(modalContext.ruleId),targets,client_error:'Selecione pelo menos um curso para a divisão manual.'};
      const values=targets.map(row=>modalContext.manualMode==='amount'?row.manual_amount:row.manual_percentage);
      if(values.some(value=>value===null||value===undefined||Number.isNaN(Number(value))))return {allocation_rule_id:Number(modalContext.ruleId),targets,client_error:'Preencha a divisão de todos os cursos selecionados.'};
      const total=values.reduce((sum,value)=>sum+Number(value||0),0);
      if(modalContext.manualMode==='percentage'&&Math.abs(total-100)>0.0001)return {allocation_rule_id:Number(modalContext.ruleId),targets,client_error:`Os percentuais precisam somar 100%. Total atual: ${number(total,2)}%.`};
      if(modalContext.manualMode==='amount'&&Math.abs(total-Number(modalContext.config.amount||0))>0.005)return {allocation_rule_id:Number(modalContext.ruleId),targets,client_error:`Os valores precisam somar ${money(modalContext.config.amount)}. Total atual: ${money(total)}.`};
    }
    return {allocation_rule_id:Number(modalContext.ruleId),targets};
  }
  function basisText(row,driver){
    const n=row.numerator,d=row.denominator;
    if(driver==='OFFERING_HOURS'||driver==='TEACHER_HOURS')return n!==null&&d!==null?`${number(n,2)}h de ${number(d,2)}h`:'Carga horária';
    if(driver==='STUDENTS')return n!==null&&d!==null?`${number(n,0)} de ${number(d,0)} alunos`:'Alunos ativos';
    if(driver==='REVENUE')return n!==null&&d!==null?`${money(n)} de ${money(d)}`:'Receita';
    if(driver==='EQUAL')return 'Parcela igual';
    if(driver==='DIRECT')return 'Destino direto';
    if(driver==='MANUAL')return 'Definido manualmente';
    return '—';
  }
  function renderPreview(payload){
    const box=$('#allocationPreview');if(!box)return;const rule=payload?.rule,rows=payload?.results||[],issues=payload?.issues||[];
    if(!rule){box.innerHTML='<div class="allocation-preview-empty"><strong>Escolha um critério</strong><span>A prévia aparecerá aqui antes de você salvar.</span></div>';return;}
    if(modalContext)modalContext.lastPreview=payload;
    const issueHtml=issues.length?`<div class="allocation-preview-issues">${issues.map(issue=>`<div><strong>${escapeHtml(issueTitle(issue))}</strong><span>${escapeHtml(String(issue.message||'').replace(/rateio/gi,'distribuição').replace(/direcionador/gi,'critério'))}</span></div>`).join('')}</div>`:'';
    const table=rows.length?`<div class="allocation-preview-table"><div class="allocation-preview-head"><span>Curso</span><span>Base</span><span>%</span><span>Valor</span></div>${rows.map(row=>`<div class="allocation-preview-row"><strong>${escapeHtml(row.label)}</strong><span>${escapeHtml(basisText(row,rule.driver_type))}</span><span>${number(row.percentage,2)}%</span><strong>${money(row.allocated_amount)}</strong></div>`).join('')}</div>`:'<div class="allocation-preview-empty compact"><span>Ainda não é possível calcular a divisão com esta configuração.</span></div>';
    const status=payload.ready?`<div class="allocation-preview-status ready"><strong>Prévia fechando em ${money(payload.allocated_total)}</strong><span>O valor total da despesa foi distribuído sem diferença.</span></div>`:`<div class="allocation-preview-status pending"><strong>${money(payload.unallocated_total)} ainda sem destino</strong><span>Revise as informações destacadas antes de atualizar os custos do mês.</span></div>`;
    box.innerHTML=`${status}${issueHtml}${table}`;
  }
  async function requestPreview(){
    if(!modalContext)return;const box=$('#allocationPreview');const payload=collectPayload();if(!payload.allocation_rule_id){renderPreview(null);return;}if(payload.client_error){if(box)box.innerHTML=`<div class="allocation-preview-status pending"><strong>Complete a configuração</strong><span>${escapeHtml(payload.client_error)}</span></div>`;return;}const sequence=++previewSequence;if(box)box.innerHTML='<div class="allocation-preview-loading">Calculando prévia…</div>';
    try{const preview=await api(`/api/dpe/cost-engine/expenses/${modalContext.config.expense_id}/allocation-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(sequence===previewSequence)renderPreview(preview);}catch(error){if(sequence!==previewSequence)return;if(box)box.innerHTML=`<div class="allocation-preview-status pending"><strong>Não foi possível montar a prévia</strong><span>${escapeHtml(formError(error))}</span></div>`;}
  }
  function schedulePreview(){if(previewTimer)clearTimeout(previewTimer);previewTimer=setTimeout(requestPreview,180);}

  function policyOptions(config){
    const suggested=config.suggested_policy?.id;
    return `<option value="">Escolha uma política cadastrada</option>`+(config.policies||[]).map(row=>`<option value="${row.id}" ${String(row.id)===String(suggested)?'selected':''} ${row.applicable?'':'disabled'}>${escapeHtml(row.name)} · ${escapeHtml(DRIVER_LABELS[row.rule?.driver_type]||row.rule?.name||'critério')} ${row.applicable?'':'· indisponível neste mês'}</option>`).join('');
  }
  async function applyPolicyToDraft(policyId){
    if(!modalContext||!policyId)return;setLoading(true);
    try{
      const resolved=await api(`/api/dpe/cost-engine/expenses/${modalContext.config.expense_id}/allocation-policies/${policyId}/resolve`);const cfg=resolved.config||{};
      modalContext.ruleId=Number(cfg.allocation_rule_id)||null;modalContext.targets=new Map((cfg.targets||[]).map(row=>[String(row.period_offering_id),{selected:true,manual_amount:row.manual_amount,manual_percentage:row.manual_percentage}]));
      modalContext.restrict=(cfg.targets||[]).length>0;modalContext.manualMode='percentage';
      $$('[name="allocationRuleChoice"]','#allocationConfigForm').forEach(input=>{input.checked=String(input.value)===String(modalContext.ruleId);});
      $$('.allocation-rule-card','#allocationConfigForm').forEach(card=>card.classList.toggle('selected',Boolean(card.querySelector('input:checked'))));
      $('#allocationGuide').innerHTML=guidePanel(selectedRule());renderTargetEditor();schedulePreview();
      const status=$('#allocationPolicyApplied');if(status){status.textContent=`Política “${resolved.policy.name}” aplicada à prévia. Revise os valores antes de salvar.`;status.classList.remove('hidden');}
    }catch(error){showFormError(error);}finally{setLoading(false);}
  }
  async function savePolicyFromDraft(){
    if(!modalContext)return;const name=$('#allocationPolicyName')?.value?.trim()||'';const auto=Boolean($('#allocationPolicyAuto')?.checked);const payload=collectPayload();
    if(!name){showFormError({message:'Informe um nome para a política.'});return;}
    if(!payload.allocation_rule_id||payload.client_error){showFormError({message:payload.client_error||'Complete a distribuição antes de salvar a política.'});return;}
    if(!modalContext.lastPreview?.ready){showFormError({message:'A prévia precisa estar reconciliada antes de virar uma política reutilizável.'});return;}
    setLoading(true);
    try{
      const policy=await api(`/api/dpe/cost-engine/expenses/${modalContext.config.expense_id}/allocation-policies`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,auto_suggest:auto,config:payload})});
      modalContext.config.policies=[...(modalContext.config.policies||[]),policy];const select=$('#allocationPolicySelect');if(select){select.innerHTML=policyOptions(modalContext.config);select.value=String(policy.id);}
      const msg=$('#allocationPolicySaveStatus');if(msg){msg.textContent='✓ Política salva. Ela ficará disponível nos próximos meses.';msg.classList.remove('hidden');}
      await refresh({periodId:currentPeriodId(),runId:state.costAllocation.runId});
    }catch(error){showFormError(error);}finally{setLoading(false);}
  }

  async function openExpenseConfig(expenseId){
    if(!editable())return; setLoading(true);
    try{
      const config=await api(`/api/dpe/cost-engine/expenses/${expenseId}/allocation-config`);initializeModalContext(config);
      if(!config.allocatable){showAlert('Esta despesa é Institucional e permanece somente no resultado geral. Altere o tratamento na área Despesas se quiser distribuí-la aos cursos.','info',6500);return;}
      const direct=String(config.expense_scope||'SHARED').toUpperCase()==='DIRECT';
      const category=config.classification?.category?.name||'';
      const suggestion=config.suggested_rule?`Sugestão${category?` para ${category}`:''}: ${DRIVER_LABELS[config.suggested_rule.driver_type]||config.suggested_rule.name}.`:'Escolha a forma que melhor representa este gasto.';
      const treatment=EXPENSE_SCOPE_LABELS[config.expense_scope]||config.expense_scope||'Compartilhada';
      const policySuggestion=config.suggested_policy?`Configuração encontrada: “${config.suggested_policy.name}”.`:'Você pode reaproveitar esta configuração nos próximos meses.';
      const heading=direct?'Conferir destino da despesa direta':'Como deseja distribuir esta despesa?';
      const intro=direct
        ? 'O tratamento já foi definido como Direta na área Despesas. Aqui você apenas confirma o curso/contexto que recebe 100% do valor.'
        : `${suggestion} A prévia mostra os valores por curso antes de salvar.`;
      const ruleBlock=direct
        ? `<div class="allocation-fixed-method"><span>Forma de distribuição</span><strong>100% para um curso/contexto</strong><small>Para transformar esta despesa em Compartilhada ou Institucional, altere o tratamento na área Despesas.</small></div>`
        : `<div class="allocation-step-heading"><span>1</span><div><strong>Escolha como dividir</strong><small>Selecione a lógica administrativa que melhor representa este gasto.</small></div></div><div class="allocation-rule-grid">${ruleCards(config)}</div><div id="allocationGuide" class="allocation-guide">${guidePanel(selectedRule())}</div>`;
      const previewStep=direct?'2':'3';
      const policyTools=direct?'':`<details class="allocation-policy-tools"><summary><div><span>Configurações reutilizáveis</span><strong>${escapeHtml(policySuggestion)}</strong></div><span>›</span></summary><div class="allocation-policy-tools-body"><div class="allocation-policy-picker-row"><select id="allocationPolicySelect">${policyOptions(config)}</select><button type="button" class="button secondary compact" id="applyAllocationPolicy">Aplicar</button></div><span id="allocationPolicyApplied" class="allocation-policy-applied hidden"></span><div class="allocation-policy-create"><label><span>Salvar a configuração atual como</span><input id="allocationPolicyName" maxlength="180" placeholder="Ex.: Energia proporcional aos alunos"></label><label class="allocation-policy-auto"><input id="allocationPolicyAuto" type="checkbox" checked><span>Sugerir quando aparecer despesa com a mesma descrição</span></label><button type="button" class="button secondary compact" id="saveAllocationPolicy">Salvar configuração</button><span id="allocationPolicySaveStatus" class="allocation-policy-save-status hidden"></span></div></div></details>`;
      modalOpen(heading,`${config.description} · ${money(config.amount)}`,`<form id="allocationConfigForm" class="allocation-config-form"><div class="allocation-treatment-summary"><div><span>Tratamento da despesa</span><strong>${escapeHtml(treatment)}</strong></div><p>${escapeHtml(intro)}</p>${direct?'':'<small>Se este gasto não deve chegar aos cursos, altere seu tratamento para Institucional na área Despesas.</small>'}</div>${ruleBlock}<div id="allocationTargetArea"></div><div class="allocation-step-heading preview-heading"><span>${previewStep}</span><div><strong>Confira a prévia em reais</strong><small>O valor total precisa fechar antes de você salvar.</small></div></div><div id="allocationPreview" class="allocation-preview"></div>${policyTools}<div id="allocationFormErrors" class="form-errors hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">${direct?'Salvar destino':'Salvar distribuição'}</button></div></form>`);
      $$('[name="allocationRuleChoice"]','#allocationConfigForm').forEach(input=>input.addEventListener('change',updateRuleUI));renderTargetEditor();schedulePreview();
      $('#applyAllocationPolicy')?.addEventListener('click',()=>{const id=Number($('#allocationPolicySelect')?.value||0);if(!id){showFormError({message:'Escolha uma configuração para aplicar.'});return;}applyPolicyToDraft(id);});
      $('#saveAllocationPolicy')?.addEventListener('click',savePolicyFromDraft);
      $('#allocationConfigForm').addEventListener('submit',async event=>{event.preventDefault();const payload=collectPayload();if(!payload.allocation_rule_id||payload.client_error){showFormError({message:payload.client_error||'Escolha como distribuir esta despesa.'});return;}if(!modalContext.lastPreview?.ready){showFormError({message:'Confira a prévia e resolva a diferença antes de salvar.'});return;}setLoading(true);try{await api(`/api/dpe/cost-engine/expenses/${expenseId}/allocation-config`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert(direct?'Destino da despesa direta salvo.':'Distribuição da despesa salva e reconciliada.','success');await refresh({periodId:currentPeriodId(),runId:null});}catch(error){showFormError(error);}finally{setLoading(false);}});
    }catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  function openDriverValues(){
    if(!editable())return; const rows=data().driver_values||[]; if(!rows.length){showAlert('O mês não possui cursos incluídos.','error');return;}
    modalOpen('Carga horária dos cursos/contextos','Normalmente o sistema deriva estas horas das aulas registradas. Ajuste somente quando a base acadêmica do mês exigir uma correção.',`<form id="allocationDriversForm" class="dpe-measurement-form"><div class="table-wrap allocation-driver-editor"><table class="data-table"><thead><tr><th>Curso / contexto</th><th>Carga informada</th><th>Alunos</th><th>Receita</th></tr></thead><tbody>${rows.map(row=>`<tr data-driver-row="${row.period_offering_id}"><td><strong>${escapeHtml(row.label)}</strong><span class="cost-cell-sub">Derivada das aulas: ${number(row.metrics?.OFFERING_HOURS?.derived_value||0,2)} h</span></td><td><input type="number" min="0" step="0.01" data-driver-hours value="${row.metrics?.OFFERING_HOURS?.explicit_value??''}" placeholder="Usar aulas"></td><td>${metricText(row.metrics?.STUDENTS,'STUDENTS')}</td><td>${metricText(row.metrics?.REVENUE,'REVENUE')}</td></tr>`).join('')}</tbody></table></div><div class="indicator-definition"><strong>Onde alterar cada dado?</strong><span>Alunos são informados nos dados econômicos do curso; a receita vem do novo módulo Receitas. Aqui você só precisa ajustar a carga horária quando o valor derivado das aulas não representar corretamente o curso/contexto no mês.</span></div><div id="allocationFormErrors" class="form-errors hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar carga</button></div></form>`,'DPE · DADOS UTILIZADOS');
    $('#allocationDriversForm').addEventListener('submit',async event=>{event.preventDefault();const values=[];$$('[data-driver-row]','#allocationDriversForm').forEach(row=>{const id=Number(row.dataset.driverRow),h=$('[data-driver-hours]',row).value;values.push({period_offering_id:id,metric_type:'OFFERING_HOURS',value:h===''?null:Number(h),source_type:'MANUAL'});});setLoading(true);try{await api(`/api/dpe/cost-engine/periods/${currentPeriodId()}/driver-values`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({values})});modalClose();showAlert('Carga horária dos cursos/contextos atualizada.','success');await refresh({periodId:currentPeriodId(),runId:null});}catch(error){showFormError(error);}finally{setLoading(false);}});
  }

  function openOfferingComposition(offeringId){
    const run=selectedRun();if(!run)return;const rows=(run.results||[]).filter(row=>String(row.period_offering_id)===String(offeringId));if(!rows.length)return;const label=rows[0].offering_label;
    modalOpen('Composição do custo',label,`<div class="allocation-composition-summary"><strong>${money(rows.reduce((sum,row)=>sum+Number(row.allocated_amount||0),0))}</strong><span>${rows.length} despesa(s) formam este valor no cálculo ${run.run_number}.</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Despesa</th><th>Critério</th><th>Base usada</th><th>%</th><th>Valor</th></tr></thead><tbody>${rows.map(row=>`<tr><td><strong>${escapeHtml(row.expense_description)}</strong></td><td>${escapeHtml(DRIVER_LABELS[row.driver_type]||row.driver_type)}</td><td>${escapeHtml(basisText(row,row.driver_type))}</td><td>${number(row.percentage,2)}%</td><td><strong>${money(row.allocated_amount)}</strong></td></tr>`).join('')}</tbody></table></div><div class="form-actions"><button type="button" class="button primary" data-close-modal="costEngineModal">Fechar</button></div>`,'DPE · DETALHES DO CUSTO');
  }

  async function calculate(){
    if(!editable()||!currentPeriodId())return; setLoading(true);
    try{const run=await api('/api/dpe/cost-engine/allocation-runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({period_id:Number(currentPeriodId())})});state.costAllocation.runId=run.id;showAlert(run.status==='BLOCKED'?`Distribuição atualizada, mas ainda existem ${run.summary?.blocker_count||0} pendência(s) para revisar.`:`Distribuição atualizada com sucesso. Todos os valores fecharam com as despesas do mês.`,run.status==='BLOCKED'?'warning':'success',run.status==='BLOCKED'?0:4500);await refresh({periodId:currentPeriodId(),runId:run.id});}
    catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }
  async function makeOfficial(){
    const run=selectedRun(); if(!run||run.status!=='CALCULATED'||!editable())return;
    const confirmed=await requestDPEConfirmation({title:'Confirmar distribuição do mês?',message:`O cálculo ${run.run_number} passará a ser o cálculo oficial. Depois disso, os dados ficarão protegidos até uma reabertura auditada.`,confirmLabel:'Confirmar distribuição',tone:'warning'});if(!confirmed)return;
    setLoading(true);try{await api(`/api/dpe/cost-engine/allocation-runs/${run.id}/official`,{method:'POST'});showAlert('Distribuição confirmada para o mês.','success');await refresh({periodId:currentPeriodId(),runId:run.id});if(typeof window.refreshDPECostEngine==='function')await window.refreshDPECostEngine({keepPeriod:true});if(typeof window.refreshDPECostExpenses==='function')await window.refreshDPECostExpenses({keepPeriod:true});if(typeof window.refreshDPECostTeaching==='function')await window.refreshDPECostTeaching({keepPeriod:true});}
    catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  function bind(){
    $('#allocationPeriodFilter')?.addEventListener('change',async event=>{state.costAllocation.periodId=Number(event.target.value)||null;state.costAllocation.runId=null;setLoading(true);try{await refresh({periodId:state.costAllocation.periodId,runId:null});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
    $('#allocationRunFilter')?.addEventListener('change',async event=>{state.costAllocation.runId=Number(event.target.value)||null;setLoading(true);try{await refresh({periodId:currentPeriodId(),runId:state.costAllocation.runId});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
    $('#allocationExpenseSearch')?.addEventListener('input',event=>{state.costAllocation.expenseSearch=event.target.value;renderExpenses();});
    $('#allocationExpenseStatusFilter')?.addEventListener('change',event=>{state.costAllocation.expenseStatus=event.target.value||'ALL';renderExpenses();});
    $('#calculateAllocationRun')?.addEventListener('click',calculate); $('#editAllocationDrivers')?.addEventListener('click',openDriverValues); $('#makeAllocationOfficial')?.addEventListener('click',makeOfficial);
    document.addEventListener('click',event=>{
      const config=event.target.closest('[data-allocation-config]');if(config){openExpenseConfig(config.dataset.allocationConfig);return;}
      const policyToggle=event.target.closest('[data-policy-toggle]');if(policyToggle){const id=Number(policyToggle.dataset.policyToggle),active=policyToggle.dataset.policyActive==='1';setLoading(true);api(`/api/dpe/cost-engine/allocation-policies/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({active:!active,period_id:currentPeriodId()})}).then(()=>{showAlert(active?'Política desativada. O histórico foi preservado.':'Política ativada.','success');return refresh({periodId:currentPeriodId(),runId:state.costAllocation.runId});}).catch(error=>showAlert(error.message,'error',0)).finally(()=>setLoading(false));return;}
      const run=event.target.closest('[data-allocation-run]');if(run){state.costAllocation.runId=Number(run.dataset.allocationRun);setLoading(true);refresh({periodId:currentPeriodId(),runId:state.costAllocation.runId}).catch(error=>showAlert(error.message,'error',0)).finally(()=>setLoading(false));return;}
      const offering=event.target.closest('[data-allocation-offering-detail]');if(offering){openOfferingComposition(offering.dataset.allocationOfferingDetail);return;}
    });
  }
  async function initialize(){bind();try{await refresh();}catch(error){showAlert(`Distribuição de custos: ${error.message}`,'error',0);}}
  window.initializeDPECostAllocation=initialize; window.refreshDPECostAllocation=refresh;
})();
