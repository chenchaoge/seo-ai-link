"""沿用以前结论（同一页面的人工复核、库里的整站结论）和「重新判断」开关的离线测试：python -B test/test_reuse_old.py"""

import json
import logging
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from config import CHECK_CONFIG  # noqa: E402
from modules.result_store import load_page_reviews  # noqa: E402
from modules.usability_checker import UsabilityChecker  # noqa: E402

LOGGER = logging.getLogger('test')


def review(verdict, reviewed_at, reason='依据'):
    """造一条 reviews.json 里的结论"""
    return {'final_verdict': verdict, 'final_group': None, 'final_check': None, 'final_reason': reason,
            'reviewed_at': reviewed_at}


def backlink(url, domain):
    """造一条外链"""
    return {'url_from': url, 'domain_from': domain, 'rank': 10, 'domain_from_platform_type': []}


class TestLoadPageReviews(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, name, reviews):
        run_dir = self.root / name
        run_dir.mkdir()
        (run_dir / 'reviews.json').write_text(json.dumps(reviews, ensure_ascii=False), encoding='utf-8')
        return run_dir

    def test_only_page_keys_latest_wins_and_exclude(self):
        self.write('20261027_a', {'https://a.com/p': review('不可用', '2026-10-27 10:00:00', '旧'),
                                  'a.com': review('免费类', '2026-10-27 10:00:00'),  # 网站名键不收
                                  'https://b.com/p': review('无法判断', '2026-10-27 10:00:00')})  # 不是三大类不收
        self.write('20261028_b', {'https://a.com/p': review('付费类', '2026-10-28 10:00:00', '新')})
        current = self.write('20261029_c', {'https://c.com/p': review('不可用', '2026-10-29 10:00:00')})
        reviews = load_page_reviews(self.root, current)
        self.assertEqual(set(reviews), {'https://a.com/p'})
        self.assertEqual(reviews['https://a.com/p']['final_reason'], '新')

    def test_missing_root(self):
        self.assertEqual(load_page_reviews(self.root / '没有'), {})


class TestCarryPageReviews(unittest.TestCase):

    def setUp(self):
        self.checker = UsabilityChecker(CHECK_CONFIG, LOGGER, {})

    def test_old_page_review_carried_as_page_scope(self):
        pages = self.checker.build_pages([backlink('https://a.com/p', 'a.com'), backlink('https://a.com/q', 'a.com')],
                                         page_reviews={'https://a.com/p': review('不可用', '2026-10-27 10:00:00')})
        by_url = {p['url_from']: p for p in pages}
        self.assertEqual(by_url['https://a.com/p']['final_verdict'], '不可用')
        self.assertEqual(by_url['https://a.com/p']['final_scope'], '页面')
        self.assertIsNone(by_url['https://a.com/q']['final_verdict'])  # 同网站别的页面不沿用

    def test_own_review_beats_old_and_unreviewed_falls_back(self):
        old_pages = [{'url_from': 'https://a.com/p', 'final_verdict': '免费类', 'final_scope': '页面'},
                     {'url_from': 'https://a.com/q', 'final_verdict': None}]
        page_reviews = {'https://a.com/p': review('不可用', '2026-10-27 10:00:00'),
                        'https://a.com/q': review('付费类', '2026-10-27 10:00:00')}
        pages = self.checker.build_pages([backlink('https://a.com/p', 'a.com'), backlink('https://a.com/q', 'a.com')],
                                         old_pages, page_reviews)
        by_url = {p['url_from']: p for p in pages}
        self.assertEqual(by_url['https://a.com/p']['final_verdict'], '免费类')
        self.assertEqual(by_url['https://a.com/q']['final_verdict'], '付费类')


class TestReuseSwitch(unittest.TestCase):
    """库里有整站结论时默认直接用；重新判断时不用（github.com 是已知平台，不联网就能判）"""

    LIBRARY = {'github.com': {'site': 'github.com', 'verdict': '不可用', 'group': None, 'check': None, 'scope': '整站',
                              'reason': '库里的依据', 'source': '人工复核', 'checked_at': '2026-10-27'}}

    def check(self, reuse_old):
        checker = UsabilityChecker(CHECK_CONFIG, LOGGER, self.LIBRARY, reuse_old)
        page = checker.build_pages([backlink('https://github.com/x', 'github.com')])[0]
        checker.check_page(page, 'competitor-c.com')
        return page

    def test_default_uses_library(self):
        page = self.check(True)
        self.assertEqual(page['auto_verdict'], '不可用')
        self.assertTrue(page['auto_from_library'])

    def test_rejudge_ignores_library(self):
        page = self.check(False)
        self.assertEqual(page['auto_verdict'], '免费类')
        self.assertFalse(page['auto_from_library'])


if __name__ == '__main__':
    unittest.main()
