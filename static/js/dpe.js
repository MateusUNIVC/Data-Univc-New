const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];

const state = {
  user: null,
  access: null,
  catalog: null,
  indicators: {},
  periods: [],
  reference: '',
  comparison: '',
  window: 12,
  dashboards: {},
  records: {'DPE-01': {items: [], offset: 0, total: 0, hasMore: false}, 'DPE-02': {items: [], offset: 0, total: 0, hasMore: false}, 'DPE-03': {items: [], offset: 0, total: 0, hasMore: false}},
  editingId: null,
  importIndicator: null,
  courseCatalog: [],
  targets: [],
  actions: [],
  finance: {dashboard:null, expenses:[], revenues:[], courseRevenues:[], courseCosts:[]},
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
function setLoading(active) { $('#dpeLoading')?.classList.toggle('hidden', !active); }
function showAlert(message, kind='error', timeout=6500) {
  const box = $('#dpeAlert');
  box.textContent = message;
  box.className = `dpe-alert ${kind}`;
  box.classList.remove('hidden');
  if (timeout) setTimeout(() => box.classList.add('hidden'), timeout);
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
  if (unit === 'R$') return number.toLocaleString('pt-BR', {style:'currency', currency:'BRL', maximumFractionDigits:0});
  if (unit === '%') return `${number.toLocaleString('pt-BR', {minimumFractionDigits:1, maximumFractionDigits:1})}%`;
  if (unit === 'x' || unit === 'índice') return `${number.toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2})}x`;
  if (unit === 'alunos/h') return `${number.toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2})} alunos/h`;
  if (unit === 'h/semana') return `${number.toLocaleString('pt-BR', {minimumFractionDigits:1, maximumFractionDigits:1})} h`;
  return number.toLocaleString('pt-BR', {minimumFractionDigits:1, maximumFractionDigits:1});
}
function formatCompactMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('pt-BR', {style:'currency', currency:'BRL', notation:'compact', maximumFractionDigits:1});
}
function option(value, label=value, selected=false) { return `<option value="${escapeHtml(value)}" ${selected?'selected':''}>${escapeHtml(label)}</option>`; }
function routeForDirectorate(code) {
  return window.DataUnivcIdentity.routeForDirectorate(code);
}
function monthPrevious(period) {
  if (!/^\d{4}-\d{2}$/.test(period || '')) return '';
  let [year, month] = period.split('-').map(Number); month -= 1;
  if (!month) { year -= 1; month = 12; }
  return `${year}-${String(month).padStart(2,'0')}`;
}
function indicatorSpec(code) { return state.indicators[code]; }
function dashboardFor(code) { return state.dashboards[code]; }
function metricOf(code, key) { return (indicatorSpec(code)?.metrics || []).find(metric => metric.key === key); }
function selectedMetric(code, key) { return (dashboardFor(code)?.selected_metrics || []).find(metric => metric.key === key); }
function currentSeriesRow(code) { return (dashboardFor(code)?.series || []).find(row => row.period === state.reference); }

function courseOptionRows(selected='') {
  const rows = state.courseCatalog || [];
  const selectedKnown = rows.some(row => row.name === selected);
  const legacy = selected && !selectedKnown ? option(selected, `${selected} · cadastro anterior`, true) : '';
  return `<option value="">Selecione um curso</option>${legacy}` + rows.map(row => option(row.name, `${row.name} · ${row.directorate_code}`, row.name===selected)).join('');
}
function renderDimensionField(code, key, value='') {
  const label = DIMENSION_LABELS[key] || key;
  if (code==='DPE-01' && key==='course') {
    return `<label><span>${escapeHtml(label)} *</span><select data-dimension-key="course" required>${courseOptionRows(value)}</select><small>Catálogo oficial dos cursos ativos de DTNH e DCS.</small></label>`;
  }
  if (code==='DPE-01' && key==='academic_directorate') {
    const found=(state.courseCatalog||[]).find(row=>row.name===value || row.name===selectedCourseName());
    const selected=value || found?.directorate_code || '';
    return `<label><span>${escapeHtml(label)}</span><input data-dimension-key="academic_directorate" value="${escapeHtml(selected)}" readonly><small>Preenchida automaticamente a partir do curso.</small></label>`;
  }
  return `<label><span>${escapeHtml(label)}</span><input data-dimension-key="${escapeHtml(key)}" value="${escapeHtml(value)}"></label>`;
}
function selectedCourseName(){ return $('[data-dimension-key="course"]','#measurementForm')?.value || ''; }
function directorateLabel(code){ return ({DTNH:'DTNH',DCS:'DCS',DEAD:'Diretoria de Ensino a Distância',SEMIPRESENCIAL:'Diretoria Semipresencial',MARKETING:'Diretoria de Marketing'})[code] || code; }
function syncCourseDirectorate(){
  const course=selectedCourseName(); const field=$('[data-dimension-key="academic_directorate"]','#measurementForm'); if(!field)return;
  const found=(state.courseCatalog||[]).find(row=>row.name===course); if(found) field.value=found.directorate_code || '';
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
    const catalog = await api('/api/management/catalog');
    state.catalog = catalog.directorates.DPE;
    state.indicators = Object.fromEntries((state.catalog.indicators || []).map(item => [item.code, item]));
    try { state.courseCatalog = (await api('/api/dpe/courses')).items || []; } catch { state.courseCatalog = []; }
    bindEvents();
    await loadAllDashboards();
    await Promise.all(['DPE-01','DPE-02','DPE-03'].map(code => loadRecords(code)));
    await Promise.all([loadTargets(), loadActions()]);
    renderFileCards();
    if (typeof window.initializeDPEFinance === 'function') await window.initializeDPEFinance();
  } catch (error) {
    showAlert(error.message, 'error', 0);
  } finally {
    setLoading(false);
  }
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
  const badge=$('#dpeDirectorateAccessBadge');
  if(badge) badge.textContent=state.access?.canEdit?'Edição':'Somente leitura';
}

function applyAccess() {
  const canWrite = Boolean(state.access?.canEdit);
  document.body.classList.toggle('write-enabled', canWrite);
  $('#dpeReadOnly')?.classList.toggle('hidden', canWrite);
  const badge=$('#dpeDirectorateAccessBadge'); if(badge) badge.textContent=canWrite?'Edição':'Leitura';
  $$('[data-write-action]').forEach(element => {
    element.hidden = !canWrite;
    element.disabled = !canWrite;
    if (!canWrite) element.setAttribute('title', 'Acesso somente leitura'); else element.removeAttribute('title');
  });
}

async function loadAllDashboards({preserveSelection=false}={}) {
  setLoading(true);
  try {
    const base = {referencia: preserveSelection ? state.reference : '', comparacao: preserveSelection ? state.comparison : '', janela: state.window === 'all' ? '' : state.window};
    const [d1,d2,d3] = await Promise.all(['DPE-01','DPE-02','DPE-03'].map(code => api('/api/management/dashboard', {}, {...base, indicador:code})));
    state.dashboards = {'DPE-01':d1,'DPE-02':d2,'DPE-03':d3};
    const allPeriods = [...new Set([...(d1.periods||[]), ...(d2.periods||[]), ...(d3.periods||[])])].sort();
    state.periods = allPeriods;
    if (!preserveSelection || !state.reference) state.reference = d1.reference || d2.reference || d3.reference || allPeriods.at(-1) || '';
    if (!preserveSelection || !state.comparison) state.comparison = d1.comparison || d2.comparison || d3.comparison || monthPrevious(state.reference);
    populateFilters();
    renderEverything();
    updateDownloadLinks();
  } finally { setLoading(false); }
}
function populateFilters() {
  const referenceOptions = state.periods.length ? state.periods.map(value => option(value,value,value===state.reference)).join('') : option('', 'Sem dados');
  const comparisonValues = [...new Set([state.comparison, ...state.periods].filter(Boolean))];
  const comparisonOptions = option('', 'Sem comparação', !state.comparison) + comparisonValues.map(value => option(value,value,value===state.comparison)).join('');
  $('#dashboardReference').innerHTML = referenceOptions;
  $('#dashboardComparison').innerHTML = comparisonOptions;
  $('#dashboardWindow').value = String(state.window);
  ['DPE-01','DPE-02','DPE-03'].forEach(code => {
    const ref = $(`[data-reference="${code}"]`); const comp = $(`[data-comparison="${code}"]`); const win = $(`[data-window="${code}"]`);
    if (ref) ref.innerHTML = referenceOptions;
    if (comp) comp.innerHTML = comparisonOptions;
    if (win) win.value = String(state.window);
  });
}
function updateDownloadLinks() {
  const params = {diretoria:'DPE', referencia:state.reference, comparacao:state.comparison};
  const link = new URL('/api/dpe/excel', location.origin); Object.entries(params).forEach(([k,v]) => v && link.searchParams.set(k,v));
  $('#dpeFullExcel').href = link.pathname + link.search;
  $$('a[href^="/api/dpe/excel/DPE-"]').forEach(anchor => {
    const base = anchor.getAttribute('href').split('?')[0];
    anchor.href = url(base, {referencia:state.reference, comparacao:state.comparison});
  });
}
function renderEverything() {
  renderDashboardSummary();
  ['DPE-01','DPE-02','DPE-03'].forEach(code => renderIndicatorPage(code));
}
function renderDashboardSummary() {
  const icons={'DPE-01':'01','DPE-02':'02','DPE-03':'03'};
  const cards = ['DPE-01','DPE-02','DPE-03'].map(code => {
    const dashboard = dashboardFor(code); const card = (dashboard?.cards || []).find(item => item.indicator_code === code) || {};
    const secondaryKey = code === 'DPE-01' ? 'net_margin_12m_pct' : code === 'DPE-02' ? 'coverage_index_12m' : 'payroll_on_revenue_3m_pct';
    const secondary = selectedMetric(code, secondaryKey);
    const sub = `${secondary ? `Leitura móvel ${formatValue(secondary.value, secondary.unit)} · ` : ''}Meta ${card.target_label || '—'}`;
    return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(card.short_name || code)}</span><span class="metric-icon">${icons[code]}</span></div><strong class="metric-value">${formatValue(card.value, card.unit)}</strong><span class="metric-sub">${escapeHtml(sub)}</span><span class="status-chip ${statusClass(card.status)}">${escapeHtml(card.status || 'Não apurado')}</span></article>`;
  }).join('');
  $('#dashboardCards').innerHTML = cards;
  renderLineChart($('#chartDashboard01'), dashboardFor('DPE-01')?.series || [], [
    {key:'net_margin_pct', label:'Margem mensal', color:COLORS[0]}, {key:'net_margin_12m_pct', label:'Margem 12m', color:COLORS[1]}, {constant: selectedMetric('DPE-01','net_margin_pct')?.target?.target ?? 15, label:'Meta', color:COLORS[2], dash:true},
  ], '%');
  renderLineChart($('#chartDashboard02'), dashboardFor('DPE-02')?.series || [], [
    {key:'coverage_index', label:'Cobertura mensal', color:COLORS[0]}, {key:'coverage_index_12m', label:'Cobertura 12m', color:COLORS[1]}, {constant:selectedMetric('DPE-02','coverage_index')?.target?.target ?? 1.11, label:'Meta', color:COLORS[2], dash:true},
  ], 'x');
  renderLineChart($('#chartDashboard03'), dashboardFor('DPE-03')?.series || [], [
    {key:'payroll_on_revenue_pct', label:'Folha mensal', color:COLORS[0]}, {key:'payroll_on_revenue_3m_pct', label:'Receita média 3m', color:COLORS[1]}, {constant:selectedMetric('DPE-03','payroll_on_revenue_pct')?.target?.target ?? 55, label:'Meta', color:COLORS[2], dash:true},
  ], '%');
  const insights = [];
  ['DPE-01','DPE-02','DPE-03'].forEach(code => {
    const card = (dashboardFor(code)?.cards || []).find(item => item.indicator_code === code);
    if (!card) return;
    if (card.status === 'Fora da meta' || card.status === 'Atenção') insights.push({kind:statusClass(card.status), title:`${code} · ${card.status}`, text:`${card.short_name}: ${formatValue(card.value,card.unit)}; meta ${card.target_label || 'não definida'}.`});
    (card.notes || []).forEach(note => insights.push({kind:'attention', title:code, text:note}));
  });
  const badCourses = (dashboardFor('DPE-01')?.dimension_items || []).filter(item => ['Atenção','Fora da meta'].includes(item.status));
  if (badCourses.length) insights.push({kind:'critical', title:'Margem por curso', text:`${badCourses.length} curso(s) abaixo da meta ou em atenção no mês de referência.`});
  if (!insights.length) insights.push({kind:'good', title:'Sem alertas críticos', text:'Os três indicadores estão dentro dos parâmetros de referência no recorte selecionado.'});
  $('#dashboardInsights').innerHTML = insights.map(item => `<div class="insight-item ${item.kind}"><span class="insight-dot"></span><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.text)}</span></div></div>`).join('');
  const context=$('#dpeAnalysisContext'); if(context) context.textContent=`${state.reference || 'Sem referência'} · comparação ${state.comparison || 'desativada'} · ${state.window==='all'?'todo histórico':state.window+' meses'}`;
}
function renderIndicatorPage(code) {
  const dashboard = dashboardFor(code); if (!dashboard) return;
  renderMetricCards(code, dashboard.selected_metrics || []);
  if (code === 'DPE-01') renderDPE01(dashboard);
  if (code === 'DPE-02') renderDPE02(dashboard);
  if (code === 'DPE-03') renderDPE03(dashboard);
}
function renderMetricCards(code, metrics) {
  const preferred = {
    'DPE-01':['net_margin_pct','net_margin_12m_pct','total_cost'],
    'DPE-02':['coverage_index','coverage_index_12m','operating_margin_pct','operating_margin_12m_pct','total_expense'],
    'DPE-03':['payroll_on_revenue_pct','payroll_on_revenue_3m_pct','faculty_payroll_pct','administrative_payroll_pct','payroll_monthly_change_pct'],
  }[code];
  const items = preferred.map(key => metrics.find(item => item.key === key)).filter(Boolean);
  const root = $(`#cards${code.replace('-','')}`);
  root.innerHTML = items.map((item,index) => `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(item.label)}</span><span class="metric-icon">${String(index+1).padStart(2,'0')}</span></div><strong class="metric-value">${formatValue(item.value,item.unit)}</strong><span class="metric-sub">Comparação ${formatValue(item.comparison_value,item.unit)} · Meta ${escapeHtml(item.target_label || '—')}</span><span class="status-chip ${statusClass(item.status)}">${escapeHtml(item.status)}</span></article>`).join('');
}
function renderDPE01(dashboard) {
  const series = dashboard.series || [];
  renderLineChart($('#chartDPE01'), series, [
    {key:'net_margin_pct',label:'Margem mensal',color:COLORS[0]}, {key:'net_margin_12m_pct',label:'Margem 12m',color:COLORS[1]}, {constant:selectedMetric('DPE-01','net_margin_pct')?.target?.target ?? 15,label:'Meta institucional',color:COLORS[2],dash:true},
  ], '%');
  const dimensions = dashboard.dimension_items || [];
  renderHorizontalBars($('#barDPE01'), dimensions.map(item => ({label:item.dimensions?.course || item.dimension_label, value:item.metrics?.net_margin_pct, status:item.status})), '%', 10);
  $('#dimensionTableDPE01').innerHTML = dimensions.length ? dimensions.map(item => {
    const metrics = item.metrics || {};
    return `<tr><td><strong>${escapeHtml(item.dimensions?.course || item.dimension_label)}</strong><small class="table-subtitle">${escapeHtml(item.dimensions?.academic_directorate || '')}</small></td><td>${formatCompactMoney(rawCourseValue(item,'revenue'))}</td><td>${formatCompactMoney(rawCourseValue(item,'cost'))}</td><td class="value-cell">${formatValue(metrics.net_margin_pct,'%')}</td><td>—</td><td><span class="status-chip ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td></tr>`;
  }).join('') : '<tr><td colspan="6">Nenhum curso apurado no período.</td></tr>';
}
function rawCourseValue(item, type) {
  const components = item?.components || {};
  if (type === 'revenue') return Number.isFinite(Number(components.net_revenue)) ? Number(components.net_revenue) : null;
  if (type === 'cost') {
    const keys = ['faculty_cost','coordination_cost','other_direct_cost','indirect_cost'];
    const values = keys.map(key => Number(components[key])).filter(Number.isFinite);
    return values.length ? values.reduce((total, value) => total + value, 0) : null;
  }
  return null;
}
function renderDPE02(dashboard) {
  const series = dashboard.series || [];
  renderLineChart($('#chartDPE02'), series, [
    {key:'coverage_index',label:'Cobertura mensal',color:COLORS[0]}, {key:'coverage_index_12m',label:'Cobertura 12m',color:COLORS[1]}, {constant:selectedMetric('DPE-02','coverage_index')?.target?.target ?? 1.11,label:'Meta',color:COLORS[2],dash:true},
  ], 'x');
  const row = currentSeriesRow('DPE-02'); const c = row?.components || {};
  renderHorizontalBars($('#barDPE02'), [
    {label:'Pessoal',value:c.personnel_expense},{label:'Operacional',value:c.operational_expense},{label:'Administrativa',value:c.administrative_expense},{label:'Financeira',value:c.financial_expense},
  ], 'R$');
}
function renderDPE03(dashboard) {
  const series = dashboard.series || [];
  renderLineChart($('#chartDPE03'), series, [
    {key:'payroll_on_revenue_pct',label:'Folha total',color:COLORS[0]}, {key:'payroll_on_revenue_3m_pct',label:'Sobre receita média 3m',color:COLORS[1]}, {constant:selectedMetric('DPE-03','payroll_on_revenue_pct')?.target?.target ?? 55,label:'Meta',color:COLORS[2],dash:true},
  ], '%');
  const row = currentSeriesRow('DPE-03');
  renderHorizontalBars($('#barDPE03'), [
    {label:'Folha docente',value:row?.metrics?.faculty_payroll_pct,target:38},{label:'Folha administrativa',value:row?.metrics?.administrative_payroll_pct,target:17},
  ], '%');
}

function encodeChartTooltip(payload={}) {
  return encodeURIComponent(JSON.stringify(payload));
}
function chartTooltipPayload(title, lines=[]) {
  return encodeChartTooltip({
    title: String(title || ''),
    lines: (lines || []).filter(item => item && item.value !== undefined && item.value !== null).map(item => ({label:String(item.label || ''), value:String(item.value)})),
  });
}
function ensureChartTooltip(container) {
  let tooltip = container.querySelector('.dpe-chart-tooltip');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.className = 'dpe-chart-tooltip';
    tooltip.setAttribute('role', 'status');
    tooltip.setAttribute('aria-live', 'polite');
    container.appendChild(tooltip);
  }
  return tooltip;
}
function positionChartTooltip(container, tooltip, clientX, clientY) {
  const bounds = container.getBoundingClientRect();
  let left = Number(clientX) - bounds.left + 14;
  let top = Number(clientY) - bounds.top + 14;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  const tw = tooltip.offsetWidth || 220;
  const th = tooltip.offsetHeight || 90;
  if (left + tw > bounds.width - 6) left = Math.max(6, left - tw - 28);
  if (top + th > bounds.height - 6) top = Math.max(6, top - th - 28);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}
function showChartTooltip(container, target, event=null) {
  if (!container || !target) return;
  let payload = null;
  try { payload = JSON.parse(decodeURIComponent(target.dataset.chartTooltip || '')); } catch { return; }
  const tooltip = ensureChartTooltip(container);
  tooltip.innerHTML = `<strong>${escapeHtml(payload.title || '')}</strong>${(payload.lines || []).map(line => `<span><b>${escapeHtml(line.label || '')}</b>${escapeHtml(line.value || '')}</span>`).join('')}`;
  tooltip.classList.add('visible');
  const targetBounds = target.getBoundingClientRect();
  const clientX = event?.clientX ?? (targetBounds.left + targetBounds.width / 2);
  const clientY = event?.clientY ?? (targetBounds.top + Math.min(targetBounds.height / 2, 45));
  positionChartTooltip(container, tooltip, clientX, clientY);
}
function hideChartTooltip(container) {
  const tooltip = container?.querySelector('.dpe-chart-tooltip');
  if (tooltip) tooltip.classList.remove('visible');
}
function bindChartInteractions(container) {
  if (!container || container.dataset.chartInteractiveBound === '1') return;
  container.dataset.chartInteractiveBound = '1';
  container.addEventListener('pointerover', event => {
    const hit = event.target.closest?.('[data-chart-tooltip]');
    if (!hit || !container.contains(hit) || container._chartPinned) return;
    showChartTooltip(container, hit, event);
  });
  container.addEventListener('pointermove', event => {
    const hit = event.target.closest?.('[data-chart-tooltip]');
    if (!hit || !container.contains(hit) || container._chartPinned) return;
    showChartTooltip(container, hit, event);
  });
  container.addEventListener('pointerout', event => {
    if (container._chartPinned) return;
    const hit = event.target.closest?.('[data-chart-tooltip]');
    if (!hit) return;
    const related = event.relatedTarget?.closest?.('[data-chart-tooltip]');
    if (related === hit) return;
    hideChartTooltip(container);
  });
  container.addEventListener('focusin', event => {
    const hit = event.target.closest?.('[data-chart-tooltip]');
    if (hit && container.contains(hit)) showChartTooltip(container, hit);
  });
  container.addEventListener('focusout', () => { if (!container._chartPinned) hideChartTooltip(container); });
  container.addEventListener('click', event => {
    const hit = event.target.closest?.('[data-chart-tooltip]');
    if (!hit || !container.contains(hit)) {
      container._chartPinned = null;
      hideChartTooltip(container);
      return;
    }
    container._chartPinned = container._chartPinned === hit ? null : hit;
    if (container._chartPinned) showChartTooltip(container, hit, event); else hideChartTooltip(container);
  });
  container.addEventListener('keydown', event => {
    const hit = event.target.closest?.('[data-chart-tooltip]');
    if (!hit || !container.contains(hit) || !['Enter',' '].includes(event.key)) return;
    event.preventDefault();
    container._chartPinned = container._chartPinned === hit ? null : hit;
    if (container._chartPinned) showChartTooltip(container, hit); else hideChartTooltip(container);
  });
}
function chartHint() {
  return '<div class="dpe-chart-hint">Passe o mouse ou toque nos dados para ver os detalhes</div>';
}
function wrapChartLabel(value, maxChars=28, maxLines=2) {
  const words = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [''];
  const lines = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars || !current) current = candidate;
    else { lines.push(current); current = word; }
  }
  if (current) lines.push(current);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, Math.max(1, maxChars - 1)).trimEnd()}…`;
  return kept;
}
function isChartNumber(value) { return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)); }
function barColorFor(item, index) {
  const status = String(item?.status || '').toLowerCase();
  if (status === 'critical' || status.includes('fora') || status.includes('negativa')) return '#ba4b50';
  if (status === 'attention' || status.includes('aten')) return '#d6a93f';
  if (status === 'good' || status.includes('dentro')) return '#0e8058';
  return COLORS[index % COLORS.length];
}
function renderLineChart(container, rows, defs, unit='') {
  if (!container) return;
  bindChartInteractions(container);
  container._chartPinned = null;
  const points = rows.filter(row => row?.period);
  const usable = points.filter(row => defs.some(def => def.constant !== undefined || isChartNumber(row.metrics?.[def.key])));
  if (!usable.length) { container.innerHTML = '<div class="dpe-chart-empty">Ainda não há histórico suficiente para este gráfico.</div>'; return; }
  const width = 800, height = 310, margin = {left:58,right:20,top:25,bottom:64};
  const values = [];
  usable.forEach(row => defs.forEach(def => { const value = def.constant !== undefined ? def.constant : row.metrics?.[def.key]; if (isChartNumber(value)) values.push(Number(value)); }));
  let min = Math.min(...values), max = Math.max(...values); if (min === max) { min -= 1; max += 1; }
  const pad = (max-min)*.13; min -= pad; max += pad; if (unit==='%' && min>0) min=Math.max(0,min);
  const plotWidth = width-margin.left-margin.right;
  const x = index => margin.left + (usable.length===1 ? plotWidth/2 : index*plotWidth/(usable.length-1));
  const y = value => margin.top + (max-value)*(height-margin.top-margin.bottom)/(max-min);
  const grid = Array.from({length:5},(_,i)=>{const value=min+(max-min)*i/4;const yy=y(value);return `<line x1="${margin.left}" x2="${width-margin.right}" y1="${yy}" y2="${yy}" stroke="#dce5e0"/><text x="${margin.left-8}" y="${yy+4}" text-anchor="end" font-size="10" fill="#74847c">${escapeHtml(formatAxis(value,unit))}</text>`}).join('');
  const hitZones = usable.map((row,index)=>{
    const center=x(index); const previous=index?x(index-1):margin.left; const next=index<usable.length-1?x(index+1):width-margin.right;
    const left=index?((previous+center)/2):margin.left; const right=index<usable.length-1?((center+next)/2):width-margin.right;
    const lines=defs.map(def=>{const value=def.constant!==undefined?def.constant:row.metrics?.[def.key];return isChartNumber(value)?{label:def.label,value:formatAxis(Number(value),unit)}:null}).filter(Boolean);
    const aria=`${row.period}. ${lines.map(line=>`${line.label}: ${line.value}`).join('. ')}`;
    return `<rect class="dpe-chart-hit-zone" x="${left}" y="${margin.top}" width="${Math.max(1,right-left)}" height="${height-margin.top-margin.bottom}" data-chart-tooltip="${chartTooltipPayload(row.period,lines)}" tabindex="0" role="button" aria-label="${escapeHtml(aria)}"/>`;
  }).join('');
  const seriesSvg = defs.map((def,seriesIndex)=>{
    const coords=usable.map((row,index)=>{const value=def.constant!==undefined?def.constant:row.metrics?.[def.key];return isChartNumber(value)?{x:x(index),y:y(Number(value)),value:Number(value),period:row.period}:null}).filter(Boolean);
    if(!coords.length)return '';
    const path=coords.map((p,i)=>`${i?'L':'M'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
    const circles=def.dash?'':coords.map(p=>`<circle class="dpe-chart-point" cx="${p.x}" cy="${p.y}" r="${seriesIndex===0?4:3}" fill="${def.color}"/>`).join('');
    return `<path class="dpe-chart-series" d="${path}" fill="none" stroke="${def.color}" stroke-width="${seriesIndex===0?3:2}" ${def.dash?'stroke-dasharray="7 5"':''}/>${circles}`;
  }).join('');
  const labelStep=Math.max(1,Math.ceil(usable.length/8));
  const labels=usable.map((row,index)=>((index%labelStep===0)||index===usable.length-1)?`<text x="${x(index)}" y="${height-35}" text-anchor="middle" font-size="10" fill="#5b6d64">${escapeHtml(row.period)}</text>`:'').join('');
  const legendSpacing=Math.max(160,Math.floor((width-margin.left-margin.right)/Math.max(defs.length,1)));
  const legend=defs.map((def,index)=>`<g transform="translate(${margin.left+index*legendSpacing},${height-9})"><line x1="0" x2="22" y1="0" y2="0" stroke="${def.color}" stroke-width="3" ${def.dash?'stroke-dasharray="6 4"':''}/><text x="28" y="4" font-size="10" fill="#5b6d64">${escapeHtml(def.label)}</text></g>`).join('');
  container.innerHTML=`${chartHint()}<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico de evolução interativo"><rect width="${width}" height="${height}" fill="white" rx="8"/>${grid}${hitZones}<line x1="${margin.left}" x2="${margin.left}" y1="${margin.top}" y2="${height-margin.bottom}" stroke="#9cafa5"/><line x1="${margin.left}" x2="${width-margin.right}" y1="${height-margin.bottom}" y2="${height-margin.bottom}" stroke="#9cafa5"/>${seriesSvg}${labels}${legend}</svg><div class="dpe-chart-tooltip" role="status" aria-live="polite"></div>`;
}
function renderHorizontalBars(container, items, unit='', target=null) {
  if (!container) return;
  bindChartInteractions(container);
  container._chartPinned = null;
  const usable = items.filter(item => item.label && isChartNumber(item.value));
  if (!usable.length) { container.innerHTML='<div class="dpe-chart-empty">Sem dados para o recorte selecionado.</div>'; return; }
  const width=760,rowHeight=48,margin={left:245,right:60,top:30,bottom:24},height=Math.max(250,margin.top+margin.bottom+usable.length*rowHeight);
  const numericValues=usable.map(item=>Number(item.value));
  const targetValues=usable.map(item=>item.target).filter(isChartNumber).map(Number);
  if(isChartNumber(target))targetValues.push(Number(target));
  let min=Math.min(0,...numericValues,...targetValues),max=Math.max(0,...numericValues,...targetValues);
  if(min===max){max=min+1}
  const span=max-min; const pad=span*.06; if(min<0)min-=pad; max+=pad;
  const plotWidth=width-margin.left-margin.right;
  const xScale=value=>margin.left+(Number(value)-min)/(max-min)*plotWidth;
  const zeroX=xScale(0);
  const showValues=usable.length<=8;
  const globalTarget=isChartNumber(target)?Number(target):null;
  const globalTargetX=globalTarget===null?null:xScale(globalTarget);
  const rows=usable.map((item,index)=>{
    const y=margin.top+index*rowHeight; const value=Number(item.value); const valueX=xScale(value); const x=Math.min(zeroX,valueX); const barWidth=Math.max(1,Math.abs(valueX-zeroX)); const color=barColorFor(item,index);
    const labelLines=wrapChartLabel(item.label,30,2); const firstLineY=y+(labelLines.length===1?24:17);
    const label=labelLines.map((line,lineIndex)=>`<tspan x="${margin.left-11}" dy="${lineIndex===0?0:13}">${escapeHtml(line)}</tspan>`).join('');
    const ownTarget=isChartNumber(item.target)?Number(item.target):null;
    const tooltipLines=[{label:'Valor',value:formatAxis(value,unit)},...(item.tooltip||[])];
    if(ownTarget!==null)tooltipLines.push({label:'Meta',value:formatAxis(ownTarget,unit)}); else if(globalTarget!==null)tooltipLines.push({label:'Meta',value:formatAxis(globalTarget,unit)});
    const aria=`${item.label}. ${tooltipLines.map(line=>`${line.label}: ${line.value}`).join('. ')}`;
    const targetMarker=ownTarget===null?'':`<line class="dpe-chart-target-marker" x1="${xScale(ownTarget)}" x2="${xScale(ownTarget)}" y1="${y+8}" y2="${y+35}"/>`;
    const valueLabel=showValues?`<text x="${value>=0?valueX+7:valueX-7}" y="${y+27}" text-anchor="${value>=0?'start':'end'}" font-size="10" font-weight="700" fill="#2b3d35">${escapeHtml(formatAxis(value,unit))}</text>`:'';
    return `<g class="dpe-chart-bar-row" data-chart-tooltip="${chartTooltipPayload(item.label,tooltipLines)}" tabindex="0" role="button" aria-label="${escapeHtml(aria)}"><text x="${margin.left-11}" y="${firstLineY}" text-anchor="end" font-size="11" fill="#2b3d35">${label}</text><rect class="dpe-chart-bar" x="${x}" y="${y+9}" width="${barWidth}" height="25" rx="5" fill="${color}"/>${targetMarker}${valueLabel}</g>`;
  }).join('');
  const globalTargetLine=globalTargetX===null?'':`<line class="dpe-chart-global-target" x1="${globalTargetX}" x2="${globalTargetX}" y1="${margin.top-9}" y2="${height-margin.bottom+1}"/><text x="${Math.min(width-margin.right-4,globalTargetX+6)}" y="${margin.top-13}" font-size="10" font-weight="800" fill="#7a5b10">Meta ${escapeHtml(formatAxis(globalTarget,unit))}</text>`;
  const zeroLine=min<0?`<line class="dpe-chart-zero" x1="${zeroX}" x2="${zeroX}" y1="${margin.top-5}" y2="${height-margin.bottom}"/>`:'';
  container.innerHTML=`${chartHint()}<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico comparativo interativo">${globalTargetLine}${zeroLine}${rows}</svg><div class="dpe-chart-tooltip" role="status" aria-live="polite"></div>`;
}

function renderGroupedHorizontalBars(container, items, defs, unit='') {
  if (!container) return;
  bindChartInteractions(container);
  container._chartPinned = null;
  const usable = (items || []).filter(item => item?.label && (defs || []).some(def => isChartNumber(item?.[def.key])));
  if (!usable.length) { container.innerHTML='<div class="dpe-chart-empty">Sem dados suficientes para comparar receita e despesa/custo neste recorte.</div>'; return; }
  const width=780,rowHeight=58,margin={left:245,right:68,top:50,bottom:26},height=Math.max(270,margin.top+margin.bottom+usable.length*rowHeight);
  const allValues=[];
  usable.forEach(item => defs.forEach(def => { const value=Number(item?.[def.key]); if(isChartNumber(item?.[def.key])) allValues.push(value); }));
  let max=Math.max(0,...allValues); if(max<=0)max=1; max*=1.07;
  const plotWidth=width-margin.left-margin.right;
  const xScale=value=>margin.left+Math.max(0,Number(value))/max*plotWidth;
  const showValues=usable.length<=7;
  const rows=usable.map((item,index)=>{
    const y=margin.top+index*rowHeight;
    const labelLines=wrapChartLabel(item.label,30,2); const firstLineY=y+(labelLines.length===1?27:20);
    const label=labelLines.map((line,lineIndex)=>`<tspan x="${margin.left-11}" dy="${lineIndex===0?0:13}">${escapeHtml(line)}</tspan>`).join('');
    const tooltipLines=[...defs.map(def=>({label:def.label,value:isChartNumber(item?.[def.key])?formatAxis(Number(item[def.key]),unit):'Não informado'})),...(item.tooltip||[])];
    const bars=defs.map((def,seriesIndex)=>{
      const rawValue=item?.[def.key]; if(!isChartNumber(rawValue))return ''; const value=Number(rawValue);
      const barY=y+9+seriesIndex*18; const barWidth=Math.max(1,xScale(value)-margin.left);
      const valueLabel=showValues?`<text x="${xScale(value)+6}" y="${barY+10}" font-size="9" font-weight="700" fill="#2b3d35">${escapeHtml(formatAxis(value,unit))}</text>`:'';
      return `<rect class="dpe-chart-bar" x="${margin.left}" y="${barY}" width="${barWidth}" height="11" rx="4" fill="${def.color}"/>${valueLabel}`;
    }).join('');
    const aria=`${item.label}. ${tooltipLines.map(line=>`${line.label}: ${line.value}`).join('. ')}`;
    return `<g class="dpe-chart-bar-row" data-chart-tooltip="${chartTooltipPayload(item.label,tooltipLines)}" tabindex="0" role="button" aria-label="${escapeHtml(aria)}"><text x="${margin.left-11}" y="${firstLineY}" text-anchor="end" font-size="11" fill="#2b3d35">${label}</text>${bars}</g>`;
  }).join('');
  const legend=(defs||[]).map((def,index)=>`<g transform="translate(${margin.left+index*170},20)"><rect width="13" height="9" rx="3" fill="${def.color}"/><text x="19" y="8" font-size="10" fill="#5b6d64">${escapeHtml(def.label)}</text></g>`).join('');
  container.innerHTML=`${chartHint()}<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Comparação interativa por curso">${legend}<line x1="${margin.left}" x2="${margin.left}" y1="${margin.top-5}" y2="${height-margin.bottom}" stroke="#9cafa5"/>${rows}</svg><div class="dpe-chart-tooltip" role="status" aria-live="polite"></div>`;
}

function formatAxis(value,unit='') {
  const number=Number(value); if(!Number.isFinite(number))return '—';
  if(unit==='R$')return number.toLocaleString('pt-BR',{style:'currency',currency:'BRL',notation:'compact',maximumFractionDigits:1});
  if(unit==='%')return `${number.toLocaleString('pt-BR',{maximumFractionDigits:1})}%`;
  if(unit==='x')return `${number.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}x`;
  return number.toLocaleString('pt-BR',{maximumFractionDigits:1});
}

async function loadRecords(code) {
  const bucket=state.records[code];
  const payload=await api('/api/management/measurements',{}, {indicador:code,offset:bucket.offset,limit:25});
  Object.assign(bucket,{items:payload.items||[],total:payload.total||0,hasMore:Boolean(payload.has_more)});
  renderRecords(code);
}
function renderRecords(code) {
  const bucket=state.records[code]; const suffix=code.replace('-',''); const body=$(`#records${suffix}`); if(!body)return;
  body.innerHTML=bucket.items.length?bucket.items.map(row=>recordRow(code,row)).join(''):`<tr><td colspan="7">Nenhum registro encontrado.</td></tr>`;
  $(`#recordsCount${suffix}`).textContent=`${bucket.total.toLocaleString('pt-BR')} registro(s)`;
  const page=Math.floor(bucket.offset/25)+1; $(`[data-page-records="${code}"]`).textContent=`Página ${page}`;
  $(`[data-prev-records="${code}"]`).disabled=bucket.offset===0; $(`[data-next-records="${code}"]`).disabled=!bucket.hasMore;
}
function recordRow(code,row) {
  const values=row.values||{}; const dimension=row.dimension_label||'TOTAL'; const canWrite=Boolean(state.access?.canEdit);
  let cells='';
  if(code==='DPE-01'){
    const cost=['faculty_cost','coordination_cost','other_direct_cost','indirect_cost'].reduce((sum,key)=>sum+(Number(values[key])||0),0); const margin=Number(values.net_revenue)?(Number(values.net_revenue)-cost)/Number(values.net_revenue)*100:null;
    cells=`<td>${escapeHtml(row.period)}</td><td>${escapeHtml(dimension)}</td><td>${formatCompactMoney(values.net_revenue)}</td><td>${formatCompactMoney(cost)}</td><td>${formatValue(margin,'%')}</td><td>${row.validated?'Sim':'Não'}</td>`;
  }else if(code==='DPE-02'){
    const expense=['personnel_expense','operational_expense','administrative_expense','financial_expense'].reduce((sum,key)=>sum+(Number(values[key])||0),0); const coverage=expense?Number(values.net_revenue)/expense:null;
    cells=`<td>${escapeHtml(row.period)}</td><td>${escapeHtml(dimension)}</td><td>${formatCompactMoney(values.net_revenue)}</td><td>${formatCompactMoney(expense)}</td><td>${formatValue(coverage,'x')}</td><td>${row.validated?'Sim':'Não'}</td>`;
  }else{
    const payroll=(Number(values.faculty_payroll)||0)+(Number(values.administrative_payroll)||0); const pct=Number(values.net_revenue)?payroll/Number(values.net_revenue)*100:null;
    cells=`<td>${escapeHtml(row.period)}</td><td>${escapeHtml(dimension)}</td><td>${formatCompactMoney(payroll)}</td><td>${formatCompactMoney(values.net_revenue)}</td><td>${formatValue(pct,'%')}</td><td>${row.validated?'Sim':'Não'}</td>`;
  }
  const actions=canWrite?`<div class="row-actions"><button data-edit-id="${row.id}" data-edit-code="${code}">Editar</button><button class="danger" data-delete-id="${row.id}" data-delete-code="${code}">Excluir</button></div>`:'';
  return `<tr>${cells}<td>${actions}</td></tr>`;
}

function openMeasurement(code, row=null) {
  if (!state.access?.canEdit) { showAlert('A DPE está em modo somente leitura para este usuário.','error'); return; }
  const spec=indicatorSpec(code); if(!spec){showAlert('Indicador não encontrado.','error');return;}
  state.editingId=row?.id||null;
  $('#measurementIndicator').value=code;
  $('#measurementCode').textContent=code;
  $('#measurementTitle').textContent=row?'Editar registro':`Registrar ${code}`;
  $('#measurementSubtitle').textContent=spec.short_name ? `${spec.short_name} · competência mensal` : 'Preencha os dados da competência mensal.';
  $('#measurementPeriod').value=row?.period||state.reference||'';
  $('#measurementNotes').value=row?.notes||'';
  $('#measurementValidated').checked=row?.validated!==false;
  $('#measurementFormErrors').classList.add('hidden'); $('#measurementFormErrors').textContent='';
  $('#measurementDimensions').innerHTML=(spec.dimensions||[]).map(key=>renderDimensionField(code,key,row?.dimensions?.[key]||'')).join('');
  $('#measurementFields').innerHTML=(spec.fields||[]).map(field=>`<label><span>${escapeHtml(field.label)}${field.required?' *':''}</span><input type="number" step="any" data-field-key="${escapeHtml(field.key)}" value="${escapeHtml(row?.values?.[field.key]??'')}" ${field.required?'required':''}><small>${escapeHtml(field.type==='currency'?'Valor em reais por competência':field.type==='integer'?'Número inteiro':'Valor numérico')}</small></label>`).join('');
  $('[data-dimension-key="course"]','#measurementForm')?.addEventListener('change',syncCourseDirectorate);
  syncCourseDirectorate();
  $('#measurementModal').classList.remove('hidden');
}

async function saveMeasurement(event) {
  event.preventDefault();
  const code=$('#measurementIndicator').value; const dimensions={}; const values={};
  $$('[data-dimension-key]','#measurementForm').forEach(input=>{if(input.value.trim())dimensions[input.dataset.dimensionKey]=input.value.trim()});
  $$('[data-field-key]','#measurementForm').forEach(input=>{if(input.value!=='')values[input.dataset.fieldKey]=Number(input.value)});
  const payload={indicator_code:code,period:$('#measurementPeriod').value.trim(),dimensions,values,source_reference:'',notes:$('#measurementNotes').value.trim(),validated:$('#measurementValidated').checked};
  setLoading(true);
  try{
    const path=state.editingId?`/api/management/measurements/${state.editingId}`:'/api/management/measurements'; const method=state.editingId?'PUT':'POST';
    await api(path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    closeModal('measurementModal'); showAlert('Registro salvo com sucesso.','success');
    await Promise.all([loadAllDashboards({preserveSelection:true}),loadRecords(code)]);
  }catch(error){const box=$('#measurementFormErrors'); if(box){box.textContent=error.message; box.classList.remove('hidden');} showAlert(error.message,'error',0)}finally{setLoading(false)}
}
async function deleteMeasurement(code,id){if(!confirm('Excluir este registro? Esta ação não pode ser desfeita.'))return;setLoading(true);try{await api(`/api/management/measurements/${id}`,{method:'DELETE'});showAlert('Registro excluído.','success');await Promise.all([loadAllDashboards({preserveSelection:true}),loadRecords(code)])}catch(error){showAlert(error.message,'error',0)}finally{setLoading(false)}}

function openImport(code){state.importIndicator=code;$('#importCode').textContent=code;$('#importFile').value='';$('#importResult').className='import-result hidden';$('#importResult').textContent='';$('#importModal').classList.remove('hidden')}
async function confirmImport(){const file=$('#importFile').files?.[0];if(!file){showImportResult('Selecione um arquivo XLSX ou XLSM.','error');return}setLoading(true);const data=new FormData();data.append('arquivo',file);try{const response=await window.DataUnivcAuth.fetch(url('/api/dpe/import',{indicador:state.importIndicator}),{method:'POST',credentials:'same-origin',body:data,headers:{'Accept':'application/json'}});let payload=null;try{payload=await response.json()}catch{}if(!response.ok){const detail=payload?.detail;const errors=detail?.linhas||[];const lines=errors.slice(0,12).map(item=>`${item.sheet||'Planilha'}${item.row?` · linha ${item.row}`:''}${item.field?` · ${item.field}`:''}: ${item.error}`).join('\n');throw new Error(`${detail?.erro||payload?.erro||'Falha na importação.'}${lines?`\n\n${lines}`:''}`)}showImportResult(payload.mensagem||'Importação concluída.','success');showAlert(payload.mensagem||'Importação concluída.','success');await Promise.all([loadAllDashboards({preserveSelection:true}),loadRecords(state.importIndicator)])}catch(error){showImportResult(error.message,'error')}finally{setLoading(false)}}
function showImportResult(message,kind){const root=$('#importResult');root.textContent=message;root.className=`import-result ${kind}`;root.classList.remove('hidden')}
function closeModal(id){$(`#${id}`)?.classList.add('hidden')}

async function loadTargets(){try{const payload=await api('/api/management/targets');const items=(payload.items||[]).filter(item=>!(item.indicator_code==='DPE-01'&&item.metric_key==='avg_hours_per_teacher'));state.targets=items;$('#targetsTable').innerHTML=items.length?items.map(item=>`<tr><td>${escapeHtml(item.indicator_code)}</td><td>${escapeHtml(metricOf(item.indicator_code,item.metric_key)?.label||item.metric_key)}</td><td>${escapeHtml(item.dimension_label||'TOTAL')}</td><td>${escapeHtml(item.valid_from)}${item.valid_to?` a ${escapeHtml(item.valid_to)}`:''}</td><td>${formatTarget(item)}</td><td>${formatAttention(item)}</td><td>${state.access?.canEdit?`<button class="table-action danger" data-delete-target="${item.id}" data-write-action>Excluir</button>`:''}</td></tr>`).join(''):'<tr><td colspan="7">Nenhuma meta cadastrada.</td></tr>';applyAccess()}catch(error){showAlert(error.message)}}
function formatTarget(item){if(item.target_min!=null||item.target_max!=null)return `${item.target_min??'—'} a ${item.target_max??'—'}`;return item.target??'—'}
function formatAttention(item){if(item.attention_min!=null||item.attention_max!=null)return `${item.attention_min??'—'} a ${item.attention_max??'—'}`;return item.attention??'—'}
async function loadActions(){try{const payload=await api('/api/management/actions');const items=payload.items||[];state.actions=items;$('#actionsTable').innerHTML=items.length?items.map(item=>`<tr><td>${escapeHtml(item.indicator_code)}</td><td>${escapeHtml(item.period||'—')}</td><td>${escapeHtml(item.problem||'')}</td><td>${escapeHtml(item.corrective_action||'')}</td><td>${escapeHtml(item.responsible||'')}</td><td>${escapeHtml(item.due_date||'—')}</td><td><span class="status-chip info">${escapeHtml(item.status||'')}</span></td><td>${state.access?.canEdit?`<button class="table-action danger" data-delete-action="${item.id}" data-write-action>Excluir</button>`:''}</td></tr>`).join(''):'<tr><td colspan="8">Nenhum plano de ação cadastrado.</td></tr>';applyAccess()}catch(error){showAlert(error.message)}}

function managementDimensionFields(code){
  const spec=indicatorSpec(code); if(!spec)return '';
  return (spec.dimensions||[]).map(key=>renderDimensionField(code,key,'')).join('') || '<div class="span-2 field-help">Meta/plano aplicado ao consolidado institucional.</div>';
}
function managementIndicatorOptions(selected='DPE-01'){return Object.values(state.indicators).map(item=>option(item.code,`${item.code} · ${item.short_name||item.name}`,item.code===selected)).join('')}
function managementMetricOptions(code, selected=''){return (indicatorSpec(code)?.metrics||[]).filter(item=>!(code==='DPE-01'&&item.key==='avg_hours_per_teacher')).map(item=>option(item.key,`${item.label}${item.unit?` (${item.unit})`:''}`,item.key===selected)).join('')}
function targetLimitFields(code,metricKey){const metric=metricOf(code,metricKey)||{};if(metric.direction==='range')return `<label><span>Meta mínima *</span><input id="targetMin" type="number" step="any" required value="${metric.target_min??''}"></label><label><span>Meta máxima *</span><input id="targetMax" type="number" step="any" required value="${metric.target_max??''}"></label><label><span>Atenção mínima</span><input id="attentionMin" type="number" step="any" value="${metric.attention_min??''}"></label><label><span>Atenção máxima</span><input id="attentionMax" type="number" step="any" value="${metric.attention_max??''}"></label>`;return `<label><span>Meta *</span><input id="targetValue" type="number" step="any" required value="${metric.target??''}"></label><label><span>Limite de atenção</span><input id="attentionValue" type="number" step="any" value="${metric.attention??''}"></label>`}
function openManagementModal(title,eyebrow,subtitle,html){$('#managementModalTitle').textContent=title;$('#managementModalEyebrow').textContent=eyebrow;$('#managementModalSubtitle').textContent=subtitle;$('#managementModalBody').innerHTML=html;$('#managementModal').classList.remove('hidden')}
function targetFormHtml(code='DPE-01',metricKey=''){const first=metricKey||indicatorSpec(code)?.metrics?.[0]?.key||'';return `<form id="targetForm" class="form-grid dpe-measurement-form"><label class="span-2"><span>Indicador *</span><select id="targetIndicator" required>${managementIndicatorOptions(code)}</select></label><label class="span-2"><span>Métrica *</span><select id="targetMetric" required>${managementMetricOptions(code,first)}</select></label><label><span>Vigência inicial *</span><input id="targetValidFrom" placeholder="AAAA-MM" required value="${state.reference||''}"></label><label><span>Vigência final</span><input id="targetValidTo" placeholder="AAAA-MM"></label><div id="targetDimensions" class="form-grid span-2 nested-grid">${managementDimensionFields(code)}</div><div id="targetLimits" class="form-grid span-2 nested-grid">${targetLimitFields(code,first)}</div><label class="span-2"><span>Justificativa</span><textarea id="targetJustification" placeholder="Contexto da meta ou decisão de gestão."></textarea></label><div id="targetFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="managementModal">Cancelar</button><button type="submit" class="button primary">Salvar meta</button></div></form>`}
function openTargetForm(){openManagementModal('Nova meta','DPE · META','Cadastre a meta com a mesma lógica de vigência usada nos painéis.',targetFormHtml());bindTargetForm()}
function bindTargetForm(){const form=$('#targetForm');const rebuild=()=>{const code=$('#targetIndicator').value;const metric=$('#targetMetric')?.value||indicatorSpec(code)?.metrics?.[0]?.key||'';$('#targetMetric').innerHTML=managementMetricOptions(code,metric);$('#targetDimensions').innerHTML=managementDimensionFields(code);$('#targetLimits').innerHTML=targetLimitFields(code,$('#targetMetric').value);bindManagementCourseSync('#targetForm')};$('#targetIndicator').addEventListener('change',rebuild);$('#targetMetric').addEventListener('change',()=>{$('#targetLimits').innerHTML=targetLimitFields($('#targetIndicator').value,$('#targetMetric').value)});bindManagementCourseSync('#targetForm');form.addEventListener('submit',saveTarget)}
function dimensionsFrom(root){const result={};$$('[data-dimension-key]',root).forEach(field=>{const value=field.value?.trim();if(value)result[field.dataset.dimensionKey]=value});return result}
function bindManagementCourseSync(rootSelector){const root=$(rootSelector);if(!root)return;const course=$('[data-dimension-key="course"]',root),directorate=$('[data-dimension-key="academic_directorate"]',root);if(course&&directorate){const sync=()=>{const found=(state.courseCatalog||[]).find(row=>row.name===course.value);directorate.value=found?.directorate_code||''};course.addEventListener('change',sync);sync()}}
async function saveTarget(event){event.preventDefault();const code=$('#targetIndicator').value,key=$('#targetMetric').value,metric=metricOf(code,key)||{};const payload={indicator_code:code,metric_key:key,valid_from:$('#targetValidFrom').value,valid_to:$('#targetValidTo').value||null,dimensions:dimensionsFrom($('#targetForm')),justification:$('#targetJustification').value.trim()||null};if(metric.direction==='range'){payload.target_min=$('#targetMin').value;payload.target_max=$('#targetMax').value;payload.attention_min=$('#attentionMin').value||null;payload.attention_max=$('#attentionMax').value||null}else{payload.target=$('#targetValue').value;payload.attention=$('#attentionValue').value||null}try{await api('/api/management/targets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeModal('managementModal');showAlert('Meta salva com sucesso.','success');await Promise.all([loadTargets(),loadAllDashboards({preserveSelection:true})])}catch(error){const box=$('#targetFormErrors');box.textContent=error.message;box.classList.remove('hidden')}}
function actionFormHtml(code='DPE-01'){return `<form id="actionForm" class="form-grid dpe-measurement-form"><label class="span-2"><span>Indicador *</span><select id="actionIndicator" required>${managementIndicatorOptions(code)}</select></label><label><span>Métrica relacionada</span><select id="actionMetric"><option value="">Indicador como um todo</option>${managementMetricOptions(code)}</select></label><label><span>Competência *</span><input id="actionPeriod" placeholder="AAAA-MM" required value="${state.reference||''}"></label><div id="actionDimensions" class="form-grid span-2 nested-grid">${managementDimensionFields(code)}</div><label class="span-2"><span>Problema identificado *</span><textarea id="actionProblem" required></textarea></label><label class="span-2"><span>Causa provável</span><textarea id="actionCause"></textarea></label><label class="span-2"><span>Ação corretiva *</span><textarea id="actionCorrective" required></textarea></label><label><span>Responsável *</span><input id="actionResponsible" required></label><label><span>Prazo *</span><input id="actionDueDate" type="date" required></label><label><span>Status</span><select id="actionStatus"><option>Aberto</option><option>Em andamento</option><option>Concluído</option><option>Atrasado</option><option>Cancelado</option></select></label><label><span>Evidência / observação</span><input id="actionEvidence"></label><div id="actionFormErrors" class="form-errors span-2 hidden"></div><div class="form-actions"><button type="button" class="button secondary" data-close-modal="managementModal">Cancelar</button><button type="submit" class="button primary">Salvar plano</button></div></form>`}
function openActionForm(){openManagementModal('Novo plano de ação','DPE · PLANO','Registre responsável, prazo e ação corretiva vinculados ao indicador.',actionFormHtml());bindActionForm()}
function bindActionForm(){const form=$('#actionForm');$('#actionIndicator').addEventListener('change',()=>{const code=$('#actionIndicator').value;$('#actionMetric').innerHTML='<option value="">Indicador como um todo</option>'+managementMetricOptions(code);$('#actionDimensions').innerHTML=managementDimensionFields(code);bindManagementCourseSync('#actionForm')});bindManagementCourseSync('#actionForm');form.addEventListener('submit',saveAction)}
async function saveAction(event){event.preventDefault();const payload={indicator_code:$('#actionIndicator').value,metric_key:$('#actionMetric').value||null,period:$('#actionPeriod').value,dimensions:dimensionsFrom($('#actionForm')),problem:$('#actionProblem').value.trim(),probable_cause:$('#actionCause').value.trim()||null,corrective_action:$('#actionCorrective').value.trim(),responsible:$('#actionResponsible').value.trim(),due_date:$('#actionDueDate').value,status:$('#actionStatus').value,evidence:$('#actionEvidence').value.trim()||null};try{await api('/api/management/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});closeModal('managementModal');showAlert('Plano de ação salvo com sucesso.','success');await loadActions()}catch(error){const box=$('#actionFormErrors');box.textContent=error.message;box.classList.remove('hidden')}}
async function deleteTarget(id){if(!confirm('Excluir esta meta?'))return;try{await api(`/api/management/targets/${id}`,{method:'DELETE'});showAlert('Meta excluída.','success');await Promise.all([loadTargets(),loadAllDashboards({preserveSelection:true})])}catch(error){showAlert(error.message)}}
async function deleteAction(id){if(!confirm('Excluir este plano de ação?'))return;try{await api(`/api/management/actions/${id}`,{method:'DELETE'});showAlert('Plano excluído.','success');await loadActions()}catch(error){showAlert(error.message)}}
function renderFileCards(){const root=$('#dpeFileCards');root.innerHTML=`<article class="dpe-file-card featured"><div><span class="eyebrow">Base financeira v0.7.7</span><h3>Receita, despesas, folha e custos sem dupla contagem</h3><p>Os novos lançamentos são feitos diretamente no sistema. A exportação financeira própria será reconstruída em uma etapa posterior sobre esta base única.</p></div><div class="dpe-file-actions">${state.access?.canEdit?'<button class="button white" data-dpe-finance-demo>Carregar demonstração financeira</button>':''}</div></article>${['DPE-01','DPE-02','DPE-03'].map(code=>`<article class="dpe-file-card"><div><span class="eyebrow">Histórico legado · ${code}</span><h3>${escapeHtml(indicatorSpec(code)?.short_name||code)}</h3><p>Modelo e exportação anteriores à base financeira única. Mantidos para auditoria e compatibilidade; não use para novos lançamentos.</p></div><div class="dpe-file-actions"><a class="button secondary compact" href="${url(`/api/dpe/modelo/${code}`)}" download>Modelo legado</a><a class="button secondary compact" href="${url(`/api/dpe/excel/${code}`,{referencia:state.reference,comparacao:state.comparison})}" download>Exportar legado</a></div></article>`).join('')}`;applyAccess()}

function navigate(section){$$('.nav-item[data-section]').forEach(item=>item.classList.toggle('active',item.dataset.section===section));$$('.page-section').forEach(item=>item.classList.toggle('active',item.id===`section-${section}`));const titles={dashboard:'Painel executivo',receitas:'Receitas',despesas:'Despesas e folha',cursos:'Resultado por curso',dpe01:'Resultado econômico por curso',dpe02:'Cobertura entre receita e despesa',dpe03:'Folha sobre receita',planos:'Planos de ação',metas:'Metas dos KPIs',arquivos:'Central de arquivos',governanca:'Governança de dados'};$('#dpePageTitle').textContent=titles[section]||'DPE';window.scrollTo({top:0,behavior:'smooth'})}
function applyFilter(sourceCode=null){if(sourceCode){state.reference=$(`[data-reference="${sourceCode}"]`).value;state.comparison=$(`[data-comparison="${sourceCode}"]`).value;const w=$(`[data-window="${sourceCode}"]`).value;state.window=w==='all'?'all':Number(w)}else{state.reference=$('#dashboardReference').value;state.comparison=$('#dashboardComparison').value;const w=$('#dashboardWindow').value;state.window=w==='all'?'all':Number(w)}loadAllDashboards({preserveSelection:true}).then(()=>typeof window.refreshDPEFinance==='function'?window.refreshDPEFinance({preserveReference:true}):null).catch(error=>showAlert(error.message,'error',0))}
function bindEvents(){
  $('#dpeDirectorateSelect')?.addEventListener('change', event => location.assign(routeForDirectorate(event.target.value)));
  $$('.nav-item[data-section]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.section)));
  $$('[data-go]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.go)));
  const applyDashboard=()=>applyFilter();
  ['#dashboardReference','#dashboardComparison','#dashboardWindow'].forEach(selector=>$(selector)?.addEventListener('change',applyDashboard));
  ['DPE-01','DPE-02','DPE-03'].forEach(code=>{
    [`[data-reference="${code}"]`,`[data-comparison="${code}"]`,`[data-window="${code}"]`].forEach(selector=>$(selector)?.addEventListener('change',()=>applyFilter(code)));
  });
  $$('[data-new]').forEach(button=>button.addEventListener('click',()=>openMeasurement(button.dataset.new)));
  $('#dpeQuickAdd')?.addEventListener('click',()=>typeof window.openDPEExpense==='function'?window.openDPEExpense():openMeasurement('DPE-01'));
  $('#measurementForm').addEventListener('submit',saveMeasurement);
  $$('[data-close-modal]').forEach(button=>button.addEventListener('click',()=>closeModal(button.dataset.closeModal)));
  $('#confirmImport').addEventListener('click',confirmImport);
  document.addEventListener('click',event=>{
    const importButton=event.target.closest('[data-import]');if(importButton){if(!importButton.disabled&&state.access?.canEdit)openImport(importButton.dataset.import);return}
    const financeDemoButton=event.target.closest('[data-dpe-finance-demo]');if(financeDemoButton){if(!state.access?.canEdit)return;if(!confirm('Criar a demonstração da nova base financeira da DPE? A operação só funciona quando a base financeira estiver vazia.'))return;setLoading(true);api('/api/dpe/finance/demo',{method:'POST'}).then(result=>{showAlert(result.mensagem||'Demonstração financeira criada.','success');return typeof window.refreshDPEFinance==='function'?window.refreshDPEFinance({preserveReference:false}):null}).catch(error=>showAlert(error.message,'error',0)).finally(()=>setLoading(false));return}
    const demoButton=event.target.closest('[data-dpe-demo]');if(demoButton){if(!state.access?.canEdit)return;if(!confirm('Criar dados demonstrativos da DPE? A operação só funciona quando a base real está vazia.'))return;setLoading(true);api('/api/dpe/demo',{method:'POST'}).then(result=>{showAlert(result.mensagem||'Demonstração criada.','success');return Promise.all([loadAllDashboards(),...['DPE-01','DPE-02','DPE-03'].map(code=>loadRecords(code))])}).catch(error=>showAlert(error.message,'error',0)).finally(()=>setLoading(false));return}
    const edit=event.target.closest('[data-edit-id]');if(edit){const row=state.records[edit.dataset.editCode].items.find(item=>String(item.id)===String(edit.dataset.editId));if(row)openMeasurement(edit.dataset.editCode,row);return}
    const del=event.target.closest('[data-delete-id]');if(del){deleteMeasurement(del.dataset.deleteCode,del.dataset.deleteId);return}
    const prev=event.target.closest('[data-prev-records]');if(prev){const b=state.records[prev.dataset.prevRecords];b.offset=Math.max(0,b.offset-25);loadRecords(prev.dataset.prevRecords);return}
    const next=event.target.closest('[data-next-records]');if(next){const b=state.records[next.dataset.nextRecords];if(b.hasMore){b.offset+=25;loadRecords(next.dataset.nextRecords)}return}
    const targetDelete=event.target.closest('[data-delete-target]');if(targetDelete){if(state.access?.canEdit)deleteTarget(targetDelete.dataset.deleteTarget);return}
    const actionDelete=event.target.closest('[data-delete-action]');if(actionDelete){if(state.access?.canEdit)deleteAction(actionDelete.dataset.deleteAction);return}
  });
  $('#newTarget').addEventListener('click',()=>{if(state.access?.canEdit)openTargetForm()});
  $('#newAction').addEventListener('click',()=>{if(state.access?.canEdit)openActionForm()});
  $('#dpeLogout').addEventListener('click',async()=>{try{await window.DataUnivcAuth.logout()}finally{location.assign('/')}});
}

document.addEventListener('DOMContentLoaded', initialize);
