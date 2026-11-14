import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)

POST_URL = "https://pokefuta.com/design-manholes/202ff606-b1b7-4b9b-bba2-de3092a16a6d"


def _manhole(**overrides) -> dict:
    base = {
        "id": "9001",
        "prefecture": "群馬県",
        "city": "渋川",
        "address": "群馬県渋川市伊香保町伊香保",
        "building": "伊香保ロープウェイ不如帰駅前",
        "lat": 36.497125,
        "lng": 138.919297,
        "pokemons": ["サンダー"],
        "titles": [],
        "tags": [],
        "detail_url": "",
        "provisional": True,
        "provisional_post_url": POST_URL,
        "provisional_source_url": "https://www.pref.gunma.jp/site/houdou/779585.html",
    }
    base.update(overrides)
    return base


def _generate(manhole: dict) -> str:
    return pages.generate_html(
        manhole=manhole,
        photo=None,
        pokemon_meta={},
        nearby=[],
        same_pref=[],
        pref_total=0,
        same_pokemon=[],
        id_to_image_url={},
    )


class ProvisionalRenderingTests(unittest.TestCase):
    def test_badge_and_note_explain_the_provisional_number(self):
        html = _generate(_manhole())
        self.assertIn("class='hero-badge hero-badge-provisional", html)
        self.assertIn("公式サイト未掲載のポケふた", html)
        self.assertIn("番号 9001 は図鑑の仮の番号", html)
        self.assertIn(f'href="{POST_URL}"', html)
        self.assertIn("www.pref.gunma.jp", html)

    def test_links_avoid_photo_studio_pages_that_do_not_exist(self):
        html = _generate(_manhole())
        self.assertNotIn("pokefuta.com/manhole/9001", html)
        self.assertNotIn("upload?manhole_id=9001", html)
        self.assertIn("https://pokefuta.com/design-manholes/new?kind=pokefuta", html)
        self.assertNotIn("公式サイト</span>", html)

    def test_official_lids_keep_their_photo_studio_links(self):
        html = _generate(_manhole(id="449", provisional=False, provisional_post_url=""))
        self.assertIn("pokefuta.com/manhole/449", html)
        self.assertIn("upload?manhole_id=449", html)
        self.assertNotIn("class='hero-badge hero-badge-provisional", html)
        self.assertNotIn("id='provisional'", html)


if __name__ == "__main__":
    unittest.main()
