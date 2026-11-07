"""
本机外链报告网页（菜单 10）：Python 自带的 http.server，只在本机 127.0.0.1 开，别的电脑访问不到
- 网页和样式脚本直接用 SKILL 的报告模板（assets/report/）；数据 data/report/report_data.js 每次请求现算，打开、刷新就是最新的
- 用户目录里只给独立站的 logo.png；别的文件一律不给（账号文件、独立站资料里有密码）
- 防别的网站借用户的浏览器来读：Host 必须是本机地址；跨站来的请求（Sec-Fetch-Site）一律不给
"""

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.error import URLError
from urllib.parse import unquote, urlsplit
from urllib.request import ProxyHandler, build_opener

from config import WEB_HOST, WEB_PORT
from modules.report_builder import DATA_FILE_NAME, LOGO_FILE, TEMPLATE, build_user_report, report_data_js
from modules.user_space import DATA_DIR, REPORT_FILES_DIR, load_user_space

APP_ID = 'seo-ai-link-report'  # /api/ping 回这个，菜单 10 用它认出端口上开着的是不是自己
CONTENT_TYPES = {  # 不用 mimetypes：Windows 注册表可能把 .js 认成 text/plain
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.png': 'image/png',
}
JSON_TYPE = 'application/json; charset=utf-8'
REPORT_PREFIX = f'/{DATA_DIR}/{REPORT_FILES_DIR}/'
SITES_PREFIX = f'/{DATA_DIR}/sites/'
NO_SPACE = '还没设置用户目录（或记的用户目录不在了）：让 AI 用菜单 6 设置'


class ReportServer(HTTPServer):
    allow_reuse_address = sys.platform != 'win32'  # Windows 上开了这个，两个程序能抢同一个端口


class ReportHandler(BaseHTTPRequestHandler):
    """一个一个处理请求就够：只有用户自己看，HTTP/1.0 每个请求完就断开，不会互相卡住"""

    def log_message(self, format, *args):
        """不在屏幕上刷每个请求"""

    def _allowed(self) -> bool:
        """Host 是本机地址、不是跨站来的"""
        port = self.server.server_address[1]
        if self.headers.get('Host') not in {f'{WEB_HOST}:{port}', f'localhost:{port}'}:
            return False
        return self.headers.get('Sec-Fetch-Site', 'none') in ('same-origin', 'none')

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')  # 每次都拿最新的数据和脚本
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict):
        self._send(status, json.dumps(data, ensure_ascii=False).encode('utf-8'), JSON_TYPE)

    def _file(self, path):
        content_type = CONTENT_TYPES.get(path.suffix.lower())
        if not content_type or not path.is_file():
            self._json(404, {'error': '没有这个文件'})
            return
        self._send(200, path.read_bytes(), content_type)

    def do_GET(self):
        if not self._allowed():
            self._json(403, {'error': '只能在本机打开'})
            return
        path = unquote(urlsplit(self.path).path)
        if path == '/api/ping':
            self._json(200, {'app': APP_ID})
        elif path in ('/', f'/{TEMPLATE.report_html.name}'):
            self._file(TEMPLATE.report_html)
        elif path == REPORT_PREFIX + DATA_FILE_NAME:
            self._report_data()
        elif path.startswith(REPORT_PREFIX) and '/' not in path[len(REPORT_PREFIX):]:
            self._file(TEMPLATE.report_files_dir / path[len(REPORT_PREFIX):])
        elif path.startswith(SITES_PREFIX):
            self._logo(path[len(SITES_PREFIX):])
        else:
            self._json(404, {'error': '没有这个页面'})

    def _alert(self, status: int, message: str):
        """数据给不了时，让页面弹出原因，不要一片空白"""
        self._send(status, f"alert({json.dumps(message, ensure_ascii=False)});".encode('utf-8'), CONTENT_TYPES['.js'])

    def _report_data(self):
        """报告数据现算（和菜单 5 写进文件的一样）"""
        space = load_user_space()
        if space is None:
            self._alert(503, NO_SPACE)
            return
        try:
            data, passwords, _ = build_user_report(space)
        except Exception as e:  # 外链库、台账、独立站资料写错了：把报错（含文件和行号）弹出来
            self._alert(500, f"报告数据算不出来：{e}")
            return
        self._send(200, report_data_js(data, passwords).encode('utf-8'), CONTENT_TYPES['.js'])

    def _logo(self, rest: str):
        """只给 data/sites/<独立站>/logo.png，独立站必须是用户目录里有的"""
        space = load_user_space()
        site, _, name = rest.partition('/')
        if space is None or name != LOGO_FILE or site not in space.independent_sites():
            self._json(404, {'error': '没有这个文件'})
            return
        self._file(space.site_dir(site) / LOGO_FILE)


def port_state(port: int) -> Optional[bool]:
    """端口上有没有程序：None = 空着；True = 已经开着外链报告网页；False = 别的程序占着"""
    opener = build_opener(ProxyHandler({}))  # 不走系统代理：开着代理软件时，连本机地址也可能被转到代理上
    try:
        with opener.open(f'http://{WEB_HOST}:{port}/api/ping', timeout=3) as resp:
            return json.load(resp).get('app') == APP_ID
    except URLError as e:
        return None if isinstance(e.reason, ConnectionRefusedError) else False
    except (OSError, ValueError):
        return False


def serve(port: int = WEB_PORT, open_browser: bool = True):
    """开本机外链报告网页，一直开着，直到这个程序被关掉；已经开着就直接用浏览器打开"""
    url = f'http://{WEB_HOST}:{port}/'
    state = port_state(port)
    if state is True:
        print(f"外链报告网页已经开着：{url}")
        if open_browser:
            webbrowser.open(url)
        return
    if state is False:
        print(f"端口 {port} 被别的程序占着，打不开外链报告网页：把 scripts/config.py 的 WEB_PORT 改成别的数字（比如 8766）再试")
        return
    server = ReportServer((WEB_HOST, port), ReportHandler)
    print(f"外链报告网页：{url}（这个程序一直开着，网页才打得开；关掉程序网页就打不开了）", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("外链报告网页已关")
    finally:
        server.server_close()
