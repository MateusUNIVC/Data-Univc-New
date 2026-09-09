window.DADMV2 = window.DADMV2 || {};
(() => {
  const NS = window.DADMV2;
  NS.buildUrl = (path, params = {}) => {
    const url = new URL(path, location.origin);
    url.searchParams.set('diretoria', 'DADM');
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
    });
    return url.pathname + url.search;
  };
  NS.api = async (path, options = {}, params = {}) => {
    const response = await fetch(NS.buildUrl(path, params), {
      credentials: 'same-origin',
      ...options,
      headers: { Accept: 'application/json', ...(options.headers || {}) },
    });
    if (response.status === 401) {
      location.assign('/');
      throw new Error('Sessão expirada.');
    }
    let payload = null;
    const type = response.headers.get('content-type') || '';
    if (type.includes('application/json')) {
      try { payload = await response.json(); } catch { payload = null; }
    }
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === 'string' ? detail : detail?.erro || payload?.erro || `Erro HTTP ${response.status}`;
      const error = new Error(message);
      error.payload = payload;
      error.status = response.status;
      throw error;
    }
    return payload ?? response;
  };
  NS.filterParams = filters => ({
    from_month: filters.fromMonth,
    to_month: filters.toMonth,
    department: filters.department,
    employee: filters.employee,
    channel: filters.channel,
    status: filters.status,
    tabulation: filters.tabulation,
  });
})();
