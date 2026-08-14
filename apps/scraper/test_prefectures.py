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

# JIS X 0401 全国地方公共団体コード順の期待値。prefectures.py から導出せず
# 独立に書き下ろす（モジュールを写すと順序の検証にならないため）。
# 先頭の数字は JIS コードで、レビュー時に原典と1行ずつ突き合わせられるよう残している。
JIS_REFERENCE: list[tuple[int, str, str]] = [
    (1, "北海道", "hokkaido"),    (2, "青森県", "aomori"),      (3, "岩手県", "iwate"),
    (4, "宮城県", "miyagi"),      (5, "秋田県", "akita"),       (6, "山形県", "yamagata"),
    (7, "福島県", "fukushima"),   (8, "茨城県", "ibaraki"),     (9, "栃木県", "tochigi"),
    (10, "群馬県", "gunma"),      (11, "埼玉県", "saitama"),    (12, "千葉県", "chiba"),
    (13, "東京都", "tokyo"),      (14, "神奈川県", "kanagawa"), (15, "新潟県", "niigata"),
    (16, "富山県", "toyama"),     (17, "石川県", "ishikawa"),   (18, "福井県", "fukui"),
    (19, "山梨県", "yamanashi"),  (20, "長野県", "nagano"),     (21, "岐阜県", "gifu"),
    (22, "静岡県", "shizuoka"),   (23, "愛知県", "aichi"),      (24, "三重県", "mie"),
    (25, "滋賀県", "shiga"),      (26, "京都府", "kyoto"),      (27, "大阪府", "osaka"),
    (28, "兵庫県", "hyogo"),      (29, "奈良県", "nara"),       (30, "和歌山県", "wakayama"),
    (31, "鳥取県", "tottori"),    (32, "島根県", "shimane"),    (33, "岡山県", "okayama"),
    (34, "広島県", "hiroshima"),  (35, "山口県", "yamaguchi"),  (36, "徳島県", "tokushima"),
    (37, "香川県", "kagawa"),     (38, "愛媛県", "ehime"),      (39, "高知県", "kochi"),
    (40, "福岡県", "fukuoka"),    (41, "佐賀県", "saga"),       (42, "長崎県", "nagasaki"),
    (43, "熊本県", "kumamoto"),   (44, "大分県", "oita"),       (45, "宮崎県", "miyazaki"),
    (46, "鹿児島県", "kagoshima"), (47, "沖縄県", "okinawa"),
]

JIS_ORDER = [name for _, name, _ in JIS_REFERENCE]
JIS_SLUGS = {name: slug for _, name, slug in JIS_REFERENCE}


class JisReferenceSelfCheckTest(unittest.TestCase):
    """期待値そのものが壊れていないことの確認（テストのテスト）。"""

    def test_codes_are_1_to_47_in_order(self) -> None:
        self.assertEqual(list(range(1, 48)), [code for code, _, _ in JIS_REFERENCE])


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

    def test_jis_order_is_pinned_exactly(self) -> None:
        # 端点や数箇所の抜き取りでは中ほどの入れ替わりを検出できないので、
        # JIS X 0401 の全国コード順を47件そのまま固定する。
        self.assertEqual(JIS_ORDER, MODULE.PREFECTURE_ORDER)

    def test_slug_mapping_is_pinned_exactly(self) -> None:
        self.assertEqual(JIS_SLUGS, MODULE.PREFECTURE_SLUGS)

    def test_source_list_is_pinned_exactly(self) -> None:
        # PREFECTURES 自体（順序込みのタプル列）も固定しておく
        self.assertEqual(list(zip(JIS_ORDER, (JIS_SLUGS[n] for n in JIS_ORDER))),
                         MODULE.PREFECTURES)

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
