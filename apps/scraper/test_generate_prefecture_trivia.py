#!/usr/bin/env python3
"""トリビア生成ロジックのテスト。**本番データを読まないこと。**

`update-pokefuta.yml`（家系B）から日次で実行されるため、`docs/pokefuta.ndjson`
の中身に依存する assert を置くと、ポケふたが1枚増えただけで日次ジョブが
何も書かずに止まる。判定は必ず fixture のレコードに対して行う。

いまのデータの写し（自治体数の実数、実際のトリビア文言など）は
`test_dataset_snapshots.py` が家系Cのジョブから検証する。
"""

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


def rec(prefecture: str, city: str, *pokemons: str, rid: str = "") -> dict:
    return {
        "id": rid or f"{prefecture}-{city}-{'-'.join(pokemons)}",
        "prefecture": prefecture,
        "city": city,
        "pokemons": list(pokemons),
        "status": "active",
    }


def trivia_of(entry: dict, fact_type: str) -> list[str]:
    return [t["text"] for t in entry["trivia"] if t["type"] == fact_type]


def generate_one(records: list[dict], prefecture: str, sources: dict | None = None) -> dict:
    empty = {"editorial_trivia": [], "pokemon_groups": []}
    entries = MODULE.generate(records, sources if sources is not None else empty)
    return next(e for e in entries if e["prefecture"] == prefecture)


class SingleMunicipalityTest(unittest.TestCase):
    def test_all_manholes_in_one_city(self) -> None:
        records = [rec("埼玉県", "所沢", "ピカチュウ") for _ in range(3)]
        for i, r in enumerate(records):
            r["id"] = f"s{i}"
        entry = generate_one(records, "埼玉県")
        self.assertEqual(["県内3枚のポケふたはすべて所沢にあります"],
                         trivia_of(entry, "single_municipality"))
        self.assertEqual(1, entry["municipality_count"])

    def test_not_emitted_for_a_lone_manhole(self) -> None:
        # total > 1 が条件。1枚だけの県には出さない
        entry = generate_one([rec("埼玉県", "所沢", "ピカチュウ")], "埼玉県")
        self.assertEqual([], trivia_of(entry, "single_municipality"))


class MunicipalityConcentrationTest(unittest.TestCase):
    def _records(self, spread: dict[str, int]) -> list[dict]:
        out = []
        for city, n in spread.items():
            for i in range(n):
                out.append(rec("愛知県", city, "ピカチュウ", rid=f"{city}{i}"))
        return out

    def test_others_all_one_uses_the_gathered_phrasing(self) -> None:
        entry = generate_one(self._records({"豊橋": 4, "a": 1, "b": 1, "c": 1}), "愛知県")
        self.assertEqual(["豊橋に4枚が集まり、ほかの3自治体は各1枚です"],
                         trivia_of(entry, "municipality_concentration"))

    def test_runner_up_uses_the_ranked_phrasing(self) -> None:
        entry = generate_one(self._records({"豊橋": 5, "岡崎": 3, "c": 1}), "愛知県")
        self.assertEqual(["最多は豊橋の5枚で、次いで岡崎の3枚です"],
                         trivia_of(entry, "municipality_concentration"))

    def test_suppressed_when_top_count_below_three(self) -> None:
        entry = generate_one(self._records({"豊橋": 2, "岡崎": 1}), "愛知県")
        self.assertEqual([], trivia_of(entry, "municipality_concentration"))

    def test_suppressed_when_share_below_30_percent(self) -> None:
        spread = {"豊橋": 3, **{f"c{i}": 1 for i in range(8)}}  # 3/11 = 27%
        entry = generate_one(self._records(spread), "愛知県")
        self.assertEqual([], trivia_of(entry, "municipality_concentration"))

    def test_suppressed_on_a_tie_for_top(self) -> None:
        entry = generate_one(self._records({"豊橋": 3, "岡崎": 3}), "愛知県")
        self.assertEqual([], trivia_of(entry, "municipality_concentration"))


class TopPokemonTest(unittest.TestCase):
    def test_names_the_single_leader(self) -> None:
        records = [
            rec("香川県", "高松", "ヤドン", rid="a"),
            rec("香川県", "丸亀", "ヤドン", rid="b"),
            rec("香川県", "坂出", "ピカチュウ", rid="c"),
        ]
        self.assertEqual(["最も多く登場するのはヤドンで、2枚に描かれています"],
                         trivia_of(generate_one(records, "香川県"), "top_pokemon"))

    def test_requires_at_least_two_appearances(self) -> None:
        records = [
            rec("香川県", "高松", "ヤドン", rid="a"),
            rec("香川県", "丸亀", "ピカチュウ", rid="b"),
        ]
        self.assertEqual([], trivia_of(generate_one(records, "香川県"), "top_pokemon"))

    def test_lists_examples_when_tied(self) -> None:
        records = [
            rec("香川県", "高松", "ヤドン", rid="a"),
            rec("香川県", "丸亀", "ヤドン", rid="b"),
            rec("香川県", "坂出", "コダック", rid="c"),
            rec("香川県", "観音寺", "コダック", rid="d"),
        ]
        self.assertEqual(["最多はコダック・ヤドンなど2種で、それぞれ2枚に登場します"],
                         trivia_of(generate_one(records, "香川県"), "top_pokemon"))

    def test_suppressed_when_a_pokemon_already_has_full_coverage(self) -> None:
        # 全枚数に出るポケモンは pokemon_100 側で語られるため top_pokemon の
        # 候補から除外される。そのポケモンが必ず最多になる以上、候補は空になり
        # top_pokemon 自体が出ない。
        records = [rec("宮城県", f"c{i}", "ラプラス", "ヤドン" if i < 2 else "コダック",
                       rid=f"m{i}") for i in range(3)]
        entry = generate_one(records, "宮城県")
        self.assertEqual(["県内3枚すべてにラプラスが登場します"],
                         trivia_of(entry, "pokemon_100"))
        self.assertEqual([], trivia_of(entry, "top_pokemon"))


class CoverageTest(unittest.TestCase):
    def test_full_coverage_pokemon_becomes_trivia(self) -> None:
        # 単体ポケモンの coverage はデータから自動生成される（sources 不要）
        records = [rec("宮城県", f"c{i}", "ラプラス", rid=f"m{i}") for i in range(4)]
        entry = generate_one(records, "宮城県")
        coverage = {c["label"]: c for c in entry["pokemon_coverage"]}
        self.assertEqual(4, coverage["ラプラス"]["cover_count"])
        self.assertEqual(100, coverage["ラプラス"]["coverage_percent"])
        self.assertEqual(["県内4枚すべてにラプラスが登場します"],
                         trivia_of(entry, "pokemon_100"))

    def test_group_coverage_uses_the_group_fact_type(self) -> None:
        records = [
            rec("鳥取県", "鳥取", "サンド", rid="a"),
            rec("鳥取県", "米子", "サンドパン", rid="b"),
        ]
        sources = {
            "editorial_trivia": [],
            "pokemon_groups": [{
                "id": "sand", "label": "サンド系", "prefecture": "鳥取県",
                "pokemon": ["サンド", "サンドパン"],
            }],
        }
        entry = generate_one(records, "鳥取県", sources)
        self.assertEqual(["県内2枚すべてにサンド系が登場します"],
                         trivia_of(entry, "pokemon_group_100"))

    def test_partial_coverage_produces_no_trivia(self) -> None:
        records = [
            rec("鳥取県", "鳥取", "サンド", rid="a"),
            rec("鳥取県", "米子", "ピカチュウ", rid="b"),
        ]
        sources = {
            "editorial_trivia": [],
            "pokemon_groups": [{
                "id": "sand", "label": "サンド系", "prefecture": "鳥取県",
                "pokemon": ["サンド"],
            }],
        }
        entry = generate_one(records, "鳥取県", sources)
        coverage = {c["label"]: c for c in entry["pokemon_coverage"]}
        self.assertEqual(50, coverage["サンド系"]["coverage_percent"])
        self.assertEqual([], trivia_of(entry, "pokemon_100"))


class SourceValidationTest(unittest.TestCase):
    """出典ファイルの不正を弾くこと。fixture のレコードに対して検証する。"""

    def setUp(self) -> None:
        self.records = [
            rec("北海道", "稚内", "ロコン", rid="a"),
            rec("北海道", "旭川", "ロコン", rid="b"),
        ]
        self.sources = {
            "editorial_trivia": [
                {"id": "hokkaido-1", "prefecture": "北海道", "type": "support_pokemon",
                 "text": "テスト", "source_url": "https://example.com/a",
                 "verified_at": "2026-08-14"},
                {"id": "hokkaido-2", "prefecture": "北海道", "type": "wordplay",
                 "text": "テスト2", "source_url": "https://example.com/b",
                 "verified_at": "2026-08-14"},
            ],
            "pokemon_groups": [
                {"id": "rokon", "label": "ロコン系", "prefecture": "北海道",
                 "pokemon": ["ロコン"]},
            ],
        }

    def test_valid_sources_pass(self) -> None:
        MODULE.validate_sources(self.sources, self.records)

    def _assert_rejected(self, mutate) -> None:
        sources = copy.deepcopy(self.sources)
        mutate(sources)
        with self.assertRaises(MODULE.ValidationError):
            MODULE.validate_sources(sources, self.records)

    def test_missing_source_url_rejected(self) -> None:
        self._assert_rejected(lambda s: s["editorial_trivia"][0].pop("source_url"))

    def test_unknown_prefecture_rejected(self) -> None:
        self._assert_rejected(
            lambda s: s["editorial_trivia"][0].update(prefecture="架空県"))

    def test_unknown_pokemon_rejected(self) -> None:
        self._assert_rejected(
            lambda s: s["pokemon_groups"][0].update(pokemon=["架空ポケモン"]))

    def test_unknown_trivia_type_rejected(self) -> None:
        self._assert_rejected(lambda s: s["editorial_trivia"][0].update(type="架空型"))

    def test_missing_verified_at_rejected(self) -> None:
        self._assert_rejected(lambda s: s["editorial_trivia"][0].pop("verified_at"))

    def test_non_https_source_url_rejected(self) -> None:
        self._assert_rejected(
            lambda s: s["editorial_trivia"][0].update(source_url="http://example.com/a"))

    def test_calculated_values_stored_in_source_rejected(self) -> None:
        # 算出値は生成側の責務。マスタに書くと二重管理になるので弾く
        for field in ("count", "manhole_count", "municipality_count", "coverage_percent"):
            with self.subTest(field=field):
                self._assert_rejected(
                    lambda s, f=field: s["editorial_trivia"][0].update({f: 50}))

    def test_duplicate_id_rejected(self) -> None:
        def dup(s):
            s["editorial_trivia"][1]["id"] = s["editorial_trivia"][0]["id"]
        self._assert_rejected(dup)


class SocialOgpSchemaTest(unittest.TestCase):
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
