import importlib.util
import unittest
from datetime import date
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("photo_caption.py")
SPEC = importlib.util.spec_from_file_location("photo_caption", MODULE_PATH)
pc = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pc)


class ToJstDateTests(unittest.TestCase):
    def test_utc_evening_rolls_over_to_next_jst_day(self):
        # UTC 15:30 = JST 翌日 00:30
        self.assertEqual(
            pc.to_jst_date("2026-07-16T15:30:00+00:00"), date(2026, 7, 17)
        )

    def test_utc_before_15h_stays_same_day(self):
        self.assertEqual(
            pc.to_jst_date("2026-07-16T14:59:59+00:00"), date(2026, 7, 16)
        )

    def test_z_suffix_is_treated_as_utc(self):
        self.assertEqual(pc.to_jst_date("2026-07-16T15:30:00Z"), date(2026, 7, 17))

    def test_date_only_string_is_kept_as_is(self):
        self.assertEqual(pc.to_jst_date("2026-07-16"), date(2026, 7, 16))

    def test_invalid_values_return_none(self):
        self.assertIsNone(pc.to_jst_date(None))
        self.assertIsNone(pc.to_jst_date(""))
        self.assertIsNone(pc.to_jst_date("  "))
        self.assertIsNone(pc.to_jst_date("not-a-date"))
        self.assertIsNone(pc.to_jst_date(12345))


class FormatPhotoDateTests(unittest.TestCase):
    def test_all_languages_short_form(self):
        iso = "2026-07-16T00:00:00+09:00"
        self.assertEqual(pc.format_photo_date(iso, "ja"), "7月16日")
        self.assertEqual(pc.format_photo_date(iso, "en"), "Jul 16")
        self.assertEqual(pc.format_photo_date(iso, "zh-CN"), "7月16日")
        self.assertEqual(pc.format_photo_date(iso, "zh-TW"), "7月16日")
        self.assertEqual(pc.format_photo_date(iso, "ko"), "7월 16일")

    def test_with_year(self):
        iso = "2026-07-16"
        self.assertEqual(
            pc.format_photo_date(iso, "ja", with_year=True), "2026年7月16日"
        )
        self.assertEqual(
            pc.format_photo_date(iso, "en", with_year=True), "Jul 16, 2026"
        )
        self.assertEqual(
            pc.format_photo_date(iso, "ko", with_year=True), "2026년 7월 16일"
        )

    def test_zh_aliases_are_accepted(self):
        self.assertEqual(pc.format_photo_date("2026-07-16", "zh-Hans"), "7月16日")
        self.assertEqual(pc.format_photo_date("2026-07-16", "zh-Hant"), "7月16日")

    def test_unknown_lang_falls_back_to_ja_format(self):
        self.assertEqual(pc.format_photo_date("2026-07-16", "fr"), "7月16日")

    def test_invalid_value_returns_empty(self):
        self.assertEqual(pc.format_photo_date(None), "")
        self.assertEqual(pc.format_photo_date("oops"), "")


class FormatDisplayNameTests(unittest.TestCase):
    def test_short_name_is_unchanged(self):
        self.assertEqual(pc.format_display_name("テスト太郎"), "テスト太郎")

    def test_whitespace_is_collapsed(self):
        self.assertEqual(pc.format_display_name("  ポケ  ふた\n太郎 "), "ポケ ふた 太郎")

    def test_long_name_is_truncated_with_ellipsis(self):
        name = "あ" * 30
        result = pc.format_display_name(name)
        self.assertEqual(len(result), pc.DISPLAY_NAME_MAX_LEN)
        self.assertTrue(result.endswith("…"))

    def test_exactly_max_len_is_not_truncated(self):
        name = "あ" * pc.DISPLAY_NAME_MAX_LEN
        self.assertEqual(pc.format_display_name(name), name)

    def test_non_string_returns_empty(self):
        self.assertEqual(pc.format_display_name(None), "")
        self.assertEqual(pc.format_display_name(123), "")


class PosterProfileUrlTests(unittest.TestCase):
    VALID_UUID = "6096691c-eeda-4e73-8401-a11274868ede"

    def test_valid_uuid_maps_to_public_stamp_book(self):
        self.assertEqual(
            pc.poster_profile_url(self.VALID_UUID),
            f"https://pokefuta.com/users/{self.VALID_UUID}/visits",
        )

    def test_invalid_values_are_not_linked(self):
        for value in (None, "", "not-a-uuid", "../evil", 123):
            with self.subTest(value=value):
                self.assertEqual(pc.poster_profile_url(value), "")


class CaptionMetaTests(unittest.TestCase):
    def test_joins_with_middle_dot(self):
        self.assertEqual(
            pc.caption_meta("北海道斜里町", "テスト太郎", "7月16日"),
            "北海道斜里町 · テスト太郎 · 7月16日",
        )

    def test_empty_and_none_parts_are_skipped(self):
        self.assertEqual(pc.caption_meta("北海道", "", None, "7月16日"), "北海道 · 7月16日")

    def test_all_empty_returns_empty_string(self):
        self.assertEqual(pc.caption_meta("", None), "")


if __name__ == "__main__":
    unittest.main()
