import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)


def _manhole() -> dict:
    return {
        "id": "1",
        "prefecture": "鹿児島県",
        "city": "指宿",
        "address": "鹿児島県指宿市湊1丁目1-1",
        "lat": 31.237194,
        "lng": 130.642861,
        "pokemons": ["イーブイ"],
        "titles": [],
        "tags": [],
    }


def _photo(gallery_local: list[dict]) -> dict:
    local_url = f"{pages.BASE_URL}manhole/image/1_latest.jpeg"
    return {
        "photo_id": "rep11111-0000",
        "url": local_url,
        "original_url": local_url,
        "display_name": "いろはす",
        "shot_at": "2026-06-07T00:00:00+00:00",
        "comment": None,
        "gallery_local": gallery_local,
    }


def _generate(photo: dict | None) -> str:
    return pages.generate_html(
        manhole=_manhole(),
        photo=photo,
        pokemon_meta={},
        nearby=[],
        same_pref=[],
        pref_total=0,
        same_pokemon=[],
        id_to_image_url={},
    )


class GallerySectionTests(unittest.TestCase):
    def test_gallery_section_rendered_with_items(self):
        gallery_local = [
            {
                "url": f"{pages.BASE_URL}manhole/image/1_abcd1234.jpeg",
                "display_name": "たこ",
                "shot_at": "2026-05-01T00:00:00+00:00",
            },
            {
                "url": f"{pages.BASE_URL}manhole/image/1_ef012345.jpeg",
                "display_name": None,
                "shot_at": None,
            },
        ]
        html = _generate(_photo(gallery_local))

        self.assertIn("みんなの写真", html)
        self.assertIn("manhole/image/1_abcd1234.jpeg", html)
        self.assertIn("manhole/image/1_ef012345.jpeg", html)
        # クレジットは「📷 名前 · 5月1日」（撮影日のロケール短表記）に統一
        self.assertIn("📷 たこ · 5月1日", html)
        self.assertIn("https://pokefuta.com/manhole/1", html)
        self.assertIn("すべての写真を見る", html)
        self.assertIn("click_gallery_more", html)

    def test_hero_credit_uses_locale_date_and_truncated_name(self):
        html = _generate(_photo([]))
        # ヒーローのクレジットは年付きロケール表記（shot_at=2026-06-07 UTC → JST 同日）
        self.assertIn("2026年6月7日", html)
        self.assertIn("📷 いろはす", html)

    def test_hero_credit_falls_back_to_created_at_without_shot_at(self):
        photo = _photo([])
        photo["shot_at"] = None
        photo["created_at"] = "2026-06-08T15:30:00+00:00"  # JST では 6/9
        html = _generate(photo)
        self.assertIn("2026年6月9日", html)

    def test_no_gallery_section_without_items(self):
        html = _generate(_photo([]))
        self.assertNotIn("みんなの写真", html)
        self.assertNotIn("click_gallery_more", html)

    def test_no_gallery_section_without_photo(self):
        html = _generate(None)
        self.assertNotIn("みんなの写真", html)


if __name__ == "__main__":
    unittest.main()
