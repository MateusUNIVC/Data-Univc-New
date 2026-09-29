const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];

const state = {
  user: null,
  access: null,
  catalog: null,
  domain: null,
  indicators: {},
  reference: '',
  courseCatalog: [],
  targets: [],
  actions: [],
  managementLoaded: false,
  managementLoading: null,
};

const DIMENSION_LABELS = {
  course: 'Curso', academic_directorate: 'Diretoria acadêmica', modality: 'Modalidade', shift: 'Turno',
  cost_center: 'Centro de custo', expense_nature: 'Natureza da despesa', category: 'Categoria', nature: 'Natureza',
};
const COLORS = ['#0e8058', '#3d8d79', '#7f8c8d', '#d6a93f', '#4477a6', '#ba4b50'];

function escapeHtml(value='') {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function url(path, params={}) {
  const output = new URL(path, location.origin);
  output.searchParams.set('diretoria', 'DPE');
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') output.searchParams.set(key, value);
  });
  return output.pathname + output.search;
}
async function api(path, options={}, params={}) {
  const response = await window.DataUnivcAuth.fetch(url(path, params), {credentials:'same-origin', ...options, headers:{'Accept':'application/json', ...(options.headers || {})}});
  if (response.status === 401) { location.assign('/'); throw new Error('Sessão expirada.'); }
  if (!response.ok) {
    let payload = null;
    try { payload = await response.json(); } catch {}
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : detail?.erro || payload?.erro || `Erro HTTP ${response.status}`;
    const error = new Error(message);
    error.payload = payload;
    throw error;
  }
  const type = response.headers.get('content-type') || '';
  return type.includes('application/json') ? response.json() : response;
}

let dpeLoadingDepth = 0;
let dpeAlertTimer = null;
let dpeLastModalTrigger = null;
let dpeConfirmResolver = null;

function setLoading(active) {
  dpeLoadingDepth = Math.max(0, dpeLoadingDepth + (active ? 1 : -1));
  const busy = dpeLoadingDepth > 0;
  $('#dpeLoading')?.classList.toggle('hidden', !busy);
  $('#dpeBusyStatus')?.classList.toggle('hidden', !busy);
  $('.main-content')?.setAttribute('aria-busy', busy ? 'true' : 'false');
  const save = $('#dpeSaveState');
  if (save) {
    save.classList.toggle('is-busy', busy);
    save.innerHTML = busy ? '<span class="status-dot"></span> Atualizando…' : '<span class="status-dot"></span> Sincronizado';
  }
}
function showAlert(message, kind='error', timeout=6500) {
  const box = $('#dpeAlert');
  if (!box) return;
  if (dpeAlertTimer) { clearTimeout(dpeAlertTimer); dpeAlertTimer = null; }
  const config = {
    success: {icon:'✓', title:'Concluído'},
    error: {icon:'!', title:'Não foi possível concluir'},
    warning: {icon:'!', title:'Atenção'},
    info: {icon:'i', title:'Informação'},
  }[kind] || {icon:'i', title:'Informação'};
  box.className = `dpe-alert ${kind}`;
  box.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  box.setAttribute('aria-live', kind === 'error' ? 'assertive' : 'polite');
  box.innerHTML = `<span class="dpe-alert-icon" aria-hidden="true">${config.icon}</span><span class="dpe-alert-copy"><strong>${escapeHtml(config.title)}</strong><span>${escapeHtml(message)}</span></span><button type="button" class="dpe-alert-close" aria-label="Fechar aviso">×</button>`;
  box.classList.remove('hidden');
  box.querySelector('.dpe-alert-close')?.addEventListener('click', () => box.classList.add('hidden'), {once:true});
  if (kind === 'error') box.focus({preventScroll:true});
  if (timeout) dpeAlertTimer = setTimeout(() => box.classList.add('hidden'), timeout);
}
function dpeFocusable(root) {
  return [...root.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(el => !el.hidden && el.offsetParent !== null);
}
function openDPEModal(id, {focusSelector=null}={}) {
  const modal = typeof id === 'string' ? $(`#${id}`) : id;
  if (!modal) return;
  dpeLastModalTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden','false');
  document.body.classList.add('dpe-modal-open');
  requestAnimationFrame(() => {
    const target = (focusSelector && modal.querySelector(focusSelector)) || dpeFocusable(modal)[0] || modal.querySelector('.modal-card');
    if (target) { if (!target.hasAttribute('tabindex') && target.classList.contains('modal-card')) target.setAttribute('tabindex','-1'); target.focus({preventScroll:true}); }
  });
}
function closeDPEModal(id) {
  const modal = typeof id === 'string' ? $(`#${id}`) : id;
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden','true');
  if (!document.querySelector('.modal:not(.hidden)')) document.body.classList.remove('dpe-modal-open');
  if (dpeLastModalTrigger?.isConnected) requestAnimationFrame(() => dpeLastModalTrigger.focus({preventScroll:true}));
}
function focusInlineError(box, message) {
  if (!box) return false;
  box.textContent = message || 'Revise os campos destacados.';
  box.classList.remove('hidden');
  box.setAttribute('role','alert');
  box.setAttribute('tabindex','-1');
  box.focus({preventScroll:false});
  return true;
}
function dpeEmptyState(title, detail='') {
  return `<div class="dpe-empty-state"><span class="dpe-empty-icon" aria-hidden="true">—</span><div><strong>${escapeHtml(title)}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ''}</div></div>`;
}
function dpeEmptyRow(colspan, title, detail='') {
  return `<tr><td colspan="${Number(colspan)||1}">${dpeEmptyState(title, detail)}</td></tr>`;
}
window.openDPEModal = openDPEModal;
window.closeDPEModal = closeDPEModal;
window.focusDPEInlineError = focusInlineError;
window.dpeEmptyState = dpeEmptyState;
window.dpeEmptyRow = dpeEmptyRow;

function resolveDPEConfirmation(value) {
  if (!dpeConfirmResolver) { closeDPEModal('dpeConfirmModal'); return; }
  const resolver = dpeConfirmResolver;
  dpeConfirmResolver = null;
  closeDPEModal('dpeConfirmModal');
  resolver(value);
}
function requestDPEConfirmation({title='Confirmar ação',message='',confirmLabel='Confirmar',eyebrow='CONFIRMAÇÃO',tone='warning',reasonLabel='',reasonHelp='',reasonRequired=false}={}) {
  if (dpeConfirmResolver) resolveDPEConfirmation(false);
  const modal=$('#dpeConfirmModal'); if(!modal) return Promise.resolve(false);
  $('#dpeConfirmTitle').textContent=title; $('#dpeConfirmMessage').textContent=message; $('#dpeConfirmEyebrow').textContent=eyebrow; $('#dpeConfirmAccept').textContent=confirmLabel;
  modal.querySelector('.dpe-confirm-card')?.classList.toggle('is-danger',tone==='danger');
  const wrap=$('#dpeConfirmReasonWrap'),reason=$('#dpeConfirmReason'),error=$('#dpeConfirmError');
  if(wrap){wrap.classList.toggle('hidden',!reasonLabel);$('#dpeConfirmReasonLabel').textContent=reasonLabel||'Justificativa';$('#dpeConfirmReasonHelp').textContent=reasonHelp||(reasonRequired?'Este campo é obrigatório.':'Opcional.');}
  if(reason){reason.value='';reason.required=Boolean(reasonRequired);}
  if(error){error.classList.add('hidden');error.textContent='';}
  return new Promise(resolve=>{dpeConfirmResolver=resolve;openDPEModal('dpeConfirmModal',{focusSelector:reasonLabel?'#dpeConfirmReason':'#dpeConfirmAccept'});});
}
function acceptDPEConfirmation(){
  const reason=$('#dpeConfirmReason'),wrap=$('#dpeConfirmReasonWrap'),error=$('#dpeConfirmError');
  const asksReason=wrap&&!wrap.classList.contains('hidden');
  if(asksReason&&reason?.required&&!reason.value.trim()){focusInlineError(error,'Informe uma justificativa antes de continuar.');reason.focus();return;}
  resolveDPEConfirmation(asksReason?(reason?.value.trim()||''):true);
}
window.requestDPEConfirmation=requestDPEConfirmation;

function formatCompactMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('pt-BR', {style:'currency', currency:'BRL', notation:'compact', maximumFractionDigits:1});
}
function option(value, label=value, selected=false) { return `<option value="${escapeHtml(value)}" ${selected?'selected':''}>${escapeHtml(label)}</option>`; }
function routeForDirectorate(code) { return window.DataUnivcIdentity.routeForDirectorate(code); }
function indicatorSpec(code) { return state.indicators[code]; }
function activeManagementIndicators() { return Object.values(state.indicators).filter(item => !item.legacy && item.targetable !== false); }
function indicatorLabel(code) { const item=indicatorSpec(code); return item ? (item.short_name || item.name || code) : code; }
function metricOf(code, key) { return (indicatorSpec(code)?.metrics || []).find(metric => metric.key === key); }
function courseOptionRows(selected='') {
  const rows = state.courseCatalog || [];
  const selectedKnown = rows.some(row => row.name === selected);
  const legacy = selected && !selectedKnown ? option(selected, `${selected} · cadastro anterior`, true) : '';
  return `<option value="">Selecione um curso</option>${legacy}` + rows.map(row => option(row.name, `${row.name} · ${row.directorate_code}`, row.name===selected)).join('');
}
function renderDimensionField(code, key, value='') {
  const label = DIMENSION_LABELS[key] || key;
  if (key==='course') return `<label><span>${escapeHtml(label)}</span><select data-dimension-key="course">${courseOptionRows(value)}</select><small>Opcional. Use quando a meta ou o plano for específico de um curso.</small></label>`;
  if (key==='academic_directorate') return `<label><span>${escapeHtml(label)}</span><input data-dimension-key="academic_directorate" value="${escapeHtml(value)}" readonly><small>Preenchida automaticamente quando um curso for selecionado.</small></label>`;
  return `<label><span>${escapeHtml(label)}</span><input data-dimension-key="${escapeHtml(key)}" value="${escapeHtml(value)}"></label>`;
}

async function initialize() {
  setLoading(true);
  try {
    state.user = await window.DataUnivcIdentity.load();
    if (!state.user) { location.assign('/'); return; }
    state.access = state.user.directorateFor('DPE');
    if (!state.access) { window.DataUnivcIdentity.redirectToAuthorizedHome(state.user); return; }
    renderUser();
    applyAccess();
    const [catalog, domain] = await Promise.all([api('/api/management/catalog'), api('/api/dpe/domain')]);
    state.catalog = catalog.directorates.DPE;
    state.domain = domain;
    state.indicators = Object.fromEntries((state.catalog?.indicators || []).map(item => [item.code, item]));
    try { state.courseCatalog = (await api('/api/dpe/courses')).items || []; } catch { state.courseCatalog = []; }
    bindEvents();
    if (typeof window.initializeDPECostEngine === 'function') await window.initializeDPECostEngine();
    if (typeof window.initializeDPECostExpenses === 'function') await window.initializeDPECostExpenses();
    if (typeof window.initializeDPECostTeaching === 'function') await window.initializeDPECostTeaching();
    if (typeof window.initializeDPECostAllocation === 'function') await window.initializeDPECostAllocation();
    if (typeof window.initializeDPECostRevenues === 'function') await window.initializeDPECostRevenues();
    if (typeof window.initializeDPECostEconomics === 'function') await window.initializeDPECostEconomics();
    if (typeof window.initializeDPECostClosure === 'function') await window.initializeDPECostClosure();
    if (typeof window.initializeDPECostProductivity === 'function') await window.initializeDPECostProductivity();
    if (typeof window.initializeDPEV2 === 'function') await window.initializeDPEV2();
    if (typeof window.initializeDPECostAnalytics === 'function') await window.initializeDPECostAnalytics();
    let initialSection='dashboard';
    try { const stored=sessionStorage.getItem(DPE_NAV_STORAGE_KEY); if(stored&&document.getElementById(`section-${stored}`)) initialSection=stored; } catch {}
    if(initialSection==='dashboard') updateSectionChrome('dashboard'); else await navigate(initialSection,{persist:false,scroll:false});
  } catch (error) { showAlert(error.message, 'error', 0); }
  finally { setLoading(false); }
}
function renderUser() {
  const name = state.user?.name || state.user?.email || 'Usuário';
  $('#dpeUserName').textContent = name;
  $('#dpeUserMeta').textContent = `${state.user?.roleLabel || 'Diretoria'} · ${state.access?.canEdit ? 'Edição' : 'Leitura'}`;
  $('#dpeUserDirectorate').textContent = state.access?.name || 'Diretoria de Planejamento Econômico e Oferta';
  window.DataUnivcIdentity.applyAvatar($('#dpeUserAvatar'), state.user);
  $('#dpeUserMini')?.setAttribute('title', [state.user?.email, state.access?.name].filter(Boolean).join(' · '));
  const select = $('#dpeDirectorateSelect');
  if (select) {
    select.innerHTML = state.user.availableDirectorates.map(item => option(item.code, `${item.code} · ${item.name} · ${item.canEdit ? 'Edição' : 'Leitura'}`, item.code === 'DPE')).join('');
    select.disabled = state.user.availableDirectorates.length <= 1;
    select.closest('.directorate-switcher')?.classList.toggle('hidden', !state.user.shouldShowSwitcher());
  }
  const badge=$('#dpeDirectorateAccessBadge'); if(badge) badge.textContent=state.access?.canEdit?'Edição':'Somente leitura';
}
function applyAccess() {
  const canWrite = Boolean(state.access?.canEdit);
  document.body.classList.toggle('write-enabled', canWrite);
  $('#dpeReadOnly')?.classList.toggle('hidden', canWrite);
  const badge=$('#dpeDirectorateAccessBadge'); if(badge) badge.textContent=canWrite?'Edição':'Leitura';
  $$('[data-write-action]').forEach(element => {
    element.hidden = !canWrite; element.disabled = !canWrite;
    if (!canWrite) element.setAttribute('title', 'Acesso somente leitura'); else element.removeAttribute('title');
  });
}

function managementMetricList(code){return (indicatorSpec(code)?.metrics||[]).filter(metric=>!metric.legacy_metric&&metric.targetable!==false)}
function managementMetricOptions(code,selected=''){return managementMetricList(code).map(item=>option(item.key,`${item.label}${item.unit?` (${item.unit})`:''}`,item.key===selected)).join('')}
function managementDimensions(code,metricKey){const metric=metricOf(code,metricKey)||{};return Array.isArray(metric.dimensions)?metric.dimensions:[]}
function managementDimensionFields(code,metricKey,values={}){const keys=managementDimensions(code,metricKey);return keys.map(key=>renderDimensionField(code,key,values?.[key]||'')).join('')||'<div class="span-2 field-help">Esta métrica é institucional e não exige dimensão adicional.</div>'}
function formatManagementValue(value,unit){if(value===null||value===undefined||Number.isNaN(Number(value)))return '—';const n=Number(value);if(unit==='R$')return n.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});if(unit==='%')return `${n.toLocaleString('pt-BR',{maximumFractionDigits:2})}%`;if(unit==='x')return `${n.toLocaleString('pt-BR',{maximumFractionDigits:2})}x`;return `${n.toLocaleString('pt-BR',{maximumFractionDigits:2})}${unit?` ${unit}`:''}`}
function formatTarget(item){const metric=metricOf(item.indicator_code,item.metric_key)||{};const unit=metric.unit;if(item.target_min!=null||item.target_max!=null)return `${formatManagementValue(item.target_min,unit)} a ${formatManagementValue(item.target_max,unit)}`;return formatManagementValue(item.target,unit)}
function managementStatusChip(status){const key=status?.key||'UNAVAILABLE';const cls={GOOD:'good',ATTENTION:'attention',BAD:'critical',INACTIVE:'neutral',INFO:'info',UNAVAILABLE:'neutral'}[key]||'neutral';return `<span class="status-chip ${cls}">${escapeHtml(status?.label||'Sem apuração')}</span>`}
function summaryCard(label,value,detail='',tone='info'){return `<article class="metric-card management-summary-card ${tone}"><span class="metric-label">${escapeHtml(label)}</span><strong class="metric-value">${escapeHtml(String(value))}</strong>${detail?`<span class="metric-sub">${escapeHtml(detail)}</span>`:''}</article>`}
function renderManagementSummary(payload){const target=payload.target_summary||{},action=payload.action_summary||{};const targetRoot=$('#targetSummary'),actionRoot=$('#actionSummary'),periodRoot=$('#targetPeriodContext');if(periodRoot){const p=payload.selected_period;periodRoot.innerHTML=p?`<strong>Competência avaliada: ${escapeHtml(p.period)}</strong><span>${escapeHtml(p.status||'')}</span><small>Os valores atuais vêm diretamente do Cost Engine; não existe lançamento manual de KPI.</small>`:'<strong>Nenhuma competência disponível.</strong>'}if(targetRoot)targetRoot.innerHTML=[summaryCard('Metas vigentes',target.active||0,'na competência selecionada','info'),summaryCard('Dentro da meta',target.good||0,'resultado satisfatório','good'),summaryCard('Atenção',target.attention||0,'acompanhar de perto','attention'),summaryCard('Fora da meta',target.bad||0,'requer decisão','critical')].join('');if(actionRoot)actionRoot.innerHTML=[summaryCard('Abertos',action.open||0,'aguardando execução','info'),summaryCard('Em andamento',action.in_progress||0,'ações em execução','info'),summaryCard('Atrasados',action.overdue||0,'prazo vencido','critical'),summaryCard('Concluídos',action.completed||0,'ações finalizadas','good')].join('')}
function renderTargets(){const root=$('#targetsTable');if(!root)return;const items=state.targets||[];root.innerHTML=items.length?items.map(item=>{const current=formatManagementValue(item.current_value,item.unit);const scope=item.dimension_label&&item.dimension_label!=='TOTAL'?item.dimension_label:'Institucional';const planAllowed=item.active_for_period&&['BAD','ATTENTION'].includes(item.status?.key);return `<tr class="${item.active_for_period?'':'management-inactive-row'}"><td><strong>${escapeHtml(item.indicator_label||indicatorLabel(item.indicator_code))}</strong><small>${escapeHtml(item.metric_label||item.metric_key)}</small></td><td>${escapeHtml(scope)}</td><td><strong>${escapeHtml(current)}</strong></td><td>${escapeHtml(formatTarget(item))}</td><td>${managementStatusChip(item.status)}</td><td>${escapeHtml(item.valid_from)}${item.valid_to?` a ${escapeHtml(item.valid_to)}`:' em diante'}</td><td><div class="table-actions">${state.access?.canEdit&&planAllowed?`<button class="table-action" data-plan-target="${item.id}" data-write-action>Criar plano</button>`:''}${state.access?.canEdit?`<button class="table-action danger" data-delete-target="${item.id}" data-write-action>Excluir</button>`:''}</div></td></tr>`}).join(''):dpeEmptyRow(7,'Nenhuma meta cadastrada','Crie metas para os indicadores reais da DPE.');applyAccess()}
function renderActions(){const root=$('#actionsTable');if(!root)return;const items=state.actions||[];root.innerHTML=items.length?items.map(item=>`<tr><td><strong>${escapeHtml(item.indicator_label||indicatorLabel(item.indicator_code))}</strong><small>${escapeHtml(item.metric_label||item.metric_key||'')}</small></td><td>${escapeHtml(item.period||'—')}</td><td>${escapeHtml(item.problem||'')}</td><td>${escapeHtml(item.corrective_action||'')}</td><td>${escapeHtml(item.responsible||'')}</td><td>${escapeHtml(item.due_date||'—')}</td><td><span class="status-chip ${item.is_overdue?'critical':String(item.effective_status||'').toLowerCase().includes('conclu')?'good':'info'}">${escapeHtml(item.effective_status||item.status||'')}</span></td><td>${state.access?.canEdit?`<button class="table-action danger" data-delete-action="${item.id}" data-write-action>Excluir</button>`:''}</td></tr>`).join(''):dpeEmptyRow(8,'Nenhum plano de ação cadastrado','Crie um plano manualmente ou a partir de uma meta em atenção/fora da meta.');applyAccess()}
async function loadManagementOverview(){const params={};if(state.dpeV2?.periodId)params.period_id=state.dpeV2.periodId;const payload=await api('/api/dpe/management/overview',{},params);state.managementOverview=payload;state.managementPeriodId=payload.selected_period?.id||null;state.targets=payload.targets||[];state.actions=payload.actions||[];if(payload.selected_period?.period)state.reference=payload.selected_period.period;renderManagementSummary(payload);renderTargets();renderActions();return payload}
async function loadTargets(){try{return await loadManagementOverview()}catch(error){showAlert(error.message);throw error}}
async function loadActions(){try{return await loadManagementOverview()}catch(error){showAlert(error.message);throw error}}
function managementIndicatorOptions(selected='DPE-RESULT'){return activeManagementIndicators().map(item=>option(item.code,item.short_name||item.name,item.code===selected)).join('')}
function targetLimitFields(code,metricKey){const metric=metricOf(code,metricKey)||{};if(metric.direction==='range')return `<label><span>Meta mínima *</span><input id="targetMin" type="number" step="any" required value="${metric.target_min??''}"></label><label><span>Meta máxima *</span><input id="targetMax" type="number" step="any" required value="${metric.target_max??''}"></label><label><span>Atenção mínima</span><input id="attentionMin" type="number" step="any" value="${metric.attention_min??''}"></label><label><span>Atenção máxima</span><input id="attentionMax" type="number" step="any" value="${metric.attention_max??''}"></label>`;return `<label><span>Meta *</span><input id="targetValue" type="number" step="any" required value="${metric.target??''}"></label><label><span>Limite de atenção</span><input id="attentionValue" type="number" step="any" value="${metric.attention??''}"></label>`}
function openManagementModal(title,eyebrow,subtitle,html){$('#managementModalTitle').textContent=title;$('#managementModalEyebrow').textContent=eyebrow;$('#managementModalSubtitle').textContent=subtitle;$('#managementModalBody').innerHTML=html;openDPEModal('managementModal')}
function targetFormHtml(code='DPE-RESULT',metricKey=''){const first=metricKey||managementMetricList(code)?.[0]?.key||'';return `<form id="targetForm" class="form-grid dpe-measurement-form"><label class="span-2"><span>Indicador *</span><select id="targetIndicator" required>${managementIndicatorOptions(code)}</select></label><label class="span-2"><span>Métrica *</span><select id="targetMetric" required>${managementMetricOptions(code,first)}</select></label><label><span>Vigência inicial *</span><input id="targetValidFrom" placeholder="AAAA-MM" required value="${state.reference||''}"></label><label><span>Vigência final</span><input id="targetValidTo" placeholder="AAAA-MM"></label><div id="targetDimensions" class="form-grid span-2 nested-grid">${managementDimensionFields(code,first)}</div><div id="targetLimits" class="form-grid span-2 nested-grid">${targetLimitFields(code,first)}</div><label class="span-2"><span>Justificativa</span><textarea id="targetJustification" placeholder="Contexto da meta ou decisão de gestão."></textarea></label><div id="targetFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="managementModal">Cancelar</button><button type="submit" class="button primary">Salvar meta</button></div></form>`}
function openTargetForm(){openManagementModal('Nova meta','DPE · META','A meta será comparada automaticamente com os dados reais da competência.',targetFormHtml());bindTargetForm()}
function bindTargetForm(){const form=$('#targetForm');const rebuild=()=>{const code=$('#targetIndicator').value;const current=$('#targetMetric')?.value;const metric=managementMetricList(code).some(item=>item.key===current)?current:(managementMetricList(code)?.[0]?.key||'');$('#targetMetric').innerHTML=managementMetricOptions(code,metric);$('#targetDimensions').innerHTML=managementDimensionFields(code,metric);$('#targetLimits').innerHTML=targetLimitFields(code,metric);bindManagementCourseSync('#targetForm')};$('#targetIndicator').addEventListener('change',rebuild);$('#targetMetric').addEventListener('change',()=>{const code=$('#targetIndicator').value,key=$('#targetMetric').value;$('#targetDimensions').innerHTML=managementDimensionFields(code,key);$('#targetLimits').innerHTML=targetLimitFields(code,key);bindManagementCourseSync('#targetForm')});bindManagementCourseSync('#targetForm');form.addEventListener('submit',saveTarget)}
function dimensionsFrom(root){const result={};$$('[data-dimension-key]',root).forEach(field=>{const value=field.value?.trim();if(value)result[field.dataset.dimensionKey]=value});return result}
function bindManagementCourseSync(rootSelector){const root=$(rootSelector);if(!root)return;const course=$('[data-dimension-key="course"]',root),directorate=$('[data-dimension-key="academic_directorate"]',root);if(course&&directorate){const sync=()=>{const found=(state.courseCatalog||[]).find(row=>row.name===course.value);directorate.value=found?.directorate_code||''};course.addEventListener('change',sync);sync()}}
async function saveTarget(event){event.preventDefault();const code=$('#targetIndicator').value,key=$('#targetMetric').value,metric=metricOf(code,key)||{};const payload={indicator_code:code,metric_key:key,valid_from:$('#targetValidFrom').value,valid_to:$('#targetValidTo').value||null,dimensions:dimensionsFrom($('#targetForm')),justification:$('#targetJustification').value.trim()||null};if(metric.direction==='range'){payload.target_min=$('#targetMin').value;payload.target_max=$('#targetMax').value;payload.attention_min=$('#attentionMin').value||null;payload.attention_max=$('#attentionMax').value||null}else{payload.target=$('#targetValue').value;payload.attention=$('#attentionValue').value||null}try{await api('/api/management/targets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeDPEModal('managementModal');showAlert('Meta salva com sucesso.','success');await loadManagementOverview()}catch(error){focusInlineError($('#targetFormErrors'),error.message)}}
function actionFormHtml(code='DPE-RESULT',metricKey='',dimensions={},problem=''){const first=metricKey||managementMetricList(code)?.[0]?.key||'';return `<form id="actionForm" class="form-grid dpe-measurement-form"><label class="span-2"><span>Indicador *</span><select id="actionIndicator" required>${managementIndicatorOptions(code)}</select></label><label class="span-2"><span>Métrica *</span><select id="actionMetric" required>${managementMetricOptions(code,first)}</select></label><label><span>Competência *</span><input id="actionPeriod" placeholder="AAAA-MM" required value="${state.reference||''}"></label><div id="actionDimensions" class="form-grid span-2 nested-grid">${managementDimensionFields(code,first,dimensions)}</div><label class="span-2"><span>Problema identificado *</span><textarea id="actionProblem" required>${escapeHtml(problem)}</textarea></label><label class="span-2"><span>Causa provável</span><textarea id="actionCause"></textarea></label><label class="span-2"><span>Ação corretiva *</span><textarea id="actionCorrective" required></textarea></label><label><span>Responsável *</span><input id="actionResponsible" required></label><label><span>Prazo *</span><input id="actionDueDate" type="date" required></label><label><span>Status</span><select id="actionStatus"><option>Aberto</option><option>Em andamento</option><option>Concluído</option><option>Cancelado</option></select></label><label><span>Evidência / observação</span><input id="actionEvidence"></label><div id="actionFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="managementModal">Cancelar</button><button type="submit" class="button primary">Salvar plano</button></div></form>`}
function openActionForm(prefill={}){const code=prefill.code||'DPE-RESULT',metricKey=prefill.metricKey||'';openManagementModal('Novo plano de ação','DPE · PLANO','Vincule o plano a uma métrica real, com responsável e prazo.',actionFormHtml(code,metricKey,prefill.dimensions||{},prefill.problem||''));bindActionForm(prefill.dimensions||{})}
function bindActionForm(initialDimensions={}){const form=$('#actionForm');const rebuild=(keep={})=>{const code=$('#actionIndicator').value;const current=$('#actionMetric')?.value;const metric=managementMetricList(code).some(item=>item.key===current)?current:(managementMetricList(code)?.[0]?.key||'');$('#actionMetric').innerHTML=managementMetricOptions(code,metric);$('#actionDimensions').innerHTML=managementDimensionFields(code,metric,keep);bindManagementCourseSync('#actionForm')};$('#actionIndicator').addEventListener('change',()=>rebuild({}));$('#actionMetric').addEventListener('change',()=>rebuild({}));bindManagementCourseSync('#actionForm');form.addEventListener('submit',saveAction)}
async function saveAction(event){event.preventDefault();const payload={indicator_code:$('#actionIndicator').value,metric_key:$('#actionMetric').value,period:$('#actionPeriod').value,dimensions:dimensionsFrom($('#actionForm')),problem:$('#actionProblem').value.trim(),probable_cause:$('#actionCause').value.trim()||null,corrective_action:$('#actionCorrective').value.trim(),responsible:$('#actionResponsible').value.trim(),due_date:$('#actionDueDate').value,status:$('#actionStatus').value,evidence:$('#actionEvidence').value.trim()||null};try{await api('/api/management/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeDPEModal('managementModal');showAlert('Plano de ação salvo com sucesso.','success');await loadManagementOverview()}catch(error){focusInlineError($('#actionFormErrors'),error.message)}}
async function deleteTarget(id){const confirmed=await requestDPEConfirmation({title:'Excluir meta?',message:'A meta será removida do histórico de gestão. Confirme somente se ela não deve mais ser utilizada.',confirmLabel:'Excluir meta',tone:'danger'});if(!confirmed)return;try{await api(`/api/management/targets/${id}`,{method:'DELETE'});showAlert('Meta excluída.','success');await loadManagementOverview()}catch(error){showAlert(error.message)}}
async function deleteAction(id){const confirmed=await requestDPEConfirmation({title:'Excluir plano de ação?',message:'O plano de ação será removido. Esta operação não altera os dados financeiros do mês.',confirmLabel:'Excluir plano',tone:'danger'});if(!confirmed)return;try{await api(`/api/management/actions/${id}`,{method:'DELETE'});showAlert('Plano excluído.','success');await loadManagementOverview()}catch(error){showAlert(error.message)}}
async function ensureManagementLoaded(){const desired=state.dpeV2?.periodId||null;if(state.managementLoaded&&state.managementPeriodId===desired)return;if(state.managementLoading)return state.managementLoading;state.managementLoading=(async()=>{setLoading(true);try{await loadManagementOverview();state.managementLoaded=true}finally{state.managementLoading=null;setLoading(false)}})();return state.managementLoading}

const DPE_SECTION_META={
  dashboard:{title:'Visão geral',subtitle:'Resultado do mês, pendências e próximos passos.'},
  'receita-operacional':{title:'Receitas',subtitle:'Receitas de cursos e outras entradas do mês.',quick:{label:'+ Outra receita',focus:'#otherRevenueDescription',write:true}},
  'central-despesas':{title:'Despesas',subtitle:'Registre, confira e classifique os gastos do mês.',quick:{label:'+ Nova despesa',target:'#newCostExpense',write:true}},
  docencia:{title:'Docência',subtitle:'Atividades, vínculos e custos docentes da competência.',quick:{label:'+ Atividade',target:'#newTeachingActivity',write:true}},
  rateio:{title:'Distribuição de custos',subtitle:'Defina como os custos diretos e compartilhados chegam aos cursos.',quick:{label:'Atualizar distribuição',target:'#calculateAllocationRun',write:true}},
  fechamento:{title:'Fechamento',subtitle:'Confira pendências, consolide os cálculos e proteja o histórico.'},
  economia:{title:'Resultado por curso',subtitle:'Receita, custo, resultado e margem de cada curso/contexto.',quick:{label:'Editar receitas',go:'receita-operacional',write:false}},
  metas:{title:'Metas',subtitle:'Compare os indicadores reais da DPE com os objetivos definidos.',quick:{label:'+ Meta',target:'#newTarget',write:true}},
  planos:{title:'Planos de ação',subtitle:'Transforme desvios em ações, responsáveis e prazos.',quick:{label:'+ Plano',target:'#newAction',write:true}},
  competencias:{title:'Períodos e histórico',subtitle:'Abra competências e consulte o retrato preservado de cada mês.',quick:{label:'+ Abrir mês',target:'#newCostPeriod',write:true}},
  catalogo:{title:'Cursos e contextos',subtitle:'Cadastre a estrutura econômica usada pela DPE.',quick:{label:'+ Vincular curso',target:'#newCostProduct',write:true}},
  produtividade:{title:'Produtividade',subtitle:'Reaproveite dados recorrentes e reduza trabalho manual repetitivo.'},
  'politicas-rateio':{title:'Políticas de distribuição',subtitle:'Gerencie configurações reutilizáveis para custos recorrentes.'},
  governanca:{title:'Regras e governança',subtitle:'Entenda fechamento, histórico, auditoria e rastreabilidade.'},
};
const DPE_NAV_STORAGE_KEY='data-univc.dpe.section';
function updateSectionChrome(section){
  const meta=DPE_SECTION_META[section]||{title:'DPE',subtitle:'Planejamento econômico e acompanhamento mensal.'};
  const title=$('#dpePageTitle'),subtitle=$('#dpePageSubtitle');
  if(title)title.textContent=meta.title;if(subtitle)subtitle.textContent=meta.subtitle;
  $$('[data-flow-section]').forEach(item=>{const active=item.dataset.flowSection===section;item.classList.toggle('active',active);if(active)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current')});
  const quick=$('#dpeQuickAdd');if(!quick)return;
  const action=meta.quick||null;quick.dataset.section=section;
  quick.hidden=!action||(Boolean(action.write)&&!state.access?.canEdit);
  quick.disabled=!action||(Boolean(action.write)&&!state.access?.canEdit);
  if(action){quick.textContent=action.label;quick.dataset.quickMode=action.target?'target':action.focus?'focus':action.go?'go':'';quick.dataset.quickValue=action.target||action.focus||action.go||'';quick.classList.toggle('secondary',action.write===false);quick.classList.toggle('primary',action.write!==false);}else{quick.dataset.quickMode='';quick.dataset.quickValue='';}
}
function runSectionQuickAction(){
  const quick=$('#dpeQuickAdd');if(!quick||quick.hidden||quick.disabled)return;
  const mode=quick.dataset.quickMode,value=quick.dataset.quickValue;if(!mode||!value)return;
  if(mode==='go'){navigate(value);return;}
  const target=$(value);if(!target){showAlert('A ação desta área ainda não está disponível.','warning');return;}
  if(mode==='focus'){target.scrollIntoView({behavior:'smooth',block:'center'});target.focus({preventScroll:true});return;}
  if(target.disabled){showAlert(target.title||'Esta ação não está disponível no estado atual do mês.','warning');return;}
  target.click();
}
async function navigate(section,{persist=true,scroll=true}={}){if(!$(`#section-${section}`)){showAlert('Esta área não faz parte da DPE atual.','warning',3500);return;}$$('.nav-item[data-section]').forEach(item=>{const active=item.dataset.section===section;item.classList.toggle('active',active);if(active)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current')});$$('.page-section').forEach(item=>{const active=item.id===`section-${section}`;item.classList.toggle('active',active);item.setAttribute('aria-hidden',active?'false':'true')});const activeNav=$(`.nav-item[data-section="${section}"]`);const secondaryGroup=activeNav?.closest('.dpe-secondary-nav');if(secondaryGroup)secondaryGroup.open=true;updateSectionChrome(section);if(persist){try{sessionStorage.setItem(DPE_NAV_STORAGE_KEY,section)}catch{}}if(section==='dashboard'&&typeof window.refreshDPEV2==='function'&&state.dpeV2?.loaded)window.refreshDPEV2({periodId:state.dpeV2.periodId}).catch(()=>{});try{if(['planos','metas'].includes(section))await ensureManagementLoaded()}catch(error){showAlert(error.message,'error',0)}if(scroll)window.scrollTo({top:0,behavior:'smooth'})}
window.navigateDPE=navigate;

function bindAccessibleTabs(){$$('[role="tablist"]').forEach(tablist=>{const tabs=()=>$$('[role="tab"]',tablist).filter(tab=>!tab.disabled);tablist.addEventListener('keydown',event=>{if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;const items=tabs();if(!items.length)return;const current=Math.max(0,items.indexOf(document.activeElement));let next=current;if(event.key==='ArrowRight')next=(current+1)%items.length;if(event.key==='ArrowLeft')next=(current-1+items.length)%items.length;if(event.key==='Home')next=0;if(event.key==='End')next=items.length-1;event.preventDefault();items[next].focus();items[next].click()});tabs().forEach(tab=>tab.setAttribute('tabindex',tab.getAttribute('aria-selected')==='true'?'0':'-1'));tablist.addEventListener('click',event=>{const selected=event.target.closest('[role="tab"]');if(!selected)return;tabs().forEach(tab=>tab.setAttribute('tabindex',tab===selected?'0':'-1'))})})}
function trapModalFocus(event){if(event.key!=='Tab')return;const modal=['dpeConfirmModal','costEngineModal','managementModal'].map(id=>$(`#${id}`)).find(el=>el&&!el.classList.contains('hidden'));if(!modal)return;const focusable=dpeFocusable(modal);if(!focusable.length){event.preventDefault();modal.querySelector('.modal-card')?.focus();return}const first=focusable[0],last=focusable[focusable.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}
function bindEvents(){bindAccessibleTabs();$$('.page-section').forEach(section=>section.setAttribute('aria-hidden',section.classList.contains('active')?'false':'true'));$('.nav-item.active[data-section]')?.setAttribute('aria-current','page');$('#dpeDirectorateSelect')?.addEventListener('change',event=>location.assign(routeForDirectorate(event.target.value)));$$('.nav-item[data-section]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.section)));$$('[data-flow-section]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.flowSection)));$$('[data-go]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.go)));$('#dpeQuickAdd')?.addEventListener('click',runSectionQuickAction);$$('[data-close-modal]').forEach(button=>button.addEventListener('click',()=>closeDPEModal(button.dataset.closeModal)));['managementModal','costEngineModal'].forEach(id=>{const modal=$(`#${id}`);modal?.addEventListener('mousedown',event=>{if(event.target===modal)closeDPEModal(id)})});$('#dpeConfirmModal')?.addEventListener('mousedown',event=>{if(event.target===$('#dpeConfirmModal'))resolveDPEConfirmation(false)});$('#dpeConfirmCancel')?.addEventListener('click',()=>resolveDPEConfirmation(false));$('#dpeConfirmClose')?.addEventListener('click',()=>resolveDPEConfirmation(false));$('#dpeConfirmAccept')?.addEventListener('click',acceptDPEConfirmation);document.addEventListener('keydown',event=>{trapModalFocus(event);if(event.key!=='Escape')return;const open=['dpeConfirmModal','costEngineModal','managementModal'].find(id=>!$(`#${id}`)?.classList.contains('hidden'));if(open){event.preventDefault();if(open==='dpeConfirmModal')resolveDPEConfirmation(false);else closeDPEModal(open)}});document.addEventListener('click',async event=>{const plan=event.target.closest('[data-plan-target]');if(plan){const item=(state.targets||[]).find(row=>String(row.id)===String(plan.dataset.planTarget));if(item&&state.access?.canEdit)openActionForm({code:item.indicator_code,metricKey:item.metric_key,dimensions:item.fact?.dimensions||{},problem:`${item.metric_label||item.metric_key}: ${item.status?.label||'desvio'} na competência ${state.reference||''}. Valor atual ${formatManagementValue(item.current_value,item.unit)}; meta ${formatTarget(item)}.`});return}const targetDelete=event.target.closest('[data-delete-target]');if(targetDelete){if(state.access?.canEdit)await deleteTarget(targetDelete.dataset.deleteTarget);return}const actionDelete=event.target.closest('[data-delete-action]');if(actionDelete){if(state.access?.canEdit)await deleteAction(actionDelete.dataset.deleteAction);return}});$('#newTarget')?.addEventListener('click',()=>{if(state.access?.canEdit)openTargetForm()});$('#newAction')?.addEventListener('click',()=>{if(state.access?.canEdit)openActionForm()});$('#dpeLogout')?.addEventListener('click',async()=>{try{await window.DataUnivcAuth.logout()}finally{location.assign('/')}})}

document.addEventListener('DOMContentLoaded', initialize);
