import json
import tempfile
import unittest
from pathlib import Path

from apps.scraper import coord_overrides

OVERRIDES = {
    "64": {"lat": 44.176286, "lng": 142.392808, "official": {"lat": 44.175974, "lng": 142.392417}},
}


class ApplyTest(unittest.TestCase):
    def test_overrides_when_official_unchanged(self):
        records = [{"id": "64", "lat": 44.175974, "lng": 142.392417}, {"id": "1", "lat": 31.2, "lng": 130.6}]
        applied, warnings = coord_overrides.apply(records, OVERRIDES)
        self.assertEqual((applied, warnings), (1, []))
        self.assertEqual((records[0]["lat"], records[0]["lng"]), (44.176286, 142.392808))
        self.assertEqual((records[1]["lat"], records[1]["lng"]), (31.2, 130.6))

    def test_keeps_official_when_official_moved(self):
        records = [{"id": "64", "lat": 44.1763, "lng": 142.3928}]
        applied, warnings = coord_overrides.apply(records, OVERRIDES)
        self.assertEqual(applied, 0)
        self.assertEqual((records[0]["lat"], records[0]["lng"]), (44.1763, 142.3928))
        self.assertEqual(len(warnings), 1)

    def test_second_run_is_quiet(self):
        records = [{"id": "64", "lat": 44.176286, "lng": 142.392808}]
        self.assertEqual(coord_overrides.apply(records, OVERRIDES), (1, []))

    def test_is_applied_only_with_override_coords(self):
        self.assertTrue(coord_overrides.is_applied({"id": "64", "lat": 44.176286, "lng": 142.392808}, OVERRIDES))
        self.assertFalse(coord_overrides.is_applied({"id": "64", "lat": 44.175974, "lng": 142.392417}, OVERRIDES))
        self.assertFalse(coord_overrides.is_applied({"id": "1", "lat": 31.2, "lng": 130.6}, OVERRIDES))

    def test_warns_missing_target(self):
        applied, warnings = coord_overrides.apply([], OVERRIDES)
        self.assertEqual(applied, 0)
        self.assertIn("64", warnings[0])

    def test_dataset_file_is_valid(self):
        # 対象が docs に残っているかは見ない。公式から消えた蓋は apply() が警告するだけにして、
        # 日次の更新（このテストを先に回す）を止めない
        self.assertTrue(coord_overrides.load())

    def test_load_rejects_missing_official(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "o.json"
            p.write_text(json.dumps({"overrides": {"64": {"lat": 1, "lng": 2}}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                coord_overrides.load(p)


if __name__ == "__main__":
    unittest.main()
