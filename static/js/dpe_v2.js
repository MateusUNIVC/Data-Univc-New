(function(){
  if (!state.dpeV2) state.dpeV2 = {periodId:null, data:null, loaded:false};

  const PERIOD_LABELS = {DRAFT:'Preparação', REVIEW:'Conferência', CALCULATED:'Calculada', CLOSED:'Fechada'};
  const STEP_LABELS = {DONE:'Concluído', READY:'Pronto', ATTENTION:'Atenção', PENDING:'Pendente'};
  const STEP_CLASS = {DONE:'good', READY:'good', ATTENTION:'attention', PENDING:'info'};

  function payload(){ return state.dpeV2.data || {periods:[],summary:{},workflow:[],issues:[],offerings:[],aggregates:{product:[]}}; }
  function currentPeriodId(){ return state.dpeV2.periodId || payload().selected_period?.id || null; }

  function syncPeriodState(periodId){
    if(!periodId)return;
    if(state.costEngine)state.costEngine.selectedPeriodId=periodId;
    if(state.costExpenses)state.costExpenses.periodId=periodId;
    if(state.costTeaching)state.costTeaching.periodId=periodId;
    if(state.costAllocation)state.costAllocation.periodId=periodId;
    if(state.costRevenues)state.costRevenues.periodId=periodId;
    if(state.costEconomics)state.costEconomics.periodId=periodId;
    if(state.costClosure)state.costClosure.periodId=periodId;
  }
  function money(value, decimals=0){
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    return Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:decimals,maximumFractionDigits:decimals});
  }
  function number(value){
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    return Number(value).toLocaleString('pt-BR',{maximumFractionDigits:0});
  }
  function percent(value){
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    return `${Number(value).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}%`;
  }
  function periodStatusChip(status){
    const classes={DRAFT:'info',REVIEW:'attention',CALCULATED:'good',CLOSED:'good'};
    return `<span class="status-chip ${classes[status]||'info'}">${escapeHtml(PERIOD_LABELS[status]||status||'—')}</span>`;
  }
  function metricCard(label,value,sub,icon,status='info'){
    return `<article class="metric-card dpe-v2-metric dpe-decision-kpi ${status}"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-sub">${escapeHtml(sub)}</span></article>`;
  }

  function updateExcelExport(){
    const link=$('#dpeExportExcel');if(!link)return;
    const pid=currentPeriodId();
    if(pid){link.href=`/api/dpe/excel?period_id=${encodeURIComponent(pid)}&diretoria=DPE`;link.classList.remove('is-disabled');link.removeAttribute('aria-disabled');}
    else{link.href='/api/dpe/excel?diretoria=DPE';link.classList.add('is-disabled');link.setAttribute('aria-disabled','true');}
  }

  function renderPeriodFilter(){
    const select=$('#dpeV2PeriodFilter'); if(!select)return;
    const rows=payload().periods||[];
    select.innerHTML=rows.length?rows.map(row=>option(row.id,`${row.period} · ${PERIOD_LABELS[row.status]||row.status}`,String(row.id)===String(currentPeriodId()))).join(''):'<option value="">Nenhum mês cadastrado</option>';
    if(currentPeriodId()) select.value=String(currentPeriodId());
    const p=payload().selected_period;
    const context=$('#dpeV2PeriodContext');
    if(context) context.innerHTML=p?`${periodStatusChip(p.status)} <span>${escapeHtml(p.period||'')}</span>`:'<span>Cadastre um mês para começar.</span>';
    updateExcelExport();
  }

  function renderProgress(){
    const s=payload().summary||{};
    const progress=Number(s.progress_percent||0);
    const root=$('#dpeV2Progress'); if(!root)return;
    root.innerHTML=`<div class="dpe-v2-progress-copy"><div><span class="eyebrow">Preparação do mês</span><strong>${progress}% concluído</strong></div><span>${s.completed_steps||0}/${s.total_steps||0} etapas concluídas</span></div><div class="dpe-v2-progress-track"><span style="width:${Math.max(0,Math.min(100,progress))}%"></span></div>`;
  }

  function renderCards(){
    const s=payload().summary||{};
    const result=s.monthly_result;
    const margin=s.monthly_margin_percent;
    const resultStatus=result===null||result===undefined?'info':(Number(result)>=0?'good':'critical');
    const marginStatus=margin===null||margin===undefined?'info':(Number(margin)>=0?'good':'critical');
    const expenseSub=(s.pending_distribution_total||0)>0?`${money(s.pending_distribution_total)} ainda aguardam distribuição`:`${s.expense_count||0} despesa(s) registrada(s)`;
    $('#dpeV2ExecutiveCards').innerHTML=[
      metricCard('Receita total',money(s.total_revenue),`Cursos ${money(s.course_revenue)} · Institucional ${money(s.institutional_revenue)}`,'R$','good'),
      metricCard('Despesas do mês',money(s.expense_total),expenseSub,'↓','info'),
      metricCard('Resultado do mês',money(result),'Receita total menos despesas oficiais','Δ',resultStatus),
      metricCard('Margem do mês',percent(margin),'Resultado do mês sobre a receita total','%',marginStatus)
    ].join('');
  }

  function renderWorkflow(){
    const rows=payload().workflow||[];
    const root=$('#dpeV2Workflow'); if(!root)return;
    root.innerHTML=rows.length?rows.map((row,index)=>`<button type="button" class="dpe-v2-step ${row.complete?'is-complete':''}" data-v2-go="${escapeHtml(row.section)}"><span class="dpe-v2-step-index">${String(index+1).padStart(2,'0')}</span><span class="dpe-v2-step-copy"><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.detail)}</small></span><span class="status-chip ${STEP_CLASS[row.status]||'info'}">${escapeHtml(STEP_LABELS[row.status]||row.status)}</span></button>`).join(''):'<div class="cost-engine-empty compact"><strong>Fluxo ainda não iniciado</strong><span>Cadastre um mês para começar.</span></div>';
  }

  function renderNextAction(){
    const action=payload().next_action||{};
    const root=$('#dpeV2NextAction'); if(!root)return;
    const p=payload().selected_period;
    root.innerHTML=`<div><span class="eyebrow">Próximo passo</span><h3>${escapeHtml(action.label||'Começar o mês')}</h3><p>${escapeHtml(action.detail||'')}</p><span class="dpe-next-period">${escapeHtml(p?.period||'')}</span></div><button type="button" class="button primary" data-v2-go="${escapeHtml(action.section||'dashboard')}">Resolver agora</button>`;
  }

  function renderIssues(){
    const rows=payload().issues||[];
    const root=$('#dpeV2Issues'); if(!root)return;
    const blockers=rows.filter(row=>row.status==='BLOCKER').length;
    const warnings=rows.filter(row=>row.status==='WARNING').length;
    $('#dpeV2IssuesContext').textContent=rows.length?`${blockers} prioritária(s) · ${warnings} aviso(s)`:'Tudo em ordem';
    if(!rows.length){root.innerHTML='<div class="dpe-decision-clear"><span>✓</span><div><strong>Nenhuma pendência importante</strong><small>Os dados essenciais deste mês estão em ordem.</small></div></div>';return;}
    root.innerHTML=rows.slice(0,5).map(row=>`<div class="dpe-decision-issue ${row.status==='BLOCKER'?'is-blocker':'is-warning'}"><div class="dpe-decision-issue-copy"><strong>${escapeHtml(row.title||row.label||'Pendência')}</strong><span>${escapeHtml(row.detail||'')}</span></div><button type="button" class="button ghost small" data-v2-go="${escapeHtml(row.section||'fechamento')}">${escapeHtml(row.action_label||'Revisar')}</button></div>`).join('')+(rows.length>5?`<div class="dpe-decision-more">+ ${rows.length-5} item(ns) adicional(is) no fechamento</div>`:'');
  }

  function readiness(row){
    const missing=[];
    if(!row.students_ready)missing.push('alunos');
    if(!row.revenue_ready)missing.push('receita');
    if(!row.cost_available)missing.push('custo');
    if(!missing.length)return '<span class="status-chip good">Completa</span>';
    return `<span class="status-chip attention">Falta ${escapeHtml(missing.join(', '))}</span>`;
  }

  function renderOfferings(){
    const rows=payload().offerings||[];
    $('#dpeV2OfferingContext').textContent=`${rows.length} curso(s)/contexto(s)`;
    $('#dpeV2OfferingTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.label)}</strong><small class="table-subtitle">${escapeHtml([row.modality,row.shift,row.location].filter(v=>v&&v!=='—').join(' · '))}</small></td><td>${number(row.active_students)}</td><td>${money(row.revenue)}</td><td>${money(row.allocated_cost)}</td><td>${money(row.economic_result)}</td><td>${percent(row.margin_percent)}</td><td>${readiness(row)}</td></tr>`).join(''):'<tr><td colspan="7">Nenhum curso/contexto incluído neste mês.</td></tr>';
  }

  function renderProducts(){
    const rows=payload().aggregates?.product||[];
    const root=$('#dpeV2ProductList'); if(!root)return;
    if(!rows.length){root.innerHTML='<div class="cost-engine-empty compact"><strong>Sem consolidação</strong><span>Os cursos aparecerão quando houver cursos/contextos e dados do mês.</span></div>';return;}
    const maxRevenue=Math.max(1,...rows.map(row=>Number(row.revenue||0)));
    root.innerHTML=rows.map(row=>{
      const width=Math.max(3,Math.min(100,(Number(row.revenue||0)/maxRevenue)*100));
      return `<div class="dpe-v2-product-row"><div class="dpe-v2-product-head"><div><strong>${escapeHtml(row.key)}</strong><span>${row.offering_count} curso(s)/contexto(s) · ${number(row.active_students)} aluno(s)</span></div><div><strong>${money(row.economic_result)}</strong><span>${percent(row.margin_percent)} margem</span></div></div><div class="dpe-v2-product-bar"><span style="width:${width}%"></span></div><div class="dpe-v2-product-values"><span>Receita ${money(row.revenue)}</span><span>Custo ${money(row.allocated_cost)}</span></div></div>`;
    }).join('');
  }

  function renderMeta(){
    const s=payload().summary||{};
    const root=$('#dpeV2Meta'); if(!root)return;
    const payrollText=s.payroll_count?`${s.payroll_linked_count||0}/${s.payroll_count}`:'Sem folha';
    const coverage=s.allocation_coverage_percent;
    root.innerHTML=`<div><span>Alunos ativos</span><strong>${number(s.active_students)}</strong></div><div><span>Receita institucional</span><strong>${money(s.institutional_revenue)}</strong></div><div><span>Custos distribuídos</span><strong>${coverage===null||coverage===undefined?'—':percent(coverage)}</strong></div><div><span>Folha conciliada</span><strong>${escapeHtml(payrollText)}</strong></div>`;
  }

  function renderAll(){
    renderPeriodFilter();renderProgress();renderCards();renderWorkflow();renderNextAction();renderIssues();renderOfferings();renderProducts();renderMeta();applyAccess();
  }

  async function refresh({periodId=null}={}){
    const pid=periodId||state.dpeV2.periodId||state.costEngine?.selectedPeriodId||null;
    const data=await api('/api/dpe/cost-engine/v2-overview',{},pid?{period_id:pid}:{});
    state.dpeV2.data=data;state.dpeV2.periodId=data.selected_period?.id||null;if(data.selected_period?.period)state.reference=data.selected_period.period;syncPeriodState(state.dpeV2.periodId);state.dpeV2.loaded=true;renderAll();return data;
  }

  async function openSection(section){
    const pid=currentPeriodId();
    await navigate(section);
    if(!pid)return;
    try{
      if(section==='competencias'&&state.costEngine){state.costEngine.selectedPeriodId=pid;if(typeof window.refreshDPECostEngine==='function')await window.refreshDPECostEngine({preservePeriod:true});}
      if(section==='central-despesas'&&state.costExpenses){state.costExpenses.periodId=pid;if(typeof window.refreshDPECostExpenses==='function')await window.refreshDPECostExpenses({keepPeriod:true});}
      if(section==='docencia'&&state.costTeaching){state.costTeaching.periodId=pid;if(typeof window.refreshDPECostTeaching==='function')await window.refreshDPECostTeaching({keepPeriod:true});}
      if(section==='receita-operacional'&&typeof window.refreshDPECostRevenues==='function')await window.refreshDPECostRevenues({periodId:pid});
      if(section==='economia'&&typeof window.refreshDPECostEconomics==='function')await window.refreshDPECostEconomics({periodId:pid});
      if(section==='rateio'&&typeof window.refreshDPECostAllocation==='function')await window.refreshDPECostAllocation({periodId:pid,runId:null});
      if(section==='fechamento'&&typeof window.refreshDPECostClosure==='function')await window.refreshDPECostClosure({periodId:pid});
    }catch(error){showAlert(error.message,'error',0);}
  }

  function bind(){
    $('#dpeV2PeriodFilter')?.addEventListener('change',async event=>{const periodId=Number(event.target.value)||null;setLoading(true);try{await refresh({periodId});if(typeof window.refreshDPECostAnalytics==='function')await window.refreshDPECostAnalytics({periodId,courseKey:null});const active=document.querySelector('.page-section.active')?.id?.replace('section-','')||'dashboard';if(active==='central-despesas'&&typeof window.refreshDPECostExpenses==='function')await window.refreshDPECostExpenses({keepPeriod:true});if(active==='docencia'&&typeof window.refreshDPECostTeaching==='function')await window.refreshDPECostTeaching({keepPeriod:true});if(active==='receita-operacional'&&typeof window.refreshDPECostRevenues==='function')await window.refreshDPECostRevenues({periodId});if(active==='economia'&&typeof window.refreshDPECostEconomics==='function')await window.refreshDPECostEconomics({periodId});if(active==='rateio'&&typeof window.refreshDPECostAllocation==='function')await window.refreshDPECostAllocation({periodId,runId:null});if(active==='fechamento'&&typeof window.refreshDPECostClosure==='function')await window.refreshDPECostClosure({periodId});if(active==='competencias'&&typeof window.refreshDPECostEngine==='function')await window.refreshDPECostEngine({preservePeriod:true});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
    $('#section-dashboard')?.addEventListener('click',event=>{const target=event.target.closest('[data-v2-go]');if(!target)return;openSection(target.dataset.v2Go);});
    $('#dpeV2Refresh')?.addEventListener('click',async()=>{setLoading(true);try{await refresh({periodId:currentPeriodId()});if(typeof window.refreshDPECostAnalytics==='function')await window.refreshDPECostAnalytics({periodId:currentPeriodId()});showAlert('Painel executivo e análises atualizados.','success',2500);}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
  }

  window.refreshDPEV2=refresh;
  window.initializeDPEV2=async function(){bind();await refresh({periodId:state.costEngine?.selectedPeriodId||null});};
})();
