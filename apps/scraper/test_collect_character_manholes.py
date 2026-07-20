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

    def test_public_map_reads_marker_style_from_records(self):
        source = (ROOT / "apps/web/gmanhole_map.html").read_text(encoding="utf-8")

        self.assertIn("markerColor(record)", source)
        self.assertIn("markerLabel(record)", source)
        self.assertNotIn("const WORK_COLORS", source)


if __name__ == "__main__":
    unittest.main()
