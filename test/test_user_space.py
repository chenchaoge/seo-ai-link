"""用户目录和报告数据的离线测试：python -B test/test_user_space.py"""

import io
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import main  # noqa: E402
from modules.report_builder import (  # noqa: E402
    ORIGIN_DEFAULT, ORIGIN_USER, build_library_sites, collect_provenance, generate_report,
)
from modules.site_library import save_library  # noqa: E402
from modules.user_space import (  # noqa: E402
    ENV_TEMPLATE, PASSWORD_LENGTH, UserSpace, create_site, init_user_space, load_user_space,
)


class TestUserSpace(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.space = UserSpace(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_layout_only_report_html_and_data_on_top(self):
        """用户目录第一层只有外链报告.html、用户档案说明.txt 和 data/，报告的样式脚本、档案和分析结果都在 data/ 里"""
        self.assertEqual(self.space.report_html, self.tmp / '外链报告.html')
        self.assertEqual(self.space.report_files_dir, self.tmp / 'data' / 'report')
        self.assertEqual(self.space.readme_path, self.tmp / '用户档案说明.txt')
        self.assertEqual(self.space.settings_path, self.tmp / 'data' / 'settings.json')
        self.assertEqual(self.space.library_files['usable'], self.tmp / 'data' / 'library' / 'usable_sites.jsonl')
        self.assertEqual(self.space.ledger_path('a.com'), self.tmp / 'data' / 'sites' / 'a.com' / 'ledger.json')
        self.assertEqual(self.space.analyses_dir, self.tmp / 'data' / 'analyses')

    def test_init_writes_pointer_outside_skill_dir(self):
        """菜单 6：建好目录结构，位置记进电脑用户文件夹的位置文件（测试里换成临时文件，不碰真的）"""
        pointer = self.tmp / 'pointer.json'
        user_dir = self.tmp / 'mine'
        with mock.patch('modules.user_space.USER_CONFIG_FILE', pointer):
            init_user_space(user_dir)
            self.assertEqual(load_user_space().root, user_dir)
        self.assertEqual(sorted(p.name for p in user_dir.iterdir()), ['data', '用户档案说明.txt'])  # 报告网页菜单 5 才生成
        self.assertIn('请保管、备份好', (user_dir / '用户档案说明.txt').read_text(encoding='utf-8'))
        self.assertEqual(sorted(p.name for p in (user_dir / 'data').iterdir()),
                         ['analyses', 'dataforseo.txt', 'library', 'settings.json', 'sites'])
        self.assertEqual(json.loads(pointer.read_text(encoding='utf-8')), {'user_dir': str(user_dir)})

    def test_init_skips_env_template_when_configured(self):
        """settings.json 另指了 DataForSEO 账号文件：不拷空模板，也不往别处写"""
        user_dir = self.tmp / 'mine'
        UserSpace(user_dir).save_settings({'dataforseo_env_file': str(self.tmp / 'elsewhere.env')})
        with mock.patch('modules.user_space.USER_CONFIG_FILE', self.tmp / 'pointer.json'):
            init_user_space(user_dir)
        self.assertFalse((user_dir / 'data' / 'dataforseo.txt').exists())
        self.assertFalse((self.tmp / 'elsewhere.env').exists())

    def test_setup_menu_generates_report(self):
        """菜单 6 建好用户目录就生成外链报告：还没有独立站，标明是用户的报告"""
        user_dir = self.tmp / 'mine'
        with mock.patch('modules.user_space.USER_CONFIG_FILE', self.tmp / 'pointer.json'), \
                mock.patch.object(main, 'read_input', return_value=str(user_dir)), \
                mock.patch('sys.stdout', new_callable=io.StringIO):
            main.run_setup_user_dir()
        self.assertEqual(sorted(p.name for p in user_dir.iterdir()), ['data', '外链报告.html', '用户档案说明.txt'])
        text = (user_dir / 'data' / 'report' / 'report_data.js').read_text(encoding='utf-8')
        data = json.loads(text[text.index('{'):].rstrip().rstrip(';'))
        self.assertTrue(data['user_report'])
        self.assertEqual(data['independent_sites'], [])

    def test_load_without_pointer_is_none(self):
        with mock.patch('modules.user_space.USER_CONFIG_FILE', self.tmp / 'none.json'):
            self.assertIsNone(load_user_space())

    def test_create_site_from_template(self):
        """新建独立站：网址写法也认，profile 从模板拷并填上域名；第一个独立站自动设成当前独立站"""
        path = create_site(self.space, 'https://www.Example.com/about')
        self.assertEqual(path, self.tmp / 'data' / 'sites' / 'example.com' / 'profile.json')
        profile = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual((profile['site'], profile['url']), ('example.com', 'https://example.com/'))
        password = profile['password']
        self.assertEqual(len(password), PASSWORD_LENGTH)
        self.assertTrue(any(c.isupper() for c in password) and any(c.islower() for c in password)
                        and any(c.isdigit() for c in password) and password.endswith('!'))
        self.assertEqual(self.space.current_site(), 'example.com')
        create_site(self.space, 'example.com')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['password'], password)  # 再跑不换密码
        create_site(self.space, 'second.com')
        self.assertEqual(self.space.current_site(), 'example.com')  # 已有当前独立站就不改
        self.assertEqual(self.space.independent_sites(), ['example.com', 'second.com'])

    def test_create_site_fills_missing_password(self):
        """已有档案只缺密码：再跑菜单 7 只补密码，别的字段不动"""
        path = self.space.profile_path('old.com')
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'site': 'old.com', 'name': 'Old', 'password': None}), encoding='utf-8')
        create_site(self.space, 'old.com')
        profile = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(profile['name'], 'Old')
        self.assertTrue(profile['password'])

    def test_env_file_default(self):
        self.assertEqual(self.space.env_file(), self.tmp / 'data' / 'dataforseo.txt')
        self.space.save_settings({'dataforseo_env_file': 'D:/x/.env'})
        self.assertEqual(self.space.env_file(), Path('D:/x/.env'))

    def test_dataforseo_account(self):
        """空模板 = 没填；两行都填了才算有账号；记事本存的带 BOM 也能读；老的英文键也认；文件没填的看环境变量"""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.space.data_dir.mkdir(parents=True)
            shutil.copyfile(ENV_TEMPLATE, self.space.env_file())
            self.assertIsNone(self.space.dataforseo_account())
            filled = ENV_TEMPLATE.read_text(encoding='utf-8').replace('_login=', '_login= u@x.com ').replace('_password=', '_password=pw-1')
            self.space.env_file().write_text(filled, encoding='utf-8-sig')
            self.assertEqual(self.space.dataforseo_account(), ('u@x.com', 'pw-1'))
            self.space.env_file().write_text('DATAFORSEO_USERNAME=u@x.com\nDATAFORSEO_PASSWORD=\n', encoding='utf-8')
            self.assertIsNone(self.space.dataforseo_account())
            os.environ['DATAFORSEO_PASSWORD'] = 'env-pw'
            self.assertEqual(self.space.dataforseo_account(), ('u@x.com', 'env-pw'))


class TestRunDirLog(unittest.TestCase):
    """日志写进那一批的分析结果目录，换一批就换文件"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        logger = logging.getLogger(main.LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        shutil.rmtree(self.tmp)

    def test_log_follows_run_dir(self):
        logger = main.setup_logging()
        self.assertFalse(any(isinstance(h, logging.FileHandler) for h in logger.handlers))  # 一开始只打印到屏幕
        first, second = self.tmp / 'run1', self.tmp / 'run2'
        first.mkdir()
        second.mkdir()
        main.log_to_run_dir(logger, first)
        logger.info('第一批')
        main.log_to_run_dir(logger, second)
        logger.info('第二批')
        self.assertEqual(sum(isinstance(h, logging.FileHandler) for h in logger.handlers), 1)
        text1 = next(first.glob('log_*.log')).read_text(encoding='utf-8')
        text2 = next(second.glob('log_*.log')).read_text(encoding='utf-8')
        self.assertIn('第一批', text1)
        self.assertNotIn('第二批', text1)
        self.assertIn('第二批', text2)


class TestReportData(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.space = UserSpace(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_provenance_from_analyses(self):
        """外链网站从哪个竞品挖出来、看过哪些页面，从用户目录的分析结果目录算"""
        for name, target in (('1_x', 'https://x.com/page'), ('2_y', 'y.com')):
            run_dir = self.space.analyses_dir / name
            run_dir.mkdir(parents=True)
            data = {'target': target, 'pages': [{'domain_from': 'www.a.com', 'url_from': f'https://a.com/{name}'}]}
            (run_dir / 'results.json').write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(collect_provenance(self.space.analyses_dir),
                         {'a.com': {'competitors': ['x.com', 'y.com'], 'pages': ['https://a.com/1_x',
                                                                              'https://a.com/2_y']}})

    def test_library_items_marked_by_origin(self):
        library = {'a.com': {'site': 'a.com', 'verdict': '免费类', 'how': '发邮件到 hello@a.com'},
                   'b.com': {'site': 'b.com', 'verdict': '付费类'}}
        library['a.com']['industry'] = 'AI产品工具'
        items = {i['site']: i for i in build_library_sites(library, {'b.com'}, {}, {'a.com': {'ours.com': '已收录'}},
                                                           {'ours.com': '计算机、电子与科技'})}
        self.assertEqual((items['a.com']['origin'], items['b.com']['origin']), (ORIGIN_DEFAULT, ORIGIN_USER))
        self.assertEqual(items['a.com']['tracks'], {'ours.com': '相近赛道'})  # 同一个赛道大类（科技）
        self.assertEqual(items['b.com']['tracks'], {'ours.com': '行业未标'})
        self.assertEqual(items['a.com']['plans']['ours.com']['tier'], '第3档')  # 契合赛道、免费、链接属性没记录
        self.assertEqual(items['b.com']['plans']['ours.com']['tier'], '第5档')  # 付费
        self.assertEqual(items['a.com']['how'], '发邮件到 he***@a.com')  # 邮箱打码
        self.assertEqual(items['a.com']['used_by'], {'ours.com': '已收录'})

    def test_generate_report_into_user_dir(self):
        """菜单 5：网页拷到用户目录第一层、样式脚本和数据进 data/report/，数据里有独立站和完整外链库，
        密码不会混进去，logo 指向 data/sites"""
        create_site(self.space, 'ours.com')
        profile_path = self.space.profile_path('ours.com')
        profile = json.loads(profile_path.read_text(encoding='utf-8'))
        profile.update({'name': 'Ours', 'password': 'pw-only-for-test', 'industry': '游戏'})
        profile_path.write_text(json.dumps(profile), encoding='utf-8')
        (profile_path.parent / 'logo.png').write_bytes(b'png')
        self.space.ledger_path('ours.com').write_text(
            json.dumps({'a.com': {'status': '已提交', 'note': '密码 pw-only-for-test'}}), encoding='utf-8')
        save_library(self.space.library_files, {'a.com': {
            'site': 'a.com', 'verdict': '付费类', 'industry': '游戏', 'scope': '整站', 'source': '人工复核'}})
        result = generate_report(self.space)
        self.assertEqual(result['index'], self.tmp / '外链报告.html')
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ['data', '外链报告.html'])  # 这里没跑菜单 6，没有说明
        self.assertEqual(result['path'], self.tmp / 'data' / 'report' / 'report_data.js')
        html = result['index'].read_text(encoding='utf-8')
        for src in re.findall(r'(?:src|href)="(data/[^"]+)"', html):  # 网页引用的样式脚本和数据都在
            self.assertTrue((self.tmp / src).exists(), src)
        text = result['path'].read_text(encoding='utf-8')
        self.assertNotIn('pw-only-for-test', text)
        data = json.loads(text[text.index('{'):].rstrip().rstrip(';'))
        self.assertTrue(data['user_report'])
        self.assertEqual([s['site'] for s in data['independent_sites']], ['ours.com'])
        self.assertEqual(data['independent_sites'][0]['industry'], '游戏')
        self.assertEqual(data['independent_sites'][0]['entries'][0]['track'], '同赛道')  # 行业以外链库为准
        self.assertEqual(len(data['industries']), 26)
        self.assertEqual(data['tracks'][:3], ['同赛道', '相近赛道', '不分行业'])
        logo = data['independent_sites'][0]['logo']
        self.assertTrue((self.tmp / logo).exists())  # 从外链报告.html 所在的第一层出发能找到 logo
        self.assertEqual(result['user_library'], 1)
        self.assertGreater(result['library'], 1)  # 默认外链库 + 用户外链库


if __name__ == '__main__':
    unittest.main()
