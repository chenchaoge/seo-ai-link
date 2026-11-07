/* 通用小工具：建元素、颜色和状态定义、日期、提示浮层、卡片和数字块 */
(function () {
  'use strict';

  // 建元素：字符串一律当文字放（textContent），不拼 HTML，数据里的外链网站名、备注不会被当成代码
  function h(tag, attrs) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [key, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') el.className = value;
        else if (key === 'style' && typeof value === 'object') {
          for (const [k, v] of Object.entries(value)) {
            if (k.startsWith('--')) el.style.setProperty(k, v); else el.style[k] = v;  // CSS 变量要用 setProperty
          }
        }
        else if (key === 'dataset') Object.assign(el.dataset, value);
        else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
        else if (key === 'tip') el._tip = value;
        else el.setAttribute(key, value === true ? '' : value);
      }
    }
    for (let i = 2; i < arguments.length; i++) append(el, arguments[i]);
    if (el._tip && !el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
    return el;
  }

  function append(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach((c) => append(el, c)); return; }
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }

  // ---------- 颜色和分类定义 ----------
  const VERDICTS = [
    { key: '免费类', color: 'var(--free)', ink: '#fff', desc: '能免费留链接' },
    { key: '付费类', color: 'var(--paid)', ink: '#fff', desc: '要付钱才能上' },
    { key: '不可用', color: 'var(--no)', ink: 'var(--ink-1)', desc: '留不下链接' },
  ];
  const VERDICT_COLOR = Object.fromEntries(VERDICTS.map((v) => [v.key, v.color]));

  // 台账状态：顺序 = 报告里的展示顺序
  const STATUSES = [
    { key: '已收录', color: 'var(--st-good)', ink: '#fff', desc: '对方已经放上链接' },
    { key: '已提交', color: 'var(--st-info)', ink: '#fff', desc: '交上去了，在等审核' },
    { key: '待提交', color: 'var(--st-warn)', ink: '#0b0b0b', desc: '还没交' },
    { key: '待登录', color: 'var(--st-warn)', ink: '#0b0b0b', desc: '卡在登录，要人配合' },
    { key: '被拒', color: 'var(--st-bad)', ink: '#fff', desc: '对方拒了' },
    { key: '未收录', color: 'var(--st-bad)', ink: '#fff', desc: '查满 7 次还没收录' },
    { key: '跳过', color: 'var(--st-skip)', ink: 'var(--ink-1)', desc: '决定不发' },
  ];
  const STATUS_COLOR = Object.fromEntries(STATUSES.map((s) => [s.key, s.color]));

  // 结论来源：越往后越靠谱
  const SOURCES = [
    { key: '自动预判', color: 'var(--ord-1)', desc: '脚本看页面自动判的，没人看过' },
    { key: '人工复核', color: 'var(--ord-2)', desc: '在浏览器里人看过' },
    { key: '提交实测', color: 'var(--ord-3)', desc: '真的去提交过' },
  ];

  const GROUPS = ['直接提交', '注册账号提交'];
  const SITE_TYPES = ['导航与产品发布类', '社区论坛类', '自建类', '要挂回链或徽章'];
  const UNSET = '还没分类';
  const MAX_CHECKS = 7; // 每日独立站外链回访查满 7 次还没收录就算未收录
  // 所属行业和赛道关系：清单、赛道大类、赛道关系的顺序都来自数据文件（industries、tracks），这里只放没标时的说法
  const INDUSTRY_UNSET = '行业未标';
  const industryOf = (item) => item.industry || INDUSTRY_UNSET;

  // ---------- 日期 ----------
  function parseDate(text) {
    if (!text) return null;
    const m = String(text).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
  }
  function dayKey(text) { return text ? String(text).slice(0, 10) : null; }
  function daysBetween(a, b) {
    const da = parseDate(dayKey(a)), db = parseDate(dayKey(b));
    if (!da || !db) return null;
    return Math.round((db - da) / 86400000);
  }
  function shortDate(text) { return text ? String(text).slice(5, 10) : '—'; }
  function updatedBox(day, note) {  // 板块右上角的「最新更新日期」：日期由脚本按文件改动时间给，大字只写月-日；备注是 AI 写的这次更新了什么，另起一行
    return h('div', { class: 'view-updated' },
      h('div', { class: 'label' }, '最新更新日期'),
      h('div', { class: 'day' }, shortDate(day)),
      note ? h('div', { class: 'note' }, note) : null);
  }
  function dateRange(from, to) {
    const out = [];
    const d = parseDate(from), end = parseDate(to);
    if (!d || !end) return out;
    while (d <= end) {
      out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
      d.setDate(d.getDate() + 1);
    }
    return out;
  }

  // ---------- 数字 ----------
  function pct(part, whole) {
    if (!whole) return '—';
    const v = (part / whole) * 100;
    return `${v >= 10 || v === 0 ? Math.round(v) : v.toFixed(1)}%`;
  }
  function countBy(list, fn) {
    const out = new Map();
    for (const item of list) {
      const k = fn(item);
      out.set(k, (out.get(k) || 0) + 1);
    }
    return out;
  }

  // ---------- 提示浮层：元素上挂 _tip 函数，返回 {title, rows:[{color, kind, name, value}], sub} ----------
  const Tip = {
    el: null,
    init() {
      this.el = document.getElementById('tooltip');
      const show = (target, x, y) => {
        let cur = target;
        while (cur && cur !== document && !cur._tip) cur = cur.parentNode;  // 往上找挂了提示的元素
        if (!cur || cur === document || !cur._tip) { this.hide(); return; }
        this.render(cur._tip());
        this.place(x, y);
      };
      document.addEventListener('pointermove', (e) => show(e.target, e.clientX, e.clientY));
      document.addEventListener('pointerleave', () => this.hide());
      document.addEventListener('focusin', (e) => {
        if (!e.target._tip) return;
        const r = e.target.getBoundingClientRect();
        show(e.target, r.left + r.width / 2, r.top);
      });
      document.addEventListener('focusout', () => this.hide());
      window.addEventListener('scroll', () => this.hide(), { passive: true });
    },
    render(info) {
      const el = this.el;
      el.textContent = '';
      if (!info) { this.hide(); return; }
      if (info.title) el.appendChild(h('div', { class: 'tt-title' }, info.title));
      for (const row of info.rows || []) {
        el.appendChild(h('div', { class: 'tt-row' },
          row.color ? h('span', { class: row.kind === 'line' ? 'tt-key' : 'tt-swatch', style: { background: row.color } }) : null,
          h('span', { class: 'tt-value' }, row.value),
          row.name ? h('span', { class: 'tt-name' }, row.name) : null));
      }
      if (info.sub) el.appendChild(h('div', { class: 'tt-sub' }, info.sub));
      el.hidden = false;
    },
    place(x, y) {
      const el = this.el;
      const w = el.offsetWidth, hgt = el.offsetHeight;
      let left = x + 14, top = y + 14;
      if (left + w > window.innerWidth - 8) left = x - w - 14;
      if (top + hgt > window.innerHeight - 8) top = y - hgt - 14;
      el.style.left = `${Math.max(8, left)}px`;
      el.style.top = `${Math.max(8, top)}px`;
    },
    hide() { if (this.el) this.el.hidden = true; },
  };

  // ---------- 版块 ----------
  function sectionTitle(title, desc) {
    return h('div', { class: 'section-title' }, h('h2', null, title), desc ? h('p', null, desc) : null);
  }
  function card(title, desc, ...body) {
    return h('div', { class: 'card' },
      title ? h('div', { class: 'card-head' }, h('h3', null, title), desc ? h('p', null, desc) : null) : null,
      body);
  }
  function note(...parts) { return h('div', { class: 'card-note' }, parts); }
  function kpi(label, value, sub, opts) {
    const o = opts || {};
    return h('div', { class: `kpi${o.hero ? ' hero' : ''}`, tip: o.tip },
      h('div', { class: 'kpi-label' }, o.color ? h('span', { class: 'swatch', style: { background: o.color } }) : null, label),
      h('div', { class: 'kpi-value' }, value, o.unit ? h('small', null, o.unit) : null),
      sub ? h('div', { class: 'kpi-sub' }, sub) : null);
  }
  function badge(text, color, muted) {
    return h('span', { class: `badge${muted ? ' muted' : ''}` }, color ? h('span', { class: 'dot', style: { background: color } }) : null, text);
  }
  function statusBadge(status) { return badge(status || '—', STATUS_COLOR[status]); }
  function verdictBadge(verdict) { return badge(verdict || '—', VERDICT_COLOR[verdict]); }
  function relBadge(rel) {
    if (rel === 'dofollow') return badge('dofollow', 'var(--st-good)');
    if (rel === 'nofollow') return badge('nofollow', 'var(--st-skip)');
    return badge('没记录', null, true);
  }
  function empty(text) { return h('div', { class: 'empty' }, text); }
  function link(url, text) {
    if (!url) return h('span', { class: 'dim' }, '—');
    return h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, text || url);
  }
  function pathOf(url) {
    try { const u = new URL(url); return u.pathname === '/' ? '首页' : u.pathname; } catch (e) { return url; }
  }

  window.R = {
    h, VERDICTS, VERDICT_COLOR, STATUSES, STATUS_COLOR, SOURCES, GROUPS, SITE_TYPES, UNSET, MAX_CHECKS,
    INDUSTRY_UNSET, industryOf,
    parseDate, dayKey, daysBetween, shortDate, updatedBox, dateRange, pct, countBy, Tip,
    sectionTitle, card, note, kpi, badge, statusBadge, verdictBadge, relBadge, empty, link, pathOf,
  };
})();
