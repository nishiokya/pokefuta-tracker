#!/usr/bin/env python3
"""本番データのスナップショット監査。**日次の生成ジョブから実行してはいけない。**

ここにあるのはロジックのテストではなく「いまの `docs/pokefuta.ndjson` が
こういう形になっている」というデータの写しである。したがって

    ポケふたが1枚増える → ここが落ちる

のが**正常な挙動**であり、`update-pokefuta.yml`（家系B: データを更新して
PRを作るジョブ）のゲートに置くと、正当なデータ更新のたびに日次ジョブが
何も書かずに停止する。実際、埼玉県に2つ目の自治体のポケふたを1枚足すだけで
`single_municipality` と `top_pokemon` の2件が落ちる。

そのため本モジュールは `check-site-stats.yml`（家系C: 読み取り専用の検証）
から実行する。落ちたときの意味は「壊れた」ではなく**「データが変わったので
期待値を更新せよ」**であり、生成・公開は止めない。

ロジックそのものの検証は fixture ベースの `test_generate_prefecture_trivia.py`
が受け持つ。ここを直すときは、まず向こうに対応するロジックテストがあるかを
確認すること。
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_prefecture_trivia.py")
SPEC = importlib.util.spec_from_file_location("generate_prefecture_trivia", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

SOCIAL_PATH = Path(__file__).with_name("generate_social_posts.py")
SOCIAL_SPEC = importlib.util.spec_from_file_location("generate_social_posts", SOCIAL_PATH)
social = importlib.util.module_from_spec(SOCIAL_SPEC)
assert SOCIAL_SPEC.loader
SOCIAL_SPEC.loader.exec_module(social)

ROOT = Path(__file__).resolve().parents[2]


class PrefectureTriviaDatasetSnapshotTest(unittest.TestCase):
    """`docs/pokefuta.ndjson` の現在値を写したもの。データ更新時は期待値を更新する。"""

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
            "長崎県": ("デンリュウ", 15),
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


class SocialPostCandidateSnapshotTest(unittest.TestCase):
    """生成済み `docs/social-post-candidates.json` の内容確認。

    このジョブ自身が再生成するファイルを読むため、生成ロジックのゲートには使えない。
    """

    def test_generated_candidates_include_teshio_story(self) -> None:
        candidates_path = social.ROOT / "docs" / "social-post-candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidate = next(
            item for item in candidates
            if item.get("id") == "gundam-crossover-teshio-roadside-pair"
        )
        self.assertEqual(
            candidate["raw_data"]["values"]["summary"],
            social.load_gundam_spots(social.GUNDAM_SPOTS_JSON)[0]["story"],
        )


if __name__ == "__main__":
    unittest.main()
