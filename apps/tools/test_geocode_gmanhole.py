import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("geocode_gmanhole.py")
SPEC = importlib.util.spec_from_file_location("geocode_gmanhole", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Unable to load geocoder module from {MODULE_PATH}")
geocoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(geocoder)


class GeocodeGmanholeTest(unittest.TestCase):
    def test_load_overrides_returns_empty_for_missing_file(self):
        self.assertEqual(geocoder.load_overrides(Path("/tmp/does-not-exist.json")), {})

    def test_load_overrides_keys_records_by_string_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            path.write_text(json.dumps({"3": {"status": "active"}}), encoding="utf-8")
            self.assertEqual(geocoder.load_overrides(path), {"3": {"status": "active"}})

    def test_full_address_does_not_duplicate_prefecture_and_city(self):
        self.assertEqual(
            geocoder.ensure_full_address(
                "北海道天塩郡天塩町新開通4丁目7227番地の2",
                "北海道",
                "天塩町",
            ),
            "北海道天塩郡天塩町新開通4丁目7227番地の2",
        )

    def test_missing_prefecture_and_city_are_added(self):
        self.assertEqual(
            geocoder.ensure_full_address("打出浜15", "滋賀県", "大津市"),
            "滋賀県大津市打出浜15",
        )

    def test_normalize_keeps_japanese_prolonged_sound_mark(self):
        self.assertEqual(
            geocoder.normalize("ロープウェー商店街"),
            "ロープウェー商店街",
        )

    def test_gsi_queries_include_numberless_and_title_locality_fallbacks(self):
        queries = geocoder.gsi_queries(
            {
                "prefecture": "兵庫県",
                "city": "姫路市",
                "title": "大手前通り 西二階町入口",
            },
            "兵庫県姫路市大手前通り 西二階町入口",
        )
        self.assertIn(("title_locality", "兵庫県姫路市西二階町"), queries)

        numberless = geocoder.gsi_queries(
            {"prefecture": "滋賀県", "city": "大津市", "title": "打出の森"},
            "滋賀県大津市打出浜15",
        )
        self.assertIn(("address_without_number", "滋賀県大津市打出浜"), numberless)

    def test_gsi_candidate_wins_over_unrelated_nominatim_place(self):
        gsi = {
            "provider": "gsi",
            "strategy": "official_address",
            "score": 82,
        }
        nominatim = {
            "provider": "nominatim",
            "strategy": "place_name",
            "score": 98,
        }
        selected, reason = geocoder.select_candidate([nominatim, gsi])
        self.assertIs(selected, gsi)
        self.assertIn("GSI", reason)

    def test_precise_yahoo_address_wins_over_gsi(self):
        yahoo = {
            "provider": "yahoo",
            "strategy": "official_address",
            "rank": 1,
            "score": 99,
            "matching_level": 6,
        }
        gsi = {
            "provider": "gsi",
            "strategy": "official_address",
            "score": 82,
        }
        selected, reason = geocoder.select_candidate([gsi, yahoo])
        self.assertIs(selected, yahoo)
        self.assertIn("Yahoo", reason)

    def test_coarse_yahoo_address_does_not_override_gsi(self):
        yahoo = {
            "provider": "yahoo",
            "strategy": "official_address",
            "rank": 1,
            "score": 80,
            "matching_level": 2,
        }
        gsi = {
            "provider": "gsi",
            "strategy": "official_address",
            "score": 82,
        }
        selected, _ = geocoder.select_candidate([yahoo, gsi])
        self.assertIs(selected, gsi)

    def test_second_yahoo_candidate_does_not_override_gsi(self):
        yahoo = {
            "provider": "yahoo",
            "strategy": "official_address",
            "rank": 2,
            "score": 99,
            "matching_level": 6,
        }
        gsi = {
            "provider": "gsi",
            "strategy": "official_address",
            "score": 82,
        }
        selected, _ = geocoder.select_candidate([yahoo, gsi])
        self.assertIs(selected, gsi)

    def test_manual_coordinate_override_wins_and_preserves_status_metadata(self):
        record = {"id": "3", "status": "active"}
        candidates = []
        selected, reason = geocoder.apply_override(
            record,
            {
                "status": "active",
                "installation_status": "installed",
                "lat": 44.87680906,
                "lng": 141.74445238,
                "verified_at": "2026-06-14",
                "official_url": "https://example.com/source",
                "note": "施設位置を確認",
            },
            candidates,
            None,
            "候補なし",
        )
        self.assertEqual(selected["provider"], "manual")
        self.assertEqual(selected["strategy"], "verified_override")
        self.assertEqual(selected["lat"], 44.87680906)
        self.assertEqual(selected["query"], "https://example.com/source")
        self.assertEqual(candidates, [selected])
        self.assertEqual(record["installation_status"], "installed")
        self.assertEqual(record["official_url"], "https://example.com/source")
        self.assertIn("手動管理", reason)

    def test_status_only_override_keeps_geocoder_selection(self):
        record = {"id": "51", "status": "active"}
        geocoded = {"provider": "gsi", "lat": 34.8, "lng": 134.6}
        selected, reason = geocoder.apply_override(
            record,
            {
                "status": "active",
                "installation_status": "installed",
                "installed_at": "2025-09-10",
            },
            [],
            geocoded,
            "GSI候補を採用",
        )
        self.assertIs(selected, geocoded)
        self.assertEqual(reason, "GSI候補を採用")
        self.assertEqual(record["installed_at"], "2025-09-10")


if __name__ == "__main__":
    unittest.main()
