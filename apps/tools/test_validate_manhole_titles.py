import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_manhole_titles.py")
TOOLS_PATH = str(MODULE_PATH.parent)
if TOOLS_PATH not in sys.path:
    sys.path.insert(0, TOOLS_PATH)
SPEC = importlib.util.spec_from_file_location("validate_manhole_titles", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Unable to load validator module from {MODULE_PATH}")
titles_validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = titles_validator
SPEC.loader.exec_module(titles_validator)


def valid_master() -> dict:
    return {
        "version": 2,
        "vocabulary": {},
        "islands": [],
        "lakes": [],
        "city_links": [],
        "manholes": {
            "1": {
                "building": "中央公園",
                "verified_at": "2026-07-25",
                "tags": ["park"],
                "confidence": 3,
                "official_url": "https://example.lg.jp/location",
            }
        },
    }


class ValidateManholeTitlesTest(unittest.TestCase):
    def validate_data(self, data: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manhole_titles.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return titles_validator.validate(path)

    def test_repository_master_is_valid(self):
        self.assertEqual(titles_validator.validate(titles_validator.DEFAULT_DATA), [])

    def test_valid_minimal_master(self):
        self.assertEqual(self.validate_data(valid_master()), [])

    def test_rejects_unknown_tag(self):
        data = valid_master()
        data["manholes"]["1"]["tags"] = ["unknown_tag"]
        messages = self.validate_data(data)
        self.assertTrue(any("unknown_tag" in message for message in messages))

    def test_rejects_unknown_manhole_field(self):
        data = valid_master()
        data["manholes"]["1"]["unexpected"] = True
        messages = self.validate_data(data)
        self.assertTrue(any("unexpected" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
