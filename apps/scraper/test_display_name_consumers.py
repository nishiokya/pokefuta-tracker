"""利用者向けの各表示面が正規マンホール名を再合成しないことを固定する。"""

from pathlib import Path
import unittest

from apps.scraper.generate_manhole_pages import manhole_label
from apps.scraper.generate_pokemon_pages import generate_html, LANG_CONFIGS, LP_STRINGS


MANHOLE = {
    "id": "210",
    "title": "大阪府/東大阪市",
    "prefecture": "大阪府",
    "city": "東大阪",
    "place_label": "東大阪市 花園中央公園（松原南2）",
    "pokemons": ["ワンパチ"],
}


class DisplayNameConsumerTests(unittest.TestCase):
    def test_related_card_label_starts_with_canonical_name(self) -> None:
        self.assertEqual(
            manhole_label(MANHOLE),
            "東大阪市 花園中央公園（松原南2）のポケふた（ワンパチ）",
        )

    def test_japanese_pokemon_page_uses_canonical_name(self) -> None:
        html = generate_html(
            slug="yamper",
            pokemon={"names": {"ja": "ワンパチ", "en": "Yamper"}},
            manholes=[MANHOLE],
            related=[],
            taxonomy_related={},
            image_dir=Path("/nonexistent"),
            lang="ja",
            lang_config=LANG_CONFIGS["ja"],
            strings=LP_STRINGS["ja"],
            translate_pref=lambda pref: pref,
        )
        self.assertIn(
            "<span class='manhole-location'>東大阪市 花園中央公園（松原南2）</span>",
            html,
        )

    def test_english_pokemon_page_keeps_localized_location(self) -> None:
        html = generate_html(
            slug="yamper",
            pokemon={"names": {"ja": "ワンパチ", "en": "Yamper"}},
            manholes=[MANHOLE],
            related=[],
            taxonomy_related={},
            image_dir=Path("/nonexistent"),
            lang="en",
            lang_config=LANG_CONFIGS["en"],
            strings=LP_STRINGS["en"],
            translate_pref=lambda pref: "Osaka Prefecture",
        )
        self.assertIn(
            "<span class='manhole-location'>Osaka Prefecture 東大阪</span>",
            html,
        )


if __name__ == "__main__":
    unittest.main()


class RepresentativeNamesTests(unittest.TestCase):
    """実データの代表IDで正本の名前を固定する（データが変わったら意図して更新する）。

    - 209 / 210: 同じ施設名が2枚。施設名を残し、住所の最短識別子を括弧で足す
    - 486: 駅前（#518 で「〇〇駅前」に揃えた）
    - 481: 自治体名が施設名の一部（「岡谷市役所前」）。自治体名を重ねない
    - 98: 同じ住所に複数枚。ポケモン名で区別する（place_ambiguous）
    - 10: 施設名の無い一意な蓋は title のまま
    """

    @classmethod
    def setUpClass(cls) -> None:
        import json
        from apps.scraper.display_names import attach_place_labels

        root = Path(__file__).resolve().parents[2]
        rows = [json.loads(line) for line in (root / "apps/scraper/pokefuta.ndjson").read_text().splitlines() if line.strip()]
        attach_place_labels(rows)
        cls.by_id = {str(r["id"]): r for r in rows if r.get("status") == "active"}

    def _name(self, mid: str) -> str:
        from apps.scraper.display_names import compose_display_name
        return compose_display_name(self.by_id[mid])

    def test_representative_names(self) -> None:
        expected = {
            "209": "東大阪市 花園中央公園（松原南1）",
            "210": "東大阪市 花園中央公園（松原南2）",
            "486": "山ノ内町 湯田中駅前",
            "481": "岡谷市役所前（蚕糸公園）",
            "98": "町田市（フシギダネ）",
            "10": "岩手県/洋野町",
        }
        for mid, name in expected.items():
            with self.subTest(id=mid):
                self.assertEqual(self._name(mid), name)

    def test_consumers_use_the_same_name(self) -> None:
        # 関連カード・トップフィードは正本の名前をそのまま使う
        from apps.scraper.generate_top_feed import build_top_feed  # noqa: F401  (import 可能であること)
        record = self.by_id["209"]
        self.assertTrue(manhole_label(record).startswith("東大阪市 花園中央公園（松原南1）のポケふた"))
