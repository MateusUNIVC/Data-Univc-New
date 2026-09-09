(() => {
  'use strict';

  const nativeFetch = window.fetch.bind(window);
  let refreshPromise = null;
  let internalFetch = false;

  const CSRF_COOKIE_NAMES = ['__Host-dataunivc_csrf', 'dataunivc_csrf'];
  const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  function cookieValue(name) {
    const prefix = `${name}=`;
    for (const part of document.cookie.split(';')) {
      const value = part.trim();
      if (value.startsWith(prefix)) return decodeURIComponent(value.slice(prefix.length));
    }
    return '';
  }

  function csrfToken() {
    for (const name of CSRF_COOKIE_NAMES) {
      const value = cookieValue(name);
      if (value) return value;
    }
    return '';
  }

  function withCsrf(input, init = {}) {
    const options = { credentials: 'same-origin', ...init };
    const method = String(options.method || 'GET').toUpperCase();
    let target;
    try { target = new URL(typeof input === 'string' ? input : input?.url || '', location.origin); }
    catch (_) { return options; }
    if (target.origin === location.origin && MUTATING_METHODS.has(method) && target.pathname !== '/api/auth/login') {
      const token = csrfToken();
      if (token) {
        const headers = new Headers(options.headers || {});
        headers.set('X-CSRF-Token', token);
        options.headers = headers;
      }
    }
    return options;
  }

  function pathOf(input) {
    try { return new URL(typeof input === 'string' ? input : input?.url || '', location.origin).pathname; }
    catch (_) { return String(input || ''); }
  }

  function isSameOriginApi(input) {
    try {
      const url = new URL(typeof input === 'string' ? input : input?.url || '', location.origin);
      return url.origin === location.origin && url.pathname.startsWith('/api/');
    } catch (_) { return false; }
  }

  function mayAutoRefresh(input) {
    const path = pathOf(input);
    return !['/api/auth/login', '/api/auth/refresh', '/api/auth/logout'].includes(path);
  }

  async function refreshSession() {
    if (!refreshPromise) {
      refreshPromise = nativeFetch('/api/auth/refresh', withCsrf('/api/auth/refresh', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' },
      }))
        .then(response => response.ok)
        .catch(() => false)
        .finally(() => { refreshPromise = null; });
    }
    return refreshPromise;
  }

  async function authenticatedFetch(input, init = {}, retry = true) {
    const options = withCsrf(input, init);
    let response = await nativeFetch(input, options);
    if (response.status === 401 && retry && isSameOriginApi(input) && mayAutoRefresh(input)) {
      const renewed = await refreshSession();
      if (renewed) response = await nativeFetch(input, withCsrf(input, init));
    }
    return response;
  }

  async function logout() {
    try {
      return await nativeFetch('/api/auth/logout', withCsrf('/api/auth/logout', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' },
      }));
    } finally { refreshPromise = null; }
  }

  function responseFilename(response, fallback = 'arquivo') {
    const disposition = response.headers.get('content-disposition') || '';
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (encoded?.[1]) { try { return decodeURIComponent(encoded[1].replace(/["']/g, '')); } catch (_) {} }
    const plain = disposition.match(/filename="?([^";]+)"?/i);
    return plain?.[1] || fallback;
  }

  async function download(url, fallbackName = '') {
    const response = await authenticatedFetch(url, { method: 'GET', credentials: 'same-origin', cache: 'no-store' });
    if (response.status === 401) { location.assign('/'); return false; }
    if (!response.ok) throw new Error(`Falha ao gerar o arquivo (${response.status}).`);
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = responseFilename(response, fallbackName || String(url).split('/').pop()?.split('?')[0] || 'arquivo');
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1200);
    return true;
  }

  window.DataUnivcAuth = Object.freeze({ fetch: authenticatedFetch, refreshSession, logout, download, csrfToken });

  // Compatibility bridge for the v0.8.33 frontend: existing same-origin API fetches
  // automatically gain CSRF and silent refresh while modules migrate to the explicit wrapper.
  window.fetch = function dataUnivcFetch(input, init = {}) {
    if (internalFetch || !isSameOriginApi(input)) return nativeFetch(input, init);
    return authenticatedFetch(input, init);
  };

  if (location.pathname !== '/') {
    document.addEventListener('click', event => {
      const anchor = event.target.closest?.('a[download][href^="/api/"]');
      if (!anchor) return;
      event.preventDefault();
      download(anchor.href, anchor.getAttribute('download') || '').catch(error => {
        console.error(error); window.alert(error.message || 'Não foi possível baixar o arquivo.');
      });
    });
  }
})();
