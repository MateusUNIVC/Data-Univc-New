(() => {
  const body = document.body;
  if (!body.classList.contains('ui-v2')) return;

  const icons = {
    dashboard: '<path d="M4 4h6v6H4zM14 4h6v4h-6zM14 12h6v8h-6zM4 14h6v6H4z"/>',
    dadm01: '<path d="M5 5h14v14H5z"/><path d="M8 9h8M8 13h5M8 17h3"/>',
    dadm02: '<path d="M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0"/><path d="M8.5 14.5c1.7 1.6 5.3 1.6 7 0M9 9h.01M15 9h.01"/>',
    dpe01: '<path d="M4 19h16M6 16l4-5 3 2 5-7"/><path d="M18 6v5h-5"/>',
    dpe02: '<circle cx="12" cy="12" r="8"/><path d="M8 14l3-4 2 2 3-4"/>',
    dpe03: '<path d="M6 4h12v16H6z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
    receitas: '<path d="M4 8h16v10H4z"/><path d="M8 8V6h8v2M8 13h8"/>',
    despesas: '<path d="M6 4h12v16H6z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    cursos: '<path d="m3 8 9-5 9 5-9 5z"/><path d="M7 11v5c3 2 7 2 10 0v-5"/>',
    'nps-institution': '<path d="M4 13a8 8 0 1 1 16 0"/><path d="m12 13 4-4"/><path d="M7 17h10"/>',
    'nps-course': '<path d="M4 13a8 8 0 1 1 16 0"/><path d="m12 13 3-5"/><path d="M8 18h8"/>',
    avaliacao_docente: '<path d="M12 3 14.6 8.2l5.7.8-4.1 4 1 5.7-5.2-2.7-5.2 2.7 1-5.7-4.1-4 5.7-.8z"/>',
    resultados: '<path d="M5 20V9M12 20V4M19 20v-7"/><path d="M3 20h18"/>',
    planos: '<path d="M7 4h10M7 8h10M7 12h6"/><path d="M5 3h14v18H5z"/>',
    metas: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m18 6 3-3"/>',
    cadastros: '<path d="M12 5v14M5 12h14"/>',
    qualidade: '<path d="M12 3 19 6v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6z"/><path d="m9 12 2 2 4-5"/>',
    arquivos: '<path d="M4 6h6l2 2h8v11H4z"/><path d="M12 11v6M9 14l3 3 3-3"/>',
    configuracoes: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.8-1L14.4 3h-4.8l-.4 3.1a7 7 0 0 0-1.8 1L5 6.1 3 9.5 5.1 11a7 7 0 0 0 0 2L3 14.5 5 18l2.4-1.1a7 7 0 0 0 1.8 1l.4 3.1h4.8l.4-3.1a7 7 0 0 0 1.8-1L19 18l2-3.5-2.1-1.5c.1-.3.1-.7.1-1z"/>',
    ajuda: '<circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.4 2.4 0 1 1 3.5 2.2c-.9.5-1.3 1-1.3 2M12 17h.01"/>',
    dm01: '<path d="M5 20V10M12 20V5M19 20v-7"/><path d="M3 20h18"/>',
    dm02: '<circle cx="12" cy="12" r="8"/><path d="M12 8v5l3 2"/>',
    turmas: '<path d="M4 18v-2c0-2 2-3 4-3s4 1 4 3v2M8 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM14 6h6M17 3v6"/>',
    alunos: '<path d="m3 8 9-5 9 5-9 5z"/><path d="M7 11v5c3 2 7 2 10 0v-5M21 9v6"/>',
    sei: '<path d="M6 8.5A7 7 0 0 1 18.8 7M18 3v5h-5"/><path d="M18 15.5A7 7 0 0 1 5.2 17M6 21v-5h5"/><circle cx="12" cy="12" r="2.3"/>',
    'tallos-overview': '<path d="M4 4h6v6H4zM14 4h6v4h-6zM14 12h6v8h-6zM4 14h6v6H4z"/>',
    'tallos-operators': '<path d="M16 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M2 20c0-3 2.5-5 6-5s6 2 6 5M14 14c4.5-.6 8 1.4 8 5"/>',
    'tallos-departments': '<path d="M4 20V7l8-4 8 4v13"/><path d="M8 10h2M14 10h2M8 14h2M14 14h2M9 20v-3h6v3"/>',
    'tallos-experience': '<circle cx="12" cy="12" r="9"/><path d="M8 14c2.1 2 5.9 2 8 0M9 9h.01M15 9h.01"/>',
    'tallos-sync': '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.2 8.2A7 7 0 0 1 18 6l2 1M17.8 15.8A7 7 0 0 1 6 18l-2-1"/>',
    governanca: '<path d="M12 3 19 6v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6z"/><path d="m9 12 2 2 4-5"/>',
    back: '<path d="m15 18-6-6 6-6"/><path d="M9 12h10"/>'
  };

  const fallback = '<circle cx="12" cy="12" r="8"/><path d="M8 12h8"/>';
  const svg = (path) => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;

  document.querySelectorAll('.nav-item').forEach((item) => {
    const icon = item.querySelector('.nav-icon');
    if (!icon) return;
    let key = item.dataset.section || '';
    if (!key && item.matches('a[href="/"]')) key = 'back';
    icon.innerHTML = svg(icons[key] || fallback);
    const label = item.querySelector(':scope > span:last-child')?.textContent?.trim();
    if (label) item.title = label;
  });

  const existingMenuToggle = document.getElementById('menuToggle');
  if (existingMenuToggle) existingMenuToggle.innerHTML = svg('<path d="M4 7h16M4 12h16M4 17h16"/>');

  const actionIcons = {
    download: '<path d="M12 3v12M8 11l4 4 4-4"/><path d="M5 20h14"/>',
    add: '<path d="M12 5v14M5 12h14"/>',
    sync: '<path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 8A7 7 0 0 1 18 6l2 1M18 16a7 7 0 0 1-12 2l-2-1"/>',
    graduate: '<path d="m3 8 9-5 9 5-9 5z"/><path d="M7 11v5c3 2 7 2 10 0v-5"/>',
    clear: '<path d="M6 6l12 12M18 6 6 18"/>',
    import: '<path d="M12 20V8M8 12l4-4 4 4"/><path d="M5 4h14"/>',
    sei: '<path d="M6 8.5A7 7 0 0 1 18.8 7M18 3v5h-5"/><path d="M18 15.5A7 7 0 0 1 5.2 17M6 21v-5h5"/><circle cx="12" cy="12" r="2.3"/>'
  };

  const decorate = (selector, iconName) => {
    document.querySelectorAll(selector).forEach((el) => {
      if (el.dataset.uiDecorated === '1') return;
      const text = el.textContent.trim();
      const label = iconName === 'add' ? text.replace(/^\+\s*/, '') : text;
      el.innerHTML = `${svg(actionIcons[iconName] || fallback)}<span>${label}</span>`;
      el.dataset.uiDecorated = '1';
    });
  };
  decorate('.download-link, a[download].ui-action, #dmFullExcel, #dadmFullExcel, #dpeFullExcel, .topbar a[download], .page-lead a[download]', 'download');
  decorate('#quickAddButton, #dmQuickAdd, #dadmQuickAdd, #dpeQuickAdd, #newStudent, #newStudentDM02, #newCohort, #newCohortDM01, #newDmTarget, #newRevenue, #newExpense, #newCourseRevenue, #newCourseCost, #newAction, #newTarget, #addActionButton, #addGoalButton, #addCourseButton, #addDisciplineButton, .add-button, [data-new]', 'add');
  decorate('#npsCourseSeiImportButton, #npsInstitutionSeiImportButton, #npsFacultySeiImportButton, #seiImportButton, #teacherSeiReadinessButton, #refreshCohortStudents, #refreshSelectedStudents, #refreshAllCohorts, #dmTopSei, #seiDirectButton', 'sei');
  decorate('[data-import]:not(#seiImportButton)', 'import');
  decorate('#graduateSelectedStudents', 'graduate');
  decorate('#clearStudentSelection, #resetNpsCourseFilters, #resetNpsInstitutionFilters, #resetFilters', 'clear');

  const sidebar = document.querySelector('.sidebar');
  if (sidebar && !sidebar.querySelector('.ui-sidebar-collapse')) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ui-sidebar-collapse';
    button.setAttribute('aria-label', 'Recolher menu lateral');
    button.title = 'Recolher menu lateral';
    button.innerHTML = svg('<path d="m14 7-5 5 5 5"/>');
    const brand = sidebar.querySelector('.brand');
    if (brand) brand.insertAdjacentElement('afterend', button);
    button.addEventListener('click', () => {
      const collapsed = body.classList.toggle('ui-sidebar-collapsed');
      button.setAttribute('aria-label', collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral');
      button.title = collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral';
      try { localStorage.setItem('data-univc-sidebar', collapsed ? 'collapsed' : 'expanded'); } catch (_) {}
    });
    try {
      if (localStorage.getItem('data-univc-sidebar') === 'collapsed' && window.innerWidth > 980) {
        body.classList.add('ui-sidebar-collapsed');
      }
    } catch (_) {}
  }

  if (!document.getElementById('menuToggle') && sidebar) {
    const headerLead = document.querySelector('.topbar > div:first-child');
    if (headerLead) {
      const mobile = document.createElement('button');
      mobile.type = 'button';
      mobile.className = 'icon-button ui-mobile-menu';
      mobile.setAttribute('aria-label', 'Abrir menu');
      mobile.innerHTML = svg('<path d="M4 7h16M4 12h16M4 17h16"/>');
      headerLead.prepend(mobile);
      mobile.addEventListener('click', () => sidebar.classList.toggle('open'));
    }
  }

  document.querySelectorAll('.nav-item[data-section]').forEach((item) => {
    item.addEventListener('click', () => {
      if (window.innerWidth <= 980) sidebar?.classList.remove('open');
    });
  });
})();
