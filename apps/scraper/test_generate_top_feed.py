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
