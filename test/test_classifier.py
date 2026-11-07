"""
离线测试：用手写 HTML 验证信号提取 + 分类规则（不联网、不花钱）
运行：python test/test_classifier.py
"""

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from modules.classifier import (  # noqa: E402
    GROUP_DIRECT, GROUP_SIGNUP, SUBMIT_UNCHECKED, TYPE_BACKLINK, TYPE_COMMUNITY, TYPE_DIRECTORY, TYPE_SELF,
    VERDICT_FREE, VERDICT_NO, VERDICT_PAID, VERDICT_UNKNOWN, classify_fetch_failure, classify_page,
    classify_submit_page, final_group_of, final_site_type_of, final_verdict_of, normalize_group, rollup_by_site,
)
from modules.link_signals import analyze_submit_page, extract_signals, match_known_platform  # noqa: E402

TARGET = 'https://competitor.com/lp/landing'
PAGE = 'https://blog.example.com/post/1'
COMMENT_FORM = """<form id="commentform" action="/wp-comments-post.php">
  <textarea name="comment"></textarea><input name="author"><input name="email"><input name="url"></form>"""
DIRECTORY_PAGE = '<html><body><a href="/submit">Submit your tool</a></body></html>'
DIRECTORY_URL = 'https://aitools.example.com/tool/competitor'


def judge(html: str, url: str = PAGE, platform_types=None, submit_html: str = None):
    signals = extract_signals(html, url, TARGET)
    submit_page = analyze_submit_page(submit_html) if submit_html else None
    return classify_page(signals, platform_types or [], url, submit_page), signals


class ClassifierTest(unittest.TestCase):

    def test_competitor_link_in_body_comment_form_not_usable(self):
        """竞品链接是编辑写在正文里的，评论框能填网址也不算入口"""
        html = f"""<html><body><article><div class="entry-content">正文
          <a href="https://competitor.com/">Competitor</a></div></article>{COMMENT_FORM}</body></html>"""
        result, signals = judge(html)
        self.assertEqual(result.verdict, VERDICT_NO)
        self.assertEqual(signals['competitor_link']['area'], '正文')
        self.assertIn('评论框', result.reasons[0])

    def test_comment_form_without_url_field_not_unknown(self):
        """竞品链接在正文里时，没有网站栏的评论框不影响判不可用"""
        html = """<html><body><div class="post-content"><a href="https://competitor.com/">Competitor</a></div>
          <form class="comment-form"><textarea name="comment"></textarea></form></body></html>"""
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_NO)

    def test_comment_form_does_not_hide_submit_entry(self):
        """竞品链接在正文、页面也有评论框时，继续往下找提交入口"""
        html = f"""<html><body><div class="entry-content"><a href="https://competitor.com/">Competitor</a></div>
          <a href="/submit">Submit your tool</a>{COMMENT_FORM}</body></html>"""
        result, _ = judge(html, url=DIRECTORY_URL)
        self.assertEqual(result.reasons, [SUBMIT_UNCHECKED])

    def test_competitor_link_in_comment_area(self):
        html = f"""<html><body><div id="comments"><div class="comment-author">
          <a href="https://competitor.com/" rel="external nofollow ugc">Competitor</a></div></div>{COMMENT_FORM}</body></html>"""
        result, signals = judge(html)
        self.assertEqual((result.verdict, result.group, result.site_type), (VERDICT_FREE, GROUP_DIRECT, TYPE_COMMUNITY))
        self.assertIsNone(result.check)
        self.assertEqual(signals['competitor_link']['area'], '评论区')
        self.assertFalse(signals['competitor_link']['dofollow'])

    def test_comment_area_link_without_comment_form(self):
        """评论区有竞品链接但页面没有评论框（如从别处搬来的评论），定不了大类"""
        html = """<html><body><div class="comment-list"><div class="comment-body">
          <a href="https://competitor.com/">Competitor</a></div></div></body></html>"""
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_comment_login_required(self):
        """竞品链接在评论区、评论要登录：免费类，注册账号提交 + 社区论坛类，另记需人工核验"""
        html = """<html><body><div id="comments"><div class="comment-body"><a href="https://competitor.com/">Competitor</a></div>
          <p>You must be logged in to post a comment.</p></div></body></html>"""
        result, _ = judge(html)
        self.assertEqual((result.verdict, result.group, result.site_type), (VERDICT_FREE, GROUP_SIGNUP, TYPE_COMMUNITY))
        self.assertIn('登录', result.check)

    def test_comment_login_text_alone_is_not_entry(self):
        """竞品链接不在评论区时，"登录后评论"不算入口"""
        words = ' '.join(['word'] * 400)
        html = f"""<html><body><article><p>{words}</p><a href="https://competitor.com/">Competitor</a></article>
          <p>You must be logged in to post a comment.</p></body></html>"""
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_NO)

    def test_blog_class_with_postcontent_is_not_forum(self):
        """h-in-q.com 同款结构：btPostContentHolder 不能被当成论坛帖子"""
        html = """<html><body><div class="btPostContentHolder"><div class="btArticleContent"><p>
          <a href="https://competitor.com/">Competitor</a></p></div></div></body></html>"""
        result, signals = judge(html)
        self.assertEqual(signals['competitor_link']['area'], '正文')
        self.assertEqual(result.verdict, VERDICT_NO)

    def test_popup_footer_link_does_not_make_page_sidebar(self):
        """ai.xiaoxinglai.com 同款：一个链接位置不明、一个在弹窗页脚，总区域不算侧边栏/页脚，也不能判不可用"""
        html = """<html><body><div class="site-go"><a href="https://competitor.com/">链接直达</a></div>
          <div class="qrcode-popup-footer"><a href="https://competitor.com/">直接访问</a></div></body></html>"""
        result, signals = judge(html)
        self.assertIsNone(signals['competitor_link']['area'])
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_all_links_in_footer_is_unknown(self):
        """竞品链接全在页脚：可能是友链、广告或合作位，证据不够判不可用"""
        html = '<html><body><p>Article</p><footer><a href="https://competitor.com/">Competitor</a></footer></body></html>'
        result, signals = judge(html)
        self.assertEqual(signals['competitor_link']['area'], '侧边栏/页脚')
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_link_missing_is_unknown(self):
        """页面上找不到竞品链接：看不出它怎么留的，不判不可用"""
        result, _ = judge('<html><body><div class="entry-content">没有链接的正文</div></body></html>')
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_third_party_comments_when_link_missing(self):
        html = '<html><body><p>Article</p><div id="disqus_thread"></div></body></html>'
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_discourse_forum(self):
        html = '<html><head><meta name="generator" content="Discourse 3.2"></head><body>帖子</body></html>'
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_sponsored_link_is_paid(self):
        html = '<html><body><p>Article</p><a href="https://competitor.com/lp/landing" rel="sponsored">x</a></body></html>'
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_PAID)

    def test_editorial_article(self):
        words = ' '.join(['word'] * 400)
        html = f'<html><body><article><p>{words}</p><a href="https://competitor.com/">Competitor</a></article></body></html>'
        result, signals = judge(html)
        self.assertEqual(result.verdict, VERDICT_NO)
        self.assertTrue(signals['competitor_link']['dofollow'])

    def test_js_shell(self):
        html = '<html><body><div id="__next"></div><script>' + 'x' * 6000 + '</script></body></html>'
        result, _ = judge(html)
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_directory_paid_submit_page(self):
        result, signals = judge(DIRECTORY_PAGE, url=DIRECTORY_URL)
        self.assertEqual(result.reasons, [SUBMIT_UNCHECKED])
        paid = analyze_submit_page('<html><body><h1>Pricing</h1><p>Listing $49 one-time fee</p></body></html>')
        self.assertEqual(classify_submit_page(paid, signals['submit_links'][0]).verdict, VERDICT_PAID)

    def test_directory_free_submit_form(self):
        submit_html = """<html><body><p>Submit for free</p><form action="/api/submit">
          <input name="name"><input type="url" name="website"></form></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group, result.scope), (VERDICT_FREE, GROUP_DIRECT, '整站'))
        self.assertEqual(result.site_type, TYPE_DIRECTORY)  # 有提交表单的默认导航与产品发布类

    def test_page_level_scopes(self):
        """评论区、正文、sponsored 只说明这个页面"""
        html = f"""<html><body><div id="comments"><div class="comment-author">
          <a href="https://competitor.com/">Competitor</a></div></div>{COMMENT_FORM}</body></html>"""
        self.assertEqual(judge(html)[0].scope, '页面')
        words = ' '.join(['word'] * 400)
        html = f'<html><body><article><p>{words}</p><a href="https://competitor.com/">Competitor</a></article></body></html>'
        self.assertEqual(judge(html)[0].scope, '页面')
        html = '<html><body><p>Article</p><a href="https://competitor.com/" rel="sponsored">x</a></body></html>'
        self.assertEqual(judge(html)[0].scope, '页面')

    def test_price_and_free_text_is_unknown(self):
        """aitoolly/vanetools 同款：提交页有价格也有 free 字样，看不出有没有免费档"""
        submit_html = """<html><body><p>Free listing or Featured $29.99</p><form action="/api/submit">
          <input name="name"><input type="url" name="website"></form></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual(result.verdict, VERDICT_UNKNOWN)

    def test_backlink_exchange_type(self):
        """airudra 同款：免登录免费表单但要求先挂回链：方式是直接提交，业务类型是要挂回链或徽章"""
        submit_html = """<html><body><h2>Required: Backlink Exchange</h2><form action="/api/submit">
          <input name="name"><input type="url" name="website"></form></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group, result.site_type), (VERDICT_FREE, GROUP_DIRECT, TYPE_BACKLINK))

    def test_explicit_fee_text_is_paid(self):
        """theaitoolsbox 同款：写明每个收录都收费，有 free 字样也判付费类"""
        submit_html = """<html><body><p>Free resources. Every listing has a fee.</p><form action="/api/submit">
          <input type="url" name="website"></form></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual(result.verdict, VERDICT_PAID)

    def test_login_wall_with_free_listing_and_password_form(self):
        """写明免费收录、要登录、有账号密码框：免费类，注册账号提交，登录方式（能用邮箱注册）记进需人工核验"""
        submit_html = """<html><body><h1>Sign in to submit</h1><p>Free listing for every tool.</p>
          <form action="/login"><input type="email" name="email"><input type="password" name="pw"></form></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group, result.site_type), (VERDICT_FREE, GROUP_SIGNUP, TYPE_DIRECTORY))
        self.assertIn('邮箱注册', result.check)

    def test_login_wall_with_oauth_only(self):
        """写明免费收录、只有第三方登录按钮：免费类，注册账号提交，第三方登录方式记进需人工核验"""
        submit_html = """<html><body><p>Sign in to submit. Submit for free.</p>
          <button>Continue with Google</button><button>Continue with GitHub</button></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group), (VERDICT_FREE, GROUP_SIGNUP))
        self.assertIn('第三方账号登录', result.check)

    def test_login_wall_without_free_text_defaults_free(self):
        """要登录、没写收费：有入口就默认免费类，登录后有没有付款步骤记进需人工核验"""
        submit_html = '<html><body><p>Sign in to submit</p><button>Continue with Google</button></body></html>'
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group), (VERDICT_FREE, GROUP_SIGNUP))
        self.assertIn('付款', result.check)

    def test_login_wall_unknown_method(self):
        """要登录、看不出用什么账号登录：注册账号提交，需人工核验写确认登录方式"""
        submit_html = '<html><body><p>Sign in to submit</p></body></html>'
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group), (VERDICT_FREE, GROUP_SIGNUP))
        self.assertIn('确认登录方式', result.check)

    def test_submit_page_without_visible_form_defaults_free(self):
        """productcool 同款：提交页靠脚本加载看不到表单、没写收费，默认免费类"""
        submit_html = '<html><body><div id="__next"></div><script>' + 'x' * 6000 + '</script></body></html>'
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group, result.scope), (VERDICT_FREE, GROUP_DIRECT, '整站'))
        self.assertIn('付款', result.check)

    def test_app_mention_only_goes_to_check(self):
        """提交页提到下载 App 只是可能的信号：默认免费类，需人工核验写确认能不能在网页上提交"""
        submit_html = '<html><body><p>Download the app to list your product.</p></body></html>'
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual(result.verdict, VERDICT_FREE)
        self.assertIn('App', result.check)

    def test_free_submit_beats_sponsored_link(self):
        """moge 同款：竞品是付费推广位，但网站有免费提交入口，有免费选项就不算付费"""
        html = """<html><body><a href="https://competitor.com/" rel="sponsored">x</a>
          <a href="/submit">Submit your tool</a></body></html>"""
        result, _ = judge(html, url=DIRECTORY_URL)
        self.assertEqual(result.reasons, [SUBMIT_UNCHECKED])
        free_html = '<html><body><form action="/api/submit"><input type="url" name="website"></form></body></html>'
        self.assertEqual(judge(html, url=DIRECTORY_URL, submit_html=free_html)[0].verdict, VERDICT_FREE)
        paid_html = '<html><body><h1>Pricing</h1><p>Listing $49 one-time fee</p></body></html>'
        result, _ = judge(html, url=DIRECTORY_URL, submit_html=paid_html)
        self.assertEqual((result.verdict, result.scope), (VERDICT_PAID, '页面'))

    def test_email_submission(self):
        """toolskit 同款：发邮件提交"""
        submit_html = """<html><body><p>To submit a tool, send us the URL by email:
          <a href="mailto:hello@tools.example">hello@tools.example</a></p></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group), (VERDICT_FREE, GROUP_DIRECT))
        self.assertIn('hello@tools.example', result.check)

    def test_pull_request_submission(self):
        """ilovefree 同款：提 PR 提交——要 GitHub 账号（注册账号提交），对方是别人维护的清单（导航与产品发布类）"""
        submit_html = '<html><body><p>Submit Website via a GitHub Pull Request.</p></body></html>'
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group, result.site_type), (VERDICT_FREE, GROUP_SIGNUP, TYPE_DIRECTORY))
        self.assertIn('PR', result.check)

    def test_comment_area_is_community(self):
        """竞品链接在评论区、页面有评论框：直接提交，社区论坛类"""
        html = f"""<html><body><div id="comments"><div class="comment-author">
          <a href="https://competitor.com/">Competitor</a></div></div>{COMMENT_FORM}</body></html>"""
        result, _ = judge(html)
        self.assertEqual((result.verdict, result.group, result.site_type), (VERDICT_FREE, GROUP_DIRECT, TYPE_COMMUNITY))

    def test_legacy_group_values_normalize(self):
        """2026-10 以前只有一个 group 字段：旧值读出来自动拆成新的两个维度，人已经写了业务类型的不覆盖"""
        self.assertEqual(normalize_group('邮箱注册后提交'), (GROUP_SIGNUP, None))
        self.assertEqual(normalize_group('第三方账号登录后提交'), (GROUP_SIGNUP, None))
        self.assertEqual(normalize_group('自建内容'), (GROUP_SIGNUP, TYPE_SELF))
        self.assertEqual(normalize_group('要挂回链或徽章'), (GROUP_DIRECT, TYPE_BACKLINK))
        self.assertEqual(normalize_group('自建内容', TYPE_COMMUNITY), (GROUP_SIGNUP, TYPE_COMMUNITY))
        self.assertEqual(normalize_group(GROUP_DIRECT), (GROUP_DIRECT, None))
        page = {'final_verdict': VERDICT_FREE, 'final_group': '自建内容'}
        self.assertEqual((final_group_of(page), final_site_type_of(page)), (GROUP_SIGNUP, TYPE_SELF))
        page = {'auto_verdict': VERDICT_FREE, 'auto_group': GROUP_DIRECT, 'auto_site_type': TYPE_DIRECTORY}
        self.assertEqual((final_group_of(page), final_site_type_of(page)), (GROUP_DIRECT, TYPE_DIRECTORY))

    def test_requirements_and_captcha_go_to_check_only(self):
        """收录条件和人机验证只记进需人工核验，不改大类"""
        submit_html = """<html><body><p>We only accept voice AI products.</p>
          <form action="/api/submit"><input type="url" name="website"><div class="cf-turnstile"></div></form></body></html>"""
        result, _ = judge(DIRECTORY_PAGE, url=DIRECTORY_URL, submit_html=submit_html)
        self.assertEqual((result.verdict, result.group), (VERDICT_FREE, GROUP_DIRECT))
        self.assertIn('只收某类', result.check)
        self.assertIn('人机验证', result.check)

    def test_rollup_by_site(self):
        """一个免费类页面整站免费；有无法判断的要人看；全是不可用才不可用"""
        def page(url, domain, verdict, group=None):
            return {'url_from': url, 'domain_from': domain, 'auto_verdict': verdict, 'auto_group': group,
                    'auto_reasons': [verdict]}
        pages = [page('https://a.com/1', 'a.com', VERDICT_NO), page('https://www.a.com/2', 'www.a.com', VERDICT_FREE,
                                                                     GROUP_DIRECT),
                 page('https://b.com/1', 'b.com', VERDICT_PAID), page('https://b.com/2', 'b.com', VERDICT_UNKNOWN),
                 page('https://c.com/1', 'c.com', VERDICT_NO), page('https://c.com/2', 'c.com', VERDICT_NO)]
        sites = {s['site']: s for s in rollup_by_site(pages)}
        self.assertEqual((sites['a.com']['verdict'], sites['a.com']['group']), (VERDICT_FREE, GROUP_DIRECT))
        self.assertEqual((sites['a.com']['scope'], sites['a.com']['source']), ('页面', '自动预判'))  # 旧数据没范围按页面
        self.assertEqual(sites['a.com']['page'], 'https://www.a.com/2')
        self.assertEqual(sites['a.com']['page_count'], 2)
        self.assertEqual(sites['b.com']['verdict'], VERDICT_UNKNOWN)
        self.assertEqual(sites['c.com']['verdict'], VERDICT_NO)

    def test_fetch_failure(self):
        self.assertEqual(classify_fetch_failure({'status': 404}).verdict, VERDICT_NO)
        self.assertEqual(classify_fetch_failure({'error': '超时'}).verdict, VERDICT_UNKNOWN)
        self.assertIsNone(classify_fetch_failure({'status': 200, 'is_html': True}))

    def test_final_verdict_prefers_review(self):
        page = {'auto_verdict': VERDICT_UNKNOWN, 'auto_group': None,
                'final_verdict': VERDICT_FREE, 'final_group': GROUP_DIRECT}
        self.assertEqual((final_verdict_of(page), final_group_of(page)), (VERDICT_FREE, GROUP_DIRECT))
        self.assertEqual(final_verdict_of({}), VERDICT_UNKNOWN)

    def test_broken_href_does_not_crash(self):
        html = """<html><body><a href="http://[broken/x">坏链接</a><a href="//[::1/x">坏链接2</a>
          <a href="https://competitor.com/">Competitor</a></body></html>"""
        _, signals = judge(html)
        self.assertTrue(signals['competitor_link']['found'])
        self.assertEqual(signals['competitor_link']['count'], 1)

    def test_known_platform(self):
        blogspot = match_known_platform('someone.blogspot.com')
        self.assertEqual((blogspot['group'], blogspot['site_type']), (GROUP_SIGNUP, TYPE_SELF))
        producthunt = match_known_platform('producthunt.com')
        self.assertEqual((producthunt['group'], producthunt['site_type']), (GROUP_SIGNUP, TYPE_DIRECTORY))
        self.assertIsNone(match_known_platform('some-video-site.net'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
