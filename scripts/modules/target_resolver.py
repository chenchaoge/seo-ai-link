"""
目标展开：用户输入页面网址时，先查这个页面，再查它所在的域名
域名 = 网址的主机名去掉 www.（在子域名上就查子域名，否则查主域名）
"""

from typing import List
from urllib.parse import urlsplit

from modules.link_signals import bare_host


def expand_targets(raw: str) -> List[str]:
    """
    把用户输入展开成要依次查询的目标列表

    Args:
        raw: 页面网址（如 https://competitor.com/lp/landing）或域名（如 competitor.com）

    Returns:
        List[str]: 页面网址 → [网址, 域名]；纯域名、首页网址（后面没有路径）→ [域名]，只查一次
    """
    value = raw.strip()
    url = value if '://' in value else 'https://' + value  # 漏写 https:// 的网址补上
    parts = urlsplit(url)
    if parts.path in ('', '/') and not parts.query and not parts.fragment:  # 纯域名、首页网址：只查域名，免得扣两次钱
        return [bare_host(url)]
    return [url, bare_host(url)]
