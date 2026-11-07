"""
开工检查：每次用这个 SKILL 先跑一次（不花钱、不用输入任何东西），AI 按打印的结果处理，见 SKILL.md「开工检查」
1. 系统和 Python：只支持 Windows、Mac；Python 至少 3.9
2. 联网：装库、查外链、打开外链网站都要能上网；平台的沙箱没开联网权限时这里会连不上。
   装库、装浏览器工具的官方源在国外，连不上就看国内镜像通不通，通了后面就用镜像（规则固定，不让 AI 挑）
3. Python 库：requirements.txt 里缺的，用跑这个脚本的同一个 Python 自动装（pip）：官方源装不上自动换国内镜像再装一次；
   装好后自动重跑一遍检查
4. Node.js 和 Chrome：浏览器工具 Playwright MCP 要 Node.js 18 或更新，并且用电脑上装的 Chrome 开一个单独的档案；
   没装只报告、不代装（装法每个系统只有一种，见 references/setup.md「装软件」）
5. 用户目录：设置了没有、能不能写进去、DataForSEO 账号填了没有（只看填没填，不打印、不去验证）
6. 回访提醒：各独立站今天该每日独立站外链回访的外链网站，到期了 AI 先问用户，用户同意才跑
第 1～4 项只用 Python 自带的库，缺库也能跑；第 5、6 项要用到 SKILL 自己的模块，库齐了才查
"""

from __future__ import annotations  # 缺库时 UserSpace 没导入，类型标注不能在定义函数时就求值

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# 禁用__pycache__目录生成
sys.dont_write_bytecode = True
# 添加模块路径
sys.path.append(str(Path(__file__).parent))

from config import SKILL_DIR, USER_CONFIG_FILE  # noqa: E402  config 只用 Python 自带的库

try:  # 下面这些要用到第三方库：缺库时先记下，装好库后重跑本脚本（新进程才认得刚装的库）
    import requests  # noqa: E402
    from modules.submission_ledger import (  # noqa: E402
        load_ledger, missing_submit_evidence, recheck_due, unverified_submissions,
    )
    from modules.submit_policy import today_text  # noqa: E402
    from modules.user_space import UserSpace, load_user_space  # noqa: E402
    MODULE_ERROR = None
except ImportError as error:
    requests = None
    MODULE_ERROR = error

MIN_PYTHON = (3, 9)  # Mac 自带的 python3 是 3.9
SUPPORTED_SYSTEMS = {'Windows': 'Windows', 'Darwin': 'Mac'}
REQUIREMENTS_FILE = SKILL_DIR / 'requirements.txt'
IMPORT_NAMES = {'beautifulsoup4': 'bs4', 'python-dotenv': 'dotenv'}  # pip 包名和 import 名不一样的
PIP_TIMEOUT = 300  # 每个源最多等 5 分钟
PIP_ERROR_LINES = 8  # 装不上时打印 pip 报错的最后几行
PIP_MIRROR = 'https://pypi.tuna.tsinghua.edu.cn/simple'  # pip 国内镜像（清华）：官方源连不上或装不上时用
NPM_MIRROR = 'https://registry.npmmirror.com'  # npm 国内镜像：官方源连不上时 MCP 配置里加环境变量 npm_config_registry
NODE_MIRROR = NPM_MIRROR + '/-/binary/node/latest-v24.x/'  # Node.js 安装包的国内镜像（nodejs.org 的镜像）
RERUN_FLAG = 'SEO_AI_LINK_START_CHECK_RERUN'  # 装完库重跑时带上，重跑那次不再装、不再重跑
NETWORK_TIMEOUT = 15
NET_PIP, NET_NPM, NET_DATAFORSEO, NET_WEB = '装 Python 库', '装浏览器工具 Playwright MCP（npm）', '菜单 1 查竞品外链（DataForSEO）', '打开外链网站'
NETWORK_TARGETS = [  # (用来干什么, 官方地址, 国内镜像或 None)；对方回任何 HTTP 状态码都算连得上
    (NET_PIP, 'https://pypi.org/simple/', PIP_MIRROR + '/'),
    (NET_NPM, 'https://registry.npmjs.org/', NPM_MIRROR + '/'),
    (NET_DATAFORSEO, 'https://api.dataforseo.com/', None),
    (NET_WEB, 'https://example.com/', None),  # 拿一个普通网站代表
]
OFFICIAL, MIRROR = '官方源', '国内镜像'  # 联网检查的结果：用哪个源；None = 都连不上
USER_AGENT = 'seo-ai-link-start-check'
NODE_MIN_MAJOR = 18  # Playwright MCP 的要求
NODE_INSTALL = {  # 每个系统只有一种装法；官方源下载失败才用镜像。winget 那条 AI 可以代跑，Mac 的安装包要用户自己双击装
    'Windows': f'跑 winget install OpenJS.NodeJS.LTS；winget 下载失败就从 {NODE_MIRROR} 下载 x64 的 .msi 装',
    'Darwin': f'到 nodejs.org 下载 macOS 安装包（.pkg）装；打不开就从 {NODE_MIRROR} 下载 .pkg',
}
CHROME_INSTALL = {  # Playwright MCP 默认用电脑上装的 Chrome；google.cn 的下载国内不用翻墙
    'Windows': '跑 winget install Google.Chrome',
    'Darwin': '到 google.cn/chrome 下载 .dmg 装',
}
PASS, TODO, NOTE = '[通过]', '[要处理]', '[提醒]'


def report(tag: str, text: str, problems: List[str]):
    """打印一项检查结果；要处理的记进 problems"""
    print(f"{tag} {text}")
    if tag == TODO:
        problems.append(text)


def check_system(problems: List[str]) -> bool:
    """系统和 Python 版本；Python 太老返回 False（后面的都不用查了）"""
    system = SUPPORTED_SYSTEMS.get(platform.system())
    version = '.'.join(str(n) for n in sys.version_info[:3])
    if system:
        report(PASS, f"系统：{system}", problems)
    else:
        report(TODO, f"系统：{platform.system()}，这个 SKILL 只支持 Windows、Mac 本机运行"
                     f"（平台要是在云端沙箱里跑命令，就碰不到用户电脑上的文件和浏览器）", problems)
    if sys.version_info[:2] < MIN_PYTHON:
        report(TODO, f"Python {version} 太老，至少要 {MIN_PYTHON[0]}.{MIN_PYTHON[1]}（{sys.executable}）", problems)
        return False
    report(PASS, f"Python {version}（{sys.executable}）", problems)
    return True


def unreachable_reason(url: str) -> Optional[str]:
    """连得上返回 None，连不上返回原因；有 requests 就用它（自带证书），没有才用 Python 自带的 urllib"""
    headers = {'User-Agent': USER_AGENT}
    if requests:
        try:
            requests.head(url, headers=headers, timeout=NETWORK_TIMEOUT, allow_redirects=False)
        except requests.RequestException as e:
            return type(e).__name__
        return None
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=headers, method='HEAD'),
                               timeout=NETWORK_TIMEOUT).close()
    except urllib.error.HTTPError:  # 对方回了错误码，网是通的
        return None
    except OSError as e:  # URLError、超时、证书错误都在这里
        return str(getattr(e, 'reason', e))
    return None


def probe(official: str, mirror: Optional[str]) -> Optional[str]:
    """一项联网检查用哪个源：官方源通 = OFFICIAL；官方源不通、镜像通 = MIRROR；都不通 = None"""
    if unreachable_reason(official) is None:
        return OFFICIAL
    if mirror and unreachable_reason(mirror) is None:
        return MIRROR
    return None


def check_network(problems: List[str]) -> Dict[str, Optional[str]]:
    """联网：一个一个试，返回 {用途: 用哪个源}"""
    result = {purpose: probe(official, mirror) for purpose, official, mirror in NETWORK_TARGETS}
    if all(source == OFFICIAL for source in result.values()):
        report(PASS, "联网正常", problems)
        return result
    for purpose, official, mirror in NETWORK_TARGETS:
        source = result[purpose]
        if source == OFFICIAL:
            report(PASS, f"联网：{purpose} 正常", problems)
        elif source == MIRROR:
            report(NOTE, f"联网：{purpose} 的官方源 {official} 连不上，国内镜像 {mirror} 通，后面用镜像", problems)
        else:
            report(TODO, f"联网：{purpose} 连不上（{official}" + (f"，镜像 {mirror} 也连不上" if mirror else '') + '）', problems)
    if not any(result.values()):
        print("    全都连不上：多半是平台没给命令联网权限（沙箱），请用户在平台设置里打开联网，或者电脑本身没网")
    if result[NET_NPM] == MIRROR:
        print(f"    装 Playwright MCP 时在 MCP 配置里加环境变量 npm_config_registry={NPM_MIRROR}（见 references/setup.md「浏览器工具：Playwright MCP」）")
    return result


def required_packages() -> List[str]:
    """requirements.txt 里的 pip 包名"""
    names = []
    for line in REQUIREMENTS_FILE.read_text(encoding='utf-8').splitlines():
        name = re.split(r'[<>=!~\[;\s]', line.split('#')[0].strip())[0]
        if name:
            names.append(name)
    return names


def missing_packages(packages: List[str]) -> List[str]:
    """这个 Python 里还没装的包"""
    return [name for name in packages if importlib.util.find_spec(IMPORT_NAMES.get(name, name)) is None]


def install_packages(packages: List[str], index_url: Optional[str]) -> bool:
    """用跑这个脚本的同一个 Python 从一个源装库，装上返回 True；装不上打印 pip 报错的最后几行"""
    source = f"国内镜像 {index_url}" if index_url else '官方源'
    print(f"    正在从{source}装：{' '.join(packages)}", flush=True)
    command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', *packages]
    if index_url:
        command += ['-i', index_url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=PIP_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"    装了 {PIP_TIMEOUT // 60} 分钟还没装完，停了")
        return False
    if result.returncode == 0:
        return True
    lines = (result.stderr.strip() or result.stdout.strip()).splitlines()[-PIP_ERROR_LINES:]
    print("    pip 报错（最后几行）：")
    for line in lines:
        print(f"      {line}")
    return False


def check_packages(problems: List[str], pip_source: Optional[str]) -> bool:
    """查 Python 库，缺了就装（官方源通就先官方源、装不上换镜像；官方源不通直接镜像）；这次装了新库返回 True（要重跑才认得）"""
    missing = missing_packages(required_packages())
    if not missing:
        report(PASS, "Python 库都装好了", problems)
        return False
    if os.environ.get(RERUN_FLAG):  # 装完重跑还缺，说明装的跟用的不是同一个 Python，不再装
        report(TODO, f"Python 库装了还是找不到：{'、'.join(missing)}", problems)
        return False
    print(f"{NOTE} 缺 Python 库：{'、'.join(missing)}")
    sources = [PIP_MIRROR] if pip_source == MIRROR else [None, PIP_MIRROR]
    for index_url in sources:
        if install_packages(missing, index_url):
            print("    装好了", flush=True)
            return True
    report(TODO, f"Python 库装不上：{'、'.join(missing)}（官方源和国内镜像都试过，把上面的报错给用户看，商量怎么装）", problems)
    return False


def parse_node_version(text: str) -> Optional[tuple]:
    """'v20.11.1' → (20, 11, 1)；认不出返回 None"""
    match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', text.strip())
    return tuple(int(n) for n in match.groups()) if match else None


def node_version() -> Optional[tuple]:
    """这台电脑的 Node.js 版本；没装或跑不起来返回 None"""
    node = shutil.which('node')
    if not node:
        return None
    try:
        output = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_node_version(output or '')


def check_node(problems: List[str]):
    """Node.js：Playwright MCP 要 18 或更新；只报告不代装"""
    version = node_version()
    hint = NODE_INSTALL.get(platform.system(), '到 nodejs.org 装')
    if version is None:
        report(TODO, f"Node.js 没装（浏览器工具 Playwright MCP 要用）：{hint}，装完重开 AI 平台", problems)
    elif version[0] < NODE_MIN_MAJOR:
        text = '.'.join(str(n) for n in version)
        report(TODO, f"Node.js {text} 太老，至少要 {NODE_MIN_MAJOR}：{hint}，装完重开 AI 平台", problems)
    else:
        report(PASS, f"Node.js {'.'.join(str(n) for n in version)}", problems)


def chrome_path() -> Optional[Path]:
    """电脑上装的 Chrome 在哪；没装返回 None"""
    if platform.system() == 'Windows':
        candidates = [Path(os.environ.get(var, '')) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'
                      for var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA') if os.environ.get(var)]
    else:
        candidates = [Path('/Applications/Google Chrome.app'), Path.home() / 'Applications' / 'Google Chrome.app']
    return next((path for path in candidates if path.exists()), None)


def check_chrome(problems: List[str]):
    """Chrome：Playwright MCP 默认用电脑上装的 Chrome 开一个单独的档案；只报告不代装"""
    path = chrome_path()
    if path:
        report(PASS, f"Chrome：{path}", problems)
    else:
        hint = CHROME_INSTALL.get(platform.system(), '到 google.cn/chrome 装')
        report(TODO, f"Chrome 没装（浏览器工具 Playwright MCP 要用它）：{hint}", problems)


def configured_user_dir() -> Optional[str]:
    """电脑用户文件夹的 .seo-external-link.json 里记的用户目录"""
    if not USER_CONFIG_FILE.exists():
        return None
    try:
        return json.loads(USER_CONFIG_FILE.read_text(encoding='utf-8-sig')).get('user_dir') or None
    except (OSError, ValueError):
        return None


def can_write(folder: Path) -> bool:
    """在文件夹里建一个临时文件试试（马上删掉）"""
    try:
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def check_user_space(problems: List[str]) -> Optional[UserSpace]:
    """用户目录：设置了没有、在不在、能不能写；DataForSEO 账号只看填没填"""
    space = load_user_space()
    if not space:
        recorded = configured_user_dir()
        if recorded:
            report(TODO, f"记的用户目录不在了：{recorded}（问用户现在放哪了，跑菜单 6 重新设置）", problems)
        else:
            report(NOTE, f"还没设置用户目录：第一次用，按 references/setup.md「基础工作准备」做（位置会记在 {USER_CONFIG_FILE}）",
                   problems)
        return None
    if not can_write(space.root):
        report(TODO, f"用户目录写不进去：{space.root}（平台没给写这个文件夹的权限，请用户在平台设置里允许）", problems)
        return space
    report(PASS, f"用户目录：{space.root}", problems)
    if space.dataforseo_account():
        report(PASS, "DataForSEO 账号已填", problems)
    else:
        report(NOTE, f"DataForSEO 账号还没填（只有挖竞品外链要用，到时候请用户自己填进 {space.env_file()}）", problems)
    return space


def _print_by_site(found: Dict[str, List[str]]):
    """按独立站打印外链网站清单"""
    for site, sites in found.items():
        print(f"    {site}：{len(sites)} 个（{'、'.join(sites)}）")


def check_recheck_due(space: UserSpace, problems: List[str]):
    """回访提醒：各独立站今天该每日独立站外链回访的外链网站"""
    day = today_text()
    due = {site: recheck_due(load_ledger(space.ledger_path(site)), day) for site in space.independent_sites()}
    due = {site: sites for site, sites in due.items() if sites}
    if not due:
        report(PASS, f"每日独立站外链回访：今天（{day}）没有要回访的", problems)
        return
    report(NOTE, f"每日独立站外链回访到期：今天（{day}）有 {sum(len(s) for s in due.values())} 个外链网站该回访了", problems)
    _print_by_site(due)
    print("    先问用户要不要现在回访，用户同意就按 references/revisit.md 跑一遍；不同意就接着做用户要做的事")


def check_submit_proof(space: UserSpace, problems: List[str]):
    """提交有没有确认交上：待核实的、已提交却没写证据的单独列出来（都没有就不打印）"""
    ledgers = {site: load_ledger(space.ledger_path(site)) for site in space.independent_sites()}
    unverified = {site: unverified_submissions(ledger) for site, ledger in ledgers.items()}
    unverified = {site: sites for site, sites in unverified.items() if sites}
    missing = {site: missing_submit_evidence(ledger) for site, ledger in ledgers.items()}
    missing = {site: sites for site, sites in missing.items() if sites}
    if unverified:
        report(NOTE, f"提交待核实：{sum(len(s) for s in unverified.values())} 个外链网站提交时没能确认对方收下", problems)
        _print_by_site(unverified)
        print("    回访时先查提交在不在，按 references/revisit.md「待核实的先查提交在不在」处理")
    if missing:
        report(NOTE, f"已提交但没写交上的证据：{sum(len(s) for s in missing.values())} 个外链网站", problems)
        _print_by_site(missing)
        print("    按 references/submit.md「每个外链网站怎么做」第 5 条查一遍，补上 submit_evidence")


def check_user_files(problems: List[str]):
    """用户目录和回访提醒；人工改过的文件（位置文件、设置、台账）写坏了或读不了，记成要处理，不让检查中断"""
    try:
        space = check_user_space(problems)
        if space:
            check_recheck_due(space, problems)
            check_submit_proof(space, problems)
    except (ValueError, OSError) as e:
        report(TODO, f"用户目录里的文件读不了：{e}（照报错里的文件和行号改好再查）", problems)


def main():
    # 输出一律 UTF-8（Windows 默认按 GBK 写，AI 平台按 UTF-8 读就是乱码），编不了的字符用?代替
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    print("开工检查")
    problems: List[str] = []
    if not check_system(problems):
        print(f"\n开工检查：有 {len(problems)} 项要处理（见上面标{TODO}的）")
        sys.exit(1)
    network = check_network(problems)
    if check_packages(problems, network[NET_PIP]):
        print("\n库刚装好，重新跑一遍开工检查：\n", flush=True)
        sys.exit(subprocess.call([sys.executable, str(Path(__file__).resolve())], env={**os.environ, RERUN_FLAG: '1'}))
    check_node(problems)
    check_chrome(problems)
    if MODULE_ERROR and missing_packages(required_packages()):
        print(f"{NOTE} 用户目录和回访提醒要等 Python 库装好才能查")
    elif MODULE_ERROR:  # 库都在还导入失败，是 SKILL 自己的代码有问题
        report(TODO, f"SKILL 程序导入出错：{MODULE_ERROR}", problems)
    else:
        check_user_files(problems)
    if problems:
        print(f"\n开工检查：有 {len(problems)} 项要处理（见上面标{TODO}的）")
        sys.exit(1)
    print("\n开工检查：都通过了")


if __name__ == "__main__":
    main()
