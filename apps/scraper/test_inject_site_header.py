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


class InjectSiteHeaderTest(unittest.TestCase):
    def test_injects_header_stylesheet_and_body_class(self):
        result = inject("<!doctype html><html><head></head><body><main></main></body></html>")
        self.assertIn('href="./assets/site-header.css"', result)
        self.assertIn('class="site-header"', result)
        mark = re.search(r'<span[^>]*class="site-header__mark"[^>]*>', result)
        self.assertIsNotNone(mark)
        self.assertIn('aria-hidden="true"', mark.group(0))
        self.assertIn('class="site-header__brand-name">ポケふた図鑑</span>', result)
        self.assertNotIn("DATABASE", result)
        pokemon_pos = result.index('href="./pokemon/">ポケモン</a>')
        map_pos = result.index('href="./map.html">')
        summary_pos = result.index('href="./summary/">')
        character_pos = result.index('href="./character_manholes.html">')
        self.assertLess(pokemon_pos, map_pos)
        self.assertLess(map_pos, summary_pos)
        self.assertLess(summary_pos, character_pos)
        self.assertIn('class="site-header__label--desktop">サマリー</span>', result)
        self.assertIn('class="site-header__label--mobile">地図</span>', result)
        self.assertIn('class="site-header__label--mobile">集計</span>', result)
        self.assertIn('class="site-header__label--mobile">キャラ</span>', result)
        self.assertIn('data-stamp-label="スタンプ帳"', result)
        self.assertIn('<body class="has-site-header">', result)

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
        self.assertIn('class="site-header"', result)
        self.assertEqual(result.count('data-stamp-page="https://pokefuta.com/"'), 2)
        self.assertNotIn('data-profile-page=', result)
        self.assertIn('data-stamp-label="スタンプ帳"', result)
        self.assertIn('data-nav-target="login"', result)
        self.assertNotIn("https://pokefuta.com/visits", result)
        self.assertNotIn("https://pokefuta.com/profile", result)
        self.assertIn('<body class="has-site-header top-page">', result)
        self.assertNotIn("top-app-bar", result)
        self.assertNotIn("ページ固有ヘッダー", result)
        self.assertEqual(result.count('class="site-header"'), 1)
        self.assertEqual(result.count("session-badge.js"), 1)

    def test_skips_redirect_documents(self):
        redirect = '<!doctype html><meta http-equiv="refresh" content="0; url=/">'
        self.assertEqual(inject(redirect), redirect)

    def test_uses_relative_paths_for_nested_localized_page(self):
        html = '<html lang="en"><head></head><body></body></html>'
        result = inject(html, asset_base="../../../", page_base="../../")
        self.assertIn('href="../../../assets/site-header.css"', result)
        self.assertIn('href="../../map.html"><span class="site-header__label--desktop">Map</span><span class="site-header__label--mobile">Map</span></a>', result)
        self.assertIn('href="../../summary/"><span class="site-header__label--desktop">Summary</span><span class="site-header__label--mobile">Stats</span></a>', result)
        self.assertIn('href="../../pokemon/">Pokémon</a>', result)
        self.assertIn('href="../../../character_manholes.html"><span class="site-header__label--desktop">Character Manholes</span><span class="site-header__label--mobile">Characters</span></a>', result)
        self.assertEqual(result.count('data-stamp-page="https://pokefuta.com/"'), 2)
        self.assertNotIn('data-profile-page=', result)
        self.assertIn('data-stamp-label="Stamp Book"', result)
        self.assertIn('href="https://pokefuta.com/login?from=data">Login</a>', result)
        self.assertIn('src="../../../assets/session-badge.js"', result)
        self.assertEqual(result.count('class="site-header__link"'), 4)
        self.assertEqual(result.count('site-header__auth-link--desktop'), 1)
        self.assertEqual(result.count('site-header__auth-link--mobile'), 1)

    def test_injects_login_link_for_japanese_page(self):
        result = inject("<!doctype html><html><head></head><body><main></main></body></html>")
        self.assertEqual(result.count('data-stamp-page="https://pokefuta.com/"'), 2)
        self.assertNotIn('data-profile-page=', result)
        self.assertIn('href="https://pokefuta.com/login?from=data">ログイン</a>', result)
        self.assertNotIn("https://pokefuta.com/visits", result)
        self.assertIn('<script src="./assets/session-badge.js" defer></script>', result)


if __name__ == "__main__":
    unittest.main()
