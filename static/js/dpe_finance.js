(function(){
  const CATEGORY_LABELS={PERSONNEL:'Pessoal',OPERATIONAL:'Operacional',ADMINISTRATIVE:'Administrativa',FINANCIAL:'Financeira',OTHER:'Outras'};
  const KIND_LABELS={PAYROLL:'Folha',GENERAL:'Despesa geral'};
  const GROUP_LABELS={FACULTY:'Docente',ADMINISTRATIVE:'Administrativa',OTHER:'Outra'};
  const NATURE_LABELS={SALARY:'Salários',CHARGES:'Encargos',PROVISIONS:'Provisões',OTHER:'Outros'};

  function money(value, compact=false){
    if(value===null||value===undefined||!Number.isFinite(Number(value)))return '—';
    return Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL',...(compact?{notation:'compact',maximumFractionDigits:1}:{minimumFractionDigits:2,maximumFractionDigits:2})});
  }
  function pct(value){return value===null||value===undefined||!Number.isFinite(Number(value))?'—':`${Number(value).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}%`}
  function ratio(value){return value===null||value===undefined||!Number.isFinite(Number(value))?'—':`${Number(value).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}x`}
  function actualCourses(){return (state.courseCatalog||[]).filter(row=>row.id!==null&&row.id!==undefined&&row.id!=='')}
  function courseOptions(selected=''){return `<option value="">Selecione um curso</option>`+actualCourses().map(row=>option(row.id,`${row.name} · ${row.directorate_code}`,String(row.id)===String(selected))).join('')}
  function monthOptions(periods,selected=''){return periods.length?periods.map(p=>option(p,p,p===selected)).join(''):option('','Sem dados')}
  function currentPeriod(){return state.reference||state.finance.dashboard?.reference||''}
  function marginTarget(){
    const configured=selectedMetric('DPE-01','net_margin_pct')?.target?.target ?? metricOf('DPE-01','net_margin_pct')?.target ?? 15;
    return Number.isFinite(Number(configured))?Number(configured):15;
  }
  function statusForMargin(value){if(value===null||value===undefined)return 'info';const target=marginTarget();return Number(value)>=target?'good':Number(value)>=0?'attention':'critical'}
  function statusForCoverage(value){if(value===null||value===undefined)return 'info';return Number(value)>=1.11?'good':Number(value)>=1.05?'attention':'critical'}
  function statusForPayroll(value){if(value===null||value===undefined)return 'info';return Number(value)<=55?'good':Number(value)<=58?'attention':'critical'}
  function hasCourseRevenue(row){return Boolean(row?.has_revenue_data ?? (row?.revenue!==null&&row?.revenue!==undefined))}
  function hasCourseCost(row){return Boolean(row?.has_cost_data ?? ((row?.reported_total_cost!==null&&row?.reported_total_cost!==undefined)||row?.has_allocated_cost))}
  function isCourseComplete(row){return hasCourseRevenue(row)&&hasCourseCost(row)}
  function courseResult(row){if(row?.result_amount!==null&&row?.result_amount!==undefined)return Number(row.result_amount);return isCourseComplete(row)?Number(row.revenue||0)-Number(row.effective_cost||0):null}
  function courseExpenseRatio(row){if(row?.expense_to_revenue_pct!==null&&row?.expense_to_revenue_pct!==undefined)return Number(row.expense_to_revenue_pct);return isCourseComplete(row)&&Number(row.revenue)?Number(row.effective_cost||0)/Number(row.revenue)*100:null}
  function courseDataStatus(row){return row?.data_status||(isCourseComplete(row)?'Apuração completa':hasCourseRevenue(row)?'Aguardando custo/despesa':hasCourseCost(row)?'Aguardando receita':'Sem apuração')}
  function costSource(row){return row?.cost_source||(row?.reported_total_cost!==null&&row?.reported_total_cost!==undefined?'Apuração gerencial':row?.has_allocated_cost?'Despesas rateadas':'Pendente')}
  function statusForExpenseRatio(value){if(value===null||value===undefined)return 'info';const target=Math.max(0,100-marginTarget());return Number(value)<=target?'good':Number(value)<=100?'attention':'critical'}
  function statusForResult(value){if(value===null||value===undefined)return 'info';return Number(value)>=0?'good':'critical'}
  function statusForCourseData(row){return isCourseComplete(row)?'good':hasCourseRevenue(row)||hasCourseCost(row)?'attention':'info'}

  async function refreshFinance({preserveReference=false}={}){
    const requested=preserveReference?state.reference:'';
    const windowValue=state.window==='all'?120:Number(state.window||12);
    let dashboard=await api('/api/dpe/finance/dashboard',{}, {referencia:requested,janela:windowValue});
    if(!preserveReference&&dashboard.reference)state.reference=dashboard.reference;
    if(preserveReference&&state.reference&&dashboard.reference!==state.reference&&(dashboard.periods||[]).includes(state.reference)){
      dashboard=await api('/api/dpe/finance/dashboard',{}, {referencia:state.reference,janela:windowValue});
    }
    state.finance.dashboard=dashboard;
    const period=dashboard.reference||state.reference||'';
    if(period)state.reference=period;
    const [revenues,courseRevenues,expenses,courseCosts]=await Promise.all([
      api('/api/dpe/finance/revenues'),
      api('/api/dpe/finance/course-revenues',{}, {periodo:period}),
      api('/api/dpe/finance/expenses',{}, {periodo:period}),
      api('/api/dpe/finance/course-costs',{}, {periodo:period}),
    ]);
    state.finance.revenues=revenues.items||[];
    state.finance.courseRevenues=courseRevenues.items||[];
    state.finance.expenses=expenses.items||[];
    state.finance.courseCosts=courseCosts.items||[];
    populateFinanceFilters();
    renderFinanceAll();
  }

  function populateFinanceFilters(){
    const financePeriods=state.finance.dashboard?.periods||[];
    state.periods=[...new Set([...(state.periods||[]),...financePeriods])].sort();
    const opts=monthOptions(financePeriods,state.reference);
    ['#financeRevenuePeriod','#financeExpensePeriod','#financeCoursePeriod'].forEach(selector=>{
      const el=$(selector);if(el){el.innerHTML=opts;el.value=state.reference||''}
    });
    const ref=$('#dashboardReference');
    if(ref){ref.innerHTML=monthOptions(state.periods,state.reference);ref.value=state.reference||''}
    const comp=$('#dashboardComparison');
    if(comp){
      const comparisonValues=[...new Set([state.comparison,...state.periods].filter(Boolean))];
      comp.innerHTML=option('','Sem comparação',!state.comparison)+comparisonValues.map(value=>option(value,value,value===state.comparison)).join('');
      comp.value=state.comparison||'';
    }
    ['DPE-01','DPE-02','DPE-03'].forEach(code=>{
      const indicatorRef=$(`[data-reference="${code}"]`);
      if(indicatorRef){indicatorRef.innerHTML=monthOptions(state.periods,state.reference);indicatorRef.value=state.reference||''}
      const indicatorComp=$(`[data-comparison="${code}"]`);
      if(indicatorComp){
        const vals=[...new Set([state.comparison,...state.periods].filter(Boolean))];
        indicatorComp.innerHTML=option('','Sem comparação',!state.comparison)+vals.map(value=>option(value,value,value===state.comparison)).join('');
        indicatorComp.value=state.comparison||'';
      }
    });
    const courseSelect=$('#financeCourseFilter');
    if(courseSelect){
      const old=courseSelect.value;
      courseSelect.innerHTML='<option value="">Todos os cursos</option>'+actualCourses().map(row=>option(row.id,`${row.name} · ${row.directorate_code}`,String(row.id)===String(old))).join('');
      if(old)courseSelect.value=old;
    }
  }

  function renderFinanceAll(){
    renderFinanceDashboard();
    renderRevenuePage();
    renderExpensePage();
    renderCoursePage();
    renderCalculatedIndicators();
  }

  function metricCard(label,value,sub,icon,status='info',statusLabel='Informativo'){
    const labelText=status==='good'?'Dentro do esperado':status==='attention'?'Atenção':status==='critical'?'Fora do esperado':statusLabel;
    return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${value}</strong><span class="metric-sub">${escapeHtml(sub||'')}</span><span class="status-chip ${status}">${escapeHtml(labelText)}</span></article>`;
  }

  function financeSeries(){return (state.finance.dashboard?.series||[]).map(r=>({period:r.period,metrics:{...r}}))}

  function renderFinanceDashboard(){
    const d=state.finance.dashboard;if(!d)return;const c=d.cards||{};
    $('#dashboardCards').innerHTML=[
      metricCard('Receita líquida',money(c.revenue,true),'Fonte única da competência','R$','info','Base oficial'),
      metricCard('Despesa operacional',money(c.expense,true),'Sem CAPEX; cada despesa uma única vez','↓','info','Base oficial'),
      metricCard('Índice de cobertura',ratio(c.coverage),`12 meses: ${ratio(c.coverage_12m)}`,'02',statusForCoverage(c.coverage)),
      metricCard('Folha / receita',pct(c.payroll_on_revenue_pct),`Folha: ${money(c.payroll,true)}`,'03',statusForPayroll(c.payroll_on_revenue_pct)),
      metricCard('Margem operacional',pct(c.operating_margin_pct),`12 meses: ${pct(c.operating_margin_12m_pct)}`,'%','info','Calculado'),
      metricCard('Despesas rateadas',pct(c.allocated_expense_pct),`${money(c.allocated_expense,true)} alocados a cursos`,'↔','info','Reconciliação'),
    ].join('');
    const rows=financeSeries();
    renderLineChart($('#chartDashboard01'),rows,[{key:'revenue',label:'Receita',color:COLORS[0]},{key:'expense',label:'Despesa',color:COLORS[4]}],'R$');
    renderLineChart($('#chartDashboard02'),rows,[{key:'coverage',label:'Cobertura mensal',color:COLORS[0]},{key:'coverage_12m',label:'Cobertura 12m',color:COLORS[1]},{constant:1.11,label:'Meta',color:COLORS[2],dash:true}],'x');
    renderHorizontalBars($('#chartDashboard03'),(d.expense_composition||[]).map(item=>({label:CATEGORY_LABELS[item.category]||item.category,value:item.value})),'R$');
    const warnings=d.warnings||[];
    $('#dashboardInsights').innerHTML=(warnings.length?warnings:[{level:'good',title:'Base financeira consistente',text:'A receita, as despesas e a folha utilizam a mesma fonte mensal sem duplicação de valores.'}]).map(item=>`<div class="insight-item ${item.level==='attention'?'attention':item.level==='good'?'good':'info'}"><span class="insight-dot"></span><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.text)}</span></div></div>`).join('');
    const context=$('#dpeAnalysisContext');if(context)context.textContent=`${state.reference||'Sem referência'} · atualização automática · base financeira única`;
  }

  function renderRevenuePage(){
    const d=state.finance.dashboard;if(!d)return;const c=d.cards||{};
    $('#financeRevenueCards').innerHTML=[
      metricCard('Receita do mês',money(c.revenue,true),'Receita líquida institucional','R$','info','Base oficial'),
      metricCard('Receita atribuída a cursos',money(c.course_revenue,true),`${pct(c.course_revenue_coverage_pct)} do total`,'C','info','Opcional'),
      metricCard('Receita não distribuída',money(c.course_revenue_unallocated,true),'Pode incluir EAD, semi, técnico, mestrado e outras receitas','…','info','Esperado'),
    ].join('');
    renderLineChart($('#financeRevenueChart'),financeSeries(),[{key:'revenue',label:'Receita líquida',color:COLORS[0]}],'R$');
    const total=Number(c.revenue)||0;
    const items=state.finance.courseRevenues||[];
    $('#courseRevenueTable').innerHTML=items.length?items.map(row=>`<tr><td><strong>${escapeHtml(row.course_name)}</strong></td><td>${escapeHtml(row.academic_directorate)}</td><td>${money(row.allocated_revenue)}</td><td>${pct(total?Number(row.allocated_revenue)/total*100:null)}</td><td>${state.access?.canEdit?`<button class="table-action danger" data-finance-delete-course-revenue="${row.id}">Excluir</button>`:''}</td></tr>`).join(''):'<tr><td colspan="5">Nenhuma receita foi distribuída aos cursos nesta competência. Isso é permitido.</td></tr>';
  }

  function renderExpensePage(){
    const d=state.finance.dashboard;if(!d)return;const c=d.cards||{};
    $('#financeExpenseCards').innerHTML=[
      metricCard('Despesa operacional',money(c.expense,true),'Base do DPE-02; CAPEX excluído','↓','info','Base oficial'),
      metricCard('Folha total',money(c.payroll,true),`${pct(c.payroll_on_revenue_pct)} da receita`,'03',statusForPayroll(c.payroll_on_revenue_pct)),
      metricCard('CAPEX',money(c.capex,true),'Registrado à parte; não entra na cobertura','◫','info','Fora do DPE-02'),
      metricCard('Rateado a cursos',money(c.allocated_expense,true),`${pct(c.allocated_expense_pct)} das despesas operacionais`,'↔','info','Reconciliação'),
    ].join('');
    renderHorizontalBars($('#financeExpenseChart'),(d.expense_composition||[]).map(item=>({label:CATEGORY_LABELS[item.category]||item.category,value:item.value})),'R$');
    renderHorizontalBars($('#financePayrollChart'),(d.payroll_composition||[]).map(item=>({label:GROUP_LABELS[item.group]||item.group,value:item.value})),'R$');
    const kind=$('#financeExpenseKind')?.value||'';
    const items=(state.finance.expenses||[]).filter(row=>!kind||row.expense_kind===kind);
    $('#expenseTable').innerHTML=items.length?items.map(row=>`<tr><td><strong>${escapeHtml(row.description)}</strong>${row.is_capex?'<small class="table-subtitle">CAPEX</small>':''}</td><td>${escapeHtml(KIND_LABELS[row.expense_kind]||row.expense_kind)}</td><td>${escapeHtml(CATEGORY_LABELS[row.category]||row.category)}</td><td>${money(row.amount)}</td><td>${money(row.allocated_amount)}</td><td>${money(row.unallocated_amount)}</td><td>${state.access?.canEdit?`<div class="row-actions"><button data-finance-edit-expense="${row.id}">Editar</button><button class="danger" data-finance-delete-expense="${row.id}">Excluir</button></div>`:''}</td></tr>`).join(''):'<tr><td colspan="7">Nenhuma despesa encontrada neste recorte.</td></tr>';
  }

  function courseRows(){return state.finance.dashboard?.courses||[]}
  function renderCoursePage(){
    const selected=$('#financeCourseFilter')?.value||'';
    let rows=courseRows();if(selected)rows=rows.filter(row=>String(row.course_id)===String(selected));
    const complete=rows.filter(isCourseComplete);
    const withRevenue=rows.filter(hasCourseRevenue);
    const withCost=rows.filter(hasCourseCost);
    const totalRevenue=withRevenue.length?withRevenue.reduce((sum,row)=>sum+Number(row.revenue||0),0):null;
    const totalCost=withCost.length?withCost.reduce((sum,row)=>sum+Number(row.effective_cost||0),0):null;
    const knownResult=complete.length?complete.reduce((sum,row)=>sum+Number(courseResult(row)||0),0):null;
    const denominator=selected?1:actualCourses().length;
    $('#financeCourseCards').innerHTML=[
      metricCard('Apuração completa',`${complete.length}/${denominator||rows.length}`,selected?'Curso selecionado com receita e custo/despesa conhecidos':'Cursos com receita e custo/despesa conhecidos','✓',complete.length&&complete.length===denominator?'good':complete.length?'attention':'info'),
      metricCard('Receita atribuída',money(totalRevenue,true),`${withRevenue.length} curso(s) com receita informada`,'R$','info','Base por curso'),
      metricCard('Despesa / custo conhecido',money(totalCost,true),`${withCost.length} curso(s) com custo apurado ou despesas rateadas`,'↓','info','Base por curso'),
      metricCard('Resultado econômico conhecido',money(knownResult,true),`${complete.length} curso(s) entram neste resultado`,'=',statusForResult(knownResult),complete.length?'Calculado':'Pendente'),
    ].join('');

    const comparisonItems=rows.filter(row=>hasCourseRevenue(row)||hasCourseCost(row)).map(row=>({
      label:row.course_name,
      revenue:hasCourseRevenue(row)?Number(row.revenue):null,
      effective_cost:hasCourseCost(row)?Number(row.effective_cost):null,
      tooltip:[
        {label:'Diretoria',value:row.academic_directorate||'—'},
        {label:'Apuração',value:courseDataStatus(row)},
        {label:'Origem do custo',value:costSource(row)},
        {label:'Resultado',value:money(courseResult(row))},
        {label:'Despesa / receita',value:pct(courseExpenseRatio(row))},
        {label:'Margem',value:pct(row.margin_pct)},
      ],
    }));
    renderGroupedHorizontalBars($('#courseRevenueExpenseChart'),comparisonItems,[
      {key:'revenue',label:'Receita atribuída',color:COLORS[0]},
      {key:'effective_cost',label:'Despesa / custo considerado',color:COLORS[4]},
    ],'R$');

    renderHorizontalBars($('#courseResultChart'),complete.map(row=>({
      label:row.course_name,
      value:courseResult(row),
      status:statusForResult(courseResult(row)),
      tooltip:[
        {label:'Receita',value:money(row.revenue)},
        {label:'Despesa / custo',value:money(row.effective_cost)},
        {label:'Margem',value:pct(row.margin_pct)},
        {label:'Origem do custo',value:costSource(row)},
      ],
    })),'R$');

    const expenseTarget=Math.max(0,100-marginTarget());
    renderHorizontalBars($('#courseExpenseRatioChart'),complete.map(row=>({
      label:row.course_name,
      value:courseExpenseRatio(row),
      status:statusForExpenseRatio(courseExpenseRatio(row)),
      tooltip:[
        {label:'Receita',value:money(row.revenue)},
        {label:'Despesa / custo',value:money(row.effective_cost)},
        {label:'Resultado',value:money(courseResult(row))},
        {label:'Margem',value:pct(row.margin_pct)},
      ],
    })),'%',expenseTarget);
    renderCourseEvolution(selected);

    $('#courseFinanceTable').innerHTML=rows.length?rows.map(row=>{
      const result=courseResult(row);const ratioValue=courseExpenseRatio(row);const status=statusForCourseData(row);
      return `<tr data-course-row="${row.course_id}"><td><strong>${escapeHtml(row.course_name)}</strong><small class="table-subtitle">${escapeHtml(row.academic_directorate)}</small></td><td>${money(row.revenue)}</td><td><strong>${money(row.effective_cost)}</strong><small class="table-subtitle">${escapeHtml(costSource(row))}</small></td><td>${money(result)}</td><td>${pct(ratioValue)}</td><td>${pct(row.margin_pct)}</td><td>${money(row.unreconciled_cost)}</td><td><span class="status-chip ${status}">${escapeHtml(courseDataStatus(row))}</span></td></tr>`;
    }).join(''):'<tr><td colspan="8">Ainda não há receita, custo ou despesas atribuídas aos cursos nesta competência.</td></tr>';
    renderCourseBreakdown(selected,rows);
  }

  function renderCourseEvolution(selected){
    const title=$('#courseEvolutionTitle');const root=$('#courseEvolutionChart');if(!root)return;
    if(!selected){if(title)title.textContent='Selecione um curso';root.innerHTML='<div class="course-breakdown-empty">Selecione um curso no filtro ou clique em uma linha da tabela para acompanhar receita, despesa/custo e resultado ao longo do tempo.</div>';return}
    const history=(state.finance.dashboard?.course_history||[]).find(item=>String(item.course_id)===String(selected));
    if(title)title.textContent=history?`${history.course_name} · evolução`:'Curso sem histórico';
    if(!history?.series?.length){root.innerHTML='<div class="course-breakdown-empty">Ainda não existe histórico suficiente para este curso.</div>';return}
    const rows=history.series.map(row=>({period:row.period,metrics:{revenue:row.revenue,effective_cost:row.effective_cost,result_amount:row.result_amount}}));
    renderLineChart(root,rows,[
      {key:'revenue',label:'Receita atribuída',color:COLORS[0]},
      {key:'effective_cost',label:'Despesa / custo considerado',color:COLORS[4]},
      {key:'result_amount',label:'Resultado',color:COLORS[1]},
    ],'R$');
  }

  function renderCourseBreakdown(selected,rows){
    const title=$('#courseBreakdownTitle'),root=$('#courseBreakdown');if(!title||!root)return;
    if(!selected){title.textContent='Selecione um curso';root.className='course-breakdown-empty';root.textContent='Escolha um curso no filtro acima para visualizar a composição da apuração e as despesas reais rateadas.';return}
    const row=rows.find(r=>String(r.course_id)===String(selected));
    if(!row){title.textContent='Curso sem dados';root.className='course-breakdown-empty';root.textContent='Este curso ainda não possui receita, apuração de custo ou despesas rateadas na competência.';return}
    title.textContent=`${row.course_name} · ${state.reference}`;
    const reported=row.reported_details||[];
    const real=row.breakdown||[];
    const result=courseResult(row);const ratioValue=courseExpenseRatio(row);
    root.className='course-breakdown-list';
    root.innerHTML=`
      <div class="course-economic-flow">
        <div><span>Receita atribuída</span><strong>${money(row.revenue)}</strong><small>${hasCourseRevenue(row)?'Informada para o curso':'Aguardando receita'}</small></div>
        <div class="course-flow-symbol" aria-hidden="true">−</div>
        <div><span>Despesa / custo considerado</span><strong>${money(row.effective_cost)}</strong><small>${escapeHtml(costSource(row))}</small></div>
        <div class="course-flow-symbol" aria-hidden="true">=</div>
        <div><span>Resultado</span><strong class="${result!==null&&result<0?'negative-value':''}">${money(result)}</strong><small>${escapeHtml(courseDataStatus(row))}</small></div>
        <div><span>Despesa / receita</span><strong>${pct(ratioValue)}</strong><small>${ratioValue===null?'Aguardando apuração':'Quanto da receita é consumido'}</small></div>
        <div><span>Margem</span><strong>${pct(row.margin_pct)}</strong><small>${row.margin_pct===null?'Aguardando apuração':'Parcela que permanece'}</small></div>
      </div>
      <div class="reconciliation-summary"><div><span>Custo gerencial informado</span><strong>${money(row.reported_total_cost)}</strong></div><div><span>Despesas reais rateadas</span><strong>${money(row.allocated_cost)}</strong></div><div><span>Diferença a reconciliar</span><strong>${money(row.unreconciled_cost)}</strong></div></div>
      <div class="course-breakdown-columns">
        <div><h4>Composição gerencial informada</h4><p class="panel-note">Quando existir uma apuração gerencial, ela é exibida aqui como referência de custo do curso. Não cria uma nova despesa institucional.</p>${reported.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Item</th><th>Valor</th></tr></thead><tbody>${reported.map(item=>`<tr><td>${escapeHtml(item.description)}</td><td>${money(item.amount)}</td></tr>`).join('')}${Number(row.reported_undetailed_cost)>0?`<tr><td><strong>Não detalhado</strong></td><td><strong>${money(row.reported_undetailed_cost)}</strong></td></tr>`:''}</tbody></table></div>`:'<div class="course-breakdown-empty">Nenhum detalhamento gerencial foi informado para este curso.</div>'}</div>
        <div><h4>Despesas reais rateadas</h4><p class="panel-note">Cada valor abaixo existe uma única vez na base institucional e apenas uma parcela foi atribuída ao curso.</p>${real.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Despesa real</th><th>Tipo</th><th>Valor rateado</th></tr></thead><tbody>${real.map(item=>`<tr><td>${escapeHtml(item.description)}</td><td>${escapeHtml(KIND_LABELS[item.expense_kind]||item.expense_kind)}</td><td>${money(item.allocated_amount)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="course-breakdown-empty">Nenhuma despesa real foi rateada para este curso ainda.</div>'}</div>
      </div>`;
  }

  function renderCalculatedIndicators(){
    const d=state.finance.dashboard;if(!d)return;const c=d.cards||{};
    const marginRows=(d.course_margin_series||[]).map(r=>({period:r.period,metrics:{margin_pct:r.margin_pct,expense_to_revenue_pct:r.expense_to_revenue_pct}}));
    const currentMargin=(d.course_margin_series||[]).find(r=>r.period===d.reference)||{};
    const currentCourses=(d.courses||[]).filter(isCourseComplete);
    const target=marginTarget();
    const expenseTarget=Math.max(0,100-target);
    $('#cardsDPE01').innerHTML=[
      metricCard('Resultado econômico conhecido',money(currentMargin.result_amount,true),`${currentMargin.courses_with_complete_data||0} curso(s) com apuração completa`,'=',statusForResult(currentMargin.result_amount),currentMargin.courses_with_complete_data?'Calculado':'Pendente'),
      metricCard('Receita dos cursos completos',money(currentMargin.course_revenue,true),'Somente cursos com receita e custo/despesa conhecidos','R$','info','Recorte'),
      metricCard('Despesa / custo dos cursos',money(currentMargin.course_cost,true),`Despesa/receita agregada: ${pct(currentMargin.expense_to_revenue_pct)}`,'↓','info','Recorte'),
      metricCard('Margem agregada',pct(currentMargin.margin_pct),`Meta vigente ≥ ${pct(target)}`,'01',statusForMargin(currentMargin.margin_pct)),
    ].join('');
    renderLineChart($('#chartDPE01'),marginRows,[{key:'margin_pct',label:'Margem agregada',color:COLORS[0]},{constant:target,label:'Meta vigente',color:COLORS[2],dash:true}],'%');
    renderHorizontalBars($('#barDPE01'),currentCourses.map(row=>({
      label:row.course_name,
      value:courseExpenseRatio(row),
      status:statusForExpenseRatio(courseExpenseRatio(row)),
      tooltip:[
        {label:'Diretoria',value:row.academic_directorate||'—'},
        {label:'Receita atribuída',value:money(row.revenue)},
        {label:'Despesa / custo',value:money(row.effective_cost)},
        {label:'Resultado',value:money(courseResult(row))},
        {label:'Margem',value:pct(row.margin_pct)},
        {label:'Origem do custo',value:costSource(row)},
      ],
    })),'%',expenseTarget);
    const table=$('#dimensionTableDPE01');if(table)table.innerHTML=(d.courses||[]).length?(d.courses||[]).map(row=>`<tr><td><strong>${escapeHtml(row.course_name)}</strong><small class="table-subtitle">${escapeHtml(row.academic_directorate)}</small></td><td>${money(row.revenue)}</td><td>${money(row.effective_cost)}</td><td>${money(courseResult(row))}</td><td>${pct(courseExpenseRatio(row))}</td><td>${pct(row.margin_pct)}</td><td><span class="status-chip ${statusForCourseData(row)}">${escapeHtml(courseDataStatus(row))}</span></td></tr>`).join(''):'<tr><td colspan="7">Nenhum curso apurado no período.</td></tr>';

    $('#cardsDPE02').innerHTML=[
      metricCard('Cobertura mensal',ratio(c.coverage),'Meta inicial ≥ 1,11x','02',statusForCoverage(c.coverage)),
      metricCard('Cobertura 12 meses',ratio(c.coverage_12m),'Razão entre receitas e despesas acumuladas','12',statusForCoverage(c.coverage_12m)),
      metricCard('Margem operacional',pct(c.operating_margin_pct),`12 meses: ${pct(c.operating_margin_12m_pct)}`,'%','info','Calculado'),
      metricCard('Despesa operacional',money(c.expense,true),'CAPEX excluído do denominador','↓','info','Base oficial'),
    ].join('');
    const rows=financeSeries();
    renderLineChart($('#chartDPE02'),rows,[{key:'coverage',label:'Cobertura mensal',color:COLORS[0]},{key:'coverage_12m',label:'Cobertura 12m',color:COLORS[1]},{constant:1.11,label:'Meta',color:COLORS[2],dash:true}],'x');
    renderHorizontalBars($('#barDPE02'),(d.expense_composition||[]).map(item=>({label:CATEGORY_LABELS[item.category]||item.category,value:item.value})),'R$');

    $('#cardsDPE03').innerHTML=[
      metricCard('Folha / receita',pct(c.payroll_on_revenue_pct),`Folha total ${money(c.payroll,true)}`,'03',statusForPayroll(c.payroll_on_revenue_pct)),
      metricCard('Folha / receita média 3m',pct(c.payroll_on_avg_revenue_3m_pct),'Segunda leitura para decisões de contratação','3m',statusForPayroll(c.payroll_on_avg_revenue_3m_pct)),
      metricCard('Folha docente',pct(c.faculty_payroll_pct),'Meta inicial ≤ 38%','D',c.faculty_payroll_pct===null?'info':c.faculty_payroll_pct<=38?'good':'critical'),
      metricCard('Folha administrativa',pct(c.administrative_payroll_pct),'Meta inicial ≤ 17%','A',c.administrative_payroll_pct===null?'info':c.administrative_payroll_pct<=17?'good':'critical'),
      metricCard('Variação mensal da folha',pct(c.payroll_monthly_change_pct),'Meta inicial ≤ 2%','Δ',c.payroll_monthly_change_pct===null?'info':c.payroll_monthly_change_pct<=2?'good':'attention'),
    ].join('');
    renderLineChart($('#chartDPE03'),rows,[{key:'payroll_on_revenue_pct',label:'Folha / receita',color:COLORS[0]},{key:'payroll_on_avg_revenue_3m_pct',label:'Folha / receita média 3m',color:COLORS[1]},{constant:55,label:'Meta',color:COLORS[2],dash:true}],'%');
    renderHorizontalBars($('#barDPE03'),[{label:'Folha docente',value:c.faculty_payroll_pct,target:38,status:c.faculty_payroll_pct===null?'info':c.faculty_payroll_pct<=38?'good':'critical',tooltip:[{label:'Leitura',value:'Percentual da receita consumido pela folha docente'}]},{label:'Folha administrativa',value:c.administrative_payroll_pct,target:17,status:c.administrative_payroll_pct===null?'info':c.administrative_payroll_pct<=17?'good':'critical',tooltip:[{label:'Leitura',value:'Percentual da receita consumido pela folha administrativa'}]}],'%');
  }

  function openFinanceModal(title,subtitle,html){$('#financeModalTitle').textContent=title;$('#financeModalSubtitle').textContent=subtitle;$('#financeModalBody').innerHTML=html;$('#financeModal').classList.remove('hidden')}
  function formErrors(error){const fields=error?.payload?.detail?.campos||{};const extra=Object.values(fields).join(' ');return `${error.message}${extra?` ${extra}`:''}`}

  function openRevenue(){
    const current=(state.finance.revenues||[]).find(row=>row.period===currentPeriod());
    openFinanceModal('Receita líquida mensal','Este é o único valor de receita institucional usado pelos indicadores da DPE.',`<form id="financeRevenueForm" class="form-grid dpe-measurement-form"><label><span>Competência *</span><input id="finRevenuePeriod" required placeholder="AAAA-MM" value="${escapeHtml(currentPeriod())}"></label><label><span>Receita líquida *</span><input id="finRevenueAmount" type="number" step="0.01" min="0" required value="${escapeHtml(current?.net_revenue??'')}"></label><label class="span-2"><span>Observações</span><textarea id="finRevenueNotes">${escapeHtml(current?.notes||'')}</textarea></label><label class="check-field span-2"><input id="finRevenueValidated" type="checkbox" ${current?.validated!==false?'checked':''}><span>Valor conferido</span></label><div id="financeFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="financeModal">Cancelar</button><button class="button primary" type="submit">Salvar receita</button></div></form>`);
    $('#financeRevenueForm').addEventListener('submit',saveRevenue);
  }
  async function saveRevenue(event){event.preventDefault();try{const period=$('#finRevenuePeriod').value;await api('/api/dpe/finance/revenues',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({period,net_revenue:Number($('#finRevenueAmount').value),notes:$('#finRevenueNotes').value,validated:$('#finRevenueValidated').checked})});closeModal('financeModal');showAlert('Receita mensal salva.','success');state.reference=period;await refreshFinance({preserveReference:true})}catch(error){const box=$('#financeFormErrors');box.textContent=formErrors(error);box.classList.remove('hidden')}}

  function openCourseRevenue(){
    openFinanceModal('Receita por curso','Opcional. Use apenas quando houver uma distribuição gerencial confiável; o restante da receita pode permanecer não distribuído.',`<form id="financeCourseRevenueForm" class="form-grid dpe-measurement-form"><label><span>Competência *</span><input id="finCourseRevenuePeriod" required value="${escapeHtml(currentPeriod())}"></label><label><span>Curso *</span><select id="finCourseRevenueCourse" required>${courseOptions()}</select></label><label><span>Receita atribuída *</span><input id="finCourseRevenueAmount" type="number" min="0" step="0.01" required></label><label class="span-2"><span>Observações</span><textarea id="finCourseRevenueNotes"></textarea></label><div class="indicator-definition span-2"><strong>Distribuição parcial permitida</strong><span>A receita institucional pode incluir EAD, semipresencial, técnico, mestrado e outras origens que não pertencem ao catálogo presencial.</span></div><div id="financeFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="financeModal">Cancelar</button><button class="button primary" type="submit">Salvar</button></div></form>`);
    $('#financeCourseRevenueForm').addEventListener('submit',saveCourseRevenue);
  }
  async function saveCourseRevenue(event){event.preventDefault();try{await api('/api/dpe/finance/course-revenues',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({period:$('#finCourseRevenuePeriod').value,course_id:Number($('#finCourseRevenueCourse').value),allocated_revenue:Number($('#finCourseRevenueAmount').value),notes:$('#finCourseRevenueNotes').value})});closeModal('financeModal');showAlert('Receita do curso salva.','success');await refreshFinance({preserveReference:true})}catch(error){const box=$('#financeFormErrors');box.textContent=formErrors(error);box.classList.remove('hidden')}}

  function allocationRow(item={}){return `<div class="finance-allocation-row"><select data-allocation-course>${courseOptions(item.course_id||'')}</select><input data-allocation-amount type="number" min="0" step="0.01" placeholder="Valor" value="${escapeHtml(item.allocated_amount??'')}"><button type="button" class="icon-button small" data-remove-allocation title="Remover">×</button></div>`}
  function openExpense(row=null){
    const allocations=(row?.allocations||[]).map(allocationRow).join('');
    openFinanceModal(row?'Editar despesa':'Nova despesa','A despesa é registrada uma única vez. Rateios aos cursos são apenas visões analíticas e não aumentam o total institucional.',`<form id="financeExpenseForm" class="form-grid dpe-measurement-form"><input id="finExpenseId" type="hidden" value="${row?.id||''}"><label><span>Competência *</span><input id="finExpensePeriod" required value="${escapeHtml(row?.period||currentPeriod())}"></label><label class="span-2"><span>Descrição *</span><input id="finExpenseDescription" required value="${escapeHtml(row?.description||'')}"></label><label><span>Valor *</span><input id="finExpenseAmount" type="number" min="0.01" step="0.01" required value="${escapeHtml(row?.amount??'')}"></label><label><span>Tipo *</span><select id="finExpenseKind"><option value="GENERAL" ${row?.expense_kind!=='PAYROLL'?'selected':''}>Despesa geral</option><option value="PAYROLL" ${row?.expense_kind==='PAYROLL'?'selected':''}>Folha de pagamento</option></select></label><label id="finCategoryWrap"><span>Categoria *</span><select id="finExpenseCategory">${Object.entries(CATEGORY_LABELS).map(([k,v])=>option(k,v,row?.category===k)).join('')}</select></label><label class="finance-payroll-field"><span>Grupo da folha</span><select id="finPayrollGroup">${Object.entries(GROUP_LABELS).map(([k,v])=>option(k,v,row?.payroll_group===k)).join('')}</select></label><label class="finance-payroll-field"><span>Natureza da folha</span><select id="finPayrollNature">${Object.entries(NATURE_LABELS).map(([k,v])=>option(k,v,row?.payroll_nature===k)).join('')}</select></label><label class="check-field"><input id="finExpenseCapex" type="checkbox" ${row?.is_capex?'checked':''}><span>Investimento / imobilizado (CAPEX)</span></label><label class="check-field"><input id="finExpenseValidated" type="checkbox" ${row?.validated!==false?'checked':''}><span>Despesa conferida</span></label><div class="span-2 finance-allocation-box"><div class="finance-allocation-heading"><div><strong>Rateio opcional entre cursos</strong><small>O total rateado pode ser menor que a despesa; nunca pode ser maior.</small></div><div><button type="button" class="button secondary compact" id="addAllocation">+ Curso</button><button type="button" class="button secondary compact" id="equalAllocation">Dividir igualmente</button></div></div><div id="allocationRows">${allocations}</div></div><label class="span-2"><span>Observações</span><textarea id="finExpenseNotes">${escapeHtml(row?.notes||'')}</textarea></label><div id="financeFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="financeModal">Cancelar</button><button class="button primary" type="submit">Salvar despesa</button></div></form>`);
    const togglePayroll=()=>{$$('.finance-payroll-field','#financeExpenseForm').forEach(el=>el.classList.toggle('hidden',$('#finExpenseKind').value!=='PAYROLL'));$('#finCategoryWrap').classList.toggle('hidden',$('#finExpenseKind').value==='PAYROLL')};togglePayroll();
    $('#finExpenseKind').addEventListener('change',togglePayroll);
    $('#addAllocation').addEventListener('click',()=>$('#allocationRows').insertAdjacentHTML('beforeend',allocationRow()));
    $('#equalAllocation').addEventListener('click',()=>{const rows=$$('.finance-allocation-row','#allocationRows');if(!rows.length)return;const amount=Number($('#finExpenseAmount').value)||0;const share=Math.floor(amount/rows.length*100)/100;rows.forEach((r,i)=>{const input=$('[data-allocation-amount]',r);input.value=i===rows.length-1?(amount-share*(rows.length-1)).toFixed(2):share.toFixed(2)})});
    $('#allocationRows').addEventListener('click',event=>{const btn=event.target.closest('[data-remove-allocation]');if(btn)btn.closest('.finance-allocation-row').remove()});
    $('#financeExpenseForm').addEventListener('submit',saveExpense);
  }
  async function saveExpense(event){event.preventDefault();const id=$('#finExpenseId').value;const allocations=$$('.finance-allocation-row','#allocationRows').map(row=>({course_id:Number($('[data-allocation-course]',row).value),allocated_amount:Number($('[data-allocation-amount]',row).value)})).filter(item=>item.course_id&&item.allocated_amount>0);const kind=$('#finExpenseKind').value;const payload={period:$('#finExpensePeriod').value,description:$('#finExpenseDescription').value,amount:Number($('#finExpenseAmount').value),expense_kind:kind,category:kind==='PAYROLL'?'PERSONNEL':$('#finExpenseCategory').value,payroll_group:kind==='PAYROLL'?$('#finPayrollGroup').value:null,payroll_nature:kind==='PAYROLL'?$('#finPayrollNature').value:null,is_capex:$('#finExpenseCapex').checked,validated:$('#finExpenseValidated').checked,notes:$('#finExpenseNotes').value,allocations};try{await api(id?`/api/dpe/finance/expenses/${id}`:'/api/dpe/finance/expenses',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeModal('financeModal');showAlert('Despesa salva sem duplicar o total institucional.','success');await refreshFinance({preserveReference:true})}catch(error){const box=$('#financeFormErrors');box.textContent=formErrors(error);box.classList.remove('hidden')}}

  function courseCostDetailRow(item={}){return `<div class="finance-cost-detail-row"><input data-cost-detail-description placeholder="Ex.: Custo docente" value="${escapeHtml(item.description||'')}"><input data-cost-detail-amount type="number" min="0.01" step="0.01" placeholder="Valor" value="${escapeHtml(item.amount??'')}"><button type="button" class="icon-button small" data-remove-cost-detail title="Remover">×</button></div>`}
  function openCourseCost(){
    const selectedCourse=$('#financeCourseFilter')?.value||'';
    const existing=(state.finance.courseCosts||[]).find(row=>String(row.course_id)===String(selectedCourse));
    const details=(existing?.details||[]).map(courseCostDetailRow).join('');
    openFinanceModal('Apuração gerencial do custo do curso','Informe este valor apenas quando houver uma apuração gerencial confiável. Ele é usado na leitura econômica do curso e não cria uma nova despesa institucional.',`<form id="financeCourseCostForm" class="form-grid dpe-measurement-form"><label><span>Competência *</span><input id="finCourseCostPeriod" required value="${escapeHtml(currentPeriod())}"></label><label><span>Curso *</span><select id="finCourseCostCourse" required>${courseOptions(selectedCourse)}</select></label><label><span>Custo gerencial apurado *</span><input id="finCourseCostAmount" type="number" min="0" step="0.01" required value="${escapeHtml(existing?.reported_total_cost??'')}"></label><div class="span-2 finance-allocation-box"><div class="finance-allocation-heading"><div><strong>Detalhamento gerencial opcional</strong><small>Ex.: custo docente, coordenação, laboratório. Os itens podem somar menos que o total, mas nunca mais.</small></div><button type="button" class="button secondary compact" id="addCourseCostDetail">+ Item</button></div><div id="courseCostDetailRows">${details}</div></div><label class="span-2"><span>Observações</span><textarea id="finCourseCostNotes" placeholder="Ex.: fechamento gerencial do curso; detalhamento ainda parcial.">${escapeHtml(existing?.notes||'')}</textarea></label><div class="indicator-definition span-2"><strong>Como este valor é usado</strong><span>Folha e demais despesas continuam existindo uma única vez em Despesas. Esta apuração é uma referência gerencial do curso; quando não existir, o sistema pode usar as despesas reais rateadas.</span></div><div id="financeFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="financeModal">Cancelar</button><button class="button primary" type="submit">Salvar custo</button></div></form>`);
    $('#addCourseCostDetail').addEventListener('click',()=>$('#courseCostDetailRows').insertAdjacentHTML('beforeend',courseCostDetailRow()));
    $('#courseCostDetailRows').addEventListener('click',event=>{const btn=event.target.closest('[data-remove-cost-detail]');if(btn)btn.closest('.finance-cost-detail-row').remove()});
    $('#finCourseCostCourse').addEventListener('change',event=>{const row=(state.finance.courseCosts||[]).find(item=>String(item.course_id)===String(event.target.value));$('#finCourseCostAmount').value=row?.reported_total_cost??'';$('#finCourseCostNotes').value=row?.notes||'';$('#courseCostDetailRows').innerHTML=(row?.details||[]).map(courseCostDetailRow).join('')});
    $('#financeCourseCostForm').addEventListener('submit',saveCourseCost);
  }
  async function saveCourseCost(event){event.preventDefault();const details=$$('.finance-cost-detail-row','#courseCostDetailRows').map(row=>({description:$('[data-cost-detail-description]',row).value.trim(),amount:Number($('[data-cost-detail-amount]',row).value)})).filter(item=>item.description&&item.amount>0);try{await api('/api/dpe/finance/course-costs',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({period:$('#finCourseCostPeriod').value,course_id:Number($('#finCourseCostCourse').value),reported_total_cost:Number($('#finCourseCostAmount').value),details,notes:$('#finCourseCostNotes').value})});closeModal('financeModal');showAlert('Apuração de custo do curso salva.','success');await refreshFinance({preserveReference:true})}catch(error){const box=$('#financeFormErrors');box.textContent=formErrors(error);box.classList.remove('hidden')}}

  async function deleteExpense(id){if(!confirm('Excluir esta despesa real e todos os seus rateios?'))return;try{await api(`/api/dpe/finance/expenses/${id}`,{method:'DELETE'});showAlert('Despesa excluída.','success');await refreshFinance({preserveReference:true})}catch(error){showAlert(error.message,'error',0)}}
  async function deleteCourseRevenue(id){if(!confirm('Excluir a distribuição de receita deste curso? A receita institucional não será alterada.'))return;try{await api(`/api/dpe/finance/course-revenues/${id}`,{method:'DELETE'});showAlert('Distribuição removida.','success');await refreshFinance({preserveReference:true})}catch(error){showAlert(error.message,'error',0)}}

  function bindFinanceEvents(){
    $('#newRevenue')?.addEventListener('click',openRevenue);
    $('#newCourseRevenue')?.addEventListener('click',openCourseRevenue);
    $('#newExpense')?.addEventListener('click',()=>openExpense());
    $('#newCourseCost')?.addEventListener('click',openCourseCost);
    $('#financeRevenuePeriod')?.addEventListener('change',event=>changeFinancePeriod(event.target.value));
    $('#financeExpensePeriod')?.addEventListener('change',event=>changeFinancePeriod(event.target.value));
    $('#financeCoursePeriod')?.addEventListener('change',event=>changeFinancePeriod(event.target.value));
    $('#financeExpenseKind')?.addEventListener('change',renderExpensePage);
    $('#financeCourseFilter')?.addEventListener('change',renderCoursePage);
    document.addEventListener('click',event=>{
      const close=event.target.closest('[data-close-modal="financeModal"]');if(close){closeModal('financeModal');return}
      const delExpense=event.target.closest('[data-finance-delete-expense]');if(delExpense){deleteExpense(delExpense.dataset.financeDeleteExpense);return}
      const editExpense=event.target.closest('[data-finance-edit-expense]');if(editExpense){const row=(state.finance.expenses||[]).find(item=>String(item.id)===String(editExpense.dataset.financeEditExpense));if(row)openExpense(row);return}
      const delRevenue=event.target.closest('[data-finance-delete-course-revenue]');if(delRevenue){deleteCourseRevenue(delRevenue.dataset.financeDeleteCourseRevenue);return}
      const courseRow=event.target.closest('[data-course-row]');if(courseRow&&$('#financeCourseFilter')){$('#financeCourseFilter').value=courseRow.dataset.courseRow;renderCoursePage();return}
    });
  }
  async function changeFinancePeriod(period){if(!period)return;state.reference=period;const main=$('#dashboardReference');if(main&&[...main.options].some(o=>o.value===period))main.value=period;await refreshFinance({preserveReference:true})}

  async function initializeFinance(){bindFinanceEvents();await refreshFinance({preserveReference:true})}
  window.initializeDPEFinance=initializeFinance;
  window.refreshDPEFinance=refreshFinance;
  window.openDPEExpense=()=>openExpense();
})();
