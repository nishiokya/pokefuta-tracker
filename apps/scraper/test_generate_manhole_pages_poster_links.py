import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)
# アイコンと称号は docs/api の実データに左右されないよう空にしておく（poster_identity.py）
import sys  # noqa: E402
sys.modules["poster_identity"].set_sources({}, {})
NO_AVATAR = "<span class='poster-avatar' aria-hidden='true'></span>"

VALID_UUID = "6096691c-eeda-4e73-8401-a11274868ede"
PROFILE_URL = f"https://pokefuta.com/users/{VALID_UUID}/visits"


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


def _photo(public_user_id=None, gallery_local: list[dict] | None = None) -> dict:
    local_url = f"{pages.BASE_URL}manhole/image/1_latest.jpeg"
    return {
        "photo_id": "rep11111-0000",
        "url": local_url,
        "original_url": local_url,
        "display_name": "いろはす",
        "public_user_id": public_user_id,
        "shot_at": "2026-06-07T00:00:00+00:00",
        "comment": None,
        "gallery_local": gallery_local or [],
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


class PosterProfileUrlTests(unittest.TestCase):
    def test_valid_uuid(self):
        self.assertEqual(pages.poster_profile_url(VALID_UUID), PROFILE_URL)

    def test_uppercase_and_whitespace(self):
        self.assertEqual(
            pages.poster_profile_url(f" {VALID_UUID.upper()} "),
            f"https://pokefuta.com/users/{VALID_UUID.upper()}/visits",
        )

    def test_invalid_values_return_empty(self):
        for value in (None, "", "not-a-uuid", "../evil", "x' onmouseover='alert(1)", 123):
            with self.subTest(value=value):
                self.assertEqual(pages.poster_profile_url(value), "")


class HeroCreditLinkTests(unittest.TestCase):
    def test_hero_credit_linked_with_valid_public_user_id(self):
        html = _generate(_photo(public_user_id=VALID_UUID))
        self.assertIn(f"<a class='poster-link' href='{PROFILE_URL}'", html)
        self.assertIn(NO_AVATAR + "いろはす</a>", html)
        self.assertIn("click_poster_profile", html)
        self.assertIn("&quot;surface&quot;: &quot;hero&quot;", html)

    def test_hero_credit_plain_text_without_public_user_id(self):
        html = _generate(_photo(public_user_id=None))
        self.assertIn("<span>" + NO_AVATAR + "いろはす</span>", html)
        self.assertNotIn("poster-link", html.replace("a.poster-link", ""))  # CSS 定義は除外
        self.assertNotIn("click_poster_profile", html)

    def test_hero_credit_plain_text_with_invalid_public_user_id(self):
        html = _generate(_photo(public_user_id="../evil"))
        self.assertIn("<span>" + NO_AVATAR + "いろはす</span>", html)
        self.assertNotIn("click_poster_profile", html)
        self.assertNotIn("/users/", html)


class GalleryCreditLinkTests(unittest.TestCase):
    def test_gallery_credit_linked_with_valid_public_user_id(self):
        gallery_local = [
            {
                "url": f"{pages.BASE_URL}manhole/image/1_abcd1234.jpeg",
                "display_name": "たこ",
                "shot_at": "2026-05-01T00:00:00+00:00",
                "public_user_id": VALID_UUID,
            },
        ]
        html = _generate(_photo(gallery_local=gallery_local))
        self.assertIn(f"<a class='gallery-credit poster-link' href='{PROFILE_URL}'", html)
        self.assertIn(NO_AVATAR + "たこ · 5月1日</a>", html)
        self.assertIn("&quot;surface&quot;: &quot;gallery&quot;", html)

    def test_gallery_credit_plain_text_without_public_user_id(self):
        gallery_local = [
            {
                "url": f"{pages.BASE_URL}manhole/image/1_abcd1234.jpeg",
                "display_name": "たこ",
                "shot_at": "2026-05-01T00:00:00+00:00",
            },
        ]
        html = _generate(_photo(gallery_local=gallery_local))
        self.assertIn("<span class='gallery-credit'>" + NO_AVATAR + "たこ · 5月1日</span>", html)
        self.assertNotIn("gallery-credit poster-link", html)


class PhotoStudioLinkCardTests(unittest.TestCase):
    def test_photo_studio_card_always_rendered(self):
        for photo in (None, _photo(public_user_id=VALID_UUID)):
            with self.subTest(has_photo=photo is not None):
                html = _generate(photo)
                self.assertIn("ポケふた写真館", html)
                self.assertIn("href='https://pokefuta.com/manhole/1'", html)
                self.assertIn("click_photo_studio", html)


if __name__ == "__main__":
    unittest.main()


class PosterAvatarAndTierTests(unittest.TestCase):
    """投稿者名の前に選んだアイコン、後ろに称号（poster_identity.py）"""

    PHOTO_ID = "0c0c0c0c-1111-4222-8333-444444444444"

    def setUp(self):
        sys.modules["poster_identity"].set_sources({VALID_UUID: self.PHOTO_ID}, {VALID_UUID: "legend"})

    def tearDown(self):
        sys.modules["poster_identity"].set_sources({}, {})

    def test_hero_credit_has_avatar_before_name_and_tier_after(self):
        html = _generate(_photo(public_user_id=VALID_UUID))
        avatar = f"https://pokefuta.com/api/photo/{self.PHOTO_ID}?size=small&amp;strict=1"
        self.assertIn(f"<img src=\"{avatar}\"", html)
        self.assertRegex(html, r"poster-avatar'[^\n]*</span>いろはす</a></span><span class='poster-tier poster-tier--legend'>🏆 LEGEND</span>")
        self.assertNotIn("📷 いろはす", html)

    def test_gallery_credit_has_icon_only_tier(self):
        gallery_local = [
            {
                "url": f"{pages.BASE_URL}manhole/image/1_abcd1234.jpeg",
                "display_name": "たこ",
                "shot_at": "2026-05-01T00:00:00+00:00",
                "public_user_id": VALID_UUID,
            },
        ]
        html = _generate(_photo(gallery_local=gallery_local))
        self.assertIn("たこ<span class='poster-tier poster-tier--icon poster-tier--legend' title=\"LEGEND\" aria-label=\"LEGEND\">🏆</span> · 5月1日</a>", html)

    def test_no_avatar_or_tier_for_unknown_user(self):
        sys.modules["poster_identity"].set_sources({}, {})
        html = _generate(_photo(public_user_id=VALID_UUID))
        self.assertIn(NO_AVATAR + "いろはす</a>", html)
        self.assertNotIn("poster-tier--", html.split("</style>")[-1])
