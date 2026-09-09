const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];

const state = {
  directorate: new URLSearchParams(location.search).get('diretoria')?.toUpperCase() || 'DADM',
  user: null,
  access: null,
  catalog: null,
  directorateSpec: null,
  dashboard: null,
  measurements: [],
  measurementOffset: 0,
  measurementLimit: 100,
  measurementTotal: 0,
  measurementHasMore: false,
  targets: [],
  actions: [],
};

function escapeHtml(value='') {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function queryWithDirectorate(path, params={}) {
  const url = new URL(path, location.origin);
  url.searchParams.set('diretoria', state.directorate);
  Object.entries(params).forEach(([key,value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  });
  return url.pathname + url.search;
}
async function api(path, options={}, params={}) {
  const response = await window.DataUnivcAuth.fetch(queryWithDirectorate(path, params), {
    credentials: 'same-origin',
    ...options,
    headers: {'Accept':'application/json', ...(options.headers || {})},
  });
  if (response.status === 401) {
    location.assign('/');
    throw new Error('Sessão expirada.');
  }
  if (!response.ok) {
    let payload = null;
    try { payload = await response.json(); } catch {}
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : detail?.erro || payload?.erro || `Erro HTTP ${response.status}`;
    const error = new Error(message);
    error.fields = detail?.campos || payload?.campos || {};
    throw error;
  }
  const type = response.headers.get('content-type') || '';
  return type.includes('application/json') ? response.json() : response;
}
function showAlert(message, kind='error') {
  const box = $('#alert');
  box.textContent = message;
  box.classList.remove('hidden');
  box.style.background = kind === 'success' ? '#e4f2e9' : '#fdeceb';
  box.style.color = kind === 'success' ? '#17643f' : '#8d2b27';
  setTimeout(() => box.classList.add('hidden'), 5200);
}
function setLoading(active, message='Carregando o Data UNIVC') {
  $('#loading').classList.toggle('hidden', !active);
  if (active) $('#loading strong').textContent = message;
}
function accessFor(code) {
  return state.user?.directorateFor(code) || null;
}
function indicatorByCode(code) {
  return (state.directorateSpec?.indicators || []).find(item => item.code === code);
}
function metricByKey(indicator, key) {
  return (indicator?.metrics || []).find(item => item.key === key);
}
function statusClass(status='') {
  if (status === 'Dentro da meta') return 'good';
  if (status === 'Atenção') return 'attention';
  if (status === 'Fora da meta') return 'critical';
  return 'info';
}
function formatValue(value, unit='') {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  const number = Number(value);
  if (unit === 'R$') return number.toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:2});
  if (unit === '%') return `${number.toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}%`;
  if (unit === 'x' || unit === 'índice') return `${number.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}x`;
  if (['alunos','solicitações'].includes(unit)) return number.toLocaleString('pt-BR',{maximumFractionDigits:0});
  return `${number.toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}${unit ? ` ${unit}` : ''}`;
}
function option(value, label=value, selected=false) {
  return `<option value="${escapeHtml(value)}" ${selected?'selected':''}>${escapeHtml(label)}</option>`;
}
function getSelectedIndicator() {
  const code = $('#indicatorSelect')?.value || state.dashboard?.selected_indicator?.code;
  return indicatorByCode(code);
}

async function initialize() {
  setLoading(true);
  try {
    state.user = await window.DataUnivcIdentity.load();
    if (!state.user) { location.assign('/'); return; }
    const available = state.user.availableDirectorates.filter(item => ['DADM','DPE','DM'].includes(item.code));
    if (!available.some(item => item.code === state.directorate)) {
      state.directorate = available[0]?.code || '';
    }
    if (!state.directorate) {
      window.DataUnivcIdentity.redirectToAuthorizedHome(state.user);
      return;
    }
    state.access = accessFor(state.directorate);
    renderUser();
    renderDirectorateSelector(available);
    await loadCatalog();
    await loadDashboard();
    bindEvents();
    $('#app').classList.remove('hidden');
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

function renderUser() {
  const profileName = state.user?.name || state.user?.email || 'Usuário';
  $('#userName').textContent = profileName;
  $('#userRole').textContent = `${state.user?.roleLabel || 'Diretoria'} · ${state.access?.canEdit ? 'Edição' : 'Leitura'}`;
  $('#userDirectorate').textContent = state.access?.name || 'Acesso institucional';
  window.DataUnivcIdentity.applyAvatar($('#userAvatar'), state.user);
  $('#managementUserCard')?.setAttribute('title', [state.user?.email, state.access?.name].filter(Boolean).join(' · '));
}

function renderDirectorateSelector(available) {
  const select = $('#directorateSelect');
  select.innerHTML = available.map(item => option(item.code, `${item.code} · ${item.name} · ${item.canEdit ? 'Edição' : 'Leitura'}`, item.code === state.directorate)).join('');
  const showSwitcher = available.length > 1;
  select.classList.toggle('hidden', !showSwitcher);
  select.previousElementSibling?.classList.toggle('hidden', !showSwitcher);
  select.disabled = !showSwitcher;
  $('#readOnlyBanner').classList.toggle('hidden', Boolean(state.access?.canEdit));
  $$('.write-action').forEach(button => { button.hidden = !state.access?.canEdit; button.disabled = !state.access?.canEdit; });
}
async function loadCatalog() {
  state.catalog = await api('/api/management/catalog');
  state.directorateSpec = state.catalog.directorates[state.directorate];
  $('#pageTitle').textContent = `${state.directorate} · ${state.directorateSpec.name}`;
  $('#pageSubtitle').textContent = state.directorateSpec.periodicity === 'semester'
    ? 'Apuração semestral, com comparação ao mesmo semestre do ano anterior.'
    : 'Apuração mensal, com histórico, metas e detalhamento por dimensão.';
  renderIndicatorOptions();
  renderCatalog();
}
function renderIndicatorOptions() {
  const indicators = state.directorateSpec.indicators || [];
  const selected = $('#indicatorSelect')?.value || indicators[0]?.code || '';
  $('#indicatorSelect').innerHTML = indicators.map(item => option(item.code, `${item.code} · ${item.name}`, item.code === selected)).join('');
  $('#measurementIndicatorFilter').innerHTML = option('', 'Todos os indicadores') + indicators.map(item => option(item.code, `${item.code} · ${item.short_name}`)).join('');
}
async function loadDashboard() {
  const params = {
    referencia: $('#referenceSelect')?.value || '',
    comparacao: $('#comparisonSelect')?.value || '',
    indicador: $('#indicatorSelect')?.value || '',
    janela: $('#windowSelect')?.value || (state.directorateSpec.periodicity === 'semester' ? 8 : 12),
  };
  state.dashboard = await api('/api/management/dashboard', {}, params);
  renderPeriodOptions();
  renderDashboard();
}
function renderPeriodOptions() {
  const periods = state.dashboard?.periods || [];
  const ref = state.dashboard?.reference || '';
  const comp = state.dashboard?.comparison || '';
  $('#referenceSelect').innerHTML = periods.length ? periods.map(value => option(value,value,value===ref)).join('') : option('', 'Sem dados');
  const comparisons = [...new Set([comp, ...periods].filter(Boolean))];
  $('#comparisonSelect').innerHTML = option('', 'Sem comparação', !comp) + comparisons.map(value => option(value,value,value===comp)).join('');
  const indicator = state.dashboard?.selected_indicator?.code;
  if (indicator && [...$('#indicatorSelect').options].some(item => item.value === indicator)) $('#indicatorSelect').value = indicator;
  $('#windowSelect').value = state.directorateSpec.periodicity === 'semester' && $('#windowSelect').value === '12' ? '8' : $('#windowSelect').value;
}
function renderDashboard() {
  renderCards();
  renderHistoryChart();
  renderMetricsTable();
  renderDimensionChart();
  renderDimensionTable();
  renderQuality();
}
function renderCards() {
  $('#cards').innerHTML = (state.dashboard.cards || []).map(card => {
    const cls = statusClass(card.status);
    return `<article class="kpi-card ${cls==='critical'?'critical':cls==='attention'?'attention':''}">
      <div class="kpi-card-head"><div><span class="eyebrow">${escapeHtml(card.indicator_code)}</span><h3>${escapeHtml(card.short_name)}</h3></div><span class="status-pill ${cls}">${escapeHtml(card.status)}</span></div>
      <div class="kpi-value">${formatValue(card.value,card.unit)}</div>
      <div class="kpi-meta"><span>Comparação: <strong>${formatValue(card.comparison_value,card.unit)}</strong></span><span>Meta: <strong>${escapeHtml(card.target_label || '—')}</strong></span></div>
      <div class="kpi-meta"><span>${card.records || 0} lançamento(s)</span><span>${card.validated_records || 0} validado(s)</span></div>
      ${(card.notes||[]).map(note=>`<div class="kpi-note">${escapeHtml(note)}</div>`).join('')}
    </article>`;
  }).join('');
}
function renderHistoryChart() {
  const indicator = state.dashboard.selected_indicator;
  const metric = metricByKey(indicator, indicator.primary_metric);
  $('#chartCode').textContent = indicator.code;
  $('#chartTitle').textContent = indicator.name;
  $('#chartContext').textContent = `${state.dashboard.series.length} período(s) · ${metric.unit}`;
  const points = (state.dashboard.series || []).map(item => ({label:item.period,value:item.metrics?.[metric.key]}));
  const selectedMetric = (state.dashboard.selected_metrics || []).find(item=>item.key===metric.key);
  const target = selectedMetric?.target?.target ?? metric.target;
  $('#historyChart').innerHTML = lineChartSvg(points,{unit:metric.unit,target,title:metric.label});
}
function lineChartSvg(points,{unit='',target=null,title=''}) {
  const clean = points.filter(point => point.value !== null && point.value !== undefined && Number.isFinite(Number(point.value)));
  if (!clean.length) return '<div class="chart-empty">Ainda não há dados para este indicador.</div>';
  const width=940,height=340,pad={l:58,r:24,t:28,b:58};
  const values=clean.map(item=>Number(item.value));
  if(target!==null&&target!==undefined&&Number.isFinite(Number(target))) values.push(Number(target));
  let min=Math.min(...values),max=Math.max(...values);
  if(unit==='%'){min=Math.min(0,min);max=Math.max(100,max)}
  else if(unit==='x'||unit==='índice'){min=Math.min(.8,min);max=Math.max(1.25,max)}
  else {const span=Math.max(1,max-min);min=Math.max(0,min-span*.18);max=max+span*.18}
  if(max===min)max=min+1;
  const x=i=>pad.l+(clean.length===1?(width-pad.l-pad.r)/2:i*(width-pad.l-pad.r)/(clean.length-1));
  const y=value=>pad.t+(max-value)*(height-pad.t-pad.b)/(max-min);
  const grid=[0,.25,.5,.75,1].map(f=>{const value=max-(max-min)*f;const yy=pad.t+(height-pad.t-pad.b)*f;return `<line x1="${pad.l}" y1="${yy}" x2="${width-pad.r}" y2="${yy}" stroke="#dce5e1"/><text x="${pad.l-10}" y="${yy+4}" text-anchor="end" font-size="11" fill="#68757f">${escapeHtml(formatValue(value,unit))}</text>`}).join('');
  const labels=clean.map((item,i)=>`<text x="${x(i)}" y="${height-22}" text-anchor="middle" font-size="11" fill="#66737d">${escapeHtml(item.label)}</text>`).join('');
  const path=clean.map((item,i)=>`${i?'L':'M'} ${x(i)} ${y(Number(item.value))}`).join(' ');
  const dots=clean.map((item,i)=>`<circle cx="${x(i)}" cy="${y(Number(item.value))}" r="5" fill="#00583f" stroke="#fff" stroke-width="2"/><text x="${x(i)}" y="${y(Number(item.value))-12}" text-anchor="middle" font-size="11" font-weight="700" fill="#00583f">${escapeHtml(formatValue(item.value,unit))}</text>`).join('');
  const targetLine=target!==null&&target!==undefined&&Number.isFinite(Number(target))?`<line x1="${pad.l}" y1="${y(Number(target))}" x2="${width-pad.r}" y2="${y(Number(target))}" stroke="#c6a15b" stroke-width="2" stroke-dasharray="8 5"/><text x="${width-pad.r}" y="${y(Number(target))-7}" text-anchor="end" font-size="11" font-weight="700" fill="#8b6b2f">Meta ${escapeHtml(formatValue(target,unit))}</text>`:'';
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">${grid}${targetLine}<path d="${path}" fill="none" stroke="#00583f" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}</svg>`;
}
function renderMetricsTable() {
  const items = state.dashboard.selected_metrics || [];
  $('#metricsTable').innerHTML = `<table class="data-table"><thead><tr><th>Métrica</th><th>Referência</th><th>Comparação</th><th>Meta</th><th>Status</th></tr></thead><tbody>${items.map(item=>`<tr><td><strong>${escapeHtml(item.label)}</strong><br><small>${escapeHtml(item.unit||'')}</small></td><td class="value-cell">${formatValue(item.value,item.unit)}</td><td>${formatValue(item.comparison_value,item.unit)}</td><td>${escapeHtml(item.target_label||'—')}</td><td class="status-text ${statusClass(item.status)}">${escapeHtml(item.status)}</td></tr>`).join('')}</tbody></table>`;
}
function renderDimensionChart() {
  const indicator=state.dashboard.selected_indicator;
  const primary=metricByKey(indicator,indicator.primary_metric);
  const items=(state.dashboard.dimension_items||[]).filter(item=>item.primary_value!==null&&item.primary_value!==undefined).sort((a,b)=>Number(b.primary_value)-Number(a.primary_value)).slice(0,18);
  $('#dimensionContext').textContent=`${state.dashboard.reference||'—'} · ${items.length} recorte(s)`;
  $('#dimensionChart').innerHTML=barChartSvg(items.map(item=>({label:item.dimension_label,value:item.primary_value,status:item.status})),primary.unit);
}
function barChartSvg(items,unit='') {
  if(!items.length)return '<div class="chart-empty">Nenhum recorte dimensional no período selecionado.</div>';
  const width=940,rowH=32,pad={l:260,r:90,t:16,b:20},height=pad.t+pad.b+items.length*rowH;
  const values=items.map(item=>Number(item.value));let min=Math.min(0,...values),max=Math.max(...values);if(max===min)max=min+1;
  const scale=value=>pad.l+(value-min)*(width-pad.l-pad.r)/(max-min);
  const zero=scale(0);
  const rows=items.map((item,index)=>{const y=pad.t+index*rowH+5;const x=scale(Number(item.value));const left=Math.min(zero,x),barW=Math.max(2,Math.abs(x-zero));const color=statusClass(item.status)==='critical'?'#c64b42':statusClass(item.status)==='attention'?'#d79b25':'#0b6b4f';return `<text x="${pad.l-10}" y="${y+14}" text-anchor="end" font-size="11" fill="#3b4850">${escapeHtml(item.label.length>38?item.label.slice(0,36)+'…':item.label)}</text><rect x="${left}" y="${y}" width="${barW}" height="18" rx="5" fill="${color}"/><text x="${x+(x>=zero?7:-7)}" y="${y+14}" text-anchor="${x>=zero?'start':'end'}" font-size="11" font-weight="700" fill="${color}">${escapeHtml(formatValue(item.value,unit))}</text>`}).join('');
  return `<svg viewBox="0 0 ${width} ${height}"><line x1="${zero}" y1="${pad.t}" x2="${zero}" y2="${height-pad.b}" stroke="#aebbb6"/>${rows}</svg>`;
}
function renderDimensionTable() {
  const indicator=state.dashboard.selected_indicator;
  const primary=metricByKey(indicator,indicator.primary_metric);
  const items=state.dashboard.dimension_items||[];
  $('#dimensionTable').innerHTML=items.length?`<table class="data-table"><thead><tr><th>Dimensão</th><th>${escapeHtml(primary.label)}</th><th>Status</th><th>Validação</th></tr></thead><tbody>${items.map(item=>`<tr><td>${escapeHtml(item.dimension_label)}</td><td class="value-cell">${formatValue(item.primary_value,primary.unit)}</td><td class="status-text ${statusClass(item.status)}">${escapeHtml(item.status)}</td><td>${item.validated?'Validado':'Pendente'}</td></tr>`).join('')}</tbody></table>`:'<div class="chart-empty">Sem lançamentos dimensionais na referência.</div>';
}
function renderQuality() {
  const q=state.dashboard.quality||{};
  const items=[['Lançamentos',q.measurements||0],['Validados',q.validated_measurements||0],['Períodos',q.periods||0],['Cobertura',`${Number(q.coverage_pct||0).toLocaleString('pt-BR',{maximumFractionDigits:0})}%`],['Ações abertas',q.open_actions||0]];
  $('#qualityGrid').innerHTML=items.map(([label,value])=>`<div class="quality-item"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join('');
}
function renderCatalog() {
  $('#catalogCards').innerHTML=(state.directorateSpec.indicators||[]).map(indicator=>`<article class="catalog-card"><span class="eyebrow">${escapeHtml(indicator.code)}</span><h3>${escapeHtml(indicator.name)}</h3><p>${escapeHtml(indicator.objective)}</p><div class="catalog-meta"><div><strong>Fórmula</strong>${escapeHtml(indicator.formula_text)}</div><div><strong>Fonte e responsabilidade</strong>${escapeHtml(indicator.source)}<br>${escapeHtml(indicator.responsible)}</div><div><strong>Periodicidade</strong>${indicator.periodicity==='semester'?'Semestral':'Mensal'}</div><div><strong>Dimensões</strong>${escapeHtml((indicator.dimensions||[]).join(', ')||'TOTAL')}</div></div><div class="metric-list"><div class="metric-row"><span>Métrica</span><span>Unidade</span><span>Direção</span><span>Meta inicial</span></div>${(indicator.metrics||[]).map(metric=>`<div class="metric-row"><span>${escapeHtml(metric.label)}</span><span>${escapeHtml(metric.unit||'')}</span><span>${escapeHtml(metric.direction||'')}</span><span>${metric.target!==undefined&&metric.target!==null?formatValue(metric.target,metric.unit):metric.target_min!==undefined?`${formatValue(metric.target_min,metric.unit)} a ${formatValue(metric.target_max,metric.unit)}`:'—'}</span></div>`).join('')}</div></article>`).join('');
}

async function loadMeasurements(reset=false) {
  if(reset) state.measurementOffset=0;
  const data=await api('/api/management/measurements',{}, {
    indicador:$('#measurementIndicatorFilter').value,
    periodo:$('#measurementPeriodFilter').value.trim(),
    busca:$('#measurementSearch').value.trim(),
    offset:state.measurementOffset,
    limit:state.measurementLimit,
  });
  state.measurements=data.items;state.measurementTotal=data.total;state.measurementHasMore=data.has_more;
  renderMeasurements();
}
function renderMeasurements(){
  const canWrite=Boolean(state.access?.canEdit);
  $('#measurementsTable').innerHTML=state.measurements.length?`<table class="data-table"><thead><tr><th>Indicador</th><th>Período</th><th>Dimensão</th><th>Componentes</th><th>Validação</th>${canWrite?'<th></th>':''}</tr></thead><tbody>${state.measurements.map(item=>`<tr><td><strong>${escapeHtml(item.indicator_code)}</strong></td><td>${escapeHtml(item.period)}</td><td>${escapeHtml(item.dimension_label)}</td><td>${Object.entries(item.values||{}).filter(([,v])=>v!==null&&v!=='').slice(0,5).map(([k,v])=>`${escapeHtml(k)}: <strong>${escapeHtml(v)}</strong>`).join('<br>')}</td><td>${item.validated?'Validado':'Pendente'}</td>${canWrite?`<td><button class="button secondary delete-measurement" data-id="${item.id}">Excluir</button></td>`:''}</tr>`).join('')}</tbody></table>`:'<div class="chart-empty">Nenhum lançamento encontrado.</div>';
  $('#measurementsCount').textContent=`${state.measurementOffset+1}-${Math.min(state.measurementOffset+state.measurements.length,state.measurementTotal)} de ${state.measurementTotal}`;
  $('#prevMeasurements').disabled=state.measurementOffset===0;$('#nextMeasurements').disabled=!state.measurementHasMore;
  $$('.delete-measurement').forEach(button=>button.addEventListener('click',()=>deleteMeasurement(Number(button.dataset.id))));
}
async function deleteMeasurement(id){if(!confirm('Excluir este lançamento?'))return;try{await api(`/api/management/measurements/${id}`,{method:'DELETE'});showAlert('Lançamento excluído.','success');await loadMeasurements(true);await loadDashboard()}catch(error){showAlert(error.message)}}
async function loadTargets(){const data=await api('/api/management/targets');state.targets=data.items;renderTargets()}
function renderTargets(){const canWrite=Boolean(state.access?.canEdit);$('#targetsTable').innerHTML=state.targets.length?`<table class="data-table"><thead><tr><th>Indicador</th><th>Métrica</th><th>Dimensão</th><th>Vigência</th><th>Meta</th><th>Atenção</th>${canWrite?'<th></th>':''}</tr></thead><tbody>${state.targets.map(item=>`<tr><td>${escapeHtml(item.indicator_code)}</td><td>${escapeHtml(item.metric_key)}</td><td>${escapeHtml(item.dimension_label)}</td><td>${escapeHtml(item.valid_from)}${item.valid_to?` a ${escapeHtml(item.valid_to)}`:' em diante'}</td><td>${item.target??`${item.target_min??'—'} a ${item.target_max??'—'}`}</td><td>${item.attention??'—'}</td>${canWrite?`<td><button class="button secondary delete-target" data-id="${item.id}">Excluir</button></td>`:''}</tr>`).join('')}</tbody></table>`:'<div class="chart-empty">As metas iniciais do catálogo estão vigentes. Nenhuma meta específica foi cadastrada.</div>';
  $$('.delete-target').forEach(button=>button.addEventListener('click',async()=>{if(!confirm('Excluir esta meta?'))return;try{await api(`/api/management/targets/${button.dataset.id}`,{method:'DELETE'});await loadTargets();await loadDashboard()}catch(error){showAlert(error.message)}}));}
async function loadActions(){const data=await api('/api/management/actions');state.actions=data.items;renderActions()}
function renderActions(){const canWrite=Boolean(state.access?.canEdit);$('#actionsTable').innerHTML=state.actions.length?`<table class="data-table"><thead><tr><th>Indicador</th><th>Período</th><th>Problema</th><th>Ação</th><th>Responsável</th><th>Prazo</th><th>Status</th>${canWrite?'<th></th>':''}</tr></thead><tbody>${state.actions.map(item=>`<tr><td>${escapeHtml(item.indicator_code)}</td><td>${escapeHtml(item.period)}</td><td>${escapeHtml(item.problem)}</td><td>${escapeHtml(item.corrective_action)}</td><td>${escapeHtml(item.responsible)}</td><td>${escapeHtml(item.due_date)}</td><td>${escapeHtml(item.status)}</td>${canWrite?`<td><button class="button secondary delete-action" data-id="${item.id}">Excluir</button></td>`:''}</tr>`).join('')}</tbody></table>`:'<div class="chart-empty">Nenhum plano de ação cadastrado.</div>';
  $$('.delete-action').forEach(button=>button.addEventListener('click',async()=>{if(!confirm('Excluir este plano de ação?'))return;try{await api(`/api/management/actions/${button.dataset.id}`,{method:'DELETE'});await loadActions();await loadDashboard()}catch(error){showAlert(error.message)}}));}

function openModal(title,eyebrow,body){$('#modalTitle').textContent=title;$('#modalEyebrow').textContent=eyebrow;$('#modalBody').innerHTML=body;$('#modal').classList.remove('hidden')}
function closeModal(){$('#modal').classList.add('hidden');$('#modalBody').innerHTML=''}
function fieldHtml(name,label,type='text',value='',options={}){const cls=options.span2?'span-2':'';const required=options.required?'required':'';const step=type==='number'?'step="any"':'';return `<label class="${cls}"><span>${escapeHtml(label)}</span><input name="${escapeHtml(name)}" type="${type}" value="${escapeHtml(value)}" ${required} ${step}>${options.help?`<small class="field-help">${escapeHtml(options.help)}</small>`:''}</label>`}
function selectHtml(name,label,items,selected='',options={}){return `<label class="${options.span2?'span-2':''}"><span>${escapeHtml(label)}</span><select name="${escapeHtml(name)}">${items.map(item=>option(item.value,item.label,item.value===selected)).join('')}</select></label>`}
function textareaHtml(name,label,value='',span2=true){return `<label class="${span2?'span-2':''}"><span>${escapeHtml(label)}</span><textarea name="${escapeHtml(name)}">${escapeHtml(value)}</textarea></label>`}
function formDataObject(form){return Object.fromEntries(new FormData(form).entries())}

function openMeasurementForm(){
  const first=state.directorateSpec.indicators[0];
  openModal('Novo lançamento','BASE OFICIAL',measurementFormHtml(first));
  bindMeasurementForm();
}
function measurementFormHtml(indicator){
  const indicators=state.directorateSpec.indicators.map(item=>({value:item.code,label:`${item.code} · ${item.name}`}));
  const periodType=indicator.periodicity==='semester'?'text':'month';
  const dimensions=(indicator.dimensions||[]).map(key=>fieldHtml(`dimension_${key}`,key.replaceAll('_',' '),'text','',{required:false})).join('');
  const fields=(indicator.fields||[]).map(field=>fieldHtml(`value_${field.key}`,field.label,'number','',{required:field.required})).join('');
  return `<form id="measurementForm" class="form-grid">${selectHtml('indicator_code','Indicador',indicators,indicator.code,{span2:true})}${fieldHtml('period','Período',periodType,'',{required:true,help:indicator.periodicity==='semester'?'Use AAAA-SEM1 ou AAAA-SEM2.':'Competência mensal.'})}${fieldHtml('source_reference','Referência da fonte','text','',{required:false})}<div class="span-2"><span class="eyebrow">DIMENSÕES</span></div>${dimensions||'<div class="span-2 field-help">O lançamento será consolidado como TOTAL.</div>'}<div class="span-2"><span class="eyebrow">COMPONENTES</span></div>${fields}${textareaHtml('notes','Observações')}<label class="span-2"><input name="validated" type="checkbox" value="true"> Marcar como validado pelo responsável</label><div class="form-actions"><button type="button" class="button secondary" id="cancelModal">Cancelar</button><button type="submit" class="button primary">Salvar lançamento</button></div></form>`;
}
function bindMeasurementForm(){
  const form=$('#measurementForm');form.indicator_code.addEventListener('change',()=>{const indicator=indicatorByCode(form.indicator_code.value);$('#modalBody').innerHTML=measurementFormHtml(indicator);bindMeasurementForm()});
  $('#cancelModal').addEventListener('click',closeModal);form.addEventListener('submit',saveMeasurement);
}
async function saveMeasurement(event){event.preventDefault();const form=event.currentTarget;const indicator=indicatorByCode(form.indicator_code.value);const raw=formDataObject(form);const dimensions={};(indicator.dimensions||[]).forEach(key=>{const value=raw[`dimension_${key}`]?.trim();if(value)dimensions[key]=value});const values={};(indicator.fields||[]).forEach(field=>{const value=raw[`value_${field.key}`];values[field.key]=value===''?null:Number(value)});const payload={indicator_code:raw.indicator_code,period:raw.period,dimensions,values,notes:raw.notes,source_reference:raw.source_reference,validated:Boolean(form.validated.checked)};try{await api('/api/management/measurements',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeModal();showAlert('Lançamento salvo.','success');await loadMeasurements(true);await loadDashboard()}catch(error){showAlert(error.message)}}

function openTargetForm(){const indicator=state.directorateSpec.indicators[0];openModal('Nova meta','VIGÊNCIA',targetFormHtml(indicator));bindTargetForm()}
function targetFormHtml(indicator){const indicators=state.directorateSpec.indicators.map(item=>({value:item.code,label:`${item.code} · ${item.name}`}));const metrics=indicator.metrics.map(item=>({value:item.key,label:`${item.label} (${item.unit})`}));const dimensions=(indicator.dimensions||[]).map(key=>fieldHtml(`dimension_${key}`,key.replaceAll('_',' '))).join('');return `<form id="targetForm" class="form-grid">${selectHtml('indicator_code','Indicador',indicators,indicator.code,{span2:true})}${selectHtml('metric_key','Métrica',metrics,metrics[0]?.value||'',{span2:true})}${fieldHtml('valid_from','Vigência inicial','text','',{required:true})}${fieldHtml('valid_to','Vigência final','text','')}${dimensions}<div class="span-2"><span class="eyebrow">LIMITES</span></div>${fieldHtml('target','Meta','number','')}${fieldHtml('attention','Atenção','number','')}${fieldHtml('target_min','Meta mínima','number','')}${fieldHtml('target_max','Meta máxima','number','')}${fieldHtml('attention_min','Atenção mínima','number','')}${fieldHtml('attention_max','Atenção máxima','number','')}${textareaHtml('justification','Justificativa')}<div class="form-actions"><button type="button" class="button secondary" id="cancelModal">Cancelar</button><button type="submit" class="button primary">Salvar meta</button></div></form>`}
function bindTargetForm(){const form=$('#targetForm');form.indicator_code.addEventListener('change',()=>{$('#modalBody').innerHTML=targetFormHtml(indicatorByCode(form.indicator_code.value));bindTargetForm()});$('#cancelModal').addEventListener('click',closeModal);form.addEventListener('submit',saveTarget)}
async function saveTarget(event){event.preventDefault();const form=event.currentTarget,raw=formDataObject(form),indicator=indicatorByCode(raw.indicator_code),dimensions={};(indicator.dimensions||[]).forEach(key=>{const value=raw[`dimension_${key}`]?.trim();if(value)dimensions[key]=value});const numeric={};['target','attention','target_min','target_max','attention_min','attention_max'].forEach(key=>numeric[key]=raw[key]===''?null:Number(raw[key]));const payload={indicator_code:raw.indicator_code,metric_key:raw.metric_key,valid_from:raw.valid_from,valid_to:raw.valid_to||null,dimensions,justification:raw.justification,...numeric};try{await api('/api/management/targets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeModal();showAlert('Meta salva.','success');await loadTargets();await loadDashboard()}catch(error){showAlert(error.message)}}

function openActionForm(){const indicator=state.directorateSpec.indicators[0];openModal('Novo plano de ação','TRATAMENTO',actionFormHtml(indicator));bindActionForm()}
function actionFormHtml(indicator){const indicators=state.directorateSpec.indicators.map(item=>({value:item.code,label:`${item.code} · ${item.name}`}));const metrics=[{value:'',label:'Indicador como um todo'},...indicator.metrics.map(item=>({value:item.key,label:item.label}))];const dimensions=(indicator.dimensions||[]).map(key=>fieldHtml(`dimension_${key}`,key.replaceAll('_',' '))).join('');return `<form id="actionForm" class="form-grid">${selectHtml('indicator_code','Indicador',indicators,indicator.code,{span2:true})}${selectHtml('metric_key','Métrica',metrics,'')}${fieldHtml('period','Período','text','',{required:true})}${dimensions}${textareaHtml('problem','Problema identificado')}${textareaHtml('probable_cause','Causa provável')}${textareaHtml('corrective_action','Ação corretiva')}${fieldHtml('responsible','Responsável','text','',{required:true})}${fieldHtml('due_date','Prazo','date','',{required:true})}${selectHtml('status','Status',[{value:'Aberto',label:'Aberto'},{value:'Em andamento',label:'Em andamento'},{value:'Concluído',label:'Concluído'},{value:'Atrasado',label:'Atrasado'},{value:'Cancelado',label:'Cancelado'}],'Aberto')}${textareaHtml('evidence','Evidência / observação')}<div class="form-actions"><button type="button" class="button secondary" id="cancelModal">Cancelar</button><button type="submit" class="button primary">Salvar plano</button></div></form>`}
function bindActionForm(){const form=$('#actionForm');form.indicator_code.addEventListener('change',()=>{$('#modalBody').innerHTML=actionFormHtml(indicatorByCode(form.indicator_code.value));bindActionForm()});$('#cancelModal').addEventListener('click',closeModal);form.addEventListener('submit',saveAction)}
async function saveAction(event){event.preventDefault();const form=event.currentTarget,raw=formDataObject(form),indicator=indicatorByCode(raw.indicator_code),dimensions={};(indicator.dimensions||[]).forEach(key=>{const value=raw[`dimension_${key}`]?.trim();if(value)dimensions[key]=value});const payload={indicator_code:raw.indicator_code,metric_key:raw.metric_key||null,period:raw.period,dimensions,problem:raw.problem,probable_cause:raw.probable_cause,corrective_action:raw.corrective_action,responsible:raw.responsible,due_date:raw.due_date,status:raw.status,evidence:raw.evidence};try{await api('/api/management/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeModal();showAlert('Plano de ação salvo.','success');await loadActions();await loadDashboard()}catch(error){showAlert(error.message)}}

function activateTab(name){$$('.nav-button').forEach(button=>button.classList.toggle('active',button.dataset.tab===name));$$('.tab-panel').forEach(panel=>panel.classList.toggle('active',panel.id===`tab-${name}`));if(name==='measurements')loadMeasurements(true).catch(error=>showAlert(error.message));if(name==='targets')loadTargets().catch(error=>showAlert(error.message));if(name==='actions')loadActions().catch(error=>showAlert(error.message))}
function bindEvents(){
  $('#directorateSelect').addEventListener('change',event=>location.assign(window.DataUnivcIdentity.routeForDirectorate(event.target.value)));
  $$('.nav-button').forEach(button=>button.addEventListener('click',()=>activateTab(button.dataset.tab)));
  $('#refreshButton').addEventListener('click',()=>loadDashboard().catch(error=>showAlert(error.message)));
  $('#indicatorSelect').addEventListener('change',()=>loadDashboard().catch(error=>showAlert(error.message)));
  $('#referenceSelect').addEventListener('change',()=>loadDashboard().catch(error=>showAlert(error.message)));
  $('#comparisonSelect').addEventListener('change',()=>loadDashboard().catch(error=>showAlert(error.message)));
  $('#windowSelect').addEventListener('change',()=>loadDashboard().catch(error=>showAlert(error.message)));
  $('#exportButton').addEventListener('click',()=>{window.DataUnivcAuth.download(queryWithDirectorate('/api/management/excel',{referencia:$('#referenceSelect').value,comparacao:$('#comparisonSelect').value}),'Painel_Gerencial.xlsx').catch(error=>showAlert(error.message))});
  $('#measurementFilterButton').addEventListener('click',()=>loadMeasurements(true).catch(error=>showAlert(error.message)));
  $('#prevMeasurements').addEventListener('click',()=>{state.measurementOffset=Math.max(0,state.measurementOffset-state.measurementLimit);loadMeasurements().catch(error=>showAlert(error.message))});
  $('#nextMeasurements').addEventListener('click',()=>{if(state.measurementHasMore){state.measurementOffset+=state.measurementLimit;loadMeasurements().catch(error=>showAlert(error.message))}});
  $('#addMeasurement').addEventListener('click',openMeasurementForm);$('#addTarget').addEventListener('click',openTargetForm);$('#addAction').addEventListener('click',openActionForm);
  $('#closeModal').addEventListener('click',closeModal);$('#modal').addEventListener('click',event=>{if(event.target.id==='modal')closeModal()});
  $('#logoutButton').addEventListener('click',async()=>{await window.DataUnivcAuth.logout();location.assign('/')});
}


function setupManagementUi(){
  const navIcons={
    dashboard:'<path d="M4 4h6v6H4zM14 4h6v4h-6zM14 12h6v8h-6zM4 14h6v6H4z"/>',
    measurements:'<path d="M6 5h12M6 10h12M6 15h8M6 20h5"/>',
    targets:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m18 6 3-3"/>',
    actions:'<path d="M7 4h10M7 8h10M7 12h6"/><path d="M5 3h14v18H5z"/>',
    catalog:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>'
  };
  const svg=(path)=>`<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
  $$('.nav-button').forEach(button=>{const slot=button.querySelector('span');if(slot)slot.innerHTML=svg(navIcons[button.dataset.tab]||navIcons.catalog)});
  const sidebar=$('.sidebar');
  const topLead=$('.topbar > div:first-child');
  if(sidebar&&topLead&&!$('.management-mobile-menu')){
    const button=document.createElement('button');button.type='button';button.className='management-mobile-menu';button.setAttribute('aria-label','Abrir menu');button.innerHTML=svg('<path d="M4 7h16M4 12h16M4 17h16"/>');
    topLead.prepend(button);button.addEventListener('click',()=>sidebar.classList.toggle('open'));
    $$('.nav-button').forEach(item=>item.addEventListener('click',()=>{if(innerWidth<=760)sidebar.classList.remove('open')}));
  }
}

setupManagementUi();
initialize();
