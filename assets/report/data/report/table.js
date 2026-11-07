/* 通用表格：点表头排序，点行展开详情 */
(function () {
  'use strict';
  const { h } = window.R;

  // cfg: {columns:[{key, label, render(row), sort(row), cls, title}], rows, detail(row), sort:{key, dir}, emptyText, maxHeight}
  function table(cfg) {
    const state = { rows: cfg.rows || [], sort: cfg.sort || null, open: new Set() };
    const wrap = h('div', { class: 'table-wrap', style: cfg.maxHeight ? { maxHeight: cfg.maxHeight } : null });

    function sorted() {
      if (!state.sort) return state.rows;
      const col = cfg.columns.find((c) => c.key === state.sort.key);
      if (!col || !col.sort) return state.rows;
      const dir = state.sort.dir === 'asc' ? 1 : -1;
      return state.rows.slice().sort((a, b) => {
        const va = col.sort(a), vb = col.sort(b);
        const na = va === null || va === undefined || va === '', nb = vb === null || vb === undefined || vb === '';
        if (na && nb) return 0;
        if (na) return 1;  // 空值永远排最后
        if (nb) return -1;
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
    }

    function header() {
      return h('thead', null, h('tr', null, cfg.columns.map((c) => {
        const active = state.sort && state.sort.key === c.key;
        return h('th', {
          class: c.sort ? 'sortable' : null,
          title: c.title || null,
          onclick: c.sort ? () => {
            state.sort = active ? { key: c.key, dir: state.sort.dir === 'asc' ? 'desc' : 'asc' } : { key: c.key, dir: c.firstDir || 'desc' };
            render();
          } : null,
        }, c.label, active ? h('span', { class: 'arrow' }, state.sort.dir === 'asc' ? '↑' : '↓') : null);
      })));
    }

    function render() {
      wrap.textContent = '';
      const rows = sorted();
      const body = h('tbody');
      if (!rows.length) {
        body.appendChild(h('tr', null, h('td', { colspan: cfg.columns.length }, h('div', { class: 'empty' }, cfg.emptyText || '没有符合条件的外链网站'))));
      }
      for (const row of rows) {
        const isOpen = state.open.has(row);
        const tr = h('tr', {
          class: `row${isOpen ? ' open' : ''}`,
          onclick: (e) => {
            if (!cfg.detail || e.target.closest('a')) return;  // 点链接不展开
            if (state.open.has(row)) state.open.delete(row); else state.open.add(row);
            render();
          },
        }, cfg.columns.map((c) => {
          const v = c.render ? c.render(row) : row[c.key];
          return h('td', { class: c.cls || null }, v === null || v === undefined || v === '' ? '—' : v);
        }));
        body.appendChild(tr);
        if (isOpen && cfg.detail) body.appendChild(h('tr', { class: 'detail' }, h('td', { colspan: cfg.columns.length }, cfg.detail(row))));
      }
      wrap.appendChild(h('table', { class: 'data' }, header(), body));
    }

    render();
    return {
      el: wrap,
      update(rows) { state.rows = rows; render(); },
    };
  }

  // 展开详情：两列（名称 / 内容），内容为空的行不显示
  function detailGrid(pairs) {
    return h('div', { class: 'detail-grid' }, pairs.filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && !v.length))
      .map(([k, v]) => [h('div', { class: 'k' }, k), h('div', { class: 'v' }, v)]));
  }

  window.R.table = table;
  window.R.detailGrid = detailGrid;
})();
