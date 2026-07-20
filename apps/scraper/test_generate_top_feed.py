import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_top_feed.py")
SPEC = importlib.util.spec_from_file_location("generate_top_feed", MODULE_PATH)
top_feed = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(top_feed)


def _photo(mid: str, created_at: str, **extra) -> dict:
    photo = {
        "manhole_id": mid,
        "created_at": created_at,
        "display_name": "テスト太郎",
        "comment": None,
        "url": f"https://example.com/{mid}.jpeg",
    }
    photo.update(extra)
    return photo


def _record(mid: str, **extra) -> dict:
    record = {
        "id": mid,
        "title": f"鹿児島県/指宿市 {mid}",
        "prefecture": "鹿児島県",
        "city": "指宿市",
        "pokemons": ["イーブイ"],
        "status": "active",
    }
    record.update(extra)
    return record


class SanitizeCommentTests(unittest.TestCase):
    def test_none_and_empty_return_none(self):
        self.assertIsNone(top_feed.sanitize_comment(None))
        self.assertIsNone(top_feed.sanitize_comment(""))
        self.assertIsNone(top_feed.sanitize_comment("   \n  "))

    def test_newlines_collapse_to_single_space(self):
        self.assertEqual(
            top_feed.sanitize_comment("とても\nきれいな\r\n  ポケふた"),
            "とても きれいな ポケふた",
        )

    def test_long_comment_is_truncated_with_ellipsis(self):
        comment = "あ" * 200
        result = top_feed.sanitize_comment(comment)
        self.assertEqual(len(result), top_feed.COMMENT_MAX_LEN)
        self.assertTrue(result.endswith("…"))


class HeroBadgeTests(unittest.TestCase):
    def _title(self, **extra):
        title = {
            "emoji": "🌟",
            "hashtag": "#レアポケふた",
            "key": "rare_pokemon",
            "label": "レアポケふた（全国2枚）",
            "priority": 70,
        }
        title.update(extra)
        return title

    def test_high_priority_title_becomes_badge_with_short_label(self):
        record = _record("1", titles=[self._title()])
        self.assertEqual(
            top_feed.hero_badge(record),
            {"emoji": "🌟", "label": "レアポケふた", "priority": 70},
        )

    def test_priority_below_threshold_is_rejected(self):
        record = _record("1", titles=[self._title(priority=59)])
        self.assertIsNone(top_feed.hero_badge(record))

    def test_generic_tag_priority_is_rejected(self):
        record = _record(
            "1",
            titles=[self._title(hashtag="#観光ポケふた", priority=36)],
        )
        self.assertIsNone(top_feed.hero_badge(record))

    def test_missing_hashtag_is_rejected(self):
        record = _record("1", titles=[self._title(hashtag=None)])
        self.assertIsNone(top_feed.hero_badge(record))

    def test_missing_titles_is_rejected(self):
        self.assertIsNone(top_feed.hero_badge(_record("1")))
        self.assertIsNone(top_feed.hero_badge(_record("1", titles=[])))

    def test_missing_emoji_becomes_empty_string(self):
        record = _record("1", titles=[self._title(emoji=None)])
        badge = top_feed.hero_badge(record)
        self.assertEqual(badge["emoji"], "")


class PhotoCountTests(unittest.TestCase):
    def test_no_gallery_counts_hero_only(self):
        self.assertEqual(top_feed.photo_count_for({}), 1)
        self.assertEqual(top_feed.photo_count_for({"gallery": None}), 1)
        self.assertEqual(top_feed.photo_count_for({"gallery": []}), 1)

    def test_gallery_length_is_the_count(self):
        # gallery は代表写真自身を先頭に含むため len がそのまま枚数
        self.assertEqual(top_feed.photo_count_for({"gallery": [{}, {}]}), 2)
        self.assertEqual(
            top_feed.photo_count_for({"gallery": [{}] * 5}), 5
        )


class PhotoCountCapTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.image_dir = Path(self._tmp.name)
        (self.image_dir / "1_latest.jpeg").write_bytes(b"")

    def _feed(self, gallery_len: int, gallery_limit: int):
        photos = {
            "1": _photo(
                "1",
                "2026-06-01T00:00:00+00:00",
                gallery=[{}] * gallery_len,
            )
        }
        feed = top_feed.build_top_feed(
            {"photos": photos},
            {"1": _record("1")},
            {},
            image_dir=self.image_dir,
            gallery_limit=gallery_limit,
        )
        return feed["photos"][0]

    def test_at_cap_sets_flag(self):
        entry = self._feed(gallery_len=5, gallery_limit=5)
        self.assertEqual(entry["photo_count"], 5)
        self.assertTrue(entry["photo_count_at_cap"])

    def test_below_cap_omits_flag(self):
        entry = self._feed(gallery_len=4, gallery_limit=5)
        self.assertEqual(entry["photo_count"], 4)
        self.assertNotIn("photo_count_at_cap", entry)

    def test_larger_cap_keeps_mid_counts_uncapped(self):
        # キャップが増えても 5 枚が「5+」にならない（クライアントは値を持たない）
        entry = self._feed(gallery_len=5, gallery_limit=10)
        self.assertEqual(entry["photo_count"], 5)
        self.assertNotIn("photo_count_at_cap", entry)


class BuildTopFeedTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.image_dir = Path(self._tmp.name)

    def _touch_image(self, mid: str):
        (self.image_dir / f"{mid}_latest.jpeg").write_bytes(b"")

    def test_empty_photos_yields_empty_list(self):
        feed = top_feed.build_top_feed({}, {}, {}, image_dir=self.image_dir)
        self.assertEqual(feed["photos"], [])
        self.assertEqual(feed["stats"], {})
        self.assertIn("generated_at", feed)

    def test_photos_sorted_by_created_at_desc_and_capped(self):
        photos = {
            str(i): _photo(str(i), f"2026-06-{i:02d}T00:00:00+00:00")
            for i in range(1, 20)
        }
        records = {str(i): _record(str(i)) for i in range(1, 20)}
        for i in range(1, 20):
            self._touch_image(str(i))
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        self.assertEqual(len(feed["photos"]), top_feed.MAX_PHOTOS)
        self.assertEqual(feed["photos"][0]["id"], "19")
        self.assertEqual(feed["photos"][0]["created_at"], "2026-06-19")

    def test_photo_without_local_image_is_excluded(self):
        photos = {
            "1": _photo("1", "2026-06-02T00:00:00+00:00"),
            "2": _photo("2", "2026-06-01T00:00:00+00:00"),
        }
        records = {"1": _record("1"), "2": _record("2")}
        self._touch_image("2")
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        self.assertEqual([p["id"] for p in feed["photos"]], ["2"])

    def test_photo_without_active_record_is_excluded(self):
        photos = {"1": _photo("1", "2026-06-01T00:00:00+00:00")}
        self._touch_image("1")
        feed = top_feed.build_top_feed(
            {"photos": photos}, {}, {}, image_dir=self.image_dir
        )
        self.assertEqual(feed["photos"], [])

    def test_entry_fields_and_pokemon_filter(self):
        photos = {
            "1": _photo(
                "1",
                "2026-06-01T12:34:56+00:00",
                comment="最高の\n一枚でした",
            )
        }
        records = {
            "1": _record("1", pokemons=["イーブイ", "ローカルActs限定", "ピカチュウ"])
        }
        self._touch_image("1")
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        entry = feed["photos"][0]
        self.assertEqual(entry["pokemons"], ["イーブイ", "ピカチュウ"])
        self.assertEqual(entry["comment"], "最高の 一枚でした")
        self.assertEqual(entry["display_name"], "テスト太郎")
        self.assertEqual(entry["created_at"], "2026-06-01")
        self.assertEqual(entry["prefecture"], "鹿児島県")
        self.assertIsNone(entry["public_user_id"])

    def test_created_at_converts_utc_evening_to_next_jst_day(self):
        # UTC 15:30 = JST 翌日 00:30 → JST の日付で焼き込む（[:10] だと1日前にずれる）
        photos = {"1": _photo("1", "2026-06-01T15:30:00+00:00")}
        records = {"1": _record("1")}
        self._touch_image("1")
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        self.assertEqual(feed["photos"][0]["created_at"], "2026-06-02")

    def test_created_at_invalid_value_becomes_empty(self):
        photos = {"1": _photo("1", "not-a-date")}
        records = {"1": _record("1")}
        self._touch_image("1")
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        self.assertEqual(feed["photos"][0]["created_at"], "")

    def test_entry_public_user_id_passed_through_when_present(self):
        photos = {
            "1": _photo(
                "1",
                "2026-06-01T12:34:56+00:00",
                public_user_id="11111111-2222-3333-4444-555555555555",
            )
        }
        records = {"1": _record("1")}
        self._touch_image("1")
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        entry = feed["photos"][0]
        self.assertEqual(
            entry["public_user_id"], "11111111-2222-3333-4444-555555555555"
        )

    def test_badge_and_photo_count_added_only_when_meaningful(self):
        photos = {
            "1": _photo("1", "2026-06-02T00:00:00+00:00", gallery=[{}, {}]),
            "2": _photo("2", "2026-06-01T00:00:00+00:00"),
        }
        records = {
            "1": _record(
                "1",
                titles=[{"emoji": "⭐", "hashtag": "#ここだけ", "priority": 90}],
            ),
            "2": _record("2"),
        }
        self._touch_image("1")
        self._touch_image("2")
        feed = top_feed.build_top_feed(
            {"photos": photos}, records, {}, image_dir=self.image_dir
        )
        rich, plain = feed["photos"]
        self.assertEqual(
            rich["badge"], {"emoji": "⭐", "label": "ここだけ", "priority": 90}
        )
        self.assertEqual(rich["photo_count"], 2)
        self.assertNotIn("photo_count_at_cap", rich)
        # 値が無いエントリにはキー自体を足さない（null を焼き込まない）
        self.assertNotIn("badge", plain)
        self.assertNotIn("photo_count", plain)

    def test_stats_subset_ignores_non_int_values(self):
        site_stats = {
            "manholes": 476,
            "manholes_with_photos": 159,
            "posts": 213,
            "posts_last_7d": 3,
            "success": True,
            "generated_at": "2026-07-06T21:53:47+00:00",
        }
        feed = top_feed.build_top_feed({}, {}, site_stats, image_dir=self.image_dir)
        self.assertEqual(
            feed["stats"],
            {"manholes": 476, "manholes_with_photos": 159, "posts": 213},
        )


if __name__ == "__main__":
    unittest.main()
