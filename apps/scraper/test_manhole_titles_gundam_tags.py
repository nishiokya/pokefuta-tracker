import unittest

from apps.scraper.manhole_titles import build_title_context, compute_titles


class GundamManholeTitleTest(unittest.TestCase):
    def test_gundam_tags_become_title_badges(self):
        manhole = {
            "id": "66",
            "status": "active",
            "prefecture": "北海道",
            "city": "天塩",
            "lat": 44.88452,
            "lng": 141.74797,
            "pokemons": ["ロコン"],
            "tags": ["near_gundam_manhole", "gundam_manhole_city"],
        }
        master = {
            "vocabulary": {
                "near_gundam_manhole": {
                    "enabled": True,
                    "emoji": "🤖",
                    "label": "ガンダムマンホールまで約500m以内",
                    "hashtag": "#ガンダムマンホール近接",
                    "priority": 44,
                },
                "gundam_manhole_city": {
                    "enabled": True,
                    "emoji": "🤖",
                    "label": "{city}にはガンダムマンホールもある",
                    "hashtag": "#ガンダムマンホールのあるまち",
                    "priority": 31,
                },
            },
            "islands": [],
            "lakes": [],
        }

        titles = compute_titles(
            manhole,
            build_title_context([manhole], master),
            nc50=0,
            nc100=0,
        )
        by_key = {title["key"]: title for title in titles}

        self.assertEqual(
            by_key["near_gundam_manhole"]["label"],
            "ガンダムマンホールまで約500m以内",
        )
        self.assertEqual(
            by_key["gundam_manhole_city"]["label"],
            "天塩にはガンダムマンホールもある",
        )
