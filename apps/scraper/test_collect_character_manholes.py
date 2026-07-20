import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("collect_character_manholes.py")
SPEC = importlib.util.spec_from_file_location("collect_character_manholes", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {MODULE_PATH}")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class CharacterManholeCollectorTests(unittest.TestCase):
    def test_aichi_ndjson_is_loaded_as_manual_source(self):
        records = collector.collect_ndjson(
            {"path": "dataset/aichi_character_manholes.ndjson"}
        )

        self.assertEqual(len(records), 15)
        self.assertEqual(
            {record["work"] for record in records},
            {"東海オンエア", "アイドルマスター シンデレラガールズ"},
        )

    def test_marker_style_is_added_from_work(self):
        record = collector.apply_marker_style({"work": "東海オンエア"})

        self.assertEqual(record["marker_label"], "東")
        self.assertEqual(record["marker_color"], "#14b8a6")

    def test_manual_marker_style_is_preserved(self):
        record = collector.apply_marker_style(
            {
                "work": "東海オンエア",
                "marker_label": "岡",
                "marker_color": "#123456",
            }
        )

        self.assertEqual(record["marker_label"], "岡")
        self.assertEqual(record["marker_color"], "#123456")

    def test_generated_dataset_contains_aichi_and_marker_styles(self):
        records = [
            json.loads(line)
            for line in (ROOT / "docs/character_manholes.ndjson")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]

        self.assertEqual(len(records), 123)
        self.assertEqual(
            len([record for record in records if record["prefecture"] == "愛知県"]),
            15,
        )
        self.assertTrue(all(record.get("marker_label") for record in records))
        self.assertTrue(all(record.get("marker_color") for record in records))

    def test_first_seen_survives_regeneration(self):
        """再生成で first_seen が書き換わると全レコードが差分になる。"""
        existing = {"zls-1": {"id": "zls-1", "address": "佐賀県佐賀市唐人二丁目",
                              "first_seen": "2026-07-05T06:05:21Z",
                              "last_updated": "2026-07-05T06:05:21Z"}}
        fresh = [{"id": "zls-1", "address": "佐賀県佐賀市唐人二丁目",
                  "first_seen": "2026-07-20T00:00:00Z",
                  "last_updated": "2026-07-20T00:00:00Z"}]

        merged = collector.merge_with_existing(fresh, existing)

        self.assertEqual(merged[0]["first_seen"], "2026-07-05T06:05:21Z")

    def test_unchanged_record_keeps_last_updated(self):
        """中身が変わっていない再実行は差分ゼロであるべき。"""
        existing = {"zls-1": {"id": "zls-1", "city": "佐賀市",
                              "first_seen": "2026-07-05T06:05:21Z",
                              "last_updated": "2026-07-05T06:05:21Z"}}
        fresh = [{"id": "zls-1", "city": "佐賀市",
                  "first_seen": "2026-07-20T00:00:00Z",
                  "last_updated": "2026-07-20T00:00:00Z"}]

        merged = collector.merge_with_existing(fresh, existing)

        self.assertEqual(merged[0], existing["zls-1"])

    def test_changed_record_bumps_last_updated(self):
        existing = {"zls-1": {"id": "zls-1", "city": "佐賀市",
                              "first_seen": "2026-07-05T06:05:21Z",
                              "last_updated": "2026-07-05T06:05:21Z"}}
        fresh = [{"id": "zls-1", "city": "鹿嶋市",
                  "first_seen": "2026-07-20T00:00:00Z",
                  "last_updated": "2026-07-20T00:00:00Z"}]

        merged = collector.merge_with_existing(fresh, existing)

        self.assertEqual(merged[0]["city"], "鹿嶋市")
        self.assertEqual(merged[0]["last_updated"], "2026-07-20T00:00:00Z")
        self.assertEqual(merged[0]["first_seen"], "2026-07-05T06:05:21Z")

    def test_no_geocode_does_not_blank_existing_address(self):
        """--no-geocode 時に address が空で返っても既存値を消さない。"""
        existing = {"zls-1": {"id": "zls-1", "prefecture": "佐賀県", "city": "佐賀市",
                              "address": "佐賀県佐賀市唐人二丁目",
                              "first_seen": "2026-07-05T06:05:21Z",
                              "last_updated": "2026-07-05T06:05:21Z"}}
        fresh = [{"id": "zls-1", "prefecture": "佐賀県", "city": "", "address": "",
                  "first_seen": "2026-07-20T00:00:00Z",
                  "last_updated": "2026-07-20T00:00:00Z"}]

        merged = collector.merge_with_existing(fresh, existing)

        self.assertEqual(merged[0]["address"], "佐賀県佐賀市唐人二丁目")
        self.assertEqual(merged[0]["city"], "佐賀市")
        self.assertEqual(merged[0]["last_updated"], "2026-07-05T06:05:21Z")

    def test_no_geocode_does_not_overwrite_with_worse_values(self):
        """逆ジオ無しの住所/市区町村は捏造・誤りを含むので既存値を優先する。"""
        existing = {"chibimaruko-1": {"id": "chibimaruko-1", "city": "静岡市葵区",
                                      "address": "静岡県静岡市　葵区追手町",
                                      "first_seen": "2026-07-05T06:06:18Z",
                                      "last_updated": "2026-07-05T06:06:18Z"}}
        fresh = [{"id": "chibimaruko-1", "city": "静岡市葵区",
                  "address": "静岡県静岡市葵区静岡市歴史博物館",
                  "first_seen": "2026-07-20T00:00:00Z",
                  "last_updated": "2026-07-20T00:00:00Z"}]

        merged = collector.merge_with_existing(fresh, existing, no_geocode=True)

        self.assertEqual(merged[0], existing["chibimaruko-1"])

    def test_geocoded_run_may_update_address(self):
        """逆ジオを実行した回は住所の更新を通す (no_geocode との非対称性)。"""
        existing = {"zls-1": {"id": "zls-1", "address": "佐賀県佐賀市唐人二丁目",
                              "first_seen": "2026-07-05T06:05:21Z",
                              "last_updated": "2026-07-05T06:05:21Z"}}
        fresh = [{"id": "zls-1", "address": "佐賀県佐賀市唐人一丁目",
                  "first_seen": "2026-07-20T00:00:00Z",
                  "last_updated": "2026-07-20T00:00:00Z"}]

        merged = collector.merge_with_existing(fresh, existing, no_geocode=False)

        self.assertEqual(merged[0]["address"], "佐賀県佐賀市唐人一丁目")
        self.assertEqual(merged[0]["last_updated"], "2026-07-20T00:00:00Z")

    def test_new_record_is_passed_through(self):
        merged = collector.merge_with_existing(
            [{"id": "imas-20th-machida-loco", "address": "東京都町田市原町田6丁目",
              "first_seen": "2026-07-20T00:00:00Z",
              "last_updated": "2026-07-20T00:00:00Z"}],
            {},
        )

        self.assertEqual(merged[0]["first_seen"], "2026-07-20T00:00:00Z")

    def test_public_map_reads_marker_style_from_records(self):
        source = (ROOT / "apps/web/gmanhole_map.html").read_text(encoding="utf-8")

        self.assertIn("markerColor(record)", source)
        self.assertIn("markerLabel(record)", source)
        self.assertNotIn("const WORK_COLORS", source)


if __name__ == "__main__":
    unittest.main()
