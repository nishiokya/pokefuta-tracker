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
                    "display_name": "とても長い名前の投稿者さんイーブイ推し団長",
                    "public_user_id": "6096691c-eeda-4e73-8401-a11274868ede",
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
        # 日付はロケール表記（UTC 00:00 → JST 同日）、投稿者名は 20 文字で省略
        self.assertEqual(cards[0]["date"], "Jun 13")
        self.assertEqual(cards[0]["poster"], "とても長い名前の投稿者さんイーブイ推し…")
        self.assertEqual(
            cards[0]["poster_profile_url"],
            "https://pokefuta.com/users/6096691c-eeda-4e73-8401-a11274868ede/visits",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            html = generate_html(
                pokemon_index,
                "en",
                LANG_CONFIGS["en"],
                LP_INDEX_STRINGS["en"],
                lambda pref: "Kagawa",
                photos_data,
                Path(tmpdir),
            )
        self.assertIn('<article class="photo-card">', html)
        self.assertIn(
            'href="https://pokefuta.com/users/'
            '6096691c-eeda-4e73-8401-a11274868ede/visits"',
            html,
        )
        self.assertIn('class="poster-link"', html)
        self.assertNotIn("さんの公開スタンプ帳を開く", html)

    def test_pokemon_index_does_not_render_hero_summary_panel(self):
        pokemon_index = {
            "slowpoke": (
                {"names": {"ja": "ヤドン", "en": "Slowpoke"}, "generation": 1},
                [
                    {
                        "id": "42",
                        "title": "香川県/高松市",
                        "prefecture": "香川県",
                        "city": "高松市",
                        "pokemons": ["ヤドン"],
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

        self.assertNotIn('class="hero-summary"', html)


if __name__ == "__main__":
    unittest.main()
