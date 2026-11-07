"""提交台账离线测试：python -B test/test_submission_ledger.py"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from modules.submission_ledger import load_ledger, merge_into_ledger, recheck_due, save_ledger  # noqa: E402


def make_page(url, domain, auto_verdict, final_verdict=None, submit_links=None, auto_group=None,
              final_group=None):
    """造一个最小的页面结果"""
    page = {'url_from': url, 'domain_from': domain, 'auto_verdict': auto_verdict, 'auto_group': auto_group,
            'auto_check': None, 'auto_reasons': ['自动依据'], 'final_verdict': final_verdict,
            'final_group': final_group, 'final_check': None, 'final_reason': None}
    if submit_links is not None:
        page['signals'] = {'submit_links': submit_links}
    return page


class TestMergeIntoLedger(unittest.TestCase):

    def test_only_free_verdicts_added(self):
        pages = [make_page('https://a.com/1', 'a.com', '免费类', submit_links=['https://a.com/submit'],
                           auto_group='直接提交'),
                 make_page('https://b.com/1', 'b.com', '不可用'),
                 make_page('https://c.com/1', 'c.com', '无法判断', final_verdict='免费类', final_group='邮箱注册后提交'),
                 make_page('https://d.com/1', 'd.com', '无法判断'),
                 make_page('https://e.com/1', 'e.com', '付费类')]
        ledger = {}
        counts = merge_into_ledger(ledger, pages, 'competitor.com')
        self.assertEqual(sorted(ledger), ['a.com', 'c.com'])
        self.assertEqual(counts, {'added': 2, 'updated': 0})
        self.assertEqual(ledger['a.com']['status'], '待提交')
        self.assertEqual(ledger['a.com']['submit_url'], 'https://a.com/submit')
        self.assertEqual(ledger['a.com']['group'], '直接提交')
        self.assertEqual(ledger['c.com']['verdict'], '免费类')
        self.assertEqual(ledger['c.com']['group'], '注册账号提交')  # 旧分组值换成新的
        self.assertIsNone(ledger['c.com']['site_type'])  # 没写业务类型就留空，第5步再定
        self.assertIsNone(ledger['c.com']['submit_url'])
        self.assertIsNone(ledger['c.com']['checked_at'])

    def test_same_site_merged_and_www_stripped(self):
        pages = [make_page('https://www.a.com/1', 'www.a.com', '免费类'),
                 make_page('https://a.com/2', 'a.com', '免费类')]
        ledger = {}
        counts = merge_into_ledger(ledger, pages, 'competitor.com')
        self.assertEqual(list(ledger), ['a.com'])
        self.assertEqual(ledger['a.com']['source_pages'], ['https://www.a.com/1', 'https://a.com/2'])
        self.assertEqual(counts, {'added': 1, 'updated': 0})

    def test_existing_entry_keeps_status(self):
        ledger = {}
        merge_into_ledger(ledger, [make_page('https://a.com/1', 'a.com', '免费类')], 'competitor.com')
        ledger['a.com'].update({'status': '已提交', 'note': '人工记录'})
        counts = merge_into_ledger(ledger, [make_page('https://a.com/1', 'a.com', '免费类'),
                                            make_page('https://a.com/9', 'a.com', '免费类')], 'other.com')
        self.assertEqual(ledger['a.com']['status'], '已提交')
        self.assertEqual(ledger['a.com']['note'], '人工记录')
        self.assertEqual(ledger['a.com']['source_pages'], ['https://a.com/1', 'https://a.com/9'])
        self.assertEqual(ledger['a.com']['sources'], ['competitor.com', 'other.com'])
        self.assertEqual(counts, {'added': 0, 'updated': 1})

    def test_rerun_same_results_changes_nothing(self):
        pages = [make_page('https://a.com/1', 'a.com', '免费类')]
        ledger = {}
        merge_into_ledger(ledger, pages, 'competitor.com')
        self.assertEqual(merge_into_ledger(ledger, pages, 'competitor.com'), {'added': 0, 'updated': 0})


class TestSaveLoad(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_one_site_per_line_roundtrip(self):
        ledger = {}
        merge_into_ledger(ledger, [make_page('https://a.com/1', 'a.com', '免费类'),
                                   make_page('https://b.com/1', 'b.com', '免费类')], 'competitor.com')
        path = self.tmp / 'sub' / 'site.json'
        save_ledger(path, ledger)
        self.assertEqual(load_ledger(path), ledger)
        lines = path.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), 4)  # { + 两个网站 + }

    def test_missing_file_is_empty(self):
        self.assertEqual(load_ledger(self.tmp / 'none.json'), {})

    def test_broken_file_reports_line(self):
        """人工编辑写坏了（少逗号），报出第几行"""
        path = self.tmp / 'bad.json'
        path.write_text('{\n"a.com": {"status": "待提交"}\n"b.com": {}\n}\n', encoding='utf-8')
        with self.assertRaises(ValueError) as ctx:
            load_ledger(path)
        self.assertIn('第 3 行', str(ctx.exception))


class TestRecheckDue(unittest.TestCase):

    def test_due_rule(self):
        """已提交、提交日早于今天、今天还没复查的才到期"""
        day = '2026-11-06'
        ledger = {
            'yesterday.com': {'status': '已提交', 'submitted_at': '2026-11-05 10:00:00', 'checked_at': None},
            'old-check.com': {'status': '已提交', 'submitted_at': '2026-11-01 10:00:00',
                              'checked_at': '2026-11-05 09:00:00'},
            'today-sent.com': {'status': '已提交', 'submitted_at': '2026-11-06 08:00:00', 'checked_at': None},
            'checked.com': {'status': '已提交', 'submitted_at': '2026-11-01 10:00:00',
                            'checked_at': '2026-11-06 09:00:00'},
            'included.com': {'status': '已收录', 'submitted_at': '2026-11-01 10:00:00', 'checked_at': None},
            'pending.com': {'status': '待提交', 'submitted_at': None, 'checked_at': None},
        }
        self.assertEqual(recheck_due(ledger, day), ['yesterday.com', 'old-check.com'])


if __name__ == '__main__':
    unittest.main()
