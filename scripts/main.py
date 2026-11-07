"""
seo-ai-link 主程序（菜单启动）
查竞品页面/网站的外链（DataForSEO），逐个打开外链所在页面，自动预判能不能也给独立站留网址
结论分 免费类 / 付费类 / 不可用 / 无法判断；无法判断的按 SKILL.md 的流程人工复核
拉完外链先和外链库比对；每次整理结果把结论和所属行业（industries.json）并进用户外链库，并刷新这次分析的竞品专属库（处理清单）
整理结果时同时把免费类外链网站加进当前独立站的提交台账（默认待提交），发外链的进度记在台账里；
台账待提交的按发外链原则（modules/submit_policy.py）打印各档数量和今天还能发几个，菜单 9 列出排好的发外链顺序
菜单 10 开本机外链报告网页（modules/web_app.py）：数据每次打开现算
SKILL 目录只放默认档案；用户自己的东西（独立站、台账、分析结果、用户外链库、报告）都在用户目录，见 modules/user_space.py
日志写进那一批的分析结果目录；不涉及分析结果目录的菜单只在屏幕上打印
"""

import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 禁用__pycache__目录生成
sys.dont_write_bytecode = True
# 添加模块路径
sys.path.append(str(Path(__file__).parent))

from config import BACKLINKS_CONFIG, CHECK_CONFIG, DEFAULT_LIBRARY_FILES, USER_CONFIG_FILE
from modules.backlink_fetcher import BacklinkFetcher
from modules.classifier import VERDICT_FREE, VERDICT_UNKNOWN, final_verdict_of, rollup_by_site
from modules.competitor_library import competitor_library_path, update_competitor_library
from modules.industry import TRACK_UNKNOWN, industries_path, load_industry_marks
from modules.link_signals import bare_host
from modules.report_builder import generate_default_report, generate_report
from modules.result_store import (
    apply_reviews, create_run_dir, find_latest_run_dir, load_page_reviews, load_results, save_results,
)
from modules.site_library import (
    apply_industries, compare_with_library, load_libraries, save_user_library, seen_before, sync_library,
)
from modules.submission_ledger import load_ledger, merge_into_ledger, save_ledger, sync_industries
from modules.submit_policy import REL_TEXT, TIERS, daily_quota, stale_pending, submit_queue, today_text
from modules.target_resolver import expand_targets
from modules.usability_checker import UsabilityChecker
from modules.user_space import UserSpace, create_site, init_user_space, load_user_space
from modules.web_app import serve

MENU = [
    ("1", "查竞品外链 + 自动预判（会花 DataForSEO 的钱）"),
    ("2", "全部重新预判（只在用户明确要求重判时用：所有页面从头重查，不花钱，保留这个目录的人工复核结论）"),
    ("3", "重新整理结果（人工复核结论写进 reviews.json、所属行业写进 industries.json 后用：结论和行业并进用户外链库，"
          "免费类外链网站进当前独立站的提交台账，刷新竞品专属库）"),
    ("4", "接着查（上次中断没查完时用：只查还没查过的页面，不花钱）"),
    ("5", "生成外链报告（HTML 网页，生成到用户目录：完整外链库 + 各独立站发外链情况，不花钱）"),
    ("6", "设置用户目录（第一次用时：用户档案都放这里）"),
    ("7", "新建独立站档案（在用户目录 data/sites/ 下建文件夹和提交资料模板）"),
    ("8", "刷新 SKILL 自带的外链库网页（只读 SKILL 默认外链库，作者改了默认外链库后用）"),
    ("9", "看发外链顺序（第5步用：当前独立站台账里待提交的按发外链原则排好，今天还能发几个，不花钱）"),
    ("10", "打开外链报告网页（本机网页，打开、刷新就是最新数据，不用先跑菜单 5）"),
    ("0", "退出"),
]
LOGGER_NAME = 'seo_ai_link'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'


def read_input(prompt: str, eof_default: Optional[str] = None) -> str:
    """读一行输入：去掉 PowerShell 管道带进来的 BOM 和首尾空白、引号；没有输入了（EOF）时有 eof_default 就用它，否则退出"""
    try:
        return input(prompt).replace('﻿', '').strip().strip('"').strip("'")  # ﻿ = BOM
    except EOFError:
        if eof_default is not None:
            print()
            return eof_default
        print("\n没有更多输入，退出")
        sys.exit(1)


def show_menu() -> str:
    """显示菜单，返回用户选择"""
    print()
    print("=" * 50)
    print("seo-ai-link")
    print("=" * 50)
    for key, text in MENU:
        print(f"{key}. {text}")
    print()
    keys = [key for key, _ in MENU]
    while True:
        choice = read_input(f"请选择 ({'/'.join(keys)}): ")
        if choice in keys:
            return choice
        print(f"无效输入，请输入 {'、'.join(keys)} 之一")


def require_space() -> Optional[UserSpace]:
    """要用用户目录的功能先确认设置过；没设置过就提示用菜单 6"""
    space = load_user_space()
    if space is None:
        print(f"还没设置用户目录（或记的目录不在了）：先用菜单 6 设置。位置记在 {USER_CONFIG_FILE}")
    return space


def ask_target(space: UserSpace) -> List[str]:
    """输入竞品网址或域名（直接回车用 settings.json 的 default_target），展开成要依次查询的目标列表"""
    default_target = space.settings().get('default_target')
    print("输入页面网址：先查这个页面，再查它所在域名（子域名就查子域名，否则查主域名）")
    print("输入域名：只查这个域名")
    hint = f"直接回车 = {default_target}" if default_target else "settings.json 没设 default_target，必须输入"
    raw = read_input(f"请输入竞品网址或域名（{hint}）: ") or default_target
    if not raw:
        print("没有输入竞品，退出")
        sys.exit(1)
    return expand_targets(raw)


def ask_reuse_old() -> bool:
    """用不用以前的结论（外链库的整站结论、以前人工复核过的同一页面）；直接回车或没有这一行输入 = 用"""
    print("以前的结论：外链库的整站结论、以前分析结果目录里人工复核过的同一页面")
    raw = read_input("用以前的结论吗？（直接回车 = 用；输入 n = 不用，全部重新判断）: ", eof_default='')
    return raw.lower() != 'n'


def ask_run_dir(space: UserSpace) -> Optional[Path]:
    """输入分析结果目录，直接回车用最新一次"""
    latest = find_latest_run_dir(space.analyses_dir)
    hint = latest if latest else "无"
    raw = read_input(f"请输入分析结果目录（直接回车 = 最新一次: {hint}）: ")
    run_dir = Path(raw) if raw else latest
    if not run_dir or load_results(run_dir) is None:
        print(f"找不到结果文件: {run_dir}")
        return None
    return run_dir


def setup_logging() -> logging.Logger:
    """日志先只输出到控制台；知道是哪一批分析结果目录后，用 log_to_run_dir 同时写进那一批的目录"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return logger


def log_to_run_dir(logger: logging.Logger, run_dir: Path) -> Path:
    """日志同时写进这一批分析结果目录的 log_<时间戳>.log；换一批（菜单 1 查多个目标）就换到新一批的目录"""
    for old in [h for h in logger.handlers if isinstance(h, logging.FileHandler)]:
        logger.removeHandler(old)
        old.close()
    log_file = run_dir / f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.info(f"日志文件: {log_file}")
    return log_file


def load_credentials(space: UserSpace, logger: logging.Logger) -> Optional[tuple]:
    """读 DataForSEO 账号（账号文件 → 环境变量）；没填就提示用户自己填进账号文件"""
    account = space.dataforseo_account()
    if not account:
        logger.error(f"DataForSEO 账号还没填：请用户自己打开 {space.env_file()}，"
                     f"把 API login、API password 分别粘贴到「DataForSEO_API_login=」「DataForSEO_API_password=」后面")
    return account


def site_titles(pages: List[dict]) -> Dict[str, str]:
    """每个外链网站取一个 DataForSEO 记的页面标题，给 AI 判断所属行业参考"""
    titles = {}
    for page in pages:
        site, title = bare_host(page['domain_from']), (page.get('backlink') or {}).get('page_from_title')
        if title and site not in titles:
            titles[site] = ' '.join(title.split())
    return titles


def log_industries(run_dir: Path, pages: List[dict], sites: List[dict], industries: Dict[str, Optional[str]],
                   logger: logging.Logger):
    """打印这批外链网站按所属行业的数量，和还没标行业的清单（AI 判断后写进这批的 industries.json）"""
    counts = Counter(industries.get(s['site']) or TRACK_UNKNOWN for s in sites)
    logger.info("按所属行业：" + "，".join(f"{k} {v}" for k, v in counts.most_common()))
    missing = [s for s in sites if not industries.get(s['site'])]
    if not missing:
        return
    titles = site_titles(pages)
    logger.info(f"所属行业还没标的外链网站 {len(missing)} 个，判断后写进 {industries_path(run_dir)}"
                f"（格式 {{\"外链网站\": \"行业\"}}，可选值和判断方法见 references/criteria.md「所属行业」）：")
    for s in missing:
        logger.info(f"  {s['site']} | {s['verdict']} | {titles.get(s['site']) or '没有页面标题'}")


def print_summary(run_dir: Path, data: dict, sites: List[dict], industries: Dict[str, Optional[str]],
                  logger: logging.Logger):
    """
    打印按外链网站的结论统计、免费类按发外链方式和业务类型的统计、按所属行业的统计和还没标行业的清单、
    要人工复核的外链网站清单（结论是无法判断的）
    """
    pages = data.get('pages') or []
    logger.info("=" * 50)
    page_counts = Counter(final_verdict_of(p) for p in pages)
    site_counts = Counter(s['verdict'] for s in sites)
    logger.info(f"检查页面 {len(pages)} 个，来自 {len(sites)} 个外链网站")
    logger.info("按外链网站：" + "，".join(f"{k} {v}" for k, v in site_counts.items()))
    logger.info("按页面：" + "，".join(f"{k} {v}" for k, v in page_counts.items()))
    free_sites = [s for s in sites if s['verdict'] == VERDICT_FREE]
    groups = Counter(s['group'] or '没写方式' for s in free_sites)
    types = Counter(s.get('site_type') or '没写类型' for s in free_sites)
    if free_sites:
        logger.info("免费类外链网站按发外链方式：" + "，".join(f"{k} {v}" for k, v in groups.items()))
        logger.info("免费类外链网站按业务类型：" + "，".join(f"{k} {v}" for k, v in types.items()))
    pending = [s for s in sites if s['verdict'] == VERDICT_UNKNOWN]
    if pending:
        logger.info(f"无法判断的外链网站 {len(pending)} 个，要人工复核（按 seo-ai-link SKILL 处理）：")
        for s in pending:
            logger.info(f"  {s['site']}（{s['page_count']} 个页面）| {s['page']} | {s['reason']}")
    log_industries(run_dir, pages, sites, industries, logger)
    logger.info(f"分析结果目录: {run_dir}")


def batch_date_of(data: dict) -> str:
    """这批外链的拉取日期（YYYY-MM-DD）"""
    return (data.get('created_at') or datetime.now().strftime('%Y-%m-%d'))[:10]


def update_library(space: UserSpace, run_dir: Path, data: dict, sites: List[dict],
                   logger: logging.Logger) -> Tuple[Dict[str, dict], Dict[str, str], set]:
    """
    把这批外链网站的结论、industries.json 判的所属行业并进用户外链库

    Returns:
        (完整外链库, industries.json 判的行业, 这批之前就在外链库里的外链网站)
    """
    library, default, user_sites = load_libraries(DEFAULT_LIBRARY_FILES, space.library_files)
    batch_date = batch_date_of(data)
    seen = {s['site'] for s in sites if seen_before(library.get(s['site']), batch_date)}  # 并库之前先记下
    counts = sync_library(library, sites, batch_date)
    marks = load_industry_marks(run_dir, logger)
    marked = apply_industries(library, marks)
    user_count = save_user_library(space.library_files, library, default, user_sites)
    logger.info(f"外链库：新增 {counts['added']} 个外链网站，更新结论 {counts['updated']} 个，结论没变 {counts['merged']} 个；"
                f"用户外链库现有 {user_count} 个，完整外链库共 {len(library)} 个")
    if marks:
        logger.info(f"所属行业：industries.json 判了 {len(marks)} 个外链网站，外链库里行业有变化的 {marked} 个")
    return library, marks, seen


def industry_map(library: Dict[str, dict], marks: Dict[str, str]) -> Dict[str, Optional[str]]:
    """每个外链网站的所属行业：外链库里的为准，库里还没有的（无法判断的）用 industries.json 判的"""
    industries = dict(marks)
    industries.update({site: entry['industry'] for site, entry in library.items() if entry.get('industry')})
    return industries


def log_submit_plan(ledger: Dict[str, dict], library: Dict[str, dict], site: str, site_industry: Optional[str],
                    logger: logging.Logger):
    """打印台账里待提交的外链网站按发外链原则各档的数量、今天还能发几个（第5步按档的顺序发，菜单 9 看排好的顺序）"""
    if not site_industry:
        logger.warning(f"{site} 的档案还没标所属行业（profile.json 的 industry），算不出赛道关系，发外链顺序排不了；"
                       f"按 references/criteria.md「所属行业」判断后补上")
        return
    queue = submit_queue(ledger, library, site_industry)
    counts = Counter(item['tier'] for item in queue)
    quota = daily_quota(ledger, today_text())
    logger.info(f"{site}（{site_industry}）台账待提交 {len(queue)} 个，按发外链原则："
                + ("，".join(f"{tier} {counts[tier]}" for tier in TIERS if counts[tier]) or "没有"))
    unconfirmed = sum(1 for item in queue if item['needs_confirm'])
    if unconfirmed:
        logger.info(f"其中还没问过用户的（其他赛道、付费）{unconfirmed} 个：排到它们时先列给用户定发不发")
    log_stale_pending(ledger, library, logger.warning)
    logger.info(f"今天（{quota['day']}）已成功提交 {quota['submitted']} 个，每天最多 {quota['limit']} 个，"
                f"还能发 {quota['left']} 个；菜单 9 看排好的发外链顺序")


def log_stale_pending(ledger: Dict[str, dict], library: Dict[str, dict], out):
    """台账里待提交但已经发不了的（外链库判成不可用、没写结论）：单独列出来，按铁律改成跳过"""
    stale = stale_pending(ledger, library)
    if stale:
        out(f"台账里待提交但已经发不了的 {len(stale)} 个（外链库判成不可用或没写结论），按铁律把台账那行改成跳过："
            + "，".join(f"{s['site']}（{s['verdict'] or '没写结论'}）" for s in stale))


def add_free_to_ledger(space: UserSpace, site: Optional[str], data: dict, industries: Dict[str, Optional[str]],
                       logger: logging.Logger) -> Dict[str, dict]:
    """
    第4步边界：把这批免费类外链网站导入当前独立站的提交台账（默认待提交，带上已知的提交入口、发外链方式和业务类型），
    台账每行的所属行业跟外链库同步

    Returns:
        当前独立站的台账；没有当前独立站返回空台账
    """
    if not site:
        logger.warning("settings.json 没写 current_site（当前发外链的独立站），这次免费类外链网站没进任何台账")
        return {}
    path = space.ledger_path(site)
    ledger = load_ledger(path)
    counts = merge_into_ledger(ledger, data.get('pages') or [], data['target'])
    synced = sync_industries(ledger, industries)
    save_ledger(path, ledger)
    logger.info(f"{site} 的提交台账：新增 {counts['added']} 个免费类外链网站（默认待提交），已有的补来源 {counts['updated']} 个，"
                f"同步所属行业 {synced} 个，台账共 {len(ledger)} 个外链网站: {path}")
    return ledger


def refresh_competitor_library(space: UserSpace, run_dir: Path, data: dict, sites: List[dict], seen: set,
                               ledger: Dict[str, dict], site: Optional[str], industries: Dict[str, Optional[str]],
                               logger: logging.Logger):
    """刷新这次分析的竞品专属库（处理方式按当前独立站的台账同步，赛道关系按当前独立站的所属行业算）"""
    path = competitor_library_path(run_dir)
    handling = update_competitor_library(path, data, sites, seen, ledger, site, industries, space.site_industry(site))
    open_count = handling.pop('open')
    logger.info("竞品专属库处理方式：" + "，".join(f"{k} {v}" for k, v in handling.items())
                + f"；还没处理完的 {open_count} 个: {path}")


def organize_results(space: UserSpace, run_dir: Path, data: dict, logger: logging.Logger):
    """
    整理结果：合并 reviews.json 的人工结论 → 保存 → 结论和所属行业并进用户外链库 → 免费类进台账（同步行业）
    → 按发外链原则打印台账各档数量 → 刷新竞品专属库 → 打印统计
    """
    apply_reviews(run_dir, data, logger)
    save_results(run_dir, data)
    sites = rollup_by_site(data.get('pages') or [])
    library, marks, seen = update_library(space, run_dir, data, sites, logger)
    industries = industry_map(library, marks)
    site = space.current_site()
    ledger = add_free_to_ledger(space, site, data, industries, logger)  # 先进台账，刷新专属库时才会显示「台账：待提交」
    if site:
        log_submit_plan(ledger, library, site, space.site_industry(site), logger)
    refresh_competitor_library(space, run_dir, data, sites, seen, ledger, site, industries, logger)
    print_summary(run_dir, data, sites, industries, logger)


def make_checker(space: UserSpace, logger: logging.Logger, reuse_old: bool = True) -> UsabilityChecker:
    """建页面检查器（带上完整外链库）；库写错会直接报错，放在花钱拉外链之前"""
    library, _, user_sites = load_libraries(DEFAULT_LIBRARY_FILES, space.library_files)
    logger.info(f"完整外链库 {len(library)} 个外链网站（其中用户外链库 {len(user_sites)} 个）")
    if not reuse_old:
        logger.info("这次不用以前的结论（用户要求重新判断）：外链库的整站结论、以前人工复核过的同一页面都不用")
    return UsabilityChecker(CHECK_CONFIG, logger, library, reuse_old)


def old_page_reviews(space: UserSpace, checker: UsabilityChecker, run_dir: Path) -> Optional[dict]:
    """要用以前的结论时，读以前别的分析结果目录里人工复核过的页面结论；不用时返回 None"""
    return load_page_reviews(space.analyses_dir, run_dir) if checker.reuse_old else None


def log_library_compare(checker: UsabilityChecker, data: dict, logger: logging.Logger):
    """第一步：这批外链网站和外链库比对，打印以前看过几个、整站结论能直接用几个、新外链网站几个"""
    sites = sorted({bare_host(p['domain_from']) for p in data.get('pages') or []})
    c = compare_with_library(checker.library, sites, batch_date_of(data))
    reusable = c['reusable'] if checker.reuse_old else 0
    logger.info(f"和外链库比对：外链网站 {c['total']} 个，以前看过 {c['seen']} 个（可用 {c['seen_usable']}、"
                f"不可用 {c['seen_unusable']}；整站结论直接用 {reusable} 个），新外链网站 {c['new']} 个")


def run_targets(space: UserSpace, targets: List[str], logger: logging.Logger, reuse_old: bool):
    """菜单1：按顺序逐个查竞品（页面网址 → 所在域名），每个目标各出一个分析结果目录"""
    credentials = load_credentials(space, logger)
    if not credentials:
        return
    checker = make_checker(space, logger, reuse_old)
    logger.info(f"本次依次查询 {len(targets)} 个目标: {' → '.join(targets)}")
    run_dirs = []
    for idx, target in enumerate(targets, 1):
        logger.info(f"========== 第 {idx}/{len(targets)} 个目标: {target} ==========")
        run_dirs.append(run_fetch_and_check(space, target, credentials, checker, logger))
    if len(targets) > 1:
        logger.info("全部分析结果目录：")
        for target, run_dir in zip(targets, run_dirs):
            logger.info(f"  {target} → {run_dir}")


def run_fetch_and_check(space: UserSpace, target: str, credentials: tuple, checker: UsabilityChecker,
                        logger: logging.Logger) -> Path:
    """查一个目标：拉外链 → 自动预判 → 整理结果，返回分析结果目录"""
    run_dir = create_run_dir(space.analyses_dir, target)
    log_to_run_dir(logger, run_dir)
    data = {'target': target, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'reuse_old': checker.reuse_old, 'fetch': None, 'backlinks': [], 'pages': []}  # reuse_old 给菜单 4 接着查用
    save_results(run_dir, data)
    logger.info(f"目标: {target}，分析结果目录: {run_dir}")

    fetched = BacklinkFetcher(*credentials, logger).fetch(target, BACKLINKS_CONFIG, run_dir / 'raw')
    data['fetch'] = {'total_count': fetched['total_count'], 'fetched': len(fetched['items']),
                     'cost': fetched['cost'], 'error': fetched['error']}
    data['backlinks'] = fetched['items']
    save_results(run_dir, data)
    if not fetched['items']:
        logger.error(f"没有拿到外链，这个目标结束（错误: {fetched['error']}）")
        return run_dir

    data['pages'] = checker.build_pages(data['backlinks'], page_reviews=old_page_reviews(space, checker, run_dir))
    save_results(run_dir, data)
    log_library_compare(checker, data, logger)
    checker.run(run_dir, data, target)
    organize_results(space, run_dir, data, logger)
    return run_dir


def run_recheck(space: UserSpace, run_dir: Path, logger: logging.Logger, reuse_old: bool):
    """菜单2：用已拉好的外链重跑自动预判（保留这个分析结果目录自己的人工复核结论）"""
    data = load_results(run_dir)
    checker = make_checker(space, logger, reuse_old)
    data['reuse_old'] = reuse_old
    data['pages'] = checker.build_pages(data['backlinks'], data.get('pages'), old_page_reviews(space, checker, run_dir))
    save_results(run_dir, data)
    log_library_compare(checker, data, logger)
    checker.run(run_dir, data, data['target'])
    organize_results(space, run_dir, data, logger)


def run_resume(space: UserSpace, run_dir: Path, logger: logging.Logger):
    """菜单4：只查上次中断时还没查的页面，查完整理结果"""
    data = load_results(run_dir)
    checker = make_checker(space, logger, data.get('reuse_old', True))  # 跟这批第一次跑时的选择一致
    checker.run(run_dir, data, data['target'], skip_checked=True)
    organize_results(space, run_dir, data, logger)


def run_organize(space: UserSpace, run_dir: Path, logger: logging.Logger):
    """菜单3：合并人工复核结论，重新整理结果（免费类外链网站同时进当前独立站的提交台账）"""
    organize_results(space, run_dir, load_results(run_dir), logger)


def run_report(space: UserSpace):
    """菜单5：在用户目录生成 HTML 外链报告（拷 SKILL 模板 + 写数据）"""
    result = generate_report(space)
    sites = "，".join(f"{site} {count} 个" for site, count in result['independent_sites'].items()) or "还没有独立站"
    print(f"完整外链库 {result['library']} 个外链网站（用户外链库 {result['user_library']} 个）；各独立站台账：{sites}")
    print(f"数据已写入 {result['path']}")
    print(f"双击打开报告：{result['index']}")


def run_setup_user_dir():
    """菜单6：设置用户目录（建 data/、settings.json 和空的 DataForSEO 账号文件，位置记进电脑用户文件夹的
    .seo-external-link.json），顺手生成外链报告"""
    current = load_user_space()
    hint = f"（现在是 {current.root}）" if current else ""
    raw = read_input(f"请输入用户目录完整路径{hint}: ")
    if not raw:
        print("没有输入路径，退出")
        return
    space = init_user_space(Path(raw))
    print(f"用户目录已设置: {space.root}")
    print(f"用户设置在 {space.settings_path}：current_site 当前独立站、default_target 默认竞品、"
          f"dataforseo_env_file DataForSEO 账号文件")
    print(f"DataForSEO 账号文件: {space.env_file()}（挖竞品外链才要，用户自己填）")
    run_report(space)


def run_new_site():
    """菜单7：新建独立站档案"""
    space = require_space()
    if not space:
        return
    raw = read_input("请输入独立站域名（如 example.com）: ")
    if not raw:
        print("没有输入域名，退出")
        return
    path = create_site(space, raw)
    print(f"独立站档案: {path}（提交资料照 references/submit.md「准备」填；logo、截图放同一个文件夹）")
    print("发外链密码: 存在档案的 password 里（空着时程序自动生成；一次性密码，不用记，想换就直接改档案）")
    print(f"当前独立站: {space.current_site()}（换别的独立站发外链就改 {space.settings_path} 的 current_site）")


def run_submit_order(space: UserSpace):
    """菜单9：当前独立站台账里待提交的外链网站按发外链原则排好，打印今天还能发几个（第5步每发一个前看）"""
    site = space.current_site()
    if not site:
        print(f"{space.settings_path} 没写 current_site（当前发外链的独立站）")
        return
    site_industry = space.site_industry(site)
    if not site_industry:
        print(f"{site} 的档案还没标所属行业（profile.json 的 industry），算不出赛道关系，发外链顺序排不了；"
              f"按 references/criteria.md「所属行业」判断后补上")
        return
    library, _, _ = load_libraries(DEFAULT_LIBRARY_FILES, space.library_files)
    ledger = load_ledger(space.ledger_path(site))
    queue = submit_queue(ledger, library, site_industry)
    quota = daily_quota(ledger, today_text())
    print(f"{site}（所属行业：{site_industry}）台账待提交 {len(queue)} 个，按发外链原则排好，从上往下发")
    print(f"今天（{quota['day']}）已成功提交 {quota['submitted']} 个，每天最多 {quota['limit']} 个，还能发 {quota['left']} 个"
          + ("；今天满了，明天接着发" if not quota['left'] else ""))
    unconfirmed = [item['site'] for item in queue if item['needs_confirm']]
    if unconfirmed:
        print(f"其他赛道、付费的还没问过用户的 {len(unconfirmed)} 个（标了「先问用户」）：排到第一个时停下，把这些一次列给用户定发不发；"
              f"要发的在台账那行写 \"user_confirmed\": true，不发的改跳过")
    log_stale_pending(ledger, library, print)
    for tier, desc in TIERS.items():
        items = [(i, item) for i, item in enumerate(queue, 1) if item['tier'] == tier]
        if items:
            print(f"{tier}：{desc}，{len(items)} 个")
        for i, item in items:
            rank = item['domain_rank'] if item['domain_rank'] is not None else '没记录'
            print(f"  {i}. {item['site']} | {item['track']} | {item['industry'] or TRACK_UNKNOWN} | "
                  f"{REL_TEXT[item['dofollow']]} | 权重 {rank} | {item['group'] or '没写方式'} | "
                  f"{item['submit_url'] or '没有提交入口'}" + (" | 先问用户" if item['needs_confirm'] else ""))


def run_default_report():
    """菜单8：刷新 SKILL 自带的外链库网页（只读 SKILL 默认外链库）"""
    result = generate_default_report()
    print(f"SKILL 默认外链库 {result['library']} 个外链网站，数据已写入 {result['path']}")
    print(f"双击打开：{result['index']}")


def main():
    # 输入输出一律 UTF-8（输入带不带 BOM 都行）：Windows 默认按本机编码（中文系统是 GBK）读写管道，
    # AI 平台按 UTF-8 读就是乱码，中文路径也会读错；Mac 本来就是 UTF-8。输出里编不了的字符用?代替，避免中途报错
    sys.stdin.reconfigure(encoding='utf-8-sig')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    # 菜单和输入在初始化日志之前完成
    choice = show_menu()
    simple = {"0": lambda: print("退出"), "6": run_setup_user_dir, "7": run_new_site, "8": run_default_report}
    if choice in simple:
        simple[choice]()
        return
    space = require_space()
    if not space:
        return
    if choice == "5":
        run_report(space)
        return
    if choice == "9":
        run_submit_order(space)
        return
    if choice == "10":
        serve()  # 一直开着，直到程序被关掉
        return
    targets, run_dir = None, None
    if choice == "1":
        targets = ask_target(space)
    else:
        run_dir = ask_run_dir(space)
        if not run_dir:
            return
    reuse_old = ask_reuse_old() if choice in ("1", "2") else True

    logger = setup_logging()
    if run_dir:
        log_to_run_dir(logger, run_dir)  # 菜单 1 的分析结果目录要等建好后才有，在 run_fetch_and_check 里换
    try:
        if choice == "1":
            run_targets(space, targets, logger, reuse_old)
        elif choice == "2":
            run_recheck(space, run_dir, logger, reuse_old)
        elif choice == "4":
            run_resume(space, run_dir, logger)
        else:
            run_organize(space, run_dir, logger)
    except KeyboardInterrupt:
        logger.info("用户中断（已判完的页面都已保存在 results.json，用菜单 4 接着查）")


if __name__ == "__main__":
    main()
