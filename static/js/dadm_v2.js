window.DADMV2 = window.DADMV2 || {};
(() => {
  const NS = window.DADMV2;
  const state = NS.state;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const VIEW_TITLES = {
    overview: 'Visão geral',
    people: 'Pessoas & setores',
    experience: 'Experiência',
    comparison: 'Análise comparativa',
    management: 'Metas & planos',
    integration: 'Dados & integração',
  };
  const ENTITY_METRICS = {
    attendances: { label: 'Atendimentos', titleEmployee: 'Atendimentos por operador', titleDepartment: 'Atendimentos por departamento' },
    tme_avg_seconds: { label: 'Tempo médio de espera', titleEmployee: 'Tempo Médio de Espera por operador', titleDepartment: 'Tempo Médio de Espera por departamento' },
    tma_avg_seconds: { label: 'Tempo médio de atendimento', titleEmployee: 'Tempo Médio de Atendimento por operador', titleDepartment: 'Tempo Médio de Atendimento por departamento' },
    rating_avg: { label: 'Avaliação média', titleEmployee: 'Avaliação média por operador', titleDepartment: 'Avaliação média por departamento' },
  };
  const PROFILE_METRICS = {
    attendances: { label: 'Atendimentos', format: NS.formatInt },
    tme_avg_seconds: { label: 'Tempo médio de espera', format: NS.formatSeconds },
    tma_avg_seconds: { label: 'Tempo médio de atendimento', format: NS.formatSeconds },
    rating_avg: { label: 'Avaliação média', format: NS.formatRating },
  };

  function selectedMonthCount() {
    const start = NS.monthIndex(state.filters.fromMonth);
    const end = NS.monthIndex(state.filters.toMonth);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return 0;
    return end - start + 1;
  }

  function hasTemporalEvolution() {
    return selectedMonthCount() > 1;
  }
  const prefersReducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

  function showLayer(element) {
    if (!element) return;
    if (element._v2MotionTimer) window.clearTimeout(element._v2MotionTimer);
    element._v2MotionTimer = null;
    element.classList.remove('is-closing', 'hidden');
  }

  function hideLayer(element, duration = 170) {
    if (!element || element.classList.contains('hidden')) return;
    if (element._v2MotionTimer) window.clearTimeout(element._v2MotionTimer);
    if (prefersReducedMotion()) {
      element.classList.remove('is-closing');
      element.classList.add('hidden');
      return;
    }
    element.classList.add('is-closing');
    element._v2MotionTimer = window.setTimeout(() => {
      element.classList.remove('is-closing');
      element.classList.add('hidden');
      element._v2MotionTimer = null;
    }, duration);
  }

  function toggleLayer(element) {
    if (!element) return;
    const opening = element.classList.contains('hidden') || element.classList.contains('is-closing');
    if (opening) showLayer(element);
    else hideLayer(element);
  }

  function setLoading(active) {
    state.loadingCount = Math.max(0, state.loadingCount + (active ? 1 : -1));
    const busy = state.loadingCount > 0;
    $('#v2Loading')?.classList.toggle('hidden', !busy);
    document.body.classList.toggle('v2-is-loading', busy);
  }

  function alertUser(message, kind = 'error', timeout = 5500) {
    const box = $('#v2Alert');
    if (!box) return;
    if (box._v2AlertTimer) window.clearTimeout(box._v2AlertTimer);
    box.textContent = message;
    box.className = `v2-alert ${kind}`;
    showLayer(box);
    box._v2AlertTimer = timeout ? window.setTimeout(() => hideLayer(box, 150), timeout) : null;
  }

  function roleLabel(role) {
    return { admin: 'Administrador', director: 'Diretor', editor: 'Editor', viewer: 'Consulta' }[role] || role || 'Usuário';
  }

  function applyAccessMode() {
    const canWrite = Boolean(state.access?.canEdit);
    $('#v2ReadOnlyNotice')?.classList.toggle('hidden', canWrite);
    const badge = $('#v2AccessBadge');
    if (badge) {
      badge.textContent = canWrite ? 'Edição' : 'Somente leitura';
      badge.classList.toggle('readonly', !canWrite);
    }
    $$('[data-write-action]').forEach(element => {
      const unavailable = element.dataset.writeUnavailable === '1';
      element.disabled = !canWrite || unavailable;
      element.setAttribute('aria-disabled', element.disabled ? 'true' : 'false');
      if (!canWrite) element.title = 'Alterações disponíveis somente para usuários com permissão de edição na DADM.';
      else if (!unavailable && element.title === 'Alterações disponíveis somente para usuários com permissão de edição na DADM.') element.removeAttribute('title');
    });
  }

  function renderDirectorateSwitcher() {
    const select = $('#v2DirectorateSelect');
    if (!select) return;
    const directorates = state.user?.availableDirectorates || [];
    select.innerHTML = directorates.map(item => {
      const suffix = item.canEdit ? ' · Edição' : ' · Leitura';
      return `<option value="${NS.escapeHtml(item.code)}">${NS.escapeHtml(item.code)} · ${NS.escapeHtml(item.name || item.code)}${NS.escapeHtml(suffix)}</option>`;
    }).join('');
    select.value = 'DADM';
    select.disabled = directorates.length <= 1;
    select.closest('.directorate-switcher')?.classList.toggle('hidden', !state.user?.shouldShowSwitcher?.());
  }

  async function loadUser() {
    state.user = await window.DataUnivcIdentity.load();
    if (!state.user) { location.assign('/'); return false; }
    state.access = state.user.directorateFor('DADM');
    if (!state.access) { window.DataUnivcIdentity.redirectToAuthorizedHome(state.user); return false; }
    state.dataScope = state.user.dataScopeFor('DADM') || { full: true, departments: [] };
    const restrictedDataScope = state.dataScope.full === false;
    // The DADM data scope limits what the user may read/manage, not what the
    // shared TALLOS integration may ingest. Keep Dados & integração available
    // to every DADM editor and hide only legacy full-scope surfaces.
    $$('.v2-legacy-link, .v2-legacy-panel').forEach(element => {
      element.classList.toggle('hidden', restrictedDataScope);
    });
    const name = state.user.name || state.user.email || 'Usuário';
    $('#v2UserName').textContent = name;
    $('#v2UserRole').textContent = `${state.user.roleLabel} · ${state.access.canEdit ? 'Edição' : 'Leitura'}`;
    window.DataUnivcIdentity.applyAvatar($('#v2UserAvatar'), state.user);
    renderDirectorateSwitcher();
    applyAccessMode();
    return true;
  }

  async function loadConnection() {
    try {
      state.connection = await NS.api('/api/dadm/tallos/status');
      renderDataState();
      return state.connection;
    } catch (error) {
      state.connection = null;
      const stateButton = $('#v2DataState');
      stateButton?.classList.add('error');
      $('#v2DataStateText').textContent = 'Status indisponível';
      return null;
    }
  }

  function renderDataState() {
    const data = state.connection;
    const button = $('#v2DataState');
    button.classList.remove('warning', 'error');
    if (!data?.configured) {
      button.classList.add('warning');
      $('#v2DataStateText').textContent = 'TALLOS não conectado';
      return;
    }
    if (!data?.data_available) {
      button.classList.add('warning');
      $('#v2DataStateText').textContent = 'TALLOS conectado · sem dados';
      return;
    }
    if (state.overview?.last_sync?.finished_at) {
      $('#v2DataStateText').textContent = `Atualizado ${NS.formatDateTime(state.overview.last_sync.finished_at)}`;
    } else {
      $('#v2DataStateText').textContent = 'Dados TALLOS disponíveis';
    }
  }

  async function loadContext({ allowReset = true } = {}) {
    setLoading(true);
    try {
      const params = NS.filterParams(state.filters);
      const context = await NS.api('/api/dadm/v2/context', {}, params);
      state.context = context;
      if (!state.filters.fromMonth) state.filters.fromMonth = context.period.from_month;
      if (!state.filters.toMonth) state.filters.toMonth = context.period.to_month;

      let reset = false;
      const checks = [
        ['department', context.departments],
        ['employee', context.employees],
        ['channel', context.channels],
        ['status', context.statuses],
        ['tabulation', context.tabulations],
      ];
      checks.forEach(([key, options]) => {
        if (state.filters[key] && !options.some(item => item.value === state.filters[key])) {
          state.filters[key] = '';
          reset = true;
        }
      });
      if (reset && allowReset) {
        return await loadContext({ allowReset: false });
      }
      renderContext();
      NS.syncUrl();
      return context;
    } finally {
      setLoading(false);
    }
  }

  function populateSelect(selector, items, emptyLabel, selected) {
    const select = $(selector);
    if (!select) return;
    select.innerHTML = `<option value="">${NS.escapeHtml(emptyLabel)}</option>` + (items || []).map(item => `<option value="${NS.escapeHtml(item.value)}" ${item.value === selected ? 'selected' : ''}>${NS.escapeHtml(item.label)}</option>`).join('');
    select.value = selected || '';
  }

  function selectedLabel(items, value) {
    return (items || []).find(item => item.value === value)?.label || value;
  }

  function renderContext() {
    const c = state.context || {};
    $('#v2PeriodLabel').textContent = NS.periodLabel(state.filters.fromMonth, state.filters.toMonth);
    populateSelect('#v2Department', c.departments, 'Todos os setores', state.filters.department);
    populateSelect('#v2Employee', c.employees, 'Todos os operadores', state.filters.employee);
    populateSelect('#v2Channel', c.channels, 'Todos os canais', state.filters.channel);
    populateSelect('#v2Status', c.statuses, 'Todos os status', state.filters.status);
    populateSelect('#v2Tabulation', c.tabulations, 'Todas as tabulações', state.filters.tabulation);

    const chips = [];
    const add = (key, label, value) => { if (value) chips.push({ key, label }); };
    add('department', selectedLabel(c.departments, state.filters.department), state.filters.department);
    add('employee', selectedLabel(c.employees, state.filters.employee), state.filters.employee);
    add('channel', state.filters.channel, state.filters.channel);
    add('status', state.filters.status, state.filters.status);
    add('tabulation', state.filters.tabulation, state.filters.tabulation);
    $('#v2FilterChips').innerHTML = chips.map(chip => `<span class="v2-chip">${NS.escapeHtml(chip.label)}<button type="button" data-remove-filter="${chip.key}" aria-label="Remover filtro">×</button></span>`).join('');
    $('#v2ClearFilters').classList.toggle('hidden', chips.length === 0);
    const extra = ['channel', 'status', 'tabulation'].filter(key => state.filters[key]).length;
    const extraBadge = $('#v2ExtraCount');
    extraBadge.textContent = String(extra);
    extraBadge.classList.toggle('hidden', extra === 0);
    updateComparisonOptions();
    const reportButton = $('#v2ReportButton');
    if (reportButton) reportButton.disabled = !(state.filters.fromMonth && state.filters.toMonth);
  }

  function reportValue(items, value, emptyLabel) {
    return value ? selectedLabel(items, value) : emptyLabel;
  }

  function renderReportSummary() {
    const c = state.context || {};
    const rows = [
      ['Per\u00edodo', NS.periodLabel(state.filters.fromMonth, state.filters.toMonth)],
      ['Departamento', reportValue(c.departments, state.filters.department, 'Todos os setores')],
      ['Operador', reportValue(c.employees, state.filters.employee, 'Todos os operadores')],
      ['Canal', reportValue(c.channels, state.filters.channel, 'Todos os canais')],
      ['Status', reportValue(c.statuses, state.filters.status, 'Todos os status')],
      ['Tabula\u00e7\u00e3o', reportValue(c.tabulations, state.filters.tabulation, 'Todas as tabula\u00e7\u00f5es')],
    ];
    const target = $('#v2ReportSummary');
    if (!target) return;
    target.innerHTML = rows.map(([label, value]) => `<div><span>${NS.escapeHtml(label)}</span><strong>${NS.escapeHtml(value || '\u2014')}</strong></div>`).join('');
  }

  function openReportModal() {
    if (!state.filters.fromMonth || !state.filters.toMonth) {
      alertUser('Aguarde o carregamento do per\u00edodo antes de gerar o relat\u00f3rio.', 'error');
      return;
    }
    renderReportSummary();
    const modal = $('#v2ReportModal');
    showLayer(modal);
    window.setTimeout(() => $('#v2GenerateReport')?.focus(), 0);
  }

  function closeReportModal() {
    hideLayer($('#v2ReportModal'));
  }

  function reportFilename(response) {
    const disposition = response.headers.get('content-disposition') || '';
    const utf = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf?.[1]) {
      try { return decodeURIComponent(utf[1].replace(/["']/g, '').trim()); } catch (_) {}
    }
    const basic = disposition.match(/filename="?([^";]+)"?/i);
    if (basic?.[1]) return basic[1].trim();
    const from = state.filters.fromMonth || 'inicio';
    const to = state.filters.toMonth || 'fim';
    return `DADM_TALLOS_${from}_a_${to}.xlsx`;
  }

  async function generateReport() {
    const button = $('#v2GenerateReport');
    const label = $('#v2GenerateReportLabel');
    if (!button || button.disabled) return;
    button.disabled = true;
    if (label) label.textContent = 'Gerando Excel\u2026';
    setLoading(true);
    try {
      const response = await fetch(NS.buildUrl('/api/dadm/v2/report.xlsx', NS.filterParams(state.filters)), {
        credentials: 'same-origin',
        headers: { Accept: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
      });
      if (response.status === 401) {
        location.assign('/');
        return;
      }
      if (!response.ok) {
        let message = `Erro HTTP ${response.status}`;
        const type = response.headers.get('content-type') || '';
        if (type.includes('application/json')) {
          try {
            const payload = await response.json();
            const detail = payload?.detail;
            message = typeof detail === 'string' ? detail : detail?.erro || payload?.erro || message;
          } catch (_) {}
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = reportFilename(response);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      closeReportModal();
      alertUser('Relat\u00f3rio Excel gerado com os filtros atuais.', 'success');
    } catch (error) {
      alertUser(`N\u00e3o foi poss\u00edvel gerar o relat\u00f3rio: ${error.message}`, 'error', 0);
    } finally {
      setLoading(false);
      button.disabled = false;
      if (label) label.textContent = 'Gerar Excel';
    }
  }

  async function refreshForContext() {
    await loadContext();
    state.entity.profileId = '';
    state.entity.profile = null;
    state.management = null;
    await loadCurrentView(true);
  }

  function navigate(view) {
    if (!VIEW_TITLES[view]) return;
    state.view = view;
    $$('.v2-nav-item[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
    $$('.v2-view').forEach(section => section.classList.toggle('active', section.dataset.viewSection === view));
    $('#v2PageTitle').textContent = VIEW_TITLES[view];
    closeSidebar();
    NS.syncUrl();
    loadCurrentView(false);
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }

  async function loadCurrentView(force = false) {
    try {
      if (state.view === 'overview') await loadOverview(force);
      else if (state.view === 'people') await loadPeople(force);
      else if (state.view === 'experience') await loadExperience(force);
      else if (state.view === 'comparison') await loadComparison(force);
      else if (state.view === 'management') await loadManagement(force);
      else if (state.view === 'integration') await loadIntegration(force);
    } catch (error) {
      alertUser(error.message, 'error', 0);
    }
  }

  async function ensureManagement(force = false) {
    if (state.management && !force) return state.management;
    if (!state.filters.toMonth) return null;
    state.management = await NS.api('/api/dadm/v2/management', {}, {
      month: state.filters.toMonth,
      department: state.filters.department,
      channel: state.filters.channel,
    });
    return state.management;
  }

  function managementMetric(metricKey) {
    return (state.management?.catalog?.metrics || []).find(item => item.key === metricKey) || null;
  }

  function formatManagementValue(metricKey, value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
    const unit = managementMetric(metricKey)?.unit;
    if (unit === 'seconds') return NS.formatSeconds(value);
    if (unit === 'rating_10') return `${NS.formatNumber(value, 2)} / 10`;
    if (unit === 'percent') return NS.formatPct(value);
    return NS.formatNumber(value, 1);
  }

  function targetStatus(metricKey, value) {
    const target = state.management?.active_targets?.[metricKey];
    const metric = managementMetric(metricKey);
    if (!target || target.target == null) return { key: 'neutral', label: 'Sem meta vigente', target: null };
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return { key: 'neutral', label: 'Sem dado no período', target };
    const current = Number(value), goal = Number(target.target), attention = target.attention == null ? null : Number(target.attention);
    if (metric?.direction === 'lower') {
      if (current <= goal) return { key: 'good', label: 'Dentro da meta', target };
      if (attention != null && current <= attention) return { key: 'attention', label: 'Atenção', target };
      return { key: 'bad', label: 'Fora da meta', target };
    }
    if (current >= goal) return { key: 'good', label: 'Dentro da meta', target };
    if (attention != null && current >= attention) return { key: 'attention', label: 'Atenção', target };
    return { key: 'bad', label: 'Fora da meta', target };
  }

  function targetNoteHtml(metricKey, value) {
    const status = targetStatus(metricKey, value);
    if (!status.target) return `<div class="v2-target-note"><span class="v2-target-state">Sem meta vigente</span></div>`;
    const metric = managementMetric(metricKey);
    const symbol = metric?.direction === 'lower' ? '≤' : '≥';
    return `<div class="v2-target-note"><span class="v2-target-state ${status.key}">${NS.escapeHtml(status.label)}</span><span>Meta ${symbol} ${NS.escapeHtml(formatManagementValue(metricKey, status.target.target))}</span></div>`;
  }

  function targetReference(metricKey, shortLabel) {
    const target = state.management?.active_targets?.[metricKey];
    if (!target || target.target == null) return null;
    return { value: Number(target.target), label: `${shortLabel} · meta ${formatManagementValue(metricKey, target.target)}` };
  }

  async function loadOverview(force = false) {
    if (state.overview && !force) {
      await ensureManagement(false);
      renderOverview();
      return;
    }
    setLoading(true);
    try {
      const [overview] = await Promise.all([
        NS.api('/api/dadm/v2/overview', {}, { ...NS.filterParams(state.filters), comparison: 'previous_period' }),
        ensureManagement(force),
      ]);
      state.overview = overview;
      renderOverview();
      renderDataState();
    } finally { setLoading(false); }
  }

  function deltaText(value, unit = '%') {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Sem comparação disponível';
    const number = Number(value);
    const arrow = number > 0 ? '↑' : number < 0 ? '↓' : '→';
    const abs = Math.abs(number);
    return `${arrow} ${NS.formatNumber(abs, 1)}${unit} vs período anterior`;
  }

  function renderOverview() {
    const data = state.overview || {};
    const s = data.summary || {};
    const d = data.deltas_pct || {};
    $('#v2OverviewSubtitle').textContent = `${NS.periodLabel(state.filters.fromMonth, state.filters.toMonth)} · filtros globais aplicados em toda a DADM V2.`;
    $('#v2OperationKpis').innerHTML = [
      ['Atendimentos', NS.formatInt(s.attendances), deltaText(d.attendances)],
      ['Protocolos', NS.formatInt(s.protocols), deltaText(d.protocols)],
      ['Pessoas', NS.formatInt(s.people), deltaText(d.people)],
    ].map(([label, value, sub]) => `<article class="v2-kpi"><span>${label}</span><strong>${value}</strong><small>${sub}</small></article>`).join('');
    $('#v2OperationSecondary').innerHTML = `<span>Finalizados <strong>${NS.formatInt(s.finalized)}</strong></span><span>Em aberto <strong>${NS.formatInt(s.open)}</strong></span><span>Taxa de finalização <strong>${NS.formatPct(s.finalization_rate_pct)}</strong></span><span>Operadores ativos <strong>${NS.formatInt(s.active_operators)}</strong></span>`;

    const showEvolution = hasTemporalEvolution();
    $('#v2VolumeEvolutionPanel')?.classList.toggle('hidden', !showEvolution);
    if (showEvolution) {
      NS.barChart($('#v2VolumeChart'), data.timeline || [], {
        value: row => row.attendances,
        label: row => NS.monthLabel(row.period, true).split('/')[0],
        tooltip: row => `${NS.monthLabel(row.period)} · ${NS.formatInt(row.attendances)} atendimentos · ${NS.formatInt(row.protocols)} protocolos`,
        ariaLabel: 'Volume mensal de atendimentos',
      });
    } else if ($('#v2VolumeChart')) {
      $('#v2VolumeChart').innerHTML = '';
    }

    $('#v2EfficiencyKpis').innerHTML = [
      ['Tempo Médio de Espera (TME)', NS.formatSeconds(s.tme_avg_seconds), 'média do período', 'tme_avg_seconds', s.tme_avg_seconds],
      ['Tempo Médio de Atendimento (TMA)', NS.formatSeconds(s.tma_avg_seconds), 'média do período', 'tma_avg_seconds', s.tma_avg_seconds],
      ['Mediana do atendimento', NS.formatSeconds(s.tma_median_seconds), '50% dos atendimentos abaixo deste valor', null, null],
      ['P90 do atendimento', NS.formatSeconds(s.tma_p90_seconds), '90% dos atendimentos abaixo deste valor', null, null],
    ].map(([label, value, sub, metricKey, raw]) => `<div class="v2-metric-box"><span>${label}</span><strong>${value}</strong><small>${sub}</small>${metricKey ? targetNoteHtml(metricKey, raw) : ''}</div>`).join('');
    const efficiencyReferences = [
      targetReference('tme_avg_seconds', 'TME'),
      targetReference('tma_avg_seconds', 'TMA'),
    ].filter(Boolean);
    $('#v2EfficiencyChart')?.classList.toggle('hidden', !showEvolution);
    if (showEvolution) {
      NS.lineChart($('#v2EfficiencyChart'), data.timeline || [], [
        { key: 'tme_avg_seconds', label: 'Tempo Médio de Espera (TME)', tooltip: row => `${NS.monthLabel(row.period)} · Espera ${NS.formatSeconds(row.tme_avg_seconds)}` },
        { key: 'tma_avg_seconds', label: 'Tempo Médio de Atendimento (TMA)', tooltip: row => `${NS.monthLabel(row.period)} · Atendimento ${NS.formatSeconds(row.tma_avg_seconds)}` },
      ], { formatY: NS.formatSeconds, formatX: row => NS.monthLabel(row.period, true).split('/')[0], ariaLabel: 'Evolução dos tempos médios', references: efficiencyReferences });
    } else if ($('#v2EfficiencyChart')) {
      $('#v2EfficiencyChart').innerHTML = '';
    }

    renderRatingHero($('#v2RatingHero'), s);
    NS.ratingBars($('#v2RatingDistribution'), data.ratings || []);
    $('#v2OverviewExperienceLayout')?.classList.toggle('single-period', !showEvolution);
    $('#v2RatingTimeline')?.classList.toggle('hidden', !showEvolution);
    if (showEvolution) {
      const ratingReference = targetReference('rating_avg', 'Avaliação');
      NS.lineChart($('#v2RatingTimeline'), data.timeline || [], [
        { key: 'rating_avg', label: 'Avaliação média', tooltip: row => `${NS.monthLabel(row.period)} · ${row.rating_avg == null ? 'sem avaliações' : NS.formatRating(row.rating_avg)} · ${NS.formatInt(row.rating_count)} respostas` },
      ], { min: 1, max: 10, formatY: value => NS.formatNumber(value, 0), formatX: row => NS.monthLabel(row.period, true).split('/')[0], ariaLabel: 'Avaliação média mensal', references: ratingReference ? [ratingReference] : [] });
    } else if ($('#v2RatingTimeline')) {
      $('#v2RatingTimeline').innerHTML = '';
    }
  }

  function renderRatingHero(container, summary) {
    if (!container) return;
    const s = summary || {};
    container.innerHTML = `<div class="v2-score"><span>Avaliação média</span><strong>${s.rating_avg == null ? '—' : NS.formatNumber(s.rating_avg, 2) + ' / 10'}</strong><small>somente notas válidas 1–10</small>${targetNoteHtml('rating_avg', s.rating_avg)}</div><div class="v2-score"><span>Avaliações válidas</span><strong>${NS.formatInt(s.rating_count)}</strong><small>${NS.formatInt(s.rating_missing)} sem avaliação</small></div><div class="v2-score"><span>Cobertura</span><strong>${NS.formatPct(s.rating_coverage_pct)}</strong><small>respostas ÷ atendimentos</small>${targetNoteHtml('rating_coverage_pct', s.rating_coverage_pct)}</div>`;
  }

  async function loadPeople(force = false) {
    if (!state.overview || force) await loadOverview(true);
    if (state.entity.profileId) {
      await openProfile(state.entity.kind, state.entity.profileId, false);
      return;
    }
    showExplorer();
    renderEntities();
  }

  function entityItems() {
    const key = state.entity.kind === 'employee' ? 'employees' : 'departments';
    let items = [...(state.overview?.entities?.[key] || [])];
    const search = state.entity.search.trim().toLocaleLowerCase('pt-BR');
    if (search) items = items.filter(item => String(item.name || '').toLocaleLowerCase('pt-BR').includes(search));
    const sort = state.entity.sort;
    items.sort((a, b) => {
      if (sort === 'name-asc') return String(a.name).localeCompare(String(b.name), 'pt-BR');
      if (sort === 'rating-desc') return (b.rating_avg ?? -Infinity) - (a.rating_avg ?? -Infinity);
      if (sort === 'tme-asc') return (a.tme_avg_seconds ?? Infinity) - (b.tme_avg_seconds ?? Infinity);
      if (sort === 'tma-asc') return (a.tma_avg_seconds ?? Infinity) - (b.tma_avg_seconds ?? Infinity);
      return Number(b.attendances || 0) - Number(a.attendances || 0);
    });
    return items;
  }

  function showExplorer() {
    $('#v2EntityExplorer').classList.remove('hidden');
    $('#v2EntityProfile').classList.add('hidden');
    $$('[data-entity-kind]').forEach(button => button.classList.toggle('active', button.dataset.entityKind === state.entity.kind));
    $$('[data-entity-metric]').forEach(button => button.classList.toggle('active', button.dataset.entityMetric === state.entity.metric));
    $('#v2EntitySearch').placeholder = state.entity.kind === 'employee' ? 'Buscar operador…' : 'Buscar departamento…';
    $('#v2EntitySort').value = state.entity.sort;
  }

  function renderEntities() {
    const items = entityItems();
    const metric = state.entity.metric;
    const meta = ENTITY_METRICS[metric] || ENTITY_METRICS.attendances;
    const isEmployee = state.entity.kind === 'employee';
    $('#v2EntityChartKicker').textContent = isEmployee ? 'Operadores' : 'Departamentos';
    $('#v2EntityChartTitle').textContent = isEmployee ? meta.titleEmployee : meta.titleDepartment;
    NS.horizontalBars($('#v2EntityChart'), items, metric, { limit: 12 });

    $('#v2EntityTableHead').innerHTML = isEmployee
      ? '<tr><th>Operador</th><th class="numeric">Atendimentos</th><th class="numeric">Protocolos</th><th class="numeric">Tempo médio de espera</th><th class="numeric">Tempo médio de atendimento</th><th class="numeric">Avaliação</th><th class="numeric">Respostas</th></tr>'
      : '<tr><th>Departamento</th><th class="numeric">Atendimentos</th><th class="numeric">Operadores</th><th class="numeric">Protocolos</th><th class="numeric">Tempo médio de espera</th><th class="numeric">Tempo médio de atendimento</th><th class="numeric">Avaliação</th><th class="numeric">Respostas</th></tr>';
    $('#v2EntityTableBody').innerHTML = items.length ? items.map(item => {
      const rating = item.rating_avg == null ? '<span class="v2-no-rating">—</span>' : `<strong>${NS.formatNumber(item.rating_avg, 2)}</strong><small>/ 10</small>`;
      if (isEmployee) return `<tr data-entity-id="${NS.escapeHtml(item.id)}"><td><strong>${NS.escapeHtml(item.name)}</strong></td><td class="numeric">${NS.formatInt(item.attendances)}</td><td class="numeric">${NS.formatInt(item.protocols)}</td><td class="numeric">${NS.formatSeconds(item.tme_avg_seconds)}</td><td class="numeric">${NS.formatSeconds(item.tma_avg_seconds)}</td><td class="numeric">${rating}</td><td class="numeric">${NS.formatInt(item.rating_count)}</td></tr>`;
      return `<tr data-entity-id="${NS.escapeHtml(item.id)}"><td><strong>${NS.escapeHtml(item.name)}</strong></td><td class="numeric">${NS.formatInt(item.attendances)}</td><td class="numeric">${NS.formatInt(item.active_operators)}</td><td class="numeric">${NS.formatInt(item.protocols)}</td><td class="numeric">${NS.formatSeconds(item.tme_avg_seconds)}</td><td class="numeric">${NS.formatSeconds(item.tma_avg_seconds)}</td><td class="numeric">${rating}</td><td class="numeric">${NS.formatInt(item.rating_count)}</td></tr>`;
    }).join('') : `<tr><td colspan="8"><div class="v2-empty">Nenhum ${isEmployee ? 'operador' : 'departamento'} encontrado.</div></td></tr>`;
  }

  async function openProfile(kind, id, updateUrl = true) {
    state.entity.kind = kind;
    state.entity.profileId = id;
    state.entity.attendances = { data: null, page: 1, pageSize: 20, order: 'newest', ratingFilter: 'all', loading: false };
    if (updateUrl) NS.syncUrl();
    setLoading(true);
    try {
      const params = { ...NS.filterParams(state.filters), kind, entity_id: id };
      // The entity itself overrides the corresponding global filter on the backend.
      if (kind === 'employee') params.employee = '';
      else params.department = '';
      state.entity.profile = await NS.api('/api/dadm/v2/entity', {}, params);
      renderProfile();
    } finally { setLoading(false); }
  }

  function renderProfile() {
    const profile = state.entity.profile;
    if (!profile) return;
    $('#v2EntityExplorer').classList.add('hidden');
    const root = $('#v2EntityProfile');
    root.classList.remove('hidden');
    const s = profile.summary || {};
    const e = profile.entity || {};
    const kindLabel = state.entity.kind === 'employee' ? 'Operadores' : 'Departamentos';
    const compositionTitle = profile.composition_type === 'employee' ? 'Equipe no período' : 'Departamentos no período';
    const showEvolution = hasTemporalEvolution();
    const timelineCards = (profile.timeline || []).map(row => `<div class="v2-month-card"><span>${NS.monthLabel(row.period)}</span><strong>${row.rating_avg == null ? '—' : NS.formatNumber(row.rating_avg, 2) + ' / 10'}</strong><small>${NS.formatInt(row.rating_count)} avaliações · ${NS.formatInt(row.attendances)} atendimentos</small></div>`).join('');
    const evolutionPanel = showEvolution ? `<article class="v2-panel"><div class="v2-panel-head responsive"><div><span class="v2-kicker">Evolução</span><h3>${NS.escapeHtml(e.name || '')} ao longo dos meses</h3></div><select id="v2ProfileMetric"><option value="attendances">Atendimentos</option><option value="tme_avg_seconds">Tempo médio de espera</option><option value="tma_avg_seconds">Tempo médio de atendimento</option><option value="rating_avg" selected>Avaliação média</option></select></div><div class="v2-chart" id="v2ProfileChart"></div></article>` : '';
    const monthlyPanel = showEvolution ? `<article class="v2-panel"><div class="v2-panel-head"><div><span class="v2-kicker">Avaliações por mês</span><h3>Média mensal e quantidade de respostas</h3></div><span class="v2-unit">mês sem avaliação = —</span></div><div class="v2-month-table">${timelineCards || '<div class="v2-empty">Sem meses no recorte.</div>'}</div></article>` : '';
    root.innerHTML = `
      <div class="v2-profile-head"><button type="button" class="v2-profile-back" id="v2ProfileBack" aria-label="Voltar">←</button><div><span class="v2-kicker">${kindLabel}</span><h2>${NS.escapeHtml(e.name || e.id)}</h2><p>${NS.periodLabel(state.filters.fromMonth, state.filters.toMonth)}</p></div><button type="button" class="v2-btn v2-btn-secondary v2-profile-action" id="v2AddProfileCompare">Adicionar à comparação</button></div>
      <div class="v2-profile-kpis">
        ${profileKpi('Atendimentos', NS.formatInt(s.attendances), `${NS.formatInt(s.protocols)} protocolos`)}
        ${profileKpi('Tempo Médio de Espera (TME)', NS.formatSeconds(s.tme_avg_seconds), 'até iniciar o atendimento')}
        ${profileKpi('Tempo Médio de Atendimento (TMA)', NS.formatSeconds(s.tma_avg_seconds), 'duração após o início')}
        ${profileKpi('Avaliação média', s.rating_avg == null ? '—' : NS.formatNumber(s.rating_avg, 2) + ' / 10', `${NS.formatInt(s.rating_count)} avaliações válidas`)}
        ${profileKpi('Cobertura', NS.formatPct(s.rating_coverage_pct), `${NS.formatInt(s.rating_missing)} sem avaliação`)}
      </div>
      <div class="v2-profile-grid ${showEvolution ? '' : 'single-period'}">
        ${evolutionPanel}
        <article class="v2-panel"><div class="v2-panel-head"><div><span class="v2-kicker">Contexto</span><h3>${compositionTitle}</h3></div></div><div class="v2-bars-large" id="v2ProfileComposition"></div></article>
      </div>
      <article class="v2-panel" id="v2ProfileAttendancesPanel">
        <div class="v2-panel-head responsive">
          <div><span class="v2-kicker">Atendimentos individuais</span><h3>Atendimentos do período</h3><p>Consulte cada sessão Tallos que compõe os tempos médios e identifique atendimentos com ou sem avaliação.</p></div>
          <div class="v2-attendance-controls">
            <select id="v2ProfileAttendanceRatingFilter" aria-label="Filtrar atendimentos por avaliação"><option value="all">Todos</option><option value="rated">Com avaliação</option><option value="unrated">Sem avaliação</option></select>
            <select id="v2ProfileAttendanceOrder" aria-label="Ordenar atendimentos"><option value="newest">Mais recentes</option><option value="oldest">Mais antigos</option><option value="tme_high">Maior TME primeiro</option><option value="tma_high">Maior TMA primeiro</option><option value="lowest_rating">Menores notas</option><option value="highest_rating">Maiores notas</option></select>
          </div>
        </div>
        <div id="v2ProfileAttendances"><div class="v2-empty v2-empty-compact">Carregando atendimentos...</div></div>
      </article>
      ${monthlyPanel}
    `;
    if (showEvolution) renderProfileChart('rating_avg');
    NS.horizontalBars($('#v2ProfileComposition'), profile.composition || [], 'attendances', { limit: 10 });
    $('#v2ProfileBack').addEventListener('click', () => {
      state.entity.profileId = '';
      state.entity.profile = null;
      state.entity.attendances = { data: null, page: 1, pageSize: 20, order: 'newest', ratingFilter: 'all', loading: false };
      NS.syncUrl();
      showExplorer();
      renderEntities();
    });
    $('#v2AddProfileCompare').addEventListener('click', () => {
      state.comparison.mode = state.entity.kind;
      state.comparison.ids = [String(e.id)];
      navigate('comparison');
    });
    $('#v2ProfileMetric')?.addEventListener('change', event => renderProfileChart(event.target.value));
    $('#v2ProfileAttendanceRatingFilter').value = state.entity.attendances?.ratingFilter || 'all';
    $('#v2ProfileAttendanceOrder').value = state.entity.attendances?.order || 'newest';
    $('#v2ProfileAttendanceRatingFilter').addEventListener('change', async event => {
      state.entity.attendances.ratingFilter = event.target.value;
      await loadProfileAttendances(1);
    });
    $('#v2ProfileAttendanceOrder').addEventListener('change', async event => {
      state.entity.attendances.order = event.target.value;
      await loadProfileAttendances(1);
    });
    loadProfileAttendances(1);
  }

  function profileKpi(label, value, sub) {
    return `<div class="v2-profile-kpi"><span>${label}</span><strong>${value}</strong><small>${sub}</small></div>`;
  }

  function formatEvaluationDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return '\u2014';
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }

  function evaluationStatusLabel(value) {
    return { finalized: 'Finalizado', open: 'Em aberto', unknown: 'N\u00e3o identificado' }[value] || value || '\u2014';
  }

  async function loadProfileAttendances(page = 1) {
    const target = $('#v2ProfileAttendances');
    if (!target || !state.entity.profileId) return;
    const requestProfileId = String(state.entity.profileId);
    const requestKind = state.entity.kind;
    const attendances = state.entity.attendances || (state.entity.attendances = { data: null, page: 1, pageSize: 20, order: 'newest', ratingFilter: 'all', loading: false });
    attendances.loading = true;
    target.innerHTML = '<div class="v2-empty v2-empty-compact">Carregando atendimentos...</div>';
    try {
      const params = { ...NS.filterParams(state.filters), kind: requestKind, entity_id: requestProfileId, page, page_size: attendances.pageSize || 20, rating_filter: attendances.ratingFilter || 'all', order: attendances.order || 'newest' };
      if (requestKind === 'employee') params.employee = ''; else params.department = '';
      const payload = await NS.api('/api/dadm/v2/entity/attendances', {}, params);
      if (String(state.entity.profileId) !== requestProfileId || state.entity.kind !== requestKind) return;
      attendances.data = payload;
      attendances.page = payload?.pagination?.page || page;
      renderProfileAttendances();
    } catch (error) {
      if (String(state.entity.profileId) !== requestProfileId || state.entity.kind !== requestKind) return;
      target.innerHTML = `<div class="v2-evaluation-error"><strong>N\u00e3o foi poss\u00edvel carregar os atendimentos.</strong><span>${NS.escapeHtml(error?.message || 'Tente novamente.')}</span><button type="button" class="v2-btn v2-btn-secondary" id="v2RetryAttendances">Tentar novamente</button></div>`;
      $('#v2RetryAttendances')?.addEventListener('click', () => loadProfileAttendances(page));
    } finally { attendances.loading = false; }
  }

  function renderProfileAttendances() {
    const target = $('#v2ProfileAttendances');
    const payload = state.entity.attendances?.data;
    if (!target || !payload) return;
    const items = payload.items || [];
    const pg = payload.pagination || {};
    const counts = payload.counts || {};
    const isDepartment = state.entity.kind === 'department';
    const ratingFilter = state.entity.attendances?.ratingFilter || 'all';
    const filterLabel = { all: 'atendimentos', rated: 'atendimentos com avalia\u00e7\u00e3o', unrated: 'atendimentos sem avalia\u00e7\u00e3o' }[ratingFilter] || 'atendimentos';
    if (!items.length) {
      target.innerHTML = `<div class="v2-empty v2-empty-compact">Nenhum ${NS.escapeHtml(filterLabel)} neste recorte.</div>`;
      return;
    }
    const employeeHead = isDepartment ? '<th>Operador</th>' : '';
    const rows = items.map(item => {
      const ratingCell = item.rating == null ? '<span class="v2-rating-missing">Sem avalia\u00e7\u00e3o</span>' : `<span class="v2-rating-badge">${NS.escapeHtml(item.rating)} / 10</span>`;
      return `<tr><td>${NS.escapeHtml(formatEvaluationDate(item.reference_date))}</td>${isDepartment ? `<td><strong>${NS.escapeHtml(item.employee_name || 'Operador sem nome')}</strong></td>` : ''}<td><span class="v2-protocol">${NS.escapeHtml(item.protocol || '\u2014')}</span></td><td class="numeric">${ratingCell}</td><td class="numeric">${NS.escapeHtml(NS.formatSeconds(item.tme_seconds))}</td><td class="numeric">${NS.escapeHtml(NS.formatSeconds(item.tma_seconds))}</td><td>${NS.escapeHtml(item.channel || '\u2014')}</td><td class="wrap">${NS.escapeHtml(item.tabulation || '\u2014')}</td><td><span class="v2-evaluation-status">${NS.escapeHtml(evaluationStatusLabel(item.status))}</span></td></tr>`;
    }).join('');
    target.innerHTML = `<div class="v2-evaluation-summary"><strong>${NS.formatInt(pg.total)} ${NS.escapeHtml(filterLabel)}</strong><span>${NS.formatInt(counts.rated)} com avalia\u00e7\u00e3o \u00b7 ${NS.formatInt(counts.unrated)} sem avalia\u00e7\u00e3o \u00b7 ${NS.formatInt(counts.all)} no total</span></div><div class="v2-table-wrap"><table class="v2-table v2-attendances-table"><thead><tr><th>Data</th>${employeeHead}<th>Protocolo</th><th class="numeric">Nota</th><th class="numeric">TME</th><th class="numeric">TMA</th><th>Canal</th><th>Tabula\u00e7\u00e3o</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div><div class="v2-pagination"><span>P\u00e1gina ${NS.formatInt(pg.page)}${pg.pages ? ` de ${NS.formatInt(pg.pages)}` : ''}</span><div><button type="button" class="v2-btn v2-btn-secondary" id="v2AttendancesPrev" ${pg.has_previous ? '' : 'disabled'}>Anterior</button><button type="button" class="v2-btn v2-btn-secondary" id="v2AttendancesNext" ${pg.has_next ? '' : 'disabled'}>Pr\u00f3xima</button></div></div>`;
    $('#v2AttendancesPrev')?.addEventListener('click', () => { if (pg.has_previous) loadProfileAttendances(Math.max(1, Number(pg.page) - 1)); });
    $('#v2AttendancesNext')?.addEventListener('click', () => { if (pg.has_next) loadProfileAttendances(Number(pg.page) + 1); });
  }

  function renderProfileChart(metric) {
    if (!hasTemporalEvolution()) return;
    const profile = state.entity.profile;
    const meta = PROFILE_METRICS[metric] || PROFILE_METRICS.rating_avg;
    NS.lineChart($('#v2ProfileChart'), profile?.timeline || [], [{ key: metric, label: meta.label, tooltip: row => `${NS.monthLabel(row.period)} · ${meta.format(row[metric])}${metric === 'rating_avg' ? ` · ${NS.formatInt(row.rating_count)} avaliações` : ''}` }], {
      min: metric === 'rating_avg' ? 1 : undefined,
      max: metric === 'rating_avg' ? 10 : undefined,
      formatY: meta.format,
      formatX: row => NS.monthLabel(row.period, true).split('/')[0],
      ariaLabel: `Evolução de ${meta.label}`,
    });
  }

  async function loadExperience(force = false) {
    if (state.experience && !force && state.experience.dimension === state.experienceDimension) { renderExperience(); return; }
    setLoading(true);
    try {
      state.experience = await NS.api('/api/dadm/v2/experience', {}, { ...NS.filterParams(state.filters), dimension: state.experienceDimension });
      renderExperience();
    } finally { setLoading(false); }
  }

  function renderExperience() {
    const data = state.experience || {};
    const s = data.summary || {};
    $('#v2ExperienceSummary').innerHTML = `<div class="v2-score"><span>Avaliação média</span><strong>${s.rating_avg == null ? '—' : NS.formatNumber(s.rating_avg, 2) + ' / 10'}</strong><small>média das avaliações válidas no período</small></div><div class="v2-score"><span>Avaliações válidas</span><strong>${NS.formatInt(s.rating_count)}</strong><small>${NS.formatInt(s.rating_missing)} atendimentos sem avaliação</small></div><div class="v2-score"><span>Cobertura</span><strong>${NS.formatPct(s.rating_coverage_pct)}</strong><small>respostas ÷ atendimentos</small></div>`;
    NS.ratingBars($('#v2ExperienceDistribution'), data.ratings || []);
    const showEvolution = hasTemporalEvolution();
    $('#v2ExperienceCharts')?.classList.toggle('single-period', !showEvolution);
    $('#v2ExperienceEvolutionPanel')?.classList.toggle('hidden', !showEvolution);
    if (showEvolution) {
      NS.lineChart($('#v2ExperienceTimeline'), data.timeline || [], [{ key: 'rating_avg', label: 'Avaliação média', tooltip: row => `${NS.monthLabel(row.period)} · ${row.rating_avg == null ? 'sem avaliações' : NS.formatRating(row.rating_avg)} · ${NS.formatInt(row.rating_count)} respostas` }], { min: 1, max: 10, formatY: value => NS.formatNumber(value, 0), formatX: row => NS.monthLabel(row.period, true).split('/')[0] });
    } else if ($('#v2ExperienceTimeline')) {
      $('#v2ExperienceTimeline').innerHTML = '';
    }
    $$('[data-dimension]').forEach(button => button.classList.toggle('active', button.dataset.dimension === state.experienceDimension));
    $('#v2ExperienceBreakdown').innerHTML = (data.items || []).length ? data.items.map(item => `<tr><td><strong>${NS.escapeHtml(item.name)}</strong></td><td class="numeric">${NS.formatInt(item.attendances)}</td><td class="numeric">${item.rating_avg == null ? '<span class="v2-no-rating">—</span>' : NS.formatNumber(item.rating_avg, 2) + ' / 10'}</td><td class="numeric">${NS.formatInt(item.rating_count)}</td><td class="numeric">${NS.formatPct(item.rating_coverage_pct)}</td><td class="numeric">${NS.formatSeconds(item.tme_avg_seconds)}</td><td class="numeric">${NS.formatSeconds(item.tma_avg_seconds)}</td></tr>`).join('') : '<tr><td colspan="7"><div class="v2-empty">Sem dados para esta dimensão.</div></td></tr>';
  }

  async function loadComparison(force = false) {
    updateComparisonOptions();
    renderComparisonMode();
    if (state.comparison.mode !== 'period' && state.comparison.ids.length) await renderEntityComparison();
  }

  function updateComparisonOptions() {
    const select = $('#v2CompareEntitySelect');
    if (!select || !state.context) return;
    const kind = state.comparison.mode === 'department' ? 'department' : 'employee';
    const items = kind === 'department' ? state.context.departments : state.context.employees;
    select.innerHTML = '<option value="">Selecione…</option>' + items.filter(item => !state.comparison.ids.includes(String(item.value))).map(item => `<option value="${NS.escapeHtml(item.value)}">${NS.escapeHtml(item.label)}</option>`).join('');
    $('#v2CompareEntityTitle').textContent = kind === 'department' ? 'Departamentos' : 'Operadores';
  }

  function renderComparisonMode() {
    $$('[data-compare-mode]').forEach(button => button.classList.toggle('active', button.dataset.compareMode === state.comparison.mode));
    const periodMode = state.comparison.mode === 'period';
    $('#v2EntityCompareBox').classList.toggle('hidden', periodMode);
    $('#v2PeriodCompareBox').classList.toggle('hidden', !periodMode);
    if (periodMode) {
      ensureCompareRanges();
      renderCompareRangeLabels();
      return;
    }
    renderCompareChips();
  }

  function compareItemLabel(id) {
    const items = state.comparison.mode === 'department' ? state.context?.departments : state.context?.employees;
    return selectedLabel(items, id) || id;
  }

  function renderCompareChips() {
    $('#v2CompareChips').innerHTML = state.comparison.ids.length ? state.comparison.ids.map(id => `<span class="v2-selected-chip">${NS.escapeHtml(compareItemLabel(id))}<button type="button" data-remove-compare="${NS.escapeHtml(id)}" aria-label="Remover">×</button></span>`).join('') : '<span class="v2-unit">Selecione uma entidade. Uma única seleção já mostra sua evolução; outras transformam a leitura em comparação.</span>';
    updateComparisonOptions();
    if (!state.comparison.ids.length) $('#v2CompareResults').innerHTML = '';
  }

  async function renderEntityComparison() {
    const kind = state.comparison.mode;
    const ids = state.comparison.ids.slice(0, 4);
    if (!ids.length) return;
    setLoading(true);
    try {
      const profiles = await Promise.all(ids.map(id => {
        const params = { ...NS.filterParams(state.filters), kind, entity_id: id };
        if (kind === 'employee') params.employee = ''; else params.department = '';
        return NS.api('/api/dadm/v2/entity', {}, params);
      }));
      const names = profiles.map(p => p.entity?.name || p.entity?.id || '—');
      const metrics = [
        ['Atendimentos', p => NS.formatInt(p.summary?.attendances)],
        ['Tempo médio de espera', p => NS.formatSeconds(p.summary?.tme_avg_seconds)],
        ['Tempo médio de atendimento', p => NS.formatSeconds(p.summary?.tma_avg_seconds)],
        ['Avaliação média', p => p.summary?.rating_avg == null ? '—' : NS.formatNumber(p.summary.rating_avg, 2) + ' / 10'],
        ['Cobertura das avaliações', p => NS.formatPct(p.summary?.rating_coverage_pct)],
      ];
      const table = `<article class="v2-panel v2-compare-table"><div class="v2-table-wrap"><table class="v2-table"><thead><tr><th>Métrica</th>${names.map(name => `<th class="numeric">${NS.escapeHtml(name)}</th>`).join('')}</tr></thead><tbody>${metrics.map(([label, getter]) => `<tr><td><strong>${label}</strong></td>${profiles.map(p => `<td class="numeric">${getter(p)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></article>`;
      const root = $('#v2CompareResults');
      const singleMonth = !hasTemporalEvolution();
      const chartKicker = singleMonth ? 'Comparação do mês' : 'Evolução';
      const chartTitle = singleMonth ? 'Resultado das entidades no período' : 'Evolução mensal das entidades';
      root.innerHTML = `${table}<article class="v2-panel"><div class="v2-panel-head responsive"><div><span class="v2-kicker">${chartKicker}</span><h3>${chartTitle}</h3></div><select id="v2CompareMetric"><option value="rating_avg">Avaliação média</option><option value="attendances">Atendimentos</option><option value="tme_avg_seconds">Tempo médio de espera</option><option value="tma_avg_seconds">Tempo médio de atendimento</option></select></div><div class="v2-chart" id="v2CompareChart"></div></article>`;
      const draw = metric => drawProfilesComparison(profiles, metric);
      draw('rating_avg');
      $('#v2CompareMetric').addEventListener('change', event => draw(event.target.value));
    } finally { setLoading(false); }
  }

  function drawProfilesComparison(profiles, metric) {
    const periods = [...new Set(profiles.flatMap(p => (p.timeline || []).map(row => row.period)))].sort();
    const maps = profiles.map(profile => new Map((profile.timeline || []).map(row => [row.period, row])));
    const rows = periods.map(period => ({ period, values: maps.map(map => map.get(period)?.[metric] ?? null), samples: maps.map(map => map.get(period)?.rating_count ?? 0) }));
    const meta = PROFILE_METRICS[metric] || PROFILE_METRICS.rating_avg;
    const series = profiles.map((profile, index) => ({
      label: profile.entity?.name || `Série ${index + 1}`,
      value: row => row.values[index],
      tooltip: row => `${NS.monthLabel(row.period)} · ${profile.entity?.name || ''} · ${meta.format(row.values[index])}${metric === 'rating_avg' ? ` · ${NS.formatInt(row.samples[index])} avaliações` : ''}`,
    }));
    if (!hasTemporalEvolution()) {
      const period = state.filters.toMonth || periods[0] || '';
      NS.snapshotComparisonChart($('#v2CompareChart'), profiles, metric, {
        period,
        format: meta.format,
        min: metric === 'rating_avg' ? 1 : 0,
        max: metric === 'rating_avg' ? 10 : undefined,
        rating: metric === 'rating_avg',
      });
      return;
    }
    NS.lineChart($('#v2CompareChart'), rows, series, {
      min: metric === 'rating_avg' ? 1 : undefined,
      max: metric === 'rating_avg' ? 10 : undefined,
      formatY: meta.format,
      formatX: row => NS.monthLabel(row.period, true).split('/')[0],
    });
  }

  function ensureCompareRanges() {
    if (!state.comparison.rangeA) state.comparison.rangeA = { fromMonth: state.filters.fromMonth, toMonth: state.filters.toMonth };
    if (!state.comparison.rangeB) {
      const span = Math.max(1, NS.monthIndex(state.filters.toMonth) - NS.monthIndex(state.filters.fromMonth) + 1);
      const end = NS.shiftMonth(state.filters.fromMonth, -1);
      state.comparison.rangeB = { fromMonth: NS.shiftMonth(end, -(span - 1)), toMonth: end };
    }
  }

  function renderCompareRangeLabels() {
    ensureCompareRanges();
    $('#v2CompareRangeALabel').textContent = NS.periodLabel(state.comparison.rangeA.fromMonth, state.comparison.rangeA.toMonth);
    $('#v2CompareRangeBLabel').textContent = NS.periodLabel(state.comparison.rangeB.fromMonth, state.comparison.rangeB.toMonth);
  }

  async function comparePeriods() {
    ensureCompareRanges();
    const base = { department: state.filters.department, employee: state.filters.employee, channel: state.filters.channel, status: state.filters.status, tabulation: state.filters.tabulation, comparison: 'none' };
    setLoading(true);
    try {
      const [a, b] = await Promise.all([
        NS.api('/api/dadm/v2/overview', {}, { ...base, from_month: state.comparison.rangeA.fromMonth, to_month: state.comparison.rangeA.toMonth }),
        NS.api('/api/dadm/v2/overview', {}, { ...base, from_month: state.comparison.rangeB.fromMonth, to_month: state.comparison.rangeB.toMonth }),
      ]);
      const metrics = [
        ['Atendimentos', 'attendances', NS.formatInt],
        ['Tempo médio de espera', 'tme_avg_seconds', NS.formatSeconds],
        ['Tempo médio de atendimento', 'tma_avg_seconds', NS.formatSeconds],
        ['Avaliação média', 'rating_avg', value => value == null ? '—' : NS.formatNumber(value, 2) + ' / 10'],
        ['Cobertura das avaliações', 'rating_coverage_pct', NS.formatPct],
      ];
      const root = $('#v2PeriodCompareResults');
      root.innerHTML = `<article class="v2-panel"><div class="v2-table-wrap"><table class="v2-table"><thead><tr><th>Métrica</th><th class="numeric">${NS.escapeHtml(NS.periodLabel(state.comparison.rangeA.fromMonth, state.comparison.rangeA.toMonth))}</th><th class="numeric">${NS.escapeHtml(NS.periodLabel(state.comparison.rangeB.fromMonth, state.comparison.rangeB.toMonth))}</th><th class="numeric">Diferença</th></tr></thead><tbody>${metrics.map(([label, key, fmt]) => {
        const av = a.summary?.[key], bv = b.summary?.[key];
        let diff = '—';
        if (av != null && bv != null) {
          if (key.includes('seconds')) diff = NS.formatSeconds(Math.abs(Number(av) - Number(bv))) + (Number(av) >= Number(bv) ? ' a mais' : ' a menos');
          else if (key === 'rating_avg') diff = `${Number(av) - Number(bv) >= 0 ? '+' : ''}${NS.formatNumber(Number(av) - Number(bv), 2)}`;
          else if (key === 'rating_coverage_pct') diff = `${Number(av) - Number(bv) >= 0 ? '+' : ''}${NS.formatNumber(Number(av) - Number(bv), 1)} p.p.`;
          else diff = `${Number(av) - Number(bv) >= 0 ? '+' : ''}${NS.formatInt(Number(av) - Number(bv))}`;
        }
        return `<tr><td><strong>${label}</strong></td><td class="numeric">${fmt(av)}</td><td class="numeric">${fmt(bv)}</td><td class="numeric">${diff}</td></tr>`;
      }).join('')}</tbody></table></div></article>`;
    } finally { setLoading(false); }
  }

  function canWrite() {
    return Boolean(state.access?.canEdit);
  }

  function managementInputValue(metricKey, value) {
    if (value === null || value === undefined || value === '') return '';
    return managementMetric(metricKey)?.unit === 'seconds' ? NS.formatNumber(Number(value) / 60, 2) : String(value);
  }

  function managementStoredValue(metricKey, value) {
    if (value === null || value === undefined || String(value).trim() === '') return null;
    const parsed = Number(String(value).replace(',', '.'));
    if (!Number.isFinite(parsed)) return value;
    return managementMetric(metricKey)?.unit === 'seconds' ? parsed * 60 : parsed;
  }

  function managementUnitHelp(metricKey) {
    const unit = managementMetric(metricKey)?.unit;
    if (unit === 'seconds') return 'Informe o valor em minutos. O sistema armazena o equivalente em segundos para manter o mesmo contrato analítico dos gráficos.';
    if (unit === 'rating_10') return 'Use a escala TALLOS de 1 a 10.';
    if (unit === 'percent') return 'Informe um percentual entre 0 e 100.';
    return '';
  }

  function scopeOptions(scopeType, currentValue = '') {
    const c = state.context || {};
    let items = [];
    if (scopeType === 'department') items = c.departments || [];
    else if (scopeType === 'channel') items = c.channels || [];
    else if (scopeType === 'employee') items = c.employees || [];
    const normalized = items.map(item => ({ value: String(item.value), label: String(item.label || item.value) }));
    if (currentValue && !normalized.some(item => item.value === currentValue)) normalized.unshift({ value: currentValue, label: currentValue });
    return normalized;
  }

  function scopeValueField(scopeType, value = '') {
    if (!scopeType || scopeType === 'TOTAL') return '<input type="hidden" id="v2MgmtScopeValue" value="">';
    const items = scopeOptions(scopeType, value);
    const label = scopeType === 'department' ? 'Departamento' : scopeType === 'channel' ? 'Canal' : 'Operador';
    return `<label id="v2MgmtScopeValueWrap"><span>${label}</span><select id="v2MgmtScopeValue" required><option value="">Selecione</option>${items.map(item => `<option value="${NS.escapeHtml(item.value)}" ${item.value === value ? 'selected' : ''}>${NS.escapeHtml(item.label)}</option>`).join('')}</select></label>`;
  }

  function dueDateDefault() {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    const pad = value => String(value).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  async function loadManagement(force = false) {
    setLoading(true);
    try {
      const tasks = [];
      if (!state.overview || force) tasks.push(NS.api('/api/dadm/v2/overview', {}, { ...NS.filterParams(state.filters), comparison: 'previous_period' }).then(data => { state.overview = data; }));
      tasks.push(ensureManagement(force));
      await Promise.all(tasks);
      renderManagement();
    } finally { setLoading(false); }
  }

  function renderManagement() {
    const s = state.overview?.summary || {};
    const cards = [
      ['tme_avg_seconds', 'Tempo Médio de Espera', s.tme_avg_seconds],
      ['tma_avg_seconds', 'Tempo Médio de Atendimento', s.tma_avg_seconds],
      ['rating_avg', 'Avaliação média', s.rating_avg],
      ['rating_coverage_pct', 'Cobertura das avaliações', s.rating_coverage_pct],
    ];
    $('#v2ManagementSummary').innerHTML = cards.map(([key, label, value]) => {
      const status = targetStatus(key, value);
      const target = status.target;
      const metric = managementMetric(key);
      const symbol = metric?.direction === 'lower' ? '≤' : '≥';
      return `<article class="v2-management-card"><span>${NS.escapeHtml(label)}</span><strong>${NS.escapeHtml(formatManagementValue(key, value))}</strong><small>${target ? `Meta vigente ${symbol} ${NS.escapeHtml(formatManagementValue(key, target.target))}` : 'Nenhuma meta vigente para este recorte.'}</small><span class="v2-target-state ${status.key}">${NS.escapeHtml(status.label)}</span></article>`;
    }).join('');

    const targets = state.management?.targets || [];
    $('#v2TargetsTable').innerHTML = targets.length ? targets.map(row => {
      const metric = managementMetric(row.metric_key);
      const actions = canWrite() ? `<div class="v2-row-actions"><button type="button" data-target-edit="${row.id}" data-write-action>Editar</button><button type="button" class="danger" data-target-delete="${row.id}" data-write-action>Excluir</button></div>` : '—';
      return `<tr><td><strong>${NS.escapeHtml(row.indicator_code)}</strong></td><td>${NS.escapeHtml(metric?.label || row.metric_key)}</td><td>${NS.escapeHtml(row.scope_label || 'Institucional')}</td><td>${NS.escapeHtml(row.valid_from)}${row.valid_to ? ` → ${NS.escapeHtml(row.valid_to)}` : ' em diante'}</td><td>${NS.escapeHtml(formatManagementValue(row.metric_key, row.target))}</td><td>${NS.escapeHtml(formatManagementValue(row.metric_key, row.attention))}</td><td>${actions}</td></tr>`;
    }).join('') : '<tr><td colspan="7"><div class="v2-empty">Nenhuma meta TALLOS V2 cadastrada.</div></td></tr>';

    const actions = state.management?.actions || [];
    $('#v2ActionsTable').innerHTML = actions.length ? actions.map(row => {
      const rowActions = canWrite() ? `<div class="v2-row-actions"><button type="button" data-action-edit="${row.id}" data-write-action>Editar</button><button type="button" class="danger" data-action-delete="${row.id}" data-write-action>Excluir</button></div>` : '—';
      const statusClass = row.status === 'Concluído' ? 'good' : row.status === 'Atrasado' ? 'bad' : '';
      return `<tr><td><strong>${NS.escapeHtml(row.indicator_code)}</strong><small>${NS.escapeHtml(managementMetric(row.metric_key)?.label || '')}</small></td><td>${NS.escapeHtml(row.period)}</td><td>${NS.escapeHtml(row.scope_label || 'Institucional')}</td><td class="wrap">${NS.escapeHtml(row.problem || '')}</td><td class="wrap">${NS.escapeHtml(row.corrective_action || '')}</td><td>${NS.escapeHtml(row.responsible || '—')}</td><td>${NS.escapeHtml(row.due_date || '—')}</td><td><span class="v2-badge ${statusClass}">${NS.escapeHtml(row.status || 'Aberto')}</span></td><td>${rowActions}</td></tr>`;
    }).join('') : '<tr><td colspan="9"><div class="v2-empty">Nenhum plano de ação TALLOS V2 cadastrado.</div></td></tr>';
    applyAccessMode();
  }

  function closeManagementModal() {
    hideLayer($('#v2ManagementModal'));
  }

  function bindScopeSelector(scopeType, scopeValue = '') {
    const select = $('#v2MgmtScopeType');
    if (!select) return;
    const render = () => {
      const old = $('#v2MgmtScopeValueWrap') || $('#v2MgmtScopeValue');
      const holder = document.createElement('div');
      holder.innerHTML = scopeValueField(select.value, select.value === scopeType ? scopeValue : '');
      const node = holder.firstElementChild;
      if (old?.id === 'v2MgmtScopeValue') old.replaceWith(node);
      else old?.replaceWith(node);
    };
    select.addEventListener('change', () => { scopeType = ''; scopeValue = ''; render(); });
  }

  function openTargetModal(row = null) {
    if (!canWrite()) return;
    const metrics = state.management?.catalog?.metrics || [];
    const scopes = state.management?.catalog?.target_scope_types || [];
    const metricKey = row?.metric_key || metrics[0]?.key || 'tme_avg_seconds';
    const scopeType = row?.scope_type && row.scope_type !== 'legacy' ? row.scope_type : 'TOTAL';
    $('#v2ManagementModalKicker').textContent = 'Meta TALLOS V2';
    $('#v2ManagementModalTitle').textContent = row ? 'Editar meta' : 'Nova meta';
    $('#v2ManagementModalBody').innerHTML = `<form class="v2-management-form" id="v2TargetForm">
      <label><span>Métrica</span><select id="v2MgmtMetric" required>${metrics.map(item => `<option value="${NS.escapeHtml(item.key)}" ${item.key === metricKey ? 'selected' : ''}>${NS.escapeHtml(item.indicator_code)} · ${NS.escapeHtml(item.label)}</option>`).join('')}</select></label>
      <label><span>Recorte</span><select id="v2MgmtScopeType">${scopes.map(item => `<option value="${NS.escapeHtml(item.value)}" ${item.value === scopeType ? 'selected' : ''}>${NS.escapeHtml(item.label)}</option>`).join('')}</select></label>
      ${scopeValueField(scopeType, row?.scope_value || '')}
      <label><span>Vigência inicial</span><input type="month" id="v2MgmtValidFrom" value="${NS.escapeHtml(row?.valid_from || state.filters.toMonth || state.currentMonth)}" required></label>
      <label><span>Vigência final</span><input type="month" id="v2MgmtValidTo" value="${NS.escapeHtml(row?.valid_to || '')}"></label>
      <label><span>Meta</span><input type="number" id="v2MgmtTarget" step="0.01" value="${NS.escapeHtml(managementInputValue(metricKey, row?.target))}" required></label>
      <label><span>Faixa de atenção</span><input type="number" id="v2MgmtAttention" step="0.01" value="${NS.escapeHtml(managementInputValue(metricKey, row?.attention))}"></label>
      <label class="span-2"><span>Justificativa</span><textarea id="v2MgmtJustification">${NS.escapeHtml(row?.justification || '')}</textarea></label>
      <div class="v2-form-help" id="v2MgmtUnitHelp">${NS.escapeHtml(managementUnitHelp(metricKey))}</div>
      <div class="v2-form-errors hidden" id="v2MgmtFormErrors"></div>
      <div class="v2-modal-actions"><button type="button" class="v2-btn v2-btn-secondary" id="v2MgmtCancel">Cancelar</button><button type="submit" class="v2-btn v2-btn-primary">Salvar meta</button></div>
    </form>`;
    showLayer($('#v2ManagementModal'));
    bindScopeSelector(scopeType, row?.scope_value || '');
    $('#v2MgmtMetric').addEventListener('change', event => { $('#v2MgmtUnitHelp').textContent = managementUnitHelp(event.target.value); $('#v2MgmtTarget').value = ''; $('#v2MgmtAttention').value = ''; });
    $('#v2MgmtCancel').addEventListener('click', closeManagementModal);
    $('#v2TargetForm').addEventListener('submit', event => saveTargetForm(event, row?.id || null));
  }

  async function saveTargetForm(event, rowId) {
    event.preventDefault();
    const metricKey = $('#v2MgmtMetric').value;
    const metric = managementMetric(metricKey);
    const payload = {
      indicator_code: metric?.indicator_code,
      metric_key: metricKey,
      scope_type: $('#v2MgmtScopeType').value,
      scope_value: $('#v2MgmtScopeValue')?.value || null,
      valid_from: $('#v2MgmtValidFrom').value,
      valid_to: $('#v2MgmtValidTo').value || null,
      target: managementStoredValue(metricKey, $('#v2MgmtTarget').value),
      attention: managementStoredValue(metricKey, $('#v2MgmtAttention').value),
      justification: $('#v2MgmtJustification').value.trim() || null,
    };
    const errors = $('#v2MgmtFormErrors');
    setLoading(true);
    try {
      await NS.api(rowId ? `/api/dadm/v2/targets/${rowId}` : '/api/dadm/v2/targets', { method: rowId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      closeManagementModal();
      alertUser(rowId ? 'Meta atualizada.' : 'Meta criada.', 'success');
      state.management = null;
      await ensureManagement(true);
      renderManagement();
      if (state.overview) renderOverview();
    } catch (error) {
      errors.textContent = error.message;
      errors.classList.remove('hidden');
    } finally { setLoading(false); }
  }

  function openActionModal(row = null) {
    if (!canWrite()) return;
    const metrics = state.management?.catalog?.metrics || [];
    const scopes = state.management?.catalog?.action_scope_types || [];
    const metricKey = row?.metric_key || metrics[0]?.key || 'tme_avg_seconds';
    const scopeType = row?.scope_type && row.scope_type !== 'legacy' ? row.scope_type : (state.filters.employee ? 'employee' : state.filters.department ? 'department' : state.filters.channel ? 'channel' : 'TOTAL');
    const scopeValue = row?.scope_value || (scopeType === 'employee' ? state.filters.employee : scopeType === 'department' ? state.filters.department : scopeType === 'channel' ? state.filters.channel : '');
    $('#v2ManagementModalKicker').textContent = 'Plano de ação';
    $('#v2ManagementModalTitle').textContent = row ? 'Editar plano de ação' : 'Novo plano de ação';
    $('#v2ManagementModalBody').innerHTML = `<form class="v2-management-form" id="v2ActionForm">
      <label><span>Métrica relacionada</span><select id="v2MgmtMetric" required>${metrics.map(item => `<option value="${NS.escapeHtml(item.key)}" ${item.key === metricKey ? 'selected' : ''}>${NS.escapeHtml(item.indicator_code)} · ${NS.escapeHtml(item.label)}</option>`).join('')}</select></label>
      <label><span>Período</span><input type="month" id="v2MgmtPeriod" value="${NS.escapeHtml(row?.period || state.filters.toMonth || state.currentMonth)}" required></label>
      <label><span>Recorte</span><select id="v2MgmtScopeType">${scopes.map(item => `<option value="${NS.escapeHtml(item.value)}" ${item.value === scopeType ? 'selected' : ''}>${NS.escapeHtml(item.label)}</option>`).join('')}</select></label>
      ${scopeValueField(scopeType, scopeValue)}
      <label class="span-2"><span>Problema identificado</span><textarea id="v2MgmtProblem" required>${NS.escapeHtml(row?.problem || '')}</textarea></label>
      <label class="span-2"><span>Causa provável</span><textarea id="v2MgmtCause">${NS.escapeHtml(row?.probable_cause || '')}</textarea></label>
      <label class="span-2"><span>Ação corretiva</span><textarea id="v2MgmtCorrective" required>${NS.escapeHtml(row?.corrective_action || '')}</textarea></label>
      <label><span>Responsável</span><input type="text" id="v2MgmtResponsible" value="${NS.escapeHtml(row?.responsible || state.user?.nome || '')}" required></label>
      <label><span>Prazo</span><input type="date" id="v2MgmtDue" value="${NS.escapeHtml(row?.due_date || dueDateDefault())}" required></label>
      <label><span>Status</span><select id="v2MgmtStatus">${['Aberto','Em andamento','Concluído','Atrasado','Cancelado'].map(value => `<option ${value === (row?.status || 'Aberto') ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
      <label><span>Evidência / observação</span><input type="text" id="v2MgmtEvidence" value="${NS.escapeHtml(row?.evidence || '')}"></label>
      <div class="v2-form-errors hidden" id="v2MgmtFormErrors"></div>
      <div class="v2-modal-actions"><button type="button" class="v2-btn v2-btn-secondary" id="v2MgmtCancel">Cancelar</button><button type="submit" class="v2-btn v2-btn-primary">Salvar plano</button></div>
    </form>`;
    showLayer($('#v2ManagementModal'));
    bindScopeSelector(scopeType, scopeValue);
    $('#v2MgmtCancel').addEventListener('click', closeManagementModal);
    $('#v2ActionForm').addEventListener('submit', event => saveActionForm(event, row?.id || null));
  }

  async function saveActionForm(event, rowId) {
    event.preventDefault();
    const metricKey = $('#v2MgmtMetric').value;
    const metric = managementMetric(metricKey);
    const payload = {
      indicator_code: metric?.indicator_code,
      metric_key: metricKey,
      period: $('#v2MgmtPeriod').value,
      scope_type: $('#v2MgmtScopeType').value,
      scope_value: $('#v2MgmtScopeValue')?.value || null,
      problem: $('#v2MgmtProblem').value.trim(),
      probable_cause: $('#v2MgmtCause').value.trim() || null,
      corrective_action: $('#v2MgmtCorrective').value.trim(),
      responsible: $('#v2MgmtResponsible').value.trim(),
      due_date: $('#v2MgmtDue').value,
      status: $('#v2MgmtStatus').value,
      evidence: $('#v2MgmtEvidence').value.trim() || null,
    };
    const errors = $('#v2MgmtFormErrors');
    setLoading(true);
    try {
      await NS.api(rowId ? `/api/dadm/v2/actions/${rowId}` : '/api/dadm/v2/actions', { method: rowId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      closeManagementModal();
      alertUser(rowId ? 'Plano de ação atualizado.' : 'Plano de ação criado.', 'success');
      state.management = null;
      await ensureManagement(true);
      renderManagement();
    } catch (error) {
      errors.textContent = error.message;
      errors.classList.remove('hidden');
    } finally { setLoading(false); }
  }

  async function deleteManagementRecord(kind, rowId) {
    if (!canWrite()) return;
    const label = kind === 'target' ? 'esta meta' : 'este plano de ação';
    if (!window.confirm(`Excluir ${label}? O registro será removido, mas os fatos TALLOS não serão alterados.`)) return;
    setLoading(true);
    try {
      await NS.api(kind === 'target' ? `/api/dadm/v2/targets/${rowId}` : `/api/dadm/v2/actions/${rowId}`, { method: 'DELETE' });
      alertUser(kind === 'target' ? 'Meta excluída.' : 'Plano de ação excluído.', 'success');
      state.management = null;
      await ensureManagement(true);
      renderManagement();
      if (kind === 'target' && state.overview) renderOverview();
    } finally { setLoading(false); }
  }

  async function loadIntegration() {
    setLoading(true);
    try {
      const [connection, quality, runs, maps] = await Promise.all([
        loadConnection(),
        NS.api('/api/dadm/v2/quality'),
        NS.api('/api/dadm/tallos/sync-runs', {}, { limit: 20 }),
        NS.api('/api/dadm/tallos/department-map'),
      ]);
      state.quality = quality;
      state.syncRuns = runs.items || [];
      state.departmentMaps = maps.items || [];
      renderIntegration(connection);
    } finally { setLoading(false); }
  }

  function renderIntegration(connection) {
    const configured = Boolean(connection?.configured);
    const badge = $('#v2ConnectionBadge');
    badge.textContent = configured ? 'Conectado' : 'Não configurado';
    badge.className = `v2-badge ${configured ? 'good' : 'bad'}`;
    const sourceText = connection?.token_source === 'local_env_file' ? '.env local' : connection?.token_source === 'environment' ? 'ambiente do servidor' : 'não configurado';
    let body = `<div class="v2-info-row"><span>Fonte</span><strong>TALLOS / RD Station Conversas</strong></div><div class="v2-info-row"><span>Token</span><strong>${NS.escapeHtml(sourceText)}</strong></div><div class="v2-info-row"><span>Registros analíticos</span><strong>${NS.formatInt(connection?.attendance_count)}</strong></div>`;
    if (connection?.token_management_enabled) {
      const tokenAction = configured ? 'Validar e substituir' : 'Validar e salvar';
      const tokenLabel = configured ? 'Substituir token TALLOS neste ambiente local' : 'Token TALLOS para homologação local';
      body += `<label class="v2-token-field"><span>${tokenLabel}</span><div class="du-password"><input class="du-control" type="password" id="v2LocalToken" autocomplete="off" placeholder="Cole o token apenas neste ambiente"><button type="button" class="du-password-toggle" data-du-password-toggle="#v2LocalToken" aria-label="Mostrar valor"></button></div><button type="button" class="v2-btn v2-btn-primary" id="v2SaveToken" data-write-action>${tokenAction}</button></label>`;
    }
    $('#v2ConnectionBody').innerHTML = body;
    $('#v2TestConnection').dataset.writeUnavailable = (!configured && !connection?.token_management_enabled) ? '1' : '0';
    $('#v2StartSync').dataset.writeUnavailable = configured ? '0' : '1';
    $('#v2SaveToken')?.addEventListener('click', saveLocalToken);
    window.DataUNIVC?.hydrate?.();

    $('#v2QualityList').innerHTML = (state.quality?.issues || []).map(item => `<div class="v2-quality-item ${item.count ? 'issue' : ''}"><span>${NS.escapeHtml(item.label)}</span><strong>${NS.formatInt(item.count)}</strong></div>`).join('') || '<div class="v2-empty">Sem diagnóstico disponível.</div>';
    renderSyncRuns();
    renderDepartmentMaps();
    applyAccessMode();
    if (!$('#v2SyncStart').value) {
      const latest = state.context?.available_range?.end_month || state.filters.toMonth;
      const bounds = NS.monthBounds(latest);
      if (bounds) { $('#v2SyncStart').value = bounds.start; $('#v2SyncEnd').value = bounds.end; }
    }
  }

  function renderDepartmentMaps() {
    const body = $('#v2DepartmentMapTable');
    if (!body) return;
    const rows = state.departmentMaps || [];
    body.innerHTML = rows.length ? rows.map(row => {
      const key = NS.escapeHtml(row.source_key || '');
      if (!canWrite()) {
        return `<tr data-map-key="${key}"><td><code>${key}</code></td><td>${NS.escapeHtml(row.display_name || '')}</td><td>${row.active ? 'Sim' : 'Não'}</td><td>${NS.escapeHtml(row.notes || '—')}</td><td>—</td></tr>`;
      }
      return `<tr data-map-key="${key}"><td><code>${key}</code></td><td><input class="v2-map-input" data-map-name value="${NS.escapeHtml(row.display_name || '')}"></td><td><input class="v2-map-check" data-map-active type="checkbox" ${row.active ? 'checked' : ''}></td><td><input class="v2-map-input" data-map-notes value="${NS.escapeHtml(row.notes || '')}"></td><td><button type="button" class="v2-btn v2-btn-secondary" data-map-save data-write-action>Salvar</button></td></tr>`;
    }).join('') : '<tr><td colspan="5"><div class="v2-empty">Nenhum identificador de departamento coletado.</div></td></tr>';
  }

  async function saveDepartmentMap(row) {
    if (!canWrite()) return;
    const key = row?.dataset.mapKey || '';
    const name = $('[data-map-name]', row)?.value.trim() || '';
    const active = Boolean($('[data-map-active]', row)?.checked);
    const notes = $('[data-map-notes]', row)?.value.trim() || '';
    if (!name) { alertUser('Informe o nome exibido do departamento.', 'error'); return; }
    setLoading(true);
    try {
      await NS.api(`/api/dadm/tallos/department-map/${encodeURIComponent(key)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: name, active, notes: notes || null }) });
      alertUser('Mapeamento de departamento atualizado.', 'success');
      const payload = await NS.api('/api/dadm/tallos/department-map');
      state.departmentMaps = payload.items || [];
      renderDepartmentMaps();
      state.overview = null;
      state.experience = null;
      state.management = null;
      await loadContext();
      if (state.view !== 'integration') await loadCurrentView(true);
    } finally { setLoading(false); }
  }

  async function testConnection() {
    if (!canWrite()) { alertUser('Você está consultando a DADM em modo somente leitura.', 'error'); return; }
    const input = $('#v2LocalToken');
    const token = input?.value.trim() || '';
    if (!state.connection?.configured && !token) { alertUser('Informe o token para testar a conexão local.', 'error'); return; }
    setLoading(true);
    try {
      const result = await NS.api('/api/dadm/tallos/test-connection', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: token || null }) });
      alertUser(result.mensagem || 'Conexão validada.', 'success');
    } finally { setLoading(false); }
  }

  async function saveLocalToken() {
    if (!canWrite()) { alertUser('Você está consultando a DADM em modo somente leitura.', 'error'); return; }
    const token = $('#v2LocalToken')?.value.trim() || '';
    if (!token) { alertUser('Informe o token TALLOS.', 'error'); return; }
    setLoading(true);
    try {
      const result = await NS.api('/api/dadm/tallos/config/token', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) });
      alertUser(result.mensagem || 'Token salvo.', 'success');
      await loadIntegration(true);
    } finally { setLoading(false); }
  }

  function renderSyncRuns() {
    const statusLabels = { queued: 'Preparando', running: 'Em andamento', completed: 'Concluído', failed: 'Falhou' };
    $('#v2SyncRuns').innerHTML = state.syncRuns.length ? state.syncRuns.map(run => `<tr><td>${NS.escapeHtml(run.start_date)} → ${NS.escapeHtml(run.end_date)}</td><td><span class="v2-badge ${run.status === 'completed' ? 'good' : run.status === 'failed' ? 'bad' : ''}">${NS.escapeHtml(statusLabels[run.status] || run.status)}</span></td><td class="numeric">${NS.formatInt(run.records_received)}</td><td class="numeric">${NS.formatInt(run.records_inserted)}</td><td class="numeric">${NS.formatInt(run.records_updated)}</td><td class="numeric">${NS.formatInt(run.records_unchanged)}</td><td>${run.finished_at ? NS.formatDateTime(run.finished_at) : '—'}</td></tr>`).join('') : '<tr><td colspan="7"><div class="v2-empty">Nenhuma sincronização registrada.</div></td></tr>';
    const active = state.syncRuns.find(run => ['queued', 'running'].includes(run.status));
    const progress = $('#v2SyncProgress');
    if (!active) {
      window.DataUNIVC?.progress?.hide(progress);
      state.syncProgress = { runId: null, maxPct: 0 };
      return;
    }
    if (state.syncProgress.runId !== active.id) state.syncProgress = { runId: active.id, maxPct: 0 };
    const expected = Number(active.total_expected || 0);
    const received = Number(active.records_received || 0);
    const preparing = active.status === 'queued' || !expected;
    let pct = preparing ? null : Math.min(99, received / expected * 100);
    if (pct != null) {
      state.syncProgress.maxPct = Math.max(state.syncProgress.maxPct || 0, pct);
      pct = state.syncProgress.maxPct;
    }
    const progressApi = window.DataUNIVC?.progress;
    if (progressApi) {
      progressApi.render(progress, {
        title: preparing ? `Preparando sincronização TALLOS #${NS.formatInt(active.id)}` : `Sincronizando TALLOS #${NS.formatInt(active.id)}`,
        message: preparing ? 'Mapeando os blocos do período e fixando o total esperado antes de iniciar o processamento.' : `${NS.formatInt(received)} de ${NS.formatInt(expected)} atendimentos processados.`,
        percent: pct,
        stage: preparing ? 'Planejando páginas e registros' : `Processando página ${NS.formatInt(active.pages_processed + 1)}`,
        meta: [
          { label: 'Novos', value: NS.formatInt(active.records_inserted) },
          { label: 'Atualizados', value: NS.formatInt(active.records_updated) },
          { label: 'Sem alteração', value: NS.formatInt(active.records_unchanged) },
          { label: 'Falhas', value: NS.formatInt(active.records_failed) },
        ],
      });
    } else {
      progress.classList.remove('hidden');
      progress.innerHTML = `<strong>${preparing ? 'Preparando sincronização' : `Sincronizando · ${NS.formatPct(pct, 0)}`}</strong><div>${NS.formatInt(received)} recebidos</div>`;
    }
  }

  async function startSync() {
    if (!canWrite()) { alertUser('Você está consultando a DADM em modo somente leitura.', 'error'); return; }
    const start = $('#v2SyncStart').value, end = $('#v2SyncEnd').value;
    if (!start || !end) { alertUser('Escolha as duas datas no calendário.', 'error'); return; }
    if (!state.connection?.configured) { alertUser('Configure a conexão TALLOS antes de sincronizar.', 'error'); return; }
    setLoading(true);
    try {
      const result = await NS.api('/api/dadm/tallos/sync', { method: 'POST' }, { inicio: start, fim: end });
      alertUser(result.mensagem || 'Sincronização iniciada.', 'success');
      pollSync();
    } finally { setLoading(false); }
  }

  function pollSync() {
    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      try {
        const payload = await NS.api('/api/dadm/tallos/sync-runs', {}, { limit: 20 });
        state.syncRuns = payload.items || [];
        renderSyncRuns();
        if (!state.syncRuns.some(run => ['queued', 'running'].includes(run.status)) || attempts >= 240) {
          window.clearInterval(timer);
          state.overview = null;
          state.experience = null;
          await loadConnection();
          await loadContext();
          await loadIntegration(true);
        }
      } catch { window.clearInterval(timer); }
    }, 2500);
  }

  function openPeriodPicker(target = 'global') {
    state.picker.target = target;
    let range;
    if (target === 'global') range = { fromMonth: state.filters.fromMonth, toMonth: state.filters.toMonth };
    else if (target === 'compareA') range = state.comparison.rangeA;
    else range = state.comparison.rangeB;
    const start = range?.fromMonth || state.filters.fromMonth || state.currentMonth;
    const end = range?.toMonth || start;
    state.picker.start = start;
    state.picker.end = end;
    state.picker.phase = 'start';
    state.picker.year = Number((start || state.currentMonth).slice(0, 4));
    renderMonthPicker();
    showLayer($('#v2PeriodModal'));
  }

  function closePeriodPicker() { hideLayer($('#v2PeriodModal')); }

  function renderMonthPicker() {
    const names = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    $('#v2PickerYear').textContent = String(state.picker.year);
    const startIdx = NS.monthIndex(state.picker.start), endIdx = NS.monthIndex(state.picker.end);
    const availableStart = NS.monthIndex(state.context?.available_range?.start_month || '');
    const availableEnd = NS.monthIndex(state.context?.available_range?.end_month || '');
    $('#v2MonthGrid').innerHTML = names.map((name, index) => {
      const month = `${state.picker.year}-${String(index + 1).padStart(2, '0')}`;
      const idx = NS.monthIndex(month);
      const selected = month === state.picker.start || month === state.picker.end;
      const inRange = startIdx != null && endIdx != null && idx > Math.min(startIdx, endIdx) && idx < Math.max(startIdx, endIdx);
      const unavailable = availableStart != null && availableEnd != null && (idx < availableStart || idx > availableEnd);
      return `<button type="button" data-picker-month="${month}" class="${selected ? 'selected' : inRange ? 'in-range' : ''} ${unavailable ? 'unavailable' : ''}">${name}</button>`;
    }).join('');
    $('#v2PendingStart').textContent = NS.monthLabel(state.picker.start);
    $('#v2PendingEnd').textContent = state.picker.end ? NS.monthLabel(state.picker.end) : 'Escolha o fim';
  }

  function pickMonth(month) {
    if (state.picker.phase === 'start') {
      state.picker.start = month;
      state.picker.end = '';
      state.picker.phase = 'end';
    } else {
      if (NS.monthIndex(month) < NS.monthIndex(state.picker.start)) {
        state.picker.end = state.picker.start;
        state.picker.start = month;
      } else {
        state.picker.end = month;
      }
      state.picker.phase = 'start';
    }
    renderMonthPicker();
  }

  function applyShortcut(shortcut) {
    const current = state.currentMonth;
    if (shortcut === 'current') { state.picker.start = current; state.picker.end = current; }
    else if (shortcut === 'previous') { const m = NS.shiftMonth(current, -1); state.picker.start = m; state.picker.end = m; }
    else if (shortcut === 'year') { state.picker.start = `${current.slice(0, 4)}-01`; state.picker.end = current; }
    else {
      const count = Number(shortcut || 1);
      state.picker.end = current;
      state.picker.start = NS.shiftMonth(current, -(count - 1));
    }
    state.picker.phase = 'start';
    state.picker.year = Number(state.picker.end.slice(0, 4));
    renderMonthPicker();
  }

  async function applyPeriodPicker() {
    const start = state.picker.start;
    const end = state.picker.end || start;
    if (!start) return;
    if (state.picker.target === 'global') {
      state.filters.fromMonth = start;
      state.filters.toMonth = end;
      state.overview = null;
      state.experience = null;
      closePeriodPicker();
      await refreshForContext();
    } else {
      const range = { fromMonth: start, toMonth: end };
      if (state.picker.target === 'compareA') state.comparison.rangeA = range;
      else state.comparison.rangeB = range;
      closePeriodPicker();
      renderCompareRangeLabels();
    }
  }

  async function clearFilters() {
    state.filters.department = '';
    state.filters.employee = '';
    state.filters.channel = '';
    state.filters.status = '';
    state.filters.tabulation = '';
    state.overview = null;
    state.experience = null;
    await refreshForContext();
  }

  function openSidebar() {
    $('#v2Sidebar').classList.add('open');
    showLayer($('#v2SidebarBackdrop'));
  }
  function closeSidebar() {
    $('#v2Sidebar').classList.remove('open');
    hideLayer($('#v2SidebarBackdrop'), 220);
  }

  function bindEvents() {
    document.addEventListener('click', async event => {
      const nav = event.target.closest('[data-view]');
      if (nav) { navigate(nav.dataset.view); return; }
      const jump = event.target.closest('[data-view-jump]');
      if (jump) { navigate(jump.dataset.viewJump); return; }
      const kind = event.target.closest('[data-entity-kind]');
      if (kind) { state.entity.kind = kind.dataset.entityKind; state.entity.profileId = ''; state.entity.search = ''; $('#v2EntitySearch').value = ''; NS.syncUrl(); showExplorer(); renderEntities(); return; }
      const metric = event.target.closest('[data-entity-metric]');
      if (metric) { state.entity.metric = metric.dataset.entityMetric; NS.syncUrl(); showExplorer(); renderEntities(); return; }
      const row = event.target.closest('#v2EntityTableBody tr[data-entity-id], #v2EntityChart [data-entity-id]');
      if (row?.dataset.entityId) { await openProfile(state.entity.kind, row.dataset.entityId); return; }
      const dim = event.target.closest('[data-dimension]');
      if (dim) { state.experienceDimension = dim.dataset.dimension; state.experience = null; await loadExperience(true); return; }
      const mode = event.target.closest('[data-compare-mode]');
      if (mode) {
        state.comparison.mode = mode.dataset.compareMode;
        if (state.comparison.mode !== 'period') state.comparison.ids = [];
        renderComparisonMode();
        updateComparisonOptions();
        return;
      }
      const removeCompare = event.target.closest('[data-remove-compare]');
      if (removeCompare) { state.comparison.ids = state.comparison.ids.filter(id => id !== removeCompare.dataset.removeCompare); renderCompareChips(); if (state.comparison.ids.length) await renderEntityComparison(); return; }
      const range = event.target.closest('[data-compare-range]');
      if (range) { openPeriodPicker(range.dataset.compareRange === 'A' ? 'compareA' : 'compareB'); return; }
      const month = event.target.closest('[data-picker-month]');
      if (month) { pickMonth(month.dataset.pickerMonth); return; }
      const shortcut = event.target.closest('[data-period-shortcut]');
      if (shortcut) { applyShortcut(shortcut.dataset.periodShortcut); return; }
      const targetEdit = event.target.closest('[data-target-edit]');
      if (targetEdit) { openTargetModal((state.management?.targets || []).find(item => String(item.id) === targetEdit.dataset.targetEdit) || null); return; }
      const targetDelete = event.target.closest('[data-target-delete]');
      if (targetDelete) { await deleteManagementRecord('target', targetDelete.dataset.targetDelete); return; }
      const actionEdit = event.target.closest('[data-action-edit]');
      if (actionEdit) { openActionModal((state.management?.actions || []).find(item => String(item.id) === actionEdit.dataset.actionEdit) || null); return; }
      const actionDelete = event.target.closest('[data-action-delete]');
      if (actionDelete) { await deleteManagementRecord('action', actionDelete.dataset.actionDelete); return; }
      const mapSave = event.target.closest('[data-map-save]');
      if (mapSave) { await saveDepartmentMap(mapSave.closest('tr')); return; }
      const removeFilter = event.target.closest('[data-remove-filter]');
      if (removeFilter) { state.filters[removeFilter.dataset.removeFilter] = ''; state.overview = null; state.experience = null; await refreshForContext(); return; }
    });

    $('#v2PeriodButton').addEventListener('click', () => openPeriodPicker('global'));
    $('#v2ClosePeriod').addEventListener('click', closePeriodPicker);
    $('#v2CancelPeriod').addEventListener('click', closePeriodPicker);
    $('#v2PeriodModal').addEventListener('click', event => { if (event.target === $('#v2PeriodModal')) closePeriodPicker(); });
    $('#v2YearPrev').addEventListener('click', () => { state.picker.year -= 1; renderMonthPicker(); });
    $('#v2YearNext').addEventListener('click', () => { state.picker.year += 1; renderMonthPicker(); });
    $('#v2ApplyPeriod').addEventListener('click', applyPeriodPicker);

    $('#v2Department').addEventListener('change', async event => { state.filters.department = event.target.value; state.filters.employee = ''; state.overview = null; state.experience = null; await refreshForContext(); });
    $('#v2Employee').addEventListener('change', async event => { state.filters.employee = event.target.value; state.overview = null; state.experience = null; await refreshForContext(); });
    $('#v2MoreFilters').addEventListener('click', () => toggleLayer($('#v2FilterPopover')));
    $('#v2CloseFilters').addEventListener('click', () => hideLayer($('#v2FilterPopover')));
    $('#v2ApplyExtra').addEventListener('click', async () => {
      state.filters.channel = $('#v2Channel').value;
      state.filters.status = $('#v2Status').value;
      state.filters.tabulation = $('#v2Tabulation').value;
      hideLayer($('#v2FilterPopover'));
      state.overview = null; state.experience = null;
      await refreshForContext();
    });
    $('#v2ClearFilters').addEventListener('click', clearFilters);

    $('#v2EntitySearch').addEventListener('input', event => { state.entity.search = event.target.value; renderEntities(); });
    $('#v2EntitySort').addEventListener('change', event => { state.entity.sort = event.target.value; renderEntities(); });

    $('#v2CompareAdd').addEventListener('click', async () => {
      const value = $('#v2CompareEntitySelect').value;
      if (!value || state.comparison.ids.includes(value)) return;
      state.comparison.ids.push(value);
      if (state.comparison.ids.length > 4) state.comparison.ids = state.comparison.ids.slice(-4);
      renderCompareChips();
      await renderEntityComparison();
    });
    $('#v2ComparePeriods').addEventListener('click', comparePeriods);

    $('#v2NewTarget').addEventListener('click', () => openTargetModal());
    $('#v2NewAction').addEventListener('click', () => openActionModal());
    $('#v2CloseManagementModal').addEventListener('click', closeManagementModal);
    $('#v2ManagementModal').addEventListener('click', event => { if (event.target === $('#v2ManagementModal')) closeManagementModal(); });
    $('#v2DirectorateSelect').addEventListener('change', event => {
      const route = window.DataUNIVC?.routeForDirectorate?.(event.target.value);
      if (route) location.assign(route);
    });
    $('#v2ReportButton').addEventListener('click', openReportModal);
    $('#v2CloseReportModal').addEventListener('click', closeReportModal);
    $('#v2CancelReport').addEventListener('click', closeReportModal);
    $('#v2GenerateReport').addEventListener('click', generateReport);
    $('#v2ReportModal').addEventListener('click', event => { if (event.target === $('#v2ReportModal')) closeReportModal(); });

    $('#v2TestConnection').addEventListener('click', testConnection);
    $('#v2StartSync').addEventListener('click', startSync);
    ['#v2SyncStart', '#v2SyncEnd'].forEach(selector => {
      const input = $(selector);
      input.addEventListener('click', () => { try { input.showPicker?.(); } catch {} });
    });

    $('#v2Logout')?.addEventListener('click', async () => { await window.DataUnivcAuth.logout(); location.assign('/'); });

    $('#v2MobileMenu').addEventListener('click', openSidebar);
    $('#v2SidebarBackdrop').addEventListener('click', closeSidebar);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        closePeriodPicker();
        closeManagementModal();
        closeReportModal();
        hideLayer($('#v2FilterPopover'));
        closeSidebar();
      }
    });
  }

  async function initialize() {
    setLoading(true);
    try {
      if (!(await loadUser())) return;
      bindEvents();
      window.DataUNIVC?.sidebar?.mount?.({ sidebar: '#v2Sidebar', button: '#v2SidebarCollapse', collapsedClass: 'v2-sidebar-collapsed', storageKey: 'data-univc-sidebar', breakpoint: 850 });
      window.DataUNIVC?.hydrate?.();
      await loadConnection();
      await loadContext();
      // First open defaults to the latest month present in the analytical base.
      if (!new URLSearchParams(location.search).get('from') && state.context?.available_range?.end_month) {
        state.filters.fromMonth = state.context.available_range.end_month;
        state.filters.toMonth = state.context.available_range.end_month;
        await loadContext();
      }
      navigate(state.view);
    } catch (error) {
      alertUser(error.message, 'error', 0);
    } finally { setLoading(false); }
  }

  document.addEventListener('DOMContentLoaded', initialize);
})();
