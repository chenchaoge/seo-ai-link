"""
外链页面信号提取：从来源页面的 HTML 里找"能不能留网址"的各种迹象（纯函数，不联网）
借鉴的开源代码（均为 MIT 许可）：
- camposped/submitdock lib/verify.ts：找指向目标的 <a>、rel 是否 nofollow/ugc/sponsored、meta robots nofollow、<base> 解析
- AgriciDaniel/claude-seo scripts/verify_backlinks.py：靠前端脚本渲染的页面识别（标记 + 文字太少）
- marketing-MEER/backlink-gap-finder core.py：垃圾域名后缀
- s87343472/backlink-pilot src/scout/discover.js：提交入口、登录入口的关键词思路
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from config import KNOWN_PLATFORMS, SIGNAL_RULES

PATTERNS = {key: re.compile(pattern, re.I) for key, pattern in SIGNAL_RULES['patterns'].items()}
STAT_SITE_WORDS = re.compile(SIGNAL_RULES['stat_site_words'], re.I)
GENERATOR_META = re.compile(r'^generator$', re.I)
ROBOTS_META = re.compile(r'^(robots|googlebot)$', re.I)

# 谷歌把 ugc / sponsored 当 nofollow 对待（submitdock NOFOLLOW_TOKENS 同款）
NOFOLLOW_TOKENS = {'nofollow', 'ugc', 'sponsored'}
# 链接所在区域：按从近到远的外层元素判断；同一页面多个链接时按这个顺序取最重要的区域
SIDEBAR_AREA = '侧边栏/页脚'
CONTENT_AREA = '正文'
AREA_RULES = [('评论区', 'comment_area'), ('论坛帖子', 'forum_area'), (CONTENT_AREA, 'content_area'),
              (SIDEBAR_AREA, 'sidebar_area')]
MAX_ANCESTOR_DEPTH = 15
BLOCKED_STATUS = (403, 429, 503)


def bare_host(url_or_host: str) -> str:
    """取主机名并去掉 www.（submitdock sameTarget 的同款处理）"""
    value = url_or_host.strip()
    try:
        host = urlparse(value if '://' in value else 'https://' + value).netloc.split(':')[0].lower()
    except ValueError:  # 网页里写坏的链接（如 http://[xxx），解析不出主机名
        return ''
    return host[4:] if host.startswith('www.') else host


def _abs_url(base: str, href: str) -> Optional[str]:
    """把页面里的链接转成完整网址，写坏的链接返回 None"""
    try:
        return urljoin(base, href.strip())
    except ValueError:
        return None


def same_site(host: str, site: str) -> bool:
    """host 是 site 本身或它的子域名"""
    return host == site or host.endswith('.' + site)


def match_known_platform(domain: str) -> Optional[dict]:
    """来源域名是已知平台时返回 {'group', 'site_type', 'hint', 'check'}，否则 None"""
    host = bare_host(domain)
    for platform, note in KNOWN_PLATFORMS.items():
        if same_site(host, platform):
            return note
    return None


def is_stat_site(domain: str) -> bool:
    """自动生成"网站估值/whois"页面的站"""
    return bool(STAT_SITE_WORDS.search(bare_host(domain)))


def has_spammy_tld(domain: str) -> bool:
    return bare_host(domain).rsplit('.', 1)[-1] in SIGNAL_RULES['spammy_tlds']


def is_blocked(status: Optional[int], html: str) -> bool:
    """被防爬拦截：403/429/503，或返回 200 但内容是验证页"""
    if status in BLOCKED_STATUS:
        return True
    head = html[:5000]
    return bool(PATTERNS['blocked_text'].search(head)) and len(html) < 30000


def _hits(key: str, text: str, limit: int = 3) -> List[str]:
    """返回某条规则在文字里命中的片段（去重，最多 limit 个），用作判断依据"""
    found = []
    for match in PATTERNS[key].finditer(text):
        piece = match.group(0).strip().lower()
        if piece and piece not in found:
            found.append(piece)
        if len(found) >= limit:
            break
    return found


def _marks(node) -> str:
    """元素的 id + class 拼成一串，用来判断区域"""
    classes = node.get('class') or []
    return ' '.join([node.get('id') or ''] + list(classes))


def _ancestor_area(tag) -> Optional[str]:
    """从链接往外层找，判断它在评论区 / 论坛帖子 / 文章正文 / 侧边栏页脚里"""
    node = tag
    for _ in range(MAX_ANCESTOR_DEPTH):
        node = node.parent
        if node is None or node.name in ('body', 'html', '[document]'):
            break
        marks = _marks(node)
        for area, key in AREA_RULES:
            if marks.strip() and PATTERNS[key].search(marks):
                return area
        if node.name in ('footer', 'aside'):
            return SIDEBAR_AREA
        if node.name == 'article':  # 没有类名的 <article> 也算文章正文
            return CONTENT_AREA
    return None


def _overall_area(areas: List[Optional[str]]) -> Optional[str]:
    """
    多个竞品链接时的总区域：评论区 > 论坛帖子 > 正文；
    只有全部链接都在侧边栏/页脚才算侧边栏/页脚（有一个位置不明的就不算，免得弹窗页脚这类误判盖过主链接）
    """
    area = next((name for name, _ in AREA_RULES if name != SIDEBAR_AREA and name in areas), None)
    if area is None and areas and all(a == SIDEBAR_AREA for a in areas):
        return SIDEBAR_AREA
    return area


def has_meta_nofollow(soup) -> bool:
    """页面级 meta robots nofollow（submitdock hasMetaNofollow 的 Python 版）"""
    for meta in soup.find_all('meta', attrs={'name': ROBOTS_META}):
        tokens = re.split(r'[\s,]+', (meta.get('content') or '').lower())
        if 'nofollow' in tokens or 'none' in tokens:
            return True
    return False


def find_competitor_link(soup, page_url: str, target: str) -> Dict:
    """
    找页面上指向竞品的链接（submitdock findBacklink 的 Python 版，外加链接所在区域）
    指向竞品任何页面都算；有一个 dofollow 就算 dofollow
    """
    target_host = bare_host(target)
    base_tag = soup.find('base', href=True)
    base = urljoin(page_url, base_tag['href']) if base_tag else page_url
    page_nofollow = has_meta_nofollow(soup)

    matches = []
    for a in soup.find_all('a', href=True):
        href = _abs_url(base, a['href'])
        if not href or not same_site(bare_host(href), target_host):
            continue
        rel = [r.lower() for r in (a.get('rel') or [])]
        matches.append({
            'href': href,
            'rel': rel,
            'nofollow': page_nofollow or bool(NOFOLLOW_TOKENS & set(rel)),
            'anchor': a.get_text(' ', strip=True)[:100],
            'area': _ancestor_area(a),
        })

    if not matches:
        return {'found': False, 'page_nofollow': page_nofollow}
    best = next((m for m in matches if not m['nofollow']), matches[0])
    area = _overall_area([m['area'] for m in matches])
    return {
        'found': True,
        'count': len(matches),
        'href': best['href'],
        'rel': ' '.join(best['rel']),
        'dofollow': not best['nofollow'],
        'anchor': best['anchor'],
        'area': area,
        'sponsored': any('sponsored' in m['rel'] for m in matches),
        'page_nofollow': page_nofollow,
    }


def _is_url_field(inp) -> bool:
    if (inp.get('type') or '').lower() == 'url':
        return True
    return any(PATTERNS['url_field_name'].search(inp.get(attr) or '') for attr in ('name', 'id'))


def detect_forms(soup) -> Dict:
    """找评论表单（及其"网站"栏）、其他带网址栏的表单、密码框"""
    result = {'comment_form': False, 'comment_url_field': False, 'other_url_form': False, 'password_form': False}
    for form in soup.find_all('form'):
        marks = ' '.join([_marks(form), form.get('action') or '', form.get('name') or ''])
        inputs = form.find_all('input')
        textareas = form.find_all('textarea')
        is_comment = bool(PATTERNS['comment_form'].search(marks)) or any(
            PATTERNS['comment_form'].search(t.get('name') or t.get('id') or '') for t in textareas)
        has_url = any(_is_url_field(i) for i in inputs)
        if any((i.get('type') or '').lower() == 'password' for i in inputs):
            result['password_form'] = True
        if is_comment:
            result['comment_form'] = True
            result['comment_url_field'] = result['comment_url_field'] or has_url
        elif has_url:
            result['other_url_form'] = True
    return result


def _match_platform(generator: str, html_lower: str, names: List[str]) -> Optional[str]:
    """按 <meta name="generator"> 或"powered by xxx"识别建站程序"""
    for name in names:
        if name in generator or f'powered by {name}' in html_lower:
            return name
    return None


def find_submit_links(soup, page_url: str) -> List[str]:
    """找本站的"提交网站/工具"入口（最多3个）"""
    page_host = bare_host(page_url)
    links = []
    for a in soup.find_all('a', href=True):
        href = _abs_url(page_url, a['href'])
        if not href or not href.startswith('http') or bare_host(href) != page_host:
            continue
        text = a.get_text(' ', strip=True)
        if PATTERNS['submit_text'].search(text) or PATTERNS['submit_href'].search(urlparse(href).path):
            if href not in links:
                links.append(href)
        if len(links) >= 3:
            break
    return links


def has_login_entry(soup) -> bool:
    """有"注册/登录"入口"""
    return any(PATTERNS['login_text'].search(tag.get_text(' ', strip=True)) for tag in soup.find_all(['a', 'button']))


def _visible_text(soup) -> str:
    """去掉脚本/样式后的可见文字（会改动 soup，放在最后调用）"""
    for tag in soup(['script', 'style', 'noscript', 'template']):
        tag.decompose()
    return soup.get_text(' ', strip=True)


def looks_js_rendered(html_lower: str, word_count: int) -> bool:
    """靠前端脚本渲染（借鉴 claude-seo）：有框架标记且文字少，或网页很大但文字极少"""
    has_marker = any(marker in html_lower for marker in SIGNAL_RULES['js_markers'])
    return (has_marker and word_count < 300) or (len(html_lower) > 5000 and word_count < 50)


def extract_signals(html: str, page_url: str, target: str) -> Dict:
    """
    提取外链所在页面的全部信号

    Args:
        html: 页面 HTML
        page_url: 页面最终网址（跟随跳转后）
        target: 目标网址/域名（竞品）

    Returns:
        Dict: 各项信号
    """
    soup = BeautifulSoup(html, 'lxml')
    html_lower = html.lower()
    generator = ' '.join(m.get('content') or '' for m in soup.find_all('meta', attrs={'name': GENERATOR_META})).lower()

    signals = {
        'competitor_link': find_competitor_link(soup, page_url, target),
        **detect_forms(soup),
        'third_party_comments': next((m for m in SIGNAL_RULES['third_party_comments'] if m in html_lower), None),
        'forum_platform': _match_platform(generator, html_lower, SIGNAL_RULES['forum_generators']),
        'wiki_platform': _match_platform(generator, html_lower, SIGNAL_RULES['wiki_generators']),
        'submit_links': find_submit_links(soup, page_url),
        'login_entry': has_login_entry(soup),
    }
    text = _visible_text(soup)
    word_count = len(text.split())
    signals.update({
        'comment_login_required': bool(PATTERNS['comment_login_required'].search(text)),
        'comments_closed': bool(PATTERNS['comments_closed'].search(text)),
        'ugc_text': _hits('ugc_text', text),
        'paid_strong': _hits('paid_strong', text),
        'reciprocal': _hits('reciprocal_text', text),
        'word_count': word_count,
        'js_rendered': looks_js_rendered(html_lower, word_count),
    })
    return signals


def _mailto_addresses(soup) -> List[str]:
    """页面上的 mailto 邮箱地址（去重，最多3个）"""
    found = []
    for a in soup.find_all('a', href=True):
        if a['href'].lower().startswith('mailto:'):
            address = a['href'][7:].split('?')[0].strip()
            if address and address not in found:
                found.append(address)
    return found[:3]


def _requirements(text: str) -> List[str]:
    """提交页写明的收录条件，只作为需人工核验的内容（符不符合要看独立站的情况）"""
    notes = []
    if PATTERNS['free_tier_required'].search(text):
        notes.append('要求有免费档才收')
    limits = _hits('category_limit_text', text, limit=2)
    if limits:
        notes.append(f"写了只收某类：{'、'.join(limits)}")
    if PATTERNS['github_repo_text'].search(text):
        notes.append('要填 GitHub 仓库地址')
    if PATTERNS['llms_txt_text'].search(text):
        notes.append('提到 llms.txt，可能要求网站先有 llms.txt')
    return notes


def analyze_submit_page(html: str) -> Dict:
    """提交页信号：有没有可填网址的表单、要不要登录及登录方式、价格/免费字样、发邮件或提 PR 提交、收录条件、人机验证"""
    soup = BeautifulSoup(html, 'lxml')
    html_lower = html.lower()
    forms = detect_forms(soup)
    mailtos = _mailto_addresses(soup)
    text = _visible_text(soup)
    word_count = len(text.split())
    return {
        'url_form': forms['other_url_form'] or forms['comment_url_field'],
        'login_wall': forms['password_form'] or bool(PATTERNS['login_wall_text'].search(text)),
        'password_form': forms['password_form'],
        'oauth_login': _hits('oauth_text', text),
        'paid_strong': _hits('paid_strong', text) + _hits('paid_submit_text', text),
        'price_hits': _hits('paid_price', text),
        'free_hits': _hits('free_text', text),
        'free_listing': _hits('free_listing_text', text),
        'reciprocal': _hits('reciprocal_text', text),
        'email_submit': mailtos if mailtos and PATTERNS['email_submit_text'].search(text) else [],
        'pr_submit': bool(PATTERNS['pr_submit_text'].search(text)),
        'app_only': bool(PATTERNS['app_only_text'].search(text)),
        'captcha': any(marker in html_lower for marker in SIGNAL_RULES['captcha_markers']),
        'requirements': _requirements(text),
        'js_rendered': looks_js_rendered(html_lower, word_count),
    }
