import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)


class HeroActionsTests(unittest.TestCase):
    """ヒーローの主役は経路案内（利用者の14%）、写真投稿（0.7%）はその下の1行。札は称号1つ＋近く。"""

    @classmethod
    def setUpClass(cls) -> None:
        manhole = {
            "id": "170",
            "prefecture": "宮崎県",
            "city": "門川町",
            "lat": 32.47,
            "lng": 131.65,
            "pokemons": ["アローラナッシー", "マケンカニ"],
            "titles": [
                {"key": "unique_pokemon", "emoji": "⭐", "label": "マケンカニは全国でここだけ"},
                {"key": "only_in_city", "emoji": "🏘️", "label": "門川で唯一のポケふた"},
            ],
        }
        other = {"id": "171", "prefecture": "宮崎県", "city": "日向市", "lat": 32.42, "lng": 131.62,
                 "pokemons": ["ナッシー"]}
        cls.html = pages.generate_html(
            manhole=manhole,
            photo=None,
            pokemon_meta={},
            nearby=[(other, 6.2)],
            same_pref=[other],
            pref_total=26,
            same_pokemon=[],
            id_to_image_url={},
            city_total=1,
            same_pokemon_total=8,
            nearby_count=4,
        )
        cls.hero = cls.html[cls.html.index('<div class="hero-card">'):cls.html.index("<!-- adsense:manhole -->")]

    def test_directions_is_the_first_hero_action_and_photo_link_follows(self) -> None:
        actions = self.hero[self.hero.index('<div class="hero-actions">'):]
        self.assertLess(actions.index('class="visit-cta"'), actions.index('class="hero-photo-link"'))
        self.assertIn("経路案内", actions)
        self.assertIn("click_photo_upload", actions)
        # 経路案内はヒーローの中だけ（下の欄に2つ目を置かない）
        self.assertEqual(1, self.html.count('class="visit-cta"'))

    def test_badges_are_one_title_and_nearby_link(self) -> None:
        self.assertIn("マケンカニは全国でここだけ", self.hero)
        self.assertNotIn("門川で唯一のポケふた", self.hero)
        self.assertNotIn("同じポケモン 8枚", self.hero)
        self.assertNotIn("Miyazaki Prefecture", self.hero)
        self.assertIn("href='#nearby'>30km以内に4件</a>", self.hero)
        self.assertIn("<section id='nearby' class='nearby-section", self.html)


if __name__ == "__main__":
    unittest.main()
