(function(){
  if(!state.costProductivity){state.costProductivity={periodId:null,data:null,copyPreview:null,policyPreview:null,loaded:false};}

  const PERIOD_LABELS={DRAFT:'Preparação',REVIEW:'Conferência',CALCULATED:'Calculada',CLOSED:'Fechada'};
  function data(){return state.costProductivity.data||{recurring_templates:[]};}
  function period(){return data().selected_period||null;}
  function previous(){return data().previous_period||null;}
  function currentPeriodId(){return state.costProductivity.periodId||period()?.id||state.costEngine?.selectedPeriodId||null;}
  function editable(){return Boolean(data().editable&&state.access?.canEdit);}
  function money(value){return Number(value||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:2,maximumFractionDigits:2});}
  function parseMoney(value){const raw=String(value||'').trim().replace(/R\$/g,'').replace(/\s/g,'');const normalized=raw.includes(',')?raw.replace(/\./g,'').replace(',','.'):raw;return Number(normalized||0);}
  function modalOpen(title,subtitle,body,eyebrow='DPE · PRODUTIVIDADE'){$('#costEngineModalEyebrow').textContent=eyebrow;$('#costEngineModalTitle').textContent=title;$('#costEngineModalSubtitle').textContent=subtitle||'';$('#costEngineModalBody').innerHTML=body;openDPEModal('costEngineModal');}
  function modalClose(){closeDPEModal('costEngineModal');}
  function formError(error){const detail=error?.payload?.detail;const fields=detail?.campos||{};return [error.message,...Object.entries(fields).map(([key,value])=>`${key}: ${value}`)].filter(Boolean).join('\n');}
  function showFormError(error){const box=$('#productivityFormErrors');if(box){focusInlineError(box,formError(error));}else showAlert(error.message,'error',0);}
  function statusChip(active){return active?'<span class="status-chip good">Ativo</span>':'<span class="status-chip info">Inativo</span>';}

  function periods(){return state.costEngine?.periods||state.costAllocation?.data?.periods||state.costExpenses?.data?.periods||[];}
  function renderPeriodFilter(){
    const el=$('#productivityPeriodFilter');if(!el)return;
    const rows=periods();
    el.innerHTML=rows.length?rows.map(row=>option(row.id,`${row.period} · ${PERIOD_LABELS[row.status]||row.status}`,String(row.id)===String(currentPeriodId()))).join(''):'<option value="">Nenhum mês</option>';
    if(currentPeriodId())el.value=String(currentPeriodId());
    const p=period();
    $('#productivityContext').textContent=p?`${p.period} · ${PERIOD_LABELS[p.status]||p.status}${editable()?' · edição liberada':' · histórico protegido'}`:'Selecione uma competência';
  }

  function renderCopy(){
    const root=$('#productivityCopySummary');if(!root)return;
    const prev=previous();const preview=state.costProductivity.copyPreview;
    if(!period()){
      root.innerHTML='<div class="cost-engine-empty"><strong>Selecione um mês</strong><span>A prévia usa o mês anterior disponível como origem.</span></div>';
      $('#previewPreviousMonth').disabled=true;$('#copyPreviousMonth').disabled=true;return;
    }
    if(!prev){
      root.innerHTML='<div class="cost-engine-empty"><strong>Não há mês anterior disponível</strong><span>Cadastre ou selecione uma competência que possua um período anterior.</span></div>';
      $('#previewPreviousMonth').disabled=true;$('#copyPreviousMonth').disabled=true;return;
    }
    $('#previewPreviousMonth').disabled=!editable();
    if(!preview){
      root.innerHTML=`<div class="productivity-callout"><strong>Origem: ${escapeHtml(prev.period)}</strong><span>Veja a prévia para saber quantas receitas e atividades docentes podem ser reaproveitadas em ${escapeHtml(period().period)}.</span></div>`;
      $('#copyPreviousMonth').disabled=true;return;
    }
    const rev=preview.revenues||{},teach=preview.teaching||{};
    root.innerHTML=`<div class="productivity-stat-grid"><div><span>Receitas de curso</span><strong>${rev.copyable||0}</strong><small>de ${rev.source_count||0} confirmada(s)</small></div><div><span>Alunos ativos</span><strong>${rev.students_copyable||0}</strong><small>contexto(s) copiável(is)</small></div><div><span>Atividades docentes</span><strong>${teach.copyable||0}</strong><small>${teach.blocked||0} bloqueada(s)</small></div><div><span>Cursos/contextos em comum</span><strong>${preview.common_offering_count||0}</strong><small>de ${preview.target_offering_count||0} no destino</small></div></div><div class="indicator-definition"><strong>Cópia é ponto de partida, não fechamento</strong><span>${escapeHtml(preview.warning||'Revise os dados copiados antes de fechar o mês.')}</span></div>`;
    $('#copyPreviousMonth').disabled=!editable()||(!$('#copyPreviousRevenues').checked&&!$('#copyPreviousTeaching').checked);
  }

  function renderPolicy(){
    const root=$('#bulkPolicySummary');if(!root)return;
    const preview=state.costProductivity.policyPreview;
    if(!period()){
      root.innerHTML='<div class="cost-engine-empty"><strong>Selecione um mês</strong><span>As políticas serão avaliadas contra as despesas do mês escolhido.</span></div>';
      $('#previewBulkPolicies').disabled=true;$('#applyBulkPolicies').disabled=true;return;
    }
    $('#previewBulkPolicies').disabled=!editable();
    if(!preview){
      root.innerHTML='<div class="productivity-callout"><strong>Somente sugestões compatíveis serão consideradas</strong><span>A prévia não altera despesas. Ela testa cada política contra os dados atuais do mês.</span></div>';
      $('#applyBulkPolicies').disabled=true;return;
    }
    root.innerHTML=`<div class="productivity-stat-grid"><div><span>Prontas</span><strong>${preview.ready_count||0}</strong><small>podem ser aplicadas</small></div><div><span>Bloqueadas</span><strong>${preview.blocked_count||0}</strong><small>exigem revisão</small></div><div><span>Sem política</span><strong>${preview.without_policy_count||0}</strong><small>continuam manuais</small></div></div>`;
    $('#applyBulkPolicies').disabled=!editable()||Number(preview.ready_count||0)===0||Number(preview.blocked_count||0)>0;
  }

  function renderRecurring(){
    const root=$('#recurringExpensesTable');if(!root)return;
    const rows=data().recurring_templates||[];
    root.innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.name)}</strong><span class="cost-cell-sub">${escapeHtml(row.description||'')}</span></td><td>${money(row.amount)}</td><td><strong>${escapeHtml(row.category_name||'—')}</strong><span class="cost-cell-sub">${escapeHtml(row.cost_center_name||'Sem setor')}</span></td><td>${escapeHtml(row.allocation_policy_name||'Sem política')}</td><td>${row.day_of_month||'—'}</td><td>${statusChip(row.active)}</td><td><button type="button" class="button secondary compact" data-recurring-edit="${row.id}" ${state.access?.canEdit?'':'disabled'}>Editar</button></td></tr>`).join(''):'<tr><td colspan="7"><div class="cost-engine-empty"><strong>Nenhum modelo recorrente</strong><span>Cadastre contas e despesas que se repetem para gerar o mês sem redigitar tudo.</span></div></td></tr>';
    $('#newRecurringExpense').disabled=!state.access?.canEdit;
    $('#generateRecurringExpenses').disabled=!editable()||!rows.some(row=>row.active);
  }

  function renderAll(){renderPeriodFilter();renderCopy();renderPolicy();renderRecurring();}

  async function refresh({periodId=null}={}){
    const pid=periodId||state.costProductivity.periodId||state.costEngine?.selectedPeriodId||state.costExpenses?.periodId||null;
    const payload=await api('/api/dpe/cost-engine/productivity-central',{},pid?{period_id:pid}:{});
    state.costProductivity.data=payload;state.costProductivity.periodId=payload.selected_period?.id||pid||null;state.costProductivity.loaded=true;
    renderAll();return payload;
  }

  async function previewCopy(){
    const p=period(),prev=previous();if(!p||!prev)return;
    setLoading(true);try{state.costProductivity.copyPreview=await api(`/api/dpe/cost-engine/periods/${p.id}/copy-preview`,{}, {source_period_id:prev.id});renderCopy();$('#copyPreviousResult').classList.add('hidden');}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  async function copyPrevious(){
    const p=period(),prev=previous();if(!p||!prev)return;
    const payload={source_period_id:prev.id,copy_revenues:$('#copyPreviousRevenues').checked,copy_teaching:$('#copyPreviousTeaching').checked,overwrite_revenues:$('#overwritePreviousRevenues').checked};
    if(!payload.copy_revenues&&!payload.copy_teaching){showAlert('Escolha ao menos um grupo para copiar.','error');return;}
    setLoading(true);try{
      const out=await api(`/api/dpe/cost-engine/periods/${p.id}/copy-previous`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const box=$('#copyPreviousResult');const parts=[];
      if(out.revenues)parts.push(`${out.revenues.revenue_copied||0} receita(s) de curso e ${out.revenues.student_copied||0} dado(s) de alunos copiado(s)`);
      if(out.teaching)parts.push(`${out.teaching.copied||0} atividade(s) docente(s) copiada(s), ${out.teaching.skipped||0} ignorada(s)`);
      box.innerHTML=`<strong>Cópia concluída</strong><span>${escapeHtml(parts.join(' · ')||'Nenhum item novo foi criado.')}</span>`;box.classList.remove('hidden');
      showAlert('Dados do mês anterior copiados como rascunho para revisão.','success');
      if(typeof window.refreshDPECostRevenues==='function')await window.refreshDPECostRevenues({periodId:p.id});
      if(typeof window.refreshDPECostTeaching==='function')await window.refreshDPECostTeaching({periodId:p.id});
      if(typeof window.refreshDPECostEconomics==='function')await window.refreshDPECostEconomics({periodId:p.id});
      await refresh({periodId:p.id});
    }catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  async function previewPolicies(){
    const p=period();if(!p)return;setLoading(true);try{
      const out=await api(`/api/dpe/cost-engine/periods/${p.id}/allocation-policies/bulk-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      state.costProductivity.policyPreview=out;renderPolicy();
      const box=$('#bulkPolicyResult');const sample=(out.items||[]).filter(item=>item.status!=='NO_POLICY').slice(0,6);
      box.innerHTML=sample.length?`<strong>Prévia conferida</strong><span>${sample.map(item=>`${escapeHtml(item.description)} — ${item.status==='READY'?'pronta':escapeHtml(item.error||'revisar')}`).join('<br>')}</span>`:'<strong>Nenhuma sugestão encontrada</strong><span>As despesas permanecem disponíveis para configuração manual.</span>';box.classList.remove('hidden');
    }catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  async function applyPolicies(){
    const p=period();if(!p)return;setLoading(true);try{
      const out=await api(`/api/dpe/cost-engine/periods/${p.id}/allocation-policies/bulk-apply`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      showAlert(`${out.applied_count||0} política(s) aplicada(s) às despesas do mês.`,'success');
      state.costProductivity.policyPreview=null;
      if(typeof window.refreshDPECostAllocation==='function')await window.refreshDPECostAllocation({periodId:p.id});
      if(typeof window.refreshDPECostExpenses==='function')await window.refreshDPECostExpenses({periodId:p.id});
      await previewPolicies();
    }catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  function categoryOptions(selected=''){return '<option value="">Selecione</option>'+((state.costExpenses?.categories)||[]).filter(row=>row.active||String(row.id)===String(selected)).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('');}
  function centerOptions(selected=''){return '<option value="">Sem setor</option>'+((state.costExpenses?.centers)||[]).filter(row=>row.active||String(row.id)===String(selected)).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('');}
  function policyOptions(selected=''){const rows=state.costAllocation?.data?.policies||[];return '<option value="">Sem política automática</option>'+rows.filter(row=>row.active||String(row.id)===String(selected)).map(row=>option(row.id,row.name,String(row.id)===String(selected))).join('');}

  function openRecurring(row=null){
    const item=row||{};
    modalOpen(row?'Editar despesa recorrente':'Nova despesa recorrente','O modelo gera uma despesa oficial por competência e evita duplicidades.',`<form id="productivityRecurringForm" class="form-grid dpe-measurement-form"><input id="recurringId" type="hidden" value="${escapeHtml(item.id||'')}"><label><span>Nome do modelo *</span><input id="recurringName" required maxlength="180" value="${escapeHtml(item.name||'')}" placeholder="Ex.: Energia elétrica"></label><label><span>Valor padrão *</span><input id="recurringAmount" required inputmode="decimal" value="${item.amount!==undefined?escapeHtml(Number(item.amount).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})):''}" placeholder="0,00"></label><label class="span-2"><span>Descrição da despesa *</span><input id="recurringDescription" required maxlength="280" value="${escapeHtml(item.description||'')}"></label><label><span>Categoria *</span><select id="recurringCategory" required>${categoryOptions(item.category_id)}</select></label><label><span>Setor de origem</span><select id="recurringCenter">${centerOptions(item.cost_center_id)}</select></label><label><span>Política de distribuição</span><select id="recurringPolicy">${policyOptions(item.allocation_policy_id)}</select></label><label><span>Dia do mês</span><input id="recurringDay" type="number" min="1" max="31" value="${escapeHtml(item.day_of_month||'')}"></label><label><span>Tipo</span><select id="recurringKind">${option('GENERAL','Despesa geral',(item.expense_kind||'GENERAL')==='GENERAL')}${option('PAYROLL','Folha',(item.expense_kind||'GENERAL')==='PAYROLL')}</select></label><label><span>Fornecedor / beneficiário</span><input id="recurringCounterparty" maxlength="220" value="${escapeHtml(item.counterparty_name||'')}"></label><label class="span-2"><span>Observações</span><textarea id="recurringNotes">${escapeHtml(item.notes||'')}</textarea></label><label class="check-field span-2"><input id="recurringActive" type="checkbox" ${item.active===false?'':'checked'}><span>Modelo ativo</span></label><div class="indicator-definition span-2"><strong>Uma vez por mês</strong><span>A geração usa uma chave idempotente. Clicar novamente não cria uma segunda despesa para o mesmo modelo e competência.</span></div><div id="productivityFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar modelo</button></div></form>`,'DPE · DESPESAS RECORRENTES');
    $('#productivityRecurringForm').addEventListener('submit',saveRecurring);
  }

  async function saveRecurring(event){
    event.preventDefault();const id=$('#recurringId').value;const amount=parseMoney($('#recurringAmount').value);
    const payload={name:$('#recurringName').value,description:$('#recurringDescription').value,amount,expense_kind:$('#recurringKind').value,counterparty_name:$('#recurringCounterparty').value||null,cost_center_id:$('#recurringCenter').value?Number($('#recurringCenter').value):null,category_id:Number($('#recurringCategory').value),allocation_policy_id:$('#recurringPolicy').value?Number($('#recurringPolicy').value):null,day_of_month:$('#recurringDay').value?Number($('#recurringDay').value):null,notes:$('#recurringNotes').value||null,active:$('#recurringActive').checked};
    setLoading(true);try{await api(id?`/api/dpe/cost-engine/recurring-expenses/${id}`:'/api/dpe/cost-engine/recurring-expenses',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert('Modelo recorrente salvo.','success');await refresh({periodId:currentPeriodId()});}catch(error){showFormError(error);}finally{setLoading(false);}
  }

  async function generateRecurring(){
    const p=period();if(!p)return;setLoading(true);try{const out=await api(`/api/dpe/cost-engine/periods/${p.id}/recurring-expenses/generate`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});showAlert(`${out.created_count||0} despesa(s) recorrente(s) gerada(s); ${out.skipped||0} já existia(m) ou foi(ram) ignorada(s).`,'success');if(typeof window.refreshDPECostExpenses==='function')await window.refreshDPECostExpenses({periodId:p.id});if(typeof window.refreshDPECostAllocation==='function')await window.refreshDPECostAllocation({periodId:p.id});await refresh({periodId:p.id});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}
  }

  function bind(){
    $('#productivityPeriodFilter')?.addEventListener('change',async event=>{state.costProductivity.periodId=Number(event.target.value)||null;state.costProductivity.copyPreview=null;state.costProductivity.policyPreview=null;setLoading(true);try{await refresh({periodId:state.costProductivity.periodId});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
    $('#previewPreviousMonth')?.addEventListener('click',previewCopy);$('#copyPreviousMonth')?.addEventListener('click',copyPrevious);
    ['#copyPreviousRevenues','#copyPreviousTeaching'].forEach(selector=>$(selector)?.addEventListener('change',renderCopy));
    $('#previewBulkPolicies')?.addEventListener('click',previewPolicies);$('#applyBulkPolicies')?.addEventListener('click',applyPolicies);
    $('#newRecurringExpense')?.addEventListener('click',()=>openRecurring());$('#generateRecurringExpenses')?.addEventListener('click',generateRecurring);
    document.addEventListener('click',event=>{const edit=event.target.closest('[data-recurring-edit]');if(edit){const row=(data().recurring_templates||[]).find(item=>String(item.id)===String(edit.dataset.recurringEdit));if(row)openRecurring(row);}});
  }

  async function initialize(){bind();try{await refresh();}catch(error){showAlert(`Produtividade DPE: ${error.message}`,'error',0);}}
  window.initializeDPECostProductivity=initialize;
  window.refreshDPECostProductivity=refresh;
})();
