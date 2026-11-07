"""
发外链原则见 references/submit.md「发外链原则」；这里只管程序排档和每天额度，档的说明在 TIERS
"""

from datetime import datetime
from typing import Dict, List, Optional

from config import DAILY_SUBMIT_LIMIT
from modules.classifier import VERDICT_FREE, VERDICT_PAID
from modules.industry import FIT_TRACKS, TRACK_ORDER, TRACK_OTHER, TRACK_UNKNOWN, track_of
from modules.submission_ledger import STATUS_PENDING

TIER_1, TIER_2, TIER_3, TIER_4, TIER_5, TIER_6 = '第1档', '第2档', '第3档', '第4档', '第5档', '第6档'
TIER_UNKNOWN = '先补行业'
TIERS = {  # 档 → 说明，顺序 = 发外链的先后
    TIER_1: '契合赛道、免费、dofollow',
    TIER_2: '其他赛道、免费、dofollow（先问用户发不发）',
    TIER_3: '契合赛道、免费、nofollow 或没记录',
    TIER_4: '其他赛道、免费、nofollow 或没记录（先问用户发不发）',
    TIER_5: '免费、冷门页 noindex（其他赛道的先问用户发不发）',
    TIER_6: '付费（先问用户发不发，定了要做的才发）',
    TIER_UNKNOWN: '行业未标，先补所属行业再排',
}
TIER_ORDER = list(TIERS)
DOFOLLOW_ORDER = {True: 0, None: 1, False: 2}  # dofollow → 没记录 → nofollow
REL_TEXT = {True: 'dofollow', None: '链接属性没记录', False: 'nofollow'}


def tier_of(track: str, verdict: Optional[str], dofollow: Optional[bool], noindex: Optional[bool]) -> Optional[str]:
    """外链网站在发外链原则里排第几档；不可用、无法判断的不发，返回 None；noindex 没记录的按原来的档排"""
    if verdict == VERDICT_PAID:
        return TIER_6
    if verdict != VERDICT_FREE:
        return None
    if track == TRACK_UNKNOWN:
        return TIER_UNKNOWN
    if noindex is True:
        return TIER_5
    fit = track in FIT_TRACKS
    if dofollow is True:
        return TIER_1 if fit else TIER_2
    return TIER_3 if fit else TIER_4


def needs_confirm(track: str, verdict: Optional[str], entry: dict) -> bool:
    """其他赛道的、付费的外链网站要先给用户看，用户定了要发（台账 user_confirmed 是 true）才发"""
    return (track == TRACK_OTHER or verdict == VERDICT_PAID) and entry.get('user_confirmed') is not True


def priority_key(item: dict) -> tuple:
    """排序键：档 → 赛道关系 → 链接属性 → 权重从高到低；item 要有 tier、track、dofollow、domain_rank"""
    return (TIER_ORDER.index(item['tier']), TRACK_ORDER.index(item['track']), DOFOLLOW_ORDER.get(item['dofollow'], 1),
            -(item['domain_rank'] or 0))


def priority_order(item: dict) -> int:
    """priority_key 压成一个整数（报告里排序用），越小越先发"""
    tier, track, rel, rank = priority_key(item)
    return ((tier * 10 + track) * 10 + rel) * 1000 + 100 + rank  # rank 是 -domain_rank（-100～0），加 100 变成 0～100


def ledger_facts(site: str, entry: dict, library: Dict[str, dict], site_industry: Optional[str]) -> dict:
    """
    台账一行排先后要用的事实：结论、所属行业以外链库为准（外链库没有的用台账里的），链接属性、冷门页 noindex 和权重只在外链库里有

    Returns:
        {'site', 'verdict', 'industry', 'track', 'dofollow', 'noindex', 'domain_rank', 'tier', 'needs_confirm'}
    """
    lib = library.get(site) or {}
    verdict = lib.get('verdict') or entry.get('verdict')
    industry = lib.get('industry') or entry.get('industry')
    track = track_of(site_industry, industry)
    return {'site': site, 'verdict': verdict, 'industry': industry, 'track': track, 'dofollow': lib.get('dofollow'),
            'noindex': lib.get('noindex'), 'domain_rank': lib.get('domain_rank'),
            'tier': tier_of(track, verdict, lib.get('dofollow'), lib.get('noindex')),
            'needs_confirm': needs_confirm(track, verdict, entry)}


def stale_pending(ledger: Dict[str, dict], library: Dict[str, dict]) -> List[dict]:
    """
    台账里还是待提交、但已经发不了的外链网站：外链库判成不可用，或台账和外链库都没写结论。
    submit_queue 不排它们，按铁律要把台账那行改成跳过

    Returns:
        [{'site', 'verdict'}]
    """
    stale = []
    for site, entry in ledger.items():
        verdict = (library.get(site) or {}).get('verdict') or entry.get('verdict')
        if entry.get('status') == STATUS_PENDING and verdict not in (VERDICT_FREE, VERDICT_PAID):
            stale.append({'site': site, 'verdict': verdict})
    return stale


def submit_queue(ledger: Dict[str, dict], library: Dict[str, dict], site_industry: Optional[str]) -> List[dict]:
    """
    台账里待提交的外链网站按发外链原则排好（不可用、无法判断的不排，按铁律它们应该已改成跳过）

    Returns:
        [{'site', 'verdict', 'industry', 'track', 'dofollow', 'noindex', 'domain_rank', 'tier', 'needs_confirm',
          'group', 'submit_url'}]，第一个就是下一个要发的（needs_confirm 是 True 的先问用户）
    """
    queue = []
    for site, entry in ledger.items():
        if entry.get('status') != STATUS_PENDING:
            continue
        item = ledger_facts(site, entry, library, site_industry)
        if item['tier']:
            queue.append({**item, 'group': entry.get('group'), 'submit_url': entry.get('submit_url')})
    return sorted(queue, key=priority_key)


def today_text() -> str:
    """今天的日期（本机时间，YYYY-MM-DD）"""
    return datetime.now().strftime('%Y-%m-%d')


def submitted_on(ledger: Dict[str, dict], day: str) -> int:
    """这一天成功提交了几个：台账 submitted_at 是这一天的（提交成功才写 submitted_at）"""
    return sum(1 for entry in ledger.values() if (entry.get('submitted_at') or '')[:10] == day)


def daily_quota(ledger: Dict[str, dict], day: str) -> dict:
    """
    这一天的提交额度（每个独立站分别算）

    Returns:
        {'day': 日期, 'submitted': 已成功提交几个, 'limit': 每天最多几个, 'left': 还能发几个}
    """
    submitted = submitted_on(ledger, day)
    return {'day': day, 'submitted': submitted, 'limit': DAILY_SUBMIT_LIMIT,
            'left': max(0, DAILY_SUBMIT_LIMIT - submitted)}
