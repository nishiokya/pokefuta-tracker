#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("address_parser.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("address_parser", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def page(address_block: str, city_title: str = "神奈川県/横浜市") -> str:
    """Minimal stand-in for a local.pokemon.jp detail page."""
    return f"""<html><body>
        <h1>{city_title}｜ポケモンマンホール『ポケふた』</h1>
        <div class="block"><h2>{city_title}</h2></div>
        {address_block}
        <div class="block about">
            <h2>横浜市について</h2>
            <p>横浜は、江戸時代後期より世界の国々と日本を結ぶ重要な港町として発展し…</p>
        </div>
    </body></html>"""


def map_block(address: str) -> str:
    return f'<div class="block map"><h2>マンホール場所</h2><p>{address}</p></div>'


class ExtractFromDomTest(unittest.TestCase):
    """tier0: 見出し付き DOM ノードをそのまま読む。"""

    def test_reads_paragraph_after_heading(self) -> None:
        html = page(map_block("神奈川県横浜市中区新港一丁目"))
        self.assertEqual("神奈川県横浜市中区新港一丁目", MODULE.extract_address_from_html(html))

    def test_keeps_prefecture_when_町名_has_no_number(self) -> None:
        # 旧 tier3 は「県大津市由美浜」に切り詰めていた
        html = page(map_block("滋賀県大津市由美浜"), city_title="滋賀県/大津市")
        self.assertEqual("滋賀県大津市由美浜", MODULE.extract_address_from_html(html))

    def test_does_not_truncate_long_字_names(self) -> None:
        # 旧 tier3 は [一-鿿]{2,3} で「県盛岡市本宮字」まで
        html = page(map_block("岩手県盛岡市本宮字蛇屋敷地内"), city_title="岩手県/盛岡市")
        self.assertEqual("岩手県盛岡市本宮字蛇屋敷地内", MODULE.extract_address_from_html(html))

    def test_prefers_address_node_over_heading_line(self) -> None:
        # 旧実装は見出しの「高知県/三原村」を拾って「県/三原村」を返していた
        html = page(map_block("高知県三原村宮ノ川"), city_title="高知県/三原村")
        self.assertEqual("高知県三原村宮ノ川", MODULE.extract_address_from_html(html))

    def test_collapses_ideographic_space(self) -> None:
        html = page(map_block("福岡県北九州市小倉北区浅野三丁目5　あさの汐風公園"))
        self.assertEqual(
            "福岡県北九州市小倉北区浅野三丁目5 あさの汐風公園",
            MODULE.extract_address_from_html(html),
        )

    def test_ignores_other_headings(self) -> None:
        html = page(map_block("秋田県仙北市田沢湖潟字ヨテコ沢４"), city_title="秋田県/仙北市")
        self.assertEqual("秋田県仙北市田沢湖潟字ヨテコ沢４", MODULE.extract_address_from_html(html))


class RegexFallbackTest(unittest.TestCase):
    """tier1-5: 見出しノードが無いページ向けの保険。県名を落とさないこと。"""

    def _fallback(self, address: str, city_title: str) -> str:
        html = page(f"<p>{address}</p>", city_title=city_title)
        self.assertEqual("", MODULE.extract_address_from_dom(html))
        return MODULE.extract_address_from_html(html)

    def test_fallback_keeps_prefecture_name(self) -> None:
        self.assertEqual(
            "滋賀県大津市由美浜",
            self._fallback("滋賀県大津市由美浜", "滋賀県/大津市"),
        )

    def test_fallback_keeps_kyoto_fu_intact(self) -> None:
        # 旧 tier3 は「京都府」の「都」から拾って「都府宇治市宇治又」を返していた
        self.assertEqual(
            "京都府宇治市宇治又振",
            self._fallback("京都府宇治市宇治又振", "京都府/宇治市"),
        )

    def test_fallback_skips_slash_separated_heading(self) -> None:
        got = self._fallback("高知県三原村宮ノ川", "高知県/三原村")
        self.assertNotIn("/", got)
        self.assertTrue(got.startswith("高知県三原村"))

    def test_fallback_still_matches_numbered_address(self) -> None:
        self.assertEqual(
            "宮崎県西都市小野崎1丁目77",
            self._fallback("宮崎県西都市小野崎1丁目77", "宮崎県/西都市"),
        )

    def test_noise_lines_are_rejected(self) -> None:
        html = page("", city_title="宮城県/松島町")
        self.assertNotIn("ポケふた", MODULE.extract_address_from_html(html))


if __name__ == "__main__":
    unittest.main()
