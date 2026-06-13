#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_prefecture_trivia.py")
SPEC = importlib.util.spec_from_file_location("generate_prefecture_trivia", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

OGP_MODULE_PATH = Path(__file__).with_name("generate_social_ogp.py")
OGP_SPEC = importlib.util.spec_from_file_location("generate_social_ogp", OGP_MODULE_PATH)
OGP_MODULE = importlib.util.module_from_spec(OGP_SPEC)
assert OGP_SPEC.loader
OGP_SPEC.loader.exec_module(OGP_MODULE)

ROOT = Path(__file__).resolve().parents[2]


class GeneratePrefectureTriviaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = MODULE.load_records(ROOT / "docs" / "pokefuta.ndjson")
        cls.sources = MODULE.load_sources(
            ROOT / "dataset" / "prefecture_trivia_sources.json"
        )
        cls.generated = {
            entry["prefecture"]: entry
            for entry in MODULE.generate(cls.records, cls.sources)
        }

    def test_single_municipality_prefectures(self) -> None:
        actual = {
            prefecture
            for prefecture, entry in self.generated.items()
            if entry["manhole_count"] > 1 and entry["municipality_count"] == 1
        }
        expected = {
            "埼玉県", "千葉県", "栃木県", "神奈川県", "新潟県",
            "富山県", "大阪府", "兵庫県", "奈良県", "岡山県",
            "山口県", "徳島県", "愛媛県", "佐賀県", "鹿児島県",
        }
        self.assertEqual(expected, actual)

    def test_non_single_municipality_regressions(self) -> None:
        self.assertEqual(2, self.generated["福岡県"]["municipality_count"])
        self.assertEqual(4, self.generated["東京都"]["municipality_count"])
        self.assertEqual(5, self.generated["静岡県"]["municipality_count"])

    def test_municipality_concentration(self) -> None:
        expected = {
            "東京都": "最多は町田の6枚で、次いで小笠原の4枚です",
            "滋賀県": "最多は甲賀の3枚で、次いで大津の2枚です",
            "京都府": "最多は京都の5枚で、次いで宇治の3枚です",
            "愛知県": "豊橋市に4枚が集まり、ほかの5自治体は各1枚です",
            "福岡県": "最多は北九州の5枚で、次いで太宰府の3枚です",
        }
        for prefecture, text in expected.items():
            matching = [
                trivia["text"]
                for trivia in self.generated[prefecture]["trivia"]
                if trivia["type"] == "municipality_concentration"
            ]
            self.assertEqual([text], matching)

        for prefecture in ("宮城県", "岩手県", "鳥取県"):
            self.assertFalse(any(
                trivia["type"] == "municipality_concentration"
                for trivia in self.generated[prefecture]["trivia"]
            ))

    def test_top_pokemon_requires_repeat_appearance(self) -> None:
        for prefecture in ("埼玉県", "愛知県", "東京都", "京都府", "福岡県"):
            self.assertFalse(any(
                trivia["type"] == "top_pokemon"
                for trivia in self.generated[prefecture]["trivia"]
            ))

        for prefecture in (
            "神奈川県", "新潟県", "宮城県", "福島県",
            "三重県", "福井県", "長崎県", "高知県",
        ):
            self.assertFalse(any(
                trivia["type"] == "top_pokemon"
                for trivia in self.generated[prefecture]["trivia"]
            ))

        self.assertTrue(any(
            trivia["type"] == "top_pokemon"
            and trivia["text"] == "最も多く登場するのはヤドンで、17枚に描かれています"
            for trivia in self.generated["香川県"]["trivia"]
        ))

    def test_single_pokemon_full_coverage(self) -> None:
        expected = {
            "新潟県": ("コイキング", 4),
            "神奈川県": ("ピカチュウ", 5),
            "宮城県": ("ラプラス", 37),
            "福島県": ("ラッキー", 43),
            "三重県": ("ミジュマル", 31),
            "福井県": ("カイリュー", 17),
            "長崎県": ("デンリュウ", 10),
            "高知県": ("ヌオー", 18),
        }
        for prefecture, (label, count) in expected.items():
            coverage = {
                item["label"]: item
                for item in self.generated[prefecture]["pokemon_coverage"]
            }
            self.assertEqual(count, coverage[label]["cover_count"])
            self.assertEqual(100, coverage[label]["coverage_percent"])

    def test_group_full_coverage(self) -> None:
        expected = {
            "北海道": ("ロコン系", 50),
            "鳥取県": ("サンド系", 20),
            "宮崎県": ("ナッシー系", 26),
            "佐賀県": ("ニャース3種", 3),
        }
        for prefecture, (label, count) in expected.items():
            coverage = {
                item["label"]: item
                for item in self.generated[prefecture]["pokemon_coverage"]
            }
            self.assertEqual(count, coverage[label]["cover_count"])
            self.assertEqual(100, coverage[label]["coverage_percent"])

    def test_source_validation(self) -> None:
        cases = []

        missing_url = copy.deepcopy(self.sources)
        missing_url["editorial_trivia"][0].pop("source_url")
        cases.append(missing_url)

        unknown_prefecture = copy.deepcopy(self.sources)
        unknown_prefecture["editorial_trivia"][0]["prefecture"] = "架空県"
        cases.append(unknown_prefecture)

        unknown_pokemon = copy.deepcopy(self.sources)
        unknown_pokemon["pokemon_groups"][0]["pokemon"] = ["架空ポケモン"]
        cases.append(unknown_pokemon)

        hard_coded_count = copy.deepcopy(self.sources)
        hard_coded_count["editorial_trivia"][0]["count"] = 50
        cases.append(hard_coded_count)

        duplicate_id = copy.deepcopy(self.sources)
        duplicate_id["editorial_trivia"][1]["id"] = duplicate_id["editorial_trivia"][0]["id"]
        cases.append(duplicate_id)

        for sources in cases:
            with self.subTest(source=json.dumps(sources, ensure_ascii=False)[:80]):
                with self.assertRaises(MODULE.ValidationError):
                    MODULE.validate_sources(sources, self.records)

    def test_social_ogp_uses_new_trivia_schema(self) -> None:
        variables = OGP_MODULE._vars_pref_trivia({
            "fact_type": "municipality_concentration",
            "values": {
                "prefecture": "愛知県",
                "manhole_count": 9,
                "summary": "豊橋市に4枚が集まり、ほかの5自治体は各1枚です",
            },
        })
        self.assertEqual("自治体分布", variables["titleLine2"])
        self.assertEqual("9", variables["mainNumber"])
        self.assertEqual("枚", variables["mainUnit"])
        self.assertEqual(
            "豊橋市に4枚が集まり、ほかの5自治体は各1枚です",
            variables["description"],
        )

    def test_social_ogp_keeps_legacy_schema_compatibility(self) -> None:
        variables = OGP_MODULE._vars_pref_trivia({
            "values": {
                "prefecture": "北海道",
                "pokemon": "ロコン",
                "summary": "北海道の応援ポケモンはロコンです",
            },
        })
        self.assertEqual("応援ポケモン", variables["titleLine2"])
        self.assertEqual("ロコン", variables["mainNumber"])
        self.assertEqual("", variables["mainUnit"])


if __name__ == "__main__":
    unittest.main()
