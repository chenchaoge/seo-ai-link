"""
外链报告数据生成
报告模板 assets/report/ 按用户目录的样子摆：外链报告.html 在第一层，样式、脚本和数据在 data/report/
- 用户报告（菜单 5）：外链报告.html 拷到用户目录第一层，data/report/ 拷到用户目录的 data/report/，数据写进 data/report/report_data.js：
  完整外链库（SKILL 默认外链库 + 用户外链库）、各独立站的提交台账、外链网站是从哪个竞品挖出来的（分析结果目录）；
  每个外链网站带所属行业和对各独立站的赛道关系，行业清单和赛道大类一起写进去给页面画行业组成；
  台账每行和外链库每个外链网站（对各独立站）都带发外链原则的档（tier）和排序值（order，越小越先发）
- SKILL 默认网页（菜单 8）：只用 SKILL 默认外链库，写进模板自己的 data/report/report_data.js，直接打开模板就能看
页面直接读这个 JS 文件（双击打开就能看，不用起服务）；菜单 10 起本机网页服务时，这个文件每次请求现算（见 web_app.py）。
报告里不放密码、cookie；邮箱只留前两位。
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import DAILY_SUBMIT_LIMIT, DEFAULT_LIBRARY_FILES, INDUSTRIES, REPORT_TEMPLATE_DIR
from modules.industry import INDUSTRY_TO_GROUP, TRACK_ORDER, track_of
from modules.link_signals import bare_host
from modules.result_store import load_hand_edited_json, load_results
from modules.site_library import load_libraries, load_library
from modules.submission_ledger import load_ledger
from modules.submit_policy import TIERS, ledger_facts, priority_order, tier_of
from modules.user_space import UserSpace

DATA_FILE_NAME = 'report_data.js'
JS_VAR = 'REPORT_DATA'
TEMPLATE = UserSpace(REPORT_TEMPLATE_DIR)  # 模板目录和用户目录摆法一样，借 UserSpace 算位置
LOGO_FILE = 'logo.png'
PROFILE_PUBLIC_FIELDS = ['site', 'url', 'name', 'launch_date', 'industry']  # 独立站 profile 里只取这些公开字段
CHECK_TEXT_FIELDS = ['evidence']
STATUS_INCLUDED = '已收录'
ORIGIN_DEFAULT = 'SKILL 默认外链库'
ORIGIN_USER = '用户外链库'
MAX_PAGES = 3  # 每个外链网站最多列几个看过的页面
LIBRARY_ITEM_FIELDS = ('site', 'verdict', 'industry', 'group', 'site_type', 'scope', 'how', 'entry_url', 'check', 'reason',
                       'source', 'checked_at', 'first_seen', 'paid_option', 'domain_rank', 'dofollow')
CROSS_GROUP = '不分行业'  # 综合导航站、综合论坛博客不属于任何赛道大类，报告里单列一组
EMAIL_RE = re.compile(r'([A-Za-z0-9._%+-]{1,2})[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})')
PASSWORD_MASK = '******'


def mask_text(text: Optional[str]) -> Optional[str]:
    """自由文本里的邮箱只留前两位：support@x.com → su***@x.com"""
    if not text:
        return text
    return EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)


def collect_provenance(analyses_dir: Path) -> Dict[str, dict]:
    """
    从用户目录的分析结果看每个外链网站是从哪些竞品的外链里挖出来的、看过哪些页面

    Returns:
        {外链网站: {'competitors': [竞品域名], 'pages': [看过的页面，最多 MAX_PAGES 个]}}
    """
    info = {}
    if not analyses_dir.exists():
        return info
    for run_dir in sorted(p for p in analyses_dir.iterdir() if p.is_dir()):
        data = load_results(run_dir)
        if not data:
            continue
        competitor = bare_host(data.get('target') or '')
        for page in data.get('pages') or []:
            site = bare_host(page.get('domain_from') or '')
            if not site:
                continue
            item = info.setdefault(site, {'competitors': [], 'pages': []})
            if competitor and competitor not in item['competitors']:
                item['competitors'].append(competitor)
            url = page.get('url_from')
            if url and url not in item['pages'] and len(item['pages']) < MAX_PAGES:
                item['pages'].append(url)
    return info


def _first_included(checks: List[dict]) -> Optional[dict]:
    """第一次查到已收录的那条复查记录"""
    return next((c for c in checks if c.get('result') == STATUS_INCLUDED), None)


def _latest_rel(checks: List[dict]) -> Optional[str]:
    """最近一次已收录记录里写的链接属性（dofollow / nofollow），没写过返回 None"""
    for check in reversed(checks):
        if check.get('result') == STATUS_INCLUDED and check.get('rel'):
            return check['rel']
    return None


def _plan(item: dict) -> dict:
    """发外链原则的档和排序值；不发的（不可用等）都是 None"""
    return {'tier': item['tier'], 'order': priority_order(item) if item['tier'] else None}


def build_ledger_entries(ledger: Dict[str, dict], library: Dict[str, dict],
                         site_industry: Optional[str]) -> List[dict]:
    """
    台账转成报告用的列表：自由文本打码，补上第一次发现收录的时间和链接属性；
    所属行业以外链库为准（外链库没标的用台账里的），赛道关系按独立站的所属行业算，再按发外链原则算档和排序值
    """
    entries = []
    for site, entry in ledger.items():
        checks = [{**c, **{k: mask_text(c.get(k)) for k in CHECK_TEXT_FIELDS}} for c in entry.get('checks') or []]
        first = _first_included(checks)
        facts = ledger_facts(site, entry, library, site_industry)
        entries.append({
            'site': site,
            'status': entry.get('status'),
            'verdict': entry.get('verdict'),
            'industry': facts['industry'],
            'track': facts['track'],
            **_plan(facts),
            'needs_confirm': facts['needs_confirm'],  # 其他赛道、用户还没定要不要发
            'dofollow': facts['dofollow'],
            'domain_rank': facts['domain_rank'],
            'group': entry.get('group'),
            'site_type': entry.get('site_type'),
            'method': entry.get('method'),
            'submit_url': entry.get('submit_url'),
            'sources': entry.get('sources') or [],
            'added_at': entry.get('added_at'),
            'submitted_at': entry.get('submitted_at'),
            'checked_at': entry.get('checked_at'),
            'listing_url': entry.get('listing_url'),
            'target_url': entry.get('target_url'),
            'note': mask_text(entry.get('note') or entry.get('notes')),  # 老台账用的是 notes
            'hint': mask_text(entry.get('hint')),
            'check': mask_text(entry.get('check')),
            'checks': checks,
            'included_at': first.get('at') if first else None,
            'rel': _latest_rel(checks),
        })
    return entries


def load_profile(space: UserSpace, site: str) -> dict:
    """读独立站的 profile，只取公开字段和内页（网址、名称）；没有 profile 就只给域名"""
    path = space.profile_path(site)
    public = {'site': site, 'url': f"https://{site}/", 'name': site, 'launch_date': None, 'industry': None,
              'inner_pages': [], 'logo': None}
    if not path.exists():
        return public
    profile = load_hand_edited_json(path)  # 人工改过的文件，带 BOM 也认，写错了报出在哪
    public.update({k: profile[k] for k in PROFILE_PUBLIC_FIELDS if profile.get(k)})
    public['inner_pages'] = [{'url': p.get('url'), 'name': p.get('name')} for p in profile.get('inner_pages') or []]
    logo = space.site_dir(site) / LOGO_FILE
    if logo.exists():
        public['logo'] = logo.relative_to(space.root).as_posix()  # 相对用户目录第一层外链报告.html 的路径
    return public


def collect_passwords(space: UserSpace) -> List[str]:
    """读出所有独立站 profile 的密码，只用来检查报告数据里有没有混进去，不写进报告"""
    passwords = []
    for site in space.independent_sites():
        path = space.profile_path(site)
        if not path.exists():
            continue
        password = load_hand_edited_json(path).get('password')
        if password:
            passwords.append(password)
    return passwords


def build_library_sites(library: Dict[str, dict], user_sites: Set[str], provenance: Dict[str, dict],
                        used_by: Dict[str, Dict[str, str]], site_industries: Dict[str, Optional[str]]) -> List[dict]:
    """
    完整外链库转成报告用的列表：标出来自哪层外链库，补上竞品出处、各独立站用到哪一步、
    对每个独立站的赛道关系（tracks：{独立站: 赛道关系}）和发外链原则（plans：{独立站: {tier, order}}）

    Args:
        site_industries: {独立站: 所属行业}
    """
    sites = []
    for site, entry in sorted(library.items()):
        item = {k: entry.get(k) for k in LIBRARY_ITEM_FIELDS}
        for key in ('how', 'check', 'reason', 'paid_option'):
            item[key] = mask_text(item[key])
        item['origin'] = ORIGIN_USER if site in user_sites else ORIGIN_DEFAULT
        item.update(provenance.get(site) or {'competitors': [], 'pages': []})
        item['used_by'] = used_by.get(site, {})
        item['tracks'] = {s: track_of(industry, item['industry']) for s, industry in site_industries.items()}
        item['plans'] = {s: _plan({'track': track, 'dofollow': item['dofollow'], 'domain_rank': item['domain_rank'],
                                   'tier': tier_of(track, item['verdict'], item['dofollow'])})
                         for s, track in item['tracks'].items()}
        sites.append(item)
    return sites


def _industry_list() -> List[dict]:
    """行业清单和各自的赛道大类（综合导航站、综合论坛博客归「不分行业」），报告按这个顺序画"""
    return [{'name': industry, 'group': INDUSTRY_TO_GROUP.get(industry, CROSS_GROUP)} for industry in INDUSTRIES]


def _report_data(library_sites: List[dict], independent_sites: List[dict], user_report: bool) -> dict:
    """user_report：用户目录的报告（菜单 5、6）为 True，SKILL 自带的网页（菜单 8）为 False"""
    now = datetime.now()
    return {
        'user_report': user_report,
        'generated_at': now.strftime('%Y-%m-%d %H:%M'),
        'today': now.strftime('%Y-%m-%d'),
        'industries': _industry_list(),
        'tracks': TRACK_ORDER,
        'tiers': [{'key': key, 'desc': desc} for key, desc in TIERS.items()],  # 发外链原则的档，顺序 = 发的先后
        'daily_limit': DAILY_SUBMIT_LIMIT,
        'library': library_sites,
        'independent_sites': independent_sites,
    }


def report_data_js(data: dict, passwords: List[str]) -> str:
    """报告数据转成 JS（window.REPORT_DATA = {...}）；混进密码就打码"""
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    for password in passwords:
        text = text.replace(password, PASSWORD_MASK)
    return f"window.{JS_VAR} = {text};\n"


def write_report_data(files_dir: Path, data: dict, passwords: List[str]) -> Path:
    """写成 JS 文件，先写临时文件再替换"""
    path = files_dir / DATA_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix('.js.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(report_data_js(data, passwords))
    os.replace(tmp_path, path)
    return path


def copy_template(space: UserSpace):
    """把 SKILL 的报告模板拷到用户目录：网页放第一层，样式脚本放 data/report/（旧的整份换掉，模板的数据文件不拷）"""
    if space.report_files_dir.exists():
        shutil.rmtree(space.report_files_dir)
    shutil.copytree(TEMPLATE.report_files_dir, space.report_files_dir, ignore=shutil.ignore_patterns(DATA_FILE_NAME))
    shutil.copyfile(TEMPLATE.report_html, space.report_html)


def generate_report(space: UserSpace) -> dict:
    """
    菜单 5：生成用户目录里的外链报告

    Returns:
        {'path': 数据文件, 'index': 网页, 'library': 完整外链库外链网站数, 'user_library': 用户外链库外链网站数,
         'independent_sites': {独立站: 台账条目数}}
    """
    data, passwords, summary = build_user_report(space)
    copy_template(space)
    path = write_report_data(space.report_files_dir, data, passwords)
    return {'path': path, 'index': space.report_html, **summary}


def build_user_report(space: UserSpace) -> Tuple[dict, List[str], dict]:
    """
    现算用户报告的数据（菜单 5 写成文件；菜单 10 的网页每次打开都现算）

    Returns:
        (报告数据, 独立站密码（只用来打码，不写进报告）,
         {'library': 完整外链库外链网站数, 'user_library': 用户外链库外链网站数, 'independent_sites': {独立站: 台账条目数}})
    """
    library, _, user_sites = load_libraries(DEFAULT_LIBRARY_FILES, space.library_files)
    sites, used_by = [], {}
    for site in space.independent_sites():
        path = space.ledger_path(site)
        profile = load_profile(space, site)
        entries = build_ledger_entries(load_ledger(path), library, profile['industry']) if path.exists() else []
        for entry in entries:
            used_by.setdefault(entry['site'], {})[site] = entry['status']
        sites.append({**profile, 'entries': entries})
    sites.sort(key=lambda s: -len(s['entries']))  # 台账条目多的排前面
    site_industries = {s['site']: s['industry'] for s in sites}
    library_sites = build_library_sites(library, user_sites, collect_provenance(space.analyses_dir), used_by,
                                        site_industries)
    summary = {'library': len(library), 'user_library': len(user_sites),
               'independent_sites': {s['site']: len(s['entries']) for s in sites}}
    return _report_data(library_sites, sites, True), collect_passwords(space), summary


def generate_default_report() -> dict:
    """
    菜单 8：刷新 SKILL 自带的外链库网页，只用 SKILL 默认外链库（不读任何用户目录）

    Returns:
        {'path': 数据文件, 'index': 网页, 'library': 默认外链库外链网站数}
    """
    library = load_library(DEFAULT_LIBRARY_FILES)
    library_sites = build_library_sites(library, set(), {}, {}, {})
    path = write_report_data(TEMPLATE.report_files_dir, _report_data(library_sites, [], False), [])
    return {'path': path, 'index': TEMPLATE.report_html, 'library': len(library)}
