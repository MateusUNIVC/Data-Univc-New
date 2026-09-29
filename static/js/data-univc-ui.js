(() => {
  const root = window.DataUNIVC = window.DataUNIVC || {};

  const paths = {
    dashboard:'<path d="M4 4h6v6H4zM14 4h6v4h-6zM14 12h6v8h-6zM4 14h6v6H4z"/>',
    users:'<path d="M16 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M2 20c0-3 2.5-5 6-5s6 2 6 5M14 14c4.5-.6 8 1.4 8 5"/>',
    department:'<path d="M4 20V7l8-4 8 4v13"/><path d="M8 10h2M14 10h2M8 14h2M14 14h2M9 20v-3h6v3"/>',
    experience:'<circle cx="12" cy="12" r="9"/><path d="M8 14c2.1 2 5.9 2 8 0M9 9h.01M15 9h.01"/>',
    compare:'<path d="M7 7h12l-3-3M17 17H5l3 3"/><path d="m19 7-3 3M5 17l3-3"/>',
    database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    sync:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.2 8.2A7 7 0 0 1 18 6l2 1M17.8 15.8A7 7 0 0 1 6 18l-2-1"/>',
    sei:'<path d="M6 8.5A7 7 0 0 1 18.8 7M18 3v5h-5"/><path d="M18 15.5A7 7 0 0 1 5.2 17M6 21v-5h5"/><circle cx="12" cy="12" r="2.3"/>',
    download:'<path d="M12 3v12M8 11l4 4 4-4M5 20h14"/>',
    upload:'<path d="M12 20V8M8 12l4-4 4 4M5 4h14"/>',
    target:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m18 6 3-3"/>',
    plan:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    file:'<path d="M4 6h6l2 2h8v11H4z"/><path d="M12 11v6M9 14l3 3 3-3"/>',
    shield:'<path d="M12 3 19 6v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6z"/><path d="m9 12 2 2 4-5"/>',
    calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18"/>',
    filter:'<path d="M4 5h16l-6.3 7.1V19l-3.4 2v-8.9z"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/>',
    eye:'<path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/>',
    eyeOff:'<path d="m4 4 16 16M10.7 6.1c.4-.1.8-.1 1.3-.1 6.1 0 9.5 6 9.5 6a16 16 0 0 1-2.6 3.2M6.3 6.8C3.9 8.5 2.5 12 2.5 12s3.4 6 9.5 6c1.7 0 3.2-.5 4.5-1.1M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    logout:'<path d="M10 5H6.7A1.7 1.7 0 0 0 5 6.7v10.6A1.7 1.7 0 0 0 6.7 19H10M14.5 8.5 18 12l-3.5 3.5M18 12H9"/>',
    back:'<path d="m15 18-6-6 6-6M9 12h10"/>',
    help:'<circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.4 2.4 0 1 1 3.5 2.2c-.9.5-1.3 1-1.3 2M12 17h.01"/>'
  };

  root.icon = (name, {className = 'du-icon', size = 18} = {}) => {
    const path = paths[name] || paths.help;
    return `<span class="${className}" aria-hidden="true"><svg viewBox="0 0 24 24" width="${size}" height="${size}">${path}</svg></span>`;
  };
  root.iconPath = name => paths[name] || paths.help;

  root.routeForDirectorate = code => {
    const key = String(code || '').trim().toUpperCase();
    if (key === 'DADM') return '/dadm?diretoria=DADM';
    if (key === 'DPE') return '/dpe?diretoria=DPE';
    if (key === 'DM') return '/dm?diretoria=DM';
    return `/?diretoria=${encodeURIComponent(key)}`;
  };

  root.sidebar = {
    mount(options = {}) {
      const sidebar = document.querySelector(options.sidebar || '.sidebar');
      const button = document.querySelector(options.button || '.ui-sidebar-collapse');
      if (!sidebar || !button || button.dataset.duSidebarBound === '1') return;
      const collapsedClass = options.collapsedClass || 'ui-sidebar-collapsed';
      const storageKey = options.storageKey || 'data-univc-sidebar';
      const breakpoint = Number(options.breakpoint || 980);
      const body = document.body;
      const syncLabel = collapsed => {
        const label = collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral';
        button.setAttribute('aria-label', label);
        button.title = label;
        button.dataset.collapsed = collapsed ? '1' : '0';
      };
      const apply = collapsed => {
        if (window.innerWidth <= breakpoint) collapsed = false;
        body.classList.toggle(collapsedClass, collapsed);
        syncLabel(collapsed);
        try { localStorage.setItem(storageKey, collapsed ? 'collapsed' : 'expanded'); } catch (_) {}
      };
      let initial = false;
      try { initial = localStorage.getItem(storageKey) === 'collapsed'; } catch (_) {}
      apply(initial);
      button.addEventListener('click', () => apply(!body.classList.contains(collapsedClass)));
      window.addEventListener('resize', () => {
        if (window.innerWidth <= breakpoint) body.classList.remove(collapsedClass);
        syncLabel(body.classList.contains(collapsedClass));
      });
      button.dataset.duSidebarBound = '1';
    },
  };

  root.progress = {
    render(container, options = {}) {
      if (!container) return;
      const raw = Number(options.percent);
      const determinate = Number.isFinite(raw);
      const pct = determinate ? Math.max(0, Math.min(100, raw)) : null;
      const meta = Array.isArray(options.meta) ? options.meta.filter(item => item && item.value !== undefined && item.value !== null) : [];
      container.className = `du-operation-progress${determinate ? '' : ' is-indeterminate'}${options.status === 'error' ? ' is-error' : ''}${options.status === 'success' ? ' is-success' : ''}`;
      container.innerHTML = `<div class="du-operation-head"><div class="du-operation-copy"><strong>${escapeHtml(options.title || 'Processando')}</strong><span>${escapeHtml(options.message || 'Aguarde enquanto o Data UNIVC conclui a operação.')}</span></div>${pct == null ? '' : `<div class="du-operation-percent">${Math.round(pct)}%</div>`}</div><div class="du-progress-track"><div class="du-progress-fill"${pct == null ? '' : ` style="width:${pct}%"`}></div></div>${options.stage ? `<div class="du-operation-stage">${escapeHtml(options.stage)}</div>` : ''}${meta.length ? `<div class="du-operation-meta">${meta.map(item => `<span>${escapeHtml(item.label || '')} <strong>${escapeHtml(String(item.value))}</strong></span>`).join('')}</div>` : ''}`;
      container.classList.remove('hidden');
    },
    hide(container) { if (container) container.classList.add('hidden'); },
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function hydrateIcons() {
    document.querySelectorAll('[data-du-icon]').forEach(el => {
      const name = el.dataset.duIcon;
      if (!name) return;
      el.innerHTML = root.icon(name, {className:'du-icon'});
      el.dataset.duHydrated = '1';
    });
    document.querySelectorAll('[data-du-password-toggle]').forEach(button => {
      if (button.dataset.duBound === '1') return;
      const selector = button.dataset.duPasswordToggle;
      const input = selector ? document.querySelector(selector) : button.closest('.du-password')?.querySelector('input');
      if (!input) return;
      button.innerHTML = root.icon('eye');
      button.addEventListener('click', () => {
        const reveal = input.type === 'password';
        input.type = reveal ? 'text' : 'password';
        button.innerHTML = root.icon(reveal ? 'eyeOff' : 'eye');
        button.setAttribute('aria-label', reveal ? 'Ocultar valor' : 'Mostrar valor');
      });
      button.dataset.duBound = '1';
    });
  }


  /*
   * Shared searchable select.
   * Keeps the native <select> as the source of truth so existing filters,
   * change listeners and API contracts continue to work unchanged.
   */
  root.searchableSelect = (() => {
    const instances = new WeakMap();

    const normalize = value => String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase('pt-BR')
      .replace(/\s+/g, ' ')
      .trim();

    const stateFor = select => instances.get(select) || null;

    function selectedLabel(select) {
      const selected = select.options?.[select.selectedIndex];
      if (!selected) return '';
      const first = select.options?.[0];
      const isEmptyChoice = selected === first && (selected.value === '' || selected.dataset.comboboxPlaceholderOption === '1');
      return isEmptyChoice ? '' : String(selected.textContent || '').trim();
    }

    function clearValue(select) {
      if (select.dataset.comboboxClearValue !== undefined) return select.dataset.comboboxClearValue;
      return select.options?.[0]?.value ?? '';
    }

    function matchingOptions(select, query = '') {
      const needle = normalize(query);
      return Array.from(select.options || []).filter((item, index) => {
        if (!needle) return true;
        if (index === 0 && (item.value === '' || item.dataset.comboboxPlaceholderOption === '1')) return false;
        return normalize(item.textContent).includes(needle);
      });
    }

    function setActive(instance, nextIndex) {
      const buttons = Array.from(instance.menu.querySelectorAll('.du-combobox-option'));
      if (!buttons.length) {
        instance.activeIndex = -1;
        return;
      }
      instance.activeIndex = Math.max(0, Math.min(buttons.length - 1, nextIndex));
      buttons.forEach((button, index) => button.classList.toggle('active', index === instance.activeIndex));
      buttons[instance.activeIndex]?.scrollIntoView({block:'nearest'});
    }

    function render(instance, query = '') {
      const {select, shell, menu} = instance;
      const matches = matchingOptions(select, query);
      instance.activeIndex = -1;
      if (!matches.length) {
        menu.innerHTML = '<div class="du-combobox-empty">Nenhuma opção encontrada.</div>';
        return;
      }
      menu.innerHTML = matches.map(item => {
        const selected = String(item.value) === String(select.value);
        return `<button type="button" class="du-combobox-option${selected ? ' selected' : ''}" role="option" aria-selected="${selected ? 'true' : 'false'}" data-combobox-value="${escapeHtml(item.value)}">${escapeHtml(item.textContent || '')}</button>`;
      }).join('');
      menu.querySelectorAll('.du-combobox-option').forEach(button => {
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', () => {
          select.value = button.dataset.comboboxValue ?? '';
          select.dispatchEvent(new Event('change', {bubbles:true}));
          close(select);
        });
      });
      shell.dataset.optionCount = String(matches.length);
    }

    function open(select, query = null) {
      const instance = stateFor(select);
      if (!instance || select.disabled) return;
      const term = query === null ? instance.input.value : query;
      render(instance, term);
      instance.menu.hidden = false;
      instance.shell.classList.add('open');
      instance.input.setAttribute('aria-expanded', 'true');
    }

    function close(select, {restore = true} = {}) {
      const instance = stateFor(select);
      if (!instance) return;
      instance.menu.hidden = true;
      instance.shell.classList.remove('open');
      instance.input.setAttribute('aria-expanded', 'false');
      instance.activeIndex = -1;
      if (restore) instance.input.value = selectedLabel(select);
    }

    function sync(select) {
      const instance = stateFor(select);
      if (!instance) return;
      const {shell, input, clear, toggle} = instance;
      const disabled = Boolean(select.disabled);
      shell.classList.toggle('disabled', disabled);
      input.disabled = disabled;
      toggle.disabled = disabled;
      clear.disabled = disabled;
      input.placeholder = disabled
        ? (select.options?.[0]?.textContent || select.dataset.comboboxPlaceholder || 'Selecione uma opção')
        : (select.dataset.comboboxPlaceholder || 'Buscar...');
      if (document.activeElement !== input || disabled) input.value = selectedLabel(select);
      const emptyValue = String(clearValue(select));
      clear.hidden = disabled || String(select.value) === emptyValue;
      if (disabled) close(select);
      else if (shell.classList.contains('open')) render(instance, input.value || '');
    }

    function attach(select) {
      if (!select) return null;
      const existing = stateFor(select);
      if (existing) {
        sync(select);
        return existing;
      }

      const shell = document.createElement('div');
      shell.className = 'du-combobox';
      const menuId = `${select.id || 'du-combobox'}-menu-${Math.random().toString(36).slice(2, 8)}`;
      shell.innerHTML = `
        <div class="du-combobox-control">
          <input class="du-combobox-input" type="search" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${escapeHtml(menuId)}" placeholder="${escapeHtml(select.dataset.comboboxPlaceholder || 'Buscar...')}">
          <button class="du-combobox-clear" type="button" aria-label="Limpar seleção" title="Limpar seleção">×</button>
          <button class="du-combobox-toggle" type="button" aria-label="Abrir opções" title="Abrir opções">⌄</button>
        </div>
        <div id="${escapeHtml(menuId)}" class="du-combobox-menu" role="listbox" hidden></div>`;
      select.insertAdjacentElement('afterend', shell);
      select.classList.add('du-combobox-native-hidden');

      const instance = {
        select,
        shell,
        input: shell.querySelector('.du-combobox-input'),
        menu: shell.querySelector('.du-combobox-menu'),
        clear: shell.querySelector('.du-combobox-clear'),
        toggle: shell.querySelector('.du-combobox-toggle'),
        activeIndex: -1,
      };
      instances.set(select, instance);

      instance.input.addEventListener('focus', () => {
        instance.input.select();
        open(select, '');
      });
      instance.input.addEventListener('input', () => open(select, instance.input.value));
      instance.input.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          if (!instance.shell.classList.contains('open')) open(select, instance.input.value);
          setActive(instance, instance.activeIndex + (event.key === 'ArrowDown' ? 1 : -1));
          return;
        }
        if (event.key === 'Enter' && instance.shell.classList.contains('open')) {
          const active = instance.menu.querySelector('.du-combobox-option.active');
          if (active) {
            event.preventDefault();
            active.click();
          }
          return;
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          close(select);
        }
      });
      instance.input.addEventListener('blur', () => setTimeout(() => close(select), 100));
      instance.toggle.addEventListener('mousedown', event => event.preventDefault());
      instance.toggle.addEventListener('click', () => {
        if (instance.shell.classList.contains('open')) close(select, {restore:false});
        else {
          instance.input.focus();
          open(select, '');
        }
      });
      instance.clear.addEventListener('mousedown', event => event.preventDefault());
      instance.clear.addEventListener('click', () => {
        select.value = clearValue(select);
        select.dispatchEvent(new Event('change', {bubbles:true}));
        close(select);
      });
      select.addEventListener('change', () => sync(select));
      sync(select);
      return instance;
    }

    function refresh(select) {
      if (!select) return null;
      return attach(select);
    }

    function destroy(select) {
      const instance = stateFor(select);
      if (!instance) return;
      instance.shell.remove();
      select.classList.remove('du-combobox-native-hidden');
      instances.delete(select);
    }

    return {attach, refresh, sync, close, destroy, normalize};
  })();

  root.hydrate = hydrateIcons;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', hydrateIcons);
  else hydrateIcons();
})();
