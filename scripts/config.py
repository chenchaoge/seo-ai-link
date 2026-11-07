"""
seo-ai-link 配置（只放 SKILL 自己的设置，跟用户无关）
查竞品页面/网站的外链（DataForSEO），再逐个打开外链所在页面，判断能不能也给独立站留网址
用户自己的设置（当前独立站、默认竞品、DataForSEO 账号文件）在用户目录的 data/settings.json，见 modules/user_space.py
"""

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent  # SKILL 根目录（SKILL.md 所在的文件夹）
ASSETS_DIR = SKILL_DIR / "assets"
# 记用户目录在哪：{"user_dir": "完整路径"}。放在电脑的用户文件夹，不放 SKILL 目录，SKILL 更新、删掉重装都不丢
USER_CONFIG_FILE = Path.home() / ".seo-external-link.json"

# 外链库分两层：SKILL 默认外链库（作者给的，只读）+ 用户外链库（用户目录 data/library/，用户新增和更正的）
LIBRARY_FILE_NAMES = {
    'usable': "usable_sites.jsonl",      # 可用：免费类、付费类
    'unusable': "unusable_sites.jsonl",  # 明确不可用
}
DEFAULT_LIBRARY_FILES = {key: ASSETS_DIR / "library" / name for key, name in LIBRARY_FILE_NAMES.items()}
REPORT_TEMPLATE_DIR = ASSETS_DIR / "report"  # HTML 外链报告模板（按用户目录的样子摆）；直接打开它的外链报告.html = 只有 SKILL 默认外链库的网页
TEMPLATES_DIR = ASSETS_DIR / "templates"     # 用户目录 settings.json、独立站 profile.json 的模板
# 菜单 10 的本机外链报告网页（modules/web_app.py）：只在本机开，别的电脑访问不到；端口被别的程序占了就改这里
WEB_HOST = '127.0.0.1'
WEB_PORT = 8765

# ============================================================================
# 所属行业（赛道）：外链网站、独立站本身是做哪个行业的，发外链先做同赛道、相近赛道的
# 规则见 references/criteria.md「所属行业」；判断逻辑在 modules/industry.py
# 前 24 个参考 Similarweb 一级分类（用户定稿）；同一个赛道大类里的行业互为相近赛道
# ============================================================================

INDUSTRY_GROUPS = {
    '科技': ['AI产品工具', '计算机、电子与科技', '加密货币与区块链'],
    '商业': ['商业与消费者服务', '电商与购物', '金融', '求职与职业', '法律与政府'],
    '文娱': ['艺术与娱乐', '游戏', '新闻与媒体', '体育'],
    '知识': ['科学与教育', '参考资料'],
    '生活': ['社区与社会', '健康', '生活方式', '餐饮', '家居与园艺', '爱好与休闲', '宠物与动物', '旅游', '交通工具'],
    '工业': ['重工业与工程'],
}
CROSS_INDUSTRIES = ['综合导航站', '综合论坛博客']  # 不分行业、什么都收的网站按功能分；只收某个行业的归那个行业（如 AI 工具导航站归 AI产品工具）
INDUSTRIES = [industry for industries in INDUSTRY_GROUPS.values() for industry in industries] + CROSS_INDUSTRIES

# ============================================================================
# 发外链原则（默认就按这个做，用户明确说了自己的做法就照用户的）：分档和排序在 modules/submit_policy.py
# ============================================================================

DAILY_SUBMIT_LIMIT = 10  # 每个独立站每天成功提交最多几个（一天发太多对 SEO 不好），满了当天停，第二天接着发

# ============================================================================
# 外链拉取（DataForSEO Backlinks API：/v3/backlinks/backlinks/live）
# 文档：https://docs.dataforseo.com/v3/backlinks/backlinks/live/
# 费用：每次请求 $0.024 + 每条结果 $0.000036（2026-10-21 账户价格）
# ============================================================================

BACKLINKS_CONFIG = {
    'max_backlinks': 1000,            # 最多拉多少条外链（控制费用），每页最多1000条
    'backlinks_status_type': 'live',  # live=当前还在的外链；all=含已丢失的
    'rank_scale': 'one_hundred',      # 权重用 0-100 分制
    'request_interval': 1,            # 翻页请求间隔秒数
}

# ============================================================================
# 来源页面检查
# ============================================================================

CHECK_CONFIG = {
    'max_pages_per_domain': 3,     # 同一个外链网站最多检查几个页面（按外链权重从高到低取）
    'timeout': 20,                 # 每次打开网页的超时秒数
    'domain_delay': 1.0,           # 同一网站两次请求之间至少间隔秒数
    'max_html_bytes': 5_000_000,   # 网页超过这个大小只取前面部分
    'follow_submit_page': True,    # 发现"提交网站"入口时，顺带打开提交页看要不要付费、要不要登录
    'owned_site_threshold': 10,    # 同一个外链网站给竞品贡献的外链达到这个数，备注"疑似竞品自己的站"
    'user_agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/130.0 Safari/537.36'),
}

# 已知平台：不抓页面直接判免费类（注册登录后都能自己发内容带链接）
# 匹配规则：来源域名等于这里的域名，或是它的子域名（如 xxx.blogspot.com）
# group = 发外链方式、site_type = 业务类型（取值见 modules/classifier.py 的 FREE_GROUPS、SITE_TYPES），
# hint = 判断依据，check = 需人工核验的内容（没有为 None）
KNOWN_PLATFORMS = {
    'github.com': {'group': '注册账号提交', 'site_type': '自建类',
                   'hint': '登录后在 README / Issue / awesome 清单 PR 里可带链接', 'check': None},
    'medium.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己发文章可带链接', 'check': None},
    'dev.to': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己发文章可带链接', 'check': None},
    'hashnode.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己发文章可带链接', 'check': None},
    'hashnode.dev': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己发文章可带链接', 'check': None},
    'substack.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己发文章可带链接', 'check': None},
    'blogspot.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己开博客发文章可带链接', 'check': None},
    'wordpress.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己开博客发文章可带链接', 'check': None},
    'tumblr.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '注册后自己发帖可带链接', 'check': None},
    'reddit.com': {'group': '注册账号提交', 'site_type': '社区论坛类', 'hint': '注册后发帖/评论可带链接',
                   'check': '各版版规不同，发之前看版规'},
    'quora.com': {'group': '注册账号提交', 'site_type': '社区论坛类', 'hint': '注册后回答问题可带链接', 'check': None},
    'news.ycombinator.com': {'group': '注册账号提交', 'site_type': '社区论坛类', 'hint': '注册后可提交链接/评论', 'check': None},
    'producthunt.com': {'group': '注册账号提交', 'site_type': '导航与产品发布类', 'hint': '注册后可发布产品',
                        'check': '只能用 LinkedIn、GitHub、X、谷歌、苹果账号登录，不能用邮箱注册'},
    'indiehackers.com': {'group': '注册账号提交', 'site_type': '社区论坛类', 'hint': '注册后可发帖/建产品页', 'check': None},
    'youtube.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '自己频道的视频简介可放链接', 'check': None},
    'x.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '个人主页/推文可放链接', 'check': None},
    'twitter.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '个人主页/推文可放链接', 'check': None},
    'facebook.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '个人主页/帖子可放链接', 'check': None},
    'linkedin.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '个人主页/文章可放链接', 'check': None},
    'pinterest.com': {'group': '注册账号提交', 'site_type': '自建类', 'hint': '图钉可带链接', 'check': None},
    'huggingface.co': {'group': '注册账号提交', 'site_type': '自建类',
                       'hint': '注册后个人/组织主页资料里的网站栏可填网址', 'check': None},
    'agentskillhub.dev': {'group': '直接提交', 'site_type': '自建类',
                          'hint': '公开 GitHub 仓库里放 SKILL.md，用公开接口导入就发布，不用登录；技能页正文里的链接是 dofollow',
                          'check': None},
}

# ============================================================================
# 页面信号规则（"匹配什么"放这里，"怎么匹配"在 modules/link_signals.py）
# 部分规则借鉴 MIT 开源项目：backlink-gap-finder（垃圾域名）、backlink-pilot（提交/登录入口）、
# claude-seo（脚本渲染页面标记）
# ============================================================================

SIGNAL_RULES = {
    'patterns': {
        # 竞品链接所在区域（看链接外层元素的 id/class）
        'comment_area': r'comment|respond|reply|discussion|disqus',
        # 论坛程序的类名要整词匹配，免得 btPostContentHolder 这种博客类名被当成论坛
        'forum_area': r'forum|\bthread\b|topic-post|topic-body|\bpostbody\b|\bpostcontent\b|message-body|'
                      r'\bbbwrapper\b|\bcooked\b',
        'sidebar_area': r'sidebar|footer|widget|blogroll|partner|sponsor',
        'content_area': (r'entry-content|post-?contents?|article-?(content|body|detail)|post-?body|blog-?content|'
                         r'entry-?body|single-?(post|article)|news-?(content|body|detail)|story-?body'),
        # 评论表单
        'comment_form': r'comment',
        'url_field_name': r'^(url|website|web|site|homepage|home_?page|link|your-?url|author_?url|author-url)$',
        'comment_login_required': (r'must\s+be\s+(logged|signed)\s+in\s+to\s+(post|comment|reply|leave)|'
                                   r'(log|sign)\s*in\s+to\s+(comment|reply|post|leave\s+a\s+comment)'),
        'comments_closed': r'comments\s+are\s+closed|commenting\s+(is\s+)?(closed|disabled)',
        # 提交入口（链接文字 / 链接地址）
        'submit_text': (r'submit\s+(a\s+|your\s+)?(tool|site|website|app|product|startup|link|url|resource|listing)|'
                        r'add\s+(a\s+|your\s+)?(tool|site|website|listing|app|product|startup|link|url|resource)|'
                        r'list\s+your|suggest\s+(a\s+)?(tool|site|website|link|resource)|get\s+listed|^submit$'),
        'submit_href': r'/(submit|add-?(listing|tool|site|website|product|startup|link)|suggest|get-listed|list-your)',
        # 登录/注册入口（链接文字）
        'login_text': r'^(sign\s*up|register|create\s+(an\s+)?account|log\s*in|sign\s*in|join(\s+now|\s+us)?)$',
        # 用户可发内容的迹象（配合登录入口用；不含"发评论"，评论只在竞品链接本身在评论区时才算入口）
        'ugc_text': r'community|forum|write\s+a\s+review|leave\s+a\s+review|ask\s+a\s+question',
        # 用户个人主页路径
        'ugc_path': r'/(user|users|u|member|members|profile|profiles)/',
        # 付费：强信号（任何页面出现都算）
        'paid_strong': (r'sponsored\s+(post|listing|article|content)|paid\s+(listing|submission|placement|post)|'
                        r'featured\s+listing|pay\s+to\s+(submit|list|publish)|submit\s+for\s+\$'),
        # 付费：价格信号（只在提交页上看）
        'paid_price': r'\$\s?\d+|€\s?\d+|\bpricing\b|\bcheckout\b|buy\s+now|one-?time\s+(fee|payment)|per\s+month',
        'free_text': r'\bfree\s+(listing|submission|plan|option|submit)|submit\s+for\s+free|\bfree\b',
        # 要求挂对方徽章/回链（airudra 的 Backlink Exchange、navifyai 的 Important: Backlink 这类说法）
        'reciprocal_text': (r'reciprocal|link\s+back\s+to\s+us|backlink\s+to\s+us|backlink\s+exchange|'
                            r'(add|place|put|placed|embed)\s+our\s+(badge|link|banner|backlink|widget)|'
                            r'important:\s*backlink|添加本站(链接|徽章)'),
        # 提交页上的登录墙（bestaifor 的 Sign in to submit、navifyai 的 Sign In Required、agentery 的 sign in to list、
        # mossai 的 Se connecter 这类说法）
        'login_wall_text': (r'(log|sign)\s*in\s+to\s+(submit|continue|add|list|post|suggest)|please\s+(log|sign)\s*in|'
                            r'create\s+an\s+account\s+to|(sign\s*in|log\s*in|login)\s+required|se\s+connecter|'
                            r'请先登录|登录后(才能)?(提交|发布)'),
        # 以下是 2026-10 发外链时见过的说法，只认字面意思明确的，用在提交页上
        # 写明要交费的（theaitoolsbox 的 Every listing has a fee、boonqo 的 35 tokens to activate）
        'paid_submit_text': (r'every\s+listing\s+has\s+a\s+fee|(listing|submission|review)\s+fee|'
                             r'tokens?\s+to\s+activate|付费(收录|提交)'),
        # 写明免费收录的（比 free_text 严：只认"免费提交/免费收录"，不认页面上随便一个 free）
        'free_listing_text': r'free\s+(listing|submissions?|submit)|submit\s+(for\s+)?free|free\s+to\s+(submit|list)|免费(提交|收录)',
        # 第三方账号登录按钮
        'oauth_text': (r'(continue|sign\s*(in|up)|log\s*in)\s+with\s+(google|github|x|twitter|linkedin|apple|facebook|'
                       r'microsoft|discord)|微信(扫码)?登录|手机号(码)?登录'),
        # 发邮件提交（toolskit：把网址和推荐理由发到 hello@...）
        'email_submit_text': r'(send|email)\s+(us|it|your)|e-?mail\s+(us|to)|via\s+e-?mail|发(送)?邮件(到|至)',
        # 提 PR 提交（ilovefree、awesome 清单）
        'pr_submit_text': r'pull\s+request',
        # 收录条件：只记进需人工核验，不改大类（符不符合要看独立站的情况）
        'free_tier_required': r'free\s+(tier|plan|version)\s+(is\s+)?required|must\s+(have|offer|include)\s+a\s+(permanent\s+)?free',
        'category_limit_text': r'(we\s+)?only\s+(accept|list|feature|include)s?\s+[^.。]{3,50}|仅收录[^。，]{2,30}|只收录[^。，]{2,30}',
        'github_repo_text': r'github\s+(repo|repository)\s+(url|link)|repository\s+url',
        'llms_txt_text': r'llms\.txt',
        'app_only_text': r'扫码下载|download\s+(the|our)\s+app|get\s+the\s+app',
        # 被防爬拦截
        'blocked_text': r'just\s+a\s+moment|cf-chl|checking\s+your\s+browser|attention\s+required|access\s+denied',
    },
    'forum_generators': ['discourse', 'phpbb', 'vbulletin', 'xenforo', 'mybb', 'flarum', 'nodebb',
                         'invision', 'simple machines', 'vanilla forums'],
    'wiki_generators': ['mediawiki', 'dokuwiki', 'tiddlywiki', 'wiki.js'],
    'third_party_comments': ['disqus_thread', 'disqus.com/embed', 'fb-comments', 'giscus', 'utteranc.es',
                             'commento', 'hyvor', 'remark42', 'cusdis'],
    # 人机验证标记（Cloudflare Turnstile、reCAPTCHA、hCaptcha）
    'captcha_markers': ['cf-turnstile', 'challenges.cloudflare.com/turnstile', 'g-recaptcha', 'recaptcha/api.js',
                        'h-captcha', 'hcaptcha.com'],
    # 靠前端脚本渲染的页面标记（借鉴 claude-seo verify_backlinks.py）
    'js_markers': ['<div id="root"', '<div id="app"', '<div id="__next"', '__next_data__', '__nuxt',
                   'ng-app=', 'ng-version=', 'react-root', 'data-reactroot'],
    # 垃圾域名（借鉴 backlink-gap-finder core.py）：自动生成"网站估值/whois"页面的站，没法主动留链接
    'spammy_tlds': ['xyz', 'top', 'click', 'loan', 'work', 'gq', 'tk', 'ml', 'cf', 'ga', 'buzz', 'rest', 'icu', 'cyou'],
    'stat_site_words': r'web-?stats|whois|site-?(value|worth|info|analysis)|domain-?(stats|info)|websiteoutlook|siteprice',
}
