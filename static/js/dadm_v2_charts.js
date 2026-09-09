window.DADMV2 = window.DADMV2 || {};
(() => {
  const NS = window.DADMV2;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  NS.escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  NS.formatInt = value => Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
  NS.formatNumber = (value, digits = 1) => {
    if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
    return Number(value).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  };
  NS.formatPct = (value, digits = 1) => value == null ? '—' : `${NS.formatNumber(value, digits)}%`;
  NS.formatRating = value => value == null ? '—' : `${NS.formatNumber(value, 2)} / 10`;
  NS.formatSeconds = value => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    const total = Math.max(0, Math.round(Number(value)));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours) return `${hours}h ${String(minutes).padStart(2, '0')}m`;
    if (minutes) return `${minutes} min`;
    return `${seconds}s`;
  };
  NS.formatDateTime = value => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('pt-BR');
  };
  NS.metricValue = (item, metric) => {
    const value = item?.[metric];
    if (metric === 'attendances' || metric === 'protocols' || metric === 'people') return NS.formatInt(value);
    if (metric === 'tme_avg_seconds' || metric === 'tma_avg_seconds') return NS.formatSeconds(value);
    if (metric === 'rating_avg') return value == null ? 'Sem avaliações' : NS.formatRating(value);
    if (metric === 'rating_coverage_pct') return NS.formatPct(value);
    return NS.formatNumber(value, 1);
  };

  function palette(index) {
    const colors = ['#136f4f', '#5a70b8', '#b47a31', '#8b5fa4', '#3d8d93', '#b45454'];
    return colors[index % colors.length];
  }

  NS.lineChart = (container, rows, series, options = {}) => {
    if (!container) return;
    const data = Array.isArray(rows) ? rows : [];
    const references = (Array.isArray(options.references) ? options.references : []).filter(item => item && Number.isFinite(Number(item.value)));
    const points = [];
    data.forEach(row => series.forEach(def => {
      const value = def.value ? def.value(row) : row?.[def.key];
      if (value !== null && value !== undefined && Number.isFinite(Number(value))) points.push(Number(value));
    }));
    references.forEach(item => points.push(Number(item.value)));
    if (!data.length || !points.length) {
      container.innerHTML = '<div class="v2-empty">Sem dados calculáveis para este recorte.</div>';
      return;
    }
    const width = 920, height = options.height || 270;
    const m = { left: 52, right: 18, top: 25, bottom: 45 };
    let min = options.min ?? Math.min(...points);
    let max = options.max ?? Math.max(...points);
    if (min === max) { min = Math.max(0, min - 1); max += 1; }
    const pad = (max - min) * .10;
    if (options.min == null) min = Math.max(0, min - pad);
    if (options.max == null) max += pad;
    const x = i => m.left + (data.length === 1 ? (width - m.left - m.right) / 2 : (width - m.left - m.right) * i / (data.length - 1));
    const y = value => height - m.bottom - (Number(value) - min) / (max - min) * (height - m.top - m.bottom);
    const formatY = options.formatY || (value => NS.formatNumber(value, 0));
    const formatX = options.formatX || (row => row.period || '');
    let grid = '';
    for (let i = 0; i < 4; i++) {
      const value = min + (max - min) * i / 3;
      const yy = y(value);
      grid += `<line x1="${m.left}" x2="${width - m.right}" y1="${yy}" y2="${yy}" stroke="#e8efeb" stroke-width="1"/><text x="${m.left - 9}" y="${yy + 3}" text-anchor="end" font-size="9" fill="#718079">${NS.escapeHtml(formatY(value))}</text>`;
    }
    const step = Math.max(1, Math.ceil(data.length / 8));
    const labels = data.map((row, i) => i % step === 0 || i === data.length - 1 ? `<text x="${x(i)}" y="${height - 13}" text-anchor="middle" font-size="9" fill="#718079">${NS.escapeHtml(formatX(row))}</text>` : '').join('');
    const referenceLines = references.map((item, index) => {
      const yy = y(Number(item.value));
      const color = item.color || palette(index);
      const label = item.label || `Meta ${formatY(Number(item.value))}`;
      return `<line x1="${m.left}" x2="${width - m.right}" y1="${yy}" y2="${yy}" stroke="${color}" stroke-width="1.2" stroke-dasharray="5 5" opacity=".72"/><text x="${width - m.right - 2}" y="${Math.max(m.top + 9, yy - 5)}" text-anchor="end" font-size="8" fill="${color}">${NS.escapeHtml(label)}</text>`;
    }).join('');
    let paths = '';
    let circles = '';
    series.forEach((def, seriesIndex) => {
      const color = def.color || palette(seriesIndex);
      let segment = [];
      const segments = [];
      data.forEach((row, i) => {
        const raw = def.value ? def.value(row) : row?.[def.key];
        if (raw === null || raw === undefined || !Number.isFinite(Number(raw))) {
          if (segment.length) segments.push(segment);
          segment = [];
          return;
        }
        segment.push([x(i), y(Number(raw)), Number(raw), row]);
      });
      if (segment.length) segments.push(segment);
      segments.forEach(seg => {
        if (seg.length === 1) {
          paths += `<circle cx="${seg[0][0]}" cy="${seg[0][1]}" r="2.8" fill="${color}"/>`;
        } else {
          paths += `<polyline class="v2-chart-line" pathLength="100" points="${seg.map(p => `${p[0]},${p[1]}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`;
        }
      });
      data.forEach((row, i) => {
        const raw = def.value ? def.value(row) : row?.[def.key];
        if (raw === null || raw === undefined || !Number.isFinite(Number(raw))) return;
        const tooltip = def.tooltip ? def.tooltip(row, Number(raw)) : `${def.label}: ${formatY(Number(raw))}`;
        circles += `<circle class="v2-chart-point" cx="${x(i)}" cy="${y(Number(raw))}" r="4.7" fill="${color}" stroke="#fff" stroke-width="2" data-tip="${NS.escapeHtml(tooltip)}"/>`;
      });
    });
    const legend = series.map((def, i) => `<span class="v2-legend-item"><span class="v2-legend-dot" style="background:${def.color || palette(i)}"></span>${NS.escapeHtml(def.label)}</span>`).join('');
    container.innerHTML = `<div class="v2-chart-legend">${legend}</div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${NS.escapeHtml(options.ariaLabel || 'Gráfico de evolução')}">${grid}${referenceLines}${paths}${circles}${labels}</svg><div class="v2-chart-tooltip hidden"></div>`;
    bindTooltip(container);
  };

  NS.barChart = (container, rows, options = {}) => {
    if (!container) return;
    const data = (Array.isArray(rows) ? rows : []).filter(row => Number.isFinite(Number(options.value ? options.value(row) : row.value)));
    if (!data.length) {
      container.innerHTML = '<div class="v2-empty">Sem dados para este recorte.</div>';
      return;
    }
    const width = 920, height = options.height || 255, m = { left: 45, right: 18, top: 18, bottom: 50 };
    const values = data.map(row => Number(options.value ? options.value(row) : row.value));
    const max = Math.max(...values, 1);
    const slot = (width - m.left - m.right) / data.length;
    const barWidth = Math.min(55, slot * .62);
    const y = value => height - m.bottom - (Number(value) / max) * (height - m.top - m.bottom);
    const formatValue = options.formatValue || (value => NS.formatNumber(value, 0));
    let bars = '';
    data.forEach((row, i) => {
      const value = values[i], xx = m.left + slot * i + (slot - barWidth) / 2, yy = y(value), h = height - m.bottom - yy;
      const label = options.label ? options.label(row) : row.period || row.label || '';
      const tip = options.tooltip ? options.tooltip(row, value) : `${label}: ${formatValue(value)}`;
      bars += `<rect class="v2-chart-point" x="${xx}" y="${yy}" width="${barWidth}" height="${h}" rx="5" fill="#178b64" data-tip="${NS.escapeHtml(tip)}"/><text x="${xx + barWidth / 2}" y="${height - 18}" text-anchor="middle" font-size="9" fill="#718079">${NS.escapeHtml(label)}</text>`;
    });
    container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${NS.escapeHtml(options.ariaLabel || 'Gráfico de barras')}">${bars}</svg><div class="v2-chart-tooltip hidden"></div>`;
    bindTooltip(container);
  };

  NS.horizontalBars = (container, items, metric, options = {}) => {
    if (!container) return;
    const data = (Array.isArray(items) ? items : []).slice(0, options.limit || 12);
    if (!data.length) {
      container.innerHTML = '<div class="v2-empty">Nenhum item encontrado neste recorte.</div>';
      return;
    }
    const numeric = data.map(item => {
      const raw = item?.[metric];
      return raw === null || raw === undefined ? null : Number(raw);
    });
    const finite = numeric.filter(Number.isFinite);
    const max = finite.length ? Math.max(...finite, 1) : 1;
    container.innerHTML = data.map((item, index) => {
      const value = numeric[index];
      const label = options.label ? options.label(item) : item.name || item.label || '—';
      const width = Number.isFinite(value) ? Math.max(1.5, value / max * 100) : 0;
      const sample = metric === 'rating_avg' ? `${NS.formatInt(item.rating_count)} avaliações` : '';
      return `<div class="v2-bar-row" data-entity-id="${NS.escapeHtml(item.id || '')}" data-entity-type="${NS.escapeHtml(item.entity_type || '')}"><div class="v2-bar-label" title="${NS.escapeHtml(label)}">${NS.escapeHtml(label)}</div><div class="v2-bar-track"><div class="v2-bar-fill" style="width:${width}%"></div></div><div class="v2-bar-value">${NS.escapeHtml(NS.metricValue(item, metric))}${sample ? `<small>${NS.escapeHtml(sample)}</small>` : ''}</div></div>`;
    }).join('');
  };


  NS.snapshotComparisonChart = (container, profiles, metric, options = {}) => {
    if (!container) return;
    const period = options.period || '';
    const rows = (Array.isArray(profiles) ? profiles : []).map(profile => {
      const row = (profile.timeline || []).find(item => item.period === period) || {};
      const raw = row?.[metric];
      return {
        name: profile.entity?.name || profile.entity?.id || '—',
        value: raw == null ? null : Number(raw),
        sample: Number(row?.rating_count || 0),
      };
    });
    const finite = rows.map(row => row.value).filter(Number.isFinite);
    if (!finite.length) {
      container.innerHTML = '<div class="v2-empty">Sem dados calculáveis para este mês.</div>';
      return;
    }
    const min = Number.isFinite(Number(options.min)) ? Number(options.min) : 0;
    let max = Number.isFinite(Number(options.max)) ? Number(options.max) : Math.max(...finite, 1);
    if (max <= min) max = min + 1;
    const format = options.format || (value => NS.formatNumber(value, 1));
    container.innerHTML = `<div class="v2-snapshot-chart">${rows.map(row => {
      if (!Number.isFinite(row.value)) return `<div class="v2-snapshot-row"><div class="v2-snapshot-name" title="${NS.escapeHtml(row.name)}">${NS.escapeHtml(row.name)}</div><div class="v2-snapshot-track"></div><div class="v2-snapshot-value">—<small>sem dado</small></div></div>`;
      const pct = Math.max(0, Math.min(100, (row.value - min) / (max - min) * 100));
      const sample = options.rating ? `${NS.formatInt(row.sample)} avaliações` : NS.monthLabel(period);
      return `<div class="v2-snapshot-row"><div class="v2-snapshot-name" title="${NS.escapeHtml(row.name)}">${NS.escapeHtml(row.name)}</div><div class="v2-snapshot-track"><span class="v2-snapshot-dot" style="left:${pct}%" title="${NS.escapeHtml(`${row.name} · ${format(row.value)}`)}"></span></div><div class="v2-snapshot-value">${NS.escapeHtml(format(row.value))}<small>${NS.escapeHtml(sample)}</small></div></div>`;
    }).join('')}</div>`;
  };

  NS.ratingBars = (container, ratings) => {
    if (!container) return;
    const rows = Array.isArray(ratings) ? ratings : [];
    const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0);
    if (!total) {
      container.innerHTML = '<div class="v2-empty">Nenhuma avaliação válida no período.</div>';
      return;
    }
    const max = Math.max(...rows.map(row => Number(row.count || 0)), 1);
    container.innerHTML = [...rows].sort((a, b) => Number(b.rating) - Number(a.rating)).map(row => {
      const count = Number(row.count || 0);
      const pct = total ? count / total * 100 : 0;
      return `<div class="v2-rating-row"><strong>${NS.escapeHtml(row.rating)}</strong><div class="v2-rating-track"><div class="v2-rating-fill" style="width:${count / max * 100}%"></div></div><strong>${NS.formatInt(count)}</strong><small>${NS.formatPct(pct)}</small></div>`;
    }).join('');
  };

  function bindTooltip(container) {
    const tooltip = container.querySelector('.v2-chart-tooltip');
    if (!tooltip) return;
    container.querySelectorAll('[data-tip]').forEach(node => {
      node.addEventListener('mouseenter', event => {
        tooltip.textContent = node.dataset.tip || '';
        tooltip.classList.remove('hidden');
        positionTooltip(container, tooltip, event);
      });
      node.addEventListener('mousemove', event => positionTooltip(container, tooltip, event));
      node.addEventListener('mouseleave', () => tooltip.classList.add('hidden'));
    });
  }
  NS.tooltipPosition = ({ x, y, containerWidth, containerHeight, tooltipWidth, tooltipHeight, gap = 12, padding = 8 }) => {
    let left = x + gap;
    let top = y - tooltipHeight - gap;
    let side = 'top-right';
    if (left + tooltipWidth > containerWidth - padding) {
      left = x - tooltipWidth - gap;
      side = 'top-left';
    }
    if (left < padding) {
      left = padding;
      side = 'top';
    }
    if (top < padding) {
      top = y + gap;
      side = side === 'top-left' ? 'bottom-left' : side === 'top-right' ? 'bottom-right' : 'bottom';
    }
    if (top + tooltipHeight > containerHeight - padding) {
      top = Math.max(padding, containerHeight - tooltipHeight - padding);
    }
    left = Math.max(padding, Math.min(left, Math.max(padding, containerWidth - tooltipWidth - padding)));
    return { left, top, side };
  };

  function positionTooltip(container, tooltip, event) {
    const rect = container.getBoundingClientRect();
    const x = Math.max(8, Math.min(rect.width - 8, event.clientX - rect.left));
    const y = Math.max(8, Math.min(rect.height - 8, event.clientY - rect.top));
    tooltip.style.left = '8px';
    tooltip.style.top = '8px';
    tooltip.style.transform = 'none';
    const availableWidth = Math.max(80, Math.min(320, rect.width - 16));
    tooltip.style.maxWidth = `${availableWidth}px`;
    const tooltipWidth = Math.min(tooltip.offsetWidth, availableWidth);
    const tooltipHeight = tooltip.offsetHeight;
    const position = NS.tooltipPosition({
      x, y,
      containerWidth: rect.width,
      containerHeight: rect.height,
      tooltipWidth,
      tooltipHeight,
    });
    tooltip.style.left = `${position.left}px`;
    tooltip.style.top = `${position.top}px`;
    tooltip.dataset.side = position.side;
  }
})();
