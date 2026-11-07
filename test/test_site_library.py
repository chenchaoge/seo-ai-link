"""外链库（两层）、竞品专属库、按外链网站复核的离线测试：python -B test/test_site_library.py"""

import json
import logging
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from config import CROSS_INDUSTRIES, DEFAULT_LIBRARY_FILES, INDUSTRIES, INDUSTRY_GROUPS  # noqa: E402
from modules.competitor_library import (  # noqa: E402
    HANDLING_NO, HANDLING_PAID, HANDLING_PENDING_REVIEW, HANDLING_TO_LEDGER, competitor_library_path,
    load_competitor_library, update_competitor_library,
)
from modules.result_store import apply_reviews  # noqa: E402
from modules.industry import (  # noqa: E402
    TRACK_CROSS, TRACK_NEAR, TRACK_OTHER, TRACK_SAME, TRACK_UNKNOWN, track_of,
)
from modules.site_library import (  # noqa: E402
    apply_industries, compare_with_library, judge_by_library, load_libraries, load_library, save_library,
    save_user_library, sync_library,
)

LOGGER = logging.getLogger('test')


def site_info(site, verdict, scope='整站', source='自动预判', evidence_at='2026-11-01', group=None, **extra):
    """造一条 rollup_by_site 的结果"""
    info = {'site': site, 'verdict': verdict, 'group': group, 'check': None, 'scope': scope, 'source': source,
            'from_library': False, 'evidence_at': evidence_at, 'reason': f'{verdict}的依据', 'entry_url': None,
            'page': f'https://{site}/p', 'page_count': 1, 'dofollow': True, 'domain_rank': 10}
    info.update(extra)
    return info


def entry(site, verdict, scope='整站', source='提交实测', checked_at='2026-10-24', group=None):
    """造一条库里的条目"""
    return {'site': site, 'verdict': verdict, 'industry': None, 'paid_option': None, 'group': group, 'site_type': None, 'scope': scope,
            'how': '人写的做法', 'entry_url': None, 'check': None, 'reason': '原来的依据', 'source': source,
            'checked_at': checked_at, 'first_seen': '2026-10-23', 'domain_rank': 5, 'dofollow': None}


class TestLibraryFiles(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.files = {'usable': self.tmp / 'usable.jsonl', 'unusable': self.tmp / 'unusable.jsonl'}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_real_library_is_valid(self):
        """SKILL 默认外链库的两个文件都能正常读，没有写错的行；每个外链网站都标了所属行业"""
        library = load_library(DEFAULT_LIBRARY_FILES)
        self.assertGreater(len(library), 0)
        self.assertEqual([site for site, e in library.items() if not e.get('industry')], [])

    def test_industry_must_be_in_list(self):
        """所属行业写了清单外的值直接报错"""
        bad = dict(entry('a.com', '付费类'), industry='不存在的行业')
        self.files['usable'].write_text(json.dumps(bad, ensure_ascii=False) + '\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_library(self.files)

    def test_apply_industries_and_sync_keeps_it(self):
        """industries.json 的行业写进库里已有的外链网站；之后同步新结论不会把行业清掉"""
        library = {'a.com': entry('a.com', '付费类', source='自动预判')}
        self.assertEqual(apply_industries(library, {'a.com': '游戏', 'not-in-library.com': '综合导航站'}), 1)
        sync_library(library, [site_info('a.com', '免费类', source='人工复核', group='直接提交')], '2026-11-02')
        self.assertEqual((library['a.com']['verdict'], library['a.com']['industry']), ('免费类', '游戏'))

    def test_user_library_overrides_default(self):
        """同一个外链网站两层都有时以用户外链库为准；改完只写用户外链库，没改过的默认条目不抄过去"""
        default_files = {'usable': self.tmp / 'd_usable.jsonl', 'unusable': self.tmp / 'd_unusable.jsonl'}
        save_library(default_files, {'a.com': entry('a.com', '付费类'), 'b.com': entry('b.com', '付费类'),
                                     'c.com': entry('c.com', '付费类')})
        save_library(self.files, {'a.com': entry('a.com', '不可用')})
        full, default, user_sites = load_libraries(default_files, self.files)
        self.assertEqual((full['a.com']['verdict'], full['b.com']['verdict']), ('不可用', '付费类'))
        full['b.com']['domain_rank'] = 50  # 默认外链库里的外链网站有了新事实
        full['d.com'] = entry('d.com', '免费类', group='直接提交')  # 新外链网站
        self.assertEqual(save_user_library(self.files, full, default, user_sites), 3)
        self.assertEqual(sorted(load_library(self.files)), ['a.com', 'b.com', 'd.com'])
        self.assertEqual(load_library(default_files)['b.com']['domain_rank'], 5)  # 默认外链库没被动

    def test_legacy_group_in_file_normalizes_on_load(self):
        """旧库文件里只有一个 group 字段：读出来自动拆成 group + site_type，再存回去就是新格式"""
        old_line = json.dumps(dict(entry('a.com', '免费类', group='自建内容'), site_type=None), ensure_ascii=False)
        self.files['usable'].write_text(old_line + '\n', encoding='utf-8')
        library = load_library(self.files)
        self.assertEqual((library['a.com']['group'], library['a.com']['site_type']), ('注册账号提交', '自建类'))
        save_library(self.files, library)
        self.assertIn('"site_type": "自建类"', self.files['usable'].read_text(encoding='utf-8'))

    def test_wrong_site_type_rejected(self):
        """业务类型写了不在四种里的值，或非免费类写了业务类型，读库时报错"""
        bad = dict(entry('a.com', '免费类', group='直接提交'), site_type='媒体类')
        self.files['usable'].write_text(json.dumps(bad, ensure_ascii=False) + '\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_library(self.files)

    def test_roundtrip_splits_by_verdict(self):
        library = {'a.com': entry('a.com', '免费类', group='直接提交'), 'b.com': entry('b.com', '付费类'),
                   'c.com': entry('c.com', '不可用')}
        save_library(self.files, library)
        self.assertEqual(len(self.files['usable'].read_text(encoding='utf-8').splitlines()), 2)
        self.assertEqual(len(self.files['unusable'].read_text(encoding='utf-8').splitlines()), 1)
        self.assertEqual(load_library(self.files), library)

    def test_wrong_file_or_value_raises(self):
        self.files['usable'].write_text(json.dumps(entry('c.com', '不可用'), ensure_ascii=False) + '\n',
                                        encoding='utf-8')
        with self.assertRaises(ValueError):
            load_library(self.files)
        bad = entry('a.com', '免费类')
        bad['scope'] = '全站'
        self.files['usable'].write_text(json.dumps(bad, ensure_ascii=False) + '\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_library(self.files)


class TestLibraryRules(unittest.TestCase):

    def test_judge_only_site_scope(self):
        """整站结论直接用；页面范围的不复用；只按完全相同的网站名（去掉 www.）匹配"""
        library = {'a.com': entry('a.com', '付费类'), 'b.com': entry('b.com', '不可用', scope='页面')}
        self.assertEqual(judge_by_library(library, 'www.a.com').verdict, '付费类')
        self.assertIsNone(judge_by_library(library, 'blog.a.com'))
        self.assertIsNone(judge_by_library(library, 'b.com'))

    def test_compare(self):
        library = {'a.com': entry('a.com', '付费类'), 'b.com': entry('b.com', '不可用', scope='页面'),
                   'c.com': dict(entry('c.com', '不可用'), first_seen='2026-11-01')}
        counts = compare_with_library(library, ['a.com', 'b.com', 'c.com', 'd.com'], '2026-11-01')
        self.assertEqual(counts, {'total': 4, 'seen': 2, 'seen_usable': 1, 'seen_unusable': 1, 'reusable': 1, 'new': 2})

    def test_sync_adds_new_and_skips_unknown(self):
        library = {}
        counts = sync_library(library, [site_info('a.com', '免费类', group='直接提交', entry_url='https://a.com/submit'),
                                        site_info('b.com', '无法判断', scope=None)], '2026-11-01')
        self.assertEqual(counts, {'added': 1, 'updated': 0, 'merged': 0})
        self.assertEqual(library['a.com']['first_seen'], '2026-11-01')
        self.assertEqual((library['a.com']['domain_rank'], library['a.com']['dofollow']), (10, True))
        self.assertIn('https://a.com/submit', library['a.com']['how'])
        self.assertNotIn('b.com', library)

    def test_sync_lower_source_does_not_override(self):
        """自动预判不覆盖提交实测，只补域名权重（取高的）和链接属性"""
        library = {'a.com': entry('a.com', '免费类', group='直接提交')}
        sync_library(library, [site_info('a.com', '付费类')], '2026-11-01')
        self.assertEqual(library['a.com']['verdict'], '免费类')
        self.assertEqual((library['a.com']['domain_rank'], library['a.com']['dofollow']), (10, True))
        sync_library(library, [site_info('a.com', '付费类', domain_rank=3, dofollow=False)], '2026-11-01')
        self.assertEqual((library['a.com']['domain_rank'], library['a.com']['dofollow']), (10, True))

    def test_sync_page_scope_does_not_override_site_scope(self):
        """某一页的人工结论不盖整站的事实"""
        library = {'a.com': entry('a.com', '免费类', source='自动预判', group='直接提交')}
        sync_library(library, [site_info('a.com', '不可用', scope='页面', source='人工复核')], '2026-11-01')
        self.assertEqual(library['a.com']['verdict'], '免费类')

    def test_sync_newer_same_source_replaces_and_moves(self):
        """同样可信、查看日期更新的结论替换旧的；变成不可用后去掉"怎么发\""""
        library = {'a.com': entry('a.com', '免费类', source='人工复核', group='直接提交')}
        counts = sync_library(library, [site_info('a.com', '不可用', source='人工复核')], '2026-11-01')
        self.assertEqual(counts['updated'], 1)
        self.assertEqual((library['a.com']['verdict'], library['a.com']['how']), ('不可用', None))
        self.assertEqual(library['a.com']['first_seen'], '2026-10-23')

    def test_sync_same_evidence_twice_changes_nothing(self):
        """同一份结果整理两次，核对日期不会被往后推"""
        library = {}
        info = site_info('a.com', '不可用', scope='页面', evidence_at='2026-11-01')
        sync_library(library, [info], '2026-11-01')
        counts = sync_library(library, [info], '2026-11-01')
        self.assertEqual(counts, {'added': 0, 'updated': 0, 'merged': 1})

    def test_sync_from_library_only_merges(self):
        library = {'a.com': entry('a.com', '付费类')}
        sync_library(library, [site_info('a.com', '付费类', from_library=True)], '2026-11-01')
        self.assertEqual(library['a.com']['checked_at'], '2026-10-24')
        self.assertEqual(library['a.com']['domain_rank'], 10)


class TestIndustryTrack(unittest.TestCase):
    """赛道关系：同赛道 > 相近赛道（同一个赛道大类）> 不分行业（综合导航站、综合论坛博客）> 其他赛道"""

    def test_tracks(self):
        self.assertEqual(track_of('AI产品工具', 'AI产品工具'), TRACK_SAME)
        self.assertEqual(track_of('AI产品工具', '计算机、电子与科技'), TRACK_NEAR)
        self.assertEqual(track_of('AI产品工具', '综合导航站'), TRACK_CROSS)
        self.assertEqual(track_of('AI产品工具', '综合论坛博客'), TRACK_CROSS)
        self.assertEqual(track_of('AI产品工具', '宠物与动物'), TRACK_OTHER)
        self.assertEqual(track_of('综合导航站', '综合导航站'), TRACK_SAME)
        self.assertEqual(track_of(None, '游戏'), TRACK_UNKNOWN)
        self.assertEqual(track_of('游戏', None), TRACK_UNKNOWN)

    def test_every_industry_in_one_group(self):
        """每个行业只属于一个赛道大类，综合导航站、综合论坛博客不进大类"""
        grouped = [i for industries in INDUSTRY_GROUPS.values() for i in industries]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(sorted(grouped + CROSS_INDUSTRIES), sorted(INDUSTRIES))
        self.assertEqual(len(INDUSTRIES), 26)


class TestCompetitorLibrary(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = competitor_library_path(self.tmp / '20261101_120000_x.com')  # 放在那一批的分析结果目录里
        self.data = {'target': 'x.com', 'created_at': '2026-11-01 12:00:00', 'fetch': {'total_count': 9},
                     'backlinks': [{}, {}], 'pages': [{}, {}, {}]}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_default_handling_and_ledger_sync(self):
        sites = [site_info('a.com', '免费类', group='直接提交'), site_info('b.com', '不可用'),
                 site_info('c.com', '无法判断', scope=None), site_info('d.com', '免费类', group='直接提交')]
        ledger = {'a.com': {'status': '已提交'}}
        counts = update_competitor_library(self.path, self.data, sites, {'b.com'}, ledger, 'ours.com', {}, None)
        self.assertEqual(self.path.name, 'competitor_library.json')
        lib = load_competitor_library(self.path)
        self.assertEqual(lib['batch']['batch_at'], '2026-11-01 12:00:00')
        self.assertNotIn('run_dir', lib['batch'])  # 文件就在分析结果目录里，不存绝对路径
        self.assertEqual(lib['batch']['sites'], 4)
        self.assertEqual(lib['sites']['a.com']['handling'], '台账：已提交')
        self.assertEqual(lib['sites']['b.com']['handling'], HANDLING_NO)
        self.assertTrue(lib['sites']['b.com']['seen_before'])
        self.assertEqual(lib['sites']['c.com']['handling'], HANDLING_PENDING_REVIEW)
        self.assertEqual(lib['sites']['d.com']['handling'], HANDLING_TO_LEDGER)
        self.assertEqual(counts['open'], 2)

    def test_paid_decision_comes_from_ledger(self):
        """处理方式全由脚本算：付费类没进台账就是先问用户，用户的决定记进台账后跟着台账状态变；手改的会被刷新掉"""
        sites = [site_info('a.com', '免费类', group='直接提交'), site_info('b.com', '付费类')]
        update_competitor_library(self.path, self.data, sites, set(), {'a.com': {'status': '已提交'}}, 'o', {}, None)
        lib = load_competitor_library(self.path)
        self.assertEqual(lib['sites']['b.com']['handling'], HANDLING_PAID)
        first_at = lib['sites']['a.com']['handled_at']
        lib['sites']['b.com']['handling'] = '手改的'
        self.path.write_text(json.dumps(lib, ensure_ascii=False), encoding='utf-8')
        ledger = {'a.com': {'status': '已提交'}, 'b.com': {'status': '跳过', 'note': '付费，用户决定不做'}}
        update_competitor_library(self.path, self.data, sites, set(), ledger, 'o', {}, None)
        lib = load_competitor_library(self.path)
        self.assertEqual(lib['sites']['b.com']['handling'], '台账：跳过')
        self.assertEqual(lib['sites']['a.com']['handled_at'], first_at)  # 处理方式没变，时间不动


class TestSiteReviews(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_site_key_is_site_scope_page_key_wins(self):
        """reviews.json 用网站名当键覆盖整站（整站范围），单独写的页面那条优先（页面范围）"""
        reviews = {
            'a.com': {'final_verdict': '免费类', 'final_group': '直接提交', 'final_check': None,
                      'final_reason': '整站', 'reviewed_at': '2026-10-24 10:00:00'},
            'https://a.com/2': {'final_verdict': '不可用', 'final_group': None, 'final_check': None,
                                'final_reason': '这一页', 'reviewed_at': '2026-10-24 10:00:00'},
        }
        (self.tmp / 'reviews.json').write_text(json.dumps(reviews, ensure_ascii=False), encoding='utf-8')
        data = {'pages': [{'url_from': 'https://www.a.com/1', 'domain_from': 'www.a.com'},
                          {'url_from': 'https://a.com/2', 'domain_from': 'a.com'},
                          {'url_from': 'https://b.com/1', 'domain_from': 'b.com'}]}
        apply_reviews(self.tmp, data, LOGGER)
        pages = data['pages']
        self.assertEqual((pages[0]['final_verdict'], pages[0]['final_scope']), ('免费类', '整站'))
        self.assertEqual((pages[1]['final_verdict'], pages[1]['final_scope']), ('不可用', '页面'))
        self.assertNotIn('final_verdict', pages[2])

    def test_wrong_group_skipped(self):
        reviews = {'a.com': {'final_verdict': '付费类', 'final_group': '直接提交'}}
        (self.tmp / 'reviews.json').write_text(json.dumps(reviews, ensure_ascii=False), encoding='utf-8')
        data = {'pages': [{'url_from': 'https://a.com/1', 'domain_from': 'a.com'}]}
        apply_reviews(self.tmp, data, LOGGER)
        self.assertNotIn('final_verdict', data['pages'][0])


if __name__ == '__main__':
    unittest.main()
