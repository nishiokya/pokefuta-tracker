import importlib.util
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)

OVERRIDES = {"64": {"lat": 44.176286, "lng": 142.392808, "official": {"lat": 44.175974, "lng": 142.392417}}}


def render(lat: float, lng: float) -> str:
    manhole = {"id": "64", "prefecture": "北海道", "city": "士別市", "lat": lat, "lng": lng, "pokemons": ["メリープ"]}
    with mock.patch.object(pages, "coord_fixed_by_photos", lambda m: pages_is_applied(m)):
        return pages.generate_html(
            manhole=manhole, photo=None, pokemon_meta={}, nearby=[], same_pref=[], pref_total=1,
            same_pokemon=[], id_to_image_url={}, city_total=1, same_pokemon_total=1, nearby_count=0,
        )


def pages_is_applied(m: dict) -> bool:
    from coord_overrides import is_applied

    return is_applied(m, OVERRIDES)


class CoordNoteTests(unittest.TestCase):
    """座標を投稿の写真で直した蓋だけ、設置場所に「地図の位置」の注記を出す。"""

    def test_note_when_overridden(self) -> None:
        html = render(44.176286, 142.392808)
        section = html[html.index("<section class='location-section"):]
        self.assertIn("<dt>地図の位置</dt>", section[: section.index("</section>")])

    def test_no_note_with_official_coords(self) -> None:
        self.assertNotIn("地図の位置", render(44.175974, 142.392417))


if __name__ == "__main__":
    unittest.main()
