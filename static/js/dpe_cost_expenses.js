(function(){
  const SOURCE_LABELS={MANUAL:'Manual',EXCEL:'Excel',API:'API',REQUEST:'Requisição',OTHER:'Outra'};
  const KIND_LABELS={GENERAL:'Demais despesas',PAYROLL:'Folha / pessoal'};
  const BATCH_STATUS_LABELS={STAGING:'Em preparação',READY:'Pronto',COMMITTED:'Processado',FAILED:'Com erro',CANCELLED:'Cancelado'};
  const DRIVER_LABELS={DIRECT:'Direto',TEACHER_HOURS:'Carga docente',OFFERING_HOURS:'Carga do curso/contexto',STUDENTS:'Alunos',REVENUE:'Receita',EQUAL:'Igualitário',MANUAL:'Manual'};
  const SCOPE_LABELS={DIRECT:'Direta',SHARED:'Compartilhada',INSTITUTIONAL:'Institucional'};

  if(!state.costExpenses){state.costExpenses={periodId:null,view:'ledger',expenses:[],centers:[],categories:[],rules:[],batches:[],periodOfferings:[],summary:{},loaded:false,selected:new Set(),lastImportPreview:null};}else if(!state.costExpenses.selected){state.costExpenses.selected=new Set();}

  function money(value){return Number(value||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:2,maximumFractionDigits:2})}
  function activeChip(active){return `<span class="status-chip ${active?'good':'info'}">${active?'Ativo':'Inativo'}</span>`}
  function expenseStatusChip(status){return `<span class="status-chip ${status==='ACTIVE'?'good':'attention'}">${status==='ACTIVE'?'Ativa':'Estornada'}</span>`}
  function periodLabel(status){return ({DRAFT:'Preparação',REVIEW:'Conferência',CALCULATED:'Calculada',CLOSED:'Fechada'})[status]||status}
  function modalOpen(title,subtitle,body,eyebrow='DPE · DESPESAS'){
    $('#costEngineModalEyebrow').textContent=eyebrow;
    $('#costEngineModalTitle').textContent=title;
    $('#costEngineModalSubtitle').textContent=subtitle||'';
    $('#costEngineModalBody').innerHTML=body;
    openDPEModal('costEngineModal');
  }
  function modalClose(){closeDPEModal('costEngineModal')}
  function formError(error){const detail=error?.payload?.detail;const fields=detail?.campos||{};const lines=Object.entries(fields).map(([key,value])=>`${key}: ${value}`);return [error.message,...lines].filter(Boolean).join('\n')}
  function showFormError(error){const box=$('#costExpenseFormErrors');if(box){focusInlineError(box,formError(error));}else showAlert(error.message,'error',0)}
  function periods(){return state.costEngine?.periods||[]}
  function selectedPeriod(){return periods().find(row=>String(row.id)===String(state.costExpenses.periodId))||null}
  function editablePeriods(){return periods().filter(row=>['DRAFT','REVIEW'].includes(row.status))}
  function currentPeriodId(){return state.costExpenses.periodId||selectedPeriod()?.id||null}

  function renderPeriodFilter(){
    const select=$('#costExpensePeriodFilter');if(!select)return;
    const old=String(state.costExpenses.periodId||'');
    select.innerHTML=periods().length?periods().map(row=>option(row.id,`${row.period} · ${periodLabel(row.status)}`,String(row.id)===old)).join(''):'<option value="">Selecione um mês primeiro</option>';
    if(old&&[...select.options].some(o=>o.value===old))select.value=old;
  }
  function renderFilterOptions(){
    const category=$('#costExpenseCategoryFilter'),center=$('#costExpenseCenterFilter');
    if(category){const old=category.value;category.innerHTML='<option value="">Todas</option>'+state.costExpenses.categories.map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===old)).join('');if(old)category.value=old;}
    if(center){const old=center.value;center.innerHTML='<option value="">Todos</option>'+state.costExpenses.centers.map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===old)).join('');if(old)center.value=old;}
  }
  function renderCards(){
    const s=state.costExpenses.summary||{}, scopes=s.by_scope||{};
    const direct=scopes.DIRECT||{count:0,amount:0},shared=scopes.SHARED||{count:0,amount:0},institutional=scopes.INSTITUTIONAL||{count:0,amount:0};
    $('#costExpenseCards').innerHTML=[
      card('Total do mês',money(s.total_amount||0),`${s.expense_count||0} despesa(s) ativa(s)`,'R$'),
      card('Diretas',money(direct.amount||0),`${direct.count||0} ligada(s) diretamente a curso`,'D'),
      card('Compartilhadas',money(shared.amount||0),`${shared.count||0} para distribuir entre cursos`,'C'),
      card('Institucionais',money(institutional.amount||0),`${institutional.count||0} somente no resultado institucional`,'I'),
    ].join('');
  }
  function card(label,value,sub,icon){return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-sub">${escapeHtml(sub)}</span></article>`}

  function filteredExpenses(){
    const kind=$('#costExpenseKindFilter')?.value||'',source=$('#costExpenseSourceFilter')?.value||'',status=$('#costExpenseStatusFilter')?.value||'',category=$('#costExpenseCategoryFilter')?.value||'',center=$('#costExpenseCenterFilter')?.value||'',scope=$('#costExpenseScopeFilter')?.value||'',q=($('#costExpenseSearch')?.value||'').trim().toLocaleLowerCase('pt-BR');
    return (state.costExpenses.expenses||[]).filter(row=>{
      if(kind&&row.expense_kind!==kind)return false;if(source&&row.source_type!==source)return false;if(status&&row.status!==status)return false;if(category&&String(row.category_id)!==String(category))return false;if(center&&String(row.cost_center_id)!==String(center))return false;if(scope&&String(row.expense_scope||'SHARED')!==scope)return false;
      if(q){const hay=[row.description,row.counterparty_name,row.document_number,row.category_name,row.cost_center_name,row.direct_destination_label,SCOPE_LABELS[row.expense_scope]].filter(Boolean).join(' ').toLocaleLowerCase('pt-BR');if(!hay.includes(q))return false;}
      return true;
    });
  }
  function renderSelection(){
    const selected=state.costExpenses.selected||new Set();
    const period=selectedPeriod();
    const visible=filteredExpenses().filter(row=>row.status==='ACTIVE'&&row.editable);
    const context=$('#costExpenseSelectionContext');
    if(context){
      if(selected.size)context.textContent=`${selected.size} selecionada(s)`;
      else if(!period)context.textContent='Selecione um mês';
      else if(!['DRAFT','REVIEW'].includes(period.status))context.textContent='Competência protegida — volte para Conferência para editar';
      else if(!visible.length)context.textContent='Nenhuma despesa visível está disponível para edição';
      else context.textContent='Nenhuma selecionada';
    }
    const button=$('#bulkClassifyExpenses');if(button)button.disabled=!selected.size;
    const selectAll=$('#selectAllCostExpenses');if(selectAll){
      selectAll.disabled=!visible.length;
      selectAll.title=!visible.length?(period&&!['DRAFT','REVIEW'].includes(period.status)?'A competência está protegida. Retorne-a para Conferência para editar.':'Não há despesas visíveis elegíveis para seleção.'):'Selecionar todas as despesas visíveis e editáveis';
      selectAll.checked=Boolean(visible.length&&visible.every(row=>selected.has(String(row.id))));
      selectAll.indeterminate=Boolean(visible.some(row=>selected.has(String(row.id)))&&!selectAll.checked);
      selectAll.closest('label')?.classList.toggle('is-disabled',!visible.length);
    }
  }
  function renderExpenses(){
    const rows=filteredExpenses();const period=selectedPeriod();const selected=state.costExpenses.selected||new Set();
    $('#costExpenseLedgerContext').textContent=period?`${rows.length} lançamento(s) · ${period.period}`:`${rows.length} lançamento(s)`;
    const treatment=row=>{
      const scope=String(row.expense_scope||'SHARED').toUpperCase();
      if(scope==='DIRECT')return `<span class="status-chip good">Direta</span><span class="cost-cell-sub">${escapeHtml(row.direct_destination_label||'Curso/contexto a confirmar')}</span>`;
      if(scope==='INSTITUTIONAL')return '<span class="status-chip info">Institucional</span><span class="cost-cell-sub">Não distribui aos cursos</span>';
      const detail=row.allocation_rule_name?`${row.allocation_rule_name} · ${DRIVER_LABELS[row.allocation_driver]||row.allocation_driver||''}`:'Critério será conferido em Distribuição';
      return `<span class="status-chip attention">Compartilhada</span><span class="cost-cell-sub">${escapeHtml(detail)}</span>`;
    };
    $('#costExpensesTable').innerHTML=rows.length?rows.map(row=>`<tr class="${row.status==='VOIDED'?'is-muted':''}">
      <td class="bulk-check-column">${state.access?.canEdit&&row.editable&&row.status==='ACTIVE'?`<input type="checkbox" data-cost-expense-select="${row.id}" ${selected.has(String(row.id))?'checked':''} aria-label="Selecionar ${escapeHtml(row.description)}">`:''}</td>
      <td><strong>${escapeHtml(row.description)}</strong><span class="cost-cell-sub">${escapeHtml([KIND_LABELS[row.expense_kind]||row.expense_kind,row.expense_date,row.counterparty_name].filter(Boolean).join(' · ')||'Sem detalhe adicional')}</span>${row.status!=='ACTIVE'?expenseStatusChip(row.status):''}</td>
      <td class="value-cell"><strong>${money(row.amount)}</strong></td>
      <td>${escapeHtml(row.category_name||'—')}<span class="cost-cell-sub">${escapeHtml(row.category_code||'')}</span></td>
      <td>${escapeHtml(row.cost_center_name||'Sem setor')}<span class="cost-cell-sub">${escapeHtml(row.cost_center_code||'opcional')}</span></td>
      <td>${treatment(row)}</td>
      <td>${state.access?.canEdit&&row.editable?`<div class="table-actions"><button class="table-action" data-cost-expense-edit="${row.id}">Editar</button><button class="table-action danger" data-cost-expense-void="${row.id}">Estornar</button></div>`:'—'}</td>
    </tr>`).join(''):dpeEmptyRow(7,'Nenhuma despesa encontrada','Ajuste os filtros ou registre uma nova despesa para este mês.');
    renderSelection();
  }
  function renderCenters(){
    const rows=state.costExpenses.centers||[];
    $('#costCentersTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.code)}</strong></td><td>${escapeHtml(row.name)}</td><td>${escapeHtml(row.parent_name||'—')}</td><td>${row.usage_count||0}</td><td>${activeChip(row.active)}</td><td>${state.access?.canEdit?`<button class="table-action" data-cost-center-edit="${row.id}">Editar</button>`:''}</td></tr>`).join(''):dpeEmptyRow(6,'Nenhum setor cadastrado','Cadastre um setor somente quando precisar identificar a origem do gasto.');
  }
  function renderCategories(){
    const rows=state.costExpenses.categories||[];
    $('#costExpenseCategoriesTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.code)}</strong></td><td>${escapeHtml(row.name)}${row.parent_name?`<span class="cost-cell-sub">${escapeHtml(row.parent_name)}</span>`:''}</td><td>${row.default_rule_name?`${escapeHtml(row.default_rule_name)}<span class="cost-cell-sub">${escapeHtml(DRIVER_LABELS[row.default_driver_type]||row.default_driver_type||'')}</span>`:'<span class="status-chip attention">A definir</span>'}</td><td>${row.usage_count||0}</td><td>${activeChip(row.active)}</td><td>${state.access?.canEdit?`<button class="table-action" data-cost-category-edit="${row.id}">Editar</button>`:''}</td></tr>`).join(''):dpeEmptyRow(6,'Nenhuma categoria cadastrada','Cadastre ao menos uma categoria para começar a lançar despesas.');
  }
  function renderBatches(){
    const rows=state.costExpenses.batches||[];
    $('#costExpenseBatchesTable').innerHTML=rows.length?rows.map(row=>{const counts=row.row_counts||{};const total=Object.values(counts).reduce((sum,value)=>sum+Number(value||0),0);return `<tr><td>${escapeHtml(row.period)}</td><td>${escapeHtml(SOURCE_LABELS[row.source_type]||row.source_type)}</td><td><strong>${escapeHtml(row.source_label)}</strong><span class="cost-cell-sub">${escapeHtml(row.original_filename||row.external_key||'')}</span></td><td><span class="status-chip ${row.status==='FAILED'?'critical':row.status==='COMMITTED'?'good':row.status==='READY'?'attention':'info'}">${escapeHtml(BATCH_STATUS_LABELS[row.status]||row.status)}</span></td><td>${total}</td><td>${escapeHtml(row.created_by||'—')}</td><td><button class="table-action" data-expense-import-review="${row.id}">Revisar</button></td></tr>`}).join(''):dpeEmptyRow(7,'Nenhuma importação neste mês','Você pode importar um Excel e revisar a prévia antes de confirmar os lançamentos.');
  }
  function switchExpenseView(view='ledger'){
    const allowed=['ledger','imports','settings'];
    state.costExpenses.view=allowed.includes(view)?view:'ledger';
    document.querySelectorAll('[data-expense-panel]').forEach(panel=>{const active=panel.dataset.expensePanel===state.costExpenses.view;panel.classList.toggle('hidden',!active);panel.setAttribute('aria-hidden',active?'false':'true');});
    document.querySelectorAll('[data-expense-view]').forEach(button=>{const active=button.dataset.expenseView===state.costExpenses.view;button.classList.toggle('active',active);button.setAttribute('aria-selected',active?'true':'false');button.setAttribute('tabindex',active?'0':'-1');});
  }
  function renderImportBadge(){
    const pending=(state.costExpenses.batches||[]).filter(row=>['STAGING','READY','FAILED'].includes(row.status)).length;
    const badge=$('#expenseImportsBadge');if(!badge)return;badge.textContent=pending?String(pending):'';badge.classList.toggle('hidden',!pending);
  }

  function renderAll(){renderPeriodFilter();renderFilterOptions();renderCards();renderExpenses();renderCenters();renderCategories();renderBatches();renderImportBadge();switchExpenseView(state.costExpenses.view||'ledger');}

  async function refresh({keepPeriod=true}={}){
    const available=periods();
    if(!available.length){state.costExpenses.periodId=null;}
    else if(!keepPeriod||!state.costExpenses.periodId||!available.some(row=>String(row.id)===String(state.costExpenses.periodId))){state.costExpenses.periodId=state.costEngine?.selectedPeriodId||available[0].id;}
    const periodId=state.costExpenses.periodId;
    const [central,rules]=await Promise.all([api('/api/dpe/cost-engine/expense-central',{}, {period_id:periodId}),api('/api/dpe/cost-engine/allocation-rules',{}, {active_only:false})]);
    state.costExpenses.expenses=central.expenses||[];state.costExpenses.centers=central.cost_centers||[];state.costExpenses.categories=central.categories||[];state.costExpenses.batches=central.import_batches||[];state.costExpenses.periodOfferings=central.period_offerings||[];state.costExpenses.summary=central.summary||{};state.costExpenses.rules=rules.items||[];const validIds=new Set(state.costExpenses.expenses.map(row=>String(row.id)));state.costExpenses.selected=new Set([...state.costExpenses.selected].filter(id=>validIds.has(String(id))));state.costExpenses.loaded=true;renderAll();
  }

  function editablePeriodOptions(selected=''){
    return editablePeriods().map(row=>option(row.id,`${row.period} · ${periodLabel(row.status)}`,String(row.id)===String(selected))).join('');
  }
  function centerOptions(selected=''){
    return '<option value="">Sem centro de custo</option>'+state.costExpenses.centers.filter(row=>row.active||String(row.id)===String(selected)).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('');
  }
  function categoryOptions(selected=''){
    return '<option value="">Selecione uma categoria</option>'+state.costExpenses.categories.filter(row=>row.active||String(row.id)===String(selected)).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('');
  }
  function ruleOptions(selected=''){
    return '<option value="">Usar regra padrão da categoria / definir depois</option>'+state.costExpenses.rules.filter(row=>row.active||String(row.id)===String(selected)).map(row=>option(row.id,`${row.name} · ${DRIVER_LABELS[row.driver_type]||row.driver_type}`,String(row.id)===String(selected))).join('');
  }
  function periodOfferingOptions(selected=''){
    const rows=state.costExpenses.periodOfferings||[];
    return '<option value="">Selecione o curso/contexto</option>'+rows.map(row=>option(row.id,row.label||`Contexto ${row.id}`,String(row.id)===String(selected))).join('');
  }
  function parentCenterOptions(selected='',selfId=''){return '<option value="">Sem centro pai</option>'+state.costExpenses.centers.filter(row=>String(row.id)!==String(selfId)&&(row.active||String(row.id)===String(selected))).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('')}
  function parentCategoryOptions(selected='',selfId=''){return '<option value="">Sem categoria pai</option>'+state.costExpenses.categories.filter(row=>String(row.id)!==String(selfId)&&(row.active||String(row.id)===String(selected))).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('')}

  function expenseRuleHint(row=null,categoryId=''){
    const scope=$('#costExpenseScope')?.value||row?.expense_scope||'SHARED';
    if(scope==='DIRECT')return '<strong>Despesa direta</strong><span>O valor pertence integralmente ao curso/contexto escolhido. Não será dividido entre outros cursos.</span>';
    if(scope==='INSTITUTIONAL')return '<strong>Despesa institucional</strong><span>O valor participa do resultado institucional, mas não será distribuído nem alterará a rentabilidade dos cursos.</span>';
    if(row?.allocation_rule_name)return `<strong>Despesa compartilhada · sugestão atual: ${escapeHtml(row.allocation_rule_name)}</strong><span>Revise a divisão entre cursos na área Distribuição antes de fechar o mês.</span>`;
    const category=state.costExpenses.categories.find(item=>String(item.id)===String(categoryId));
    if(category?.default_rule_name&&category?.default_driver_type!=='DIRECT')return `<strong>Despesa compartilhada · sugestão: ${escapeHtml(category.default_rule_name)}</strong><span>O sistema prepara esse critério. Confira o efeito em Distribuição antes de fechar o mês.</span>`;
    return '<strong>Despesa compartilhada</strong><span>Salve agora e defina como o valor será dividido entre os cursos na área Distribuição.</span>';
  }
  function updateExpenseRuleHint(row=null){
    const category=$('#costExpenseCategory');const rule=$('#costExpenseRule');const hint=$('#costExpenseRuleHint');if(!category||!rule||!hint)return;
    const scope=$('#costExpenseScope')?.value||row?.expense_scope||'SHARED';
    const found=state.costExpenses.categories.find(item=>String(item.id)===String(category.value));
    if(scope==='SHARED'){
      if(found?.default_rule_id&&found?.default_driver_type!=='DIRECT')rule.value=String(found.default_rule_id);else if(!row?.allocation_rule_id||row?.allocation_driver==='DIRECT')rule.value='';
    }else rule.value='';
    hint.innerHTML=expenseRuleHint(row,category.value);
  }
  function updateExpenseScopeUI(row=null){
    const scope=$('#costExpenseScope')?.value||row?.expense_scope||'SHARED';
    const directWrap=$('#costExpenseDirectDestinationWrap');
    const direct=$('#costExpenseDirectDestination');
    if(directWrap)directWrap.classList.toggle('hidden',scope!=='DIRECT');
    if(direct)direct.required=scope==='DIRECT';
    updateExpenseRuleHint(row);
  }
  function updateExpenseTypeHelp(){
    const payroll=$('#costExpenseKind')?.value==='PAYROLL';const label=$('#costExpenseCounterpartyLabel');const help=$('#costExpenseCounterpartyHelp');if(label)label.textContent=payroll?'Professor / beneficiário':'Fornecedor / beneficiário';if(help)help.textContent=payroll?'Na folha, este nome será conferido com o cadastro de professores em Docentes.':'Opcional, mas ajuda a identificar para quem o valor foi pago.';
  }
  function openExpense(row=null){
    if(!state.access?.canEdit)return;
    if(!editablePeriods().length){showAlert('Selecione um mês em Preparação ou Conferência antes de lançar despesas.','error');return;}
    if(!state.costExpenses.categories.length){showAlert('Cadastre uma categoria de despesa antes do primeiro lançamento.','error');switchExpenseView('settings');return;}
    const periodId=row?.period_id||currentPeriodId()||editablePeriods()[0].id;
    const period=periods().find(item=>String(item.id)===String(periodId));
    const source=row?.source_type||'MANUAL';
    const scope=row?.expense_scope||'SHARED';
    modalOpen(row?'Editar despesa':'Nova despesa',period?`${period.period} · ${row?'Altere somente o que precisa ser corrigido.':'Primeiro defina quem absorve o gasto; depois preencha os dados essenciais.'}`:'Preencha os dados principais da despesa.',`<form id="costExpenseForm" class="form-grid dpe-measurement-form expense-progressive-form">
      <input type="hidden" id="costExpenseId" value="${escapeHtml(row?.id||'')}">
      <input type="hidden" id="costExpensePeriod" value="${escapeHtml(periodId)}">
      <input type="hidden" id="costExpenseRule" value="${escapeHtml(row?.allocation_rule_id||'')}">
      <input type="hidden" id="costExpenseSource" value="${escapeHtml(source)}">
      <div class="expense-form-period span-2"><span>Mês do lançamento</span><strong>${escapeHtml(period?.period||'Mês selecionado')}</strong><small>Para lançar em outro mês, altere o período no topo da DPE antes de abrir este formulário.</small></div>
      <label class="span-2"><span>Como esta despesa entra no resultado? *</span><select id="costExpenseScope" required><option value="DIRECT" ${scope==='DIRECT'?'selected':''}>Direta — pertence a um curso/contexto</option><option value="SHARED" ${scope==='SHARED'?'selected':''}>Compartilhada — será dividida entre cursos</option><option value="INSTITUTIONAL" ${scope==='INSTITUTIONAL'?'selected':''}>Institucional — não pertence a curso</option></select><small>Essa escolha define se o gasto vai diretamente para um curso, será distribuído ou ficará somente no resultado institucional.</small></label>
      <label id="costExpenseDirectDestinationWrap" class="span-2 ${scope==='DIRECT'?'':'hidden'}"><span>Curso / contexto de destino *</span><select id="costExpenseDirectDestination">${periodOfferingOptions(row?.direct_period_offering_id||'')}</select><small>O valor inteiro será atribuído a este curso/contexto.</small></label>
      <label class="span-2"><span>Descrição *</span><input id="costExpenseDescription" required maxlength="280" value="${escapeHtml(row?.description||'')}" placeholder="Ex.: manutenção preventiva do laboratório"></label>
      <label><span>Valor *</span><input id="costExpenseAmount" inputmode="decimal" required value="${escapeHtml(row?.amount??'')}" placeholder="0,00"></label>
      <label><span>Data</span><input id="costExpenseDate" type="date" value="${escapeHtml(row?.expense_date||'')}"><small>Opcional. Se informada, deve pertencer ao mês.</small></label>
      <label><span>Categoria *</span><select id="costExpenseCategory" required>${categoryOptions(row?.category_id||'')}</select><small>Classifica o gasto; para compartilhadas, pode sugerir um critério de divisão.</small></label>
      <label><span>Setor</span><select id="costExpenseCenter">${centerOptions(row?.cost_center_id||'')}</select><small>Opcional. Indica onde o gasto surgiu, não quem deve absorvê-lo.</small></label>
      <label><span>Tipo *</span><select id="costExpenseKind"><option value="GENERAL" ${row?.expense_kind==='PAYROLL'?'':'selected'}>Despesa comum</option><option value="PAYROLL" ${row?.expense_kind==='PAYROLL'?'selected':''}>Folha / pessoal</option></select></label>
      <label><span id="costExpenseCounterpartyLabel">Fornecedor / beneficiário</span><input id="costExpenseCounterparty" maxlength="240" value="${escapeHtml(row?.counterparty_name||'')}"><small id="costExpenseCounterpartyHelp">Opcional, mas ajuda a identificar para quem o valor foi pago.</small></label>
      <div id="costExpenseRuleHint" class="indicator-definition span-2 expense-rule-hint">${expenseRuleHint(row,row?.category_id||'')}</div>
      <details class="dpe-form-advanced span-2">
        <summary>Informações adicionais</summary>
        <div class="dpe-form-advanced-body two-columns">
          <label><span>Documento / referência</span><input id="costExpenseDocument" maxlength="140" value="${escapeHtml(row?.document_number||'')}"></label>
          <label><span>Origem do lançamento</span><input value="${escapeHtml(SOURCE_LABELS[source]||source)}" disabled><small>A origem é preservada automaticamente.</small></label>
          <label class="span-2"><span>Referência da origem</span><input id="costExpenseSourceReference" maxlength="220" value="${escapeHtml(row?.source_reference||'')}"></label>
          <label class="span-2"><span>Observações</span><textarea id="costExpenseNotes">${escapeHtml(row?.notes||'')}</textarea></label>
        </div>
      </details>
      <div id="costExpenseFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar despesa</button></div>
    </form>`,'DPE · DESPESA');
    const category=$('#costExpenseCategory');
    category?.addEventListener('change',()=>updateExpenseRuleHint(null));
    $('#costExpenseScope')?.addEventListener('change',()=>updateExpenseScopeUI(null));
    $('#costExpenseKind')?.addEventListener('change',updateExpenseTypeHelp);
    updateExpenseTypeHelp();
    updateExpenseScopeUI(row);
    $('#costExpenseForm').addEventListener('submit',saveExpense);
  }
  async function saveExpense(event){
    event.preventDefault();const id=$('#costExpenseId').value;const amount=$('#costExpenseAmount').value;const scope=$('#costExpenseScope').value;
    const payload={period_id:Number($('#costExpensePeriod').value),expense_date:$('#costExpenseDate').value||null,description:$('#costExpenseDescription').value,amount,expense_kind:$('#costExpenseKind').value,expense_scope:scope,direct_period_offering_id:scope==='DIRECT'&&$('#costExpenseDirectDestination').value?Number($('#costExpenseDirectDestination').value):null,counterparty_name:$('#costExpenseCounterparty').value||null,document_number:$('#costExpenseDocument').value||null,cost_center_id:$('#costExpenseCenter').value?Number($('#costExpenseCenter').value):null,category_id:Number($('#costExpenseCategory').value),allocation_rule_id:scope==='SHARED'&&$('#costExpenseRule').value?Number($('#costExpenseRule').value):null,source_type:$('#costExpenseSource').value,source_reference:$('#costExpenseSourceReference').value||null,notes:$('#costExpenseNotes').value||null};
    setLoading(true);try{const saved=await api(id?`/api/dpe/cost-engine/expenses/${id}`:'/api/dpe/cost-engine/expenses',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.costExpenses.periodId=saved.period_id;modalClose();const messages={DIRECT:'Despesa direta salva e atribuída ao curso/contexto escolhido.',SHARED:'Despesa compartilhada salva. Próximo passo: confira a divisão entre os cursos em Distribuição.',INSTITUTIONAL:'Despesa institucional salva. Ela ficará somente no resultado institucional.'};showAlert(messages[scope]||'Despesa salva.','success');await refresh();}catch(error){showFormError(error)}finally{setLoading(false)}
  }
  async function voidExpense(row){
    if(!row?.editable||!state.access?.canEdit)return;const reason=await requestDPEConfirmation({title:'Estornar despesa?',message:`A despesa “${row.description}” será estornada, mas permanecerá no histórico para auditoria.`,confirmLabel:'Estornar despesa',tone:'danger',eyebrow:'ESTORNO',reasonLabel:'Motivo do estorno *',reasonHelp:'Explique por que este lançamento não deve mais compor o mês.',reasonRequired:true});if(!reason)return;
    setLoading(true);try{await api(`/api/dpe/cost-engine/expenses/${row.id}/void`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})});showAlert('Despesa estornada. O registro foi preservado para auditoria.','success');await refresh();}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}
  }

  function openCenter(row=null){
    if(!state.access?.canEdit)return;modalOpen(row?'Editar setor':'Novo setor','Setores ajudam a responder onde o dinheiro foi gasto. Esse campo é opcional nas despesas.',`<form id="costExpenseForm" class="form-grid dpe-measurement-form">
      <input type="hidden" id="costCenterId" value="${escapeHtml(row?.id||'')}">
      <label><span>Código *</span><input id="costCenterCode" required maxlength="80" value="${escapeHtml(row?.code||'')}"></label>
      <label><span>Setor *</span><input id="costCenterName" required maxlength="180" value="${escapeHtml(row?.name||'')}"></label>
      <label class="check-field span-2"><input id="costCenterActive" type="checkbox" ${row?.active===false?'':'checked'}><span>Disponível para novos lançamentos</span></label>
      <details class="dpe-form-advanced span-2"><summary>Informações adicionais</summary><div class="dpe-form-advanced-body two-columns">
        <label><span>Setor pai</span><select id="costCenterParent">${parentCenterOptions(row?.parent_id||'',row?.id||'')}</select></label>
        <label><span>Chave de integração</span><input id="costCenterExternal" maxlength="160" value="${escapeHtml(row?.external_key||'')}"></label>
        <label class="span-2"><span>Observações</span><textarea id="costCenterNotes">${escapeHtml(row?.notes||'')}</textarea></label>
      </div></details>
      <div id="costExpenseFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar setor</button></div></form>`,'DPE · SETORES');
    $('#costExpenseForm').addEventListener('submit',saveCenter);
  }
  async function saveCenter(event){event.preventDefault();const id=$('#costCenterId').value;const payload={code:$('#costCenterCode').value,name:$('#costCenterName').value,parent_id:$('#costCenterParent').value?Number($('#costCenterParent').value):null,external_key:$('#costCenterExternal').value||null,active:$('#costCenterActive').checked,notes:$('#costCenterNotes').value||null};setLoading(true);try{await api(id?`/api/dpe/cost-engine/cost-centers/${id}`:'/api/dpe/cost-engine/cost-centers',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert('Centro de custo salvo.','success');await refresh();}catch(error){showFormError(error)}finally{setLoading(false)}}

  function openCategory(row=null){
    if(!state.access?.canEdit)return;modalOpen(row?'Editar categoria':'Nova categoria de despesa','Categorias organizam os gastos e podem sugerir automaticamente como eles devem ser distribuídos entre os cursos.',`<form id="costExpenseForm" class="form-grid dpe-measurement-form">
      <input type="hidden" id="costCategoryId" value="${escapeHtml(row?.id||'')}">
      <label><span>Código *</span><input id="costCategoryCode" required maxlength="80" value="${escapeHtml(row?.code||'')}"></label>
      <label><span>Categoria *</span><input id="costCategoryName" required maxlength="180" value="${escapeHtml(row?.name||'')}"></label>
      <label class="span-2"><span>Distribuição sugerida</span><select id="costCategoryRule">${ruleOptions(row?.default_rule_id||'')}</select><small>Você ainda poderá revisar cada despesa em Distribuição de custos.</small></label>
      <label class="check-field span-2"><input id="costCategoryActive" type="checkbox" ${row?.active===false?'':'checked'}><span>Disponível para novos lançamentos</span></label>
      <details class="dpe-form-advanced span-2"><summary>Informações adicionais</summary><div class="dpe-form-advanced-body two-columns">
        <label class="span-2"><span>Categoria pai</span><select id="costCategoryParent">${parentCategoryOptions(row?.parent_id||'',row?.id||'')}</select></label>
        <label class="span-2"><span>Observações</span><textarea id="costCategoryNotes">${escapeHtml(row?.notes||'')}</textarea></label>
      </div></details>
      <div id="costExpenseFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar categoria</button></div></form>`,'DPE · CATEGORIAS');
    $('#costExpenseForm').addEventListener('submit',saveCategory);
  }
  async function saveCategory(event){event.preventDefault();const id=$('#costCategoryId').value;const payload={code:$('#costCategoryCode').value,name:$('#costCategoryName').value,parent_id:$('#costCategoryParent').value?Number($('#costCategoryParent').value):null,default_rule_id:$('#costCategoryRule').value?Number($('#costCategoryRule').value):null,active:$('#costCategoryActive').checked,notes:$('#costCategoryNotes').value||null};setLoading(true);try{await api(id?`/api/dpe/cost-engine/expense-categories/${id}`:'/api/dpe/cost-engine/expense-categories',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert('Categoria de despesa salva.','success');await refresh();}catch(error){showFormError(error)}finally{setLoading(false)}}

  function openBatch(){
    if(!state.access?.canEdit)return;if(!editablePeriods().length){showAlert('Selecione um mês editável antes de preparar uma entrada.','error');return;}
    modalOpen('Preparar entrada de despesas','Use esta etapa quando os gastos chegarem por arquivo, API, requisição ou outra fonte. Nada será contabilizado até a conferência.',`<form id="costExpenseForm" class="form-grid dpe-measurement-form">
      <label><span>Mês *</span><select id="costBatchPeriod">${editablePeriodOptions(currentPeriodId()||editablePeriods()[0].id)}</select></label><label><span>Origem *</span><select id="costBatchSource"><option value="EXCEL">Excel</option><option value="API">API</option><option value="REQUEST">Requisição</option><option value="OTHER">Outra</option></select></label>
      <label class="span-2"><span>Identificação *</span><input id="costBatchLabel" required maxlength="220" placeholder="Ex.: despesas da contabilidade - setembro/2026"></label>
      <label class="span-2"><span>Nome do arquivo</span><input id="costBatchFilename" maxlength="255" placeholder="Opcional"></label>
      <details class="dpe-form-advanced span-2"><summary>Informações adicionais</summary><div class="dpe-form-advanced-body two-columns">
        <label class="span-2"><span>Chave de integração</span><input id="costBatchExternal" maxlength="180"></label>
        <label class="span-2"><span>Observações</span><textarea id="costBatchNotes"></textarea></label>
      </div></details>
      <div class="indicator-definition span-2"><strong>Nada entra nos números automaticamente</strong><span>Esta etapa apenas registra o que foi recebido. A despesa oficial só nasce depois da validação.</span></div>
      <div id="costExpenseFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Preparar entrada</button></div></form>`,'DPE · IMPORTAÇÕES');
    $('#costExpenseForm').addEventListener('submit',saveBatch);
  }
  async function saveBatch(event){event.preventDefault();const payload={period_id:Number($('#costBatchPeriod').value),source_type:$('#costBatchSource').value,source_label:$('#costBatchLabel').value,original_filename:$('#costBatchFilename').value||null,external_key:$('#costBatchExternal').value||null,notes:$('#costBatchNotes').value||null};setLoading(true);try{const row=await api('/api/dpe/cost-engine/expense-imports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.costExpenses.periodId=row.period_id;modalClose();showAlert('Entrada preparada para conferência, sem alterar as despesas oficiais.','success');await refresh();}catch(error){showFormError(error)}finally{setLoading(false)}}

  function openImportPreview(result){
    state.costExpenses.lastImportPreview=result;const batch=result.batch||{};const rows=result.rows||[];const summary=batch.summary||{};
    modalOpen('Previa da importacao',`${batch.original_filename||batch.source_label||'Arquivo'} · ${batch.period||''}`,`<div class="expense-import-preview"><div class="metric-grid executive dpe-metric-grid"><article class="metric-card"><span class="metric-label">Linhas validas</span><strong class="metric-value">${summary.valid_count||0}</strong></article><article class="metric-card"><span class="metric-label">Com erro / duplicadas</span><strong class="metric-value">${summary.error_count||0}</strong></article><article class="metric-card"><span class="metric-label">Valor valido</span><strong class="metric-value">${money(summary.valid_amount||0)}</strong></article></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Linha</th><th>Despesa</th><th>Valor</th><th>Categoria</th><th>Setor</th><th>Situacao</th></tr></thead><tbody>${rows.map(row=>{const n=row.normalized_data||{},errors=row.errors||[];return `<tr><td>${row.row_number}</td><td>${escapeHtml(n.description||row.raw_data?.description||'—')}</td><td>${n.amount!==undefined?money(n.amount):'—'}</td><td>${escapeHtml(n.category_name||row.raw_data?.category||'—')}</td><td>${escapeHtml(n.cost_center_name||row.raw_data?.cost_center||'—')}</td><td>${row.status==='VALID'?'<span class="status-chip good">Valida</span>':`<span class="status-chip critical">Bloqueada</span><span class="cost-cell-sub">${escapeHtml(errors.map(item=>item.error||item).join(' · '))}</span>`}</td></tr>`}).join('')}</tbody></table></div><div class="indicator-definition"><strong>${result.can_commit?'Arquivo pronto para confirmar':'Nada sera importado enquanto houver erros'}</strong><span>${result.can_commit?'A confirmacao cria as despesas oficiais em uma unica transacao.':'Corrija a planilha e envie novamente. Linhas invalidas nao sao ignoradas silenciosamente.'}</span></div><div id="costExpenseFormErrors" class="form-errors hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Fechar</button>${result.can_commit&&batch.status!=='COMMITTED'?`<button type="button" class="button primary" id="commitExpenseImport" data-batch-id="${batch.id}">Confirmar importacao</button>`:''}</div></div>`,'DPE · IMPORTACAO EXCEL');
    $('#commitExpenseImport')?.addEventListener('click',async event=>{setLoading(true);try{const out=await api(`/api/dpe/cost-engine/expense-imports/${event.currentTarget.dataset.batchId}/commit`,{method:'POST'});modalClose();showAlert(`${out.created} despesa(s) importada(s) com sucesso.`,'success');await refresh();}catch(error){showFormError(error)}finally{setLoading(false)}});
  }
  async function uploadExpenseExcel(file){if(!file)return;const period=selectedPeriod();if(!period||!['DRAFT','REVIEW'].includes(period.status)){showAlert('Selecione um mes em Preparacao ou Conferencia antes de importar.','error');return}const form=new FormData();form.append('arquivo',file);setLoading(true);try{const result=await api(`/api/dpe/cost-engine/periods/${period.id}/expense-imports/excel/preview`,{method:'POST',body:form});await refresh();openImportPreview(result);}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false);const input=$('#costExpenseExcelFile');if(input)input.value='';}}
  async function reviewImport(batchId){setLoading(true);try{const [rowPayload]=await Promise.all([api(`/api/dpe/cost-engine/expense-imports/${batchId}/rows`)]);const batch=(state.costExpenses.batches||[]).find(item=>String(item.id)===String(batchId));if(!batch)return;openImportPreview({batch,rows:rowPayload.items||[],can_commit:batch.status==='READY'});}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}}
  function openBulkClassify(){
    const ids=[...(state.costExpenses.selected||new Set())];if(!ids.length)return;
    modalOpen('Classificar despesas em massa',`${ids.length} despesa(s) selecionada(s). Ajuste somente o que for comum ao grupo.`,`<form id="costExpenseForm" class="form-grid dpe-measurement-form">
      <label><span>Tratamento</span><select id="bulkExpenseScope"><option value="__UNCHANGED__">Manter como está</option><option value="SHARED">Compartilhada — distribuir entre cursos</option><option value="INSTITUTIONAL">Institucional — não distribuir aos cursos</option></select><small>Despesa direta não pode ser aplicada em massa porque exige escolher um curso/contexto específico.</small></label>
      <label><span>Categoria</span><select id="bulkExpenseCategory"><option value="__UNCHANGED__">Manter como está</option>${state.costExpenses.categories.filter(row=>row.active).map(row=>option(row.id,`${row.name} · ${row.code}`)).join('')}</select></label>
      <label><span>Setor</span><select id="bulkExpenseCenter"><option value="__UNCHANGED__">Manter como está</option><option value="">Remover setor</option>${state.costExpenses.centers.filter(row=>row.active).map(row=>option(row.id,`${row.name} · ${row.code}`)).join('')}</select></label>
      <div class="indicator-definition span-2"><strong>Alteração controlada</strong><span>Institucionais deixam de ir para Distribuição. Compartilhadas seguem para revisão do critério. Trocar categoria não transforma automaticamente uma despesa em direta.</span></div>
      <div id="costExpenseFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Aplicar a ${ids.length} despesa(s)</button></div>
    </form>`,'DPE · EDIÇÃO EM MASSA');
    $('#costExpenseForm').addEventListener('submit',async event=>{event.preventDefault();const category=$('#bulkExpenseCategory').value,center=$('#bulkExpenseCenter').value,scope=$('#bulkExpenseScope').value;const payload={expense_ids:ids};if(category!=='__UNCHANGED__')payload.category_id=category?Number(category):null;if(center!=='__UNCHANGED__')payload.cost_center_id=center?Number(center):null;if(scope!=='__UNCHANGED__')payload.expense_scope=scope;if(category==='__UNCHANGED__'&&center==='__UNCHANGED__'&&scope==='__UNCHANGED__'){showFormError(new Error('Escolha ao menos uma alteração.'));return}setLoading(true);try{const out=await api(`/api/dpe/cost-engine/periods/${currentPeriodId()}/expenses/bulk-classify`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.costExpenses.selected.clear();modalClose();showAlert(`${out.updated_count} despesa(s) atualizada(s).`,'success');await refresh();}catch(error){showFormError(error)}finally{setLoading(false)}});
  }
  function bind(){
    $('#newCostExpense')?.addEventListener('click',()=>openExpense());$('#newCostCenter')?.addEventListener('click',()=>openCenter());$('#newExpenseCategory')?.addEventListener('click',()=>openCategory());$('#newCostExpenseBatch')?.addEventListener('click',openBatch);$('#uploadCostExpenseExcel')?.addEventListener('click',()=>$('#costExpenseExcelFile')?.click());$('#costExpenseExcelFile')?.addEventListener('change',event=>uploadExpenseExcel(event.target.files?.[0]));$('#bulkClassifyExpenses')?.addEventListener('click',openBulkClassify);$('#selectAllCostExpenses')?.addEventListener('change',event=>{if(event.target.disabled)return;filteredExpenses().filter(row=>row.status==='ACTIVE'&&row.editable).forEach(row=>event.target.checked?state.costExpenses.selected.add(String(row.id)):state.costExpenses.selected.delete(String(row.id)));renderExpenses();});
    document.querySelectorAll('[data-expense-view]').forEach(button=>button.addEventListener('click',()=>switchExpenseView(button.dataset.expenseView)));
    $('#costExpensePeriodFilter')?.addEventListener('change',async event=>{state.costExpenses.periodId=Number(event.target.value)||null;state.costExpenses.selected.clear();setLoading(true);try{await refresh();}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}});
    ['#costExpenseKindFilter','#costExpenseSourceFilter','#costExpenseStatusFilter','#costExpenseCategoryFilter','#costExpenseCenterFilter','#costExpenseScopeFilter'].forEach(selector=>$(selector)?.addEventListener('change',renderExpenses));$('#costExpenseSearch')?.addEventListener('input',renderExpenses);
    document.addEventListener('click',event=>{
      const selectedBox=event.target.closest('[data-cost-expense-select]');if(selectedBox){selectedBox.checked?state.costExpenses.selected.add(String(selectedBox.dataset.costExpenseSelect)):state.costExpenses.selected.delete(String(selectedBox.dataset.costExpenseSelect));renderSelection();return;}
      const importReview=event.target.closest('[data-expense-import-review]');if(importReview){reviewImport(importReview.dataset.expenseImportReview);return;}
      const edit=event.target.closest('[data-cost-expense-edit]');if(edit){const row=state.costExpenses.expenses.find(item=>String(item.id)===String(edit.dataset.costExpenseEdit));if(row)openExpense(row);return;}
      const voidButton=event.target.closest('[data-cost-expense-void]');if(voidButton){const row=state.costExpenses.expenses.find(item=>String(item.id)===String(voidButton.dataset.costExpenseVoid));if(row)voidExpense(row);return;}
      const center=event.target.closest('[data-cost-center-edit]');if(center){const row=state.costExpenses.centers.find(item=>String(item.id)===String(center.dataset.costCenterEdit));if(row)openCenter(row);return;}
      const category=event.target.closest('[data-cost-category-edit]');if(category){const row=state.costExpenses.categories.find(item=>String(item.id)===String(category.dataset.costCategoryEdit));if(row)openCategory(row);return;}
    });
  }
  async function initialize(){bind();try{await refresh({keepPeriod:false});}catch(error){showAlert(`Central de Despesas: ${error.message}`,'error',0)}}
  window.initializeDPECostExpenses=initialize;
  window.refreshDPECostExpenses=refresh;
  window.openDPECostExpense=openExpense;
})();
