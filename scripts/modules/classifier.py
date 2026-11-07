"""
外链可用性分类：根据页面信号给出自动预判结论和判断依据（纯函数，不联网）
分类标准与 references/criteria.md 保持一致
- 三大类：免费类 / 付费类 / 不可用；定不下属于哪一类的归「无法判断」，交给人工复核
- 不可用要有明确证据，证据不够的一律归无法判断
- 免费类按两个维度分：发外链方式 group（要不要先有账号）、业务类型 site_type（对方是什么站）；大类已定、细节还要人确认的，另记「需人工核验」
- 每个结论带「结论范围」：整站（对整个网站成立，以后直接复用）/ 页面（只在这个页面上成立，别的页面要重查）
"""

from collections import Counter
from typing import Dict, List, NamedTuple, Optional, Tuple

from modules.link_signals import CONTENT_AREA, PATTERNS, SIDEBAR_AREA, bare_host

VERDICT_FREE = '免费类'
VERDICT_PAID = '付费类'
VERDICT_NO = '不可用'
VERDICT_UNKNOWN = '无法判断'

SETTLED_VERDICTS = (VERDICT_FREE, VERDICT_PAID, VERDICT_NO)  # 三大类；人工复核结论只能写这三种
SITE_PRIORITY = [VERDICT_FREE, VERDICT_UNKNOWN, VERDICT_PAID, VERDICT_NO]  # 页面结论合并成网站结论时谁优先

# 免费类按两个维度分：发外链方式 group（拿到链接要不要先有账号）、业务类型 site_type（对方是什么站）
GROUP_DIRECT = '直接提交'      # 免登录表单、发邮件、推荐入口，不用账号
GROUP_SIGNUP = '注册账号提交'  # 要先有账号：邮箱注册、谷歌等第三方登录都算；用哪个账号看 references/accounts.md「注册登录用哪个账号」
FREE_GROUPS = [GROUP_DIRECT, GROUP_SIGNUP]

TYPE_BACKLINK = '要挂回链或徽章'     # 要先在独立站挂对方链接或徽章才收录；有这个要求就归这类，不管它本身是什么站
TYPE_DIRECTORY = '导航与产品发布类'  # 工具目录、导航站、产品发布/榜单站、awesome 清单：链接长在对方给独立站建的收录页上
TYPE_COMMUNITY = '社区论坛类'        # 论坛、社区、问答、评论区：链接长在用户发的帖子/回答/评论里，内容归对方平台管
TYPE_SELF = '自建类'                 # 自己的 GitHub / Hugging Face / 个人主页资料：内容完全自己掌控
SITE_TYPES = [TYPE_BACKLINK, TYPE_DIRECTORY, TYPE_COMMUNITY, TYPE_SELF]  # 加新类型要先问用户，用户点头才加

# 2026-10-28 以前只有一个 group 字段混着两个维度，旧值按这张表换成 (group, site_type)；None = 定不了，留给人工或第5步
LEGACY_GROUPS = {
    '邮箱注册后提交': (GROUP_SIGNUP, None),
    '第三方账号登录后提交': (GROUP_SIGNUP, None),
    '自建内容': (GROUP_SIGNUP, TYPE_SELF),
    '评论': (GROUP_DIRECT, TYPE_COMMUNITY),
    '要挂回链或徽章': (GROUP_DIRECT, TYPE_BACKLINK),
}


def normalize_group(group: Optional[str], site_type: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """旧分组值换成新的两个维度；已经是新值的原样返回；site_type 已有值时不覆盖"""
    if group in LEGACY_GROUPS:
        new_group, legacy_type = LEGACY_GROUPS[group]
        return new_group, site_type or legacy_type
    return group, site_type

# 结论范围
SCOPE_SITE = '整站'  # 网站层面的事实（提交规则、收费档、平台类型），以后碰到这个网站直接用
SCOPE_PAGE = '页面'  # 只在这个页面上看到的（评论关了、编辑文章、页面没了），别的页面要重新查

# 结论来源，按可信度从低到高
SOURCE_AUTO = '自动预判'
SOURCE_REVIEW = '人工复核'
SOURCE_TESTED = '提交实测'

# 走到"提交入口"这一步但还没看提交页时的标记，检查器看到它就去打开提交页再判一次
SUBMIT_UNCHECKED = '有提交入口，还没检查提交页'
PAY_CHECK = '提交时看清有没有付款步骤'  # 有入口、没写收费默认判免费类时，写进需人工核验


class Judgement(NamedTuple):
    """一次判断的结果"""
    verdict: str                 # 四种结论之一
    reasons: List[str]           # 判断依据
    group: Optional[str] = None  # 免费分组，只有免费类才有
    check: Optional[str] = None  # 需人工核验的内容：大类已定、细节还要人确认时才有
    scope: Optional[str] = None  # 结论范围：整站 / 页面；无法判断时为 None
    site_type: Optional[str] = None  # 业务类型，只有免费类才有；自动预判定不了的为 None，留给第2步人工或第5步定


def final_verdict_of(page: Dict) -> str:
    """最终结论：有人工复核结论用人工的，否则用自动预判；都没有算无法判断"""
    return page.get('final_verdict') or page.get('auto_verdict') or VERDICT_UNKNOWN


def final_group_of(page: Dict) -> Optional[str]:
    """最终发外链方式：人工复核过就用人工写的，否则用自动预判的；旧数据里的老分组值自动换成新的"""
    return normalize_group(page.get('final_group') if page.get('final_verdict') else page.get('auto_group'))[0]


def final_site_type_of(page: Dict) -> Optional[str]:
    """最终业务类型：人工复核过就用人工写的，否则用自动预判的；旧数据没这个字段时从老分组值推"""
    reviewed = bool(page.get('final_verdict'))
    group = page.get('final_group') if reviewed else page.get('auto_group')
    site_type = page.get('final_site_type') if reviewed else page.get('auto_site_type')
    return normalize_group(group, site_type)[1]


def final_check_of(page: Dict) -> Optional[str]:
    """最终的需人工核验内容：人工复核过就用人工写的，否则用自动预判的"""
    return page.get('final_check') if page.get('final_verdict') else page.get('auto_check')


def final_scope_of(page: Dict) -> Optional[str]:
    """最终结论范围：人工按网站复核的是整站、按页面复核的是页面；旧数据没记范围的按页面算（不往大了推）"""
    if final_verdict_of(page) == VERDICT_UNKNOWN:
        return None
    scope = page.get('final_scope') if page.get('final_verdict') else page.get('auto_scope')
    return scope or SCOPE_PAGE


def final_source_of(page: Dict) -> str:
    """最终结论的来源：人工复核过是人工复核，否则是自动预判（外链库给的结论另有标记 auto_from_library）"""
    return SOURCE_REVIEW if page.get('final_verdict') else SOURCE_AUTO


def classify_fetch_failure(fetch: Dict) -> Optional[Judgement]:
    """页面没正常打开时的结论；正常打开返回 None"""
    status = fetch.get('status')
    if fetch.get('error'):
        return Judgement(VERDICT_UNKNOWN, [f"页面打不开：{fetch['error']}"])
    if status in (404, 410):
        return Judgement(VERDICT_NO, [f'来源页面已不存在（HTTP {status}）'], scope=SCOPE_PAGE)
    if fetch.get('blocked'):
        return Judgement(VERDICT_UNKNOWN, [f'被网站防爬拦截（HTTP {status}），需要用浏览器打开看'])
    if status is not None and status >= 400:
        return Judgement(VERDICT_UNKNOWN, [f'页面返回错误（HTTP {status}）'])
    if not fetch.get('is_html'):
        return Judgement(VERDICT_UNKNOWN, ['返回的不是网页'])
    return None


def classify_page(signals: Dict, platform_types: List[str], url_from: str,
                  submit_page: Optional[Dict] = None) -> Judgement:
    """
    按顺序判断：评论区 → 论坛/维基/个人主页 → 提交入口（判出免费类就用）→ 付费 → 提交页的其他结论 → 社区登录
    → 脚本渲染 → 竞品链接位置
    能免费留就算免费类（有免费选项就不算付费），所以评论和提交入口排在付费前面
    评论只在竞品链接本身就在评论区时才算入口：竞品链接在正文（编辑写的）时，评论框不是竞品拿到链接的方式，
    评论链接一般也是 nofollow，不算入口
    不可用只在有明确证据时才判：竞品链接在正文里、页面又没有任何留网址的入口
    评论、正文、sponsored 这些只说明这个页面，结论范围记页面；提交页的规则是网站层面的，记整站

    Args:
        signals: link_signals.extract_signals 的结果
        platform_types: DataForSEO 给的外链网站类型（domain_from_platform_type）
        url_from: 来源页面网址
        submit_page: 提交页信号（analyze_submit_page 结果，打不开时为 {'error': ...}），没检查过为 None

    Returns:
        Judgement: 结论、依据、免费分组、需人工核验的内容、结论范围
    """
    link = signals.get('competitor_link') or {}
    area = link.get('area')
    platform_types = platform_types or []

    # 评论区：竞品链接本身在评论里，才说明评论能带链接
    if area == '评论区':
        if signals['comments_closed']:
            return Judgement(VERDICT_NO, ['竞品链接在评论区，但评论已关闭'], scope=SCOPE_PAGE)
        if signals['comment_login_required'] or signals['third_party_comments']:
            return Judgement(VERDICT_FREE, ['竞品链接在评论区，说明评论可以带链接，但要登录才能评论'],
                             GROUP_SIGNUP, '评论要登录：确认用什么账号登录', SCOPE_PAGE, TYPE_COMMUNITY)
        if not signals['comment_form']:
            return Judgement(VERDICT_UNKNOWN, ['竞品链接在评论区，但页面上没有评论框（可能登录后才显示，或评论是从别处搬来的）'])
        return Judgement(VERDICT_FREE, ['竞品链接就在评论区里，页面有评论框，说明评论可以带链接'], GROUP_DIRECT,
                         scope=SCOPE_PAGE, site_type=TYPE_COMMUNITY)
    if not link.get('found') and signals['third_party_comments']:  # 第三方评论在 iframe 里，程序看不到里面的链接
        system = signals['third_party_comments']
        return Judgement(VERDICT_UNKNOWN, [f'页面上找不到竞品链接，可能在第三方评论系统（{system}）里，需要登录后看'])
    # 竞品链接不在评论区时，评论框不算入口，只在最后说明一句
    comment_note = ('；页面虽有评论框能填网址，但竞品链接不是评论留的，评论链接一般也是 nofollow，不算入口'
                    if signals['comment_form'] and signals['comment_url_field'] and not signals['comments_closed']
                    else '')

    # 论坛 / 维基 / 个人主页：注册后能不能带链接要看规则，定不了大类
    if signals['forum_platform'] or 'message-boards' in platform_types or area == '论坛帖子':
        which = signals['forum_platform'] or ('论坛帖子' if area == '论坛帖子' else 'DataForSEO 标为论坛')
        return Judgement(VERDICT_UNKNOWN, [f'论坛（{which}），注册后能不能在帖子/签名/资料里带网址要看版规'])
    if signals['wiki_platform'] or 'wikis' in platform_types:
        return Judgement(VERDICT_UNKNOWN, ['维基站，注册后能不能加外链要看规则（多数维基对外链审核很严）'])
    if PATTERNS['ugc_path'].search(url_from):
        return Judgement(VERDICT_UNKNOWN, ['像是用户个人主页，要确认注册后能不能在资料里留网址'])

    # 提交入口：提交页判出免费类就用，本页的付费推广位挡不住免费提交
    submit_judgement = None
    if signals['submit_links']:
        if submit_page is None:
            return Judgement(VERDICT_UNKNOWN, [SUBMIT_UNCHECKED])
        submit_judgement = classify_submit_page(submit_page, signals['submit_links'][0], signals.get('reciprocal'))
        if submit_judgement.verdict == VERDICT_FREE:
            return submit_judgement

    # 付费：这个页面上的推广位，不代表网站别处也只能花钱
    if link.get('sponsored'):
        return Judgement(VERDICT_PAID, ['竞品链接带 rel="sponsored"，是付费推广位'], scope=SCOPE_PAGE)
    if signals['paid_strong']:
        return Judgement(VERDICT_PAID, [f"页面出现付费字样：{'、'.join(signals['paid_strong'])}"], scope=SCOPE_PAGE)
    if submit_judgement:
        return submit_judgement

    # 有注册/登录入口，且像是用户能发内容的社区
    if signals['login_entry'] and signals['ugc_text']:
        return Judgement(VERDICT_UNKNOWN, [f"有注册/登录入口，页面像社区（{'、'.join(signals['ugc_text'])}），"
                                           f"注册后能不能发带链接的内容要看规则"])

    if signals['js_rendered']:
        return Judgement(VERDICT_UNKNOWN, ['页面靠脚本加载内容，程序看不全，需要用浏览器打开看'])

    # 走到这里页面上没发现任何留网址的入口，再看竞品链接在哪，够不够当不可用的证据
    if area == CONTENT_AREA:
        return Judgement(VERDICT_NO, ['竞品链接在正文里，是编辑写的内容，页面上没有提交入口、论坛或注册入口' + comment_note],
                         scope=SCOPE_PAGE)
    if area == SIDEBAR_AREA:
        return Judgement(VERDICT_UNKNOWN, ['竞品链接在侧边栏/页脚，可能是友链、广告位或合作位，看不出能不能留' + comment_note])
    if not link.get('found'):
        return Judgement(VERDICT_UNKNOWN, ['页面上找不到竞品链接，看不出它是怎么留上去的，页面上也没发现留网址的入口'
                                           + comment_note])
    return Judgement(VERDICT_UNKNOWN, ['看不出竞品链接是不是编辑写在正文里的，页面上也没发现留网址的入口' + comment_note])


def _login_note(submit_page: Dict) -> str:
    """提交页上看到的登录方式，写进需人工核验给第5步选账号用：有密码框能用邮箱注册，只有第三方按钮就只能第三方登录"""
    oauth = submit_page.get('oauth_login') or []
    if submit_page.get('password_form'):
        return '有账号密码登录框，确认能不能用邮箱注册'
    if oauth:
        return f"只看到第三方账号登录（{'、'.join(oauth)}）"
    return '要登录，页面上看不出能用什么账号登录，确认登录方式'


def classify_submit_page(submit_page: Dict, submit_url: str, page_reciprocal: Optional[List[str]] = None) -> Judgement:
    """
    根据提交页信号判断：付费 → 有价格也有免费字样 → 有网址表单 → 发邮件 → 提 PR → 要登录 → 提到 App → 看不出
    写明收费才判付费类；有价格也有免费字样才判无法判断；其余有入口、没写收费的默认免费类，
    看不到的步骤（登录后的表单、靠脚本加载的表单）记进需人工核验；收录条件、人机验证这类只记进需人工核验
    提交页的规则是网站层面的，定下来的结论范围都是整站

    Args:
        submit_page: 提交页信号（analyze_submit_page 结果，打不开时为 {'error': ...}）
        submit_url: 提交页网址
        page_reciprocal: 来源页面上"要求挂回链"的字样，和提交页上的一起算
    """
    if submit_page.get('error'):
        return Judgement(VERDICT_UNKNOWN, [f"有提交入口 {submit_url}，但提交页打不开：{submit_page['error']}"])
    checks = list(submit_page.get('requirements') or [])
    if submit_page.get('captcha'):
        checks.append('提交页有人机验证')
    if submit_page['paid_strong']:
        return Judgement(VERDICT_PAID, [f"提交页 {submit_url} 要付费：{'、'.join(submit_page['paid_strong'])}"],
                         scope=SCOPE_SITE)
    prices = submit_page['price_hits']
    if prices and not submit_page['free_hits']:
        return Judgement(VERDICT_PAID, [f"提交页 {submit_url} 只看到价格：{'、'.join(prices)}"], scope=SCOPE_SITE)
    if prices:  # 有价格也有 free 字样：看不出有没有免费档，交给人工看
        return Judgement(VERDICT_UNKNOWN, [f"提交页 {submit_url} 有价格（{'、'.join(prices)}）也有免费字样"
                                           f"（{'、'.join(submit_page['free_hits'])}），看不出有没有免费档"] + checks)
    reciprocal = list(dict.fromkeys((page_reciprocal or []) + (submit_page.get('reciprocal') or [])))
    reciprocal_note = f"要求先挂对方徽章/回链（{'、'.join(reciprocal)}）"

    # 有提交页的，业务类型默认导航与产品发布类（要求回链的归要挂回链或徽章）；第2步人工、第5步提交时看到不是再改
    if submit_page['url_form']:
        if reciprocal:
            return Judgement(VERDICT_FREE, [f'提交页 {submit_url} 有可填网址的表单，但{reciprocal_note}'],
                             GROUP_DIRECT, '；'.join(checks) or None, SCOPE_SITE, TYPE_BACKLINK)
        return Judgement(VERDICT_FREE, [f'提交页 {submit_url} 有可填网址的表单，没看到价格'], GROUP_DIRECT,
                         '；'.join(checks) or None, SCOPE_SITE, TYPE_DIRECTORY)
    if submit_page.get('email_submit'):
        addresses = '、'.join(submit_page['email_submit'])
        return Judgement(VERDICT_FREE, [f'提交页 {submit_url} 写明发邮件提交（{addresses}），没看到价格'], GROUP_DIRECT,
                         '；'.join([f'发邮件提交，收件地址 {addresses}'] + checks), SCOPE_SITE, TYPE_DIRECTORY)
    if submit_page.get('pr_submit'):  # awesome 清单是别人维护的目录，要用 GitHub 账号提 PR
        return Judgement(VERDICT_FREE, [f'提交页 {submit_url} 写明在 GitHub 提 PR 提交，没看到价格'], GROUP_SIGNUP,
                         '；'.join(['先看外人提的 PR 有没有被合并过'] + checks), SCOPE_SITE, TYPE_DIRECTORY)
    if submit_page['login_wall']:  # 要登录才看到表单：没写收费就默认免费，登录后有没有付款步骤留到提交时看
        login_note = _login_note(submit_page)
        free_words = submit_page.get('free_listing')
        said = f"写明免费收录（{'、'.join(free_words)}）" if free_words else '没写收费'
        pay_check = [] if free_words else [PAY_CHECK]
        if reciprocal:
            return Judgement(VERDICT_FREE, [f'提交页 {submit_url} {said}，要登录，{reciprocal_note}'],
                             GROUP_SIGNUP, '；'.join([login_note] + pay_check + checks), SCOPE_SITE, TYPE_BACKLINK)
        return Judgement(VERDICT_FREE, [f'提交页 {submit_url} {said}，要登录后提交；{login_note}'], GROUP_SIGNUP,
                         '；'.join(pay_check + [login_note] + checks), SCOPE_SITE, TYPE_DIRECTORY)
    if submit_page.get('app_only'):  # 提到 App 只是"可能"的信号，不改大类
        return Judgement(VERDICT_FREE, [f'提交页 {submit_url} 没写收费，没看到网页表单，提到下载 App'], GROUP_DIRECT,
                         '；'.join(['确认能不能在网页上提交（只能用 App 提交就是不可用）', PAY_CHECK] + checks), SCOPE_SITE,
                         TYPE_DIRECTORY)
    return Judgement(VERDICT_FREE, [f'提交页 {submit_url} 没写收费，表单看不到（可能靠脚本加载或要先登录）'], GROUP_DIRECT,
                     '；'.join(['确认提交方式和登录方式', PAY_CHECK] + checks), SCOPE_SITE, TYPE_DIRECTORY)


def _evidence_date(page: Dict) -> Optional[str]:
    """结论所依据的那次查看的日期：人工复核用复核时间，自动预判用检查时间"""
    stamp = page.get('reviewed_at') if page.get('final_verdict') else page.get('checked_at')
    return stamp[:10] if stamp else None


def rollup_by_site(pages: List[Dict]) -> List[Dict]:
    """
    按外链网站（去掉 www.）合并页面结论：留一个链接只要一个入口，所以有一个页面是免费类整站就是免费类；
    否则有无法判断的就要人看；再否则付费类；所有页面都是不可用才算不可用
    网站结论取自决定它的那个页面（代表页面），结论相同时优先人工复核过的、整站范围的
    分组、需人工核验、依据、范围、来源都跟着代表页面

    Returns:
        List[Dict]: 每个网站一条
    """
    by_site = {}
    for page in pages:
        by_site.setdefault(bare_host(page['domain_from']), []).append(page)
    sites = []
    for site, site_pages in by_site.items():
        best = min(site_pages, key=lambda p: (rank_in(final_verdict_of(p), SITE_PRIORITY),
                                              0 if p.get('final_verdict') else 1,
                                              0 if final_scope_of(p) == SCOPE_SITE else 1))
        signals = best.get('signals') or {}
        link = signals.get('competitor_link') or {}
        submit_links = signals.get('submit_links') or []
        sites.append({
            'site': site,
            'verdict': final_verdict_of(best),
            'group': final_group_of(best),
            'site_type': final_site_type_of(best),
            'check': final_check_of(best),
            'scope': final_scope_of(best),
            'source': final_source_of(best),
            'from_library': bool(best.get('auto_from_library')) and not best.get('final_verdict'),
            'evidence_at': _evidence_date(best),
            'reason': best.get('final_reason') or '；'.join(best.get('auto_reasons') or []),
            'entry_url': submit_links[0] if submit_links else None,
            'page': best['url_from'],
            'page_count': len(site_pages),
            'page_verdicts': dict(Counter(final_verdict_of(p) for p in site_pages)),
            'dofollow': link.get('dofollow') if link.get('found') else (best.get('backlink') or {}).get('dofollow'),
            'domain_rank': (best.get('backlink') or {}).get('domain_from_rank'),
        })
    return sites


def rank_in(value, order: List[str]) -> int:
    """在排序列表里的位置，不认识的排最后（排序用）"""
    return order.index(value) if value in order else len(order)
