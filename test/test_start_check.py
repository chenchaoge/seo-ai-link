"""开工检查离线测试（不联网、不装库）：python -B test/test_start_check.py"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import start_check  # noqa: E402
from modules.submission_ledger import save_ledger  # noqa: E402
from modules.user_space import UserSpace  # noqa: E402


class TestPackages(unittest.TestCase):

    def test_required_packages(self):
        """读 requirements.txt 的包名"""
        self.assertEqual(start_check.required_packages(), ['requests', 'beautifulsoup4', 'lxml', 'python-dotenv'])

    def test_missing_uses_import_name(self):
        """包名和 import 名不一样的按 import 名查；没装的列出来"""
        missing = start_check.missing_packages(['beautifulsoup4', 'python-dotenv', 'surely-not-installed-pkg-x'])
        self.assertEqual(missing, ['surely-not-installed-pkg-x'])

    def test_install_not_called_when_complete(self):
        """库都在就不装"""
        with mock.patch.object(start_check, 'install_packages') as install, redirect_stdout(io.StringIO()):
            self.assertFalse(start_check.check_packages([], start_check.OFFICIAL))
        install.assert_not_called()

    def test_official_then_mirror(self):
        """官方源通：先官方源，装不上换清华镜像；官方源不通：直接镜像"""
        with mock.patch.object(start_check, 'missing_packages', return_value=['lxml']), \
                mock.patch.object(start_check, 'install_packages', side_effect=[False, True]) as install, \
                redirect_stdout(io.StringIO()):
            self.assertTrue(start_check.check_packages([], start_check.OFFICIAL))
        self.assertEqual([c.args[1] for c in install.call_args_list], [None, start_check.PIP_MIRROR])
        with mock.patch.object(start_check, 'missing_packages', return_value=['lxml']), \
                mock.patch.object(start_check, 'install_packages', return_value=True) as install, \
                redirect_stdout(io.StringIO()):
            self.assertTrue(start_check.check_packages([], start_check.MIRROR))
        self.assertEqual([c.args[1] for c in install.call_args_list], [start_check.PIP_MIRROR])

    def test_mirror_flag_in_pip_command(self):
        """走镜像时 pip 命令带 -i"""
        done = mock.Mock(returncode=0)
        with mock.patch.object(start_check.subprocess, 'run', return_value=done) as run, redirect_stdout(io.StringIO()):
            self.assertTrue(start_check.install_packages(['lxml'], start_check.PIP_MIRROR))
            self.assertEqual(run.call_args.args[0][-2:], ['-i', start_check.PIP_MIRROR])
            self.assertTrue(start_check.install_packages(['lxml'], None))
            self.assertNotIn('-i', run.call_args.args[0])


class TestNetwork(unittest.TestCase):

    def test_probe(self):
        """官方源通 = 官方源；官方源不通镜像通 = 镜像；都不通 = None；没镜像的不试镜像"""
        def down(url):
            return None if 'mirror' in url else 'Timeout'
        with mock.patch.object(start_check, 'unreachable_reason', side_effect=down):
            self.assertEqual(start_check.probe('https://official', 'https://mirror'), start_check.MIRROR)
            self.assertIsNone(start_check.probe('https://official', None))
        with mock.patch.object(start_check, 'unreachable_reason', return_value=None):
            self.assertEqual(start_check.probe('https://official', 'https://mirror'), start_check.OFFICIAL)


class TestChrome(unittest.TestCase):

    def test_report(self):
        with mock.patch.object(start_check, 'chrome_path', return_value=None), redirect_stdout(io.StringIO()) as out:
            problems = []
            start_check.check_chrome(problems)
        self.assertEqual(len(problems), 1)
        self.assertIn('Chrome 没装', out.getvalue())
        with mock.patch.object(start_check, 'chrome_path', return_value=Path('C:/x/chrome.exe')), \
                redirect_stdout(io.StringIO()) as out:
            problems = []
            start_check.check_chrome(problems)
        self.assertEqual(problems, [])
        self.assertTrue(out.getvalue().startswith(start_check.PASS))


class TestNode(unittest.TestCase):

    def test_parse_version(self):
        self.assertEqual(start_check.parse_node_version('v20.11.1\n'), (20, 11, 1))
        self.assertEqual(start_check.parse_node_version('18.0.0'), (18, 0, 0))
        self.assertIsNone(start_check.parse_node_version('command not found'))

    def test_report(self):
        """没装、太老 = 要处理；够新 = 通过"""
        cases = {None: start_check.TODO, (16, 20, 0): start_check.TODO, (22, 1, 0): start_check.PASS}
        for version, tag in cases.items():
            with self.subTest(version=version), mock.patch.object(start_check, 'node_version', return_value=version):
                problems = []
                out = io.StringIO()
                with redirect_stdout(out):
                    start_check.check_node(problems)
                self.assertTrue(out.getvalue().startswith(tag))
                self.assertEqual(len(problems), 0 if tag == start_check.PASS else 1)


class TestUserSpace(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_can_write(self):
        self.assertTrue(start_check.can_write(self.tmp))
        self.assertFalse(start_check.can_write(self.tmp / '不存在'))

    def test_dataforseo_only_reminds(self):
        """账号没填只算提醒不算要处理；填了算通过，账号密码不打印"""
        space = UserSpace(self.tmp)
        space.data_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith('DATAFORSEO_')}
        for content, tag in (('DataForSEO_API_login=\nDataForSEO_API_password=\n', start_check.NOTE),
                             ('DataForSEO_API_login=u@x.com\nDataForSEO_API_password=pw-secret\n', start_check.PASS)):
            space.env_file().write_text(content, encoding='utf-8')
            problems = []
            with self.subTest(tag=tag), mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(start_check, 'load_user_space', return_value=space), \
                    redirect_stdout(io.StringIO()) as out:
                start_check.check_user_space(problems)
            self.assertEqual(problems, [])
            self.assertIn(f"{tag} DataForSEO 账号", out.getvalue())
            self.assertNotIn('pw-secret', out.getvalue())
            self.assertNotIn('u@x.com', out.getvalue())

    def test_recheck_reminder(self):
        """到期的按独立站列出来，算提醒不算要处理"""
        space = UserSpace(self.tmp)
        save_ledger(space.ledger_path('a.com'), {
            'x.com': {'status': '已提交', 'submitted_at': '2026-01-01 10:00:00', 'checked_at': None},
            'y.com': {'status': '已收录', 'submitted_at': '2026-01-01 10:00:00', 'checked_at': None},
        })
        save_ledger(space.ledger_path('b.com'), {})
        problems = []
        out = io.StringIO()
        with redirect_stdout(out):
            start_check.check_recheck_due(space, problems)
        text = out.getvalue()
        self.assertIn('每日复查到期', text)
        self.assertIn('a.com：1 个（x.com）', text)
        self.assertNotIn('b.com', text)
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
