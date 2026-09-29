(() => {
  const API_BASE = '/api/surveys/faculty-student';
  const moduleState = {
    directorate: null,
    loaded: false,
    bound: false,
    view: 'overview',
    questionScope: 'all',
    filters: { semester: '', course_id: '', discipline_id: '', teacher_id: '' },
    facets: { semesters: [], courses: [], disciplines: [], teachers: [], offerings: [], matching_contexts: 0 },
    overview: null,
    operational: null,
    questions: [],
    teachers: [],
    disciplines: [],
    semesterComparison: [],
    importHistory: [],
    identityQuality: null,
    methodology: null,
    teacherSearch: '',
    disciplineSearch: '',
    loadSerial: 0,
    periodInitialized: false,
  };

  const byId = id => document.getElementById(id);
  const number = (value, decimals = 0) => formatNumber(Number(value || 0), decimals);
  const pct = value => value === null || value === undefined ? '—' : `${formatNumber(Number(value), 1)}%`;
  const safeId = value => value === '' || value === null || value === undefined ? '' : String(value);


  function normalizeComboboxText(value) {
    return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').trim();
  }

  function comboboxOptionButtons(select, query = '') {
    const needle = normalizeComboboxText(query);
    const options = Array.from(select.options || []);
    return options.filter((item, index) => {
      if (!needle) return true;
      if (index === 0 && !item.value) return false;
      return normalizeComboboxText(item.textContent).includes(needle);
    });
  }

  function closeFacultyCombobox(shell, { restore = true } = {}) {
    if (!shell) return;
    const menu = shell.querySelector('.faculty-combobox-menu');
    const input = shell.querySelector('.faculty-combobox-input');
    shell.classList.remove('open');
    input?.setAttribute('aria-expanded', 'false');
    if (menu) menu.hidden = true;
    shell.dataset.activeIndex = '-1';
    if (restore) {
      const select = byId(shell.dataset.selectId || '');
      if (select && input) {
        const selected = select.options[select.selectedIndex];
        input.value = selected && selected.value ? selected.textContent : '';
      }
    }
  }

  function renderFacultyComboboxMenu(select, shell, query = '') {
    const menu = shell?.querySelector('.faculty-combobox-menu');
    if (!menu) return;
    const matches = comboboxOptionButtons(select, query);
    if (!matches.length) {
      menu.innerHTML = '<div class="faculty-combobox-empty">Nenhuma opção encontrada.</div>';
      shell.dataset.activeIndex = '-1';
      return;
    }
    menu.innerHTML = matches.map((item, index) => `
      <button type="button" class="faculty-combobox-option${String(item.value) === String(select.value) ? ' selected' : ''}" role="option" aria-selected="${String(item.value) === String(select.value) ? 'true' : 'false'}" data-combobox-value="${escapeHtml(item.value)}" data-combobox-index="${index}">
        ${escapeHtml(item.textContent || '')}
      </button>`).join('');
    menu.querySelectorAll('.faculty-combobox-option').forEach(button => {
      button.addEventListener('mousedown', event => event.preventDefault());
      button.addEventListener('click', () => {
        select.value = button.dataset.comboboxValue || '';
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeFacultyCombobox(shell);
      });
    });
  }

  function openFacultyCombobox(select, shell, query = '') {
    const menu = shell?.querySelector('.faculty-combobox-menu');
    const input = shell?.querySelector('.faculty-combobox-input');
    if (!menu || !input) return;
    renderFacultyComboboxMenu(select, shell, query);
    menu.hidden = false;
    shell.classList.add('open');
    input.setAttribute('aria-expanded', 'true');
  }

  function setComboboxActive(shell, delta) {
    const buttons = Array.from(shell?.querySelectorAll('.faculty-combobox-option') || []);
    if (!buttons.length) return;
    let current = Number(shell.dataset.activeIndex || -1);
    current = Math.max(0, Math.min(buttons.length - 1, current + delta));
    shell.dataset.activeIndex = String(current);
    buttons.forEach((button, index) => button.classList.toggle('active', index === current));
    buttons[current]?.scrollIntoView({ block: 'nearest' });
  }

  function syncFacultyCombobox(select) {
    if (!select) return;
    let shell = select.nextElementSibling;
    if (!shell || !shell.classList.contains('faculty-combobox')) return;
    const input = shell.querySelector('.faculty-combobox-input');
    const clear = shell.querySelector('.faculty-combobox-clear');
    const selected = select.options[select.selectedIndex];
    if (input && document.activeElement !== input) input.value = selected && selected.value ? selected.textContent : '';
    if (clear) clear.hidden = !select.value;
    if (shell.classList.contains('open')) renderFacultyComboboxMenu(select, shell, input?.value || '');
  }

  function enhanceFacultyCombobox(select) {
    if (!select) return;
    let shell = select.nextElementSibling;
    if (!shell || !shell.classList.contains('faculty-combobox')) {
      shell = document.createElement('div');
      shell.className = 'faculty-combobox';
      shell.dataset.selectId = select.id;
      shell.dataset.activeIndex = '-1';
      shell.innerHTML = `
        <div class="faculty-combobox-control">
          <input class="faculty-combobox-input" type="search" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" placeholder="${escapeHtml(select.dataset.comboboxPlaceholder || 'Buscar...')}">
          <button class="faculty-combobox-clear" type="button" aria-label="Limpar seleção" title="Limpar seleção">×</button>
          <button class="faculty-combobox-toggle" type="button" aria-label="Abrir opções" title="Abrir opções">⌄</button>
        </div>
        <div class="faculty-combobox-menu" role="listbox" hidden></div>`;
      select.insertAdjacentElement('afterend', shell);
      select.classList.add('faculty-combobox-native-hidden');

      const input = shell.querySelector('.faculty-combobox-input');
      const toggle = shell.querySelector('.faculty-combobox-toggle');
      const clear = shell.querySelector('.faculty-combobox-clear');
      input?.addEventListener('focus', () => { input.select(); openFacultyCombobox(select, shell, ''); });
      input?.addEventListener('input', () => openFacultyCombobox(select, shell, input.value));
      input?.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          if (!shell.classList.contains('open')) openFacultyCombobox(select, shell, input.value);
          setComboboxActive(shell, 1);
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          if (!shell.classList.contains('open')) openFacultyCombobox(select, shell, input.value);
          setComboboxActive(shell, -1);
        } else if (event.key === 'Enter' && shell.classList.contains('open')) {
          const active = shell.querySelector('.faculty-combobox-option.active');
          if (active) {
            event.preventDefault();
            active.click();
          }
        } else if (event.key === 'Escape') {
          event.preventDefault();
          closeFacultyCombobox(shell);
        }
      });
      input?.addEventListener('blur', () => setTimeout(() => closeFacultyCombobox(shell), 100));
      toggle?.addEventListener('mousedown', event => event.preventDefault());
      toggle?.addEventListener('click', () => {
        if (shell.classList.contains('open')) closeFacultyCombobox(shell, { restore: false });
        else {
          input?.focus();
          openFacultyCombobox(select, shell, '');
        }
      });
      clear?.addEventListener('mousedown', event => event.preventDefault());
      clear?.addEventListener('click', () => {
        select.value = '';
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeFacultyCombobox(shell);
      });
      select.addEventListener('change', () => syncFacultyCombobox(select));
    }
    syncFacultyCombobox(select);
  }

  function reset() {
    moduleState.directorate = null;
    moduleState.loaded = false;
    moduleState.view = 'overview';
    moduleState.questionScope = 'all';
    moduleState.filters = { semester: '', course_id: '', discipline_id: '', teacher_id: '' };
    moduleState.facets = { semesters: [], courses: [], disciplines: [], teachers: [], offerings: [], matching_contexts: 0 };
    moduleState.overview = null;
    moduleState.operational = null;
    moduleState.questions = [];
    moduleState.teachers = [];
    moduleState.disciplines = [];
    moduleState.semesterComparison = [];
    moduleState.importHistory = [];
    moduleState.identityQuality = null;
    moduleState.methodology = null;
    moduleState.teacherSearch = '';
    moduleState.disciplineSearch = '';
    moduleState.periodInitialized = false;
    moduleState.loadSerial += 1;
  }

  function filterParams(filters = moduleState.filters) {
    const params = new URLSearchParams();
    if (filters.semester) params.set('semester', filters.semester);
    if (filters.course_id) params.set('course_id', filters.course_id);
    if (filters.discipline_id) params.set('discipline_id', filters.discipline_id);
    if (filters.teacher_id) params.set('teacher_id', filters.teacher_id);
    return params;
  }

  function withQuery(path, params) {
    const query = params?.toString?.() || '';
    return `${API_BASE}${path}${query ? `?${query}` : ''}`;
  }

  function showLoading(visible, message = 'Consultando os dados oficiais do módulo.') {
    const el = byId('facultyLoadingState');
    if (!el) return;
    el.classList.toggle('hidden', !visible);
    const span = el.querySelector('span');
    if (span) span.textContent = message;
  }

  function showError(error = null) {
    const el = byId('facultyErrorState');
    if (!el) return;
    if (!error) {
      el.classList.add('hidden');
      el.innerHTML = '';
      return;
    }
    el.classList.remove('hidden');
    el.innerHTML = `<strong>Não foi possível carregar esta análise.</strong><span>${escapeHtml(error.message || String(error))}</span>`;
  }

  function setView(view, { load = true } = {}) {
    moduleState.view = view;
    document.querySelectorAll('#facultyViewTabs [data-faculty-view]').forEach(button => {
      button.classList.toggle('active', button.dataset.facultyView === view);
    });
    document.querySelectorAll('[data-faculty-panel]').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.facultyPanel === view);
    });
    byId('facultyFilterShell')?.classList.toggle('hidden', view === 'imports');
    if (load && moduleState.loaded) loadCurrentView(true);
  }

  function reconcileFilters(facets) {
    let changed = false;
    const f = moduleState.filters;
    const allowed = {
      semester: new Set((facets.semesters || []).map(String)),
      course_id: new Set((facets.courses || []).map(item => String(item.id))),
      discipline_id: new Set((facets.disciplines || []).map(item => String(item.id))),
      teacher_id: new Set((facets.teachers || []).map(item => String(item.id))),
    };
    Object.keys(allowed).forEach(key => {
      if (f[key] && !allowed[key].has(String(f[key]))) {
        f[key] = '';
        changed = true;
      }
    });
    return changed;
  }

  async function loadFacets() {
    let facets = await api(withQuery('/analytics/filters', filterParams()), { blocking: false });
    if (reconcileFilters(facets)) {
      facets = await api(withQuery('/analytics/filters', filterParams()), { blocking: false });
      reconcileFilters(facets);
    }
    if (!moduleState.periodInitialized) {
      moduleState.periodInitialized = true;
      const latestSemester = (facets.semesters || [])[0];
      if (!moduleState.filters.semester && latestSemester) {
        moduleState.filters.semester = String(latestSemester);
        facets = await api(withQuery('/analytics/filters', filterParams()), { blocking: false });
        reconcileFilters(facets);
      }
    }
    moduleState.facets = facets;
    renderFilters();
  }

  function renderFilters() {
    const facets = moduleState.facets || {};
    const f = moduleState.filters;
    const semester = byId('facultySemesterFilter');
    const course = byId('facultyCourseFilter');
    const discipline = byId('facultyDisciplineFilter');
    const teacher = byId('facultyTeacherFilter');
    if (!semester || !course || !discipline || !teacher) return;

    semester.innerHTML = option('', !f.semester, 'Todos os semestres') + (facets.semesters || []).map(value => option(value, value === f.semester, formatMonth(value, true))).join('');
    course.innerHTML = option('', !f.course_id, 'Todos os cursos') + (facets.courses || []).map(item => option(String(item.id), String(item.id) === String(f.course_id), item.name)).join('');
    discipline.innerHTML = option('', !f.discipline_id, 'Todas as disciplinas') + (facets.disciplines || []).map(item => option(String(item.id), String(item.id) === String(f.discipline_id), `${item.name} · ${item.course_name}`)).join('');
    teacher.innerHTML = option('', !f.teacher_id, 'Todos os docentes') + (facets.teachers || []).map(item => option(String(item.id), String(item.id) === String(f.teacher_id), item.name)).join('');
    enhanceFacultyCombobox(course);
    enhanceFacultyCombobox(discipline);
    enhanceFacultyCombobox(teacher);

    const labels = [];
    const semesterLabel = f.semester ? formatMonth(f.semester, true) : '';
    const courseItem = (facets.courses || []).find(item => String(item.id) === String(f.course_id));
    const disciplineItem = (facets.disciplines || []).find(item => String(item.id) === String(f.discipline_id));
    const teacherItem = (facets.teachers || []).find(item => String(item.id) === String(f.teacher_id));
    if (semesterLabel) labels.push(semesterLabel);
    if (courseItem) labels.push(courseItem.name);
    if (disciplineItem) labels.push(disciplineItem.name);
    if (teacherItem) labels.push(teacherItem.name);
    const context = byId('facultyFilterContext');
    if (context) context.innerHTML = `<strong>${number(facets.matching_contexts || 0)} contexto(s)</strong> no recorte${labels.length ? ` · ${labels.map(escapeHtml).join(' · ')}` : ' · todo o histórico disponível'}`;
  }

  function summaryCard(label, value, sub, primary = false) {
    return `<article class="faculty-metric-card ${primary ? 'primary' : ''}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></article>`;
  }

  function signedPp(value) {
    if (value === null || value === undefined) return '—';
    const n = Number(value);
    return `${n > 0 ? '+' : ''}${formatNumber(n, 1)} pp`;
  }

  function readinessClass(value) {
    if (value === 'ready') return 'ok';
    if (value === 'ready_no_goal') return 'warning';
    if (String(value || '').startsWith('blocked')) return 'error';
    return 'neutral';
  }

  function renderOperationalStatus(summary) {
    const target = byId('facultyOperationalStatus');
    if (!target) return;
    const op = moduleState.operational || {};
    const quality = op.quality || {};
    const latest = op.latest_import || {};
    const period = op.current_period ? formatMonth(op.current_period, true) : 'sem período';
    const lastImport = latest.last_activity_at || latest.created_at;
    const importText = lastImport ? formatImportDate(lastImport) : 'nenhuma importação';
    const userText = latest.last_imported_by ? ` · ${latest.last_imported_by}` : '';
    const action = op.readiness === 'ready_no_goal'
      ? '<button class="button secondary compact" id="facultyOperationalAction" type="button" data-action="goals">Configurar meta</button>'
      : op.readiness === 'blocked_identity'
        ? '<button class="button secondary compact" id="facultyOperationalAction" type="button" data-action="imports">Revisar importações</button>'
        : op.readiness === 'blocked_scale'
          ? '<button class="button secondary compact" id="facultyOperationalAction" type="button" data-action="questions">Revisar perguntas</button>'
          : op.readiness === 'no_data'
            ? '<button class="button secondary compact" id="facultyOperationalAction" type="button" data-action="import">Importar relatório</button>'
            : '';
    target.innerHTML = `<div class="faculty-readiness ${readinessClass(op.readiness)}"><div class="faculty-readiness-main"><span>Prontidão do indicador · ${escapeHtml(period)}</span><strong>${escapeHtml(op.readiness_message || 'Sem diagnóstico operacional.')}</strong>${action}</div><div class="faculty-operational-facts"><div><span>Participações</span><strong>${number(summary.respondent_participations || 0)}</strong></div><div><span>Docentes</span><strong>${number(summary.teachers || 0)}</strong></div><div><span>Disciplinas</span><strong>${number(summary.disciplines || 0)}</strong></div><div><span>Contextos</span><strong>${number(summary.contexts || 0)}</strong></div><div><span>Qualidade</span><strong>${number(quality.blocking_issue_count || 0)} bloqueio(s) · ${number(quality.warning_count || 0)} aviso(s)</strong></div><div><span>Última importação</span><strong>${escapeHtml(importText)}${escapeHtml(userText)}</strong></div></div></div>`;
    byId('facultyOperationalAction')?.addEventListener('click', event => {
      const actionName = event.currentTarget.dataset.action;
      if (actionName === 'goals') navigate('metas');
      else if (actionName === 'imports') setView('imports');
      else if (actionName === 'questions') setView('questions');
      else if (actionName === 'import') triggerImport();
    });
  }

  function renderOverview() {
    const response = moduleState.overview || {};
    const summary = response.summary || {};
    const fav = summary.favorability || {};
    const op = moduleState.operational || {};
    const goal = op.goal || {};
    moduleState.methodology = response.methodology || op.methodology || moduleState.methodology;
    const cards = byId('facultyOverviewCards');
    const previousLabel = op.previous_period ? `vs. ${formatMonth(op.previous_period, true)}` : 'sem semestre anterior comparável';
    const goalValue = goal.meta === null || goal.meta === undefined ? 'Sem meta' : pct(goal.meta);
    const goalSub = goal.meta === null || goal.meta === undefined
      ? 'Cadastre uma meta percentual para o KPI 02'
      : `${op.goal_status || 'Sem status'} · ${goal.origem || goal.recorte || 'meta vigente'}`;
    if (cards) {
      cards.innerHTML = [
        summaryCard('Favorabilidade docente', fav.mapping_complete === false ? 'Revisar escala' : pct(fav.favorable_percentage), 'Perguntas do docente · indicador derivado', true),
        summaryCard('Variação semestral', signedPp(op.delta_percentage_points), previousLabel),
        summaryCard('Meta vigente', goalValue, goalSub),
        summaryCard('Cobertura classificada', pct(fav.classified_coverage_percentage), `${number(fav.classified_total || 0)} classificadas · ${number(fav.unclassified_total || 0)} fora do denominador`),
      ].join('');
    }

    const warning = byId('facultyMethodWarning');
    if (warning) {
      const unmapped = Number(fav.unmapped_total || 0);
      warning.classList.toggle('hidden', fav.mapping_complete !== false);
      warning.innerHTML = fav.mapping_complete === false
        ? `<strong>Há ${number(unmapped)} resposta(s) em categoria ainda não mapeada.</strong> A favorabilidade sintética foi suspensa neste recorte para evitar um percentual incompleto. A distribuição original continua disponível em Perguntas.`
        : '';
    }
    renderOperationalStatus(summary);
    renderComposition(fav);
    renderSemesterTrend();
    renderQuestionHighlights();
  }

  function renderComposition(fav) {
    const target = byId('facultyComposition');
    if (!target) return;
    const source = Number(fav.source_total || 0);
    if (!source) {
      target.innerHTML = '<div class="faculty-empty"><strong>Sem respostas no recorte</strong>Importe um relatório ou altere os filtros.</div>';
      return;
    }
    const rows = [
      ['Favoráveis', Number(fav.favorable || 0), 'favorable'],
      ['Intermediárias', Number(fav.intermediate || 0), 'intermediate'],
      ['Desfavoráveis', Number(fav.unfavorable || 0), 'unfavorable'],
      ['Não classificáveis', Number(fav.unclassified_total || 0) + Number(fav.unmapped_total || 0), 'unclassified'],
    ];
    target.innerHTML = rows.map(([label, count, cls]) => {
      const percentage = source ? count / source * 100 : 0;
      return `<div class="faculty-composition-row ${cls}"><div class="faculty-composition-label">${escapeHtml(label)}</div><div class="faculty-composition-track"><div class="faculty-composition-fill" style="width:${Math.max(0, Math.min(100, percentage))}%"></div></div><div class="faculty-composition-value">${formatNumber(percentage, 1)}%</div></div>`;
    }).join('') + `<div class="faculty-composition-note">Base visual: ${number(source)} seleções nas perguntas sobre o docente. A favorabilidade usa apenas favoráveis + intermediárias + desfavoráveis como denominador; “Não sei” permanece fora desse cálculo.</div>`;
  }

  function renderSemesterTrend() {
    const timeline = (moduleState.semesterComparison || []).map(item => ({
      periodo: item.semester,
      valor: item.summary?.favorability?.mapping_complete === false ? null : item.summary?.favorability?.favorable_percentage,
      meta: item.goal?.meta ?? null,
      meta_recorte: item.goal?.origem || item.goal?.recorte || null,
      meta_vigencia: item.goal?.vigencia || null,
      status: item.goal_status || null,
      respondentes: item.summary?.respondent_participations || 0,
      classificados: item.summary?.favorability?.classified_total || 0,
      favoraveis: item.summary?.favorability?.favorable || 0,
      nao_mapeados: item.summary?.favorability?.unmapped_total || 0,
    }));
    renderLineChart(byId('facultySemesterTrend'), timeline, { suffix: '%', decimals: 1, unit: 'favorabilidade', metric: 'avaliacao_docente', usePointStatus: true });
    const context = byId('facultyTrendContext');
    if (context) {
      const op = moduleState.operational || {};
      context.textContent = op.previous_period
        ? `${signedPp(op.delta_percentage_points)} em relação a ${formatMonth(op.previous_period, true)}. A linha pontilhada representa a meta vigente em cada semestre.`
        : 'A linha pontilhada representa a meta vigente em cada semestre; a variação aparece quando existir período anterior comparável.';
    }
  }

  function renderQuestionHighlights() {
    const target = byId('facultyQuestionHighlights');
    if (!target) return;
    const teacherQuestions = (moduleState.questions || []).filter(item => item.analytical_scope === 'teacher' && item.favorability?.favorable_percentage !== null && item.favorability?.favorable_percentage !== undefined);
    const contextual = (moduleState.questions || []).filter(item => item.analytical_scope === 'contextual');
    if (!teacherQuestions.length && !contextual.length) {
      target.innerHTML = '<div class="faculty-empty"><strong>Sem perguntas disponíveis</strong>Não há questionário importado neste recorte.</div>';
      return;
    }
    const sorted = [...teacherQuestions].sort((a, b) => Number(b.favorability.favorable_percentage) - Number(a.favorability.favorable_percentage));
    const high = sorted[0];
    const low = sorted.at(-1);
    const cards = [];
    if (high) cards.push(`<div class="faculty-highlight-card"><div class="faculty-rank"><span class="faculty-chip">Maior favorabilidade</span><strong>${pct(high.favorability.favorable_percentage)}</strong></div><p>${escapeHtml(high.question)}</p></div>`);
    if (low && low.question_id !== high?.question_id) cards.push(`<div class="faculty-highlight-card"><div class="faculty-rank"><span class="faculty-chip warning">Menor favorabilidade</span><strong>${pct(low.favorability.favorable_percentage)}</strong></div><p>${escapeHtml(low.question)}</p></div>`);
    if (contextual.length) cards.push(`<div class="faculty-highlight-card contextual"><div class="faculty-rank"><span class="faculty-chip contextual">Contextual</span><strong>${number(contextual.length)}</strong></div><p>${escapeHtml(contextual[0].question)}${contextual.length > 1 ? ` (+${contextual.length - 1})` : ''}</p></div>`);
    target.innerHTML = cards.join('');
  }

  function entityRow(item, type) {
    const s = item.summary || {};
    const fav = s.favorability || {};
    const isDiscipline = type === 'discipline';
    const subtitle = isDiscipline ? item.course_name : `${number(s.courses || 0)} curso(s) · ${number(s.disciplines || 0)} disciplina(s)`;
    return `<article class="faculty-entity-row">
      <div class="faculty-entity-main"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(subtitle)}</small></div>
      <div class="faculty-entity-stat"><span>Favorabilidade</span><strong class="faculty-score">${fav.mapping_complete === false ? 'Revisar' : pct(fav.favorable_percentage)}</strong></div>
      <div class="faculty-entity-stat"><span>Participações</span><strong>${number(s.respondent_participations || 0)}</strong></div>
      <div class="faculty-entity-stat"><span>Contextos</span><strong>${number(s.contexts || 0)}</strong></div>
      <div class="faculty-entity-stat"><span>${isDiscipline ? 'Docentes' : 'Disciplinas'}</span><strong>${number(isDiscipline ? s.teachers : s.disciplines)}</strong></div>
      <button class="button secondary compact" type="button" data-faculty-detail="${type}" data-id="${item.id}">Ver detalhes</button>
    </article>`;
  }

  function renderTeachers() {
    const target = byId('facultyTeachersList');
    if (!target) return;
    const term = moduleState.teacherSearch.trim().toLocaleLowerCase('pt-BR');
    const rows = (moduleState.teachers || []).filter(item => !term || String(item.name || '').toLocaleLowerCase('pt-BR').includes(term));
    target.innerHTML = rows.length ? rows.map(item => entityRow(item, 'teacher')).join('') : '<div class="faculty-empty"><strong>Nenhum docente encontrado</strong>Altere a busca ou os filtros do recorte.</div>';
    target.querySelectorAll('[data-faculty-detail="teacher"]').forEach(button => button.addEventListener('click', () => openTeacherDetail(Number(button.dataset.id))));
  }

  function renderDisciplines() {
    const target = byId('facultyDisciplinesList');
    if (!target) return;
    const term = moduleState.disciplineSearch.trim().toLocaleLowerCase('pt-BR');
    const rows = (moduleState.disciplines || []).filter(item => !term || `${item.name || ''} ${item.course_name || ''}`.toLocaleLowerCase('pt-BR').includes(term));
    target.innerHTML = rows.length ? rows.map(item => entityRow(item, 'discipline')).join('') : '<div class="faculty-empty"><strong>Nenhuma disciplina encontrada</strong>Altere a busca ou os filtros do recorte.</div>';
    target.querySelectorAll('[data-faculty-detail="discipline"]').forEach(button => button.addEventListener('click', () => openDisciplineDetail(Number(button.dataset.id))));
  }

  function distributionRows(question) {
    const items = question.distribution?.items || [];
    return items.map(item => {
      const cls = item.classification || 'unclassified';
      return `<div class="faculty-distribution-row"><div>${escapeHtml(item.label)}</div><div class="faculty-distribution-track"><div class="faculty-distribution-fill ${escapeHtml(cls)}" style="width:${Math.max(0, Math.min(100, Number(item.percentage || 0)))}%"></div></div><div class="faculty-distribution-count">${number(item.count)} · ${formatNumber(Number(item.percentage || 0), 1)}%</div></div>`;
    }).join('');
  }

  function questionCardHtml(item, compact = false) {
    const fav = item.favorability || {};
    const contextual = item.analytical_scope === 'contextual';
    const score = fav.mapping_complete === false ? 'Revisar escala' : pct(fav.favorable_percentage);
    return `<article class="faculty-question-card ${contextual ? 'contextual' : ''}">
      <div class="faculty-question-head"><div><span class="faculty-question-number">Pergunta ${number(item.position || 0)} · <span class="faculty-chip ${contextual ? 'contextual' : ''}">${contextual ? 'Contextual' : 'Docente'}</span></span><h4>${escapeHtml(item.question)}</h4></div><div class="faculty-question-score"><strong>${escapeHtml(score)}</strong><small>${contextual ? 'favorabilidade da pergunta · fora da síntese docente' : 'favorabilidade'}</small></div></div>
      ${compact ? '' : `<div class="faculty-distribution">${distributionRows(item)}</div><div class="faculty-question-foot"><span>${number(item.distribution?.total || 0)} seleções</span><span>·</span><span>${number(item.contexts || 0)} contexto(s)</span><span>·</span><span>cobertura classificada ${pct(fav.classified_coverage_percentage)}</span></div>`}
    </article>`;
  }

  function renderQuestions() {
    const target = byId('facultyQuestionsList');
    if (!target) return;
    document.querySelectorAll('#facultyQuestionScope [data-question-scope]').forEach(button => button.classList.toggle('active', button.dataset.questionScope === moduleState.questionScope));
    const rows = (moduleState.questions || []).filter(item => moduleState.questionScope === 'all' || item.analytical_scope === moduleState.questionScope);
    target.innerHTML = rows.length ? rows.map(item => questionCardHtml(item)).join('') : '<div class="faculty-empty"><strong>Nenhuma pergunta neste escopo</strong>Altere os filtros ou selecione outro tipo de pergunta.</div>';
  }

  function detailContextRows(contexts) {
    return (contexts || []).map(item => `<div class="faculty-context-row"><strong>${escapeHtml(formatMonth(item.semester, true))}</strong><span>${escapeHtml(item.course_name)}</span><span>${escapeHtml(item.discipline_name)}</span><span>${number(item.respondent_count)} part.</span></div>`).join('');
  }

  function detailSummaryHtml(summary) {
    const fav = summary?.favorability || {};
    return `<div class="faculty-import-summary"><div class="faculty-import-stat"><strong>${fav.mapping_complete === false ? 'Revisar' : pct(fav.favorable_percentage)}</strong><span>Favorabilidade</span></div><div class="faculty-import-stat"><strong>${number(summary?.respondent_participations || 0)}</strong><span>Participações</span></div><div class="faculty-import-stat"><strong>${number(summary?.disciplines || 0)}</strong><span>Disciplinas</span></div><div class="faculty-import-stat"><strong>${number(summary?.contexts || 0)}</strong><span>Contextos</span></div></div>`;
  }

  async function openTeacherDetail(id) {
    try {
      const params = filterParams();
      params.delete('teacher_id');
      const data = await api(withQuery(`/analytics/teachers/${id}`, params), { blocking: false });
      const questions = data.questions?.items || [];
      openModal('Avaliação Docente', data.teacher?.name || 'Docente', `<div class="faculty-detail-head"><div><span class="faculty-chip">Identidade global do docente</span><h3>${escapeHtml(data.teacher?.name || '')}</h3><p>O histórico abaixo respeita o recorte ativo e mantém curso, disciplina e semestre separados.</p></div></div>${detailSummaryHtml(data.overview?.summary || {})}<div class="faculty-detail-contexts">${detailContextRows(data.contexts)}</div><div class="faculty-question-list">${questions.map(item => questionCardHtml(item, false)).join('')}</div>`);
    } catch (error) { toast('Não foi possível abrir o docente', error.message, 'error'); }
  }

  async function openDisciplineDetail(id) {
    try {
      const params = new URLSearchParams();
      if (moduleState.filters.semester) params.set('semester', moduleState.filters.semester);
      if (moduleState.filters.teacher_id) params.set('teacher_id', moduleState.filters.teacher_id);
      const data = await api(withQuery(`/analytics/disciplines/${id}`, params), { blocking: false });
      const questions = data.questions?.items || [];
      openModal('Avaliação Docente', data.discipline?.name || 'Disciplina', `<div class="faculty-detail-head"><div><span class="faculty-chip">${escapeHtml(data.discipline?.course_name || 'Curso')}</span><h3>${escapeHtml(data.discipline?.name || '')}</h3><p>A disciplina é mantida dentro da identidade do curso para evitar consolidação indevida entre cursos homônimos.</p></div></div>${detailSummaryHtml(data.overview?.summary || {})}<div class="faculty-detail-contexts">${detailContextRows(data.contexts)}</div><div class="faculty-question-list">${questions.map(item => questionCardHtml(item, false)).join('')}</div>`);
    } catch (error) { toast('Não foi possível abrir a disciplina', error.message, 'error'); }
  }

  function renderImports() {
    const quality = moduleState.identityQuality || {};
    const qsummary = quality.summary || {};
    const qtarget = byId('facultyIdentityQuality');
    if (qtarget) {
      const blockers = Number(quality.blocking_issue_count || 0);
      const warnings = Number(quality.warning_count || 0);
      qtarget.innerHTML = [
        `<div class="faculty-quality-card ${blockers ? 'error' : 'ok'}"><strong>${number(blockers)}</strong><span>${blockers ? 'bloqueio(s) de identidade encontrados' : 'Nenhum bloqueio estrutural'}</span></div>`,
        `<div class="faculty-quality-card ${warnings ? 'warning' : 'ok'}"><strong>${number(warnings)}</strong><span>${warnings ? 'aviso(s) de rastreabilidade/qualidade' : 'Nenhum aviso de qualidade'}</span></div>`,
        `<div class="faculty-quality-card"><strong>${number(qsummary.contexts || 0)}</strong><span>contextos persistidos · ${number(qsummary.teachers || 0)} docente(s)</span></div>`,
      ].join('');
    }
    const qualityDetails = byId('facultyQualityDetails');
    if (qualityDetails) {
      const issues = [
        ...(quality.blockers || []).map(item => ({ ...item, tone: 'error', label: 'Bloqueio' })),
        ...(quality.warnings || []).map(item => ({ ...item, tone: 'warning', label: 'Aviso' })),
      ];
      qualityDetails.innerHTML = issues.length
        ? issues.map(item => `<div class="faculty-quality-detail ${escapeHtml(item.tone)}"><div><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.message || item.code || 'Pendência')}</strong></div><b>${number(item.count || 0)}</b></div>`).join('')
        : '<div class="faculty-quality-detail ok"><div><span>Integridade</span><strong>Nenhuma pendência estrutural encontrada na malha acadêmica importada.</strong></div></div>';
    }
    const target = byId('facultyImportHistory');
    if (!target) return;
    const rows = moduleState.importHistory || [];
    if (!rows.length) {
      target.innerHTML = '<div class="faculty-empty"><strong>Nenhum lote importado</strong>Use “Nova importação” para analisar um ZIP/XLSX do relatório Disciplina/Professor do SEI.</div>';
      return;
    }
    target.innerHTML = `<table><thead><tr><th>Última atividade</th><th>Semestre</th><th>Arquivo / origem</th><th>Auditoria</th><th class="numeric">Contextos</th><th class="numeric">Resoluções</th><th>Status</th></tr></thead><tbody>${rows.map(item => { const audit = item.last_import_result || {}; const attempts = Number(item.import_attempts || 0); const actor = item.last_imported_by || 'Usuário não registrado'; return `<tr><td>${escapeHtml(formatImportDate(item.last_activity_at || item.created_at))}<br><small>${attempts > 1 ? `${number(attempts)} operações neste lote` : 'primeira importação do lote'}</small></td><td><strong>${escapeHtml(formatMonth(item.semester, true))}</strong><br><small>${escapeHtml(formatDate(item.period_start))} – ${escapeHtml(formatDate(item.period_end))}</small></td><td><strong>${escapeHtml(item.source_filename || '—')}</strong><br><small>${escapeHtml(item.origin === 'sei' ? 'Gerado pelo SEI' : 'Upload manual')} · ${escapeHtml(item.questionnaire_name || '')}</small></td><td><strong>${escapeHtml(actor)}</strong><br><small>${number(audit.imported || 0)} novo(s) · ${number(audit.skipped || 0)} existente(s) · ${number(audit.unmapped || 0)} não mapeado(s)</small></td><td class="numeric">${number(item.context_count || 0)}</td><td class="numeric">${number(item.course_resolution_count || 0)}</td><td>${badge(item.status === 'completed' ? 'Concluído' : item.status || '—')}</td></tr>`; }).join('')}</tbody></table>`;
  }

  function formatImportDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
  }

  async function loadCurrentView(force = false) {
    const serial = ++moduleState.loadSerial;
    showLoading(true);
    showError(null);
    try {
      if (moduleState.view !== 'imports') await loadFacets();
      if (serial !== moduleState.loadSerial) return;
      const params = filterParams();
      if (moduleState.view === 'overview') {
        const comparisonParams = (() => { const p = filterParams(); p.delete('semester'); return p; })();
        const [overview, questions, comparison, operational] = await Promise.all([
          api(withQuery('/analytics/overview', params), { blocking: false }),
          api(withQuery('/analytics/questions', params), { blocking: false }),
          api(withQuery('/analytics/semesters/compare', comparisonParams), { blocking: false }),
          api(withQuery('/analytics/operational', params), { blocking: false }),
        ]);
        if (serial !== moduleState.loadSerial) return;
        moduleState.overview = overview;
        moduleState.operational = operational;
        moduleState.questions = questions.items || [];
        moduleState.semesterComparison = comparison.items || [];
        moduleState.methodology = overview.methodology || operational.methodology || questions.methodology || moduleState.methodology;
        renderOverview();
      } else if (moduleState.view === 'teachers') {
        const data = await api(withQuery('/analytics/teachers', params), { blocking: false });
        if (serial !== moduleState.loadSerial) return;
        moduleState.teachers = data.items || [];
        moduleState.methodology = data.methodology || moduleState.methodology;
        renderTeachers();
      } else if (moduleState.view === 'disciplines') {
        const data = await api(withQuery('/analytics/disciplines', params), { blocking: false });
        if (serial !== moduleState.loadSerial) return;
        moduleState.disciplines = data.items || [];
        moduleState.methodology = data.methodology || moduleState.methodology;
        renderDisciplines();
      } else if (moduleState.view === 'questions') {
        const data = await api(withQuery('/analytics/questions', params), { blocking: false });
        if (serial !== moduleState.loadSerial) return;
        moduleState.questions = data.items || [];
        moduleState.methodology = data.methodology || moduleState.methodology;
        renderQuestions();
      } else if (moduleState.view === 'imports') {
        const [history, quality] = await Promise.all([
          api(`${API_BASE}/imports`, { blocking: false }),
          api(`${API_BASE}/identity/quality`, { blocking: false }),
        ]);
        if (serial !== moduleState.loadSerial) return;
        moduleState.importHistory = history.items || [];
        moduleState.identityQuality = quality;
        renderImports();
      }
    } catch (error) {
      if (serial === moduleState.loadSerial) showError(error);
    } finally {
      if (serial === moduleState.loadSerial) showLoading(false);
    }
  }

  async function load(force = false) {
    if (!['DTNH', 'DCS'].includes(state.activeDirectorate)) return;
    bindEvents();
    if (moduleState.directorate !== state.activeDirectorate) reset();
    moduleState.directorate = state.activeDirectorate;
    moduleState.loaded = true;
    setView(moduleState.view, { load: false });
    await loadCurrentView(force);
  }

  function openMethodology() {
    const m = moduleState.methodology;
    if (!m) {
      toast('Metodologia ainda não carregada', 'Abra a Visão Geral para carregar a metodologia do indicador.', 'warning');
      return;
    }
    const c = m.classification || {};
    openModal('Metodologia', 'Como a favorabilidade é calculada', `<div class="faculty-import-preview"><div class="faculty-import-note"><strong>Não é uma nota 0–10.</strong><br>${escapeHtml(m.description || '')}</div><div><span class="eyebrow">Denominador</span><p>${escapeHtml(m.denominator || '')}</p></div><div class="faculty-import-summary"><div class="faculty-import-stat"><strong>Favoráveis</strong><span>${escapeHtml((c.favorable || []).join(' · '))}</span></div><div class="faculty-import-stat"><strong>Intermediárias</strong><span>${escapeHtml((c.intermediate || []).join(' · '))}</span></div><div class="faculty-import-stat"><strong>Desfavoráveis</strong><span>${escapeHtml((c.unfavorable || []).join(' · '))}</span></div><div class="faculty-import-stat"><strong>Fora do denominador</strong><span>${escapeHtml((c.unclassified || []).join(' · '))}</span></div></div><div class="faculty-import-note"><strong>Escopo das perguntas</strong><br>${escapeHtml(m.question_scope?.teacher || '')}<br><br>${escapeHtml(m.question_scope?.contextual || '')}</div><div class="modal-form-footer"><button class="button primary" type="button" id="facultyCloseMethodology">Fechar</button></div></div>`);
    byId('facultyCloseMethodology')?.addEventListener('click', closeModal);
  }

  function canStartFacultyImport() {
    if (!canEditCurrentDirectorate()) {
      toast('Somente leitura', 'Seu acesso atual não permite importar novos relatórios.', 'warning');
      return false;
    }
    if (!['DTNH', 'DCS'].includes(state.activeDirectorate)) {
      toast('Diretoria não acadêmica', 'A Avaliação Docente via SEI está disponível apenas em DTNH e DCS.', 'warning');
      return false;
    }
    return true;
  }

  function facultySeiContext() {
    return state.modalContext?.type === 'faculty-student-sei' ? state.modalContext : null;
  }

  function triggerFileImport() {
    if (!canStartFacultyImport()) return;
    const input = byId('facultyImportFile');
    if (!input) return;
    input.value = '';
    input.click();
  }

  function triggerImport() {
    if (!canStartFacultyImport()) return;
    openModal('Avaliação Docente · SEI', 'Buscar relatório direto no SEI', '<div id="facultySeiFlow"></div>');
    state.modalContext = {
      type: 'faculty-student-sei',
      sessionToken: null,
      searchResults: [],
      selectedEvaluation: null,
      metadata: null,
    };
    renderFacultySeiLoginStep();
  }

  function renderFacultySeiLoginStep() {
    const root = byId('facultySeiFlow');
    const ctx = facultySeiContext();
    if (!root || !ctx) return;
    root.innerHTML = `<form id="facultySeiLoginForm" class="form-grid">
      <div class="tip-box span-2"><strong>Importação direta do SEI.</strong> O Data UNIVC entra no SEI com uma sessão temporária, localiza a Avaliação Institucional, gera o relatório <strong>Disciplina/Professor</strong> da unidade de Graduação de São Mateus e traz o ZIP/XLSX para a prévia antes de gravar. Usuário, senha, JSESSIONID e ViewState não são persistidos.</div>
      ${formField('faculty_sei_username', 'Usuário do SEI', 'text', '')}
      ${formField('faculty_sei_password', 'Senha do SEI', 'password', '')}
      ${formField('faculty_sei_keyword', 'Palavra-chave da avaliação', 'text', 'docente', { className: 'span-2', help: 'Ex.: docente. Você escolherá a aplicação correta na próxima etapa.' })}
      <div class="modal-form-footer span-2"><button type="button" class="button subtle" id="facultySeiUploadFallback">Usar XLSX/ZIP já baixado</button><button type="button" class="button secondary" id="facultySeiCancel">Cancelar</button><button type="submit" class="button primary">Conectar e buscar avaliações</button></div>
    </form>`;
    byId('facultySeiCancel')?.addEventListener('click', closeModal);
    byId('facultySeiUploadFallback')?.addEventListener('click', () => {
      closeModal();
      triggerFileImport();
    });
    byId('facultySeiLoginForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget).entries());
      try {
        const login = await api('/api/surveys/sei/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: values.faculty_sei_username, password: values.faculty_sei_password }),
          loadingTitle: 'Conectando ao SEI',
          loadingMessage: 'Criando uma sessão temporária para buscar a Avaliação Docente.'
        });
        const live = facultySeiContext();
        if (!live) return;
        live.sessionToken = login.session_token;
        const password = byId('field-faculty_sei_password');
        if (password) password.value = '';
        const search = await api('/api/surveys/sei/evaluations/search', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_token: live.sessionToken, keyword: values.faculty_sei_keyword || 'docente' }),
          loadingTitle: 'Buscando avaliações no SEI',
          loadingMessage: 'Consultando as aplicações de Avaliação Institucional disponíveis.'
        });
        live.searchResults = search.results || [];
        renderFacultySeiEvaluationStep();
      } catch (error) {
        toast('Não foi possível acessar o SEI', error.message, 'error');
      }
    });
  }

  function renderFacultySeiEvaluationStep() {
    const root = byId('facultySeiFlow');
    const ctx = facultySeiContext();
    if (!root || !ctx) return;
    const rows = ctx.searchResults || [];
    root.innerHTML = `<div class="form-grid">
      <div class="tip-box span-2"><strong>Escolha a aplicação correta.</strong> O Data UNIVC não usa um ID fixo do SEI. Depois da escolha, o backend localizará semanticamente o questionário de <em>discente avaliando docente</em> e travará o relatório em Graduação São Mateus + Disciplina/Professor + todos os turnos + todas as perguntas.</div>
      <div class="field span-2"><span>Avaliações encontradas</span>${rows.length ? `<div class="sei-course-grid">${rows.map((item, index) => `<label class="sei-course-option"><input type="radio" name="faculty_sei_evaluation" value="${escapeHtml(item.source)}" ${index === 0 ? 'checked' : ''}><span class="sei-course-check">✓</span><span class="sei-course-copy"><strong>${escapeHtml(item.name || 'Avaliação')}</strong><small>${escapeHtml([item.start_date && `Início ${item.start_date}`, item.end_date && `Fim ${item.end_date}`, item.target && `Público: ${item.target}`, item.status].filter(Boolean).join(' · ') || 'Sem metadados adicionais')}</small></span></label>`).join('')}</div>` : '<div class="warning-box">Nenhuma avaliação foi encontrada. Volte e tente outra palavra-chave.</div>'}</div>
      <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="facultySeiBackLogin">Voltar</button>${rows.length ? '<button type="button" class="button primary" id="facultySeiSelectEvaluation">Selecionar e preparar relatório</button>' : ''}</div>
    </div>`;
    byId('facultySeiBackLogin')?.addEventListener('click', renderFacultySeiLoginStep);
    byId('facultySeiSelectEvaluation')?.addEventListener('click', async () => {
      const selected = root.querySelector('input[name="faculty_sei_evaluation"]:checked');
      const source = selected?.value;
      if (!source) {
        toast('Escolha uma avaliação', 'Selecione a aplicação da Avaliação Docente antes de continuar.', 'warning');
        return;
      }
      try {
        ctx.metadata = await api('/api/surveys/sei/evaluations/select', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_token: ctx.sessionToken, source }),
          loadingTitle: 'Abrindo avaliação no SEI',
          loadingMessage: 'Lendo questionários e filtros disponíveis na aplicação selecionada.'
        });
        ctx.selectedEvaluation = rows.find(item => item.source === source) || null;
        renderFacultySeiPrepareStep();
      } catch (error) {
        toast('Não foi possível abrir a avaliação', error.message, 'error');
      }
    });
  }

  function renderFacultySeiPrepareStep() {
    const root = byId('facultySeiFlow');
    const ctx = facultySeiContext();
    const metadata = ctx?.metadata;
    if (!root || !ctx || !metadata) return;
    const questionnaires = metadata.questionnaires || [];
    const normalizeLabel = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const compatible = questionnaires.filter(item => {
      const label = normalizeLabel(item.name);
      return label.includes('aluno avalia professor') || label.includes('discente avalia docente') || label.includes('discente avalia professor');
    });
    const candidates = compatible.length ? compatible : questionnaires;
    const preferred = candidates.find(item => String(item.sei_id) === String(metadata.selected_questionnaire_id)) || candidates[0] || null;
    root.innerHTML = `<form id="facultySeiPrepareForm" class="form-grid">
      <div class="tip-box span-2"><strong>${escapeHtml(metadata.evaluation_name || ctx.selectedEvaluation?.name || 'Avaliação selecionada')}</strong><br>O escopo de Avaliação Docente será protegido pelo backend. O usuário não poderá trocar a unidade, o detalhamento ou o turno nesta etapa.</div>
      ${candidates.length ? `<label class="field span-2"><span>Questionário de discente avaliando docente</span><select id="facultySeiQuestionnaire" required>${candidates.map(item => `<option value="${escapeHtml(item.sei_id)}" ${preferred && String(item.sei_id) === String(preferred.sei_id) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('')}</select><small>O backend também valida semanticamente o questionário; uma opção incompatível será recusada.</small></label>` : '<div class="warning-box span-2"><strong>Nenhum questionário foi retornado pelo SEI.</strong><br>Volte e confirme se esta é realmente a aplicação de Avaliação Docente.</div>'}
      <div class="faculty-import-summary span-2"><div class="faculty-import-stat"><strong>Disciplina/Professor</strong><span>nível do relatório</span></div><div class="faculty-import-stat"><strong>Graduação · São Mateus</strong><span>unidade protegida</span></div><div class="faculty-import-stat"><strong>Todos</strong><span>turnos</span></div><div class="faculty-import-stat"><strong>Todas</strong><span>perguntas</span></div></div>
      <div class="modal-form-footer span-2"><button type="button" class="button secondary" id="facultySeiBackEvaluation">Voltar</button>${candidates.length ? '<button type="submit" class="button primary">Gerar relatório no SEI</button>' : ''}</div>
    </form>`;
    byId('facultySeiBackEvaluation')?.addEventListener('click', renderFacultySeiEvaluationStep);
    byId('facultySeiPrepareForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const qid = byId('facultySeiQuestionnaire')?.value || null;
      try {
        ctx.metadata = await api(`${API_BASE}/sei/prepare`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_token: ctx.sessionToken, questionnaire_id: qid }),
          loadingTitle: 'Preparando Avaliação Docente',
          loadingMessage: 'Aplicando o escopo protegido e selecionando todas as perguntas no SEI.'
        });
        const preview = await api(`${API_BASE}/sei/report/generate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_token: ctx.sessionToken }),
          loadingTitle: 'Gerando relatório no SEI',
          loadingMessage: 'O Data UNIVC fará as duas etapas do SEI: preparar os relatórios, gerar os XLSX e baixar o ZIP final. Não feche esta janela.'
        });
        openImportPreview(preview);
      } catch (error) {
        toast('Não foi possível gerar o relatório docente', error.message, 'error');
      }
    });
  }

  async function inspectImportFile(file) {
    if (!file) return;
    if (!/\.(zip|xlsx)$/i.test(file.name || '')) {
      toast('Arquivo incompatível', 'Envie um ZIP ou XLSX do relatório Disciplina/Professor do SEI.', 'warning');
      return;
    }
    const data = new FormData();
    data.append('file', file);
    try {
      const preview = await api(`${API_BASE}/import/inspect`, {
        method: 'POST', body: data,
        loadingTitle: 'Analisando Avaliação Docente',
        loadingMessage: 'Validando unidade, questionário, cursos, professores, disciplinas e duplicidade antes de gravar.'
      });
      openImportPreview(preview);
    } catch (error) { toast('Não foi possível analisar o arquivo', error.message, 'error'); }
  }

  function candidateOptions(entry) {
    const candidates = entry.course_match?.candidate_courses || [];
    return `<option value="">Não importar este relatório agora</option>${candidates.map(item => `<option value="${Number(item.course_id)}">${escapeHtml(item.course_name)}${item.modality ? ` · ${escapeHtml(item.modality)}` : ''}</option>`).join('')}`;
  }

  function openImportPreview(preview) {
    const summary = preview.summary || {};
    const unresolved = (preview.entries || []).filter(item => item.scope_status === 'course_resolution_required');
    const semester = preview.suggested_semester || '';
    const importable = Number(summary.eligible || 0) + Number(summary.resolvable || 0);
    const warningHtml = (preview.warnings || []).map(text => `<div class="faculty-import-warning">${escapeHtml(text)}</div>`).join('');
    const resolutionsHtml = unresolved.length ? `<div><span class="eyebrow">Cursos que exigem decisão</span><p>Esses relatórios não serão importados até que uma habilitação seja escolhida. Deixar em “Não importar agora” é seguro e não altera os demais.</p><div class="faculty-resolution-list">${unresolved.map(entry => `<label class="faculty-resolution-row"><div><strong>${escapeHtml(entry.teacher_name || 'Docente')} · ${escapeHtml(entry.discipline_name || 'Disciplina')}</strong><small>${escapeHtml(entry.course_name || '')} · ${escapeHtml(entry.internal_path || '')}</small></div><select data-course-resolution="${escapeHtml(entry.resolution_key || entry.internal_path || '')}">${candidateOptions(entry)}</select></label>`).join('')}</div></div>` : '';
    const body = `<form id="facultyImportConfirmForm" class="faculty-import-preview">
      <div class="faculty-import-note"><strong>${escapeHtml(preview.filename || 'Relatório')}</strong><br>Esta etapa é apenas uma prévia. Nenhum dado foi gravado no banco.</div>
      <div class="faculty-import-summary"><div class="faculty-import-stat"><strong>${number(summary.total_reports || 0)}</strong><span>relatórios encontrados</span></div><div class="faculty-import-stat"><strong>${number(summary.eligible || 0)}</strong><span>prontos para importar</span></div><div class="faculty-import-stat"><strong>${number(summary.already_imported || 0)}</strong><span>já importados</span></div><div class="faculty-import-stat"><strong>${number(summary.course_resolution_required || 0)}</strong><span>exigem decisão de curso</span></div></div>
      ${warningHtml}
      <label class="field"><span>Semestre letivo</span><input id="facultyImportSemester" type="text" value="${escapeHtml(semester)}" placeholder="Ex.: 2026-SEM1" pattern="[0-9]{4}-SEM[12]" required><small>${semester ? `Sugestão explícita encontrada na fonte: ${escapeHtml(formatMonth(semester, true))}. Confirme antes de importar.` : 'O SEI não informou o semestre de forma inequívoca. Digite AAAA-SEM1 ou AAAA-SEM2; a data da avaliação não será usada para adivinhar.'}</small></label>
      ${resolutionsHtml}
      <div class="faculty-import-summary"><div class="faculty-import-stat"><strong>${number(summary.outside_unit || 0)}</strong><span>fora da unidade</span></div><div class="faculty-import-stat"><strong>${number(summary.course_out_of_scope || 0)}</strong><span>fora do escopo da diretoria</span></div><div class="faculty-import-stat"><strong>${number(summary.wrong_questionnaire || 0)}</strong><span>questionário incompatível</span></div><div class="faculty-import-stat"><strong>${number(summary.invalid_report || 0)}</strong><span>relatório inválido</span></div></div>
      <div class="modal-form-footer"><button class="button secondary" type="button" id="facultyCancelImport">Cancelar</button><button class="button primary" type="submit" ${importable ? '' : 'disabled'}>Confirmar importação</button></div>
    </form>`;
    openModal('Avaliação Docente · Importação', 'Revisar antes de gravar', body);
    state.modalContext = { type: 'faculty-student-import', preview };
    byId('facultyCancelImport')?.addEventListener('click', closeModal);
    byId('facultyImportConfirmForm')?.addEventListener('submit', event => processImport(event, preview));
  }

  async function processImport(event, preview) {
    event.preventDefault();
    const semester = String(byId('facultyImportSemester')?.value || '').trim().toUpperCase();
    if (!/^\d{4}-SEM[12]$/.test(semester)) {
      toast('Confirme o semestre', 'Use o formato AAAA-SEM1 ou AAAA-SEM2.', 'warning');
      byId('facultyImportSemester')?.focus();
      return;
    }
    const selected = [...(preview.eligible_paths || [])];
    const resolutions = {};
    document.querySelectorAll('[data-course-resolution]').forEach(select => {
      if (!select.value) return;
      const path = select.dataset.courseResolution;
      resolutions[path] = Number(select.value);
      selected.push(path);
    });
    if (!selected.length) {
      toast('Nada para importar', 'Não há relatórios elegíveis ou resoluções selecionadas neste lote.', 'warning');
      return;
    }
    try {
      const result = await api(`${API_BASE}/import/process`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: preview.token, selected_paths: selected, semester_override: semester, course_resolutions: resolutions }),
        loadingTitle: 'Importando Avaliação Docente',
        loadingMessage: 'Persistindo professor, curso, disciplina, semestre e distribuições originais das respostas.'
      });
      closeModal();
      reset();
      moduleState.directorate = state.activeDirectorate;
      moduleState.loaded = true;
      moduleState.view = 'imports';
      setView('imports', { load: false });
      await loadCurrentView(true);
      const imported = (result.imported_contexts || []).length;
      const skipped = (result.skipped_contexts || []).length;
      toast('Avaliação Docente importada', `${imported} contexto(s) novo(s) · ${skipped} já existente(s).`, 'success');
      await loadDashboard();
    } catch (error) { toast('Não foi possível concluir a importação', error.message, 'error'); }
  }

  function bindEvents() {
    if (moduleState.bound) return;
    moduleState.bound = true;
    document.querySelectorAll('#facultyViewTabs [data-faculty-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.facultyView)));
    const map = {
      facultySemesterFilter: 'semester',
      facultyCourseFilter: 'course_id',
      facultyDisciplineFilter: 'discipline_id',
      facultyTeacherFilter: 'teacher_id',
    };
    Object.entries(map).forEach(([id, key]) => byId(id)?.addEventListener('change', async event => {
      moduleState.filters[key] = event.target.value;
      if (key === 'course_id') moduleState.filters.discipline_id = '';
      if (key === 'discipline_id') { /* teacher remains valid only if facet reconciliation confirms it */ }
      await loadCurrentView(true);
    }));
    byId('facultyResetFilters')?.addEventListener('click', async () => {
      moduleState.filters = { semester: '', course_id: '', discipline_id: '', teacher_id: '' };
      await loadCurrentView(true);
    });
    byId('facultyTeacherSearch')?.addEventListener('input', event => { moduleState.teacherSearch = event.target.value || ''; renderTeachers(); });
    byId('facultyDisciplineSearch')?.addEventListener('input', event => { moduleState.disciplineSearch = event.target.value || ''; renderDisciplines(); });
    document.querySelectorAll('#facultyQuestionScope [data-question-scope]').forEach(button => button.addEventListener('click', () => { moduleState.questionScope = button.dataset.questionScope; renderQuestions(); }));
    byId('facultyMethodologyButton')?.addEventListener('click', openMethodology);
    byId('facultyImportButton')?.addEventListener('click', triggerImport);
    byId('facultyImportButtonSecondary')?.addEventListener('click', triggerImport);
    byId('facultyFileImportButton')?.addEventListener('click', triggerFileImport);
    byId('facultyFileImportButtonSecondary')?.addEventListener('click', triggerFileImport);
    byId('facultyImportFile')?.addEventListener('change', event => inspectImportFile(event.target.files?.[0]));
  }

  window.FacultyEvaluationUI = { load, reset, setView, triggerImport, triggerFileImport };
})();
