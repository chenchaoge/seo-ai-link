"""
外链提交台账：用户目录 data/sites/<独立站>/ledger.json，记录这个独立站在每个外链网站上发外链的进度
- 免费类整理结果时自动加进来；付费类问过用户后由人加（要做 = 待提交，不做 = 跳过），竞品专属库按它显示处理方式
- 按外链网站（去掉 www.）一条，同一个外链网站只提交一次
- 一个外链网站一行，方便人工直接编辑；脚本只往里加新的外链网站、补来源页面、同步所属行业，不改已有的状态和记录
- 状态和提交方式由人工/AI 按进度改，可用值见 references/submit.md
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from modules.classifier import (
    VERDICT_FREE, final_check_of, final_group_of, final_site_type_of, final_verdict_of, normalize_group,
)
from modules.link_signals import bare_host
from modules.result_store import load_hand_edited_json

LEDGER_VERDICTS = [VERDICT_FREE]  # 免费类的外链网站进台账
STATUS_PENDING = '待提交'
STATUS_SUBMITTED = '已提交'  # 等对方审核，每日独立站外链回访查的就是这个状态
# industry = 外链网站的所属行业（整理结果时跟外链库同步），group = 发外链方式，site_type = 业务类型；
# user_confirmed = 用户看过、定了要发（其他赛道的要用户点头才发，见 modules/submit_policy.py）；
# checked_at = 最后一次每日独立站外链回访的时间；
# checks = 每次回访一条记录（at、result、listing_url、rel、evidence），提交后第二天起每天查一次，收录、被拒或查满 7 次后不再查
LEDGER_FIELDS = ['status', 'verdict', 'industry', 'user_confirmed', 'group', 'site_type', 'check', 'method',
                 'submit_url', 'hint', 'sources', 'source_pages', 'added_at', 'submitted_at', 'checked_at', 'checks',
                 'listing_url', 'note']


def load_ledger(path: Path) -> Dict[str, dict]:
    """读台账，不存在返回空字典"""
    if not path.exists():
        return {}
    ledger = load_hand_edited_json(path)
    for entry in ledger.values():  # 旧台账里的老分组值自动换成新的两个维度
        entry['group'], entry['site_type'] = normalize_group(entry.get('group'), entry.get('site_type'))
    return ledger


def _ordered(entry: dict) -> dict:
    """按 LEDGER_FIELDS 的顺序写字段，人加的别的字段跟在后面"""
    ordered = {key: entry.get(key) for key in LEDGER_FIELDS}
    ordered.update({key: value for key, value in entry.items() if key not in LEDGER_FIELDS})
    return ordered


def save_ledger(path: Path, ledger: Dict[str, dict]):
    """写台账：一个外链网站一行（先写临时文件再替换）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{json.dumps(site, ensure_ascii=False)}: {json.dumps(_ordered(entry), ensure_ascii=False)}"
             for site, entry in ledger.items()]
    tmp_path = path.with_suffix('.json.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write('{\n' + ',\n'.join(lines) + '\n}\n')
    os.replace(tmp_path, path)


def _page_hint(page: dict) -> str:
    """判断依据：有人工说明用人工的，否则用自动预判依据"""
    return page.get('final_reason') or '；'.join(page.get('auto_reasons') or [])


def _new_entry(page: dict, target: str, now: str) -> dict:
    """新外链网站的台账条目"""
    submit_links = (page.get('signals') or {}).get('submit_links') or []
    entry = {key: None for key in LEDGER_FIELDS}
    entry.update({
        'status': STATUS_PENDING,
        'verdict': final_verdict_of(page),
        'group': final_group_of(page),
        'site_type': final_site_type_of(page),
        'check': final_check_of(page),
        'submit_url': submit_links[0] if submit_links else None,
        'hint': _page_hint(page),
        'sources': [target],
        'source_pages': [page['url_from']],
        'added_at': now,
    })
    return entry


def merge_into_ledger(ledger: Dict[str, dict], pages: List[dict], target: str) -> Dict[str, int]:
    """
    把一次结果里免费类的页面并进台账

    Args:
        ledger: 台账（原地修改）
        pages: results.json 的 pages（已合并人工复核结论）
        target: 这次分析的竞品，记进 sources

    Returns:
        dict: {'added': 新增外链网站数, 'updated': 已有外链网站补了来源的个数}
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    added, updated = set(), set()
    for page in pages:
        if final_verdict_of(page) not in LEDGER_VERDICTS:
            continue
        site = bare_host(page['domain_from'])
        entry = ledger.get(site)
        if entry is None:
            ledger[site] = _new_entry(page, target, now)
            added.add(site)
            continue
        if page['url_from'] not in entry['source_pages']:  # 已有外链网站：只补来源页面和竞品，不动状态
            entry['source_pages'].append(page['url_from'])
            if site not in added:
                updated.add(site)
        if target not in entry['sources']:
            entry['sources'].append(target)
            if site not in added:
                updated.add(site)
    return {'added': len(added), 'updated': len(updated)}


def sync_industries(ledger: Dict[str, dict], industries: Dict[str, Optional[str]]) -> int:
    """
    台账每行的所属行业跟外链库同步（原地修改）；外链库里没标的不清掉台账里已有的

    Args:
        industries: {外链网站: 行业}

    Returns:
        int: 行业有变化的行数
    """
    changed = 0
    for site, entry in ledger.items():
        industry = industries.get(site)
        if industry and entry.get('industry') != industry:
            entry['industry'] = industry
            changed += 1
    return changed


def recheck_due(ledger: Dict[str, dict], day: str) -> List[str]:
    """
    这一天该每日独立站外链回访的外链网站：已提交、提交日早于这一天、这一天还没回访过
    （跟报告「今天还有几个没回访」同一规则，见 assets/report/data/report/sites.js）

    Args:
        day: 'YYYY-MM-DD'
    """
    return [site for site, entry in ledger.items()
            if entry.get('status') == STATUS_SUBMITTED
            and (entry.get('submitted_at') or '')[:10] < day
            and (entry.get('checked_at') or '')[:10] != day]
