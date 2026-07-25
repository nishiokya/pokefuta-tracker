import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_location_research.py")
SPEC = importlib.util.spec_from_file_location("validate_location_research", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Unable to load validator module from {MODULE_PATH}")
research_validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = research_validator
SPEC.loader.exec_module(research_validator)


def valid_record(record_id: str = "44") -> dict:
    return {
        "schema_version": 1,
        "id": record_id,
        "candidate": {
            "building": "候補施設名",
            "tags": ["park", "tourism"],
        },
        "evidence": [
            {
                "url": "https://example.lg.jp/location",
                "source_type": "municipality_official",
                "summary": "自治体が同施設への設置を案内",
                "published_at": None,
                "checked_at": "2026-07-25",
            }
        ],
        "spatial_check": {
            "method": "official_coordinates",
            "distance_m": 4.2,
        },
        "field_confidence": {
            "building": 3,
            "tags": {
                "park": 3,
                "tourism": 2,
            },
        },
        "confidence": 2,
        "decision": "review",
        "issues": [],
    }


class ValidateLocationResearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = research_validator.load_validator()

    def validate_lines(self, lines: list[str]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research.ndjson"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return research_validator.validate_file(path, self.validator)

    def test_valid_record_has_no_issues(self):
        issues = self.validate_lines([json.dumps(valid_record(), ensure_ascii=False)])
        self.assertEqual(issues, [])

    def test_reports_json_error_with_line_and_column(self):
        issues = self.validate_lines(["{"])
        self.assertEqual(issues[0].line, 1)
        self.assertIsNotNone(issues[0].column)
        self.assertIn("invalid JSON", issues[0].message)

    def test_reports_blank_line(self):
        issues = self.validate_lines(
            [json.dumps(valid_record(), ensure_ascii=False), ""]
        )
        self.assertEqual(issues[0].line, 2)
        self.assertIn("blank lines", issues[0].message)

    def test_rejects_unknown_tag(self):
        record = valid_record()
        record["candidate"]["tags"] = ["unknown_tag"]
        record["field_confidence"]["tags"] = {"unknown_tag": 3}
        issues = self.validate_lines([json.dumps(record, ensure_ascii=False)])
        self.assertTrue(any("unknown_tag" in issue.message for issue in issues))

    def test_reports_duplicate_id(self):
        record = json.dumps(valid_record("44"), ensure_ascii=False)
        issues = self.validate_lines([record, record])
        self.assertTrue(any("first seen on line 1" in issue.message for issue in issues))

    def test_accept_requires_confidence_three(self):
        record = valid_record()
        record["decision"] = "accept"
        issues = self.validate_lines([json.dumps(record, ensure_ascii=False)])
        self.assertTrue(
            any(issue.message.startswith("confidence:") for issue in issues)
        )

    def test_requires_at_least_one_evidence_item(self):
        record = valid_record()
        record["evidence"] = []
        issues = self.validate_lines([json.dumps(record, ensure_ascii=False)])
        self.assertTrue(any(issue.message.startswith("evidence:") for issue in issues))

    def test_unresolved_requires_an_issue(self):
        record = valid_record()
        record["decision"] = "unresolved"
        record["confidence"] = 0
        issues = self.validate_lines([json.dumps(record, ensure_ascii=False)])
        self.assertTrue(any(issue.message.startswith("issues:") for issue in issues))


if __name__ == "__main__":
    unittest.main()
