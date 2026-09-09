const state = {
  bootstrap: null,
  dashboard: null,
  data: { nps: [], avaliacao_docente: [], resultados: [] },
  npsInstitution: [],
  npsInstitutionByCourse: [],
  npsInstitutionSearch: '',
  npsInstitutionFilters: { periodo: '', curso: '', window: '6' },
  npsCourseFilters: { periodo: '', curso: '', window: '6' },
  npsFaculty: [],
  npsFacultySearch: '',
  npsFacultyFilters: { periodo: '', window: '6' },
  activeDirectorate: null,
  directorates: [],
  actions: [],
  goals: [],
  schedules: [],
  catalogs: { cursos: [], disciplinas: [] },
  currentSection: 'dashboard',
  comparisonMetric: 'nps',
  coursePerformancePeriod: 'geral',
  searches: { nps: '', avaliacao_docente: '', resultados: '', planos: '', metas: '', disciplinas: '' },
  modalContext: null,
  user: null,
  sessionRefreshTimer: null,
  eventsBound: false,
  pagination: {},
  resultFilters: { periodo: '', curso: '', disciplina: '' },
  teacherFilters: { periodo: '', curso: '', disciplina: '', professor: '' },
  teacherOptions: { periodos: [], cursos: [], disciplinas: [], professores: [] },
  teacherAnalysis: { summary: {}, trend: [], comparison: [], comparison_dimension: 'professor' },
  teacherServer: { total: 0, page: 1, pageSize: 10, pages: 1 },
  teacherSearchTimer: null,
  resultView: 'resumo',
  resultSummary: [],
  resultTrend: [],
  resultTrendKey: '',
  resultServer: { total: 0, page: 1, pageSize: 50, pages: 1 },
  resultSearchTimer: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatNumber(value, decimals = 0) {
  if (value === null || value === undefined || value === '') return '—';
  return Number(value).toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function formatDate(value) {
  if (!value) return '—';
  const parts = String(value).slice(0, 10).split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : value;
}

function formatMonth(value, short = false) {
  const text = String(value || '').toUpperCase();
  const semester = text.match(/^(\d{4})-SEM([12])$/);
  if (semester) return short ? `${semester[1]}/S${semester[2]}` : `${semester[2]}º semestre de ${semester[1]}`;
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(text)) return text || '—';
  const [year, month] = text.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, 1));
  const label = new Intl.DateTimeFormat('pt-BR', { month: short ? 'short' : 'long', year: 'numeric', timeZone: 'UTC' }).format(date);
  return short ? label.replace('.', '') : label.charAt(0).toUpperCase() + label.slice(1);
}

function periodStartKey(value) {
  const text = String(value || '').trim().toUpperCase();
  const semester = text.match(/^(\d{4})-SEM([12])$/);
  if (semester) return Number(semester[1]) * 100 + (semester[2] === '1' ? 1 : 7);
  const month = text.match(/^(\d{4})-(0[1-9]|1[0-2])$/);
  if (month) return Number(month[1]) * 100 + Number(month[2]);
  return -1;
}

function currentPeriodKey() {
  const now = new Date();
  return now.getFullYear() * 100 + (now.getMonth() + 1);
}

function currentAcademicSemester() {
  const now = new Date();
  return `${now.getFullYear()}-SEM${now.getMonth() < 6 ? 1 : 2}`;
}

function parseAcademicSemester(value = currentAcademicSemester()) {
  const text = String(value || '').trim().toUpperCase();
  const semester = text.match(/^(\d{4})-SEM([12])$/);
  if (semester) return { year: semester[1], semester: semester[2] };
  const month = text.match(/^(\d{4})-(0[1-9]|1[0-2])$/);
  if (month) return { year: month[1], semester: Number(month[2]) <= 6 ? '1' : '2' };
  const now = parseAcademicSemester(currentAcademicSemester());
  return { year: now.year, semester: now.semester };
}

function academicSemesterFields(name, value = currentAcademicSemester(), opts = {}) {
  const parsed = parseAcademicSemester(value);
  const yearName = `${name}_year`;
  const semesterName = `${name}_semester`;
  const help = opts.help ? `<small>${escapeHtml(opts.help)}</small>` : '';
  return `
    <label class="field ${opts.yearClassName || ''}" data-field-wrapper="${escapeHtml(yearName)}">
      <span>${escapeHtml(opts.yearLabel || 'Ano')}</span>
      <input type="number" name="${escapeHtml(yearName)}" id="field-${escapeHtml(yearName)}" value="${escapeHtml(parsed.year)}" min="2000" max="2100" required>
      <div class="field-error"></div>
    </label>
    <label class="field ${opts.semesterClassName || ''}" data-field-wrapper="${escapeHtml(semesterName)}">
      <span>${escapeHtml(opts.semesterLabel || 'Semestre')}</span>
      <select name="${escapeHtml(semesterName)}" id="field-${escapeHtml(semesterName)}" required>
        ${option('1', parsed.semester === '1', '1º semestre')}
        ${option('2', parsed.semester === '2', '2º semestre')}
      </select>
      ${help}
      <div class="field-error"></div>
    </label>`;
}

function academicSemesterFromForm(form, name) {
  const year = String(new FormData(form).get(`${name}_year`) || '').trim();
  const semester = String(new FormData(form).get(`${name}_semester`) || '').trim();
  if (!/^\d{4}$/.test(year) || !['1', '2'].includes(semester)) return '';
  return `${year}-SEM${semester}`;
}

function statusClass(status) {
  const s = String(status || '').toLowerCase();
  if (s.includes('dentro') || s === 'ok' || s.includes('concluído')) return 'success';
  if (s.includes('atenção') || s.includes('andamento') || s.includes('não iniciado')) return 'warning';
  if (s.includes('fora') || s.includes('erro') || s.includes('atrasado')) return 'danger';
  if (s.includes('meta') || s.includes('dados')) return 'neutral';
  return 'info';
}

function badge(status, label = status) {
  return `<span class="badge ${statusClass(status)}">${escapeHtml(label || '—')}</span>`;
}

let readLoadingCount = 0;
let blockingLoadingCount = 0;

function setLoading(active) {
  const bar = $('#loadingBar');
  if (bar) bar.classList.toggle('hidden', !active);
}

function beginLoading({ blocking = false, title = 'Processando', message = 'Aguarde alguns instantes.' } = {}) {
  if (blocking) {
    blockingLoadingCount += 1;
    const overlay = $('#operationOverlay');
    const progress = $('#operationProgress');
    if (overlay) {
      window.DataUNIVC?.progress?.render(progress, {
        title,
        message,
        stage: 'Operação em andamento',
      });
      overlay.classList.remove('hidden');
    }
  } else {
    readLoadingCount += 1;
    setLoading(true);
  }
}

function endLoading({ blocking = false } = {}) {
  if (blocking) {
    blockingLoadingCount = Math.max(0, blockingLoadingCount - 1);
    if (!blockingLoadingCount) {
      $('#operationOverlay')?.classList.add('hidden');
      window.DataUNIVC?.progress?.hide($('#operationProgress'));
    }
  } else {
    readLoadingCount = Math.max(0, readLoadingCount - 1);
    if (!readLoadingCount) setLoading(false);
  }
}

function setSaveState(type = 'ok', text = 'Banco sincronizado') {
  const el = $('#saveState');
  if (!el) return;
  el.classList.remove('saving', 'error');
  if (type === 'saving') el.classList.add('saving');
  if (type === 'error') el.classList.add('error');
  el.innerHTML = `<span class="status-dot"></span>${escapeHtml(text)}`;
}

async function refreshAuthSession() {
  if (window.DataUnivcAuth?.refreshSession) return window.DataUnivcAuth.refreshSession();
  try {
    const response = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' });
    return response.ok;
  } catch {
    return false;
  }
}

async function api(url, options = {}, retry = true) {
  const method = String(options.method || 'GET').toUpperCase();
  const blocking = options.blocking ?? method !== 'GET';
  const loadingMessage = options.loadingMessage || (blocking ? 'Salvando alterações no banco de dados.' : 'Atualizando informações.');
  const loadingTitle = options.loadingTitle || (blocking ? 'Processando operação' : 'Carregando');
  const fetchOptions = { ...options };
  delete fetchOptions.blocking;
  delete fetchOptions.loadingMessage;
  delete fetchOptions.loadingTitle;
  const requestUrl = scopedUrl(url);

  beginLoading({ blocking, title: loadingTitle, message: loadingMessage });
  try {
    const response = window.DataUnivcAuth?.fetch
      ? await window.DataUnivcAuth.fetch(requestUrl, { credentials: 'same-origin', ...fetchOptions }, retry)
      : await fetch(requestUrl, { credentials: 'same-origin', ...fetchOptions });
    if (response.status === 401 && !requestUrl.includes('/api/auth/')) {
      showLogin('Sua sessão expirou. Entre novamente para continuar.');
    }
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof data === 'object' && data ? (data.erro || data.detail) : String(data || '');
      const error = new Error(detail || 'Não foi possível concluir a operação.');
      error.fields = (typeof data === 'object' && data?.campos) || {};
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (String(error.message).includes('Failed to fetch')) {
      error.message = 'Não foi possível acessar o servidor. Verifique sua conexão com a internet e tente novamente.';
    }
    throw error;
  } finally {
    endLoading({ blocking });
  }
}

function filenameFromDisposition(disposition, fallbackName = 'arquivo.xlsx') {
  if (!disposition) return fallbackName;
  const utf = disposition.match(/filename\*=utf-8''([^;]+)/i);
  if (utf?.[1]) {
    try { return decodeURIComponent(utf[1].replace(/["']/g, '')); } catch {}
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  return plain?.[1] || fallbackName;
}

async function downloadFile(url, fallbackName = 'arquivo.xlsx') {
  beginLoading({ blocking: true, title: 'Preparando arquivo', message: 'Gerando o arquivo solicitado para download.' });
  setSaveState('saving', 'Preparando download…');
  const requestUrl = scopedUrl(url);
  try {
    let response = await fetch(requestUrl, { method: 'GET', credentials: 'same-origin', cache: 'no-store' });
    if (response.status === 401 && !requestUrl.includes('/api/auth/')) {
      const refreshed = await refreshAuthSession();
      if (refreshed) response = await fetch(requestUrl, { method: 'GET', credentials: 'same-origin', cache: 'no-store' });
    }
    if (!response.ok) {
      const contentType = response.headers.get('content-type') || '';
      let message = `Falha ao gerar o arquivo (${response.status}).`;
      try {
        if (contentType.includes('application/json')) {
          const data = await response.json();
          message = data.erro || data.detail || message;
        } else {
          const text = await response.text();
          if (text && text.length < 500) message = text;
        }
      } catch {}
      throw new Error(message);
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error('O servidor gerou um arquivo vazio.');
    const name = filenameFromDisposition(response.headers.get('content-disposition'), fallbackName);
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = name;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
    setSaveState('ok', 'Banco sincronizado');
    toast('Download iniciado', name, 'success');
  } catch (error) {
    setSaveState('error', 'Falha no download');
    toast('Não foi possível baixar', error.message, 'error');
  } finally {
    endLoading({ blocking: true });
  }
}

function academicExcelUrl(baseUrl = '/api/excel') {
  if (!['DTNH','DCS'].includes(state.activeDirectorate)) return baseUrl;
  const params = new URLSearchParams();
  const granularity = $('#dashboardGranularity')?.value || state.dashboard?.contexto?.granularidade || 'semestral';
  const reference = $('#dashboardReference')?.value || state.dashboard?.contexto?.referencia || '';
  const comparison = $('#dashboardComparison')?.value || state.dashboard?.contexto?.comparacao || '';
  const course = $('#dashboardCourse')?.value || '(todos)';
  const discipline = $('#dashboardDiscipline')?.value || '(todas)';
  const windowValue = $('#dashboardWindow')?.value || 'all';
  params.set('granularidade', granularity);
  if (reference) params.set('referencia', reference);
  if (comparison) params.set('comparacao', comparison);
  params.set('janela', windowValue === 'all' ? 'all' : windowValue);
  if (course && course !== '(todos)') params.set('curso', course);
  if (course !== '(todos)' && discipline && discipline !== '(todas)') params.set('disciplina', discipline);
  return `${baseUrl}?${params.toString()}`;
}

function bindDownloadLinks() {
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href="/api/excel"], a[href="/api/excel-interativo"], a[href^="/api/modelos/"]');
    if (!link) return;
    event.preventDefault();
    const baseUrl = link.getAttribute('href');
    const url = ['/api/excel','/api/excel-interativo'].includes(baseUrl) ? academicExcelUrl(baseUrl) : baseUrl;
    const fallback = baseUrl === '/api/excel' ? `Relatorio_${state.activeDirectorate || 'UNIVC'}_Academico.xlsx` : baseUrl === '/api/excel-interativo' ? `Painel_${state.activeDirectorate || 'DTNH'}_Interativo_beta.xlsx` : `Modelo_${baseUrl.split('/').pop()}.xlsx`;
    downloadFile(url, fallback);
  });
}

function toast(title, message = '', type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : type === 'warning' ? 'warning' : ''}`;
  el.innerHTML = `<strong>${escapeHtml(title)}</strong>${message ? `<span>${escapeHtml(message)}</span>` : ''}`;
  $('#toastRegion').appendChild(el);
  setTimeout(() => el.remove(), 4800);
}

function navigate(section) {
  const nav = $(`.nav-item[data-section="${section}"]`);
  if (nav?.classList.contains('hidden')) section = 'dashboard';
  state.currentSection = section;
  $$('.page-section').forEach(el => el.classList.toggle('active', el.id === `section-${section}`));
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.section === section));
  const titles = {
    dashboard:'Painel executivo', 'nps-institution':'KPI · NPS da Instituição', 'nps-course':'KPI · NPS do Curso', 'nps-faculty':'KPI · NPS da Instituição · Docentes', avaliacao_docente:'KPI · Avaliação docente pelo aluno', resultados:'KPI · Aprovação, notas e reprovações',
    planos:'Planos de ação', metas:'Metas dos KPIs', cadastros:'Cursos e disciplinas', qualidade:'Governança de dados', arquivos:'Central de arquivos', configuracoes:'Configurações', ajuda:'Guia de uso'
  };
  $('#pageTitle').textContent=titles[section] || 'Data UNIVC';
  $('.sidebar').classList.remove('open');
  window.scrollTo({top:0,behavior:'smooth'});
  if (section==='nps-institution') loadInstitutionNps();
  else if (section==='nps-course') loadDataset('nps');
  else if (section==='nps-faculty') loadFacultyNps();
  else if (['avaliacao_docente','resultados'].includes(section)) loadDataset(section);
  if (section==='planos') loadActions();
  if (section==='metas') loadGoals();
  if (section==='cadastros') loadCatalogs();
  if (section==='qualidade') renderQuality();
  if (section==='configuracoes') loadSchedules();
}

function option(value, selected = false, label = value) {
  return `<option value="${escapeHtml(value)}" ${selected ? 'selected' : ''}>${escapeHtml(label)}</option>`;
}

function paginationFor(key) {
  if (!state.pagination[key]) state.pagination[key] = { page: 1, size: 10 };
  return state.pagination[key];
}

function resetPagination(key) {
  const current = paginationFor(key);
  current.page = 1;
}

function paginate(items, key) {
  const cfg = paginationFor(key);
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / cfg.size));
  cfg.page = Math.min(Math.max(1, cfg.page), pages);
  const start = (cfg.page - 1) * cfg.size;
  return { rows: items.slice(start, start + cfg.size), total, pages, start };
}

function attachPagination(target, key, total, renderFn) {
  if (!target || total <= 0) return;
  const cfg = paginationFor(key);
  const pages = Math.max(1, Math.ceil(total / cfg.size));
  const start = (cfg.page - 1) * cfg.size + 1;
  const end = Math.min(total, cfg.page * cfg.size);
  const compactPages = [];
  const from = Math.max(1, cfg.page - 2);
  const to = Math.min(pages, cfg.page + 2);
  for (let i = from; i <= to; i += 1) compactPages.push(i);
  const footer = document.createElement('div');
  footer.className = 'pagination-bar';
  footer.innerHTML = `
    <span class="pagination-range">${start}–${end} de ${total}</span>
    <div class="pagination-actions">
      <label class="page-size">Exibir <select data-page-size="${escapeHtml(key)}">${[10,25,50].map(size => option(size, size === cfg.size, size)).join('')}</select></label>
      <button class="page-button page-edge" data-page-first="${escapeHtml(key)}" ${cfg.page <= 1 ? 'disabled' : ''} aria-label="Ir para a primeira página" title="Primeira página">«</button>
      <button class="page-button" data-page-prev="${escapeHtml(key)}" ${cfg.page <= 1 ? 'disabled' : ''} aria-label="Ir para a página anterior" title="Página anterior">‹</button>
      ${compactPages.map(page => `<button class="page-button ${page === cfg.page ? 'active' : ''}" data-page-number="${page}" data-page-key="${escapeHtml(key)}" aria-label="Ir para a página ${page}" ${page === cfg.page ? 'aria-current="page"' : ''}>${page}</button>`).join('')}
      <button class="page-button" data-page-next="${escapeHtml(key)}" ${cfg.page >= pages ? 'disabled' : ''} aria-label="Ir para a próxima página" title="Próxima página">›</button>
      <button class="page-button page-edge" data-page-last="${escapeHtml(key)}" ${cfg.page >= pages ? 'disabled' : ''} aria-label="Ir para a última página" title="Última página">»</button>
    </div>`;
  target.appendChild(footer);
  $('[data-page-size]', footer)?.addEventListener('change', event => {
    cfg.size = Number(event.target.value) || 10;
    cfg.page = 1;
    renderFn();
  });
  $('[data-page-first]', footer)?.addEventListener('click', () => { if (cfg.page > 1) { cfg.page = 1; renderFn(); } });
  $('[data-page-prev]', footer)?.addEventListener('click', () => { if (cfg.page > 1) { cfg.page -= 1; renderFn(); } });
  $('[data-page-next]', footer)?.addEventListener('click', () => { if (cfg.page < pages) { cfg.page += 1; renderFn(); } });
  $('[data-page-last]', footer)?.addEventListener('click', () => { if (cfg.page < pages) { cfg.page = pages; renderFn(); } });
  $$('[data-page-number]', footer).forEach(button => button.addEventListener('click', () => { cfg.page = Number(button.dataset.pageNumber); renderFn(); }));
}


function scopedUrl(path) {
  if (!path || !String(path).startsWith('/api/') || String(path).startsWith('/api/auth/') || !state.activeDirectorate) return path;
  const url = new URL(path, window.location.origin);
  url.searchParams.set('diretoria', state.activeDirectorate);
  return `${url.pathname}${url.search}${url.hash}`;
}

function formatCurrency(value) {
  if (value === null || value === undefined || value === '') return '—';
  return Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatGoalDisplay(info, decimals = 1) {
  if (!info || info.meta === null || info.meta === undefined) return 'Sem meta';
  const unit = String(info.unidade || '').trim();
  if (unit.startsWith('R$')) {
    const suffix = unit.includes('/') ? unit.slice(unit.indexOf('/')) : '';
    return `${formatCurrency(info.meta)}${suffix}`;
  }
  if (unit === '%') return `${formatNumber(info.meta, decimals)}%`;
  if (unit === 'pontos') return `${formatNumber(info.meta, decimals)} pts`;
  return `${formatNumber(info.meta, decimals)}${unit ? ` ${unit}` : ''}`;
}


function currentDirectorateAccess() {
  return state.directorates.find(item => item.code === state.activeDirectorate) || null;
}

function canEditCurrentDirectorate() {
  return Boolean(currentDirectorateAccess()?.canEdit);
}

function directorateStorageKey() {
  const identity = state.user?.id || state.user?.email || 'anonymous';
  return `univc.activeDirectorate.${identity}`;
}

function initializeDirectorateState() {
  state.directorates = [...(state.user?.availableDirectorates || [])];
  const requested = new URLSearchParams(window.location.search).get('diretoria')?.trim().toUpperCase() || '';
  const requestedAllowed = state.directorates.some(item => item.code === requested);
  const saved = localStorage.getItem(directorateStorageKey());
  const savedAllowed = state.directorates.some(item => item.code === saved);
  if (!state.activeDirectorate || !state.directorates.some(item => item.code === state.activeDirectorate)) {
    state.activeDirectorate = requestedAllowed
      ? requested
      : (savedAllowed ? saved : state.user?.preferredDirectorate(requested));
  }
}

function resetDirectorateCaches() {
  state.bootstrap = null;
  state.dashboard = null;
  state.data = { nps: [], avaliacao_docente: [], resultados: [] };
  state.npsInstitution = [];
  state.npsInstitutionByCourse = [];
  state.npsInstitutionSearch = '';
  state.npsInstitutionFilters = { periodo: '', curso: '', window: '6' };
  state.npsCourseFilters = { periodo: '', curso: '', window: '6' };
  state.npsFaculty = [];
  state.npsFacultySearch = '';
  state.npsFacultyFilters = { periodo: '', window: '6' };
  state.actions = [];
  state.goals = [];
  state.schedules = [];
  state.catalogs = { cursos: [], disciplinas: [] };
  state.searches = { nps: '', avaliacao_docente: '', resultados: '', planos: '', metas: '', disciplinas: '' };
  state.pagination = {};
  state.resultFilters = { periodo: '', curso: '', disciplina: '' };
  state.teacherFilters = { periodo: '', curso: '', disciplina: '', professor: '' };
  state.teacherOptions = { periodos: [], cursos: [], disciplinas: [], professores: [] };
  state.teacherAnalysis = { summary: {}, trend: [], comparison: [], comparison_dimension: 'professor' };
  state.teacherServer = { total: 0, page: 1, pageSize: 10, pages: 1 };
  clearTimeout(state.teacherSearchTimer); state.teacherSearchTimer = null;
  state.resultView = 'resumo';
  state.resultSummary = [];
  state.resultTrend = [];
  state.resultTrendKey = '';
  state.resultServer = { total: 0, page: 1, pageSize: 50, pages: 1 };
}

function renderDirectorateSelector() {
  const select = $('#directorateSelect');
  if (!select) return;
  const switcher = select.closest('.directorate-switcher');
  if (switcher) switcher.classList.toggle('hidden', !state.user?.shouldShowSwitcher());
  select.innerHTML = state.directorates.map(item => {
    const suffix = item.canEdit ? ' · Edição' : ' · Somente leitura';
    return option(item.code, item.code === state.activeDirectorate, `${item.code}${suffix}`);
  }).join('');
  select.disabled = state.directorates.length <= 1;
}

function renderKpiEssentials() {
  if (!state.bootstrap) return;
  const academicPrefix = ['DTNH','DCS'].includes(state.activeDirectorate) ? state.activeDirectorate : 'DTNH';
  const map = {
    [`${academicPrefix}-01A`]: ['#meta-nps-institution'],
    [`${academicPrefix}-01B`]: ['#meta-nps-course'],
    [`${academicPrefix}-01C`]: ['#meta-nps-faculty'],
    [`${academicPrefix}-02`]: ['#meta-dtnh-02'],
    [`${academicPrefix}-03`]: ['#meta-dtnh-03'],
  };
  const goalMap = {
    [`${academicPrefix}-01A`]: 'nps_institution',
    [`${academicPrefix}-01B`]: 'nps_course',
    [`${academicPrefix}-01C`]: 'nps_faculty',
    [`${academicPrefix}-02`]: 'avaliacao_docente',
    [`${academicPrefix}-03`]: 'aprovacao',
  };
  for (const indicator of state.bootstrap.indicators || []) {
    const targets = (map[indicator.code] || []).map(selector => $(selector)).filter(Boolean);
    if (!targets.length) continue;
    const objective = indicator.objective || indicator.help || 'Acompanhar o desempenho deste KPI.';
    const liveGoal = state.dashboard?.metas_vigentes?.[goalMap[indicator.code]];
    let targetText = indicator.target_text || liveGoal?.texto || 'Meta definida na área de Metas.';
    if (liveGoal?.meta != null) {
      const vigency = liveGoal.vigencia ? ` · desde ${formatMonth(liveGoal.vigencia,true)}` : '';
      if (indicator.direction === 'range' && liveGoal.limite_superior != null) {
        targetText = `Faixa vigente: ${formatNumber(liveGoal.meta,1)}% a ${formatNumber(liveGoal.limite_superior,1)}%${vigency}`;
      } else {
        const symbol = indicator.direction === 'lower' ? '≤ ' : '≥ ';
        targetText = `Meta vigente: ${symbol}${formatGoalDisplay(liveGoal)}${vigency}`;
      }
    }
    const essentialHtml = `
      <div class="kpi-essential-item"><span>Objetivo</span><strong>${escapeHtml(objective)}</strong></div>
      <div class="kpi-essential-item target"><span>Meta</span><strong>${escapeHtml(targetText)}</strong></div>`;
    targets.forEach(target => { target.innerHTML = essentialHtml; });
  }
}

function applyDirectorateUi() {
  const access = currentDirectorateAccess();
  const editable = canEditCurrentDirectorate();
  document.body.classList.toggle('readonly-mode', !editable);
  $('#readOnlyBanner')?.classList.toggle('hidden', editable);
  if ($('#readOnlyText') && access) {
    $('#readOnlyText').textContent = `Seu acesso a ${access.code} é somente leitura. Os dados podem ser consultados e exportados, mas operações de alteração ficam indisponíveis.`;
  }
  const badgeEl = $('#directorateAccessBadge');
  if (badgeEl) {
    badgeEl.textContent = editable ? 'Leitura e edição' : 'Somente leitura';
    badgeEl.className = `access-badge ${editable ? 'write' : 'read'}`;
  }
  $('#directorLabel').textContent = state.activeDirectorate || state.user?.homeDirectorate?.code || '';
  $$('[data-directorate-nav]').forEach(item => { const scope=item.dataset.directorateNav; const visible=scope===state.activeDirectorate || (scope==='ACADEMIC' && ['DTNH','DCS'].includes(state.activeDirectorate)); item.classList.toggle('hidden', !visible); });
  $$('[data-file-directorate]').forEach(item => { const scope=item.dataset.fileDirectorate; const visible=scope===state.activeDirectorate || (scope==='ACADEMIC' && ['DTNH','DCS'].includes(state.activeDirectorate)); item.classList.toggle('hidden', !visible); });
  $$('[data-academic-interactive-excel]').forEach(item => item.classList.toggle('hidden', !['DTNH','DCS'].includes(state.activeDirectorate)));
  $$('[data-academic-interactive-label]').forEach(item => { if (['DTNH','DCS'].includes(state.activeDirectorate)) item.textContent = `Beta · ${state.activeDirectorate}`; });
  renderDirectorateSelector();
  const academic = ['DTNH','DCS'].includes(state.activeDirectorate);
  $$('[data-academic-code]').forEach(el => { if (academic) el.textContent = `${state.activeDirectorate}-${el.dataset.academicCode}`; });
  $$('[data-academic-directorate]').forEach(el => { if (academic) el.textContent = `${state.activeDirectorate} · visão executiva`; });
  renderKpiEssentials();
  const activeNav = $(`.nav-item[data-section="${state.currentSection}"]`);
  if (activeNav?.classList.contains('hidden')) navigate('dashboard');
}

async function switchDirectorate(code) {
  const target = state.directorates.find(item => item.code === code);
  if (!target || code === state.activeDirectorate) return;
  beginLoading({ blocking: true, title: `Abrindo ${code}`, message: 'Carregando o painel e as permissões da diretoria selecionada.' });
  try {
    state.activeDirectorate = code;
    localStorage.setItem(directorateStorageKey(), code);
    resetDirectorateCaches();
    state.activeDirectorate = code;
    state.currentSection = 'dashboard';
    await bootstrapApp();
    navigate('dashboard');
    toast(target.canEdit ? `Diretoria ${code}` : `${code} · somente leitura`, target.canEdit ? 'Você pode consultar e alterar os dados desta diretoria.' : 'Seu grant para esta diretoria permite apenas consulta.');
  } finally {
    endLoading({ blocking: true });
  }
}

function indicatorByCode(code) {
  return (state.bootstrap?.indicators || []).find(item => item.code === code) || null;
}

function renderDashboard() {
  renderKpiEssentials();
  renderDtnhDashboard();
}

function showLogin(message = '') {
  state.user = null;
  $('#app').classList.add('hidden');
  $('#loginScreen').classList.remove('hidden');
  $('#loginError').textContent = message;
  $('#loginError').classList.toggle('hidden', !message);
  if (state.sessionRefreshTimer) clearInterval(state.sessionRefreshTimer);
}

function showApp() {
  $('#loginScreen').classList.add('hidden');
  $('#app').classList.remove('hidden');
}

function renderUserMini() {
  const user = state.user;
  if (!user) return;
  const name = user.name || user.email || 'Usuário';
  window.DataUnivcIdentity.applyAvatar($('#userAvatar'), user);
  $('#userMiniName').textContent = name;
  const active = currentDirectorateAccess();
  $('#userMiniMeta').textContent = `${user.roleLabel}${active ? ` · ${active.access === 'EDIT' ? 'Edição' : 'Leitura'}` : ''}`;
  const directorateName = active?.name || (user.globalAccess ? 'Acesso institucional' : user.homeDirectorate?.name) || 'Data UNIVC';
  $('#userMiniDirectorate').textContent = directorateName;
  $('#userMini')?.setAttribute('title', [user.email, directorateName].filter(Boolean).join(' · '));
  $('#adminUsersLink')?.classList.toggle('hidden', !user.globalAccess);
  if ($('#adminUsersLink')) $('#adminUsersLink').href = '/reitoria#usuarios';
}

async function getCurrentUserWithRefresh() {
  return await window.DataUnivcIdentity.load();
}

function startSessionKeepAlive() {
  if (state.sessionRefreshTimer) clearInterval(state.sessionRefreshTimer);
  state.sessionRefreshTimer = setInterval(async () => {
    const ok = await refreshAuthSession();
    if (!ok) showLogin('Sua sessão expirou. Entre novamente para continuar.');
  }, 45 * 60 * 1000);
}

async function login(event) {
  event.preventDefault();
  beginLoading({ blocking:true, title:'Autenticando', message:'Validando seu acesso institucional.' });
  try {
    const response=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('#loginEmail').value,password:$('#loginPassword').value})});
    const contentType=response.headers.get('content-type')||'';
    const data=contentType.includes('application/json')?await response.json():{detail:(await response.text())||`Erro HTTP ${response.status}`};
    if(!response.ok) throw new Error(data.detail||data.erro||'Não foi possível entrar.');
    localStorage.setItem('univc.lastEmail',$('#loginEmail').value);
    state.user=await getCurrentUserWithRefresh();
    if(!state.user) throw new Error('A autenticação foi concluída, mas o perfil do Data UNIVC não pôde ser carregado.');
    if(state.user.globalAccess && !new URLSearchParams(location.search).get('diretoria')) { location.assign('/reitoria'); return; }
    initializeDirectorateState();
    $('#loginPassword').value=''; showApp(); renderUserMini(); startSessionKeepAlive(); await bootstrapApp();
  } catch(error){showLogin(error.message);} finally {endLoading({blocking:true});}
}

async function logout() {
  beginLoading({ blocking: true, title: 'Encerrando sessão', message: 'Finalizando seu acesso com segurança.' });
  try {
    await (window.DataUnivcAuth?.logout?.() || fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'}));
    state.user = null;
    location.reload();
  } finally {
    endLoading({ blocking: true });
  }
}

bindDownloadLinks();

async function startAuthenticatedApp() {
  $('#loginForm')?.addEventListener('submit', login);
  const lastEmail=localStorage.getItem('univc.lastEmail');
  if(lastEmail&&$('#loginEmail')) $('#loginEmail').value=lastEmail;
  beginLoading({blocking:true,title:'Iniciando Data UNIVC',message:'Restaurando sua sessão e carregando os KPIs.'});
  try {
    state.user=await getCurrentUserWithRefresh();
    if(!state.user){showLogin();return;}
    if(state.user.globalAccess && !new URLSearchParams(location.search).get('diretoria')) { location.assign('/reitoria'); return; }
    initializeDirectorateState(); showApp(); renderUserMini(); startSessionKeepAlive(); await bootstrapApp();
  } catch {showLogin('Servidor indisponível.');} finally {endLoading({blocking:true});}
}

async function bootstrapApp() {
  try {
    if (!state.directorates.length) initializeDirectorateState();
    if (state.activeDirectorate === 'DPE') {
      window.location.assign('/dpe?diretoria=DPE');
      return;
    }
    if (state.activeDirectorate === 'DM') {
      window.location.assign('/dm?diretoria=DM');
      return;
    }
    if (state.activeDirectorate === 'DADM') {
      window.location.assign('/dadm?diretoria=DADM');
      return;
    }
    state.bootstrap=await api('/api/bootstrap');
    $('#directorLabel').textContent=state.activeDirectorate || state.bootstrap.config.diretoria_exibicao;
    fillCourseSelectors(); fillResultFilters(); fillConfig(); renderDirectorateSelector(); applyDirectorateUi();
    if(!state.eventsBound){bindEvents();state.eventsBound=true;}
    await loadDashboard();
  } catch(error){toast('Não foi possível iniciar',error.message,'error');}
}

function academicDisciplinesForCourse(course) {
  if (!course || course === '(todos)') return [];
  return state.bootstrap?.disciplines?.[course] || [];
}

function fillCourseSelectors() {
  const select=$('#dashboardCourse');
  if(!select) return;
  const courses=state.bootstrap?.courses || [];
  select.innerHTML=option('(todos)',true,'Todos os cursos')+courses.map(c=>option(c)).join('');
  updateDashboardDisciplineOptions();
}

function updateDashboardDisciplineOptions(preserve = false) {
  const course=$('#dashboardCourse')?.value || '(todos)';
  const select=$('#dashboardDiscipline');
  if(!select) return;
  const current=preserve ? (state.dashboard?.contexto?.disciplina || select.value || '(todas)') : '(todas)';
  const disciplines=academicDisciplinesForCourse(course);
  select.disabled=course==='(todos)';
  select.innerHTML=option('(todas)',current==='(todas)',course==='(todos)'?'Selecione um curso':'Todas as disciplinas')+disciplines.map(d=>option(d,d===current)).join('');
  if (![...select.options].some(opt=>opt.value===current)) select.value='(todas)';
}

function fillResultFilters() {
  $$('#resultsViewTabs [data-results-view]').forEach(button=>button.classList.toggle('active',button.dataset.resultsView===state.resultView));
  const periodSelect=$('#resultsPeriodFilter');
  if(periodSelect){
    const periods=state.dashboard?.periodos?.semestrais || [];
    const currentPeriod=state.resultFilters.periodo || '';
    periodSelect.innerHTML=option('',!currentPeriod,'Todos os semestres')+periods.map(period=>option(period,period===currentPeriod,formatMonth(period,true))).join('');
    if(currentPeriod && !periods.includes(currentPeriod)){ state.resultFilters.periodo=''; periodSelect.value=''; }
  }
  const courseSelect=$('#resultsCourseFilter');
  if(!courseSelect) return;
  const courses=state.bootstrap?.courses || [];
  const current=state.resultFilters.curso || '';
  courseSelect.innerHTML=option('',!current,'Todos os cursos')+courses.map(c=>option(c,c===current)).join('');
  updateResultDisciplineOptions();
}

function updateResultDisciplineOptions() {
  const course=state.resultFilters.curso || '';
  const select=$('#resultsDisciplineFilter');
  if(!select) return;
  const disciplines=course ? academicDisciplinesForCourse(course) : [];
  const current=state.resultFilters.disciplina || '';
  select.disabled=!course;
  select.innerHTML=option('',!current,course?'Todas as disciplinas':'Selecione um curso')+disciplines.map(d=>option(d,d===current)).join('');
  if (![...select.options].some(opt=>opt.value===current)) { state.resultFilters.disciplina=''; select.value=''; }
}

function sortedUnique(values) {
  return [...new Set((values || []).filter(value => value !== null && value !== undefined && String(value).trim() !== '').map(value => String(value).trim()))]
    .sort((a,b) => a.localeCompare(b,'pt-BR',{numeric:true,sensitivity:'base'}));
}

function teacherFilterQuery({ includePeriod = true, includeSearch = false, includePage = false } = {}) {
  const params = new URLSearchParams();
  const f = state.teacherFilters || {};
  if (includePeriod && f.periodo) params.set('periodo', f.periodo);
  if (f.curso) params.set('curso', f.curso);
  if (f.disciplina) params.set('disciplina', f.disciplina);
  if (f.professor) params.set('professor', f.professor);
  if (includeSearch && (state.searches.avaliacao_docente || '').trim()) params.set('busca', state.searches.avaliacao_docente.trim());
  if (includePage) {
    const cfg = paginationFor('data-avaliacao_docente');
    params.set('page', String(cfg.page));
    params.set('page_size', String(cfg.size));
  }
  return params;
}

async function loadTeacherOptions() {
  const params = new URLSearchParams();
  if (state.teacherFilters.curso) params.set('curso', state.teacherFilters.curso);
  if (state.teacherFilters.disciplina) params.set('disciplina', state.teacherFilters.disciplina);
  const response = await api(`/api/avaliacao-docente/opcoes${params.toString() ? `?${params}` : ''}`);
  state.teacherOptions = {
    periodos: response.periodos || [], cursos: response.cursos || [],
    disciplinas: response.disciplinas || [], professores: response.professores || [],
  };
  fillTeacherFilters();
}

function fillTeacherFilters() {
  const options = state.teacherOptions || { periodos: [], cursos: [], disciplinas: [], professores: [] };
  const f = state.teacherFilters || (state.teacherFilters = { periodo:'', curso:'', disciplina:'', professor:'' });
  const period = $('#teacherPeriodFilter');
  const course = $('#teacherCourseFilter');
  const discipline = $('#teacherDisciplineFilter');
  const professor = $('#teacherProfessorFilter');
  if (!period || !course || !discipline || !professor) return;

  if (f.periodo && !options.periodos.includes(f.periodo)) f.periodo = '';
  if (f.curso && !options.cursos.includes(f.curso)) f.curso = '';
  if (f.disciplina && !options.disciplinas.includes(f.disciplina)) f.disciplina = '';
  if (f.professor && !options.professores.includes(f.professor)) f.professor = '';
  period.innerHTML = option('', !f.periodo, 'Todos os semestres') + options.periodos.map(value => option(value, value===f.periodo, formatMonth(value,true))).join('');
  course.innerHTML = option('', !f.curso, 'Todos os cursos') + options.cursos.map(value => option(value, value===f.curso)).join('');
  discipline.innerHTML = option('', !f.disciplina, 'Todas as disciplinas') + options.disciplinas.map(value => option(value, value===f.disciplina)).join('');
  professor.innerHTML = option('', !f.professor, 'Todos os professores') + options.professores.map(value => option(value, value===f.professor)).join('');
}

async function loadTeacherAnalysis() {
  const params = teacherFilterQuery();
  state.teacherAnalysis = await api(`/api/avaliacao-docente/analise${params.toString() ? `?${params}` : ''}`);
  renderTeacherAnalysis();
}

async function loadTeacherPage() {
  const params = teacherFilterQuery({ includeSearch: true, includePage: true });
  const response = await api(`/api/dados/avaliacao_docente?${params}`);
  state.data.avaliacao_docente = response.items || [];
  state.teacherServer = {
    total: Number(response.total || 0), page: Number(response.page || 1),
    pageSize: Number(response.page_size || paginationFor('data-avaliacao_docente').size),
    pages: Number(response.pages || 1),
  };
  const cfg = paginationFor('data-avaliacao_docente');
  cfg.page = state.teacherServer.page;
  cfg.size = state.teacherServer.pageSize;
  renderTeacherTableServer();
}

async function loadTeacherWorkspace() {
  await loadTeacherOptions();
  // Options may invalidate a selection after an edit/delete. Fetch analytics and
  // the table only after the canonical filter state has been reconciled.
  await Promise.all([loadTeacherAnalysis(), loadTeacherPage()]);
}

function renderTeacherAnalysis() {
  const targetCards = $('#teacherAnalysisCards');
  if (!targetCards) return;
  const summary = state.teacherAnalysis?.summary || {};
  targetCards.innerHTML = [
    ['Média ponderada', summary.valor==null?'—':formatNumber(summary.valor,2), `${formatNumber(summary.respondentes||0,0)} resposta(s)`, 'info'],
    ['Respondentes', formatNumber(summary.respondentes||0,0), 'volume do recorte', 'neutral'],
    ['Professores', formatNumber(summary.professores||0,0), 'docente(s) no recorte', 'neutral'],
    ['Disciplinas', formatNumber(summary.disciplinas||0,0), 'disciplina(s) no recorte', 'neutral'],
  ].map(([label,value,sub,tone])=>`<article class="result-summary-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></article>`).join('');

  const f = state.teacherFilters || {};
  const context = [];
  if (f.professor) context.push(`Professor: ${f.professor}`);
  if (f.disciplina) context.push(`Disciplina: ${f.disciplina}`);
  if (f.curso) context.push(`Curso: ${f.curso}`);
  if (f.periodo) context.push(`Semestre: ${formatMonth(f.periodo,true)}`);
  const ctx = $('#teacherKpiContext');
  if (ctx) ctx.textContent = context.length ? context.join(' · ') : 'Todo o histórico de avaliação docente da diretoria';

  renderLineChart($('#chartTeacherKpiEvolution'), state.teacherAnalysis?.trend || [], {decimals:2, metric:'avaliacao_docente', unit:'nota 0–10'});
  const title = $('#teacherComparisonTitle');
  if (title) title.textContent = state.teacherAnalysis?.comparison_dimension === 'disciplina' ? 'Disciplinas do professor' : 'Professores no recorte';
  renderBarChart($('#chartTeacherKpiComparison'), state.teacherAnalysis?.comparison || [], {decimals:2, metric:'avaliacao_docente', unit:'nota 0–10', clickFilter:false});
}

function renderTeacherTableServer() {
  const dataset = 'avaliacao_docente';
  const items = state.data.avaliacao_docente || [];
  const server = state.teacherServer || { total:0, page:1, pageSize:10, pages:1 };
  const target = $('#table-avaliacao_docente');
  const count = $('#count-avaliacao_docente');
  if (!target || !count) return;
  const start = server.total ? (server.page - 1) * server.pageSize + 1 : 0;
  const end = server.total ? Math.min(server.total, start + items.length - 1) : 0;
  count.textContent = server.total ? `${start}–${end} de ${server.total}` : '0 registros';
  if (!items.length) {
    target.innerHTML = '<div class="empty-table"><strong>Nenhum registro encontrado</strong>Altere os filtros ou a busca.</div>';
    return;
  }
  const defs = columns.avaliacao_docente;
  const editable = canEditCurrentDirectorate();
  target.innerHTML = `<table><thead><tr>${defs.map(c=>`<th class="${c[2]||''}">${escapeHtml(c[1])}</th>`).join('')}${editable?'<th class="actions">Ações</th>':''}</tr></thead><tbody>${items.map(item=>`<tr>${defs.map(c=>{const raw=item[c[0]];const value=c[3]?c[3](raw):escapeHtml(raw||raw===0?raw:'—');return `<td class="${c[2]||''}">${value}</td>`;}).join('')}${editable?`<td class="actions"><button class="row-action" title="Editar" data-edit="${dataset}" data-id="${item.id}">✎</button><button class="row-action delete" title="Excluir" data-delete="${dataset}" data-id="${item.id}">×</button></td>`:''}</tr>`).join('')}</tbody></table>`;
  attachPagination(target, 'data-avaliacao_docente', server.total, () => loadTeacherPage());
  $$(`[data-edit="${dataset}"]`,target).forEach(btn=>btn.addEventListener('click',()=>openDataForm(dataset,Number(btn.dataset.id))));
  $$(`[data-delete="${dataset}"]`,target).forEach(btn=>btn.addEventListener('click',()=>deleteData(dataset,Number(btn.dataset.id))));
}

function fillConfig() {
  const config=state.bootstrap?.config || {};
  $('#configResponsavel').value=config.responsavel || state.user?.name || '';
  $('#configDiretoria').value=state.activeDirectorate || config.diretoria_exibicao || '';
}

function bindEvents() {
  $$('.nav-item[data-section]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.section)));
  $$('[data-section-target]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.sectionTarget)));
  $('#directorateSelect')?.addEventListener('change',event=>switchDirectorate(event.target.value));
  $('#menuToggle')?.addEventListener('click',()=>$('.sidebar').classList.toggle('open'));
  $('#applyFilters')?.addEventListener('click',loadDashboard);
  $('#dashboardCourse')?.addEventListener('change',()=>updateDashboardDisciplineOptions(false));
  const academicReference=$('#dashboardReference');
  academicReference?.addEventListener('focus',event=>{ event.currentTarget.dataset.previousValue=event.currentTarget.value || ''; });
  academicReference?.addEventListener('change',event=>{
    const previous=event.currentTarget.dataset.previousValue || state.dashboard?.contexto?.referencia || '';
    const current=event.currentTarget.value || '';
    const comparison=$('#dashboardComparison');
    // Ao trocar a referência, o período que estava sendo analisado não deve
    // desaparecer: ele vira automaticamente a comparação quando for válido.
    if(comparison && previous && previous!==current){
      if(![...comparison.options].some(opt=>opt.value===previous)){
        comparison.add(new Option(formatMonth(previous,true),previous));
      }
      comparison.value=previous;
    }
    event.currentTarget.dataset.previousValue=current;
  });
  $('#dashboardGranularity')?.addEventListener('change',()=>{ updateAcademicWindowOptions($('#dashboardGranularity').value); loadDashboard(); });
  $('#resetFilters')?.addEventListener('click',()=>{ $('#dashboardCourse').value='(todos)'; updateDashboardDisciplineOptions(false); if($('#dashboardGranularity'))$('#dashboardGranularity').value='semestral'; updateAcademicWindowOptions('semestral','4'); const periods=state.dashboard?.periodos?.semestrais||[]; $('#dashboardReference').value=periods.at(-1)||''; $('#dashboardComparison').value=periods.at(-2)||''; loadDashboard(); });
  $$('#comparisonMetric button').forEach(button=>button.addEventListener('click',()=>{state.comparisonMetric=button.dataset.metric;$$('#comparisonMetric button').forEach(b=>b.classList.toggle('active',b===button));renderCourseComparison();}));
  $('#coursePerformancePeriod')?.addEventListener('change',event=>{state.coursePerformancePeriod=event.target.value || 'geral';resetPagination(`course-comparison-${state.comparisonMetric}`);renderCourseComparison();});
  $$('.add-button').forEach(button=>button.addEventListener('click',()=>openDataForm(button.dataset.dataset)));
  $$('.import-button').forEach(button=>button.addEventListener('click',()=>openImportForm(button.dataset.dataset)));
  $('#seiImportButton')?.addEventListener('click', openSeiImportForm);
  $('#npsInstitutionSeiImportButton')?.addEventListener('click', ()=>openNpsSeiImportForm('institution'));
  $('#npsCourseSeiImportButton')?.addEventListener('click', ()=>openNpsSeiImportForm('course'));
  $('#npsFacultySeiImportButton')?.addEventListener('click', ()=>openNpsSeiImportForm('faculty'));
  $('#npsInstitutionSearch')?.addEventListener('input',event=>{state.npsInstitutionSearch=event.target.value||'';resetPagination('nps-institution');renderInstitutionNps();});
  ['npsCoursePeriodFilter','npsCourseFilter','npsCourseWindow'].forEach(id=>{
    $(`#${id}`)?.addEventListener('change',event=>{
      const key={npsCoursePeriodFilter:'periodo',npsCourseFilter:'curso',npsCourseWindow:'window'}[id];
      state.npsCourseFilters[key]=event.target.value||'';
      resetPagination('data-nps');
      renderDatasetTable('nps');
    });
  });
  $('#resetNpsCourseFilters')?.addEventListener('click',()=>{
    state.npsCourseFilters={periodo:'',curso:'',window:'6'};
    fillNpsCourseFilters(); resetPagination('data-nps'); renderDatasetTable('nps');
  });
  ['npsInstitutionPeriodFilter','npsInstitutionCourseFilter','npsInstitutionWindow'].forEach(id=>{
    $(`#${id}`)?.addEventListener('change',event=>{
      const key={npsInstitutionPeriodFilter:'periodo',npsInstitutionCourseFilter:'curso',npsInstitutionWindow:'window'}[id];
      state.npsInstitutionFilters[key]=event.target.value||'';
      resetPagination('nps-institution');
      renderInstitutionNps();
    });
  });
  $('#resetNpsInstitutionFilters')?.addEventListener('click',()=>{
    state.npsInstitutionFilters={periodo:'',curso:'',window:'6'};
    fillNpsInstitutionFilters(); resetPagination('nps-institution'); renderInstitutionNps();
  });
  $('#npsFacultySearch')?.addEventListener('input',event=>{state.npsFacultySearch=event.target.value||'';resetPagination('nps-faculty');renderFacultyNps();});
  ['npsFacultyPeriodFilter','npsFacultyWindow'].forEach(id=>{
    $(`#${id}`)?.addEventListener('change',event=>{
      const key={npsFacultyPeriodFilter:'periodo',npsFacultyWindow:'window'}[id];
      state.npsFacultyFilters[key]=event.target.value||'';
      resetPagination('nps-faculty'); renderFacultyNps();
    });
  });
  $('#resetNpsFacultyFilters')?.addEventListener('click',()=>{
    state.npsFacultyFilters={periodo:'',window:'6'}; fillNpsFacultyFilters(); resetPagination('nps-faculty'); renderFacultyNps();
  });
  $('#teacherSeiReadinessButton')?.addEventListener('click', openTeacherSeiReadiness);
  $$('.table-search').forEach(input=>input.addEventListener('input',()=>{
    const dataset=input.dataset.dataset;
    state.searches[dataset]=input.value;
    resetPagination(`data-${dataset}`);
    if(dataset==='avaliacao_docente'){
      clearTimeout(state.teacherSearchTimer);
      state.teacherSearchTimer=setTimeout(()=>loadTeacherPage(),260);
      return;
    }
    if(dataset==='resultados'){
      if(state.resultView==='resumo'){renderResultSummaryTable();return;}
      clearTimeout(state.resultSearchTimer);
      state.resultSearchTimer=setTimeout(()=>loadDataset('resultados',true),260);
      return;
    }
    renderDatasetTable(dataset);
  }));
  ['teacherPeriodFilter','teacherCourseFilter','teacherDisciplineFilter','teacherProfessorFilter'].forEach(id=>{
    $(`#${id}`)?.addEventListener('change',event=>{
      const map={teacherPeriodFilter:'periodo',teacherCourseFilter:'curso',teacherDisciplineFilter:'disciplina',teacherProfessorFilter:'professor'};
      const key=map[id];
      state.teacherFilters[key]=event.target.value;
      if(key==='curso'){ state.teacherFilters.disciplina=''; state.teacherFilters.professor=''; }
      if(key==='disciplina'){ state.teacherFilters.professor=''; }
      resetPagination('data-avaliacao_docente');
      loadTeacherWorkspace().catch(error=>toast('Erro ao filtrar avaliação docente',error.message,'error'));
    });
  });
  $('#resetTeacherFilters')?.addEventListener('click',()=>{
    state.teacherFilters={periodo:'',curso:'',disciplina:'',professor:''};
    resetPagination('data-avaliacao_docente');
    loadTeacherWorkspace().catch(error=>toast('Erro ao limpar filtros',error.message,'error'));
  });
  $('#resultsPeriodFilter')?.addEventListener('change',event=>{
    state.resultFilters.periodo=event.target.value;state.resultSummary=[];resetPagination('data-resultados');loadDataset('resultados',true);
  });
  $('#resultsCourseFilter')?.addEventListener('change',event=>{
    state.resultFilters.curso=event.target.value;state.resultFilters.disciplina='';state.resultSummary=[];state.resultTrendKey='';updateResultDisciplineOptions();resetPagination('data-resultados');loadDataset('resultados',true);
  });
  $('#resultsDisciplineFilter')?.addEventListener('change',event=>{
    state.resultFilters.disciplina=event.target.value;state.resultSummary=[];state.resultTrendKey='';resetPagination('data-resultados');loadDataset('resultados',true);
  });
  $$('#resultsViewTabs [data-results-view]').forEach(button=>button.addEventListener('click',()=>{
    state.resultView=button.dataset.resultsView;
    $$('#resultsViewTabs [data-results-view]').forEach(x=>x.classList.toggle('active',x===button));
    resetPagination('data-resultados');
    const search=$('.table-search[data-dataset="resultados"]');
    if(search)search.placeholder=state.resultView==='resumo'?'Buscar curso, disciplina ou semestre':'Buscar aluno, matrícula, curso, disciplina, turma ou situação';
    loadDataset('resultados',true);
  }));
  $('#addActionButton')?.addEventListener('click',()=>openActionForm());
  $('#addGoalButton')?.addEventListener('click',()=>openGoalForm());
  $('#importDisciplineButton')?.addEventListener('click',()=>openImportForm('disciplinas'));
  $('#addCourseButton')?.addEventListener('click',()=>openCourseForm());
  $('#addDisciplineButton')?.addEventListener('click',()=>openDisciplineForm());
  $('#disciplineSearch')?.addEventListener('input',e=>{state.searches.disciplinas=e.target.value;resetPagination('disciplines');renderCatalogs();});
  $('#goalSearch')?.addEventListener('input',e=>{state.searches.metas=e.target.value;resetPagination('goals');renderGoals();});
  $('#actionSearch')?.addEventListener('input',e=>{state.searches.planos=e.target.value;resetPagination('actions');renderActions();});
  $('#quickAddButton')?.addEventListener('click',quickAdd);
  $('#logoutButton')?.addEventListener('click',logout);
  $('#refreshQuality')?.addEventListener('click',async()=>{await loadDashboard();renderQuality();});
  $('#configForm')?.addEventListener('submit',saveConfig);
  $('#closeModal')?.addEventListener('click',closeModal);
  $('#modalBackdrop')?.addEventListener('click',e=>{if(e.target===$('#modalBackdrop')) closeModal();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape') closeModal();});
}

async function loadDashboard() {
  const params = new URLSearchParams();
  const course=$('#dashboardCourse')?.value || '(todos)';
  const discipline=$('#dashboardDiscipline')?.value || '(todas)';
  const granularity=$('#dashboardGranularity')?.value || state.dashboard?.contexto?.granularidade || 'semestral';
  const ref=$('#dashboardReference')?.value||'';
  const cmp=$('#dashboardComparison')?.value||'';
  const windowValue=$('#dashboardWindow')?.value || (granularity==='mensal'?'12':'4');
  params.set('curso',course);
  params.set('granularidade',granularity);
  if(course !== '(todos)' && discipline !== '(todas)') params.set('disciplina',discipline);
  if(ref) params.set('referencia',ref);
  if(cmp) params.set('comparacao',cmp);
  if(windowValue !== 'all') params.set('janela',windowValue);
  try {
    state.dashboard=await api(`/api/dashboard${params.toString()?`?${params}`:''}`);
    populatePeriodSelectors();
    renderDashboard();
  } catch(error){toast('Erro ao carregar o painel',error.message,'error');}
}

function updateAcademicWindowOptions(granularity, preferredValue = null) {
  const select=$('#dashboardWindow');
  if(!select)return;
  const current=preferredValue || select.value;
  const monthly=granularity==='mensal';
  const options=monthly
    ? [['6','6 meses'],['12','12 meses'],['24','24 meses'],['all','Todo histórico']]
    : [['2','2 semestres'],['4','4 semestres'],['6','6 semestres'],['all','Todo histórico']];
  const fallback=monthly?'12':'4';
  const chosen=options.some(([value])=>value===current)?current:fallback;
  select.innerHTML=options.map(([value,label])=>option(value,value===chosen,label)).join('');
}

function populatePeriodSelectors() {
  const context=state.dashboard?.contexto || {};
  const granularity=context.granularidade || 'semestral';
  if($('#dashboardGranularity'))$('#dashboardGranularity').value=granularity;
  updateAcademicWindowOptions(granularity);
  const periods=granularity==='mensal'
    ? (state.dashboard?.periodos?.mensais || [])
    : (state.dashboard?.periodos?.semestrais || []);
  const ref=$('#dashboardReference'), cmp=$('#dashboardComparison');
  if(ref) ref.innerHTML=periods.map(p=>option(p,p===context.referencia,formatMonth(p,true))).join('') || option('',true,'Sem dados');
  if(cmp) cmp.innerHTML=option('',!context.comparacao,'Sem comparação') + periods.filter(p=>p!==context.referencia).map(p=>option(p,p===context.comparacao,formatMonth(p,true))).join('');
  updateDashboardDisciplineOptions(true);
}

function metricCard(label, icon, value, sub, status, extraClass = '') {
  return `<article class="metric-card ${extraClass}">
    <div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${icon}</span></div>
    <div class="metric-value">${value}</div>
    <div class="metric-sub">${escapeHtml(sub)}</div>
    <div class="metric-status">${badge(status)}</div>
  </article>`;
}

function goalSummary(info) {
  if (!info || info.meta === null || info.meta === undefined) return 'Sem meta vigente';
  const unit = info.unidade === '%' ? '%' : info.unidade === 'nota' ? ' pontos' : ' pontos';
  return `Meta ${formatNumber(info.meta, 1)}${unit} · ${info.recorte || 'TOTAL'} · desde ${formatMonth(info.vigencia,true) || '—'}`;
}

function renderKpiContext() {
  const ctx = state.dashboard?.contexto;
  const target = $('#kpiContext');
  if (!target || !ctx?.referencia) { if (target) target.textContent = ''; return; }
  const pieces = [`Visualização ${ctx.granularidade==='mensal'?'mensal':'semestral'}`, `Referência ${formatMonth(ctx.referencia,true)}`];
  if (ctx.curso && ctx.curso !== '(todos)') pieces.push(`curso ${ctx.curso}`);
  if (ctx.disciplina && ctx.disciplina !== '(todas)') pieces.push(`disciplina ${ctx.disciplina}`);
  if (ctx.comparacao) pieces.push(`comparação ${formatMonth(ctx.comparacao,true)}`);
  if (ctx.inicio && ctx.fim) pieces.push(`janela ${formatMonth(ctx.inicio,true)} a ${formatMonth(ctx.fim,true)}`);
  if (ctx.frequencia_periodo && ctx.frequencia_periodo !== ctx.referencia) pieces.push(`frequência em ${formatMonth(ctx.frequencia_periodo,true)}`);
  const q = state.dashboard?.cards?.qualidade;
  const a = state.dashboard?.cards?.planos;
  if (q) pieces.push(q.total ? `${q.total} pendência(s) de dados` : 'dados validados');
  if (a) pieces.push(`${a.abertos || 0} plano(s) aberto(s)`);
  target.textContent = pieces.join(' · ');
}

function renderActiveGoals() {
  const target = $('#activeGoals');
  if (!target) return;
  const goals = state.dashboard?.metas_vigentes || {};
  const items = [
    [`${state.activeDirectorate}-01A`, 'NPS da Instituição · Alunos', goals.nps_institution],
    [`${state.activeDirectorate}-01B`, 'NPS do Curso', goals.nps_course || goals.nps],
    [`${state.activeDirectorate}-01C`, 'NPS da Instituição · Docentes', goals.nps_faculty],
    [`${state.activeDirectorate}-02`, 'Avaliação docente pelo aluno', goals.avaliacao_docente],
    [`${state.activeDirectorate}-03`, 'Taxa de aprovação', goals.aprovacao],
  ];
  target.innerHTML = items.map(([code, label, info]) => {
    if (!info) return `<article class="active-goal-card empty"><span class="eyebrow">${code}</span><strong>${label}</strong><p>Sem meta aplicável ao contexto selecionado.</p></article>`;
    const value = formatGoalDisplay(info);
    const specific = info.recorte !== 'TOTAL';
    return `<article class="active-goal-card ${specific ? 'specific' : ''}">
      <div><span class="eyebrow">${code} · meta do período</span><strong>${escapeHtml(label)}</strong></div>
      <div class="active-goal-value">${value}</div>
      <p>${escapeHtml(info.origem)} · recorte <b>${escapeHtml(info.recorte)}</b> · vigente desde ${escapeHtml(info.vigencia)}</p>
    </article>`;
  }).join('');
}

function renderDtnhDashboard() {
  const d = state.dashboard;
  if (!d || !d.cards) return;
  const c = d.cards;
  const institution = c.nps_institution || {};
  const courseNps = c.nps_course || c.nps || {};
  const facultyNps = c.nps_faculty || {};
  const compareLabel = d.contexto.comparacao ? formatMonth(d.contexto.comparacao,true) : (d.contexto.granularidade==='mensal'?'mês anterior':'semestre anterior');
  const npsCompareLabel = d.contexto.nps_comparacao ? formatMonth(d.contexto.nps_comparacao,true) : 'semestre anterior';

  const institutionCoverage = institution.coverage_total
    ? (institution.complete ? 'cobertura institucional completa' : `cobertura ${institution.coverage || 0}/${institution.coverage_total}`)
    : `${formatNumber(institution.respondentes || 0,0)} respondente(s)`;
  const institutionSource = institution.fonte ? ` · ${institution.fonte}` : '';
  const institutionVariation = institution.comparacao == null
    ? goalSummary(institution.meta_info)
    : `${institution.variacao >= 0 ? '+' : ''}${formatNumber(institution.variacao,1)} p.p. vs. ${npsCompareLabel}`;
  const institutionSub = `${institutionVariation} · ${institutionCoverage}${institutionSource}`;

  const npsVolume = `${formatNumber(courseNps.respondentes || 0,0)} respondente(s)`;
  const npsSource = courseNps.fonte ? ` · ${courseNps.fonte}` : '';
  const npsVariation = courseNps.comparacao == null ? goalSummary(courseNps.meta_info) : `${courseNps.variacao >= 0 ? '+' : ''}${formatNumber(courseNps.variacao,1)} p.p. vs. ${npsCompareLabel}`;
  const npsSub = `${npsVariation} · ${npsVolume}${npsSource}`;
  const facultyVolume = `${formatNumber(facultyNps.respondentes || 0,0)} respondente(s)`;
  const facultySource = facultyNps.fonte ? ` · ${facultyNps.fonte}` : '';
  const facultyVariation = facultyNps.comparacao == null ? goalSummary(facultyNps.meta_info) : `${facultyNps.variacao >= 0 ? '+' : ''}${formatNumber(facultyNps.variacao,1)} p.p. vs. ${npsCompareLabel}`;
  const facultySub = `${facultyVariation} · ${facultyVolume} · institucional/anônimo${facultySource}`;
  const teacherSub = c.avaliacao_docente.comparacao == null ? goalSummary(c.avaliacao_docente.meta_info) : `${c.avaliacao_docente.variacao >= 0 ? '+' : ''}${formatNumber(c.avaliacao_docente.variacao,2)} ponto(s) vs. ${compareLabel}`;
  const apprSub = c.aprovacao.comparacao == null ? goalSummary(c.aprovacao.meta_info) : `${c.aprovacao.variacao >= 0 ? '+' : ''}${formatNumber(c.aprovacao.variacao,1)} p.p. vs. ${compareLabel}`;
  const details = c.aprovacao.finalizados ? ` · ${formatNumber(c.aprovacao.finalizados,0)} resultado(s) finalizado(s)` : '';
  const grid = $('#metricGrid');
  if (grid) grid.innerHTML = [
    metricCard('NPS da Instituição · Alunos','01A',institution.valor==null?'—':formatNumber(institution.valor,1),institutionSub,institution.status),
    metricCard('NPS do Curso','01B',courseNps.valor==null?'—':formatNumber(courseNps.valor,1),npsSub,courseNps.status),
    metricCard('NPS da Instituição · Docentes','01C',facultyNps.valor==null?'—':formatNumber(facultyNps.valor,1),facultySub,facultyNps.status),
    metricCard('Avaliação docente','02',c.avaliacao_docente.valor==null?'—':formatNumber(c.avaliacao_docente.valor,2),teacherSub,c.avaliacao_docente.status),
    metricCard('Taxa de aprovação','03',c.aprovacao.valor==null?'—':`${formatNumber(c.aprovacao.valor,1)}%`,`${apprSub}${details}`,c.aprovacao.status),
  ].join('');
  const outcomeGrid=$('#academicOutcomeGrid');
  if(outcomeGrid){
    const gradeLabel=d.contexto?.disciplina && d.contexto.disciplina!=='(todas)'?'Média da disciplina':'Média das notas';
    outcomeGrid.innerHTML=[
      ['Aprovações',formatNumber(c.aprovacao.aprovados||0,0),'resultados oficiais aprovados','approved'],
      ['Reprovação por nota',formatNumber(c.aprovacao.reprovacoes?.nota||0,0),'reprovações sem indicação de falta','grade'],
      ['Reprovação por falta',formatNumber(c.aprovacao.reprovacoes?.falta||0,0),'reprovações por falta/frequência','absence'],
      [gradeLabel,c.aprovacao.media_notas==null?'—':formatNumber(c.aprovacao.media_notas,2),'média das notas finais disponíveis','average'],
    ].map(([label,value,sub,tone])=>`<article class="academic-outcome-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></article>`).join('');
  }
  renderKpiContext();
  renderActiveGoals();
  fillResultFilters();
  renderLineChart($('#chartNpsInstitutionExecutive'), d.series?.nps_institution_semestral || [], { suffix:'', decimals:1, metric:'nps', unit:'pontos' });
  renderLineChart($('#chartNps'), d.series?.nps_course_semestral || d.series?.nps_semestral || d.series?.nps || [], { suffix:'', decimals:1, metric:'nps', unit:'pontos' });
  renderLineChart($('#chartNpsFacultyExecutive'), d.series?.nps_faculty_semestral || [], { suffix:'', decimals:1, metric:'nps', unit:'pontos' });
  renderLineChart($('#chartAvaliacaoDocente'), d.series?.avaliacao_docente || [], { suffix:'', decimals:2, metric:'avaliacao_docente', unit:'nota 0–10' });
  renderLineChart($('#chartAprovacao'), d.series?.aprovacao || [], { suffix:'%', decimals:1, metric:'aprovacao', unit:'%' });
  const insights=$('#insightsList');
  if (insights) insights.innerHTML = (d.insights || []).length ? d.insights.slice(0,5).map(item=>`<div class="insight-item ${escapeHtml(item.nivel)}"><span class="insight-dot">•</span><div><strong>${escapeHtml(item.titulo)}</strong><p>${escapeHtml(item.texto)}</p></div></div>`).join('') : '<div class="chart-empty">Sem alertas para o contexto atual.</div>';
  renderAcademicDisciplineSummary();
  renderCourseComparison();
}

function renderAcademicDisciplineSummary(){
  const target=$('#academicDisciplineSummaryTable');
  if(!target||!state.dashboard)return;
  const rows=state.dashboard.resumo_disciplinas||[];
  const key='academic-discipline-summary';
  const page=paginate(rows,key);
  if(!rows.length){target.innerHTML='<div class="empty-table">Sem resultados por disciplina para o recorte selecionado.</div>';return;}
  target.innerHTML=`<table class="academic-summary-table"><thead><tr><th>Curso</th><th>Disciplina</th><th class="numeric">Aprovados</th><th class="numeric">Rep. nota</th><th class="numeric">Rep. falta</th><th class="numeric">Taxa</th><th class="numeric">Média</th></tr></thead><tbody>${page.rows.map(item=>`<tr><td>${escapeHtml(item.curso)}</td><td><strong>${escapeHtml(item.disciplina)}</strong></td><td class="numeric outcome-approved">${formatNumber(item.aprovados,0)}</td><td class="numeric outcome-grade">${formatNumber(item.reprovados_nota,0)}</td><td class="numeric outcome-absence">${formatNumber(item.reprovados_falta,0)}</td><td class="numeric"><strong>${item.taxa_aprovacao==null?'—':`${formatNumber(item.taxa_aprovacao,1)}%`}</strong></td><td class="numeric"><strong>${item.media_notas==null?'—':formatNumber(item.media_notas,2)}</strong></td></tr>`).join('')}</tbody></table>`;
  attachPagination(target,key,rows.length,renderAcademicDisciplineSummary);
}

function chartTooltipContent(point, opts = {}) {
  const lines=[`<div class="chart-tip-title">${escapeHtml(point.periodo ? formatMonth(point.periodo,true) : (point.curso || ''))}</div>`];
  const hasValue=point.valor!==null&&point.valor!==undefined;
  lines.push(`<div class="chart-tip-main"><strong>${hasValue?`${escapeHtml(opts.prefix || '')}${formatNumber(point.valor,opts.decimals??1)}${opts.suffix||''}`:'—'}</strong><span>${escapeHtml(hasValue?(opts.unit||''):'sem resultado no período')}</span></div>`);
  if(point.meta!==null&&point.meta!==undefined){
    let metaText;
    if (opts.metaUnit?.startsWith('R$')) {
      const suffix = opts.metaUnit.includes('/') ? opts.metaUnit.slice(opts.metaUnit.indexOf('/')) : '';
      metaText = `${formatCurrency(point.meta)}${suffix}`;
    } else if (opts.metric==='nps') metaText = `${formatNumber(point.meta,1)} pontos`;
    else if (opts.metric==='avaliacao_docente') metaText = `${formatNumber(point.meta,2)} / 10`;
    else metaText = `${formatNumber(point.meta,1)}%`;
    lines.push(`<div class="chart-tip-row"><span>Meta do período</span><b>${escapeHtml(metaText)}</b></div>`);
    if(point.limite_superior!==null&&point.limite_superior!==undefined){
      const upperText=opts.metric==='nps'?`${formatNumber(point.limite_superior,1)} pontos`:opts.metric==='avaliacao_docente'?`${formatNumber(point.limite_superior,2)} / 10`:`${formatNumber(point.limite_superior,1)}%`;
      lines.push(`<div class="chart-tip-row"><span>Limite superior</span><b>${escapeHtml(upperText)}</b></div>`);
    }
    if(point.meta_recorte)lines.push(`<div class="chart-tip-row"><span>Origem</span><b>${escapeHtml(point.meta_recorte)}</b></div>`);
    if(point.meta_vigencia)lines.push(`<div class="chart-tip-row"><span>Vigência</span><b>${escapeHtml(point.meta_vigencia)}</b></div>`);
  }
  if(point.status)lines.push(`<div class="chart-tip-row"><span>Status</span><b>${escapeHtml(point.status)}</b></div>`);
  if(opts.metric==='nps'&&point.respondentes!==undefined){lines.push('<div class="chart-tip-divider"></div>');lines.push(`<div class="chart-tip-row"><span>Respondentes</span><b>${formatNumber(point.respondentes,0)}</b></div>`);lines.push(`<div class="chart-tip-row"><span>Promotores</span><b>${formatNumber(point.promotores,0)}</b></div>`);lines.push(`<div class="chart-tip-row"><span>Neutros</span><b>${formatNumber(point.neutros,0)}</b></div>`);lines.push(`<div class="chart-tip-row"><span>Detratores</span><b>${formatNumber(point.detratores,0)}</b></div>`);if(point.fonte)lines.push(`<div class="chart-tip-row"><span>Fonte</span><b>${escapeHtml(point.fonte)}</b></div>`);}
  if(opts.metric==='avaliacao_docente'&&point.respondentes!==undefined){lines.push('<div class="chart-tip-divider"></div>');lines.push(`<div class="chart-tip-row"><span>Respondentes</span><b>${formatNumber(point.respondentes,0)}</b></div>`);if(point.professores!==undefined)lines.push(`<div class="chart-tip-row"><span>Professores</span><b>${formatNumber(point.professores,0)}</b></div>`);if(point.disciplinas!==undefined)lines.push(`<div class="chart-tip-row"><span>Disciplinas</span><b>${formatNumber(point.disciplinas,0)}</b></div>`);}
  if(opts.metric==='aprovacao'&&point.aprovados!==undefined){lines.push('<div class="chart-tip-divider"></div>');lines.push(`<div class="chart-tip-row"><span>Aprovados</span><b>${formatNumber(point.aprovados,0)}</b></div>`);if(point.finalizados!==undefined)lines.push(`<div class="chart-tip-row"><span>Finalizados</span><b>${formatNumber(point.finalizados,0)}</b></div>`);if(point.reprovados!==undefined)lines.push(`<div class="chart-tip-row"><span>Reprovados</span><b>${formatNumber(point.reprovados,0)}</b></div>`);}
  if(opts.metric==='alunos_aprovados'&&point.alunos_aprovados!==undefined){lines.push('<div class="chart-tip-divider"></div>');lines.push(`<div class="chart-tip-row"><span>Alunos aprovados</span><b>${formatNumber(point.alunos_aprovados,0)}</b></div>`);if(point.alunos_finalizados!==undefined)lines.push(`<div class="chart-tip-row"><span>Alunos com resultado final</span><b>${formatNumber(point.alunos_finalizados,0)}</b></div>`);if(point.aprovados!==undefined)lines.push(`<div class="chart-tip-row"><span>Aprovações disciplinares</span><b>${formatNumber(point.aprovados,0)}</b></div>`);}
  if(opts.metric==='matriculas'&&point.variacao!==null&&point.variacao!==undefined){lines.push(`<div class="chart-tip-row"><span>Variação vs. mês anterior</span><b>${point.variacao>=0?'+':''}${formatNumber(point.variacao,1)}%</b></div>`);if(point.valor_anterior!==null&&point.valor_anterior!==undefined)lines.push(`<div class="chart-tip-row"><span>Mês anterior</span><b>${formatNumber(point.valor_anterior,0)}</b></div>`);}
  if(opts.metric==='frequencia'&&point.presencas_previstas!==undefined){lines.push('<div class="chart-tip-divider"></div>');lines.push(`<div class="chart-tip-row"><span>Presenças previstas</span><b>${formatNumber(point.presencas_previstas,0)}</b></div>`);lines.push(`<div class="chart-tip-row"><span>Presenças registradas</span><b>${formatNumber(point.presencas_registradas,0)}</b></div>`);lines.push(`<div class="chart-tip-row"><span>Disciplinas lançadas</span><b>${formatNumber(point.disciplinas,0)}</b></div>`);}
  if(point.alunos_inicio!==undefined) lines.push(`<div class="chart-tip-row"><span>Alunos no início</span><b>${formatNumber(point.alunos_inicio,0)}</b></div>`);
  if(point.desligamentos!==undefined) lines.push(`<div class="chart-tip-row"><span>Desligamentos</span><b>${formatNumber(point.desligamentos,0)}</b></div>`);
  if(point.alunos_ativos!==undefined&&point.alunos_ativos!==null) lines.push(`<div class="chart-tip-row"><span>Alunos ativos</span><b>${formatNumber(point.alunos_ativos,0)}</b></div>`);
  if(point.despesa!==undefined&&point.despesa!==null) lines.push(`<div class="chart-tip-row"><span>Despesa</span><b>${formatCurrency(point.despesa)}</b></div>`);
  if(point.receita!==undefined&&point.receita!==null) lines.push(`<div class="chart-tip-row"><span>Receita líquida</span><b>${formatCurrency(point.receita)}</b></div>`);
  if(point.resultado!==undefined&&point.resultado!==null) lines.push(`<div class="chart-tip-row"><span>Resultado</span><b>${formatCurrency(point.resultado)}</b></div>`);
  if(point.orcado!==undefined&&point.orcado!==null) lines.push(`<div class="chart-tip-row"><span>Orçado</span><b>${formatCurrency(point.orcado)}</b></div>`);
  if(point.realizado!==undefined&&point.realizado!==null) lines.push(`<div class="chart-tip-row"><span>Realizado</span><b>${formatCurrency(point.realizado)}</b></div>`);
  if(point.desvio!==undefined&&point.desvio!==null) lines.push(`<div class="chart-tip-row"><span>Desvio</span><b>${formatCurrency(point.desvio)}</b></div>`);
  if(point.entradas!==undefined&&point.entradas!==null) lines.push(`<div class="chart-tip-row"><span>Entradas</span><b>${formatCurrency(point.entradas)}</b></div>`);
  if(point.saidas!==undefined&&point.saidas!==null) lines.push(`<div class="chart-tip-row"><span>Saídas</span><b>${formatCurrency(point.saidas)}</b></div>`);
  if(point.saldo_acumulado!==undefined&&point.saldo_acumulado!==null) lines.push(`<div class="chart-tip-row"><span>Saldo acumulado carregado</span><b>${formatCurrency(point.saldo_acumulado)}</b></div>`);
  return lines.join('');
}

function renderLineChart(container, data, opts = {}) {
  if (!container) return;
  const timeline = (data || []).filter(item => item && item.periodo);
  const showGoals = opts.metric !== 'matriculas';
  const hasValues = timeline.some(item => item.valor !== null && item.valor !== undefined);
  const hasGoals = showGoals && timeline.some(item => item.meta !== null && item.meta !== undefined);
  const hasUpper = showGoals && timeline.some(item => item.limite_superior !== null && item.limite_superior !== undefined);
  if (!timeline.length || (!hasValues && !hasGoals && !hasUpper)) {
    container.innerHTML = '<div class="chart-empty"><div><strong>Sem dados para exibir</strong><br><small>O período selecionado não possui resultado nem meta aplicável.</small></div></div>';
    return;
  }

  const width = Math.max(container.clientWidth || 560, 360);
  const height = 260;
  const margin = { top: 24, right: 24, bottom: 48, left: 52 };
  const values = [];
  timeline.forEach(item => {
    if (item.valor !== null && item.valor !== undefined) values.push(Number(item.valor));
    if (showGoals && item.meta !== null && item.meta !== undefined) values.push(Number(item.meta));
    if (showGoals && item.limite_superior !== null && item.limite_superior !== undefined) values.push(Number(item.limite_superior));
  });
  let min = Math.min(...values), max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) { min = 0; max = 1; }
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * .18 || 1;
  min -= pad; max += pad;
  if (opts.suffix === '%' && min > 0) min = Math.max(0, min);

  const spacing = (width - margin.left - margin.right) / Math.max(timeline.length - 1, 1);
  const x = i => margin.left + i * spacing;
  const y = value => margin.top + (max - value) * ((height - margin.top - margin.bottom) / (max - min));
  const ticks = 4;
  const grid = Array.from({ length: ticks + 1 }, (_, i) => {
    const value = min + (max - min) * (i / ticks);
    const yy = y(value);
    return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${yy}" y2="${yy}" stroke="#e4ebe7"/><text x="${margin.left - 8}" y="${yy + 4}" text-anchor="end" fill="#74847c" font-size="10">${escapeHtml(opts.prefix || '')}${formatNumber(value, opts.decimals ?? 1)}${opts.suffix || ''}</text>`;
  }).join('');

  // Resultado: mantém a escala temporal completa e interrompe a linha quando
  // existem períodos sem dado, em vez de comprimir os pontos para a esquerda.
  const resultSegments = [];
  let currentSegment = [];
  timeline.forEach((item, index) => {
    if (item.valor === null || item.valor === undefined) {
      if (currentSegment.length) resultSegments.push(currentSegment);
      currentSegment = [];
      return;
    }
    currentSegment.push({ index, value: Number(item.valor) });
  });
  if (currentSegment.length) resultSegments.push(currentSegment);
  const resultPaths = resultSegments.map(segment => {
    const d = segment.map((point, i) => `${i ? 'L' : 'M'} ${x(point.index)} ${y(point.value)}`).join(' ');
    return `<path d="${d}" fill="none" stroke="#0e8058" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
  }).join('');

  const labelsEvery = timeline.length > 18 ? 3 : timeline.length > 10 ? 2 : 1;
  const labels = timeline.map((p, i) => i % labelsEvery === 0 || i === timeline.length - 1
    ? `<text x="${x(i)}" y="${height - 16}" text-anchor="middle" fill="#74847c" font-size="10">${escapeHtml(formatMonth(p.periodo,true))}</text>`
    : '').join('');
  const circles = timeline.map((p, i) => {
    if (p.valor === null || p.valor === undefined) return '';
    const aboveMetaIsBad = opts.badAboveMeta && p.meta !== null && p.meta !== undefined && Number(p.valor) > Number(p.meta);
    let fill = aboveMetaIsBad ? '#b64a4a' : '#0e8058';
    if (opts.usePointStatus && p.status) { const cls=statusClass(p.status); fill=cls==='success'?'#0e8058':cls==='warning'?'#c08214':cls==='danger'?'#b64a4a':'#78958a'; }
    return `<circle class="chart-point" data-index="${i}" cx="${x(i)}" cy="${y(Number(p.valor))}" r="4.5" fill="${fill}" stroke="white" stroke-width="2"/>`;
  }).join('');

  let metaPath = '';
  if (showGoals) {
    const metaPoints = timeline.map((p, i) => p.meta === null || p.meta === undefined ? null : { i, v: Number(p.meta) }).filter(Boolean);
    if (metaPoints.length) {
      let d = `M ${x(metaPoints[0].i)} ${y(metaPoints[0].v)}`;
      for (let j = 1; j < metaPoints.length; j++) { const curr=metaPoints[j]; d += ` H ${x(curr.i)} V ${y(curr.v)}`; }
      metaPath = `<path d="${d}" fill="none" stroke="#a46700" stroke-width="2" stroke-dasharray="7 5" opacity=".9"/><text x="${width-margin.right}" y="${Math.max(12,y(metaPoints.at(-1).v)-7)}" text-anchor="end" fill="#a46700" font-size="10" font-weight="700">${opts.rangeGoal?'Limite inferior':'Meta do período'}</text>`;
    }
    const upperPoints = timeline.map((p, i) => p.limite_superior === null || p.limite_superior === undefined ? null : { i, v: Number(p.limite_superior) }).filter(Boolean);
    if (upperPoints.length) {
      let d2 = `M ${x(upperPoints[0].i)} ${y(upperPoints[0].v)}`;
      for (let j = 1; j < upperPoints.length; j++) { const curr=upperPoints[j]; d2 += ` H ${x(curr.i)} V ${y(curr.v)}`; }
      metaPath += `<path d="${d2}" fill="none" stroke="#a46700" stroke-width="2" stroke-dasharray="3 5" opacity=".8"/><text x="${width-margin.right}" y="${Math.min(height-margin.bottom-5,y(upperPoints.at(-1).v)+14)}" text-anchor="end" fill="#a46700" font-size="10" font-weight="700">Limite superior</text>`;
    }
  }

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="260" aria-hidden="true">${grid}${metaPath}${resultPaths}<line class="chart-hover-line" x1="0" x2="0" y1="${margin.top}" y2="${height-margin.bottom}" stroke="#7aa995" stroke-dasharray="3 4" opacity="0"/><circle class="chart-hover-focus" cx="0" cy="0" r="7" fill="white" stroke="#0e8058" stroke-width="3" opacity="0"/>${circles}${labels}</svg><div class="chart-hover-card hidden"></div>`;

  const svg = $('svg', container);
  const tip = $('.chart-hover-card', container);
  const hoverLine = $('.chart-hover-line', container);
  const hoverFocus = $('.chart-hover-focus', container);
  const showPoint = (event, index) => {
    index = Math.max(0, Math.min(timeline.length - 1, index));
    const point = timeline[index];
    const px = x(index);
    hoverLine.setAttribute('x1', px); hoverLine.setAttribute('x2', px); hoverLine.setAttribute('opacity', '1');
    if (point.valor !== null && point.valor !== undefined) {
      hoverFocus.setAttribute('cx', px); hoverFocus.setAttribute('cy', y(Number(point.valor))); hoverFocus.setAttribute('opacity', '1');
    } else {
      hoverFocus.setAttribute('opacity', '0');
    }
    tip.innerHTML = chartTooltipContent(point, opts);
    tip.classList.remove('hidden');
    const rect = container.getBoundingClientRect();
    let left = event.clientX - rect.left + 14;
    let top = event.clientY - rect.top - 18;
    if (left + 245 > rect.width) left = Math.max(8, event.clientX - rect.left - 255);
    top = Math.max(8, Math.min(top, rect.height - 190));
    tip.style.left = `${left}px`; tip.style.top = `${top}px`;
  };
  svg.addEventListener('pointermove', event => {
    const rect = svg.getBoundingClientRect();
    const pointerX = (event.clientX - rect.left) / rect.width * width;
    const index = spacing ? Math.round((pointerX - margin.left) / spacing) : 0;
    showPoint(event, index);
  });
  svg.addEventListener('pointerleave', () => {
    tip.classList.add('hidden');
    hoverLine.setAttribute('opacity', '0');
    hoverFocus.setAttribute('opacity', '0');
  });
}

function renderVariationChart(container, data, opts = {}) {
  if (!container) return;
  const valid = (data || []).filter(item => item.variacao !== null && item.variacao !== undefined);
  if (!valid.length) {
    container.innerHTML = '<div class="chart-empty compact"><small>A variação aparece a partir do segundo mês disponível.</small></div>';
    return;
  }
  const width = Math.max(container.clientWidth || 560, 360);
  const height = 150;
  const margin = { top: 14, right: 18, bottom: 40, left: 44 };
  const metaValues = opts.showMeta ? valid.filter(item => item.meta != null).map(item => Math.abs(Number(item.meta))) : [];
  const maxAbs = Math.max(1, ...valid.map(item => Math.abs(Number(item.variacao))), ...metaValues);
  const chartH = height - margin.top - margin.bottom;
  const zeroY = margin.top + chartH / 2;
  const slot = (width - margin.left - margin.right) / Math.max(valid.length, 1);
  const barW = Math.min(28, Math.max(8, slot * .48));
  const scale = value => Math.abs(Number(value)) / maxAbs * (chartH / 2 - 8);
  const labelsEvery = valid.length > 12 ? 2 : 1;
  const bars = valid.map((item, index) => {
    const value = Number(item.variacao);
    const h = scale(value);
    const x = margin.left + index * slot + slot / 2 - barW / 2;
    const y = value >= 0 ? zeroY - h : zeroY;
    const fill = value >= 0 ? '#0e8058' : '#b64a4a';
    const label = index % labelsEvery === 0 || index === valid.length - 1 ? `<text x="${x + barW / 2}" y="${height - 14}" text-anchor="middle" fill="#74847c" font-size="10">${escapeHtml(formatMonth(item.periodo,true))}</text>` : '';
    return `<rect class="variation-bar" data-index="${index}" x="${x}" y="${y}" width="${barW}" height="${Math.max(2,h)}" rx="4" fill="${fill}"/><text x="${x + barW / 2}" y="${value >= 0 ? Math.max(11,y - 5) : Math.min(height - margin.bottom - 2,y + h + 12)}" text-anchor="middle" fill="${fill}" font-size="9" font-weight="700">${value >= 0 ? '+' : ''}${formatNumber(value,1)}%</text>${label}`;
  }).join('');
  let metaPath = '';
  if (opts.showMeta) {
    const points = valid.map((item,index) => item.meta == null ? null : { index, value:Number(item.meta) }).filter(Boolean);
    if (points.length) {
      const yMeta = value => zeroY - (Number(value) / maxAbs) * (chartH / 2 - 8);
      let d = `M ${margin.left + points[0].index * slot + slot / 2} ${yMeta(points[0].value)}`;
      for (let i=1;i<points.length;i++){ const p=points[i]; d += ` H ${margin.left + p.index * slot + slot / 2} V ${yMeta(p.value)}`; }
      metaPath = `<path d="${d}" fill="none" stroke="#a46700" stroke-width="2" stroke-dasharray="6 5"/><text x="${width-margin.right}" y="${Math.max(11,yMeta(points.at(-1).value)-5)}" text-anchor="end" fill="#a46700" font-size="9" font-weight="700">Meta</text>`;
    }
  }
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="150" aria-hidden="true"><line x1="${margin.left}" x2="${width-margin.right}" y1="${zeroY}" y2="${zeroY}" stroke="#b9c7c0" stroke-width="1"/>${metaPath}${bars}</svg><div class="chart-hover-card hidden"></div>`;
  const tip = $('.chart-hover-card', container);
  $$('.variation-bar', container).forEach(bar => {
    const item = valid[Number(bar.dataset.index)];
    const show = event => {
      tip.innerHTML = `<div class="chart-tip-title">${escapeHtml(formatMonth(item.periodo,true))}</div><div class="chart-tip-main"><strong>${item.variacao >= 0 ? '+' : ''}${formatNumber(item.variacao,1)}%</strong><span>variação mensal</span></div>${item.meta == null ? '' : `<div class="chart-tip-row"><span>Meta vigente</span><b>≥ ${formatNumber(item.meta,1)}%</b></div>`}${item.valor_anterior == null ? '' : `<div class="chart-tip-row"><span>Mês anterior</span><b>${formatNumber(item.valor_anterior,0)} alunos</b></div>`}<div class="chart-tip-row"><span>Alunos ativos</span><b>${formatNumber(item.valor,0)}</b></div>`;
      tip.classList.remove('hidden');
      const rect = container.getBoundingClientRect();
      let left = event.clientX - rect.left + 12;
      if (left + 240 > rect.width) left = Math.max(8, left - 250);
      tip.style.left = `${left}px`;
      tip.style.top = '8px';
    };
    bar.addEventListener('mouseenter',show);
    bar.addEventListener('mousemove',show);
    bar.addEventListener('mouseleave',()=>tip.classList.add('hidden'));
  });
}

function wrapChartLabel(value, maxChars = 28, maxLines = 2) {
  const words = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return ['—'];
  const lines = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars || !current) current = candidate;
    else { lines.push(current); current = word; }
  }
  if (current) lines.push(current);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines - 1);
  let tail = lines.slice(maxLines - 1).join(' ');
  if (tail.length > maxChars) tail = `${tail.slice(0, Math.max(1, maxChars - 1)).trimEnd()}…`;
  kept.push(tail);
  return kept;
}

function courseLabelSvg(item, index, x, y, maxChars = 28) {
  const lines = wrapChartLabel(item?.curso, maxChars, 2);
  const firstY = y + (lines.length === 1 ? 17 : 11);
  const tspans = lines.map((line, lineIndex) => `<tspan x="${x}" ${lineIndex ? 'dy="12"' : ''}>${escapeHtml(line)}</tspan>`).join('');
  return `<text class="course-bar-label" data-index="${index}" x="${x}" y="${firstY}" text-anchor="end" fill="#2b3d35" font-size="10">${tspans}</text>`;
}

function npsStatusLegendHtml() {
  return `<div class="nps-goal-legend" aria-label="Legenda das cores por meta"><span class="nps-goal-legend-title">Cores pela meta</span><span><i class="success"></i>Dentro da meta</span><span><i class="warning"></i>Atenção</span><span><i class="danger"></i>Fora da meta</span><span><i class="neutral"></i>Sem meta</span></div>`;
}

function renderBarChart(container, data, opts = {}) {
  if (!container) return;
  const valid = (data || []).filter(x => x.valor !== null && x.valor !== undefined);
  if (!valid.length) { container.innerHTML = '<div class="chart-empty">Sem dados para comparar no período selecionado.</div>'; return; }
  const sorted = [...valid].sort((a, b) => Number(b.valor) - Number(a.valor));
  const width = Math.max(container.clientWidth || 760, 520);
  const wrapLabels = opts.wrapLabels !== false;
  const rowH = wrapLabels ? 44 : 35;
  const margin = { top: 10, right: 68, bottom: 10, left: Math.min(285, Math.max(175, width * .31)) };
  const height = margin.top + margin.bottom + sorted.length * rowH;
  const min = Math.min(0, ...sorted.map(x => Number(x.valor)));
  const max = Math.max(1, ...sorted.map(x => Number(x.valor)));
  const zeroX = margin.left + (0 - min) / (max - min) * (width - margin.left - margin.right);
  const xVal = value => margin.left + (Number(value) - min) / (max - min) * (width - margin.left - margin.right);
  const maxLabelChars = Math.max(18, Math.min(34, Math.floor((margin.left - 26) / 5.7)));
  const rows = sorted.map((item, i) => {
    const yy = margin.top + i * rowH + Math.max(5, (rowH - 22) / 2);
    const end = xVal(item.valor);
    const xPos = Math.min(zeroX, end);
    const barW = Math.max(2, Math.abs(end - zeroX));
    const cls = statusClass(item.status);
    const compositionTone = String(item.compositionTone || '').toLowerCase();
    const fill = compositionTone === 'promoter' ? '#0e8058'
      : compositionTone === 'neutral' ? '#c08214'
      : compositionTone === 'detractor' ? '#b64a4a'
      : cls === 'success' ? '#0e8058'
      : cls === 'warning' ? '#c08214'
      : cls === 'danger' ? '#b64a4a'
      : '#78958a';
    const label = wrapLabels
      ? courseLabelSvg(item, i, margin.left - 10, yy, maxLabelChars)
      : `<text class="course-bar-label" data-index="${i}" x="${margin.left - 10}" y="${yy + 17}" text-anchor="end" fill="#2b3d35" font-size="10">${escapeHtml(item.curso)}</text>`;
    return `${label}<rect class="interactive-bar" data-index="${i}" x="${xPos}" y="${yy}" width="${barW}" height="22" rx="5" fill="${fill}"/><text x="${end >= zeroX ? end + 7 : end - 7}" y="${yy + 15}" text-anchor="${end >= zeroX ? 'start' : 'end'}" fill="#5b6d64" font-size="10" font-weight="700">${escapeHtml(opts.prefix || '')}${formatNumber(item.valor, opts.decimals ?? 1)}${opts.suffix || ''}</text>`;
  }).join('');
  const hint = opts.clickFilter === false ? 'Passe o mouse para detalhes' : 'Passe o mouse para detalhes · clique em um curso para filtrar o painel';
  const legend = opts.statusLegend && valid.some(item => item.status) ? npsStatusLegendHtml() : '';
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${Math.max(280, height)}" aria-hidden="true"><line x1="${zeroX}" x2="${zeroX}" y1="0" y2="${height}" stroke="#dce5e0"/>${rows}</svg><div class="chart-hover-card hidden"></div>${legend}<div class="chart-click-hint">${hint}</div>`;
  const tip = $('.chart-hover-card', container);
  const showFor = (item, event) => {
    tip.innerHTML = chartTooltipContent(item, { ...opts, unit: opts.unit || (opts.metric === 'matriculas' ? 'alunos' : opts.metric === 'nps' ? 'pontos' : '%') });
    tip.classList.remove('hidden');
    const rect = container.getBoundingClientRect();
    const tipWidth = tip.offsetWidth || 235;
    const tipHeight = tip.offsetHeight || 120;
    let left = event.clientX - rect.left + 12;
    let top = event.clientY - rect.top - 12;
    if (left + tipWidth + 8 > rect.width) left = Math.max(8, event.clientX - rect.left - tipWidth - 12);
    if (top + tipHeight + 8 > rect.height) top = Math.max(8, rect.height - tipHeight - 8);
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  };
  const applyCourseFilter = async item => {
    if (opts.clickFilter === false) return;
    const select = $('#dashboardCourse');
    if (select && [...select.options].some(option => option.value === item.curso)) {
      select.value = item.curso;
      await loadDashboard();
      toast('Filtro aplicado', `Painel atualizado para ${item.curso}.`);
    }
  };
  $$('.interactive-bar, .course-bar-label', container).forEach(element => {
    const item = sorted[Number(element.dataset.index)];
    if (!item) return;
    const show = event => showFor(item, event);
    element.addEventListener('mouseenter', show);
    element.addEventListener('mousemove', show);
    element.addEventListener('mouseleave', () => tip.classList.add('hidden'));
    if (opts.clickFilter !== false) element.addEventListener('click', () => applyCourseFilter(item));
  });
}

function fillCoursePerformancePeriods(){
  const select=$('#coursePerformancePeriod');
  if(!select||!state.dashboard)return;
  const performance=state.dashboard.desempenho_cursos || {};
  const periods=performance.periodos || state.dashboard.periodos?.semestrais || [];
  let current=state.coursePerformancePeriod || 'geral';
  if(current!=='geral'&&!periods.includes(current)) current='geral';
  state.coursePerformancePeriod=current;
  select.innerHTML=option('geral',current==='geral','Geral · todo histórico')+periods.slice().reverse().map(period=>option(period,period===current,formatMonth(period,true))).join('');
}

function renderCourseComparison() {
  if (!state.dashboard) return;
  fillCoursePerformancePeriods();
  const metric = state.comparisonMetric;
  const performance=state.dashboard.desempenho_cursos || {};
  const selected=state.coursePerformancePeriod || 'geral';
  const data = selected==='geral'
    ? (performance.geral?.[metric] || state.dashboard.comparacoes?.[metric] || [])
    : (performance.por_semestre?.[selected]?.[metric] || []);
  const opts = metric === 'nps'
    ? { suffix: '', decimals: 1, metric: 'nps', statusLegend: true }
    : metric === 'avaliacao_docente'
      ? { suffix: '', decimals: 2, metric: 'avaliacao_docente' }
      : { suffix: '%', decimals: 1, metric: 'aprovacao' };
  renderBarChart($('#chartCourseComparison'), data, opts);
  const rows = [...data].sort((a, b) => (b.valor ?? -Infinity) - (a.valor ?? -Infinity));
  const target = $('#courseComparisonTable');
  if (!target) return;
  const key = `course-comparison-${metric}-${selected}`;
  const page = paginate(rows, key);
  const unit = metric === 'aprovacao' ? '%' : metric === 'nps' ? ' pts' : '';
  const contextLabel=selected==='geral'?'Todo histórico':formatMonth(selected,true);
  const showNpsGoal = metric === 'nps' && rows.some(item => item.status);
  target.innerHTML = rows.length ? `<table><thead><tr><th>Curso</th><th>Período</th><th class="numeric">Resultado</th>${showNpsGoal?'<th class="numeric">Meta</th><th>Status</th>':''}</tr></thead><tbody>${page.rows.map(item => `<tr><td>${escapeHtml(item.curso)}</td><td>${escapeHtml(contextLabel)}</td><td class="numeric"><strong>${formatNumber(item.valor, opts.decimals)}${unit}</strong></td>${showNpsGoal?`<td class="numeric">${item.meta==null?'—':`${formatNumber(item.meta,1)} pts`}</td><td>${badge(item.status,item.status||'Sem meta')}</td>`:''}</tr>`).join('')}</tbody></table>` : `<div class="empty-table">Sem dados por curso em ${escapeHtml(contextLabel)}.</div>`;
  attachPagination(target, key, rows.length, renderCourseComparison);
}

const columns = {
  nps: [
    ['periodo', 'Período', '', v => formatMonth(v,true)], ['curso', 'Curso'], ['respondentes', 'Respondentes', 'numeric'], ['promotores', 'Promotores', 'numeric'],
    ['neutros', 'Neutros', 'numeric'], ['detratores', 'Detratores', 'numeric'], ['valor', 'NPS', 'numeric', v => formatNumber(v, 1)],
    ['fonte', 'Fonte'], ['validacao', 'Validação', '', v => badge(v)], ['lancado_por', 'Lançado por']
  ],
  avaliacao_docente: [
    ['periodo', 'Semestre', '', v => formatMonth(v,true)], ['curso', 'Curso'], ['disciplina', 'Disciplina'], ['professor', 'Professor'],
    ['respondentes', 'Respondentes', 'numeric', v => formatNumber(v,0)], ['nota_media', 'Nota média', 'numeric', v => formatNumber(v,2)],
    ['validacao', 'Validação', '', v => badge(v)], ['lancado_por', 'Lançado por']
  ],
  resultados: [
    ['periodo', 'Semestre', '', v => formatMonth(v,true)], ['curso', 'Curso'], ['disciplina', 'Disciplina'], ['turma', 'Turma'],
    ['matricula', 'Matrícula'], ['aluno', 'Aluno'], ['media', 'Média', 'numeric', v => v == null ? '—' : formatNumber(v,2)],
    ['situacao', 'Situação'], ['motivo_reprovacao', 'Motivo reprovação', '', v => v || '—'], ['fonte', 'Fonte'],
    ['lancado_por', 'Lançado por']
  ]
};


function resultFilterQuery({ includeSearch = false } = {}) {
  const params = new URLSearchParams();
  if (state.resultFilters.periodo) params.set('periodo', state.resultFilters.periodo);
  if (state.resultFilters.curso) params.set('curso', state.resultFilters.curso);
  if (state.resultFilters.disciplina) params.set('disciplina', state.resultFilters.disciplina);
  if (includeSearch && (state.searches.resultados || '').trim()) params.set('busca', state.searches.resultados.trim());
  return params;
}

async function loadResultSummary(force = false) {
  if (state.resultSummary.length && !force) return state.resultSummary;
  const params = resultFilterQuery();
  const response = await api(`/api/resultados/resumo${params.toString() ? `?${params}` : ''}`);
  state.resultSummary = response.items || [];
  return state.resultSummary;
}

function visibleResultSummary() {
  const term = (state.searches.resultados || '').trim().toLocaleLowerCase('pt-BR');
  if (!term) return state.resultSummary;
  return state.resultSummary.filter(item => [item.periodo, item.curso, item.disciplina]
    .some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(term)));
}

function resultTrendQuery() {
  const params=new URLSearchParams();
  if(state.resultFilters.curso) params.set('curso',state.resultFilters.curso);
  if(state.resultFilters.disciplina) params.set('disciplina',state.resultFilters.disciplina);
  return params;
}

async function loadResultTrend(force=false) {
  const params=resultTrendQuery();
  const key=params.toString();
  if(!force && state.resultTrendKey===key && state.resultTrend.length) return state.resultTrend;
  const response=await api(`/api/resultados/tendencia${key?`?${key}`:''}`);
  state.resultTrend=response.items||[]; state.resultTrendKey=key;
  return state.resultTrend;
}

function renderResultTrend() {
  const series=(state.resultTrend||[]).map(item=>({
    ...item,
    valor:item.taxa_aprovacao,
  }));
  renderLineChart($('#chartResultsApprovalTrend'),series,{suffix:'%',decimals:1,metric:'aprovacao',unit:'%'});
  renderLineChart($('#chartResultsApprovedTrend'),series.map(item=>({...item,valor:item.alunos_aprovados})),{decimals:0,metric:'alunos_aprovados',unit:'alunos distintos'});
  const pieces=[];
  if(state.resultFilters.curso)pieces.push(`Curso: ${state.resultFilters.curso}`);
  if(state.resultFilters.disciplina)pieces.push(`Disciplina: ${state.resultFilters.disciplina}`);
  if(state.resultFilters.periodo)pieces.push(`Semestre: ${formatMonth(state.resultFilters.periodo,true)}`);
  const ctx=$('#resultsTrendContext');if(ctx)ctx.textContent=pieces.length?`${pieces.join(' · ')} · gráficos mostram todo o histórico do recorte`:'Gráficos mostram todo o histórico consolidado da diretoria';
}

function renderResultSummaryCards(items = visibleResultSummary()) {
  const target = $('#resultsSummaryCards');
  if (!target) return;
  const finalized = items.reduce((sum, row) => sum + Number(row.finalizados || 0), 0);
  const approved = items.reduce((sum, row) => sum + Number(row.aprovados || 0), 0);
  const failedGrade = items.reduce((sum, row) => sum + Number(row.reprovados_nota || 0), 0);
  const failedAbsence = items.reduce((sum, row) => sum + Number(row.reprovados_falta || 0), 0);
  const gradeCount = items.reduce((sum, row) => sum + Number(row.notas_contagem || 0), 0);
  const gradeSum = items.reduce((sum, row) => sum + Number(row.soma_notas ?? (Number(row.media_notas || 0) * Number(row.notas_contagem || 0))), 0);
  const avg = gradeCount ? gradeSum / gradeCount : null;
  const rate = finalized ? approved / finalized * 100 : null;
  target.innerHTML = [
    ['Taxa de aprovação', rate == null ? '—' : `${formatNumber(rate,1)}%`, `${formatNumber(finalized,0)} resultado(s) finalizado(s)`, 'success'],
    ['Aprovações', formatNumber(approved,0), 'situação oficial aprovada', 'success'],
    ['Reprovação por nota', formatNumber(failedGrade,0), 'reprovações sem indicação de falta', failedGrade ? 'danger' : 'neutral'],
    ['Reprovação por falta', formatNumber(failedAbsence,0), 'reprovações por falta/frequência', failedAbsence ? 'warning' : 'neutral'],
    ['Média das notas', avg == null ? '—' : formatNumber(avg,2), `${formatNumber(gradeCount,0)} nota(s) disponível(is)`, 'info'],
  ].map(([label,value,sub,tone]) => `<article class="result-summary-card ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></article>`).join('');
}

function renderResultSummaryTable() {
  const items = visibleResultSummary();
  renderResultSummaryCards(items);
  renderResultTrend();
  const key = 'data-resultados';
  const page = paginate(items, key);
  const target = $('#table-resultados');
  const count = $('#count-resultados');
  if (count) count.textContent = items.length ? `${page.start + 1}–${Math.min(items.length, page.start + page.rows.length)} de ${items.length} resumo(s)` : '0 resumos';
  if (!target) return;
  if (!items.length) {
    target.innerHTML = '<div class="empty-table"><strong>Nenhum resumo encontrado</strong>Altere o curso, a disciplina ou a busca.</div>';
    return;
  }
  target.innerHTML = `<table class="academic-summary-table"><thead><tr>
    <th>Semestre</th><th>Curso</th><th>Disciplina</th><th class="numeric">Total</th><th class="numeric">Aprovados</th>
    <th class="numeric">Rep. nota</th><th class="numeric">Rep. falta</th><th class="numeric">Em andamento</th>
    <th class="numeric">Taxa</th><th class="numeric">Média</th>
  </tr></thead><tbody>${page.rows.map(item => `<tr>
    <td>${escapeHtml(formatMonth(item.periodo,true))}</td><td>${escapeHtml(item.curso)}</td><td><strong>${escapeHtml(item.disciplina)}</strong></td>
    <td class="numeric">${formatNumber(item.total_registros,0)}</td><td class="numeric outcome-approved">${formatNumber(item.aprovados,0)}</td>
    <td class="numeric outcome-grade">${formatNumber(item.reprovados_nota,0)}</td><td class="numeric outcome-absence">${formatNumber(item.reprovados_falta,0)}</td>
    <td class="numeric">${formatNumber(item.em_andamento,0)}</td><td class="numeric"><strong>${item.taxa_aprovacao == null ? '—' : `${formatNumber(item.taxa_aprovacao,1)}%`}</strong></td>
    <td class="numeric"><strong>${item.media_notas == null ? '—' : formatNumber(item.media_notas,2)}</strong></td>
  </tr>`).join('')}</tbody></table>`;
  attachPagination(target, key, items.length, renderResultSummaryTable);
}

async function loadResultDetails() {
  const cfg = paginationFor('data-resultados');
  const params = resultFilterQuery({ includeSearch: true });
  params.set('page', cfg.page);
  params.set('page_size', cfg.size);
  const response = await api(`/api/dados/resultados?${params}`);
  state.data.resultados = response.items || [];
  state.resultServer = {
    total: Number(response.total || 0),
    page: Number(response.page || 1),
    pageSize: Number(response.page_size || cfg.size),
    pages: Number(response.pages || 1),
  };
  cfg.page = state.resultServer.page;
  cfg.size = state.resultServer.pageSize;
  renderResultDetailTable();
}

function renderResultDetailTable() {
  renderResultSummaryCards();
  const items = state.data.resultados || [];
  const target = $('#table-resultados');
  const total = state.resultServer.total || 0;
  const cfg = paginationFor('data-resultados');
  const start = total ? (cfg.page - 1) * cfg.size : 0;
  const count = $('#count-resultados');
  if (count) count.textContent = total ? `${start + 1}–${Math.min(total, start + items.length)} de ${total} registros` : '0 registros';
  if (!target) return;
  if (!items.length) {
    target.innerHTML = '<div class="empty-table"><strong>Nenhum registro encontrado</strong>Altere os filtros ou a busca.</div>';
    return;
  }
  const defs = columns.resultados;
  const editable = canEditCurrentDirectorate();
  target.innerHTML = `<table><thead><tr>${defs.map(c=>`<th class="${c[2]||''}">${escapeHtml(c[1])}</th>`).join('')}${editable?'<th class="actions">Ações</th>':''}</tr></thead><tbody>${items.map(item=>`<tr>${defs.map(c=>{const raw=item[c[0]];const value=c[3]?c[3](raw):escapeHtml(raw||raw===0?raw:'—');return `<td class="${c[2]||''}">${value}</td>`;}).join('')}${editable?`<td class="actions"><button class="row-action" title="Editar" data-edit="resultados" data-id="${item.id}">✎</button><button class="row-action delete" title="Excluir" data-delete="resultados" data-id="${item.id}">×</button></td>`:''}</tr>`).join('')}</tbody></table>`;
  attachPagination(target, 'data-resultados', total, () => loadDataset('resultados', true));
  $$('[data-edit="resultados"]',target).forEach(btn=>btn.addEventListener('click',()=>openDataForm('resultados',Number(btn.dataset.id))));
  $$('[data-delete="resultados"]',target).forEach(btn=>btn.addEventListener('click',()=>deleteData('resultados',Number(btn.dataset.id))));
}

function npsAggregate(rows) {
  const respondents=(rows||[]).reduce((sum,row)=>sum+Number(row.respondentes||0),0);
  const promoters=(rows||[]).reduce((sum,row)=>sum+Number(row.promotores||0),0);
  const neutrals=(rows||[]).reduce((sum,row)=>sum+Number(row.neutros||0),0);
  const detractors=(rows||[]).reduce((sum,row)=>sum+Number(row.detratores||0),0);
  return {
    respondents,promoters,neutrals,detractors,
    score:respondents?((promoters-detractors)/respondents*100):null,
    promoterPct:respondents?(promoters/respondents*100):null,
    neutralPct:respondents?(neutrals/respondents*100):null,
    detractorPct:respondents?(detractors/respondents*100):null,
  };
}

function npsSimpleCard(label,value,sub,icon='NPS') {
  return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span><span class="metric-icon">${escapeHtml(icon)}</span></div><div class="metric-value">${value}</div><div class="metric-sub">${escapeHtml(sub)}</div><div class="metric-status">${badge('Dados','SEI')}</div></article>`;
}

function npsWindowPeriods(rows, windowValue, anchorPeriod='') {
  let periods=sortedUnique((rows||[]).map(row=>row.periodo).filter(Boolean)).sort((a,b)=>periodStartKey(a)-periodStartKey(b));
  if(anchorPeriod) periods=periods.filter(period=>periodStartKey(period)<=periodStartKey(anchorPeriod));
  if(windowValue==='all') return periods;
  const size=Math.max(1,Number(windowValue||6));
  return periods.slice(-size);
}

function npsAggregateByPeriod(rows) {
  const grouped={};
  (rows||[]).forEach(row=>{(grouped[row.periodo] ||= []).push(row);});
  return Object.entries(grouped).map(([periodo,items])=>{
    const metric=npsAggregate(items);
    return {periodo,valor:metric.score,respondentes:metric.respondents,promotores:metric.promoters,neutros:metric.neutrals,detratores:metric.detractors};
  }).sort((a,b)=>periodStartKey(a.periodo)-periodStartKey(b.periodo));
}

function fillNpsCourseFilters() {
  const rows=state.data.nps||[];
  const periods=sortedUnique(rows.map(row=>row.periodo).filter(Boolean)).sort((a,b)=>periodStartKey(b)-periodStartKey(a));
  const courses=sortedUnique(rows.map(row=>row.curso).filter(Boolean)).sort((a,b)=>a.localeCompare(b,'pt-BR'));
  const p=$('#npsCoursePeriodFilter'), c=$('#npsCourseFilter'), w=$('#npsCourseWindow');
  if(p){ if(state.npsCourseFilters.periodo&&!periods.includes(state.npsCourseFilters.periodo))state.npsCourseFilters.periodo=''; p.innerHTML=option('',!state.npsCourseFilters.periodo,'Todos os semestres')+periods.map(v=>option(v,v===state.npsCourseFilters.periodo,formatMonth(v,true))).join(''); }
  if(c){ if(state.npsCourseFilters.curso&&!courses.includes(state.npsCourseFilters.curso))state.npsCourseFilters.curso=''; c.innerHTML=option('',!state.npsCourseFilters.curso,'Todos os cursos')+courses.map(v=>option(v,v===state.npsCourseFilters.curso,v)).join(''); }
  if(w)w.value=state.npsCourseFilters.window||'6';
}

function npsCourseRowsForFilters({includePeriod=true}={}) {
  const f=state.npsCourseFilters;
  return (state.data.nps||[]).filter(row=>(!f.curso||row.curso===f.curso)&&(!includePeriod||!f.periodo||row.periodo===f.periodo));
}

function renderNpsCourseSummary() {
  const target=$('#npsCourseSummary'); if(!target)return;
  fillNpsCourseFilters();
  const f=state.npsCourseFilters;
  const historyRows=npsCourseRowsForFilters({includePeriod:false});
  const rows=npsCourseRowsForFilters();
  const periods=sortedUnique(rows.map(row=>row.periodo)).sort((a,b)=>periodStartKey(b)-periodStartKey(a));
  const focusPeriod=f.periodo||periods[0];
  const focusRows=focusPeriod?rows.filter(row=>row.periodo===focusPeriod):[];
  const m=npsAggregate(focusRows);
  const context=$('#npsCourseContext');
  if(context) context.innerHTML=`<strong>Recorte:</strong> ${escapeHtml(f.curso||'Todos os cursos')} · ${escapeHtml(f.periodo?formatMonth(f.periodo,true):'todo o histórico')} · gráfico ${escapeHtml(f.window==='all'?'todo histórico':`${f.window} semestres`)}`;
  if(!rows.length){target.innerHTML=npsSimpleCard('NPS do Curso','—','Nenhum registro encontrado no recorte');renderLineChart($('#chartNpsCourseEvolution'),[],{});renderBarChart($('#chartNpsCourseComparison'),[],{});return;}
  target.innerHTML=[
    npsSimpleCard(f.curso?'NPS do curso':'NPS geral dos cursos',m.score==null?'—':formatNumber(m.score,1),`${formatMonth(focusPeriod,true)} · ${focusRows.length} curso(s)`,'01B'),
    npsSimpleCard('Respondentes',formatNumber(m.respondents,0),'respostas no recorte','Σ'),
    npsSimpleCard('Promotores',m.promoterPct==null?'—':`${formatNumber(m.promoterPct,1)}%`,`${formatNumber(m.promoters,0)} resposta(s)`,'9–10'),
    npsSimpleCard('Detratores',m.detractorPct==null?'—':`${formatNumber(m.detractorPct,1)}%`,`${formatNumber(m.detractors,0)} resposta(s)`,'0–6'),
  ].join('');
  const allowed=npsWindowPeriods(historyRows,f.window,f.periodo);
  const trend=npsAggregateByPeriod(historyRows.filter(row=>allowed.includes(row.periodo)));
  renderLineChart($('#chartNpsCourseEvolution'),trend,{suffix:'',decimals:1,metric:'nps',unit:'pontos'});
  const evolutionTitle=$('#npsCourseEvolutionTitle'); if(evolutionTitle)evolutionTitle.textContent=f.curso?`Evolução · ${f.curso}`:'Evolução agregada dos cursos';
  const comparisonPeriod=f.periodo||allowed.at(-1)||focusPeriod;
  const comparisonRows=(state.data.nps||[]).filter(row=>row.periodo===comparisonPeriod&&(!f.curso||row.curso===f.curso)).map(row=>({curso:row.curso,valor:Number(row.valor),respondentes:row.respondentes,promotores:row.promotores,neutros:row.neutros,detratores:row.detratores,meta:row.meta,atencao:row.atencao,limite_superior:row.limite_superior,meta_vigencia:row.meta_vigencia,meta_recorte:row.meta_recorte,status:row.status}));
  renderBarChart($('#chartNpsCourseComparison'),comparisonRows,{suffix:'',decimals:1,metric:'nps',unit:'pontos',clickFilter:false,statusLegend:true});
  const comparisonTitle=$('#npsCourseComparisonTitle'); if(comparisonTitle)comparisonTitle.textContent=`Cursos · ${formatMonth(comparisonPeriod,true)}`;
}

async function loadInstitutionNps(force = false) {
  if(state.npsInstitution.length && !force){fillNpsInstitutionFilters();renderInstitutionNps();return;}
  try{
    const response=await api('/api/surveys/nps/institution/history',{blocking:false});
    state.npsInstitution=response.items||[];
    state.npsInstitutionByCourse=response.by_course||[];
    fillNpsInstitutionFilters();
    renderInstitutionNps();
  }catch(error){toast('Erro ao carregar NPS da Instituição',error.message,'error');}
}

function fillNpsInstitutionFilters() {
  const all=[...(state.npsInstitution||[]),...(state.npsInstitutionByCourse||[])];
  const periods=sortedUnique(all.map(row=>row.periodo).filter(Boolean)).sort((a,b)=>periodStartKey(b)-periodStartKey(a));
  const courses=sortedUnique((state.npsInstitutionByCourse||[]).map(row=>row.curso).filter(Boolean)).sort((a,b)=>a.localeCompare(b,'pt-BR'));
  const p=$('#npsInstitutionPeriodFilter'), c=$('#npsInstitutionCourseFilter'), w=$('#npsInstitutionWindow');
  if(p){if(state.npsInstitutionFilters.periodo&&!periods.includes(state.npsInstitutionFilters.periodo))state.npsInstitutionFilters.periodo='';p.innerHTML=option('',!state.npsInstitutionFilters.periodo,'Todos os semestres')+periods.map(v=>option(v,v===state.npsInstitutionFilters.periodo,formatMonth(v,true))).join('');}
  if(c){if(state.npsInstitutionFilters.curso&&!courses.includes(state.npsInstitutionFilters.curso))state.npsInstitutionFilters.curso='';c.innerHTML=option('',!state.npsInstitutionFilters.curso,'Todos os cursos')+courses.map(v=>option(v,v===state.npsInstitutionFilters.curso,v)).join('');}
  if(w)w.value=state.npsInstitutionFilters.window||'6';
}

function renderInstitutionNps() {
  const summary=$('#npsInstitutionSummary'); const table=$('#table-nps-institution');
  if(!summary||!table)return;
  fillNpsInstitutionFilters();
  const f=state.npsInstitutionFilters;
  const overall=[...(state.npsInstitution||[])];
  const byCourse=[...(state.npsInstitutionByCourse||[])];
  const directorateBase=f.curso
    ? byCourse.filter(row=>row.curso===f.curso)
    : npsAggregateByPeriod(byCourse);
  const directorateFiltered=directorateBase.filter(row=>!f.periodo||row.periodo===f.periodo).sort((a,b)=>periodStartKey(b.periodo)-periodStartKey(a.periodo));
  const latest=directorateFiltered[0];
  const overallFiltered=overall.filter(row=>!f.periodo||row.periodo===f.periodo).sort((a,b)=>periodStartKey(b.periodo)-periodStartKey(a.periodo));
  const overallFocus=overallFiltered[0];
  const context=$('#npsInstitutionContext');
  const directorateLabel=f.curso?f.curso:(state.activeDirectorate||'Diretoria');
  if(context)context.innerHTML=`<strong>Recorte:</strong> ${escapeHtml(directorateLabel)} · ${escapeHtml(f.periodo?formatMonth(f.periodo,true):'todo o histórico')} · gráfico ${escapeHtml(f.window==='all'?'todo histórico':`${f.window} semestres`)} · o gráfico geral da UNIVC ignora o filtro de curso.`;

  const promoterPct=latest?.respondentes?latest.promotores/latest.respondentes*100:null;
  const detractorPct=latest?.respondentes?latest.detratores/latest.respondentes*100:null;
  summary.innerHTML=[
    npsSimpleCard(f.curso?'NPS institucional do curso':`NPS · ${state.activeDirectorate||'Diretoria'}`,latest?.valor==null?'—':formatNumber(latest.valor,1),latest?formatMonth(latest.periodo,true):'sem dado no recorte','01A'),
    npsSimpleCard('NPS geral UNIVC',overallFocus?.valor==null?'—':formatNumber(overallFocus.valor,1),overallFocus?formatMonth(overallFocus.periodo,true):'sem dado no recorte','UNIVC'),
    npsSimpleCard('Respondentes',formatNumber(latest?.respondentes||0,0),'respostas no recorte da diretoria','Σ'),
    npsSimpleCard('Promotores / Detratores',promoterPct==null?'—':`${formatNumber(promoterPct,1)}% / ${formatNumber(detractorPct,1)}%`,'comparação do recorte','9–10 / 0–6'),
  ].join('');

  const allowedDirectorate=npsWindowPeriods(directorateBase,f.window,f.periodo);
  const directorateTrend=directorateBase.filter(row=>allowedDirectorate.includes(row.periodo)).sort((a,b)=>periodStartKey(a.periodo)-periodStartKey(b.periodo)).map(row=>({periodo:row.periodo,valor:row.valor,respondentes:row.respondentes,promotores:row.promotores,neutros:row.neutros,detratores:row.detratores}));
  renderLineChart($('#chartNpsInstitution'),directorateTrend,{suffix:'',decimals:1,metric:'nps',unit:'pontos'});
  const evolutionTitle=$('#npsInstitutionEvolutionTitle'); if(evolutionTitle)evolutionTitle.textContent=f.curso?`NPS institucional · ${f.curso}`:`NPS institucional · ${state.activeDirectorate||'Diretoria'}`;

  const allowedOverall=npsWindowPeriods(overall,f.window,f.periodo);
  const overallTrend=overall.filter(row=>allowedOverall.includes(row.periodo)).sort((a,b)=>periodStartKey(a.periodo)-periodStartKey(b.periodo)).map(row=>({periodo:row.periodo,valor:row.valor,respondentes:row.respondentes,promotores:row.promotores,neutros:row.neutros,detratores:row.detratores}));
  renderLineChart($('#chartNpsInstitutionOverall'),overallTrend,{suffix:'',decimals:1,metric:'nps',unit:'pontos'});
  const overallTitle=$('#npsInstitutionOverallTitle'); if(overallTitle)overallTitle.textContent='NPS geral da instituição · todos os cursos';

  // Comparative snapshot: always shows every course in the active directorate.
  // Course is intentionally ignored here. Semester chooses the snapshot and
  // the trend window controls only the two line charts above.
  const comparisonPeriods=sortedUnique(byCourse.map(row=>row.periodo).filter(Boolean)).sort((a,b)=>periodStartKey(b)-periodStartKey(a));
  const comparisonPeriod=f.periodo||comparisonPeriods[0]||'';
  const comparison=comparisonPeriod
    ? byCourse.filter(row=>row.periodo===comparisonPeriod).map(row=>({curso:row.curso,valor:row.valor,respondentes:row.respondentes,promotores:row.promotores,neutros:row.neutros,detratores:row.detratores,meta:row.meta,atencao:row.atencao,limite_superior:row.limite_superior,meta_vigencia:row.meta_vigencia,meta_recorte:row.meta_recorte,status:row.status}))
    : [];
  renderBarChart($('#chartNpsInstitutionCourses'),comparison,{suffix:'',decimals:1,metric:'nps',unit:'pontos',clickFilter:false,statusLegend:true});
  const comparisonTitle=$('#npsInstitutionComparisonTitle');
  if(comparisonTitle)comparisonTitle.textContent=comparisonPeriod?`NPS institucional por curso · ${formatMonth(comparisonPeriod,true)}`:'NPS institucional por curso';

  const term=(state.npsInstitutionSearch||'').trim().toLowerCase();
  let rows;
  const showBreakdown=Boolean(f.curso||f.periodo);
  if(showBreakdown){rows=byCourse.filter(row=>(!f.curso||row.curso===f.curso)&&(!f.periodo||row.periodo===f.periodo));}
  else rows=npsAggregateByPeriod(byCourse).sort((a,b)=>periodStartKey(b.periodo)-periodStartKey(a.periodo));
  if(term)rows=rows.filter(row=>Object.values(row).some(value=>String(value??'').toLowerCase().includes(term)));
  rows.sort((a,b)=>periodStartKey(b.periodo)-periodStartKey(a.periodo));
  const page=paginate(rows,'nps-institution');
  $('#count-nps-institution').textContent=rows.length?`${page.start+1}–${Math.min(rows.length,page.start+page.rows.length)} de ${rows.length}`:'0 registros';
  if(!rows.length){table.innerHTML='<div class="empty-table"><strong>Nenhum NPS institucional encontrado</strong>Altere os filtros ou sincronize a pergunta institucional pelo SEI.</div>';return;}
  table.innerHTML=showBreakdown
    ? `<table><thead><tr><th>Semestre</th><th>Curso</th><th>NPS institucional</th><th>Respondentes</th><th>Promotores</th><th>Neutros</th><th>Detratores</th></tr></thead><tbody>${page.rows.map(row=>`<tr><td>${escapeHtml(formatMonth(row.periodo,true))}</td><td><strong>${escapeHtml(row.curso||'—')}</strong></td><td><strong>${row.valor==null?'—':formatNumber(row.valor,1)}</strong></td><td>${formatNumber(row.respondentes,0)}</td><td>${formatNumber(row.promotores,0)}</td><td>${formatNumber(row.neutros,0)}</td><td>${formatNumber(row.detratores,0)}</td></tr>`).join('')}</tbody></table>`
    : `<table><thead><tr><th>Semestre</th><th>NPS da diretoria</th><th>Respondentes</th><th>Promotores</th><th>Neutros</th><th>Detratores</th></tr></thead><tbody>${page.rows.map(row=>`<tr><td>${escapeHtml(formatMonth(row.periodo,true))}</td><td><strong>${row.valor==null?'—':formatNumber(row.valor,1)}</strong></td><td>${formatNumber(row.respondentes,0)}</td><td>${formatNumber(row.promotores,0)}</td><td>${formatNumber(row.neutros,0)}</td><td>${formatNumber(row.detratores,0)}</td></tr>`).join('')}</tbody></table>`;
  attachPagination(table,'nps-institution',rows.length,renderInstitutionNps);
}

async function loadFacultyNps(force = false) {
  if (state.npsFaculty.length && !force) { fillNpsFacultyFilters(); renderFacultyNps(); return; }
  try {
    const response = await api('/api/surveys/nps/faculty/history', { blocking:false });
    state.npsFaculty = response.items || [];
    fillNpsFacultyFilters();
    renderFacultyNps();
  } catch (error) { toast('Erro ao carregar NPS dos docentes', error.message, 'error'); }
}

function fillNpsFacultyFilters() {
  const periods = sortedUnique((state.npsFaculty || []).map(row => row.periodo).filter(Boolean)).sort((a,b)=>periodStartKey(b)-periodStartKey(a));
  const p = $('#npsFacultyPeriodFilter'), w = $('#npsFacultyWindow');
  if (p) {
    if (state.npsFacultyFilters.periodo && !periods.includes(state.npsFacultyFilters.periodo)) state.npsFacultyFilters.periodo = '';
    p.innerHTML = option('', !state.npsFacultyFilters.periodo, 'Todos os semestres') + periods.map(v=>option(v, v===state.npsFacultyFilters.periodo, formatMonth(v,true))).join('');
  }
  if (w) w.value = state.npsFacultyFilters.window || '6';
}

function renderFacultyNps() {
  const summary = $('#npsFacultySummary');
  const table = $('#table-nps-faculty');
  if (!summary || !table) return;
  fillNpsFacultyFilters();
  const f = state.npsFacultyFilters;
  const history = [...(state.npsFaculty || [])].sort((a,b)=>periodStartKey(b.periodo)-periodStartKey(a.periodo));
  const filtered = history.filter(row => !f.periodo || row.periodo === f.periodo);
  const latest = filtered[0];
  const context = $('#npsFacultyContext');
  if (context) context.innerHTML = `<strong>Recorte:</strong> todos os docentes da instituição · ${escapeHtml(f.periodo ? formatMonth(f.periodo,true) : 'todo o histórico')} · gráfico ${escapeHtml(f.window==='all'?'todo histórico':`${f.window} semestres`)}`;

  if (!latest) {
    summary.innerHTML = npsSimpleCard('NPS da Instituição · Docentes','—','Nenhum NPS docente oficial no recorte','01C');
    renderLineChart($('#chartNpsFaculty'), [], {});
    renderBarChart($('#chartNpsFacultyComposition'), [], {});
  } else {
    const metric = npsAggregate([latest]);
    summary.innerHTML = [
      npsSimpleCard('NPS da Instituição · Docentes', latest.valor == null ? '—' : formatNumber(latest.valor,1), formatMonth(latest.periodo,true), '01C'),
      npsSimpleCard('Respondentes', formatNumber(latest.respondentes,0), 'docentes anônimos', 'Σ'),
      npsSimpleCard('Promotores', metric.promoterPct == null ? '—' : `${formatNumber(metric.promoterPct,1)}%`, `${formatNumber(latest.promotores,0)} resposta(s)`, '9–10'),
      npsSimpleCard('Detratores', metric.detractorPct == null ? '—' : `${formatNumber(metric.detractorPct,1)}%`, `${formatNumber(latest.detratores,0)} resposta(s)`, '0–6'),
    ].join('');
    const allowed = npsWindowPeriods(history, f.window, f.periodo);
    const trend = history.filter(row=>allowed.includes(row.periodo)).sort((a,b)=>periodStartKey(a.periodo)-periodStartKey(b.periodo));
    renderLineChart($('#chartNpsFaculty'), trend, { suffix:'', decimals:1, metric:'nps', unit:'pontos' });
    const composition = [
      { curso:'Promotores', valor:metric.promoterPct, respondentes:latest.promotores, compositionTone:'promoter' },
      { curso:'Neutros', valor:metric.neutralPct, respondentes:latest.neutros, compositionTone:'neutral' },
      { curso:'Detratores', valor:metric.detractorPct, respondentes:latest.detratores, compositionTone:'detractor' },
    ];
    renderBarChart($('#chartNpsFacultyComposition'), composition, { suffix:'%', decimals:1, unit:'%', clickFilter:false });
    const compositionTitle = $('#npsFacultyCompositionTitle'); if (compositionTitle) compositionTitle.textContent = `Composição · ${formatMonth(latest.periodo,true)}`;
  }

  const term = (state.npsFacultySearch || '').trim().toLowerCase();
  let rows = filtered;
  if (term) rows = rows.filter(row => Object.values(row).some(value => String(value ?? '').toLowerCase().includes(term)));
  rows.sort((a,b)=>periodStartKey(b.periodo)-periodStartKey(a.periodo));
  const page = paginate(rows,'nps-faculty');
  $('#count-nps-faculty').textContent = rows.length ? `${page.start+1}–${Math.min(rows.length,page.start+page.rows.length)} de ${rows.length}` : '0 registros';
  if (!rows.length) {
    table.innerHTML = '<div class="empty-table"><strong>Nenhum NPS docente encontrado</strong>Importe a Avaliação Institucional dos docentes pelo SEI ou por XLSX/ZIP. Questionários sem pergunta completa 0–10 serão preservados, mas não gerarão NPS.</div>';
    return;
  }
  table.innerHTML = `<table><thead><tr><th>Semestre</th><th>NPS</th><th>Respondentes</th><th>Promotores</th><th>Neutros</th><th>Detratores</th><th>Pergunta oficial</th><th>Fonte</th></tr></thead><tbody>${page.rows.map(row=>`<tr><td>${escapeHtml(formatMonth(row.periodo,true))}</td><td><strong>${row.valor==null?'—':formatNumber(row.valor,1)}</strong></td><td>${formatNumber(row.respondentes,0)}</td><td>${formatNumber(row.promotores,0)}</td><td>${formatNumber(row.neutros,0)}</td><td>${formatNumber(row.detratores,0)}</td><td><strong>${escapeHtml(row.question||'—')}</strong><br><small>${escapeHtml(row.questionnaire||row.title||'—')}</small></td><td>${escapeHtml(row.origin ? String(row.origin).toUpperCase() : row.fonte || 'SEI')}<br><small>${escapeHtml(row.source_filename||'—')}</small></td></tr>`).join('')}</tbody></table>`;
  attachPagination(table,'nps-faculty',rows.length,renderFacultyNps);
}

async function loadDataset(dataset, force = false) {
  if (dataset === 'avaliacao_docente') {
    try { await loadTeacherWorkspace(); }
    catch (error) { toast('Erro ao carregar avaliação docente', error.message, 'error'); }
    return;
  }
  if (dataset === 'resultados') {
    try {
      await Promise.all([loadResultSummary(force), loadResultTrend(force)]);
      renderResultTrend();
      if (state.resultView === 'resumo') renderResultSummaryTable();
      else await loadResultDetails();
    } catch (error) { toast('Erro ao carregar resultados', error.message, 'error'); }
    return;
  }
  if (state.data[dataset].length && !force) { if(dataset==='avaliacao_docente'){fillTeacherFilters();renderTeacherAnalysis();} renderDatasetTable(dataset); return; }
  try {
    const response = await api(`/api/dados/${dataset}`);
    state.data[dataset] = response.items;
    if(dataset==='nps') fillNpsCourseFilters();
    if(dataset==='avaliacao_docente'){ fillTeacherFilters(); renderTeacherAnalysis(); }
    renderDatasetTable(dataset);
  } catch (error) { toast('Erro ao carregar a base', error.message, 'error'); }
}

function renderDatasetTable(dataset) {
  if (dataset === 'avaliacao_docente') { renderTeacherTableServer(); return; }
  if (dataset === 'resultados') {
    if (state.resultView === 'resumo') renderResultSummaryTable();
    else renderResultDetailTable();
    return;
  }
  const term=(state.searches[dataset]||'').trim().toLowerCase();
  let items=state.data[dataset];
  if(dataset==='nps') items=npsCourseRowsForFilters();
  if(term)items=items.filter(item=>Object.values(item).some(value=>String(value??'').toLowerCase().includes(term)));
  const key=`data-${dataset}`;
  const page=paginate(items,key);
  const target=$(`#table-${dataset}`);
  $(`#count-${dataset}`).textContent=items.length?`${page.start+1}–${Math.min(items.length,page.start+page.rows.length)} de ${items.length}`:'0 registros';
  if(!items.length){target.innerHTML='<div class="empty-table"><strong>Nenhum registro encontrado</strong>Sincronize o NPS pelo SEI ou altere a busca.</div>';if(dataset==='nps')renderNpsCourseSummary();return;}
  const defs=columns[dataset]; const editable=canEditCurrentDirectorate() && dataset !== 'nps';
  target.innerHTML=`<table><thead><tr>${defs.map(c=>`<th class="${c[2]||''}">${escapeHtml(c[1])}</th>`).join('')}${editable?'<th class="actions">Ações</th>':''}</tr></thead><tbody>${page.rows.map(item=>`<tr>${defs.map(c=>{const raw=item[c[0]];const value=c[3]?c[3](raw):escapeHtml(raw||raw===0?raw:'—');return `<td class="${c[2]||''}">${value}</td>`;}).join('')}${editable?`<td class="actions"><button class="row-action" title="Editar" data-edit="${dataset}" data-id="${item.id}">✎</button><button class="row-action delete" title="Excluir" data-delete="${dataset}" data-id="${item.id}">×</button></td>`:''}</tr>`).join('')}</tbody></table>`;
  attachPagination(target,key,items.length,()=>renderDatasetTable(dataset));
  if(dataset==='nps')renderNpsCourseSummary();
  $$(`[data-edit="${dataset}"]`,target).forEach(btn=>btn.addEventListener('click',()=>openDataForm(dataset,Number(btn.dataset.id))));
  $$(`[data-delete="${dataset}"]`,target).forEach(btn=>btn.addEventListener('click',()=>deleteData(dataset,Number(btn.dataset.id))));
}

function formField(name, label, type = 'text', value = '', opts = {}) {
  const attrs = [`name="${name}"`, `id="field-${name}"`, `value="${escapeHtml(value ?? '')}"`, opts.required === false ? '' : 'required'];
  if (opts.min !== undefined) attrs.push(`min="${opts.min}"`);
  if (opts.max !== undefined) attrs.push(`max="${opts.max}"`);
  if (opts.step !== undefined) attrs.push(`step="${opts.step}"`);
  if (opts.placeholder) attrs.push(`placeholder="${escapeHtml(opts.placeholder)}"`);
  return `<label class="field ${opts.className || ''}" data-field-wrapper="${name}"><span>${escapeHtml(label)}</span><input type="${type}" ${attrs.join(' ')}>${opts.help ? `<small>${escapeHtml(opts.help)}</small>` : ''}<div class="field-error"></div></label>`;
}

function selectField(name, label, options, value = '', opts = {}) {
  return `<label class="field ${opts.className || ''}" data-field-wrapper="${name}"><span>${escapeHtml(label)}</span><select name="${name}" id="field-${name}" required>${opts.placeholder ? option('', !value, opts.placeholder) : ''}${options.map(v => option(v, v === value)).join('')}</select>${opts.help ? `<small>${escapeHtml(opts.help)}</small>` : ''}<div class="field-error"></div></label>`;
}

function datalistField(name, label, options, value = '', opts = {}) {
  const listId = `list-${name}-${Math.random().toString(36).slice(2,8)}`;
  return `<label class="field ${opts.className || ''}" data-field-wrapper="${name}"><span>${escapeHtml(label)}</span><input type="text" name="${name}" id="field-${name}" value="${escapeHtml(value || '')}" list="${listId}" ${opts.placeholder ? `placeholder="${escapeHtml(opts.placeholder)}"` : ''} required><datalist id="${listId}">${(options||[]).map(v=>`<option value="${escapeHtml(v)}"></option>`).join('')}</datalist>${opts.help ? `<small>${escapeHtml(opts.help)}</small>` : ''}<div class="field-error"></div></label>`;
}

function openModal(eyebrow, title, body) {
  $('#modalEyebrow').textContent = eyebrow;
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = body;
  $('#modalBackdrop').classList.remove('hidden');
  $('#modalBackdrop').setAttribute('aria-hidden', 'false');
  setTimeout(() => $('input, select, textarea', $('#modalBody'))?.focus(), 60);
}

function closeModal() {
  $('#modalBackdrop').classList.add('hidden');
  $('#modalBackdrop').setAttribute('aria-hidden', 'true');
  state.modalContext = null;
}

function openDataForm(dataset, id = null) {
  if (dataset === 'nps') { openNpsSeiImportForm('course'); return; }
  const record = id ? state.data[dataset].find(x => x.id === id) : {};
  const courses = state.bootstrap?.courses || [];
  const academicPrefix = ['DTNH','DCS'].includes(state.activeDirectorate) ? state.activeDirectorate : 'DTNH';
  const names = {
    avaliacao_docente: ['avaliação docente', `${academicPrefix}-02 · KPI`],
    resultados: ['resultado acadêmico', `${academicPrefix}-03 · KPI`],
  };
  let fields = '';
  if (dataset === 'avaliacao_docente') {
    const disciplines = record.curso ? (state.bootstrap?.disciplines?.[record.curso] || []) : Object.values(state.bootstrap?.disciplines || {}).flat();
    fields = academicSemesterFields('periodo', record.periodo || currentAcademicSemester()) +
      datalistField('curso','Curso',courses,record.curso||'',{placeholder:'Digite ou selecione',help:'Cursos novos são cadastrados automaticamente.'}) +
      datalistField('disciplina','Disciplina',disciplines,record.disciplina||'',{placeholder:'Digite ou selecione',help:'Disciplinas novas também são cadastradas.'}) +
      formField('professor','Professor', 'text',record.professor||'',{placeholder:'Nome do docente'}) +
      formField('respondentes','Respondentes','number',record.respondentes??'',{min:1}) +
      formField('nota_media','Nota média (0–10)','number',record.nota_media??'',{min:0,max:10,step:'0.01'});
  } else {
    const disciplines = record.curso ? (state.bootstrap?.disciplines?.[record.curso] || []) : Object.values(state.bootstrap?.disciplines || {}).flat();
    fields = academicSemesterFields('periodo', record.periodo || currentAcademicSemester()) +
      datalistField('curso','Curso',courses,record.curso||'',{placeholder:'Digite ou selecione',help:'O curso será cadastrado se ainda não existir.'}) +
      datalistField('disciplina','Disciplina',disciplines,record.disciplina||'',{placeholder:'Digite ou selecione'}) +
      formField('turma','Turma','text',record.turma||'',{placeholder:'Ex.: ADM6NA'}) +
      formField('matricula','Matrícula','text',record.matricula||'') +
      formField('aluno','Aluno','text',record.aluno||'') +
      formField('media','Média final','number',record.media??'',{min:0,max:10,step:'0.01',required:false}) +
      formField('situacao','Situação oficial','text',record.situacao||'',{placeholder:'Aprovado, Reprovado, Reprovado Falta, Cursando…',help:'A situação é a fonte oficial; o sistema não recalcula aprovação pela média.',className:'span-2'});
  }
  openModal(names[dataset][1], id ? `Editar ${names[dataset][0]}` : `Novo lançamento de ${names[dataset][0]}`, `<form id="dataForm" class="form-grid">${fields}<div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelDataForm">Cancelar</button><button type="submit" class="button primary">${id ? 'Salvar alterações' : 'Salvar no banco'}</button></div></form>`);
  state.modalContext = { type: 'data', dataset, id };
  $('#cancelDataForm').addEventListener('click', closeModal);
  $('#dataForm').addEventListener('submit', submitDataForm);
}

async function submitDataForm(event) {
  event.preventDefault();
  const { dataset, id } = state.modalContext;
  const form = event.currentTarget;
  clearFormErrors(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  if (form.elements.periodo_year && form.elements.periodo_semester) {
    payload.periodo = academicSemesterFromForm(form, 'periodo');
    delete payload.periodo_year;
    delete payload.periodo_semester;
  }
  ['respondentes', 'promotores', 'neutros', 'detratores', 'nota_media', 'media'].forEach(key => {
    if (payload[key] !== undefined && payload[key] !== '') payload[key] = Number(payload[key]);
  });
  setSaveState('saving', 'Salvando no banco…');
  try {
    await api(id ? `/api/dados/${dataset}/${id}` : `/api/dados/${dataset}`, {
      method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), loadingTitle: id ? 'Atualizando KPI' : 'Registrando KPI', loadingMessage: 'Validando e gravando os dados no banco oficial.'
    });
    closeModal();
    state.data[dataset] = [];
    await loadDataset(dataset, true);
    if (['nps','avaliacao_docente','resultados'].includes(dataset)) await refreshBootstrapAfterCatalogChange();
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast(id ? 'Registro atualizado' : 'Registro adicionado', 'A alteração foi gravada no banco de dados.');
  } catch (error) {
    setSaveState('error', 'Falha ao salvar');
    showFormErrors(form, error.fields);
    toast('Não foi possível salvar', error.message, 'error');
  }
}

function clearFormErrors(form) {
  $$('.field', form).forEach(el => { el.classList.remove('has-error'); $('.field-error', el).textContent = ''; });
}
function showFormErrors(form, errors = {}) {
  Object.entries(errors).forEach(([field, message]) => {
    const wrapper = $(`[data-field-wrapper="${field}"]`, form);
    if (wrapper) { wrapper.classList.add('has-error'); $('.field-error', wrapper).textContent = message; return; }
    if (field === 'periodo' && form.elements.periodo_year && form.elements.periodo_semester) {
      ['periodo_year','periodo_semester'].forEach(name => {
        const academicWrapper = $(`[data-field-wrapper="${name}"]`, form);
        if (academicWrapper) { academicWrapper.classList.add('has-error'); $('.field-error', academicWrapper).textContent = message; }
      });
    }
  });
}

function confirmDialog(text) {
  return new Promise(resolve => {
    $('#confirmText').textContent = text;
    $('#confirmBackdrop').classList.remove('hidden');
    const finish = value => {
      $('#confirmBackdrop').classList.add('hidden');
      $('#confirmOk').onclick = null;
      $('#confirmCancel').onclick = null;
      resolve(value);
    };
    $('#confirmOk').onclick = () => finish(true);
    $('#confirmCancel').onclick = () => finish(false);
  });
}

async function deleteData(dataset, id) {
  const item = state.data[dataset].find(x => x.id === id);
  const label = item ? `${item.periodo} · ${item.curso}${item.disciplina ? ` · ${item.disciplina}` : ''}` : 'este registro';
  if (!await confirmDialog(`Deseja excluir ${label}? A exclusão será registrada no log de auditoria.`)) return;
  setSaveState('saving', 'Excluindo do banco…');
  try {
    await api(`/api/dados/${dataset}/${id}`, { method: 'DELETE', loadingTitle: 'Excluindo registro', loadingMessage: 'Registrando a exclusão no banco e no log de auditoria.' });
    state.data[dataset] = [];
    await loadDataset(dataset, true);
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast('Registro excluído', 'A exclusão foi registrada no log de auditoria.');
  } catch (error) {
    setSaveState('error', 'Falha ao excluir');
    toast('Não foi possível excluir', error.message, 'error');
  }
}

function openImportForm(dataset) {
  const isDisciplineCatalog = dataset === 'disciplinas';
  const label = isDisciplineCatalog ? 'Disciplinas' : state.bootstrap.datasets[dataset].label;
  const duplicateHelp = isDisciplineCatalog
    ? 'A atualização usa a chave Curso + Disciplina e pode alterar status e vigências.'
    : dataset === 'resultados'
      ? 'Duplicatas são identificadas por semestre + aluno + curso + disciplina + turma. Resultados diferentes do mesmo aluno são preservados. O arquivo pode ser o modelo do Data UNIVC ou o XLSX bruto do Mapa de Nota do SEI.'
      : dataset === 'avaliacao_docente'
        ? 'Duplicatas são identificadas por semestre + curso + disciplina + professor.'
        : 'A atualização usa a chave de período e curso.';
  const extraHelp = isDisciplineCatalog
    ? '<div class="tip-box"><strong>Pré-requisito:</strong> os cursos informados precisam estar cadastrados. O recorte para METAS é derivado como <b>Curso » Disciplina</b>.</div>'
    : ['resultados','avaliacao_docente','nps'].includes(dataset)
      ? '<div class="tip-box"><strong>Catálogo automático:</strong> cursos e disciplinas que ainda não existirem serão criados a partir das linhas válidas.</div>'
      : '';
  openModal('Importação em lote', `Importar ${label}`, `<form id="importForm">
    <div class="tip-box"><strong>Use o modelo do sistema.</strong> A primeira linha deve manter os cabeçalhos originais. Todas as linhas serão validadas antes da gravação.</div>
    ${extraHelp}
    <div class="form-grid">
      <label class="field span-2"><span>Arquivo Excel (.xlsx)</span><input type="file" name="arquivo" accept=".xlsx,.xlsm" required><div class="field-error"></div></label>
      <label class="field span-2"><span>Como tratar registros já existentes</span><select name="modo"><option value="add">Ignorar duplicados e adicionar apenas novos</option><option value="update">Atualizar duplicados e adicionar novos</option></select><small>${duplicateHelp}</small></label>
    </div>
    <div id="importResult"></div>
    <div class="modal-form-footer"><a class="button secondary" href="/api/modelos/${dataset}" download>Baixar modelo</a><button type="button" class="button secondary" id="cancelImport">Cancelar</button><button type="submit" class="button primary">Validar e importar</button></div>
  </form>`);
  state.modalContext = { type: 'import', dataset };
  $('#cancelImport').addEventListener('click', closeModal);
  $('#importForm').addEventListener('submit', submitImport);
}

async function submitImport(event) {
  event.preventDefault(); const dataset=state.modalContext.dataset; const form=event.currentTarget; const fd=new FormData(form); const file=fd.get('arquivo'); if(!file||!file.name)return; const mode=fd.get('modo');
  setSaveState('saving','Importando para o banco…');
  try {
    const result=await api(`/api/importar/${dataset}?modo=${mode}`,{method:'POST',body:fd,loadingTitle:'Importando planilha',loadingMessage:'Validando as linhas e gravando os registros aprovados.'});
    const errors=result.erros||[]; $('#importResult').innerHTML=`<div class="import-result"><strong>Importação concluída</strong><div>${result.inseridos} inserido(s), ${result.atualizados} atualizado(s), ${result.ignorados} duplicado(s) ignorado(s).</div>${errors.length?`<ul>${errors.slice(0,12).map(e=>`<li>Linha ${e.linha}: ${escapeHtml(Object.values(e.campos||{}).join(' ')||e.mensagem)}</li>`).join('')}</ul>`:''}</div>`;
    if(dataset==='disciplinas'){state.catalogs={cursos:[],disciplinas:[]};await refreshBootstrapAfterCatalogChange();await loadCatalogs(true);}
    else {state.data[dataset]=[];await loadDataset(dataset,true);if(['nps','avaliacao_docente','resultados'].includes(dataset))await refreshBootstrapAfterCatalogChange();}
    await loadDashboard();setSaveState('ok','Banco sincronizado');toast('Importação processada',errors.length?`${errors.length} linha(s) precisam de correção.`:'Todas as linhas foram processadas.',errors.length?'warning':'success');
  } catch(error){setSaveState('error','Falha na importação');toast('Não foi possível importar',error.message,'error');}
}


function openSeiImportForm() {
  if (!canEditCurrentDirectorate()) { toast('Somente leitura','A sincronização com o SEI só pode ser executada na diretoria principal.','warning'); return; }
  const available=state.bootstrap?.sei_courses || [];
  const courseChecks=available.length
    ? `<div class="sei-course-grid">${available.map(course=>`<label class="sei-course-option"><input type="checkbox" name="curso_sei" value="${escapeHtml(course)}" checked><span class="sei-course-check">✓</span><span class="sei-course-copy"><strong>${escapeHtml(course)}</strong><small>Incluir na consulta ao SEI</small></span></label>`).join('')}</div>`
    : '<div class="tip-box">Nenhum curso padrão foi configurado para esta diretoria.</div>';
  const help=state.activeDirectorate==='DTNH'
    ? 'Os 9 cursos do DTNH já aparecem selecionados. Desmarque os que não deseja consultar ou mantenha todos.'
    : 'Os 8 cursos da DCS já aparecem selecionados. Desmarque os que não deseja consultar ou mantenha todos.';
  const now=new Date();
  const currentSemester=now.getMonth()<6?'1':'2';
  openModal('Integração SEI', 'Buscar notas diretamente no SEI', `<form id="seiImportForm" class="form-grid">
    <div class="tip-box span-2"><strong>Protótipo controlado.</strong> O Data UNIVC usa as credenciais somente durante esta operação. Senha, JSESSIONID e ViewState não são gravados.</div>
    ${formField('usuario','Usuário do SEI','text','')}
    ${formField('senha','Senha do SEI','password','')}
    ${formField('ano','Ano','number',new Date().getFullYear(),{min:2020,max:2100})}
    ${selectField('semestre','Semestre',['1','2'],currentSemester)}
    <div class="field span-2"><span>Cursos a consultar</span><div class="sei-course-actions"><button type="button" class="button subtle compact" id="selectAllSeiCourses">Selecionar todos</button><button type="button" class="button subtle compact" id="clearSeiCourses">Limpar seleção</button></div>${courseChecks}<small>${escapeHtml(help)} Cursos, disciplinas e alunos ainda inexistentes serão cadastrados automaticamente.</small><div class="field-error"></div></div>
    <div class="tip-box span-2"><strong>Integridade:</strong> cada vínculo aluno-disciplina é importado separadamente. Só uma duplicata exata do mesmo semestre, curso, disciplina, turma e matrícula é ignorada.</div>
    <div id="seiImportResult" class="span-2"></div>
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelSeiImport">Cancelar</button><button type="submit" class="button primary">Consultar e importar</button></div>
  </form>`);
  state.modalContext={type:'sei-import'};
  $('#cancelSeiImport').addEventListener('click',closeModal);
  $('#selectAllSeiCourses')?.addEventListener('click',()=>$$('input[name="curso_sei"]',$('#seiImportForm')).forEach(input=>input.checked=true));
  $('#clearSeiCourses')?.addEventListener('click',()=>$$('input[name="curso_sei"]',$('#seiImportForm')).forEach(input=>input.checked=false));
  $('#seiImportForm').addEventListener('submit',submitSeiImport);
}

async function submitSeiImport(event) {
  event.preventDefault();
  const form=event.currentTarget; clearFormErrors(form);
  const raw=Object.fromEntries(new FormData(form).entries());
  const courses=$$('input[name="curso_sei"]:checked',form).map(input=>input.value);
  if(!courses.length){toast('Selecione pelo menos um curso','Marque um ou mais cursos antes de consultar o SEI.','warning');return;}
  const payload={usuario:raw.usuario,senha:raw.senha,ano:String(raw.ano||''),semestre:String(raw.semestre||''),cursos:courses};
  setSaveState('saving','Consultando o SEI…');
  try {
    const result=await api('/api/sei/importar-resultados',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),loadingTitle:'Consultando o SEI',loadingMessage:`Autenticando e processando ${courses.length} curso(s). Cada resultado aluno-disciplina será validado separadamente.`});
    const failures=result.falhas_sei||[]; const errors=result.erros||[]; const reports=result.relatorios_importados||[];
    const read=reports.reduce((sum,item)=>sum+Number(item.registros_lidos||0),0);
    const reportDetails=reports.length?`<ul class="sei-sync-details">${reports.map(item=>{const periodo=(item.ano_xlsx&&item.semestre_xlsx)?`${item.ano_xlsx}/${item.semestre_xlsx}`:'período não identificado';return `<li><strong>${escapeHtml(item.curso)}</strong> → XLSX: ${escapeHtml(item.curso_sei_xlsx||'curso não informado')} · período ${escapeHtml(periodo)} · ${Number(item.registros_lidos||0)} registro(s) · identidade ${item.identidade_validada?'validada':'não validada'} por ${escapeHtml(item.identidade_validada_por||'campo Curso:')}</li>`}).join('')}</ul>`:'';
    $('#seiImportResult').innerHTML=`<div class="import-result"><strong>Sincronização processada</strong><div>Build Data UNIVC: <strong>${escapeHtml(result.versao||'não informado')}</strong> · fingerprint <code>${escapeHtml(result.build||'não informado')}</code></div><div>Política Educação Física: <code>${escapeHtml(result.educacao_fisica_policy||'não informada')}</code></div><div>${read} registro(s) lido(s) nos relatórios.</div><div>${result.inseridos||0} novo(s), ${result.ignorados||0} duplicado(s) exato(s) ignorado(s), ${result.atualizados||0} atualizado(s).</div><div>${reports.length} relatório(s) do SEI importado(s).</div>${reportDetails}${failures.length?`<ul>${failures.slice(0,10).map(x=>`<li>${escapeHtml(x.curso)}: ${escapeHtml(x.erro)}</li>`).join('')}</ul>`:''}${errors.length?`<small>${errors.length} linha(s) não puderam ser gravadas. Consulte o resumo para identificar a causa.</small>`:''}</div>`;
    state.data.resultados=[]; await loadDataset('resultados',true); await refreshBootstrapAfterCatalogChange(); fillResultFilters(); await loadDashboard();
    setSaveState('ok','Banco sincronizado'); toast('Importação do SEI concluída',failures.length?'Parte dos cursos apresentou falha; confira o resumo.':'Todos os relatórios disponíveis foram processados.',failures.length?'warning':'success');
    $('#field-senha').value='';
  } catch(error) { setSaveState('error','Falha na integração'); showFormErrors(form,error.fields); toast('Não foi possível consultar o SEI',error.message,'error'); }
}


function surveyFilterSelect(name, label, options = [], selected = '', help = '') {
  const normalized = Array.isArray(options) ? options : [];
  const opts = normalized.length
    ? normalized.map(item => `<option value="${escapeHtml(item.value)}" ${String(item.value)===String(selected)?'selected':''}>${escapeHtml(item.label || item.value)}</option>`).join('')
    : `<option value="${escapeHtml(selected || '')}" selected>${escapeHtml(selected || 'Padrão do SEI')}</option>`;
  return `<label class="field"><span>${escapeHtml(label)}</span><select name="${escapeHtml(name)}" id="survey-${escapeHtml(name)}">${opts}</select>${help?`<small>${escapeHtml(help)}</small>`:''}</label>`;
}

function npsSurveyContext() {
  return state.modalContext?.type === 'nps-sei' ? state.modalContext : null;
}

function npsScopeCopy(scope) {
  if (scope === 'faculty') return {
    scope:'faculty', short:'Docentes', title:'NPS da Instituição · Docentes',
    action:'Atualizar NPS da Instituição pelos docentes',
    description:'a pergunta oficial 0–10 respondida anonimamente pelos docentes sobre recomendar a UNIVC / a instituição',
    bindHelp:'Escolha a pergunta 0–10 de recomendação institucional respondida pelos docentes. O resultado será único para toda a população docente do semestre, sem curso.',
    keyword:'docente',
  };
  if (scope === 'institution') return {
    scope:'institution', short:'Instituição', title:'NPS da Instituição · Alunos',
    action:'Atualizar NPS da Instituição pelos alunos via SEI',
    description:'a pergunta oficial 0–10 dos alunos sobre recomendar o UNIVC / a instituição',
    bindHelp:'Escolha a pergunta 0–10 que mede a recomendação do UNIVC pelos alunos. Somente esta pergunta será vinculada nesta área.',
    keyword:'aluno',
  };
  return {
    scope:'course', short:'Curso', title:'NPS do Curso',
    action:'Atualizar NPS dos Cursos pelo SEI',
    description:'a pergunta oficial 0–10 dos alunos sobre recomendar o próprio curso',
    bindHelp:'Escolha a pergunta 0–10 que mede a recomendação do próprio curso. O resultado será calculado separadamente para cada curso.',
    keyword:'aluno',
  };
}

function openNpsSeiImportForm(scope) {
  const copy=npsScopeCopy(scope);
  if (!canEditCurrentDirectorate()) {
    toast('Somente leitura',`A atualização do ${copy.title} pelo SEI só pode ser executada na diretoria principal.`,'warning');
    return;
  }
  if (!['DTNH','DCS'].includes(state.activeDirectorate)) {
    toast('Diretoria não acadêmica','Os indicadores NPS acadêmicos via Avaliação Institucional estão disponíveis em DTNH e DCS.','warning');
    return;
  }
  openModal('Avaliações SEI', copy.action, `<div id="npsSeiFlow"></div>`);
  state.modalContext = {
    type:'nps-sei', npsScope:copy.scope, sessionToken:null, searchResults:[], metadata:null,
    inspection:null, importResult:null, selectedEvaluation:null,
  };
  renderNpsSeiLoginStep();
}

function renderNpsSeiLoginStep() {
  const root=$('#npsSeiFlow'); const ctx=npsSurveyContext(); if(!root||!ctx) return; const copy=npsScopeCopy(ctx.npsScope);
  root.innerHTML=`<form id="npsSeiLoginForm" class="form-grid">
    <div class="tip-box span-2"><strong>Fonte oficial · ${escapeHtml(copy.title)}.</strong> O Data UNIVC abre o relatório de Avaliação Institucional, baixa XLSX/ZIP e usa ${escapeHtml(copy.description)} para formar promotores, neutros e detratores. Senha, JSESSIONID e ViewState ficam somente em memória durante esta sessão.</div>
    ${formField('survey_usuario','Usuário do SEI','text','')}
    ${formField('survey_senha','Senha do SEI','password','')}
    ${formField('survey_keyword','Palavra-chave da avaliação','text',copy.keyword,{className:'span-2',help:'Use uma palavra do nome da avaliação. Você poderá escolher o resultado correto antes de gerar o relatório.'})}
    <div class="modal-form-footer span-2"><button type="button" class="button subtle" id="surveyUploadFallback">Usar XLSX/ZIP já baixado</button><button type="button" class="button secondary" id="cancelNpsSei">Cancelar</button><button type="submit" class="button primary">Conectar e buscar avaliações</button></div>
  </form>`;
  $('#cancelNpsSei')?.addEventListener('click',closeModal);
  $('#surveyUploadFallback')?.addEventListener('click',renderNpsSurveyUploadStep);
  $('#npsSeiLoginForm')?.addEventListener('submit',async event=>{
    event.preventDefault(); const form=event.currentTarget; clearFormErrors(form);
    const values=Object.fromEntries(new FormData(form).entries());
    try {
      const login=await api('/api/surveys/sei/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:values.survey_usuario,password:values.survey_senha}),loadingTitle:'Conectando ao SEI',loadingMessage:'Criando uma sessão temporária e protegida para a Avaliação Institucional.'});
      const ctx=npsSurveyContext(); if(!ctx) return;
      ctx.sessionToken=login.session_token;
      $('#field-survey_senha').value='';
      const search=await api('/api/surveys/sei/evaluations/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_token:ctx.sessionToken,keyword:values.survey_keyword||''}),loadingTitle:'Buscando avaliações',loadingMessage:'Consultando as avaliações disponíveis no SEI.'});
      ctx.searchResults=search.results||[];
      renderNpsSeiEvaluationStep();
    } catch(error){ setSaveState('error','Falha na integração'); toast('Não foi possível acessar as avaliações do SEI',error.message,'error'); }
  });
}

function renderNpsSurveyUploadStep() {
  const ctx=npsSurveyContext(); const root=$('#npsSeiFlow'); if(!ctx||!root)return; const copy=npsScopeCopy(ctx.npsScope);
  root.innerHTML=`<form id="npsSurveyUploadForm" class="form-grid">
    <div class="tip-box span-2"><strong>Contingência · ${escapeHtml(copy.title)}.</strong> Envie o XLSX ou ZIP gerado pelo relatório de Avaliação Institucional. O arquivo percorre o mesmo parser e, ao final, você vincula somente ${escapeHtml(copy.description)}.</div>
    <label class="field span-2"><span>Relatório do SEI</span><input type="file" id="surveyFallbackFile" name="file" accept=".xlsx,.zip" required><small>O arquivo bruto será normalizado antes de alimentar o indicador.</small></label>
    ${academicSemesterFields('survey_fallback_semester', currentAcademicSemester(), {help:'Período lógico usado no histórico do Data UNIVC.'})}
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="surveyFallbackBack">Voltar</button><button type="submit" class="button primary">Analisar arquivo</button></div>
  </form>`;
  $('#surveyFallbackBack')?.addEventListener('click',renderNpsSeiLoginStep);
  $('#npsSurveyUploadForm')?.addEventListener('submit',async event=>{
    event.preventDefault(); const file=$('#surveyFallbackFile')?.files?.[0];
    if(!file){toast('Selecione um arquivo','Envie o XLSX ou ZIP do relatório do SEI.','warning');return;}
    const body=new FormData(); body.append('file',file);
    try {
      ctx.requestedSemester=academicSemesterFromForm(event.currentTarget,'survey_fallback_semester')||currentAcademicSemester();
      const inspectEndpoint=copy.scope==='faculty'?'/api/surveys/faculty-institution/import/inspect':'/api/surveys/import/inspect';
      ctx.inspection=await api(inspectEndpoint,{method:'POST',body,loadingTitle:'Analisando relatório',loadingMessage:copy.scope==='faculty'?'Validando o XLSX/ZIP institucional dos docentes e identificando os questionários disponíveis.':'Validando o XLSX/ZIP e identificando os blocos de curso do SEI.'});
      renderNpsSeiInspectionStep();
    } catch(error){toast('Não foi possível analisar o relatório',error.message,'error');}
  });
}

function renderNpsSeiEvaluationStep() {
  const ctx=npsSurveyContext(); const root=$('#npsSeiFlow'); if(!ctx||!root) return;
  const rows=ctx.searchResults||[];
  root.innerHTML=`<div class="form-grid">
    <div class="tip-box span-2"><strong>1. Escolha a aplicação correta.</strong> Avaliação e questionário são entidades diferentes no SEI. Primeiro selecione a aplicação/período; no passo seguinte você escolherá o questionário.</div>
    <div class="field span-2"><span>Avaliações encontradas</span>${rows.length?`<div class="sei-course-grid">${rows.map((item,index)=>`<label class="sei-course-option"><input type="radio" name="survey_evaluation" value="${escapeHtml(item.source)}" ${index===0?'checked':''}><span class="sei-course-check">✓</span><span class="sei-course-copy"><strong>${escapeHtml(item.name||'Avaliação')}</strong><small>${escapeHtml([item.start_date&&`Início ${item.start_date}`,item.end_date&&`Fim ${item.end_date}`,item.target&&`Público: ${item.target}`,item.status].filter(Boolean).join(' · ')||'Sem metadados adicionais')}</small></span></label>`).join('')}</div>`:'<div class="warning-box">Nenhuma avaliação foi encontrada. Volte e tente outra palavra-chave.</div>'}</div>
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="surveyBackLogin">Voltar</button>${rows.length?'<button type="button" class="button primary" id="surveySelectEvaluation">Selecionar avaliação</button>':''}</div>
  </div>`;
  $('#surveyBackLogin')?.addEventListener('click',renderNpsSeiLoginStep);
  $('#surveySelectEvaluation')?.addEventListener('click',async()=>{
    const source=$('input[name="survey_evaluation"]:checked',root)?.value;
    if(!source){toast('Escolha uma avaliação','Selecione uma linha antes de continuar.','warning');return;}
    try {
      const metadata=await api('/api/surveys/sei/evaluations/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_token:ctx.sessionToken,source}),loadingTitle:'Abrindo avaliação',loadingMessage:'Descobrindo questionários e filtros disponíveis no SEI.'});
      ctx.metadata=metadata; ctx.selectedEvaluation=(ctx.searchResults||[]).find(item=>item.source===source)||null;
      renderNpsSeiQuestionnaireStep();
    } catch(error){toast('Não foi possível abrir a avaliação',error.message,'error');}
  });
}

function renderNpsSeiQuestionnaireStep() {
  const ctx=npsSurveyContext(); const root=$('#npsSeiFlow'); const m=ctx?.metadata; if(!ctx||!root||!m) return; const copy=npsScopeCopy(ctx.npsScope);
  const questionnaires=m.questionnaires||[];
  const qOptions=questionnaires.map(item=>`<option value="${escapeHtml(item.sei_id)}" ${String(item.sei_id)===String(m.selected_questionnaire_id)?'selected':''}>${escapeHtml(item.name)}</option>`).join('');
  root.innerHTML=`<form id="npsSeiQuestionnaireForm" class="form-grid">
    <div class="tip-box span-2"><strong>${escapeHtml(m.evaluation_name||'Avaliação selecionada')}</strong><br>${escapeHtml([m.start_date&&`Início ${m.start_date}`,m.end_date&&`Fim ${m.end_date}`,m.target&&`Público ${m.target}`,m.status].filter(Boolean).join(' · '))}</div>
    <label class="field span-2"><span>Questionário</span><select id="survey-questionnaire" name="questionnaire_id" required>${qOptions}</select><small>Escolha o questionário que contém ${escapeHtml(copy.description)}.</small></label>
    ${surveyFilterSelect('detail','Nível de detalhamento',m.detail_options,m.detail_value,'O Data UNIVC usa os valores realmente encontrados no SEI; nenhum j_idt é fixado.')}
    ${surveyFilterSelect('unit','Unidade de ensino',m.unit_options,m.unit_value)}
    ${surveyFilterSelect('turn','Turno',m.turn_options,m.turn_value)}
    ${academicSemesterFields('survey_semester', currentAcademicSemester(), {help:'Poderá ser ajustado depois da leitura do relatório.'})}
    <div class="tip-box span-2"><strong>Próximo passo:</strong> o Data UNIVC preservará o questionário completo, mas nesta área você vinculará somente ${escapeHtml(copy.title)}.</div>
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="surveyBackEvaluation">Voltar</button><button type="submit" class="button primary">Gerar e analisar relatório</button></div>
  </form>`;
  $('#surveyBackEvaluation')?.addEventListener('click',renderNpsSeiEvaluationStep);
  $('#npsSeiQuestionnaireForm')?.addEventListener('submit',async event=>{
    event.preventDefault();
    const qid=$('#survey-questionnaire')?.value; const semester=academicSemesterFromForm(event.currentTarget,'survey_semester');
    if(!qid){toast('Escolha um questionário','O SEI não retornou um questionário selecionável.','warning');return;}
    try {
      ctx.requestedSemester=semester;
      ctx.metadata=await api('/api/surveys/sei/report/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_token:ctx.sessionToken,detail_value:$('#survey-detail')?.value||null,unit_value:$('#survey-unit')?.value||null,turn_value:$('#survey-turn')?.value||null}),loadingTitle:'Configurando relatório',loadingMessage:'Aplicando nível de detalhamento, unidade e turno no relatório do SEI.'});
      ctx.metadata=await api('/api/surveys/sei/questionnaire/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_token:ctx.sessionToken,questionnaire_id:qid}),loadingTitle:'Preparando questionário',loadingMessage:'Selecionando as perguntas no SEI e validando o total selecionado.'});
      const generateEndpoint=copy.scope==='faculty'?'/api/surveys/faculty-institution/sei/report/generate':'/api/surveys/sei/report/generate';
      ctx.inspection=await api(generateEndpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_token:ctx.sessionToken}),loadingTitle:'Gerando relatório no SEI',loadingMessage:'O SEI está processando o relatório. O Data UNIVC acompanha o polling até o XLSX/ZIP ficar disponível.'});
      renderNpsSeiInspectionStep();
    } catch(error){toast('Não foi possível gerar o relatório',error.message,'error');}
  });
}

function renderNpsSeiInspectionStep() {
  const ctx=npsSurveyContext(); const root=$('#npsSeiFlow'); const inspection=ctx?.inspection; if(!ctx||!root||!inspection) return;
  const copy=npsScopeCopy(ctx.npsScope);
  const entries=inspection.entries||[];
  const suggested=(inspection.semester_suggestions||[])[0];
  let semester=ctx.requestedSemester||suggested||currentAcademicSemester();
  if(suggested && (!ctx.requestedSemester || ctx.requestedSemester===currentAcademicSemester())) semester=suggested.replace('.1','-SEM1').replace('.2','-SEM2');

  if(copy.scope==='faculty') {
    root.innerHTML=`<form id="npsSurveyImportForm" class="form-grid">
      <div class="tip-box span-2"><strong>Relatório docente recebido: ${escapeHtml(inspection.filename||'arquivo')}</strong><br>${entries.length} relatório(s) institucional(is) encontrado(s). Como os docentes são anônimos e o SEI não informa curso, todos os relatórios selecionados serão tratados como uma única população institucional no semestre.</div>
      ${academicSemesterFields('survey_import_semester', semester, {help:'Todos os arquivos selecionados precisam representar o mesmo semestre.'})}
      <div class="field span-2"><span>Relatórios encontrados</span><div class="sei-course-actions"><button type="button" class="button subtle compact" id="surveySelectMapped">Selecionar todos</button><button type="button" class="button subtle compact" id="surveyClearEntries">Limpar</button></div><div class="sei-course-grid">${entries.map(entry=>`<label class="sei-course-option"><input type="checkbox" name="survey_path" value="${escapeHtml(entry.internal_path)}" checked><span class="sei-course-check">✓</span><span class="sei-course-copy"><strong>${escapeHtml(entry.survey_title||entry.questionnaire_name||entry.internal_path)}</strong><small>${escapeHtml(entry.questionnaire_name||'Questionário institucional')} · ${formatNumber(entry.respondent_count||0,0)} respondente(s) estimado(s) · ${formatNumber(entry.question_count||0,0)} pergunta(s) · ${formatNumber(entry.nps_candidate_count||0,0)} candidata(s) 0–10</small></span></label>`).join('')}</div><small>Nenhum vínculo com curso, disciplina ou professor será criado. A fonte permanece anônima.</small></div>
      <div id="npsSurveyImportResult" class="span-2"></div>
      <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="surveyBackQuestionnaire">Voltar</button><button type="submit" class="button primary">Importar todos selecionados</button></div>
    </form>`;
  } else {
    root.innerHTML=`<form id="npsSurveyImportForm" class="form-grid">
      <div class="tip-box span-2"><strong>Relatório recebido: ${escapeHtml(inspection.filename||'arquivo')}</strong><br>${entries.length} bloco(s) de curso encontrados. Marque somente os cursos desta diretoria que devem alimentar o Data UNIVC.</div>
      ${academicSemesterFields('survey_import_semester', semester, {help:'Este é o período lógico usado no histórico do Data UNIVC.'})}
      <div class="field span-2"><span>Cursos encontrados no relatório</span><div class="sei-course-actions"><button type="button" class="button subtle compact" id="surveySelectMapped">Selecionar mapeados</button><button type="button" class="button subtle compact" id="surveyClearEntries">Limpar</button></div><div class="sei-course-grid">${entries.map((entry,index)=>{const match=entry.course_match||{}; const checked=match.matched?'checked':''; const disabled=match.matched?'':'disabled'; const mapped=match.matched?`→ ${match.course_name}`:`Não mapeado: ${match.reason||'curso fora do catálogo'}`; return `<label class="sei-course-option ${match.matched?'':'survey-unmapped'}"><input type="checkbox" name="survey_path" value="${escapeHtml(entry.internal_path)}" ${checked} ${disabled}><span class="sei-course-check">✓</span><span class="sei-course-copy"><strong>${escapeHtml(entry.course_name||entry.internal_path)}</strong><small>${escapeHtml(mapped)} · ${escapeHtml(entry.respondent_count??0)} respondente(s) estimado(s)</small></span></label>`;}).join('')}</div><small>Cursos não mapeados não são criados silenciosamente; primeiro devem existir no catálogo acadêmico correto.</small></div>
      <div id="npsSurveyImportResult" class="span-2"></div>
      <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="surveyBackQuestionnaire">Voltar</button><button type="submit" class="button primary">Importar no Data UNIVC</button></div>
    </form>`;
  }
  $('#surveySelectMapped')?.addEventListener('click',()=>$$('input[name="survey_path"]:not(:disabled)',root).forEach(input=>input.checked=true));
  $('#surveyClearEntries')?.addEventListener('click',()=>$$('input[name="survey_path"]',root).forEach(input=>input.checked=false));
  $('#surveyBackQuestionnaire')?.addEventListener('click', ctx.sessionToken ? renderNpsSeiQuestionnaireStep : renderNpsSurveyUploadStep);
  $('#npsSurveyImportForm')?.addEventListener('submit',async event=>{
    event.preventDefault(); const paths=$$('input[name="survey_path"]:checked',root).map(input=>input.value);
    const sem=academicSemesterFromForm(event.currentTarget,'survey_import_semester');
    if(!paths.length){toast(copy.scope==='faculty'?'Selecione ao menos um relatório':'Selecione ao menos um curso',copy.scope==='faculty'?'Escolha um ou mais relatórios institucionais dos docentes.':'Somente cursos mapeados podem ser importados.','warning');return;}
    try {
      const processEndpoint=copy.scope==='faculty'?'/api/surveys/faculty-institution/import/process':'/api/surveys/import/process';
      ctx.importResult=await api(processEndpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:inspection.token,selected_paths:paths,semester_override:sem}),loadingTitle:'Importando questionário',loadingMessage:copy.scope==='faculty'?'Salvando o questionário docente institucional sem identificar pessoas ou cursos.':'Salvando o relatório normalizado e preservando as distribuições originais do SEI.'});
      renderNpsSeiCandidateStep();
    } catch(error){toast('Não foi possível importar o questionário',error.message,'error');}
  });
}

function renderNpsSeiCandidateStep() {
  const ctx=npsSurveyContext(); const root=$('#npsSeiFlow'); const result=ctx?.importResult; if(!ctx||!root||!result) return;
  const copy=npsScopeCopy(ctx.npsScope);
  const candidates=result.nps_candidates||[];
  const faculty=copy.scope==='faculty';
  const available = faculty
    ? candidates
    : candidates.filter(q=>copy.scope==='institution'?!q.official_for_course_semester:!q.official_for_institution_semester);
  const existingId = faculty
    ? (candidates.find(q=>q.official_for_semester)?.id||'')
    : ((copy.scope==='institution'
        ? candidates.find(q=>q.official_for_institution_semester)?.id
        : candidates.find(q=>q.official_for_course_semester)?.id)||'');
  const sourceExists = faculty
    ? Boolean(candidates[0]?.source_exists)
    : Boolean(candidates[0]?.[copy.scope==='institution'?'institution_source_exists':'course_source_exists']);
  const options=`<option value="">Selecione a pergunta oficial</option>${available.map(q=>`<option value="${q.id}" ${Number(existingId)===Number(q.id)?'selected':''}>${escapeHtml(q.text)}</option>`).join('')}`;
  const importedCount = result.imported_files?.length || 0;
  const skippedCount = result.skipped_files?.length || 0;
  const zeroCandidateText = faculty
    ? '<div class="warning-box span-2"><strong>Questionário docente preservado, mas nenhuma pergunta NPS 0–10 foi encontrada.</strong><br>O Data UNIVC armazenou o relatório institucional completo e anônimo. Este semestre só poderá gerar o KPI 01C quando o questionário possuir uma pergunta com alternativas exatamente de 0 a 10. Nenhuma nota categórica será convertida artificialmente em NPS.</div>'
    : '<div class="warning-box span-2"><strong>Nenhuma pergunta 0–10 foi encontrada.</strong><br>O relatório foi preservado, mas não é possível gerar NPS sem uma pergunta com alternativas exatamente de 0 a 10.</div>';
  root.innerHTML=`<form id="npsScopedBindForm" class="form-grid">
    <div class="tip-box span-2"><strong>Questionário preservado no banco.</strong> ${escapeHtml(result.semester||'')} · ${importedCount} novo(s) bloco(s), ${skippedCount} já existente(s). ${faculty?'A população permanece institucional e anônima.':`Agora defina somente o <strong>${escapeHtml(copy.title)}</strong>.`}</div>
    ${candidates.length?`<label class="field span-2"><span>Pergunta oficial · ${escapeHtml(copy.title)}</span><select id="npsScopedCandidate" required>${options}</select><small>${escapeHtml(copy.bindHelp)}</small></label>`:zeroCandidateText}
    ${!faculty && candidates.length && !available.length?`<div class="warning-box span-2"><strong>As perguntas 0–10 disponíveis já estão vinculadas ao outro NPS.</strong><br>Uma mesma pergunta não pode representar simultaneamente NPS da Instituição e NPS do Curso.</div>`:''}
    ${sourceExists?`<label class="field span-2"><label class="sei-course-option"><input type="checkbox" id="surveyReplaceScopedNps"><span class="sei-course-check">✓</span><span class="sei-course-copy"><strong>Substituir o ${escapeHtml(copy.title)} existente</strong><small>Use somente se este relatório deve virar a nova fonte oficial deste indicador no semestre.</small></span></label></label>`:''}
    <div id="npsBindResult" class="span-2"></div>
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="finishSurveyWithoutNps">Fechar sem vincular</button>${available.length?'<button type="submit" class="button primary">Salvar pergunta oficial e atualizar</button>':''}</div>
  </form>`;
  $('#finishSurveyWithoutNps')?.addEventListener('click',closeModal);
  $('#npsScopedBindForm')?.addEventListener('submit',async event=>{
    event.preventDefault();
    const questionId=Number($('#npsScopedCandidate')?.value||0);
    if(!questionId){toast('Selecione a pergunta oficial',`Escolha a pergunta de ${copy.title} antes de continuar.`,'warning');return;}
    try{
      const endpoint=faculty?'/api/surveys/nps/faculty/bind':'/api/surveys/nps/bind';
      const body=faculty
        ? {run_id:result.run_id,question_id:questionId,semester:result.semester,replace:Boolean($('#surveyReplaceScopedNps')?.checked)}
        : {run_id:result.run_id,question_id:questionId,semester:result.semester,replace:Boolean($('#surveyReplaceScopedNps')?.checked),nps_scope:copy.scope};
      const synced=await api(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),loadingTitle:`Atualizando ${copy.title}`,loadingMessage:faculty?'Agregando anonimamente as respostas 0–10 do corpo docente e preservando a fonte oficial.':copy.scope==='institution'?'Agregando as respostas 0–10 da pergunta institucional e preservando a fonte oficial.':'Agregando as respostas 0–10 por curso e reconstruindo o indicador acadêmico.'});
      const o=synced.overall||{};
      $('#npsBindResult').innerHTML=`<div class="import-result"><strong>${escapeHtml(copy.title)} atualizado pelo SEI</strong><div>${escapeHtml(synced.semester)} · NPS ${o.score==null?'—':formatNumber(o.score,1)} · ${formatNumber(o.respondents||0,0)} resposta(s)${copy.scope==='course'?` · ${synced.courses_synced?.length||0} curso(s)`:''}.</div></div>`;
      if(faculty) { state.npsFaculty=[]; await loadFacultyNps(true); }
      else if(copy.scope==='institution') { state.npsInstitution=[]; await loadInstitutionNps(true); }
      else { state.data.nps=[]; await loadDataset('nps',true); }
      await refreshBootstrapAfterCatalogChange(); await loadDashboard();
      setSaveState('ok',`${copy.title} sincronizado pelo SEI`); toast(`${copy.title} atualizado`, 'A nova fonte oficial já está refletida no histórico.','success');
    }catch(error){toast(`Não foi possível atualizar ${copy.title}`,error.message,'error');}
  });
}

async function openTeacherSeiReadiness() {
  try {
    const data=await api('/api/surveys/faculty/readiness',{blocking:false});
    const c=data.counts||{};
    openModal('Avaliação Docente · SEI','Fundação de integração preparada',`<div class="tip-box"><strong>A estrutura já está dentro do Data UNIVC.</strong> Professor, disciplina, curso, turma/oferta e semestre são dimensões independentes. O adaptador do XLSX/ZIP docente será ativado somente depois que existir um relatório real do SEI.</div><div class="help-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:14px 0"><div class="help-card"><span>${formatNumber(c.teachers||0,0)}</span><h3>Docentes normalizados</h3><p>Identidade histórica do professor.</p></div><div class="help-card"><span>${formatNumber(c.academic_offerings||0,0)}</span><h3>Ofertas acadêmicas</h3><p>Semestre × curso × disciplina × turma.</p></div><div class="help-card"><span>${formatNumber(c.teaching_assignments||0,0)}</span><h3>Vínculos docentes</h3><p>Professor associado à oferta.</p></div><div class="help-card"><span>${formatNumber(c.faculty_evaluation_contexts||0,0)}</span><h3>Contextos avaliados</h3><p>Prontos para receber o futuro relatório.</p></div></div><div class="warning-box"><strong>Por que ainda não importamos do SEI?</strong><br>Não existe um relatório docente real validado para confirmar onde o SEI informa professor, disciplina e turma. Inventar essas posições agora colocaria o histórico em risco. O restante da arquitetura já está pronto para receber esse adaptador.</div><div class="modal-form-footer"><button class="button primary" id="closeTeacherReadiness" type="button">Entendi</button></div>`);
    state.modalContext={type:'teacher-sei-readiness'}; $('#closeTeacherReadiness')?.addEventListener('click',closeModal);
  } catch(error){toast('Não foi possível verificar a fundação docente',error.message,'error');}
}

async function loadActions(force = false) {
  if (state.actions.length && !force) { renderActions(); return; }
  try {
    const response = await api('/api/planos');
    state.actions = response.items;
    renderActions();
  } catch (error) { toast('Erro ao carregar os planos', error.message, 'error'); }
}

function renderActions() {
  const term=(state.searches.planos||'').toLowerCase(); let items=state.actions;
  if(term)items=items.filter(x=>Object.values(x).some(v=>String(v??'').toLowerCase().includes(term)));
  const page=paginate(items,'actions');
  $('#count-planos').textContent=items.length?`${page.start+1}–${Math.min(items.length,page.start+page.rows.length)} de ${items.length}`:'0 planos';
  const open=state.actions.filter(x=>!['Concluído','Cancelado'].includes(x.status)).length;
  const overdue=state.actions.filter(x=>x.dias_prazo!==null&&x.dias_prazo<0&&!['Concluído','Cancelado'].includes(x.status)).length;
  const concluded=state.actions.filter(x=>x.status==='Concluído').length;
  const soon=state.actions.filter(x=>x.dias_prazo!==null&&x.dias_prazo>=0&&x.dias_prazo<=15&&!['Concluído','Cancelado'].includes(x.status)).length;
  $('#actionSummary').innerHTML=[['Abertos',open],['Atrasados',overdue],['Vencem em 15 dias',soon],['Concluídos',concluded]].map(([label,value])=>`<div class="action-summary-card"><strong>${value}</strong><span>${label}</span></div>`).join('');
  const target=$('#table-planos'); if(!items.length){target.innerHTML='<div class="empty-table"><strong>Nenhum plano encontrado</strong>Crie um plano para acompanhar um desvio.</div>';return;}
  const editable=canEditCurrentDirectorate();
  target.innerHTML=`<table><thead><tr><th>Nº</th><th>Mês</th><th>KPI</th><th>Recorte</th><th>Problema e ação</th><th>Responsável</th><th>Prazo</th><th>Status</th>${editable?'<th class="actions">Ações</th>':''}</tr></thead><tbody>${page.rows.map(a=>`<tr><td>${escapeHtml(a.numero)}</td><td>${escapeHtml(a.mes)}</td><td>${escapeHtml(a.indicador)}</td><td>${escapeHtml(a.recorte)}</td><td><strong>${escapeHtml(a.problema)}</strong><br><small>${escapeHtml(a.acao)}</small></td><td>${escapeHtml(a.responsavel)}</td><td>${formatDate(a.prazo)}${a.dias_prazo!==null?`<br><small>${a.dias_prazo<0?`${Math.abs(a.dias_prazo)} dia(s) atrasado`:`${a.dias_prazo} dia(s)`}</small>`:''}</td><td>${badge(a.status)}</td>${editable?`<td class="actions"><button class="row-action" data-action-edit="${a.id}">✎</button><button class="row-action delete" data-action-delete="${a.id}">×</button></td>`:''}</tr>`).join('')}</tbody></table>`;
  attachPagination(target,'actions',items.length,renderActions);
  $$('[data-action-edit]',target).forEach(btn=>btn.addEventListener('click',()=>openActionForm(Number(btn.dataset.actionEdit))));
  $$('[data-action-delete]',target).forEach(btn=>btn.addEventListener('click',()=>deleteAction(Number(btn.dataset.actionDelete))));
}

function textareaField(name, label, value = '', opts = {}) {
  return `<label class="field ${opts.className || ''}" data-field-wrapper="${name}"><span>${escapeHtml(label)}</span><textarea name="${name}" id="field-${name}" ${opts.required === false ? '' : 'required'}>${escapeHtml(value || '')}</textarea><div class="field-error"></div></label>`;
}

function openActionForm(id = null) {
  if(!canEditCurrentDirectorate()){toast('Somente leitura','Planos de ação só podem ser alterados na sua diretoria principal.','warning');return;}
  const a=id?state.actions.find(x=>x.id===id):{};const status=['Não iniciado','Em andamento','Concluído','Atrasado','Cancelado'];const indicators=(state.bootstrap?.indicators||[]).map(item=>item.code);
  const body=`<form id="actionForm" class="form-grid">${formField('mes','Mês de abertura','month',a.mes||'')}${selectField('indicador','KPI',indicators,a.indicador||indicators[0]||'',{placeholder:'Selecione'})}${formField('recorte','Recorte afetado','text',a.recorte||'',{className:'span-2',placeholder:'Ex.: Administração ou Administração » Gestão de Pessoas'})}${formField('resultado','Resultado observado','number',a.resultado??'',{required:false,step:'0.01'})}${formField('meta','Meta relacionada','number',a.meta??'',{required:false,step:'0.01'})}${textareaField('problema','Problema identificado',a.problema||'',{className:'span-2'})}${textareaField('causa','Causa provável',a.causa||'',{className:'span-2',required:false})}${textareaField('acao','Ação corretiva',a.acao||'',{className:'span-2'})}${formField('responsavel','Responsável','text',a.responsavel||'')}${formField('prazo','Prazo','date',a.prazo||'')}${formField('meta_acao','Resultado esperado da ação','text',a.meta_acao||'',{className:'span-2',required:false})}${selectField('status','Status',status,a.status||'Não iniciado',{className:'span-2'})}<div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelAction">Cancelar</button><button type="submit" class="button primary">${id?'Salvar alterações':'Criar plano'}</button></div></form>`;
  openModal('Plano de ação',id?'Editar plano':'Novo plano',body);state.modalContext={type:'action',id};$('#cancelAction').addEventListener('click',closeModal);$('#actionForm').addEventListener('submit',submitAction);
}

async function submitAction(event) {
  event.preventDefault();
  const form = event.currentTarget;
  clearFormErrors(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  ['resultado', 'meta'].forEach(k => { payload[k] = payload[k] === '' ? null : Number(payload[k]); });
  const id = state.modalContext.id;
  setSaveState('saving', 'Salvando plano…');
  try {
    await api(id ? `/api/planos/${id}` : '/api/planos', { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), loadingTitle: id ? 'Atualizando plano de ação' : 'Criando plano de ação', loadingMessage: 'Validando responsabilidades, prazo e dados do plano.' });
    closeModal();
    state.actions = [];
    await loadActions(true);
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast(id ? 'Plano atualizado' : 'Plano criado', 'A alteração foi gravada no banco de dados.');
  } catch (error) {
    setSaveState('error', 'Falha ao salvar');
    showFormErrors(form, error.fields);
    toast('Não foi possível salvar o plano', error.message, 'error');
  }
}

async function deleteAction(id) {
  const item = state.actions.find(x => x.id === id);
  if (!await confirmDialog(`Deseja excluir o plano ${item?.numero || ''}? A exclusão será registrada no log de auditoria.`)) return;
  setSaveState('saving', 'Excluindo plano…');
  try {
    await api(`/api/planos/${id}`, { method: 'DELETE', loadingTitle: 'Excluindo registro', loadingMessage: 'Registrando a exclusão no banco e no log de auditoria.' });
    state.actions = [];
    await loadActions(true);
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast('Plano excluído');
  } catch (error) { setSaveState('error', 'Falha ao excluir'); toast('Não foi possível excluir', error.message, 'error'); }
}

function quickAdd() {
  if(!canEditCurrentDirectorate()){toast('Somente leitura','Selecione sua diretoria principal para registrar ou alterar KPIs.','warning');return;}
  if(state.currentSection==='nps-institution'){openNpsSeiImportForm('institution');return;}
  if(state.currentSection==='nps-course'){openNpsSeiImportForm('course');return;}
  if(state.currentSection==='nps-faculty'){openNpsSeiImportForm('faculty');return;}
  if(['avaliacao_docente','resultados'].includes(state.currentSection)){openDataForm(state.currentSection);return;}
  openModal('Registro de KPI','Qual base acadêmica deseja alimentar?',`<div class="help-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:0"><button class="help-card" data-quick="nps-institution"><span>01A</span><h3>NPS da Instituição</h3><p>Pergunta oficial sobre recomendar o UNIVC.</p></button><button class="help-card" data-quick="nps-course"><span>01B</span><h3>NPS do Curso</h3><p>Pergunta oficial sobre recomendar o próprio curso.</p></button><button class="help-card" data-quick="nps-faculty"><span>01C</span><h3>NPS · Docentes</h3><p>Recomendação institucional anônima pelo corpo docente.</p></button><button class="help-card" data-quick="avaliacao_docente"><span>02</span><h3>Avaliação docente</h3><p>Nota do professor pelo aluno.</p></button><button class="help-card" data-quick="resultados"><span>03</span><h3>Aprovação e notas</h3><p>Resultado por aluno e disciplina.</p></button></div>`);$$('[data-quick]').forEach(btn=>btn.addEventListener('click',()=>{const dataset=btn.dataset.quick;closeModal();navigate(dataset);setTimeout(()=>dataset==='nps-institution'?openNpsSeiImportForm('institution'):dataset==='nps-course'?openNpsSeiImportForm('course'):dataset==='nps-faculty'?openNpsSeiImportForm('faculty'):openDataForm(dataset),120);}));
}

async function refreshBootstrapAfterCatalogChange() {
  state.bootstrap=await api('/api/bootstrap');fillCourseSelectors();fillResultFilters();fillConfig();applyDirectorateUi();
}

async function loadCatalogs(force = false) {
  if ((state.catalogs.cursos.length || state.catalogs.disciplinas.length) && !force) {
    renderCatalogs();
    return;
  }
  try {
    state.catalogs = await api('/api/cadastros');
    renderCatalogs();
  } catch (error) {
    toast('Erro ao carregar os cadastros', error.message, 'error');
  }
}

function catalogPeriod(value) {
  if (!value) return '—';
  return String(value).startsWith('=') ? 'Padrão da planilha' : String(value);
}

function renderCatalogs() {
  const courses=state.catalogs.cursos||[], disciplinesAll=state.catalogs.disciplinas||[];
  const term=(state.searches.disciplinas||'').trim().toLowerCase();
  const disciplines=term?disciplinesAll.filter(item=>`${item.curso} ${item.disciplina}`.toLowerCase().includes(term)):disciplinesAll;
  const editable=canEditCurrentDirectorate();
  const coursePage=paginate(courses,'courses');
  const disciplinePage=paginate(disciplines,'disciplines');
  $('#count-cursos').textContent=courses.length?`${coursePage.start+1}–${Math.min(courses.length,coursePage.start+coursePage.rows.length)} de ${courses.length}`:'0 cursos';
  $('#count-disciplinas').textContent=disciplines.length?`${disciplinePage.start+1}–${Math.min(disciplines.length,disciplinePage.start+disciplinePage.rows.length)} de ${disciplines.length}`:'0 disciplinas';
  const courseTarget=$('#table-cursos'), disciplineTarget=$('#table-disciplinas');
  courseTarget.innerHTML=courses.length?`<table><thead><tr><th>Curso</th><th>Status</th><th>Vigência</th>${editable?'<th class="actions">Ação</th>':''}</tr></thead><tbody>${coursePage.rows.map(item=>`<tr class="${item.ativo?'':'catalog-inactive'}"><td><strong>${escapeHtml(item.curso)}</strong></td><td>${badge(item.ativo?'OK':'Inativo',item.ativo?'Ativo':'Inativo')}</td><td><span>${escapeHtml(catalogPeriod(item.vigencia_inicio))}</span>${item.vigencia_fim?`<small> até ${escapeHtml(catalogPeriod(item.vigencia_fim))}</small>`:''}</td>${editable?`<td class="actions"><button class="row-action ${item.ativo?'delete':''}" data-course-status="${item.id}">${item.ativo?'○':'↻'}</button></td>`:''}</tr>`).join('')}</tbody></table>`:'<div class="empty-table">Nenhum curso cadastrado.</div>';
  disciplineTarget.innerHTML=disciplines.length?`<table><thead><tr><th>Curso</th><th>Disciplina</th><th>Status</th>${editable?'<th class="actions">Ação</th>':''}</tr></thead><tbody>${disciplinePage.rows.map(item=>`<tr class="${item.ativo?'':'catalog-inactive'}"><td>${escapeHtml(item.curso)}</td><td><strong>${escapeHtml(item.disciplina)}</strong></td><td>${badge(item.ativo?'OK':'Inativo',item.ativo?'Ativa':'Inativa')}</td>${editable?`<td class="actions"><button class="row-action ${item.ativo?'delete':''}" data-discipline-status="${item.id}">${item.ativo?'○':'↻'}</button></td>`:''}</tr>`).join('')}</tbody></table>`:'<div class="empty-table">Nenhuma disciplina encontrada.</div>';
  if(courses.length) attachPagination(courseTarget,'courses',courses.length,renderCatalogs);
  if(disciplines.length) attachPagination(disciplineTarget,'disciplines',disciplines.length,renderCatalogs);
  $$('[data-course-status]',courseTarget).forEach(btn=>btn.addEventListener('click',()=>changeCatalogStatus('curso',Number(btn.dataset.courseStatus))));
  $$('[data-discipline-status]',disciplineTarget).forEach(btn=>btn.addEventListener('click',()=>changeCatalogStatus('disciplina',Number(btn.dataset.disciplineStatus))));
}

function openCourseForm() {
  const currentMonth = new Date().toISOString().slice(0, 7);
  const body = `<form id="courseForm" class="form-grid">
    ${formField('curso', 'Nome do curso', 'text', '', { className: 'span-2', placeholder: 'Ex.: Engenharia Elétrica' })}
    ${formField('vigencia_inicio', 'Início da vigência', 'month', currentMonth, { className: 'span-2', help: 'Define a partir de quando o curso passa a ser utilizado em novos lançamentos.' })}
    <div class="tip-box span-2"><strong>Depois de salvar:</strong> o curso passa a aparecer automaticamente nos formulários dos KPIs e nas metas.</div>
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelCourse">Cancelar</button><button type="submit" class="button primary">Adicionar curso</button></div>
  </form>`;
  openModal('Cadastro acadêmico', 'Novo curso', body);
  state.modalContext = { type: 'course' };
  $('#cancelCourse').addEventListener('click', closeModal);
  $('#courseForm').addEventListener('submit', submitCourse);
}

async function submitCourse(event) {
  event.preventDefault();
  const form = event.currentTarget;
  clearFormErrors(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  setSaveState('saving', 'Cadastrando curso…');
  try {
    await api('/api/cursos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), loadingTitle: 'Cadastrando curso', loadingMessage: 'Validando e registrando o curso no banco oficial.' });
    closeModal();
    state.catalogs = { cursos: [], disciplinas: [] };
    await refreshBootstrapAfterCatalogChange();
    await loadCatalogs(true);
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast('Curso adicionado', 'O curso já está disponível nos novos lançamentos.');
  } catch (error) {
    setSaveState('error', 'Falha ao cadastrar');
    showFormErrors(form, error.fields);
    toast('Não foi possível adicionar o curso', error.message, 'error');
  }
}

function openDisciplineForm() {
  const currentMonth = new Date().toISOString().slice(0, 7);
  const body = `<form id="disciplineForm" class="form-grid">
    ${selectField('curso', 'Curso', state.bootstrap.courses, '', { placeholder: 'Selecione o curso', className: 'span-2' })}
    ${formField('disciplina', 'Nome da disciplina', 'text', '', { className: 'span-2', placeholder: 'Ex.: Mecânica dos Fluidos' })}
    ${formField('vigencia_inicio', 'Início da vigência', 'month', currentMonth, { className: 'span-2' })}
    <div class="tip-box span-2"><strong>Uso na frequência:</strong> a nova disciplina passa a aparecer somente quando o curso correspondente estiver selecionado.</div>
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelDiscipline">Cancelar</button><button type="submit" class="button primary">Adicionar disciplina</button></div>
  </form>`;
  openModal('Cadastro acadêmico', 'Nova disciplina', body);
  state.modalContext = { type: 'discipline' };
  $('#cancelDiscipline').addEventListener('click', closeModal);
  $('#disciplineForm').addEventListener('submit', submitDiscipline);
}

async function submitDiscipline(event) {
  event.preventDefault();
  const form = event.currentTarget;
  clearFormErrors(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  setSaveState('saving', 'Cadastrando disciplina…');
  try {
    await api('/api/disciplinas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), loadingTitle: 'Cadastrando disciplina', loadingMessage: 'Validando e registrando a disciplina no banco oficial.' });
    closeModal();
    state.catalogs = { cursos: [], disciplinas: [] };
    await refreshBootstrapAfterCatalogChange();
    await loadCatalogs(true);
    setSaveState('ok', 'Banco sincronizado');
    toast('Disciplina adicionada', 'Ela já está disponível nos lançamentos de frequência.');
  } catch (error) {
    setSaveState('error', 'Falha ao cadastrar');
    showFormErrors(form, error.fields);
    toast('Não foi possível adicionar a disciplina', error.message, 'error');
  }
}

async function changeCatalogStatus(type, id) {
  const list = type === 'curso' ? state.catalogs.cursos : state.catalogs.disciplinas;
  const item = list.find(x => x.id === id);
  if (!item) return;
  const label = type === 'curso' ? item.curso : `${item.disciplina} (${item.curso})`;
  if (!item.ativo) {
    if (!await confirmDialog(`Deseja reativar ${label}? O item voltará a aparecer nos novos lançamentos.`)) return;
    try {
      await api(type === 'curso' ? `/api/cursos/${id}/status` : `/api/disciplinas/${id}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ativo: true }), loadingTitle: 'Reativando cadastro', loadingMessage: 'Atualizando o cadastro no banco oficial.' });
      state.catalogs = { cursos: [], disciplinas: [] };
      await refreshBootstrapAfterCatalogChange();
      await loadCatalogs(true);
      await loadDashboard();
      toast('Cadastro reativado', `${label} voltou a ficar disponível.`);
    } catch (error) { toast('Não foi possível reativar', error.message, 'error'); }
    return;
  }

  const currentMonth = new Date().toISOString().slice(0, 7);
  const body = `<form id="deactivateCatalogForm" class="form-grid">
    <div class="warning-box span-2"><strong>O histórico será preservado.</strong> O item deixará de aparecer em novos lançamentos, mas os dados antigos continuarão válidos.</div>
    ${formField('vigencia_fim', 'Fim da vigência', 'month', currentMonth, { className: 'span-2' })}
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelDeactivate">Cancelar</button><button type="submit" class="button danger">Inativar</button></div>
  </form>`;
  openModal('Preservação histórica', `Inativar ${type === 'curso' ? 'curso' : 'disciplina'}`, body);
  state.modalContext = { type: 'catalog-status', catalogType: type, id };
  $('#cancelDeactivate').addEventListener('click', closeModal);
  $('#deactivateCatalogForm').addEventListener('submit', async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    payload.ativo = false;
    clearFormErrors(event.currentTarget);
    try {
      await api(type === 'curso' ? `/api/cursos/${id}/status` : `/api/disciplinas/${id}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), loadingTitle: 'Inativando cadastro', loadingMessage: 'Preservando o histórico e registrando o fim da vigência.' });
      closeModal();
      state.catalogs = { cursos: [], disciplinas: [] };
      await refreshBootstrapAfterCatalogChange();
      await loadCatalogs(true);
      await loadDashboard();
      toast('Cadastro inativado', `${label} foi retirado dos novos lançamentos sem apagar o histórico.`);
    } catch (error) {
      showFormErrors(event.currentTarget, error.fields);
      toast('Não foi possível inativar', error.message, 'error');
    }
  });
}

async function loadGoals(force = false) {
  if (state.goals.length && !force) { renderGoals(); return; }
  try {
    const response = await api('/api/metas');
    state.goals = response.items;
    renderGoals();
  } catch (error) { toast('Erro ao carregar as metas', error.message, 'error'); }
}

function renderGoals() {
  const term=(state.searches.metas||'').toLowerCase(); let items=state.goals;
  if(term)items=items.filter(x=>Object.values(x).some(v=>String(v??'').toLowerCase().includes(term)));
  const page=paginate(items,'goals');
  $('#count-metas').textContent=items.length?`${page.start+1}–${Math.min(items.length,page.start+page.rows.length)} de ${items.length}`:'0 metas';
  const target=$('#table-metas');
  if(!items.length){target.innerHTML='<div class="empty-table"><strong>Nenhuma meta encontrada</strong>Crie uma meta para avaliar os KPIs.</div>';return;}
  // A situação da tabela de metas é relativa ao calendário de hoje, não ao
  // último período com dados no dashboard. Uma meta 2026-SEM2 passa a vigorar
  // em julho/2026, mesmo que a base acadêmica mais recente ainda seja SEM1.
  const todayKey=currentPeriodKey();
  const statusForGoal=goal=>{
    const key=periodStartKey(goal.vigencia);
    if(key<0)return{label:'Vigência inválida',kind:'danger',active:false};
    if(key>todayKey)return{label:'Futura',kind:'info',active:false};
    const peers=state.goals
      .filter(x=>x.indicador===goal.indicador&&x.recorte===goal.recorte&&periodStartKey(x.vigencia)>=0&&periodStartKey(x.vigencia)<=todayKey)
      .sort((a,b)=>periodStartKey(b.vigencia)-periodStartKey(a.vigencia));
    const latest=peers[0];
    return latest?.id===goal.id?{label:'Vigente hoje',kind:'OK',active:true}:{label:'Histórica',kind:'neutral',active:false};
  };
  const editable=canEditCurrentDirectorate();
  const goalValue=(g,value)=>{if(value===null||value===undefined||value==='')return '—';if(g.unidade==='R$')return formatCurrency(value);if(g.unidade==='%')return `${formatNumber(value,1)}%`;if(g.unidade==='pontos')return `${formatNumber(value,1)} pts`;return `${formatNumber(value,1)}${g.unidade?` ${escapeHtml(g.unidade)}`:''}`;};
  target.innerHTML=`<table><thead><tr><th>KPI</th><th>Recorte</th><th>Vigência</th><th>Situação</th><th class="numeric">Meta / limite inferior</th><th class="numeric">Atenção</th><th class="numeric">Limite superior</th><th>Justificativa</th>${editable?'<th class="actions">Ações</th>':''}</tr></thead><tbody>${page.rows.map(g=>{const situation=statusForGoal(g);return `<tr class="${situation.active?'active-goal-row':''}"><td>${escapeHtml(g.indicador)}</td><td><strong>${escapeHtml(g.recorte)}</strong></td><td>${escapeHtml(g.vigencia)}</td><td>${badge(situation.kind,situation.label)}</td><td class="numeric">${goalValue(g,g.meta)}</td><td class="numeric">${goalValue(g,g.atencao)}</td><td class="numeric">${goalValue(g,g.limite_superior)}</td><td>${escapeHtml(g.justificativa||'—')}</td>${editable?`<td class="actions"><button class="row-action" data-goal-edit="${g.id}">✎</button><button class="row-action delete" data-goal-delete="${g.id}">×</button></td>`:''}</tr>`;}).join('')}</tbody></table>`;
  attachPagination(target,'goals',items.length,renderGoals);
  $$('[data-goal-edit]',target).forEach(btn=>btn.addEventListener('click',()=>openGoalForm(Number(btn.dataset.goalEdit))));
  $$('[data-goal-delete]',target).forEach(btn=>btn.addEventListener('click',()=>deleteGoal(Number(btn.dataset.goalDelete))));
}

function goalRecortes(indicatorCode = '') {
  const code = String(indicatorCode || '').toUpperCase();
  if (code.endsWith('-01A') || code.endsWith('-01C')) return ['TOTAL'];
  const result=['TOTAL'];
  for(const course of state.bootstrap.courses||[]){
    result.push(course);
    if (!code.endsWith('-01B')) {
      for(const discipline of state.bootstrap.disciplines?.[course]||[]) result.push(`${course} » ${discipline}`);
    }
  }
  return [...new Set(result)];
}

function openGoalForm(id = null) {
  if(!canEditCurrentDirectorate()){toast('Somente leitura','Metas só podem ser alteradas na sua diretoria principal.','warning');return;}
  const g=id?state.goals.find(x=>x.id===id):{};const indicators=(state.bootstrap?.indicators||[]).map(item=>item.code);const selected=g.indicador||indicators[0]||'';
  const defaultVigencia=g.vigencia||currentAcademicSemester();
  const vigencyField=formField('vigencia','Início da vigência','text',defaultVigencia,{placeholder:'2026-SEM2 ou 2026-07',help:'Semestre começa em janeiro/julho. Use AAAA-SEM1, AAAA-SEM2 ou AAAA-MM.'});
  const body=`<form id="goalForm" class="form-grid">${selectField('indicador','KPI',indicators,selected)}${vigencyField}${selectField('recorte','Recorte',goalRecortes(selected),g.recorte||'TOTAL',{className:'span-2'})}${formField('meta','Meta','number',g.meta??'',{step:'0.01'})}${formField('atencao','Limiar de atenção','number',g.atencao??'',{step:'0.01'})}${formField('limite_superior','Limite superior, opcional','number',g.limite_superior??'',{step:'0.01',required:false,className:'span-2'})}${textareaField('justificativa','Justificativa da meta',g.justificativa||'',{className:'span-2',required:false})}<div class="tip-box span-2" id="goalHelp"></div><div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelGoal">Cancelar</button><button type="submit" class="button primary">${id?'Salvar alterações':'Criar meta'}</button></div></form>`;
  openModal('Governança de KPI',id?'Editar meta':'Nova meta',body);state.modalContext={type:'goal',id};
  const updateRecortes=()=>{
    const code=$('#field-indicador')?.value||'';
    const select=$('#field-recorte');
    if(!select)return;
    const current=select.value;
    const values=goalRecortes(code);
    const chosen=values.includes(current)?current:'TOTAL';
    select.innerHTML=values.map(value=>option(value,value===chosen,value)).join('');
  };
  const updateHelp=()=>{const code=$('#field-indicador').value;const info=indicatorByCode(code);$('#goalHelp').innerHTML=`<strong>${escapeHtml(code)}:</strong> ${escapeHtml(info?.help||'Defina o parâmetro operacional e registre a justificativa.')}`;};
  $('#field-indicador').addEventListener('change',()=>{updateRecortes();updateHelp();});
  updateRecortes();updateHelp();$('#cancelGoal').addEventListener('click',closeModal);$('#goalForm').addEventListener('submit',submitGoal);
}

async function submitGoal(event) {
  event.preventDefault();
  const form = event.currentTarget;
  clearFormErrors(form);
  const payload = Object.fromEntries(new FormData(form).entries());
  ['meta', 'atencao', 'limite_superior'].forEach(k => { payload[k] = payload[k] === '' ? null : Number(payload[k]); });
  const id = state.modalContext.id;
  setSaveState('saving', 'Salvando meta…');
  try {
    await api(id ? `/api/metas/${id}` : '/api/metas', { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), loadingTitle: id ? 'Atualizando meta do KPI' : 'Criando meta do KPI', loadingMessage: 'Validando vigência, recorte e limites da meta.' });
    closeModal();
    state.goals = [];
    await loadGoals(true);
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast(id ? 'Meta atualizada' : 'Meta criada', 'A configuração já foi gravada no banco de dados.');
  } catch (error) {
    setSaveState('error', 'Falha ao salvar');
    showFormErrors(form, error.fields);
    toast('Não foi possível salvar a meta', error.message, 'error');
  }
}

async function deleteGoal(id) {
  const item = state.goals.find(x => x.id === id);
  if (!await confirmDialog(`Deseja excluir a meta de ${item?.indicador || ''} para ${item?.recorte || ''}, vigente desde ${item?.vigencia || ''}?`)) return;
  setSaveState('saving', 'Excluindo meta…');
  try {
    await api(`/api/metas/${id}`, { method: 'DELETE', loadingTitle: 'Excluindo registro', loadingMessage: 'Registrando a exclusão no banco e no log de auditoria.' });
    state.goals = [];
    await loadGoals(true);
    await loadDashboard();
    setSaveState('ok', 'Banco sincronizado');
    toast('Meta excluída', 'A exclusão foi registrada no log de auditoria.');
  } catch (error) { setSaveState('error', 'Falha ao excluir'); toast('Não foi possível excluir', error.message, 'error'); }
}

function renderQuality() {
  if(!state.dashboard)return;
  const q=state.dashboard.cards.qualidade;
  const items=[
    ['KPI · NPS discente',q.nps,'respondentes, categorias e duplicidade'],
    ['KPI · Avaliação docente',q.avaliacao_docente,'professor, disciplina, respondentes e escala'],
    ['KPI · Aprovação e notas',q.resultados,'aluno, turma, situação oficial e duplicidade'],
  ];
  $('#qualityCards').innerHTML=items.map(([label,value,sub])=>metricCard(label,value?'!':'✓',String(value),sub,value?`${value} pendência(s)`:'Dados disponíveis')).join('');
}

async function saveConfig(event) {
  event.preventDefault();const payload={responsavel:$('#configResponsavel').value,diretoria_exibicao:state.user?.diretoria||$('#configDiretoria').value};
  try{const config=await api('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),loadingTitle:'Salvando configuração',loadingMessage:'Atualizando sua identificação no banco oficial.'});state.bootstrap.config={...state.bootstrap.config,...config};if(state.user){state.user.nome=config.responsavel||state.user.nome;renderUserMini();}toast('Configurações salvas','Sua identificação foi atualizada.');}catch(error){toast('Não foi possível salvar',error.message,'error');}
}

async function loadSchedules() {
  try {
    const response=await api('/api/cronograma'); state.schedules=response.items||[];
    const target=$('#scheduleTable'); if(!target)return;
    if(!state.schedules.length){target.innerHTML='<div class="empty-table">Nenhum cronograma configurado para esta diretoria.</div>';return;}
    const page=paginate(state.schedules,'schedules');
    const editable=canEditCurrentDirectorate();
    target.innerHTML=`<table><thead><tr><th>KPI</th><th>Periodicidade</th><th>Referência</th><th>Janela</th><th>Prazo atual</th>${editable?'<th></th>':''}</tr></thead><tbody>${page.rows.map(item=>`<tr><td><strong>${escapeHtml(item.codigo)}</strong><br><small>${escapeHtml(item.indicador)}</small></td><td>${escapeHtml(item.periodicidade||'—')}</td><td>${escapeHtml(item.grao_referencia)}</td><td>${item.abre_no_dia_util}º ao ${item.vence_no_dia_util}º dia útil</td><td>${formatDate(item.prazo_mes_atual)}<br>${badge(item.status_calendario)}</td>${editable?`<td class="actions"><button class="row-action" data-schedule-edit="${escapeHtml(item.codigo)}">✎</button></td>`:''}</tr>`).join('')}</tbody></table>`;
    attachPagination(target,'schedules',state.schedules.length,()=>renderSchedulesFromCache());
    $$('[data-schedule-edit]',target).forEach(btn=>btn.addEventListener('click',()=>openScheduleForm(btn.dataset.scheduleEdit)));
  } catch(error){toast('Erro ao carregar cronograma',error.message,'error');}
}

function renderSchedulesFromCache() {
  const target=$('#scheduleTable'); if(!target || !state.schedules.length)return;
  const page=paginate(state.schedules,'schedules'); const editable=canEditCurrentDirectorate();
  target.innerHTML=`<table><thead><tr><th>KPI</th><th>Periodicidade</th><th>Referência</th><th>Janela</th><th>Prazo atual</th>${editable?'<th></th>':''}</tr></thead><tbody>${page.rows.map(item=>`<tr><td><strong>${escapeHtml(item.codigo)}</strong><br><small>${escapeHtml(item.indicador)}</small></td><td>${escapeHtml(item.periodicidade||'—')}</td><td>${escapeHtml(item.grao_referencia)}</td><td>${item.abre_no_dia_util}º ao ${item.vence_no_dia_util}º dia útil</td><td>${formatDate(item.prazo_mes_atual)}<br>${badge(item.status_calendario)}</td>${editable?`<td class="actions"><button class="row-action" data-schedule-edit="${escapeHtml(item.codigo)}">✎</button></td>`:''}</tr>`).join('')}</tbody></table>`;
  attachPagination(target,'schedules',state.schedules.length,renderSchedulesFromCache);
  $$('[data-schedule-edit]',target).forEach(btn=>btn.addEventListener('click',()=>openScheduleForm(btn.dataset.scheduleEdit)));
}

function openScheduleForm(code) {
  const item = state.schedules.find(x => x.codigo === code);
  if (!item) return;
  const grains = ['month','bimonth','quarter','semester','annual','event'];
  const body = `<form id="scheduleForm" class="form-grid">
    <div class="tip-box span-2"><strong>${escapeHtml(item.codigo)} · ${escapeHtml(item.indicador)}</strong><br>A periodicidade institucional do KPI continua sendo ${escapeHtml(item.periodicidade || 'definida na matriz')}; os campos abaixo controlam a janela operacional de alimentação.</div>
    ${selectField('reference_grain','Grão da referência',grains,item.grao_referencia)}
    ${formField('collection_window_start_business_day','Abre no dia útil','number',item.abre_no_dia_util,{min:1,max:23})}
    ${formField('due_business_day','Vence no dia útil','number',item.vence_no_dia_util,{min:1,max:23})}
    ${textareaField('notes','Observações','',{className:'span-2',required:false})}
    <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="cancelSchedule">Cancelar</button><button type="submit" class="button primary">Salvar cronograma</button></div>
  </form>`;
  openModal('Recorrência', `Cronograma · ${code}`, body);
  state.modalContext = { type:'schedule', code };
  $('#cancelSchedule').addEventListener('click', closeModal);
  $('#scheduleForm').addEventListener('submit', submitSchedule);
}

async function submitSchedule(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.collection_window_start_business_day = Number(payload.collection_window_start_business_day);
  payload.due_business_day = Number(payload.due_business_day);
  try {
    await api(`/api/cronograma/${encodeURIComponent(state.modalContext.code)}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), loadingTitle:'Atualizando cronograma', loadingMessage:'Salvando a regra de recorrência do KPI.' });
    closeModal(); await loadSchedules(); toast('Cronograma atualizado', 'A próxima janela será calculada com a nova regra.');
  } catch (error) { toast('Não foi possível atualizar', error.message, 'error'); }
}

document.addEventListener('visibilitychange', async () => {
  if (document.visibilityState !== 'visible' || !state.user) return;
  const ok = await refreshAuthSession();
  if (!ok) showLogin('Sua sessão expirou. Entre novamente para continuar.');
});

window.addEventListener('resize', () => {
  if (!state.dashboard || state.currentSection !== 'dashboard') return;
  clearTimeout(window.__chartResize);
  window.__chartResize = setTimeout(renderDashboard, 180);
});

document.addEventListener('DOMContentLoaded', startAuthenticatedApp);
