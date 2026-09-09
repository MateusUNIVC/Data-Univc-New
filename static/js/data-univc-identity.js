(() => {
  'use strict';

  const OPERATING_CODES = Object.freeze(['DTNH', 'DCS', 'DADM', 'DPE', 'DM']);
  const ROLE_REITORIA = 'REITORIA';
  const ROLE_DIRECTORATE = 'DIRECTORATE';
  const ACCESS_READ = 'READ';
  const ACCESS_EDIT = 'EDIT';

  function normalizeCode(value) {
    return String(value || '').trim().toUpperCase();
  }

  function normalizeDirectorate(item = {}) {
    const code = normalizeCode(item.code);
    if (!code) return null;
    const access = normalizeCode(item.access) === ACCESS_EDIT ? ACCESS_EDIT : ACCESS_READ;
    return Object.freeze({
      code,
      name: String(item.name || code),
      access,
      primary: Boolean(item.primary),
      canEdit: access === ACCESS_EDIT,
    });
  }

  function uniqueDirectorates(items = []) {
    const seen = new Set();
    const out = [];
    for (const raw of items || []) {
      const item = normalizeDirectorate(raw);
      if (!item || seen.has(item.code)) continue;
      seen.add(item.code);
      out.push(item);
    }
    return Object.freeze(out);
  }

  function roleLabel(role) {
    return normalizeCode(role) === ROLE_REITORIA ? 'Reitoria' : 'Diretoria';
  }

  function routeForDirectorate(code) {
    const key = normalizeCode(code);
    if (window.DataUnivcUI?.routeForDirectorate) return window.DataUnivcUI.routeForDirectorate(key);
    if (key === 'DADM') return '/dadm?diretoria=DADM';
    if (key === 'DPE') return '/dpe?diretoria=DPE';
    if (key === 'DM') return '/dm?diretoria=DM';
    return `/?diretoria=${encodeURIComponent(key)}`;
  }

  function normalize(payload = {}) {
    const user = payload.user || {};
    const role = normalizeCode(payload.role) === ROLE_REITORIA ? ROLE_REITORIA : ROLE_DIRECTORATE;
    const globalAccess = Boolean(payload.global_access || role === ROLE_REITORIA);
    const directorates = uniqueDirectorates(payload.directorates || []);
    const availableDirectorates = uniqueDirectorates(
      globalAccess ? (payload.available_directorates || []) : directorates,
    );

    const dataScopes = payload.data_scopes && typeof payload.data_scopes === 'object' ? payload.data_scopes : {};
    const homePayload = normalizeDirectorate(payload.home_directorate || {});
    const homeDirectorate = homePayload
      || directorates.find(item => item.primary)
      || availableDirectorates.find(item => item.primary)
      || availableDirectorates[0]
      || null;

    const identity = {
      id: String(user.id || ''),
      name: String(user.name || user.email || 'Usuário'),
      email: String(user.email || ''),
      avatarUrl: String(user.avatar_url || ''),
      role,
      roleLabel: roleLabel(role),
      globalAccess,
      permissionVersion: Number(payload.permission_version || 1),
      sessionVersion: Number(payload.session_version || 2),
      directorates,
      availableDirectorates,
      homeDirectorate,
      dataScopes: Object.freeze(dataScopes),
      dataScopeFor(code) {
        return this.dataScopes[normalizeCode(code)] || null;
      },
      accessFor(code) {
        const key = normalizeCode(code);
        if (!key) return null;
        if (globalAccess) return availableDirectorates.some(item => item.code === key) ? ACCESS_EDIT : null;
        return directorates.find(item => item.code === key)?.access || null;
      },
      directorateFor(code) {
        const key = normalizeCode(code);
        return availableDirectorates.find(item => item.code === key) || null;
      },
      canAccess(code) {
        return Boolean(this.accessFor(code));
      },
      canEdit(code) {
        return this.accessFor(code) === ACCESS_EDIT;
      },
      routeFor(code) {
        return routeForDirectorate(code);
      },
      preferredDirectorate(requested = '') {
        const key = normalizeCode(requested);
        if (key && this.canAccess(key)) return key;
        if (this.homeDirectorate?.code && this.canAccess(this.homeDirectorate.code)) return this.homeDirectorate.code;
        return this.availableDirectorates[0]?.code || null;
      },
      shouldShowSwitcher() {
        return this.availableDirectorates.length > 1;
      },
    };
    return Object.freeze(identity);
  }

  function initials(value) {
    return String(value || 'Usuário').split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'U';
  }

  function applyAvatar(element, identity, urlOverride = '') {
    if (!element || !identity) return;
    const fallback = initials(identity.name || identity.email || 'Usuário');
    const url = String(urlOverride || identity.avatarUrl || identity.avatar_url || '');
    element.textContent = fallback;
    element.style.backgroundImage = '';
    element.style.backgroundSize = '';
    element.style.backgroundPosition = '';
    if (!url) return;
    const image = new Image();
    image.onload = () => {
      element.textContent = '';
      element.style.backgroundImage = `url("${url.replace(/"/g, '%22')}")`;
      element.style.backgroundSize = 'cover';
      element.style.backgroundPosition = 'center';
    };
    image.onerror = () => {
      element.textContent = fallback;
      element.style.backgroundImage = '';
    };
    image.src = url;
  }

  async function load() {
    if (!window.DataUnivcAuth?.fetch) throw new Error('Camada de autenticação indisponível.');
    const response = await window.DataUnivcAuth.fetch('/api/auth/me', {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (response.status === 401) return null;
    if (!response.ok) {
      let detail = '';
      try {
        const body = await response.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
      } catch (_) {}
      throw new Error(detail || 'Não foi possível carregar sua identidade no Data UNIVC.');
    }
    return normalize(await response.json());
  }

  function redirectToAuthorizedHome(identity, requested = '') {
    if (!identity) {
      location.assign('/');
      return false;
    }
    if (identity.globalAccess && !normalizeCode(requested)) {
      location.assign('/reitoria');
      return true;
    }
    const target = identity.preferredDirectorate(requested);
    if (!target) {
      location.assign('/');
      return false;
    }
    location.assign(routeForDirectorate(target));
    return true;
  }

  window.DataUnivcIdentity = Object.freeze({
    OPERATING_CODES,
    ROLE_REITORIA,
    ROLE_DIRECTORATE,
    ACCESS_READ,
    ACCESS_EDIT,
    normalize,
    load,
    roleLabel,
    routeForDirectorate,
    redirectToAuthorizedHome,
    applyAvatar,
  });
})();
