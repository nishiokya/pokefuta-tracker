"""英語版トップ（/en/index.html）の生成ブロックの検査。

データと写真の選び方は日本語版と共有しているので、ここでは英語の文言と
/en/ から見たリンク先（英語ページは ./、日本語のみのページと画像は ../）を見る。
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_top_page_en as module
from apps.scraper.test_generate_top_page import SHELL, TODAY, Fixture, _block, _event

ROOT = Path(__file__).resolve().parents[2]
INDEX_EN = ROOT / "apps" / "web" / "index.en.html"
# 英語版は日本語のテーマチップ（tag-chips）を持たず、themes ブロックを自前で描く
EN_SHELL = re.sub(
    r"[ ]*<!-- tag-chips:start -->.*?<!-- tag-chips:end -->",
    "          <!-- home:themes:start -->\n          <!-- home:themes:end -->",
    SHELL,
    flags=re.DOTALL,
)
JA_TEXT = re.compile(r"[぀-ヿ一-鿿]")


def _visible(html: str) -> str:
    """日本語が混ざってよい箇所（JSON-LD の正式名称・計測引数・lang="ja" のイベント名）を除く。"""
    html = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r'onclick="[^"]*"', "", html)
    return re.sub(r'<b lang="ja">[^<]*</b>', "", html)


class EnglishTopTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.en = module.English(pokemon_metadata=None)
        self.en.pokemon_by_slug = {"pikachu": "Pikachu", "lapras": "Lapras"}
        self.en.pokemon = {"ピカチュウ": "Pikachu", "ラプラス": "Lapras"}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def html(self, fixture: Fixture | None = None) -> str:
        fixture = fixture or Fixture(self.tmp)
        data = fixture.data()
        data.tag_counts = {"world_heritage": 50, "seaside": 40}
        return module.apply_blocks(EN_SHELL, data, self.en)

    def test_description_and_h1_use_real_counts_in_english(self) -> None:
        html = self.html()
        head = _block(html, "head")
        self.assertIn("Find all 20 Poké Lids", head)
        self.assertIn("across 10 prefectures in Japan", head)
        self.assertIn("Find all 20 Poké Lids in Japan</h1>", html)

    def test_json_ld_points_at_the_english_page(self) -> None:
        ld = json.loads(re.search(r'ld\+json">(.*?)</script>', self.html(), re.DOTALL).group(1))
        graph = {node["@type"]: node for node in ld["@graph"]}
        self.assertEqual("https://data.pokefuta.com/en/", graph["CollectionPage"]["url"])
        self.assertEqual("en", graph["CollectionPage"]["inLanguage"])
        self.assertEqual(10, graph["ItemList"]["numberOfItems"])
        self.assertEqual("Poké Lids in Hokkaido (2)", graph["ItemList"]["itemListElement"][0]["name"])

    def test_no_japanese_in_visible_text(self) -> None:
        events = [_event("東京都", "東京スタンプラリー", "2026-08-01", "2026-12-31")]
        html = self.html(Fixture(self.tmp, events=events))
        self.assertIn('<b lang="ja">東京スタンプラリー</b>', html)
        leftovers = JA_TEXT.findall(re.sub(r"<!--.*?-->", "", _visible(html), flags=re.DOTALL))
        self.assertEqual([], leftovers)

    def test_paths_from_the_en_directory(self) -> None:
        html = self.html()
        srcs = re.findall(r'<img [^>]*src="([^"]+)"', html)
        self.assertTrue(srcs)
        self.assertTrue(all(src.startswith("../") for src in srcs))
        self.assertRegex(html, r'href="\.\./manholes/\d+/"')
        self.assertIn('href="../prefectures/hokkaido/" hreflang="ja"', html)
        self.assertIn('href="pokemon/pikachu/"', html)
        self.assertIn('href="map.html?tag=', html)
        self.assertNotIn('href="/tags/', html)
        self.assertNotIn('href="manholes/', html)

    def test_prefectures_and_regions_are_in_english(self) -> None:
        block = _block(self.html(), "pref")
        self.assertIn("Hokkaido &amp; Tohoku", block)
        self.assertIn('<span class="home-pref__name">Hokkaido</span>', block)
        self.assertIn("As of September 2026, there are no Poké Lids in", block)
        self.assertIn(">Gunma</a>", block)
        self.assertIn("(Japanese)", block)

    def test_photos_are_lazy_outside_the_hero_and_dated_in_english(self) -> None:
        html = self.html()
        self.assertEqual(module.ja.HERO_PHOTO_LIMIT, _block(html, "hero").count('loading="eager"'))
        gallery = _block(html, "photos")
        self.assertEqual(module.ja.GALLERY_PHOTO_LIMIT, gallery.count('loading="lazy"'))
        self.assertRegex(gallery, r'<time datetime="2026-09-\d\d">Sep \d+</time>')
        self.assertIn("Fan photo of the Poké Lid in", gallery)

    def test_themes_use_english_labels(self) -> None:
        block = _block(self.html(), "themes")
        self.assertIn("World Heritage", block)
        self.assertIn("click_hub_tag", block)

    def test_events_fold_after_three(self) -> None:
        events = [_event(p, f"E{i}", "2026-08-01", f"2026-12-{10 + i}") for i, p in enumerate(["北海道", "宮城県", "東京都", "京都府"])]
        block = _block(self.html(Fixture(self.tmp, events=events)), "events")
        self.assertIn("Show all (4)", block)
        self.assertIn(">Ongoing<", block)

    def test_same_events_as_the_japanese_top(self) -> None:
        def names(text: str) -> set[str]:
            return set(re.findall(r"trackEvent\(\s*'([a-z_]+)'", text))
        ja_html = (ROOT / "apps/web/index.html").read_text(encoding="utf-8")
        en_html = INDEX_EN.read_text(encoding="utf-8")
        self.assertEqual(names(ja_html), names(en_html))

    def test_committed_page_has_every_marker(self) -> None:
        html = INDEX_EN.read_text(encoding="utf-8")
        for name in ["head", *module.RENDERERS]:
            with self.subTest(name=name):
                self.assertIn(f"<!-- home:{name}:start -->", html)
        self.assertIn('<html lang="en">', html)
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/en/">', html)
        self.assertIn("../assets/top-home.css", html)


if __name__ == "__main__":
    unittest.main()
