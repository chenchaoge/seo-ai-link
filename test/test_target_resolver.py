"""目标展开规则离线测试：python -B test/test_target_resolver.py"""

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from modules.target_resolver import expand_targets  # noqa: E402


class TestExpandTargets(unittest.TestCase):

    def test_page_on_main_domain(self):
        self.assertEqual(expand_targets('https://competitor.com/lp/landing'),
                         ['https://competitor.com/lp/landing', 'competitor.com'])

    def test_page_on_www(self):
        self.assertEqual(expand_targets('https://www.competitor.com/lp/landing'),
                         ['https://www.competitor.com/lp/landing', 'competitor.com'])

    def test_page_on_subdomain(self):
        self.assertEqual(expand_targets('https://blog.competitor.com/post/1'),
                         ['https://blog.competitor.com/post/1', 'blog.competitor.com'])

    def test_page_without_scheme(self):
        self.assertEqual(expand_targets('competitor.com/lp/landing'),
                         ['https://competitor.com/lp/landing', 'competitor.com'])

    def test_bare_domain(self):
        self.assertEqual(expand_targets('competitor.com'), ['competitor.com'])

    def test_bare_www_domain(self):
        self.assertEqual(expand_targets(' WWW.Competitor.com '), ['competitor.com'])

    def test_bare_subdomain(self):
        self.assertEqual(expand_targets('blog.competitor.com'), ['blog.competitor.com'])

    def test_homepage_counts_as_domain(self):
        """首页网址（后面没有路径）按域名算，只查一次，不扣两次钱"""
        for raw in ('https://competitor.com', 'https://www.competitor.com/', 'competitor.com/'):
            self.assertEqual(expand_targets(raw), ['competitor.com'], raw)

    def test_homepage_with_query_is_page(self):
        self.assertEqual(expand_targets('https://competitor.com/?ref=x'), ['https://competitor.com/?ref=x', 'competitor.com'])


if __name__ == '__main__':
    unittest.main()
