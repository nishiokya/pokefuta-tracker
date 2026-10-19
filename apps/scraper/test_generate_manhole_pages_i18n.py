from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_manhole_pages as ja
from apps.scraper import generate_manhole_pages_i18n as module
from apps.scraper import generate_prefecture_pages_i18n as pref_i18n
from apps.scraper.generate_pokemon_pages import load_pokemon_metadata
from apps.scraper.generate_sitemap import build_sitemap
from apps.scraper.prefectures import MANHOLE_PAGE_LANGS
from apps.scraper.test_generate_prefecture_pages_i18n import JAPANESE

ROOT = Path(__file__).resolve().parents[2]


def _visible_text_outside_ja(html: str) -> str:
    """script・style・svg・lang="ja" の要素・投稿者名（<bdi>）を除いた本文。"""
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<svg\b.*?</svg>", "", html, flags=re.S)
    body = re.sub(r"<(span|a|small|p)\b[^>]*\blang=['\"]ja['\"][^>]*>.*?</\1>", "", body, flags=re.S)
    body = re.sub(r"<bdi\b[^>]*>.*?</bdi>", "", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


class ManholePagesI18nTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manholes = ja.load_manholes(ROOT / "docs" / "pokefuta.ndjson")
        photos = ja.load_photos(ROOT / "docs" / "latest-manhole-photos.json")
        pokemon_path = ROOT / "docs" / "pokemon_metadata.json"
        pokemon_meta = load_pokemon_metadata(pokemon_path)
        ja_to_slug = ja.build_ja_to_slug(json.loads(pokemon_path.read_text(encoding="utf-8")))
        names = pref_i18n.load_municipality_names()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.outs = {lang: Path(cls.tmp.name) / lang for lang in MANHOLE_PAGE_LANGS}
        cls.counts = {
            lang: module.generate_all(
                lang, cls.manholes, photos, pokemon_meta, ja_to_slug, names,
                ROOT / "dataset" / "manhole" / "image", out,
            )
            for lang, out in cls.outs.items()
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def read(self, manhole_id: str = "1", lang: str = "en") -> str:
        return (self.outs[lang] / manhole_id / "index.html").read_text(encoding="utf-8")

    def test_generates_a_page_for_every_manhole(self) -> None:
        ids = {str(m.get("id", "")).strip() for m in self.manholes} - {""}
        for lang, out in self.outs.items():
            self.assertEqual(len(ids), self.counts[lang])
            self.assertEqual(ids, {p.parent.name for p in out.glob("*/index.html")})

    def test_page_is_english(self) -> None:
        html = self.read("1")
        self.assertIn('<html lang="en">', html)
        self.assertIn("<title>Eevee Poké Lid in Ibusuki, Kagoshima | Pokéfuta Directory</title>", html)
        self.assertIn('<h1 class="hero-title">Eevee Poké Lid in Ibusuki</h1>', html)
        self.assertIn("Type: Normal", html)

    def test_page_is_traditional_chinese(self) -> None:
        html = self.read("1", "zh-TW")
        self.assertIn('<html lang="zh-TW">', html)
        self.assertIn("指宿市的寶可夢人孔蓋（伊布）", html)
        self.assertIn("屬性：一般", html)
        self.assertIn('href="/zh-TW/prefectures/kagoshima/"', html)

    @unittest.skipIf(
        os.environ.get("POKEFUTA_PAGES_DEPLOY") == "1",
        "デプロイ中は止めない。抜けは生成時の WARN と日次データ PR の差分レポートで出る",
    )
    def test_no_japanese_outside_marked_japanese_names(self) -> None:
        """施設名・住所・アクセスなど日本語のままのものは lang="ja" を付けて出す。"""
        for lang, out in self.outs.items():
            leaks = []
            for page in out.glob("*/index.html"):
                match = JAPANESE[lang].search(_visible_text_outside_ja(page.read_text(encoding="utf-8")))
                if match:
                    leaks.append(f"{page.parent.name}: {match.group(0)}")
            self.assertEqual([], leaks[:10], lang)

    def test_regional_forms_show_their_own_type_and_generation(self) -> None:
        """アローラロコンと通常のロコンを取り違えない（メタデータの日本語名は同じ「ロコン」）。"""
        def card(pokemon: str) -> str:
            for m in self.manholes:
                if pokemon in ja.filter_pokemons(m.get("pokemons", [])):
                    html = self.read(str(m["id"]).strip())
                    section = html.split("pokemon-section", 1)[1]
                    start = section.index(f"lang='ja'>{pokemon}<")
                    return section[start:section.index("</div>", start)]
            self.skipTest(f"{pokemon} のポケふたが今のデータに無い")

        self.assertIn("Type: Fire", card("ロコン"))
        self.assertIn("Generation 1", card("ロコン"))
        self.assertIn("Type: Ice", card("アローラロコン"))
        self.assertIn("Generation 7", card("アローラロコン"))

    def test_hreflang_links_every_language_both_ways(self) -> None:
        expected = [
            'hreflang="ja" href="https://data.pokefuta.com/manholes/1/"',
            'hreflang="en" href="https://data.pokefuta.com/en/manholes/1/"',
            'hreflang="zh-TW" href="https://data.pokefuta.com/zh-TW/manholes/1/"',
            'hreflang="x-default" href="https://data.pokefuta.com/manholes/1/"',
        ]
        for lang in MANHOLE_PAGE_LANGS:
            html = self.read("1", lang)
            self.assertIn(f'<link rel="canonical" href="https://data.pokefuta.com/{lang}/manholes/1/">', html)
            for link in expected:
                self.assertIn(link, html)
        # 日本語版の詳細ページからも訳を指す
        for link in expected:
            self.assertIn(link, ja.hreflang_links("1"))

    def test_analytics_match_the_japanese_page(self) -> None:
        """page_path・イベント名は日本語版と同じ。言語は analytics.js の page_lang で分ける。"""
        html = self.read("1")
        self.assertIn("'page_path': '/manholes/' + \"1\" + '/'", html)
        self.assertIn("page_type: 'map_manhole'", html)
        self.assertIn("gtag('event', 'view_manhole_detail'", html)
        self.assertNotIn("page_lang", html)
        for call in re.findall(r"trackEvent\('[a-z_]+', \{[^}]*\}\)", html.replace("&quot;", '"')):
            self.assertIn('"surface"', call)

    def test_links_stay_inside_the_language_or_mark_japanese(self) -> None:
        html = self.read("1")
        self.assertIn("href='/en/pokemon/eevee/'", html)
        self.assertIn("href='/en/manholes/", html)
        self.assertIn('href="/en/prefectures/kagoshima/"', html)
        self.assertIn("href='/en/map.html?manhole=1'", html)
        # 日本語だけのページへのリンクには hreflang="ja" を付ける
        for link in re.findall(r"<a [^>]*href=['\"]/(?:manholes|prefectures|pokemon)/[^'\"]*['\"][^>]*>", html):
            self.assertRegex(link, r"hreflang=['\"]ja['\"]")
        # 写真館（日本語のみ）への投稿・訪問記録・プロフィールの導線は出さない
        for lang in MANHOLE_PAGE_LANGS:
            for page in self.outs[lang].glob("*/index.html"):
                text = page.read_text(encoding="utf-8")
                self.assertNotIn("https://pokefuta.com/upload", text)
                self.assertNotIn("https://pokefuta.com/users/", text)
                self.assertNotIn("https://pokefuta.com/manhole/", text)

    def test_preinstall_page_says_it_is_not_installed(self) -> None:
        preinstall = [m for m in self.manholes if m.get("installed") is False]
        if not preinstall:
            self.skipTest("設置前のポケふたが今のデータに無い")
        html = self.read(str(preinstall[0]["id"]).strip())
        self.assertIn("Not installed yet", html)

    def test_sitemap_lists_translated_detail_pages(self) -> None:
        xml = build_sitemap(["1", "2"], [])
        for lang in MANHOLE_PAGE_LANGS:
            self.assertIn(f"<loc>https://data.pokefuta.com/{lang}/manholes/1/</loc>", xml)
            self.assertIn(f"<loc>https://data.pokefuta.com/{lang}/manholes/2/</loc>", xml)


if __name__ == "__main__":
    unittest.main()
