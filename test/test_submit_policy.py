"""发外链原则：分档、先后顺序、每天成功提交上限。离线测试：python -B test/test_submit_policy.py"""

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from config import DAILY_SUBMIT_LIMIT  # noqa: E402
from modules.submit_policy import (  # noqa: E402
    TIER_1, TIER_2, TIER_3, TIER_4, TIER_5, TIER_UNKNOWN, daily_quota, priority_order, stale_pending, submit_queue,
    tier_of,
)

SITE_INDUSTRY = 'AI产品工具'


def lib(verdict, industry, dofollow, rank):
    """造一个最小的外链库条目"""
    return {'verdict': verdict, 'industry': industry, 'dofollow': dofollow, 'domain_rank': rank}


class TestTier(unittest.TestCase):
    def test_tiers(self):
        """契合赛道 + 免费 + dofollow 第1档；其他赛道 dofollow 第2档；契合赛道 nofollow 或没记录第3档；
        其他赛道 nofollow 或没记录第4档；付费第5档；行业未标先补；不可用不发"""
        cases = [
            (('同赛道', '免费类', True), TIER_1),
            (('不分行业', '免费类', True), TIER_1),
            (('其他赛道', '免费类', True), TIER_2),
            (('相近赛道', '免费类', None), TIER_3),
            (('同赛道', '免费类', False), TIER_3),
            (('其他赛道', '免费类', None), TIER_4),
            (('同赛道', '付费类', True), TIER_5),
            (('行业未标', '免费类', True), TIER_UNKNOWN),
            (('同赛道', '不可用', True), None),
        ]
        for args, tier in cases:
            self.assertEqual(tier_of(*args), tier, args)


class TestQueue(unittest.TestCase):
    def setUp(self):
        self.library = {
            'a.com': lib('免费类', 'AI产品工具', True, 10),
            'b.com': lib('免费类', '计算机、电子与科技', True, 50),
            'c.com': lib('免费类', 'AI产品工具', None, 90),
            'd.com': lib('免费类', 'AI产品工具', False, 95),
            'e.com': lib('免费类', '游戏', True, 5),
            'f.com': lib('免费类', '游戏', False, 80),
            'g.com': lib('付费类', 'AI产品工具', True, 99),
            'h.com': lib('免费类', 'AI产品工具', True, 100),
            'i.com': lib('不可用', 'AI产品工具', True, 100),
        }
        self.ledger = {site: {'status': '待提交'} for site in self.library}
        self.ledger['h.com']['status'] = '已提交'

    def test_order(self):
        """先第1档（同赛道再相近赛道）；剩下的 dofollow 先于 nofollow：其他赛道 dofollow 排在契合赛道 nofollow 前面；
        契合赛道 nofollow 里没记录的在前；付费最后；已提交的、外链库判不可用的不排"""
        queue = submit_queue(self.ledger, self.library, SITE_INDUSTRY)
        self.assertEqual([q['site'] for q in queue], ['a.com', 'b.com', 'e.com', 'c.com', 'd.com', 'f.com', 'g.com'])
        self.assertEqual([q['tier'] for q in queue], [TIER_1, TIER_1, TIER_2, TIER_3, TIER_3, TIER_4, TIER_5])

    def test_other_track_and_paid_need_confirm(self):
        """其他赛道的、付费的要先问用户；台账写了 user_confirmed: true 就不用再问"""
        self.ledger['e.com']['user_confirmed'] = True
        flags = {q['site']: q['needs_confirm'] for q in submit_queue(self.ledger, self.library, SITE_INDUSTRY)}
        self.assertEqual([site for site, flag in flags.items() if flag], ['f.com', 'g.com'])
        self.ledger['g.com']['user_confirmed'] = True
        flags = {q['site']: q['needs_confirm'] for q in submit_queue(self.ledger, self.library, SITE_INDUSTRY)}
        self.assertEqual([site for site, flag in flags.items() if flag], ['f.com'])

    def test_stale_pending(self):
        """台账待提交、但外链库判成不可用或没写结论的，单独列出来；已提交的、能发的不列"""
        self.ledger['j.com'] = {'status': '待提交'}  # 外链库没有、台账也没写结论
        self.ledger['i.com']['status'] = '待提交'
        stale = stale_pending(self.ledger, self.library)
        self.assertEqual(stale, [{'site': 'i.com', 'verdict': '不可用'}, {'site': 'j.com', 'verdict': None}])
        self.ledger['i.com']['status'] = '跳过'
        self.assertEqual([s['site'] for s in stale_pending(self.ledger, self.library)], ['j.com'])

    def test_same_tier_by_rank(self):
        """同一档、同赛道关系、同链接属性的按权重从高到低"""
        self.library['b.com']['industry'] = 'AI产品工具'
        queue = submit_queue(self.ledger, self.library, SITE_INDUSTRY)
        self.assertEqual([q['site'] for q in queue][:2], ['b.com', 'a.com'])

    def test_order_number_matches_queue(self):
        """报告用的排序值跟程序排的先后一致"""
        queue = submit_queue(self.ledger, self.library, SITE_INDUSTRY)
        orders = [priority_order(q) for q in queue]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(set(orders)), len(orders))

    def test_industry_from_ledger_when_library_missing(self):
        """外链库里没有的外链网站，行业和结论用台账里的；没有链接属性和权重"""
        ledger = {'x.com': {'status': '待提交', 'verdict': '免费类', 'industry': '游戏'}}
        queue = submit_queue(ledger, {}, SITE_INDUSTRY)
        self.assertEqual((queue[0]['tier'], queue[0]['track'], queue[0]['dofollow']), (TIER_4, '其他赛道', None))


class TestDailyQuota(unittest.TestCase):
    def test_quota(self):
        """当天 submitted_at 的才算今天成功提交的；满了还能发 0 个"""
        ledger = {f's{i}.com': {'submitted_at': '2026-11-06 10:00:00'} for i in range(3)}
        ledger.update({f'y{i}.com': {'submitted_at': '2026-11-05 23:59:00'} for i in range(2)})
        ledger['skip.com'] = {'status': '跳过', 'submitted_at': None}
        self.assertEqual(daily_quota(ledger, '2026-11-06'),
                         {'day': '2026-11-06', 'submitted': 3, 'limit': DAILY_SUBMIT_LIMIT,
                          'left': DAILY_SUBMIT_LIMIT - 3})
        full = {f's{i}.com': {'submitted_at': '2026-11-06 10:00:00'} for i in range(DAILY_SUBMIT_LIMIT + 2)}
        self.assertEqual(daily_quota(full, '2026-11-06')['left'], 0)

    def test_limit_is_ten(self):
        self.assertEqual(DAILY_SUBMIT_LIMIT, 10)


if __name__ == '__main__':
    unittest.main()
