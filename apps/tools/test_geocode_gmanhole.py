import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("geocode_gmanhole.py")
SPEC = importlib.util.spec_from_file_location("geocode_gmanhole", MODULE_PATH)
geocoder = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(geocoder)


class GeocodeGmanholeTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
