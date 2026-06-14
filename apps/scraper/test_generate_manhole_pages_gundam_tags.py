import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)


class GundamTagPageTests(unittest.TestCase):
    def test_gundam_titles_appear_in_badges_and_share_hashtags(self):
        manhole = {
            "id": "66",
            "prefecture": "北海道",
            "city": "天塩町",
            "address": "北海道天塩郡天塩町",
            "lat": 44.88,
            "lng": 141.74,
            "pokemons": ["ロコン"],
            "titles": [
                {
                    "key": "near_gundam_manhole",
                    "emoji": "🤖",
                    "label": "ガンダムマンホールまで約500m以内",
                    "hashtag": "#ガンダムマンホール近接",
                },
                {
                    "key": "gundam_manhole_city",
                    "emoji": "🤖",
                    "label": "天塩町にはガンダムマンホールもある",
                    "hashtag": "#ガンダムマンホールのあるまち",
                },
            ],
        }

        html = pages.generate_html(
            manhole=manhole,
            photo=None,
            pokemon_meta={},
            nearby=[],
            same_pref=[],
            pref_total=1,
            same_pokemon=[],
            id_to_image_url={},
        )

        self.assertIn("🤖 ガンダムマンホールまで約500m以内", html)
        self.assertIn("🤖 天塩町にはガンダムマンホールもある", html)
        self.assertIn("%23%E3%82%AC%E3%83%B3%E3%83%80%E3%83%A0%E3%83%9E%E3%83%B3%E3%83%9B%E3%83%BC%E3%83%AB%E8%BF%91%E6%8E%A5", html)
        self.assertIn("%23%E3%82%AC%E3%83%B3%E3%83%80%E3%83%A0%E3%83%9E%E3%83%B3%E3%83%9B%E3%83%BC%E3%83%AB%E3%81%AE%E3%81%82%E3%82%8B%E3%81%BE%E3%81%A1", html)


if __name__ == "__main__":
    unittest.main()
