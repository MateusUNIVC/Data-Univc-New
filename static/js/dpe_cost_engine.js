(function(){
  const LEVEL_LABELS={GRADUATION:'Graduação',TECHNICAL:'Técnico',POSTGRADUATE:'Pós-graduação',EXTENSION:'Extensão',OTHER:'Outro'};
  const STATUS_LABELS={DRAFT:'Preparação',REVIEW:'Conferência',CALCULATED:'Calculada',CLOSED:'Fechada'};
  const MODALITY_LABELS={PRESENCIAL:'Presencial',EAD:'EAD',SEMIPRESENCIAL:'Semipresencial',HIBRIDO:'Híbrido',HYBRID:'Híbrido',OUTRA:'Outra',OTHER:'Outra',NAO_INFORMADA:'Não informada'};
  const MONTH_RE=/^\d{4}-(0[1-9]|1[0-2])$/;

  if(!state.costEngine){state.costEngine={products:[],offerings:[],periods:[],counts:{},selectedPeriodId:null,periodDetail:null};}

  function clean(value){return value===null||value===undefined?'':String(value)}
  function statusChip(status){
    const kind=status==='CLOSED'?'good':status==='CALCULATED'?'good':status==='REVIEW'?'attention':'info';
    return `<span class="status-chip ${kind}">${escapeHtml(STATUS_LABELS[status]||status)}</span>`;
  }
  function activeChip(active){return `<span class="status-chip ${active?'good':'info'}">${active?'Ativo':'Inativo'}</span>`}
  function validity(row){return `${escapeHtml(row.valid_from||'—')}${row.valid_to?` → ${escapeHtml(row.valid_to)}`:' → atual'}`}
  function localLabel(row){return row.pole_name||row.unit_name||row.campus||'—'}
  function modalOpen(title,subtitle,body,eyebrow='DPE · GESTÃO MENSAL'){
    $('#costEngineModalEyebrow').textContent=eyebrow;
    $('#costEngineModalTitle').textContent=title;
    $('#costEngineModalSubtitle').textContent=subtitle||'';
    $('#costEngineModalBody').innerHTML=body;
    openDPEModal('costEngineModal');
  }
  function modalClose(){closeDPEModal('costEngineModal')}
  function formError(error){
    const detail=error?.payload?.detail;
    const fields=detail?.campos||{};
    const fieldText=Object.entries(fields).map(([key,value])=>`${key}: ${value}`).join('\n');
    return [error.message,fieldText].filter(Boolean).join('\n');
  }
  function showFormError(error){
    const box=$('#costEngineFormErrors');
    if(box){box.textContent=formError(error);box.classList.remove('hidden');}
  }
  function productOptions(selected=''){
    const rows=(state.costEngine.products||[]).filter(row=>row.active||String(row.id)===String(selected));
    return `<option value="">Selecione um curso</option>`+rows.map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(selected))).join('');
  }
  function officialCourseOptions(selected=''){
    const rows=(state.courseCatalog||[]).filter(row=>row.persisted&&row.id);
    const selectedKnown=rows.some(row=>String(row.id)===String(selected));
    const legacy=selected&&!selectedKnown?`<option value="${escapeHtml(selected)}" selected>Vínculo anterior · selecione novamente</option>`:'';
    return `<option value="">Selecione um curso oficial</option>${legacy}`+rows.map(row=>option(row.id,`${row.name} · ${row.directorate_code} · ${row.modality||'modalidade não informada'}`,String(row.id)===String(selected))).join('');
  }
  function levelOptions(selected='GRADUATION'){
    return Object.entries(LEVEL_LABELS).map(([value,label])=>option(value,label,value===selected)).join('');
  }
  function modalityOptions(selected=''){
    const values=['PRESENCIAL','EAD','SEMIPRESENCIAL','HIBRIDO','OUTRA'];
    return option('','Mesma modalidade do curso',!selected)+values.map(value=>option(value,MODALITY_LABELS[value]||value,value===selected)).join('');
  }
  function shiftOptions(selected=''){
    const values=[['','Não se aplica / não informado'],['MATUTINO','Matutino'],['VESPERTINO','Vespertino'],['NOTURNO','Noturno'],['INTEGRAL','Integral'],['FLEXIVEL','Flexível']];
    const known=values.some(([value])=>value===selected);
    return `${!known&&selected?option(selected,selected,true):''}`+values.map(([value,label])=>option(value,label,value===selected)).join('');
  }

  function renderCards(){
    const c=state.costEngine.counts||{};
    const products=c.products||0, contexts=c.contexts||0, periods=c.periods||0;
    $('#costCatalogCards').innerHTML=[
      card('Cursos',products,`${c.active_products||0} ativos`,'C'),
      card('Contextos adicionais',contexts,`${c.active_contexts||0} ativos`,'↳'),
      card('Estrutura','Curso primeiro','contexto somente quando necessário','✓'),
    ].join('');
    $('#costPeriodCards').innerHTML=[
      card('Meses cadastrados',periods,'histórico disponível','M'),
      card('Em preparação',c.draft_periods||0,'mês ainda editável','D'),
      card('Em conferência',c.review_periods||0,'prontas para validação','R'),
    ].join('');
  }
  function card(label,value,sub,icon){return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-sub">${escapeHtml(sub)}</span><span class="status-chip info">Cadastro</span></article>`}

  function renderProducts(){
    const rows=state.costEngine.products||[];
    $('#costProductsTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.code)}</strong></td><td><strong>${escapeHtml(row.name)}</strong><small class="cost-cell-sub">${escapeHtml(MODALITY_LABELS[row.source_modality]||row.source_modality||'Modalidade não informada')}</small></td><td>${escapeHtml(LEVEL_LABELS[row.academic_level]||row.academic_level)}</td><td>${validity(row)}</td><td>${row.context_count||0}</td><td>${activeChip(row.active)}</td><td><div class="table-actions-inline"><button class="table-action" data-cost-view-offerings="${row.id}">Ver contextos</button>${state.access?.canEdit?`<button class="table-action" data-cost-edit-product="${row.id}">Editar</button>`:''}</div></td></tr>`).join(''):dpeEmptyRow(7,'Nenhum curso vinculado','Vincule um curso ativo do catálogo acadêmico oficial.');
  }

  function renderOfferings(){
    const filter=$('#costOfferingProductFilter');
    const old=filter?.value||'';
    if(filter){
      filter.innerHTML='<option value="">Todos os cursos</option>'+(state.costEngine.products||[]).map(row=>option(row.id,`${row.name} · ${row.code}`,String(row.id)===String(old))).join('');
      if(old&&[...filter.options].some(o=>o.value===old))filter.value=old;
    }
    const productId=filter?.value||'';
    const rows=(state.costEngine.offerings||[]).filter(row=>!row.is_default_context&&(!productId||String(row.product_id)===String(productId)));
    $('#costOfferingsTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${escapeHtml(row.product_name)}</strong><small class="cost-cell-sub">${escapeHtml(row.code)}</small></td><td>${escapeHtml(MODALITY_LABELS[row.modality]||row.modality||'—')}</td><td>${escapeHtml(row.shift||'—')}</td><td>${escapeHtml(localLabel(row))}</td><td>${validity(row)}</td><td>${activeChip(row.active)}</td><td>${state.access?.canEdit?`<button class="table-action" data-cost-edit-offering="${row.id}">Editar</button>`:''}</td></tr>`).join(''):dpeEmptyRow(7,'Nenhum contexto adicional','Isso é normal: sem contexto adicional, o curso inteiro funciona como uma única unidade de análise.');
  }

  function renderPeriods(){
    const rows=state.costEngine.periods||[];
    $('#costPeriodsTable').innerHTML=rows.length?rows.map(row=>`<tr class="${String(row.id)===String(state.costEngine.selectedPeriodId)?'selected-row':''}"><td><strong>${escapeHtml(row.period)}</strong></td><td>${statusChip(row.status)}</td><td>${row.included_offering_count||0}/${row.offering_count||0}</td><td>${escapeHtml(row.opened_by||'—')}</td><td class="component-cell">${escapeHtml(row.notes||'—')}</td><td><button class="table-action" data-cost-open-period="${row.id}">Abrir</button></td></tr>`).join(''):dpeEmptyRow(6,'Nenhum período cadastrado','Abra o primeiro mês para iniciar o fluxo financeiro.');
    if(!rows.length){renderEmptyPeriod();}
  }

  function renderEmptyPeriod(){
    $('#costPeriodDetailPanel').innerHTML='<div class="cost-engine-empty"><strong>Selecione um mês</strong><span>Os cursos e contextos preservados para esse período aparecerão aqui.</span></div>';
  }

  function renderPeriodDetail(){
    const row=state.costEngine.periodDetail;
    if(!row){renderEmptyPeriod();return;}
    const editable=Boolean(row.editable&&state.access?.canEdit);
    const offerings=row.offerings||[];
    $('#costPeriodDetailPanel').innerHTML=`
      <div class="panel-heading responsive-heading cost-period-heading">
        <div><span class="eyebrow">Mês ${escapeHtml(row.period)}</span><h3>Cursos preservados neste mês</h3><p>${row.included_offering_count||0} de ${row.offering_count||0} curso(s)/contexto(s) incluído(s)</p></div>
        <div class="indicator-actions">${editable?'<button class="button secondary compact" data-cost-refresh-period>Atualizar cursos do mês</button>':''}</div>
      </div>
      <div class="cost-period-meta">
        <label><span>Status</span><select id="costPeriodStatus" ${editable?'':'disabled'}>${option('DRAFT','Preparação',row.status==='DRAFT')}${option('REVIEW','Conferência',row.status==='REVIEW')}${!['DRAFT','REVIEW'].includes(row.status)?option(row.status,STATUS_LABELS[row.status]||row.status,true):''}</select></label>
        <label class="cost-period-notes"><span>Observações</span><textarea id="costPeriodNotes" ${editable?'':'disabled'}>${escapeHtml(row.notes||'')}</textarea></label>
        ${editable?'<button class="button primary compact" data-cost-save-period>Salvar mês</button>':''}
      </div>
      <div class="cost-period-snapshot-note"><strong>Histórico protegido</strong><span>Os cursos abaixo pertencem a este mês. Mudanças futuras no cadastro não alteram este histórico, a menos que você atualize o mês enquanto ele ainda estiver editável.</span></div>
      <div class="cost-snapshot-list">${offerings.length?offerings.map(item=>`<label class="cost-snapshot-item ${item.included?'':'excluded'}"><input type="checkbox" data-cost-toggle-snapshot="${item.id}" ${item.included?'checked':''} ${editable?'':'disabled'}><span><strong>${escapeHtml(item.label||item.offering?.code||'Curso')}</strong><small>${escapeHtml(item.offering?.code||'')} · vigência ${escapeHtml(item.offering?.valid_from||'—')}${item.offering?.valid_to?` → ${escapeHtml(item.offering.valid_to)}`:''}</small></span></label>`).join(''):'<div class="cost-engine-empty compact"><strong>Nenhum curso/contexto incluído</strong><span>Vincule cursos válidos e atualize este mês.</span></div>'}</div>`;
    applyAccess();
  }

  function renderAll(){renderCards();renderProducts();renderOfferings();renderPeriods();applyAccess();}

  async function refreshCatalog({preservePeriod=true}={}){
    const current=preservePeriod?state.costEngine.selectedPeriodId:null;
    const payload=await api('/api/dpe/cost-engine/catalog');
    state.costEngine.products=payload.products||[];
    state.costEngine.offerings=payload.offerings||[];
    state.costEngine.periods=payload.periods||[];
    state.costEngine.counts=payload.counts||{};
    state.costEngine.selectedPeriodId=current&&state.costEngine.periods.some(row=>String(row.id)===String(current))?current:null;
    renderAll();
    if(state.costEngine.selectedPeriodId)await loadPeriodDetail(state.costEngine.selectedPeriodId);
    if(state.costExpenses?.loaded&&typeof window.refreshDPECostExpenses==='function')await window.refreshDPECostExpenses({keepPeriod:true});
  }

  async function loadPeriodDetail(id){
    state.costEngine.selectedPeriodId=Number(id);
    state.costEngine.periodDetail=await api(`/api/dpe/cost-engine/periods/${id}`);
    renderPeriods();renderPeriodDetail();
  }

  function openProduct(row=null){
    if(!state.access?.canEdit)return;
    const available=(state.courseCatalog||[]).filter(item=>item.persisted&&item.id);
    if(!available.length&&!row){showAlert('Nenhum curso persistido foi encontrado no catálogo acadêmico oficial.','error',0);return;}
    const title=row?'Revisar vínculo do curso':'Vincular curso oficial';
    modalOpen(title,'O nome, a modalidade e a vigência vêm do catálogo acadêmico oficial. O curso funciona sozinho; contextos adicionais são opcionais.',`<form id="costProductForm" class="form-grid dpe-measurement-form">
      <input type="hidden" id="costProductId" value="${escapeHtml(row?.id||'')}">
      <label class="span-2"><span>Curso oficial *</span><select id="costProductSource" required>${officialCourseOptions(row?.source_course_id||'')}</select><small>Cursos ativos de DTNH e DCS podem ser utilizados independentemente da modalidade.</small></label>
      <label><span>Código econômico *</span><input id="costProductCode" required maxlength="80" value="${escapeHtml(row?.code||'')}" placeholder="Ex.: DIR"><small>Identificador estável usado pelo motor financeiro.</small></label>
      <label><span>Nome utilizado</span><input value="${escapeHtml(row?.name||'Definido pelo catálogo oficial')}" readonly><small>Atualizado a partir do curso oficial.</small></label>
      <details class="span-2 dpe-form-advanced"><summary>Informações adicionais</summary><div class="form-grid nested-grid"><label><span>Chave externa</span><input id="costProductExternal" maxlength="160" value="${escapeHtml(row?.external_key||'')}"><small>Use somente para integração com outro sistema.</small></label><label><span>Observações</span><textarea id="costProductNotes">${escapeHtml(row?.notes||'')}</textarea></label></div></details>
      <div class="indicator-definition span-2"><strong>Fonte única de verdade</strong><span>A DPE não cria um novo curso acadêmico aqui. Ela vincula a camada econômica ao curso já cadastrado institucionalmente e cria internamente um contexto-base automático.</span></div>
      <div id="costEngineFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar vínculo</button></div>
    </form>`,'DPE · CURSO OFICIAL');
    $('#costProductForm').addEventListener('submit',saveProduct);
  }

  async function saveProduct(event){
    event.preventDefault();const id=$('#costProductId').value;
    const payload={code:$('#costProductCode').value,source_course_id:Number($('#costProductSource').value),external_key:$('#costProductExternal').value||null,notes:$('#costProductNotes').value||null};
    setLoading(true);try{await api(id?`/api/dpe/cost-engine/products/${id}`:'/api/dpe/cost-engine/products',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert('Curso oficial vinculado à DPE.','success');await refreshCatalog();}catch(error){showFormError(error)}finally{setLoading(false)}
  }

  function openOffering(row=null){
    if(!state.access?.canEdit)return;
    if(!(state.costEngine.products||[]).length){showAlert('Cadastre um curso antes de criar um contexto adicional.','error');return;}
    modalOpen(row?'Editar contexto do curso':'Novo contexto do curso','Use somente quando uma parte do curso precisar de alunos, receita, docência ou custos separados. Se não houver essa necessidade, não crie nada: o curso já funciona sozinho.',`<form id="costOfferingForm" class="form-grid dpe-measurement-form">
      <input type="hidden" id="costOfferingId" value="${escapeHtml(row?.id||'')}">
      <label class="span-2"><span>Curso *</span><select id="costOfferingProduct" required>${productOptions(row?.product_id||'')}</select></label>
      <label><span>Identificação do contexto *</span><input id="costOfferingCode" required maxlength="100" value="${escapeHtml(row?.code||'')}" placeholder="Ex.: ADM-NOT ou TURMA-A"><small>Pode representar turno, turma, unidade ou outro agrupamento operacional.</small></label>
      <label><span>Modalidade</span><select id="costOfferingModality">${modalityOptions(row?.modality||'')}</select><small>Deixe em “Mesma modalidade do curso” quando não houver diferença.</small></label>
      <label><span>Turno</span><select id="costOfferingShift">${shiftOptions(row?.shift||'')}</select></label>
      <label><span>Campus / local</span><input id="costOfferingCampus" maxlength="120" value="${escapeHtml(row?.campus||'')}"></label>
      <label><span>Unidade</span><input id="costOfferingUnit" maxlength="160" value="${escapeHtml(row?.unit_name||'')}"></label>
      <label><span>Chave externa / turma</span><input id="costOfferingExternal" maxlength="180" value="${escapeHtml(row?.external_key||'')}" placeholder="Opcional"></label>
      <label><span>Vigência inicial *</span><input id="costOfferingValidFrom" type="month" required value="${escapeHtml(row?.valid_from||'')}"></label>
      <label><span>Vigência final</span><input id="costOfferingValidTo" type="month" value="${escapeHtml(row?.valid_to||'')}"><small>Obrigatória ao inativar.</small></label>
      <label class="check-field span-2"><input id="costOfferingActive" type="checkbox" ${row?.active===false?'':'checked'}><span>Contexto ativo</span></label>
      <label class="span-2"><span>Observações</span><textarea id="costOfferingNotes">${escapeHtml(row?.notes||'')}</textarea></label>
      <div class="indicator-definition span-2"><strong>Contexto é opcional</strong><span>Crie um contexto somente se o curso precisar ser separado em mais de uma unidade econômica. Caso contrário, use apenas o curso.</span></div>
      <div id="costEngineFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar contexto</button></div>
    </form>`,'DPE · CONTEXTO DO CURSO');
    $('#costOfferingForm').addEventListener('submit',saveOffering);
  }

  async function saveOffering(event){
    event.preventDefault();const id=$('#costOfferingId').value;
    const payload={product_id:Number($('#costOfferingProduct').value),code:$('#costOfferingCode').value,modality:$('#costOfferingModality').value||null,shift:$('#costOfferingShift').value||null,campus:$('#costOfferingCampus').value||null,unit_name:$('#costOfferingUnit').value||null,pole_name:null,external_key:$('#costOfferingExternal').value||null,valid_from:$('#costOfferingValidFrom').value,valid_to:$('#costOfferingValidTo').value||null,active:$('#costOfferingActive').checked,notes:$('#costOfferingNotes').value||null};
    setLoading(true);try{await api(id?`/api/dpe/cost-engine/offerings/${id}`:'/api/dpe/cost-engine/offerings',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert('Contexto do curso salvo.','success');await refreshCatalog();}catch(error){showFormError(error)}finally{setLoading(false)}
  }

  function openPeriod(){
    if(!state.access?.canEdit)return;
    modalOpen('Abrir mês','O novo mês começa em Preparação e inclui automaticamente os cursos e contextos válidos vinculados ao catálogo acadêmico oficial.',`<form id="costPeriodForm" class="form-grid dpe-measurement-form">
      <label><span>Mês *</span><input id="costPeriodMonth" type="month" required></label>
      <label class="check-field"><input id="costPeriodMaterialize" type="checkbox" checked><span>Incluir automaticamente os cursos/contextos válidos neste mês</span></label>
      <label class="span-2"><span>Observações</span><textarea id="costPeriodCreateNotes" placeholder="Ex.: abertura inicial do mês para conferência."></textarea></label>
      <div class="indicator-definition span-2"><strong>O que será preservado</strong><span>Curso oficial e, quando existirem, modalidade, turno e localização dos contextos válidos no momento da abertura.</span></div>
      <div id="costEngineFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Abrir mês</button></div>
    </form>`,'DPE · PERÍODO');
    $('#costPeriodForm').addEventListener('submit',createPeriod);
  }

  async function createPeriod(event){
    event.preventDefault();const period=$('#costPeriodMonth').value;
    if(!MONTH_RE.test(period)){showFormError(new Error('Informe um mês válido.'));return;}
    setLoading(true);try{const row=await api('/api/dpe/cost-engine/periods',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({period,notes:$('#costPeriodCreateNotes').value||null,materialize_offerings:$('#costPeriodMaterialize').checked})});modalClose();showAlert(`Mês ${row.period} aberto com ${row.included_offering_count||0} curso(s)/contexto(s).`,'success');state.costEngine.selectedPeriodId=row.id;await refreshCatalog();}catch(error){showFormError(error)}finally{setLoading(false)}
  }

  async function savePeriodMeta(){
    const row=state.costEngine.periodDetail;if(!row||!state.access?.canEdit)return;
    setLoading(true);try{const updated=await api(`/api/dpe/cost-engine/periods/${row.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:$('#costPeriodStatus').value,notes:$('#costPeriodNotes').value||null})});state.costEngine.periodDetail=updated;showAlert('Mês atualizado.','success');await refreshCatalog();}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}
  }

  async function refreshPeriodSnapshot(){
    const row=state.costEngine.periodDetail;if(!row||!state.access?.canEdit)return;
    const confirmed=await requestDPEConfirmation({title:'Atualizar cursos do mês?',message:`Os cursos de ${row.period} serão sincronizados com os contextos vigentes do catálogo. Exclusões manuais já feitas serão preservadas.`,confirmLabel:'Atualizar cursos'});if(!confirmed)return;
    setLoading(true);try{const updated=await api(`/api/dpe/cost-engine/periods/${row.id}/refresh-offerings`,{method:'POST'});state.costEngine.periodDetail=updated;showAlert('Cursos do mês atualizados.','success');await refreshCatalog();}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}
  }

  async function toggleSnapshot(snapshotId,included){
    const row=state.costEngine.periodDetail;if(!row||!state.access?.canEdit)return;
    setLoading(true);try{const updated=await api(`/api/dpe/cost-engine/periods/${row.id}/offerings/${snapshotId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({included})});state.costEngine.periodDetail=updated;renderPeriodDetail();await refreshCatalog();}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}
  }

  function bind(){
    $('#newCostProduct')?.addEventListener('click',()=>openProduct());
    $('#newCostOffering')?.addEventListener('click',()=>openOffering());
    $('#newCostPeriod')?.addEventListener('click',openPeriod);
    $('#costOfferingProductFilter')?.addEventListener('change',renderOfferings);
    document.addEventListener('click',event=>{
      if(event.target.closest('[data-close-modal="costEngineModal"]')){modalClose();return;}
      const vo=event.target.closest('[data-cost-view-offerings]');if(vo){const filter=$('#costOfferingProductFilter');if(filter){filter.value=String(vo.dataset.costViewOfferings);renderOfferings();document.querySelector('.cost-catalog-offerings-panel')?.scrollIntoView({behavior:'smooth',block:'start'});}return;}
      const ep=event.target.closest('[data-cost-edit-product]');if(ep){const row=state.costEngine.products.find(item=>String(item.id)===String(ep.dataset.costEditProduct));if(row)openProduct(row);return;}
      const eo=event.target.closest('[data-cost-edit-offering]');if(eo){const row=state.costEngine.offerings.find(item=>String(item.id)===String(eo.dataset.costEditOffering));if(row)openOffering(row);return;}
      const op=event.target.closest('[data-cost-open-period]');if(op){loadPeriodDetail(op.dataset.costOpenPeriod).catch(error=>showAlert(error.message,'error',0));return;}
      if(event.target.closest('[data-cost-save-period]')){savePeriodMeta();return;}
      if(event.target.closest('[data-cost-refresh-period]')){refreshPeriodSnapshot();return;}
    });
    document.addEventListener('change',event=>{
      const toggle=event.target.closest('[data-cost-toggle-snapshot]');if(toggle){toggleSnapshot(toggle.dataset.costToggleSnapshot,toggle.checked);}
    });
  }

  async function initialize(){
    bind();
    try{await refreshCatalog({preservePeriod:false});}
    catch(error){showAlert(`DPE: ${error.message}`,'error',0);}
  }

  window.initializeDPECostEngine=initialize;
  window.refreshDPECostEngine=refreshCatalog;
})();
