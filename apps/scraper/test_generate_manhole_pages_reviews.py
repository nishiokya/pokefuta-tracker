"""詳細ページの「口コミから」チップと「訪れた人のひとこと」（manhole_reviews.py）。名前・本文は作り物。"""
import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)
sys.modules["poster_identity"].set_sources({}, {})

UID = "11111111-1111-4111-8111-111111111111"


def _manhole(**extra) -> dict:
    return {
        "id": "1", "prefecture": "鹿児島県", "city": "指宿", "address": "鹿児島県指宿市湊1丁目1-1",
        "lat": 31.237194, "lng": 130.642861, "pokemons": ["イーブイ"], "titles": [], "tags": [], **extra,
    }


def _photo() -> dict:
    url = f"{pages.BASE_URL}manhole/image/1_latest.jpeg"
    return {
        "photo_id": "rep-photo", "url": url, "original_url": url, "display_name": "テスト花子",
        "shot_at": "2026-06-07T00:00:00+00:00", "comment": "ヒーローのひとこと",
        "gallery_local": [{"photo_id": "gal-photo", "url": f"{pages.BASE_URL}manhole/image/1_abcd1234.webp"}],
    }


def _review(comment, shot_at="2026-10-01T00:00:00+00:00", photo_ids=None):
    return {"comment": comment, "display_name": "テスト太郎", "public_user_id": UID,
            "shot_at": shot_at, "created_at": shot_at, "photo_ids": photo_ids or []}


def _generate(reviews, manhole=None, photo="default") -> str:
    return pages.generate_html(
        manhole=manhole or _manhole(), photo=_photo() if photo == "default" else photo, pokemon_meta={},
        nearby=[], same_pref=[], pref_total=0, same_pokemon=[], id_to_image_url={}, reviews=reviews,
    )


class ReviewsSectionTests(unittest.TestCase):
    def test_without_review_data_the_page_is_unchanged(self):
        html = _generate(None)
        self.assertNotIn("id='reviews'", html)
        self.assertNotIn("<dt>口コミから</dt>", html)
        self.assertIn("ヒーローのひとこと", html)

    def test_reviews_render_newest_first_with_credit_and_photo(self):
        html = _generate([
            _review("駅前交番の横。駐車場あり", shot_at="2026-11-02T00:00:00+00:00", photo_ids=["gal-photo"]),
            _review("見つけにくい", shot_at="2026-01-01T00:00:00+00:00"),
        ])
        section = html[html.index("id='reviews'"):]
        self.assertLess(section.index("駅前交番の横"), section.index("見つけにくい"))
        self.assertIn("1_abcd1234.webp", section)
        self.assertIn(f"https://pokefuta.com/users/{UID}/visits", section)
        self.assertIn("2026年11月2日", section)
        # ひとことはこの欄にまとめ、ヒーローには重ねない
        self.assertNotIn("<div class='photo-comment'>", html)

    def test_chips_show_basis_and_link_to_reviews(self):
        html = _generate([_review("駐車場あり", shot_at="2026-11-02T00:00:00+00:00"), _review("駐車場あり。駅前")])
        location = html[html.index("<h2>設置場所</h2>"):html.index("id='reviews'")]
        self.assertIn("口コミから", location)
        self.assertIn("🅿️ 駐車場あり<span class='tip-basis'>口コミ2件・2026/11</span>", location)
        self.assertIn("href='#reviews'", location)
        self.assertNotIn("駐車場の情報がまだありません", html)

    def test_more_link_when_over_limit(self):
        html = _generate([_review(f"ひとこと{i}番目です", shot_at=f"2026-0{i}-01T00:00:00+00:00") for i in range(1, 8)])
        self.assertEqual(html.count("class='review-item'"), 5)
        self.assertIn("ひとこと全7件を写真館で見る", html)
        self.assertIn("click_reviews_more", html)

    def test_empty_state_still_asks_for_the_first_tip(self):
        html = _generate([])
        self.assertIn("まだひとことがありません", html)
        self.assertIn("駐車場の情報がまだありません", html)
        self.assertIn("https://pokefuta.com/upload?manhole_id=1&amp;from=data", html)
        self.assertIn("click_review_cta", html)
        self.assertIn("投稿済みの写真にひとことを足す", html)

    def test_comment_is_escaped(self):
        html = _generate([_review("<script>alert(1)</script>駅前")])
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)

    def test_preinstall_has_no_review_section(self):
        html = _generate([_review("駅前")], manhole=_manhole(installed=False), photo=None)
        self.assertNotIn("id='reviews'", html)
        # セクションが無いのでチップ（#reviews へのリンク）も出さない（PR #929 の Copilot レビュー）
        self.assertNotIn("<dt>口コミから</dt>", html)
        self.assertNotIn("href='#reviews'", html)


if __name__ == "__main__":
    unittest.main()
