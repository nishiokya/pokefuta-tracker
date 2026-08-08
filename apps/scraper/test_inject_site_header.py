import importlib.util
import re
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("inject_site_header.py")
SPEC = importlib.util.spec_from_file_location("inject_site_header", MODULE_PATH)
header = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(header)

inject = header.inject

BARE = "<!doctype html><html><head></head><body><main></main></body></html>"


class InjectSiteHeaderTest(unittest.TestCase):
    def test_injects_stylesheet_header_tabs_and_body_class(self):
        result = inject(BARE)
        self.assertIn('href="./assets/site-header.css"', result)
        self.assertIn('class="site-header"', result)
        self.assertIn('class="site-tabs"', result)
        self.assertIn('class="site-footer"', result)
        self.assertIn('<body class="has-site-header">', result)

        mark = re.search(r'<span[^>]*class="site-header__mark"[^>]*>', result)
        self.assertIsNotNone(mark)
        self.assertIn('aria-hidden="true"', mark.group(0))
        self.assertNotIn("DATABASE", result)

    def test_pc_nav_order(self):
        result = inject(BARE)
        # スイッチャーのメニューにも同じ href が出るので、ナビの中だけを見る
        nav = re.search(r'<nav class="site-header__nav".*?</nav>', result, re.DOTALL).group(0)
        result = nav
        positions = [
            result.index('href="./map.html">地図</a>'),
            result.index('href="./pokemon/">ポケモン</a>'),
            result.index('href="./summary/">集計</a>'),
            result.index('href="./character_manholes.html">キャラ蓋</a>'),
        ]
        self.assertEqual(positions, sorted(positions))

    # ── サイトスイッチャー ────────────────────────────────

    def test_brand_is_a_site_switcher(self):
        result = inject(BARE)
        self.assertIn('<details class="site-switch">', result)
        self.assertIn('class="site-header__brand-name">ポケふた', result)
        self.assertIn(">図鑑</span>", result)
        # 写真館へ渡る導線が図鑑側にも必ずあること（従来は片方向だった）
        self.assertIn('href="https://pokefuta.com/?from=data"><b>写真館</b>', result)
        # 図鑑ホームへのリンクは「いま図鑑にいる」というサイト単位の現在地。
        # 図鑑内のどのページでも付くので page は使わない
        self.assertIn('aria-current="true"', result)
        self.assertNotIn('aria-current="page"', result)

    # ── 下タブ ───────────────────────────────────────────

    def test_all_app_links_carry_the_referral_marker(self):
        """pokefuta.com への導線は必ず from=data を付ける（AGENTS.md）。

        都道府県ページからの流入もこのクロム経由になるため、1つでも欠けると
        着地側の source_app=tracker / p_data_referral と突き合わせられなくなる。
        """
        result = inject(BARE)
        links = re.findall(r'href="(https://pokefuta\.com[^"]*)"', result)
        self.assertTrue(links)
        for link in links:
            self.assertIn("from=data", link, f"from=data が無い: {link}")
        # 内部UTMは使わない
        self.assertNotIn("utm_", result)

    def test_stamp_tab_targets_the_stamp_book(self):
        """スタンプ帳タブの行き先。

        ログイン中は直接スタンプ帳へ。未ログインでも session-badge.js が
        redirect にスタンプ帳を積むので、ログイン後にそのまま辿り着く
        （現在の図鑑ページを積むと、もう一度タップさせることになる）。
        """
        result = inject(BARE)
        self.assertIn('data-stamp-page="https://pokefuta.com/visits?from=data"', result)

    def test_signup_opens_the_signup_tab(self):
        """ラベルが「新規登録」なのにログインタブが開く、を防ぐ。"""
        result = inject(BARE)
        self.assertIn('href="https://pokefuta.com/login?from=data&mode=signup">新規登録</a>', result)
        self.assertIn('href="https://pokefuta.com/login?from=data&mode=login">ログイン</a>', result)

    def test_map_only_links_are_reachable_from_the_switcher(self):
        """全画面地図ページはフッターに到達できないので、同じ導線をメニューにも常設する。"""
        result = inject(BARE)
        menu = result[result.index('site-switch__menu'):result.index("</details>")]
        self.assertIn("キャラ蓋", menu)
        self.assertIn("https://pokefuta.com/about?from=data", menu)
        self.assertIn("https://x.com/pokemonmanhole", menu)

    def test_bottom_tabs_match_photo_site_roles(self):
        """左2つが探す系、右端がサイトをまたぐ導線、という並びを写真館と揃える。"""
        result = inject(BARE)
        tabs = re.findall(r'<a class="site-tab[^"]*"[^>]*>.*?<span>([^<]+)</span>', result, re.DOTALL)
        self.assertEqual(tabs, ["地図", "ポケモン", "集計", "スタンプ帳"])
        self.assertIn('data-login-link data-stamp-page="https://pokefuta.com/visits?from=data"', result)

    def test_marks_active_tab_from_page_path(self):
        """図鑑にはアクティブ表現が一切無かったので、現在地を出せることを固定する。"""
        result = inject(BARE, page_path="summary/index.html")
        self.assertIn('<a class="site-header__link is-active" href="./summary/">', result)
        self.assertIn('<a class="site-tab is-active" href="./summary/">', result)
        # 他のタブまで active にしない
        self.assertEqual(result.count("is-active"), 2)

    def test_no_active_marker_for_unknown_page(self):
        result = inject(BARE, page_path="manholes/482/index.html")
        self.assertNotIn("is-active", result)

    # ── 認証 ─────────────────────────────────────────────

    def test_auth_is_separate_from_navigation(self):
        """認証ピルとナビ項目を分離したこと（ラベルが化けないこと）を固定する。"""
        result = inject(BARE)
        self.assertIn("data-auth-guest", result)
        self.assertIn("data-auth-user", result)
        self.assertIn("data-auth-name", result)
        self.assertIn(">ログイン</a>", result)
        self.assertIn(">新規登録</a>", result)
        self.assertIn('href="https://pokefuta.com/profile?from=data"', result)
        # 旧実装の「ログインボタンのラベルがスタンプ帳に化ける」は復活させない。
        # data-stamp-page（遷移先の差し替え）はナビ項目に必要なので残るが、
        # data-stamp-label（ラベルの差し替え）が戻ってきたらこのテストで落とす。
        self.assertNotIn("data-stamp-label", result)
        # 認証ピル自体はラベル差し替えの対象にしない
        self.assertNotIn("data-stamp-page", result[result.index('class="site-auth"'):result.index("</header>")])
        self.assertIn('<script src="./assets/session-badge.js" defer></script>', result)

    def test_info_and_x_links(self):
        result = inject(BARE)
        self.assertIn('href="https://pokefuta.com/about?from=data"', result)
        self.assertIn('href="https://x.com/pokemonmanhole"', result)

    # ── 既存の振る舞い ───────────────────────────────────

    def test_preserves_existing_body_classes(self):
        result = inject('<html><head></head><body class="map-page"></body></html>')
        self.assertIn('<body class="has-site-header map-page">', result)

    def test_does_not_duplicate_shared_header(self):
        shared = '<html><head></head><body><header class="site-header"></header></body></html>'
        self.assertEqual(inject(shared), shared)

    def test_replaces_legacy_top_header(self):
        legacy = """<html><head>
<script src="./assets/session-badge.js" defer></script>
</head><body class="top-page">
<header class="top-app-bar">
  <div><span>ページ固有ヘッダー</span></div>
</header>
<main>本文</main>
</body></html>"""
        result = inject(legacy)
        self.assertIn('href="./assets/site-header.css"', result)
        self.assertIn('<body class="has-site-header top-page">', result)
        self.assertNotIn("top-app-bar", result)
        self.assertNotIn("ページ固有ヘッダー", result)
        self.assertEqual(result.count('class="site-header"'), 1)
        self.assertEqual(result.count('class="site-tabs"'), 1)
        self.assertEqual(result.count("session-badge.js"), 1)

    def test_skips_redirect_documents(self):
        redirect = '<!doctype html><meta http-equiv="refresh" content="0; url=/">'
        self.assertEqual(inject(redirect), redirect)

    def test_chrome_goes_before_body_close(self):
        result = inject(BARE)
        self.assertLess(result.index('class="site-footer"'), result.index("</body>"))
        self.assertLess(result.index('class="site-tabs"'), result.index("</body>"))
        self.assertLess(result.index("<main>"), result.index('class="site-tabs"'))

    def test_uses_relative_paths_for_nested_localized_page(self):
        html = '<html lang="en"><head></head><body></body></html>'
        result = inject(html, asset_base="../../../", page_base="../../")
        self.assertIn('href="../../../assets/site-header.css"', result)
        self.assertIn('href="../../map.html">Map</a>', result)
        self.assertIn('href="../../summary/">Stats</a>', result)
        self.assertIn('href="../../pokemon/">Pokémon</a>', result)
        self.assertIn('href="../../../character_manholes.html">Characters</a>', result)
        self.assertIn('src="../../../assets/session-badge.js"', result)
        self.assertIn(">Login</a>", result)
        self.assertIn(">Sign up</a>", result)
        self.assertIn("<b>Album</b>", result)
        self.assertEqual(result.count('class="site-header__link'), 4)

    def test_every_language_has_the_same_label_keys(self):
        """翻訳漏れがあると .format() が KeyError で落ちるので先に検知する。"""
        expected = set(header.LABELS["ja"])
        for language, labels in header.LABELS.items():
            self.assertEqual(set(labels), expected, f"{language} のラベルが不足/余分")

    def test_injects_for_every_supported_language(self):
        for language in header.LABELS:
            with self.subTest(language=language):
                html = f'<html lang="{language}"><head></head><body></body></html>'
                result = inject(html)
                self.assertIn('class="site-header"', result)
                self.assertIn('class="site-tabs"', result)


if __name__ == "__main__":
    unittest.main()
