"""ポケモンのページの上に出す1枚（と og:image）が、人が選んだ代表を優先して選ばれることを固定する。

一覧（マンホールごとのカード）は代表とは関係なく全部出ることも確かめる。
"""

import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper.generate_pokemon_pages import (
    DEFAULT_OGP_IMAGE,
    LANG_CONFIGS,
    LP_STRINGS,
    generate_html,
    pick_hero_manhole,
)

MANHOLES = [
    {"id": "42", "prefecture": "香川県", "city": "高松", "title": "香川県/高松", "pokemons": ["ヤドン"]},
    {"id": "43", "prefecture": "香川県", "city": "坂出", "title": "香川県/坂出", "pokemons": ["ヤドン"]},
]
# 43 のほうが新しい写真
PHOTOS = {
    "42": {"manhole_id": 42, "created_at": "2026-01-01T00:00:00Z"},
    "43": {"manhole_id": 43, "created_at": "2026-06-01T00:00:00Z"},
}
SLOWPOKE = {"slug": "slowpoke", "names": {"ja": "ヤドン", "en": "Slowpoke"}}


class PickHeroManholeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.image_dir = Path(self._tmp.name)
        for mid in ("42", "43"):
            (self.image_dir / f"{mid}_latest.jpeg").write_bytes(b"")

    def tearDown(self):
        self._tmp.cleanup()

    def test_representative_wins_over_newest_photo(self):
        self.assertEqual(pick_hero_manhole(MANHOLES, "42", PHOTOS, self.image_dir), "42")

    def test_newest_public_photo_without_representative(self):
        self.assertEqual(pick_hero_manhole(MANHOLES, "", PHOTOS, self.image_dir), "43")
        # そのポケモンのいないマンホールが代表になっていたら使わない
        self.assertEqual(pick_hero_manhole(MANHOLES, "99", PHOTOS, self.image_dir), "43")

    def test_representative_without_public_photo_is_not_used(self):
        # 写真が非公開・削除で photos から消えたら、_latest.jpeg が残っていても使わない
        self.assertEqual(pick_hero_manhole(MANHOLES, "42", {"43": PHOTOS["43"]}, self.image_dir), "43")

    def test_no_public_photo_means_no_hero(self):
        self.assertEqual(pick_hero_manhole(MANHOLES, "42", {}, self.image_dir), "")


def _html(hero: str, lang: str = "ja") -> str:
    return generate_html(
        slug="slowpoke", pokemon=SLOWPOKE, manholes=MANHOLES, related=[], taxonomy_related={},
        image_dir=Path("/nonexistent"), lang=lang, lang_config=LANG_CONFIGS[lang], strings=LP_STRINGS[lang],
        translate_pref=lambda pref: pref, hero_manhole_id=hero,
    )


class HeroHtmlTests(unittest.TestCase):
    def test_hero_photo_and_og_image_use_the_chosen_manhole(self):
        html = _html("42")
        hero = re.search(r"<figure class='poke-hero-photo'>(.*?)</figure>", html, re.S).group(1)
        self.assertIn("manhole/image/42_latest.jpeg", hero)
        self.assertIn("href='/manholes/42/'", hero)
        self.assertIn('og:image" content="https://data.pokefuta.com/manhole/image/42_latest.jpeg"', html)
        self.assertIn('twitter:image" content="https://data.pokefuta.com/manhole/image/42_latest.jpeg"', html)
        # 一覧は代表と関係なく全部出す
        self.assertEqual(2, html.count("class='manhole-item'"))

    def test_without_hero_keeps_the_default_ogp(self):
        html = _html("")
        self.assertNotIn("<figure class='poke-hero-photo'>", html)
        self.assertIn(f'og:image" content="{DEFAULT_OGP_IMAGE}"', html)

    def test_other_languages_get_the_hero_too(self):
        self.assertIn("manhole/image/42_latest.jpeg' alt='Slowpoke'", _html("42", "en"))


if __name__ == "__main__":
    unittest.main()
