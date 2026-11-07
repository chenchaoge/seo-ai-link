"""
外链拉取模块
使用 DataForSEO Backlinks API（/v3/backlinks/backlinks/live）拉目标页面/网站的外链明细
每页原始响应立即落盘到分析结果目录的 raw/，再解析
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from lib.client import RestClient

# 每条外链保留的字段（DataForSEO 原始字段名）
KEEP_FIELDS = [
    'url_from', 'domain_from', 'url_to', 'anchor', 'dofollow', 'attributes', 'item_type',
    'rank', 'page_from_rank', 'domain_from_rank', 'domain_from_platform_type',
    'page_from_external_links', 'page_from_title', 'page_from_language', 'page_from_status_code',
    'semantic_location', 'text_pre', 'text_post', 'links_count', 'backlink_spam_score',
    'first_seen', 'last_seen', 'is_lost',
]


class BacklinkFetcher:
    """外链明细拉取器"""

    API_ENDPOINT = '/v3/backlinks/backlinks/live'
    PAGE_LIMIT = 1000  # 接口单页上限

    def __init__(self, username: str, password: str, logger: logging.Logger):
        """
        Args:
            username: DataForSEO API 用户名
            password: DataForSEO API 密码
            logger: 日志记录器
        """
        self.client = RestClient(username, password)
        self.logger = logger

    def fetch(self, target: str, config: dict, raw_dir: Path) -> Dict:
        """
        按权重从高到低翻页拉外链，直到拉完或达到 max_backlinks

        Args:
            target: 目标网址（带 https:// 只查该页面）或域名
            config: BACKLINKS_CONFIG
            raw_dir: 原始响应保存目录

        Returns:
            Dict: {'items': 外链列表, 'total_count': 接口报告的总数, 'cost': 总费用, 'error': 错误信息或None}
        """
        max_backlinks = config.get('max_backlinks', 1000)
        items: List[Dict] = []
        total_count = None
        total_cost = 0.0
        error = None
        page_no = 0

        while len(items) < max_backlinks:
            page_no += 1
            limit = min(self.PAGE_LIMIT, max_backlinks - len(items))
            payload = [{
                'target': target,
                'mode': 'as_is',
                'limit': limit,
                'offset': len(items),
                'order_by': ['rank,desc'],
                'backlinks_status_type': config.get('backlinks_status_type', 'live'),
                'rank_scale': config.get('rank_scale', 'one_hundred'),
            }]
            result, cost, error = self._post(payload, raw_dir / f"backlinks_page{page_no}.json")
            if cost is not None:
                total_cost += cost
            if error:
                break

            if total_count is None:
                total_count = result.get('total_count')
                self.logger.info(f"目标共有 {total_count} 条外链（最多拉 {max_backlinks} 条）")
            page_items = result.get('items') or []
            items.extend({key: raw.get(key) for key in KEEP_FIELDS} for raw in page_items)
            self.logger.info(f"第 {page_no} 页拿到 {len(page_items)} 条，累计 {len(items)} 条")

            if not page_items or len(page_items) < limit:
                break
            if total_count is not None and len(items) >= total_count:
                break
            time.sleep(config.get('request_interval', 1))

        self.logger.info(f"外链拉取结束：{len(items)} 条，费用 ${total_cost:.4f}")
        return {'items': items, 'total_count': total_count, 'cost': round(total_cost, 6), 'error': error}

    def _post(self, payload: list, raw_file: Path) -> tuple:
        """
        发请求、原始响应立即落盘、检查状态

        Returns:
            tuple: (task.result[0], 费用, 错误信息)；失败时 result 为 None
        """
        try:
            response = self.client.post(self.API_ENDPOINT, payload)
        except Exception as e:
            self.logger.error(f"DataForSEO 请求失败: {e}")
            return None, None, str(e)

        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=2)

        tasks = response.get('tasks') or []
        task = tasks[0] if tasks else {}
        status_code = task.get('status_code', response.get('status_code'))
        status_message = task.get('status_message', response.get('status_message'))
        cost: Optional[float] = task.get('cost')
        if status_code != 20000:
            self.logger.error(f"DataForSEO 任务状态异常: code={status_code}, msg={status_message}")
            return None, cost, f"code={status_code}, {status_message}"
        result_list = task.get('result') or []
        if not result_list:
            return None, cost, "result为空"
        return result_list[0], cost, None
