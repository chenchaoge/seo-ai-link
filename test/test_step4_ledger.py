"""第4步收尾：整理结果时把免费类外链网站导入当前独立站的提交台账。离线测试：python -B test/test_step4_ledger.py"""

import json
import logging
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import main  # noqa: E402
from modules.competitor_library import competitor_library_path, load_competitor_library  # noqa: E402
from modules.industry import industries_path  # noqa: E402
from modules.site_library import load_library  # noqa: E402
from modules.submission_ledger import load_ledger, save_ledger  # noqa: E402
from modules.user_space import UserSpace, create_site  # noqa: E402

QUIET = logging.getLogger('test_step4')
QUIET.addHandler(logging.NullHandler())


def make_page(url, domain, auto_verdict, final_verdict=None, submit_links=None, auto_group=None,
              final_group=None):
    """造一个最小的页面结果"""
    page = {'url_from': url, 'domain_from': domain, 'auto_verdict': auto_verdict, 'auto_group': auto_group,
            'auto_check': None, 'auto_reasons': ['自动依据'], 'final_verdict': final_verdict,
            'final_group': final_group, 'final_check': None, 'final_reason': None}
    if submit_links is not None:
        page['signals'] = {'submit_links': submit_links}
    return page


class TestAddFreeToLedger(unittest.TestCase):
    """add_free_to_ledger 是第4步整理结果的收尾动作（原菜单 5 已并进整理结果）"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.space = UserSpace(self.tmp)  # 临时用户目录，不碰真的用户目录位置文件
        self.space.save_settings({'current_site': 'ours.com'})

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _ledger(self):
        return load_ledger(self.space.ledger_path('ours.com'))

    def _add(self, data, industries=None):
        """整理结果里进台账的那一步：当前独立站从 settings.json 读"""
        return main.add_free_to_ledger(self.space, self.space.current_site(), data, industries or {}, QUIET)

    def test_free_sites_land_in_ledger_as_pending_with_known_info(self):
        """整理结果后免费类外链网站进当前独立站的台账（data/sites/<独立站>/ledger.json），默认待提交，带上已知的入口和分组；非免费的不进"""
        data = {'target': 'competitor-b.com', 'pages': [
            make_page('https://a.com/1', 'a.com', '免费类', submit_links=['https://a.com/submit'],
                      auto_group='直接提交'),
            make_page('https://b.com/1', 'b.com', '无法判断', final_verdict='免费类', final_group='邮箱注册后提交'),
            make_page('https://c.com/1', 'c.com', '不可用'),
            make_page('https://d.com/1', 'd.com', '付费类'),
        ]}
        self._add(data)
        self.assertTrue((self.tmp / 'data' / 'sites' / 'ours.com' / 'ledger.json').exists())
        ledger = self._ledger()
        self.assertEqual(sorted(ledger), ['a.com', 'b.com'])  # 只进免费类
        self.assertEqual(ledger['a.com']['status'], '待提交')
        self.assertEqual(ledger['a.com']['submit_url'], 'https://a.com/submit')
        self.assertEqual(ledger['a.com']['group'], '直接提交')
        self.assertEqual(ledger['b.com']['group'], '注册账号提交')  # 人工写的旧分组值导入时换成新的
        self.assertIn('site_type', ledger['a.com'])

    def test_second_export_keeps_status_only_adds(self):
        """再整理一次（或并新一批）：已有外链网站不改状态，只补来源，新的免费类外链网站才新增"""
        self._add({'target': 'competitor-b.com', 'pages': [make_page('https://a.com/1', 'a.com', '免费类')]})
        path = self.space.ledger_path('ours.com')
        ledger = load_ledger(path)
        ledger['a.com']['status'] = '已提交'
        save_ledger(path, ledger)
        self._add({'target': 'other.com', 'pages': [
            make_page('https://a.com/1', 'a.com', '免费类'),
            make_page('https://e.com/1', 'e.com', '免费类')]})
        ledger = self._ledger()
        self.assertEqual(ledger['a.com']['status'], '已提交')  # 状态不动
        self.assertIn('other.com', ledger['a.com']['sources'])  # 补了来源
        self.assertEqual(ledger['e.com']['status'], '待提交')  # 新外链网站进来

    def test_no_current_site_writes_nothing(self):
        """settings.json 没写当前独立站：不建任何台账"""
        self.space.save_settings({})
        ledger = self._add({'target': 'x.com', 'pages': [make_page('https://a.com/1', 'a.com', '免费类')]})
        self.assertEqual(ledger, {})
        self.assertFalse(self.space.sites_dir.exists())

    def test_ledger_industry_follows_library(self):
        """台账每行的所属行业跟外链库同步：新加的带上，已有的也补上；外链库没标的不清掉台账里已有的"""
        self._add({'target': 'x.com', 'pages': [make_page('https://a.com/1', 'a.com', '免费类'),
                                                make_page('https://b.com/1', 'b.com', '免费类')]})
        path = self.space.ledger_path('ours.com')
        ledger = load_ledger(path)
        ledger['b.com']['industry'] = '综合导航站'
        save_ledger(path, ledger)
        self._add({'target': 'x.com', 'pages': [make_page('https://c.com/1', 'c.com', '免费类')]},
                  {'a.com': 'AI产品工具', 'c.com': '游戏'})
        ledger = self._ledger()
        self.assertEqual((ledger['a.com']['industry'], ledger['b.com']['industry'], ledger['c.com']['industry']),
                         ('AI产品工具', '综合导航站', '游戏'))

    def test_no_site_industry_warns(self):
        """独立站档案没标所属行业：提醒补上，算不出赛道关系，发外链顺序排不了"""
        ledger = self._add({'target': 'x.com', 'pages': [make_page('https://a.com/1', 'a.com', '免费类')]})
        with self.assertLogs(QUIET, level='WARNING') as logs:
            main.log_submit_plan(ledger, {}, 'ours.com', None, QUIET)
        self.assertIn('还没标所属行业', '\n'.join(logs.output))

    def test_menu_5_removed(self):
        """旧的单独加台账菜单已并进整理结果，不再存在；Excel 导出也去掉了"""
        self.assertFalse(hasattr(main, 'run_add_to_ledger'))
        self.assertFalse(hasattr(main, 'export_xlsx'))


class TestOrganizeIndustry(unittest.TestCase):
    """整理结果时：industries.json 判的行业并进用户外链库、台账和竞品专属库，还没标的列出来给 AI 判"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.space = UserSpace(self.tmp)
        profile_path = create_site(self.space, 'ours.com')  # 第一个独立站自动设成当前独立站
        profile = json.loads(profile_path.read_text(encoding='utf-8'))
        profile['industry'] = 'AI产品工具'
        profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
        self.run_dir = self.space.analyses_dir / '20261106_100000_x.com'
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_industries_flow(self):
        data = {'target': 'x.com', 'created_at': '2026-11-06 10:00:00', 'backlinks': [], 'pages': [
            make_page('https://new-ai.example/1', 'www.new-ai.example', '免费类'),
            make_page('https://new-game.example/1', 'new-game.example', '免费类'),
            make_page('https://unknown.example/1', 'unknown.example', '无法判断'),
            make_page('https://other.example/1', 'other.example', '付费类')]}
        data['pages'][1]['backlink'] = {'page_from_title': 'Best   Games'}
        industries_path(self.run_dir).write_text(json.dumps(
            {'www.new-ai.example': 'AI产品工具', 'unknown.example': '综合导航站', 'other.example': '游戏',
             'bad.example': '不存在的行业'}, ensure_ascii=False), encoding='utf-8')
        with self.assertLogs(QUIET, level='INFO') as logs:
            main.organize_results(self.space, self.run_dir, data, QUIET)
        library = load_library(self.space.library_files)
        self.assertEqual(library['new-ai.example']['industry'], 'AI产品工具')
        self.assertIsNone(library['new-game.example']['industry'])
        self.assertNotIn('unknown.example', library)  # 无法判断的不进库，行业先留在 industries.json
        self.assertEqual(self._ledger()['new-ai.example']['industry'], 'AI产品工具')
        comp = load_competitor_library(competitor_library_path(self.run_dir))
        self.assertEqual(comp['batch']['independent_site_industry'], 'AI产品工具')
        tracks = {site: comp['sites'][site]['track'] for site in comp['sites']}
        self.assertEqual(tracks, {'new-ai.example': '同赛道', 'new-game.example': '行业未标',
                                  'unknown.example': '不分行业', 'other.example': '其他赛道'})
        text = '\n'.join(logs.output)
        self.assertIn('不存在的行业', text)  # 不在清单里的报警告
        self.assertIn('按发外链原则：第3档 1，先补行业 1', text)  # 同赛道、链接属性没记录 → 第3档；行业没标 → 先补行业
        self.assertIn('每天最多 10 个，还能发 10 个', text)
        self.assertIn('所属行业还没标的外链网站 1 个', text)
        self.assertIn('new-game.example | 免费类 | Best Games', text)  # 带上页面标题给 AI 判

    def _ledger(self):
        return load_ledger(self.space.ledger_path('ours.com'))


if __name__ == '__main__':
    unittest.main()
