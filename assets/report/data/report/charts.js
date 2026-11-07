/* 图表组件：分段条、横向条形、竖向柱、热力格、折线图、进度条。全部手写，不依赖外部库，离线也能看 */
(function () {
  'use strict';
  const { h, pct } = window.R;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function s(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
    return el;
  }
  const sum = (list, fn) => list.reduce((acc, x) => acc + (fn ? fn(x) : x), 0);

  // 一个整体拆成几块（≤7 块）。块里放占比（放得下才放），图例写名称和数量
  function segBar(parts, opts) {
    const o = opts || {};
    const shown = parts.filter((p) => p.value > 0);
    const total = sum(shown, (p) => p.value);
    const bar = h('div', {
      class: `segbar${o.thin ? ' thin' : ''}`,
      role: 'img',
      'aria-label': shown.map((p) => `${p.name} ${p.value}`).join('，'),
    });
    for (const p of shown) {
      const share = p.value / total;
      bar.appendChild(h('div', {
        class: 'seg',
        style: { flex: `${p.value} 1 0`, background: p.color, color: p.ink || '#fff' },
        tip: () => ({ title: o.title || '', rows: [{ color: p.color, name: p.name, value: `${p.value} 个 · ${pct(p.value, total)}` }], sub: p.desc }),
      }, !o.thin && share >= (o.labelMin || 0.08) ? pct(p.value, total) : null));
    }
    if (!total) bar.appendChild(h('div', { class: 'seg', style: { flex: '1 1 0', background: 'var(--grid)' } }));
    const legend = o.legend === false ? null : h('div', { class: 'legend' },
      parts.filter((p) => p.value > 0 || o.showZero).map((p) => h('span', { class: 'legend-item' },
        h('span', { class: 'legend-swatch', style: { background: p.color } }), `${p.name} ${p.value}`)));
    return h('div', null, bar, legend);
  }

  // 横向条形，每行可以是几段堆起来的。rows: [{label, segs:[{name, value, color}], value, sub, tipSub}]
  function hbars(rows, opts) {
    const o = opts || {};
    const totals = rows.map((r) => sum(r.segs, (x) => x.value));
    const max = o.max || Math.max(1, ...totals);
    const wrap = h('div', { class: 'hbars', style: { '--label-w': o.labelW || '130px', '--value-w': o.valueW || '92px' } });
    rows.forEach((row, i) => {
      const total = totals[i];
      const tip = () => ({
        title: row.label,
        rows: row.segs.filter((x) => x.value > 0 || o.tipZero).map((x) => ({ color: x.color, name: x.name, value: o.tipValue ? o.tipValue(x, total) : `${x.value}` })),
        sub: row.tipSub,
      });
      const track = h('div', { class: 'hbar-track', style: { width: `${(total / max) * 100}%` } });
      row.segs.filter((x) => x.value > 0).forEach((x) => {
        track.appendChild(h('div', { class: 'seg', style: { flex: `${x.value} 1 0`, background: x.color }, tip }));
      });
      wrap.appendChild(h('div', { class: 'hbar-row' },
        h('div', { class: 'hbar-label', title: row.label }, row.label),
        h('div', null, track),
        h('div', { class: 'hbar-value' }, row.value !== undefined ? row.value : String(total), row.sub ? h('span', null, row.sub) : null)));
    });
    return wrap;
  }

  // 竖向柱（按日期等），可以堆叠。cols: [{label, segs:[{name, value, color}]}]
  function columns(cols, opts) {
    const o = opts || {};
    const totals = cols.map((c) => sum(c.segs, (x) => x.value));
    const max = Math.max(1, ...totals);
    const area = h('div', { class: 'cols', style: { height: `${o.height || 210}px` } });
    cols.forEach((col, i) => {
      const tip = () => ({
        title: col.label,
        rows: col.segs.filter((x) => x.value > 0).map((x) => ({ color: x.color, name: x.name, value: `${x.value}` })),
        sub: `合计 ${totals[i]}`,
      });
      const stack = h('div', { class: 'col-stack', style: { height: `${(totals[i] / max) * 84}%` } });
      col.segs.filter((x) => x.value > 0).forEach((x) => {
        stack.appendChild(h('div', { class: 'seg', style: { flex: `${x.value} 1 0`, background: x.color }, tip }));
      });
      area.appendChild(h('div', { class: 'col' }, h('div', { class: 'col-total' }, String(totals[i])), stack));
    });
    const labels = h('div', { class: 'col-labels' }, cols.map((c) => h('div', null, c.label)));
    return h('div', null, area, labels);
  }

  // 热力格：行 × 列的数量，颜色越深越多（单色阶）
  function heat(rowKeys, colKeys, count, opts) {
    const o = opts || {};
    let max = 1;
    for (const r of rowKeys) for (const c of colKeys) max = Math.max(max, count(r, c));
    const head = h('tr', null, h('th', null), colKeys.map((c) => h('th', null, c)), h('th', null, '合计'));
    const body = rowKeys.map((r) => {
      const cells = colKeys.map((c) => {
        const n = count(r, c);
        const level = n === 0 ? 0 : Math.min(6, 1 + Math.floor((n / max) * 5.999));
        return h('td', {
          class: `cell l${level}`,
          style: { background: `var(--seq-${level})` },
          tip: () => ({ title: `${r} × ${c}`, rows: [{ value: `${n} 个`, name: o.unitName || '' }], sub: o.cellSub ? o.cellSub(r, c) : null }),
        }, n ? String(n) : '·');
      });
      const rowTotal = sum(colKeys, (c) => count(r, c));
      return h('tr', null, h('th', { class: 'row-head' }, r), cells, h('td', { class: 'total' }, String(rowTotal)));
    });
    const foot = h('tr', null, h('th', { class: 'row-head' }, '合计'),
      colKeys.map((c) => h('td', { class: 'total' }, String(sum(rowKeys, (r) => count(r, c))))), h('td', { class: 'total' }));
    return h('table', { class: 'heat' }, h('thead', null, head), h('tbody', null, body, foot));
  }

  // 纵轴刻度：步长取 1/2/5×10ⁿ 的整数，最多约 5 格
  function niceScale(v) {
    const raw = Math.max(1, v) / 4;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = Math.max(1, [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw));
    const ticks = Math.max(1, Math.ceil(Math.max(1, v) / step));
    return { max: ticks * step, step, ticks };
  }

  // 折线图：同一个单位的几条线（不做双纵轴）。cfg: {dates, series:[{name, color, values}], height}
  function lineChart(cfg) {
    const holder = h('div', { class: 'linechart' });
    const draw = () => {
      holder.textContent = '';
      const width = Math.max(320, holder.clientWidth || 700);
      const height = cfg.height || 260;
      const m = { l: 34, r: 92, t: 14, b: 28 };
      const iw = width - m.l - m.r, ih = height - m.t - m.b;
      const n = cfg.dates.length;
      const scale = niceScale(Math.max(...cfg.series.flatMap((x) => x.values)));
      const maxV = scale.max;
      const x = (i) => m.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
      const y = (v) => m.t + ih - (v / maxV) * ih;
      const svg = s('svg', { viewBox: `0 0 ${width} ${height}`, height, role: 'img', 'aria-label': cfg.label || '' });
      for (let k = 0; k <= scale.ticks; k++) {
        const v = scale.step * k;
        svg.appendChild(s('line', { class: k === 0 ? 'baseline' : 'gridline', x1: m.l, x2: m.l + iw, y1: y(v), y2: y(v) }));
        const t = s('text', { class: 'tick', x: m.l - 8, y: y(v) + 4, 'text-anchor': 'end' });
        t.textContent = String(v);
        svg.appendChild(t);
      }
      const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 70))));
      for (let i = 0; i < n; i += step) {
        const t = s('text', { class: 'tick', x: x(i), y: height - 8, 'text-anchor': 'middle' });
        t.textContent = cfg.dates[i].slice(5);
        svg.appendChild(t);
      }
      for (const ser of cfg.series) {
        const d = ser.values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
        svg.appendChild(s('path', { d, fill: 'none', stroke: ser.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      }
      // 线尾数值：两条线尾挨得太近就不标，靠图例和悬停
      const ends = cfg.series.map((ser) => ({ ser, v: ser.values[n - 1], py: y(ser.values[n - 1]) }));
      const apart = ends.every((a, i) => ends.every((b, j) => i === j || Math.abs(a.py - b.py) >= 15));
      for (const e of ends) {
        svg.appendChild(s('circle', { cx: x(n - 1), cy: e.py, r: 4, fill: e.ser.color, stroke: 'var(--card)', 'stroke-width': 2 }));
        if (apart) {
          const t = s('text', { class: 'end-label', x: x(n - 1) + 10, y: e.py + 4 });
          t.textContent = `${e.ser.name} ${e.v}`;
          svg.appendChild(t);
        }
      }
      // 悬停：竖线吸附到最近的日期，浮层列出每条线的值
      const cross = s('line', { class: 'crosshair', x1: 0, x2: 0, y1: m.t, y2: m.t + ih, visibility: 'hidden' });
      const dots = cfg.series.map((ser) => s('circle', { r: 4, fill: ser.color, stroke: 'var(--card)', 'stroke-width': 2, visibility: 'hidden' }));
      svg.appendChild(cross);
      dots.forEach((dot) => svg.appendChild(dot));
      const hit = s('rect', { x: m.l, y: m.t, width: iw, height: ih, fill: 'transparent', tabindex: 0 });
      let idx = n - 1;
      const moveTo = (i) => {
        idx = Math.max(0, Math.min(n - 1, i));
        cross.setAttribute('x1', x(idx)); cross.setAttribute('x2', x(idx)); cross.setAttribute('visibility', 'visible');
        dots.forEach((dot, k) => { dot.setAttribute('cx', x(idx)); dot.setAttribute('cy', y(cfg.series[k].values[idx])); dot.setAttribute('visibility', 'visible'); });
      };
      hit.addEventListener('pointermove', (e) => {
        const r = svg.getBoundingClientRect();
        const px = ((e.clientX - r.left) / r.width) * width;
        moveTo(n <= 1 ? 0 : Math.round(((px - m.l) / iw) * (n - 1)));
      });
      hit.addEventListener('focus', () => moveTo(idx));
      hit.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') moveTo(idx - 1);
        if (e.key === 'ArrowRight') moveTo(idx + 1);
      });
      hit.addEventListener('pointerleave', () => {
        cross.setAttribute('visibility', 'hidden');
        dots.forEach((dot) => dot.setAttribute('visibility', 'hidden'));
      });
      hit._tip = () => ({
        title: cfg.dates[idx],
        rows: cfg.series.map((ser) => ({ kind: 'line', color: ser.color, name: ser.name, value: String(ser.values[idx]) })),
        sub: cfg.tipSub ? cfg.tipSub(idx) : null,
      });
      svg.appendChild(hit);
      holder.appendChild(svg);
    };
    holder._redraw = draw;
    requestAnimationFrame(draw);
    return holder;
  }

  // 进度条：复查了几次 / 7 次
  function meter(value, max, warnAt) {
    const ratio = Math.min(1, value / max);
    return h('div', { class: 'meter' },
      h('div', { class: 'meter-track' }, h('div', { class: `meter-fill${value >= warnAt ? ' warn' : ''}`, style: { width: `${ratio * 100}%` } })),
      h('span', { class: 'meter-text' }, `${value}/${max}`));
  }

  function legend(items) {
    return h('div', { class: 'legend' }, items.map((it) => h('span', { class: 'legend-item' },
      h('span', { class: it.kind === 'line' ? 'legend-line' : 'legend-swatch', style: { background: it.color } }), it.name)));
  }

  window.Charts = { segBar, hbars, columns, heat, lineChart, meter, legend };
})();
