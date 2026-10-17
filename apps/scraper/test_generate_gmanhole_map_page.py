from __future__ import annotations

import re
import unittest
from pathlib import Path

from apps.scraper.generate_gmanhole_map_page import (
    DEFAULT_GUNDAM, DEFAULT_TEMPLATE, LIST_MARKER, SUMMARY_MARKER, gundam_records, render,
)
from apps.scraper.generate_character_manhole_page import load_ndjson

RECORDS = [
    {"id": "2", "title": "岡山の<蓋>", "prefecture": "岡山県", "city": "岡山市", "address": "岡山県岡山市北区",
     "detail_url": "https://www.g-manhole.net/about/detail.php?id=2", "status": "active"},
    {"id": "1", "title": "豊富町観光情報センター", "prefecture": "北海道", "city": "豊富町", "address": "北海道天塩郡豊富町",
     "detail_url": "https://www.g-manhole.net/about/detail.php?id=1", "status": "active",
     "image_urls": ["../img/about/img1/img_manhole1.png"]},
    {"id": "3", "title": "Warning: 壊れた行", "prefecture": "", "status": "invalid"},
    {"id": "4", "title": "撤去済み", "prefecture": "千葉県", "status": "active", "installation_status": "removed"},
    {"id": "5", "title": "出典が壊れている", "prefecture": "北海道", "city": "稚内市", "status": "active",
     "detail_url": "javascript:alert(1)"},
]
TEMPLATE = f"<title>t</title><p>{SUMMARY_MARKER}</p><li>{SUMMARY_MARKER}</li>{LIST_MARKER}"


class GmanholeMapPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = render(TEMPLATE, gundam_records(RECORDS))

    def test_lists_only_installed_rows_grouped_in_prefecture_order(self) -> None:
        self.assertNotIn("壊れた行", self.html)
        self.assertNotIn("撤去済み", self.html)
        self.assertLess(self.html.index("北海道 <small>2基</small>"), self.html.index("岡山県 <small>1基</small>"))

    def test_fills_every_summary_marker_with_the_same_count(self) -> None:
        self.assertEqual(3, self.html.count("3基・2都道府県"))  # マーカー2か所＋一覧の見出し
        self.assertNotIn("<!--", self.html)

    def test_escapes_names_and_drops_unsafe_source_links(self) -> None:
        self.assertIn("岡山の&lt;蓋&gt;", self.html)
        self.assertIn('href="https://www.g-manhole.net/about/detail.php?id=1"', self.html)
        self.assertNotIn("javascript:", self.html)

    def test_does_not_hotlink_images_from_the_source_site(self) -> None:
        self.assertNotIn("img_manhole1.png", self.html)

    def test_links_to_the_guide_page(self) -> None:
        self.assertIn('href="./characters/gundam/"', self.html)

    def test_refuses_to_build_without_records_or_marker(self) -> None:
        with self.assertRaises(ValueError):
            render(TEMPLATE, [])
        with self.assertRaises(ValueError):
            render(TEMPLATE.replace(LIST_MARKER, ""), gundam_records(RECORDS))


class GmanholeMapTemplateTest(unittest.TestCase):
    """本番のテンプレートとデータで、検索向けの見出しと一覧が出ること。"""

    def setUp(self) -> None:
        self.html = render(DEFAULT_TEMPLATE.read_text(encoding="utf-8"), gundam_records(load_ndjson(DEFAULT_GUNDAM)))

    def test_title_and_h1_name_the_gundam_list_and_map(self) -> None:
        self.assertIn("<title>ガンダムマンホール一覧・地図｜全国の設置場所マップ</title>", self.html)
        self.assertIn("<h1>ガンダムマンホール一覧・地図 — 全国の設置場所</h1>", self.html)
        self.assertEqual(1, self.html.count("<h1"))

    def test_every_installed_record_is_in_the_static_list(self) -> None:
        records = gundam_records(load_ndjson(DEFAULT_GUNDAM))
        self.assertEqual(len(records), len(re.findall(r'<li id="gundam-', self.html)))
        self.assertNotIn("<!-- GUNDAM_", self.html)

    def test_no_stale_hand_written_counts(self) -> None:
        self.assertNotIn("約80基", self.html)
        self.assertNotIn("180枚以上", self.html)


if __name__ == "__main__":
    unittest.main()
