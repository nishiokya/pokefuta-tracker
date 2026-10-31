"""詳細ページの「ほかの県の同じポケモン」と「◯◯県のポケふた」が同じ蓋を重ねて出さないことを確かめる。"""

import unittest

from generate_manhole_pages import RelatedIndex


def _m(mid: str, pref: str, pokemons: list[str]) -> dict:
    return {"id": mid, "prefecture": pref, "city": "", "pokemons": pokemons}


class SamePokemonExcludesSamePrefectureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manholes = [
            _m("1", "香川県", ["ヤドン"]),
            _m("2", "香川県", ["ヤドン"]),
            _m("3", "香川県", ["ヤドン"]),
            _m("4", "岡山県", ["ヤドン"]),
        ]
        self.rel = RelatedIndex(self.manholes).related(self.manholes[0])

    def test_same_pokemon_lists_only_other_prefectures(self) -> None:
        self.assertEqual([m["id"] for m in self.rel["same_pokemon"]], ["4"])

    def test_no_overlap_with_prefecture_section(self) -> None:
        pref_ids = {m["id"] for m in self.rel["same_pref"]}
        self.assertFalse(pref_ids & {m["id"] for m in self.rel["same_pokemon"]})

    def test_badge_count_stays_nationwide(self) -> None:
        self.assertEqual(self.rel["same_pokemon_total"], 3)

    def test_empty_when_pokemon_only_in_same_prefecture(self) -> None:
        manholes = self.manholes[:3]
        rel = RelatedIndex(manholes).related(manholes[0])
        self.assertEqual(rel["same_pokemon"], [])


if __name__ == "__main__":
    unittest.main()
