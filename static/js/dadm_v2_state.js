window.DADMV2 = window.DADMV2 || {};
(() => {
  const NS = window.DADMV2;
  const now = new Date();
  const pad = value => String(value).padStart(2, '0');
  const currentMonth = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
  const params = new URLSearchParams(location.search);
  const allowedViews = new Set(['overview', 'people', 'experience', 'comparison', 'management', 'integration']);

  NS.state = {
    user: null,
    access: null,
    connection: null,
    context: null,
    overview: null,
    experience: null,
    quality: null,
    management: null,
    departmentMaps: [],
    syncRuns: [],
    syncProgress: { runId: null, maxPct: 0 },
    view: allowedViews.has(params.get('view')) ? params.get('view') : 'overview',
    filters: {
      fromMonth: params.get('from') || '',
      toMonth: params.get('to') || '',
      department: params.get('department') || '',
      employee: params.get('employee') || '',
      channel: params.get('channel') || '',
      status: params.get('status') || '',
      tabulation: params.get('tabulation') || '',
    },
    entity: {
      kind: params.get('entity_kind') === 'department' ? 'department' : 'employee',
      metric: params.get('entity_metric') || 'attendances',
      search: '',
      sort: 'attendances-desc',
      profile: null,
      profileId: params.get('entity_id') || '',
      evaluations: { data: null, page: 1, pageSize: 20, order: 'newest', loading: false },
    },
    experienceDimension: 'employee',
    comparison: {
      mode: 'employee',
      ids: [],
      rangeA: null,
      rangeB: null,
    },
    picker: {
      target: 'global',
      year: now.getFullYear(),
      start: '',
      end: '',
      phase: 'start',
    },
    currentMonth,
    loadingCount: 0,
  };

  NS.monthIndex = value => {
    if (!/^\d{4}-\d{2}$/.test(value || '')) return null;
    const [year, month] = value.split('-').map(Number);
    return year * 12 + month - 1;
  };
  NS.monthFromIndex = index => `${Math.floor(index / 12)}-${pad(index % 12 + 1)}`;
  NS.shiftMonth = (value, delta) => {
    const index = NS.monthIndex(value);
    return index == null ? '' : NS.monthFromIndex(index + delta);
  };
  NS.monthLabel = (value, short = false) => {
    if (!/^\d{4}-\d{2}$/.test(value || '')) return '—';
    const [year, month] = value.split('-').map(Number);
    const date = new Date(year, month - 1, 1);
    const text = new Intl.DateTimeFormat('pt-BR', { month: short ? 'short' : 'long', year: 'numeric' }).format(date);
    return text.replace(/^./, char => char.toUpperCase()).replace('.', '');
  };
  NS.periodLabel = (fromMonth, toMonth) => {
    if (!fromMonth && !toMonth) return 'Sem período';
    if (fromMonth === toMonth) return NS.monthLabel(fromMonth);
    return `${NS.monthLabel(fromMonth, true)} → ${NS.monthLabel(toMonth, true)}`;
  };
  NS.todayIso = () => {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  };
  NS.monthBounds = month => {
    if (!/^\d{4}-\d{2}$/.test(month || '')) return null;
    const [year, mon] = month.split('-').map(Number);
    const last = new Date(year, mon, 0).getDate();
    return { start: `${year}-${pad(mon)}-01`, end: `${year}-${pad(mon)}-${pad(last)}` };
  };
  NS.syncUrl = () => {
    const { state } = NS;
    const q = new URLSearchParams();
    q.set('diretoria', 'DADM');
    if (state.view !== 'overview') q.set('view', state.view);
    const f = state.filters;
    if (f.fromMonth) q.set('from', f.fromMonth);
    if (f.toMonth) q.set('to', f.toMonth);
    if (f.department) q.set('department', f.department);
    if (f.employee) q.set('employee', f.employee);
    if (f.channel) q.set('channel', f.channel);
    if (f.status) q.set('status', f.status);
    if (f.tabulation) q.set('tabulation', f.tabulation);
    if (state.view === 'people') {
      q.set('entity_kind', state.entity.kind);
      if (state.entity.metric !== 'attendances') q.set('entity_metric', state.entity.metric);
      if (state.entity.profileId) q.set('entity_id', state.entity.profileId);
    }
    history.replaceState(null, '', `${location.pathname}?${q.toString()}`);
  };
})();
