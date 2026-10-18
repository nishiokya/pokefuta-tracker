from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_prefecture_pages as ja
from apps.scraper import generate_prefecture_pages_i18n as module
from apps.scraper.display_names import municipality_label
from apps.scraper.generate_sitemap import build_sitemap
from apps.scraper.prefectures import PREFECTURE_PAGE_LANGS

# 英語ページに日本語が混ざってよいのは lang="ja" を付けた正式名・「日本語」ボタンと、
# 投稿者が自分で付けた表示名（<bdi>）だけ
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")


def _visible_text_outside_ja(html: str) -> str:
    """script・style・lang="ja" の要素・属性を除いた本文。"""
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", html, flags=re.S)
    body = re.sub(r'<(span|a)\b[^>]*\blang="ja"[^>]*>.*?</\1>', "", body, flags=re.S)
    body = re.sub(r"<bdi\b[^>]*>.*?</bdi>", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return body


class PrefecturePagesI18nTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = ja.load_records(ja.DEFAULT_MANHOLES)
        cls.pokemon_slugs = ja.load_pokemon_slugs(ja.DEFAULT_POKEMON)
        cls.photos = ja.load_photos(ja.DEFAULT_PHOTOS)
        cls.names = module.load_municipality_names()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.count = module.generate_all("en", cls.records, cls.pokemon_slugs, cls.photos, cls.names, cls.out)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def read(self, slug: str = "") -> str:
        return (self.out / slug / "index.html").read_text(encoding="utf-8")

    @unittest.skipIf(
        os.environ.get("POKEFUTA_PAGES_DEPLOY") == "1",
        "デプロイ中は止めない。抜けは生成時の WARN と日次データ PR の差分レポートで出る",
    )
    def test_every_municipality_has_a_name_in_each_language(self) -> None:
        """抜けがあると、その自治体だけ日本語名で出る（デプロイは止めない）。"""
        for lang in PREFECTURE_PAGE_LANGS:
            with self.subTest(lang=lang):
                self.assertEqual([], module.missing_municipalities(self.records, self.names, lang))

    @unittest.skipIf(
        os.environ.get("POKEFUTA_PAGES_DEPLOY") == "1",
        "デプロイ中は止めない。抜けは生成時の WARN と日次データ PR の差分レポートで出る",
    )
    def test_names_file_has_no_stale_or_misplaced_entries(self) -> None:
        """県を取り違えた行・もう無い自治体の行が残っていないこと。"""
        current = {(r.get("prefecture"), municipality_label(r)) for r in self.records}
        listed = {(pref, label) for pref, names in self.names.items() for label in names}
        self.assertEqual(set(), listed - current)

    def test_generates_all_prefectures_and_the_index(self) -> None:
        self.assertEqual(47, self.count)
        self.assertEqual(47, len(list(self.out.glob("*/index.html"))))
        self.assertTrue((self.out / "index.html").exists())

    def test_prefecture_page_is_english(self) -> None:
        html = self.read("hokkaido")
        self.assertIn('<html lang="en">', html)
        self.assertIn("Poké Lids (Pokémon Manholes) in Hokkaido", html)

    @unittest.skipIf(
        os.environ.get("POKEFUTA_PAGES_DEPLOY") == "1",
        "デプロイ中は止めない。新しいポケモン・自治体の訳の抜けで落ちうる",
    )
    def test_no_page_has_japanese_outside_marked_places(self) -> None:
        """訳の抜け（自治体名・ポケモン名の表記揺れ）があると日本語のまま出る。全ページを見る。"""
        leftover = {}
        for path in sorted(self.out.glob("**/index.html")):
            found = JAPANESE.findall(_visible_text_outside_ja(path.read_text(encoding="utf-8")))
            if found:
                leftover[path.parent.name] = "".join(found[:20])
        self.assertEqual({}, leftover)

    def test_hreflang_pairs_with_the_japanese_page(self) -> None:
        en = self.read("kyoto")
        jp_html = ja.build_page("京都府", "kyoto", [], None, {}, None)
        for html in (en, jp_html):
            self.assertIn('hreflang="ja" href="https://data.pokefuta.com/prefectures/kyoto/"', html)
            self.assertIn('hreflang="en" href="https://data.pokefuta.com/en/prefectures/kyoto/"', html)
            self.assertIn('hreflang="x-default" href="https://data.pokefuta.com/prefectures/kyoto/"', html)
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/en/prefectures/kyoto/">', en)

    def test_analytics_match_the_japanese_page(self) -> None:
        """page_path・イベント名は日本語版と同じ。言語は analytics.js の page_lang で分ける。"""
        html = self.read("kyoto")
        self.assertIn("'page_path': \"/prefectures/kyoto/\"", html)
        self.assertIn("page_type: \"prefecture\"", html)
        self.assertIn("surface: 'prefecture_page'", html)
        self.assertNotIn("page_lang", html)

    def test_links_stay_inside_the_language_or_mark_japanese(self) -> None:
        html = self.read("hokkaido")
        self.assertIn('href="/en/pokemon/', html)
        self.assertIn('href="/en/prefectures/aomori/"', html)
        self.assertIn('href="/manholes/', html)
        # 日本語だけのページへのリンクには hreflang="ja" を付ける
        for link in re.findall(r'<a [^>]*href="/(?:manholes|prefectures)/[^"]*"[^>]*>', html):
            self.assertIn('hreflang="ja"', link)
        # 写真館（日本語のみ）への投稿・訪問記録の導線は出さない
        self.assertNotIn("pokefuta.com/upload", html)
        self.assertNotIn("pokefuta.com/visits", html)

    def test_empty_prefecture_shows_the_nearest_poke_lids(self) -> None:
        html = self.read("gunma")
        self.assertIn("No Poké Lids have been confirmed in Gunma yet", html)
        self.assertIn("Nearest Poké Lids from Gunma", html)
        self.assertIn("km away", html)
        self.assertNotIn('id="prefecture-map"', html)

    def test_sitemap_lists_translated_prefecture_pages(self) -> None:
        sitemap = build_sitemap([])
        self.assertIn("https://data.pokefuta.com/en/prefectures/</loc>", sitemap)
        self.assertIn("https://data.pokefuta.com/en/prefectures/hokkaido/</loc>", sitemap)


if __name__ == "__main__":
    unittest.main()
