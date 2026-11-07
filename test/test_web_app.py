"""菜单 10 本机外链报告网页的离线测试：python -B test/test_web_app.py
用临时目录和临时位置文件，不碰真的用户目录和 ~/.seo-external-link.json；只在本机 127.0.0.1 开临时端口"""

import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock
from urllib.parse import quote

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from modules import web_app  # noqa: E402
from modules.user_space import create_site, init_user_space  # noqa: E402


class OtherProgram(BaseHTTPRequestHandler):
    """占着端口的别的程序：什么请求都不会答（回 501），也不在屏幕上打印"""

    def log_message(self, format, *args):
        pass


class TestWebApp(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        patcher = mock.patch('modules.user_space.USER_CONFIG_FILE', self.tmp / 'pointer.json')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.space = init_user_space(self.tmp / 'user')
        create_site(self.space, 'a.com')
        (self.space.site_dir('a.com') / 'logo.png').write_bytes(b'\x89PNG fake')
        self.space.env_file().write_text('DataForSEO_API_login=u@x.com\nDataForSEO_API_password=pw-secret\n', encoding='utf-8')
        self.server = web_app.ReportServer(('127.0.0.1', 0), web_app.ReportHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        sent = {'Host': f'127.0.0.1:{self.port}', **(headers or {})}
        conn.request('GET', path, headers=sent)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def test_serves_page_scripts_and_live_data(self):
        status, page = self.request('/')
        self.assertEqual(status, 200)
        self.assertEqual(self.request(quote('/外链报告.html')), (200, page))
        self.assertEqual(self.request('/data/report/app.js')[0], 200)
        status, data = self.request('/data/report/report_data.js')
        self.assertEqual(status, 200)
        self.assertIn(b'"user_report":true', data)
        self.assertIn(b'"a.com"', data)
        self.assertEqual(self.request('/data/sites/a.com/logo.png'), (200, b'\x89PNG fake'))

    def test_shows_error_when_library_broken(self):
        """用户外链库写错时，数据文件变成弹窗说明错在哪，页面不会一片空白"""
        usable = self.space.library_files['usable']
        usable.parent.mkdir(parents=True, exist_ok=True)
        usable.write_text('{"site": "x.com", "verdict": "免费类"\n', encoding='utf-8')
        status, data = self.request('/data/report/report_data.js')
        self.assertEqual(status, 500)
        self.assertTrue(data.startswith(b'alert('))
        self.assertIn('usable_sites.jsonl'.encode('utf-8'), data)

    def test_never_serves_private_files(self):
        """账号文件、独立站资料（有密码）、设置、路径穿越一律不给"""
        password = json.loads(self.space.profile_path('a.com').read_text(encoding='utf-8'))['password']
        for path in ('/data/dataforseo.txt', '/data/settings.json', '/data/sites/a.com/profile.json',
                     '/data/sites/a.com/ledger.json', '/data/report/../settings.json', '/data/report/%2e%2e/settings.json',
                     '/data/sites/a.com/../../dataforseo.txt','/data/sites/b.com/logo.png', quote('/用户档案说明.txt')):
            with self.subTest(path):
                status, body = self.request(path)
                self.assertEqual(status, 404)
                for secret in (password, 'pw-secret', 'u@x.com'):
                    self.assertNotIn(secret.encode(), body)

    def test_blocks_other_websites(self):
        """别的网站（换 Host、跨站来读）一律拒绝"""
        self.assertEqual(self.request('/data/report/report_data.js', {'Host': 'evil.com'})[0], 403)
        self.assertEqual(self.request('/data/report/report_data.js', {'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_port_state(self):
        """端口空着 / 开着自己 / 被别的程序占着"""
        self.assertTrue(web_app.port_state(self.port))
        other = web_app.ReportServer(('127.0.0.1', 0), OtherProgram)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        self.assertFalse(web_app.port_state(other.server_address[1]))
        free = other.server_address[1]
        other.shutdown()
        other.server_close()
        self.assertIsNone(web_app.port_state(free))


if __name__ == '__main__':
    unittest.main()
