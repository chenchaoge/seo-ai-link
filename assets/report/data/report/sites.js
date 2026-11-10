/* 第二部分：每个独立站的外链发布情况（所有独立站同一个模板）。
   回答「外链库里的免费类各赛道还能发多少、拿到了多少外链、哪些在等审核、哪些要人动手、跳过了哪些、外链库里还有多少没发」 */
(function () {
  'use strict';
  const R = window.R, C = window.Charts;
  const { h } = R;

  const SUBMITTED_STATUSES = ['已提交', '已收录', '被拒', '未收录'];
  const ACTION_STATUSES = ['待提交', '待登录'];
  const SKIP_REASONS = [
    { key: '外链网站本身用不了', desc: '外链网站坏了、没有自助入口、留不下链接' },
    { key: '只有付费档', desc: '没有免费收录' },
    { key: '要先挂回链或徽章', desc: '刚上线的独立站暂时不做挂回链的' },
    { key: '其他原因', desc: '不符合收录条件、价值低等，看备注' },
  ];
  const HOME = '首页';
  const WARN_CHECKS = 5;  // 回访到第 5 次就快要判未收录了，进度条变黄

  const isSubmitted = (e) => Boolean(e.submitted_at) || SUBMITTED_STATUSES.includes(e.status);
  const submittedToday = (entries, today) => entries.filter((e) => R.dayKey(e.submitted_at) === today).length;  // 跟程序一样：submitted_at 是当天的才算
  const includedDay = (e) => R.dayKey(e.included_at || e.submitted_at);  // 自建类没有回访记录，按发布当天算
  const lastCheck = (e) => (e.checks.length ? e.checks[e.checks.length - 1] : null);
  const clipText = (text, n) => (text ? (text.length > n ? `${text.slice(0, n)}…` : text) : null);
  const daysText = (d) => (d === 0 ? '当天' : `${d} 天`);

  function skipReason(e, libMap) {
    const verdict = (libMap.get(e.site) || {}).verdict || e.verdict;
    if (verdict === '不可用') return SKIP_REASONS[0].key;
    if (verdict === '付费类') return SKIP_REASONS[1].key;
    if (e.site_type === '要挂回链或徽章') return SKIP_REASONS[2].key;
    return SKIP_REASONS[3].key;
  }

  function targetLabel(url, site) {
    if (!url) return HOME;
    const inner = (site.inner_pages || []).find((p) => p.url === url);
    return inner ? `内页：${R.pathOf(url)}` : R.pathOf(url);
  }

  function logoOf(site, cls) {
    if (site.logo) {
      const img = h('img', { src: site.logo, alt: '', class: cls || null });
      img.addEventListener('error', () => img.replaceWith(h('div', { class: 'site-logo-fallback' }, site.name.slice(0, 1))));
      return img;
    }
    return h('div', { class: 'site-logo-fallback' }, site.name.slice(0, 1));
  }

  function header(site) {
    return h('div', { class: 'view-head' }, h('div', null,
      h('div', { class: 'eyebrow' }, '第二部分 · 各独立站发外链情况'),
      h('h1', { class: 'view-title' }, '每个独立站的外链做到哪一步了'),
      h('p', { class: 'view-desc' }, '每个独立站用同一套报告：拿到了多少外链、哪些在等外链网站审核、哪些要人动手、跳过了哪些、外链库里还有哪些没发。点下面的独立站卡片切换。')),
      site ? R.updatedBox(site.ledger_updated_at, site.update_note) : null);  // 日期 = ledger.json 文件的改动时间，备注 = AI 写的这次更新了什么
  }

  function siteTabs(sites, current, onSwitch) {
    return h('div', { class: 'site-tabs', role: 'tablist', 'aria-label': '选择独立站' }, sites.map((s) => {
      const included = s.entries.filter((e) => e.status === '已收录').length;
      return h('button', {
        type: 'button', role: 'tab', class: 'site-tab', 'aria-selected': String(s.site === current.site),
        onclick: () => onSwitch(s.site),
      }, logoOf(s), h('div', null, h('div', { class: 'name' }, s.name), h('div', { class: 'meta' }, `${s.site} · 台账 ${s.entries.length} 个 · 已收录 ${included} 个`)));
    }));
  }

  function siteHero(site, today, industries) {
    const day = site.launch_date ? R.daysBetween(site.launch_date, today) + 1 : null;
    const group = (industries.find((x) => x.name === site.industry) || {}).group;
    return h('div', { class: 'card site-hero' }, logoOf(site),
      h('div', null,
        h('h2', null, site.name),
        h('div', { class: 'links' },
          R.link(site.url, site.url),
          h('span', null, site.industry ? `所属行业：${site.industry}（赛道大类：${group}）` : '所属行业：还没标（profile.json 的 industry），赛道关系算不出来'),
          site.launch_date ? h('span', null, `${site.launch_date} 上线 · 今天是第 ${day} 天`) : null,
          (site.inner_pages || []).map((p) => h('span', null, '单独推的内页：', R.link(p.url, p.name || p.url))))));
  }

  function kpis(site, entries, today, limit) {
    const by = R.countBy(entries, (e) => e.status);
    const todayN = submittedToday(entries, today);
    const included = entries.filter((e) => e.status === '已收录');
    const rel = R.countBy(included, (e) => e.rel || '没记录');
    const pending = entries.filter((e) => e.status === '已提交');
    const toCheck = pending.filter((e) => R.dayKey(e.submitted_at) < today && R.dayKey(e.checked_at) !== today).length;
    const submitted = entries.filter(isSubmitted).length;
    const actions = entries.filter((e) => ACTION_STATUSES.includes(e.status));
    return h('div', { class: 'kpis' },
      R.kpi('已拿到的外链', String(included.length), `dofollow ${rel.get('dofollow') || 0} · nofollow ${rel.get('nofollow') || 0} · 没记录 ${rel.get('没记录') || 0}`, { hero: true, unit: '个' }),
      R.kpi('等对方审核', String(pending.length), toCheck ? `今天还有 ${toCheck} 个没回访` : '今天的回访都做完了', { color: 'var(--st-info)' }),
      R.kpi('收录率', R.pct(included.length, submitted), `提交过 ${submitted} 个，收录 ${included.length} 个`, { color: 'var(--st-good)' }),
      R.kpi('要人动手', String(actions.length), `${R.shortDate(today)} 已提交 ${todayN} 个，每天最多 ${limit} 个`, { color: 'var(--st-warn)' }),
      R.kpi('跳过', String(by.get('跳过') || 0), `台账一共 ${entries.length} 个外链网站`, { color: 'var(--st-skip)' }));
  }

  // ---------- 免费类外链网站：这个独立站申请了多少、还剩多少，按赛道关系分（状态取外链库 used_by，跟台账一致） ----------
  const TRACK_HINT = {
    同赛道: '行业直接相关', 相近赛道: '行业间接相关', 不分行业: '综合类，不挑行业', 其他赛道: '行业不相干', 行业未标: '外链网站还没标行业',
  };
  const FRESH_FILL = 'repeating-linear-gradient(135deg, var(--free) 0 3px, var(--accent-wash) 3px 6px)';  // 还没进台账：斜纹蓝，跟等审核的实心蓝分开
  const COVER_PARTS = [
    { key: '已收录', kind: 'applied', color: 'var(--st-good)', desc: '申请过，对方已经放上链接', test: (st) => st === '已收录' },
    { key: '等审核', kind: 'applied', color: 'var(--st-info)', desc: '申请过，在等对方审核（台账状态已提交）', test: (st) => st === '已提交' },
    { key: '被拒或未收录', kind: 'applied', color: 'var(--st-bad)', desc: '申请过，对方拒了，或回访查满还没收录', test: (st) => st === '被拒' || st === '未收录' },
    { key: '跳过', kind: 'skip', color: 'var(--st-skip)', desc: '决定不发', test: (st) => st === '跳过' },
    { key: '台账里待做', kind: 'left', color: 'var(--st-warn)', desc: '进了台账还没交（待提交、待登录）', test: (st) => st === '待提交' || st === '待登录' },
    { key: '还没进台账', kind: 'left', color: FRESH_FILL, desc: '外链库里有，还没给这个独立站安排', test: (st) => !st },
  ];

  function coverStats(list, site) {
    const part = (key) => COVER_PARTS.find((p) => p.key === key);
    const counts = Object.fromEntries(COVER_PARTS.map((p) => [p.key, list.filter((s) => p.test(s.used_by[site.site])).length]));
    const sumKind = (kind) => COVER_PARTS.filter((p) => p.kind === kind).reduce((a, p) => a + counts[p.key], 0);
    const left = list.filter((s) => part('台账里待做').test(s.used_by[site.site]) || part('还没进台账').test(s.used_by[site.site]));
    return {
      n: list.length, counts, applied: sumKind('applied'), skipped: sumKind('skip'), left: sumKind('left'),
      backlink: left.filter((s) => s.site_type === '要挂回链或徽章').length,
    };
  }

  // 小方块：标题、大数字、一条分段条、每段一行（色块 + 名称 + 数量），底部一句说明
  const TRACK_COLOR = { 同赛道: 'var(--seq-6)', 相近赛道: 'var(--seq-4)', 不分行业: 'var(--seq-3)', 其他赛道: 'var(--seq-2)' };  // 越相关颜色越深
  function statTile(title, value, parts, foot) {
    return h('div', { class: 'kpi stat-tile' },
      h('div', { class: 'stat-tile-head' }, title),
      h('div', { class: 'kpi-value' }, String(value), h('small', null, '个')),
      C.segBar(parts, { thin: true, legend: false, title }),
      h('div', { class: 'stat-rows' }, parts.map((p) => h('div', { class: `stat-row${p.value ? '' : ' zero'}` },
        h('span', { class: 'legend-swatch', style: { background: p.color } }), h('span', null, p.name), h('span', { class: 'n' }, String(p.value))))),
      h('div', { class: 'stat-foot' }, foot));
  }

  // 每种赛道关系是什么、包括哪些行业（行业后面的数 = 外链库里这个行业的免费类个数）
  function trackGuide(rows, free, trackOf, site, industries) {
    const group = (industries.find((x) => x.name === site.industry) || {}).group;
    const members = (g, exclude) => industries.filter((x) => x.group === g && x.name !== exclude).map((x) => x.name);
    const defs = {
      同赛道: `外链网站的所属行业跟这个独立站一样（${site.industry || '独立站还没标行业'}）。`,
      相近赛道: group ? `行业不同，但跟这个独立站同属「${group}」这个赛道大类。` : '行业不同，但同属一个赛道大类。',
      不分行业: '综合导航站、综合论坛博客，不限行业，哪个独立站都能发。',
      其他赛道: '除了上面三种，剩下的行业都算其他赛道，跟这个独立站不相干；发之前要先问用户。',
      行业未标: '外链网站还没标所属行业，赛道关系算不出来。',
    };
    const always = { 相近赛道: group ? members(group, site.industry) : [], 不分行业: members('不分行业') };  // 这两种把该有的行业都列出来，外链库里没有的记 0
    return h('div', { class: 'track-guide' },
      h('div', { class: 'track-guide-title' }, `${rows.length} 种赛道关系分别是什么`, h('span', null, '行业后面的数 = 外链库里这个行业的免费类外链网站个数')),
      h('div', { class: 'track-guide-grid' }, rows.map((r) => {
        const counts = R.countBy(free.filter((s) => trackOf(s) === r.track), R.industryOf);
        (always[r.track] || []).forEach((name) => { if (!counts.has(name)) counts.set(name, 0); });
        const list = [...counts.entries()].sort((a, b) => b[1] - a[1]);
        return h('div', { class: 'track-guide-item' },
          h('div', { class: 'track-left-name' }, r.track, h('span', null, TRACK_HINT[r.track] || '')),
          h('p', null, defs[r.track] || ''),
          h('div', { class: 'track-guide-tags' }, list.map(([name, n]) => h('span', { class: `track-tag${n ? '' : ' zero'}` }, name, h('b', null, `${n} 个`)))));
      })));
  }

  function freeCoverageSection(site, lib, tracks, industries) {
    const free = lib.filter((s) => s.verdict === '免费类');
    const trackOf = (s) => (s.tracks || {})[site.site] || R.INDUSTRY_UNSET;
    const all = coverStats(free, site);
    const rows = tracks.map((t) => ({ track: t, ...coverStats(free.filter((s) => trackOf(s) === t), site) })).filter((r) => r.n);
    const progress = (x) => R.pct(x.applied, x.n - x.skipped);  // 申请进度 = 申请过 ÷（一共 − 跳过）

    const tiles = h('div', { class: 'kpis kpis-4' },
      h('div', { class: 'kpi hero track-left' },  // 还能申请：按赛道关系拆成几个中总结，不放总数
        h('h3', { class: 'track-left-title' }, '现有外链库还能发：'),
        h('div', { class: 'track-left-grid' }, rows.map((r) => h('div', { class: 'track-left-item' },
          h('div', { class: 'track-left-name' }, r.track, h('span', null, TRACK_HINT[r.track] || '')),
          h('div', { class: 'track-left-value' }, String(r.left), h('small', null, '个')),
          h('div', { class: 'track-left-sub' }, `台账里待做 ${r.counts['台账里待做']} · 还没进台账 ${r.counts['还没进台账']}`))))),
      statTile('申请过', all.applied, COVER_PARTS.filter((p) => p.kind === 'applied').map((p) => ({ name: p.key, value: all.counts[p.key], color: p.color })),
        `收录率 ${R.pct(all.counts['已收录'], all.applied)}（已收录 ÷ 申请过）`),
      statTile('跳过', all.skipped, rows.map((r) => ({ name: r.track, value: r.skipped, color: TRACK_COLOR[r.track] || 'var(--no)' })),
        '决定不发的；原因看下面「跳过了哪些、为什么」'),
      statTile('免费类一共', all.n, rows.map((r) => ({ name: r.track, value: r.n, color: TRACK_COLOR[r.track] || 'var(--no)' })),
        `申请进度 ${progress(all)}（申请过 ÷ 不算跳过的）`));

    const bars = C.hbars(rows.map((r) => ({
      label: `${r.track} · ${TRACK_HINT[r.track] || ''}`,
      segs: COVER_PARTS.map((p) => ({ name: p.key, value: r.counts[p.key], color: p.color })),
      value: `还剩 ${r.left}`,
      sub: `申请过 ${r.applied}`,
      tipSub: `一共 ${r.n} 个：申请过 ${r.applied}、跳过 ${r.skipped}、还能申请 ${r.left}（台账里待做 ${r.counts['台账里待做']}、还没进台账 ${r.counts['还没进台账']}）`,
    })), { labelW: '196px', valueW: '140px', tipValue: (x) => `${x.value} 个` });

    const num = (v) => h('td', { class: 'num' }, String(v));
    const tableRow = (label, hint, x, cls) => h('tr', { class: cls || null },
      h('td', { class: 'site' }, label), h('td', { class: 'nowrap dim' }, hint),
      num(x.n), num(x.applied), num(x.counts['已收录']), num(x.skipped),
      h('td', { class: 'num strong' }, String(x.left)), num(x.counts['台账里待做']), num(x.counts['还没进台账']),
      num(progress(x)));
    const heads = ['赛道关系', '跟独立站的关系', '一共', '申请过', '其中已收录', '跳过', '还能申请', '其中台账里待做', '其中还没进台账', '申请进度'];
    const table = h('div', { class: 'table-wrap', style: { marginTop: '18px' } },
      h('table', { class: 'data' },
        h('thead', null, h('tr', null, heads.map((x, i) => h('th', { class: i > 1 ? 'num' : null }, x)))),
        h('tbody', null, rows.map((r) => tableRow(r.track, TRACK_HINT[r.track] || '', r)), tableRow('合计', '', all, 'total'))));

    return h('div', { class: 'ccg-cover' },
      R.sectionTitle('免费类外链网站：申请了多少、还剩多少', `外链库里现在判成免费类的 ${all.n} 个外链网站，按跟这个独立站的赛道关系分开看（这个独立站的所属行业：${site.industry || '还没标'}）`),
      tiles,
      h('div', { style: { marginTop: '18px' } }, R.card('按赛道关系看：申请了多少、还剩多少', '条越长 = 这类外链网站越多；鼠标停在条上看每段的数量',
        bars,
        C.legend(COVER_PARTS.map((p) => ({ name: p.key, color: p.color }))),
        trackGuide(rows, free, trackOf, site, industries),
        table,
        R.note(h('b', null, '怎么算的：'), '只算外链库现在判成免费类的。申请过 = 台账状态是已提交、已收录、被拒、未收录；还能申请 = 台账里待提交、待登录的，加上还没进这个独立站台账的；跳过的不算还能申请。',
          all.backlink ? `还能申请的 ${all.left} 个里，有 ${all.backlink} 个要挂回链或徽章，新站默认先不做。` : '',
          '其他赛道的发之前要先问用户。还没进台账的清单在下面「外链库里还没给这个独立站发过的免费类外链网站」，可以按赛道关系排序。'))));
  }

  function statusCard(entries) {
    const by = R.countBy(entries, (e) => e.status);
    return R.card('台账里每个外链网站到哪一步了', '台账 = 这个独立站要发外链的外链网站清单，一个外链网站一行',
      C.segBar(R.STATUSES.map((s) => ({ name: s.key, value: by.get(s.key) || 0, color: s.color, ink: s.ink, desc: s.desc })), { title: '台账状态' }),
      h('div', { class: 'legend', style: { marginTop: '10px' } },
        R.STATUSES.filter((s) => by.get(s.key)).map((s) => h('span', { class: 'legend-item' }, `${s.key}：${s.desc}`))),
      by.get('跳过') ? R.note(`跳过的 ${by.get('跳过')} 个为什么跳过，看下面「跳过了哪些、为什么」。`) : null);
  }

  function funnelCard(entries) {
    const submitted = entries.filter(isSubmitted).length;
    const included = entries.filter((e) => e.status === '已收录');
    const dofollow = included.filter((e) => e.rel === 'dofollow').length;
    const stages = [
      ['进了台账', entries.length, 'var(--fun-1)'],
      ['提交过', submitted, 'var(--fun-2)'],
      ['已收录', included.length, 'var(--fun-3)'],
      ['其中 dofollow', dofollow, 'var(--fun-4)'],
    ];
    const rows = stages.map(([label, n, color], i) => ({
      label,
      segs: [{ name: label, value: n, color }],
      value: String(n),
      sub: i ? `占上一步 ${R.pct(n, stages[i - 1][1])}` : null,
    }));
    return R.card('从进台账到拿到 dofollow 外链', '每一步还剩多少个；dofollow 的链接才会给独立站传权重',
      C.hbars(rows, { labelW: '96px', valueW: '130px', max: entries.length || 1 }),
      R.note('「没记录」的是收录时没查是 dofollow 还是 nofollow，或者是自建类（GitHub、Hugging Face 这种自己的主页）。'));
  }

  function trendCard(entries, today) {
    const days = entries.flatMap((e) => [R.dayKey(e.added_at), R.dayKey(e.submitted_at)]).filter(Boolean).sort();
    if (!days.length) return R.card('提交和收录随时间累计', null, R.empty('还没有提交记录'));
    const dates = R.dateRange(days[0], today);
    const sub = entries.filter(isSubmitted).map((e) => R.dayKey(e.submitted_at)).filter(Boolean);
    const inc = entries.filter((e) => e.status === '已收录').map(includedDay).filter(Boolean);
    const cumulative = (list) => dates.map((d) => list.filter((x) => x <= d).length);
    const series = [
      { name: '提交过', color: 'var(--st-info)', values: cumulative(sub) },
      { name: '已收录', color: 'var(--st-good)', values: cumulative(inc) },
    ];
    return R.card('提交和收录随时间累计', '收录日期 = 每日独立站外链回访第一次看到收录的那天；自建类没有回访，按发布当天算',
      C.lineChart({
        dates, series, label: '提交和收录累计数量',
        tipSub: (i) => {
          const d = dates[i];
          const s = sub.filter((x) => x === d).length, n = inc.filter((x) => x === d).length;
          return s || n ? `当天新提交 ${s} 个、新发现收录 ${n} 个` : '当天没有变化';
        },
      }),
      C.legend(series.map((x) => ({ name: x.name, color: x.color, kind: 'line' }))));
  }

  function includedSection(site, entries) {
    const rows = entries.filter((e) => e.status === '已收录');
    const tbl = R.table({
      rows,
      sort: { key: 'inc', dir: 'desc' },
      emptyText: '还没有收录的外链',
      columns: [
        { key: 'site', label: '外链网站', cls: 'site', sort: (e) => e.site, firstDir: 'asc' },
        { key: 'listing', label: '收录页（外链网站上链到独立站的那一页）', cls: 'clip', render: (e) => R.link(e.listing_url, e.listing_url ? e.listing_url.replace(/^https?:\/\/(www\.)?/, '') : null) },
        { key: 'rel', label: '链接属性', cls: 'nowrap', sort: (e) => e.rel || '', render: (e) => R.relBadge(e.rel) },
        { key: 'target', label: '链到独立站哪一页', cls: 'nowrap', render: (e) => targetLabel(e.target_url, site) },
        { key: 'type', label: '业务类型', cls: 'nowrap', render: (e) => e.site_type },
        { key: 'sub', label: '提交', cls: 'num', sort: (e) => e.submitted_at, render: (e) => R.shortDate(e.submitted_at) },
        { key: 'inc', label: '发现收录', cls: 'num', sort: (e) => includedDay(e), render: (e) => R.shortDate(includedDay(e)) },
        { key: 'days', label: '用了几天', cls: 'num', sort: (e) => (e.included_at ? R.daysBetween(e.submitted_at, e.included_at) : null), render: (e) => (e.included_at ? daysText(R.daysBetween(e.submitted_at, e.included_at)) : '发布即上线') },
      ],
    });
    const withDays = rows.filter((e) => e.included_at && e.submitted_at).map((e) => R.daysBetween(e.submitted_at, e.included_at));
    const avg = withDays.length ? (withDays.reduce((a, b) => a + b, 0) / withDays.length).toFixed(1) : null;
    return h('div', null,
      R.sectionTitle('已拿到的外链', avg ? `从提交到回访发现收录，平均 ${avg} 天（回访每天一次，实际收录可能更早）` : '对方已经放上链接的外链网站'),
      h('div', { class: 'card' }, tbl.el));
  }

  function pendingCard(entries, today) {
    const rows = entries.filter((e) => e.status === '已提交');
    const tbl = R.table({
      rows,
      sort: { key: 'checks', dir: 'desc' },
      emptyText: '没有在等审核的外链网站',
      maxHeight: '460px',
      columns: [
        { key: 'site', label: '外链网站', cls: 'site', sort: (e) => e.site, firstDir: 'asc' },
        { key: 'wait', label: '等了几天', cls: 'num', sort: (e) => R.daysBetween(e.submitted_at, today), render: (e) => daysText(R.daysBetween(e.submitted_at, today)) },
        { key: 'checks', label: '回访进度', sort: (e) => e.checks.length, render: (e) => C.meter(e.checks.length, R.MAX_CHECKS, WARN_CHECKS) },
        { key: 'today', label: '今天', cls: 'nowrap', sort: (e) => (R.dayKey(e.checked_at) === today ? 1 : 0), render: (e) => (R.dayKey(e.submitted_at) >= today ? R.badge('今天刚交', null, true) : R.dayKey(e.checked_at) === today ? R.badge('已回访', 'var(--st-good)') : R.badge('待回访', 'var(--st-warn)')) },
      ],
      detail: (e) => checksDetail(e),
    });
    return R.card('等对方审核的外链网站', `每天回访一次，查满 ${R.MAX_CHECKS} 次还没收录就改成未收录；点一行看每次回访看到了什么`, tbl.el);
  }

  function checksDetail(e) {
    const last = lastCheck(e);
    return R.detailGrid([
      ['提交方式', e.method],
      ['提交入口', e.submit_url ? R.link(e.submit_url) : null],
      ['提交时间', e.submitted_at],
      ['最近一次', last ? `${last.at} ${last.result}` : '还没回访过'],
      ['回访记录', e.checks.length ? h('ul', { class: 'timeline' }, e.checks.map((c) => h('li', null,
        h('span', { class: 't' }, c.at), R.badge(c.result, c.result === '已收录' ? 'var(--st-good)' : c.result === '被拒' ? 'var(--st-bad)' : 'var(--st-skip)'),
        h('span', { class: 'e' }, c.evidence || '')))) : null],
      ['备注', e.note],
    ]);
  }

  function actionCard(entries) {
    const rows = entries.filter((e) => ACTION_STATUSES.includes(e.status));
    const tbl = R.table({
      rows,
      sort: { key: 'order', dir: 'asc' },
      emptyText: '没有要人动手的外链网站',
      maxHeight: '460px',
      columns: [
        { key: 'site', label: '外链网站', cls: 'site', sort: (e) => e.site, firstDir: 'asc' },
        { key: 'order', label: '发外链顺序', cls: 'nowrap', sort: (e) => e.order, firstDir: 'asc', render: tierText },
        { key: 'status', label: '状态', cls: 'nowrap', render: (e) => R.statusBadge(e.status) },
        { key: 'what', label: '说明', cls: 'clip', render: (e) => clipText(e.note || e.hint || e.check, 40) },
      ],
      detail: (e) => R.detailGrid([['赛道关系', e.track], ['提交入口', e.submit_url ? R.link(e.submit_url) : null], ['提示', e.hint], ['要注意', e.check], ['备注', e.note]]),
    });
    return R.card('要人动手的外链网站', '还没交（待提交）或卡在登录（待登录）的，按发外链原则从上往下发；点一行看全文', tbl.el);
  }

  function typeCard(entries) {
    const types = [...R.SITE_TYPES, R.UNSET];
    const rows = types.map((t) => {
      const list = entries.filter((e) => (e.site_type || R.UNSET) === t);
      const submitted = list.filter(isSubmitted).length;
      const included = list.filter((e) => e.status === '已收录').length;
      return {
        label: t, n: list.length,
        segs: R.STATUSES.map((s) => ({ name: s.key, value: list.filter((e) => e.status === s.key).length, color: s.color })),
        value: `${included} / ${submitted}`,
        sub: '收录/提交',
        tipSub: `提交过 ${submitted} 个，收录 ${included} 个（${R.pct(included, submitted)}）`,
      };
    }).filter((r) => r.n).sort((a, b) => b.n - a.n);
    const present = R.STATUSES.filter((s) => entries.some((e) => e.status === s.key));
    return R.card('哪类外链网站收录得好', '按业务类型分，每类外链网站现在的状态；右边是收录数 / 提交过的数',
      C.hbars(rows, { labelW: '120px', valueW: '110px', tipValue: (x) => `${x.value} 个` }),
      C.legend(present.map((s) => ({ name: s.key, color: s.color }))));
  }

  function targetCard(site, entries) {
    const live = entries.filter((e) => e.status === '已收录' || e.status === '已提交');
    const targets = [...new Set(live.map((e) => e.target_url || null))];
    const rows = targets.map((t) => {
      const list = live.filter((e) => (e.target_url || null) === t);
      return {
        label: targetLabel(t, site),
        segs: [
          { name: '已收录', value: list.filter((e) => e.status === '已收录').length, color: 'var(--st-good)' },
          { name: '已提交', value: list.filter((e) => e.status === '已提交').length, color: 'var(--st-info)' },
        ],
        value: String(list.length),
        tipSub: t || site.url,
      };
    }).sort((a, b) => Number(b.value) - Number(a.value));
    return R.card('外链链到独立站哪一页', '已收录和等审核的外链，各自链到首页还是某个内页',
      rows.length ? C.hbars(rows, { labelW: '200px', valueW: '40px' }) : R.empty('还没有提交过的外链'),
      C.legend([{ name: '已收录', color: 'var(--st-good)' }, { name: '已提交', color: 'var(--st-info)' }]));
  }

  // ---------- 发外链原则：先发契合赛道、免费、dofollow 的（第1档），剩下的免费先于付费、dofollow 先于 nofollow、最后看赛道；档和排序值由程序算好（tier、order） ----------
  const trackIndex = (tracks, track) => { const i = tracks.indexOf(track); return i < 0 ? tracks.length : i; };
  const planOf = (s, site) => (s.plans || {})[site.site] || {};
  const tierText = (e) => (e.tier ? `${e.tier}${e.needs_confirm ? '（先问用户）' : ''}` : null);  // 台账里其他赛道、用户还没定的标出来
  const tierNote = (tiers, limit) => R.note(h('b', null, `发外链原则：先发${tiers[0].key}（${tiers[0].desc}），发完再按 ${tiers.slice(1, -1).map((t) => t.key).join(' → ')} 往下，其他赛道的先给用户看、用户定了才发，每天最多成功提交 ${limit} 个。`),
    `契合赛道 = 同赛道、相近赛道、不分行业（综合导航站、综合论坛博客）。${tiers.slice(1).map((t) => `${t.key}：${t.desc}`).join('；')}。`);

  function ledgerTierCard(entries, tiers, limit) {
    const rows = tiers.map((t) => {
      const list = entries.filter((e) => e.tier === t.key);
      const todo = list.filter((e) => ACTION_STATUSES.includes(e.status)).length;
      return {
        label: t.key, n: list.length,
        segs: R.STATUSES.map((s) => ({ name: s.key, value: list.filter((e) => e.status === s.key).length, color: s.color })),
        value: String(list.length), sub: todo ? `待做 ${todo}` : null,
        tipSub: `${t.desc}；还要做的（待提交、待登录）${todo} 个`,
      };
    }).filter((r) => r.n);
    const present = R.STATUSES.filter((s) => entries.some((e) => e.tier && e.status === s.key));
    return R.card('台账按发外链原则分档', '台账里免费类、付费类的外链网站各在第几档，各自做到哪一步',
      rows.length ? C.hbars(rows, { labelW: '72px', valueW: '96px', tipValue: (x) => `${x.value} 个` }) : R.empty('台账里没有要发的外链网站'),
      C.legend(present.map((s) => ({ name: s.key, color: s.color }))),
      tierNote(tiers, limit));
  }

  function notSentTierCard(site, lib, tiers) {
    const free = lib.filter((s) => s.verdict === '免费类' && !s.used_by[site.site]);
    const rows = tiers.map((t) => {
      const list = free.filter((s) => planOf(s, site).tier === t.key);
      const top = list.slice().sort((a, b) => planOf(a, site).order - planOf(b, site).order).slice(0, 5);
      return {
        label: t.key, n: list.length,
        segs: [{ name: '还没发的免费类外链网站', value: list.length, color: 'var(--free)' }],
        tipSub: `${t.desc}。排最前的：${top.map((s) => s.site).join('、')}`,
      };
    }).filter((r) => r.n);
    return R.card('外链库里还没发的免费类，按发外链原则分档', `一共 ${free.length} 个；鼠标停在条上看每档排最前的几个`,
      rows.length ? C.hbars(rows, { labelW: '72px', valueW: '40px' }) : R.empty('外链库里的免费类外链网站都发过了'),
      R.note('清单在下面「外链库里还没给这个独立站发过的免费类外链网站」，已经按发外链原则排好。'));
  }

  function skipSection(entries, libMap) {
    const skipped = entries.filter((e) => e.status === '跳过').map((e) => ({ ...e, reason: skipReason(e, libMap) }));
    const rows = SKIP_REASONS.map((r) => ({
      label: r.key,
      segs: [{ name: r.key, value: skipped.filter((e) => e.reason === r.key).length, color: 'var(--st-skip)' }],
      tipSub: r.desc,
    }));
    const tbl = R.table({
      rows: skipped,
      sort: { key: 'reason', dir: 'asc' },
      maxHeight: '420px',
      columns: [
        { key: 'site', label: '外链网站', cls: 'site', sort: (e) => e.site, firstDir: 'asc' },
        { key: 'reason', label: '原因', cls: 'nowrap', sort: (e) => SKIP_REASONS.findIndex((r) => r.key === e.reason), firstDir: 'asc', render: (e) => e.reason },
        { key: 'note', label: '备注', cls: 'clip', render: (e) => clipText(e.note, 80) },
      ],
      detail: (e) => R.detailGrid([['备注全文', e.note], ['提交入口', e.submit_url ? R.link(e.submit_url) : null]]),
    });
    return R.card('跳过了哪些、为什么', `一共跳过 ${skipped.length} 个；原因按外链库的现结论和业务类型归类，具体看备注`,
      skipped.length ? C.hbars(rows, { labelW: '130px', valueW: '40px' }) : R.empty('没有跳过的外链网站'),
      skipped.length ? h('details', { style: { marginTop: '16px' } }, h('summary', { style: { cursor: 'pointer', color: 'var(--ink-2)' } }, `看全部 ${skipped.length} 个跳过的外链网站`),
        h('div', { style: { marginTop: '12px' } }, tbl.el)) : null);
  }

  function notSentSection(site, lib, tracks, tiers) {
    const rows = lib.filter((s) => s.verdict === '免费类' && !s.used_by[site.site]);
    const byGroup = R.countBy(rows, (s) => s.group || R.UNSET);
    const backlink = rows.filter((s) => s.site_type === '要挂回链或徽章').length;
    const trackOf = (s) => (s.tracks || {})[site.site];
    const tbl = R.table({
      rows,
      sort: { key: 'order', dir: 'asc' },
      maxHeight: '520px',
      emptyText: '外链库里的免费类外链网站都发过了',
      columns: [
        { key: 'site', label: '外链网站', cls: 'site', sort: (s) => s.site, firstDir: 'asc' },
        { key: 'order', label: '发外链顺序', cls: 'nowrap', sort: (s) => planOf(s, site).order, firstDir: 'asc', render: (s) => planOf(s, site).tier },
        { key: 'track', label: '赛道关系', cls: 'nowrap', sort: (s) => trackIndex(tracks, trackOf(s)), firstDir: 'asc', render: (s) => trackOf(s) },
        { key: 'industry', label: '所属行业', cls: 'nowrap', sort: (s) => R.industryOf(s), firstDir: 'asc', render: (s) => s.industry },
        { key: 'rank', label: '权重', cls: 'num', sort: (s) => s.domain_rank, render: (s) => (s.domain_rank === null || s.domain_rank === undefined ? null : String(s.domain_rank)) },
        { key: 'dofollow', label: '竞品链接', cls: 'nowrap', render: (s) => (s.dofollow === true ? R.relBadge('dofollow') : s.dofollow === false ? R.relBadge('nofollow') : null) },
        { key: 'group', label: '发外链方式', cls: 'nowrap', render: (s) => s.group },
        { key: 'type', label: '业务类型', cls: 'nowrap', render: (s) => s.site_type },
        { key: 'source', label: '结论来源', cls: 'nowrap', render: (s) => s.source },
        { key: 'used', label: '别的独立站用过', render: (s) => (Object.keys(s.used_by).length ? h('div', { class: 'badges' }, Object.entries(s.used_by).map(([k, st]) => R.badge(`${k.split('.')[0]} · ${st}`, R.STATUS_COLOR[st]))) : null) },
      ],
      detail: (s) => R.detailGrid([['怎么发', s.how], ['提交入口', s.entry_url ? R.link(s.entry_url) : null], ['要注意', s.check], ['付费档', s.paid_option], ['判断依据', s.reason]]),
    });
    return h('div', null,
      R.sectionTitle('外链库里还没给这个独立站发过的免费类外链网站', `一共 ${rows.length} 个，按发外链原则排（${tiers.filter((t) => rows.some((s) => planOf(s, site).tier === t.key)).map((t) => t.key).join(' → ')}；同一档里先赛道关系、再 dofollow、再权重从高到低）；点一行看怎么发`),
      h('div', { class: 'card' },
        h('div', { class: 'legend', style: { marginTop: 0, marginBottom: '14px' } },
          [...R.GROUPS, R.UNSET].map((g) => h('span', { class: 'legend-item' }, `${g} ${byGroup.get(g) || 0} 个`)),
          h('span', { class: 'legend-item' }, `其中要挂回链或徽章 ${backlink} 个`)),
        tbl.el));
  }

  function ledgerSection(site, entries, tracks) {
    const state = { status: '全部', track: '全部', q: '' };
    const trackOptions = tracks.filter((t) => entries.some((e) => e.track === t));
    const counter = h('span', { class: 'filter-count' });
    const present = R.STATUSES.filter((s) => entries.some((e) => e.status === s.key));
    const labels = ['全部', ...present.map((s) => s.key)];
    const chipBox = h('div', { class: 'chips', role: 'group', 'aria-label': '按状态筛' });
    const chips = labels.map((label) => {
      const n = label === '全部' ? entries.length : entries.filter((e) => e.status === label).length;
      const btn = h('button', { type: 'button', class: 'chip', onclick: () => { state.status = label; refresh(); } },
        label !== '全部' ? h('span', { class: 'legend-swatch', style: { background: R.STATUS_COLOR[label] } }) : null, label, h('span', { class: 'n' }, String(n)));
      chipBox.appendChild(btn);
      return btn;
    });
    const tbl = R.table({
      rows: [],
      sort: { key: 'sub', dir: 'desc' },
      maxHeight: '720px',
      columns: [
        { key: 'site', label: '外链网站', cls: 'site', sort: (e) => e.site, firstDir: 'asc' },
        { key: 'status', label: '状态', cls: 'nowrap', sort: (e) => R.STATUSES.findIndex((s) => s.key === e.status), firstDir: 'asc', render: (e) => R.statusBadge(e.status) },
        { key: 'order', label: '发外链顺序', cls: 'nowrap', sort: (e) => e.order, firstDir: 'asc', render: tierText },
        { key: 'track', label: '赛道关系', cls: 'nowrap', sort: (e) => trackIndex(tracks, e.track), firstDir: 'asc', render: (e) => e.track },
        { key: 'industry', label: '所属行业', cls: 'nowrap', sort: (e) => R.industryOf(e), firstDir: 'asc', render: (e) => e.industry },
        { key: 'group', label: '发外链方式', cls: 'nowrap', render: (e) => e.group },
        { key: 'type', label: '业务类型', cls: 'nowrap', render: (e) => e.site_type },
        { key: 'method', label: '提交方式', cls: 'nowrap', render: (e) => e.method },
        { key: 'sub', label: '提交时间', cls: 'num', sort: (e) => e.submitted_at, render: (e) => (e.submitted_at ? String(e.submitted_at).slice(0, 16) : null) },
        { key: 'checks', label: '回访', cls: 'num', sort: (e) => e.checks.length, render: (e) => (e.checks.length ? `${e.checks.length} 次` : null) },
        { key: 'rel', label: '链接属性', cls: 'nowrap', render: (e) => (e.status === '已收录' ? R.relBadge(e.rel) : null) },
        { key: 'target', label: '链到', cls: 'nowrap', render: (e) => (isSubmitted(e) ? targetLabel(e.target_url, site) : null) },
      ],
      detail: (e) => R.detailGrid([
        ['收录页', e.listing_url ? R.link(e.listing_url) : null],
        ['提交入口', e.submit_url ? R.link(e.submit_url) : null],
        ['提示', e.hint],
        ['要注意', e.check],
        ['备注', e.note],
        ['从哪来', e.sources.join('、')],
        ['进台账', e.added_at],
        ['回访记录', e.checks.length ? h('ul', { class: 'timeline' }, e.checks.map((c) => h('li', null,
          h('span', { class: 't' }, c.at), R.badge(c.result, c.result === '已收录' ? 'var(--st-good)' : 'var(--st-skip)'), h('span', { class: 'e' }, c.evidence || '')))) : null],
      ]),
    });
    const filters = h('div', { class: 'filters' },
      h('input', { type: 'search', placeholder: '搜外链网站、行业、备注…', 'aria-label': '搜索', oninput: (e) => { state.q = e.target.value.trim().toLowerCase(); refresh(); } }),
      chipBox,
      h('select', { 'aria-label': '赛道关系', onchange: (e) => { state.track = e.target.value; refresh(); } },
        ['全部', ...trackOptions].map((t) => h('option', { value: t }, t === '全部' ? '赛道关系：全部' : t))),
      counter);
    function refresh() {
      chips.forEach((btn, i) => btn.setAttribute('aria-pressed', String(labels[i] === state.status)));
      const rows = entries.filter((e) => (state.status === '全部' || e.status === state.status)
        && (state.track === '全部' || e.track === state.track)
        && (!state.q || [e.site, e.industry, e.note, e.hint, e.method].filter(Boolean).join(' ').toLowerCase().includes(state.q)));
      counter.textContent = `显示 ${rows.length} / ${entries.length} 个 · 点一行看详情`;
      tbl.update(rows);
    }
    refresh();
    return h('div', null, R.sectionTitle('台账完整清单', '这个独立站要发外链的所有外链网站；点一行看备注和每次回访记录'), h('div', { class: 'card' }, filters, tbl.el));
  }

  function renderSites(root, data, siteKey, onSwitch) {
    const sites = data.independent_sites;
    root.textContent = '';
    const site = sites.find((s) => s.site === siteKey) || sites[0];  // 没有独立站时是 undefined，开头就不显示日期
    root.appendChild(header(site));
    if (!sites.length) { root.appendChild(R.empty('还没有任何独立站的提交台账')); return; }
    const entries = site.entries;
    const libMap = new Map(data.library.map((s) => [s.site, s]));
    root.appendChild(siteTabs(sites, site, onSwitch));
    root.appendChild(siteHero(site, data.today, data.industries));
    root.appendChild(kpis(site, entries, data.today, data.daily_limit));
    root.appendChild(freeCoverageSection(site, data.library, data.tracks, data.industries));
    root.appendChild(R.sectionTitle('进度总览', '台账里各状态的数量，以及从提交到收录的转化'));
    root.appendChild(h('div', { class: 'grid grid-2' }, statusCard(entries), funnelCard(entries)));
    root.appendChild(h('div', { style: { marginTop: '18px' } }, trendCard(entries, data.today)));
    root.appendChild(includedSection(site, entries));
    root.appendChild(R.sectionTitle('等审核和要动手的', '每日独立站外链回访看这里'));
    root.appendChild(h('div', { class: 'grid grid-7-5' }, pendingCard(entries, data.today), actionCard(entries)));
    root.appendChild(R.sectionTitle('按发外链原则看', `先发契合赛道、免费、dofollow 的；剩下的免费先于付费、dofollow 先于 nofollow，其他赛道的先给用户看；赛道关系按这个独立站的所属行业（${site.industry || '还没标行业'}）算`));
    root.appendChild(h('div', { class: 'grid grid-2' }, ledgerTierCard(entries, data.tiers, data.daily_limit), notSentTierCard(site, data.library, data.tiers)));
    root.appendChild(R.sectionTitle('收录和跳过的细分', '按业务类型看收录，外链链到哪一页，跳过的原因'));
    root.appendChild(h('div', { class: 'grid grid-2' }, typeCard(entries), targetCard(site, entries)));
    root.appendChild(h('div', { style: { marginTop: '18px' } }, skipSection(entries, libMap)));
    root.appendChild(notSentSection(site, data.library, data.tracks, data.tiers));
    root.appendChild(ledgerSection(site, entries, data.tracks));
    return site.site;
  }

  window.renderSites = renderSites;
})();
