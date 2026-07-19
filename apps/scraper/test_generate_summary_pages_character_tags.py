import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_summary_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_summary_pages", MODULE_PATH)
summary = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(summary)

CHARACTER_KEYS = ("near_character_manhole", "character_manhole_city")


class CharacterManholeTravelCopyTest(unittest.TestCase):
    def test_all_languages_have_character_travel_labels(self):
        for lang, strings in summary.SUMMARY_STRINGS.items():
            travel = strings.get("discovery_hubs", {}).get("travel", {})
            for key in CHARACTER_KEYS:
                with self.subTest(lang=lang, key=key):
                    self.assertIn(key, travel)
                    self.assertTrue(travel[key].strip())

    def test_japanese_labels_match_vocabulary(self):
        travel = summary.SUMMARY_STRINGS["ja"]["discovery_hubs"]["travel"]
        self.assertEqual(
            travel["near_character_manhole"], "キャラクターマンホールまで約1km以内"
        )
        self.assertEqual(
            travel["character_manhole_city"], "キャラクターマンホールのあるまち"
        )

    def test_travel_keys_include_character_keys(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('"near_character_manhole",\n        "character_manhole_city",', source)


if __name__ == "__main__":
    unittest.main()
