"""
用户目录（用户档案）：SKILL 目录只放作者给的默认档案（代码、文档、SKILL 默认外链库、模板），
用户自己的东西都放用户目录，SKILL 更新、删掉重装都不丢。用户目录的位置由用户定，
记在电脑用户文件夹的 .seo-external-link.json（见 config.USER_CONFIG_FILE）

用户目录结构（第一层只放给用户看的报告网页和说明，中间文件都收进 data/）：
  外链报告.html                  HTML 外链报告（菜单 5 从 SKILL 模板生成），用户双击打开看
  用户档案说明.txt               告诉用户这里都是他的资料、要备份、只在本地（菜单 6 从模板拷）
  data/                         程序自己用的数据，用户不用管
    report/                   报告网页用的样式、脚本和数据 report_data.js（菜单 5 生成）
    settings.json               用户设置：current_site 当前发外链的独立站，default_target 菜单 1 直接回车查的竞品，
                                dataforseo_env_file DataForSEO 账号文件（空着 = data/dataforseo.txt）
    dataforseo.txt              DataForSEO 账号（菜单 6 从模板拷，空的；用户要挖竞品外链时自己填，不经过对话）
    library/                    用户外链库（usable_sites.jsonl、unusable_sites.jsonl）：用户新增和更正的外链网站
    sites/<独立站域名>/          一个独立站一个文件夹：profile.json 提交资料（含所属行业），ledger.json 提交台账，logo 和截图
    analyses/<分析结果目录>/      每查一次竞品一个：raw/ 原始数据、results.json、reviews.json、
                                industries.json 这批外链网站的所属行业、competitor_library.json 竞品专属库、
                                log_<时间>.log 日志
"""

import json
import logging
import os
import secrets
import shutil
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import dotenv_values

from config import LIBRARY_FILE_NAMES, TEMPLATES_DIR, USER_CONFIG_FILE
from modules.link_signals import bare_host
from modules.result_store import load_hand_edited_json

DATA_DIR = 'data'
REPORT_HTML = '外链报告.html'
REPORT_FILES_DIR = 'report'  # 在 data/ 下
SETTINGS_FILE = 'settings.json'
PROFILE_FILE = 'profile.json'
LEDGER_FILE = 'ledger.json'
README_FILE = '用户档案说明.txt'
ENV_FILE = 'dataforseo.txt'  # 用 .txt：双击就是记事本 / 文本编辑；.env 双击打不开，点开头的 Mac 访达还不显示
ENV_KEYS = (('DataForSEO_API_login', 'DATAFORSEO_USERNAME'),  # (账号文件里的键, 老账号文件的键 = 环境变量名)
            ('DataForSEO_API_password', 'DATAFORSEO_PASSWORD'))
SETTINGS_TEMPLATE = TEMPLATES_DIR / SETTINGS_FILE
README_TEMPLATE = TEMPLATES_DIR / README_FILE
ENV_TEMPLATE = TEMPLATES_DIR / ENV_FILE
PROFILE_TEMPLATE = TEMPLATES_DIR / 'site' / PROFILE_FILE
PASSWORD_LENGTH = 12  # 发外链密码长度：外链网站常见要求是至少 8 位、有大小写字母和数字、带一个符号
logging.getLogger('dotenv.main').setLevel(logging.ERROR)  # 账号文件里的说明不是「键=值」，读的时候别刷「could not parse」警告


@dataclass
class UserSpace:
    """一个用户目录里各样东西放在哪"""
    root: Path

    @property
    def data_dir(self) -> Path:
        """程序自己用的数据"""
        return self.root / DATA_DIR

    @property
    def report_html(self) -> Path:
        """HTML 外链报告网页（第一层只有它是给用户看的）"""
        return self.root / REPORT_HTML

    @property
    def report_files_dir(self) -> Path:
        """报告网页用的样式、脚本和数据"""
        return self.data_dir / REPORT_FILES_DIR

    @property
    def readme_path(self) -> Path:
        """用户档案说明（给用户看的，放第一层）"""
        return self.root / README_FILE

    @property
    def settings_path(self) -> Path:
        return self.data_dir / SETTINGS_FILE

    @property
    def library_dir(self) -> Path:
        return self.data_dir / 'library'

    @property
    def library_files(self) -> Dict[str, Path]:
        """用户外链库的两个文件"""
        return {key: self.library_dir / name for key, name in LIBRARY_FILE_NAMES.items()}

    @property
    def sites_dir(self) -> Path:
        return self.data_dir / 'sites'

    @property
    def analyses_dir(self) -> Path:
        return self.data_dir / 'analyses'

    def site_dir(self, site: str) -> Path:
        """独立站的文件夹"""
        return self.sites_dir / site

    def profile_path(self, site: str) -> Path:
        """独立站的提交资料"""
        return self.site_dir(site) / PROFILE_FILE

    def ledger_path(self, site: str) -> Path:
        """独立站的提交台账"""
        return self.site_dir(site) / LEDGER_FILE

    def site_industry(self, site: Optional[str]) -> Optional[str]:
        """独立站的所属行业（profile.json 的 industry），没标或没有档案返回 None"""
        path = self.profile_path(site) if site else None
        return load_hand_edited_json(path).get('industry') if path and path.exists() else None

    def settings(self) -> dict:
        """读用户设置，没有文件当空设置"""
        return load_hand_edited_json(self.settings_path) if self.settings_path.exists() else {}

    def save_settings(self, settings: dict):
        """写用户设置"""
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def current_site(self) -> Optional[str]:
        """当前发外链的独立站（settings.json 的 current_site）"""
        return self.settings().get('current_site') or None

    def independent_sites(self) -> List[str]:
        """用户目录里有哪些独立站：data/sites/ 下有 profile.json 或 ledger.json 的文件夹"""
        if not self.sites_dir.exists():
            return []
        return sorted(p.name for p in self.sites_dir.iterdir()
                      if p.is_dir() and ((p / PROFILE_FILE).exists() or (p / LEDGER_FILE).exists()))

    def env_file(self) -> Path:
        """DataForSEO 账号文件：settings.json 写了就用它，否则用 data/dataforseo.txt"""
        configured = self.settings().get('dataforseo_env_file')
        return Path(configured) if configured else self.data_dir / ENV_FILE

    def dataforseo_account(self) -> Optional[Tuple[str, str]]:
        """
        DataForSEO 账号（API login, API password）：先读账号文件的新键，没有再读老键，再没有看环境变量；
        有一样没填返回 None。只给程序用，不打印
        """
        path = self.env_file()
        values = dotenv_values(path, encoding='utf-8-sig') if path.exists() else {}  # 记事本存的可能带 BOM
        account = tuple(values.get(key) or values.get(env_key) or os.getenv(env_key) for key, env_key in ENV_KEYS)
        return account if all(account) else None


def load_user_space() -> Optional[UserSpace]:
    """读电脑用户文件夹的 .seo-external-link.json 找用户目录；没设置过或目录不在了返回 None"""
    if not USER_CONFIG_FILE.exists():
        return None
    user_dir = (load_hand_edited_json(USER_CONFIG_FILE).get('user_dir') or '').strip()
    if not user_dir or not Path(user_dir).is_dir():
        return None
    return UserSpace(Path(user_dir))


def init_user_space(user_dir: Path) -> UserSpace:
    """
    设置用户目录：建好 data/ 下的各子目录，没有 settings.json、用户档案说明.txt 就从模板拷一份；
    settings.json 没另指 DataForSEO 账号文件时，再拷一份空的 data/dataforseo.txt 等用户自己填；
    最后把位置记进电脑用户文件夹的 .seo-external-link.json。目录里已有的东西一律不动
    """
    user_dir = Path(user_dir).expanduser().resolve()  # 记绝对路径：给的是相对路径，换个目录跑程序也找得到
    space = UserSpace(user_dir)
    for path in (space.library_dir, space.sites_dir, space.analyses_dir):
        path.mkdir(parents=True, exist_ok=True)
    copies = [(SETTINGS_TEMPLATE, space.settings_path), (README_TEMPLATE, space.readme_path)]
    if not space.settings().get('dataforseo_env_file'):
        copies.append((ENV_TEMPLATE, space.env_file()))
    for template, target in copies:
        if not target.exists():
            shutil.copyfile(template, target)
    remember_user_dir(user_dir)
    return space


def remember_user_dir(user_dir: Path):
    """把用户目录的位置记进电脑用户文件夹的 .seo-external-link.json（先写临时文件再替换）"""
    tmp_path = USER_CONFIG_FILE.with_suffix('.json.tmp')
    tmp_path.write_text(json.dumps({'user_dir': str(user_dir)}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp_path, USER_CONFIG_FILE)


def new_password() -> str:
    """生成发外链专用的一次性密码：大小写字母、数字都有，末尾一个 !"""
    alphabet = string.ascii_letters + string.digits
    while True:
        body = ''.join(secrets.choice(alphabet) for _ in range(PASSWORD_LENGTH - 1))
        if any(c.islower() for c in body) and any(c.isupper() for c in body) and any(c.isdigit() for c in body):
            return body + '!'


def create_site(space: UserSpace, raw_site: str) -> Path:
    """
    新建独立站档案：data/sites/<域名>/profile.json 从模板拷，填上域名、网址和程序生成的发外链密码；
    已有的不动，只在 password 空着时补一个（密码直接写进文件，不打印）
    settings.json 还没有当前独立站时，顺手把它设成当前独立站

    Returns:
        Path: profile.json 路径
    """
    site = bare_host(raw_site)
    path = space.profile_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        profile = load_hand_edited_json(path)
        changed = not profile.get('password')
    else:
        profile = load_hand_edited_json(PROFILE_TEMPLATE)
        profile.update({'site': site, 'url': f"https://{site}/"})
        changed = True
    if not profile.get('password'):
        profile['password'] = new_password()
    if changed:
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    settings = space.settings()
    if not settings.get('current_site'):
        settings['current_site'] = site
        space.save_settings(settings)
    return path
