(function(){
  if(!state.costEconomics){state.costEconomics={periodId:null,data:null,loaded:false,expandedProducts:new Set()};}
  if(!(state.costEconomics.expandedProducts instanceof Set))state.costEconomics.expandedProducts=new Set();

  const PERIOD_LABELS={DRAFT:'Preparação',REVIEW:'Conferência',CALCULATED:'Calculada',CLOSED:'Fechada'};
  const SOURCE_LABELS={MANUAL:'Manual',IMPORT:'Importação',API:'API',REQUEST:'Requisição',SYSTEM:'Sistema'};

  function money(value){if(value===null||value===undefined)return '—';return Number(value||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:2,maximumFractionDigits:2});}
  function integer(value){if(value===null||value===undefined)return '—';return Number(value||0).toLocaleString('pt-BR',{maximumFractionDigits:0});}
  function percent(value){if(value===null||value===undefined)return '—';return `${Number(value||0).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}%`;}
  function data(){return state.costEconomics.data||{periods:[],rows:[],summary:{},aggregates:{product:[],modality:[],shift:[]}};}
  function period(){return data().selected_period||null;}
  function editable(){return Boolean(data().editable&&state.access?.canEdit);}
  function currentPeriodId(){return state.costEconomics.periodId||period()?.id||null;}
  function modalOpen(title,subtitle,body,eyebrow='DPE · RESULTADOS'){$('#costEngineModalEyebrow').textContent=eyebrow;$('#costEngineModalTitle').textContent=title;$('#costEngineModalSubtitle').textContent=subtitle||'';$('#costEngineModalBody').innerHTML=body;openDPEModal('costEngineModal');}
  function modalClose(){closeDPEModal('costEngineModal');}
  function formError(error){const detail=error?.payload?.detail;const fields=detail?.campos||{};return [error.message,...Object.entries(fields).map(([key,value])=>`${key}: ${value}`)].filter(Boolean).join('\n');}
  function showFormError(error){const box=$('#economicsFormErrors');if(box){focusInlineError(box,formError(error));}else showAlert(error.message,'error',0);}
  function card(label,value,sub,icon,tone='info'){return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-sub">${escapeHtml(sub)}</span><span class="status-chip ${tone}">Cursos</span></article>`;}

  function renderPeriodFilter(){const el=$('#economicsPeriodFilter');if(!el)return;const rows=data().periods||[];el.innerHTML=rows.length?rows.map(row=>option(row.id,`${row.period} · ${PERIOD_LABELS[row.status]||row.status}`,String(row.id)===String(currentPeriodId()))).join(''):'<option value="">Abra um mês primeiro</option>';if(currentPeriodId())el.value=String(currentPeriodId());}

  function renderCards(){
    const root=$('#economicsCards');if(!root)return;const s=data().summary||{},run=data().selected_run;
    root.innerHTML=[
      card('Receita dos cursos',s.course_revenue===null||s.course_revenue===undefined?'—':money(s.course_revenue),`${s.revenue_ready_count||0}/${s.offering_count||0} curso(s)/contexto(s) confirmados`,'R$',s.revenue_ready_count===s.offering_count?'good':'attention'),
      card('Custo distribuído',s.allocated_cost===null||s.allocated_cost===undefined?'Aguardando':money(s.allocated_cost),run?`cálculo v${run.run_number}${run.current?'':' desatualizado'}`:'calcule a distribuição','C'),
      card('Resultado dos cursos',s.economic_result===null||s.economic_result===undefined?'Aguardando':money(s.economic_result),s.margin_percent===null||s.margin_percent===undefined?'resultado disponível após receita + custos':`margem ${percent(s.margin_percent)}`,'Δ',Number(s.economic_result||0)>=0?'good':'attention'),
      card('Alunos ativos',s.active_students===null||s.active_students===undefined?'Parcial':integer(s.active_students),`${s.student_ready_count||0}/${s.offering_count||0} curso(s)/contexto(s) preenchido(s)`,'A')
    ].join('');
  }

  function renderContext(){const p=period(),run=data().selected_run;const runText=run?` · custos v${run.run_number}${run.current?'':' · desatualizados'}`:' · custos ainda não calculados';$('#economicsContext').textContent=p?`${p.period} · ${PERIOD_LABELS[p.status]||p.status}${runText}`:'Selecione um mês';const offeringContext=$('#economicsOfferingContext');if(offeringContext)offeringContext.textContent=`${(data().aggregates?.product||[]).length} curso(s) · ${(data().rows||[]).length} contexto(s)`;}

  function courseOfferLabel(row){const offer=row.offering||{};const bits=[];if(offer.is_default_context||String(offer.context_kind||'').toUpperCase()==='BASE')return 'Curso completo';if(offer.modality)bits.push(String(offer.modality).replace('SEMIPRESENCIAL','Semipresencial').replace('PRESENCIAL','Presencial').replace('EAD','EAD').replace('HIBRIDO','Híbrido'));if(offer.shift)bits.push(String(offer.shift).charAt(0)+String(offer.shift).slice(1).toLowerCase());const local=offer.pole_name||offer.unit_name||offer.campus;if(local)bits.push(local);return bits.join(' · ')||'Curso completo';}

  function rowStatus(row){const issues=[];if(!row.revenue_ready)issues.push('receita');if(row.allocated_cost===null||row.allocated_cost===undefined)issues.push('custos');if(issues.length)return `<span class="status-chip attention">Pendente: ${escapeHtml(issues.join(' e '))}</span>`;return '<span class="status-chip good">Completo</span>';}
  function productAggregate(name){return (data().aggregates?.product||[]).find(row=>String(row.key)===String(name))||null;}

  function renderCourseList(){
    const root=$('#economicsCourseList');if(!root)return;const rows=data().rows||[];const grouped=new Map();
    rows.forEach(row=>{const name=row.product?.name||'Curso sem nome';if(!grouped.has(name))grouped.set(name,[]);grouped.get(name).push(row);});
    if(!grouped.size){root.innerHTML='<div class="courses-empty-state"><strong>Nenhum curso disponível neste mês.</strong><span>Vincule cursos e revise a competência selecionada.</span></div>';return;}
    root.innerHTML=[...grouped.entries()].map(([name,offers])=>{const agg=productAggregate(name)||{};const expanded=state.costEconomics.expandedProducts.has(name);const resultClass=agg.economic_result===null||agg.economic_result===undefined?'':Number(agg.economic_result)>=0?'positive':'negative';const details=offers.map(row=>`<div class="course-offer-row"><div class="course-offer-main"><strong>${escapeHtml(courseOfferLabel(row))}</strong>${rowStatus(row)}</div><div><span>Alunos</span><strong>${integer(row.active_students)}</strong>${editable()?`<button class="table-action compact" data-economics-edit="${row.period_offering_id}">Editar</button>`:''}</div><div><span>Receita</span><strong>${money(row.revenue)}</strong></div><div><span>Custo</span><strong>${money(row.allocated_cost)}</strong></div><div><span>Resultado</span><strong>${money(row.economic_result)}</strong></div><div><span>Margem</span><strong>${percent(row.margin_percent)}</strong></div></div>`).join('');return `<article class="course-result-card ${expanded?'expanded':''}" data-course-name="${escapeHtml(name)}"><button class="course-result-head" type="button" data-course-toggle="${escapeHtml(name)}" aria-expanded="${expanded?'true':'false'}"><div class="course-result-title"><strong>${escapeHtml(name)}</strong><span>${offers.length} contexto(s) neste mês</span></div><div class="course-result-metrics"><div><span>Alunos</span><strong>${integer(agg.active_students)}</strong></div><div><span>Receita</span><strong>${money(agg.revenue)}</strong></div><div><span>Custo</span><strong>${money(agg.allocated_cost)}</strong></div><div class="${resultClass}"><span>Resultado</span><strong>${money(agg.economic_result)}</strong></div><div><span>Margem</span><strong>${percent(agg.margin_percent)}</strong></div></div><span class="course-result-chevron">›</span></button><div class="course-offer-list ${expanded?'':'hidden'}">${details}</div></article>`;}).join('');
  }

  function renderAll(){renderPeriodFilter();renderContext();renderCards();renderCourseList();}

  async function refresh({periodId=null}={}){const pid=periodId||state.costEconomics.periodId||state.costEngine?.selectedPeriodId||null;const params={};if(pid)params.period_id=pid;const payload=await api('/api/dpe/cost-engine/economics-central',{},params);state.costEconomics.data=payload;state.costEconomics.periodId=payload.selected_period?.id||null;state.costEconomics.loaded=true;renderAll();return payload;}
  function editRow(id){return (data().rows||[]).find(row=>String(row.period_offering_id)===String(id));}

  function openEdit(periodOfferingId){
    if(!editable())return;const row=editRow(periodOfferingId);if(!row)return;const eco=row.economics||{};
    modalOpen('Alunos ativos',`${period()?.period||''} · ${row.product?.name||''} · ${courseOfferLabel(row)}`,`<form id="economicsEditForm" class="form-grid dpe-measurement-form courses-economics-form">
      <div class="span-2 courses-form-intro"><strong>Receita não é editada aqui.</strong><span>Esta tela mantém somente o dado auxiliar de alunos. Para alterar valores financeiros, use Receitas.</span></div>
      <label><span>Alunos ativos</span><input id="ecoActive" type="number" min="0" step="1" value="${eco.active_students??''}" placeholder="Ex.: 210"></label>
      <label><span>Origem</span><select id="ecoSource">${Object.entries(SOURCE_LABELS).map(([value,label])=>`<option value="${value}" ${String(eco.source_type||'MANUAL')===value?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>
      <label class="span-2"><span>Referência da origem</span><input id="ecoReference" maxlength="255" value="${escapeHtml(eco.source_reference||'')}" placeholder="Arquivo, processo ou identificador externo"></label>
      <label class="span-2"><span>Observações</span><textarea id="ecoNotes" rows="3">${escapeHtml(eco.notes||'')}</textarea></label>
      <div id="economicsFormErrors" class="form-errors span-2 hidden"></div>
      <div class="form-actions"><button type="button" class="button secondary" data-close-modal="costEngineModal">Cancelar</button><button type="submit" class="button primary">Salvar alunos</button></div>
    </form>`,'DPE · DADOS AUXILIARES');
    $('#economicsEditForm').addEventListener('submit',async event=>{event.preventDefault();const payload={active_students:$('#ecoActive').value===''?null:Number($('#ecoActive').value),source_type:$('#ecoSource').value,source_reference:$('#ecoReference').value||null,notes:$('#ecoNotes').value||null};setLoading(true);try{await api(`/api/dpe/cost-engine/periods/${currentPeriodId()}/offerings/${periodOfferingId}/economics`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});modalClose();showAlert('Alunos atualizados.','success');await refresh({periodId:currentPeriodId()});if(typeof window.refreshDPECostAllocation==='function')await window.refreshDPECostAllocation({periodId:currentPeriodId(),runId:null});}catch(error){showFormError(error);}finally{setLoading(false);}});
  }

  function bind(){
    $('#economicsPeriodFilter')?.addEventListener('change',async event=>{state.costEconomics.periodId=Number(event.target.value)||null;setLoading(true);try{await refresh({periodId:state.costEconomics.periodId});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});
    document.addEventListener('click',event=>{const toggle=event.target.closest('[data-course-toggle]');if(toggle){const name=toggle.dataset.courseToggle;if(state.costEconomics.expandedProducts.has(name))state.costEconomics.expandedProducts.delete(name);else state.costEconomics.expandedProducts.add(name);renderCourseList();return;}const edit=event.target.closest('[data-economics-edit]');if(edit){openEdit(edit.dataset.economicsEdit);return;}});
  }
  async function initialize(){bind();try{await refresh();}catch(error){showAlert(`Cursos DPE: ${error.message}`,'error',0);}}
  window.initializeDPECostEconomics=initialize;window.refreshDPECostEconomics=refresh;
})();
