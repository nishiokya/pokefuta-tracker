import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_pokemon_index_page import _build_latest_photo_cards
from generate_pokemon_index_page import generate_html
from generate_pokemon_index_page import LP_INDEX_STRINGS
from generate_pokemon_pages import LANG_CONFIGS


class LatestPhotoCardsTest(unittest.TestCase):
    def test_uses_shared_manhole_path_and_localized_pokemon_names(self):
        manhole = {
            "id": "42",
            "title": "香川県/高松市",
            "prefecture": "香川県",
            "city": "高松市",
            "pokemons": ["ヤドン"],
        }
        pokemon_index = {
            "slowpoke": (
                {"names": {"ja": "ヤドン", "en": "Slowpoke"}},
                [manhole],
            ),
            "pikachu": (
                {"names": {"ja": "ピカチュウ", "en": "Pikachu"}},
                [manhole],
            ),
        }
        photos_data = {
            "photos": {
                "42": {
                    "manhole_id": 42,
                    "url": "https://example.com/slowpoke.jpg",
                    "created_at": "2026-06-13T00:00:00Z",
                },
            },
        }
        lang_config = {"name_key": "en", "pref_joiner": " / "}

        with tempfile.TemporaryDirectory() as tmpdir:
            cards = _build_latest_photo_cards(
                pokemon_index,
                photos_data,
                Path(tmpdir),
                lang_config,
                lambda pref: "Kagawa",
                "en",
            )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["href"], "/manholes/42/")
        self.assertEqual(cards[0]["title"], "Slowpoke / Pikachu")
        self.assertEqual(cards[0]["location"], "Kagawa 高松市")

    def test_ja_index_hero_has_desktop_summary(self):
        pokemon_index = {
            "chansey": (
                {"names": {"ja": "ラッキー", "en": "Chansey"}, "generation": 1},
                [
                    {
                        "id": "1",
                        "prefecture": "福島県",
                        "city": "福島",
                        "pokemons": ["ラッキー"],
                    },
                    {
                        "id": "2",
                        "prefecture": "福島県",
                        "city": "郡山",
                        "pokemons": ["ラッキー"],
                    },
                ],
            ),
            "eevee": (
                {"names": {"ja": "イーブイ", "en": "Eevee"}, "generation": 1},
                [
                    {
                        "id": "3",
                        "prefecture": "鹿児島県",
                        "city": "指宿",
                        "pokemons": ["イーブイ"],
                    }
                ],
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            html = generate_html(
                pokemon_index,
                "ja",
                LANG_CONFIGS["ja"],
                LP_INDEX_STRINGS["ja"],
                lambda pref: pref,
                {},
                Path(tmpdir),
            )

        self.assertIn('class="hero-summary"', html)
        self.assertIn("<span>サマリー</span>", html)
        self.assertIn("2体の登場ポケモンから探せます。", html)
        self.assertIn("最多はラッキーで、全国2枚のポケふたに登場します。", html)
        self.assertIn(".hero-summary { display: none; }", html)


if __name__ == "__main__":
    unittest.main()
