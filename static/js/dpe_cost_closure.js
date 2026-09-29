(function(){
  if(!state.costClosure){state.costClosure={periodId:null,data:null,overview:null,loaded:false};}

  const PERIOD_LABELS={DRAFT:'Preparação',REVIEW:'Conferência',CALCULATED:'Calculada',CLOSED:'Fechada'};
  const EVENT_LABELS={CLOSED:'Fechamento',REOPENED:'Reabertura'};
  const WORKFLOW_LABELS={
    COMPETENCE:'Cursos do mês',
    EXPENSES:'Despesas',
    TEACHING:'Docentes e folha',
    ECONOMICS:'Alunos e receitas',
    ALLOCATION:'Distribuição de custos',
    GOVERNANCE:'Alertas revisados'
  };
  const CHECK_LABELS={
    PERIOD_STATUS:'Etapa do mês',
    OFFERINGS:'Cursos do mês',
    EXPENSES:'Despesas registradas',
    EXPENSE_CONFIGURATION:'Despesas prontas para distribuição',
    ACTIVE_STUDENTS:'Alunos ativos',
    NET_REVENUE:'Receitas dos cursos',
    TICKET_BASIS:'Alunos pagantes',
    ESTIMATED_REVENUE:'Receitas estimadas',
    OFFICIAL_RUN:'Cálculo atualizado',
    ALLOCATION_RECONCILIATION:'Custos distribuídos',
    PENDING_STAGING:'Importações pendentes',
    TEACHING_RECONCILIATION:'Docentes reconciliados',
    ECONOMIC_RESULT:'Resultado econômico calculado',
    ANOMALY_REVIEW:'Alertas e anomalias revisados'
  };
  const ACTION_LABELS={
    open_period:'Abertura da competência',update_period:'Alteração da competência',refresh_period_offerings:'Atualização dos cursos',set_period_offering:'Inclusão/exclusão de curso',
    create:'Criação',update:'Alteração',void:'Estorno',import_commit:'Importação confirmada',bulk_classify:'Classificação em massa',
    upsert:'Atualização de receita',bulk_upsert:'Receitas em massa',create_policy:'Criação de política',update_policy:'Alteração de política',configure_allocation:'Configuração de distribuição',bulk_apply_policy:'Políticas em massa',calculate_allocation:'Cálculo de rateio',officialize_allocation:'Oficialização do rateio',
    link_payroll:'Conciliação de folha',unlink_payroll:'Desvinculação de folha',copy_revenues:'Cópia de receitas',copy_teaching:'Cópia do quadro docente',generate_recurring:'Geração de recorrentes',review_warning:'Revisão de alerta',return_review:'Retorno para conferência',close:'Fechamento',reopen:'Reabertura'
  };
  const ENTITY_LABELS={
    dpe_cost_period:'Competência',dpe_period_offerings:'Cursos do mês',dpe_period_offering:'Curso do mês',dpe_expense:'Despesa',dpe_expense_import:'Importação',dpe_expense_batch:'Despesas em massa',dpe_economics:'Receita / alunos',dpe_economics_batch:'Receitas em massa',dpe_teaching_activity:'Atividade docente',dpe_payroll_link:'Folha docente',dpe_expense_allocation:'Distribuição da despesa',dpe_allocation_policy:'Política de distribuição',dpe_allocation_batch:'Distribuição em massa',dpe_allocation_run:'Cálculo de rateio',dpe_productivity:'Produtividade',dpe_governance_warning:'Alerta de governança'
  };

  function data(){return state.costClosure.data||{periods:[],events:[],audit_trail:[],event_counts:{},checklist:null};}
  function overview(){return state.costClosure.overview||{summary:{},workflow:[],issues:[],next_action:null};}
  function period(){return data().selected_period||overview().selected_period||null;}
  function checklist(){return data().checklist||overview().checklist||{checks:[],summary:{}};}
  function currentPeriodId(){return state.costClosure.periodId||period()?.id||null;}
  function money(value){return Number(value||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:2,maximumFractionDigits:2});}
  function dateTime(value){if(!value)return '—';try{return new Date(value).toLocaleString('pt-BR');}catch{return value;}}
  function monthLabel(value){
    if(!value)return 'mês selecionado';
    const [year,month]=String(value).split('-').map(Number);
    if(!year||!month)return value;
    const label=new Intl.DateTimeFormat('pt-BR',{month:'long',year:'numeric'}).format(new Date(year,month-1,1));
    return label.charAt(0).toUpperCase()+label.slice(1);
  }
  function chip(status){
    const map={PASS:['good','Pronto'],WARNING:['attention','Atenção'],BLOCKER:['critical','Pendente'],CLOSED:['good','Fechado'],CALCULATED:['good','Calculado'],REVIEW:['attention','Em conferência'],DRAFT:['info','Em preparação']};
    const item=map[status]||['info',status||'—'];
    return `<span class="status-chip ${item[0]}">${escapeHtml(item[1])}</span>`;
  }
  function modalOpen(title,subtitle,body,eyebrow='DPE · FECHAMENTO'){
    $('#costEngineModalEyebrow').textContent=eyebrow;
    $('#costEngineModalTitle').textContent=title;
    $('#costEngineModalSubtitle').textContent=subtitle||'';
    $('#costEngineModalBody').innerHTML=body;
    openDPEModal('costEngineModal');
  }
  function modalClose(){closeDPEModal('costEngineModal');}
  function formError(error){const detail=error?.payload?.detail;const fields=detail?.campos||{};return [error.message,...Object.entries(fields).map(([key,value])=>`${key}: ${value}`)].filter(Boolean).join('\n');}
  function showFormError(error){const box=$('#closureFormErrors');if(box){focusInlineError(box,formError(error));}else showAlert(error.message,'error',0);}

  function renderPeriodFilter(){
    const el=$('#closurePeriodFilter');if(!el)return;
    const rows=data().periods||[];
    el.innerHTML=rows.length?rows.map(row=>option(row.id,`${row.period} · ${PERIOD_LABELS[row.status]||row.status}`,String(row.id)===String(currentPeriodId()))).join(''):'<option value="">Nenhum mês</option>';
    if(currentPeriodId())el.value=String(currentPeriodId());
    const p=period();
    $('#closureContext').textContent=p?`${monthLabel(p.period)} · ${PERIOD_LABELS[p.status]||p.status}`:'Selecione um mês';
  }

  function workflowRows(){
    return (overview().workflow||[]).filter(row=>row.code!=='CLOSE');
  }

  function issueCount(){return (overview().issues||[]).filter(row=>row.status==='BLOCKER').length;}
  function warningCount(){return (overview().issues||[]).filter(row=>row.status==='WARNING').length;}

  function renderDecision(){
    const p=period();
    const summary=checklist().summary||{};
    const hero=$('#closureDecisionHero');
    if(!hero)return;
    hero.classList.remove('is-ready','is-pending','is-closed');
    const title=$('#closureDecisionTitle'),text=$('#closureDecisionText'),eyebrow=$('#closureDecisionEyebrow'),meta=$('#closureDecisionMeta');
    if(!p){
      hero.classList.add('is-pending');eyebrow.textContent='Situação do mês';title.textContent='Nenhum mês selecionado';text.textContent='Escolha um mês no topo da DPE para verificar o fechamento.';meta.innerHTML='';return;
    }
    const label=monthLabel(p.period);
    const blockers=issueCount();
    const warnings=warningCount();
    const done=workflowRows().filter(row=>row.complete).length;
    const total=workflowRows().length;
    if(p.status==='CLOSED'){
      hero.classList.add('is-closed');eyebrow.textContent='Mês encerrado';title.textContent=`${label} está fechado`;
      text.textContent='Os dados deste mês estão protegidos. Reabra somente se houver uma correção necessária.';
      meta.innerHTML=`<span>${done}/${total} etapas concluídas</span><span>${data().event_counts?.closed||0} fechamento(s)</span><span>${data().event_counts?.reopened||0} reabertura(s)</span>`;
      return;
    }
    if(summary.can_close){
      hero.classList.add('is-ready');eyebrow.textContent='Pronto para concluir';title.textContent=`Tudo pronto para fechar ${label}`;
      text.textContent=warnings?`As etapas obrigatórias estão concluídas. Existem ${warnings} alerta(s) não bloqueante(s), que ficarão registrados na auditoria.`:'As etapas obrigatórias estão concluídas e o mês pode ser fechado com segurança.';
      meta.innerHTML=`<span>${done}/${total} etapas concluídas</span><span>${warnings} alerta(s)</span><span>Distribuição conciliada</span>`;
    }else{
      hero.classList.add('is-pending');eyebrow.textContent='Ainda há trabalho a concluir';
      const count=Math.max(1,blockers);
      title.textContent=`${label} ainda precisa de ${count} ajuste${count===1?'':'s'}`;
      const next=overview().next_action;
      text.textContent=next?.detail||'Resolva as pendências abaixo antes de fechar o mês.';
      meta.innerHTML=`<span>${done}/${total} etapas concluídas</span><span>${blockers} pendência(s)</span><span>${warnings} alerta(s)</span>`;
    }
  }

  function workflowAction(row){
    const map={
      COMPETENCE:['catalogo','Revisar cursos'],
      EXPENSES:['central-despesas','Revisar despesas'],
      TEACHING:['docencia','Revisar docentes'],
      ECONOMICS:['economia','Completar dados'],
      ALLOCATION:['rateio','Revisar distribuição'],
      GOVERNANCE:['fechamento','Revisar alertas']
    };
    return map[row.code]||[row.section||'fechamento','Resolver'];
  }

  function renderReadiness(){
    const rows=workflowRows();
    const done=rows.filter(row=>row.complete).length;
    $('#closureReadinessContext').textContent=rows.length?`${done} de ${rows.length} prontos`:'';
    const root=$('#closureReadinessGrid');if(!root)return;
    if(!rows.length){root.innerHTML='<div class="cost-engine-empty"><strong>Sem etapas para verificar</strong><span>Escolha um mês para iniciar.</span></div>';return;}
    root.innerHTML=rows.map(row=>{
      const [section,action]=workflowAction(row);
      const cls=row.complete?'is-ready':(row.status==='ATTENTION'?'is-warning':'is-pending');
      return `<article class="closure-readiness-card ${cls}">
        <div class="closure-readiness-top"><span class="closure-readiness-index">${escapeHtml(String(rows.indexOf(row)+1))}</span>${chip(row.complete?'PASS':(row.status==='ATTENTION'?'WARNING':'BLOCKER'))}</div>
        <div class="closure-readiness-copy"><strong>${escapeHtml(WORKFLOW_LABELS[row.code]||row.label)}</strong><span>${escapeHtml(row.detail||'')}</span></div>
        ${row.complete?'':'<button type="button" class="button secondary compact" data-closure-go="'+escapeHtml(section)+'" data-closure-code="'+escapeHtml(row.code)+'">'+escapeHtml(action)+'</button>'}
      </article>`;
    }).join('');
  }

  function renderAttention(){
    const issues=overview().issues||[];
    const root=$('#closureAttentionList');if(!root)return;
    const blockers=issues.filter(row=>row.status==='BLOCKER').length;
    const warnings=issues.filter(row=>row.status==='WARNING').length;
    $('#closureAttentionContext').textContent=issues.length?`${blockers} pendência(s) · ${warnings} alerta(s)`:'Tudo certo';
    $('#closureAttentionTitle').textContent=issues.length?'O que precisa da sua atenção':'Nenhuma pendência para resolver';
    if(!issues.length){root.innerHTML='<div class="closure-all-clear"><span class="closure-all-clear-icon">✓</span><div><strong>Não há pendências abertas</strong><span>As etapas obrigatórias do mês estão conferidas.</span></div></div>';return;}
    root.innerHTML=issues.map(issue=>`<div class="closure-attention-item ${issue.status==='WARNING'?'is-warning':'is-blocker'}">
      <div class="closure-attention-status">${chip(issue.status)}</div>
      <div class="closure-attention-copy"><strong>${escapeHtml(issue.title||issue.label||'Revisar')}</strong><span>${escapeHtml(issue.detail||'')}</span></div>
      <button type="button" class="button secondary compact" data-closure-go="${escapeHtml(issue.section||'fechamento')}" data-closure-code="${escapeHtml(issue.code||'')}">${escapeHtml(issue.action_label||'Resolver')}</button>
    </div>`).join('');
  }

  function renderChecklist(){
    const rows=checklist().checks||[],summary=checklist().summary||{};
    $('#closureChecklistContext').textContent=rows.length?`${summary.pass_count||0} prontos · ${summary.warning_count||0} alertas · ${summary.blocker_count||0} bloqueios`:'';
    $('#closureChecklist').innerHTML=rows.length?rows.map(row=>`<div class="closure-check closure-check-${String(row.status||'').toLowerCase()}"><div class="closure-check-status">${chip(row.status)}</div><div><strong>${escapeHtml(CHECK_LABELS[row.code]||row.label)}</strong><span>${escapeHtml(row.detail)}</span></div></div>`).join(''):'<div class="cost-engine-empty compact"><strong>Sem verificações</strong><span>Selecione um mês para avaliar o fechamento.</span></div>';
  }

  function renderRun(){
    const run=data().official_run,root=$('#closureRunDetail'),badge=$('#closureRunBadge');if(!root||!badge)return;
    if(!run){badge.textContent='cálculo não confirmado';root.innerHTML='<div class="cost-engine-empty"><strong>A distribuição ainda não foi oficializada</strong><span>Conclua a Distribuição de custos e confirme o cálculo atualizado antes de fechar o mês.</span><button type="button" class="button secondary compact" data-closure-go="rateio" data-closure-code="OFFICIAL_RUN">Ir para distribuição</button></div>';return;}
    badge.textContent=`v${run.run_number} · ${run.current?'atual':'desatualizada'}`;
    root.innerHTML=`<div class="closure-run-grid"><div><span>Atualização</span><strong>#${run.run_number}</strong></div><div><span>Situação</span><strong>${run.current?'Atual':'Precisa recalcular'}</strong></div><div><span>Despesas</span><strong>${money(run.expense_total)}</strong></div><div><span>Distribuído</span><strong>${money(run.allocated_total)}</strong></div><div><span>Falta distribuir</span><strong>${money(run.unallocated_total)}</strong></div><div><span>Oficializado em</span><strong>${escapeHtml(dateTime(run.official_at))}</strong></div></div><div class="closure-run-note ${run.current?'is-current':'is-stale'}"><strong>${run.current?'Cálculo atualizado':'Os dados mudaram'}</strong><span>${run.current?'O cálculo oficial corresponde aos dados atuais do mês.':'Recalcule e oficialize uma nova versão antes de fechar.'}</span></div>`;
  }

  function renderEvents(){
    const rows=data().events||[];$('#closureEventContext').textContent=`${rows.length} evento(s)`;
    $('#closureEventsTable').innerHTML=rows.length?rows.map(row=>`<tr><td>${escapeHtml(dateTime(row.created_at))}</td><td><strong>${escapeHtml(EVENT_LABELS[row.event_type]||row.event_type)}</strong></td><td>${escapeHtml(PERIOD_LABELS[row.from_status]||row.from_status)} → ${escapeHtml(PERIOD_LABELS[row.to_status]||row.to_status)}</td><td>${row.allocation_run_number?`v${row.allocation_run_number}`:'—'}</td><td>${escapeHtml(row.created_by||'—')}</td><td class="component-cell">${escapeHtml(row.reason||'—')}</td></tr>`).join(''):dpeEmptyRow(6,'Nenhum evento de fechamento','Fechamentos e reaberturas aparecerão aqui quando ocorrerem.');
  }

  function auditSummary(row){
    const meta=row.metadata||{},before=row.before||{},after=row.after||{};
    if(meta.reason)return `Motivo: ${meta.reason}`;
    if(meta.note)return `Revisão: ${meta.note}`;
    if(before.status||after.status)return `${before.status||'—'} → ${after.status||'—'}`;
    if(before.period_status||after.period_status)return `${before.period_status||'—'} → ${after.period_status||'—'}`;
    if(meta.updated_count!=null)return `${meta.updated_count} registro(s) atualizado(s)`;
    if(meta.applied_count!=null)return `${meta.applied_count} política(s) aplicada(s)`;
    if(after.created_count!=null)return `${after.created_count} item(ns) criado(s)`;
    if(after.copied!=null)return `${after.copied} item(ns) copiado(s)`;
    if(after.run_number!=null)return `Versão v${after.run_number} · ${money(after.allocated_total||0)} distribuído`;
    if(after.amount!=null&&before.amount!=null&&Number(after.amount)!==Number(before.amount))return `${money(before.amount)} → ${money(after.amount)}`;
    if(after.description)return after.description;
    if(meta.source_period)return `Origem: ${meta.source_period}`;
    return 'Alteração registrada com valores anterior e novo disponíveis na auditoria.';
  }

  function renderAudit(){
    const rows=data().audit_trail||[];
    const ctx=$('#closureAuditContext'),table=$('#closureAuditTable');if(!table)return;
    if(ctx)ctx.textContent=`${rows.length} registro(s)`;
    table.innerHTML=rows.length?rows.map(row=>`<tr>
      <td>${escapeHtml(dateTime(row.created_at))}</td>
      <td><strong>${escapeHtml(ACTION_LABELS[row.action]||row.action||'Operação')}</strong></td>
      <td>${escapeHtml(ENTITY_LABELS[row.entity]||row.entity||'DPE')}${row.entity_id?` <span class="muted">#${escapeHtml(row.entity_id)}</span>`:''}</td>
      <td>${escapeHtml(row.user_email||'—')}</td>
      <td class="component-cell">${escapeHtml(auditSummary(row))}</td>
    </tr>`).join(''):dpeEmptyRow(5,'Nenhuma operação auditável registrada','As alterações críticas do mês aparecerão aqui com usuário, data e contexto.');
  }

  function renderActions(){
    const p=period(),s=checklist().summary||{},canWrite=Boolean(state.access?.canEdit&&data().can_write);
    const close=$('#closeCostPeriod'),reopen=$('#reopenCostPeriod'),returnReview=$('#returnReviewPeriod'),resolve=$('#closureResolveNext');
    if(close){close.classList.toggle('hidden',!(canWrite&&s.can_close));close.disabled=!s.can_close;}
    if(reopen){reopen.classList.toggle('hidden',!(canWrite&&s.can_reopen));reopen.disabled=!s.can_reopen;}
    if(returnReview){const show=Boolean(canWrite&&p?.status==='CALCULATED');returnReview.classList.toggle('hidden',!show);returnReview.disabled=!show;}
    const next=overview().next_action;
    const showResolve=Boolean(p&&p.status!=='CLOSED'&&!s.can_close&&next&&next.section&&next.section!=='fechamento');
    if(resolve){
      const nextCode={docencia:'TEACHING',economia:'ECONOMICS','central-despesas':'EXPENSES',rateio:'ALLOCATION',competencias:'COMPETENCE',catalogo:'COMPETENCE'}[next?.section]||'NEXT';
      resolve.classList.toggle('hidden',!showResolve);resolve.dataset.closureGo=showResolve?next.section:'';resolve.dataset.closureCode=nextCode;resolve.textContent=next?.label||'Resolver próxima pendência';
    }
  }

  function renderAll(){renderPeriodFilter();renderDecision();renderReadiness();renderAttention();renderChecklist();renderRun();renderEvents();renderAudit();renderActions();applyAccess();}

  async function refresh({periodId=null}={}){
    const pid=periodId||state.costClosure.periodId||state.costEngine?.selectedPeriodId||null;
    const params=pid?{period_id:pid}:{};
    const [closurePayload,overviewPayload]=await Promise.all([
      api('/api/dpe/cost-engine/closure-central',{},params),
      api('/api/dpe/cost-engine/v2-overview',{},params)
    ]);
    state.costClosure.data=closurePayload;state.costClosure.overview=overviewPayload;state.costClosure.periodId=closurePayload.selected_period?.id||overviewPayload.selected_period?.id||null;state.costClosure.loaded=true;renderAll();return closurePayload;
  }

  async function refreshRelated(periodId){
    const jobs=[];
    if(typeof window.refreshDPECostEngine==='function')jobs.push(window.refreshDPECostEngine({preservePeriod:true}));
    if(typeof window.refreshDPECostExpenses==='function')jobs.push(window.refreshDPECostExpenses({keepPeriod:true}));
    if(typeof window.refreshDPECostTeaching==='function')jobs.push(window.refreshDPECostTeaching({keepPeriod:true}));
    if(typeof window.refreshDPECostAllocation==='function')jobs.push(window.refreshDPECostAllocation({periodId,runId:null}));
    if(typeof window.refreshDPECostEconomics==='function')jobs.push(window.refreshDPECostEconomics({periodId}));
    if(typeof window.refreshDPEV2==='function')jobs.push(window.refreshDPEV2({periodId}));
    await Promise.allSettled(jobs);
  }

  function issueSubView(code){
    if(code==='PENDING_STAGING')return ['expense','imports'];
    if(['ACTIVE_STUDENTS','NET_REVENUE','TICKET_BASIS','ESTIMATED_REVENUE','ECONOMICS'].includes(code))return ['economics','data'];
    if(['PAYROLL_RECONCILIATION','TEACHING','TEACHING_RECONCILIATION'].includes(code))return ['teaching','payroll'];
    if(code==='EXPENSES')return ['expense','ledger'];
    return null;
  }

  async function goToResolution(section,code){
    if(code==='GOVERNANCE'||code==='ANOMALY_REVIEW'){openGovernanceReview();return;}
    let target=section||'fechamento';
    if(code==='COMPETENCE'||code==='OFFERINGS')target='catalogo';
    if(typeof navigate==='function')await navigate(target);
    else document.querySelector(`.nav-item[data-section="${target}"]`)?.click();
    window.setTimeout(()=>{
      const sub=issueSubView(code);
      if(!sub)return;
      if(sub[0]==='expense')document.querySelector(`[data-expense-view="${sub[1]}"]`)?.click();
      if(sub[0]==='economics')document.querySelector(`[data-economics-view="${sub[1]}"]`)?.click();
      if(sub[0]==='teaching')document.querySelector(`[data-teaching-view="${sub[1]}"]`)?.click();
    },0);
  }

  function openClose(){
    const p=period(),summary=checklist().summary||{};if(!p||!summary.can_close)return;
    const warnings=overview().issues?.filter(row=>row.status==='WARNING')||[];
    const warningText=warnings.length?`Existem ${warnings.length} alerta(s) não bloqueante(s). Eles continuarão visíveis no histórico do fechamento.`:'Não existem alertas pendentes.';
    modalOpen('Fechar mês',`${monthLabel(p.period)} · depois de fechar, os dados ficam protegidos até uma reabertura formal.`,`<form id="closureCloseForm" class="form-grid dpe-measurement-form">
      <div class="span-2 closure-confirm-summary"><strong>Tudo pronto para concluir</strong><span>${escapeHtml(warningText)} O cálculo oficial atual será registrado junto ao fechamento.</span></div>
      <label class="span-2"><span>Observação do fechamento</span><textarea id="closureCloseNote" rows="4" maxlength="2000" placeholder="Opcional: registre alguma ressalva ou contexto útil para auditoria."></textarea></label>
      <label class="check-field span-2"><input id="closureCloseConfirm" type="checkbox" required><span>Confirmo que revisei este mês e desejo proteger seus dados contra alterações.</span></label>
      <div id="closureFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Fechar ${escapeHtml(monthLabel(p.period))}</button></div>
    </form>`);
    $('#closureCloseForm').addEventListener('submit',async event=>{event.preventDefault();if(!$('#closureCloseConfirm').checked)return;setLoading(true);try{await api(`/api/dpe/cost-engine/periods/${p.id}/close`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note:$('#closureCloseNote').value||null})});modalClose();showAlert(`${monthLabel(p.period)} foi fechado e registrado na auditoria.`,'success');await refreshRelated(p.id);await refresh({periodId:p.id});}catch(error){showFormError(error);}finally{setLoading(false);}});
  }

  function openGovernanceReview(){
    const p=period();if(!p)return;
    const items=(checklist().review_items||[]).filter(row=>!row.reviewed);
    if(!items.length){showAlert('Todos os alertas atuais já possuem registro de revisão.','success');return;}
    const item=items[0];
    modalOpen('Revisar alerta de governança',`${monthLabel(p.period)} · ${items.length} alerta(s) aguardando registro.`,`<form id="closureReviewForm" class="form-grid dpe-measurement-form">
      <div class="span-2 closure-confirm-summary"><strong>${escapeHtml(item.label||'Alerta')}</strong><span>${escapeHtml(item.detail||'Revise a situação antes do fechamento.')}</span></div>
      <label class="span-2"><span>Registro da revisão *</span><textarea id="closureReviewNote" rows="4" minlength="5" maxlength="2000" required placeholder="Ex.: receita estimada conferida com a Controladoria; valor será ajustado no próximo fechamento."></textarea><small>Registre o que foi conferido ou por que o alerta foi aceito neste mês.</small></label>
      <div id="closureFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Registrar revisão</button></div>
    </form>`,'DPE · GOVERNANÇA');
    $('#closureReviewForm').addEventListener('submit',async event=>{event.preventDefault();setLoading(true);try{await api(`/api/dpe/cost-engine/periods/${p.id}/governance-reviews`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({review_key:item.review_key,note:$('#closureReviewNote').value.trim()})});modalClose();showAlert('Revisão registrada na auditoria.','success');await refresh({periodId:p.id});}catch(error){showFormError(error);}finally{setLoading(false);}});
  }

  function openReturnReview(){
    const p=period();if(!p||p.status!=='CALCULATED')return;
    modalOpen('Voltar para conferência',`${monthLabel(p.period)} · o cálculo oficial atual será supersedido para permitir correções.`,`<form id="closureReturnReviewForm" class="form-grid dpe-measurement-form">
      <div class="span-2 closure-reopen-warning"><strong>O cálculo oficial não será apagado</strong><span>A versão atual ficará preservada no histórico como supersedida. Depois das correções, gere e oficialize um novo rateio antes de fechar.</span></div>
      <label class="span-2"><span>Por que o mês precisa voltar para conferência? *</span><textarea id="closureReturnReviewReason" rows="5" minlength="10" maxlength="2000" required placeholder="Ex.: corrigir uma despesa identificada durante a revisão final."></textarea><small>Mínimo de 10 caracteres. A justificativa ficará registrada na auditoria.</small></label>
      <div id="closureFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Voltar para conferência</button></div>
    </form>`,'DPE · GOVERNANÇA');
    $('#closureReturnReviewForm').addEventListener('submit',async event=>{event.preventDefault();setLoading(true);try{await api(`/api/dpe/cost-engine/periods/${p.id}/return-to-review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:$('#closureReturnReviewReason').value.trim()})});modalClose();showAlert(`${monthLabel(p.period)} voltou para Conferência. O cálculo anterior foi preservado na auditoria.`,'success');await refreshRelated(p.id);await refresh({periodId:p.id});}catch(error){showFormError(error);}finally{setLoading(false);}});
  }

  function openReopen(){
    const p=period();if(!p||p.status!=='CLOSED')return;
    modalOpen('Reabrir mês',`${monthLabel(p.period)} · a reabertura volta o mês para Conferência e fica registrada permanentemente.`,`<form id="closureReopenForm" class="form-grid dpe-measurement-form">
      <div class="span-2 closure-reopen-warning"><strong>O fechamento anterior não será apagado</strong><span>Depois da correção, será necessário atualizar a distribuição de custos e fazer um novo fechamento.</span></div>
      <label class="span-2"><span>Por que este mês precisa ser reaberto? *</span><textarea id="closureReopenReason" rows="5" minlength="10" maxlength="2000" required placeholder="Ex.: corrigir uma despesa de folha identificada após a conferência."></textarea><small>Mínimo de 10 caracteres. O motivo ficará visível no histórico.</small></label>
      <div id="closureFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Reabrir mês para correção</button></div>
    </form>`,'DPE · REABERTURA');
    $('#closureReopenForm').addEventListener('submit',async event=>{event.preventDefault();setLoading(true);try{await api(`/api/dpe/cost-engine/periods/${p.id}/reopen`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:$('#closureReopenReason').value.trim()})});modalClose();showAlert(`${monthLabel(p.period)} foi reaberto para Conferência. O motivo ficou registrado.`,'success');await refreshRelated(p.id);await refresh({periodId:p.id});}catch(error){showFormError(error);}finally{setLoading(false);}});
  }

  function bind(){
    $('#closurePeriodFilter')?.addEventListener('change',async event=>{state.costClosure.periodId=Number(event.target.value)||null;setLoading(true);try{await refresh({periodId:state.costClosure.periodId});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
    $('#closeCostPeriod')?.addEventListener('click',openClose);
    $('#reopenCostPeriod')?.addEventListener('click',openReopen);
    $('#returnReviewPeriod')?.addEventListener('click',openReturnReview);
    $('#section-fechamento')?.addEventListener('click',event=>{
      const go=event.target.closest('[data-closure-go]');
      if(!go)return;
      goToResolution(go.dataset.closureGo,go.dataset.closureCode).catch(error=>showAlert(error.message,'error',0));
    });
  }

  async function initialize(){bind();try{await refresh();}catch(error){showAlert(`Fechamento DPE: ${error.message}`,'error',0);}}
  window.initializeDPECostClosure=initialize;
  window.refreshDPECostClosure=refresh;
})();
