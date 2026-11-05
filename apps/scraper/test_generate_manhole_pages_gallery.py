import importlib.util
import re
import tempfile
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

    def test_hero_photo_is_eager_but_gallery_thumbs_stay_lazy(self):
        """ヒーロー写真は LCP 要素なので lazy にしない。

        キャラマンホールLPでは同じ方針が
        test_generate_character_manhole_page.py で既に固定されているのに、
        詳細ページのヒーローだけがそこから漏れていた。
        """
        gallery_local = [
            {
                "url": f"{pages.BASE_URL}manhole/image/1_abcd1234.jpeg",
                "display_name": "たこ",
                "shot_at": "2026-05-01T00:00:00+00:00",
            },
        ]
        html = _generate(_photo(gallery_local))

        hero = html[html.index("<div class='hero-photo'>"):html.index("みんなの写真")]
        self.assertIn('loading="eager"', hero)
        self.assertIn('fetchpriority="high"', hero)
        self.assertNotIn('loading="lazy"', hero)
        # サムネ側は lazy のまま（ヒーローだけを eager にした）
        self.assertIn('loading="lazy"', html[html.index("みんなの写真"):])

    def test_thumbs_reserve_their_size(self):
        html = _generate(_photo([{"url": f"{pages.BASE_URL}manhole/image/1_abcd1234.webp"}]))
        self.assertIn('width="360" height="360" loading="lazy" decoding="async"', html)
        # height 属性があると CSS で高さを auto にしない限り 360px の縦長になる（aspect-ratio が効かない）
        rule = re.search(r"\.gallery-item img \{([^}]*)\}", html).group(1)
        self.assertIn("height: auto", rule)
        self.assertIn("aspect-ratio: 1 / 1", rule)

    def test_more_link_tells_how_many_photos_the_studio_has(self):
        gallery_local = [{"url": f"{pages.BASE_URL}manhole/image/1_abcd123{i}.webp"} for i in range(3)]
        photo = _photo(gallery_local)
        photo["public_photo_count"] = 21
        self.assertIn("写真館で全 21 枚を見る →", _generate(photo))
        # 代表＋3枚で全部出しているときは枚数を出さない
        photo["public_photo_count"] = 4
        html = _generate(photo)
        self.assertIn("すべての写真を見る →", html)
        self.assertNotIn("写真館で全", html)

    def test_no_gallery_section_without_items(self):
        html = _generate(_photo([]))
        self.assertNotIn("みんなの写真", html)
        self.assertNotIn("click_gallery_more", html)

    def test_no_gallery_section_without_photo(self):
        html = _generate(None)
        self.assertNotIn("みんなの写真", html)


class PagePhotoGalleryFilesTests(unittest.TestCase):
    """ギャラリー画像は .webp。前の形式の .jpeg は取り込みが作り直すまでの間だけ使う"""

    def _page_photo(self, files: list[str]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            for name in files:
                (image_dir / name).write_bytes(b"")
            photos = {"1": {"photo_id": "rep11111-0000", "gallery": [
                {"photo_id": "rep11111-0000"},
                {"photo_id": "abcd1234-0000"},
                {"photo_id": "ef012345-0000"},
                {"photo_id": "99999999-0000"},
            ]}}
            return pages.page_photo("1", photos, image_dir, {"1": f"{pages.BASE_URL}manhole/image/1_latest.jpeg"})

    def test_prefers_webp_and_falls_back_to_jpeg(self):
        photo = self._page_photo(["1_abcd1234.webp", "1_abcd1234.jpeg", "1_ef012345.jpeg"])
        self.assertEqual(
            [g["url"] for g in photo["gallery_local"]],
            [f"{pages.BASE_URL}manhole/image/1_abcd1234.webp", f"{pages.BASE_URL}manhole/image/1_ef012345.jpeg"],
        )


if __name__ == "__main__":
    unittest.main()
