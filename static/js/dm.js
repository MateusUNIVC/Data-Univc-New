const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];

const state = {
  user: null,
  access: null,
  cohorts: [],
  dashboard: null,
  students: {items: [], total: 0, offset: 0, hasMore: false},
  editingCohort: null,
  editingStudent: null,
  importKind: null,
  quality: null,
  seiHistory: [],
  seiMode: 'direct',
  seiPreview: null,
  seiSourceType: 'upload',
  studentSearchTimer: null,
  selectedStudentIds: new Set(),
  graduationPreview: null,
  seiRefreshScope: null,
  seiRefreshRunId: null,
  seiRefreshRuns: [],
  seiRefreshPauseRequested: false,
  seiRefreshProcessing: false,
  seiLastSelectedCohortIds: [],
  targetCatalog: null,
  targets: [],
};

const AREA_NAMES = {
  CTE: 'Ciência, Tecnologia e Educação',
  SDS: 'Saúde e Desigualdade Social',
};
const COLORS = {green:'#0b7a54', teal:'#398c78', blue:'#4679a6', gold:'#d9b44a', red:'#c74b50', gray:'#87978e'};

function escapeHtml(value='') {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}
function queryUrl(path, params={}) {
  const url = new URL(path, location.origin);
  url.searchParams.set('diretoria', 'DM');
  Object.entries(params).forEach(([key,value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  });
  return url.pathname + url.search;
}
async function api(path, options={}, params={}) {
  const response = await window.DataUnivcAuth.fetch(queryUrl(path, params), {
    credentials: 'same-origin',
    ...options,
    headers: {'Accept':'application/json', ...(options.headers || {})},
  });
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
function setLoading(active) { $('#dmLoading')?.classList.toggle('hidden', !active); }
function alertMessage(message, type='') {
  const box = $('#dmAlert');
  if (!box) return;
  box.textContent = message || '';
  box.className = `dm-alert ${type}`.trim();
  box.classList.toggle('hidden', !message);
  if (message) window.scrollTo({top:0, behavior:'smooth'});
}
function statusClass(status='') {
  if (status === 'Dentro da meta' || status === 'Encerrada' || status === 'Titulado') return 'good';
  if (status === 'Atenção' || status === 'Aberta') return 'attention';
  if (status === 'Fora da meta' || status === 'Desligado') return 'critical';
  if (status === 'Em andamento' || status === 'Ativo') return 'info';
  return 'neutral';
}
function chip(status) { return `<span class="status-chip ${statusClass(status)}">${escapeHtml(status || 'Sem dados')}</span>`; }
function fmtNumber(value, digits=0) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString('pt-BR',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
}
function fmtPct(value) { return value === null || value === undefined ? '—' : `${fmtNumber(value,1)}%`; }
function fmtDate(value) {
  if (!value) return '—';
  const [y,m,d] = String(value).slice(0,10).split('-');
  return `${d}/${m}/${y}`;
}
function routeForDirectorate(code) {
  return window.DataUnivcIdentity.routeForDirectorate(code);
}

async function loadIdentity() {
  state.user = await window.DataUnivcIdentity.load();
  if (!state.user) { location.assign('/'); return false; }
  state.access = state.user.directorateFor('DM');
  if (!state.access) {
    window.DataUnivcIdentity.redirectToAuthorizedHome(state.user);
    return false;
  }
  const dmName = state.user.name || state.user.email || 'Usuário';
  $('#dmUserName').textContent = dmName;
  $('#dmUserMeta').textContent = `${state.user.roleLabel} · ${state.access.canEdit ? 'Edição' : 'Leitura'}`;
  $('#dmUserDirectorate').textContent = state.access.name || 'Diretoria de Mestrado';
  window.DataUnivcIdentity.applyAvatar($('#dmUserAvatar'), state.user);
  $('#dmUserMini')?.setAttribute('title', [state.user.email, state.access.name].filter(Boolean).join(' · '));
  const select = $('#dmDirectorateSelect');
  if (select) {
    select.innerHTML = state.user.availableDirectorates.map(item =>
      `<option value="${escapeHtml(item.code)}" ${item.code === 'DM' ? 'selected' : ''}>${escapeHtml(item.code)} · ${escapeHtml(item.name)} · ${item.canEdit ? 'Edição' : 'Leitura'}</option>`
    ).join('');
    select.disabled = state.user.availableDirectorates.length <= 1;
    select.closest('.directorate-switcher')?.classList.toggle('hidden', !state.user.shouldShowSwitcher());
  }
  const canWrite = state.access.canEdit;
  document.body.classList.toggle('write-enabled', canWrite);
  $('#dmReadOnly')?.classList.toggle('hidden', canWrite);
  const badge = $('#dmDirectorateAccessBadge');
  if (badge) badge.textContent = canWrite ? 'Edição' : 'Somente leitura';
  $$('[data-write-action]').forEach(element => {
    element.hidden = !canWrite;
    element.disabled = !canWrite;
  });
  return true;
}

function showSection(section) {
  $$('.page-section').forEach(item => item.classList.toggle('active', item.id === `section-${section}`));
  $$('.nav-item[data-section]').forEach(item => item.classList.toggle('active', item.dataset.section === section));
  const titles = {
    dashboard:'Painel executivo', dm01:'Evolução por turma', dm02:'Ingresso até a defesa',
    turmas:'Turmas do Mestrado', alunos:'Alunos, defesas e titulação', sei:'Integração com o SEI', metas:'Metas dos KPIs',
    arquivos:'Planilhas', governanca:'Governança de dados',
  };
  $('#dmPageTitle').textContent = titles[section] || 'Diretoria de Mestrado';
  if (section === 'alunos') loadStudents().catch(handleError);
  if (section === 'sei') Promise.all([loadQuality(), loadSeiHistory(), loadSeiRefreshRuns()]).catch(handleError);
  window.scrollTo({top:0,behavior:'smooth'});
}

function fillCohortOptions() {
  const rows = state.cohorts || [];
  const makeOptions = (areaCode='') => rows
    .filter(row => !areaCode || row.area_code === areaCode)
    .map(row => ({value: row.id, label: `${row.area_code} · Turma ${row.cohort_number}${row.opening_date ? ` · ${fmtDate(row.opening_date)}` : ''}`}));
  const fill = (select, areaCode='', emptyLabel='Todas as turmas') => {
    if (!select) return;
    const current = select.value;
    const opts = makeOptions(areaCode);
    select.innerHTML = `<option value="">${emptyLabel}</option>` + opts.map(item => `<option value="${item.value}">${escapeHtml(item.label)}</option>`).join('');
    if ([...select.options].some(option => option.value === current)) select.value = current;
  };
  fill($('#dashboardCohort'), $('#dashboardArea')?.value || '');
  fill($('#studentCohortFilter'), $('#studentAreaFilter')?.value || '');
  fill($('#studentCohort'), '', 'Selecione a turma');
}

function dmTargetSpec() {
  return state.targetCatalog?.directorates?.DM || null;
}
function dmIndicatorSpec(code) {
  return (dmTargetSpec()?.indicators || []).find(item => item.code === code) || null;
}
function dmMetricSpec(code, key) {
  return (dmIndicatorSpec(code)?.metrics || []).find(item => item.key === key) || null;
}
function currentSemester() {
  const now = new Date();
  return `${now.getFullYear()}-SEM${now.getMonth() < 6 ? 1 : 2}`;
}
function targetFormat(value, unit='') {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return escapeHtml(value);
  const formatted = number.toLocaleString('pt-BR',{maximumFractionDigits:2});
  return unit === '%' ? `${formatted}%` : unit === 'meses' ? `${formatted} meses` : unit === 'alunos' ? `${formatted} aluno(s)` : `${formatted}${unit ? ` ${escapeHtml(unit)}` : ''}`;
}
async function loadTargets() {
  const [catalog, payload] = await Promise.all([api('/api/dm/target-catalog'), api('/api/dm/targets')]);
  state.targetCatalog = catalog;
  state.targets = (payload.items || []).filter(row => !row.dimension_key || row.dimension_key === 'TOTAL');
  renderTargets();
}
function renderTargets() {
  const body = $('#dmTargetsTable');
  if (!body || !dmTargetSpec()) return;
  const canWrite = Boolean(state.access?.canEdit);
  const customByMetric = new Map();
  (state.targets || []).forEach(row => {
    const key = `${row.indicator_code}:${row.metric_key}`;
    if (!customByMetric.has(key)) customByMetric.set(key, []);
    customByMetric.get(key).push(row);
  });
  const rows = [];
  for (const indicator of dmTargetSpec().indicators || []) {
    for (const metric of indicator.metrics || []) {
      const custom = customByMetric.get(`${indicator.code}:${metric.key}`) || [];
      if (custom.length) {
        custom.forEach(row => rows.push(`<tr><td><strong>${escapeHtml(indicator.code)}</strong><small class="table-subtitle">${escapeHtml(indicator.short_name || indicator.name)}</small></td><td>${escapeHtml(metric.label)}</td><td>${escapeHtml(row.valid_from)}${row.valid_to ? ` a ${escapeHtml(row.valid_to)}` : ' em diante'}</td><td>${targetFormat(row.target,metric.unit)}</td><td><span class="status-chip info">Cadastrada</span></td><td>${canWrite ? `<div class="row-actions"><button data-edit-target="${row.id}">Editar</button><button class="danger" data-delete-target="${row.id}">Excluir</button></div>` : '—'}</td></tr>`));
      } else {
        const hasDefault = metric.target !== null && metric.target !== undefined;
        rows.push(`<tr><td><strong>${escapeHtml(indicator.code)}</strong><small class="table-subtitle">${escapeHtml(indicator.short_name || indicator.name)}</small></td><td>${escapeHtml(metric.label)}</td><td>${hasDefault ? 'Referência padrão' : 'Sem vigência cadastrada'}</td><td>${hasDefault ? targetFormat(metric.target,metric.unit) : 'Não definida'}</td><td><span class="status-chip neutral">${hasDefault ? 'Catálogo' : 'Pendente'}</span></td><td>${canWrite ? `<button data-create-target="${indicator.code}" data-metric="${metric.key}">${hasDefault ? 'Personalizar' : 'Definir meta'}</button>` : '—'}</td></tr>`);
      }
    }
  }
  body.innerHTML = rows.join('') || '<tr><td colspan="6">Nenhuma meta disponível.</td></tr>';
}
function targetIndicatorOptions(selected='DM-01') {
  return (dmTargetSpec()?.indicators || []).map(ind => `<option value="${ind.code}" ${ind.code===selected?'selected':''}>${escapeHtml(ind.code)} · ${escapeHtml(ind.short_name || ind.name)}</option>`).join('');
}
function targetMetricOptions(code, selected='') {
  const metrics = dmIndicatorSpec(code)?.metrics || [];
  const value = selected || metrics[0]?.key || '';
  return metrics.map(metric => `<option value="${escapeHtml(metric.key)}" ${metric.key===value?'selected':''}>${escapeHtml(metric.label)}</option>`).join('');
}
function syncTargetDefaults(force=false) {
  const code = $('#targetIndicator')?.value || 'DM-01';
  const metric = dmMetricSpec(code, $('#targetMetric')?.value || '');
  if (!metric) return;
  if (force || !$('#targetValue').value) $('#targetValue').value = metric.target ?? '';
  const hint = $('#targetValueHint');
  if (hint) hint.textContent = metric.unit === 'meses' ? 'Menor ou igual à meta é considerado dentro da meta.' : 'Maior ou igual à meta é considerado dentro da meta.';
}
function openTarget(row=null, code='DM-01', metricKey='') {
  if (!dmTargetSpec()) return;
  code = row?.indicator_code || code;
  metricKey = row?.metric_key || metricKey;
  $('#targetModalTitle').textContent = row ? 'Editar meta' : 'Cadastrar meta';
  $('#targetId').value = row?.id || '';
  $('#targetIndicator').innerHTML = targetIndicatorOptions(code);
  $('#targetMetric').innerHTML = targetMetricOptions(code, metricKey);
  $('#targetValidFrom').value = row?.valid_from || currentSemester();
  $('#targetValidTo').value = row?.valid_to || '';
  $('#targetValue').value = row?.target ?? '';
  $('#targetJustification').value = row?.justification || '';
  if (!row) syncTargetDefaults(true); else syncTargetDefaults(false);
  $('#targetErrors').classList.add('hidden');
  openModal('targetModal');
}
async function saveTarget(event) {
  event.preventDefault();
  const id = $('#targetId').value;
  const payload = {
    indicator_code: $('#targetIndicator').value,
    metric_key: $('#targetMetric').value,
    valid_from: $('#targetValidFrom').value.trim().toUpperCase(),
    valid_to: $('#targetValidTo').value.trim().toUpperCase() || null,
    target: $('#targetValue').value,
    dimensions: {},
    justification: $('#targetJustification').value.trim() || null,
  };
  try {
    await api(id ? `/api/dm/targets/${id}` : '/api/dm/targets', {method:id?'PUT':'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    closeModal('targetModal');
    alertMessage('Meta da DM salva e aplicada ao painel.','success');
    await Promise.all([loadTargets(), loadDashboard()]);
  } catch(error) { handleError(error); }
}
async function deleteTarget(id) {
  if (!confirm('Excluir esta meta? O sistema usará outra vigência aplicável ou ficará sem meta definida para este indicador.')) return;
  try {
    await api(`/api/dm/targets/${id}`,{method:'DELETE'});
    alertMessage('Meta excluída.','success');
    await Promise.all([loadTargets(), loadDashboard()]);
  } catch(error) { handleError(error); }
}

async function loadCohorts() {
  const payload = await api('/api/dm/cohorts');
  state.cohorts = payload.items || [];
  fillCohortOptions();
  renderCohorts();
}

function renderCohorts() {
  const body = $('#cohortsTable');
  if (!body) return;
  const canWrite = Boolean(state.access?.canEdit);
  const area = $('#cohortAreaFilter')?.value || '';
  const status = $('#cohortStatusFilter')?.value || '';
  const rows = (state.cohorts || []).filter(row => (!area || row.area_code === area) && (!status || row.status === status));
  body.innerHTML = rows.length ? rows.map(row => `<tr>
    <td><strong>${escapeHtml(row.area_code)}</strong><small class="table-subtitle">${escapeHtml(row.area_name)}</small></td>
    <td><strong>Turma ${fmtNumber(row.cohort_number)}</strong></td>
    <td>${fmtDate(row.opening_date)}${!row.opening_date ? '<small class="table-subtitle">opcional</small>' : ''}</td>
    <td>${fmtNumber(row.vacancies_authorized)}</td><td>${fmtNumber(row.student_count)}</td>
    <td>${chip(row.status)}</td><td><div class="row-actions">${canWrite ? `<button data-manage-graduation="${row.id}" title="Abrir os alunos ativos desta turma para gerenciar titulação">Gerenciar titulação</button><button data-refresh-cohort="${row.id}" title="Consultar início e defesa de todos os alunos desta turma no SEI">Atualizar SEI</button><button data-edit-cohort="${row.id}">Editar</button><button class="danger" data-delete-cohort="${row.id}">Excluir</button>` : ''}</div></td>
  </tr>`).join('') : `<tr><td colspan="7">Nenhuma turma cadastrada para o recorte.</td></tr>`;
}

function updateDmExcelExportLinks() {
  const params = {
    area: $('#dashboardArea')?.value || '',
    turma_id: $('#dashboardCohort')?.value || '',
    data_corte: $('#dashboardAsOf')?.value || '',
  };
  const href = queryUrl('/api/dm/excel', params);
  $$('[data-dm-excel-export]').forEach(link => { link.href = href; });
}

async function loadDashboard() {
  const dashboard = await api('/api/dm/dashboard', {}, {
    area: $('#dashboardArea')?.value || '',
    turma_id: $('#dashboardCohort')?.value || '',
    data_corte: $('#dashboardAsOf')?.value || '',
  });
  state.dashboard = dashboard;
  updateDmExcelExportLinks();
  renderDashboard();
}

function metricCard(label, value, note='', icon='•') {
  return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-sub">${escapeHtml(note)}</span></article>`;
}
function renderDashboard() {
  const data = state.dashboard;
  if (!data) return;
  const overall = data.overall || {};
  $('#dashboardCards').innerHTML = [
    metricCard('Turmas', fmtNumber(overall.cohort_count), `${fmtNumber(overall.areas_with_open_cohort)} área(s) com turma aberta`, 'T'),
    metricCard('Alunos ativos', fmtNumber(overall.active_students), `${fmtNumber(overall.total_students)} vínculo(s) na base`, 'A'),
    metricCard('Titulados', fmtNumber(overall.graduated_students), `${fmtNumber(overall.defenses_count)} defesa(s) registrada(s)`, '✓'),
    metricCard('Tempo médio até a defesa', overall.average_months_to_defense == null ? '—' : `${fmtNumber(overall.average_months_to_defense,1)} meses`, 'entre ingresso individual e defesa', '24'),
    metricCard('Ocupação das vagas', fmtPct(overall.occupancy_pct), `${fmtNumber(overall.vacancies_authorized)} vaga(s) autorizada(s)`, '%'),
    metricCard('Taxa de evasão', fmtPct(overall.dropout_rate_pct), `${fmtNumber(overall.dropped_students)} desligado(s)`, '↓'),
  ].join('');
  const visibleAreas = data.visible_areas || data.areas || [];
  const cohorts = visibleAreas.flatMap(area => area.cohorts || []);
  renderDM01Chart($('#chartDashboardDM01'), cohorts);
  renderDM02Chart($('#chartDashboardDM02'), cohorts);
  $('#areaPanels').innerHTML = visibleAreas.map(renderAreaPanel).join('');
  renderIndicatorTables();
  ['CTE','SDS'].forEach(code => {
    const area = (data.areas || []).find(item => item.area_code === code);
    renderDM01Chart($(`#chartDM01${code}`), area?.cohorts || []);
    renderDM02Chart($(`#chartDM02${code}`), area?.cohorts || []);
  });
  const context = $('#dmAnalysisContext');
  if (context) context.textContent = `${$('#dashboardArea')?.selectedOptions?.[0]?.textContent || 'Todas as áreas'} · ${$('#dashboardCohort')?.selectedOptions?.[0]?.textContent || 'Todas as turmas'}`;
}
function renderAreaPanel(area) {
  const totals = area.totals || {};
  const rows = (area.cohorts || []).slice().reverse().map(row => `<div class="area-cohort-row">
    <div><strong class="cohort-number">Turma ${fmtNumber(row.cohort_number)}</strong><small>Abertura: ${fmtDate(row.opening_date)}</small></div>
    <div><strong>${fmtNumber(row.total_students)} alunos</strong><small>${fmtNumber(row.active_students)} ativos</small></div>
    <div><strong>${fmtNumber(row.graduated_students)}</strong><small>Titulados</small></div>
    <div><strong>${fmtPct(row.dropout_rate_pct)}</strong><small>Evasão</small></div>
    <div><strong>${row.average_months_to_defense == null ? '—' : `${fmtNumber(row.average_months_to_defense,1)}m`}</strong><small>Até a defesa</small></div>
    <div>${chip(row.dm01_status)}</div>
  </div>`).join('');
  return `<article class="panel area-panel"><div class="panel-heading"><div><span class="eyebrow">${escapeHtml(area.area_code)}</span><h3>${escapeHtml(area.area_name)}</h3></div>${area.has_open_cohort ? chip('Em andamento') : chip('Sem turma aberta')}</div>
    <div class="area-summary"><div class="area-summary-item"><span>Turmas</span><strong>${fmtNumber(totals.cohort_count)}</strong></div><div class="area-summary-item"><span>Alunos</span><strong>${fmtNumber(totals.total_students)}</strong></div><div class="area-summary-item"><span>Titulados</span><strong>${fmtNumber(totals.graduated_students)}</strong></div></div>
    <div class="area-cohort-list">${rows || '<div class="dm-chart-empty">Nenhuma turma cadastrada nesta área.</div>'}</div></article>`;
}

function renderIndicatorTables() {
  const cohorts = (state.dashboard?.visible_areas || state.dashboard?.areas || []).flatMap(area => area.cohorts || []);
  $('#dm01Table').innerHTML = cohorts.length ? cohorts.map(row => `<tr><td>${escapeHtml(row.area_code)}</td><td><strong>Turma ${fmtNumber(row.cohort_number)}</strong></td><td>${fmtDate(row.opening_date)}</td><td>${fmtNumber(row.vacancies_authorized)}</td><td>${fmtNumber(row.total_students)}</td><td>${fmtNumber(row.active_students)}</td><td>${fmtNumber(row.graduated_students)}</td><td>${fmtNumber(row.dropped_students)}</td><td>${fmtPct(row.occupancy_pct)}</td><td>${fmtPct(row.dropout_rate_pct)}</td><td>${chip(row.dm01_status)}</td></tr>`).join('') : `<tr><td colspan="11">Sem turmas.</td></tr>`;
  $('#dm02Table').innerHTML = cohorts.length ? cohorts.map(row => `<tr><td>${escapeHtml(row.area_code)}</td><td><strong>Turma ${fmtNumber(row.cohort_number)}</strong></td><td>${fmtNumber(row.defenses_count)}</td><td>${row.average_months_to_defense == null ? '—' : `${fmtNumber(row.average_months_to_defense,1)}m`}</td><td>${row.median_months_to_defense == null ? '—' : `${fmtNumber(row.median_months_to_defense,1)}m`}</td><td>${fmtPct(row.on_time_graduation_pct)}</td><td>${fmtNumber(row.active_over_18_no_qualification)}</td><td>${fmtNumber(row.active_over_24_no_scheduled_defense)}</td><td>${fmtNumber(row.active_over_30_no_defense)}</td><td>${chip(row.dm02_status)}</td></tr>`).join('') : `<tr><td colspan="10">Sem turmas.</td></tr>`;
}

function renderDM01Chart(container, rows) {
  if (!container) return;
  if (!rows.length) { container.innerHTML='<div class="dm-chart-empty">Nenhuma turma cadastrada nesta área.</div>'; return; }
  const width=720,height=330,margin={left:48,right:18,top:28,bottom:62};
  const max=Math.max(1,...rows.flatMap(row=>[row.total_students,row.active_students,row.graduated_students,row.dropped_students].map(Number)));
  const groups=rows.length, groupWidth=(width-margin.left-margin.right)/groups, barWidth=Math.min(18,groupWidth/5);
  const series=[['Total','total_students',COLORS.gray],['Ativos','active_students',COLORS.green],['Titulados','graduated_students',COLORS.blue],['Desligados','dropped_students',COLORS.red]];
  const y=value=>height-margin.bottom-(Number(value)||0)/max*(height-margin.top-margin.bottom);
  const grid=[0,.25,.5,.75,1].map(f=>{const value=Math.round(max*f),yy=y(value);return `<line x1="${margin.left}" x2="${width-margin.right}" y1="${yy}" y2="${yy}" stroke="#e1e8e4"/><text x="${margin.left-8}" y="${yy+4}" text-anchor="end" font-size="10" fill="#66786f">${value}</text>`}).join('');
  const bars=rows.map((row,index)=>{const base=margin.left+index*groupWidth+groupWidth/2;const elements=series.map(([,key,color],s)=>{const value=Number(row[key])||0;const x=base+(s-(series.length-1)/2)*(barWidth+3)-barWidth/2;const yy=y(value);return `<rect x="${x}" y="${yy}" width="${barWidth}" height="${height-margin.bottom-yy}" rx="3" fill="${color}"/><text x="${x+barWidth/2}" y="${Math.max(12,yy-4)}" text-anchor="middle" font-size="9" font-weight="700" fill="#30443a">${value}</text>`}).join('');return `${elements}<text x="${base}" y="${height-margin.bottom+20}" text-anchor="middle" font-size="10" font-weight="700" fill="#30443a">${escapeHtml(row.area_code ? row.area_code+' · T'+row.cohort_number : 'T'+row.cohort_number)}</text><text x="${base}" y="${height-margin.bottom+34}" text-anchor="middle" font-size="8" fill="#6a7a72">${fmtDate(row.opening_date).slice(3)}</text>`}).join('');
  const legendSvg=series.map(([label,,color],i)=>`<rect x="${margin.left+i*120}" y="${height-18}" width="10" height="10" rx="2" fill="${color}"/><text x="${margin.left+15+i*120}" y="${height-9}" font-size="9" fill="#53655c">${label}</text>`).join('');
  container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução dos alunos por turma">${grid}${bars}${legendSvg}</svg>`;
}

function renderDM02Chart(container, rows) {
  if (!container) return;
  const usable=rows.filter(row=>row.average_months_to_defense!=null || row.total_students>0);
  if (!usable.length) { container.innerHTML='<div class="dm-chart-empty">Ainda não há base suficiente para calcular tempo até a defesa.</div>'; return; }
  const width=720,height=330,margin={left:52,right:20,top:35,bottom:60};
  const max=Math.max(30,...usable.map(row=>Number(row.average_months_to_defense)||0));
  const groupWidth=(width-margin.left-margin.right)/usable.length, barWidth=Math.min(34,groupWidth*.45);
  const y=value=>height-margin.bottom-(Number(value)||0)/max*(height-margin.top-margin.bottom);
  const grid=[0,6,12,18,24,30].map(value=>{const yy=y(value);return `<line x1="${margin.left}" x2="${width-margin.right}" y1="${yy}" y2="${yy}" stroke="${value===24?'#d9b44a':'#e1e8e4'}" stroke-width="${value===24?2:1}"/><text x="${margin.left-8}" y="${yy+4}" text-anchor="end" font-size="10" fill="#66786f">${value}m</text>`}).join('');
  const bars=usable.map((row,index)=>{const value=Number(row.average_months_to_defense)||0;const x=margin.left+index*groupWidth+groupWidth/2-barWidth/2,yy=y(value);const color=value>24?COLORS.red:COLORS.green;return `<rect x="${x}" y="${yy}" width="${barWidth}" height="${height-margin.bottom-yy}" rx="5" fill="${color}"/><text x="${x+barWidth/2}" y="${Math.max(14,yy-7)}" text-anchor="middle" font-size="10" font-weight="700" fill="#30443a">${value?fmtNumber(value,1)+'m':'—'}</text><text x="${x+barWidth/2}" y="${height-margin.bottom+18}" text-anchor="middle" font-size="10" font-weight="700" fill="#30443a">${escapeHtml(row.area_code ? row.area_code+' · T'+row.cohort_number : 'T'+row.cohort_number)}</text><text x="${x+barWidth/2}" y="${height-margin.bottom+33}" text-anchor="middle" font-size="8" fill="#6a7a72">${fmtPct(row.on_time_graduation_pct)} no prazo</text>`}).join('');
  container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Tempo médio até a defesa por turma">${grid}${bars}<text x="${width-margin.right}" y="${y(24)-6}" text-anchor="end" font-size="9" fill="#8a6500">meta: 24 meses</text></svg>`;
}

async function loadStudents() {
  const payload = await api('/api/dm/students', {}, {
    area: $('#studentAreaFilter')?.value || '',
    turma_id: $('#studentCohortFilter')?.value || '',
    status: $('#studentStatusFilter')?.value || '',
    documento: $('#studentDocumentFilter')?.value || '',
    busca: $('#studentSearch')?.value || '',
    offset: state.students.offset,
    limit: 50,
  });
  state.students = {...state.students, ...payload};
  renderStudents();
}
function currentStudentFilterParams() {
  return {
    area: $('#studentAreaFilter')?.value || '',
    turma_id: $('#studentCohortFilter')?.value || '',
    status: $('#studentStatusFilter')?.value || '',
    documento: $('#studentDocumentFilter')?.value || '',
    busca: $('#studentSearch')?.value || '',
  };
}
function updateStudentSelectionControls() {
  const selectedCount = state.selectedStudentIds.size;
  const selectedButton = $('#refreshSelectedStudents');
  const graduationButton = $('#graduateSelectedStudents');
  const selectionBar = $('#studentSelectionBar');
  if (selectedButton) {
    selectedButton.disabled = !state.access?.canEdit || selectedCount === 0;
    selectedButton.textContent = selectedCount ? `Atualizar no SEI (${selectedCount})` : 'Atualizar no SEI';
  }
  if (graduationButton) {
    graduationButton.disabled = !state.access?.canEdit || selectedCount === 0;
    graduationButton.textContent = selectedCount ? `Registrar defesa (${selectedCount})` : 'Registrar defesa';
  }
  if (selectionBar) selectionBar.classList.toggle('hidden', selectedCount === 0 || !state.access?.canEdit);
  if ($('#studentSelectionCount')) $('#studentSelectionCount').textContent = `${fmtNumber(selectedCount)} aluno(s) selecionado(s)`;
  if ($('#studentSelectionScope')) {
    const total = Number(state.students.total || 0);
    $('#studentSelectionScope').textContent = selectedCount === total && total > 0
      ? 'Todos os alunos do filtro atual estão selecionados.'
      : 'A seleção pode atravessar páginas. Nenhuma alteração ocorre sem confirmação.';
  }
  const cohortButton = $('#refreshCohortStudents');
  if (cohortButton) cohortButton.disabled = !state.access?.canEdit || !$('#studentCohortFilter')?.value;
  const selectAll = $('#studentsSelectAll');
  if (selectAll) {
    const pageIds = (state.students.items || []).map(row => Number(row.id));
    const selectedOnPage = pageIds.filter(id => state.selectedStudentIds.has(id)).length;
    selectAll.checked = pageIds.length > 0 && selectedOnPage === pageIds.length;
    selectAll.indeterminate = selectedOnPage > 0 && selectedOnPage < pageIds.length;
  }
  const banner = $('#studentSelectFilteredBanner');
  const pageIds = (state.students.items || []).map(row => Number(row.id));
  const pageFullySelected = pageIds.length > 0 && pageIds.every(id => state.selectedStudentIds.has(id));
  const canExpand = pageFullySelected && Number(state.students.total || 0) > pageIds.length && selectedCount < Number(state.students.total || 0);
  banner?.classList.toggle('hidden', !canExpand);
  if (canExpand && $('#studentSelectFilteredText')) {
    $('#studentSelectFilteredText').textContent = `${fmtNumber(pageIds.length)} desta página selecionados. O filtro atual possui ${fmtNumber(state.students.total)} alunos.`;
  }
}

function diplomaChip(value) {
  const text = value || 'Não informado';
  const cls = text === 'Emitido' ? 'issued' : text === 'Em emissão' ? 'issuing' : text === 'Pendente' ? 'pending' : '';
  return `<span class="diploma-chip ${cls}">${escapeHtml(text)}</span>`;
}
function dmRowIcon(name) {
  const paths = {
    sei: '<path d="M6 8.5A7 7 0 0 1 18.8 7M18 3v5h-5"/><path d="M18 15.5A7 7 0 0 1 5.2 17M6 21v-5h5"/><circle cx="12" cy="12" r="2.3"/>',
    edit: '<path d="M4 20h4l11-11-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    delete: '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13"/>'
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name] || ''}</svg>`;
}
function renderStudents() {
  const body=$('#studentsTable'); if(!body)return;
  const canWrite=Boolean(state.access?.canEdit);
  body.innerHTML=state.students.items.length ? state.students.items.map(row=>{
    const entryNote = !row.entry_date ? 'pendente · consulte o SEI' : (row.last_course_dates_sei_at ? 'confirmado no SEI' : 'informado manualmente');
    const defenseNote = row.status === 'Titulado' && !row.defense_date ? '<small class="table-subtitle">data não informada</small>' : (row.defense_date && row.last_course_dates_sei_at && row.status === 'Titulado' ? '<small class="table-subtitle">confirmada pelo SEI</small>' : '');
    const titleAction = row.status === 'Ativo'
      ? `<button class="primary-action" data-graduate-student="${row.id}">Registrar defesa</button>`
      : row.status === 'Titulado' ? `<button data-graduate-student="${row.id}">${row.defense_date ? 'Defesa' : 'Completar defesa'}</button>` : '';
    return `<tr>
    <td><input type="checkbox" data-select-student="${row.id}" ${state.selectedStudentIds.has(Number(row.id))?'checked':''} aria-label="Selecionar ${escapeHtml(row.student_name)}"></td>
    <td>${escapeHtml(row.area_code)}</td>
    <td><strong>Turma ${fmtNumber(row.cohort_number)}</strong></td>
    <td>${escapeHtml(row.student_code)}</td>
    <td>${escapeHtml(row.student_name)}</td>
    <td><div>${fmtDate(row.entry_date)}</div><small class="table-subtitle">${entryNote}</small></td>
    <td>${fmtDate(row.defense_date)}${defenseNote}</td>
    <td>${chip(row.status)}</td>
    <td><div class="row-actions">${canWrite?`${titleAction}<button class="row-icon-action" data-refresh-student="${row.id}" title="Atualizar pelo SEI" aria-label="Atualizar ${escapeHtml(row.student_name)} pelo SEI">${dmRowIcon('sei')}</button><button class="row-icon-action" data-edit-student="${row.id}" title="Editar aluno" aria-label="Editar ${escapeHtml(row.student_name)}">${dmRowIcon('edit')}</button><button class="row-icon-action danger" data-delete-student="${row.id}" title="Excluir aluno" aria-label="Excluir ${escapeHtml(row.student_name)}">${dmRowIcon('delete')}</button>`:''}</div></td>
  </tr>`}).join('') : `<tr><td colspan="9">Nenhum aluno encontrado.</td></tr>`;
  $('#studentsCount').textContent=`${fmtNumber(state.students.total)} registro(s)`;
  const pageSize = Number(state.students.limit || 50);
  const total = Number(state.students.total || 0);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(totalPages, Math.floor(Number(state.students.offset || 0) / pageSize) + 1);
  const firstRecord = total ? Number(state.students.offset || 0) + 1 : 0;
  const lastRecord = Math.min(total, Number(state.students.offset || 0) + (state.students.items || []).length);
  $('#studentsPage').textContent = total ? `Página ${currentPage} de ${totalPages} · ${fmtNumber(firstRecord)}–${fmtNumber(lastRecord)} de ${fmtNumber(total)}` : 'Nenhum registro';
  $('#studentsFirst').disabled = currentPage <= 1;
  $('#studentsPrev').disabled = currentPage <= 1;
  $('#studentsNext').disabled = currentPage >= totalPages;
  $('#studentsLast').disabled = currentPage >= totalPages;
  updateStudentSelectionControls();
}

function openModal(id) { $(`#${id}`).classList.remove('hidden'); }
function closeModal(id) { $(`#${id}`).classList.add('hidden'); }
function formError(id, error) {
  const box=$(`#${id}`); if(!box)return;
  const fields=error?.payload?.detail?.campos || error?.payload?.campos;
  box.textContent=fields ? Object.entries(fields).map(([field,message])=>`${field}: ${message}`).join('\n') : error.message;
  box.classList.remove('hidden');
}
function openCohort(row=null) {
  state.editingCohort=row;
  $('#cohortId').value=row?.id||'';
  $('#cohortArea').value=row?.area_code||'CTE';
  $('#cohortNumber').value=row?.cohort_number||'';
  $('#cohortOpening').value=row?.opening_date||'';
  $('#cohortVacancies').value=row?.vacancies_authorized||'';
  $('#cohortStatus').value=row?.status||'Em andamento';
  $('#cohortNotes').value=row?.notes||'';
  $('#cohortModalTitle').textContent=row?'Editar turma':'Cadastrar turma';
  $('#cohortErrors').classList.add('hidden');
  openModal('cohortModal');
}
function openStudent(row=null) {
  state.editingStudent=row;
  $('#studentId').value=row?.id||'';
  fillCohortOptions();
  $('#studentCohort').value=row?.cohort_id||'';
  $('#studentCode').value=row?.student_code||'';
  $('#studentName').value=row?.student_name||'';
  syncStudentEntryFromCohort(row?.entry_date || '');
  $('#studentQualification').value=row?.qualification_date||'';
  $('#studentDefense').value=row?.defense_date||'';
  $('#studentDefenseScheduled').value=row?.defense_scheduled_date||'';
  $('#studentExit').value=row?.exit_date||'';
  $('#studentStatus').value=row?.status||'Ativo';
  $('#studentResearchLine').value=row?.research_line||'';
  $('#studentNotes').value=row?.notes||'';
  $('#studentModalTitle').textContent=row?'Editar aluno':'Cadastrar aluno';
  $('#studentErrors').classList.add('hidden');
  openModal('studentModal');
}
function syncStudentEntryFromCohort(fallback='') {
  // A turma organiza o vínculo, mas não determina o ingresso individual.
  // O campo permanece vazio até informação manual ou confirmação pelo SEI.
  $('#studentEntry').value = fallback || '';
}

async function saveCohort(event) {
  event.preventDefault();
  const payload={area_code:$('#cohortArea').value,cohort_number:$('#cohortNumber').value,opening_date:$('#cohortOpening').value,vacancies_authorized:$('#cohortVacancies').value||null,status:$('#cohortStatus').value,notes:$('#cohortNotes').value||null};
  try {
    const id=$('#cohortId').value;
    await api(id?`/api/dm/cohorts/${id}`:'/api/dm/cohorts',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    closeModal('cohortModal'); alertMessage('Turma salva com sucesso.','success'); await refreshAll();
  } catch(error){formError('cohortErrors',error)}
}
async function saveStudent(event) {
  event.preventDefault();
  const entryDate=$('#studentEntry').value || null;
  const sameExisting=Boolean(state.editingStudent && entryDate===state.editingStudent.entry_date);
  const studentStatus=$('#studentStatus').value;
  const payload={cohort_id:$('#studentCohort').value,student_code:$('#studentCode').value,student_name:$('#studentName').value,entry_date:entryDate,entry_date_estimated:sameExisting?Boolean(state.editingStudent.entry_date_estimated):false,qualification_date:$('#studentQualification').value||null,defense_date:$('#studentDefense').value||null,defense_scheduled_date:$('#studentDefenseScheduled').value||null,exit_date:$('#studentExit').value||null,status:studentStatus,advisor:state.editingStudent?.advisor||null,research_line:$('#studentResearchLine').value||null,notes:$('#studentNotes').value||null};
  try {
    const id=$('#studentId').value;
    await api(id?`/api/dm/students/${id}`:'/api/dm/students',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    closeModal('studentModal'); alertMessage('Aluno salvo com sucesso.','success'); await refreshAll();
  } catch(error){formError('studentErrors',error)}
}
function graduationPayloadFromForm() {
  const mode = document.querySelector('input[name="graduationMode"]:checked')?.value || 'common';
  const payload = {student_ids:[...state.selectedStudentIds], operation_type: state.selectedStudentIds.size === 1 ? 'individual' : 'bulk'};
  if (mode === 'common') {
    payload.defense_date = $('#graduationCommonDefense')?.value || null;
  } else {
    payload.students = $$('[data-graduation-row]').map(row => ({
      student_id:Number(row.dataset.graduationRow),
      defense_date:row.querySelector('[data-grad-defense]')?.value || null,
    }));
  }
  return payload;
}
function renderGraduationSummary(preview) {
  const summary = preview?.summary || {};
  $('#graduationSummary').innerHTML = [
    ['Selecionados', summary.selected || 0], ['Elegíveis', summary.eligible || 0],
    ['Alterações', summary.changes || 0], ['Sem defesa', summary.without_defense || 0], ['Bloqueados', summary.blocked || 0],
  ].map(([label,value])=>`<div class="graduation-summary-card"><span>${label}</span><strong>${fmtNumber(value)}</strong></div>`).join('');
}
function renderGraduationRows(rows=[]) {
  const body=$('#graduationStudentsTable'); if(!body)return;
  body.innerHTML = rows.map(row=>`<tr data-graduation-row="${row.student_id}">
    <td><strong>${escapeHtml(row.student_name)}</strong><small class="table-subtitle">${escapeHtml(row.student_code)} · ${escapeHtml(row.area_code||'')} · Turma ${fmtNumber(row.cohort_number)}</small></td>
    <td>${chip(row.previous_status)}</td>
    <td><input type="date" data-grad-defense value="${escapeHtml(row.new_defense_date||row.previous_defense_date||'')}"></td>
  </tr>`).join('');
}
function renderGraduationPreview(preview) {
  state.graduationPreview = preview;
  renderGraduationSummary(preview);
  renderGraduationRows((preview.rows && preview.rows.length ? preview.rows : preview.selection_rows) || []);
  const errors = preview.errors || [];
  const box=$('#graduationErrors');
  if(errors.length){
    box.textContent=errors.slice(0,8).map(item=>`${item.student_name||item.student_code||'Aluno'}: ${item.error}`).join('\n');
    box.classList.remove('hidden');
  } else box.classList.add('hidden');
  const result=$('#graduationPreview');
  if(preview.ok){
    result.className='graduation-preview success';
    const missingDefense=Number(preview.summary?.without_defense||0);
    result.textContent=`Validação concluída: ${fmtNumber(preview.summary?.changes||0)} alteração(ões) pronta(s) para confirmação.${missingDefense?` ${fmtNumber(missingDefense)} aluno(s) ficará(ão) Titulado(s) sem data de defesa informada.`:''} Nenhuma mudança foi gravada ainda.`;
  } else {
    result.className='graduation-preview warning';
    result.textContent=`Há ${fmtNumber(preview.summary?.blocked||errors.length)} aluno(s) que precisam de revisão. Nenhuma mudança foi gravada.`;
  }
  $('#confirmGraduation').disabled=!preview.ok || Number(preview.summary?.changes||0)===0;
}
async function previewGraduation() {
  const payload=graduationPayloadFromForm();
  const preview=await api('/api/dm/graduation/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  renderGraduationPreview(preview);
  return preview;
}
async function openGraduationModal(studentIds=null) {
  if(studentIds){state.selectedStudentIds=new Set(studentIds.map(Number));updateStudentSelectionControls();}
  if(!state.selectedStudentIds.size)return;
  state.graduationPreview=null;
  $('#graduationModalTitle').textContent=state.selectedStudentIds.size===1?'Registrar defesa':'Registrar defesas em lote';
  $('#graduationModalSubtitle').textContent=`${fmtNumber(state.selectedStudentIds.size)} aluno(s) selecionado(s). A data de defesa, quando informada, confirma Titulado. Registros históricos sem data conhecida podem ser confirmados sem criar data fictícia.`;
  $('#graduationCommonDefense').value='';
  const radio=document.querySelector('input[name="graduationMode"][value="common"]'); if(radio)radio.checked=true;
  syncGraduationMode();
  $('#graduationPreview').className='graduation-preview'; $('#graduationPreview').textContent='Carregando a situação atual dos alunos…';
  $('#graduationErrors').classList.add('hidden'); $('#confirmGraduation').disabled=true;
  openModal('graduationModal');
  try { await previewGraduation(); } catch(error){ formError('graduationErrors',error); }
}
function syncGraduationMode() {
  const mode=document.querySelector('input[name="graduationMode"]:checked')?.value||'common';
  $('#graduationCommonFields')?.classList.toggle('hidden',mode!=='common');
  $('#graduationIndividualWrap')?.classList.toggle('hidden',mode!=='individual');
  $('#confirmGraduation').disabled=true;
  $('#graduationPreview').className='graduation-preview';
  $('#graduationPreview').textContent='Revise os campos e clique em “Validar alteração”.';
}
async function confirmGraduation() {
  const preview=await previewGraduation();
  if(!preview.ok || !Number(preview.summary?.changes||0))return;
  const button=$('#confirmGraduation'); button.disabled=true; button.textContent='Confirmando…';
  try{
    const result=await api('/api/dm/graduation/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(graduationPayloadFromForm())});
    closeModal('graduationModal');
    state.selectedStudentIds.clear();
    alertMessage(`${fmtNumber(result.updated||0)} aluno(s) atualizado(s) como Titulado. Operação ${result.operation_id?.slice(0,8)||''}.`,'success');
    await Promise.all([loadStudents(),loadDashboard()]);
  }catch(error){formError('graduationErrors',error)}finally{button.textContent='Confirmar';}
}
async function selectAllFilteredStudents() {
  const result=await api('/api/dm/students/ids',{},currentStudentFilterParams());
  state.selectedStudentIds=new Set((result.ids||[]).map(Number));
  renderStudents();
}

function openImport(kind) {
  state.importKind=kind;
  $('#importTitle').textContent=kind==='turmas'?'Importar turmas':'Importar alunos';
  $('#importFile').value=''; $('#importResult').className='import-result hidden'; $('#importResult').textContent=''; openModal('importModal');
}
async function confirmImport() {
  const file=$('#importFile').files[0]; if(!file){$('#importResult').textContent='Selecione um arquivo.';$('#importResult').className='import-result error';return}
  const form=new FormData(); form.append('arquivo',file);
  try {const result=await api(`/api/dm/import/${state.importKind}`,{method:'POST',body:form});$('#importResult').textContent=result.mensagem||'Importação concluída.';$('#importResult').className='import-result success';await refreshAll()}
  catch(error){const lines=error?.payload?.detail?.linhas||[];$('#importResult').textContent=[error.message,...lines.slice(0,12).map(item=>`Linha ${item.row||'?'} · ${item.field||''}: ${item.error}`)].join('\n');$('#importResult').className='import-result error'}
}

async function loadQuality({silent=false}={}) {
  try {
    state.quality = await api('/api/dm/quality');
    renderQuality();
  } catch (error) {
    state.quality = null;
    renderQuality();
    if (!silent) throw error;
  }
}

function renderQuality() {
  const container = $('#seiQualityCards');
  if (!container) return;
  const quality = state.quality || {};
  const total = Number(quality.students_total || 0);
  container.innerHTML = [
    metricCard('Alunos na base do DM', fmtNumber(total), `${fmtNumber(quality.students_seen_in_sei || 0)} reconhecido(s) pelo SEI`, 'A'),
    metricCard('Ingressos confirmados', fmtNumber(quality.students_with_confirmed_entry || 0), `${fmtNumber(quality.students_missing_entry || 0)} aguardando confirmação`, 'I'),
    metricCard('Consultas acadêmicas no SEI', fmtNumber(quality.students_course_dates_checked || 0), `${fmtNumber(quality.students_defense_confirmed_by_sei || 0)} defesa(s) confirmada(s)`, 'S'),
    metricCard('Turmas reconhecidas pelo SEI', fmtNumber(quality.cohorts_seen_in_sei || 0), 'área + número da turma', 'T'),
  ].join('');
}

async function loadSeiHistory({silent=false}={}) {
  try {
    const payload = await api('/api/dm/sei/history', {}, {limit: 20});
    state.seiHistory = payload.items || [];
    renderSeiHistory();
  } catch (error) {
    state.seiHistory = [];
    renderSeiHistory(error);
    if (!silent) throw error;
  }
}

function fmtDateTime(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? escapeHtml(value) : parsed.toLocaleString('pt-BR');
}

function renderSeiHistory(error=null) {
  const body = $('#seiHistoryTable');
  if (!body) return;
  if (error) {
    body.innerHTML = `<tr><td colspan="8">O histórico estará disponível após aplicar a migration 017 do DM.</td></tr>`;
    return;
  }
  body.innerHTML = state.seiHistory.length ? state.seiHistory.map(row => `<tr>
    <td>${fmtDateTime(row.completed_at)}</td>
    <td>${escapeHtml(({sei_direto:'Acesso direto',upload_xlsx:'XLSX enviado',sei_import_datas:'Dados após importação',sei_import_defesas:'Defesas após importação',sei_atualizacao_datas:'Atualização de alunos',sei_atualizacao_defesas:'Atualização de turma/alunos'}[row.source_type]) || row.source_type || 'SEI')}</td>
    <td>${fmtNumber(row.cohorts_detected)}</td>
    <td>${fmtNumber(row.students_detected)}</td>
    <td>${fmtNumber(row.students_created)}</td>
    <td>${fmtNumber(row.students_updated)}</td>
    <td>${fmtNumber(row.students_not_seen)}</td>
    <td>${chip(row.status)}</td>
  </tr>`).join('') : `<tr><td colspan="8">Nenhuma sincronização do SEI registrada.</td></tr>`;
}

const SEI_REFRESH_TERMINAL = new Set(['COMPLETED','COMPLETED_WITH_ERRORS','CANCELLED']);

function seiQueueStatusLabel(status='') {
  return ({
    PENDING:'Aguardando', IN_PROGRESS:'Em andamento', PAUSED:'Pausada',
    COMPLETED:'Concluída', COMPLETED_WITH_ERRORS:'Concluída com falhas', CANCELLED:'Cancelada',
  })[String(status || '').toUpperCase()] || status || '—';
}

function seiQueueStatusClass(status='') {
  return ({PENDING:'pending',IN_PROGRESS:'running',PAUSED:'paused',COMPLETED:'completed',COMPLETED_WITH_ERRORS:'errors',CANCELLED:'errors'})[String(status || '').toUpperCase()] || '';
}

function seiQueueScopeLabel(run={}) {
  const scope = run.scope || {};
  if (scope.all_cohorts) return 'Todas as turmas';
  if (scope.cohort_id) {
    const cohort = (state.cohorts || []).find(row => Number(row.id) === Number(scope.cohort_id));
    return cohort ? `${cohort.area_code} · Turma ${cohort.cohort_number}` : `Turma #${scope.cohort_id}`;
  }
  if ((scope.cohort_ids || []).length) return `${scope.cohort_ids.length} turma(s)`;
  if ((scope.student_ids || []).length) return `${scope.student_ids.length} aluno(s)`;
  return run.scope_type === 'all_cohorts' ? 'Todas as turmas' : 'Seleção de alunos';
}

function renderSeiRefreshRuns(error=null) {
  const body = $('#seiQueueTable');
  const summary = $('#seiQueueSummary');
  if (!body || !summary) return;
  if (error) {
    summary.innerHTML = '';
    body.innerHTML = `<tr><td colspan="8"><div class="sei-queue-empty">Não foi possível carregar as filas: ${escapeHtml(error.message || 'erro desconhecido')}.</div></td></tr>`;
    return;
  }
  const rows = state.seiRefreshRuns || [];
  const active = rows.filter(run => !SEI_REFRESH_TERMINAL.has(String(run.status || '').toUpperCase()));
  const failed = rows.reduce((sum, run) => sum + Number(run.failed || 0), 0);
  const processed = rows.reduce((sum, run) => sum + Number(run.processed || 0), 0);
  summary.innerHTML = rows.length ? `
    <div class="sei-queue-stat"><span>Filas recentes</span><strong>${fmtNumber(rows.length)}</strong></div>
    <div class="sei-queue-stat"><span>Ativas / pausadas</span><strong>${fmtNumber(active.length)}</strong></div>
    <div class="sei-queue-stat"><span>Processados</span><strong>${fmtNumber(processed)}</strong></div>
    <div class="sei-queue-stat"><span>Falhas para revisão</span><strong>${fmtNumber(failed)}</strong></div>` : '';
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="8"><div class="sei-queue-empty">Nenhuma fila de atualização individual criada ainda.</div></td></tr>';
    return;
  }
  body.innerHTML = rows.map(run => {
    const total = Number(run.total || 0);
    const processedRun = Number(run.processed || 0);
    const pct = total > 0 ? Math.max(0, Math.min(100, Math.round((processedRun / total) * 100))) : 0;
    const status = String(run.status || '').toUpperCase();
    const canContinue = ['PENDING','IN_PROGRESS','PAUSED'].includes(status) && Number(run.remaining || 0) > 0;
    const canPause = ['PENDING','IN_PROGRESS'].includes(status) && Number(run.remaining || 0) > 0;
    const canRetry = Number(run.failed || 0) > 0 && ['COMPLETED_WITH_ERRORS','PAUSED'].includes(status);
    const buttons = [
      canContinue ? `<button class="button primary compact" data-sei-run-continue="${run.id}">${status === 'PAUSED' ? 'Continuar' : 'Abrir fila'}</button>` : '',
      canPause ? `<button class="button secondary compact" data-sei-run-pause="${run.id}">Pausar</button>` : '',
      canRetry ? `<button class="button secondary compact" data-sei-run-retry="${run.id}">Reprocessar falhas</button>` : '',
      Number(run.failed || 0) > 0 ? `<button class="button secondary compact" data-sei-run-errors="${run.id}">Ver falhas</button>` : '',
    ].filter(Boolean).join('');
    return `<tr>
      <td><strong>#${fmtNumber(run.id)}</strong></td>
      <td>${fmtDateTime(run.created_at)}</td>
      <td>${escapeHtml(seiQueueScopeLabel(run))}</td>
      <td><div class="sei-queue-progress"><div class="sei-queue-progress-track"><span style="width:${pct}%"></span></div><small>${fmtNumber(processedRun)} / ${fmtNumber(total)} · ${pct}%</small></div></td>
      <td>${fmtNumber(run.completed || 0)}</td>
      <td>${fmtNumber(run.failed || 0)}</td>
      <td><span class="sei-queue-status ${seiQueueStatusClass(status)}">${escapeHtml(seiQueueStatusLabel(status))}</span></td>
      <td><div class="sei-queue-actions">${buttons || '<span class="muted">—</span>'}</div></td>
    </tr>`;
  }).join('');
}

async function loadSeiRefreshRuns({silent=false}={}) {
  try {
    const payload = await api('/api/dm/sei/refresh-runs', {}, {limit:20});
    state.seiRefreshRuns = payload.runs || [];
    renderSeiRefreshRuns();
  } catch (error) {
    state.seiRefreshRuns = [];
    renderSeiRefreshRuns(error);
    if (!silent) throw error;
  }
}

async function showSeiRefreshRunErrors(runId) {
  const panel = $('#seiQueueDetails');
  if (!panel) return;
  panel.classList.remove('hidden');
  panel.innerHTML = '<div class="sei-queue-empty">Carregando falhas…</div>';
  try {
    const payload = await api(`/api/dm/sei/refresh-runs/${runId}/items`, {}, {status:'FAILED',limit:500});
    const items = payload.items || [];
    panel.innerHTML = `<div class="sei-queue-details-head"><strong>Fila #${fmtNumber(runId)} · alunos para revisão</strong><button type="button" class="button secondary compact" data-sei-close-errors>Fechar</button></div>${items.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Aluno</th><th>Turma</th><th>Tentativas</th><th>Último erro</th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${escapeHtml(item.student_name || 'Aluno')}</strong><small class="table-subtitle">${escapeHtml(item.student_code || '')}</small></td><td>${escapeHtml(item.area_code || '—')} ${item.cohort_number ? `· Turma ${escapeHtml(item.cohort_number)}` : ''}</td><td>${fmtNumber(item.attempts || 0)}</td><td class="sei-queue-error">${escapeHtml(item.last_error || 'Sem detalhe informado.')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="sei-queue-empty">Nenhuma falha pendente nesta fila.</div>'}`;
  } catch (error) {
    panel.innerHTML = `<div class="sei-queue-empty">${escapeHtml(error.message || 'Não foi possível carregar as falhas.')}</div>`;
  }
}

function openExistingSeiRefreshRun(run) {
  if (!run) return;
  state.seiRefreshRunId = Number(run.id);
  state.seiRefreshScope = {...(run.scope || {})};
  state.seiRefreshPauseRequested = false;
  $('#seiRefreshScope').textContent = `Fila #${fmtNumber(run.id)} · ${seiQueueScopeLabel(run)} · ${fmtNumber(run.processed || 0)} de ${fmtNumber(run.total || 0)} processados`;
  $('#seiRefreshPassword').value = '';
  $('#seiRefreshError').textContent = '';
  $('#seiRefreshError').classList.add('hidden');
  $('#seiRefreshResult').textContent = '';
  $('#seiRefreshResult').classList.add('hidden');
  $('#pauseSeiRefresh')?.classList.add('hidden');
  hideSeiOperationProgress('#seiRefreshProgress');
  const button = $('#confirmSeiRefresh');
  if (button) button.textContent = run.status === 'PAUSED' ? 'Continuar fila' : 'Continuar atualização';
  openModal('seiRefreshModal');
}

async function pauseSeiRefreshRun(runId) {
  const payload = await api(`/api/dm/sei/refresh-runs/${runId}/pause`, {method:'POST'});
  await loadSeiRefreshRuns({silent:true});
  return payload.run;
}

async function retryFailedSeiRefreshRun(runId) {
  const payload = await api(`/api/dm/sei/refresh-runs/${runId}/retry-failed`, {method:'POST'});
  await loadSeiRefreshRuns({silent:true});
  openExistingSeiRefreshRun(payload.run);
}

function openSeiRefreshModal({cohortId=null, cohortIds=[], studentIds=[], allCohorts=false}={}) {
  const ids = [...new Set((studentIds || []).map(Number).filter(Number.isFinite))];
  const cohortIdList = [...new Set((cohortIds || []).map(Number).filter(Number.isFinite))];
  const singleCohortId = cohortId ? Number(cohortId) : null;
  if (!allCohorts && !singleCohortId && !cohortIdList.length && !ids.length) {
    alertMessage('Selecione uma turma ou pelo menos um aluno para atualizar no SEI.', 'error');
    return;
  }
  state.seiRefreshScope = {
    cohort_id: singleCohortId,
    cohort_ids: cohortIdList,
    student_ids: ids,
    all_cohorts: Boolean(allCohorts),
  };
  state.seiRefreshRunId = null;
  state.seiRefreshPauseRequested = false;
  state.seiRefreshProcessing = false;
  $('#pauseSeiRefresh')?.classList.add('hidden');
  const cohort = singleCohortId ? state.cohorts.find(row => Number(row.id) === singleCohortId) : null;
  $('#seiRefreshScope').textContent = allCohorts
    ? `Todas as turmas · ${(state.cohorts || []).length} cadastrada(s)`
    : (cohort
      ? `${cohort.area_code} · Turma ${cohort.cohort_number} · todos os alunos`
      : (cohortIdList.length ? `${cohortIdList.length} turma(s) selecionada(s)` : `${ids.length} aluno(s) selecionado(s)`));
  $('#seiRefreshPassword').value = '';
  $('#seiRefreshError').textContent = '';
  $('#seiRefreshError').classList.add('hidden');
  $('#seiRefreshResult').textContent = '';
  $('#seiRefreshResult').classList.add('hidden');
  hideSeiOperationProgress('#seiRefreshProgress');
  openModal('seiRefreshModal');
}

function navigateToStudents({cohortId=null, all=false, status=null}={}) {
  const cohort = cohortId ? (state.cohorts || []).find(row => Number(row.id) === Number(cohortId)) : null;
  if (cohort) {
    $('#studentAreaFilter').value = cohort.area_code;
    fillCohortOptions();
    $('#studentCohortFilter').value = String(cohort.id);
  } else if (all) {
    $('#studentAreaFilter').value = '';
    fillCohortOptions();
    $('#studentCohortFilter').value = '';
  }
  if (status !== null && $('#studentStatusFilter')) $('#studentStatusFilter').value = status;
  state.selectedStudentIds.clear();
  state.students.offset = 0;
  showSection('alunos');
}


function renderSeiOperationProgress(selector, {title, message, stage, status} = {}) {
  const container = $(selector);
  if (!container) return;
  if (window.DataUNIVC?.progress?.render) {
    window.DataUNIVC.progress.render(container, {title, message, stage, status});
  } else {
    container.textContent = `${title || 'Processando'} — ${message || 'Aguarde.'}`;
    container.classList.remove('hidden');
  }
}

function hideSeiOperationProgress(selector) {
  const container = $(selector);
  if (!container) return;
  if (window.DataUNIVC?.progress?.hide) window.DataUNIVC.progress.hide(container);
  else container.classList.add('hidden');
}

async function confirmSeiRefresh() {
  const scope = state.seiRefreshScope;
  if (!scope) return;
  const username = $('#seiRefreshUsername')?.value.trim() || '';
  const password = $('#seiRefreshPassword')?.value || '';
  const errorBox = $('#seiRefreshError');
  const resultBox = $('#seiRefreshResult');
  errorBox?.classList.add('hidden');
  resultBox?.classList.add('hidden');
  if (!username || !password) {
    if (errorBox) {
      errorBox.textContent = 'Informe usuário e senha do SEI.';
      errorBox.classList.remove('hidden');
    }
    return;
  }
  const button = $('#confirmSeiRefresh');
  const pauseButton = $('#pauseSeiRefresh');
  if (button) button.disabled = true;
  if (pauseButton) {
    pauseButton.classList.remove('hidden');
    pauseButton.disabled = false;
    pauseButton.textContent = 'Pausar após este lote';
  }
  state.seiRefreshPauseRequested = false;
  state.seiRefreshProcessing = true;
  renderSeiOperationProgress('#seiRefreshProgress', {
    title: scope.all_cohorts ? 'Atualizando todas as turmas pelo SEI' : 'Atualizando alunos pelo SEI',
    message: 'Preparando a fila segura. Cada lote é salvo antes do próximo começar.',
    stage: state.seiRefreshRunId ? `Retomando fila #${state.seiRefreshRunId}` : 'Criando fila de alunos',
  });
  if (button) button.textContent = 'Processando em lotes…';
  try {
    let run = null;
    if (state.seiRefreshRunId) {
      const existing = await api(`/api/dm/sei/refresh-runs/${state.seiRefreshRunId}`);
      run = existing.run;
      if (run.status === 'PAUSED') {
        const resumed = await api(`/api/dm/sei/refresh-runs/${run.id}/resume`, {method:'POST'});
        run = resumed.run;
      }
    } else {
      const created = await api('/api/dm/sei/refresh-runs', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(scope),
      });
      run = created.run;
      state.seiRefreshRunId = Number(run.id);
    }

    let updated = 0;
    let defenses = 0;
    let batches = 0;
    while (run && !SEI_REFRESH_TERMINAL.has(run.status) && run.status !== 'PAUSED' && Number(run.remaining || 0) > 0) {
      const total = Number(run.total || 0);
      const processed = Number(run.processed || 0);
      const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
      renderSeiOperationProgress('#seiRefreshProgress', {
        title: 'Atualizando datas e titulação pelo SEI',
        message: `${fmtNumber(processed)} de ${fmtNumber(total)} aluno(s) processado(s). Você pode pausar; a pausa acontece após o lote atual terminar.`,
        stage: `Fila #${fmtNumber(run.id)} · lote ${batches + 1} · ${pct}% concluído`,
        status: `${fmtNumber(run.completed || 0)} concluído(s) · ${fmtNumber(run.failed || 0)} para revisão`,
      });
      const beforeProcessed = Number(run.processed || 0);
      const result = await api(`/api/dm/sei/refresh-runs/${run.id}/batch`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({usuario:username, senha:password}),
      });
      run = result.run;
      batches += 1;
      updated += Number(result.batch?.updated || 0);
      defenses += Number(result.batch?.defenses_confirmed || 0);
      await loadSeiRefreshRuns({silent:true});

      if (state.seiRefreshPauseRequested && !SEI_REFRESH_TERMINAL.has(run.status)) {
        run = await pauseSeiRefreshRun(run.id);
        break;
      }
      if (Number(run.processed || 0) <= beforeProcessed && Number(result.batch?.processed || 0) === 0 && Number(run.remaining || 0) > 0) {
        throw new Error('O lote não avançou. A fila foi preservada para uma nova tentativa.');
      }
    }

    if (run?.status === 'PAUSED') {
      if (resultBox) {
        resultBox.innerHTML = `<strong>Fila pausada com segurança</strong><div class="sei-preview-summary compact-summary">
          <div class="sei-preview-card"><span>Processados</span><strong>${fmtNumber(run.processed || 0)}</strong></div>
          <div class="sei-preview-card"><span>Pendentes</span><strong>${fmtNumber(run.pending || 0)}</strong></div>
          <div class="sei-preview-card"><span>Concluídos</span><strong>${fmtNumber(run.completed || 0)}</strong></div>
          <div class="sei-preview-card"><span>Revisar</span><strong>${fmtNumber(run.failed || 0)}</strong></div>
        </div><small>Fila #${fmtNumber(run.id)} preservada. Você pode fechar esta janela e continuar depois em Integração com o SEI.</small>`;
        resultBox.classList.remove('hidden');
      }
      alertMessage(`Fila #${fmtNumber(run.id)} pausada. O progresso foi preservado.`, 'warning');
      await loadSeiRefreshRuns({silent:true});
      return;
    }

    const message = `SEI atualizado: ${fmtNumber(run?.processed || 0)} processado(s), ${fmtNumber(updated)} atualizado(s), ${fmtNumber(defenses)} defesa(s) confirmada(s) e ${fmtNumber(run?.failed || 0)} para revisão.`;
    if (resultBox) {
      resultBox.innerHTML = `<strong>Atualização concluída</strong><div class="sei-preview-summary compact-summary">
        <div class="sei-preview-card"><span>Processados</span><strong>${fmtNumber(run?.processed || 0)}</strong></div>
        <div class="sei-preview-card"><span>Atualizados neste acesso</span><strong>${fmtNumber(updated)}</strong></div>
        <div class="sei-preview-card"><span>Defesas confirmadas</span><strong>${fmtNumber(defenses)}</strong></div>
        <div class="sei-preview-card"><span>Revisar</span><strong>${fmtNumber(run?.failed || 0)}</strong></div>
      </div><small>Fila #${fmtNumber(run?.id)} · ${fmtNumber(batches)} lote(s) neste acesso. As credenciais do SEI não foram persistidas.</small>`;
      resultBox.classList.remove('hidden');
    }
    state.selectedStudentIds.clear();
    await refreshAll();
    closeModal('seiRefreshModal');
    state.seiRefreshScope = null;
    state.seiRefreshRunId = null;
    alertMessage(message, Number(run?.failed || 0) ? 'warning' : 'success');
    if (scope.cohort_id) navigateToStudents({cohortId:scope.cohort_id});
    else if (scope.all_cohorts || (scope.cohort_ids || []).length) navigateToStudents({all:true});
    else showSection('alunos');
  } catch (error) {
    if (errorBox) {
      errorBox.textContent = `${error.message || 'Não foi possível consultar o SEI.'}${state.seiRefreshRunId ? ` A fila #${state.seiRefreshRunId} foi preservada; feche a janela e continue pela área de filas.` : ''}`;
      errorBox.classList.remove('hidden');
    }
    await loadSeiRefreshRuns({silent:true});
  } finally {
    const passwordInput = $('#seiRefreshPassword');
    if (passwordInput) passwordInput.value = '';
    state.seiRefreshProcessing = false;
    state.seiRefreshPauseRequested = false;
    hideSeiOperationProgress('#seiRefreshProgress');
    if (pauseButton) pauseButton.classList.add('hidden');
    if (button) {
      button.disabled = false;
      button.textContent = state.seiRefreshRunId ? 'Continuar fila' : 'Consultar e atualizar';
    }
  }
}

function setSeiStep(step) {
  const panels = {source:'#seiSourceStep', preview:'#seiPreviewStep', result:'#seiResultStep'};
  Object.entries(panels).forEach(([name, selector]) => $(selector)?.classList.toggle('hidden', name !== step));
  $$('[data-sei-step-indicator]').forEach(item => item.classList.toggle('active', item.dataset.seiStepIndicator === step));
}

function clearSeiErrors() {
  ['#seiSourceError','#seiCommitError'].forEach(selector => {
    const box = $(selector);
    if (!box) return;
    box.textContent = '';
    box.classList.add('hidden');
  });
}

function showSeiError(selector, error) {
  const box = $(selector);
  if (!box) return;
  const fields = error?.payload?.detail?.campos || error?.payload?.campos;
  const details = error?.payload?.detail?.detalhes || [];
  const lines = [error.message || 'Não foi possível concluir a operação.'];
  if (fields) lines.push(...Object.entries(fields).map(([field, message]) => `${field}: ${message}`));
  if (Array.isArray(details)) lines.push(...details.slice(0,12).map(item => item.error || JSON.stringify(item)));
  box.textContent = lines.join('\n');
  box.classList.remove('hidden');
}

function openSeiModal(mode='direct') {
  state.seiMode = mode;
  state.seiPreview = null;
  state.seiSourceType = mode === 'direct' ? 'sei_direto' : 'upload_xlsx';
  $('#seiModalTitle').textContent = mode === 'direct' ? 'Buscar relatório integral no SEI' : 'Analisar Excel Sintético do SEI';
  $('#seiDirectFields').classList.toggle('hidden', mode !== 'direct');
  $('#seiUploadFields').classList.toggle('hidden', mode !== 'upload');
  $('#seiPassword').value = '';
  $('#seiReportFile').value = '';
  $('#seiExcludeTest').checked = true;
  $('#seiRemoveDemo').checked = true;
  $('#seiTechnicalYear').value = new Date().getFullYear();
  $('#seiPreviewSummary').innerHTML = '';
  $('#seiCohortPreviewTable').innerHTML = '';
  $('#seiResultContent').innerHTML = '';
  clearSeiErrors();
  hideSeiOperationProgress('#seiOperationProgress');
  hideSeiOperationProgress('#seiCommitProgress');
  setSeiStep('source');
  openModal('seiModal');
}

function selectedSeiCohortKeys() {
  return $$('[data-sei-cohort-select]:checked').map(input => input.dataset.seiCohortSelect);
}

function updateSeiCohortSelection() {
  const selected = new Set(selectedSeiCohortKeys());
  const count = $('#seiSelectedCohortsCount');
  if (count) count.textContent = `${selected.size} turma(s) selecionada(s)`;
  if ($('#seiCommitButton')) $('#seiCommitButton').disabled = selected.size === 0;
}

function renderSeiPreview() {
  const preview = state.seiPreview;
  if (!preview) return;
  const summary = preview.summary || {};
  $('#seiPreviewSummary').innerHTML = `
    <div class="sei-preview-card"><span>Turmas encontradas</span><strong>${fmtNumber(summary.cohort_count)}</strong><small>${fmtNumber(summary.cohorts_new)} nova(s)</small></div>
    <div class="sei-preview-card"><span>Alunos encontrados</span><strong>${fmtNumber(summary.student_count)}</strong><small>${fmtNumber(summary.students_new)} novo(s)</small></div>
    <div class="sei-preview-card"><span>CTE</span><strong>${fmtNumber(summary.area_counts?.CTE?.students || 0)}</strong><small>${fmtNumber(summary.area_counts?.CTE?.cohorts || 0)} turma(s)</small></div>
    <div class="sei-preview-card"><span>SDS</span><strong>${fmtNumber(summary.area_counts?.SDS?.students || 0)}</strong><small>${fmtNumber(summary.area_counts?.SDS?.cohorts || 0)} turma(s)</small></div>
  `;
  const body = $('#seiCohortPreviewTable');
  body.innerHTML = (preview.cohorts || []).map(row => {
    const selected = Boolean(row.default_selected);
    const key = escapeHtml(row.key);
    const existingOpeningDate = String(row.existing_opening_date || '').trim();
    const dateCell = existingOpeningDate
      ? `<div class="sei-opening-control" data-sei-opening-control="${key}" data-existing-opening-date="${escapeHtml(existingOpeningDate)}" data-editing="0">
          <div class="sei-opening-summary">
            <span class="sei-existing-date">${fmtDate(existingOpeningDate)}</span>
            <button type="button" class="sei-opening-action" data-sei-opening-toggle="${key}">Alterar</button>
          </div>
          <div class="sei-opening-editor hidden">
            <input type="date" value="${escapeHtml(existingOpeningDate)}" data-sei-opening-date="${key}" data-sei-opening-existing="1">
            <button type="button" class="sei-opening-cancel" data-sei-opening-cancel="${key}">Cancelar</button>
          </div>
        </div>`
      : `<div class="sei-opening-control" data-sei-opening-control="${key}" data-existing-opening-date="" data-editing="0">
          <div class="sei-opening-summary">
            <span class="sei-opening-placeholder">Opcional</span>
            <button type="button" class="sei-opening-action" data-sei-opening-toggle="${key}">Informar data</button>
          </div>
          <div class="sei-opening-editor hidden">
            <input type="date" data-sei-opening-date="${key}" data-sei-opening-existing="0">
            <button type="button" class="sei-opening-cancel" data-sei-opening-cancel="${key}">Cancelar</button>
          </div>
        </div>`;
    const statusBadge = row.existing_is_demo
      ? '<span class="quality-badge demo">Demonstração</span>'
      : (row.existing
        ? '<span class="quality-badge confirmed">Já cadastrada</span>'
        : '<span class="quality-badge pending">Nova turma</span>');
    return `<tr>
      <td><input type="checkbox" data-sei-cohort-select="${escapeHtml(row.key)}" data-sei-default="${row.default_selected?'1':'0'}" ${selected?'checked':''} aria-label="Selecionar ${escapeHtml(row.key)}"></td>
      <td><strong>${escapeHtml(row.area_code)}</strong><small class="table-subtitle">${escapeHtml(row.area_name)}</small></td>
      <td><strong>${escapeHtml(row.raw_label)}</strong><small class="table-subtitle">Turma ${fmtNumber(row.cohort_number)}</small></td>
      <td>${fmtNumber(row.student_count)}</td>
      <td>${statusBadge}</td>
      <td class="sei-opening-cell">${dateCell}</td>
    </tr>`;
  }).join('');
  updateSeiCohortSelection();
  syncSeiOpeningAvailability();
  hideSeiOperationProgress('#seiCommitProgress');
  setSeiStep('preview');
}

async function analyzeSei() {
  clearSeiErrors();
  const button = $('#seiAnalyzeButton');
  button.disabled = true;
  button.textContent = state.seiMode === 'direct' ? 'Consultando o SEI…' : 'Analisando planilha…';
  renderSeiOperationProgress('#seiOperationProgress', {
    title: state.seiMode === 'direct' ? 'Consultando relatório integral no SEI' : 'Analisando relatório do SEI',
    message: state.seiMode === 'direct'
      ? 'Autenticando, solicitando o relatório e preparando a prévia de turmas e alunos.'
      : 'Validando o arquivo e preparando a prévia de turmas e alunos.',
    stage: state.seiMode === 'direct' ? 'Conectando ao SEI' : 'Validando arquivo',
  });
  try {
    const excludeTest = $('#seiExcludeTest').checked;
    let preview;
    if (state.seiMode === 'direct') {
      const username = $('#seiUsername').value.trim();
      const password = $('#seiPassword').value;
      if (!username || !password) throw new Error('Informe o usuário e a senha do SEI.');
      preview = await api('/api/dm/sei/preview', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          usuario: username,
          senha: password,
          ano_tecnico: $('#seiTechnicalYear').value,
          excluir_turmas_teste: excludeTest,
        }),
      });
    } else {
      const file = $('#seiReportFile').files[0];
      if (!file) throw new Error('Selecione o Excel Sintético gerado pelo SEI.');
      const form = new FormData();
      form.append('arquivo', file);
      preview = await api('/api/dm/sei/preview-file', {method:'POST', body:form}, {excluir_turmas_teste: excludeTest});
    }
    state.seiPreview = preview;
    state.seiSourceType = preview.source_type || (state.seiMode === 'direct' ? 'sei_direto' : 'upload_xlsx');
    renderSeiPreview();
  } catch (error) {
    showSeiError('#seiSourceError', error);
  } finally {
    hideSeiOperationProgress('#seiOperationProgress');
    button.disabled = false;
    button.textContent = 'Gerar prévia';
  }
}

function setSeiOpeningControlState(control, editing) {
  if (!control) return;
  control.dataset.editing = editing ? '1' : '0';
  control.querySelector('.sei-opening-summary')?.classList.toggle('hidden', editing);
  control.querySelector('.sei-opening-editor')?.classList.toggle('hidden', !editing);
  if (editing) control.querySelector('[data-sei-opening-date]')?.focus();
}

function syncSeiOpeningAvailability() {
  $$('[data-sei-opening-control]').forEach(control => {
    const key = control.dataset.seiOpeningControl;
    const selected = Boolean(document.querySelector(`[data-sei-cohort-select="${CSS.escape(key)}"]`)?.checked);
    control.classList.toggle('disabled', !selected);
    control.querySelectorAll('button,input').forEach(element => { element.disabled = !selected; });
  });
}

function collectOpeningDates() {
  const selected = new Set(selectedSeiCohortKeys());
  if (!selected.size) throw new Error('Selecione pelo menos uma turma para sincronizar.');
  const openingDates = {};
  let updateExistingOpeningDates = false;
  $$('[data-sei-opening-control]').forEach(control => {
    const key = control.dataset.seiOpeningControl;
    if (!selected.has(key) || control.dataset.editing !== '1') return;
    const input = control.querySelector('[data-sei-opening-date]');
    if (!input) return;
    input.classList.remove('invalid');
    if (!input.checkValidity()) {
      input.classList.add('invalid');
      throw new Error(`Revise a data de abertura da turma ${key}.`);
    }
    const value = String(input.value || '').trim();
    if (!value) return;
    openingDates[key] = value;
    const existing = String(control.dataset.existingOpeningDate || '').trim();
    if (existing && existing !== value) updateExistingOpeningDates = true;
  });
  return { openingDates, updateExistingOpeningDates };
}

async function commitSei() {
  if (!state.seiPreview?.report) return;
  clearSeiErrors();
  const button = $('#seiCommitButton');
  const selectedKeys = selectedSeiCohortKeys();
  button.disabled = true;
  button.textContent = 'Sincronizando…';
  renderSeiOperationProgress('#seiCommitProgress', {
    title: 'Sincronizando dados do SEI',
    message: 'Gravando no Data UNIVC as turmas e os alunos selecionados. As datas individuais serão atualizadas depois, em uma etapa separada.',
    stage: 'Atualizando turmas e alunos',
  });
  try {
    const openingDateSelection = collectOpeningDates();
    const result = await api('/api/dm/sei/commit', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        report: state.seiPreview.report,
        opening_dates: openingDateSelection.openingDates,
        atualizar_datas_existentes: openingDateSelection.updateExistingOpeningDates,
        selected_cohort_keys: selectedKeys,
        excluir_turmas_teste: $('#seiExcludeTest').checked,
        remover_demonstracao: $('#seiRemoveDemo').checked,
        source_type: state.seiSourceType,
        consultar_datas_alunos: false,
      }),
    });
    const sync = result.sync || {};
    state.seiLastSelectedCohortIds = (result.selected_cohort_ids || sync.selected_cohort_ids || []).map(Number).filter(Number.isFinite);
    const warnings = result.warnings || [];
    const dates = result.student_dates || {};
    const datePanel = `<div class="sei-info-list"><strong>Atualização individual separada</strong><span>${escapeHtml(dates.message || 'As turmas foram sincronizadas. Agora você pode atualizar início, conclusão e titulação em uma operação separada.')}</span></div>`;
    $('#seiResultContent').innerHTML = `
      <div class="sei-result-hero"><span class="sei-result-check">✓</span><div><strong>Sincronização concluída</strong><p>${escapeHtml(result.message || 'A base do DM foi atualizada.')}</p></div></div>
      <div class="sei-preview-summary">
        <div class="sei-preview-card"><span>Turmas selecionadas</span><strong>${fmtNumber(selectedKeys.length)}</strong></div>
        <div class="sei-preview-card"><span>Turmas criadas</span><strong>${fmtNumber(sync.cohorts_created)}</strong></div>
        <div class="sei-preview-card"><span>Alunos novos</span><strong>${fmtNumber(sync.students_created)}</strong></div>
        <div class="sei-preview-card"><span>Atualizados</span><strong>${fmtNumber(sync.students_updated)}</strong></div>
      </div>
      ${datePanel}
      <div class="form-actions sei-result-actions"><button type="button" class="button primary" id="seiRefreshSyncedCohorts">Atualizar datas e titulação pelo SEI</button></div>
      ${warnings.length ? `<div class="sei-info-list"><strong>Observações da sincronização</strong><ul>${warnings.slice(0,20).map(item=>`<li>${escapeHtml(item)}</li>`).join('')}</ul>${warnings.length>20?`<small>Mais ${warnings.length-20} observação(ões) ficaram registradas no histórico.</small>`:''}</div>` : '<div class="sei-success-note">Nenhum aviso adicional foi gerado.</div>'}
    `;
    $('#seiRefreshSyncedCohorts')?.addEventListener('click',()=>openSeiRefreshModal({cohortIds:state.seiLastSelectedCohortIds}));
    setSeiStep('result');
    await refreshAll();
  } catch (error) {
    showSeiError('#seiCommitError', error);
  } finally {
    $('#seiPassword').value = '';
    hideSeiOperationProgress('#seiCommitProgress');
    button.disabled = false;
    button.textContent = 'Confirmar sincronização';
    updateSeiCohortSelection();
  }
}

function resetSeiMemory() {
  state.seiPreview = null;
  $('#seiPassword').value = '';
  $('#seiReportFile').value = '';
}

async function refreshAll() {
  setLoading(true);
  try {
    await loadCohorts();
    await loadTargets();
    await loadDashboard();
    state.students.offset=0;
    await loadStudents();
    await Promise.all([loadQuality({silent:true}), loadSeiHistory({silent:true}), loadSeiRefreshRuns({silent:true})]);
  }
  finally {setLoading(false)}
}
function handleError(error) { console.error(error); alertMessage(error.message||'Ocorreu um erro.','error'); }

function bindEvents() {
  if (document.body.dataset.dmEventsBound === '1') return;
  document.body.dataset.dmEventsBound = '1';
  $$('.nav-item[data-section]').forEach(item=>item.addEventListener('click',()=>showSection(item.dataset.section)));
  $$('[data-go]').forEach(item=>item.addEventListener('click',()=>showSection(item.dataset.go)));
  $('#dmDirectorateSelect')?.addEventListener('change',event=>location.assign(routeForDirectorate(event.target.value)));
  const refreshDashboard = () => loadDashboard().catch(handleError);
  $('#dashboardArea')?.addEventListener('change',()=>{ fillCohortOptions(); refreshDashboard(); });
  $('#dashboardCohort')?.addEventListener('change',refreshDashboard);
  $('#dashboardAsOf')?.addEventListener('change',refreshDashboard);
  $('#cohortAreaFilter')?.addEventListener('change',renderCohorts);
  $('#cohortStatusFilter')?.addEventListener('change',renderCohorts);
  const refreshStudents = () => { state.selectedStudentIds.clear(); state.students.offset=0; loadStudents().catch(handleError); };
  $('#studentAreaFilter')?.addEventListener('change',()=>{ fillCohortOptions(); refreshStudents(); });
  $('#studentCohortFilter')?.addEventListener('change',()=>{ refreshStudents(); updateStudentSelectionControls(); });
  $('#studentStatusFilter')?.addEventListener('change',refreshStudents);
  $('#studentDocumentFilter')?.addEventListener('change',refreshStudents);
  $('#studentSearch')?.addEventListener('input',()=>{ clearTimeout(state.studentSearchTimer); state.studentSearchTimer=setTimeout(refreshStudents,260); });
  $('#studentCohort')?.addEventListener('change',()=>syncStudentEntryFromCohort());
  $('#studentDefense')?.addEventListener('change',event=>{ if (event.target.value && $('#studentStatus')) $('#studentStatus').value='Titulado'; });
  $('#studentsFirst')?.addEventListener('click',()=>{state.students.offset=0;loadStudents().catch(handleError)});
  $('#studentsPrev')?.addEventListener('click',()=>{const size=Number(state.students.limit||50);state.students.offset=Math.max(0,state.students.offset-size);loadStudents().catch(handleError)});
  $('#studentsNext')?.addEventListener('click',()=>{const size=Number(state.students.limit||50);if(state.students.has_more){state.students.offset+=size;loadStudents().catch(handleError)}});
  $('#studentsLast')?.addEventListener('click',()=>{const size=Number(state.students.limit||50);const total=Number(state.students.total||0);state.students.offset=Math.max(0,(Math.max(1,Math.ceil(total/size))-1)*size);loadStudents().catch(handleError)});
  $('#studentsSelectAll')?.addEventListener('change',event=>{
    (state.students.items||[]).forEach(row=>{
      if(event.target.checked) state.selectedStudentIds.add(Number(row.id));
      else state.selectedStudentIds.delete(Number(row.id));
    });
    renderStudents();
  });
  $('#refreshAllCohorts')?.addEventListener('click',()=>openSeiRefreshModal({allCohorts:true}));
  $('#refreshSelectedStudents')?.addEventListener('click',()=>openSeiRefreshModal({studentIds:[...state.selectedStudentIds]}));
  $('#graduateSelectedStudents')?.addEventListener('click',()=>openGraduationModal());
  $('#clearStudentSelection')?.addEventListener('click',()=>{state.selectedStudentIds.clear();renderStudents();});
  $('#selectAllFilteredStudents')?.addEventListener('click',()=>selectAllFilteredStudents().catch(handleError));
  $$('input[name="graduationMode"]').forEach(input=>input.addEventListener('change',syncGraduationMode));
  $('#previewGraduation')?.addEventListener('click',()=>previewGraduation().catch(error=>formError('graduationErrors',error)));
  $('#confirmGraduation')?.addEventListener('click',confirmGraduation);
  $('#refreshCohortStudents')?.addEventListener('click',()=>openSeiRefreshModal({cohortId:$('#studentCohortFilter').value}));
  $('#confirmSeiRefresh')?.addEventListener('click',confirmSeiRefresh);
  ['#dmQuickAdd','#newCohort','#newCohortDM01'].forEach(selector=>$(selector)?.addEventListener('click',()=>openCohort()));
  ['#newStudent','#newStudentDM02'].forEach(selector=>$(selector)?.addEventListener('click',()=>openStudent()));
  $('#cohortForm')?.addEventListener('submit',saveCohort); $('#studentForm')?.addEventListener('submit',saveStudent);
  $$('[data-close-modal]').forEach(item=>item.addEventListener('click',()=>{
    if (item.dataset.closeModal === 'seiModal') resetSeiMemory();
    if (item.dataset.closeModal === 'graduationModal') state.graduationPreview = null;
    if (item.dataset.closeModal === 'seiRefreshModal') {
      if (state.seiRefreshProcessing) {
        state.seiRefreshPauseRequested = true;
        alertMessage('Pausa solicitada. O lote atual será concluído e salvo antes de fechar a fila.', 'warning');
        return;
      }
      const password = $('#seiRefreshPassword');
      if (password) password.value = '';
      state.seiRefreshScope = null;
      state.seiRefreshRunId = null;
    }
    closeModal(item.dataset.closeModal);
  }));
  $$('[data-import-kind]').forEach(item=>item.addEventListener('click',()=>openImport(item.dataset.importKind)));
  $('#confirmImport')?.addEventListener('click',confirmImport);
  $('#seiDirectButton')?.addEventListener('click',()=>openSeiModal('direct'));
  $('#seiUploadButton')?.addEventListener('click',()=>openSeiModal('upload'));
  $('#seiAnalyzeButton')?.addEventListener('click',analyzeSei);
  $('#seiCohortPreviewTable')?.addEventListener('change',event=>{
    if(event.target.matches('[data-sei-cohort-select]')){updateSeiCohortSelection();syncSeiOpeningAvailability();}
    if(event.target.matches('[data-sei-opening-date]')) event.target.classList.remove('invalid');
  });
  $('#seiCohortPreviewTable')?.addEventListener('click',event=>{
    const toggle=event.target.closest('[data-sei-opening-toggle]');
    const cancel=event.target.closest('[data-sei-opening-cancel]');
    if(toggle){
      const control=toggle.closest('[data-sei-opening-control]');
      setSeiOpeningControlState(control,true);
      return;
    }
    if(cancel){
      const control=cancel.closest('[data-sei-opening-control]');
      const input=control?.querySelector('[data-sei-opening-date]');
      if(input) input.value=control.dataset.existingOpeningDate || '';
      input?.classList.remove('invalid');
      setSeiOpeningControlState(control,false);
    }
  });
  $('#seiSelectNewCohorts')?.addEventListener('click',()=>{$$('[data-sei-cohort-select]').forEach(input=>input.checked=input.dataset.seiDefault==='1');updateSeiCohortSelection();syncSeiOpeningAvailability();});
  $('#seiSelectAllCohorts')?.addEventListener('click',()=>{$$('[data-sei-cohort-select]').forEach(input=>input.checked=true);updateSeiCohortSelection();syncSeiOpeningAvailability();});
  $('#seiClearCohorts')?.addEventListener('click',()=>{$$('[data-sei-cohort-select]').forEach(input=>input.checked=false);updateSeiCohortSelection();syncSeiOpeningAvailability();});
  $('#seiBackButton')?.addEventListener('click',()=>setSeiStep('source'));
  $('#seiCommitButton')?.addEventListener('click',commitSei);
  $('#seiOpenStudentsButton')?.addEventListener('click',()=>{const ids=[...state.seiLastSelectedCohortIds];resetSeiMemory();closeModal('seiModal');if(ids.length===1)navigateToStudents({cohortId:ids[0]});else navigateToStudents({all:true})});
  $('#refreshSeiHistory')?.addEventListener('click',()=>Promise.all([loadQuality(),loadSeiHistory()]).catch(handleError));
  $('#refreshSeiQueues')?.addEventListener('click',()=>loadSeiRefreshRuns().catch(handleError));
  $('#pauseSeiRefresh')?.addEventListener('click',()=>{
    if (!state.seiRefreshProcessing) return;
    state.seiRefreshPauseRequested = true;
    const button = $('#pauseSeiRefresh');
    if (button) { button.disabled = true; button.textContent = 'Pausando após o lote atual…'; }
  });
  $('#seiQueueTable')?.addEventListener('click',async event=>{
    const continueButton = event.target.closest('[data-sei-run-continue]');
    const pauseButton = event.target.closest('[data-sei-run-pause]');
    const retryButton = event.target.closest('[data-sei-run-retry]');
    const errorsButton = event.target.closest('[data-sei-run-errors]');
    try {
      if (continueButton) {
        const run = state.seiRefreshRuns.find(row=>Number(row.id)===Number(continueButton.dataset.seiRunContinue));
        openExistingSeiRefreshRun(run); return;
      }
      if (pauseButton) {
        await pauseSeiRefreshRun(Number(pauseButton.dataset.seiRunPause));
        alertMessage('Fila pausada. O progresso foi preservado.', 'warning'); return;
      }
      if (retryButton) {
        await retryFailedSeiRefreshRun(Number(retryButton.dataset.seiRunRetry)); return;
      }
      if (errorsButton) {
        await showSeiRefreshRunErrors(Number(errorsButton.dataset.seiRunErrors)); return;
      }
    } catch(error) { handleError(error); }
  });
  $('#seiQueueDetails')?.addEventListener('click',event=>{
    if (event.target.closest('[data-sei-close-errors]')) $('#seiQueueDetails')?.classList.add('hidden');
  });
  $('#resetDemo')?.addEventListener('click',async()=>{if(!confirm('Recriar somente os dados demonstrativos do DM? Dados reais serão preservados.'))return;try{setLoading(true);const result=await api('/api/dm/demo/reset',{method:'POST'});alertMessage(result.mensagem,'success');await refreshAll()}catch(error){handleError(error)}finally{setLoading(false)}});
  $('#cohortsTable')?.addEventListener('click',async event=>{const manage=event.target.closest('[data-manage-graduation]');const refresh=event.target.closest('[data-refresh-cohort]');const edit=event.target.closest('[data-edit-cohort]');const remove=event.target.closest('[data-delete-cohort]');if(manage){navigateToStudents({cohortId:Number(manage.dataset.manageGraduation),status:'Ativo'});return;}if(refresh){openSeiRefreshModal({cohortId:Number(refresh.dataset.refreshCohort)});return;}if(edit){openCohort(state.cohorts.find(row=>String(row.id)===edit.dataset.editCohort))}if(remove&&confirm('Excluir esta turma?')){try{await api(`/api/dm/cohorts/${remove.dataset.deleteCohort}`,{method:'DELETE'});await refreshAll()}catch(error){handleError(error)}}});
  $('#studentsTable')?.addEventListener('change',event=>{const checkbox=event.target.closest('[data-select-student]');if(!checkbox)return;const id=Number(checkbox.dataset.selectStudent);if(checkbox.checked)state.selectedStudentIds.add(id);else state.selectedStudentIds.delete(id);updateStudentSelectionControls();});
  $('#studentsTable')?.addEventListener('click',async event=>{const graduate=event.target.closest('[data-graduate-student]');const refresh=event.target.closest('[data-refresh-student]');const edit=event.target.closest('[data-edit-student]');const remove=event.target.closest('[data-delete-student]');if(graduate){openGraduationModal([Number(graduate.dataset.graduateStudent)]);return;}if(refresh){openSeiRefreshModal({studentIds:[Number(refresh.dataset.refreshStudent)]});return;}if(edit){openStudent(state.students.items.find(row=>String(row.id)===edit.dataset.editStudent))}if(remove&&confirm('Excluir este aluno?')){try{state.selectedStudentIds.delete(Number(remove.dataset.deleteStudent));await api(`/api/dm/students/${remove.dataset.deleteStudent}`,{method:'DELETE'});await refreshAll()}catch(error){handleError(error)}}});
  $('#newDmTarget')?.addEventListener('click',()=>openTarget());
  $('#targetIndicator')?.addEventListener('change',()=>{const code=$('#targetIndicator').value;$('#targetMetric').innerHTML=targetMetricOptions(code);syncTargetDefaults(true);});
  $('#targetMetric')?.addEventListener('change',()=>syncTargetDefaults(true));
  $('#targetForm')?.addEventListener('submit',saveTarget);
  $('#dmTargetsTable')?.addEventListener('click',event=>{const edit=event.target.closest('[data-edit-target]');const remove=event.target.closest('[data-delete-target]');const create=event.target.closest('[data-create-target]');if(edit){openTarget(state.targets.find(row=>String(row.id)===edit.dataset.editTarget));return;}if(remove){deleteTarget(Number(remove.dataset.deleteTarget));return;}if(create){openTarget(null,create.dataset.createTarget,create.dataset.metric);}});
  $('#dmLogout')?.addEventListener('click',async()=>{await window.DataUnivcAuth.logout();location.assign('/')});
}

async function init() {
  setLoading(true);
  bindEvents();
  try {
    const asOf = $('#dashboardAsOf');
    if (asOf) asOf.value = new Date().toISOString().slice(0,10);
    const identityReady = await loadIdentity();
    if (!identityReady) return;
    await refreshAll();
    const search = new URLSearchParams(location.search);
    const requestedSection = search.get('view') || String(location.hash || '').replace(/^#/, '');
    if (requestedSection && document.getElementById(`section-${requestedSection}`)) {
      showSection(requestedSection);
    }
  } catch(error) { handleError(error); }
  finally { setLoading(false); }
}
document.addEventListener('DOMContentLoaded',init);
