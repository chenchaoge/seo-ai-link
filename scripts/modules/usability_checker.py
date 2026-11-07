"""
外链页面自动预判模块：逐个打开外链所在页面，提取信号并分类
每判完一个页面立即写回 results.json（中途中断不丢已判结果）
礼貌抓取：同一网站两次请求之间留间隔（借鉴 claude-seo verify_backlinks.py 的 _polite_delay）
"""

import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from modules.classifier import (
    SCOPE_PAGE, SCOPE_SITE, SUBMIT_UNCHECKED, TYPE_BACKLINK, VERDICT_FREE, VERDICT_NO, Judgement,
    classify_fetch_failure, classify_page,
)
from modules.link_signals import (
    NOFOLLOW_TOKENS, analyze_submit_page, bare_host, extract_signals, has_spammy_tld, is_blocked,
    is_stat_site, match_known_platform,
)
from modules.result_store import CARRY_FIELDS, save_results
from modules.site_library import judge_by_library

# 每个待查页面从外链数据里带上的字段
PAGE_BACKLINK_FIELDS = [
    'url_to', 'anchor', 'dofollow', 'rank', 'domain_from_rank', 'page_from_rank',
    'domain_from_platform_type', 'page_from_external_links', 'page_from_title', 'semantic_location',
]


def page_backlink(b: Dict) -> Dict:
    """页面从外链数据里带上的字段；DataForSEO 的 dofollow 只认 nofollow，带 ugc、sponsored 的它也标 dofollow，这里改成 nofollow"""
    backlink = {key: b.get(key) for key in PAGE_BACKLINK_FIELDS}
    rel = {r.lower() for r in (b.get('attributes') or [])}
    if backlink['dofollow'] and rel & NOFOLLOW_TOKENS:
        backlink['dofollow'] = False
    return backlink


class UsabilityChecker:
    """外链页面可用性自动预判器"""

    def __init__(self, config: dict, logger: logging.Logger, library: Dict[str, dict], reuse_old: bool = True):
        """
        Args:
            config: CHECK_CONFIG
            logger: 日志记录器
            library: 完整外链库（site_library.load_libraries 的第一个结果）
            reuse_old: 用不用库里的整站结论；用户要求重新判断时为 False
        """
        self.config = config
        self.logger = logger
        self.library = library
        self.reuse_old = reuse_old
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config['user_agent'],
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self._last_request = {}

    def build_pages(self, backlinks: List[Dict], old_pages: Optional[List[Dict]] = None,
                    page_reviews: Optional[Dict[str, dict]] = None) -> List[Dict]:
        """
        从外链列表挑出要检查的页面：同一页面只查一次，同一网站按外链权重取前 N 个
        人工复核结论按页面网址带过来：old_pages（这个结果目录重判前的页面）优先，
        其次 page_reviews（以前别的结果目录里人工复核过的同一页面，result_store.load_page_reviews 的结果）

        Returns:
            List[Dict]: 待检查页面列表
        """
        max_per_domain = self.config.get('max_pages_per_domain', 3)
        domain_counts = Counter(bare_host(b.get('domain_from') or '') for b in backlinks)  # www. 和不带 www. 算同一个外链网站
        old_reviews = {url: dict(review, final_scope=SCOPE_PAGE) for url, review in (page_reviews or {}).items()}
        own = {p['url_from']: p for p in (old_pages or []) if p.get('final_verdict')}
        old_reviews.update(own)
        per_domain = Counter()
        seen = set()
        pages = []

        for b in sorted(backlinks, key=lambda x: x.get('rank') or 0, reverse=True):
            url, domain = b.get('url_from'), b.get('domain_from')
            site = bare_host(domain or '')
            if not url or url in seen or per_domain[site] >= max_per_domain:
                continue
            seen.add(url)
            per_domain[site] += 1
            page = {
                'url_from': url,
                'domain_from': domain,
                'domain_backlink_count': domain_counts[site],
                'backlink': page_backlink(b),
                'auto_verdict': None,
                'auto_group': None,
                'auto_site_type': None,
                'auto_check': None,
                'auto_scope': None,
                'auto_from_library': False,
                'auto_reasons': [],
                'signals': None,
                'http_status': None,
                'checked_at': None,
            }
            old = old_reviews.get(url, {})
            page.update({key: old.get(key) for key in CARRY_FIELDS})
            pages.append(page)

        self.logger.info(f"外链 {len(backlinks)} 条 → 外链网站 {len(domain_counts)} 个 → 待检查页面 {len(pages)} 个"
                         f"（每个网站最多 {max_per_domain} 个）")
        if page_reviews is not None:
            reused = sum(1 for p in pages if p['url_from'] in page_reviews and p['url_from'] not in own)
            self.logger.info(f"沿用以前结果目录里人工复核过的同一页面结论 {reused} 个（这些页面不用再复核）")
        return pages

    def run(self, run_dir: Path, data: dict, target: str, skip_checked: bool = False):
        """逐个检查 data['pages']，每查完一个就保存；skip_checked=True 时跳过已检查过的页面（接着查）"""
        pages = data['pages']
        todo = [p for p in pages if not (skip_checked and p.get('checked_at'))]
        if skip_checked:
            self.logger.info(f"已检查 {len(pages) - len(todo)} 个，接着查剩下的 {len(todo)} 个")
        for idx, page in enumerate(todo, 1):
            self.check_page(page, target)
            save_results(run_dir, data)
            self.logger.info(f"[{idx}/{len(todo)}] {page['auto_verdict']} | {page['url_from']} | "
                             f"{'；'.join(page['auto_reasons'])}")

    def check_page(self, page: Dict, target: str):
        """判断一个外链页面，结果写进 page"""
        url, domain = page['url_from'], page['domain_from']
        platform_types = page['backlink'].get('domain_from_platform_type') or []
        signals = None
        known = match_known_platform(domain)
        learned = judge_by_library(self.library, domain) if self.reuse_old else None

        if learned:  # 外链库里有整站结论的外链网站，直接用
            result = learned
        elif known:
            result = Judgement(VERDICT_FREE, [f"已知平台：{known['hint']}"], known['group'], known['check'], SCOPE_SITE,
                               known.get('site_type'))
        elif is_stat_site(domain):
            result = Judgement(VERDICT_NO, ['自动生成的"网站信息/估值"页，没法主动留链接'], scope=SCOPE_SITE)
        else:
            fetch = self.fetch(url)
            page['http_status'] = fetch['status']
            result = classify_fetch_failure(fetch)
            if result is None:
                signals = extract_signals(fetch['html'], fetch['final_url'], target)
                result = classify_page(signals, platform_types, url)
                if result.reasons == [SUBMIT_UNCHECKED] and self.config.get('follow_submit_page', True):
                    submit_page = self.check_submit_page(signals['submit_links'][0])
                    signals['submit_page'] = submit_page
                    result = classify_page(signals, platform_types, url, submit_page)

        page['auto_verdict'] = result.verdict
        page['auto_group'] = result.group
        page['auto_site_type'] = result.site_type
        page['auto_check'] = result.check
        page['auto_scope'] = result.scope
        page['auto_from_library'] = learned is not None
        page['auto_reasons'] = result.reasons + self._notes(page, signals, result.site_type)
        page['signals'] = signals
        page['checked_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def check_submit_page(self, submit_url: str) -> Dict:
        """打开提交页提取信号，打不开返回 {'error': 原因}"""
        fetch = self.fetch(submit_url)
        failure = classify_fetch_failure(fetch)
        if failure:
            return {'error': failure.reasons[0]}
        return analyze_submit_page(fetch['html'])

    def _notes(self, page: Dict, signals: Optional[Dict], site_type: Optional[str]) -> List[str]:
        """附加备注：竞品链接状态、疑似自建站、垃圾域名、要求互链（业务类型已是「要挂回链或徽章」的不重复写）"""
        notes = []
        if signals:
            link = signals['competitor_link']
            if not link['found'] and not signals['js_rendered']:
                notes.append('页面上已找不到竞品链接（可能已删除）')
            elif link['found'] and not link['dofollow']:
                notes.append('竞品链接是 nofollow')
            reciprocal = signals['reciprocal'] + (signals.get('submit_page') or {}).get('reciprocal', [])
            if reciprocal and site_type != TYPE_BACKLINK:
                notes.append(f"要求挂对方徽章/回链（{'、'.join(dict.fromkeys(reciprocal))}）")
        count = page['domain_backlink_count']
        if count >= self.config.get('owned_site_threshold', 10):
            notes.append(f'该网站给目标贡献了 {count} 条外链，疑似对方自己的站')
        if has_spammy_tld(page['domain_from']):
            notes.append('垃圾域名后缀')
        return notes

    def fetch(self, url: str) -> Dict:
        """
        打开网页，最多读 max_html_bytes

        Returns:
            Dict: status, final_url, html, is_html, blocked, error
        """
        result = {'status': None, 'final_url': url, 'html': '', 'is_html': False, 'blocked': False, 'error': None}
        self._polite_delay(bare_host(url))
        try:
            with self.session.get(url, timeout=self.config['timeout'], allow_redirects=True, stream=True) as resp:
                content = b''
                for chunk in resp.iter_content(65536):
                    content += chunk
                    if len(content) >= self.config['max_html_bytes']:
                        break
                result['status'] = resp.status_code
                result['final_url'] = resp.url
                content_type = (resp.headers.get('Content-Type') or '').lower()
                encoding = resp.encoding if resp.encoding and resp.encoding.lower() != 'iso-8859-1' else 'utf-8'
        except requests.exceptions.SSLError:
            result['error'] = 'SSL证书错误'
            return result
        except requests.exceptions.Timeout:
            result['error'] = '超时'
            return result
        except requests.exceptions.ConnectionError:
            result['error'] = '连不上'
            return result
        except requests.exceptions.RequestException as e:
            result['error'] = str(e)[:100]
            return result

        html = content.decode(encoding, errors='replace')
        result['html'] = html
        result['is_html'] = 'html' in content_type or 'xml' in content_type or html.lstrip()[:1] == '<'
        result['blocked'] = is_blocked(result['status'], html)
        return result

    def _polite_delay(self, domain: str):
        """同一网站两次请求之间至少间隔 domain_delay 秒"""
        delay = self.config.get('domain_delay', 1.0)
        last = self._last_request.get(domain)
        if last is not None:
            wait = delay - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[domain] = time.time()
