import unittest

from apps.scraper.manhole_titles import build_title_context, compute_titles


class CharacterManholeTitleTest(unittest.TestCase):
    def test_character_tags_become_title_badges(self):
        manhole = {
            "id": "406",
            "status": "active",
            "prefecture": "愛知県",
            "city": "常滑",
            "lat": 34.87472,
            "lng": 136.83156,
            "pokemons": ["ポッチャマ"],
            "tags": ["near_character_manhole", "character_manhole_city"],
        }
        master = {
            "vocabulary": {
                "near_character_manhole": {
                    "enabled": True,
                    "emoji": "🎨",
                    "label": "キャラクターマンホールまで約1km以内",
                    "hashtag": "#キャラクターマンホール近接",
                    "priority": 43,
                },
                "character_manhole_city": {
                    "enabled": True,
                    "emoji": "🎨",
                    "label": "{city}にはキャラクターマンホールもある",
                    "hashtag": "#キャラクターマンホールのあるまち",
                    "priority": 30,
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
            by_key["near_character_manhole"]["label"],
            "キャラクターマンホールまで約1km以内",
        )
        self.assertEqual(
            by_key["near_character_manhole"]["hashtag"],
            "#キャラクターマンホール近接",
        )
        self.assertEqual(
            by_key["character_manhole_city"]["label"],
            "常滑にはキャラクターマンホールもある",
        )

    def test_no_character_tags_no_badges(self):
        manhole = {
            "id": "1",
            "status": "active",
            "prefecture": "北海道",
            "city": "札幌",
            "lat": 43.06,
            "lng": 141.35,
            "pokemons": [],
            "tags": [],
        }
        master = {
            "vocabulary": {
                "near_character_manhole": {
                    "enabled": True,
                    "emoji": "🎨",
                    "label": "キャラクターマンホールまで約1km以内",
                    "hashtag": "#キャラクターマンホール近接",
                    "priority": 43,
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
        self.assertNotIn(
            "near_character_manhole",
            {title["key"] for title in titles},
        )


if __name__ == "__main__":
    unittest.main()
