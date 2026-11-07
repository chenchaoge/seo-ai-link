"""
竞品专属库：每分析一次竞品的外链出一个，放在那一批的分析结果目录里（competitor_library.json），是这批外链网站的处理清单
- batch：竞品、这批外链的拉取时间、当时发外链的独立站和它的所属行业、数量
- sites：一个外链网站一行；每次整理结果时按结论和当前独立站的提交台账整行刷新，不手改；
  industry 所属行业、track 对当前独立站的赛道关系（同赛道 / 相近赛道 / 不分行业 / 其他赛道 / 行业未标）
- 外链库只记外链网站本身的事实；外链网站是从哪个竞品挖出来的，报告从分析结果目录算
- 处理方式 handling 全由脚本算：待复核 / 不可用，不处理 / 台账：<台账状态> / 付费，先问用户要不要做 /
  免费，待加入台账（兜底，免费但还没进台账时才出现）。付费类问过用户后，决定记进台账（要做 = 待提交，不做 = 跳过），
  下次整理就变成「台账：<状态>」，换个竞品再碰到这个外链网站也不用再问
- 目标：每个网站最后都有处理方式，没有「待复核」「待加入台账」
"""

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from modules.classifier import VERDICT_NO, VERDICT_PAID, VERDICT_UNKNOWN
from modules.industry import track_of
from modules.result_store import load_hand_edited_json

COMPETITOR_LIBRARY_FILE = 'competitor_library.json'
HANDLING_PENDING_REVIEW = '待复核'
HANDLING_NO = '不可用，不处理'
HANDLING_PAID = '付费，先问用户要不要做'
HANDLING_TO_LEDGER = '免费，待加入台账'
LEDGER_PREFIX = '台账：'
OPEN_HANDLINGS = (HANDLING_PENDING_REVIEW, HANDLING_TO_LEDGER)  # 还没处理完的


def competitor_library_path(run_dir: Path) -> Path:
    """专属库路径：放在这一批的分析结果目录里"""
    return run_dir / COMPETITOR_LIBRARY_FILE


def default_handling(verdict: str, ledger_entry: Optional[dict]) -> str:
    """按结论和当前独立站的台账算处理方式：免费类、付费类在台账里有就跟着台账状态走（付费类的决定也记在台账）"""
    if verdict == VERDICT_UNKNOWN:
        return HANDLING_PENDING_REVIEW
    if verdict == VERDICT_NO:
        return HANDLING_NO
    if ledger_entry:
        return f"{LEDGER_PREFIX}{ledger_entry.get('status')}"
    return HANDLING_PAID if verdict == VERDICT_PAID else HANDLING_TO_LEDGER


def load_competitor_library(path: Path) -> dict:
    """读专属库，不存在返回空结构"""
    if not path.exists():
        return {'batch': {}, 'sites': {}}
    return load_hand_edited_json(path)


def save_competitor_library(path: Path, library: dict):
    """写专属库：batch 一行，sites 里一个外链网站一行（先写临时文件再替换）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    site_lines = [f"{json.dumps(site, ensure_ascii=False)}: {json.dumps(entry, ensure_ascii=False)}"
                  for site, entry in library['sites'].items()]
    text = ('{\n"batch": ' + json.dumps(library['batch'], ensure_ascii=False) + ',\n"sites": {\n'
            + ',\n'.join(site_lines) + '\n}\n}\n')
    tmp_path = path.with_suffix('.json.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp_path, path)


def update_competitor_library(path: Path, data: dict, sites: List[dict], seen: set, ledger: Dict[str, dict],
                              independent_site: Optional[str], industries: Dict[str, Optional[str]],
                              site_industry: Optional[str]) -> Dict[str, int]:
    """
    按这次的结果生成或刷新专属库

    Args:
        path: 专属库路径
        data: results.json 内容
        sites: classifier.rollup_by_site 的结果
        seen: 这批之前就在外链库里的外链网站
        ledger: 当前独立站的提交台账
        independent_site: 当前发外链的独立站
        industries: 这批外链网站的所属行业 {外链网站: 行业}
        site_industry: 当前独立站的所属行业

    Returns:
        dict: 各处理方式的网站数，外加 open（还没处理完的）
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    old = load_competitor_library(path)
    old_sites = old.get('sites') or {}
    entries = {}
    for info in sites:
        prev = old_sites.get(info['site']) or {}
        handling = default_handling(info['verdict'], ledger.get(info['site']))
        handled_at = prev.get('handled_at') if handling == prev.get('handling') else now  # 处理方式变了才记新时间
        industry = industries.get(info['site'])
        entries[info['site']] = {
            'verdict': info['verdict'], 'industry': industry, 'track': track_of(site_industry, industry),
            'group': info.get('group'), 'site_type': info.get('site_type'), 'check': info.get('check'),
            'scope': info.get('scope'), 'source': '外链库' if info.get('from_library') else info.get('source'),
            'seen_before': info['site'] in seen, 'reason': info.get('reason'), 'page': info.get('page'),
            'page_count': info.get('page_count'), 'dofollow': info.get('dofollow'),
            'domain_rank': info.get('domain_rank'), 'handling': handling, 'handled_at': handled_at,
        }
    fetch = data.get('fetch') or {}
    library = {
        'batch': {
            'target': data.get('target'), 'batch_at': data.get('created_at'), 'independent_site': independent_site,
            'independent_site_industry': site_industry, 'backlinks': len(data.get('backlinks') or []),
            'total_backlinks': fetch.get('total_count'), 'pages': len(data.get('pages') or []),
            'sites': len(entries), 'updated_at': now,
        },
        'sites': dict(sorted(entries.items())),
    }
    save_competitor_library(path, library)
    counts = dict(Counter(_handling_category(e['handling']) for e in entries.values()))
    counts['open'] = sum(1 for e in entries.values() if e['handling'] in OPEN_HANDLINGS)
    return counts


def _handling_category(handling: str) -> str:
    """统计用的处理方式类别：台账同步来的合成一类"""
    return '已加入台账' if handling.startswith(LEDGER_PREFIX) else handling
