import importlib.util
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
        self.assertIn('href="./map.html">マップ</a>', result)
        self.assertIn('<body class="has-site-header">', result)

    def test_preserves_existing_body_classes(self):
        result = inject('<html><head></head><body class="map-page"></body></html>')
        self.assertIn('<body class="has-site-header map-page">', result)

    def test_does_not_duplicate_shared_header(self):
        shared = '<html><head></head><body><header class="site-header"></header></body></html>'
        self.assertEqual(inject(shared), shared)

    def test_replaces_legacy_top_header(self):
        legacy = """<html><head></head><body class="top-page">
<header class="top-app-bar">
  <div><span>ページ固有ヘッダー</span></div>
</header>
<main>本文</main>
</body></html>"""
        result = inject(legacy)
        self.assertIn('href="./assets/site-header.css"', result)
        self.assertIn('class="site-header"', result)
        self.assertIn('data-login-page="./login.html"', result)
        self.assertIn('<body class="has-site-header top-page">', result)
        self.assertNotIn("top-app-bar", result)
        self.assertNotIn("ページ固有ヘッダー", result)
        self.assertEqual(result.count('class="site-header"'), 1)

    def test_skips_redirect_documents(self):
        redirect = '<!doctype html><meta http-equiv="refresh" content="0; url=/">'
        self.assertEqual(inject(redirect), redirect)

    def test_uses_relative_paths_for_nested_localized_page(self):
        html = '<html lang="en"><head></head><body></body></html>'
        result = inject(html, asset_base="../../../", page_base="../../")
        self.assertIn('href="../../../assets/site-header.css"', result)
        self.assertIn('href="../../map.html">Map</a>', result)
        self.assertIn('href="../../pokemon/">Pokémon</a>', result)
        self.assertIn('href="../../../gmanhole_map.html">Character Manholes</a>', result)
        self.assertIn('data-login-page="../../../login.html"', result)
        self.assertIn('href="https://pokefuta.com/login?from=data">Login</a>', result)
        self.assertIn('src="../../../assets/session-badge.js"', result)
        self.assertEqual(result.count('class="site-header__link"'), 4)

    def test_injects_login_link_for_japanese_page(self):
        result = inject("<!doctype html><html><head></head><body><main></main></body></html>")
        self.assertIn('data-login-page="./login.html"', result)
        self.assertIn('href="https://pokefuta.com/login?from=data">ログイン</a>', result)
        self.assertIn('<script src="./assets/session-badge.js" defer></script>', result)


if __name__ == "__main__":
    unittest.main()
