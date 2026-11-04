"""サイト名が1つにそろっているかのテスト。名前がページごとにばらけると、検索結果のサイト名がドメイン名で出る。"""

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from apps.scraper import generate_manhole_pages_i18n, generate_prefecture_pages_i18n, generate_top_page
from apps.scraper.site_names import SITE_NAMES, og_site_name
from apps.scraper.top_page_i18n_text import TEXT

SCRAPER = Path(__file__).parent
WEB = SCRAPER.parent / "web"


class SiteNamesTest(unittest.TestCase):
    def test_every_place_uses_the_same_name_per_language(self):
        self.assertEqual(generate_top_page.SITE_NAME, SITE_NAMES["ja"])
        for lang, name in SITE_NAMES.items():
            with self.subTest(lang=lang):
                strings = json.loads((WEB / "i18n" / f"strings.{lang}.json").read_text(encoding="utf-8"))
                found = {}

                def walk(value):
                    if isinstance(value, dict):
                        for key, child in value.items():
                            if key in ("siteName", "shareTitleSuffix"):
                                found[key] = child
                            walk(child)

                walk(strings)
                self.assertEqual(found.get("siteName"), name)
                self.assertTrue(found.get("shareTitleSuffix", "").endswith(name))
                if lang != "ja":
                    self.assertEqual(TEXT[lang]["site_name"], name)
        for module in (generate_manhole_pages_i18n, generate_prefecture_pages_i18n):
            for lang, strings in module.TEXT.items():
                with self.subTest(module=module.__name__, lang=lang):
                    self.assertEqual(strings["site_name"], SITE_NAMES[lang])

    def test_every_page_head_with_og_locale_has_og_site_name(self):
        for path in sorted(SCRAPER.glob("generate_*.py")):
            source = path.read_text(encoding="utf-8")
            locales = source.count('property="og:locale"')
            with self.subTest(file=path.name):
                self.assertGreaterEqual(source.count("og_site_name(") + source.count('property="og:site_name"'), locales)
        en_top = (WEB / "index.en.html").read_text(encoding="utf-8")
        self.assertIn(og_site_name("en_US"), en_top)

    def test_web_pages_with_og_locale_have_og_site_name(self):
        # 手で保守している HTML と、build_i18n.py が多言語版を作るテンプレート。地図だけ抜けていた
        for path in sorted(WEB.glob("*.html")):
            source = path.read_text(encoding="utf-8")
            if 'property="og:locale"' not in source:
                continue
            with self.subTest(file=path.name):
                self.assertIn('property="og:site_name"', source)

    def test_i18n_build_fills_the_site_name_of_each_language(self):
        from tools import build_i18n

        for lang in build_i18n.LANGS:
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(build_i18n, "DIST", Path(tmp)), redirect_stdout(io.StringIO()):
                strings = json.loads((WEB / "i18n" / f"strings.{lang}.json").read_text(encoding="utf-8"))
                build_i18n.build_template(WEB / "map.template.html", "map.html", lang, strings, {})
                built = (Path(tmp) / lang / "map.html").read_text(encoding="utf-8")
                self.assertIn(f'<meta property="og:site_name" content="{SITE_NAMES[lang]}">', built)
                self.assertNotIn("%%SITE_NAME%%", built)

    def test_traditional_chinese_uses_the_current_name(self):
        # 「神奇寶貝」は旧訳。検索語としてキーワードにだけ残す
        strings = (WEB / "i18n" / "strings.zh-TW.json").read_text(encoding="utf-8")
        outside_keywords = re.sub(r'"META_KEYWORDS": "[^"]*"', "", strings)
        self.assertNotIn("神奇寶貝", outside_keywords)
        self.assertNotIn("神奇寶貝", (SCRAPER / "inject_site_header.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
