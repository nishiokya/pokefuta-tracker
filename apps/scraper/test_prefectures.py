#!/usr/bin/env python3
"""47都道府県マスタの不変条件。

ロジックの無いデータモジュールだが、重複・タイポ・並び順の崩れが入ると
都道府県ページの生成が静かに壊れる（URL衝突・欠番・並び違い）ため、
数と一意性と JIS 順だけを固定する。
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("prefectures.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("prefectures", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class PrefectureMasterTest(unittest.TestCase):
    def test_has_exactly_47_entries(self) -> None:
        self.assertEqual(47, len(MODULE.PREFECTURES))

    def test_names_are_unique(self) -> None:
        names = [name for name, _ in MODULE.PREFECTURES]
        self.assertEqual(len(names), len(set(names)))

    def test_slugs_are_unique(self) -> None:
        # slug が衝突すると2県が同じURLを取り合って片方が消える
        slugs = [slug for _, slug in MODULE.PREFECTURES]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_slugs_are_url_safe_ascii(self) -> None:
        for name, slug in MODULE.PREFECTURES:
            with self.subTest(prefecture=name):
                self.assertRegex(slug, r'^[a-z]+$')

    def test_every_name_ends_with_a_valid_suffix(self) -> None:
        for name, _ in MODULE.PREFECTURES:
            with self.subTest(prefecture=name):
                self.assertTrue(re.search(r'(都|道|府|県)$', name))

    def test_jis_order_endpoints_and_landmarks(self) -> None:
        order = MODULE.PREFECTURE_ORDER
        self.assertEqual("北海道", order[0])
        self.assertEqual("沖縄県", order[-1])
        self.assertEqual("東京都", order[12])
        self.assertLess(order.index("東京都"), order.index("大阪府"))

    def test_derived_views_match_the_source_list(self) -> None:
        self.assertEqual([n for n, _ in MODULE.PREFECTURES], MODULE.PREFECTURE_ORDER)
        self.assertEqual(dict(MODULE.PREFECTURES), MODULE.PREFECTURE_SLUGS)
        self.assertEqual(47, len(MODULE.PREFECTURE_SLUGS))

    def test_only_one_to_do_fu_each_and_43_ken(self) -> None:
        names = MODULE.PREFECTURE_ORDER
        self.assertEqual(1, sum(1 for n in names if n.endswith("都")))
        self.assertEqual(1, sum(1 for n in names if n.endswith("道")))
        self.assertEqual(2, sum(1 for n in names if n.endswith("府")))
        self.assertEqual(43, sum(1 for n in names if n.endswith("県")))


if __name__ == "__main__":
    unittest.main()
