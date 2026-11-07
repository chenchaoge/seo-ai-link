"""
所属行业（赛道）：外链网站、独立站各标一个行业，发外链按赛道关系排先后
- 行业清单和赛道大类在 config.py（INDUSTRY_GROUPS、CROSS_INDUSTRIES、INDUSTRIES），规则见 references/criteria.md「所属行业」
- 外链网站的行业记在外链库（industry 字段），独立站的记在 profile.json（industry 字段）
- 每批外链网站的行业由 AI 判断，写进那一批分析结果目录的 industries.json（{"外链网站": "行业"}），整理结果时并进外链库
- 赛道关系（外链网站对某个独立站）：同赛道 > 相近赛道（同一个赛道大类）> 不分行业（综合导航站、综合论坛博客）> 其他赛道；
  前三种算契合赛道，发外链先后见 modules/submit_policy.py（发外链原则）
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from config import CROSS_INDUSTRIES, INDUSTRIES, INDUSTRY_GROUPS
from modules.link_signals import bare_host
from modules.result_store import load_hand_edited_json

INDUSTRIES_FILE = 'industries.json'
TRACK_SAME = '同赛道'
TRACK_NEAR = '相近赛道'
TRACK_CROSS = '不分行业'
TRACK_OTHER = '其他赛道'
TRACK_UNKNOWN = '行业未标'  # 外链网站或独立站还没标行业，先补上才能排
TRACK_ORDER = [TRACK_SAME, TRACK_NEAR, TRACK_CROSS, TRACK_OTHER, TRACK_UNKNOWN]
FIT_TRACKS = (TRACK_SAME, TRACK_NEAR, TRACK_CROSS)  # 契合赛道：发外链原则里优先发的
INDUSTRY_TO_GROUP = {industry: group for group, industries in INDUSTRY_GROUPS.items() for industry in industries}


def is_industry(value) -> bool:
    """是不是清单里的行业"""
    return value in INDUSTRIES


def track_of(site_industry: Optional[str], backlink_industry: Optional[str]) -> str:
    """外链网站对独立站的赛道关系"""
    if not site_industry or not backlink_industry:
        return TRACK_UNKNOWN
    if backlink_industry == site_industry:
        return TRACK_SAME
    if backlink_industry in CROSS_INDUSTRIES:
        return TRACK_CROSS
    group = INDUSTRY_TO_GROUP.get(site_industry)
    if group and group == INDUSTRY_TO_GROUP.get(backlink_industry):
        return TRACK_NEAR
    return TRACK_OTHER


def industries_path(run_dir: Path) -> Path:
    """这一批的行业判断文件"""
    return run_dir / INDUSTRIES_FILE


def load_industry_marks(run_dir: Path, logger: logging.Logger) -> Dict[str, str]:
    """
    读这一批的 industries.json：{"外链网站": "行业"}；外链网站名去掉 www.，不在清单里的行业报警告并跳过

    Returns:
        Dict[str, str]: {外链网站: 行业}，文件不存在返回空字典
    """
    path = industries_path(run_dir)
    if not path.exists():
        return {}
    marks = {}
    for site, industry in load_hand_edited_json(path).items():
        if not is_industry(industry):
            logger.warning(f"industries.json 的行业不在清单里（可选值见 references/criteria.md「所属行业」），跳过: "
                           f"{site} → {industry}")
            continue
        marks[bare_host(site)] = industry
    return marks
