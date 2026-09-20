#!/usr/bin/env python3
"""トップのテーマチップ生成の固定条件。

チップは**内部リンク**なので静的HTMLに入っている必要がある。生成結果と
コミットされている index.html がずれると、クロールされる中身とビルド後の
中身が食い違うので、そこを固定する。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    from apps.scraper import generate_top_tag_chips as module
    from apps.scraper import tag_meta as tag_meta_module
except ModuleNotFoundError as exc:  # 直接実行されたとき
    if exc.name != "apps":
        raise
    import generate_top_tag_chips as module  # type: ignore[no-redef]
    import tag_meta as tag_meta_module  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "apps" / "web" / "index.html"


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.meta = tag_meta_module.TagMeta({
            "min_count": 5,
            "top_chip_limit": 2,
            "priority": ["roadside"],
            "tags": [
                {"slug": "roadside", "emoji": "🛤", "label": "道の駅", "featured": True, "page": True},
                {"slug": "tourism", "emoji": "🗺", "label": "観光地"},
                {"slug": "history", "emoji": "⛩", "label": "史跡・名所"},
            ],
        })
        self.counts = {"roadside": 99, "tourism": 92, "history": 11}
        self.html = module.render_chips(self.meta, self.counts)

    def test_links_to_the_static_page_when_the_tag_has_one(self) -> None:
        self.assertIn('href="/tags/roadside/"', self.html)
        self.assertIn("destination:'tag_page'", self.html)

    def test_links_to_the_filtered_map_otherwise(self) -> None:
        self.assertIn('href="/map.html?tag=tourism"', self.html)
        self.assertIn("destination:'map_tag_filter'", self.html)

    def test_shows_the_count_like_the_map_does(self) -> None:
        self.assertIn('<span class="chip-count">99枚</span>', self.html)

    def test_keeps_the_existing_tracking_event(self) -> None:
        self.assertIn("trackEvent('click_hub_tag',{surface:'top_hub_tag',tag:'roadside'", self.html)

    def test_obeys_the_limit(self) -> None:
        self.assertEqual(2, self.html.count("hub-chip"))
        self.assertNotIn("history", self.html)


class ApplyTest(unittest.TestCase):
    def test_replaces_only_between_the_markers(self) -> None:
        html = (
            "<div>\n          <!-- tag-chips:start -->\n"
            "          <a>old</a>\n"
            "          <!-- tag-chips:end -->\n        </div>"
        )
        updated = module.apply_chips(html, "          <a>new</a>")
        self.assertIn("<a>new</a>", updated)
        self.assertNotIn("<a>old</a>", updated)
        self.assertTrue(updated.startswith("<div>"))
        self.assertTrue(updated.endswith("</div>"))

    def test_leaves_files_without_markers_alone(self) -> None:
        html = "<div><a>keep</a></div>"
        self.assertEqual(html, module.apply_chips(html, "<a>new</a>"))


def _without_counts(html: str) -> str:
    """件数だけを伏せる。

    枚数は日次のデータ更新で動き、ビルド時に dist へ入れ直される。
    コミット済みの index.html に対して件数まで一致を求めると、
    データ更新のたびに Pages のデプロイが落ちる。
    """
    return re.sub(r'<span class="chip-count">\d+枚</span>', "<span class=\"chip-count\"></span>", html)


class CommittedIndexTest(unittest.TestCase):
    def test_index_html_has_the_same_chips_as_the_generator(self) -> None:
        """apps/web/index.html のチップの顔ぶれ・順序・行き先が生成結果と一致すること。

        件数は見ない（上の `_without_counts` の理由）。
        ずれたら `python3 apps/scraper/generate_top_tag_chips.py` で直す。
        """
        dataset = ROOT / "docs" / "pokefuta.ndjson"
        if not dataset.exists():
            self.skipTest(f"dataset not available: {dataset}")
        html = INDEX.read_text(encoding="utf-8")
        regenerated = module.apply_chips(html, module.build_chips(dataset))
        self.assertEqual(_without_counts(html), _without_counts(regenerated))

    def test_counts_are_allowed_to_go_stale_in_the_source(self) -> None:
        """件数だけがずれてもテストは落ちないこと（日次データ更新でデプロイを止めない）。

        実データの枚数に依存させない。枚数が変わった日にこのテストが
        落ちると、それ自体がデプロイを止める原因になる。
        """
        fresh = '<a class="hub-chip" href="/tags/roadside/">道の駅 <span class="chip-count">99枚</span></a>'
        stale = fresh.replace("99枚", "98枚")
        self.assertNotEqual(fresh, stale)
        self.assertEqual(_without_counts(fresh), _without_counts(stale))

    def test_markers_are_present(self) -> None:
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn(module.START_MARKER, html)
        self.assertIn(module.END_MARKER, html)


if __name__ == "__main__":
    unittest.main()
