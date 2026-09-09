(() => {
  'use strict';

  const state = {
    identity: null,
    users: [],
    directorates: [],
    actorUserId: '',
    selectedUserId: '',
    avatarRemoveRequested: false,
  };
  const $ = selector => document.querySelector(selector);

  function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function initials(value) {
    return String(value || 'Usuário').split(/\s+/).filter(Boolean).slice(0,2).map(part => part[0]).join('').toUpperCase() || 'U';
  }
  function fmtDate(value) {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('pt-BR', {dateStyle:'short', timeStyle:'short'});
  }
  function toast(message) {
    const el = $('#toast');
    el.textContent = message;
    el.classList.remove('hidden');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.add('hidden'), 3600);
  }
  async function apiFetch(url, options = {}) {
    const headers = {Accept:'application/json', ...(options.headers || {})};
    if (!(options.body instanceof FormData) && options.body !== undefined && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const response = await window.DataUnivcAuth.fetch(url, {cache:'no-store', credentials:'same-origin', ...options, headers});
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json() : null;
    if (response.status === 401) {
      location.assign('/');
      throw new Error('Sua sessão administrativa expirou. Entre novamente.');
    }
    if (!response.ok) throw new Error(data?.detail || data?.erro || `Erro HTTP ${response.status}`);
    return data;
  }
  function setAvatar(element, person, urlOverride = '') {
    if (!element) return;
    const name = person?.name || person?.email || 'Usuário';
    const url = urlOverride || person?.avatar_url || '';
    element.textContent = initials(name);
    element.style.backgroundImage = '';
    element.dataset.avatarLoaded = '0';
    if (!url) return;
    const image = new Image();
    image.onload = () => {
      element.textContent = '';
      element.style.backgroundImage = `url("${url.replace(/"/g, '%22')}")`;
      element.dataset.avatarLoaded = '1';
    };
    image.onerror = () => {
      element.textContent = initials(name);
      element.style.backgroundImage = '';
      element.dataset.avatarLoaded = '0';
    };
    image.src = url;
  }
  function roleLabel(user) { return user.global_role === 'REITORIA' ? 'Reitoria' : 'Diretoria'; }
  function grantsHtml(user) {
    if (user.global_role === 'REITORIA') return '<span class="pill reitoria">Acesso global</span>';
    const visible = (user.directorates || []).map(g => `<span class="pill ${g.access === 'EDIT' ? 'edit' : 'read'}">${esc(g.code)} · ${g.access === 'EDIT' ? 'Edição' : 'Leitura'}${g.primary ? ' · principal' : ''}</span>`).join('');
    const hiddenCount = Number(user.hidden_directorate_count || 0);
    const preserved = hiddenCount ? `<span class="pill preserved">${hiddenCount} acesso${hiddenCount === 1 ? '' : 's'} oculto${hiddenCount === 1 ? '' : 's'} preservado${hiddenCount === 1 ? '' : 's'}</span>` : '';
    return visible + preserved || '—';
  }
  function renderSummary() {
    $('#summaryUsers').textContent = state.users.length;
    $('#summaryActive').textContent = state.users.filter(u => u.active).length;
    $('#summaryEdit').textContent = state.users.filter(u => u.global_role === 'REITORIA' || (u.directorates || []).some(g => g.access === 'EDIT')).length;
    $('#summarySessions').textContent = state.users.reduce((n,u) => n + Number(u.active_sessions || 0), 0);
  }
  function renderUsers() {
    const body = $('#usersBody');
    if (!state.users.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty-state">Nenhum usuário encontrado.</td></tr>';
      return;
    }
    body.innerHTML = state.users.map(user => `
      <tr>
        <td><div class="user-cell"><div class="table-avatar" data-user-avatar="${esc(user.id)}">${esc(initials(user.name))}</div><div class="user-copy"><strong>${esc(user.name || 'Usuário')}</strong><span>${esc(user.email)}</span></div></div></td>
        <td><span class="pill ${user.global_role === 'REITORIA' ? 'reitoria' : ''}">${roleLabel(user)}</span></td>
        <td>${grantsHtml(user)}</td>
        <td>${user.active ? '<span class="pill edit">Ativo</span>' : '<span class="pill blocked">Bloqueado</span>'}</td>
        <td>${fmtDate(user.last_seen_at)}</td>
        <td>${Number(user.active_sessions || 0)}</td>
        <td><div class="row-actions"><button class="icon-action" data-sessions="${esc(user.id)}">Sessões</button><button class="icon-action" data-edit="${esc(user.id)}">Editar</button></div></td>
      </tr>`).join('');
    body.querySelectorAll('[data-user-avatar]').forEach(el => {
      const user = state.users.find(item => item.id === el.dataset.userAvatar);
      setAvatar(el, user);
    });
    body.querySelectorAll('[data-edit]').forEach(button => button.addEventListener('click', () => openEdit(button.dataset.edit)));
    body.querySelectorAll('[data-sessions]').forEach(button => button.addEventListener('click', () => openSessions(button.dataset.sessions)));
  }
  function renderDirectorates() {
    const identityDirs = state.identity?.availableDirectorates || [];
    $('#directorateCards').innerHTML = identityDirs.length ? identityDirs.map(item => `
      <a class="directorate-card" href="${esc(state.identity.routeFor(item.code))}">
        <strong>${esc(item.code)}</strong><span>${esc(item.name)}</span><small>Abrir diretoria →</small>
      </a>`).join('') : '<div class="empty-state">Nenhuma diretoria disponível.</div>';
    $('#sidebarDirectorates').innerHTML = identityDirs.map(item => `<a class="sidebar-directorate" href="${esc(state.identity.routeFor(item.code))}"><span>${esc(item.code)}</span><small>Abrir</small></a>`).join('');
  }
  async function loadUsers() {
    const term = $('#userSearch').value.trim();
    $('#usersStatus').textContent = 'Carregando…';
    const data = await apiFetch(`/api/admin/users${term ? `?search=${encodeURIComponent(term)}` : ''}`);
    state.users = data.users || [];
    state.directorates = data.directorates || [];
    state.actorUserId = data.actor_user_id || '';
    $('#usersStatus').textContent = `${state.users.length} usuário${state.users.length === 1 ? '' : 's'}`;
    renderSummary();
    renderUsers();
  }
  function renderDirectorateEditor(user) {
    const grants = new Map((user?.directorates || []).map(g => [g.code, g]));
    const hiddenCount = Number(user?.hidden_directorate_count || 0);
    const hiddenNotice = $('#hiddenGrantNotice');
    hiddenNotice.classList.toggle('hidden', !hiddenCount);
    hiddenNotice.textContent = hiddenCount ? `${hiddenCount} acesso${hiddenCount === 1 ? '' : 's'} em diretoria temporariamente oculta está${hiddenCount === 1 ? '' : 'o'} preservado${hiddenCount === 1 ? '' : 's'} e não será apagado ao salvar.` : '';
    $('#directorateEditor').innerHTML = state.directorates.map(d => {
      const grant = grants.get(d.code);
      const level = grant?.access || 'NONE';
      return `<div class="directorate-row">
        <div class="directorate-label"><strong>${esc(d.code)}</strong><small>${esc(d.name)}</small></div>
        <select data-code-access="${esc(d.code)}" aria-label="Acesso a ${esc(d.code)}">
          <option value="NONE" ${level === 'NONE' ? 'selected' : ''}>Sem acesso</option>
          <option value="READ" ${level === 'READ' ? 'selected' : ''}>Somente leitura</option>
          <option value="EDIT" ${level === 'EDIT' ? 'selected' : ''}>Edição</option>
        </select>
        <label class="primary-choice"><input type="radio" name="primaryDirectorate" value="${esc(d.code)}" ${grant?.primary ? 'checked' : ''} ${level === 'NONE' ? 'disabled' : ''}> Principal</label>
      </div>`;
    }).join('');
    $('#directorateEditor').querySelectorAll('[data-code-access]').forEach(select => select.addEventListener('change', () => {
      const code = select.dataset.codeAccess;
      const radio = document.querySelector(`input[name="primaryDirectorate"][value="${CSS.escape(code)}"]`);
      radio.disabled = select.value === 'NONE';
      if (radio.disabled && radio.checked) radio.checked = false;
      const enabled = [...document.querySelectorAll('[data-code-access]')].filter(item => item.value !== 'NONE');
      const selectedPrimary = document.querySelector('input[name="primaryDirectorate"]:checked');
      if (!selectedPrimary && enabled.length) {
        const firstCode = enabled[0].dataset.codeAccess;
        const firstRadio = document.querySelector(`input[name="primaryDirectorate"][value="${CSS.escape(firstCode)}"]`);
        if (firstRadio) firstRadio.checked = true;
      }
    }));
  }
  function syncRoleUi() {
    const reitoria = $('#editRole').value === 'REITORIA';
    $('#directorateFieldset').classList.toggle('hidden', reitoria);
  }
  function resetAvatarEditor(person) {
    state.avatarRemoveRequested = false;
    $('#editAvatar').value = '';
    const preview = $('#editAvatarPreview');
    setAvatar(preview, person || {name: $('#editName').value || 'Usuário'});
    $('#removeAvatarButton').classList.toggle('hidden', !person?.id);
  }
  function openEdit(id) {
    const user = state.users.find(u => u.id === id);
    if (!user) return;
    $('#editingUserId').value = user.id;
    $('#dialogTitle').textContent = 'Editar usuário';
    $('#editName').value = user.name || '';
    $('#editEmail').value = user.email || '';
    $('#editPassword').value = '';
    $('#editPasswordConfirm').value = '';
    $('#passwordLabel').textContent = 'Nova senha';
    $('#passwordHelp').textContent = 'Deixe em branco para manter a senha atual. A senha existente nunca é exibida pelo Data UNIVC.';
    $('#editRole').value = user.global_role;
    $('#editActive').checked = Boolean(user.active);
    renderDirectorateEditor(user);
    syncRoleUi();
    resetAvatarEditor(user);
    $('#dialogMessage').classList.add('hidden');
    $('#userDialog').showModal();
  }
  function openNew() {
    $('#editingUserId').value = '';
    $('#dialogTitle').textContent = 'Novo usuário';
    $('#editName').value = '';
    $('#editEmail').value = '';
    $('#editPassword').value = '';
    $('#editPasswordConfirm').value = '';
    $('#passwordLabel').textContent = 'Senha inicial';
    $('#passwordHelp').textContent = 'Defina a senha inicial. Ela será enviada diretamente ao Supabase Auth e não ficará armazenada no Data UNIVC.';
    $('#editRole').value = 'DIRECTORATE';
    $('#editActive').checked = true;
    renderDirectorateEditor(null);
    syncRoleUi();
    resetAvatarEditor(null);
    $('#removeAvatarButton').classList.add('hidden');
    $('#dialogMessage').classList.add('hidden');
    $('#userDialog').showModal();
  }
  function formPayload() {
    const role = $('#editRole').value;
    const directorates = [];
    if (role !== 'REITORIA') {
      document.querySelectorAll('[data-code-access]').forEach(select => {
        if (select.value === 'NONE') return;
        const code = select.dataset.codeAccess;
        directorates.push({
          code,
          access: select.value,
          primary: document.querySelector(`input[name="primaryDirectorate"][value="${CSS.escape(code)}"]`)?.checked || false,
        });
      });
    }
    return {
      name: $('#editName').value.trim(),
      email: $('#editEmail').value.trim(),
      password: $('#editPassword').value || null,
      global_role: role,
      active: $('#editActive').checked,
      directorates,
    };
  }
  async function uploadAvatar(userId) {
    const file = $('#editAvatar').files?.[0];
    if (!file) return null;
    const form = new FormData();
    form.append('avatar', file, file.name);
    return await apiFetch(`/api/admin/users/${encodeURIComponent(userId)}/avatar`, {method:'POST', body:form});
  }
  async function saveUser(event) {
    event.preventDefault();
    if (event.submitter?.value === 'cancel') {
      $('#userDialog').close();
      return;
    }
    const id = $('#editingUserId').value;
    const existing = id ? state.users.find(user => user.id === id) : null;
    const body = formPayload();
    const confirmPassword = $('#editPasswordConfirm').value;
    if (!id && !body.password) {
      $('#dialogMessage').textContent = 'Defina uma senha inicial para o novo usuário.';
      $('#dialogMessage').classList.remove('hidden');
      return;
    }
    if (body.password && body.password.length < 8) {
      $('#dialogMessage').textContent = 'A senha deve ter pelo menos 8 caracteres.';
      $('#dialogMessage').classList.remove('hidden');
      return;
    }
    if ((body.password || confirmPassword) && body.password !== confirmPassword) {
      $('#dialogMessage').textContent = 'A confirmação de senha não confere.';
      $('#dialogMessage').classList.remove('hidden');
      return;
    }
    if (body.global_role !== 'REITORIA' && !body.directorates.length && !Number(existing?.hidden_directorate_count || 0)) {
      $('#dialogMessage').textContent = 'Selecione pelo menos uma diretoria para este usuário.';
      $('#dialogMessage').classList.remove('hidden');
      return;
    }
    const button = $('#saveUserButton');
    button.disabled = true;
    $('#dialogMessage').classList.add('hidden');
    try {
      const sensitiveSelfChange = Boolean(id && id === state.actorUserId && (body.password || (existing && body.email.toLowerCase() !== String(existing.email || '').toLowerCase())));
      const result = await apiFetch(id ? `/api/admin/users/${encodeURIComponent(id)}` : '/api/admin/users', {
        method: id ? 'PATCH' : 'POST',
        body: JSON.stringify(body),
      });
      const savedUser = id ? result.user : result;
      let avatarWarning = '';
      try {
        if (state.avatarRemoveRequested && id && !$('#editAvatar').files?.[0]) {
          await apiFetch(`/api/admin/users/${encodeURIComponent(savedUser.id)}/avatar`, {method:'DELETE'});
        }
        if ($('#editAvatar').files?.[0]) await uploadAvatar(savedUser.id);
      } catch (avatarError) {
        avatarWarning = avatarError.message || 'Não foi possível atualizar a foto de perfil.';
      }
      $('#userDialog').close();
      if (sensitiveSelfChange) {
        alert('Seu e-mail ou senha foi alterado. Por segurança, a sessão atual foi revogada. Entre novamente com as novas credenciais.');
        location.assign('/');
        return;
      }
      toast(avatarWarning ? `${id ? 'Usuário atualizado' : 'Usuário criado'}, mas a foto não foi salva: ${avatarWarning}` : (id ? 'Usuário atualizado.' : 'Usuário criado e pronto para entrar.'));
      await Promise.all([loadUsers(), loadAudit()]);
    } catch (error) {
      $('#dialogMessage').textContent = error.message;
      $('#dialogMessage').classList.remove('hidden');
    } finally {
      button.disabled = false;
    }
  }
  async function openSessions(userId) {
    const user = state.users.find(u => u.id === userId);
    state.selectedUserId = userId;
    $('#sessionDialogTitle').textContent = `Sessões · ${user?.name || 'Usuário'}`;
    const data = await apiFetch(`/api/admin/users/${encodeURIComponent(userId)}/sessions`);
    const rows = data.sessions || [];
    $('#sessionList').innerHTML = rows.length ? rows.map(s => `<div class="session-item"><div><strong>${s.current ? 'Sessão atual' : 'Sessão ativa'}</strong><small>Iniciada: ${fmtDate(s.created_at)} · Última atividade: ${fmtDate(s.last_seen_at)}</small><small>Expira: ${fmtDate(s.expires_at)}</small></div>${s.current ? '' : `<button class="icon-action" data-revoke-session="${esc(s.id)}">Revogar</button>`}</div>`).join('') : '<div class="empty-state">Nenhuma sessão ativa.</div>';
    $('#revokeAllSessionsButton').disabled = userId === state.actorUserId || !rows.length;
    $('#sessionList').querySelectorAll('[data-revoke-session]').forEach(button => button.addEventListener('click', () => revokeSession(button.dataset.revokeSession)));
    $('#sessionDialog').showModal();
  }
  async function revokeSession(id) {
    if (!confirm('Revogar esta sessão?')) return;
    await apiFetch(`/api/admin/sessions/${encodeURIComponent(id)}/revoke`, {method:'POST', body:'{}'});
    toast('Sessão revogada.');
    await Promise.all([openSessions(state.selectedUserId), loadUsers(), loadAudit()]);
  }
  async function revokeAll() {
    if (!state.selectedUserId || !confirm('Revogar todas as sessões deste usuário?')) return;
    await apiFetch(`/api/admin/users/${encodeURIComponent(state.selectedUserId)}/sessions/revoke`, {method:'POST', body:'{}'});
    toast('Sessões revogadas.');
    $('#sessionDialog').close();
    await Promise.all([loadUsers(), loadAudit()]);
  }
  const auditLabels = {
    USER_PROVISIONED:'Usuário criado', PERMISSION_CHANGED:'Permissões alteradas', IDENTITY_CHANGED:'Identidade alterada',
    PROFILE_AVATAR_CHANGED:'Foto de perfil', USER_DISABLED:'Usuário bloqueado', USER_ENABLED:'Usuário reativado',
    SESSION_REVOKED:'Sessão revogada', LOGIN_SUCCESS:'Login', LOGIN_FAILED:'Falha de login', AUTHORIZATION_DENIED:'Acesso negado',
  };
  async function loadAudit() {
    const data = await apiFetch('/api/admin/audit?limit=100');
    const list = $('#auditList');
    const events = data.events || [];
    list.innerHTML = events.length ? events.map(e => `<div class="audit-item"><time>${fmtDate(e.created_at)}</time><span class="audit-event">${esc(auditLabels[e.event_type] || e.event_type)}</span><span class="audit-detail">${esc(e.target_name || e.actor_name || e.email || e.directorate_code || 'Evento do sistema')}</span><span class="pill ${e.outcome === 'DENIED' || e.outcome === 'FAILURE' ? 'blocked' : 'edit'}">${esc(e.outcome)}</span></div>`).join('') : '<div class="empty-state">Nenhum evento de segurança registrado.</div>';
  }
  async function logout() {
    await window.DataUnivcAuth.logout();
    location.assign('/');
  }
  function bindNav() {
    document.querySelectorAll('[data-admin-nav]').forEach(link => link.addEventListener('click', () => {
      document.querySelectorAll('[data-admin-nav]').forEach(item => item.classList.toggle('active', item === link));
    }));
  }
  async function start() {
    state.identity = await window.DataUnivcIdentity.load();
    if (!state.identity?.globalAccess) {
      location.assign('/');
      return;
    }
    state.actorUserId = state.identity.id;
    $('#reitoriaUserName').textContent = state.identity.name;
    $('#reitoriaUserEmail').textContent = state.identity.email;
    setAvatar($('#reitoriaAvatar'), state.identity);
    renderDirectorates();
    await Promise.all([loadUsers(), loadAudit()]);
  }

  $('#userForm').addEventListener('submit', saveUser);
  $('#editRole').addEventListener('change', syncRoleUi);
  $('#editName').addEventListener('input', () => {
    if (!$('#editAvatar').files?.[0] && !$('#editingUserId').value) setAvatar($('#editAvatarPreview'), {name:$('#editName').value || 'Usuário'});
  });
  $('#editAvatar').addEventListener('change', () => {
    const file = $('#editAvatar').files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      $('#editAvatar').value = '';
      $('#dialogMessage').textContent = 'A foto de perfil deve ter no máximo 2 MB.';
      $('#dialogMessage').classList.remove('hidden');
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    setAvatar($('#editAvatarPreview'), {name:$('#editName').value || 'Usuário'}, previewUrl);
    state.avatarRemoveRequested = false;
  });
  $('#removeAvatarButton').addEventListener('click', () => {
    state.avatarRemoveRequested = true;
    $('#editAvatar').value = '';
    setAvatar($('#editAvatarPreview'), {name:$('#editName').value || 'Usuário'}, '');
    $('#removeAvatarButton').classList.add('hidden');
  });
  $('#newUserButton').addEventListener('click', openNew);
  $('#refreshAuditButton').addEventListener('click', () => loadAudit().catch(error => toast(error.message)));
  $('#closeSessionDialog').addEventListener('click', () => $('#sessionDialog').close());
  $('#closeSessionDialogFooter').addEventListener('click', () => $('#sessionDialog').close());
  $('#revokeAllSessionsButton').addEventListener('click', () => revokeAll().catch(error => toast(error.message)));
  $('#reitoriaLogout').addEventListener('click', () => logout().catch(error => toast(error.message)));
  let searchTimer;
  $('#userSearch').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadUsers().catch(error => toast(error.message)), 260);
  });
  bindNav();
  start().catch(error => {
    console.error(error);
    toast(error.message || 'Não foi possível carregar a Área da Reitoria.');
  });
})();
