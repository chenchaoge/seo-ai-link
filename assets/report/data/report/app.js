/* 入口：两部分报告切换（网址 # 后面记住看的是哪部分、哪个独立站，刷新不丢），深浅色切换
   没有独立站数据（SKILL 自带的网页）时只有外链库这一部分 */
(function () {
  'use strict';
  const R = window.R;
  const { h } = R;
  const data = window.REPORT_DATA;
  const hasSites = Boolean(data && data.independent_sites && data.independent_sites.length);

  const views = { library: document.getElementById('view-library'), sites: document.getElementById('view-sites') };
  const tabs = [...document.querySelectorAll('.view-switch button')];
  const rendered = { library: false, sites: null };

  function showMissing() {
    document.querySelector('main').replaceChildren(h('div', { class: 'missing-data' },
      h('h2', null, '还没有报告数据'),
      h('p', null, '在 SKILL 目录运行 scripts/main.py：用户目录里的报告选菜单 5，SKILL 自带的外链库网页选菜单 8，再刷新这个页面。'),
      h('p', null, h('code', null, '$env:PYTHONDONTWRITEBYTECODE="1"; "5" | python scripts/main.py'))));
  }

  // #library 或 #site/<独立站>；没有独立站数据时只有 #library
  function parseHash() {
    const raw = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
    if (hasSites && raw.startsWith('site')) return { view: 'sites', site: raw.split('/')[1] || null };
    return { view: 'library', site: null };
  }

  function go(view, site) {
    const hash = view === 'sites' ? `#site/${site || ''}` : '#library';
    if (location.hash !== hash) history.replaceState(null, '', hash);
    route();
  }

  function route() {
    const { view, site } = parseHash();
    tabs.forEach((t) => t.setAttribute('aria-selected', String(t.dataset.view === view)));
    Object.entries(views).forEach(([k, el]) => { el.hidden = k !== view; });
    if (view === 'library' && !rendered.library) {
      window.renderLibrary(views.library, data);
      rendered.library = true;
    }
    if (view === 'sites') {
      const want = site || (rendered.sites || (data.independent_sites[0] || {}).site);
      if (rendered.sites !== want) {
        rendered.sites = window.renderSites(views.sites, data, want, (next) => { go('sites', next); window.scrollTo({ top: 0, behavior: 'smooth' }); });
      }
      if (rendered.sites && site !== rendered.sites) history.replaceState(null, '', `#site/${rendered.sites}`);  // 网址里补上实际显示的独立站
    }
    redrawCharts();
  }

  // 折线图按容器宽度画，切换视图、改窗口大小后重画
  function redrawCharts() {
    requestAnimationFrame(() => document.querySelectorAll('.linechart').forEach((el) => {
      if (el.offsetParent && el._redraw) el._redraw();
    }));
  }

  function init() {
    if (!data) { showMissing(); return; }
    R.Tip.init();
    const libCount = data.library.length;
    const sitesText = hasSites ? `${data.independent_sites.length} 个独立站` : '还没有独立站';
    document.getElementById('generated-at').textContent = data.user_report
      ? `数据生成于 ${data.generated_at} · 外链库 ${libCount} 个外链网站 · ${sitesText}`
      : `数据生成于 ${data.generated_at} · SKILL 默认外链库 ${libCount} 个外链网站`;
    let footer = '这是 SKILL 自带的网页，只有 SKILL 默认外链库；域名权重来自 DataForSEO。设置好用户目录后跑 scripts/main.py 菜单 5，用户目录第一层会生成「外链报告.html」，带用户外链库和各独立站发外链情况。';
    if (data.user_report) {
      const live = location.protocol.startsWith('http');  // 菜单 10 的本机网页：数据每次打开现算
      footer = '数据来源：SKILL 默认外链库 + 用户外链库、各独立站的提交台账、分析结果目录（外链网站从哪个竞品挖出来）；域名权重来自 DataForSEO。报告里不放密码，邮箱只留前两位。'
        + (live ? '这是本机网页，刷新就是最新数据。' : '数据更新后跑 scripts/main.py 菜单 5 重新生成。')
        + (hasSites ? '' : `现在还没有独立站：建好独立站、开始发外链后${live ? '刷新' : '重新生成'}，会多出「各独立站发外链情况」。`);
    }
    document.getElementById('footer').textContent = footer;
    if (!hasSites) document.querySelector('.view-switch').hidden = true;  // 只有一部分，不用切换
    tabs.forEach((t) => t.addEventListener('click', () => go(t.dataset.view, t.dataset.view === 'sites' ? rendered.sites : null)));
    document.getElementById('theme-toggle').addEventListener('click', () => {
      const root = document.documentElement;
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      redrawCharts();
    });
    window.addEventListener('hashchange', route);
    let timer = null;
    window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(redrawCharts, 150); });
    route();
  }

  init();
})();
