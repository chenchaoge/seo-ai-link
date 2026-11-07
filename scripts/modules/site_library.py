"""
外链库：跑过、看过的外链网站各自什么情况（能不能发外链、怎么发、条件、依据），以后分析别的竞品时先拿来比对
- 分两层：SKILL 默认外链库（assets/library/，作者给的，只读）+ 用户外链库（用户目录 library/，用户新增和更正的）。
  两层合起来才是完整外链库；同一个外链网站两层都有时，以用户外链库为准
- 每层两个文件，一个外链网站一行（JSONL）：可用 usable_sites.jsonl（免费类、付费类），不可用 unusable_sites.jsonl
- 程序改动外链库时只写用户外链库：默认外链库里的外链网站有了新结论，就把整行抄进用户外链库再改
- 只记外链网站本身的事实；从哪个竞品挖出来、看过哪些页面在用户目录的分析结果目录里，独立站收录情况记在台账
- 结论范围 scope：整站 = 对整个外链网站成立，以后再碰到直接用；页面 = 只在某些页面上看到（比如那篇文章评论关了），
  以后碰到这个外链网站别的页面还要重新查。不用局部经验做整体判断
- 来源 source 可信度：提交实测 > 人工复核 > 自动预判；低的不覆盖高的，同级的按查看日期新的覆盖旧的
- 外链网站会变，每条带核对日期 checked_at，提交前还要再看一眼
- 所属行业 industry 是外链网站本身的事实，跟结论分开管：同步结论时不动它，只由 industries.json 或人改
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from modules.classifier import (
    FREE_GROUPS, SCOPE_PAGE, SCOPE_SITE, SETTLED_VERDICTS, SITE_TYPES, SOURCE_AUTO, SOURCE_REVIEW, SOURCE_TESTED,
    VERDICT_FREE, VERDICT_NO, VERDICT_UNKNOWN, Judgement, normalize_group,
)
from modules.industry import is_industry
from modules.link_signals import bare_host

SOURCE_RANK = {SOURCE_AUTO: 1, SOURCE_REVIEW: 2, SOURCE_TESTED: 3}
USABLE, UNUSABLE = 'usable', 'unusable'
# 字段顺序即写文件的顺序；industry = 所属行业（可选值见 config.INDUSTRIES），
# group = 发外链方式，site_type = 业务类型（都只有免费类才有），how = 怎么发外链，
# entry_url = 提交/发布入口，check = 收录条件或要人确认的，paid_option = 免费类另有的付费档（价格等，有内容就同时算收费），
# domain_rank = DataForSEO 域名权重 0-100（看到过的最高值），dofollow = 在这个外链网站上留的链接是不是 dofollow（ugc、sponsored 也算 nofollow；脚本只填空，人看到的直接改），
# noindex = 冷门产品的同类页面会不会被禁止谷歌收录（脚本不填，只由第5步提交前、第6步回访写，见 references/data.md「外链库」noindex）
LIBRARY_FIELDS = ['site', 'verdict', 'industry', 'paid_option', 'group', 'site_type', 'scope', 'how', 'entry_url', 'check',
                  'reason', 'source', 'checked_at', 'first_seen', 'domain_rank', 'dofollow', 'noindex']


def library_file_of(verdict: str) -> str:
    """结论属于哪个文件：不可用进不可用库，免费类和付费类进可用库"""
    return UNUSABLE if verdict == VERDICT_NO else USABLE


def _validate(entry: dict, where: str, file_key: str):
    """校验一行：写错了直接报错，让人改正"""
    verdict = entry.get('verdict')
    entry['group'], entry['site_type'] = normalize_group(entry.get('group'), entry.get('site_type'))  # 旧分组值自动换新
    group, site_type = entry['group'], entry['site_type']
    if not entry.get('site'):
        raise ValueError(f"{where} 缺少 site")
    if verdict not in SETTLED_VERDICTS:
        raise ValueError(f"{where} 的结论 {verdict} 不是 免费类/付费类/不可用")
    if library_file_of(verdict) != file_key:
        raise ValueError(f"{where} 的结论是{verdict}，放错文件了")
    if group and (verdict != VERDICT_FREE or group not in FREE_GROUPS):
        raise ValueError(f"{where} 的发外链方式写错了：{verdict} {group}（只有免费类有，可选 {'/'.join(FREE_GROUPS)}）")
    if site_type and (verdict != VERDICT_FREE or site_type not in SITE_TYPES):
        raise ValueError(f"{where} 的业务类型写错了：{verdict} {site_type}（只有免费类有，可选 {'/'.join(SITE_TYPES)}）")
    if entry.get('industry') is not None and not is_industry(entry['industry']):
        raise ValueError(f"{where} 的所属行业不在清单里：{entry['industry']}（可选值见 references/criteria.md「所属行业」）")
    if entry.get('scope') not in (SCOPE_SITE, SCOPE_PAGE):
        raise ValueError(f"{where} 的结论范围只能是 整站/页面：{entry.get('scope')}")
    if entry.get('source') not in SOURCE_RANK:
        raise ValueError(f"{where} 的来源只能是 {'/'.join(SOURCE_RANK)}：{entry.get('source')}")


def load_library(files: Dict[str, Path]) -> Dict[str, dict]:
    """
    读一层外链库的两个文件，合成 {外链网站: 条目}；文件不存在当空库

    Args:
        files: {'usable': 可用文件路径, 'unusable': 不可用文件路径}
    """
    library = {}
    for file_key, path in files.items():
        if not path.exists():
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                where = f"{path} 第 {lineno} 行"
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{where} 格式写错了：{e.msg}") from e
                _validate(entry, where, file_key)
                if entry['site'] in library:
                    raise ValueError(f"{where}：{entry['site']} 在同一层外链库里出现了两次")
                library[entry['site']] = entry
    return library


def load_libraries(default_files: Dict[str, Path],
                   user_files: Dict[str, Path]) -> Tuple[Dict[str, dict], Dict[str, dict], Set[str]]:
    """
    读两层外链库

    Returns:
        (完整外链库, SKILL 默认外链库, 用户外链库里有的外链网站)；
        完整外链库里的条目是拷贝，原地改它不会动到默认外链库；同一个外链网站以用户外链库为准
    """
    default = load_library(default_files)
    user = load_library(user_files)
    full = {site: dict(entry) for site, entry in default.items()}
    full.update(user)
    return full, default, set(user)


def save_library(files: Dict[str, Path], library: Dict[str, dict]):
    """把一层外链库按结论分到两个文件，各自按外链网站排序，一个外链网站一行（先写临时文件再替换）"""
    for file_key, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({field: entry.get(field) for field in LIBRARY_FIELDS}, ensure_ascii=False)
                 for _, entry in sorted(library.items()) if library_file_of(entry['verdict']) == file_key]
        text = ''.join(line + '\n' for line in lines)
        if path.exists() and path.read_text(encoding='utf-8') == text:  # 内容没变不重写：文件改动时间就是报告右上角的最新更新日期
            continue
        tmp_path = path.with_suffix('.jsonl.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp_path, path)


def save_user_library(user_files: Dict[str, Path], full: Dict[str, dict], default: Dict[str, dict],
                      user_sites: Set[str]) -> int:
    """
    完整外链库改完后写回：只写用户外链库（原来就在用户外链库的，加上跟默认外链库不一样了的），默认外链库不动

    Returns:
        int: 用户外链库现在有几个外链网站
    """
    changed = {site: entry for site, entry in full.items()
               if site in user_sites or site not in default
               or any(entry.get(k) != default[site].get(k) for k in LIBRARY_FIELDS)}
    save_library(user_files, changed)
    return len(changed)


def judge_by_library(library: Dict[str, dict], domain: str) -> Optional[Judgement]:
    """
    外链库里有这个外链网站、结论范围是整站时，直接用库里的结论；页面范围的不复用（别的页面情况可能不一样）
    只按完全相同的外链网站名匹配（去掉 www.），不推到子域名
    """
    entry = library.get(bare_host(domain))
    if not entry or entry.get('scope') != SCOPE_SITE:
        return None
    reason = f"外链库（{entry.get('checked_at')} {entry.get('source')}）：{entry.get('reason')}"
    return Judgement(entry['verdict'], [reason], entry.get('group'), entry.get('check'), SCOPE_SITE,
                     entry.get('site_type'))


def seen_before(entry: Optional[dict], batch_date: str) -> bool:
    """这个外链网站在这批外链之前就看过（库里有，且第一次看到早于这批的日期）"""
    return bool(entry) and bool(entry.get('first_seen')) and entry['first_seen'] < batch_date


def compare_with_library(library: Dict[str, dict], sites: List[str], batch_date: str) -> Dict[str, int]:
    """
    这批外链网站和外链库比对

    Returns:
        dict: total 外链网站数，seen 以前看过的，seen_usable / seen_unusable 分别在哪个文件，reusable 整站结论能直接用的，
              new 新外链网站
    """
    counts = {'total': len(sites), 'seen': 0, 'seen_usable': 0, 'seen_unusable': 0, 'reusable': 0, 'new': 0}
    for site in sites:
        entry = library.get(site)
        if not seen_before(entry, batch_date):
            counts['new'] += 1
            continue
        counts['seen'] += 1
        counts['seen_usable' if library_file_of(entry['verdict']) == USABLE else 'seen_unusable'] += 1
        if entry.get('scope') == SCOPE_SITE:
            counts['reusable'] += 1
    return counts


def apply_industries(library: Dict[str, dict], marks: Dict[str, str]) -> int:
    """
    把 industries.json 判的行业写进完整外链库（原地修改，之后用 save_user_library 写回）；库里还没有的外链网站
    （无法判断的）先不写，等它有了结论进库后再整理结果时补上

    Returns:
        int: 行业有变化的外链网站数
    """
    changed = 0
    for site, industry in marks.items():
        entry = library.get(site)
        if entry is not None and entry.get('industry') != industry:
            entry['industry'] = industry
            changed += 1
    return changed


def _merge_link_facts(entry: dict, info: dict):
    """补上域名权重（取看到过的最高值）和竞品链接属性（自动的只填空，不改已有的值，见 references/data.md「外链库」dofollow）"""
    rank = info.get('domain_rank')
    if rank is not None and (entry.get('domain_rank') is None or rank > entry['domain_rank']):
        entry['domain_rank'] = rank
    if entry.get('dofollow') is None and info.get('dofollow') is not None:
        entry['dofollow'] = info['dofollow']


def _auto_how(site_info: dict) -> Optional[str]:
    """自动预判时能写的"怎么发"：只写分组和入口，没实测过的要说明"""
    if site_info['verdict'] == VERDICT_NO or not site_info.get('entry_url'):
        return None
    return f"{site_info.get('group') or site_info['verdict']}：入口 {site_info['entry_url']}（自动预判，没实测过）"


def sync_library(library: Dict[str, dict], sites: List[dict], batch_date: str) -> Dict[str, int]:
    """
    把一批外链网站的结论并进完整外链库（原地修改，之后用 save_user_library 写回用户外链库）

    - 无法判断的不进库（库里已有的只补域名权重和链接属性）
    - 结论本身就来自库的（整站复用），只补域名权重和链接属性，不改结论
    - 新外链网站加进来，first_seen 记这批外链的日期
    - 已有外链网站：来源更可信，或同样可信但查看日期更新，才替换结论；页面范围的结论不替换整站范围的；
      怎么发、入口这类人写的说明只在新结论带了时才换

    Args:
        library: 完整外链库
        sites: classifier.rollup_by_site 的结果
        batch_date: 这批外链的拉取日期（YYYY-MM-DD）

    Returns:
        dict: added 新增，updated 替换了结论，merged 结论没变
    """
    counts = {'added': 0, 'updated': 0, 'merged': 0}
    for info in sites:
        site, entry = info['site'], library.get(info['site'])
        if info['verdict'] == VERDICT_UNKNOWN or info.get('from_library'):
            if entry:
                _merge_link_facts(entry, info)
                counts['merged'] += 1
            continue
        conclusion = {
            'verdict': info['verdict'], 'group': info.get('group'), 'site_type': info.get('site_type'),
            'scope': info.get('scope') or SCOPE_PAGE, 'check': info.get('check'), 'reason': info.get('reason'),
            'source': info.get('source') or SOURCE_AUTO, 'checked_at': info.get('evidence_at') or batch_date,
        }
        if entry and conclusion['verdict'] == VERDICT_FREE and not conclusion['site_type']:
            conclusion['site_type'] = entry.get('site_type')  # 新结论没定业务类型时，库里人定过的不清掉
        if entry is None:
            entry = {field: None for field in LIBRARY_FIELDS}
            entry.update(conclusion)
            entry.update({'site': site, 'how': _auto_how(info), 'entry_url': info.get('entry_url'),
                          'first_seen': batch_date})
            _merge_link_facts(entry, info)
            library[site] = entry
            counts['added'] += 1
            continue
        _merge_link_facts(entry, info)
        new_rank, old_rank = SOURCE_RANK[conclusion['source']], SOURCE_RANK.get(entry.get('source'), 0)
        newer = (conclusion['checked_at'] or '') > (entry.get('checked_at') or '')
        narrower = entry.get('scope') == SCOPE_SITE and conclusion['scope'] == SCOPE_PAGE  # 某一页的情况不盖整站的事实
        if not narrower and (new_rank > old_rank or (new_rank == old_rank and newer)):
            entry.update(conclusion)
            if info.get('entry_url'):
                entry['entry_url'] = info['entry_url']
            if conclusion['verdict'] == VERDICT_NO:
                entry['how'], entry['paid_option'] = None, None  # 不可用了，怎么发和付费档都没意义
            elif not entry.get('how'):
                entry['how'] = _auto_how(info)
            counts['updated'] += 1
        else:
            counts['merged'] += 1
    return counts
