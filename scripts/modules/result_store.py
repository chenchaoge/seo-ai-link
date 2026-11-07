"""
结果文件读写：每查一次竞品一个分析结果目录，在用户目录 data/analyses/<时间戳>_<竞品>/
- results.json：外链、自动预判、人工复核结论
- reviews.json：人工复核结论（人工直接编辑这个小文件），整理结果时按来源页面网址合并进 results.json
- 同一目录里还有所属行业 industries.json（见 modules/industry.py）、竞品专属库 competitor_library.json 和日志 log_<时间>.log
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from modules.classifier import (
    FREE_GROUPS, SCOPE_PAGE, SCOPE_SITE, SETTLED_VERDICTS, SITE_TYPES, VERDICT_FREE, normalize_group,
)
from modules.link_signals import bare_host

RESULTS_FILE = 'results.json'
REVIEWS_FILE = 'reviews.json'
# reviews.json 里的字段：final_group = 发外链方式，final_site_type = 业务类型（都只有免费类才写）
REVIEW_FIELDS = ['final_verdict', 'final_group', 'final_site_type', 'final_check', 'final_reason', 'reviewed_at']
# 重判时从旧页面带过来的人工复核字段：final_scope 由合并时按键的种类定（网站名 = 整站，页面网址 = 页面）
CARRY_FIELDS = REVIEW_FIELDS + ['final_scope']


def create_run_dir(data_root: Path, target: str) -> Path:
    """
    为一次查询新建运行目录（含 raw/ 子目录）

    Args:
        data_root: data 根目录
        target: 目标网址或域名

    Returns:
        Path: 运行目录
    """
    slug = re.sub(r'^https?://', '', target.strip().lower())
    slug = re.sub(r'[^0-9a-z.-]+', '_', slug).strip('_')[:80]
    run_dir = data_root / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}"
    (run_dir / 'raw').mkdir(parents=True, exist_ok=True)
    return run_dir


def save_results(run_dir: Path, data: dict):
    """写 results.json（先写临时文件再替换，中途断电也不会写坏原文件）"""
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    path = run_dir / RESULTS_FILE
    tmp_path = run_dir / (RESULTS_FILE + '.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_results(run_dir: Path) -> Optional[dict]:
    """读 results.json，不存在返回 None"""
    path = run_dir / RESULTS_FILE
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_hand_edited_json(path: Path) -> dict:
    """读人工直接编辑的 JSON 文件（reviews.json、台账、设置、独立站资料），记事本存的可能带 BOM 也认；格式写错时报出文件、行号和原因"""
    with open(path, 'r', encoding='utf-8-sig') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} 格式写错了（第 {e.lineno} 行第 {e.colno} 列）：{e.msg}") from e


def apply_reviews(run_dir: Path, data: dict, logger: logging.Logger):
    """
    把 reviews.json 的人工复核结论合并进页面
    reviews.json 格式：{"键": {"final_verdict": "免费类", "final_group": "直接提交", "final_site_type": "导航与产品发布类",
                        "final_check": null, "final_reason": "依据", "reviewed_at": "时间"}}
    键可以是网站名（一条覆盖这个网站的所有页面；写了 www. 也认），也可以是来源页面网址（只管这个页面，优先于网站那条）
    旧 reviews.json 里的老分组值（邮箱注册后提交、自建内容这些）读的时候自动换成新的两个维度
    """
    path = run_dir / REVIEWS_FILE
    if not path.exists():
        return
    reviews = load_hand_edited_json(path)
    site_reviews = {bare_host(key): value for key, value in reviews.items() if '://' not in key}
    applied, no_group, no_type = 0, 0, 0
    for page in data.get('pages') or []:
        review, scope = reviews.get(page['url_from']), SCOPE_PAGE
        if not review:
            review, scope = site_reviews.get(bare_host(page['domain_from'])), SCOPE_SITE
        if not review:
            continue
        verdict = review.get('final_verdict')
        group, site_type = normalize_group(review.get('final_group'), review.get('final_site_type'))
        if verdict not in SETTLED_VERDICTS:
            logger.warning(f"人工结论不是 免费类/付费类/不可用 之一，跳过: {page['url_from']} → {verdict}")
            continue
        if group and (verdict != VERDICT_FREE or group not in FREE_GROUPS):
            logger.warning(f"发外链方式写错了（只有免费类有，可选: {'/'.join(FREE_GROUPS)}），跳过: "
                           f"{page['url_from']} → {verdict} {group}")
            continue
        if site_type and (verdict != VERDICT_FREE or site_type not in SITE_TYPES):
            logger.warning(f"业务类型写错了（只有免费类有，可选: {'/'.join(SITE_TYPES)}），跳过: "
                           f"{page['url_from']} → {verdict} {site_type}")
            continue
        if verdict == VERDICT_FREE and not group:
            no_group += 1
        if verdict == VERDICT_FREE and not site_type:
            no_type += 1
        page.update({key: review.get(key) for key in REVIEW_FIELDS})
        page['final_group'], page['final_site_type'] = group, site_type
        page['final_scope'] = scope
        applied += 1
    logger.info(f"人工复核结论 {len(reviews)} 条（按网站 {len(site_reviews)} 条），合并进 {applied} 个页面")
    if no_group:
        logger.warning(f"其中 {no_group} 条免费类结论没写发外链方式（final_group）")
    if no_type:
        logger.warning(f"其中 {no_type} 条免费类结论没写业务类型（final_site_type），第5步提交前要定")


def load_page_reviews(data_root: Path, exclude: Optional[Path] = None) -> Dict[str, dict]:
    """
    以前各结果目录 reviews.json 里用页面网址做键的人工复核结论，新查到同一页面时直接沿用
    只收页面键（外链网站名做键的整站结论已经并进外链库）；同一页面有多条时取复核时间最新的

    Args:
        data_root: data 根目录
        exclude: 不读的结果目录（当前这次的目录，它自己的 reviews.json 整理结果时另外合并）

    Returns:
        Dict[str, dict]: {页面网址: reviews.json 里的那条结论}
    """
    reviews = {}
    if not data_root.exists():
        return reviews
    skip = exclude.resolve() if exclude else None
    for run_dir in sorted(p for p in data_root.iterdir() if p.is_dir()):
        path = run_dir / REVIEWS_FILE
        if run_dir.resolve() == skip or not path.exists():
            continue
        for key, review in load_hand_edited_json(path).items():
            if '://' not in key or review.get('final_verdict') not in SETTLED_VERDICTS:
                continue
            old = reviews.get(key)
            if old is None or (review.get('reviewed_at') or '') > (old.get('reviewed_at') or ''):
                reviews[key] = review
    return reviews


def find_latest_run_dir(data_root: Path) -> Optional[Path]:
    """找最新一次有 results.json 的运行目录"""
    if not data_root.exists():
        return None
    run_dirs = [p for p in data_root.iterdir() if p.is_dir() and (p / RESULTS_FILE).exists()]
    return max(run_dirs, key=lambda p: p.name) if run_dirs else None
