#!/usr/bin/env python3
"""テーマタグの単一ソース（`dataset/tag_meta.json`）の固定条件。

トップ・地図・`/tags/`・`/summary/` が**それぞれ手書きのリスト**を持っていた頃は、
史跡（11枚）がトップにあって公園（46枚）が落ちている、ガンダムだけトップで
絵文字が無い、離島の枚数が面によって 28 と 30 で違う、といったズレが起きていた。
定義を1か所に寄せたので、各面がそこから外れて手書きに戻らないことを固定する。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

try:
    from apps.scraper import tag_meta as module
    from apps.scraper.generate_tag_pages import load_records
except ModuleNotFoundError as exc:  # 直接実行されたとき
    if exc.name != "apps":
        raise
    import tag_meta as module  # type: ignore[no-redef]
    from generate_tag_pages import load_records  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
MAP_FILES = ("map.html", "map.template.html")


class SelectionRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = module.TagMeta({
            "min_count": 5,
            "top_chip_limit": 4,
            "priority": ["roadside", "seaside"],
            "tags": [
                {"slug": "seaside", "emoji": "🌊", "label": "海沿い", "featured": True},
                {"slug": "roadside", "emoji": "🛤", "label": "道の駅", "featured": True, "page": True},
                {"slug": "tourism", "emoji": "🗺", "label": "観光地", "icon_only": True},
                {"slug": "park", "emoji": "🌳", "label": "公園", "icon_only": True},
                {"slug": "history", "emoji": "⛩", "label": "史跡・名所", "icon_only": True},
                {"slug": "beach", "emoji": "🏖", "label": "ビーチ"},
                {"slug": "internal", "emoji": "🔒", "label": "内部用", "public": False},
            ],
        })
        self.counts = {
            "seaside": 119, "roadside": 99, "tourism": 92,
            "park": 46, "history": 11, "beach": 1,
            "internal": 100,
        }

    def test_hides_tags_below_min_count(self) -> None:
        self.assertNotIn("beach", self.meta.visible_slugs(self.counts))

    def test_hides_non_public_tags_from_theme_directories(self) -> None:
        self.assertNotIn("internal", self.meta.visible_slugs(self.counts))
        self.assertNotIn("internal", self.meta.top_chip_slugs(self.counts))
        self.assertIn("internal", self.meta.by_slug)

    def test_orders_by_priority_then_by_count(self) -> None:
        self.assertEqual(
            ["roadside", "seaside", "tourism", "park", "history"],
            self.meta.visible_slugs(self.counts),
        )

    def test_top_chips_take_featured_first_then_the_largest(self) -> None:
        """史跡(11)より公園(46)が先に載る。以前は手書きで逆だった。"""
        self.assertEqual(
            ["roadside", "seaside", "tourism", "park"],
            self.meta.top_chip_slugs(self.counts),
        )

    def test_top_chips_respect_the_limit(self) -> None:
        self.assertEqual(4, len(self.meta.top_chip_slugs(self.counts)))

    def test_href_prefers_the_static_page_when_one_exists(self) -> None:
        self.assertEqual("/tags/roadside/", self.meta.href("roadside"))
        self.assertEqual("/map.html?tag=seaside", self.meta.href("seaside"))

    def test_chip_label_joins_emoji_and_label(self) -> None:
        self.assertEqual("🛤 道の駅", self.meta.chip_label("roadside"))


class RealDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = module.load_tag_meta()
        dataset = ROOT / "docs" / "pokefuta.ndjson"
        if not dataset.exists():
            self.skipTest(f"dataset not available: {dataset}")
        self.counts = module.count_tags(load_records(dataset))

    def test_every_featured_or_page_tag_has_enough_records(self) -> None:
        """看板に出すタグが実データで min_count を割っていないこと。"""
        for slug in set(self.meta.featured_slugs()) | set(self.meta.page_slugs()):
            with self.subTest(slug=slug):
                self.assertGreaterEqual(self.counts.get(slug, 0), self.meta.min_count)

    def test_every_tag_has_an_emoji_and_a_label(self) -> None:
        for tag in self.meta.tags:
            with self.subTest(slug=tag["slug"]):
                self.assertTrue(tag.get("emoji"))
                self.assertTrue(tag.get("label"))

    def test_redundant_travel_tags_are_not_public(self) -> None:
        self.assertNotIn("rail_access_good", self.meta.public_slugs())
        self.assertNotIn("gundam_manhole_city", self.meta.public_slugs())

    def test_public_labels_explain_the_theme_boundary(self) -> None:
        self.assertEqual("ガンダムマンホール徒歩圏", self.meta.label("near_gundam_manhole"))
        self.assertEqual("海が見える", self.meta.label("seaside"))
        self.assertEqual("駅前（150m以内）", self.meta.label("station_front"))
        self.assertEqual("駅近（150〜500m）", self.meta.label("near_station"))

    def test_top_and_map_share_the_seven_featured_themes(self) -> None:
        self.assertEqual(
            [
                "seaside", "remote_island", "roadside", "tourism", "park",
                "world_heritage", "near_gundam_manhole",
            ],
            self.meta.featured_slugs(),
        )

    def test_priority_only_names_known_tags(self) -> None:
        for slug in self.meta.priority:
            with self.subTest(slug=slug):
                self.assertIn(slug, self.meta.by_slug)


class NoHardcodedListsTest(unittest.TestCase):
    """各面が手書きのタグ定義に戻っていないこと。"""

    def test_map_reads_the_generated_asset(self) -> None:
        for name in MAP_FILES:
            with self.subTest(name=name):
                source = (WEB / name).read_text(encoding="utf-8")
                self.assertIn("assets/tag-meta.js", source)
                self.assertIn("window.POKEFUTA_TAG_META", source)

    def test_map_no_longer_hardcodes_tag_meta(self) -> None:
        for name in MAP_FILES:
            with self.subTest(name=name):
                source = (WEB / name).read_text(encoding="utf-8")
                self.assertNotIn("const TAG_META = {", source)
                self.assertIsNone(
                    re.search(r"FEATURED_TAGS = \[\s*'", source),
                    "FEATURED_TAGS を手書きの配列に戻さない",
                )

    def test_top_and_multilingual_template_use_the_featured_theme_set(self) -> None:
        expected = set(module.load_tag_meta().featured_slugs())
        for name in ("index.html", "index.template.html"):
            with self.subTest(name=name):
                source = (WEB / name).read_text(encoding="utf-8")
                actual = set(re.findall(
                    r"click_hub_tag',[^}]*tag:'([^']+)'",
                    source,
                ))
                self.assertEqual(expected, actual)

    def test_manhole_detail_labels_come_from_tag_meta(self) -> None:
        source = (ROOT / "apps/scraper/generate_manhole_pages.py").read_text(encoding="utf-8")
        self.assertIn("load_tag_meta", source)
        # 地図が「史跡・名所」と呼ぶものを詳細ページだけ「歴史スポット」と呼んでいた
        self.assertNotIn("歴史スポット", source)

    def test_badge_emoji_match_tag_meta(self) -> None:
        """称号バッジ（manhole_titles.json）の絵文字がテーマ定義と一致すること。"""
        meta = module.load_tag_meta()
        titles = json.loads((ROOT / "dataset/manhole_titles.json").read_text(encoding="utf-8"))
        found = {}

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, dict) and "emoji" in value and key in meta.by_slug:
                        found[key] = value["emoji"]
                    else:
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(titles)
        self.assertTrue(found, "manhole_titles.json からテーマの称号が1件も読めていない")
        for slug, emoji in found.items():
            with self.subTest(slug=slug):
                self.assertEqual(meta.emoji(slug), emoji)


class DeployWorkflowTest(unittest.TestCase):
    """生成物が本番に出ること。tag-meta.js が無いと地図のテーマ一覧が空になる。"""

    def setUp(self) -> None:
        self.workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")

    def test_builds_the_tag_asset_and_the_top_chips(self) -> None:
        self.assertIn("generate_tag_pages.py", self.workflow)
        self.assertIn("generate_top_tag_chips.py", self.workflow)

    def test_rebuilds_when_the_tag_source_changes(self) -> None:
        self.assertIn("dataset/tag_meta.json", self.workflow)


if __name__ == "__main__":
    unittest.main()
