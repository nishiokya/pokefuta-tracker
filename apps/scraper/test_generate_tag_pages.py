#!/usr/bin/env python3
"""テーマ（タグ）ページ生成の固定条件。

このページの存在理由は「地図は1URLなので検索の着地面になれない」ことなので、
検索面として成立する条件（canonical・件数・都道府県への内部リンク）と、
探索の出口が地図であること（/map.html?tag=）を壊さないよう固定する。

計測側は `tag` をイベントに載せることが前提（GA4 のカスタムディメンション
`tag` が未登録だと「どのテーマが押されたか」が分からないため）。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from apps.scraper import generate_tag_pages as module
except ModuleNotFoundError as exc:  # 直接実行されたとき
    if exc.name != "apps":
        raise
    import generate_tag_pages as module  # type: ignore[no-redef]


def record(
    manhole_id: str,
    prefecture: str,
    city: str,
    tags: list[str],
    **extra: object,
) -> dict:
    base = {
        "id": manhole_id,
        "prefecture": prefecture,
        "city": city,
        "tags": tags,
        "pokemons": ["ピカチュウ"],
        "lat": 35.0,
        "lng": 135.0,
        "status": "active",
    }
    base.update(extra)
    return base


SAMPLE = [
    record("1", "北海道", "上ノ国", ["roadside"]),
    record("2", "沖縄県", "那覇", ["roadside", "seaside"]),
    record("3", "岩手県", "久慈", ["roadside"]),
    record("4", "長崎県", "五島", ["remote_island"]),
    record("5", "奈良県", "斑鳩", ["world_heritage"]),
]


class RecordsForTagTest(unittest.TestCase):
    def test_selects_only_records_carrying_the_tag(self) -> None:
        selected = module.records_for_tag(SAMPLE, "roadside")
        self.assertEqual(["1", "3", "2"], [r["id"] for r in selected])

    def test_orders_by_prefecture_order_then_city(self) -> None:
        """並び順は都道府県コード順。地図・県ページと読み順を揃えるため。"""
        selected = module.records_for_tag(SAMPLE, "roadside")
        self.assertEqual(
            ["北海道", "岩手県", "沖縄県"],
            [r["prefecture"] for r in selected],
        )

    def test_drops_records_whose_prefecture_is_unknown(self) -> None:
        rows = SAMPLE + [record("9", "海外", "どこか", ["roadside"])]
        self.assertNotIn("9", [r["id"] for r in module.records_for_tag(rows, "roadside")])

    def test_available_tags_skip_themes_without_records(self) -> None:
        only_roadside = [r for r in SAMPLE if "roadside" in r["tags"]]
        self.assertEqual(["roadside"], module.available_tag_slugs(only_roadside))


class CampaignParamsTest(unittest.TestCase):
    """写真館へのリンクは from=data + pref + tag。utm_* は使わない。"""

    def test_carries_prefecture_and_tag(self) -> None:
        self.assertEqual(
            "from=data&pref=okinawa&tag=roadside",
            module._campaign_params("okinawa", "roadside"),
        )

    def test_falls_back_when_prefecture_is_unknown(self) -> None:
        self.assertEqual("from=data&tag=roadside", module._campaign_params("", "roadside"))

    def test_generator_never_emits_utm_parameters(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("utm_source", source)
        self.assertNotIn("utm_medium", source)
        self.assertNotIn("utm_campaign", source)


class BuildPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.records = module.records_for_tag(SAMPLE, "roadside")
        self.html = module.build_page(
            "roadside", self.records, {}, ["roadside", "remote_island", "world_heritage"]
        )

    def test_has_canonical_and_indexable_robots(self) -> None:
        self.assertIn(
            '<link rel="canonical" href="https://data.pokefuta.com/tags/roadside/">',
            self.html,
        )
        self.assertIn('<meta name="robots" content="index,follow">', self.html)

    def test_title_and_heading_state_the_real_count(self) -> None:
        self.assertIn("<title>道の駅のポケふた一覧（全国3枚）| ポケふた図鑑</title>", self.html)
        self.assertIn("<strong>3枚</strong>", self.html)

    def test_primary_cta_goes_to_the_filtered_map(self) -> None:
        """探索の出口は地図。ここが外れると新設面が行き止まりになる。"""
        self.assertIn('href="/map.html?tag=roadside"', self.html)

    def test_links_every_prefecture_in_the_breakdown(self) -> None:
        for slug in ("hokkaido", "iwate", "okinawa"):
            with self.subTest(slug=slug):
                self.assertIn(f'href="/prefectures/{slug}/"', self.html)

    def test_links_each_manhole_detail_page(self) -> None:
        for manhole_id in ("1", "2", "3"):
            with self.subTest(manhole_id=manhole_id):
                self.assertIn(f'href="/manholes/{manhole_id}/"', self.html)

    def test_upload_link_carries_the_prefecture_of_that_manhole(self) -> None:
        self.assertIn("manhole_id=1&amp;from=data&amp;pref=hokkaido&amp;tag=roadside", self.html)
        self.assertIn("manhole_id=2&amp;from=data&amp;pref=okinawa&amp;tag=roadside", self.html)
        self.assertEqual(1, self.html.count("pref=okinawa"))

    def test_cross_links_other_theme_pages_but_not_itself(self) -> None:
        self.assertIn('href="/tags/remote_island/"', self.html)
        self.assertIn('href="/tags/world_heritage/"', self.html)
        self.assertNotIn('href="/tags/roadside/"', self.html)

    def test_analytics_uses_the_shared_loader_and_sends_the_tag(self) -> None:
        self.assertIn("/assets/analytics.js", self.html)
        self.assertIn("PokefutaAnalytics.init", self.html)
        self.assertNotIn("googletagmanager.com/gtag", self.html)
        self.assertIn("page_type: 'tag'", self.html)
        self.assertIn('tag: "roadside"', self.html)

    def test_preinstall_manholes_hide_the_upload_action(self) -> None:
        rows = [record("7", "青森県", "弘前", ["roadside"], installed=False)]
        html = module.build_page("roadside", rows, {}, ["roadside"])
        self.assertIn("🚧 設置前", html)
        self.assertNotIn("pokefuta.com/upload", html)


class GenerateAllTest(unittest.TestCase):
    def test_writes_one_page_per_available_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            written = module.generate_all(SAMPLE, {}, out)
            self.assertEqual(3, written)
            for slug in ("roadside", "remote_island", "world_heritage"):
                with self.subTest(slug=slug):
                    self.assertTrue((out / slug / "index.html").exists())

    def test_skips_themes_that_have_no_records(self) -> None:
        rows = [r for r in SAMPLE if "roadside" in r["tags"]]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(1, module.generate_all(rows, {}, out))
            self.assertFalse((out / "world_heritage").exists())


class RealDatasetTest(unittest.TestCase):
    """実データでも3本とも生成できること（タグが消えると空ページが出るため）。"""

    def test_every_configured_theme_has_records(self) -> None:
        dataset = module.DEFAULT_MANHOLES
        if not dataset.exists():
            self.skipTest(f"dataset not available: {dataset}")
        records = module.load_records(dataset)
        self.assertEqual(sorted(module.TAG_PAGES), sorted(module.available_tag_slugs(records)))


if __name__ == "__main__":
    unittest.main()
